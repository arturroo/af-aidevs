import os
import time
import json
from typing import Optional
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
        "metadata": metadata
    }
    # Lean Logging: print to stdout for Log Sinks to pick up asynchronously
    print(json.dumps(audit_entry), flush=True)

def get_safe_path(relative_path: str, ctx: Context, check_file: bool = False, max_size_bytes: Optional[int] = None) -> Path:
    """Validates session, updates activity, and returns a secure resolved Path.
    
    Prevents path traversal attacks by validating workspace boundaries.
    If check_file is True, verifies that the file exists, is a file, and is not empty.
    If max_size_bytes is specified, checks that the file size does not exceed the limit.
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
        log_audit("workspace", "Access Denied - Path Traversal", 
                  {"workspace": workspace_name, "relative_path": relative_path, "resolved_path": str(target_path)}, 
                  session_id=x_session_id)
        raise PermissionError("Access denied: path traversal attempt detected.")
        
    if check_file:
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"File {relative_path} not found.")
        file_size = target_path.stat().st_size
        if file_size == 0:
            raise ValueError("File is empty.")
        if max_size_bytes is not None and file_size > max_size_bytes:
            raise ValueError(f"File size exceeds safety limit of {max_size_bytes} bytes.")
            
    return target_path
