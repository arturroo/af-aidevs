import time
from typing import List
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from state import SESSION_MAPPING
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

def register_list_files(mcp: FastMCP):
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
