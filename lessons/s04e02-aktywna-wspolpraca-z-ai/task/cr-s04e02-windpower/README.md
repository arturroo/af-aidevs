# cr-s04e02-windpower

Cloud Run microservice implementing the autonomous wind turbine scheduling task (`windpower`) for lesson S04E02 in `af-aidevs`.

## Quick Start (CLI Mode)

```powershell
# Set private GAR token
$env:UV_INDEX_GAR_USERNAME="oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)

# Run with LangChain backend
uv run python main.py --backend langchain

# Run with Google ADK backend
uv run python main.py --backend adk
```

## Running Tests

```powershell
uv run pytest -v
```
