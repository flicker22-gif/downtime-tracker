import csv
import hashlib
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import import_service, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _batch_out(batch: models.ImportBatch, deduplicated: bool = False) -> schemas.ImportBatchOut:
    return schemas.ImportBatchOut(
        id=batch.id,
        filename=batch.filename,
        status=batch.status,
        total_rows=batch.total_rows,
        ok_rows=batch.ok_rows,
        duplicate_rows=batch.duplicate_rows,
        conflict_rows=batch.conflict_rows,
        error_rows=batch.error_rows,
        imported_rows=batch.imported_rows,
        skipped_rows=batch.skipped_rows,
        created_at=batch.created_at,
        committed_at=batch.committed_at,
        deduplicated=deduplicated,
    )


def _row_out(row: models.ImportRow) -> schemas.ImportRowOut:
    return schemas.ImportRowOut(
        row_no=row.row_no,
        status=row.status,
        external_event_no=row.external_event_no,
        errors=json.loads(row.errors) if row.errors else [],
        data=json.loads(row.payload),
        event_no=row.event.event_no if row.event else None,
    )


def _get_batch_or_404(batch_id: int, db: Session) -> models.ImportBatch:
    batch = db.get(models.ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "导入批次不存在")
    return batch


@router.post("/precheck", response_model=schemas.ImportBatchOut, status_code=201)
def precheck(file: UploadFile, db: Session = Depends(get_db)):
    """上传 CSV 并逐行预检：结果落暂存表，不影响统计。同内容文件幂等。"""
    raw = file.file.read()
    try:
        batch, deduplicated = import_service.create_batch(db, file.filename or "", raw)
    except import_service.ImportError400 as e:
        raise HTTPException(400, str(e))
    except IntegrityError:
        # 并发上传同一内容：唯一约束兜底，返回先到的批次
        db.rollback()
        file_hash = hashlib.sha256(raw).hexdigest()
        batch = db.scalar(
            select(models.ImportBatch).where(models.ImportBatch.file_hash == file_hash)
        )
        if batch is None:
            raise
        deduplicated = True
    return _batch_out(batch, deduplicated)


@router.get("", response_model=list[schemas.ImportBatchOut])
def list_batches(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(models.ImportBatch).order_by(models.ImportBatch.id.desc()).limit(50)
    ).all()
    return [_batch_out(b) for b in rows]


@router.get("/{batch_id}", response_model=schemas.ImportBatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    return _batch_out(_get_batch_or_404(batch_id, db))


@router.get("/{batch_id}/rows", response_model=schemas.ImportRowListResponse)
def list_rows(
    batch_id: int,
    status: str | None = Query(None, description="按行状态过滤 ok/duplicate/conflict/error"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _get_batch_or_404(batch_id, db)
    filters = [models.ImportRow.batch_id == batch_id]
    if status:
        filters.append(models.ImportRow.status == status)
    total = db.scalar(
        select(func.count()).select_from(models.ImportRow).where(*filters)
    ) or 0
    rows = db.scalars(
        select(models.ImportRow)
        .options(selectinload(models.ImportRow.event))
        .where(*filters)
        .order_by(models.ImportRow.row_no)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return schemas.ImportRowListResponse(total=total, items=[_row_out(r) for r in rows])


@router.get("/{batch_id}/errors.csv")
def download_errors(batch_id: int, db: Session = Depends(get_db)):
    """下载需修正的行（含错误说明），修正后可直接重新上传预检。"""
    batch = _get_batch_or_404(batch_id, db)
    rows = db.scalars(
        select(models.ImportRow)
        .where(models.ImportRow.batch_id == batch_id)
        .where(models.ImportRow.status.in_([models.ROW_ERROR, models.ROW_CONFLICT]))
        .order_by(models.ImportRow.row_no)
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    fields = list(import_service.FIELD_ALIASES.keys())
    writer.writerow(["row_no", "errors"] + fields)
    for r in rows:
        p = json.loads(r.payload)
        writer.writerow(
            [r.row_no, "；".join(json.loads(r.errors) or [])]
            + [p.get(f) if p.get(f) is not None else "" for f in fields]
        )
    data = buf.getvalue().encode("utf-8-sig")  # BOM：Excel 直接打开不乱码
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import_{batch_id}_errors.csv"'},
    )


@router.post("/{batch_id}/confirm", response_model=schemas.ImportConfirmResponse)
def confirm(batch_id: int, db: Session = Depends(get_db)):
    """确认导入：事务内批量写入，任一不可修正错误整体回滚；重复确认幂等。"""
    try:
        batch = import_service.confirm_batch(db, batch_id)
    except KeyError:
        raise HTTPException(404, "导入批次不存在")
    except ValueError as e:
        db.rollback()
        try:
            detail = json.loads(str(e))
        except json.JSONDecodeError:
            detail = {"message": str(e), "rows": []}
        raise HTTPException(409, detail)
    return schemas.ImportConfirmResponse(
        batch=_batch_out(batch), imported=batch.imported_rows, skipped=batch.skipped_rows
    )
