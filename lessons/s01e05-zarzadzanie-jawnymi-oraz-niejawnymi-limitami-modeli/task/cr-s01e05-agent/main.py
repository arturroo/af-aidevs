import argparse
import asyncio
import logging
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

from agent_langchain import run_langchain_agent
from agent_adk import run_adk_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("s01e05_task")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="S01E05 Agent Service")

# Request-response logging middleware for debuggability in Cloud Run
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url} | Headers: {dict(request.headers)}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code} for {request.method} {request.url.path}")
        return response
    except Exception as e:
        logger.error(f"Error processing request {request.method} {request.url.path}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error": str(e)}
        )

class TaskRequest(BaseModel):
    backend: str = "langchain"

@app.get("/")
def read_root():
    return {
        "message": "Welcome to S01E05 Agent Service",
        "endpoints": {
            "GET /": "Service info",
            "GET /health": "Health check",
            "POST /run": "Run the agent with specified backend (json payload: {'backend': 'langchain' | 'adk'})"
        }
    }

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

