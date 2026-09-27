import argparse
import asyncio
import logging
import sys

import uvicorn
from fastapi import FastAPI

import config
from schemas import RunTaskRequest, RunTaskResponse
from services.orchestrator import ConversationalOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="cr-s05e02-phonecall",
    description="Conversational Voice Agent for S05E02 Phonecall",
    version="0.1.0",
)


@app.get("/health")
@app.get("/")
async def health_check() -> dict[str, str]:
    """Canonical health check and readiness status."""
    return {
        "status": "ok",
        "service": config.SERVICE_NAME,
        "version": "0.1.0",
        "gemini_model": config.GEMINI_MODEL,
        "voice_name": config.DEFAULT_VOICE_NAME,
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest) -> RunTaskResponse:
    """Canonical execution endpoint."""
    orchestrator = ConversationalOrchestrator(request=request)
    return await orchestrator.run()


def run_cli() -> None:
    """CLI mode entrypoint for local execution and debugging."""
    parser = argparse.ArgumentParser(description="Run S05E02 Phonecall Voice Agent CLI")
    parser.add_argument("--backend", default="langchain", choices=["langchain", "adk"])
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--thinking-level", choices=["low", "medium", "high"], default=None
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=config.DEFAULT_MAX_ITERATIONS,
    )
    parser.add_argument(
        "--voice-name",
        default=config.DEFAULT_VOICE_NAME,
    )
    parser.add_argument(
        "--speaking-rate",
        type=float,
        default=config.DEFAULT_SPEAKING_RATE,
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=config.DEFAULT_MAX_RESTARTS,
    )
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
        thinking_level=args.thinking_level,
        max_iterations=args.max_iterations,
        voice_name=args.voice_name,
        speaking_rate=args.speaking_rate,
        max_restarts=args.max_restarts,
    )
    orchestrator = ConversationalOrchestrator(request=req)
    res = asyncio.run(orchestrator.run())
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mode" and sys.argv[2] == "server":
        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
    else:
        run_cli()
