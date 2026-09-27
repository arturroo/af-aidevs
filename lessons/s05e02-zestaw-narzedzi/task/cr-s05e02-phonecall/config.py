import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load local environment variables if available
load_dotenv(find_dotenv(usecwd=True))

# Service Identity
SERVICE_NAME = "cr-s05e02-phonecall"

# Centrala API Configuration
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY") or ""
AIDEVS_API_VERIFY = os.getenv("AIDEVS_VERIFY") or os.getenv("AIDEVS_API_VERIFY") or ""

# Google Cloud & Vertex AI Configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
THINKING_LEVEL = os.getenv("THINKING_LEVEL") or "low"

# Text-to-Speech Configuration
DEFAULT_VOICE_NAME = os.getenv("DEFAULT_VOICE_NAME") or "pl-PL-Chirp3-HD-Fenrir"
DEFAULT_SPEAKING_RATE = float(os.getenv("DEFAULT_SPEAKING_RATE") or "1.0")
DEFAULT_MAX_ITERATIONS = int(os.getenv("DEFAULT_MAX_ITERATIONS") or "15")
DEFAULT_MAX_RESTARTS = int(os.getenv("DEFAULT_MAX_RESTARTS") or "2")

# BigQuery Telemetry
BQ_DATASET = os.getenv("BQ_DATASET") or "s05e02"
BQ_TABLE = os.getenv("BQ_TABLE") or "audit"

# Local Cache & Workspace
LOCAL_CACHE_DIR = Path(os.getenv("LOCAL_CACHE_DIR") or "/tmp/phonecall_cache")

# LangSmith Observability
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or "af-aidevs"
LANGSMITH_TRACING = (os.getenv("LANGSMITH_TRACING") or "true").lower() == "true"
LANGSMITH_ENDPOINT = (
    os.getenv("LANGSMITH_ENDPOINT") or "https://eu.api.smith.langchain.com"
)
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY") or ""
