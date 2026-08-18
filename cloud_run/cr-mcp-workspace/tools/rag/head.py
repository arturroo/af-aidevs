from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import HeadResponse

def register_head(mcp: FastMCP):
    @mcp.tool()
    async def head(
        reasoning: str = Field(description="Mandatory justification explaining why this head read is needed"),
        file_path: str = Field(description="Relative path to the file in the workspace"),
        lines: int = Field(default=10, ge=1, le=100, description="Number of lines to read from the top (max 100)"),
        ctx: Context = CurrentContext()
    ) -> HeadResponse:
        """Reads the first N lines of a file in the workspace securely, with length safety limits."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx, check_file=True)
            truncated_any = False
            lines_content = []
            max_line_bytes = 8192  # 8 KB safety limit
            
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                for _ in range(lines):
                    line = f.readline(max_line_bytes)
                    if not line:
                        break
                    if len(line) == max_line_bytes and not line.endswith("\n"):
                        truncated_any = True
                    lines_content.append(line)
            
            content = "".join(lines_content)
            hint = None
            if truncated_any:
                hint = "Some lines in the output were truncated because they exceeded the 8KB per-line safety limit."
                
            log_audit("workspace", f"Head file: {file_path}", {"workspace": workspace_name, "lines": lines, "truncated": truncated_any, "reasoning": reasoning}, session_id=x_session_id)
            return HeadResponse(content=content, hint=hint)
        except ValueError as ve:
            log_audit("workspace", f"Head file (empty): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return HeadResponse(content="", hint=str(ve))
        except Exception as e:
            log_audit("workspace", "Head failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Head operation failed: {e}")
