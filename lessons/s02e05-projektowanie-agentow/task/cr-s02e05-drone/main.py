import argparse
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

import config
from schemas import HealthResponse, RunTaskRequest, RunTaskResponse
from services.audit_service import generate_session_id
from agents.factory import create_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting cr-s02e05-drone service with default backend {config.BACKEND}")
    yield
    logger.info("Shutting down cr-s02e05-drone service")


app = FastAPI(
    title="S02E05 Zero-Trust Preemptive Strike Drone Service",
    version="0.1.0",
    description="Autonomous military drone strike agent executing visual coordinate discovery, documentation RAG, and iterative verification.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s02e05-drone",
        version="0.1.0",
    )


@app.get("/")
async def root():
    return {
        "service": "cr-s02e05-drone",
        "task": config.TASK_NAME,
        "target": config.MISSION_TARGET,
        "status": "ready",
    }


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    backend = request.backend or config.BACKEND
    session_id = request.session_id or generate_session_id(backend)
    logger.info(f"Received HTTP /run request for session={session_id}, backend={backend}")

    try:
        agent = create_agent(backend)
        result = await agent.solve(session_id=session_id, max_iterations=request.max_iterations)
        return result
    except Exception as e:
        logger.error(f"Error executing drone task for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(backend: str, max_iterations: int, session_id: str | None = None):
    chosen_session = session_id or generate_session_id(backend)
    print("\n==================================================")
    print("  S02E05 PREEMPTIVE STRIKE DRONE AGENT")
    print(f"  Session ID : {chosen_session}")
    print(f"  Backend    : {backend}")
    print(f"  Model      : {config.GEMINI_MODEL} (thinking: {config.THINKING_LEVEL})")
    print(f"  Target     : {config.MISSION_TARGET}")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print("==================================================\n")

    agent = create_agent(backend)
    response = await agent.solve(session_id=chosen_session, max_iterations=max_iterations)

    print("\n==================================================")
    print("  MISSION OUTCOME")
    print(f"  Status            : {response.status.upper()}")
    print(f"  Iterations Used   : {response.iterations}")
    if response.dam_coordinates:
        print(f"  Dam Coordinates   : (col={response.dam_coordinates.dam_column}, row={response.dam_coordinates.dam_row})")
    print(f"  Final Instructions: {response.instructions}")
    print(f"  Course Flag       : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Summary           : {response.summary}")
    print("==================================================\n")

    if response.flag:
        print(f"Preemptive strike successful! Flag: {response.flag}\n")
    else:
        print(f"Warning: Flag not captured within {max_iterations} attempts.\n")


def main():
    parser = argparse.ArgumentParser(description="S02E05 Preemptive Strike Drone Agent")
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND,
        help="Wybór frameworka do użycia w operacji operacyjnej (domyślnie langchain)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maksymalna liczba iteracji weryfikacji i korekty (domyślnie 10)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Opcjonalny niestandardowy identyfikator sesji",
    )
    args = parser.parse_args()

    asyncio.run(run_cli(backend=args.backend, max_iterations=args.max_iterations, session_id=args.session_id))


if __name__ == "__main__":
    main()
