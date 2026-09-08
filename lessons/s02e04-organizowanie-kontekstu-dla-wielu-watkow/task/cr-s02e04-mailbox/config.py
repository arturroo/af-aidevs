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
TASK_NAME = "mailbox"
BACKEND = (os.getenv("BACKEND") or "langchain").strip()
AIDEVS_API_KEY = (os.getenv("AIDEVS_API_KEY") or "").strip()

raw_verify = (
    os.getenv("AIDEVS_VERIFY")
    or os.getenv("AIDEVS_VERIFY_URL")
    or os.getenv("AIDEVS_API_VERIFY")
    or "https://hub.ag3nts.org/verify"
).strip()
AIDEVS_VERIFY_URL = (raw_verify.replace("/api/verify", "/verify") if raw_verify.endswith("/api/verify") else raw_verify).strip()

AIDEVS_API_ZMAIL = (
    os.getenv("AIDEVS_API_ZMAIL")
    or os.getenv("AIDEVS_ZMAIL_URL")
    or (AIDEVS_VERIFY_URL.replace("/verify", "/api/zmail") if "/verify" in AIDEVS_VERIFY_URL else f"{AIDEVS_VERIFY_URL.rstrip('/')}/api/zmail")
).strip()

# GCP & MCP Infrastructure
GOOGLE_CLOUD_PROJECT = (os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs").strip()
GOOGLE_CLOUD_LOCATION = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip()
MCP_WORKSPACE_URL = (os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app").strip()
MCP_WEB_GATEWAY_URL = (os.getenv("MCP_WEB_GATEWAY_URL") or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app").strip()
MODEL_ARMOR_URL = (os.getenv("MODEL_ARMOR_URL") or "https://cr-model-armor-qsvqxjqyrq-oa.a.run.app").strip()

# BigQuery Auditing
BQ_DATASET = os.getenv("BQ_DATASET") or "s02e04"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"

# LLM Configuration (Starting 2026-09-07 default is Gemini 3.8 Flash on Vertex AI)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"

# Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY") or ""
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY") or ""
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"
