import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Also attempt loading root workspace .env
    root_env = Path(__file__).parent.parent.parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env)
    else:
        load_dotenv()

# Course and Task Configuration
TASK_NAME = "drone"
MISSION_TARGET = "PWR6132PL"
BACKEND = (os.getenv("BACKEND") or "langchain").strip()
AIDEVS_API_KEY = (os.getenv("AIDEVS_API_KEY") or "").strip()

raw_verify = (
    os.getenv("AIDEVS_VERIFY")
    or os.getenv("AIDEVS_VERIFY_URL")
    or os.getenv("AIDEVS_API_VERIFY")
    or "https://hub.ag3nts.org/verify"
).strip()
AIDEVS_VERIFY_URL = (raw_verify.replace("/api/verify", "/verify") if raw_verify.endswith("/api/verify") else raw_verify).strip()

AIDEVS_BASE_URL = (os.getenv("AIDEVS_API_BASE_URL") or "https://hub.ag3nts.org").rstrip("/")
AIDEVS_DRONE_MAP_URL = (
    os.getenv("AIDEVS_DRONE_MAP_URL")
    or f"{AIDEVS_BASE_URL}/data/{AIDEVS_API_KEY}/drone.png"
).strip()
AIDEVS_DRONE_DOCS_URL = (
    os.getenv("AIDEVS_DRONE_DOCS_URL")
    or f"{AIDEVS_BASE_URL}/dane/drone.html"
).strip()

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = (os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs").strip()
GOOGLE_CLOUD_LOCATION = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip()
GCS_WORKSPACE_BUCKET = (os.getenv("GCS_WORKSPACE_BUCKET") or "af-aidevs-workspaces").strip()
MCP_WORKSPACE_URL = (os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app").strip()
MCP_WEB_GATEWAY_URL = (os.getenv("MCP_WEB_GATEWAY_URL") or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app").strip()

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s02e05"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"
BQ_AUDIT_TABLE = os.getenv("BQ_AUDIT_TABLE") or f"{GOOGLE_CLOUD_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

# LLM Configuration (Default is Gemini 3.8 Flash on Vertex AI)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"

# Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING") or "true"
