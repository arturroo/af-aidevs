<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-14
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S03E03 Reactor Navigation (`cr-s03e03-reactor`)

## 1. Context
Following the stabilization and verification of the emergency cooling software in S03E02, the physical cooling controller module must be mounted in slot `G` (Column 7, Row 5) of the reactor chamber. The 7x5 chamber floor is subject to lethal radiation levels and contains vertically oscillating reactor core blocks (`B`) that cycle up and down with each command. The system is governed by a turn-based HTTP verification API (`$AIDEVS_API_VERIFY`) accepting discrete commands (`start`, `reset`, `right`, `left`, `wait`). The fitness function and terminal condition for the autonomous system is safely navigating the transport robot from starting position `P` (Column 1, Row 5) to target slot `G` without collisions, securing the course completion flag (`{FLG:...}`).

---

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Navigation & Pathfinding Engine | Hybrid Architecture: LLM Agent with Kinematic Pathfinding Tool | Combines deterministic State-Space BFS simulation (guaranteeing mathematically safe, collision-free moves) with agentic supervisory feedback and step execution. |
| 2 | Collision Guardrail & Pre-Flight Validation | Client-Side Kinematic Safety Guardrail | Evaluates block kinematics and enforces safe move constraints at step `t+1` before HTTP dispatch, preventing robot destruction and wasted budget. |
| 3 | Failure Recovery & Deadlock Handling | Autonomous Recovery Loop with Capped Resets | Automatically triggers the `reset` command upon unexpected state desynchronization or deadlock, rebuilding trajectory state up to 3 retry attempts. |
| 4 | Agent Framework & Architecture Baseline | Dual Framework Parity (LangChain 1.2.15 & Google ADK 1.33.0) with Gemini 3.8 Flash | Fully satisfies `GEMINI.md` architectural baseline standards, providing microservice, CLI mode, and BigQuery telemetry parity across frameworks. |
| 5 | Egress Architecture & Shared Package Integration | Zero-Trust Egress via `cr-mcp-web-gateway` and Artifact Registry `af-aidevs` Package | Eliminates direct container egress by routing all verification and reactor API calls through `cr-mcp-web-gateway`, adhering to Google Zero-Trust standards and using the central `af_aidevs` shared package. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Navigation & Pathfinding Engine

#### Problem & Drivers
The reactor floor consists of a 7x5 discrete grid where vertical obstacles (`B`) move 1 cell per issued command in a periodic oscillation. Relying purely on raw prompt-based token generation for temporal-spatial trajectory calculations risks spatial hallucinations, collisions, and budget waste. Conversely, a completely non-agentic script lacks adaptability to unexpected API feedback or course telemetry requirements.

#### Considered Options

##### Option 1.1: Hybrid Architecture — LLM Agent with Kinematic Pathfinding Tool (ACCEPTED)
* **Description**: The agent operates as a supervisory coordinator equipped with a deterministic pathfinding tool (`calculate_safe_path` or `get_next_safe_action`). The tool executes a State-Space Breadth-First Search (BFS) / A* lookahead over dynamic state `(col, row, time_step % cycle_period)` to evaluate guaranteed collision-free move sequences (`right`, `wait`, `left`), which the agent dispatches and monitors.
* **Data Engineering & Performance**: Negligible compute latency (<5ms for a 7x5 state space); zero token bloat from iterative spatial recalculations.
* **Cost & FinOps**: Highly token-efficient; agent requires minimal turns to execute the optimal trajectory.
* **Security & Reliability**: 100% mathematical guarantee against spatial reasoning errors; provides explainable audit trails.
* **Pros & Cons**:
  * Good, because it eliminates LLM arithmetic/spatial hallucinations while maintaining full agentic interface and reasoning auditability.
  * Bad / Trade-off, because it requires implementing a discrete simulation model of the reactor grid kinematics.

##### Option 1.2: Pure Agentic Step-by-Step ReAct Loop (REJECTED)
* **Description**: On each turn, the raw ASCII board map and block directions are injected into the LLM context prompt, and the model selects `right`, `wait`, or `left` via pure reasoning.
* **Data Engineering & Performance**: High latency (1 LLM call per robot step); high token consumption per run.
* **Cost & FinOps**: Significantly higher Vertex AI inference cost across 10-20 discrete steps.
* **Security & Reliability**: Prone to spatial-temporal hallucinations, misinterpreting cyclic block velocity, and colliding with descending obstacles.
* **Pros & Cons**:
  * Good, because it requires no specialized local pathfinding code.
  * Bad, because probabilistic language models are inherently unreliable for strict multi-step kinematic obstacle avoidance.

#### Consequences
* **Positive**: Deterministic traversal with zero collision risk and rapid completion time.
* **Negative / Trade-offs**: Requires implementing the grid dynamics and kinematic simulator in `services/pathfinding_service.py`.
* **Confirmation**: Unit tests asserting path optimality and zero collisions across varied initial block positions and cycle phases.

