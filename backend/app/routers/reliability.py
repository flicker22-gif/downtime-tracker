from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _window(
    date_from: datetime | None, date_to: datetime | None, all_data: bool
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    d_to = date_to or now
    if date_from is not None:
        return date_from, d_to
    if all_data:
        # 观察起点取库中最早事件时间，避免用过长的空窗期稀释 MTBF
        return _earliest_event() or (d_to - timedelta(days=30)), d_to
    return now - timedelta(days=30), d_to


def _earliest_event() -> datetime | None:
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        return db.scalar(select(func.min(models.DowntimeEvent.start_time)))
    finally:
        db.close()


def _build_rows(
    db: Session,
    dimension: str,
    date_from: datetime,
    date_to: datetime,
    line_id: int | None,
) -> list[schemas.ReliabilityRow]:
    """按设备/产线聚合故障次数与故障停机时长（仅统计 is_failure 原因）。"""
    is_fail = models.DowntimeReason.is_failure.is_(True)
    fail_flag = case((is_fail, 1), else_=0)
    fail_dur = case((is_fail, models.DowntimeEvent.duration_min), else_=0)

    event_join_cond = (
        models.DowntimeEvent.equipment_id == models.Equipment.id,
        models.DowntimeEvent.start_time >= date_from,
        models.DowntimeEvent.start_time < date_to,
    )
    if line_id is not None:
        event_join_cond = (*event_join_cond, models.DowntimeEvent.line_id == line_id)

    base = (
        select(
            func.sum(fail_flag).label("failure_count"),
            func.coalesce(func.sum(fail_dur), 0).label("failure_downtime"),
        )
        .select_from(models.Equipment)
        .join(models.ProductionLine, models.Equipment.line_id == models.ProductionLine.id)
        .outerjoin(models.DowntimeEvent, and_(*event_join_cond))
        .outerjoin(
            models.DowntimeReason,
            models.DowntimeEvent.reason_id == models.DowntimeReason.id,
        )
    )

    window_min = int((date_to - date_from).total_seconds() / 60)

    if dimension == "equipment":
        stmt = base.add_columns(
            models.Equipment.id,
            models.Equipment.code,
            models.Equipment.name,
            models.Equipment.line_id,
            models.ProductionLine.name.label("line_name"),
        ).group_by(
            models.Equipment.id, models.Equipment.code, models.Equipment.name,
            models.Equipment.line_id, models.ProductionLine.name,
        )
        if line_id is not None:
            stmt = stmt.where(models.Equipment.line_id == line_id)

        rows = []
        for r in db.execute(stmt).all():
            downtime = int(r.failure_downtime or 0)
            failures = int(r.failure_count or 0)
            rows.append(
                schemas.ReliabilityRow(
                    id=r.id,
                    code=r.code,
                    name=r.name,
                    line_id=r.line_id,
                    line_name=r.line_name,
                    equipment_count=1,
                    failure_count=failures,
                    failure_downtime_min=downtime,
                    observation_min=window_min,
                    mttr_min=round(downtime / failures, 1) if failures else None,
                    mtbf_min=round((window_min - downtime) / failures, 1) if failures else None,
                    availability_pct=round((window_min - downtime) / window_min * 100, 2)
                    if window_min
                    else None,
                )
            )
        rows.sort(key=lambda x: (x.failure_count, x.failure_downtime_min), reverse=True)
        return rows

    # dimension == "line"
    stmt = base.add_columns(
        models.ProductionLine.id,
        models.ProductionLine.code,
        models.ProductionLine.name,
        func.count(func.distinct(models.Equipment.id)).label("eq_count"),
    ).group_by(
        models.ProductionLine.id, models.ProductionLine.code, models.ProductionLine.name
    )
    if line_id is not None:
        stmt = stmt.where(models.ProductionLine.id == line_id)

    rows = []
    for r in db.execute(stmt).all():
        downtime = int(r.failure_downtime or 0)
        failures = int(r.failure_count or 0)
        eq_count = int(r.eq_count or 0)
        observation = window_min * eq_count  # 产线运行时长基数 = 区间 × 设备数
        rows.append(
            schemas.ReliabilityRow(
                id=r.id,
                code=r.code,
                name=r.name,
                equipment_count=eq_count,
                failure_count=failures,
                failure_downtime_min=downtime,
                observation_min=observation,
                mttr_min=round(downtime / failures, 1) if failures else None,
                mtbf_min=round((observation - downtime) / failures, 1) if failures else None,
                availability_pct=round((observation - downtime) / observation * 100, 2)
                if observation
                else None,
            )
        )
    rows.sort(key=lambda x: (x.failure_count, x.failure_downtime_min), reverse=True)
    return rows


@router.get("/reliability", response_model=schemas.ReliabilityResponse)
def reliability(
    dimension: str = Query("equipment", pattern="^(equipment|line)$"),
    line_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    all_data: bool = Query(False, description="取全部数据，观察起点用最早事件时间"),
    db: Session = Depends(get_db),
):
    """MTTR / MTBF / 可用度。

    - 仅统计停机原因 is_failure=true（设备故障类）的事件
    - MTTR = 故障停机总时长 / 故障次数
    - MTBF = (运行时长基数 − 故障停机时长) / 故障次数；运行时长基数取统计区间
      （产线维度 = 区间 × 产线内设备数）
    - 可用度 = (运行时长基数 − 故障停机时长) / 运行时长基数
    - 无故障的设备/产线：MTTR、MTBF 为空，可用度 100%
    """
    d_from, d_to = _window(date_from, date_to, all_data)
    rows = _build_rows(db, dimension, d_from, d_to, line_id)
    return schemas.ReliabilityResponse(
        dimension=dimension, date_from=d_from, date_to=d_to, rows=rows
    )
