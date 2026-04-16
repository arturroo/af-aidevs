import json
import os
import urllib.request
import logging
from google.cloud import bigquery
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.environ.get("BQ_AUDIT_TABLE", "bq-s01e03-audit")

mcp = FastMCP("Hub-Packages-MCP")

AIDEVS_API_PACKAGES_URL = os.environ["AIDEVS_API_PACKAGES_URL"]
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

@mcp.tool()
def check_package(packageid: str) -> str:
    """Check the contents and current destination of a package."""
    log_to_bq("check_package", {"packageid": packageid})
    if not AIDEVS_API_KEY:
        return json.dumps({"error": "AIDEVS_API_KEY missing"})

    data = {
        "apikey": AIDEVS_API_KEY,
        "action": "check",
        "packageid": packageid
    }
    
    req = urllib.request.Request(
        AIDEVS_API_PACKAGES_URL,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode('utf-8')
            return result
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def redirect_package(packageid: str, destination: str, code: str) -> str:
    """Redirect a package using the confirmation code obtained from the operator."""
    log_to_bq("redirect_package", {"packageid": packageid, "destination": destination, "code": code})
    if not AIDEVS_API_KEY:
        return json.dumps({"error": "AIDEVS_API_KEY missing"})

    data = {
        "apikey": AIDEVS_API_KEY,
        "action": "redirect",
        "packageid": packageid,
        "destination": destination,
        "code": code
    }
    
    req = urllib.request.Request(
        AIDEVS_API_PACKAGES_URL,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode('utf-8')
            return result
    except Exception as e:
        return json.dumps({"error": str(e)})

# Expose Starlette app as "main" for the Cloud Functions (Gen2 / Cloud Run)
try:
    main = mcp.get_starlette_app()
except AttributeError:
    # Fallback for different fastmcp version
    from fastapi import FastAPI
    main = FastAPI()
