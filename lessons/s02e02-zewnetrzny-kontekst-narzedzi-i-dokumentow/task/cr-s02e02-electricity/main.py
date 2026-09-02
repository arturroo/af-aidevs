import argparse
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from pydantic import BaseModel
import config
from agents.factory import AgentFactory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

app = FastAPI(title="S02E02 Electricity Solver Agent Service")


class TaskRequest(BaseModel):
    backend: str = config.BACKEND


@app.get("/")
def root():
    return {"message": "S02E02 Electricity Circuit Solver Agent Service", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
async def run_task(req: TaskRequest):
    result = await run_solver(backend=req.backend)
    return {"status": "success", "result": result}


async def run_solver(backend: str):
    session_id = f"s02e02_{backend}_{datetime.now(ZURICH_TZ).strftime('%Y%m%d_%H%M%S')}"

    # Instantiate and trigger autonomous agent
    agent = AgentFactory.create(backend=backend)
    result = await agent.solve(session_id=session_id)

    print(
        f"\n--- Execution Result ({backend}) ---\nSession ID: {session_id}\nStatus: {result.status}\nFlag: {result.flag}\nReasoning:\n{result.reasoning}\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="S02E02 Electricity Circuit Solver")
    parser.add_argument(
        "--backend",
        choices=["langchain", "adk"],
        default=config.BACKEND,
        help=f"Choice of orchestration backend framework (default: {config.BACKEND})",
    )
    args = parser.parse_args()
    asyncio.run(run_solver(backend=args.backend))


if __name__ == "__main__":
    main()
