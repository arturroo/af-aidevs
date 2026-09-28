"""Main entrypoint for cr-s05e03-shellaccess exposing FastAPI microservice and dual-mode CLI."""

import argparse
import asyncio
import logging
import sys

import uvicorn
from fastapi import FastAPI, HTTPException

import config
from schemas import RunTaskRequest, RunTaskResponse
from services.centrala_service import CentralaService
from services.orchestrator import ShellAccessOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="cr-s05e03-shellaccess",
    description="S05E03 Remote Shell Access & Time Archive Investigation",
    version="0.1.0",
)


@app.get("/health")
@app.get("/")
async def health_check() -> dict[str, str]:
    """Canonical health check probe."""
    return {"status": "ok", "service": "cr-s05e03-shellaccess"}


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest | None = None) -> RunTaskResponse:
    """Canonical execution endpoint running the autonomous shell exploration agent."""
    req = request or RunTaskRequest()
    try:
        orchestrator = ShellAccessOrchestrator(req)
        result = await orchestrator.run()
        return result
    except Exception as exc:
        logger.exception("Unhandled error during task execution")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def run_repl() -> None:
    """Launches Artur's direct, unfiltered interactive shell session."""
    if not sys.stdin.isatty():
        print("ERROR: REPL mode requires an interactive TTY terminal.", file=sys.stderr)
        sys.exit(1)

    centrala = CentralaService()

    print("\n" + "=" * 65)
    print("  S05E03 REMOTE SHELL ACCESS - DIRECT PASSTHROUGH REPL")
    print("  Target: Centrala ($AIDEVS_API_VERIFY)")
    print("  Direct unrestricted execution. Type 'exit' or 'quit' to exit.")
    print("=" * 65 + "\n")

    while True:
        try:
            line = input("shellaccess> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL session.")
            break

        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            print("Session ended.")
            break

        try:
            resp = await centrala.execute_shell_raw(line, caller="HUMAN_REPL")
            output = resp.message or "(empty output)"
            print(output)
            if "{FLG:" in output:
                print("\n[MISSION SUCCESS: Course Flag Detected in Output!]")
        except Exception as err:
            print(f"[REPL ERROR: {err}]", file=sys.stderr)


async def run_auto_cli(args: argparse.Namespace) -> None:
    """Executes the autonomous agent in CLI mode."""
    req = RunTaskRequest(
        backend=args.backend,
        model=args.model,
        max_iterations=args.max_iterations or 30,
        thinking_level=args.thinking_level,
        session_id=args.session_id,
    )
    print(
        f"\n[INFO] Starting autonomous ReAct agent with model={req.model or config.config.GEMINI_MODEL}..."
    )
    orchestrator = ShellAccessOrchestrator(req)
    result = await orchestrator.run()

    print("\n" + "=" * 50)
    print(f"Status:       {result.status.upper()}")
    print(f"Session ID:   {result.session_id}")
    print(f"Turns:        {result.total_turns}")
    print(f"Duration:     {result.execution_time_seconds}s")
    if result.rendezvous:
        print(f"Rendezvous:   {result.rendezvous.model_dump_json()}")
    if result.flag:
        print(f"Flag:         {result.flag}")
    if result.error:
        print(f"Error:        {result.error}")
    print("=" * 50 + "\n")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="cr-s05e03-shellaccess CLI & Service")
    parser.add_argument(
        "--mode",
        choices=["auto", "repl", "server"],
        default="auto",
        help="Operational mode: auto (autonomous agent), repl (interactive direct terminal), server (FastAPI)",
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default="langchain",
        help="Agent framework backend",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model name (e.g. gemini-3.8-flash)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum iterations for the agent loop",
    )
    parser.add_argument(
        "--thinking-level",
        choices=["low", "medium", "high"],
        default=None,
        help="Thinking level for Gemini reasoning models",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Custom session identifier",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for FastAPI server (when mode=server)",
    )

    args = parser.parse_args()

    if args.mode == "repl":
        asyncio.run(run_repl())
    elif args.mode == "server":
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        asyncio.run(run_auto_cli(args))


if __name__ == "__main__":
    main()
