import argparse
import asyncio
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI

import config
from agents.audio_subagent import AudioSubagent
from agents.sqlite_subagent import SQLiteSubagent
from agents.synthesis_subagent import SynthesisSubagent
from agents.text_subagent import TextSubagent
from agents.vision_subagent import VisionSubagent
from schemas import (
    CentralaListenResponse,
    RunTaskRequest,
    RunTaskResponse,
)
from services.audit_service import AuditService, generate_session_id
from services.centrala_service import CentralaService
from services.mcp_service import MCPService
from services.model_armor_service import ModelArmorService
from services.router_service import RouterService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="cr-s05e01-radiomonitoring",
    description="Microservice for S05E01 Radiomonitoring & Multimodal Scatter-Gather Ingestion",
    version="0.1.0",
)


async def execute_task(request: RunTaskRequest) -> RunTaskResponse:
    """Executes the complete Asynchronous Scatter-Gather radiomonitoring pipeline."""
    start_time = time.perf_counter()
    session_id = request.session_id or generate_session_id(backend=request.backend)
    logger.info(
        f"Starting execution session {session_id} with backend {request.backend}"
    )

    # 1. Initialize services
    audit_service = AuditService()
    centrala_service = CentralaService(audit_service=audit_service)
    mcp_service = MCPService()
    await mcp_service.get_tools_for_session(session_id)
    model_armor = ModelArmorService()
    router_service = RouterService(mcp_service=mcp_service, audit_service=audit_service)

    # Initialize specialized subagents
    vision_agent = VisionSubagent(
        mcp_service=mcp_service,
        audit_service=audit_service,
        model_armor_service=model_armor,
        model_name=request.enrichment_model or config.ENRICHMENT_MODEL,
    )
    text_agent = TextSubagent(
        mcp_service=mcp_service,
        audit_service=audit_service,
        model_armor_service=model_armor,
        model_name=request.model or config.GEMINI_MODEL,
    )
    sqlite_agent = SQLiteSubagent(
        mcp_service=mcp_service,
        audit_service=audit_service,
        model_armor_service=model_armor,
        model_name=request.model or config.GEMINI_MODEL,
    )
    audio_agent = AudioSubagent(
        mcp_service=mcp_service,
        audit_service=audit_service,
        model_armor_service=model_armor,
        model_name=request.model or config.GEMINI_MODEL,
    )

    # 2. Phase 1: Start radio listening session
    try:
        start_res = await centrala_service.start(session_id)
        logger.info(f"Centrala radio session started: {start_res}")
    except Exception as e:
        logger.error(f"Failed to start Centrala radio session: {e}")
        return RunTaskResponse(
            status="error",
            session_id=session_id,
            error=f"Start failed: {e}",
            execution_time_seconds=round(time.perf_counter() - start_time, 2),
        )

    # 3. Phase 2: Ingestion & Asynchronous Scatter (Fan-Out) Loop
    subagent_tasks: list[asyncio.Task] = []
    packet_index = 0
    max_packets = request.max_iterations or 50

    while packet_index < max_packets:
        packet_index += 1
        try:
            packet: CentralaListenResponse = await centrala_service.listen(session_id)
        except Exception as e:
            logger.error(f"Centrala listen error at packet {packet_index}: {e}")
            break

        # Check for stream completion indicators
        msg_lower = (packet.message or "").lower()
        if (
            packet.code != 100
            or "wystarczająco" in msg_lower
            or "enough" in msg_lower
            or "koniec" in msg_lower
            or "done" in msg_lower
            or (not packet.transcription and not packet.attachment)
        ):
            logger.info(
                f"Stream termination reached at packet {packet_index}: code={packet.code}, msg='{packet.message}'"
            )
            # Check if terminal packet contained flag
            if packet.flag:
                logger.info(f"Captured flag in stream termination: {packet.flag}")
            break

        # Land packet in /raw/ and normalized artifacts in /decoded/
        artifacts = await router_service.ingest_packet(session_id, packet_index, packet)

        # Dispatch each artifact to specialized subagent asynchronously
        for art in artifacts:
            path = art["path"]
            mime = art["mime"]

            if mime.startswith("image/"):
                t = asyncio.create_task(vision_agent.analyze(session_id, path, mime))
                subagent_tasks.append(t)
            elif mime.startswith("audio/"):
                t = asyncio.create_task(audio_agent.analyze(session_id, path, mime))
                subagent_tasks.append(t)
            elif mime == "application/x-sqlite3":
                t = asyncio.create_task(sqlite_agent.analyze(session_id, path, mime))
                subagent_tasks.append(t)
            elif mime in ("text/plain", "text/markdown", "application/json"):
                t = asyncio.create_task(text_agent.analyze(session_id, path, mime))
                subagent_tasks.append(t)
            else:
                logger.info(f"Skipping unroutable artifact {path} with MIME {mime}")

    # 4. Wait for all subagents to finish their object findings
    logger.info(
        f"Waiting for {len(subagent_tasks)} background subagent tasks to complete..."
    )
    if subagent_tasks:
        await asyncio.gather(*subagent_tasks, return_exceptions=True)
    logger.info("All subagent analysis tasks completed.")

    # 5. Phase 3: Fan-In Aggregation & Synthesis
    synthesis_agent = SynthesisSubagent(
        mcp_service=mcp_service,
        centrala_service=centrala_service,
        audit_service=audit_service,
        model_name=request.model or config.GEMINI_MODEL,
        thinking_level=request.thinking_level or config.THINKING_LEVEL,
    )

    findings = await synthesis_agent.aggregate_findings(session_id)
    logger.info(f"Aggregated {len(findings)} findings from workspace.")

    response = await synthesis_agent.synthesize_and_transmit(session_id, findings)
    response.execution_time_seconds = round(time.perf_counter() - start_time, 2)
    logger.info(
        f"Execution finished in {response.execution_time_seconds}s. Status={response.status}, Flag={response.mission_flag}"
    )

    # Persist unanonymized run_notes.txt directly into GCS workspace via MCP
    await _persist_run_notes(
        mcp_service=mcp_service,
        session_id=session_id,
        response=response,
        findings=findings,
        execution_time=response.execution_time_seconds,
    )

    return response


