"""Main FastAPI application and CLI runner for S04E03 cr-s04e03-domatowo.

Provides:
- GET /health and GET / (readiness & health checks)
- POST /run (canonical execution endpoint)
- CLI entrypoint: run_cli()
- Automated generation of run_notes.txt
"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException

import config
from agents.factory import get_agent
from schemas import RunTaskRequest, RunTaskResponse
from services.audit_service import AuditService, generate_session_id
from services.mcp_service import MCPService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(
    title="cr-s04e03-domatowo",
    description="S04E03 Autonomous Tactical Search & Rescue in Domatowo Service",
    version="0.1.0",
)

audit_service = AuditService()
mcp_service = MCPService()


async def save_run_notes(result: RunTaskResponse, session_id: str):
    """Saves formatted execution notes to run_notes.txt and cr-mcp-workspace with course flag."""
    now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")

    notes_content = f"""Task: {config.TASK_NAME} (S04E03)
Backend: {result.backend_used}
Session ID: {session_id}
Timestamp: {now_str}
Status: {"SUCCESS" if result.success else "FAILED"}
AP Spent: {result.ap_spent} / {config.MAX_AP_BUDGET}
Final Location: {result.final_location or "N/A"}
Flag: {result.flag or "[NONE]"}
Error: {result.error or "None"}
"""
    # Write locally in microservice folder
    notes_file = Path(__file__).parent / "run_notes.txt"
    try:
        notes_file.write_text(notes_content, encoding="utf-8")
        logger.info(f"Saved local execution notes to {notes_file}")
    except Exception as e:
        logger.warning(f"Failed to write local run_notes.txt: {e}")

    # Persist to cr-mcp-workspace
    try:
        await mcp_service.write_file(
            session_id=session_id,
            file_path="run_notes.txt",
            content=notes_content,
            reasoning="Persisting session run notes",
        )
        logger.info("Saved execution notes to workspace at run_notes.txt")
    except Exception as e:
        logger.debug(f"Workspace run notes persistence skipped: {e}")


# ==============================================================================
# Canonical Health & Readiness Endpoints
# ==============================================================================


@app.get("/health")
@app.get("/")
async def health_check():
    """Canonical health check and readiness endpoint."""
    return {
        "status": "healthy",
        "service": "cr-s04e03-domatowo",
        "task": config.TASK_NAME,
        "default_backend": config.BACKEND,
    }


# ==============================================================================
# Canonical Execution Endpoint
# ==============================================================================


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest | None = None):
    """Executes autonomous search and rescue operation in Domatowo using the requested agent backend."""
    req = request or RunTaskRequest()
    session_id = req.session_id or generate_session_id(backend=req.backend)
    rec_limit = req.recursion_limit or req.max_iterations or config.MAX_AGENT_ITERATIONS

    logger.info(
        f"Incoming run request: backend={req.backend}, session_id={session_id}, recursion_limit={rec_limit}"
    )

    try:
        agent = get_agent(backend=req.backend)
        result = await agent.execute(session_id=session_id, recursion_limit=rec_limit)

        await save_run_notes(result, session_id=session_id)

        await audit_service.log_event(
            session_id=session_id,
            actor="system",
            content=(
                f"Task completed: success={result.success}, ap_spent={result.ap_spent}, "
                f"location={result.final_location}, flag={result.flag}"
            ),
            step_type="mission_completed",
            flag=result.flag,
        )

        return result
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        await audit_service.log_event(
            session_id=session_id,
            actor="system",
            content=f"Task execution error: {e}",
            step_type="mission_error",
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


# ==============================================================================
# CLI Entrypoint
# ==============================================================================


def run_cli():
    """CLI runner supporting --backend [langchain|adk]."""
    parser = argparse.ArgumentParser(
        description="Run S04E03 Domatowo Search & Rescue Agent CLI"
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND,
        help="Wybór frameworka agentowego (domyślnie langchain)",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session ID for tracing and audit logging",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=config.MAX_AGENT_ITERATIONS,
        help="Maximum agent turns",
    )

    args = parser.parse_args()
    session_id = args.session_id or generate_session_id(backend=args.backend)

    print("=" * 65)
    print("  COMMANDER DISPATCH: S04E03 Domatowo Search & Rescue")
    print(f"  Backend: {args.backend} | Session ID: {session_id}")
    print("=" * 65)

    agent = get_agent(backend=args.backend)
    result = asyncio.run(
        agent.execute(session_id=session_id, recursion_limit=args.recursion_limit)
    )

    asyncio.run(save_run_notes(result, session_id=session_id))

    print("\n" + "=" * 65)
    print("  MISSION EXECUTION SUMMARY")
    print(f"  Status:       {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  AP Consumed:  {result.ap_spent} / {config.MAX_AP_BUDGET}")
    print(f"  Survivor At:  {result.final_location or 'N/A'}")
    print(f"  Flag:         {result.flag or 'None'}")
    if result.error:
        print(f"  Error:        {result.error}")
    print("=" * 65)


if __name__ == "__main__":
    run_cli()
