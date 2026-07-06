from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING

def register_write_file(mcp: FastMCP):
    @mcp.tool()
    async def write_file(file_path: str = Field(description="Relative path to the file to write in the session workspace"), 
                         content: str = Field(description="Content to write into the file"), 
                         ctx: Context = CurrentContext()) -> str:
        """Writes content to a file in the session workspace."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            log_audit("workspace", f"Write file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content), "absolute_path": str(target_path)}, session_id=x_session_id)
            return f"File successfully written to {file_path}"
        except Exception as e:
            log_audit("workspace", "Write file failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e)}, session_id=x_session_id)
            raise Exception(f"Write operation failed: {e}")
