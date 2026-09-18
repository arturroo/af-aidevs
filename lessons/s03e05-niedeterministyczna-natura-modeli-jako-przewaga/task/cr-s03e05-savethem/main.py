"""Main FastAPI application for S03E05 savethem autonomous routing microservice.

Provides:
- GET /health and GET / (canonical health mirror)
- POST /run (canonical task execution endpoint)
- CLI entrypoint: run_cli()
"""

import argparse
import asyncio
from datetime import datetime
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
import uvicorn

from agents.factory import get_agent
import config
from schemas import HealthResponse, RunTaskRequest, RunTaskResponse
from services.audit_service import AuditService, generate_session_id

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(
    title="cr-s03e05-savethem",
    description="S03E05 Savethem Autonomous Routing Service",
    version="0.1.0",
)

audit_service = AuditService()


# ==============================================================================
# Canonical Health & Readiness Endpoints
# ==============================================================================

@app.get("/health", response_model=HealthResponse)
@app.get("/", response_model=HealthResponse)
async def health_check():
    """Canonical health check and readiness endpoint."""
    return HealthResponse(
        status="healthy",
        service="cr-s03e05-savethem",
        timestamp=datetime.now(ZURICH_TZ).isoformat(),
    )


# ==============================================================================
# Canonical Task Orchestrator Endpoint
# ==============================================================================

@app.post("/run", response_model=RunTaskResponse)
async def run_task(req: Optional[RunTaskRequest] = None):
    """Executes the autonomous navigation mission using the requested backend framework."""
    if req is None:
        req = RunTaskRequest(backend=config.BACKEND)

    backend = (req.backend or config.BACKEND or "langchain").lower().strip()
    session_id = req.session_id or generate_session_id(backend=backend)

    logger.info(f"Received /run request: backend={backend}, session_id={session_id}")

    try:
        agent = get_agent(backend=backend)
        response = await agent.execute(
            session_id=session_id,
            force_refresh=req.force_refresh,
            recursion_limit=req.recursion_limit,
        )
        return response
    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        await audit_service.log_event(
            session_id=session_id,
            actor="main",
            content=f"Unhandled exception in /run: {e}",
            step_type="SYSTEM_ERROR",
            metadata={"error": str(e)},
        )
        raise HTTPException(
            status_code=500, detail=f"Mission execution failed: {str(e)}"
        )


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def run_cli():
    """CLI mode supporting --backend [langchain|adk]."""
    parser = argparse.ArgumentParser(
        description="S03E05 Savethem Autonomous Routing Task CLI"
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND or "langchain",
        help="Agent framework to use: langchain (default) or adk",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Custom session ID for audit logging and workspace storage",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass in-memory caches and re-query external tools",
    )
    parser.add_argument(
        "--recursion-limit",
        "-r",
        type=int,
        default=30,
        help="Maximum recursion/turn limit for agent execution graph (default: 30)",
    )

    args = parser.parse_args()
    session_id = args.session_id or generate_session_id(backend=args.backend)

    print("\n=======================================================")
    print(" S03E05 Savethem Autonomous Routing CLI")
    print(f" Backend:         {args.backend.upper()}")
    print(f" Session ID:      {session_id}")
    print(f" Model:           {config.GEMINI_MODEL} (thinking={config.THINKING_LEVEL})")
    print(f" Recursion Limit: {args.recursion_limit}")
    print("=======================================================\n")

    agent = get_agent(backend=args.backend)
    result = asyncio.run(
        agent.execute(
            session_id=session_id,
            force_refresh=args.force_refresh,
            recursion_limit=args.recursion_limit,
        )
    )

    print("\n-------------------------------------------------------")
    print(f" Status:         {result.status.upper()}")
    print(f" Flag Captured:  {result.flag or 'None'}")
    print(f" Total Steps:    {result.steps_count}")
    print(f" Fuel Remaining: {result.fuel_remaining}")
    print(f" Food Remaining: {result.food_remaining}")
    print(f" Route Itinerary:")
    print(f"   {result.itinerary}")
    print("-------------------------------------------------------\n")


if __name__ == "__main__":
    run_cli()
