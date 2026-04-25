import json
import os
import urllib.request
import logging
from google.cloud import bigquery
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.getenv("BQ_AUDIT_TABLE") or "bq-s01e03-audit"

mcp = FastMCP("Hub-Packages-MCP")

AIDEVS_API_PACKAGES = os.environ["AIDEVS_API_PACKAGES"]
AIDEVS_API_KEY = os.environ["AIDEVS_API_KEY"]

def log_to_bq(action: str, details: dict):
    try:
        row = {"action": action, "details": json.dumps(details)}
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
    if re.match(r"^PKG\d{8}$", packageid):
        return True, ""
    
    # Detailed checks for better feedback
    if not packageid.startswith("PKG"):
        return False, f"The ID '{packageid}' is missing the required 'PKG' prefix."
    
    rest = packageid[3:]
    if not rest.isdigit():
        return False, f"The ID '{packageid}' contains non-digit characters ('{rest}') after the 'PKG' prefix."
    
    if len(rest) != 8:
        return False, f"The ID '{packageid}' has {len(rest)} digits, but exactly 8 digits are required after 'PKG'."
    
    return False, f"The ID '{packageid}' does not match the required PKGXXXXXXXX format."

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
            "error": "Invalid package ID format.",
            "details": error_detail,
            "hint": "Please ask the operator for the correct ID. It must be in the format 'PKG' followed by 8 digits (e.g., PKG12345678).",
            "corrections_attempted": corrections
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
            "error": "Invalid package ID format.",
            "details": error_detail,
            "hint": "The redirection cannot be processed with an invalid ID. Please verify the ID format with the operator.",
            "corrections_attempted": corrections
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
# We increase max_sessions to allow more concurrent tests/clients.
main = mcp.http_app()



