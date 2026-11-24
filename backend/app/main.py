from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.datasets import router as datasets_router
from app.api.health import router as health_router
from app.api.overview import router as overview_router
from app.api.profiling import router as profiling_router
from app.api.pipelines import router as pipelines_router
from app.api.quality import router as quality_router
from app.api.analytics import router as analytics_router
from app.api.orchestration import internal_router as orchestration_internal_router, monitor_router as orchestration_monitor_router, schedule_router as pipeline_schedule_router

app = FastAPI(title="DataPulse API", version="0.1.0", description="Phase 1 data ingestion and dataset catalog API")
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health_router, prefix="/api")
app.include_router(datasets_router, prefix="/api")
app.include_router(overview_router, prefix="/api")
app.include_router(profiling_router, prefix="/api")
app.include_router(pipelines_router, prefix="/api")
app.include_router(quality_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(pipeline_schedule_router, prefix="/api")
app.include_router(orchestration_monitor_router, prefix="/api")
app.include_router(orchestration_internal_router, prefix="/api")
