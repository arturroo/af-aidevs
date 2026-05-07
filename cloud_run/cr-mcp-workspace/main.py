import os
import logging
import json
from typing import List
from pathlib import Path
from contextvars import ContextVar

from fastmcp import FastMCP
from pydantic import Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

# --- 1. CONFIGURATION & CONSTANTS ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# The workspace root is determined by the mounted GCS bucket (Cloud Storage FUSE)
# Typically mounted at /mnt/workspaces
WORKSPACE_MOUNT_ROOT = Path(os.getenv("WORKSPACE_MOUNT_ROOT", "/mnt/workspaces"))
RESOURCE_NAME = "cr-mcp-workspace"

# --- 2. STATE & CONTEXT ---
# ContextVar to store session_id across the request lifespan for auditability
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="unknown")

# --- 3. AUDIT & UTILS ---
def log_audit(actor: str, content: str, metadata: dict):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": RESOURCE_NAME,
        "session_id": session_id_ctx.get(),
        "actor": actor,
        "content": content,
        "metadata": metadata
    }
    # Lean Logging: print to stdout for Log Sinks to pick up asynchronously
    print(json.dumps(audit_entry), flush=True)

def get_caller_identity() -> str:
    """Returns the cleaned service account name for workspace isolation."""
    # TODO (Tomorrow): Implement actual OIDC token decoding from 'Authorization: Bearer <ID_TOKEN>'
    # 1. Extract token from request headers
    # 2. Use google.oauth2.id_token.verify_oauth2_token to decode
    # 3. Validate if 'email_verified' is true and domain is '@af-aidevs.iam.gserviceaccount.com'
    # 4. Remove this hardcoded mock:
    full_email = "sa-agent-s01e05@af-aidevs.iam.gserviceaccount.com"
    
    # Extract the part before "@" and remove "sa-" prefix
    sa_name = full_email.split("@")[0]
    if sa_name.startswith("sa-"):
        sa_name = sa_name[len("sa-"):]
        
    return sa_name

# --- 4. MCP SERVER INITIALIZATION ---
mcp = FastMCP("Workspace-Manager")

# --- 5. TOOLS DEFINITION ---
@mcp.tool()
def list_files(path: str = Field(description="Directory path relative to your workspace root to list. Example: '.' or 'logs'")) -> List[str]:
    """Lists files in the agent's workspace directory."""
    workspace_name = get_caller_identity()
    
    # Isolate to caller's directory
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name).resolve()
    target_path = (agent_workspace / path).resolve()
    
    # Security: Ensure target path doesn't escape the agent's workspace
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "List files - Access Denied", {"workspace": workspace_name, "path": path})
        raise PermissionError("Access denied. Path traversal attempt detected.")
        
    if not target_path.exists():
        log_audit("workspace", f"List files in {path} - Result: Not Found", {"workspace": workspace_name, "path": path})
        return []
        
    files = [f.name for f in target_path.iterdir()]
    log_audit("workspace", f"List files in {path}", {"workspace": workspace_name, "path": path, "count": len(files)})
    return files

@mcp.tool()
def read_file(file_path: str = Field(description="Relative path to the file to read from the workspace")) -> str:
    """Reads the complete content of a file in the workspace."""
    workspace_name = get_caller_identity()
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name).resolve()
    target_path = (agent_workspace / file_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "Read file - Access Denied", {"workspace": workspace_name, "file_path": file_path})
        raise PermissionError("Access denied.")
        
    if not target_path.is_file():
        raise FileNotFoundError(f"File {file_path} not found.")
        
    content = target_path.read_text(encoding="utf-8")
    log_audit("workspace", f"Read file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content)})
    return content

@mcp.tool()
def write_file(file_path: str = Field(description="Relative path to the file to write in the workspace"), 
               content: str = Field(description="Content to write into the file")) -> str:
    """Writes content to a file in the workspace."""
    workspace_name = get_caller_identity()
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name).resolve()
    target_path = (agent_workspace / file_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "Write file - Access Denied", {"workspace": workspace_name, "file_path": file_path})
        raise PermissionError("Access denied.")
        
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    
    log_audit("workspace", f"Write file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content)})
    return f"File successfully written to {file_path}"

# --- 6. HTTP TRANSPORT & MIDDLEWARE ---
# We use a simple function middleware to avoid BaseHTTPMiddleware issues with streaming
async def session_id_middleware(request: Request, call_next):
    """Middleware to extract session_id from headers for auditability."""
    session_id = request.headers.get("X-Session-ID", "unknown")
    token = session_id_ctx.set(session_id)
    try:
        return await call_next(request)
    finally:
        session_id_ctx.reset(token)

# Create the Starlette app from MCP instance AFTER tools registration
app = mcp.http_app()

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
