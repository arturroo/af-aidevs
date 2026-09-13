import hashlib
import mimetypes
from pathlib import Path
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import FileInfoResponse

MAX_HASH_FILE_SIZE = 50 * 1024 * 1024  # Compute SHA256 if <= 50 MB


def is_binary_file(file_path: Path, mime_type: str) -> bool:
    if mime_type.startswith("text/") or mime_type in [
        "application/json",
        "application/xml",
        "application/javascript",
    ]:
        return False
    try:
        with file_path.open("rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except Exception:
        return True


def register_get_file_info(mcp: FastMCP):
    @mcp.tool()
    async def get_file_info(
        reasoning: str = Field(description="Mandatory justification explaining why file metadata inspection is needed"),
        file_path: str = Field(description="Relative path to the file in the session workspace to inspect"),
        ctx: Context = CurrentContext(),
    ) -> FileInfoResponse:
        """Inspects file metadata (size, MIME type, binary status, SHA-256) without loading entire payload into LLM memory."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(
                file_path,
                ctx,
                check_file=False,
                allow_shared_fallback=True,
            )

            if not target_path.exists() or not target_path.is_file():
                log_audit(
                    "workspace",
                    f"Get file info - Not Found: {file_path}",
                    {"workspace": workspace_name, "file_path": file_path, "reasoning": reasoning},
                    session_id=x_session_id,
                )
                return FileInfoResponse(
                    status="error",
                    file_path=file_path,
                    size_bytes=0,
                    mime_type="",
                    is_binary=False,
                    hint=f"File '{file_path}' does not exist or is not a regular file.",
                )

            size_bytes = target_path.stat().st_size
            guessed_type, _ = mimetypes.guess_type(str(target_path))
            mime_type = guessed_type or "application/octet-stream"
            binary = is_binary_file(target_path, mime_type)

            sha256_checksum = None
            if size_bytes <= MAX_HASH_FILE_SIZE:
                sha256_checksum = hashlib.sha256(target_path.read_bytes()).hexdigest()

            hint = (
                "File is binary. Use read_binary_file tool to retrieve content."
                if binary
                else "File is text. Use read_file tool to retrieve content."
            )

            log_audit(
                "workspace",
                f"Get file info: {file_path}",
                {
                    "workspace": workspace_name,
                    "file_path": file_path,
                    "size": size_bytes,
                    "mime_type": mime_type,
                    "is_binary": binary,
                    "sha256": sha256_checksum,
                    "reasoning": reasoning,
                },
                session_id=x_session_id,
            )

            return FileInfoResponse(
                status="success",
                file_path=file_path,
                size_bytes=size_bytes,
                mime_type=mime_type,
                is_binary=binary,
                sha256=sha256_checksum,
                hint=hint,
            )
        except PermissionError as pe:
            return FileInfoResponse(
                status="error",
                file_path=file_path,
                size_bytes=0,
                mime_type="",
                is_binary=False,
                hint=f"Access denied: {pe}",
            )
        except Exception as e:
            log_audit(
                "workspace",
                "Get file info failed",
                {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning},
                session_id=x_session_id,
            )
            return FileInfoResponse(
                status="error",
                file_path=file_path,
                size_bytes=0,
                mime_type="",
                is_binary=False,
                hint=f"Get file info failed: {e}",
            )
