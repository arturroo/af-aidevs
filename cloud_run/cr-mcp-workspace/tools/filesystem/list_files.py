from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit, extract_lesson_id
from config import WORKSPACE_MOUNT_ROOT
from state import SESSION_MAPPING
from schemas import ListFilesResponse


def register_list_files(mcp: FastMCP):
    @mcp.tool()
    async def list_files(
        reasoning: str = Field(description="Mandatory justification explaining why directory listing is needed"),
        path: str = Field(default=".", description="Directory path relative to your session workspace to list. Example: '.'"),
        ctx: Context = CurrentContext(),
    ) -> ListFilesResponse:
        """Lists files and directories in the agent's multi-layered workspace directory with metadata."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            root_path = get_safe_path(".", ctx)
            root_path.mkdir(parents=True, exist_ok=True)

            target_path = get_safe_path(path, ctx)

            files_map = {}

            # 1. OverlayFS: Scan Read-Only Shared Base Layer first
            lesson_id = extract_lesson_id(workspace_name)
            if lesson_id:
                shared_workspace = (WORKSPACE_MOUNT_ROOT / "shared" / lesson_id).resolve()
                shared_target = (shared_workspace / path).resolve()
                if shared_target.exists() and shared_target.is_dir() and str(shared_target).startswith(str(shared_workspace)):
                    for f in shared_target.iterdir():
                        try:
                            is_dir = f.is_dir()
                            files_map[f.name] = {
                                "name": f.name,
                                "type": "directory" if is_dir else "file",
                                "size_bytes": f.stat().st_size if not is_dir else 0,
                            }
                        except Exception:
                            continue

            # 2. OverlayFS: Scan Read-Write Session Layer (overrides shared layer on collisions)
            if target_path.exists() and target_path.is_dir():
                for f in target_path.iterdir():
                    try:
                        is_dir = f.is_dir()
                        files_map[f.name] = {
                            "name": f.name,
                            "type": "directory" if is_dir else "file",
                            "size_bytes": f.stat().st_size if not is_dir else 0,
                        }
                    except Exception:
                        continue

            if not files_map and not target_path.exists():
                log_audit(
                    "workspace",
                    f"List files in {path} - Result: Not Found",
                    {"workspace": workspace_name, "path": path, "absolute_path": str(target_path), "reasoning": reasoning},
                    session_id=x_session_id,
                )
                return ListFilesResponse(
                    status="error",
                    message=f"Directory '{path}' not found.",
                    hint="Check if the directory exists. Use '.' to see available files in the root directory.",
                )

            files = list(files_map.values())
            log_audit(
                "workspace",
                f"List files in {path}",
                {"workspace": workspace_name, "path": path, "count": len(files), "reasoning": reasoning},
                session_id=x_session_id,
            )
            return ListFilesResponse(status="success", files=files)
        except PermissionError as pe:
            return ListFilesResponse(
                status="error",
                message=str(pe),
                hint="You are confined to your workspace directory. You cannot use '..' to escape.",
            )
        except Exception as e:
            return ListFilesResponse(status="error", message=f"List files failed: {e}")
