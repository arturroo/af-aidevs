import os
import logging
import time
import asyncio

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from contextlib import asynccontextmanager
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from state import SESSION_MAPPING, x_session_id_ctx
from tools.filesystem.read_file import register_read_file
from tools.filesystem.write_file import register_write_file
from tools.filesystem.list_files import register_list_files
from tools.rag.grep import register_grep
from tools.rag.head import register_head
from tools.rag.tail import register_tail
from tools.rag.read_markdown_section import register_read_markdown_section
from tools.rag.list_markdown_sections import register_list_markdown_sections

# --- 1. CONFIGURATION ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# --- 2. MCP SERVER INITIALIZATION ---
# --- 2. HTTP TRANSPORT & MIDDLEWARE ---
async def cleanup_sessions():
    """Periodically removes expired sessions from SESSION_MAPPING."""
    while True:
        await asyncio.sleep(600) # Check every 10 minutes
        now = time.time()
        expired = []
        for mcp_id, data in SESSION_MAPPING.items():
            if now - data["last_activity"] > 1800: # 30 minutes
                expired.append(mcp_id)
        
        for mcp_id in expired:
            del SESSION_MAPPING[mcp_id]
            print(f"[DEBUG] Cleaned up expired session: {mcp_id}", flush=True)

class WorkspaceManager(FastMCP):
    @asynccontextmanager
    async def lifespan(self):
        task = asyncio.create_task(cleanup_sessions())
        try:
            yield
        finally:
            task.cancel()

# --- 3. MCP SERVER INITIALIZATION ---
mcp = WorkspaceManager("Workspace-Manager")

# --- 4. TOOLS REGISTRATION ---
register_read_file(mcp)
register_write_file(mcp)
register_list_files(mcp)
register_grep(mcp)
register_head(mcp)
register_tail(mcp)
register_read_markdown_section(mcp)
register_list_markdown_sections(mcp)

async def session_id_middleware(request: Request, call_next):
    """Middleware to extract session_id from headers for auditability."""
    # print(f"[DEBUG] All Headers: {dict(request.headers)}", flush=True)
    
    mcp_session_id = request.headers.get("mcp-session-id")
    x_session_id = request.headers.get("X-Session-ID")
    
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})
        
    token = auth_header.split(" ")[1]
    try:
        id_info = id_token.verify_oauth2_token(token, google_requests.Request())
        # print(f"[DEBUG] Token Claims: {id_info}", flush=True)
        
        # Check if email claim is present (user accounts and some SA tokens)
        if "email" in id_info:
            if not id_info.get("email_verified") or not id_info.get("email").endswith("@af-aidevs.iam.gserviceaccount.com"):
                return JSONResponse(status_code=403, content={"detail": "Domain not allowed or email not verified"})
            caller_identity = id_info.get("email")
        else:
            # Strict fallback for Artur's test impersonated token
            ALLOWED_TEST_SUB = "110832476443475170542"
            
            if id_info.get("sub") != ALLOWED_TEST_SUB:
                return JSONResponse(status_code=403, content={"detail": "Access denied: Unknown identity"})
            
            # If it matches, we know it's our test SA!
            caller_identity = "sa-cr-s01e05-agent-integration-test@af-aidevs.iam.gserviceaccount.com"
            print(f"[DEBUG] Recognized test SA via sub claim. Mapping to: {caller_identity}", flush=True)
            
        # Compromise: Strip domain but KEEP the 'sa-' prefix for clarity!
        if "@" in caller_identity:
            caller_identity = caller_identity.split("@")[0]
            
        print(f"[DEBUG] Verified caller: {caller_identity}", flush=True)
    except Exception as e:
        print(f"[ERROR] Token verification failed: {e}", flush=True)
        return JSONResponse(status_code=401, content={"detail": f"Token verification failed: {e}"})
    
    if mcp_session_id and x_session_id:
        if mcp_session_id not in SESSION_MAPPING:
            SESSION_MAPPING[mcp_session_id] = {
                "x_session_id": x_session_id,
                "caller_identity": caller_identity,
                "cre_ts": time.time(),
                "last_activity": time.time()
            }
            print(f"[DEBUG] Mapped MCP Session {mcp_session_id} to X-Session-ID {x_session_id}", flush=True)
        else:
            # Update last activity and identity on subsequent requests
            SESSION_MAPPING[mcp_session_id]["last_activity"] = time.time()
            SESSION_MAPPING[mcp_session_id]["caller_identity"] = caller_identity
        
    x_session_id = x_session_id or "unknown"
    token_ctx = x_session_id_ctx.set(x_session_id)
    try:
        return await call_next(request)
    finally:
        x_session_id_ctx.reset(token_ctx)



# Create the Starlette app from MCP instance AFTER tools registration
app = mcp.http_app()

# middleware are executed in REVERSE order of addition (last added is outermost)
# 1. First wrap with session ID handling
app.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)

# 2. Then wrap with CORS (must be OUTERMOST to handle preflights correctly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"] # Ensure the client can see the MCP session ID
)

# --- DEBUG: Print registered routes (including Mounts) ---
print("\n[DEBUG] Registered Starlette Routes:")
def print_routes(routes, prefix=""):
    for route in routes:
        if hasattr(route, 'path'):
            methods = getattr(route, "methods", "N/A")
            print(f"  {methods} {prefix}{route.path}")
        if hasattr(route, 'routes'): # Handle Mounts
            print_routes(route.routes, prefix=getattr(route, 'path', ""))

print_routes(app.routes)
print("-" * 35 + "\n")

# --- 5. ENTRYPOINT ---
if __name__ == "__main__":
    import uvicorn
    # For local testing; Cloud Run will use uvicorn via Procfile (web: uvicorn main:app ...)
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
