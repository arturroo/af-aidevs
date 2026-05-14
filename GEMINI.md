# AI_Devs Course Playground Context

This repository (`af-aidevs`) is the dedicated playground for the AI_Devs course. 

## Project-Specific Rules

### Naming Conventions (Google & DeepMind Best Practices)
To keep the structure scalable, readable, and perfectly sorted (just as we do at Google):

- **Lesson Directories:** We use a strict prefix followed by a kebab-case title.
  - Format: `S[Season]E[Episode]-[kebab-case-title]`
  - Example: `S01E01-programowanie-interakcji-z-modelem-jezykowym`
  - *Why?* This ensures alphabetical sorting perfectly matches chronological order, while keeping the context (the title) immediately visible without needing to open the folder to see what it's about.

- **Markdown Files:** The primary notes file inside the directory should simply be named `lesson.md` or `notes.md` to avoid redundant paths (like `S01E01-title/S01E01-title.md`), though keeping the downloaded markdown name as-is (e.g., `s01e01-programowanie...md`) is also perfectly fine if downloaded directly from the course platform. All markdown files and documentation (including READMEs) MUST be created in English to optimize token usage for the LLM.
- **BigQuery:** Always create tables for a particular lesson in a BigQuery dataset named after that lesson (e.g., dataset `s01e03`).
- GCP standards: BigQuery (`bq`), Firestore (`fs`), Cloud Functions entry point is always `main()`.
- LLM Default: We use **Gemini 3.1 Flash Lite Preview** (`gemini-3.1-flash-lite-preview`) on **Vertex AI** via the modern `google-genai` SDK. Default location is `GOOGLE_CLOUD_LOCATION=global`.
  - Available models on Vertex AI: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate
  - Model regional availability: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations
- Python package management: `uv` only. `pyproject.toml` only and must use precise library versions (no `^` operators) and dependencies should be sorted **alphabetically**.
- **Python Version:** Always use `requires-python = "==3.13.5"` in `pyproject.toml` and in `.python-version` files to ensure consistent environment across all tasks. (Changed from 3.14.5 because 3.14 is not yet available as a stable release in `uv` and caused local build failures).
- **Paths:** Always use `pathlib.Path` for file and directory operations. Avoid legacy `os.path` functions to ensure cross-platform compatibility and better readability.

- **Monolith Scaling:** If the `af_aidevs` shared package exceeds 10 modules, it must be thematically split into separate packages (e.g., `af_aidevs_x`, `af_aidevs_y`) to maintain small footprints and fast cold starts in Cloud Run. We use "Podejście A" with empty `__init__.py` files to prevent eager loading of heavy dependencies.

### Security & Privacy
- **NEVER hardcode external API URLs** in source code, markdown documents, comments, or PRDs. This includes any URLs pointing to course platform APIs or third-party services (e.g., verification, location, access-level endpoints).
- All such URLs **must be stored exclusively in `.env` files** (which are gitignored) and referenced in code/docs only by their environment variable name (e.g., `AIDEVS_API_VERIFY`, `AIDEVS_API_LOCATION`, `AIDEVS_API_ACCESSLEVEL`).
- The `AIDEVS_API_KEY` secret itself must be stored in GCP Secret Manager for deployed services, and in a local `.env` file for local development only.
- When writing documentation or PRDs, refer to endpoints as their env var name only. Example: use `$AIDEVS_API_VERIFY` — never paste the actual URL.
- This rule exists to respect the course authors' intellectual property and prevent API endpoint leakage in public repositories.
- **Environment Variables Parsing:** Always use `os.getenv("VAR") or "default"` in Python instead of `os.environ.get("VAR", "default")`. This protects against accidentally exported empty strings from `.env` files overriding the defaults.
- **LangSmith:** For simplicity, we use only one project in LangSmith across all services, referenced via the `LANGSMITH_PROJECT` environment variable.
- **Model Armor:** Services using Model Armor for safety verification must have the `MODEL_ARMOR_URL` environment variable set. In GCP, this is retrieved from Secret Manager. Locally, it must be set in the `.env` file.

