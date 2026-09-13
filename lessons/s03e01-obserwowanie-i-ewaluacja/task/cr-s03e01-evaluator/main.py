import argparse
import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException

from agents.factory import create_evaluator
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
        f"Starting cr-s03e01-evaluator service with default backend {config.BACKEND}"
    )
    yield
    logger.info("Shutting down cr-s03e01-evaluator service")


app = FastAPI(
    title="S03E01 Zero-Trust Sensor Anomaly Evaluator Service",
    version="0.1.0",
    description="Industrial sensor telemetry evaluation service identifying physical and operator false-positive anomalies.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="cr-s03e01-evaluator",
        version="0.1.0",
    )


@app.get("/")
async def root():
    return {
        "service": "cr-s03e01-evaluator",
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
        evaluator = create_evaluator(backend)
        result = await evaluator.run(session_id=session_id)
        return result
    except Exception as e:
        logger.error(
            f"Error executing evaluator pipeline for session {session_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


async def run_cli(backend: str, session_id: Optional[str] = None):
    chosen_session = session_id or generate_session_id(backend)
    print("\n==================================================")
    print("  S03E01 INDUSTRIAL TELEMETRY ANOMALY EVALUATOR")
    print(f"  Session ID : {chosen_session}")
    print(f"  Backend    : {backend}")
    print(f"  Model      : {config.GEMINI_MODEL} (thinking: {config.THINKING_LEVEL})")
    print(f"  Task       : {config.TASK_NAME}")
    print(f"  Dataset    : {config.BQ_DATASET}")
    print("==================================================\n")

    evaluator = create_evaluator(backend)
    response = await evaluator.run(session_id=chosen_session)

    print("\n==================================================")
    print("  EVALUATION OUTCOME")
    print(f"  Status          : {response.status.upper()}")
    print(f"  Total Scanned   : {response.total_scanned}")
    print(f"  Anomalies Found : {response.anomalies_found}")
    print(f"  Sample Rechecks : {response.recheck[:10]}...")
    print(f"  Course Flag     : {response.flag or 'NOT_CAPTURED'}")
    print(f"  Hint            : {response.hint}")
    print("==================================================\n")

    if response.flag:
        print(f"Success! Captured course flag: {response.flag}\n")
    else:
        print(f"Verification completed. Centrala response: {response.verification_response}\n")


def main():
    parser = argparse.ArgumentParser(
        description="S03E01 Industrial Telemetry Anomaly Evaluator"
    )
    parser.add_argument(
        "--backend",
        choices=["langchain", "genai", "adk"],
        default=config.BACKEND,
        help="Framework backend for semantic note classification (default: langchain)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional explicit session ID (defaults to standardized Europe/Zurich timestamp format)",
    )

    args = parser.parse_args()
    asyncio.run(run_cli(backend=args.backend, session_id=args.session_id))


if __name__ == "__main__":
    main()
