"""CSV 批量导入：预检、幂等、事务回滚、并发、编码与时区边界。"""
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func, select

from app import import_service, models
from app.database import SessionLocal

HEADERS = [
    "external_event_no", "line_code", "equipment_code", "reason_code",
    "start_time", "end_time", "duration_min", "shift", "reporter", "product", "note",
]
# 一条完全合法的基准行
BASE_ROW = ["E001", "L1", "P101", "EQ_MECH", "2026-09-10 08:30", "2026-09-10 09:15",
            "45", "白班", "张伟", "WO-1", "测试"]


def make_csv(rows, headers=HEADERS, encoding="utf-8"):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode(encoding)


def upload(client, data, filename="t.csv"):
    return client.post("/api/imports/precheck", files={"file": (filename, data, "text/csv")})


def confirm(client, batch_id):
    return client.post(f"/api/imports/{batch_id}/confirm")


def event_count(db):
    return db.scalar(select(func.count()).select_from(models.DowntimeEvent))


def row(**kw):
    r = list(BASE_ROW)
    for k, v in kw.items():
        r[HEADERS.index(k)] = v
    return r


# ---------------------------------------------------------------- 逐行预检


def test_precheck_validates_each_row(client, db):
    rows = [
        row(external_event_no="V01"),                                    # 合法
        row(external_event_no="V02", line_code="L9"),                    # 产线不存在
        row(external_event_no="V03", line_code="L2", equipment_code="P101"),  # 设备不属于该产线
        row(external_event_no="V04", equipment_code="X999"),             # 设备不存在
        row(external_event_no="V05", reason_code="NOPE"),                # 原因编码不存在
        row(external_event_no="V06", end_time="2026-09-10 08:00", duration_min=""),  # 结束早于开始
        row(external_event_no="V07", shift="中班"),                      # 非法班次
        row(external_event_no="V08", duration_min="-5"),                 # 负时长
        row(external_event_no="V09", duration_min="999"),                # 时长与起止不一致
    ]
    res = upload(client, make_csv(rows))
    assert res.status_code == 201, res.text
    batch = res.json()
    assert (batch["total_rows"], batch["ok_rows"], batch["error_rows"]) == (9, 1, 8)
    assert batch["status"] == "prechecked"

    items = client.get(f"/api/imports/{batch['id']}/rows",
                       params={"status": "error", "page_size": 100}).json()["items"]
    by_no = {i["row_no"]: i for i in items}
    assert "产线编码不存在" in by_no[2]["errors"][0]
    assert "不属于产线" in by_no[3]["errors"][0]
    assert "设备编码不存在" in by_no[4]["errors"][0]
    assert "原因编码不存在" in by_no[5]["errors"][0]
    assert "结束时间早于开始时间" in by_no[6]["errors"][0]
    assert "班次必须" in by_no[7]["errors"][0]
    assert "时长不能为负数" in by_no[8]["errors"][0]
    assert "不一致" in by_no[9]["errors"][0]

    # 预检只写暂存表，统计不可见
    assert event_count(db) == 0
    assert client.get("/api/analytics/pareto").json()["total_count"] == 0


def test_missing_required_column_rejected(client):
    res = upload(client, make_csv([["L1"]], headers=["line_code"]))
    assert res.status_code == 400
    assert "缺少必需列" in res.json()["detail"]


# ---------------------------------------------------------------- 重复 / 冲突


def test_duplicate_and_conflict_against_db(client):
    # 第一批：E100 导入成功
    b1 = upload(client, make_csv([row(external_event_no="E100")])).json()
    assert confirm(client, b1["id"]).json()["imported"] == 1

    # 第二批：E100 内容一致 -> 重复；E101 -> 可导入
    b2 = upload(client, make_csv([
        row(external_event_no="E100"),
        row(external_event_no="E101"),
    ])).json()
    assert (b2["ok_rows"], b2["duplicate_rows"], b2["conflict_rows"]) == (1, 1, 0)

    # 第三批：E100 内容不一致 -> 冲突
    b3 = upload(client, make_csv([row(external_event_no="E100", note="改了内容")])).json()
    assert b3["conflict_rows"] == 1
    item = client.get(f"/api/imports/{b3['id']}/rows").json()["items"][0]
    assert item["status"] == "conflict"
    assert "内容不一致" in item["errors"][0]


