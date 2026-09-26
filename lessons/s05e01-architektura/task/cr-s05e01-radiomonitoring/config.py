import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load local environment variables if available
load_dotenv(find_dotenv(usecwd=True))

# Service Identity
SERVICE_NAME = "cr-s05e01-radiomonitoring"

# Centrala API Configuration
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY", "")
AIDEVS_API_VERIFY = (
    os.getenv("AIDEVS_VERIFY")
    or os.getenv("AIDEVS_API_VERIFY")
    or ""
)

# Google Cloud & Vertex AI Configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "af-aidevs")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
ENRICHMENT_MODEL = os.getenv("ENRICHMENT_MODEL", "gemini-3.5-flash-lite")
THINKING_LEVEL = os.getenv("THINKING_LEVEL", "low")
ENRICHMENT_THINKING_LEVEL = os.getenv("ENRICHMENT_THINKING_LEVEL", "medium")

# BigQuery Telemetry
BQ_DATASET = os.getenv("BQ_DATASET", "s05e01")
BQ_TABLE = os.getenv("BQ_TABLE", "audit")

# Remote Microservices & Storage
MCP_WORKSPACE_URL = os.getenv("MCP_WORKSPACE_URL", "")
MCP_WEB_GATEWAY_URL = os.getenv("MCP_WEB_GATEWAY_URL", "")
MODEL_ARMOR_URL = os.getenv("MODEL_ARMOR_URL", "")
GCS_WORKSPACE_BUCKET = os.getenv("GCS_WORKSPACE_BUCKET", "af-aidevs-workspaces")

# Local Workspace & Cache Path (tmpfs in Cloud Run)
LOCAL_CACHE_DIR = Path(os.getenv("LOCAL_CACHE_DIR", "/tmp/mcp_cache"))
LOCAL_WORKSPACE_DIR = Path(os.getenv("LOCAL_WORKSPACE_DIR", "workspace"))

# LangSmith Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "af-aidevs")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
LANGSMITH_ENDPOINT = os.getenv(
    "LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com"
)
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
