# cr-s02e05-drone: Zero-Trust Preemptive Strike Drone Agent

This microservice implements the autonomous agent for lesson `s02e05` (Task: `drone`).

## Architecture & Responsibilities
- **Dual Framework**: Supports both **LangChain 1.2.15** (`create_agent`) and **Google ADK 1.33.0** (`Agent`) selectable via `--backend` (defaulting to `langchain`).
- **In-Process Multi-Agent Topology**: Supervisor coordinates the mission, while an in-process Vision Worker ingests `drone.png` via Vertex AI Gemini 3.8 Flash (`Part.from_uri`), extracts `DamCoordinates`, and returns only compact JSON to prevent context bloat.
- **Zero-Trust Network Isolation**: Direct outbound HTTP egress is completely disabled; all external requests to download map/docs and verify instructions route through `cr-mcp-web-gateway`.
- **OverlayFS Workspace Persistence**: Session files (`drone.png`, `drone.html`, `drone.md`, `run_notes.txt`) are managed via `cr-mcp-workspace`.
- **Autonomous Error Recovery**: Receptive feedback loop with up to 10 verification retries, dynamically adjusting parameters and prepending `hardReset` when cascading state errors occur.
- **Full-Fidelity Auditing**: Detailed operational traces, tool calls, and captured flags are streamed to BigQuery dataset `s02e05` (`audit` table).

## Local Usage

### Install Dependencies
```powershell
$env:UV_INDEX_GAR_USERNAME="oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)
uv sync
```

### Run CLI
```powershell
# LangChain backend
uv run python main.py --backend langchain

# Google ADK backend
uv run python main.py --backend adk
```

### Run FastAPI Service
```powershell
uv run uvicorn main:app --port 8080
```
