from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from markdown_it import MarkdownIt

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import ReadMarkdownSectionResponse

def register_read_markdown_section(mcp: FastMCP):
    @mcp.tool()
    async def read_markdown_section(
        reasoning: str = Field(description="Mandatory justification explaining why this markdown section is being read"),
        file_path: str = Field(description="Relative path to the markdown file in the workspace"),
        header_title: str = Field(description="The heading title to search for (case-insensitive)"),
        ctx: Context = CurrentContext()
    ) -> ReadMarkdownSectionResponse:
        """Parses a markdown file via AST and returns the section under the specified header."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx, check_file=True, max_size_bytes=5242880)
            content = target_path.read_text(encoding="utf-8")
            
            md = MarkdownIt()
            tokens = md.parse(content)
            
            target_level = None
            target_index = -1
            
            for i, token in enumerate(tokens):
                if token.type == "heading_open":
                    level = int(token.tag[1])
                    next_token = tokens[i+1] if i + 1 < len(tokens) else None
                    if next_token and next_token.type == "inline":
                        heading_text = next_token.content.strip().lower()
                        if header_title.strip().lower() in heading_text:
                            target_level = level
                            target_index = i
                            break
                            
            if target_index == -1:
                return ReadMarkdownSectionResponse(content="", hint=f"Header '{header_title}' not found in the document.")
                
            lines = content.splitlines()
            start_line = tokens[target_index].map[0] if tokens[target_index].map else 0
            
            end_line = len(lines)
            for i in range(target_index + 1, len(tokens)):
                token = tokens[i]
                if token.type == "heading_open":
                    level = int(token.tag[1])
                    if level <= target_level:
                        if token.map:
                            end_line = token.map[0]
                            break
                            
            section_content = "\n".join(lines[start_line:end_line])
            log_audit("workspace", f"Read markdown section: {header_title}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return ReadMarkdownSectionResponse(content=section_content)
        except ValueError as ve:
            log_audit("workspace", f"Read markdown section (empty): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return ReadMarkdownSectionResponse(content="", hint=str(ve))
        except Exception as e:
            log_audit("workspace", "Read markdown section failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Failed to read markdown section: {e}")
