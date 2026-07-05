import time
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from state import SESSION_MAPPING
from config import WORKSPACE_MOUNT_ROOT
from utils import log_audit

def register_head(mcp: FastMCP):
    @mcp.tool()
    async def head(
        file_path: str = Field(description="Relative path to the file in the workspace"),
        lines: int = Field(default=10, ge=1, le=100, description="Number of lines to read from the top (max 100)"),
        ctx: Context = CurrentContext()
    ) -> str:
        """Reads the first N lines of a file in the workspace."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        if not session_data:
            raise PermissionError("Access denied. Session expired or invalid.")
            
        workspace_name = session_data["caller_identity"]
        x_session_id = session_data["x_session_id"]
        session_data["last_activity"] = time.time()
        
        agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
        target_path = (agent_workspace / file_path).resolve()
        
        if not str(target_path).startswith(str(agent_workspace)):
            log_audit("workspace", "Head - Access Denied", {"workspace": workspace_name, "file_path": file_path, "absolute_path": str(target_path)}, session_id=x_session_id)
            raise PermissionError("Access denied: path traversal detected.")
            
        try:
            if not target_path.is_file():
                raise FileNotFoundError(f"File {file_path} not found.")
                
            with open(target_path, "r", encoding="utf-8") as f:
                head_lines = [next(f) for _ in range(lines)]
            
            content = "".join(head_lines)
            log_audit("workspace", f"Head file: {file_path}", {"workspace": workspace_name, "lines": lines}, session_id=x_session_id)
            return content
        except StopIteration:
            # File has fewer lines than requested
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
            log_audit("workspace", f"Head file (full read): {file_path}", {"workspace": workspace_name, "lines": lines}, session_id=x_session_id)
            return content
        except Exception as e:
            log_audit("workspace", "Head failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e)}, session_id=x_session_id)
            raise Exception(f"Head operation failed: {e}")
