"""Main FastAPI application and CLI runner for S04E01 cr-s04e01-okoeditor.

Provides:
- GET /health and GET / (readiness & health checks)
- POST /run (canonical execution endpoint)
- CLI entrypoint: run_cli()
- Automated generation of run_notes.txt with [REDACTED_FLAG]
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
from schemas import HealthResponse, RunTaskRequest, RunTaskResponse
from services.audit_service import AuditService, generate_session_id
from services.mcp_service import MCPService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(
    title="cr-s04e01-okoeditor",
    description="S04E01 OKO Surveillance Record Manipulation Service",
    version="0.1.0",
)

audit_service = AuditService()
mcp_service = MCPService()


def save_run_notes(result: RunTaskResponse):
    """Saves formatted execution notes to run_notes.txt and cr-mcp-workspace with unanonymized course flag."""
    now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")

    actions_formatted = (
        "\n".join(
            f"  {idx + 1}. Action: {action}"
            for idx, action in enumerate(result.actions_taken)
        )
        if result.actions_taken
        else "  (No actions recorded)"
    )

    notes_content = f"""Task: {config.TASK_NAME} (S04E01)
Backend: {result.backend}
Session ID: {result.session_id}
Timestamp: {now_str}
Status: {result.status.upper()}
Actions Executed:
{actions_formatted}
Verification: done
Flag: {result.flag}
Summary:
{result.reasoning}
"""
    # Write locally in microservice folder
    notes_file = Path(__file__).parent / "run_notes.txt"
    try:
        notes_file.write_text(notes_content, encoding="utf-8")
        logger.info(f"Saved local execution notes to {notes_file}")
    except Exception as e:
        logger.warning(f"Failed to write local run_notes.txt: {e}")

    # Persist to cr-mcp-workspace asynchronously via event loop or background task
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                mcp_service.write_file(
                    session_id=result.session_id,
                    file_path="run_notes.txt",
                    content=notes_content,
                    reasoning="Persisting session run notes",
                )
            )
    except Exception as e:
        logger.debug(f"Workspace run notes persistence skipped: {e}")


# ==============================================================================
# Canonical Health & Readiness Endpoints
# ==============================================================================


@app.get("/health", response_model=HealthResponse)
@app.get("/", response_model=HealthResponse)
async def health_check():
    """Canonical health check and readiness endpoint."""
    return HealthResponse(
        status="healthy",
        service="cr-s04e01-okoeditor",
        timestamp=datetime.now(ZURICH_TZ).isoformat(),
    )


# ==============================================================================
# Canonical Task Execution Endpoint
# ==============================================================================


@app.post("/run", response_model=RunTaskResponse)
async def run_task(req: RunTaskRequest | None = None):
    """Executes the covert OKO record manipulation using the requested backend framework."""
    if req is None:
        req = RunTaskRequest(backend=config.BACKEND)

    backend = (req.backend or config.BACKEND or "langchain").lower().strip()
    session_id = req.session_id or generate_session_id(backend=backend)

    logger.info(f"Received /run request: backend={backend}, session_id={session_id}")

    try:
        agent = get_agent(backend=backend)
        response = await agent.execute(
            session_id=session_id, recursion_limit=req.max_iterations or 30
        )
        save_run_notes(response)

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
        raise HTTPException(status_code=500, detail=f"Mission execution failed: {e!s}")


# ==============================================================================
# CLI Entrypoint
# ==============================================================================


def run_cli():
    """CLI mode supporting --backend [langchain|adk]."""
    parser = argparse.ArgumentParser(
        description="S04E01 OKO Surveillance Record Manipulation CLI"
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

    args = parser.parse_args()
    session_id = args.session_id or generate_session_id(backend=args.backend)

    print("\n=======================================================")
    print(" S04E01 OKO Record Manipulation CLI")
    print(f" Backend:         {args.backend.upper()}")
    print(f" Session ID:      {session_id}")
    print(f" Model:           {config.GEMINI_MODEL} (thinking={config.THINKING_LEVEL})")
    print("=======================================================\n")

    agent = get_agent(backend=args.backend)
    result = asyncio.run(agent.execute(session_id=session_id))
    save_run_notes(result)

    print("\n-------------------------------------------------------")
    print(f" Status:         {result.status.upper()}")
    print(f" Actions Taken:  {', '.join(result.actions_taken)}")
    print(f" Flag Captured:  {result.flag}")
    print(" Notes Saved:    run_notes.txt")
    print("-------------------------------------------------------\n")


if __name__ == "__main__":
    run_cli()
