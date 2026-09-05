import argparse
import asyncio
import logging
import sys
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

import config
from schemas import HealthResponse, RunTaskRequest, RunTaskResponse
from services.audit_service import generate_session_id
from agents.factory import get_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {config.TASK_NAME} service with default backend {config.BACKEND}")
    yield
    logger.info(f"Shutting down {config.TASK_NAME} service")


app = FastAPI(
    title="S02E03 Failure Diagnostic & Compression Service",
    version="0.1.0",
    description="Analyzes massive power plant operational telemetry, condenses incident logs under 1,500 tokens, and autonomously remediates technician feedback.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s02e03-failure",
        version="0.1.0",
    )


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    backend = request.backend or config.BACKEND
    session_id = request.session_id or generate_session_id(backend)
    logger.info(f"Received HTTP /run request for session={session_id}, backend={backend}")

    try:
        agent = get_agent(backend)
        result = await agent.solve(session_id=session_id, max_iterations=request.max_iterations)
        return result
    except Exception as e:
        logger.error(f"Error executing task for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(backend: str, max_iterations: int):
    session_id = generate_session_id(backend)
    print(f"\n==================================================")
    print(f"  S02E03 FAILURE LOG COMPRESSOR & REMEDIATION")
    print(f"  Session ID : {session_id}")
    print(f"  Backend    : {backend}")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print(f"==================================================\n")

    agent = get_agent(backend)
    response = await agent.solve(session_id=session_id, max_iterations=max_iterations)

    print(f"\n==================================================")
    print(f"  EXECUTION COMPLETED")
    print(f"  Status       : {response.status}")
    print(f"  Iterations   : {response.iterations}")
    print(f"  Token Count  : {response.token_count} / {config.MAX_TOKENS_LIMIT}")
    print(f"  Flag         : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Notes File   : {response.notes_file}")
    print(f"==================================================\n")

    if response.flag:
        print(f"Flag successfully retrieved: {response.flag}\n")
    else:
        print(f"Warning: Flag not retrieved within {max_iterations} iterations.\n")


def main():
    parser = argparse.ArgumentParser(description="S02E03 failure log compressor & technician remediation")
    parser.add_argument(
        "--backend",
        choices=["langchain", "genai"],
        default=config.BACKEND,
        help="Wybór frameworka do użycia w operacji operacyjnej (domyślnie langchain)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Maksymalna liczba iteracji weryfikacji z Centralą (domyślnie 5)",
    )
    args = parser.parse_args()
    asyncio.run(run_cli(backend=args.backend, max_iterations=args.iterations))


if __name__ == "__main__":
    main()
