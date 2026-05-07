import argparse
import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

from agent_langchain import run_langchain_agent
from agent_adk import run_adk_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("s01e05_task")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

class TaskRequest(BaseModel):
    backend: str = "langchain"

@app.post("/run")
async def run_task(req: TaskRequest):
    logger.info(f"Starting agent with backend: {req.backend}")
    if req.backend == "langchain":
        await run_langchain_agent(BASE_DIR)
    else:
        await run_adk_agent(BASE_DIR)
    return {"status": "success", "backend": req.backend}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    # When deployed to Cloud Run, it must listen on PORT (default 8080)
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