async def _persist_run_notes(
    mcp_service: MCPService,
    session_id: str,
    response: RunTaskResponse,
    findings: list[Any],
    execution_time: float,
) -> None:
    """Persists unanonymized execution run notes directly to the remote GCS workspace via MCP."""
    try:
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        clues_summary = []
        for f in findings:
            sc = getattr(f, "secret_clues", None)
            if sc and (
                sc.telegraphist_mentions
                or sc.morse_detected
                or sc.raw_clue
                or sc.extracted_key
            ):
                clues_summary.append(
                    f"- Source: {f.source_file}\n"
                    f"  Telegraphist mentions: {sc.telegraphist_mentions}\n"
                    f"  Morse detected: {sc.morse_detected}\n"
                    f"  Raw clue: {sc.raw_clue}\n"
                    f"  Extracted key: {sc.extracted_key}"
                )
        clues_block = (
            "\n".join(clues_summary)
            if clues_summary
            else "No explicit secret clues detected in findings."
        )

        notes_content = f"""================================================================================
AI_Devs Season 05 Episode 01 — Architektura (radiomonitoring)
Execution Run Notes & Mission Verification Report
Timestamp: {now_str}
Session ID: {session_id}
Execution Time: {execution_time}s
Status: {response.status.upper()}
================================================================================

1. MISSION OBJECTIVE A (Main Task: radiomonitoring):
- Status: {response.status.upper()}
- Verified Parameters Sent to Centrala:
  * action: "transmit"
  * cityName: "{response.city_name}"
  * cityArea: "{response.city_area}"
  * warehousesCount: {response.warehouses_count}
  * phoneNumber: "{response.phone_number}"
- Mission Flag: {response.mission_flag or "None"}
- Error Details: {response.error or "None"}

2. OBJECT FINDINGS DIGEST:
- Total Analyzed Artifacts: {len(findings)}
- Secret Telegraphist / Morse Clues:
{clues_block}

3. SECRET / EASTER EGG FINDINGS:
- Secret Flag: {response.secret_flag or "None"}
================================================================================
"""
        await mcp_service.write_file(session_id, "run_notes.txt", notes_content)
        logger.info(
            f"Successfully persisted run_notes.txt to workspace for session {session_id}"
        )
    except Exception as e:
        logger.warning(f"Failed to persist run_notes.txt to workspace: {e}")


@app.get("/health")
@app.get("/")
async def health_check():
    """Canonical health check and readiness status."""
    return {
        "status": "ok",
        "service": config.SERVICE_NAME,
        "version": "0.1.0",
        "gemini_model": config.GEMINI_MODEL,
        "enrichment_model": config.ENRICHMENT_MODEL,
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    """Canonical task execution endpoint."""
    return await execute_task(request)


def run_cli():
    """CLI mode entrypoint for local evaluation and debugging."""
    parser = argparse.ArgumentParser(description="Run S05E01 Radiomonitoring Task CLI")
    parser.add_argument("--backend", default="langchain", choices=["langchain"])
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--enrichment-model", default=None)
    parser.add_argument(
        "--thinking-level", choices=["low", "medium", "high"], default=None
    )
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--mode", choices=["cli", "server"], default="cli")
    args = parser.parse_args()

    if args.mode == "server":
        uvicorn.run("main:app", host="0.0.0.0", port=args.port, reload=False)
        return

    req = RunTaskRequest(
        backend=args.backend,
        session_id=args.session_id,
        model=args.model,
        enrichment_model=args.enrichment_model,
        thinking_level=args.thinking_level,
        max_iterations=args.max_iterations,
    )
    res = asyncio.run(execute_task(req))
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mode" and sys.argv[2] == "server":
        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
    else:
        run_cli()
