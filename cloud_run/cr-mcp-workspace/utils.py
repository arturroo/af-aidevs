import json
from state import x_session_id_ctx
from config import RESOURCE_NAME

def log_audit(actor: str, content: str, metadata: dict):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": RESOURCE_NAME,
        "session_id": x_session_id_ctx.get(),
        "actor": actor,
        "content": content,
        "metadata": metadata
    }
    # Lean Logging: print to stdout for Log Sinks to pick up asynchronously
    print(json.dumps(audit_entry), flush=True)
