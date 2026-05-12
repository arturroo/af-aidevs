import os
import logging
import json
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from schemas import ArmorRequest, ArmorResponse
from agent import check_safety

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ContextVar to store session_id across the request lifespan
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="unknown")

app = FastAPI(title="Model Armor API")

# Resource identification for logging
RESOURCE_NAME = "cr-model-armor"

def log_audit(actor: str, content: str, metadata: dict, session_id: str):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": RESOURCE_NAME,
        "session_id": session_id,
        "actor": actor,
        "content": content,
        "metadata": metadata
    }
    print(json.dumps(audit_entry), flush=True)

# Middleware to extract session_id from headers
async def session_id_middleware(request: Request, call_next):
    session_id = request.headers.get("X-Session-ID", "unknown")
    token = session_id_ctx.set(session_id)
    try:
        response = await call_next(request)
    finally:
        session_id_ctx.reset(token)
    return response

app.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)

@app.post("/verify", response_model=ArmorResponse)
async def verify_safety(request: ArmorRequest, background_tasks: BackgroundTasks):
    """
    Evaluates input text against a provided policy context.
    Calls the agent logic and returns the result.
    """
    session_id = session_id_ctx.get()
    try:
        # Call the agent logic
        result = check_safety(request)
        
        # Log the interaction in the background
        background_tasks.add_task(
            log_audit,
            actor="model-armor",
            content=f"Decision: {result.decision}",
            metadata={
                "input": request.input,
                "policy": request.policy_context,
                "reasoning": result.reasoning
            },
            session_id=session_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error evaluating safety: {e}")
        # Fail closed - if we can't verify, consider it unsafe
        raise HTTPException(status_code=500, detail="Safety verification failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
