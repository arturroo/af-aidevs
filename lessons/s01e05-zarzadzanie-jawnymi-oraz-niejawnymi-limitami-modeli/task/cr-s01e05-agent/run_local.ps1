# Automation script to run the agent locally with fresh tokens
$ErrorActionPreference = "Stop"

Write-Host "Fetching fresh Google Cloud tokens..." -ForegroundColor Cyan

# 1. Set credentials for UV to access Artifact Registry
$env:UV_INDEX_GAR_USERNAME = "oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD = $(gcloud auth print-access-token)

# 2. Load .env file manually to get URLs before uv run
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^(?<key>[^#\s=]+)=(?<value>.*)$") {
            $key = $Matches.key
            $val = $Matches.value.Trim('"').Trim("'")
            Set-Item "env:$key" $val
        }
    }
}

# Generate separate tokens because Cloud Run strictly validates the "audience" (URL) of the token!
$env:MODEL_ARMOR_TOKEN = $(gcloud auth print-identity-token --impersonate-service-account=$env:AGENT_SA_EMAIL --audiences=$env:MODEL_ARMOR_URL)
$env:MCP_WORKSPACE_TOKEN = $(gcloud auth print-identity-token --impersonate-service-account=$env:AGENT_SA_EMAIL --audiences=$env:MCP_WORKSPACE_URL)

Write-Host "Tokens refreshed successfully! Starting agent..." -ForegroundColor Green

# 3. Run the application
uv run python main.py
