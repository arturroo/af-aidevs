from contextvars import ContextVar

# ContextVar to store session_id across the request lifespan for auditability
x_session_id_ctx: ContextVar[str] = ContextVar("x_session_id", default="unknown")

# Mapping from MCP Session ID to session data dict
SESSION_MAPPING: dict[str, dict] = {}
