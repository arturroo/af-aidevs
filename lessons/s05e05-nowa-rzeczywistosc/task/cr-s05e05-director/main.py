import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from schemas import RunTaskRequest, RunTaskResponse
from services.audit_service import audit_service
from services.trajectory_orchestrator import orchestrator

logger = logging.getLogger("director_service")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Ensures BigQuery audit table and telemetry dependencies are initialized."""
    logger.info("Initializing cr-s05e05-director microservice...")
    try:
        audit_service.ensure_table()
    except Exception as e:
        logger.warning("BigQuery table check deferred: %s", e)
    yield
    logger.info("Shutting down cr-s05e05-director microservice.")


app = FastAPI(
    title="cr-s05e05-director",
    version="0.1.0",
    description="Temporal Flight Director Microservice for CHRONOS-P1",
    lifespan=lifespan,
)


@app.get("/health")
@app.get("/")
async def health_check() -> dict[str, str]:
    """Canonical health check and service readiness status endpoint."""
    return {
        "status": "healthy",
        "service": "cr-s05e05-director",
        "version": "0.1.0",
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest | None = None) -> RunTaskResponse:
    """Canonical task execution endpoint initiating autonomous 3-hop temporal displacement."""
    req = request or RunTaskRequest()
    return await orchestrator.run_mission(req)
