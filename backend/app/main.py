from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .migrations import ensure_schema
from .routers import analysis, events, imports, meta, reliability, stats
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    if settings.seed_on_startup:
        seed()
    yield


app = FastAPI(title="车间停机管理 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(events.router)
app.include_router(imports.router)
app.include_router(analysis.router)
app.include_router(stats.router)
app.include_router(reliability.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