def test_in_file_duplicate(client):
    rows = [
        row(external_event_no="E200"),
        row(external_event_no="E200"),                     # 与上一行一致 -> 重复
        row(external_event_no="E201"),
        row(external_event_no="E201", note="不同内容"),  # 不一致 -> 冲突
    ]
    b = upload(client, make_csv(rows)).json()
    assert (b["ok_rows"], b["duplicate_rows"], b["conflict_rows"]) == (2, 1, 1)


# ---------------------------------------------------------------- 确认与幂等


def test_confirm_and_reupload_idempotent(client, db):
    data = make_csv([row(external_event_no="E300"), row(external_event_no="E301")])
    batch = upload(client, data).json()
    res = confirm(client, batch["id"])
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 2

    events = db.scalars(select(models.DowntimeEvent)).all()
    assert len(events) == 2
    assert len({e.event_no for e in events}) == 2  # 事件编号唯一
    assert {e.external_event_no for e in events} == {"E300", "E301"}
    assert all(e.event_no.startswith("DT") for e in events)

    # 同一文件重复上传：命中已有批次，不产生新数据
    again = upload(client, data)
    assert again.json()["deduplicated"] is True
    assert again.json()["id"] == batch["id"]
    assert again.json()["status"] == "committed"

    # 重复确认：幂等，不重复写入
    res2 = confirm(client, batch["id"])
    assert res2.status_code == 200
    assert res2.json()["imported"] == 2
    assert event_count(db) == 2

    # 暂存行回填了事件编号
    items = client.get(f"/api/imports/{batch['id']}/rows").json()["items"]
    assert all(i["event_no"] for i in items)


def test_confirm_rolls_back_on_error_rows(client, db):
    data = make_csv([
        row(external_event_no="E400"),
        row(external_event_no="E401", reason_code="NOPE"),
    ])
    batch = upload(client, data).json()
    assert batch["error_rows"] == 1

    res = confirm(client, batch["id"])
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "整体回滚" in detail["message"]
    assert detail["rows"][0]["row_no"] == 2

    # 整体回滚：合法行也没有写入，批次仍可修正后重新预检
    assert event_count(db) == 0
    assert client.get(f"/api/imports/{batch['id']}").json()["status"] == "prechecked"


def test_confirm_conflict_introduced_after_precheck_rolls_back(client, db):
    # A 预检时 E500 合法；B 抢先导入了内容不同的 E500
    batch_a = upload(client, make_csv([
        row(external_event_no="E500"),
        row(external_event_no="E501"),
    ])).json()
    batch_b = upload(client, make_csv([
        row(external_event_no="E500", note="另一系统的内容"),
    ])).json()
    assert confirm(client, batch_b["id"]).json()["imported"] == 1

    res = confirm(client, batch_a["id"])
    assert res.status_code == 409
    # 整体回滚：A 的 E501 也没有写入
    assert event_count(db) == 1
    assert db.scalars(select(models.DowntimeEvent)
                      .where(models.DowntimeEvent.external_event_no == "E501")).first() is None


