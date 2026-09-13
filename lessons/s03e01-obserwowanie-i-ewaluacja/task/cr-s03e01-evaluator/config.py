import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
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
TASK_NAME = "evaluation"
BACKEND = (os.getenv("BACKEND") or "langchain").strip()
AIDEVS_API_KEY = (os.getenv("AIDEVS_API_KEY") or "").strip()

raw_verify = (
    os.getenv("AIDEVS_VERIFY")
    or os.getenv("AIDEVS_VERIFY_URL")
    or os.getenv("AIDEVS_API_VERIFY")
    or "https://hub.ag3nts.org/verify"
).strip()
AIDEVS_VERIFY_URL = (
    raw_verify.replace("/api/verify", "/verify")
    if raw_verify.endswith("/api/verify")
    else raw_verify
).strip()

AIDEVS_BASE_URL = (os.getenv("AIDEVS_API_BASE_URL") or "https://hub.ag3nts.org").rstrip("/")
AIDEVS_SENSORS_DATA_URL = (
    os.getenv("AIDEVS_SENSORS_DATA_URL")
    or f"{AIDEVS_BASE_URL}/dane/sensors.zip"
).strip()

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = (os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs").strip()
GOOGLE_CLOUD_LOCATION = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip()
GCS_WORKSPACE_BUCKET = (os.getenv("GCS_WORKSPACE_BUCKET") or "af-aidevs-workspaces").strip()
MCP_WORKSPACE_URL = (
    os.getenv("MCP_WORKSPACE_URL")
    or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
).strip()
MCP_WEB_GATEWAY_URL = (
    os.getenv("MCP_WEB_GATEWAY_URL")
    or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app"
).strip()

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s03e01"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"
BQ_AUDIT_TABLE = os.getenv("BQ_AUDIT_TABLE") or f"{GOOGLE_CLOUD_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

# LLM Configuration (Default is Gemini 3.8 Flash on Vertex AI)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"

# Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING") or "true"

# Allowed Sensor Types in SCADA firmware
ALLOWED_SENSOR_TYPES = {"temperature", "pressure", "water", "voltage", "humidity"}

# Timestamp sanity bounds: between 2026-01-01 and 2026-07-01 UTC
# 2026-01-01T00:00:00Z = 1767225600
# 2026-07-01T00:00:00Z = 1782864000
MIN_VALID_TIMESTAMP = 1767225600
MAX_VALID_TIMESTAMP = 1782864000

# Deterministic Sensor Physical Thresholds & Metrics
SENSOR_BOUNDS = {
    "temperature": (553.0, 873.0),
    "pressure": (60.0, 160.0),
    "water": (5.0, 15.0),
    "voltage": (229.0, 231.0),
    "humidity": (40.0, 80.0),
}

FIELD_TO_METRIC = {
    "temperature_K": "temperature",
    "pressure_bar": "pressure",
    "water_level_meters": "water",
    "voltage_supply_v": "voltage",
    "humidity_percent": "humidity",
}

METRIC_TO_FIELD = {v: k for k, v in FIELD_TO_METRIC.items()}
