<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-20
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S04E02 - Wind Turbine Autonomous Scheduling & Active Collaboration (`windpower`)

## 1. Context
The task `windpower` requires configuring an optimal and safe operating schedule for a newly acquired wind turbine to satisfy an energy deficit required to boot power plant control computers while protecting the turbine's rotor from destructive storms. The system faces an unforgiving operational constraint: due to an unchargeable backup battery, the turbine's hardware service window remains active for at most **40 seconds** after initialization. The architectural challenge lies in harmonizing **high agentic autonomy**—where the agent begins knowing only `action: "help"` and must autonomously explore and document the API surface—with **time-critical execution**, where linear turn-taking would breach the 40-second battery lifetime. The architectural fitness function is defined by closed-loop verification: the agent discovers all API capabilities, initiates the service window, gathers diagnostic telemetry via an asynchronous queuing interface, calculates feathering protection and power generation windows, fetches cryptographic unlock signatures, passes the hardware self-test (`turbinecheck`), submits bulk configuration, and verifies completion (`done`) to obtain the course flag `{FLG:...}` within 40 seconds.

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Baseline Standards & Stack | Adhere 100% to GEMINI.md Baseline | Guarantees consistency across Terraform, BigQuery telemetry streaming, Cloud Run, Gemini 3.8 Flash on Vertex AI, and dual framework parity (LangChain + Google ADK). |
| 2 | Agent Autonomy vs. Time Budget | Two-Phase Lifecycle: Autonomous Discovery followed by Time-Critical Execution | Enables full agentic discovery starting only with `help` in Phase 1 (unbounded time), transitioning cleanly to high-speed Phase 2 within the 40s battery constraint. |
| 3 | Network Egress & Workspace Storage | Route via cr-mcp-web-gateway & cr-mcp-workspace | Upholds Zero Direct Egress security pattern from BEST_PRACTICES.md, provides persistent session workspace notes, and guarantees local fallback resiliency. |
| 4 | Schedule Calculation & Signature Execution | Agent-Invoked Deterministic Python Solver Tool | Eliminates LLM arithmetic hallucinations and turn latency by delegating aerodynamic formulas, storm window selection, and batch signature polling to a dedicated deterministic tool. |
| 5 | Asynchronous Telemetry & Result Draining | Centralized Async Stream Demultiplexer | Non-blocking consumer loop continuously drains single-read `getResult` responses and routes them by `sourceFunction` into a structured state store. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Architectural Baseline & Standards Adherence

#### Problem & Drivers
The lesson task requires seamless integration into the repository's Google Cloud infrastructure (Terraform registration, BigQuery audit telemetry, Vertex AI IAM, and strict dual-framework support).

#### Considered Options

##### Option 1.1: Adhere 100% to GEMINI.md Baseline (ACCEPTED)
* **Description**: Scaffold and deploy a standard Cloud Run microservice `cr-s04e02-windpower` managed via Terraform in `terraform/variables.tf`, BigQuery dataset `s04e02` with streaming `audit` table, Gemini 3.8 Flash (`thinking_level="low"`) on Vertex AI (`global`), dual agent backends (LangChain `1.2.15` and Google ADK `1.33.0`), and Python 3.13.5 managed with `uv`.
* **Data Engineering & Performance**: Structured JSON event streaming to BigQuery via `af_aidevs.audit.bigquery`; fast cold starts with pinned dependencies.
* **Cost & FinOps**: Minimal compute allocation (1 CPU, 1Gi RAM, CPU idle enabled); Vertex AI low thinking level keeps token spend well within free-tier quotas.
* **Security & Reliability**: IAM Workload Identity authentication (`roles/aiplatform.user`, `roles/bigquery.dataEditor`); Zero-Trust secret management via Secret Manager and local `.env`.
* **Pros & Cons**:
  * Good, because it maintains complete feature, structural, and observability parity across all course lessons.
  * Good, because it fulfills Artur's educational mandate for both LangChain and Google ADK.
  * Trade-off: Requires scaffolding both LangChain and ADK agent implementations.

