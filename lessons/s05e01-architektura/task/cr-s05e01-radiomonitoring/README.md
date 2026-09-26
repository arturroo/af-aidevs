# Cloud Run Service: cr-s05e01-radiomonitoring

Cloud Run microservice implementing the **S05E01 Radiomonitoring & Multimodal Scatter-Gather Ingestion** task for AI_Devs.

## Architecture Highlights
- **Asynchronous Scatter-Gather Router:** Rapid packet capture and concurrent dispatch to specialized subagents.
- **3-Tier Medallion Workspace:** Session-isolated storage in `cr-mcp-workspace` (`/raw/`, `/decoded/`, `/findings/`) with strict `APPEND_ONLY` immutability.
- **Specialized Multi-Modal Subagents:**
  - `VisionSubagent`: 3-sentence visual description, OCR, and metrics via `gemini-3.5-flash-lite`.
  - `TextSubagent`: Transcript analysis and Markdown structure extraction.
  - `SQLiteSubagent`: Introspected schema and read-only `query_sqlite` tool.
  - `AudioSubagent`: Audio transcription and Morse rhythm detector for "FLAGA".
- **Deterministic Math Tool:** `ROUND_HALF_UP` in Python via `decimal.Decimal` for `cityArea`.
- **Zero-Pollution Observability:** BigQuery streaming to `s05e01.audit` and LangSmith tracing with masked Base64 binaries.

## Local Execution (CLI)
```powershell
$env:UV_INDEX_GAR_USERNAME="oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)
uv sync
uv run python main.py --mode cli
```

## Running Tests & Quality Gates
```powershell
uvx ruff check . --exclude .venv --fix
uvx ruff format . --exclude .venv
uvx mypy . --ignore-missing-imports --exclude .venv
uv run pytest -v
```
