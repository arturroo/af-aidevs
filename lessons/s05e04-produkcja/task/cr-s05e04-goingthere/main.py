"""FastAPI service and developer CLI entrypoint for cr-s05e04-goingthere."""

import argparse
import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import config
from schemas import RunTaskRequest, RunTaskResponse
from services.flight_controller import FlightController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="cr-s05e04-goingthere",
    description="Autonomous Rocket Navigation & OKO Radar Neutralization",
    version="0.1.0",
)


@app.get("/")
@app.get("/health")
async def health_check() -> JSONResponse:
    """Canonical health check and service readiness status."""
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "service": config.SERVICE_NAME},
    )


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest | None = None) -> RunTaskResponse:
    """Canonical execution endpoint for Cloud Run."""
    req = request or RunTaskRequest()
    controller = FlightController(request=req)
    return await controller.run_flight()


def print_cli_summary(res: RunTaskResponse) -> None:
    """Renders formatted execution summary in terminal."""
    print("\n" + "=" * 55)
    print(" [FLIGHT MISSION EXECUTION SUMMARY]")
    print(f" Session ID:    {res.session_id}")
    print(f" Status:        {res.status.upper()}")
    print(f" Target Base:   Column 12, Row {res.target_row}")
    print(f" Total Steps:   {res.total_steps} (Columns 1 -> 12)")
    print(f" Radar Disarms: {res.radar_disarms}")
    print(f" Duration:      {res.execution_time_seconds}s")
    flag_display = res.flag or "[NONE / FAILED]"
    print(f" Flag:          {flag_display}")
    if res.error:
        print(f" Error:         {res.error}")
    print("-" * 55)
    print(" Trajectory Trace:")
    for step in res.trajectory:
        lock_label = "RADAR-DISARMED" if step.radar_locked else "radar-clear"
        rock_label = f"Rock: Row {step.rock_row}" if step.rock_row else "Spawn"
        print(
            f"   Col {step.column:2d} | Alt Row {step.row} | Cmd: {step.command:5s} | {rock_label:14s} | {lock_label}"
        )
    print("=" * 55 + "\n")


def main() -> None:
    """Developer CLI entrypoint supporting fast debugging and evaluation flags."""
    parser = argparse.ArgumentParser(
        description="cr-s05e04-goingthere: Autonomous Rocket Navigation & OKO Radar Neutralization"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Dynamic LLM override (e.g. gemini-3.5-flash-lite, gemini-3.8-flash)",
    )
    parser.add_argument(
        "--thinking-level",
        choices=["low", "medium", "high"],
        default=None,
        help="Reasoning effort level for Gemini models",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Custom session identifier for audit and workspace tracking",
    )
    parser.add_argument(
        "--step-by-step",
        "-i",
        action="store_true",
        help="Interactive mode pausing before each column thrust with terminal dashboard",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Fast 1-second pre-flight check verifying credentials and target base without flying",
    )
    parser.add_argument(
        "--direct-egress",
        action="store_true",
        help="Bypass cr-mcp-web-gateway and use direct httpx egress (recommended for local dev)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG level logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("services").setLevel(logging.DEBUG)

    req = RunTaskRequest(
        session_id=args.session_id,
        model=args.model,
        thinking_level=args.thinking_level,
        direct_egress=args.direct_egress,
    )

    controller = FlightController(
        request=req,
        direct_egress=args.direct_egress,
        interactive=args.step_by_step,
        verbose=args.verbose,
    )

    if args.probe:
        asyncio.run(controller.probe())
    else:
        result = asyncio.run(controller.run_flight())
        print_cli_summary(result)
        if result.status != "completed":
            sys.exit(1)


if __name__ == "__main__":
    main()