##### Option 1.2: Ad-Hoc Script Execution (REJECTED)
* **Description**: Standalone local Python script without BigQuery audit streaming or Cloud Run packaging.
* **Data Engineering & Performance**: Lacks auditable telemetry or queryable logs.
* **Cost & FinOps**: Negligible compute cost.
* **Security & Reliability**: Fragile execution without containerized lifecycle guarantees.
* **Pros & Cons**:
  * Good, because fast to hack together.
  * Bad, because violates repo standard architecture and prevents deployment.

#### Consequences
* **Positive**: Predictable CI/CD and container builds via `cloudbuild.yaml`, automated audit tracking in BigQuery dataset `s04e02`.
* **Negative / Trade-offs**: Container scaffolding overhead.
* **Confirmation**: Verified via `uv run pytest` tests, `curl.exe` health checks on `/health`, and BigQuery audit queries.

---

### Decision 2: Agent Autonomy vs. Time-Critical Execution Architecture

#### Problem & Drivers
Artur emphasized that the agent must be "let off the leash" to autonomously explore the API starting only with knowledge of `action: "help"`. However, the hardware service window (`start`) expires after 40 seconds. If an agent attempts sequential, turn-by-turn interactive reasoning during the 40-second window, inference latencies (1.5–2.5s per turn $\times$ 10–12 turns) and network hops will cause battery depletion and task failure.

#### Considered Options

##### Option 2.1: Two-Phase Lifecycle: Autonomous Discovery $\rightarrow$ Time-Critical Execution (ACCEPTED)
* **Description**:
  - **Phase 1 (Pre-Flight Autonomous Discovery - Unbounded Time, Fully Asynchronous)**: The agent starts with zero hardcoded knowledge of endpoints except `action: "help"`. Using a flexible asynchronous introspection tool `probe_windpower_api(action, params)` implemented with `httpx.AsyncClient`, the agent can issue single or **parallel tool calls** in a single reasoning step. Gemini 3.8 Flash natively outputs multiple tool invocations simultaneously, and both LangChain (`1.2.15`) and Google ADK (`1.33.0`) execute these calls concurrently via `asyncio.gather`. The agent calls `help`, reads the returned documentation, discovers `get: documentation`, retrieves technical parameters (feathering angles, wind speed limits, power formulas), probes auxiliary capabilities in parallel, and records this knowledge into context and workspace notes without blocking the event loop.
  - **Phase 2 (Time-Critical Execution - 40s Budget)**: Armed with the exact discovered rules, the agent initiates the execution phase by invoking the deterministic solver and execution tool (`solve_and_execute_windpower`), or executing the coordinated sequence within the service window.
* **Data Engineering & Performance**: Separates unbounded exploratory reasoning from hard-real-time execution; zero latency risk during discovery; non-blocking asynchronous I/O with parallel tool dispatch.
* **Cost & FinOps**: Highly efficient token usage; the LLM reasons freely during Phase 1 without risking battery timeout.
* **Security & Reliability**: Eliminates timeout failures caused by LLM latency while maintaining 100% genuine agentic learning and discovery.
* **Pros & Cons**:
  * Good, because fully satisfies Artur's requirement to let the agent discover and document the API autonomously.
  * Good, because supports concurrent asynchronous probing (parallel tool calling via `asyncio.gather`).
  * Good, because guarantees execution within the strict 40-second hardware window.
  * Good, because adapts dynamically if Centrala's documentation or parameters change.
  * Trade-off: Requires designing tool boundaries separating discovery from composite execution.

##### Option 2.2: Pure Turn-by-Turn ReAct Loop during Service Window (REJECTED)
* **Description**: The agent triggers `start` and performs every subsequent queue, poll, calculation, signing, and submission step through individual turn-by-turn LLM tool invocations.
* **Data Engineering & Performance**: Extreme latency; 10+ LLM turns easily exceed the 40-second ceiling.
* **Cost & FinOps**: High token consumption due to repeated polling messages in the prompt history.
* **Security & Reliability**: High failure rate; transient network spikes or model hesitation lead directly to battery depletion.
* **Pros & Cons**:
  * Good, because pure theoretical agent autonomy.
  * Bad, because practically guaranteed to fail the 40-second physical deadline.

