"""Main FastAPI application and CLI runner for S04E04 cr-s04e04-filesystem.

Provides:
- GET /health and GET / (canonical readiness & health checks)
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
from services.centrala_service import CentralaService
from services.extraction_service import ExtractionService
from services.mcp_service import MCPService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(
    title="cr-s04e04-filesystem",
    description="S04E04 Digital Knowledge Base & Virtual Filesystem Service",
    version="0.1.0",
)

audit_service = AuditService()
mcp_service = MCPService()


async def save_run_notes(result: RunTaskResponse, session_id: str):
    """Saves formatted execution notes to run_notes.txt with captured flag."""
    now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")

    stats_str = "None"
    if result.stats:
        stats_str = (
            f"Cities: {result.stats.cities_count}, "
            f"Persons: {result.stats.persons_count}, "
            f"Commodities: {result.stats.commodities_count}, "
            f"Files Uploaded: {result.stats.files_uploaded}"
        )

    notes_content = f"""Task: {config.TASK_NAME} (S04E04)
Backend: {result.backend}
Session ID: {session_id}
Timestamp: {now_str}
Status: {"SUCCESS" if result.status == "success" else "FAILED"}
Stats: {stats_str}
Flag: {result.flag or "[NONE]"}
Error: {result.error or "None"}
"""
    notes_file = Path(__file__).parent / "run_notes.txt"
    try:
        notes_file.write_text(notes_content, encoding="utf-8")
        logger.info(f"Saved local execution notes to {notes_file}")
    except Exception as e:
        logger.warning(f"Failed to write local run_notes.txt: {e}")

    # Persist to cr-mcp-workspace (GCS bucket)
    try:
        await mcp_service.write_file(
            session_id=session_id,
            file_path="run_notes.txt",
            content=notes_content,
            reasoning="Persisting session run notes with flag",
        )
        logger.info("Saved execution notes to workspace at run_notes.txt")
    except Exception as e:
        logger.debug(f"Workspace run notes persistence skipped: {e}")


@app.get("/health")
@app.get("/")
async def health_check():
    """Readiness probe and canonical health check."""
    return {
        "status": "healthy",
        "service": "cr-s04e04-filesystem",
        "version": "0.1.0",
        "task": config.TASK_NAME,
        "default_backend": config.BACKEND,
    }


@app.get("/test-verify")
async def test_verify():
    """Diagnostic endpoint to inspect Centrala /verify help, reset, createDirectory, and createFile."""
    centrala = CentralaService()
    try:
        help_resp = await centrala.get_help()
        reset_resp = await centrala.reset()
        list_before = await centrala.list_files("/")

        # Test single createDirectory
        dir_res = await centrala._post_verify(
            {"action": "createDirectory", "path": "/miasta"}
        )
        list_after_dir = await centrala.list_files("/")

        # Test single createFile
        file_res = await centrala._post_verify(
            {"action": "createFile", "path": "/miasta/test", "content": '{"woda": 10}'}
        )
        list_after_file = await centrala.list_files("/miasta")

        return {
            "status": "ok",
            "help": help_resp,
            "reset": reset_resp,
            "list_before": list_before,
            "create_dir_result": dir_res,
            "list_after_dir": list_after_dir,
            "create_file_result": file_res,
            "list_after_file": list_after_file,
        }
    except Exception as e:
        logger.error(f"Diagnostic error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@app.get("/test-pipeline")
async def test_pipeline():
    """Diagnostic endpoint executing extraction, build_virtual_files, and batch upload directly."""
    centrala = CentralaService()
    extraction = ExtractionService()
    try:
        # 1. Reset
        reset_resp = await centrala.reset()

        # 2. Extract & build files
        notes = await extraction.fetch_notes()
        raw_res = await extraction.extract_structured_plan(notes)
        files = extraction.build_virtual_files(raw_res)

        # 3. Batch upload
        upload_resp = await centrala.batch_create_files(files)

        # 4. Done verification
        done_resp, flag = await centrala.done()

        return {
            "status": "ok",
            "reset": reset_resp,
            "total_files": len(files),
            "files": [{"path": f.path, "content_len": len(f.content)} for f in files],
            "upload_response": upload_resp,
            "done_response": done_resp,
            "flag": flag,
        }
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@app.post("/run", response_model=RunTaskResponse)
async def run_task_endpoint(request: RunTaskRequest):
    """Executes the filesystem task via the specified backend."""
    session_id = request.session_id or generate_session_id(request.backend)
    logger.info(
        f"Triggering execution via API: backend={request.backend}, session_id={session_id}"
    )

    try:
        agent = get_agent(request.backend)
        result = await agent.execute(session_id=session_id)
        await save_run_notes(result, session_id)
        return result
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        err_res = RunTaskResponse(
            status="error",
            backend=request.backend,
            error=str(e),
        )
        await save_run_notes(err_res, session_id)
        raise HTTPException(status_code=500, detail=str(e))


def run_cli():
    """CLI mode entrypoint allowing direct execution via uv run python main.py."""
    parser = argparse.ArgumentParser(
        description="S04E04 Filesystem Knowledge Base Reconstructor Runner"
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
    args = parser.parse_args()

    session_id = args.session_id or generate_session_id(args.backend)
    print(
        f"[*] Starting S04E04 Filesystem Operation: backend={args.backend}, session_id={session_id}"
    )

    agent = get_agent(args.backend)
    result = asyncio.run(agent.execute(session_id=session_id))

    asyncio.run(save_run_notes(result, session_id))

    print("\n" + "=" * 60)
    print(f"Status:   {result.status.upper()}")
    print(f"Backend:  {result.backend}")
    print(f"Flag:     {result.flag}")
    if result.stats:
        print(f"Cities:   {result.stats.cities_count}")
        print(f"Persons:  {result.stats.persons_count}")
        print(f"Commodities: {result.stats.commodities_count}")
        print(f"Uploaded: {result.stats.files_uploaded}")
    if result.error:
        print(f"Error:    {result.error}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_cli()
