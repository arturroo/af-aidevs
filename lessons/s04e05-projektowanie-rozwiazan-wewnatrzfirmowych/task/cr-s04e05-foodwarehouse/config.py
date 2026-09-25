import os
from pathlib import Path

from dotenv import load_dotenv

# Load local or repository .env by traversing parent directories
cur_p = Path(__file__).resolve()
for parent in [cur_p.parent] + list(cur_p.parents):
    candidate = parent / ".env"
    if candidate.exists():
        load_dotenv(dotenv_path=candidate)
        break

# Course and Task Configuration
TASK_NAME = "foodwarehouse"
BACKEND = (os.getenv("BACKEND") or "langchain").strip()
AIDEVS_API_KEY = (os.getenv("AIDEVS_API_KEY") or "").strip()

AIDEVS_BASE_URL = (
    os.getenv("AIDEVS_API_BASE_URL")
    or os.getenv("AIDEVS_BASE_URL")
    or "https://hub.ag3nts.org"
).rstrip("/")

# Verify API endpoint resolution with fallbacks
raw_verify = (
    os.getenv("AIDEVS_VERIFY")
    or os.getenv("AIDEVS_VERIFY_URL")
    or os.getenv("AIDEVS_API_VERIFY")
    or f"{AIDEVS_BASE_URL}/verify"
).strip()
AIDEVS_VERIFY_URL = (
    raw_verify.replace("/api/verify", "/verify")
    if raw_verify.endswith("/api/verify")
    else raw_verify
).strip()

AIDEVS_FOOD4CITIES_URL = (
    os.getenv("AIDEVS_FOOD4CITIES_URL")
    or os.getenv("AIDEVS_FOODWAREHOUSE_DATA_URL")
    or f"{AIDEVS_BASE_URL}/dane/food4cities.json"
).strip()

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = (os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs").strip()
GOOGLE_CLOUD_LOCATION = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip()
GCS_WORKSPACE_BUCKET = (
    os.getenv("GCS_WORKSPACE_BUCKET") or "af-aidevs-workspaces"
).strip()
MCP_WORKSPACE_URL = (
    os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
).strip()
MCP_WEB_GATEWAY_URL = (
    os.getenv("MCP_WEB_GATEWAY_URL")
    or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app"
).strip()

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s04e05"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"
BQ_AUDIT_TABLE = (
    os.getenv("BQ_AUDIT_TABLE") or f"{GOOGLE_CLOUD_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
)

# LLM Configuration (Default: Gemini 3.5 Flash-Lite on Vertex AI with thinking_level="low")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
GEMINI_FLASH_LITE_MODEL = (
    os.getenv("GEMINI_FLASH_LITE_MODEL") or "gemini-3.5-flash-lite"
)
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "medium"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"

# Model Armor Security
MODEL_ARMOR_URL = (os.getenv("MODEL_ARMOR_URL") or "").strip()

# Local / MCP staging directory configuration
LOCAL_WORKSPACE_DIR = cur_p.parent / "workspace"
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS") or "100")
