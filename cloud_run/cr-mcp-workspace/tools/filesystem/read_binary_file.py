import base64
import hashlib
import mimetypes
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from utils import get_safe_path, log_audit
from state import SESSION_MAPPING
from schemas import ReadBinaryFileResponse

MAX_BINARY_FILE_SIZE = 50 * 1024 * 1024  # 50 MB circuit breaker


def register_read_binary_file(mcp: FastMCP):
    @mcp.tool()
    async def read_binary_file(
        reasoning: str = Field(description="Mandatory justification explaining why this binary file needs to be read"),
        file_path: str = Field(description="Relative path to the binary file to read from the session workspace"),
        ctx: Context = CurrentContext(),
    ) -> ReadBinaryFileResponse:
        """Reads a binary file from the session workspace, enforcing a 50MB safety limit, returning Base64 and SHA-256."""
        mcp_session_id = ctx.session_id
        session_data = SESSION_MAPPING.get(mcp_session_id)
        x_session_id = session_data["x_session_id"] if session_data else "unknown"
        workspace_name = session_data["caller_identity"] if session_data else "unknown"

        try:
            target_path = get_safe_path(
                file_path,
                ctx,
                check_file=True,
                max_size_bytes=MAX_BINARY_FILE_SIZE,
                allow_shared_fallback=True,
            )
            raw_bytes = target_path.read_bytes()
            size = len(raw_bytes)
            content_base64 = base64.b64encode(raw_bytes).decode("ascii")
            sha256_checksum = hashlib.sha256(raw_bytes).hexdigest()
            guessed_type, _ = mimetypes.guess_type(file_path)
            mime_type = guessed_type or "application/octet-stream"

            log_audit(
                "workspace",
                f"Read binary file: {file_path}",
                {
                    "workspace": workspace_name,
                    "file_path": file_path,
                    "size": size,
                    "mime_type": mime_type,
                    "sha256": sha256_checksum,
                    "reasoning": reasoning,
                },
                session_id=x_session_id,
            )
            return ReadBinaryFileResponse(
                status="success",
                content_base64=content_base64,
                size_bytes=size,
                mime_type=mime_type,
                sha256=sha256_checksum,
                hint="Binary file read successfully. Decode base64 to process.",
            )
        except ValueError as ve:
            log_audit(
                "workspace",
                f"Read binary file error: {file_path}",
                {"workspace": workspace_name, "file_path": file_path, "error": str(ve), "reasoning": reasoning},
                session_id=x_session_id,
            )
            raise Exception(f"Validation error: {ve}")
        except FileNotFoundError:
            raise
        except Exception as e:
            log_audit(
                "workspace",
                "Read binary file failed",
                {"workspace": workspace_name, "file_path": file_path, "error": str(e), "reasoning": reasoning},
                session_id=x_session_id,
            )
            raise Exception(f"Access denied or binary read error: {e}")
