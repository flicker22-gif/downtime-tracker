"""初始化基础数据与演示事件（仅在表为空时执行）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from . import models
from .database import Base, SessionLocal, engine

LINES = [
    ("L1", "一号总装线"),
    ("L2", "二号总装线"),
    ("L3", "包装线"),
]

EQUIPMENTS = {
    "L1": [("P101", "冲压机A"), ("W102", "焊接机器人1#"), ("C103", "输送链1段")],
    "L2": [("P201", "冲压机B"), ("W202", "焊接机器人2#"), ("T203", "拧紧机")],
    "L3": [("F301", "封箱机"), ("L302", "贴标机")],
}

# (category, code, name, is_failure)
REASONS = [
    ("设备故障", "EQ_MECH", "机械故障", True),
    ("设备故障", "EQ_ELEC", "电气/控制系统故障", True),
    ("设备故障", "EQ_TOOL", "刀具/模具磨损", True),
    ("换型换模", "CHANGEOVER", "换型换模", False),
    ("换型换模", "ADJUST", "首件调试/参数调整", False),
    ("物料问题", "WAIT_MAT", "待料/缺料", False),
    ("物料问题", "MAT_QC", "来料不良", False),
    ("质量问题", "QUALITY", "质量异常停机", False),
    ("人员因素", "OPERATOR", "人员操作/交接班", False),
    ("公用工程", "UTILITY", "水电气中断", False),
    ("其他", "OTHER", "其他", False),
]

SHIFT_DAY = "白班"
SHIFT_NIGHT = "夜班"


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.scalar(select(func.count()).select_from(models.ProductionLine)):
            return

        line_map: dict[str, models.ProductionLine] = {}
        for code, name in LINES:
            line = models.ProductionLine(code=code, name=name)
            db.add(line)
            line_map[code] = line
        db.flush()

        equip_map: dict[tuple[str, str], models.Equipment] = {}
        for line_code, items in EQUIPMENTS.items():
            for code, name in items:
                eq = models.Equipment(line_id=line_map[line_code].id, code=code, name=name)
                db.add(eq)
                equip_map[(line_code, code)] = eq
        db.flush()

        reason_map: dict[str, models.DowntimeReason] = {}
        for idx, (category, code, name, is_failure) in enumerate(REASONS):
            reason = models.DowntimeReason(
                code=code,
                name=name,
                category=category,
                is_failure=is_failure,
                sort_order=idx,
            )
            db.add(reason)
            reason_map[code] = reason
        db.flush()

        # 演示用停机事件：近 7 天
        now = datetime.now(timezone.utc)
        demo = [
            # line, equip, reason, hours_ago, duration_min, reporter, shift
            ("L1", "P101", "EQ_MECH", 2, 45, "张伟", SHIFT_DAY),
            ("L1", "W102", "EQ_ELEC", 5, 30, "张伟", SHIFT_DAY),
            ("L1", "P101", "EQ_TOOL", 26, 20, "李娜", SHIFT_NIGHT),
            ("L1", "C103", "WAIT_MAT", 30, 60, "李娜", SHIFT_NIGHT),
            ("L2", "P201", "EQ_MECH", 8, 55, "王强", SHIFT_DAY),
            ("L2", "W202", "CHANGEOVER", 28, 40, "赵敏", SHIFT_NIGHT),
            ("L2", "T203", "ADJUST", 50, 25, "王强", SHIFT_DAY),
            ("L2", "P201", "EQ_MECH", 70, 75, "赵敏", SHIFT_NIGHT),
            ("L3", "F301", "MAT_QC", 10, 35, "陈杰", SHIFT_DAY),
            ("L3", "L302", "QUALITY", 52, 50, "陈杰", SHIFT_DAY),
            ("L3", "F301", "UTILITY", 74, 15, "孙磊", SHIFT_NIGHT),
            ("L1", "P101", "EQ_MECH", 90, 40, "张伟", SHIFT_DAY),
        ]
        events = []
        for i, (lc, ec, rc, hours_ago, dur, reporter, shift) in enumerate(demo, start=1):
            start = now - timedelta(hours=hours_ago)
            e = models.DowntimeEvent(
                event_no=f"SEED{i:04d}",
                line_id=equip_map[(lc, ec)].line_id,
                equipment_id=equip_map[(lc, ec)].id,
                reason_id=reason_map[rc].id,
                start_time=start,
                end_time=start + timedelta(minutes=dur),
                duration_min=dur,
                shift=shift,
                reporter=reporter,
                product=f"WO-{2600 + i}",
                note="演示数据",
                status=models.STATUS_OPEN,
            )
            events.append(e)
            db.add(e)
        db.flush()

        # 给第一个事件补一份已完成的 5 Whys + 措施，便于页面展示
        first = events[0]
        first.status = models.STATUS_ANALYZING
        db.add(
            models.FiveWhyAnalysis(
                event_id=first.id,
                problem_statement="冲压机A在生产中突发停机，持续45分钟",
                why1="为什么停机？——主电机过载保护跳脱",
                why2="为什么过载？——冲压负荷异常增大",
                why3="为什么负荷增大？——润滑不足导致导轨摩擦增大",
                why4="为什么润滑不足？——自动润滑泵滤芯堵塞，出油量下降",
                why5="为什么滤芯会堵塞？——润滑保养清单中未包含定期更换滤芯项",
                root_cause="预防性保养清单缺失润滑滤芯更换项，导致润滑系统失效、设备过载停机",
                analyst="周班长",
            )
        )
        db.add_all(
            [
                models.CorrectiveAction(
                    event_id=first.id,
                    content="在设备保养清单中增加润滑泵滤芯每季度更换项",
                    owner="设备部-刘洋",
                    due_date=now + timedelta(days=14),
                    status=models.ACTION_DOING,
                ),
                models.CorrectiveAction(
                    event_id=first.id,
                    content="对全部冲压机润滑系统做一次专项检查",
                    owner="设备部-刘洋",
                    due_date=now + timedelta(days=7),
                    status=models.ACTION_DONE,
                    completed_at=now - timedelta(days=1),
                ),
            ]
        )
        db.commit()
        print("种子数据已写入")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