---

### Decision 2: Collision Guardrail & Pre-Flight Validation

#### Problem & Drivers
The mission rules emphasize: "postaraj się to zrobić raz a dobrze" (avoid wasting budget on destroyed robots). If an errant command is submitted that places the robot in a cell occupied by or moving into a block at step `t+1`, the robot is destroyed immediately.

#### Considered Options

##### Option 2.1: Client-Side Kinematic Safety Guardrail (ACCEPTED)
* **Description**: A dedicated validation interceptor (`services/safety_guardrail.py`) verifies every outgoing command against the known block positions and velocities projected forward by 1 step. If a proposed command would result in a collision, the guardrail rejects the action locally with a descriptive explanation, forcing an alternative safe action (`wait` or `left`).
* **Data Engineering & Performance**: Microsecond verification overhead before HTTP request dispatch.
* **Cost & FinOps**: Zero wasted turns from API-level robot death and reset penalties.
* **Security & Reliability**: Hard architectural barrier preventing accidental robot destruction.
* **Pros & Cons**:
  * Good, because it acts as an absolute defensive safety net between the decision engine and the remote verification API.
  * Bad / Trade-off, because the guardrail must accurately maintain the discrete block kinematic cycle.

##### Option 2.2: Optimistic Execution with Post-Mortem Handling (REJECTED)
* **Description**: Directly send whatever command is produced to `$AIDEVS_API_VERIFY` and only react if the API returns a collision message.
* **Data Engineering & Performance**: Increases network traffic and triggers unnecessary reset cycles.
* **Cost & FinOps**: Violates the course budget constraint and wastes round-trip API calls.
* **Security & Reliability**: Weak reliability; allows avoidable robot destruction.
* **Pros & Cons**:
  * Good, because no client-side move validation logic is needed.
  * Bad, because it breaches the zero-waste engineering principle and fails cleanly on first attempt.

#### Consequences
* **Positive**: Absolute protection against catastrophic collision commands.
* **Negative / Trade-offs**: Synchronization between API board telemetry and local kinematic model must be strictly tested.
* **Confirmation**: Automated unit tests testing edge collision scenarios (e.g. attempting to step under a descending block).

---

### Decision 3: Failure Recovery & Deadlock Handling

#### Problem & Drivers
Transient network disconnects, server resets, or edge-case state desynchronizations could leave the robot in an invalid state. The system must autonomously recover without requiring human intervention, while avoiding infinite loops.

#### Considered Options

##### Option 3.1: Autonomous Recovery Loop with Capped Resets (ACCEPTED)
* **Description**: An automated recovery policy in the execution controller. If a collision is reported by the API or a state deadlock is detected, the service automatically sends a `reset` command, flushes step history, resynchronizes the initial board configuration, and recomputes the optimal path. The reset budget is strictly capped at 3 attempts before raising an explicit task failure exception.
* **Data Engineering & Performance**: Clean state boundary; logs all reset events to BigQuery audit telemetry.
* **Cost & FinOps**: Bounds worst-case execution cost and avoids infinite API retry storms.
* **Security & Reliability**: Ensures high operational autonomy and resilience against transient state drift.
* **Pros & Cons**:
  * Good, because it enables autonomous self-healing within a controlled budget cap.
  * Bad / Trade-off, because state re-synchronization requires re-invoking the pathfinding sequence.

##### Option 3.2: Immediate Fail-Fast Termination (REJECTED)
* **Description**: The service immediately halts and raises an exception upon any error or unexpected response.
* **Data Engineering & Performance**: Minimal code complexity.
* **Cost & FinOps**: Low cost per run, but requires manual intervention to restart.
* **Security & Reliability**: Fragile; cannot handle transient API synchronization glitches.
* **Pros & Cons**:
  * Good, because it prevents repeated retries.
  * Bad, because it requires manual human intervention for recoverable transient issues.

#### Consequences
* **Positive**: Resilient, self-healing execution capable of overcoming intermittent environment anomalies.
* **Negative / Trade-offs**: Recovery logic must be carefully bounded with loop guards.
* **Confirmation**: Mock tests verifying recovery after simulated API errors or reset triggers.

---

### Decision 4: Agent Framework & Architecture Baseline

#### Problem & Drivers
`GEMINI.md` mandates 100% adherence to repository architectural baselines: dual framework support (LangChain 1.2.15 and Google ADK 1.33.0), Gemini 3.8 Flash (`gemini-3.8-flash`) on Vertex AI, Cloud Run container microservice (`cr-s03e03-reactor`), BigQuery telemetry streaming dataset (`s03e03`), and `uv` package management.

#### Considered Options

