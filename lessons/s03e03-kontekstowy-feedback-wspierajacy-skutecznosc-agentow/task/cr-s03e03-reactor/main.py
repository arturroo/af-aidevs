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
        f"Starting cr-s03e03-reactor service with default backend {config.BACKEND}"
    )
    yield
    logger.info("Shutting down cr-s03e03-reactor service")


app = FastAPI(
    title="S03E03 Autonomous Reactor Core Navigation Service",
    version="0.1.0",
    description="Microservice guiding a transport robot across a 7x5 reactor grid to deliver the cooling module.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s03e03-reactor",
        version="0.1.0",
    )


@app.get("/")
async def root():
    return {
        "service": "cr-s03e03-reactor",
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
        result = await agent.solve(
            session_id=session_id, max_iterations=request.max_iterations or 25
        )
        return result
    except Exception as e:
        logger.error(
            f"Error executing reactor agent for session {session_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(
    backend: str, session_id: Optional[str] = None, max_iterations: int = 25
):
    chosen_session = session_id or generate_session_id(backend)
    print("\n==================================================")
    print("  S03E03 AUTONOMOUS REACTOR NAVIGATION")
    print(f"  Session ID : {chosen_session}")
    print(f"  Backend    : {backend}")
    print(f"  Model      : {config.GEMINI_MODEL} (thinking: {config.THINKING_LEVEL})")
    print(f"  Task       : {config.TASK_NAME}")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print("==================================================\n")

    agent = create_agent(backend)
    response = await agent.solve(
        session_id=chosen_session, max_iterations=max_iterations
    )

    print("\n==================================================")
    print("  MISSION OUTCOME")
    print(f"  Status          : {response.status.upper()}")
    print(f"  Steps Executed  : {response.steps_executed}")
    print(f"  Planned Path    : {' -> '.join(response.planned_commands or [])}")
    print(f"  Executed Path   : {' -> '.join(response.executed_commands or [])}")
    print(f"  Course Flag     : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Details         : {response.details}")
    print("==================================================\n")

    if response.flag:
        print(f"Mission Success! Captured course flag: {response.flag}\n")
    else:
        print("Reactor navigation finished without flag.\n")


def main():
    parser = argparse.ArgumentParser(
        description="S03E03 Autonomous Reactor Core Navigation Agent"
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
        help="Optional explicit session ID (defaults to standardized Europe/Zurich format)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=25,
        help="Maximum supervisory reasoning steps (default: 25)",
    )

    args = parser.parse_args()
    asyncio.run(
        run_cli(
            backend=args.backend,
            session_id=args.session_id,
            max_iterations=args.max_iterations,
        )
    )


if __name__ == "__main__":
    main()
