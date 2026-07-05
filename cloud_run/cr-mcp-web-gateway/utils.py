import json
from config import RESOURCE_NAME

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
    print(json.dumps(audit_entry), flush=True)
