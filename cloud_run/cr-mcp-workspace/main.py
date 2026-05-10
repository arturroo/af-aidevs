import os
import logging
import json
import time
import asyncio
from typing import List
from pathlib import Path
from contextvars import ContextVar

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from pydantic import Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# --- 1. CONFIGURATION & CONSTANTS ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# The workspace root is determined by the mounted GCS bucket (Cloud Storage FUSE)
# Typically mounted at /mnt/workspaces
WORKSPACE_MOUNT_ROOT = Path(os.getenv("WORKSPACE_MOUNT_ROOT", "/mnt/workspaces"))
RESOURCE_NAME = "cr-mcp-workspace"

# --- 2. STATE & CONTEXT ---
# ContextVar to store session_id across the request lifespan for auditability
x_session_id_ctx: ContextVar[str] = ContextVar("x_session_id", default="unknown")

# Mapping from MCP Session ID to X-Session-ID
SESSION_MAPPING: dict[str, str] = {}

# --- 3. AUDIT & UTILS ---
def log_audit(actor: str, content: str, metadata: dict):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": RESOURCE_NAME,
        "session_id": x_session_id_ctx.get(),
        "actor": actor,
        "content": content,
        "metadata": metadata
    }
    # Lean Logging: print to stdout for Log Sinks to pick up asynchronously
    print(json.dumps(audit_entry), flush=True)

# --- 4. MCP SERVER INITIALIZATION ---

# --- 4. MCP SERVER INITIALIZATION ---
mcp = FastMCP("Workspace-Manager")

# --- 5. TOOLS DEFINITION ---
@mcp.tool()
async def list_files(path: str = Field(description="Directory path relative to your session workspace to list. Example: '.'"), 
                     ctx: Context = CurrentContext()) -> List[str]:
    """Lists files in the agent's session workspace directory."""
    mcp_session_id = ctx.session_id
    
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")
        
    workspace_name = session_data["caller_identity"]
    x_session_id = session_data["x_session_id"]
    
    # Update activity
    session_data["last_activity"] = time.time()
        
    # Isolate to caller's directory and session
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
    target_path = (agent_workspace / path).resolve()
    
    # Security: Ensure target path doesn't escape the agent's workspace
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "List files - Access Denied", {"workspace": workspace_name, "path": path, "absolute_path": str(target_path)})
        raise PermissionError("Access denied. Path traversal attempt detected.")
        
    if not target_path.exists():
        log_audit("workspace", f"List files in {path} - Result: Not Found", {"workspace": workspace_name, "path": path, "absolute_path": str(target_path)})
        return []
        
    files = [f.name for f in target_path.iterdir()]
    log_audit("workspace", f"List files in {path}", {"workspace": workspace_name, "path": path, "count": len(files), "absolute_path": str(target_path)})
    return files

