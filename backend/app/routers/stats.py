from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/pareto", response_model=schemas.ParetoResponse)
def downtime_pareto(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    line_id: int | None = None,
    top: int = 10,
    db: Session = Depends(get_db),
):
    """按停机原因聚合：次数、停机时长，按次数降序并给出累计百分比（帕累托）"""
    duration = func.coalesce(models.DowntimeEvent.duration_min, 0)
    stmt = (
        select(
            models.DowntimeReason.id,
            models.DowntimeReason.name,
            models.DowntimeReason.category,
            func.count().label("cnt"),
            func.coalesce(func.sum(duration), 0).label("dur"),
        )
        .join(models.DowntimeReason, models.DowntimeEvent.reason_id == models.DowntimeReason.id)
        .group_by(models.DowntimeReason.id)
        .order_by(func.count().desc(), func.sum(duration).desc())
    )
    if date_from:
        stmt = stmt.where(models.DowntimeEvent.start_time >= date_from)
    if date_to:
        stmt = stmt.where(models.DowntimeEvent.start_time <= date_to)
    if line_id is not None:
        stmt = stmt.where(models.DowntimeEvent.line_id == line_id)

    rows = db.execute(stmt).all()
    total_count = sum(r.cnt for r in rows) or 0
    total_dur = int(sum(r.dur for r in rows)) or 0

    items = []
    cum = 0
    for r in rows[:top]:
        cum += r.cnt
        items.append(
            schemas.ParetoItem(
                reason_id=r.id,
                reason_name=r.name,
                category=r.category,
                count=r.cnt,
                duration_min=int(r.dur),
                count_pct=round(r.cnt / total_count * 100, 1) if total_count else 0.0,
                cum_pct=round(cum / total_count * 100, 1) if total_count else 0.0,
            )
        )

    return schemas.ParetoResponse(
        total_count=total_count, total_duration_min=total_dur, items=items
    )
