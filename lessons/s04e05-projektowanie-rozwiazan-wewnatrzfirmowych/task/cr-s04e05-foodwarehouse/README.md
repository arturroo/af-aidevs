# cr-s04e05-foodwarehouse

Cloud Run microservice implementing the **S04E05** `foodwarehouse` mission.
Autonomously orchestrates municipal food & tool deliveries to 8 settlements across Centrala's logistics API (`$AIDEVS_API_VERIFY`), using progressive disclosure, database introspection, signature generation, pre-flight validation gates, and batch dispatch.

## Features
- **Progressive Disclosure**: Universal meta-tool `call_centrala_api` allows autonomous discovery of `help`, SQLite tables (`database`), and `signatureGenerator`.
- **Pre-Flight Validation Gate**: Quality Gate tool `validate_staged_orders` asserts 1:1 match against `food4cities.json` prior to execution.
- **Atomic Batch Dispatch**: `dispatch_staged_orders` executes reset, creates 8 orders, appends item batches, and captures verification flag.
- **Zero Direct Egress**: External traffic routes strictly through `cr-mcp-web-gateway` with Tenacity retry.
- **Dual Framework**: Supports both LangChain `1.2.15` and Google ADK `1.33.0`.
- **Dynamic Runtime Overrides**: Full support for overriding model (`--model`), thinking level (`--thinking-level`), and recursion limit (`--max-iterations`) on the fly without rebuilds.

## Execution Modes

### 1. Cloud Run Remote Execution (HTTP POST /run)

The deployed private Cloud Run microservice endpoint accepts `POST /run` authenticated with a Google Cloud identity token.

#### PowerShell Execution:
```powershell
$token = $(gcloud auth print-identity-token)
curl.exe -s -X POST "https://cr-s04e05-foodwarehouse-qsvqxjqyrq-oa.a.run.app/run" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{\"backend\": \"langchain\", \"model\": \"gemini-3.5-flash-lite\", \"max_iterations\": 80, \"thinking_level\": \"medium\"}'
```

#### Request Payload Specification (`RunTaskRequest`):
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `backend` | `Literal["langchain", "adk"]` | No | `"langchain"` | Agent execution framework |
| `session_id` | `str | None` | No | `None` (auto-generated) | Session identifier for telemetry correlation |
| `model` | `str | None` | No | `"gemini-3.5-flash-lite"` | Model override on Vertex AI |
| `max_iterations` | `int | None` | No | `80` | Maximum recursion limit (LangGraph node transitions) |
| `thinking_level` | `Literal["low", "medium", "high"] | None` | No | `"medium"` | Model thinking/reasoning depth |

#### Response Format (`RunTaskResponse`):
```json
{
  "status": "success",
  "flag": "{FLG:...}",
  "session_id": "s04e05_langchain_20260925_172729",
  "backend": "langchain",
  "orders_count": 8,
  "stats": {
    "discovery_queries": 26,
    "signatures_generated": 0,
    "orders_created": 8,
    "items_appended": 29,
    "duration_seconds": 150.57
  },
  "message": "Mission complete. Flag: {FLG:...}"
}
```

### 2. Local CLI Execution

```powershell
uv run python main.py --backend langchain --model gemini-3.5-flash-lite --thinking-level medium --max-iterations 80
uv run python main.py --backend adk --model gemini-3.5-flash-lite --thinking-level medium --max-iterations 80
```

## Observability & Verification

- **Health Check (`GET /health`):**
  ```powershell
  $token = $(gcloud auth print-identity-token)
  curl.exe -s -H "Authorization: Bearer $token" "https://cr-s04e05-foodwarehouse-qsvqxjqyrq-oa.a.run.app/health"
  ```

- **Query BigQuery Audit Logs (PowerShell):**
  ```powershell
  bq query --use_legacy_sql=false --project_id=af-aidevs 'SELECT timestamp, session_id, actor, SUBSTR(content, 1, 100) AS preview FROM `af-aidevs.s04e05.audit` ORDER BY timestamp DESC LIMIT 20'
  ```

- **Inspect Remote Session Workspace (GCS):**
  ```powershell
  gcloud storage ls "gs://af-aidevs-workspaces/sa-cr-s04e05-foodwarehouse/**"
  ```