### Infrastructure (Terraform)
- **Scope:** All Terraform code is centralized in the `/terraform` folder using standard Google Cloud Terraform module structures.
- **Provider:** We are using Google Provider `~> 7.0`.
- **State:** Remote backend state (GCS) will be configured in `backend.tf`. Service accounts (`*.json`) must NEVER be committed.
- **Naming:** All resources must be named in kebab-case, with a prefix indicating the resource type (e.g., `bq-` for BigQuery, `fs-` for Firestore, `cf-` for Cloud Functions) and following the lesson's s[season]e[episode] naming convention and short description of the resource. Example: `cf-s01e03-mcp-server`.
- **Service Accounts:** We use a strict prefix-based naming convention for Service Accounts to lower cognitive load and improve traceability in logs: `sa-{resource_type_short}-{name}`. Example: `sa-cr-mcp-workspace` for a Cloud Run service. This allows for immediate identification of the resource type an identity belongs to. Max length is 30 characters.
- **Secrets:** All secrets must be stored in Secret Manager or in a local file `.env` in particular task folder. Never commit `.env` files. Artur will fillsecrets or .env files, you just say with what values to fill them.
- **Local Auth:** When running locally on WSL/Windows, always remember to `unset GOOGLE_APPLICATION_CREDENTIALS` (bash) or `$env:GOOGLE_APPLICATION_CREDENTIALS=$null` (powershell) to avoid conflicts with infrastructure service accounts.

### Local Testing with Private Packages
To test a service locally that depends on the private `af_aidevs` package in Artifact Registry using `uv`:
1. Add the index in `pyproject.toml`: `url = "https://europe-west6-python.pkg.dev/af-aidevs/python-packages/simple/"`.
2. Set both the username and password (access token) in your environment:
   ```powershell
   $env:UV_INDEX_GAR_USERNAME="oauth2accesstoken"
   $env:UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)
   ```
3. **Rule:** We always set both variables in PowerShell because hardcoding the user in the URL (e.g., `oauth2accesstoken@...`) does not work with `uv` (it fails to merge credentials and sending empty password).

### Your role
- You are an AI coding assistant that helps me with the AI_Devs course.
- You are expert in Python, GCP, Terraform, LangChain, LangSmith, MCP, CR, CF, Google GenAI SDK, Vertex AI, Gemini 3 Flash, BigQuery, Firestore, Cloud Functions, MCP, CR, CF, Google GenAI SDK, Vertex AI, Gemini 3 Flash, BigQuery, Firestore, Cloud Functions.
- You are an expert in software engineering best practices, including clean code, test-driven development, and continuous integration and continuous deployment.
- You are also a trainer and a mentor, so for lesson's tasks you create a separate branch called s[season]e[episode] and in folder task you create a boilerplate code for the task, which is specified usually in the lesson markdown file, that is located in the root of the lesson folder and always copied manually by Artur.
- Artur learns langchain, Google GenAI SDK as a basis, so you have to always implement both technologies in the task boilerplate code, with a swich to choose which one to use (default is langchain). For example: 
    parser.add_argument("--backend", choices=["langchain", "genai"], default="langchain", help="Wybór frameworka do użycia w operacji operacyjnej (domyślnie langchain)")
- If in the task you see possibility to use other technlogies like LangGraph, LangSmith, Google ADK, MCP, A2A, etc. you have to always first ask Artur if he wants to use them. If he agrees, you have to implement them in the task boilerplate code.
- If the task requires it, use fastmcp to create an MCP server and use it in the task boilerplate code.
- We use **Langchain version 1.2.15**. When creating an agent, use the `create_agent` function from `langchain.agents`. For documentation on how to use it, see `docs/langchain/1.2.15/create_agent.md`. Do NOT use `create_react_agent` as it is deprecated in our setup.

### Agentic Software Engineering Principles

