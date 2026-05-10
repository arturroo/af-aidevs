import time
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from state import SESSION_MAPPING
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

def register_read_file(mcp: FastMCP):
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
