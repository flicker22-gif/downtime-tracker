"""CSV 批量导入：解析、逐行预检、事务化确认写入。

设计要点：
- 文件内容 sha256 作为批次唯一键，同一文件重复上传命中已有批次（幂等）；
- 预检结果落 import_batch/import_row 暂存表，不进入 downtime_event，统计不可见；
- 确认时在单事务内重新校验并批量写入，任何不可修正错误整体回滚；
- 外部事件号（external_event_no）跨文件唯一：内容一致判重复（跳过），不一致判冲突。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .numbering import lock_event_numbering, next_event_nos

MAX_IMPORT_ROWS = 10000          # 单文件最大数据行
MAX_FILE_BYTES = 20 * 1024 * 1024  # 单文件最大 20MB
CHUNK_SIZE = 500                 # 大文件分批写入/落库的批大小

VALID_SHIFTS = {"白班", "夜班"}

# 列名 -> 可接受的表头（设备日志导出常见为中英文混合）
FIELD_ALIASES: dict[str, list[str]] = {
    "external_event_no": ["external_event_no", "外部事件号", "外部编号", "外部单号"],
    "line_code": ["line_code", "产线编码", "产线代码", "产线"],
    "equipment_code": ["equipment_code", "设备编码", "设备代码", "设备"],
    "reason_code": ["reason_code", "原因编码", "原因代码", "停机原因编码"],
    "start_time": ["start_time", "开始时间", "停机开始时间"],
    "end_time": ["end_time", "结束时间", "停机结束时间"],
    "duration_min": ["duration_min", "时长", "停机时长", "时长(分钟)", "时长（分钟）"],
    "shift": ["shift", "班次"],
    "reporter": ["reporter", "操作工", "登记人", "报告人"],
    "product": ["product", "工单", "产品", "工单/产品", "工单号"],
    "note": ["note", "备注", "说明"],
}
REQUIRED_FIELDS = ["line_code", "equipment_code", "reason_code", "start_time", "shift", "reporter"]

# 与库内事件比对内容是否一致的字段（判重复/冲突用）
_COMPARE_FIELDS = (
    "line_id", "equipment_id", "reason_id", "start_time", "end_time",
    "duration_min", "shift", "reporter", "product", "note",
)


class ImportError400(Exception):
    """文件级错误（无法解析），对应 HTTP 400。"""


@dataclass
class EvaluatedRow:
    row_no: int
    status: str                     # ok / duplicate / conflict / error
    errors: list[str] = field(default_factory=list)
    payload: dict = field(default_factory=dict)  # 规范化后的行数据


# ---------------------------------------------------------------- 解析


def decode_csv(raw: bytes) -> str:
    """兼容 UTF-8（含 BOM）与 GBK（Excel 导出的中文 CSV）。"""
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportError400("无法识别文件编码，请使用 UTF-8 或 GBK 编码的 CSV")


def parse_csv_text(text: str) -> list[dict[str, str]]:
    """解析为 [{字段: 值}]，表头按别名映射为规范字段名；未知列忽略。"""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportError400("文件为空")

    col_of: dict[int, str] = {}
    for idx, name in enumerate(header):
        key = name.strip().lstrip("\ufeff").lower()
        for field_name, aliases in FIELD_ALIASES.items():
            if key == field_name or name.strip() in aliases:
                col_of[idx] = field_name
                break

    missing = [f for f in REQUIRED_FIELDS if f not in col_of.values()]
    if missing:
        readable = "、".join(missing)
        raise ImportError400(f"缺少必需列：{readable}（支持表头见导入模板）")

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        if not raw_row or all(not c.strip() for c in raw_row):
            continue  # 跳过空行
        rows.append(
            {field: (raw_row[i].strip() if i < len(raw_row) else "") for i, field in col_of.items()}
        )
    if not rows:
        raise ImportError400("文件中没有数据行")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportError400(f"单文件最多导入 {MAX_IMPORT_ROWS} 行，当前 {len(rows)} 行，请拆分后上传")
    return rows


def parse_time(value: str, tz: ZoneInfo) -> datetime:
    """解析时间：无时区按导入时区（默认 Asia/Shanghai）解释，统一返回带时区时间。"""
    v = value.strip()
    if not v:
        raise ValueError("时间为空")
    try:
        dt = datetime.fromisoformat(v)
        return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"时间格式无法解析：{value}")


# ---------------------------------------------------------------- 主数据


class Masters:
    """一次预检/确认内缓存的主数据映射。"""

    def __init__(self, db: Session):
        self.lines = {l.code: l for l in db.scalars(select(models.ProductionLine))}
        line_code_by_id = {l.id: c for c, l in self.lines.items()}
        self.equipments: dict[tuple[str, str], models.Equipment] = {}
        self.equipment_by_code: dict[str, list[models.Equipment]] = {}
        for e in db.scalars(select(models.Equipment)):
            line_code = line_code_by_id.get(e.line_id)
            if line_code:
                self.equipments[(line_code, e.code)] = e
            self.equipment_by_code.setdefault(e.code, []).append(e)
        self.reasons = {r.code: r for r in db.scalars(select(models.DowntimeReason))}


# ---------------------------------------------------------------- 行校验


def validate_row(raw: dict[str, str], masters: Masters, tz: ZoneInfo) -> EvaluatedRow:
    """字段级校验：产线/设备归属、原因编码、时间顺序、班次、时长。"""
    errors: list[str] = []
    p: dict = {
        "external_event_no": raw.get("external_event_no") or None,
        "line_code": raw.get("line_code", ""),
        "equipment_code": raw.get("equipment_code", ""),
        "reason_code": raw.get("reason_code", ""),
        "shift": raw.get("shift", ""),
        "reporter": raw.get("reporter", ""),
        "product": raw.get("product") or None,
        "note": raw.get("note") or None,
        "line_id": None, "equipment_id": None, "reason_id": None,
        "start_time": None, "end_time": None, "duration_min": None,
    }

    if p["external_event_no"] and len(p["external_event_no"]) > 64:
        errors.append("外部事件号超长（最多64字符）")

    line = masters.lines.get(p["line_code"])
    if not p["line_code"]:
        errors.append("产线编码为空")
    elif line is None:
        errors.append(f"产线编码不存在：{p['line_code']}")
    p["line_id"] = line.id if line else None

    eq_code = p["equipment_code"]
    if not eq_code:
        errors.append("设备编码为空")
    elif line is not None:
        eq = masters.equipments.get((p["line_code"], eq_code))
        if eq is None:
            if eq_code in masters.equipment_by_code:
                errors.append(f"设备 {eq_code} 不属于产线 {p['line_code']}")
            else:
                errors.append(f"设备编码不存在：{eq_code}")
        else:
            p["equipment_id"] = eq.id

    reason = masters.reasons.get(p["reason_code"])
    if not p["reason_code"]:
        errors.append("原因编码为空")
    elif reason is None:
        errors.append(f"原因编码不存在：{p['reason_code']}")
    elif not reason.is_active:
        errors.append(f"原因编码已停用：{p['reason_code']}")
    p["reason_id"] = reason.id if reason and reason.is_active else None

    start = end = None
    if not raw.get("start_time"):
        errors.append("开始时间为空")
    else:
        try:
            start = parse_time(raw["start_time"], tz)
            p["start_time"] = start.astimezone(timezone.utc).isoformat()
        except ValueError as e:
            errors.append(str(e))
    if raw.get("end_time"):
        try:
            end = parse_time(raw["end_time"], tz)
            p["end_time"] = end.astimezone(timezone.utc).isoformat()
        except ValueError as e:
            errors.append(str(e))

    duration: int | None = None
    raw_duration = raw.get("duration_min")
    if raw_duration is not None and raw_duration != "":
        try:
            duration = int(raw_duration)
            if duration < 0:
                errors.append("时长不能为负数")
                duration = None
        except (ValueError, TypeError):
            errors.append(f"时长不是有效数字：{raw_duration}")

    if start and end:
        if end < start:
            errors.append("结束时间早于开始时间")
        else:
            computed = round((end - start).total_seconds() / 60)
            if duration is None:
                duration = computed
            elif abs(duration - computed) > 1:
                errors.append(f"时长 {duration} 分钟与起止时间（{computed} 分钟）不一致")
    p["duration_min"] = duration

    if p["shift"] not in VALID_SHIFTS:
        errors.append(f"班次必须是 {'/'.join(sorted(VALID_SHIFTS))}：{p['shift'] or '空'}")

    if not p["reporter"]:
        errors.append("操作工为空")
    elif len(p["reporter"]) > 32:
        errors.append("操作工姓名超长（最多32字符）")
    if p["product"] and len(p["product"]) > 64:
        errors.append("工单/产品超长（最多64字符）")

    return EvaluatedRow(row_no=0, status=models.ROW_OK if not errors else models.ROW_ERROR,
                        errors=errors, payload=p)


def _comparable(payload: dict) -> tuple:
    return tuple(payload.get(k) for k in _COMPARE_FIELDS)


def _event_comparable(e: models.DowntimeEvent) -> tuple:
    def iso(dt: datetime | None) -> str | None:
        return dt.astimezone(timezone.utc).isoformat() if dt else None

    return (
        e.line_id, e.equipment_id, e.reason_id, iso(e.start_time), iso(e.end_time),
        e.duration_min, e.shift, e.reporter, e.product, e.note,
    )


def mark_duplicates(rows: list[EvaluatedRow], db: Session) -> None:
    """标注重复/冲突：文件内部 + 与库内已有事件（按外部事件号）。"""
    ext_nos = {r.payload["external_event_no"] for r in rows if r.payload.get("external_event_no")}
    existing: dict[str, models.DowntimeEvent] = {}
    if ext_nos:
        for e in db.scalars(
            select(models.DowntimeEvent).where(models.DowntimeEvent.external_event_no.in_(ext_nos))
        ):
            existing[e.external_event_no] = e

    seen_in_file: dict[str, EvaluatedRow] = {}
    for row in rows:
        if row.status == models.ROW_ERROR:
            continue
        ext = row.payload.get("external_event_no")
        if not ext:
            continue  # 无外部事件号的历史数据：无法判重，按新事件导入
        mine = _comparable(row.payload)
        if ext in seen_in_file:
            first = seen_in_file[ext]
            if _comparable(first.payload) == mine:
                row.status, row.errors = models.ROW_DUPLICATE, ["与文件内前行内容一致，导入时跳过"]
            else:
                row.status, row.errors = models.ROW_CONFLICT, [f"外部事件号 {ext} 在文件内重复且内容不一致"]
            continue
        seen_in_file[ext] = row
        event = existing.get(ext)
        if event is not None:
            if _event_comparable(event) == mine:
                row.status, row.errors = models.ROW_DUPLICATE, ["数据库已存在相同事件，导入时跳过"]
            else:
                row.status, row.errors = models.ROW_CONFLICT, [f"外部事件号 {ext} 已存在但内容不一致"]


def evaluate_rows(raw_rows: list[dict[str, str]], db: Session) -> list[EvaluatedRow]:
    masters = Masters(db)
    tz = ZoneInfo(settings.import_timezone)
    rows = []
    for i, raw in enumerate(raw_rows, start=1):
        r = validate_row(raw, masters, tz)
        r.row_no = i
        rows.append(r)
    mark_duplicates(rows, db)
    return rows


# ---------------------------------------------------------------- 预检落库


def create_batch(db: Session, filename: str, raw: bytes) -> tuple[models.ImportBatch, bool]:
    """预检并落暂存表。返回 (批次, 是否命中已有批次)。同内容文件幂等。"""
    if len(raw) > MAX_FILE_BYTES:
        raise ImportError400(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB 限制")
    file_hash = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(models.ImportBatch).where(models.ImportBatch.file_hash == file_hash))
    if existing is not None:
        return existing, True

    rows = evaluate_rows(parse_csv_text(decode_csv(raw)), db)
    batch = models.ImportBatch(
        file_hash=file_hash,
        filename=filename or "import.csv",
        status=models.IMPORT_PRECHECKED,
        total_rows=len(rows),
        ok_rows=sum(1 for r in rows if r.status == models.ROW_OK),
        duplicate_rows=sum(1 for r in rows if r.status == models.ROW_DUPLICATE),
        conflict_rows=sum(1 for r in rows if r.status == models.ROW_CONFLICT),
        error_rows=sum(1 for r in rows if r.status == models.ROW_ERROR),
    )
    db.add(batch)
    db.flush()
    for i in range(0, len(rows), CHUNK_SIZE):  # 大文件分批写入暂存表
        db.add_all([
            models.ImportRow(
                batch_id=batch.id,
                row_no=r.row_no,
                external_event_no=r.payload.get("external_event_no"),
                status=r.status,
                errors=json.dumps(r.errors, ensure_ascii=False),
                payload=json.dumps(r.payload, ensure_ascii=False),
            )
            for r in rows[i:i + CHUNK_SIZE]
        ])
        db.flush()
    db.commit()
    return batch, False


# ---------------------------------------------------------------- 确认导入


def confirm_batch(db: Session, batch_id: int) -> models.ImportBatch:
    """事务内批量写入；任何不可修正错误整体回滚。重复确认幂等。"""
    batch = db.get(models.ImportBatch, batch_id)
    if batch is None:
        raise KeyError("导入批次不存在")
    if batch.status == models.IMPORT_COMMITTED:
        return batch  # 幂等：已确认过的批次直接返回原结果

    # 与单条登记共用编号锁：并发确认/登记在此串行化
    lock_event_numbering(db)
    db.refresh(batch)  # 锁内重读：另一并发确认可能已提交
    if batch.status == models.IMPORT_COMMITTED:
        return batch

    staged = db.scalars(
        select(models.ImportRow).where(models.ImportRow.batch_id == batch.id)
        .order_by(models.ImportRow.row_no)
    ).all()
    raw_payloads = [json.loads(r.payload) for r in staged]
    # 以当前库状态重新校验（预检后设备/原因可能变更，外部号可能已被其它批次导入）
    rows = evaluate_rows(raw_payloads, db)
    for r in rows:  # 同步最新预检结论到暂存行
        staged[r.row_no - 1].status = r.status
        staged[r.row_no - 1].errors = json.dumps(r.errors, ensure_ascii=False)

    problems = [r for r in rows if r.status in (models.ROW_ERROR, models.ROW_CONFLICT)]
    if problems:
        detail = [
            {"row_no": r.row_no, "status": r.status, "errors": r.errors} for r in problems[:50]
        ]
        raise ValueError(json.dumps(
            {"message": f"存在 {len(problems)} 行不可导入，已整体回滚", "rows": detail},
            ensure_ascii=False,
        ))

    to_insert = [r for r in rows if r.status == models.ROW_OK]
    duplicates = [r for r in rows if r.status == models.ROW_DUPLICATE]

    imported = 0
    for i in range(0, len(to_insert), CHUNK_SIZE):  # 大文件分批写入
        chunk = to_insert[i:i + CHUNK_SIZE]
        nos = next_event_nos(db, len(chunk))
        events = []
        for no, r in zip(nos, chunk):
            p = r.payload
            events.append(models.DowntimeEvent(
                event_no=no,
                external_event_no=p.get("external_event_no"),
                line_id=p["line_id"], equipment_id=p["equipment_id"], reason_id=p["reason_id"],
                start_time=datetime.fromisoformat(p["start_time"]),
                end_time=datetime.fromisoformat(p["end_time"]) if p.get("end_time") else None,
                duration_min=p.get("duration_min"),
                shift=p["shift"], reporter=p["reporter"],
                product=p.get("product"), note=p.get("note"),
                status=models.STATUS_OPEN,
            ))
        db.add_all(events)
        db.flush()  # 分批 flush，保持事件编号唯一约束即时生效
        for r, e in zip(chunk, events):
            staged[r.row_no - 1].status = models.ROW_OK
            staged[r.row_no - 1].event_id = e.id
        imported += len(events)

    batch.status = models.IMPORT_COMMITTED
    batch.imported_rows = imported
    batch.skipped_rows = len(duplicates)
    batch.ok_rows = len(to_insert)
    batch.duplicate_rows = len(duplicates)
    batch.conflict_rows = 0
    batch.error_rows = 0
    batch.committed_at = datetime.now(timezone.utc)
    db.commit()
    return batch
