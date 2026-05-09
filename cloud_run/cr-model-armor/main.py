import os
import logging
import json
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware

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
    # Using logger.info with extra or just print(json.dumps)
    # Cloud Run automatically captures stdout as structured logs if it's a JSON string.
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

class ArmorRequest(BaseModel):
    input: str = Field(description="The text to analyze for safety")
    policy_context: str = Field(description="Context defining what is considered safe or unsafe for this specific invocation")

class ArmorResponse(BaseModel):
    decision: Literal["safe", "unsafe"] = Field(
        description="The safety evaluation result. Must be either 'safe' or 'unsafe'.",
        json_schema_extra={"example": "safe"}
    )
    reasoning: str = Field(
        description="Detailed explanation of the decision based on the provided policy context.",
        json_schema_extra={"example": "The input does not contain any sensitive information or policy violations."}
    )

@app.post("/verify", response_model=ArmorResponse)
async def verify_safety(request: ArmorRequest, background_tasks: BackgroundTasks):
    """
    Evaluates input text against a provided policy context using Gemini Flash-Lite.
    Returns whether the text is safe or unsafe.
    """
    session_id = session_id_ctx.get()
    try:
        client = genai.Client()
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        
        system_instruction = f"""
        You are an impartial safety judge (Model Armor).
        Your task is to verify whether the input violates the organizational policy provided below.
        
        ORGANIZATIONAL POLICY FOR THIS TASK:
        {request.policy_context}
        """
        
        response = client.models.generate_content(
            model=model_name,
            contents=request.input,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=ArmorResponse,
            )
        )
        
        result = response.parsed
        
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
