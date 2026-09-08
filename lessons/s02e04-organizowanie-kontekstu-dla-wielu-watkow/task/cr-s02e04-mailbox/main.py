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
    logger.info(f"Starting cr-s02e04-mailbox service with default backend {config.BACKEND}")
    yield
    logger.info("Shutting down cr-s02e04-mailbox service")


app = FastAPI(
    title="S02E04 Zero-Trust Mailbox Investigation Service",
    version="0.1.0",
    description="Autonomous cyber intelligence agent investigating compromised operator mailbox via Zmail API, Model Armor screening, and Centrala verification.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s02e04-mailbox",
        version="0.1.0",
    )


@app.post("/run", response_model=RunTaskResponse)
async def run_task(request: RunTaskRequest):
    backend = request.backend or config.BACKEND
    session_id = generate_session_id(backend)
    logger.info(f"Received HTTP /run request for session={session_id}, backend={backend}")

    try:
        agent = create_agent(backend)
        result = await agent.solve(session_id=session_id, max_iterations=request.max_iterations)
        return result
    except Exception as e:
        logger.error(f"Error executing task for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(backend: str, max_iterations: int):
    session_id = generate_session_id(backend)
    print(f"\n==================================================")
    print(f"  S02E04 ZERO-TRUST MAILBOX INVESTIGATION AGENT")
    print(f"  Session ID : {session_id}")
    print(f"  Backend    : {backend}")
    print(f"  Model      : {config.GEMINI_MODEL} (thinking: {config.THINKING_LEVEL})")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print(f"==================================================\n")

    agent = create_agent(backend)
    response = await agent.solve(session_id=session_id, max_iterations=max_iterations)

    print(f"\n==================================================")
    print(f"  INVESTIGATION COMPLETED")
    print(f"  Status            : {response.status}")
    print(f"  Iterations        : {response.iterations}")
    print(f"  Attack Date       : {response.date or 'NOT_FOUND'}")
    print(f"  Employee Password : {response.password or 'NOT_FOUND'}")
    print(f"  Confirmation Code : {response.confirmation_code or 'NOT_FOUND'}")
    print(f"  Course Flag       : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Notes File        : {response.notes_file}")
    print(f"==================================================\n")

    if response.flag:
        print(f"Success! Captured course flag: {response.flag}\n")
    else:
        print(f"Warning: Flag not captured within {max_iterations} iterations.\n")


def main():
    parser = argparse.ArgumentParser(description="S02E04 Zero-Trust Mailbox Investigation Agent")
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
        help="Maksymalna liczba iteracji weryfikacji i pollingu skrzynki (domyślnie 10)",
    )
    args = parser.parse_args()

    asyncio.run(run_cli(backend=args.backend, max_iterations=args.max_iterations))


if __name__ == "__main__":
    main()
