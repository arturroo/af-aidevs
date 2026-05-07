# Workspace Manager (MCP Server)

This is a Model Context Protocol (MCP) server that provides file system access to isolated agent workspaces. It is designed to run on Google Cloud Run with a mounted GCS bucket (via Cloud Storage FUSE) but can also be run locally for development.

## Local Development

### 1. Prerequisites
- Python 3.12.11
- `uv` (Fast Python package manager)

### 2. Setup Local Workspace
Create a local directory structure that mimics the production mount:
```powershell
mkdir -Force "./local_workspaces/agent-s01e05"
"Hello world" | Out-File -Encoding utf8 "./local_workspaces/agent-s01e05/test.txt"
```

### 3. Run the Server
Set the environment variables and start the server:
```powershell
$env:WORKSPACE_MOUNT_ROOT = "$(Get-Location)/local_workspaces"
$env:PORT = "8080"
$env:LOG_LEVEL = "DEBUG"
uv run python main.py
```

## Testing

### Option 1: MCP Inspector (Visual)
The Inspector is the easiest way to test tools. It requires **CORS** to be enabled on the server (which is configured in `main.py`).

1. Open a new terminal.
2. Run the inspector:
   ```powershell
   npx @modelcontextprotocol/inspector http://localhost:8080/mcp
   ```
3. In the browser UI:
   - Ensure **Transport Type** is set to `Streamable HTTP`.
   - Ensure **URL** is `http://localhost:8080/mcp`.
   - (Optional) Under **Authentication**, add Header `X-Session-ID` with any value to see it in audit logs.
   - Click **Connect**.

### Option 2: PowerShell (Invoke-RestMethod)
Bash-like testing directly from PowerShell. Note that we must provide the `Mcp-Session-Id` header (returned by the server on first contact or visible in logs).

```powershell
$postParams = @{
    jsonrpc = "2.0"
    method = "tools/call"
    params = @{
        name = "list_files"
        arguments = @{ path = "." }
    }
    id = 1
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8080/mcp" `
  -Headers @{
      "Content-Type" = "application/json"
      "Accept" = "application/json, text/event-stream"
      "Mcp-Session-Id" = "PASTE_SESSION_ID_FROM_LOGS"
      "X-Session-ID" = "local-test-session"
  } `
  -Body $postParams
```

### Option 3: Bash (curl)
For testing from a Unix-like shell or `curl.exe` on Windows. CORS is **not** required for curl tests.

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: PASTE_SESSION_ID_FROM_LOGS" \
  -H "X-Session-ID: local-test-session" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "list_files", "arguments": {"path": "."}}, "id": 1}' \
  "http://localhost:8080/mcp"
```

## Deployment
Deployed to Google Cloud Run via Terraform.
- **URL**: Referenced in `.env` or Terraform variables.
- **Auth**: Private service (`public = false`), requires OIDC token.
- **Storage**: Mounted GCS bucket at `/mnt/workspaces`.
