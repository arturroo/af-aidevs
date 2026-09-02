import os
import re
import time
import json
from typing import Optional, Tuple
from pathlib import Path
from fastmcp.server.context import Context
from config import RESOURCE_NAME, WORKSPACE_MOUNT_ROOT
from state import SESSION_MAPPING


def log_audit(actor: str, content: str, metadata: dict, session_id: str = "unknown"):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": RESOURCE_NAME,
        "session_id": session_id,
        "actor": actor,
        "content": content,
        "metadata": metadata,
    }
    # Lean Logging: print to stdout for Log Sinks to pick up asynchronously
    print(json.dumps(audit_entry), flush=True)


def extract_lesson_id(workspace_name: str) -> Optional[str]:
    """Extracts authoritative lesson identifier (e.g. 's02e02') strictly and exclusively

    from the cryptographically verified Google IAM Service Account identity (e.g. 'sa-cr-s02e02-...').
    No unauthenticated or header-based fallbacks allowed.
    """
    if not workspace_name:
        return None

    match = re.search(r"s\d{2}e\d{2}", workspace_name, re.IGNORECASE)
    return match.group(0).lower() if match else None


def get_safe_path(
    relative_path: str,
    ctx: Context,
    check_file: bool = False,
    max_size_bytes: Optional[int] = None,
    allow_shared_fallback: bool = False,
) -> Path:
    """Validates session, updates activity, and returns a secure resolved Path.

    Enforces Multi-Layered Virtual File System (OverlayFS):
    - Upper Layer (Read-Write Session): WORKSPACE_MOUNT_ROOT / caller / session_id / relative_path
    - Lower Layer (Read-Only Shared Base): WORKSPACE_MOUNT_ROOT / shared / lesson_id / relative_path
    """
    mcp_session_id = ctx.session_id
    session_data = SESSION_MAPPING.get(mcp_session_id)
    if not session_data:
        raise PermissionError("Access denied. Session expired or invalid.")

    workspace_name = session_data["caller_identity"]
    x_session_id = session_data["x_session_id"]

    # Update activity timestamp
    session_data["last_activity"] = time.time()

    agent_workspace = (WORKSPACE_MOUNT_ROOT / workspace_name / x_session_id).resolve()
    target_path = (agent_workspace / relative_path).resolve()

    if not str(target_path).startswith(str(agent_workspace)):
        log_audit(
            "workspace",
            "Access Denied - Path Traversal",
            {"workspace": workspace_name, "relative_path": relative_path, "resolved_path": str(target_path)},
            session_id=x_session_id,
        )
        raise PermissionError("Access denied: path traversal attempt detected.")

    # OverlayFS Resolution: Fallback to Read-Only Shared Layer if file does not exist in Session Layer
    if allow_shared_fallback and (not target_path.exists()):
        lesson_id = extract_lesson_id(workspace_name)
        if lesson_id:
            shared_workspace = (WORKSPACE_MOUNT_ROOT / "shared" / lesson_id).resolve()
            shared_path = (shared_workspace / relative_path).resolve()
            if str(shared_path).startswith(str(shared_workspace)) and shared_path.exists():
                target_path = shared_path

    if check_file:
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"File {relative_path} not found.")
        file_size = target_path.stat().st_size
        if file_size == 0:
            raise ValueError("File is empty.")
        if max_size_bytes is not None and file_size > max_size_bytes:
            raise ValueError(f"File size exceeds safety limit of {max_size_bytes} bytes.")

    return target_path
