# Workspace Manager (MCP Server)

This is a Model Context Protocol (MCP) server that provides file system access to isolated agent workspaces. It is designed to run on Google Cloud Run with a mounted GCS bucket (via Cloud Storage FUSE) but can also be run locally for development.

## Local Development

### 1. Prerequisites
- Python 3.12.11
- `uv` (Fast Python package manager)

### 2. Setup Local Workspace
Create a local directory structure that mimics the production mount:
```powershell
mkdir -Force "./data/workspaces/local"
"Hello world" | Out-File -Encoding utf8 "./data/workspaces/local/test.txt"
```

### 3. Run the Server
Set the environment variables and start the server:
```powershell
$env:WORKSPACE_MOUNT_ROOT = "$(Get-Location)/data/workspaces"
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

### Option 4: Remote Testing (Cloud Run)
This service follows the standard private MCP testing pattern defined in the repository root.

**Connection Initialization:**
See `GEMINI.md` section **"MCP Server Testing Pattern (Remote on Cloud Run)"** for instructions on how to get the OIDC token and initialize the session (`$env:MCP_SESSION_ID`).

**Testing Tools:**
Once the session is initialized, you can test the tools using the following commands:

1. **Write File**:
   ```powershell
   $currentDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
   $writeParams = @{
       jsonrpc = "2.0"
       method = "tools/call"
       params = @{
           name = "write_file"
           arguments = @{
               file_path = "$env:MCP_SESSION_ID/test.md"
               content = "Artur MCP server test in GCP: $currentDate"
           }
       }
       id = 2
   } | ConvertTo-Json

   Invoke-RestMethod -Method Post `
     -Uri "$env:CLOUD_RUN_URL/mcp" `
     -Headers @{
         "Content-Type" = "application/json"
         "Accept" = "application/json, text/event-stream"
         "Authorization" = "Bearer $token"
         "Mcp-Session-Id" = $env:MCP_SESSION_ID
     } `
     -Body $writeParams
   ```

2. **List Files**:
   ```powershell
   $listParams = @{
       jsonrpc = "2.0"
       method = "tools/call"
       params = @{
           name = "list_files"
           arguments = @{ path = $env:MCP_SESSION_ID }
       }
       id = 3
   } | ConvertTo-Json

   Invoke-RestMethod -Method Post `
     -Uri "$env:CLOUD_RUN_URL/mcp" `
     -Headers @{
         "Content-Type" = "application/json"
         "Accept" = "application/json, text/event-stream"
         "Authorization" = "Bearer $token"
         "Mcp-Session-Id" = $env:MCP_SESSION_ID
     } `
     -Body $listParams
   ```

3. **Read File**:
   ```powershell
   $readParams = @{
       jsonrpc = "2.0"
       method = "tools/call"
       params = @{
           name = "read_file"
           arguments = @{ file_path = "$env:MCP_SESSION_ID/test.md" }
       }
       id = 4
   } | ConvertTo-Json

   Invoke-RestMethod -Method Post `
     -Uri "$env:CLOUD_RUN_URL/mcp" `
     -Headers @{
         "Content-Type" = "application/json"
         "Accept" = "application/json, text/event-stream"
         "Authorization" = "Bearer $token"
         "Mcp-Session-Id" = $env:MCP_SESSION_ID
     } `
     -Body $readParams
   ```

## Deployment
Deployed to Google Cloud Run via Terraform.
- **URL**: Referenced in `.env` or Terraform variables.
- **Auth**: Private service (`public = false`), requires OIDC token.
- **Storage**: Mounted GCS bucket at `/mnt/workspaces`.