def test_concurrent_confirm_same_batch(client, db):
    # 含一行无外部事件号的历史数据：并发确认也不能重复写入
    data = make_csv([
        row(external_event_no="E600"),
        row(external_event_no="", reporter="李四"),
        row(external_event_no="E601"),
    ])
    batch = upload(client, data).json()
    batch_id = batch["id"]

    def run_confirm():
        s = SessionLocal()
        try:
            b = import_service.confirm_batch(s, batch_id)
            return b.status, b.imported_rows  # 会话关闭前取出标量，避免 detached
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _: run_confirm(), range(2)))

    assert all(status == models.IMPORT_COMMITTED for status, _ in results)
    assert all(imported == 3 for _, imported in results)
    assert event_count(db) == 3  # 只写入一次
    events = db.scalars(select(models.DowntimeEvent)).all()
    assert len({e.event_no for e in events}) == 3
    ext = [e.external_event_no for e in events if e.external_event_no]
    assert len(ext) == len(set(ext)) == 2


# ---------------------------------------------------------------- 大文件分批


def test_large_file_chunked_import(client, db):
    n = 2500  # 超过 CHUNK_SIZE 多倍，验证分批写入
    rows = [
        [f"B{i:04d}", "L1" if i % 2 == 0 else "L2",
         "P101" if i % 2 == 0 else "P201", "EQ_MECH",
         "2026-09-10 08:30", "2026-09-10 08:35", "5", "白班", "张伟", "", ""]
        for i in range(n)
    ]
    batch = upload(client, make_csv(rows)).json()
    assert batch["ok_rows"] == n

    res = confirm(client, batch["id"])
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == n
    assert event_count(db) == n
    distinct_nos = db.scalar(select(func.count(func.distinct(models.DowntimeEvent.event_no))))
    assert distinct_nos == n  # 事件编号唯一


# ---------------------------------------------------------------- 编码


def test_encoding_gbk_with_chinese_headers(client):
    headers = ["外部事件号", "产线编码", "设备编码", "原因编码", "开始时间", "结束时间",
               "时长（分钟）", "班次", "操作工", "工单/产品", "备注"]
    rows = [["G001", "L1", "P101", "EQ_MECH", "2026-09-10 08:30", "2026-09-10 09:15",
             "45", "白班", "张伟", "WO-9", "轴承磨损"]]
    res = upload(client, make_csv(rows, headers=headers, encoding="gbk"))
    assert res.status_code == 201, res.text
    batch = res.json()
    assert batch["ok_rows"] == 1
    item = client.get(f"/api/imports/{batch['id']}/rows").json()["items"][0]
    assert item["data"]["reporter"] == "张伟"
    assert item["data"]["note"] == "轴承磨损"


def test_encoding_utf8_bom(client):
    data = make_csv([row(external_event_no="G002")], encoding="utf-8-sig")
    res = upload(client, data)
    assert res.status_code == 201, res.text
    assert res.json()["ok_rows"] == 1


# ---------------------------------------------------------------- 时区边界


def test_timezone_boundaries(client, db):
    rows = [
        # 无时区：按 Asia/Shanghai 解释 -> UTC 2026-09-13 16:30
        row(external_event_no="T01", start_time="2026-09-14 00:30",
            end_time="2026-09-14 01:30", duration_min="60"),
        # 带 +08:00 偏移：与上面同一时刻
        row(external_event_no="T02", start_time="2026-09-14T00:30:00+08:00",
            end_time="2026-09-14T01:30:00+08:00", duration_min="60"),
        # UTC Z 时间：直接换算
        row(external_event_no="T03", start_time="2026-09-13T16:30:00Z",
            end_time="2026-09-13T17:30:00Z", duration_min="60"),
        # 跨零点：23:50 -> 次日 00:10，时长自动算 20 分钟
        row(external_event_no="T04", start_time="2026-09-14 23:50",
            end_time="2026-09-15 00:10", duration_min=""),
    ]
    batch = upload(client, make_csv(rows)).json()
    assert batch["ok_rows"] == 4, client.get(f"/api/imports/{batch['id']}/rows").json()
    assert confirm(client, batch["id"]).json()["imported"] == 4

    events = {e.external_event_no: e for e in db.scalars(select(models.DowntimeEvent))}
    expected = datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc)
    for no in ("T01", "T02", "T03"):
        assert events[no].start_time.astimezone(timezone.utc) == expected, no
    assert events["T04"].duration_min == 20
    assert events["T04"].end_time.astimezone(timezone.utc) == datetime(
        2026, 9, 14, 16, 10, tzinfo=timezone.utc)


