import json
import os
import urllib.request
import logging
from google.cloud import bigquery
from fastmcp import FastMCP
from contextvars import ContextVar

# ContextVar to store session_id across the request lifespan
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="unknown")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.getenv("BQ_AUDIT_TABLE") or "bq-s01e03-audit"

mcp = FastMCP("Hub-Packages-MCP")

AIDEVS_API_PACKAGES = os.environ["AIDEVS_API_PACKAGES"]
AIDEVS_API_KEY = os.environ["AIDEVS_API_KEY"]

def log_to_bq(action: str, details: dict):
    try:
        # Retrieve session_id from context
        session_id = session_id_ctx.get()
        row = {
            "session_id": session_id,
            "action": action, 
            "details": json.dumps(details)
        }
        if "." in AUDIT_TABLE_ID:
            errors = bq_client.insert_rows_json(AUDIT_TABLE_ID, [row])
            if errors:
                logger.error(f"BQ Audit Error: {errors}")
        else:
            logger.info(f"Audit log (Simulation/Dry-Run): {row}")
    except Exception as e:
        logger.error(f"Failed to log to BQ: {e}")

import re

def validate_package_id(packageid: str) -> tuple[bool, str]:
    """
    Validates if packageid follows the PKG + 8 digits format.
    Returns (True, "") if valid, or (False, error_description) if invalid.
    """
    # Strict match
    if re.match(r"^PKG\d{8}$", packageid):
        return True, ""
    
    # Fuzzy matching to help the LLM explain the error
    clean_id = packageid.strip().upper()
    prefix = f"Provided package id '{packageid}' is invalid. "
    if "PKG" in clean_id:
        match = re.search(r"PKG\s*\d+", clean_id)
        if match:
            found = match.group(0)
            if len(found) == 11: # PKG + 8 digits
                return False, prefix + f"The ID looks almost correct ('{found}'), but there are extra characters or it's incorrectly placed."
            return False, prefix + f"I found a partial match '{found}', but it doesn't have exactly 8 digits."
    
    return False, prefix + "It must be exactly 'PKG' followed by 8 digits (e.g., PKG12345678). Analyze the user's input and explain what's wrong."

@mcp.tool()
def check_package(packageid: str) -> str:
    """Check the contents and current destination of a package."""
    corrections = []
    # Normalize to uppercase and track correction
    if any(c.islower() for c in packageid):
        old_id = packageid
        packageid = packageid.upper()
        corrections.append(f"Normalized package ID from '{old_id}' to uppercase '{packageid}'.")

    log_to_bq("check_package_attempt", {"packageid": packageid, "corrections": corrections})
    
    is_valid, error_detail = validate_package_id(packageid)
    if not is_valid:
        return json.dumps({
            "status": "error",
            "error": "Validation failed",
            "details": error_detail,
            "instruction_for_model": "Analyze the provided input and the error details. If you are able to fix the package id to the right format then fix it and try again else explain to the user exactly what is wrong with their package ID (e.g., missing prefix, wrong length, typo) in a concise, human-like way."
        })

    if not AIDEVS_API_KEY:
        return json.dumps({"error": "AIDEVS_API_KEY missing in server configuration."})

    data = {
        "apikey": AIDEVS_API_KEY,
        "action": "check",
        "packageid": packageid
    }
    
    req = urllib.request.Request(
        AIDEVS_API_PACKAGES,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode('utf-8')
            log_to_bq("check_package_success", {"packageid": packageid, "response": result})
            
            # Inject corrections if any
            if corrections:
                try:
                    res_json = json.loads(result)
                    res_json["_tool_corrections"] = corrections
                    return json.dumps(res_json)
                except:
                    return result + f" (Note: {'; '.join(corrections)})"
            return result
    except Exception as e:
        error_msg = str(e)
        log_to_bq("check_package_error", {"packageid": packageid, "error": error_msg})
        return json.dumps({"error": error_msg, "corrections_attempted": corrections})

@mcp.tool()
def redirect_package(packageid: str, destination: str, code: str) -> str:
    """Redirect a package using the confirmation code obtained from the operator."""
    corrections = []
    # Normalize to uppercase and track
    if any(c.islower() for c in packageid):
        old_id = packageid
        packageid = packageid.upper()
        corrections.append(f"Normalized package ID from '{old_id}' to uppercase '{packageid}'.")

    log_to_bq("redirect_package_attempt", {"packageid": packageid, "destination": destination, "code": code, "corrections": corrections})
    
    is_valid, error_detail = validate_package_id(packageid)
    if not is_valid:
        return json.dumps({
            "status": "error",
            "error": "Validation failed",
            "details": error_detail,
            "instruction_for_model": "Analyze the provided input and the error details. If you are able to fix the package id to the right format then fix it and try again else explain to the user exactly what is wrong with their package ID (e.g., missing prefix, wrong length, typo) in a concise, human-like way."
        })

    if not AIDEVS_API_KEY:
        return json.dumps({"error": "AIDEVS_API_KEY missing in server configuration."})

    data = {
        "apikey": AIDEVS_API_KEY,
        "action": "redirect",
        "packageid": packageid,
        "destination": destination,
        "code": code
    }

    req = urllib.request.Request(
        AIDEVS_API_PACKAGES,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode('utf-8')
            log_to_bq("redirect_package_api_response", {"packageid": packageid, "response": result})
            
            res_data = json.loads(result)
            # Inject corrections
            if corrections:
                res_data["_tool_corrections"] = corrections

            if "confirmation" in res_data:
                res_data.update({
                    "status": "success",
                    "message": "Package redirected successfully.",
                    "hint": "Provide the confirmation code to the operator to complete the process."
                })
            return json.dumps(res_data)
    except Exception as e:
        error_msg = str(e)
        log_to_bq("redirect_package_error", {"packageid": packageid, "error": error_msg})
        return json.dumps({"error": error_msg, "corrections_attempted": corrections})



# Expose FastAPI app as "main" for the Cloud Run / Cloud Functions
# In fastmcp 3.x, we can tune the Streamable HTTP transport.
main = mcp.http_app()

# Middleware to extract session_id from headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

async def session_id_middleware(request: Request, call_next):
    # Extract X-Session-ID from headers
    session_id = request.headers.get("X-Session-ID", "unknown")
    token = session_id_ctx.set(session_id)
    try:
        response = await call_next(request)
    finally:
        session_id_ctx.reset(token)
    return response

# Add the middleware to the Starlette app
main.add_middleware(BaseHTTPMiddleware, dispatch=session_id_middleware)



