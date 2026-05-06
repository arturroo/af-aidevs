import os
import logging
import json
from typing import List
from pathlib import Path
from fastmcp import FastMCP
from pydantic import Field
import google.auth
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# The workspace root is determined by the mounted GCS bucket (Cloud Storage FUSE)
# Typically mounted at /mnt/workspaces
WORKSPACE_MOUNT_ROOT = Path(os.getenv("WORKSPACE_MOUNT_ROOT", "/mnt/workspaces"))

# ContextVar to store session_id across the request lifespan
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="unknown")

# Resource identification for logging
RESOURCE_NAME = "cr-mcp-workspace"

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
    print(json.dumps(audit_entry), flush=True)

# Create the MCP Server
mcp = FastMCP("Workspace_Manager", description="Global file management MCP server with OIDC isolation")

# Middleware to extract session_id from headers (compatible with SSE/HTTP)
async def session_id_middleware(request: Request, call_next):
    session_id = request.headers.get("X-Session-ID", "unknown")
    token = session_id_ctx.set(session_id)
    try:
        return await call_next(request)
    finally:
        session_id_ctx.reset(token)

# Attach middleware to the internal Starlette app
mcp._app.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)

def get_caller_identity() -> str:
    """Returns the cleaned service account name for workspace isolation."""
    # TODO: Implement actual OIDC token decoding from X-Forwarded-Authorization or Authorization headers
    # For now, return a mock or default identity
    full_email = "sa-agent-s01e05@af-aidevs.iam.gserviceaccount.com"
    
    # Extract the part before "@" and remove "sa-" prefix
    sa_name = full_email.split("@")[0]
    if sa_name.startswith("sa-"):
        sa_name = sa_name[len("sa-"):]
        
    return sa_name

@mcp.tool()
def list_files(path: str = Field(description="Directory path relative to your workspace root to list. Example: '.' or 'logs'")) -> List[str]:
    """Lists files in the agent's isolated workspace directory."""
    workspace_name = get_caller_identity()
    
    # Isolate to caller's directory
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name).resolve()
    target_path = (agent_workspace / path).resolve()
    
    # Security: Ensure target path doesn't escape the agent's workspace
    if not str(target_path).startswith(str(agent_workspace)):
        raise PermissionError("Access denied. Path traversal attempt detected.")
        
    if not target_path.exists():
        log_audit("workspace", f"List files in {path} - Result: Not Found", {"workspace": workspace_name, "path": path})
        return []
        
    files = [f.name for f in target_path.iterdir()]
    log_audit("workspace", f"List files in {path}", {"workspace": workspace_name, "path": path, "count": len(files)})
    return files

@mcp.tool()
def read_file(file_path: str = Field(description="Relative path to the file to read")) -> str:
    """Reads the complete content of a file in the workspace."""
    workspace_name = get_caller_identity()
    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name).resolve()
    target_path = (agent_workspace / file_path).resolve()
    
    if not str(target_path).startswith(str(agent_workspace)):
        log_audit("workspace", "Read file - Access Denied", {"workspace": workspace_name, "file_path": file_path})
        raise PermissionError("Access denied.")
        
    content = target_path.read_text(encoding="utf-8")
    log_audit("workspace", f"Read file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content)})
    return content

@mcp.tool()
def write_file(file_path: str = Field(description="Relative path to the file to write"), 
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
    
    log_to_bq("workspace", f"Write file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content)})
    return f"File successfully written to {file_path}"

if __name__ == "__main__":
    # For Cloud Run, FastMCP exposes an ASGI app we can run with uvicorn or just use run()
    # When deployed to Cloud Run, it's recommended to use the SSE transport for HTTP
    mcp.run(transport="sse", port=int(os.getenv("PORT", "8080")))