# ---------------------------------------------------------------- 无外部事件号


def test_rows_without_external_event_no(client, db):
    data = make_csv([
        row(external_event_no="", reporter="李四"),
        row(external_event_no="", reporter="王五"),
    ])
    batch = upload(client, data).json()
    assert batch["ok_rows"] == 2  # 历史数据无外部号也可登记
    assert confirm(client, batch["id"]).json()["imported"] == 2
    assert event_count(db) == 2
    assert db.scalars(select(models.DowntimeEvent)
                      .where(models.DowntimeEvent.external_event_no.is_(None))).all()

    # 同文件重复上传仍幂等（按文件内容哈希）
    again = upload(client, data).json()
    assert again["deduplicated"] is True and again["status"] == "committed"
    assert event_count(db) == 2


# ---------------------------------------------------------------- 错误下载与修正后重传


def test_errors_csv_download_and_reupload(client, db):
    data = make_csv([
        row(external_event_no="F001"),
        row(external_event_no="F002", equipment_code="X999"),
    ])
    batch = upload(client, data).json()
    assert batch["error_rows"] == 1

    res = client.get(f"/api/imports/{batch['id']}/errors.csv")
    assert res.status_code == 200
    text = res.content.decode("utf-8-sig")
    assert "X999" in text and "设备编码不存在" in text

    # 用户修正后直接拿错误行文件重新预检（row_no/errors 附加列被忽略）
    fixed = text.replace("X999", "W102")
    batch2 = upload(client, fixed.encode("utf-8")).json()
    assert batch2["ok_rows"] == 1, client.get(f"/api/imports/{batch2['id']}/rows").json()
    assert confirm(client, batch2["id"]).json()["imported"] == 1
    assert event_count(db) == 1


# ---------------------------------------------------------------- 统计只见已提交行


def test_stats_only_see_committed_rows(client):
    data = make_csv([row(external_event_no="S001"), row(external_event_no="S002")])
    batch = upload(client, data).json()
    assert client.get("/api/analytics/pareto").json()["total_count"] == 0
    confirm(client, batch["id"])
    pareto = client.get("/api/analytics/pareto").json()
    assert pareto["total_count"] == 2
    assert pareto["total_duration_min"] == 90


# ---------------------------------------------------------------- 单条登记回归


def test_zero_duration_preserved(client, db):
    # 时长 0 是合法值，确认时不能被当成"未填"漂移为 NULL
    data = make_csv([row(external_event_no="Z001", end_time="", duration_min="0")])
    batch = upload(client, data).json()
    assert batch["ok_rows"] == 1
    assert confirm(client, batch["id"]).json()["imported"] == 1
    e = db.scalar(select(models.DowntimeEvent).where(
        models.DowntimeEvent.external_event_no == "Z001"))
    assert e.duration_min == 0


def test_single_create_still_works(client, db):
    masters = db.scalars(select(models.ProductionLine)).all()
    line = next(l for l in masters if l.code == "L1")
    eq = db.scalar(select(models.Equipment).where(models.Equipment.code == "P101"))
    reason = db.scalar(select(models.DowntimeReason).where(models.DowntimeReason.code == "EQ_MECH"))
    res = client.post("/api/events", json={
        "line_id": line.id, "equipment_id": eq.id, "reason_id": reason.id,
        "start_time": "2026-09-10T08:30:00+08:00", "end_time": "2026-09-10T09:00:00+08:00",
        "duration_min": 30, "shift": "白班", "reporter": "张伟",
    })
    assert res.status_code == 201, res.text
    assert res.json()["event_no"].startswith("DT")
