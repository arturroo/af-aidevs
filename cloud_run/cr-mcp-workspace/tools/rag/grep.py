import subprocess
from typing import List, Optional
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import GrepResponse

def register_grep(mcp: FastMCP):
    @mcp.tool()
    async def grep(
        reasoning: str = Field(description="Mandatory justification explaining why this search is needed"),
        pattern: str = Field(description="The pattern/string to search for"),
        file_path: str = Field(description="The relative path of the file to search in"),
        flags: Optional[List[str]] = Field(default=None, description="Optional allowed grep flags: -i, -n, -v, -C, -A, -B followed by value (e.g. ['-i', '-n'])"),
        ctx: Context = CurrentContext()
    ) -> GrepResponse:
        """Executes a safe grep command on a file within the workspace boundaries."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(file_path, ctx, check_file=True)

            # Whitelist checks for flags
            allowed_flags = {"-i", "-n", "-v", "-C", "-A", "-B"}
            cmd_args = ["grep"]
            
            if flags:
                for flag in flags:
                    clean_flag = flag.strip()
                    parts = clean_flag.split()
                    f = parts[0]
                    if f not in allowed_flags:
                        raise ValueError(f"Flag {f} is not allowed. Only {allowed_flags} are permitted.")
                    if "-r" in parts or "-R" in parts:
                        raise ValueError("Recursive grep is strictly forbidden.")
                    cmd_args.extend(parts)

            cmd_args.extend([pattern, str(target_path)])
            
            log_audit("workspace", f"Grep command execution", {"args": cmd_args, "reasoning": reasoning}, session_id=x_session_id)
            res = subprocess.run(cmd_args, capture_output=True, text=True, check=False)
            
            if res.returncode == 0:
                return GrepResponse(results=res.stdout)
            elif res.returncode == 1:
                return GrepResponse(results="", hint="No matches found.")
            else:
                raise Exception(f"Grep error (code {res.returncode}): {res.stderr}")
        except ValueError as ve:
            log_audit("workspace", f"Grep (empty file): {file_path}", {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning}, session_id=x_session_id)
            return GrepResponse(results="", hint=f"No matches found ({ve}).")
        except Exception as e:
            log_audit("workspace", "Grep failed", {"error": str(e), "reasoning": reasoning}, session_id=x_session_id)
            raise Exception(f"Grep execution failed: {e}")
