---
status: "accepted"
date: 2026-09-25
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S04E05 — foodwarehouse

## 1. Context
The `foodwarehouse` mission requires reprogramming Siegfried's central automated food and tool distribution logistics via Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) to fulfill the resource requirements of eight starving regional settlements without raising alarms in the "OKO" surveillance grid. The system faces multiple operational constraints: unknown SQLite database schemas, cryptographic SHA1 order authorization rules, strict item quantity matching (`Bez braków i bez nadmiarów`), and Centrala rate-limiting. The architectural challenge lies in balancing **high agentic autonomy and progressive disclosure** (starting with knowledge of `tool: "help"` and discovering capabilities dynamically) with **reliable pre-flight validation and batch execution** (preventing dirty orders or accidental container disk poisoning).

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Baseline Compliance & Scaffolding | Option 1.1: 100% GEMINI.md Baseline Adherence | Guarantees standard containerization, dual LangChain/ADK parity, BigQuery telemetry, and Terraform management. |
| 2 | Agent Lifecycle & Progressive Disclosure | Option 2.1: Four-Phase Progressive Disclosure & Staging | Allows autonomous exploration (starting only with `help`) and documents knowledge in workspace before executing orders. |
| 3 | API Interaction & Safe Circuit Breaking | Option 3.1: Universal Meta-Tool with Mutative Interception Circuit Breaker | Allows unbounded exploration (`help`, `database`, `signatureGenerator`) while blocking fragile single-order mutations with steering hints. |
| 4 | Workspace Storage & State Isolation | Option 4.1: Session-Isolated Staging via `cr-mcp-workspace` | Strictly satisfies Zero Container Disk Poisoning by maintaining all intermediate manifests and `TODOs.md` in remote workspace. |
| 5 | Pre-Flight Validation & Defense in Depth | Option 5.1: 3-Layer Validation Defense & Atomic Batch Dispatcher | Combines prompt SOP, semantic tool descriptions, and hard code assertion in `dispatch_staged_orders` to guarantee 100% compliant execution. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Baseline Compliance & Cloud Run Deployment

#### Problem & Drivers
Every lesson microservice in the `af-aidevs` repository must maintain architectural consistency, automated auditability, infrastructure-as-code synchronization, and support both canonical agent frameworks (LangChain and Google ADK).

#### Considered Options

##### Option 1.1: 100% GEMINI.md Baseline Adherence (ACCEPTED)
* **Description**: Implement `cr-s04e05-foodwarehouse` as a Cloud Run microservice with BigQuery audit dataset `s04e05`, registered in `terraform/variables.tf`, powered by Vertex AI Gemini 3.8 Flash (`gemini-3.8-flash`), featuring dual LangChain (`langchain==1.2.15`) and Google ADK (`google-adk==1.33.0`) backends, pinned to Python 3.13.5 with `uv`.
* **Data Engineering & Performance**: Full BigQuery audit streaming for prompt/completion/tool-invocation telemetry. Sub-second container cold starts on Cloud Run.
* **Cost & FinOps**: Free-tier eligible compute on Cloud Run; minimal inference cost with low-thinking Gemini 3.8 Flash.
* **Security & Reliability**: Zero hardcoded URLs; secrets managed via GCP Secret Manager and `.env`; OIDC authentication for private Cloud Run invocation.
* **Pros & Cons**:
  * Good, because it adheres strictly to repository standards, CI/CD, and quality gates.
  * Bad / Trade-off, because it requires container scaffolding and Terraform variable registration.

##### Option 1.2: Local-Only Script Deviation (REJECTED)
* **Description**: Create a standalone Python script without Cloud Run containerization, BigQuery telemetry, or Terraform registration.
* **Data Engineering & Performance**: No central telemetry or long-term observability.
* **Cost & FinOps**: Zero cloud hosting cost, but introduces technical debt and inconsistency across lessons.
* **Security & Reliability**: High risk of unmonitored failures and environment drift.
* **Pros & Cons**:
  * Good, because it is slightly faster to write initially.
  * Bad / Trade-off, because it violates core repository rules and skips production-grade engineering standards.

#### Consequences
* **Positive**: Full observability in BigQuery, clean CLI/HTTP execution modes, seamless Terraform deployment.
* **Negative / Trade-offs**: Scaffolding files (`Dockerfile`, `cloudbuild.yaml`, `.dockerignore`) required.
* **Confirmation**: Verified via quality gate commands (`ruff`, `mypy`, `pytest`, `terraform plan`).