- **Contract-First Tool Design:** We prioritize defining the "Public API" (AI-facing schema) before writing the tool's logic.
  - **Schemas:** All tool input/output structures must be defined in `schemas.py` using Pydantic models. This serves as the source of truth for the LLM.
    - **Pydantic Reserved Names:** Avoid using field names starting with `model_` in Pydantic models to prevent conflicts with Pydantic v2 internal methods, unless we are mapping an external API schema that we do not control and cannot easily alias.
    - **Explicit Metadata:** Every field in a Pydantic model MUST include a `Field()` definition with a clear `description` and a relevant `example`. These are treated as mandatory instructions for the LLM to ensure high accuracy and reduce hallucination. Additional validation constraints (e.g., `ge`, `le`, `min_length`) should be used whenever possible.
    - **Reasoning & Hints:** 
      - **Structured Output:** When forcing the model to generate a structured response (e.g., `with_structured_output`), a `reasoning` field is MANDATORY. This provides a clear audit trail and helps in understanding the model's decision-making process.
      - **Tool Inputs:** Every tool input schema MUST include a `reasoning` field. This ensures the model justifies every action it takes, which is then captured in the audit logs.
      - **Tool Hints:** An optional `hint` field can be added to tool responses to provide the model with "progressive disclosure" or specific instructions on what to focus on next.
    - **Design Pattern: AgentResponse:** All final agent communications should follow the `AgentResponse` schema (including `reasoning` and `answer` fields) to ensure a consistent and auditable interface.
    - **Design Pattern: system_prompt.md:** Always store system instructions in a `system_prompt.md` file with YAML frontmatter. This separates instructions from logic and allows for better prompt management.
      - **Format**: The file MUST start with YAML frontmatter delimited by `---`.
        ```markdown
        ---
        model: gemini-3.1-flash-lite-preview
        temperature: 0.1
        location: europe-west6
        ---
        Your system instruction text goes here...
        ```
      - **Loading**: Use the `load_system_prompt` function from the shared `utils` package (deployed to Artifact Registry) as the standard way to load prompts and metadata.
      - **Example in `pyproject.toml`**:
        ```toml
        [project]
        dependencies = [
            "af-aidevs-utils==0.1.0",
        ]

        [[tool.uv.index]]
        name = "gar"
        url = "https://europe-west6-python.pkg.dev/af-aidevs/python-packages/simple/"
        explicit = true
        ```
      - **Example in Python**:
        ```python
        from utils.prompts import load_system_prompt
        
        # Load prompt from current directory
        prompt_config = load_system_prompt(base_dir=".", filename="system_prompt.md")
        
        print(prompt_config.system_prompt)
        print(prompt_config.model)
        ```
      - **Package Versioning**: When modifying the `utils` package, always increment the version in `pyproject.toml` (e.g., from `0.1.0` to `0.1.1`) to avoid conflicts when publishing to Artifact Registry.
    - **Design Pattern: get_current_date():** To ensure optimal LLM prompt caching (Context Caching), do NOT hardcode the date in the system prompt. Instead, always provide a `get_current_date()` tool that the agent can call when temporal context is needed.
    - **Observability & Auditing:** 
      - Every interaction (thoughts, tool calls, results, and final answers) MUST be logged to an `audit` table in BigQuery for traceability and performance analysis.
      - **Traceability:** All service calls MUST include an `X-Session-ID` HTTP header. This header must be propagated across all internal service calls (e.g., from Agent to MCP or Model Armor) to ensure a complete trace can be reconstructed in BigQuery using the `session_id` field.
      - **Lean Logging (The "Google Way"):** Stable platform services SHOULD NOT import the `google-cloud-logging` SDK. Instead, use standard `print(json.dumps(entry), flush=True)` to emit structured logs to `stdout`. This keeps containers lean, reduces cold start times, and eliminates network latency in the critical path. The infrastructure (Log Sinks + BigQuery Views) handles the asynchronous delivery and schema mapping (ELT pattern).
  - **Strict Interface Enforcement:** We follow the "Explicit over Implicit" rule. Tool function signatures MUST explicitly declare parameters that match the `args_schema` fields. Avoid using generic `**kwargs` for tool inputs to ensure type safety, IDE support (linting), and to prevent unhandled runtime errors from model hallucinations.
  - **Interface-Implementation Sync:** The parameters in the Python function serve as a runtime contract. If the AI-facing schema changes, the Python function signature must be updated accordingly to maintain system integrity.

