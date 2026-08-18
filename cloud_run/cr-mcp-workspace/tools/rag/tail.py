from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import TailResponse

def register_tail(mcp: FastMCP):
    @mcp.tool()
    async def tail(
        reasoning: str = Field(description="Mandatory justification explaining why this tail read is needed"),
        file_path: str = Field(description="Relative path to the file in the workspace"),
        lines: int = Field(default=10, ge=1, le=100, description="Number of lines to read from the bottom (max 100)"),
        ctx: Context = CurrentContext()
    ) -> TailResponse:
        """Reads the last N lines of a file in the workspace securely, seeking from the end to avoid OOM."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx, check_file=True)
            file_size = target_path.stat().st_size
            
            read_buffer = 65536
            seek_pos = max(0, file_size - read_buffer)
            
            with open(target_path, "rb") as f:
                f.seek(seek_pos)
                raw_data = f.read()
                
            content = raw_data.decode("utf-8", errors="ignore")
            lines_list = content.splitlines()
            tail_lines = lines_list[-lines:]
            
            truncated_top = seek_pos > 0
            final_content = "\n".join(tail_lines)
            hint = None
            if truncated_top:
                hint = "File size exceeds safety limits. Showing only the tail end (last 64KB). Previous contents omitted."
                
            log_audit("workspace", f"Tail file: {file_path}", {"workspace": workspace_name, "lines": lines, "truncated_top": truncated_top, "reasoning": reasoning}, session_id=x_session_id)
            return TailResponse(content=final_content, hint=hint)
        except ValueError as ve:
            log_audit("workspace", f"Tail file (empty): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return TailResponse(content="", hint=str(ve))
        except Exception as e:
            log_audit("workspace", "Tail failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Tail operation failed: {e}")