#### Consequences
* **Positive**: Perfect balance of agentic discovery and production-grade reliability.
* **Negative / Trade-offs**: The agent system prompt must clearly distinguish between pre-flight discovery and live-service execution.
* **Confirmation**: Integration tests asserting that Phase 1 extracts full documentation, followed by Phase 2 completing in $<15$ seconds total elapsed time.

---

### Decision 3: Network Egress & Workspace Storage via MCP Gateway & Workspace

#### Problem & Drivers
According to the **Zero Direct Egress** architectural pattern recorded in `BEST_PRACTICES.md`, microservices should route external network calls through an auditable egress proxy (`cr-mcp-web-gateway`) and persist session artifacts to a centralized storage service (`cr-mcp-workspace`). Direct `httpx` egress risks unmanaged rate limits and lacks centralized egress telemetry.

#### Considered Options

##### Option 3.1: Route via cr-mcp-web-gateway & cr-mcp-workspace with Local Resilient Fallbacks (ACCEPTED)
* **Description**: Implement `services/mcp_service.py` to route all Centrala API POST requests (`help`, `get`, `config`, `done`) through `cr-mcp-web-gateway` (`post_web_resource`) and persist discovered documentation and runtime logs to `cr-mcp-workspace` (`write_file`, `read_file`). When running in local test environments without remote MCP container availability, the service automatically falls back to direct `httpx.AsyncClient` and local disk paths (`/tmp/af_aidevs_workspace`).
* **Data Engineering & Performance**: Centralized egress telemetry, automatic rate limit retry (`CentralaRateLimitError` / HTTP 429), and non-blocking async execution.
* **Cost & FinOps**: Negligible latency overhead (~20ms per intra-region VPC hop); complies with GCP internal egress quotas.
* **Security & Reliability**: Strict adherence to Zero Direct Egress; prevents API key leakage; resilient fallbacks ensure local offline development never blocks CI/CD.
* **Pros & Cons**:
  * Good, because maintains complete architectural harmony with `s04e01` and `BEST_PRACTICES.md`.
  * Good, because provides persistent workspace file storage for agent discovery notes.
  * Good, because resilient fallback enables seamless local CLI and automated testing.
  * Trade-off: Additional MCP client integration layer.

##### Option 3.2: Direct httpx Only without MCP Gateway (REJECTED)
* **Description**: Microservice communicates directly with `$AIDEVS_VERIFY` using standalone `httpx` client without gateway abstraction.
* **Data Engineering & Performance**: Bypasses centralized egress proxy and audit logs.
* **Cost & FinOps**: Saves minimal Cloud Run invocations.
* **Security & Reliability**: Violates repo Zero Direct Egress rule.
* **Pros & Cons**:
  * Good, because marginally simpler code.
  * Bad, because violates established enterprise security architecture.

#### Consequences
* **Positive**: 100% compliance with repo security standards, unified rate limit handling, and persistent workspace storage.
* **Negative / Trade-offs**: Requires wiring `MCP_WEB_GATEWAY_URL` and `MCP_WORKSPACE_URL` environment variables.
* **Confirmation**: Integration tests asserting calls pass through `MCPService` with local fallback verified.

---

### Decision 4: Schedule Calculation & Signature Execution Strategy

#### Problem & Drivers
Configuring the turbine requires: (1) calculating storm feathering for all hours where predicted wind exceeds the turbine's physical limit, (2) finding the earliest hour fulfilling the power plant's deficit, (3) requesting cryptographic unlock signatures via `unlockCodeGenerator` for each configuration point, (4) performing `turbinecheck`, and (5) transmitting bulk configurations. LLMs are notoriously prone to arithmetic mistakes in tabular data and cannot perform fast concurrent MD5/token polling.

#### Considered Options

