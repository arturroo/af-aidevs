import argparse
import asyncio
import logging
from datetime import datetime
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
    title="cr-s04e05-foodwarehouse",
    description="S04E05 Central Food Warehouse Autonomous Distribution Service",
    version="0.1.0",
)

audit_service = AuditService()
mcp_service = MCPService()


async def save_run_notes(result: RunTaskResponse, session_id: str):
    """Saves formatted execution notes strictly to session-isolated cr-mcp-workspace (GCS) to prevent repo pollution."""
    now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")

    stats_str = (
        f"Discovery Queries: {result.stats.discovery_queries}, "
        f"Signatures: {result.stats.signatures_generated}, "
        f"Orders: {result.stats.orders_created}, "
        f"Items: {result.stats.items_appended}, "
        f"Duration: {result.stats.duration_seconds}s"
    )

    notes_content = f"""Task: {config.TASK_NAME} (S04E05)
Backend: {result.backend}
Session ID: {session_id}
Timestamp: {now_str}
Status: {result.status.upper()}
Orders Count: {result.orders_count}
Stats: {stats_str}
Flag: {result.flag or "[NONE]"}
Message: {result.message or "None"}
"""
    # Persist to cr-mcp-workspace (GCS bucket)
    try:
        await mcp_service.write_file(
            session_id=session_id,
            file_path="run_notes.txt",
            content=notes_content,
            reasoning="Persisting session run notes with flag",
        )
        logger.info(
            f"Saved execution notes to workspace at session {session_id}/run_notes.txt"
        )
    except Exception as e:
        logger.debug(f"Workspace run notes persistence skipped: {e}")


@app.get("/health")
@app.get("/")
async def health_check():
    """Readiness probe and canonical health check."""
    return {
        "status": "healthy",
        "service": "cr-s04e05-foodwarehouse",
        "version": "0.1.0",
        "task": config.TASK_NAME,
        "default_backend": config.BACKEND,
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task_endpoint(request: RunTaskRequest):
    """Executes the foodwarehouse task via the specified backend."""
    session_id = request.session_id or generate_session_id(request.backend)
    effective_limit = request.max_iterations or config.MAX_AGENT_ITERATIONS
    effective_model = request.model or config.GEMINI_MODEL
    effective_thinking = request.thinking_level or config.THINKING_LEVEL

    logger.info(
        f"Triggering execution via API: backend={request.backend}, session_id={session_id}, "
        f"model={effective_model}, thinking_level={effective_thinking}, max_iterations={effective_limit}"
    )

    try:
        agent = get_agent(
            backend=request.backend,
            model=effective_model,
            thinking_level=effective_thinking,
        )
        result = await agent.execute(
            session_id=session_id,
            recursion_limit=effective_limit,
            model=effective_model,
            thinking_level=effective_thinking,
        )
        await save_run_notes(result, session_id)
        return result
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        err_res = RunTaskResponse(
            status="error",
            session_id=session_id,
            backend=request.backend,
            message=str(e),
        )
        await save_run_notes(err_res, session_id)
        raise HTTPException(status_code=500, detail=str(e))


def run_cli():
    """CLI mode entrypoint allowing direct execution via uv run python main.py."""
    parser = argparse.ArgumentParser(
        description="S04E05 Food Warehouse Autonomous Distribution Runner"
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND,
        help="Agent backend selection (default: langchain)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional session ID for BigQuery audit tracking",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.GEMINI_MODEL,
        help=f"Model ID to use (default: {config.GEMINI_MODEL})",
    )
    parser.add_argument(
        "--thinking-level",
        choices=["low", "medium", "high"],
        default=config.THINKING_LEVEL,
        help=f"Thinking level for reasoning models (default: {config.THINKING_LEVEL})",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=config.MAX_AGENT_ITERATIONS,
        help=f"Max agent iterations (default: {config.MAX_AGENT_ITERATIONS})",
    )
    args = parser.parse_args()

    session_id = args.session_id or generate_session_id(args.backend)
    print(
        f"[*] Starting S04E05 Food Warehouse Operation: backend={args.backend}, session_id={session_id}, "
        f"model={args.model}, thinking_level={args.thinking_level}, max_iterations={args.max_iterations}"
    )

    agent = get_agent(
        backend=args.backend,
        model=args.model,
        thinking_level=args.thinking_level,
    )
    result = asyncio.run(
        agent.execute(
            session_id=session_id,
            recursion_limit=args.max_iterations,
            model=args.model,
            thinking_level=args.thinking_level,
        )
    )

    asyncio.run(save_run_notes(result, session_id))

    print("\n" + "=" * 60)
    print(f"Status:       {result.status.upper()}")
    print(f"Backend:      {result.backend}")
    print(f"Flag:         {result.flag}")
    print(f"Orders Count: {result.orders_count}")
    print(f"Discovery:    {result.stats.discovery_queries}")
    print(f"Signatures:   {result.stats.signatures_generated}")
    print(f"Items Appended: {result.stats.items_appended}")
    print(f"Duration:     {result.stats.duration_seconds}s")
    if result.message:
        print(f"Message:      {result.message}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_cli()
