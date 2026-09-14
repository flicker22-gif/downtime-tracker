"""测试运行在与开发库隔离的 downtime_test 库（便携 PG，端口 55433）。"""
import os

os.environ.setdefault(
    "DT_DATABASE_URL",
    "postgresql+psycopg://downtime:downtime@localhost:55433/downtime_test",
)
os.environ["DT_SEED_ON_STARTUP"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import models, seed as seed_module
from app.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """重建测试库结构并只导主数据（产线/设备/原因），不导演示事件。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        line_map = {}
        for code, name in seed_module.LINES:
            line = models.ProductionLine(code=code, name=name)
            db.add(line)
            line_map[code] = line
        db.flush()
        for line_code, items in seed_module.EQUIPMENTS.items():
            for code, name in items:
                db.add(models.Equipment(line_id=line_map[line_code].id, code=code, name=name))
        for idx, (category, code, name, is_failure) in enumerate(seed_module.REASONS):
            db.add(
                models.DowntimeReason(
                    code=code, name=name, category=category,
                    is_failure=is_failure, sort_order=idx,
                )
            )
        db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client(setup_database):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE downtime_event, five_why_analysis, corrective_action, "
                "import_batch, import_row RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
