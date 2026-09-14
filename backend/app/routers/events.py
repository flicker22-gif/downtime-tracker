from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..numbering import lock_event_numbering, next_event_nos

router = APIRouter(prefix="/api/events", tags=["events"])

VALID_STATUS = {models.STATUS_OPEN, models.STATUS_ANALYZING, models.STATUS_CLOSED}


def _to_list_item(e: models.DowntimeEvent) -> schemas.EventListItem:
    open_actions = sum(1 for a in e.actions if a.status != models.ACTION_DONE)
    return schemas.EventListItem(
        id=e.id,
        event_no=e.event_no,
        line_id=e.line_id,
        equipment_id=e.equipment_id,
        reason_id=e.reason_id,
        start_time=e.start_time,
        end_time=e.end_time,
        duration_min=e.duration_min,
        shift=e.shift,
        reporter=e.reporter,
        product=e.product,
        note=e.note,
        status=e.status,
        created_at=e.created_at,
        line_name=e.line.name,
        equipment_name=e.equipment.name,
        reason_name=e.reason.name,
        reason_category=e.reason.category,
        has_analysis=e.analysis is not None,
        open_actions=open_actions,
    )


@router.get("", response_model=schemas.EventListResponse)
def list_events(
    line_id: int | None = None,
    equipment_id: int | None = None,
    reason_id: int | None = None,
    status: str | None = None,
    q: str | None = Query(None, description="按事件编号/操作工/工单模糊搜索"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = (
        select(models.DowntimeEvent)
        .options(
            selectinload(models.DowntimeEvent.line),
            selectinload(models.DowntimeEvent.equipment),
            selectinload(models.DowntimeEvent.reason),
            selectinload(models.DowntimeEvent.analysis),
            selectinload(models.DowntimeEvent.actions),
        )
        .order_by(models.DowntimeEvent.start_time.desc(), models.DowntimeEvent.id.desc())
    )
    count_stmt = select(func.count()).select_from(models.DowntimeEvent)

    filters = []
    if line_id is not None:
        filters.append(models.DowntimeEvent.line_id == line_id)
    if equipment_id is not None:
        filters.append(models.DowntimeEvent.equipment_id == equipment_id)
    if reason_id is not None:
        filters.append(models.DowntimeEvent.reason_id == reason_id)
    if status:
        filters.append(models.DowntimeEvent.status == status)
    if q:
        kw = f"%{q.strip()}%"
        filters.append(
            or_(
                models.DowntimeEvent.event_no.ilike(kw),
                models.DowntimeEvent.reporter.ilike(kw),
                models.DowntimeEvent.product.ilike(kw),
                models.Equipment.name.ilike(kw),
            )
        )
        stmt = stmt.join(
            models.Equipment, models.DowntimeEvent.equipment_id == models.Equipment.id
        )
        count_stmt = count_stmt.join(
            models.Equipment, models.DowntimeEvent.equipment_id == models.Equipment.id
        )
    if date_from:
        filters.append(models.DowntimeEvent.start_time >= date_from)
    if date_to:
        filters.append(models.DowntimeEvent.start_time <= date_to)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return schemas.EventListResponse(total=total, items=[_to_list_item(e) for e in rows])


@router.post("", response_model=schemas.EventDetail, status_code=201)
def create_event(payload: schemas.EventCreate, db: Session = Depends(get_db)):
    if not db.get(models.ProductionLine, payload.line_id):
        raise HTTPException(400, "产线不存在")
    equipment = db.get(models.Equipment, payload.equipment_id)
    if not equipment or equipment.line_id != payload.line_id:
        raise HTTPException(400, "设备不存在或不属于该产线")
    if not db.get(models.DowntimeReason, payload.reason_id):
        raise HTTPException(400, "停机原因不存在")

    # 与批量导入共用编号锁，避免并发下事件编号撞号
    lock_event_numbering(db)
    event = models.DowntimeEvent(
        event_no=next_event_nos(db, 1)[0],
        status=models.STATUS_OPEN,
        **payload.model_dump(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return get_event(event.id, db)


@router.get("/{event_id}", response_model=schemas.EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.scalar(
        select(models.DowntimeEvent)
        .options(
            selectinload(models.DowntimeEvent.line),
            selectinload(models.DowntimeEvent.equipment),
            selectinload(models.DowntimeEvent.reason),
            selectinload(models.DowntimeEvent.analysis),
            selectinload(models.DowntimeEvent.actions),
        )
        .where(models.DowntimeEvent.id == event_id)
    )
    if not event:
        raise HTTPException(404, "事件不存在")
    item = _to_list_item(event)
    return schemas.EventDetail(**item.model_dump(), analysis=event.analysis, actions=event.actions)


@router.patch("/{event_id}", response_model=schemas.EventDetail)
def update_event(event_id: int, payload: schemas.EventUpdate, db: Session = Depends(get_db)):
    event = db.get(models.DowntimeEvent, event_id)
    if not event:
        raise HTTPException(404, "事件不存在")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in VALID_STATUS:
        raise HTTPException(400, "非法状态")

    for key, value in data.items():
        setattr(event, key, value)
    db.commit()
    return get_event(event_id, db)