---

### Decision 2: Agent Lifecycle & Progressive Disclosure Architecture

#### Problem & Drivers
In previous lessons (such as S04E02 `windpower` and S04E03 `domatowo`), we established that the agent should not be pre-loaded with static assumptions about Centrala's API and SQLite schemas. The agent should be given autonomy to discover the API starting solely from `tool: "help"` (Progressive Disclosure), record structured documentation in Markdown on the workspace, and only then proceed to assembling and executing orders.

#### Considered Options

##### Option 2.1: Four-Phase Progressive Disclosure & Staging Architecture (ACCEPTED)
* **Description**:
  - **Phase 1: Autonomous API & Schema Discovery (Progressive Disclosure)**: The agent begins knowing only `call_centrala_api(tool="help")`. It queries Centrala to discover available tools (`database`, `signatureGenerator`, `orders`, `reset`, `done`). It saves discovered documentation into `docs/api_spec.md` in `cr-mcp-workspace`. Then it executes dynamic SQL introspection via `call_centrala_api(tool="database", params={"query": "show tables"})` and `PRAGMA table_info`, extracting destination codes and user credentials into `docs/db_schema.md`.
  - **Phase 2: Manifest Assembly & Signature Staging**: The agent reads municipal requirements from `cr-mcp-workspace/food4cities.json` (seeded at session initialization from `$AIDEVS_FOOD4CITIES_URL`), requests SHA1 signatures via `call_centrala_api(tool="signatureGenerator", params={...})`, and stages the 8 complete orders into `cr-mcp-workspace` as `orders_manifest.json` alongside a tracking checklist `TODOs.md`.
  - **Phase 3: Pre-Flight Validation Gate**: The agent invokes `validate_staged_orders()`. The validator cross-checks all 8 orders against `food4cities.json` requirements and SQLite destinations.
  - **Phase 4: Atomic Batch Execution & Audit**: Once validated, the agent invokes `dispatch_staged_orders()`, which triggers `reset` -> 8x `orders.create` -> 8x batch `orders.append` -> `done` -> flag capture.
* **Data Engineering & Performance**: Separates exploratory reasoning from batch execution; optimizes network calls by buffering orders in workspace before network dispatch.
* **Cost & FinOps**: Minimal token usage with Gemini 3.8 Flash; documents persisted to workspace prevent re-discovering schemas on retries.
* **Security & Reliability**: Zero ungrounded model assumptions; resilient to schema drift.
* **Pros & Cons**:
  * Good, because it implements true progressive disclosure and agentic learning.
  * Good, because persistent workspace documentation decouples learning from execution.
  * Bad / Trade-off, because multi-phase workflows require structured prompt instructions.

##### Option 2.2: Blind Single-Turn Execution (REJECTED)
* **Description**: Hardcode all API payloads and SQL queries directly into prompt or code, bypassing discovery.
* **Data Engineering & Performance**: Lower turn count but fragile.
* **Cost & FinOps**: Marginal token savings.
* **Security & Reliability**: Fails immediately if table names, column schemas, or signature formats shift.
* **Pros & Cons**:
  * Good, because fewer agent turns.
  * Bad, because violates core AI_Devs educational objectives and brittle in production.

#### Consequences
* **Positive**: Adaptive, self-documenting agent that learns API capabilities dynamically.
* **Negative / Trade-offs**: Requires initial discovery turns before order creation.
* **Confirmation**: Verified by asserting `docs/api_spec.md` and `docs/db_schema.md` exist in workspace after Phase 1.

---

### Decision 3: API Interaction Layer — Universal Meta-Tool with Mutative Interception Circuit Breaker

#### Problem & Drivers
Centrala's API exposes dynamic RPC-style tools (`help`, `database`, `signatureGenerator`, `orders`, `reset`, `done`). If we generate separate, static Python tools for each command (e.g. `generate_signature(user_id: int, salt: str)`), we introduce rigid, ungrounded assumptions that break if Centrala changes field names or parameters. Conversely, if we permit the agent to issue raw single-order `create` and `append` calls through `call_centrala_api`, the agent enters an 18-turn loop prone to forgetting `order_id` values, accumulating duplicate items, and exhausting rate limits.

#### Considered Options

