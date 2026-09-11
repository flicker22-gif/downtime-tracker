from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 事件状态
STATUS_OPEN = "open"          # 待分析
STATUS_ANALYZING = "analyzing"  # 分析/改善中
STATUS_CLOSED = "closed"      # 已关闭

# 措施状态
ACTION_OPEN = "open"
ACTION_DOING = "doing"
ACTION_DONE = "done"


class ProductionLine(Base):
    __tablename__ = "production_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    equipments: Mapped[list["Equipment"]] = relationship(back_populates="line", cascade="all, delete-orphan")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (UniqueConstraint("line_id", "code", name="uq_equipment_line_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("production_line.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line: Mapped[ProductionLine] = relationship(back_populates="equipments")


class DowntimeReason(Base):
    """停机原因选项（按大类分组，如：设备故障/换型换模/待料/质量/其他）"""

    __tablename__ = "downtime_reason"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)
    # 是否计入设备可靠性指标（MTTR/MTBF）：设备故障类原因为 True，
    # 换型换模、待料等计划性/外部原因不计为故障
    is_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class DowntimeEvent(Base):
    __tablename__ = "downtime_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("production_line.id"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    reason_id: Mapped[int] = mapped_column(ForeignKey("downtime_reason.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shift: Mapped[str] = mapped_column(String(16))  # 白班/夜班
    reporter: Mapped[str] = mapped_column(String(32))  # 操作工
    product: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 当时生产产品/工单号
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_OPEN, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    line: Mapped[ProductionLine] = relationship()
    equipment: Mapped[Equipment] = relationship()
    reason: Mapped[DowntimeReason] = relationship()
    analysis: Mapped["FiveWhyAnalysis | None"] = relationship(
        back_populates="event", cascade="all, delete-orphan", uselist=False
    )
    actions: Mapped[list["CorrectiveAction"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class FiveWhyAnalysis(Base):
    """班组长填写的 5 Whys 根因分析（一个事件一份）"""

    __tablename__ = "five_why_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("downtime_event.id", ondelete="CASCADE"), unique=True)
    problem_statement: Mapped[str] = mapped_column(Text)  # 问题描述
    why1: Mapped[str | None] = mapped_column(Text, nullable=True)
    why2: Mapped[str | None] = mapped_column(Text, nullable=True)
    why3: Mapped[str | None] = mapped_column(Text, nullable=True)
    why4: Mapped[str | None] = mapped_column(Text, nullable=True)
    why5: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst: Mapped[str] = mapped_column(String(32))  # 班组长
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    event: Mapped[DowntimeEvent] = relationship(back_populates="analysis")


class CorrectiveAction(Base):
    """针对根因的改善措施，用于跟踪闭环"""

    __tablename__ = "corrective_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("downtime_event.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(32))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ACTION_OPEN, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[DowntimeEvent] = relationship(back_populates="actions")
