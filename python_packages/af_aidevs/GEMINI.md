# Shared Package: `af_aidevs`

This directory contains the central `af_aidevs` shared Python package deployed to Google Cloud Artifact Registry and used across all course lesson tasks and microservices.

## Architectural Principles
1. **Zero Cold-Start Drift ("Podejście A"):** The root `__init__.py` contains minimal imports to avoid eager-loading heavy dependencies (e.g., `google-cloud-bigquery`, `langchain`) upon package import. Consumers import submodules directly (e.g., `from af_aidevs import model_armor`).
2. **Version Pinning:** Always increment `version` in `python_packages/pyproject.toml` (e.g. `0.2.1` -> `0.2.2`) when modifying shared code before running `publish.sh`.

---

## Public Modules & API Reference

### 1. `af_aidevs.model_armor`
Lightweight Zero-Trust security SDK communicating with `cr-model-armor`.

- **Function:** `async def verify(text: str, policy_context: str, session_id: str) -> bool`
  - `text`: Prompt or text content to inspect for jailbreaks, prompt injections, or policy violations.
  - `policy_context`: Domain identifier (e.g., `"negotiations_catalog"`, `"reactor_command"`).
  - `session_id`: Session ID passed via the `X-Session-ID` header.
  - **Returns:** `True` if safe to process, `False` if flagged/rejected.
- **Environment:** Requires `MODEL_ARMOR_URL` (injected via Secret Manager on Cloud Run or `.env` locally).

```python
from af_aidevs import model_armor

is_safe = await model_armor.verify(
    text=user_query,
    policy_context="negotiations_catalog",
    session_id=session_id,
)
if not is_safe:
    logger.warning("Prompt rejected by Model Armor policy")
```

---

### 2. `af_aidevs.clients.mcp`
Multi-server MCP client connecting to `cr-mcp-workspace` and `cr-mcp-web-gateway` with built-in `GoogleOIDCAuth` and `X-Session-ID` header propagation.

- **Function:** `async def get_all_mcp_tools(session_id: str, workspace_url: Optional[str] = None, web_url: Optional[str] = None) -> List[Any]`
- **Function:** `create_mcp_client(session_id: str, workspace_url: Optional[str] = None, web_url: Optional[str] = None) -> MultiServerMCPClient`

```python
from af_aidevs.clients.mcp import get_all_mcp_tools

tools = await get_all_mcp_tools(session_id=session_id)
# Returns LangChain StructuredTools from both workspace and web gateway
```

---

### 3. `af_aidevs.audit.bigquery`
Real-time telemetry and auditing streaming callbacks directly into BigQuery.

- **Classes:** `AuditService`, `BigQueryCallbackHandler`
- **Usage:** Passed into LangChain agents via `config={"callbacks": [callback_handler]}`.

```python
from af_aidevs.audit.bigquery import AuditService, BigQueryCallbackHandler

audit = AuditService(dataset_id="s03e04", table_id="audit")
callback = BigQueryCallbackHandler(audit_service=audit, session_id=session_id)
```

---

### 4. `af_aidevs.auth.oidc`
Custom HTTPX authentication handler managing Cloud Run service-to-service OIDC tokens.

- **Class:** `GoogleOIDCAuth(audience: str, token_override_env: Optional[str] = "MCP_WORKSPACE_TOKEN")`
- Automatically fetches ID tokens from Google Cloud Metadata Server in Cloud Run with 50-minute caching.

---

### 5. `af_aidevs.utils.prompts`
Loads Markdown system prompts with YAML frontmatter.

- **Function:** `load_system_prompt(base_dir: str = ".", filename: str = "system_prompt.md") -> PromptConfig`
  - Extracts `prompt_config.system_prompt`, `prompt_config.model`, `prompt_config.temperature`, `prompt_config.location`.