@mcp.tool()
async def read_file(file_path: str = Field(description="Relative path to the file to read from the session workspace"), 
                    ctx: Context = CurrentContext()) -> str:
    """Reads the complete content of a file in the session workspace."""
    mcp_session_id = ctx.session_id
    
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")
        
    workspace_name = session_data["caller_identity"]
    x_session_id = session_data["x_session_id"]
    
    # Update activity
    session_data["last_activity"] = time.time()
    
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
    target_path = (agent_workspace / file_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "Read file - Access Denied", {"workspace": workspace_name, "file_path": file_path, "absolute_path": str(target_path)})
        raise PermissionError("Access denied.")
        
    try:
        if not target_path.is_file():
            raise FileNotFoundError(f"File {file_path} not found.")
            
        content = target_path.read_text(encoding="utf-8")
        log_audit("workspace", f"Read file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content), "absolute_path": str(target_path)})
        return content
    except FileNotFoundError:
        raise
    except Exception as e:
        log_audit("workspace", "Read file failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "absolute_path": str(target_path)})
        raise Exception("Access denied: permission denied or invalid path in workspace.")

@mcp.tool()
async def write_file(file_path: str = Field(description="Relative path to the file to write in the session workspace"), 
                     content: str = Field(description="Content to write into the file"), 
                     ctx: Context = CurrentContext()) -> str:
    """Writes content to a file in the session workspace."""
    mcp_session_id = ctx.session_id
    
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")
        
    workspace_name = session_data["caller_identity"]
    x_session_id = session_data["x_session_id"]
    
    # Update activity
    session_data["last_activity"] = time.time()
    
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
    target_path = (agent_workspace / file_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "Write file - Access Denied", {"workspace": workspace_name, "file_path": file_path, "absolute_path": str(target_path)})
        raise PermissionError("Access denied.")
        
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        log_audit("workspace", f"Write file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content), "absolute_path": str(target_path)})
        return f"File successfully written to {file_path}"
    except Exception as e:
        log_audit("workspace", "Write file failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "absolute_path": str(target_path)})
        raise Exception("Access denied: permission denied or invalid path in workspace.")

async def cleanup_sessions():
    """Periodically removes expired sessions from SESSION_MAPPING."""
    while True:
        await asyncio.sleep(600) # Check every 10 minutes
        now = time.time()
        expired = []
        for mcp_id, data in SESSION_MAPPING.items():
            if now - data["last_activity"] > 1800: # 30 minutes
                expired.append(mcp_id)
        
        for mcp_id in expired:
            del SESSION_MAPPING[mcp_id]
            print(f"[DEBUG] Cleaned up expired session: {mcp_id}", flush=True)

# We use a simple function middleware to avoid BaseHTTPMiddleware issues with streaming
async def session_id_middleware(request: Request, call_next):
    """Middleware to extract session_id from headers for auditability."""
    print(f"[DEBUG] All Headers: {dict(request.headers)}", flush=True)
    
    mcp_session_id = request.headers.get("mcp-session-id")
    x_session_id = request.headers.get("X-Session-ID")
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})
        
    token = auth_header.split(" ")[1]
    try:
        # Verify OIDC token
        id_info = id_token.verify_oauth2_token(token, google_requests.Request())
        
        if not id_info.get("email_verified") or not id_info.get("email").endswith("@af-aidevs.iam.gserviceaccount.com"):
            return JSONResponse(status_code=403, content={"detail": "Domain not allowed or email not verified"})
            
        caller_email = id_info.get("email")
        caller_identity = caller_email.split("@")[0]
        if caller_identity.startswith("sa-"):
            caller_identity = caller_identity[len("sa-"):]
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
            # Update last activity and identity on subsequent requests
            SESSION_MAPPING[mcp_session_id]["last_activity"] = time.time()
            SESSION_MAPPING[mcp_session_id]["caller_identity"] = caller_identity
        
    x_session_id = x_session_id or "unknown"
    token = x_session_id_ctx.set(x_session_id)
    try:
        return await call_next(request)
    finally:
        x_session_id_ctx.reset(token)

# Create the Starlette app from MCP instance AFTER tools registration
app = mcp.http_app()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_sessions())

# middleware are executed in REVERSE order of addition (last added is outermost)
# 1. First wrap with session ID handling
app.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)

# 2. Then wrap with CORS (must be OUTERMOST to handle preflights correctly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"] # Ensure the client can see the MCP session ID
)

# --- DEBUG: Print registered routes (including Mounts) ---
print("\n[DEBUG] Registered Starlette Routes:")
def print_routes(routes, prefix=""):
    for route in routes:
        if hasattr(route, 'path'):
            methods = getattr(route, "methods", "N/A")
            print(f"  {methods} {prefix}{route.path}")
        if hasattr(route, 'routes'): # Handle Mounts
            print_routes(route.routes, prefix=getattr(route, 'path', ""))

print_routes(app.routes)
print("-" * 35 + "\n")

# --- 7. ENTRYPOINT ---
if __name__ == "__main__":
    import uvicorn
    # For local testing; Cloud Run will use uvicorn via Procfile (web: uvicorn main:app ...)
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
