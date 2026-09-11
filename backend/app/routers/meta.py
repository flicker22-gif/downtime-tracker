from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api", tags=["master-data"])


@router.get("/lines", response_model=list[schemas.Line])
def list_lines(db: Session = Depends(get_db)):
    return db.scalars(select(models.ProductionLine).order_by(models.ProductionLine.code)).all()


@router.get("/equipments", response_model=list[schemas.Equipment])
def list_equipments(line_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(models.Equipment).order_by(models.Equipment.code)
    if line_id is not None:
        stmt = stmt.where(models.Equipment.line_id == line_id)
    return db.scalars(stmt).all()


@router.get("/reasons", response_model=list[schemas.Reason])
def list_reasons(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.DowntimeReason)
        .where(models.DowntimeReason.is_active.is_(True))
        .order_by(models.DowntimeReason.sort_order, models.DowntimeReason.id)
    ).all()


@router.get("/reasons/{reason_id}", response_model=schemas.Reason)
def get_reason(reason_id: int, db: Session = Depends(get_db)):
    obj = db.get(models.DowntimeReason, reason_id)
    if not obj:
        raise HTTPException(404, "原因不存在")
    return obj
