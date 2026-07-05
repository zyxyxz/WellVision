from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    admin,
    analysis,
    algorithms,
    auth,
    health,
    ingestion,
    ingestion_events,
    projects,
    reports,
    tenants,
    well_runs,
    warehouses,
)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    ai_chat,
    analysis_run,
    algorithm_definition,
    audit_log,
    dataset,
    event,
    event_metric,
    event_metric_rollup,
    event_metric_rollup_v2,
    import_job,
    membership,
    op_segment,
    project,
    report,
    report_template,
    system_setting,
    tenant,
    well_run,
    warehouse,
    user,
)  # noqa: F401 - ensures model metadata is registered
from app.services.bootstrap import bootstrap_defaults
from app.services.schema import ensure_schema, ensure_timescaledb
from app.services.import_worker import start_import_worker

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
        ensure_schema(engine)
        ensure_timescaledb(
            engine,
            enabled=settings.timescaledb_enabled,
            chunk_interval_hours=settings.timescaledb_chunk_interval_hours,
            compress_after_hours=settings.timescaledb_compress_after_hours,
            retention_days=settings.timescaledb_retention_days,
        )
        with SessionLocal() as db:
            bootstrap_defaults(db)
    start_import_worker()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(tenants.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(ingestion_events.router, prefix="/api")
app.include_router(warehouses.router, prefix="/api")
app.include_router(well_runs.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(algorithms.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
