from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import ReadFileResponse

def register_read_file(mcp: FastMCP):
    @mcp.tool()
    async def read_file(
        reasoning: str = Field(description="Mandatory justification explaining why this file needs to be read"),
        file_path: str = Field(description="Relative path to the file to read from the session workspace"),
        ctx: Context = CurrentContext()
    ) -> ReadFileResponse:
        """Reads the complete content of a file in the session workspace."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx, check_file=True, max_size_bytes=5242880, allow_shared_fallback=True)
            content = target_path.read_text(encoding="utf-8")
            log_audit("workspace", f"Read file: {file_path}", {"workspace": workspace_name, "file_path": file_path, "size": len(content), "absolute_path": str(target_path), "reasoning": reasoning}, session_id=x_session_id)
            return ReadFileResponse(content=content)
        except ValueError as ve:
            log_audit("workspace", f"Read file (empty): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return ReadFileResponse(content="", hint=str(ve))
        except FileNotFoundError:
            raise
        except Exception as e:
            log_audit("workspace", "Read file failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Access denied or read error: {e}")
