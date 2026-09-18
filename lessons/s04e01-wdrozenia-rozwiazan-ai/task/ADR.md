<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-18
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S04E01 - OKO Surveillance Record Manipulation (`okoeditor`)

## 1. Context
The task `okoeditor` requires covertly altering incident and task records in the authoritarian surveillance system **Centrum Operacyjne OKO** to protect the survivor city of Skolwin. Phished operator credentials (`Zofia`) exist, but any interactive write operations in the web UI will trigger alarms and sever access. The mission must be carried out exclusively via Centrala's backdoor API (`$AIDEVS_VERIFY`). The system's architectural fitness function is defined by achieving closed-loop verification: the agent must introspect available operations using `help`, execute three distinct data mutations (reclassifying Skolwin incident to animals, completing the Skolwin task with animal notes, and injecting a diversion incident in Komarowo), and successfully terminate with `done` to capture the course flag `{FLG:...}`.

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Baseline Standards & Stack | Adhere 100% to GEMINI.md Baseline | Guarantees architectural consistency across Terraform, BigQuery audit streaming, Cloud Run, Gemini 3.8 Flash, and dual framework parity. |
| 2 | Tool Architecture for Centrala API | Dynamic Introspection Single Tool Wrapper (`call_oko_api`) | Maximizes autonomy by discovering API schemas via `help` at runtime without requiring hardcoded static tools for unknown endpoints. |
| 3 | Surveillance Interface Exposure | Pure API-Only Execution (Zero Web UI Interaction) | Completely eliminates detection risk and session timeouts by routing all inspection and mutations through the backdoor API. |
| 4 | State Validation & Error Recovery | Dynamic Re-Query & Self-Correction Loop | Ensures resiliency against schema mismatches or transient network drops with bounded retries before issuing `done`. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Architectural Baseline & Standards Adherence

#### Problem & Drivers
The task microservice requires full integration with existing infrastructure (Terraform, BigQuery telemetry, Vertex AI IAM, and dual framework execution).

#### Considered Options

##### Option 1.1: Adhere 100% to GEMINI.md Baseline (ACCEPTED)
* **Description**: Deploy a standard Cloud Run microservice `cr-s04e01-okoeditor` managed via Terraform in `terraform/variables.tf`, BigQuery dataset `s04e01` with streaming `audit` table, Gemini 3.8 Flash (`thinking_level="low"`) on Vertex AI (`global`), dual agent backends (LangChain `1.2.15` and Google ADK `1.33.0`), and Python 3.13.5 with `uv`.
* **Data Engineering & Performance**: Native integration with `af_aidevs.audit.bigquery` for structured JSON streaming; sub-second cold starts with pre-compiled dependency pins.
* **Cost & FinOps**: Fully compliant with GCP free-tier quotas; minimal compute footprint (1 CPU, 1Gi memory, CPU idle enabled).
* **Security & Reliability**: Workload identity and IAM authentication (`roles/aiplatform.user`, `roles/bigquery.dataEditor`); Zero-Trust secret management via Secret Manager and local `.env`.
* **Pros & Cons**:
  * Good, because it maintains complete feature and architectural parity across all lessons.
  * Good, because dual backend support satisfies all educational requirements for LangChain and Google ADK.
  * Trade-off: Requires scaffolding both LangChain and ADK agent implementations.

##### Option 1.2: Custom Lightweight Script Deviation (REJECTED)
* **Description**: A standalone one-off Python script running locally without Cloud Run or BigQuery audit infrastructure.
* **Data Engineering & Performance**: No telemetry persistence or centralized queryability.
* **Cost & FinOps**: Zero GCP resource footprint beyond model tokens.
* **Security & Reliability**: Fragile execution without containerized lifecycle guarantees.
* **Pros & Cons**:
  * Good, because faster initial scratchpad execution.
  * Bad, because violates repo standard architecture and prevents deployment to Cloud Run.

#### Consequences
* **Positive**: Predictable CI/CD and container builds via `cloudbuild.yaml`, automated audit tracking in BigQuery dataset `s04e01`.
* **Negative / Trade-offs**: Scaffolding overhead for Cloud Run containerization.
* **Confirmation**: Verified via `uv run pytest` tests, `curl.exe` health checks on `/health`, and BigQuery audit queries.

---

### Decision 2: Tool Architecture & Centrala API Interaction

#### Problem & Drivers
The backdoor API provides a `help` action that documents available commands. Hardcoding mutations statically risks brittleness if Centrala's internal parameters or schemas differ slightly.

#### Considered Options

##### Option 2.1: Dynamic Introspection Single Tool Wrapper (`call_oko_api`) (ACCEPTED)
* **Description**: Implement a unified tool `call_oko_api(action: str, params: dict | None = None)` that routes requests directly to `$AIDEVS_VERIFY` with the standard `{apikey, task: "okoeditor", answer: {action, ...params}}` envelope. The agent uses this tool first to discover the API capabilities via `action: "help"`, plans the 3 mutations, and executes them dynamically.
* **Data Engineering & Performance**: Single tool schema passed to the LLM minimizes prompt token overhead compared to 5+ distinct tools.
* **Cost & FinOps**: Lower input token usage per LLM turn due to compact tool definitions.
* **Security & Reliability**: API key is injected securely inside the tool service and never exposed to the LLM context or logs.
* **Pros & Cons**:
  * Good, because adapts seamlessly to whatever schema `help` outputs without code modifications.
  * Good, because clean single-tool implementation for both LangChain and Google ADK.
  * Trade-off: The LLM must construct the action payload dictionary correctly from the help text.