##### Option 3.1: Universal Meta-Tool with Mutative Interception Circuit Breaker (ACCEPTED)
* **Description**: Provide a single meta-tool `call_centrala_api(tool: str, params: dict[str, Any] = {}, reasoning: str = "")` routed through `cr-mcp-web-gateway` with automated Tenacity backoff for rate limits (`-9999` and HTTP 429).
  - **Permitted Operations (Read/Discovery)**: `help`, `database` (read queries), `signatureGenerator`, `orders` (with `action: "get"`), and `reset`.
  - **Intercepted Operations (Circuit Breaker with Steering Hints)**:
    - If the agent calls `tool == "orders"` with `action in ("create", "append")`, the tool blocks execution and returns:
      `{"status": "blocked", "message": "Pojedyncza modyfikacja zamówień jest zablokowana. Zbierz wszystkie 8 zamówień w orders_manifest.json w workspace, zwaliduj przez validate_staged_orders i wyślij atomowo przez dispatch_staged_orders."}`
    - If the agent calls `tool == "done"`, the tool blocks execution and returns:
      `{"status": "blocked", "message": "Bezpośrednie wywołanie 'done' jest zablokowane. Wywołaj narzędzie 'dispatch_staged_orders', które automatycznie przeprowadzi walidację, zresetuje magazyn, załaduje wszystkie 8 zamówień i zweryfikuje rozwiązanie."}`
* **Data Engineering & Performance**: Shields Centrala from partial, corrupting state mutations; zero prompt-level credential exposure.
* **Cost & FinOps**: Minimal token spend; eliminates 18-turn LLM ping-pong loops.
* **Security & Reliability**: Satisfies Zero Direct Container Egress; enforces self-healing agent steering.
* **Pros & Cons**:
  * Good, because 100% agnostic to discovery schemas while actively preventing dangerous state corruption.
  * Good, because guides the LLM back to the golden path if it attempts fragile single-order mutations.
  * Bad / Trade-off, because requires explicit parameter filtering logic in the meta-tool implementation.

##### Option 3.2: Unrestricted Universal Tool (REJECTED)
* **Description**: Allow any Centrala tool call including single-order `create` and `append`.
* **Data Engineering & Performance**: Highly fragmented state; excessive turn latency and high token consumption.
* **Cost & FinOps**: Consumes up to 18 LLM turns per run.
* **Security & Reliability**: High failure rate; partial order mutations cannot be rolled back easily.
* **Pros & Cons**:
  * Good, because simpler tool implementation.
  * Bad, because creates fragile 18-turn execution loops with high risk of state corruption.

#### Consequences
* **Positive**: Absolute protection against incomplete warehouse mutations; reliable self-healing agent behavior.
* **Negative / Trade-offs**: Agent cannot manipulate individual orders manually outside `dispatch_staged_orders`.
* **Confirmation**: Unit tests verifying that `call_centrala_api` blocks `orders: create/append` and `done` with clear guidance messages.

---

### Decision 4: Workspace Storage & State Isolation via `cr-mcp-workspace`

#### Problem & Drivers
As codified in `GEMINI.md` (Strict Container Statelessness & Zero Disk Poisoning), Cloud Run containers must NEVER write intermediate scratch buffers or staging files to local container disk storage (`workspace/`), as local files get accidentally baked into Docker images via `COPY . .` causing stale data poisoning and false validation failures.

#### Considered Options

##### Option 4.1: Session-Isolated Staging via `cr-mcp-workspace` (ACCEPTED)
* **Description**: All intermediate files (`food4cities.json`, `orders_manifest.json`, `TODOs.md`, `docs/api_spec.md`, `docs/db_schema.md`) are stored exclusively in the remote `cr-mcp-workspace` microservice using the session ID (`X-Session-ID`). The agent is equipped with standard workspace tools (`read_file`, `write_file`, `list_files`).
* **Data Engineering & Performance**: Remote workspace operations via OIDC; fast JSON serialization.
* **Cost & FinOps**: Free-tier Cloud Run storage; zero container disk bloating.
* **Security & Reliability**: Complete isolation across sessions; prevents container filesystem poisoning.
* **Pros & Cons**:
  * Good, because 100% compliant with container statelessness standards.
  * Good, because allows agent to inspect, review, and patch staged files via `write_file`.
  * Bad / Trade-off, because workspace I/O introduces minor network overhead.

