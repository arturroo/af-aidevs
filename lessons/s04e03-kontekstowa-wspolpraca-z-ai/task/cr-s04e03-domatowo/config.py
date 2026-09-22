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
TASK_NAME = "domatowo"
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

AIDEVS_DOMATOWO_PREVIEW_URL = (
    os.getenv("AIDEVS_DOMATOWO_PREVIEW_URL") or f"{AIDEVS_BASE_URL}/domatowo_preview"
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
BQ_DATASET = os.getenv("BQ_DATASET") or "s04e03"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"
BQ_AUDIT_TABLE = (
    os.getenv("BQ_AUDIT_TABLE") or f"{GOOGLE_CLOUD_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
)

# LLM Configuration (Gemini 3.8 Flash on Vertex AI with thinking_level="low")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"

# Model Armor Security
MODEL_ARMOR_URL = (os.getenv("MODEL_ARMOR_URL") or "").strip()

# Agent execution constants & AP Budget
MAX_AGENT_ITERATIONS = 120
MAX_AP_BUDGET = 300
EMERGENCY_AP_BUFFER = 25
