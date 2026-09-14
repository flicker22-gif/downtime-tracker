"""事件编号分配：DT + yyyymmdd + 当日序号（如 DT20260914-007）。

单条登记与批量导入共用同一套分配逻辑。PostgreSQL 下用事务级咨询锁
把"取最大序号 + 写入"串行化，避免并发确认/登记时撞号后整批回滚。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import models

# 咨询锁 key（任意固定整数，"DTNO" 的 ASCII 低 4 字节）
_ADVISORY_LOCK_KEY = 0x44544E4F


def lock_event_numbering(db: Session) -> None:
    """在事务内对事件编号分配加锁（仅 PG 有效，其它库退化为无操作）。"""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})


def next_event_nos(db: Session, count: int = 1) -> list[str]:
    """分配 count 个连续事件编号。调用方需在同一事务内完成写入。"""
    today = datetime.now()
    prefix = f"DT{today:%Y%m%d}-"
    # 序号定长 3 位、超过后变长：按 (长度, 字典序) 取最大等价于按数值取最大
    last = db.scalar(
        select(models.DowntimeEvent.event_no)
        .where(models.DowntimeEvent.event_no.like(prefix + "%"))
        .order_by(
            func.length(models.DowntimeEvent.event_no).desc(),
            models.DowntimeEvent.event_no.desc(),
        )
        .limit(1)
    )
    seq = int(last.split("-")[1]) + 1 if last else 1
    return [f"{prefix}{seq + i:03d}" for i in range(count)]