##### Option 4.1: Agent-Invoked Deterministic Python Solver Tool (ACCEPTED)
* **Description**: Equip the agent with a dedicated tool: `solve_and_execute_windpower(discovery_metadata: dict | None)`. The tool carries out the mathematical evaluation (threshold filtering, formula-based pitch angle selection), concurrently queues `unlockCodeGenerator` for all timestamps, collects signatures, runs `turbinecheck`, and sends the batch `config` payload and final `done` signal in a single high-performance routine.
* **Data Engineering & Performance**: Sub-millisecond mathematical calculations; concurrent async I/O completes entire execution in 4–8 seconds total.
* **Cost & FinOps**: Zero LLM tokens spent on raw numerical calculations or repetitive signature polling.
* **Security & Reliability**: 100% mathematical precision; zero risk of off-by-one errors in timestamp formatting or angle calculations.
* **Pros & Cons**:
  * Good, because satisfies Artur's specific instruction: *"I believe LLM should have a tool for deterministic exact python solver"*.
  * Good, because completely eliminates calculation hallucination.
  * Trade-off: Core aerodynamic formulas and signing loops reside in the deterministic service layer.

##### Option 4.2: LLM In-Context Mathematical Reasoning (REJECTED)
* **Description**: The LLM parses raw tabular forecast data and power deficits in context, manually computes the production window and feathering angles, and calls individual tools.
* **Data Engineering & Performance**: Consumes significant context tokens and inference time.
* **Cost & FinOps**: High token cost for multi-step numerical reasoning.
* **Security & Reliability**: High risk of arithmetic hallucination or missing consecutive storm hours.
* **Pros & Cons**:
  * Good, because relies entirely on model intelligence.
  * Bad, because slow, costly, and error-prone on numerical matrices under time pressure.

#### Consequences
* **Positive**: Lightning-fast execution, zero arithmetic errors, reliable bulk configuration submission.
* **Negative / Trade-offs**: Solver logic must be cleanly modularized and tested with mocked Centrala data.
* **Confirmation**: Pytest suite verifying aerodynamic calculations, storm window detection, and signature dispatch against test fixtures.

---

### Decision 5: Asynchronous Telemetry & Result Draining Pattern

#### Problem & Drivers
Centrala's API returns queued results via `action: "getResult"` in non-deterministic order, and each result is removed from the queue upon retrieval (single-read constraint). If multiple callers poll independently, reports could be dropped or cross-contaminated.

#### Considered Options

##### Option 5.1: Centralized Async Stream Demultiplexer (ACCEPTED)
* **Description**: Implement an asynchronous drainer loop in `services/windpower_service.py` that continuously polls `getResult` with a brief backoff (e.g. 100ms) until all expected results (identified by `sourceFunction`) are gathered or an internal timeout (e.g. 20s) is reached.
* **Data Engineering & Performance**: Minimizes polling latency; collects all asynchronous responses in parallel without blocking.
* **Cost & FinOps**: Negligible compute overhead.
* **Security & Reliability**: Prevents race conditions and guarantees that single-read reports are safely routed to their corresponding handlers.
* **Pros & Cons**:
  * Good, because robustly handles random arrival order and queue clearing.
  * Good, because isolates queue polling complexity from agent reasoning.
  * Trade-off: Requires tracking outstanding request IDs/source functions.

##### Option 4.2: Ad-Hoc On-Demand Polling (REJECTED)
* **Description**: Each tool call independently triggers `getResult` when it expects an answer, buffering unexpected messages in a global dictionary.
* **Data Engineering & Performance**: Complicated state management across fragmented tool executions.
* **Cost & FinOps**: Similar compute footprint.
* **Security & Reliability**: High risk of dropped messages, deadlocks, or race conditions.
* **Pros & Cons**:
  * Good, because conceptually decentralized.
  * Bad, because error-prone and hard to debug under time constraints.

#### Consequences
* **Positive**: Clean, predictable ingestion of weather, turbine status, power plant requirements, and unlock codes.
* **Negative / Trade-offs**: Requires a central demultiplexing collector function.
* **Confirmation**: Unit tests with mocked out-of-order queue responses verifying correct demultiplexing and state assembly.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
