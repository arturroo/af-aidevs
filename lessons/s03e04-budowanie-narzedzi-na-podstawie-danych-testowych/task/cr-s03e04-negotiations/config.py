import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present, otherwise fallback to root repository .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    root_env = Path(__file__).parent.parent.parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env)
    else:
        load_dotenv()

# Course and Task Configuration
TASK_NAME = "negotiations"
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

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = (os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs").strip()
GOOGLE_CLOUD_LOCATION = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip()
GCS_WORKSPACE_BUCKET = (
    os.getenv("GCS_WORKSPACE_BUCKET") or "af-aidevs-workspaces"
).strip()
MCP_WORKSPACE_URL = (
    os.getenv("MCP_WORKSPACE_URL")
    or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
).strip()
MCP_WEB_GATEWAY_URL = (
    os.getenv("MCP_WEB_GATEWAY_URL")
    or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app"
).strip()

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s03e04"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"
BQ_AUDIT_TABLE = (
    os.getenv("BQ_AUDIT_TABLE") or f"{GOOGLE_CLOUD_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
)

# LLM Configuration (Default is Gemini 3.8 Flash on Vertex AI with thinking_level="low")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL") or "gemini-3.5-flash-lite"
EXTRACTION_LOCATION = os.getenv("EXTRACTION_LOCATION") or "global"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "text-multilingual-embedding-002"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"

# Model Armor Security
MODEL_ARMOR_URL = (os.getenv("MODEL_ARMOR_URL") or "").strip()

# Database and Storage Configuration
INVENTORY_DB_GCS_PATH = (
    os.getenv("INVENTORY_DB_GCS_PATH") or "shared/s03e04/inventory.db"
).strip()
INVENTORY_DB_PATH = Path(os.getenv("INVENTORY_DB_PATH") or "/tmp/inventory.db")
_candidate_dirs = [
    Path(__file__).resolve().parent.parent.parent / "data",
    Path(__file__).resolve().parent.parent / "data",
    Path(__file__).resolve().parent / "data",
]
DATA_DIR = next((d for d in _candidate_dirs if (d / "items.csv").exists()), _candidate_dirs[0])

# Central Public URL of our Cloud Run service (for registration with Centrala)
CENTRAL_PUBLIC_URL = (os.getenv("CENTRAL_PUBLIC_URL") or "").strip()
