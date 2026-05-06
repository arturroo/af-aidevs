# AI_Devs Course Playground Context

This repository (`af-aidevs`) is the dedicated playground for the AI_Devs course. 

## Project-Specific Rules

### Naming Conventions (Google & DeepMind Best Practices)
To keep the structure scalable, readable, and perfectly sorted (just as we do at Google):

- **Lesson Directories:** We use a strict prefix followed by a kebab-case title.
  - Format: `S[Season]E[Episode]-[kebab-case-title]`
  - Example: `S01E01-programowanie-interakcji-z-modelem-jezykowym`
  - *Why?* This ensures alphabetical sorting perfectly matches chronological order, while keeping the context (the title) immediately visible without needing to open the folder to see what it's about.

- **Markdown Files:** The primary notes file inside the directory should simply be named `lesson.md` or `notes.md` to avoid redundant paths (like `S01E01-title/S01E01-title.md`), though keeping the downloaded markdown name as-is (e.g., `s01e01-programowanie...md`) is also perfectly fine if downloaded directly from the course platform.
- **BigQuery:** Always create tables for a particular lesson in a BigQuery dataset named after that lesson (e.g., dataset `s01e03`).
- GCP standards: BigQuery (`bq`), Firestore (`fs`), Cloud Functions entry point is always `main()`.
- LLM Default: We use **Gemini 3.1 Flash Lite Preview** (`gemini-3.1-flash-lite-preview`) on **Vertex AI** via the modern `google-genai` SDK. Default location is `GOOGLE_CLOUD_LOCATION=global`.
- Python package management: `uv` only. `pyproject.toml` or `requirements.txt` must use precise library versions (no `^` operators).
- **Python Version:** Always use `requires-python = "==3.12.*"` in `pyproject.toml` to ensure consistent environment across all tasks.
- **Paths:** Always use `pathlib.Path` for file and directory operations. Avoid legacy `os.path` functions to ensure cross-platform compatibility and better readability.

### Security & Privacy
- **NEVER hardcode external API URLs** in source code, markdown documents, comments, or PRDs. This includes any URLs pointing to course platform APIs or third-party services (e.g., verification, location, access-level endpoints).
- All such URLs **must be stored exclusively in `.env` files** (which are gitignored) and referenced in code/docs only by their environment variable name (e.g., `AIDEVS_API_VERIFY`, `AIDEVS_API_LOCATION`, `AIDEVS_API_ACCESSLEVEL`).
- The `AIDEVS_API_KEY` secret itself must be stored in GCP Secret Manager for deployed services, and in a local `.env` file for local development only.
- When writing documentation or PRDs, refer to endpoints as their env var name only. Example: use `$AIDEVS_API_VERIFY` — never paste the actual URL.
- This rule exists to respect the course authors' intellectual property and prevent API endpoint leakage in public repositories.
- **Environment Variables Parsing:** Always use `os.getenv("VAR") or "default"` in Python instead of `os.environ.get("VAR", "default")`. This protects against accidentally exported empty strings from `.env` files overriding the defaults.

### Infrastructure (Terraform)
- **Scope:** All Terraform code is centralized in the `/terraform` folder using standard Google Cloud Terraform module structures.
- **Provider:** We are using Google Provider `~> 7.0`.
- **State:** Remote backend state (GCS) will be configured in `backend.tf`. Service accounts (`*.json`) must NEVER be committed.
- **Naming:** All resources must be named in kebab-case, with a prefix indicating the resource type (e.g., `bq-` for BigQuery, `fs-` for Firestore, `cf-` for Cloud Functions) and following the lesson's s[season]e[episode] naming convention and short description of the resource. Example: `cf-s01e03-mcp-server`.
- **Service Accounts:** We use a strict prefix-based naming convention for Service Accounts to lower cognitive load and improve traceability in logs: `sa-{resource_type_short}-{name}`. Example: `sa-cr-mcp-workspace` for a Cloud Run service. This allows for immediate identification of the resource type an identity belongs to. Max length is 30 characters.
- **Secrets:** All secrets must be stored in Secret Manager or in a local file `.env` in particular task folder. Never commit `.env` files. Artur will fillsecrets or .env files, you just say with what values to fill them.
- **Local Auth:** When running locally on WSL/Windows, always remember to `unset GOOGLE_APPLICATION_CREDENTIALS` (bash) or `$env:GOOGLE_APPLICATION_CREDENTIALS=$null` (powershell) to avoid conflicts with infrastructure service accounts.

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
    - **Explicit Metadata:** Every field in a Pydantic model MUST include a `Field()` definition with a clear `description` and a relevant `example`. These are treated as mandatory instructions for the LLM to ensure high accuracy and reduce hallucination. Additional validation constraints (e.g., `ge`, `le`, `min_length`) should be used whenever possible.
    - **Reasoning & Hints:** 
      - **Structured Output:** When forcing the model to generate a structured response (e.g., `with_structured_output`), a `reasoning` field is MANDATORY. This provides a clear audit trail and helps in understanding the model's decision-making process.
      - **Tool Inputs:** Every tool input schema MUST include a `reasoning` field. This ensures the model justifies every action it takes, which is then captured in the audit logs.
      - **Tool Hints:** An optional `hint` field can be added to tool responses to provide the model with "progressive disclosure" or specific instructions on what to focus on next.
    - **Design Pattern: AgentResponse:** All final agent communications should follow the `AgentResponse` schema (including `reasoning` and `answer` fields) to ensure a consistent and auditable interface.
    - **Design Pattern: system_prompt.md:** Always store system instructions in a `system_prompt.md` file with YAML frontmatter containing at least `model` and `temperature`. This separates instructions from logic and allows for better prompt management.
    - **Design Pattern: get_current_date():** To ensure optimal LLM prompt caching (Context Caching), do NOT hardcode the date in the system prompt. Instead, always provide a `get_current_date()` tool that the agent can call when temporal context is needed.
    - **Observability & Auditing:** 
      - Every interaction (thoughts, tool calls, results, and final answers) MUST be logged to an `audit` table in BigQuery for traceability and performance analysis.
      - **Traceability:** All service calls MUST include an `X-Session-ID` HTTP header. This header must be propagated across all internal service calls (e.g., from Agent to MCP or Model Armor) to ensure a complete trace can be reconstructed in BigQuery using the `session_id` field.
      - **Lean Logging (The "Google Way"):** Stable platform services SHOULD NOT import the `google-cloud-logging` SDK. Instead, use standard `print(json.dumps(entry), flush=True)` to emit structured logs to `stdout`. This keeps containers lean, reduces cold start times, and eliminates network latency in the critical path. The infrastructure (Log Sinks + BigQuery Views) handles the asynchronous delivery and schema mapping (ELT pattern).
  - **Strict Interface Enforcement:** We follow the "Explicit over Implicit" rule. Tool function signatures MUST explicitly declare parameters that match the `args_schema` fields. Avoid using generic `**kwargs` for tool inputs to ensure type safety, IDE support (linting), and to prevent unhandled runtime errors from model hallucinations.
  - **Interface-Implementation Sync:** The parameters in the Python function serve as a runtime contract. If the AI-facing schema changes, the Python function signature must be updated accordingly to maintain system integrity.

### TODO
- [ ] Migrate `system_message.md` and tool hints/instructions to **Vertex AI Prompt Management** to allow dynamic updates without Cloud Run redeployment.
