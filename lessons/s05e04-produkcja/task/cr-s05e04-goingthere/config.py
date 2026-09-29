"""Configuration module for cr-s05e04-goingthere."""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load local environment variables dynamically with override=True and utf-8-sig (strips Windows PowerShell BOM)
local_env = Path(__file__).resolve().parent / ".env"
if local_env.exists():
    load_dotenv(dotenv_path=local_env, override=True, encoding="utf-8-sig")
else:
    load_dotenv(find_dotenv(usecwd=True), override=True, encoding="utf-8-sig")


class Config:
    """Runtime configuration loaded from environment variables."""

    # Service Identity
    SERVICE_NAME: str = "cr-s05e04-goingthere"
    TASK_NAME: str = (os.getenv("TASK_NAME") or "goingthere").strip()

    # Centrala credentials & course endpoints
    AIDEVS_API_KEY: str = (
        os.getenv("AIDEVS_API_KEY") or os.getenv("\ufeffAIDEVS_API_KEY") or ""
    ).strip()
    AIDEVS_API_VERIFY: str = (
        os.getenv("AIDEVS_VERIFY")
        or os.getenv("AIDEVS_API_VERIFY")
        or os.getenv("AIDEVS_VERIFY_URL")
        or ""
    ).strip()
    AIDEVS_API_GETMESSAGE: str = (
        os.getenv("AIDEVS_API_GETMESSAGE") or os.getenv("AIDEVS_GETMESSAGE_URL") or ""
    ).strip()
    AIDEVS_API_FREQUENCY_SCANNER: str = (
        os.getenv("AIDEVS_API_FREQUENCY_SCANNER")
        or os.getenv("AIDEVS_FREQUENCY_SCANNER_URL")
        or ""
    ).strip()
    AIDEVS_GOINGTHERE_PREVIEW_URL: str = (
        os.getenv("AIDEVS_GOINGTHERE_PREVIEW_URL")
        or "https://hub.ag3nts.org/goingthere_preview"
    ).strip()

    @property
    def getmessage_url(self) -> str:
        """Returns explicitly configured GETMESSAGE URL or derives from VERIFY URL."""
        if self.AIDEVS_API_GETMESSAGE:
            return self.AIDEVS_API_GETMESSAGE
        if self.AIDEVS_API_VERIFY:
            base = self.AIDEVS_API_VERIFY.rsplit("/verify", 1)[0].rstrip("/")
            return f"{base}/api/getmessage"
        return ""

    @property
    def frequency_scanner_url(self) -> str:
        """Returns explicitly configured FREQUENCY_SCANNER URL or derives from VERIFY URL."""
        if self.AIDEVS_API_FREQUENCY_SCANNER:
            return self.AIDEVS_API_FREQUENCY_SCANNER
        if self.AIDEVS_API_VERIFY:
            base = self.AIDEVS_API_VERIFY.rsplit("/verify", 1)[0].rstrip("/")
            return f"{base}/api/frequencyScanner"
        return ""

    # Google Cloud & Vertex AI settings
    GOOGLE_CLOUD_PROJECT: str = (
        os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
    ).strip()
    GOOGLE_CLOUD_LOCATION: str = (
        os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
    ).strip()
    GEMINI_MODEL: str = (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip()
    THINKING_LEVEL: str = (os.getenv("THINKING_LEVEL") or "high").strip()

    # BigQuery Audit Settings
    BQ_DATASET: str = (os.getenv("BQ_DATASET") or "s05e04").strip()
    BQ_TABLE: str = (os.getenv("BQ_TABLE") or "audit").strip()

    # Remote Microservices & Storage
    MCP_WORKSPACE_URL: str = (
        os.getenv("MCP_WORKSPACE_URL")
        or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
    ).strip()
    MCP_WEB_GATEWAY_URL: str = (os.getenv("MCP_WEB_GATEWAY_URL") or "").strip()
    MODEL_ARMOR_URL: str = (os.getenv("MODEL_ARMOR_URL") or "").strip()
    GCS_WORKSPACE_BUCKET: str = (
        os.getenv("GCS_WORKSPACE_BUCKET") or "af-aidevs-workspaces"
    ).strip()

    # Observability
    LANGSMITH_API_KEY: str = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    LANGSMITH_PROJECT: str = (os.getenv("LANGSMITH_PROJECT") or "af-aidevs").strip()
    LANGSMITH_ENDPOINT: str = (
        os.getenv("LANGSMITH_ENDPOINT")
        or os.getenv("LANGCHAIN_ENDPOINT")
        or "https://eu.api.smith.langchain.com"
    ).strip()
    LANGSMITH_TRACING: bool = (
        os.getenv("LANGSMITH_TRACING") or "true"
    ).lower() == "true"


config = Config()

# Explicitly map to standard LangChain environment variables to activate LangSmith tracing
if config.LANGSMITH_API_KEY and config.LANGSMITH_TRACING:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGSMITH_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = config.LANGSMITH_PROJECT
    os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = config.LANGSMITH_ENDPOINT
    os.environ["LANGSMITH_ENDPOINT"] = config.LANGSMITH_ENDPOINT
