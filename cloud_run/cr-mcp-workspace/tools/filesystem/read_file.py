from pydantic import BaseModel, Field
from typing import Optional
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING

class FileContentResponse(BaseModel):
    content: str = Field(description="The original content read from the file")
    hint: Optional[str] = Field(default=None, description="Optional hint or system notice about the file content")

def register_read_file(mcp: FastMCP):
    @mcp.tool()
    async def read_file(file_path: str = Field(description="Relative path to the file to read from the session workspace"), 
                        ctx: Context = CurrentContext()) -> FileContentResponse:
        """Reads the complete content of a file in the session workspace."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx)
            if not target_path.is_file():
                raise FileNotFoundError(f"File {file_path} not found.")
                
            content = target_path.read_text(encoding="utf-8")
            log_audit("workspace", f"Read file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content), "absolute_path": str(target_path)}, session_id=x_session_id)
            return FileContentResponse(content=content)
        except FileNotFoundError:
            raise
        except Exception as e:
            log_audit("workspace", "Read file failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e)}, session_id=x_session_id)
            raise Exception(f"Access denied or read error: {e}")