##### Option 4.1: Dual Framework Parity (LangChain 1.2.15 & Google ADK 1.33.0) (ACCEPTED)
* **Description**: Standard microservice layout under `cr-s03e03-reactor/`:
  - `main.py` with FastAPI endpoints (`GET /health`, `GET /`, `POST /run`) and CLI entrypoint (`--backend langchain|adk`).
  - `agents/langchain_agent.py` using `create_agent` from `langchain.agents` and `ChatVertexAI(model="gemini-3.8-flash")`.
  - `agents/adk_agent.py` using `google.adk.Agent` and `Runner` with `InMemorySessionService`.
  - `services/audit_service.py` integrating BigQuery streaming to dataset `s03e03`.
  - Container manifests (`Dockerfile`, `.dockerignore`, `.gcloudignore`, `cloudbuild.yaml`).
* **Data Engineering & Performance**: Complete real-time audit streaming; zero-drift container scaffolding.
* **Cost & FinOps**: Serverless Cloud Run scale-to-zero; Gemini 3.8 Flash low-latency inference.
* **Security & Reliability**: Zero hardcoded URLs; all credentials passed via Secret Manager / `.env`.
* **Pros & Cons**:
  * Good, because it provides 100% baseline compliance, production readiness, and architectural consistency.
  * Bad / Trade-off, because dual framework parity requires maintaining both agent runners.

##### Option 4.2: Single Framework Prototype (REJECTED)
* **Description**: Implementing only LangChain or only a standalone Python script without Cloud Run or BigQuery.
* **Data Engineering & Performance**: Incomplete telemetry; lacks standardized logging.
* **Cost & FinOps**: No container footprint, but violates course standards.
* **Security & Reliability**: Non-compliant with repository engineering standards.
* **Pros & Cons**:
  * Good, because fewer files to scaffold.
  * Bad, because it violates core `GEMINI.md` mandatory requirements.

#### Consequences
* **Positive**: Complete compliance with Google engineering standards and the AI_Devs course roadmap.
* **Negative / Trade-offs**: Scaffolding standard repository modules.
* **Confirmation**: Health check and CLI verification for both backends (`--backend langchain` and `--backend adk`).

---

### Decision 5: Egress Architecture & Shared Package Integration

#### Problem & Drivers
The task requires sending commands to and receiving telemetry from `$AIDEVS_API_VERIFY`. Direct egress from task containers is an architectural anti-pattern violating Google Cloud Zero-Trust network guidelines. Furthermore, reimplementing MCP wrappers locally creates code duplication and cold-start drift.

#### Considered Options

##### Option 5.1: Zero-Trust Egress via `cr-mcp-web-gateway` and Artifact Registry `af-aidevs` (ACCEPTED)
* **Description**: The service container has zero direct public egress routes for course APIs. All HTTP POST operations to `$AIDEVS_API_VERIFY` are routed through `cr-mcp-web-gateway.post_web_resource` using the centralized `af-aidevs` package from Artifact Registry (`af_aidevs.clients.mcp`). Workspace operations (such as saving `run_notes.txt`) are managed via `cr-mcp-workspace`.
* **Data Engineering & Performance**: Centralized telemetry, consistent request/response schema serialization, and persistent session artifact storage in GCS.
* **Cost & FinOps**: Leverages shared container infrastructure and cached Google OIDC tokens.
* **Security & Reliability**: Strictly adheres to Zero-Trust egress isolation; eliminates raw credential/endpoint exposure across task containers.
* **Pros & Cons**:
  * Good, because it enforces 100% Zero-Trust network isolation and standardizes MCP integration across all course microservices.
  * Bad / Trade-off, because it introduces a network hop to `cr-mcp-web-gateway` over internal Cloud Run invoker authentication.

##### Option 5.2: Direct Container Egress via Raw `httpx` (REJECTED)
* **Description**: Microservice directly executes HTTP POST requests to `$AIDEVS_API_VERIFY` using local `httpx` client.
* **Data Engineering & Performance**: Bypasses central gateway telemetry and workspace integration.
* **Cost & FinOps**: No gateway hop, but violates repository architectural patterns.
* **Security & Reliability**: Anti-pattern: direct public egress from worker containers increases blast radius and duplicates network resilience code.
* **Pros & Cons**:
  * Good, because it is marginally simpler to write.
  * Bad, because it constitutes direct container egress anti-pattern and violates repository-wide MCP gateway standards.

#### Consequences
* **Positive**: Complete network isolation, centralized egress auditing, and zero code duplication via Artifact Registry.
* **Negative / Trade-offs**: Requires setting `UV_INDEX_GAR_USERNAME` and `UV_INDEX_GAR_PASSWORD` for local dependency resolution.
* **Confirmation**: Verification that outgoing requests to `$AIDEVS_API_VERIFY` pass strictly through `cr-mcp-web-gateway`.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None. 100% alignment with `GEMINI.md` baseline standards.

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Pre-Flight Agent Readiness & Security Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
