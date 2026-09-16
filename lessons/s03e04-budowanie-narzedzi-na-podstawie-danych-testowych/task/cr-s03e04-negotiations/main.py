"""Main FastAPI application for S03E04 negotiations tooling microservice.

Provides:
- GET /health and GET / (canonical health mirror)
- POST /reload-db (administrative live database reload from GCS)
- POST /api/search-item-in-catalog (Tool 1: Catalog Search)
- POST /api/find-cities-having-items-ids (Tool 2: City Availability Intersection)
- POST /run (canonical orchestrator endpoint)
- CLI entrypoint: run_cli()
"""

import argparse
import asyncio
from datetime import datetime
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
import uvicorn

from agents.factory import get_orchestrator
import config
from schemas import (
    ReloadDbResponse,
    RunTaskRequest,
    RunTaskResponse,
    ToolRequest,
    ToolResponse,
)
from services.audit_service import AuditService, generate_session_id
from services.catalog_service import CatalogService
from services.city_service import CityService
from services.db_service import DatabaseService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(
    title="cr-s03e04-negotiations",
    description="S03E04 Autonomous Negotiations Tooling Service",
    version="0.1.0",
)

db_service = DatabaseService.get_instance()
audit_service = AuditService()
catalog_service = CatalogService(audit_service=audit_service)
city_service = CityService(db_service=db_service, audit_service=audit_service)


# ==============================================================================
# Canonical Health & Readiness Endpoints
# ==============================================================================

@app.get("/health")
@app.get("/")
async def health_check():
    """Canonical health check and service readiness status (exact mirror)."""
    return {
        "status": "ok",
        "service": "cr-s03e04-negotiations",
        "backend": config.BACKEND,
        "task": config.TASK_NAME,
        "timestamp": datetime.now(ZURICH_TZ).isoformat(),
    }


@app.post("/reload-db", response_model=ReloadDbResponse)
async def reload_database():
    """Administrative endpoint to re-download inventory.db from cr-mcp-workspace without redeployment."""
    try:
        logger.info("Admin request: Reloading inventory.db from cr-mcp-workspace...")
        await db_service.download_db_from_workspace()
        return ReloadDbResponse(
            status="ok",
            message="Database successfully reloaded from cr-mcp-workspace.",
            timestamp=datetime.now(ZURICH_TZ).isoformat(),
        )
    except Exception as e:
        logger.error("Failed to reload database from cr-mcp-workspace: %s", e)
        err_msg = str(e)
        if len(err_msg) > 300:
            err_msg = err_msg[:300] + "..."
        raise HTTPException(status_code=500, detail=f"Database reload failed: {err_msg}")


# ==============================================================================
# Centrala Webhook Tool Endpoints
# ==============================================================================

@app.post("/api/search-item-in-catalog", response_model=ToolResponse)
async def api_search_item_in_catalog(
    request: ToolRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
):
    """Tool 1: Search catalog for item IDs based on natural language technical descriptions."""
    session_id = x_session_id or generate_session_id(backend=config.BACKEND)
    logger.info("[%s] Tool 1 search received: %s", session_id, request.params[:100])
    try:
        output = await catalog_service.search_items(
            user_query=request.params,
            session_id=session_id,
            backend=config.BACKEND,
        )
        return ToolResponse(output=output)
    except Exception as e:
        logger.error("[%s] Tool 1 execution error: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/find-cities-having-items-ids", response_model=ToolResponse)
async def api_find_cities_having_items_ids(
    request: ToolRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
):
    """Tool 2: Find survivor cities stocking all specified 6-character item codes simultaneously."""
    session_id = x_session_id or generate_session_id(backend=config.BACKEND)
    logger.info("[%s] Tool 2 city check received: %s", session_id, request.params[:100])
    try:
        output = await city_service.find_cities(
            user_query=request.params,
            session_id=session_id,
            backend=config.BACKEND,
        )
        return ToolResponse(output=output)
    except Exception as e:
        logger.error("[%s] Tool 2 execution error: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Canonical Task Orchestrator Endpoint
# ==============================================================================

@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    """Execute task orchestration, register tools at Centrala, and poll status."""
    session_id = request.session_id or generate_session_id(backend=request.backend)
    logger.info("[%s] POST /run received for backend: %s", session_id, request.backend)

    try:
        orchestrator = get_orchestrator(request.backend)
        result = await orchestrator.solve(
            session_id=session_id,
            public_url=request.public_url,
        )
        return RunTaskResponse(
            session_id=session_id,
            backend=request.backend,
            status="success",
            result=result,
        )
    except Exception as e:
        logger.error("[%s] Orchestration failed: %s", session_id, e)
        return RunTaskResponse(
            session_id=session_id,
            backend=request.backend,
            status="error",
            result={"error": str(e)},
        )


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def run_cli():
    """Command-line entrypoint for local execution and testing."""
    parser = argparse.ArgumentParser(description="CLI mode for S03E04 negotiations service.")
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default="langchain",
        help="Choice of agent framework (default: langchain)",
    )
    parser.add_argument(
        "--public-url",
        type=str,
        default=None,
        help="Public URL of deployed Cloud Run service for Centrala registration",
    )
    parser.add_argument(
        "--run-orchestration",
        action="store_true",
        help="Run full task orchestration with Centrala verification",
    )
    parser.add_argument(
        "--test-item-search",
        type=str,
        default=None,
        help="Test Tool 1 locally with a sample query string",
    )
    parser.add_argument(
        "--test-cities",
        type=str,
        default=None,
        help="Test Tool 2 locally with a sample code string",
    )
    args = parser.parse_args()

    session_id = generate_session_id(backend=args.backend)

    if args.test_item_search:
        print(f"\n--- Testing Tool 1: search_item_in_catalog [{args.backend}] ---")
        output = asyncio.run(
            catalog_service.search_items(args.test_item_search, session_id, args.backend)
        )
        print(f"Output ({len(output.encode('utf-8'))} bytes):\n{output}\n")
        return

    if args.test_cities:
        print(f"\n--- Testing Tool 2: find_cities_having_items_ids [{args.backend}] ---")
        output = asyncio.run(
            city_service.find_cities(args.test_cities, session_id, args.backend)
        )
        print(f"Output ({len(output.encode('utf-8'))} bytes):\n{output}\n")
        return

    if args.run_orchestration:
        print(f"\n--- Running Task Orchestration [{args.backend}] ---")
        orchestrator = get_orchestrator(args.backend)
        result = asyncio.run(orchestrator.solve(session_id, public_url=args.public_url))
        print("Result:", result)
        return

    # Default: Start local uvicorn server
    print("Starting uvicorn server on http://0.0.0.0:8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    run_cli()
