import time
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from state import SESSION_MAPPING
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

def register_write_file(mcp: FastMCP):
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
