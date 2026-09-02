import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Course and Task Configuration
BACKEND = os.getenv("BACKEND") or "langchain"
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY") or ""
AIDEVS_VERIFY_URL = os.getenv("AIDEVS_VERIFY") or os.getenv("AIDEVS_VERIFY_URL") or "https://hub.ag3nts.org/verify"
AIDEVS_ELECTRICITY_DATA_URL = os.getenv("AIDEVS_ELECTRICITY_DATA_URL") or f"https://hub.ag3nts.org/data/{AIDEVS_API_KEY}/electricity.png"
AIDEVS_ELECTRICITY_SOLVED_URL = os.getenv("AIDEVS_ELECTRICITY_SOLVED_URL") or "https://hub.ag3nts.org/i/solved_electricity.png"

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
MCP_WORKSPACE_URL = os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
MCP_WEB_GATEWAY_URL = os.getenv("MCP_WEB_GATEWAY_URL") or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app"
VISION_AGENT_URL = os.getenv("VISION_AGENT_URL") or "https://cr-agent-vision-qsvqxjqyrq-oa.a.run.app"

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s02e02"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"

# Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY") or ""
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY") or ""
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"
