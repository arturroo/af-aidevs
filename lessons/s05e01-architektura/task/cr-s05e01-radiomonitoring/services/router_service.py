import base64
import io
import json
import logging
import zipfile
from typing import Any

from schemas import CentralaListenResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService

logger = logging.getLogger("services.router")

MAX_ZIP_EXTRACT_SIZE = 50 * 1024 * 1024  # 50 MB safety ceiling against zip bombs


def detect_payload_type(buffer: bytes, meta_hint: str | None = None) -> str:
    """Classifies binary or text payloads using magic bytes, headers, and encoding tests."""
    if buffer.startswith(b"SQLite format 3\x00"):
        return "application/x-sqlite3"
    if buffer.startswith(b"PK\x03\x04"):
        return "application/zip"
    if buffer.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if buffer.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if buffer.startswith(b"RIFF") and len(buffer) >= 12 and buffer[8:12] == b"WEBP":
        return "image/webp"
    if buffer.startswith(b"RIFF") and len(buffer) >= 12 and buffer[8:12] == b"WAVE":
        return "audio/wav"
    if buffer.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3")):
        return "audio/mpeg"
    if buffer.startswith(b"OggS"):
        return "audio/ogg"

    # Check for text or JSON
    try:
        text = buffer.decode("utf-8")
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                json.loads(stripped)
                return "application/json"
            except Exception:
                pass
        if "# " in text or "## " in text or "- " in text:
            return "text/markdown"
        return "text/plain"
    except UnicodeDecodeError:
        pass

    if meta_hint:
        return meta_hint
    return "application/octet-stream"


def get_extension_for_mime(mime_type: str) -> str:
    mapping = {
        "application/x-sqlite3": ".sqlite",
        "application/zip": ".zip",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/ogg": ".ogg",
        "application/json": ".json",
        "text/markdown": ".md",
        "text/plain": ".txt",
    }
    return mapping.get(mime_type, ".bin")


class RouterService:
    """Deterministic routing and de-multiplexing engine for intercepted radio packets."""

    def __init__(
        self, mcp_service: MCPService, audit_service: AuditService | None = None
    ):
        self.mcp = mcp_service
        self.audit = audit_service

    async def unpack_zip(
        self, session_id: str, archive_stem: str, buffer: bytes
    ) -> list[dict[str, Any]]:
        """Safely unpacks ZIP archive into /decoded/{archive_stem}/ and returns lightweight manifest."""
        manifest = []
        with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_ZIP_EXTRACT_SIZE:
                raise ValueError(
                    f"ZIP archive exceeds uncompressed safety limit ({total_size} > {MAX_ZIP_EXTRACT_SIZE} bytes)"
                )

            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Path traversal defense
                raw_name = info.filename.replace("\\", "/")
                if ".." in raw_name or raw_name.startswith("/"):
                    logger.warning(f"Rejecting insecure path in zip: {raw_name}")
                    continue

                file_data = zf.read(info)
                file_mime = detect_payload_type(file_data)
                target_path = f"/decoded/{archive_stem}/{raw_name}"
                if file_mime.startswith("text/") or file_mime == "application/json":
                    try:
                        await self.mcp.write_file(
                            session_id, target_path, file_data.decode("utf-8")
                        )
                    except UnicodeDecodeError:
                        await self.mcp.write_file(session_id, target_path, file_data)
                else:
                    await self.mcp.write_file(session_id, target_path, file_data)

                manifest.append(
                    {
                        "path": target_path,
                        "mime": file_mime,
                        "size_bytes": len(file_data),
                    }
                )

        if self.audit:
            await self.audit.log_event(
                session_id=session_id,
                actor="router",
                content=f"ZIP unpacked: {archive_stem} ({len(manifest)} files extracted)",
                step_type="zip_unpack",
                metadata={
                    "archive": archive_stem,
                    "files": [m["path"] for m in manifest],
                },
            )
        return manifest

    async def ingest_packet(
        self, session_id: str, packet_index: int, packet: CentralaListenResponse
    ) -> list[dict[str, Any]]:
        """Lands raw envelope into /raw/ and normalized artifacts into /decoded/. Returns list of target files."""
        # 1. Land raw packet into /raw/
        raw_path = f"/raw/packet_{packet_index:03d}.json"
        raw_json = packet.model_dump_json(indent=2)
        await self.mcp.write_file(session_id, raw_path, raw_json)

        artifacts: list[dict[str, Any]] = []

        # 2. Case A: Text transcript
        if packet.transcription:
            text_path = f"/decoded/packet_{packet_index:03d}.txt"
            await self.mcp.write_file(session_id, text_path, packet.transcription)
            artifacts.append(
                {
                    "path": text_path,
                    "mime": "text/plain",
                    "size_bytes": len(packet.transcription.encode("utf-8")),
                    "content_text": packet.transcription,
                }
            )

        # 3. Case B: Binary attachment
        if packet.attachment:
            try:
                binary_bytes = base64.b64decode(packet.attachment)
            except Exception as e:
                logger.error(
                    f"Failed to decode base64 attachment in packet {packet_index}: {e}"
                )
                return artifacts

            mime_type = detect_payload_type(binary_bytes, packet.meta)
            ext = get_extension_for_mime(mime_type)

            if mime_type == "application/zip":
                archive_stem = f"archive_{packet_index:03d}"
                unpacked = await self.unpack_zip(session_id, archive_stem, binary_bytes)
                artifacts.extend(unpacked)
            else:
                artifact_path = f"/decoded/packet_{packet_index:03d}{ext}"
                if mime_type.startswith("text/") or mime_type == "application/json":
                    try:
                        await self.mcp.write_file(
                            session_id, artifact_path, binary_bytes.decode("utf-8")
                        )
                    except UnicodeDecodeError:
                        await self.mcp.write_file(
                            session_id, artifact_path, binary_bytes
                        )
                else:
                    await self.mcp.write_file(session_id, artifact_path, binary_bytes)
                artifacts.append(
                    {
                        "path": artifact_path,
                        "mime": mime_type,
                        "size_bytes": len(binary_bytes),
                    }
                )

        return artifacts
