from typing import List, Dict, Any, Optional
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from markdown_it import MarkdownIt

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import ListMarkdownSectionsResponse

def register_list_markdown_sections(mcp: FastMCP):
    @mcp.tool()
    async def list_markdown_sections(
        reasoning: str = Field(description="Mandatory justification explaining why listing headings is needed"),
        file_path: str = Field(description="Relative path to the markdown file in the workspace"),
        ctx: Context = CurrentContext()
    ) -> ListMarkdownSectionsResponse:
        """Parses a markdown file via AST and returns a list of all headings (with their level and title)."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            # Safely resolve path and enforce 5 MB max size check
            target_path = get_safe_path(file_path, ctx, check_file=True, max_size_bytes=5242880)
            content = target_path.read_text(encoding="utf-8")
            
            md = MarkdownIt()
            tokens = md.parse(content)
            
            sections = []
            for i, token in enumerate(tokens):
                if token.type == "heading_open":
                    level = int(token.tag[1])
                    next_token = tokens[i+1] if i + 1 < len(tokens) else None
                    if next_token and next_token.type == "inline":
                        sections.append({
                            "level": level,
                            "title": next_token.content.strip()
                        })
                        
            log_audit("workspace", f"List markdown sections", {"workspace": workspace_name, "file_path": file_path, "count": len(sections), "reasoning": reasoning}, session_id=x_session_id)
            return ListMarkdownSectionsResponse(sections=sections)
        except ValueError as ve:
            log_audit("workspace", f"List markdown sections (empty/too large): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return ListMarkdownSectionsResponse(sections=[], hint=str(ve))
        except Exception as e:
            log_audit("workspace", "List markdown sections failed", {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Failed to list markdown sections: {e}")
