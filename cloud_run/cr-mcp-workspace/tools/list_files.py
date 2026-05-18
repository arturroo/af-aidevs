import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from state import SESSION_MAPPING
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

class WorkspaceResponse(BaseModel):
    status: str = Field(description="Status operacji: 'success' lub 'error'")
    files: Optional[List[Dict[str, Any]]] = Field(default=None, description="Lista plików i katalogów z metadanymi")
    message: Optional[str] = Field(default=None, description="Komunikat o błędzie lub statusie")
    hint: Optional[str] = Field(default=None, description="Podpowiedź dla agenta, co powinien zrobić")

def register_list_files(mcp: FastMCP):
    @mcp.tool()
    async def list_files(path: str = Field(description="Directory path relative to your session workspace to list. Example: '.'"), 
                         ctx: Context = CurrentContext()) -> WorkspaceResponse:
        """Lists files and directories in the agent's session workspace directory with metadata."""
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
        
        # Ensure the session workspace exists before we try to list it
        agent_workspace.mkdir(parents=True, exist_ok=True)
        
        target_path = (agent_workspace / path).resolve()
        
        # Security: Ensure target path doesn't escape the agent's workspace
        if not str(target_path).startswith(str(agent_workspace)):
            log_audit("workspace", "List files - Access Denied", {"workspace": workspace_name, "path": path, "absolute_path": str(target_path)}, session_id=x_session_id)
            return WorkspaceResponse(
                status="error",
                message="Access denied. Path traversal attempt detected.",
                hint="You are confined to your workspace directory. You cannot use '..' to go outside. Use '.' to list the root of your workspace."
            )
            
        if not target_path.exists():
            log_audit("workspace", f"List files in {path} - Result: Not Found", {"workspace": workspace_name, "path": path, "absolute_path": str(target_path)}, session_id=x_session_id)
            return WorkspaceResponse(
                status="error",
                message=f"Directory '{path}' not found.",
                hint="Check if the directory exists. Use '.' to see available files in the root directory."
            )
            
        files = []
        for f in target_path.iterdir():
            try:
                is_dir = f.is_dir()
                files.append({
                    "name": f.name,
                    "type": "directory" if is_dir else "file",
                    "size_bytes": f.stat().st_size if not is_dir else 0
                })
            except Exception:
                # Skip files that are inaccessible or deleted mid-iteration
                continue
                
        log_audit("workspace", f"List files in {path}", {"workspace": workspace_name, "path": path, "count": len(files), "absolute_path": str(target_path)}, session_id=x_session_id)
        return WorkspaceResponse(
            status="success",
            files=files
        )
