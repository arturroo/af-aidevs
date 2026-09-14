import argparse
import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException

from agents.factory import create_agent
import config
from schemas import HealthResponse, RunTaskRequest, RunTaskResponse
from services.audit_service import generate_session_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting cr-s03e02-firmware service with default backend {config.BACKEND}"
    )
    yield
    logger.info("Shutting down cr-s03e02-firmware service")


app = FastAPI(
    title="S03E02 ECCS Controller Firmware Diagnostics Service",
    version="0.1.0",
    description="Microservice diagnosing and remediating ECCS firmware failure on sandboxed Linux VM.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s03e02-firmware",
        version="0.1.0",
    )


@app.get("/")
async def root():
    return {
        "service": "cr-s03e02-firmware",
        "task": config.TASK_NAME,
        "status": "ready",
        "model": config.GEMINI_MODEL,
        "location": config.GOOGLE_CLOUD_LOCATION,
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    backend = request.backend or config.BACKEND
    session_id = request.session_id or generate_session_id(backend)
    logger.info(
        f"Received HTTP /run request for session={session_id}, backend={backend}"
    )

    try:
        agent = create_agent(backend)
        result = await agent.solve(session_id=session_id)
        return result
    except Exception as e:
        logger.error(
            f"Error executing firmware agent for session {session_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(backend: str, session_id: Optional[str] = None, max_iterations: int = 15):
    chosen_session = session_id or generate_session_id(backend)
    print("\n==================================================")
    print("  S03E02 ECCS CONTROLLER FIRMWARE DIAGNOSTICS")
    print(f"  Session ID : {chosen_session}")
    print(f"  Backend    : {backend}")
    print(f"  Model      : {config.GEMINI_MODEL} (thinking: {config.THINKING_LEVEL})")
    print(f"  Task       : {config.TASK_NAME}")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print("==================================================\n")

    agent = create_agent(backend)
    response = await agent.solve(session_id=chosen_session, max_iterations=max_iterations)

    print("\n==================================================")
    print("  DIAGNOSTIC OUTCOME")
    print(f"  Status          : {response.status.upper()}")
    print(f"  Steps Executed  : {response.steps_executed}")
    print(f"  Token Extracted : {response.confirmation_code or 'NONE'}")
    print(f"  Course Flag     : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Details         : {response.details}")
    print("==================================================\n")

    if response.flag:
        print(f"Success! Captured course flag: {response.flag}\n")
    else:
        print("Firmware troubleshooting finished without flag.\n")


def main():
    parser = argparse.ArgumentParser(
        description="S03E02 ECCS Controller Firmware Troubleshooting Agent"
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND,
        help="Framework backend for autonomous agent execution (default: langchain)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional explicit session ID (defaults to standardized Europe/Zurich timestamp format)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Maximum diagnostic iterations (default: 15)",
    )

    args = parser.parse_args()
    asyncio.run(run_cli(backend=args.backend, session_id=args.session_id, max_iterations=args.max_iterations))


if __name__ == "__main__":
    main()
