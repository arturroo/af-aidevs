# S02E04: Zero-Trust Mailbox Investigation Service (`cr-s02e04-mailbox`)

Autonomous cyber intelligence agent microservice deployed on Google Cloud Run to investigate a compromised System operator's mailbox via the Zmail API, screen incoming content through Model Armor, extract critical security telemetry, and verify the outcome with Centrala.

## Architecture & Guarantees

1. **Primary LLM**: **Gemini 3.8 Flash** (`gemini-3.8-flash`) hosted on Google Cloud Vertex AI (`location: global`, `thinking_level: low`).
2. **Dual-Framework Parity**: Full support for both **LangChain 1.2.15** (`create_agent`) and **Google ADK** (`google-adk==1.33.0`) switchable via `--backend`.
3. **Zero Direct Egress**: 100% of external HTTP traffic (Zmail API and Centrala Verification) is routed through `cr-mcp-web-gateway` (`post_web_resource`) using Google Cloud OIDC tokens.
4. **Adversarial Ingestion Defense**: All ingested email message bodies pass through `af_aidevs.model_armor.verify` (`cr-model-armor`) before being presented to the model context. Flagged adversarial inputs are quarantined.
5. **No Tool Stacking Anti-Pattern**: High-level domain tools invoke ordinary methods on `MCPService`. Service methods are decorated with LangSmith's `@traceable(run_type="tool", name="mcp.post_web_resource")` for granular distributed tracing.
6. **Streaming BigQuery Telemetry**: All events, thoughts, and tool executions are streamed in real time to dataset `s02e04`, table `audit`.

## Intelligence Targets

The agent extracts:
- `date`: Scheduled date of power plant attack (`YYYY-MM-DD`).
- `password`: System operator employee password.
- `confirmation_code`: Security ticket confirmation code matching `^SEC-[A-Za-z0-9]{28}$` (32 characters).

## Local Development & Testing

### 1. Synchronize Dependencies
```powershell
$env:UV_INDEX_GAR_USERNAME = "oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD = $(gcloud auth print-access-token)
uv sync
```

### 2. Run Unit Tests
```powershell
uv run pytest -v
```

### 3. Run Agent via CLI
Using default LangChain backend:
```powershell
uv run python main.py --backend langchain --max-iterations 10
```

Using Google ADK backend:
```powershell
uv run python main.py --backend adk --max-iterations 10
```

### 4. Run HTTP Service
```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```
- `GET /health`: Health status.
- `POST /run`: Execute investigation loop via JSON payload (`{"backend": "langchain", "max_iterations": 10}`).
