"""对已有数据库做最小化的前向结构补齐（开发期轻量迁移）。

正式环境建议改用 Alembic；这里仅在启动时检查并补齐新增列，避免重建演示库。
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from .database import engine

# 表名 -> [(列名, 列DDL)]
_PENDING_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "downtime_reason": [
        ("is_failure", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ],
    "downtime_event": [
        ("external_event_no", "VARCHAR(64)"),
    ],
}

# 表名 -> [(索引名, 建索引DDL)]：新列上的唯一约束（PG 唯一索引允许多个 NULL）
_PENDING_INDEXES: dict[str, list[tuple[str, str]]] = {
    "downtime_event": [
        (
            "uq_downtime_event_external_event_no",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_downtime_event_external_event_no "
            "ON downtime_event (external_event_no)",
        ),
    ],
}


def ensure_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _PENDING_COLUMNS.items():
            if table not in existing_tables:
                continue  # 表尚不存在，create_all 会按最新模型建表
            present = {c["name"] for c in inspector.get_columns(table)}
            added = False
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added = True
            # 新列：设备故障大类的既有原因回填为计入可靠性指标
            if table == "downtime_reason" and added:
                conn.execute(
                    text(
                        "UPDATE downtime_reason SET is_failure = TRUE "
                        "WHERE category = '设备故障'"
                    )
                )
        for table, indexes in _PENDING_INDEXES.items():
            if table not in existing_tables:
                continue
            existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
            for name, ddl in indexes:
                if name not in existing_indexes:
                    conn.execute(text(ddl))