##### Option 4.2: Local Container Disk Storage (`/tmp` or `workspace/`) (REJECTED)
* **Description**: Write JSON files and markdown notes to local container disk.
* **Data Engineering & Performance**: Fast local I/O.
* **Cost & FinOps**: Zero network egress.
* **Security & Reliability**: Severe violation of `GEMINI.md`; risks baking stale test state into Docker builds.
* **Pros & Cons**:
  * Good, because simple file operations.
  * Bad, because dangerous architectural anti-pattern for Cloud Run.

#### Consequences
* **Positive**: Clean, hermetic container builds with session-isolated execution state.
* **Negative / Trade-offs**: Requires `MCPService` client with local fallback for offline tests.
* **Confirmation**: Verified by verifying `.dockerignore` excludes `workspace/` and inspecting `cr-mcp-workspace` logs.

---

### Decision 5: Pre-Flight Validation Gate & Three-Layer Defense-in-Depth

#### Problem & Drivers
Centrala requires exact fulfillment of 8 municipal orders without deficit or surplus (`Bez braków i bez nadmiarów`). Submitting an incomplete or miscalculated order risks failing verification and requires a full `reset`. The architectural challenge is ensuring the LLM reliably invokes validation before dispatching without relying on blind trust.

#### Considered Options

##### Option 5.1: Three-Layer Defense-in-Depth for Validation & Atomic Dispatch (ACCEPTED)
* **Description**:
  1. **Layer 1 (Procedural Steering)**: The system prompt codifies a strict Standard Operating Procedure (SOP) where Step 3 is mandatory Pre-Flight Validation.
  2. **Layer 2 (Semantic Tool Steering)**: The tool description for `validate_staged_orders` explicitly marks it as required before dispatch, while `dispatch_staged_orders` warns that valid=true is an absolute prerequisite.
  3. **Layer 3 (Deterministic Code Assertion)**: The first statement in `dispatch_staged_orders` unconditionally calls `ValidationService.validate_manifest()`. If `valid == False`, dispatch aborts immediately, returning detailed field errors and actionable repair hints (`"Popraw plik orders_manifest.json za pomocą write_file..."`).
  - Upon valid assertion, `dispatch_staged_orders` executes `reset` -> 8x `orders.create` -> 8x batch `orders.append` -> `done` in <2 seconds.
* **Data Engineering & Performance**: Sub-2s batch dispatch; saves 16 redundant LLM turns; 0% chance of corrupt dispatch.
* **Cost & FinOps**: Drastically reduces LLM token consumption and execution latency.
* **Security & Reliability**: 100% deterministic batch execution; zero risk of state desynchronization or forgotten order IDs.
* **Pros & Cons**:
  * Good, because multi-layered defense guarantees validation even if the LLM acts erratically.
  * Good, because agent can fix errors locally via `write_file` before Centrala ever sees them.
  * Bad / Trade-off, because requires building `ValidationService` and dispatch logic.

##### Option 5.2: Unchecked Single-Layer Dispatch (REJECTED)
* **Description**: Rely entirely on prompt instructions to validate, letting dispatch execute blindly.
* **Data Engineering & Performance**: Prone to failed submissions.
* **Cost & FinOps**: Wasteful on failed runs requiring full resets.
* **Security & Reliability**: Weak; model non-compliance directly causes Centrala validation failure.
* **Pros & Cons**:
  * Good, because less validation code.
  * Bad, because fragile and untrustworthy in production.

#### Consequences
* **Positive**: Flawless zero-defect batch execution on Centrala with sub-2s dispatch latency and self-healing agent capability.
* **Negative / Trade-offs**: Minor development overhead for `ValidationService` and `dispatch_staged_orders`.
* **Confirmation**: Comprehensive unit tests in `tests/test_validation_service.py` asserting that invalid manifests are blocked before network dispatch.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [PRD.md](PRD.md)
  - [Lesson Source Notes](../s04e05-projektowanie-rozwiazan-wewnatrzfirmowych-1775189135.md)
  - [S04E02 Architecture Decision Record](../../s04e02-aktywna-wspolpraca-z-ai/task/ADR.md)
  - [S04E03 Architecture Decision Record](../../s04e03-kontekstowa-wspolpraca-z-ai/task/ADR.md)
  - [S04E04 Architecture Decision Record](../../s04e04-projektowanie-wlasnej-bazy-wiedzy-dla-ai/task/ADR.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
