import os
import logging
import time
import asyncio
from typing import Dict, Any

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from pydantic import Field
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from state import SESSION_MAPPING, x_session_id_ctx
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

# --- 1. CONFIGURATION ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# --- 2. MCP SERVER INITIALIZATION ---
async def cleanup_sessions():
    """Periodically removes expired sessions from SESSION_MAPPING."""
    while True:
        await asyncio.sleep(600)  # Check every 10 minutes
        now = time.time()
        expired = []
        for mcp_id, data in SESSION_MAPPING.items():
            if now - data["last_activity"] > 1800:  # 30 minutes
                expired.append(mcp_id)
        
        for mcp_id in expired:
            del SESSION_MAPPING[mcp_id]
            print(f"[DEBUG] Cleaned up expired session: {mcp_id}", flush=True)

class WebGatewayServer(FastMCP):
    @asynccontextmanager
    async def lifespan(self):
        task = asyncio.create_task(cleanup_sessions())
        try:
            yield
        finally:
            task.cancel()

mcp = WebGatewayServer("Web-Gateway")

# --- 3. TOOLS REGISTRATION ---
@mcp.tool()
async def fetch_web_resource(
    url: str = Field(description="The URL of the resource to fetch"),
    output_path: str = Field(description="The relative path where the fetched resource should be saved in the workspace"),
    ctx: Context = CurrentContext()
) -> str:
    """Downloads an external web resource (file) directly to the session's workspace."""
    mcp_session_id = ctx.session_id
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")
        
    workspace_name = session_data["caller_identity"]
    x_session_id = session_data["x_session_id"]
    
    # Update activity
    session_data["last_activity"] = time.time()
    
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
    target_path = (agent_workspace / output_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("web-gateway", "Fetch resource - Access Denied", {"workspace": workspace_name, "output_path": output_path, "absolute_path": str(target_path)}, session_id=x_session_id)
        raise PermissionError("Access denied: path traversal attempt detected.")
        
    try:
        log_audit("web-gateway", "Fetching URL", {"url": url, "output_path": output_path}, session_id=x_session_id)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(response.content)
        
        log_audit("web-gateway", "Fetched resource successfully", {"workspace": workspace_name, "output_path": output_path, "size": len(response.content)}, session_id=x_session_id)
        return f"Successfully fetched resource and saved to {output_path} (size: {len(response.content)} bytes)"
    except Exception as e:
        log_audit("web-gateway", "Fetch resource failed", {"url": url, "output_path": output_path, "error": str(e)}, session_id=x_session_id)
        raise Exception(f"Failed to fetch resource: {e}")

@mcp.tool()
async def post_web_resource(
    url: str = Field(description="The URL to send the POST request to"),
    payload: Dict[str, Any] = Field(description="The JSON payload to include in the body"),
    headers: Dict[str, str] = Field(default=None, description="Optional HTTP headers"),
    ctx: Context = CurrentContext()
) -> Dict[str, Any]:
    """Sends a POST request to an external web service and returns the response."""
    mcp_session_id = ctx.session_id
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")
        
    x_session_id = session_data["x_session_id"]
    session_data["last_activity"] = time.time()
    
    try:
        masked_payload = {k: ("***" if "key" in k.lower() else v) for k, v in payload.items()}
        logger.info(f"POST {url} | Headers: {headers} | Payload: {masked_payload}")
        log_audit("web-gateway", "POST request", {"url": url, "payload": masked_payload, "headers": headers}, session_id=x_session_id)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"Response from {url} -> Status: {response.status_code} | Headers: {dict(response.headers)}")
            
            if response.status_code >= 400:
                logger.error(f"POST {url} failed with {response.status_code} -> Body: {response.text}")
                log_audit("web-gateway", "POST request error", {
                    "url": url,
                    "status_code": response.status_code,
                    "response_headers": dict(response.headers),
                    "response_body": response.text
                }, session_id=x_session_id)
                
            response.raise_for_status()
            res_json = response.json()
            logger.info(f"Response Body JSON: {res_json}")
            
        log_audit("web-gateway", "POST request successful", {"url": url, "response": res_json}, session_id=x_session_id)
        return res_json
    except httpx.HTTPStatusError as e:
        error_details = f"HTTP {e.response.status_code}: {e.response.text}"
        logger.error(f"POST request to {url} failed: {error_details}")
        log_audit("web-gateway", "POST request failed", {
            "url": url,
            "error": error_details,
            "status_code": e.response.status_code,
            "response_body": e.response.text,
            "response_headers": dict(e.response.headers)
        }, session_id=x_session_id)
        raise Exception(f"POST request failed: {error_details}")
    except Exception as e:
        logger.error(f"POST request to {url} encountered exception: {e}")
        log_audit("web-gateway", "POST request failed", {"url": url, "error": str(e)}, session_id=x_session_id)
        raise Exception(f"POST request failed: {e}")

# --- 4. MIDDLEWARE ---
async def session_id_middleware(request: Request, call_next):
    """Middleware to extract session_id from headers for auditability and verification."""
    mcp_session_id = request.headers.get("mcp-session-id")
    x_session_id = request.headers.get("X-Session-ID")
    
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})
        
    token = auth_header.split(" ")[1]
    try:
        id_info = id_token.verify_oauth2_token(token, google_requests.Request())
        
        if "email" in id_info:
            if not id_info.get("email_verified") or not id_info.get("email").endswith("@af-aidevs.iam.gserviceaccount.com"):
                return JSONResponse(status_code=403, content={"detail": "Domain not allowed or email not verified"})
            caller_identity = id_info.get("email")
        else:
            # Strict fallback for Artur's test impersonated token
            ALLOWED_TEST_SUB = "110832476443475170542"
            if id_info.get("sub") != ALLOWED_TEST_SUB:
                return JSONResponse(status_code=403, content={"detail": "Access denied: Unknown identity"})
            caller_identity = "sa-cr-s01e05-agent-integration-test"
            
        if "@" in caller_identity:
            caller_identity = caller_identity.split("@")[0]
            
        print(f"[DEBUG] Verified caller: {caller_identity}", flush=True)
    except Exception as e:
        print(f"[ERROR] Token verification failed: {e}", flush=True)
        return JSONResponse(status_code=401, content={"detail": f"Token verification failed: {e}"})
    
    if mcp_session_id and x_session_id:
        if mcp_session_id not in SESSION_MAPPING:
            SESSION_MAPPING[mcp_session_id] = {
                "x_session_id": x_session_id,
                "caller_identity": caller_identity,
                "cre_ts": time.time(),
                "last_activity": time.time()
            }
            print(f"[DEBUG] Mapped MCP Session {mcp_session_id} to X-Session-ID {x_session_id}", flush=True)
        else:
            SESSION_MAPPING[mcp_session_id]["last_activity"] = time.time()
            SESSION_MAPPING[mcp_session_id]["caller_identity"] = caller_identity
        
    x_session_id = x_session_id or "unknown"
    token_ctx = x_session_id_ctx.set(x_session_id)
    try:
        return await call_next(request)
    finally:
        x_session_id_ctx.reset(token_ctx)

app = mcp.http_app()

app.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
