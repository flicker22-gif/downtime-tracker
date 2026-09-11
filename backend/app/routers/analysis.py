from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/events/{event_id}", tags=["analysis"])


def _get_event(db: Session, event_id: int) -> models.DowntimeEvent:
    event = db.get(models.DowntimeEvent, event_id)
    if not event:
        raise HTTPException(404, "事件不存在")
    return event


@router.put("/analysis", response_model=schemas.FiveWhyOut)
def upsert_analysis(event_id: int, payload: schemas.FiveWhyCreate, db: Session = Depends(get_db)):
    """班组长提交/更新 5 Whys；首次提交时事件流转为「分析/改善中」"""
    event = _get_event(db, event_id)
    data = payload.model_dump()

    if event.analysis:
        for key, value in data.items():
            setattr(event.analysis, key, value)
    else:
        analysis = models.FiveWhyAnalysis(event_id=event_id, **data)
        db.add(analysis)
        if event.status == models.STATUS_OPEN:
            event.status = models.STATUS_ANALYZING

    db.commit()
    return event.analysis or db.scalar(
        select(models.FiveWhyAnalysis).where(models.FiveWhyAnalysis.event_id == event_id)
    )


@router.delete("/analysis", status_code=204)
def delete_analysis(event_id: int, db: Session = Depends(get_db)):
    event = _get_event(db, event_id)
    if not event.analysis:
        raise HTTPException(404, "分析记录不存在")
    db.delete(event.analysis)
    db.commit()


@router.post("/actions", response_model=schemas.ActionOut, status_code=201)
def create_action(event_id: int, payload: schemas.ActionCreate, db: Session = Depends(get_db)):
    _get_event(db, event_id)
    if payload.status not in {models.ACTION_OPEN, models.ACTION_DOING, models.ACTION_DONE}:
        raise HTTPException(400, "非法措施状态")
    action = models.CorrectiveAction(
        event_id=event_id,
        completed_at=datetime.now(timezone.utc) if payload.status == models.ACTION_DONE else None,
        **payload.model_dump(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.patch("/actions/{action_id}", response_model=schemas.ActionOut)
def update_action(
    event_id: int, action_id: int, payload: schemas.ActionUpdate, db: Session = Depends(get_db)
):
    _get_event(db, event_id)
    action = db.get(models.CorrectiveAction, action_id)
    if not action or action.event_id != event_id:
        raise HTTPException(404, "措施不存在")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        if data["status"] not in {models.ACTION_OPEN, models.ACTION_DOING, models.ACTION_DONE}:
            raise HTTPException(400, "非法措施状态")
        # 标记完成时自动盖时间戳；重开时清空
        if data["status"] == models.ACTION_DONE and action.completed_at is None:
            action.completed_at = datetime.now(timezone.utc)
        elif data["status"] != models.ACTION_DONE:
            action.completed_at = None

    for key, value in data.items():
        setattr(action, key, value)
    db.commit()
    db.refresh(action)
    return action


@router.delete("/actions/{action_id}", status_code=204)
def delete_action(event_id: int, action_id: int, db: Session = Depends(get_db)):
    _get_event(db, event_id)
    action = db.get(models.CorrectiveAction, action_id)
    if not action or action.event_id != event_id:
        raise HTTPException(404, "措施不存在")
    db.delete(action)
    db.commit()