##### Option 2.2: Static Dedicated Tools per Action (REJECTED)
* **Description**: Manually probe `help` beforehand and define static Pydantic schemas: `ReclassifyIncidentTool`, `UpdateTaskTool`, `CreateIncidentTool`, `CompleteVerificationTool`.
* **Data Engineering & Performance**: Larger tool definitions increase prompt size on every reasoning step.
* **Cost & FinOps**: Slightly higher token consumption per turn.
* **Security & Reliability**: Strict compile-time typing, but brittle if the backend schema evolves.
* **Pros & Cons**:
  * Good, because strongly-typed Pydantic validation on tool arguments.
  * Bad, because eliminates the agent's ability to autonomously introspect and adapt to API schema variations.

#### Consequences
* **Positive**: Highly flexible agent loop; zero maintenance if action parameters have optional fields.
* **Negative / Trade-offs**: Agent reasoning must carefully parse the response from `action: help`.
* **Confirmation**: Integration tests asserting that `call_oko_api` handles `help`, mutations, and `done` actions cleanly.

---

### Decision 3: Surveillance Web Panel Reconnaissance Strategy

#### Problem & Drivers
Operator credentials (`Zofia` / `Zofia2026!`) are provided for the web panel `$AIDEVS_OKO_PANEL_URL`. However, the narrative strictly forbids modifying data via the UI on pain of detection.

#### Considered Options

##### Option 3.1: Pure API-Only Execution (Zero Web UI Interaction) (ACCEPTED)
* **Description**: Completely avoid issuing requests to the web UI. Centrala's backdoor API provides all required querying, state inspection, and mutation primitives.
* **Data Engineering & Performance**: Eliminates browser scraping latency and unnecessary headless browser overhead.
* **Cost & FinOps**: Zero headless browser compute or memory usage.
* **Security & Reliability**: 100% blast-radius containment: zero possibility of accidental POST/PUT form submissions triggering operator alarms.
* **Pros & Cons**:
  * Good, because strictly respects the operational constraint: "pod żadnym pozorem nie wolno Ci niczego zmieniać w interfejsie webowym".
  * Good, because keeps the microservice lightweight and fast.
  * Trade-off: Cannot visually inspect rendered HTML tables (not needed when API provides raw data).

##### Option 3.2: Hybrid API + Web Scraping via MCP (REJECTED)
* **Description**: Connect `cr-mcp-web-gateway` to scrape the web panel in read-only mode to fetch HTML tables while using the API for mutations.
* **Data Engineering & Performance**: Incurs network latency and HTML parsing overhead.
* **Cost & FinOps**: Additional container invocations.
* **Security & Reliability**: Risk of session token leaks or unintentional state modification.
* **Pros & Cons**:
  * Good, because visual cross-verification of web panel state.
  * Bad, because unnecessary complexity and elevated detection risk.

#### Consequences
* **Positive**: Minimal attack surface, zero UI detection risk, fast and reliable execution.
* **Negative / Trade-offs**: Relies entirely on the backdoor API for both inspection and execution.
* **Confirmation**: Verified by inspecting that no outbound calls to the web panel occur in audit logs.

---

### Decision 4: Error Recovery & State Validation Strategy

#### Problem & Drivers
If any mutation fails due to invalid parameters, missing IDs, or transient network errors, calling `action: done` prematurely would result in mission failure.

#### Considered Options

##### Option 4.1: Dynamic Re-Query & Self-Correction Loop (ACCEPTED)
* **Description**: The agent inspects API response status codes and error messages. Upon failure, it re-queries the relevant resource or help documentation, adjusts parameters, and retries up to 3 times before deciding whether to proceed to `done`.
* **Data Engineering & Performance**: Minimal extra token cost on failure; bounded at 3 attempts to prevent infinite loops.
* **Cost & FinOps**: Cost-controlled through strict loop limits (`max_iterations=10`).
* **Security & Reliability**: Prevents premature mission failure while maintaining bounded execution.
* **Pros & Cons**:
  * Good, because resilient to minor parameter hallucinations or formatting differences.
  * Good, because verifies data state prior to final confirmation.
  * Trade-off: Requires prompt instructions guiding the agent through iterative correction.

##### Option 4.2: Strict Fail-Fast (REJECTED)
* **Description**: Instantly terminate execution upon the first non-200 or non-zero code response from the API.
* **Data Engineering & Performance**: Lowest token usage on failure.
* **Cost & FinOps**: Minimal cost.
* **Security & Reliability**: Brittle; a single transient failure causes the entire mission to fail.
* **Pros & Cons**:
  * Good, because prevents repetitive anomalous traffic.
  * Bad, because lacks autonomy and self-healing capability.

#### Consequences
* **Positive**: High first-run success rate and robust autonomy.
* **Negative / Trade-offs**: Agent prompt must instruct clear self-correction behavior.
* **Confirmation**: Unit tests with mocked API errors ensuring the agent handles error payloads gracefully.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