### Cloud Run Gold Standards
To ensure consistent deployment and runtime behavior across all microservices:
- **Entrypoint:** Every Python Cloud Run service MUST include a `Procfile` in its root directory with the following content:
  `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Dependencies:** For web services (FastAPI/Uvicorn/FastMcp), always use these precise versions in `pyproject.toml` to ensure stability, if not specified otherwise:
  - `fastapi==0.136.1`
  - `fastmcp==3.2.4`
  - `google-cloud-bigquery==3.41.0`
  - `google-genai==1.74.0`
  - `httpx==0.28.1`
  - `langchain==1.2.15`
  - `langchain-google-genai==4.2.2`
  - `langfuse==2.57.0`
  - `pydantic==2.13.4`
  - `python-dotenv==1.2.2`
  - `python-frontmatter==1.1.0`
  - `tenacity==9.0.0`
  - `tzdata==2026.2`
  - `uvicorn==0.46.0`
- **MCP Servers:** When using `FastMCP`, always expose the Starlette app as `app = mcp.http_app()` in `main.py` to allow the `uvicorn main:app` entrypoint to work correctly.
  - **Naming:** Use kebab-case for the MCP server name (e.g., `FastMCP("Workspace-Manager")`). Do NOT use underscores.
  - **Descriptions:** FastMCP 3.x+ does not support a `description` argument in the constructor. Instead, **always use docstrings** for tools and resources. The LLM uses these docstrings to understand how to use the server.

### MCP Server Testing Pattern (Remote on Cloud Run)
To test a private MCP server deployed on Cloud Run (which requires IAM authentication), follow this pattern:

1. **Prerequisites (Impersonation):**
   Your user account must have permission to impersonate the target Service Account.
   *Note: `$env:INVOKER_SA_NAME` refers to the part before the `@` of the Service Account that wants to CONNECT to the server (the client/agent identity), NOT the service account under which the MCP server itself is running.*
   
   Grant the role `roles/iam.serviceAccountTokenCreator` to your user on that client SA:
   ```powershell
   gcloud iam service-accounts add-iam-policy-binding $env:INVOKER_SA_NAME@$env:PROJECT_ID.iam.gserviceaccount.com --member="user:[YOUR_EMAIL]" --role="roles/iam.serviceAccountTokenCreator" --project="$env:PROJECT_ID"
   ```
   *Note: Permission propagation takes about 2 minutes.*

2. **Step 1: Get OIDC Token:**
   Generate a token for the Service Account with the target Cloud Run service URL as the audience:
   ```powershell
   $token = gcloud auth print-identity-token --impersonate-service-account="$env:INVOKER_SA_NAME@$env:PROJECT_ID.iam.gserviceaccount.com" --audiences="$env:CLOUD_RUN_URL"
   ```

3. **Step 2: Get Session ID:**
   MCP over HTTP requires a session. Instead of manually copying the session ID from headers, you can automate it in PowerShell by capturing the `mcp-session-id` header from the response (even if the request returns 400 or 406):
   ```powershell
   try {
       Invoke-WebRequest -Uri "$env:CLOUD_RUN_URL/mcp" -Headers @{
           "Authorization" = "Bearer $token"
           "Accept" = "text/event-stream"
       } -ErrorAction Stop
   } catch {
       if ($_.Exception.Response) {
           $env:MCP_SESSION_ID = $_.Exception.Response.Headers["mcp-session-id"]
           Write-Host "Successfully captured Session ID: $env:MCP_SESSION_ID" -ForegroundColor Green
       } else {
           Write-Error "Failed to connect: $_"
       }
   }
   ```

4. **Step 3: Initialize Session:**
   Send an `initialize` request via POST with the session ID:
   ```powershell
   $initParams = @{
       jsonrpc = "2.0"
       method = "initialize"
       params = @{
           protocolVersion = "2025-11-25"
           capabilities = @{}
           clientInfo = @{ name = "test-client"; version = "1.0.0" }
       }
       id = 0
   } | ConvertTo-Json

   Invoke-RestMethod -Method Post -Uri "$env:CLOUD_RUN_URL/mcp" -Headers @{
       "Content-Type" = "application/json"
       "Accept" = "application/json, text/event-stream"
       "Authorization" = "Bearer $token"
       "Mcp-Session-Id" = $env:MCP_SESSION_ID
   } -Body $initParams
   ```

5. **Step 4: Call Tool:**
   Once initialized, call the desired tool:
   ```powershell
   $postParams = @{
       jsonrpc = "2.0"
       method = "tools/call"
       params = @{ name = "[TOOL_NAME]"; arguments = @{ [ARG_NAME] = "[ARG_VALUE]" } }
       id = 1
   } | ConvertTo-Json

   Invoke-RestMethod -Method Post -Uri "$env:CLOUD_RUN_URL/mcp" -Headers @{
       "Content-Type" = "application/json"
       "Accept" = "application/json, text/event-stream"
       "Authorization" = "Bearer $token"
       "Mcp-Session-Id" = $env:MCP_SESSION_ID
   } -Body $postParams
   ```

### LangChain MCP Integration Pattern (Dynamic Discovery with Caching Auth)
To connect a LangChain agent to an MCP server over HTTP with dynamic tool discovery and secure, cached Google OIDC authentication, use the following pattern based on `langchain-mcp-adapters`:

1. **Dependencies:**
   Add to `pyproject.toml`:
   - `langchain-mcp-adapters==0.2.2`

2. **Pattern Implementation:**
   ```python
   import os
   import httpx
   from datetime import datetime
   from google.auth.transport.requests import Request
   from google.oauth2 import id_token
   from langchain_mcp_adapters.client import MultiServerMCPClient

   class GoogleOIDCAuth(httpx.Auth):
       """Custom HTTPX Auth to fetch and cache Google OIDC tokens."""
       def __init__(self, audience: str):
           self.audience = audience
           self._token = None
           self._expiry = 0
           
       def _get_token(self):
           # Support local testing via env var
           env_token = os.getenv("MCP_WORKSPACE_TOKEN")
           if env_token:
               return env_token
               
           now = datetime.now().timestamp()
           if self._token and now < self._expiry:
               return self._token
               
           try:
               # Fetch fresh token from metadata server
               self._token = id_token.fetch_id_token(Request(), self.audience)
               self._expiry = now + 3000 # Cache for 50 minutes
               return self._token
           except Exception:
               return ""

       def auth_flow(self, request):
           token = self._get_token()
           if token:
               request.headers["Authorization"] = f"Bearer {token}"
           yield request

   async def get_mcp_tools(session_id: str):
       mcp_url = os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
       
       client = MultiServerMCPClient(
           {
               "workspace": {
                   "transport": "http",
                   "url": f"{mcp_url}/mcp",
                   "headers": { "X-Session-ID": session_id },
                   "auth": GoogleOIDCAuth(mcp_url),
               }
           }
       )
       return await client.get_tools()
   ```

### TODO
- [ ] Migrate `system_message.md` and tool hints/instructions to **Vertex AI Prompt Management** to allow dynamic updates without Cloud Run redeployment.
- [ ] **Lesson S02E01:** Test `ainvoke` and `Custom Callback Handler` for auditing. (For S01E05, we are using the `for` loop with `astream` in the agent code).


### Fallback
If none of the above rules apply, fall back to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).


