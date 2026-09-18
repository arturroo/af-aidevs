<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-17
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S03E05 Savethem Autonomous Routing (`cr-s03e05-savethem`)

## 1. Context
Following the tragic destruction of the first contact city due to radio transmission leakage in S03E05 (`savethem`), direct automated negotiations are banned. The resistance must deploy a human envoy across a hazardous 10x10 terrain grid to reach the survivor enclave of Skolwin. The envoy operates under strict resource limits: exactly 10 food rations and 10 fuel units, with a choice of base vehicles and the option to proceed on foot. To plan the expedition, the autonomous agent is provided solely with an external toolsearch endpoint (`$AIDEVS_API_TOOLSEARCH`), whose discovered tools return at most 3 items per query and operate strictly in English. The architectural fitness function is autonomous tool discovery, knowledge grounding via MCP services, mathematical route optimization, and submission of the itinerary to `$AIDEVS_API_VERIFY` securing the course flag (`{FLG:...}`).

---

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Infrastructure & Engineering Baseline | Full Compliance with `GEMINI.md` (`cr-s03e05-savethem`, Gemini 3.8 Flash, BigQuery `s03e05.audit`, dual LangChain + Google ADK) | Guarantees zero architectural drift, enterprise telemetry, dual framework educational parity, and reproducible Cloud Run deployments. |
| 2 | Dynamic Tool Discovery & Agent Reasoning Topology | Fully Autonomous Meta-Tool Agent with Progressive Disclosure | Equips the LLM with `toolsearch` and a generic `invoke_remote_tool` meta-tool, enabling dynamic discovery, inspection, and reasoning without static hardcoding. |
| 3 | Route Planning & Terrain Navigation Engine | Hybrid Deterministic A* / Dijkstra State-Space Search | Separates heuristic discovery from mathematical route solving, completely eliminating LLM coordinate hallucination and guaranteeing provably optimal paths within resource budgets. |
| 4 | Vehicle Selection & Foot Travel Evaluation | Multi-State Graph Expansion `(x, y, vehicle_mode, fuel, food)` | Allows the pathfinding engine to evaluate multimodal transitions (e.g. driving across roads/plains, abandoning vehicle to cross rough terrain on foot) within a single unified search graph. |
| 5 | Telemetry, Workspace Persistence & Egress Gateway | MCP Session Workspace (`cr-mcp-workspace`) + Web Gateway (`cr-mcp-web-gateway`) + Hierarchical Markdown Logging | Conforms to Zero Direct Egress security, routes all external HTTP traffic via MCP Web Gateway, and stores discovered tool specifications, map layouts, and timestamped query responses as structured markdown in GCS. |
| 6 | Semantic Ingestion vs. Hardcoded Fallbacks | Agent-Driven Semantic Parameterization with Zero Heuristic Fallbacks (Accepted) | Leverages LLM semantic reasoning to extract entities (vehicles, costs, coordinates) from unstructured or shifting tool responses and pass them directly to the solver, completely eliminating brittle regex parsers and code-bypass fallbacks. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Infrastructure & Engineering Baseline Alignment

#### Problem & Drivers
The solution requires standard cloud deployment, audit logging, dual-framework compatibility (LangChain & Google ADK), and strict dependency management in accordance with the course repository principles.

#### Considered Options

##### Option 1.1: Full Compliance with `GEMINI.md` Baseline (ACCEPTED)
* **Description**:
  - Deployable Cloud Run microservice `cr-s03e05-savethem` on Python `3.13.5` with container scaffolding (`Dockerfile`, `.dockerignore`, `.gcloudignore`, `cloudbuild.yaml`).
  - LLM: **Gemini 3.8 Flash** (`gemini-3.8-flash`) on Vertex AI with `thinking_level="low"`.
  - BigQuery Audit Dataset: `af-aidevs.s03e05.audit` streaming structured telemetry via `af_aidevs.audit.bigquery`.
  - Dual Framework Parity: CLI switch `--backend [langchain|adk]` implementing both LangChain `1.2.15` (`create_agent`) and Google ADK `1.33.0` (`Agent` + `Runner`).
  - Terraform registration in `terraform/variables.tf`.
* **Data Engineering & Performance**: Zero-overhead BigQuery streaming callback; fast container cold starts using Python 3.13.5 slim and UV package resolution.
* **Cost & FinOps**: Vertex AI Gemini 3.8 Flash low-thinking minimizes input/output token expenditure; Cloud Run scales to zero.
* **Security & Reliability**: Service account IAM (`sa-cr-s03e05-savethem`), Model Armor prompt sanitization, no hardcoded secrets or URLs.
* **Pros & Cons**:
  * Good, 100% consistent with repository patterns and continuous integration pipeline.
  * Bad / Trade-off, requires implementing dual agent backends with feature parity.

##### Option 1.2: Ad-Hoc Scripting with Single Framework (REJECTED)
* **Description**: Standalone Python script running solely LangChain or pure requests.
* **Reason for Rejection**: Violates dual framework standard and Cloud Run microservice deployment requirements.

#### Consequences
* **Positive**: Production-ready microservice ready for Cloud Run and Terraform deployment.
* **Negative / Trade-offs**: Dual backend maintenance.
* **Confirmation**: Verified via unit tests, BigQuery audit log streaming, and container build checks.

---

### Decision 2: Dynamic Tool Discovery & Agent Reasoning Topology

#### Problem & Drivers
Operational tools (maps, terrain rules, vehicle specs) are not pre-configured. Centrala provides only `$AIDEVS_API_TOOLSEARCH`. Discovered tools accept `{"apikey": "...", "query": "..."}`, return at most 3 items per call, and communicate strictly in English.

#### Considered Options

##### Option 2.1: Fully Autonomous Meta-Tool Agent with Progressive Disclosure (ACCEPTED)
* **Description**:
  The agent is equipped with two core meta-tools:
  1. `search_tools(query: str, reasoning: str) -> SearchToolsResponse`: Calls `$AIDEVS_API_TOOLSEARCH` to discover relevant tools and endpoints.
  2. `invoke_remote_tool(endpoint_url: str, query: str, tool_name: str, reasoning: str) -> RemoteToolResponse`: Sends targeted English queries to any discovered tool.
  As tools are discovered, their API specs, parameter guidance, and capabilities are written as markdown files to the session workspace (`cr-mcp-workspace`). The agent reads and inspects these specifications progressively, constructing targeted follow-up queries.
* **Data Engineering & Performance**: Minimizes prompt bloat by loading tool specifications on demand rather than pre-stuffing entire schemas into system prompts.
* **Cost & FinOps**: Targeted English queries avoid wasteful conversational cycles; top-3 retrieval is handled deliberately.
* **Security & Reliability**: Centralized validation of tool URLs; prevents prompt injection from untrusted external tool responses.
* **Pros & Cons**:
  * Good, true autonomous meta-agent behavior as highlighted in the lesson theme (nondeterministic reasoning as an advantage).
  * Good, accommodates arbitrary tool additions or schema nuances without code changes.
  * Bad / Trade-off, requires robust error handling if the agent formulates vague queries.

##### Option 2.2: Two-Phase Discovery & Static Dynamic Registration (REJECTED)
* **Description**: A pre-flight phase queries `toolsearch` programmatically to discover tools, then registers distinct LangChain/ADK tool wrappers before handing off to the agent.
* **Reason for Rejection**: Less dynamic; restricts agent autonomy in refining search queries if unexpected tools emerge.

#### Consequences
* **Positive**: High flexibility; agent autonomously formulates queries to uncover all vehicles, rules, and terrain features.
* **Negative / Trade-offs**: LLM must understand how to chain `search_tools` and `invoke_remote_tool`.
* **Confirmation**: Logged execution traces in BigQuery audit tables and LangSmith showing progressive discovery.

---

### Decision 3: Route Planning & Terrain Navigation Engine

#### Problem & Drivers
Navigating a 10x10 grid with varied obstacles (rivers, trees, rocks) and strict resource caps (10 food, 10 fuel) requires error-free calculation. LLMs frequently hallucinate coordinates, miss boundary collisions, or calculate resource subtraction inaccurately.

#### Considered Options

##### Option 3.1: Hybrid Deterministic A* / Dijkstra State-Space Search (ACCEPTED)
* **Description**:
  The LLM agent focuses on semantic discovery: querying tools, gathering map tiles, identifying start/destination coordinates, and extracting vehicle/terrain physics into structured Pydantic data structures (`TerrainMap`, `VehicleSpec`). Once structured data is compiled, the agent invokes a local deterministic pathfinding solver (`solve_optimal_route`) implementing A* / Dijkstra state-space search. The solver guarantees finding the mathematically optimal, collision-free route that arrives at Skolwin with positive resource balances.
* **Data Engineering & Performance**: Sub-millisecond execution time ($<5\text{ ms}$) on 10x10 grids; zero token usage for path combinatorial search.
* **Cost & FinOps**: $0 inference cost for the pathfinding step.
* **Security & Reliability**: 100% mathematical guarantee against obstacle collisions, out-of-bounds moves, or resource exhaustion.
* **Pros & Cons**:
  * Good, eliminates coordinate hallucinations and arithmetic errors.
  * Good, deterministic reproducibility and fast unit testing.
  * Bad / Trade-off, requires parsing the retrieved map into a structured 2D grid matrix.

##### Option 3.2: Pure LLM Path Generation with Local Simulation Guardrail (REJECTED)
* **Description**: Gemini 3.8 Flash generates the step-by-step direction array directly from ASCII map prompts, with a Python guardrail retrying upon constraint violations.
* **Reason for Rejection**: LLMs struggle with multi-constraint spatial pathfinding on 10x10 grids; leads to high token consumption and unpredictable retries.

#### Consequences
* **Positive**: Absolute reliability and immediate verification success.
* **Negative / Trade-offs**: Need clean regex/parsing to convert external tool map outputs into structured grid arrays.
* **Confirmation**: Unit tests with mock maps, obstacle matrices, and resource counters.

---

### Decision 4: Vehicle Selection & Foot Travel Evaluation

#### Problem & Drivers
The envoy can choose from multiple vehicles at the base, each with differing speeds, fuel burns, and food burns. Crucially, the envoy can abandon the vehicle at any tile and proceed on foot (consuming 0 fuel, but more food).

#### Considered Options

##### Option 4.1: Multi-State Graph Expansion `(x, y, mode, fuel, food)` (ACCEPTED)
* **Description**:
  The graph search state is modeled as a tuple:
  $$\text{State} = (x, y, \text{mode}, \text{fuel}, \text{food})$$
  where $\text{mode} \in \{\text{vehicle}_1, \ldots, \text{vehicle}_k, \text{foot}\}$.
  Transitions allow:
  1. Moving to an adjacent valid tile $(x', y')$ in the current mode, deducting mode-specific fuel and food costs.
  2. Transitioning mode from $\text{vehicle} \to \text{foot}$ at the current tile (a one-way irreversible transition).
  The cost function prioritizes reaching the destination while maximizing remaining resources or minimizing total time/steps.
* **Data Engineering & Performance**: Expands state space to at most $10 \times 10 \times (V + 1) \times 11 \times 11 \approx 60,000$ states, solved via priority queue in $<20\text{ ms}$.
* **Cost & FinOps**: Negligible compute overhead.
* **Security & Reliability**: Discovers hybrid strategies that single-mode algorithms would miss (e.g. driving across open fields, then walking around obstacles or when fuel runs out).
* **Pros & Cons**:
  * Good, provably finds the globally optimal travel strategy across all vehicles and foot combinations.
  * Bad / Trade-off, slightly higher graph modeling complexity than checking vehicles independently.

##### Option 4.2: Single Vehicle Evaluation (Independent Runs) (REJECTED)
* **Description**: Run pathfinding separately for each vehicle end-to-end, and once for pure foot travel, selecting the best single vehicle.
* **Reason for Rejection**: Cannot discover optimal mixed strategies where driving followed by walking is necessary to bypass fuel exhaustion.

#### Consequences
* **Positive**: Optimal solution guaranteed even under complex multi-terrain constraints.
* **Negative / Trade-offs**: Requires formalizing the transition rules in the solver.
* **Confirmation**: Comprehensive pytest test suite validating edge cases (e.g. running out of fuel right before the goal and walking the last steps).

---

### Decision 5: Telemetry, Workspace Persistence & Egress Gateway

#### Problem & Drivers
In accordance with `GEMINI.md`, direct container egress is restricted. Agent session artifacts, task notes, and discovered tool specifications must be preserved across turns in an auditable, centralized storage environment (`cr-mcp-workspace`), while outbound HTTP traffic must flow through `cr-mcp-web-gateway`.

#### Considered Options

##### Option 5.1: MCP Session Workspace + Web Gateway + Hierarchical Markdown Persistence (ACCEPTED)
* **Description**:
  1. **Egress Gateway**: All HTTP requests to `$AIDEVS_API_TOOLSEARCH`, discovered tools, and `$AIDEVS_API_VERIFY` are routed through `cr-mcp-web-gateway` (`MCP_WEB_GATEWAY_URL`) using the standard MCP client from `af_aidevs.clients.mcp`.
  2. **Session Persistence**: Session notes, discovered tool specifications, map topology, and vehicle dossiers are stored in `cr-mcp-workspace` (`MCP_WORKSPACE_URL`) under `sessions/{session_id}/`.
  3. **Hierarchical Tool Result Logging**: Raw responses from external tools are saved to the workspace as:
     `sessions/{session_id}/tools/{tool_name}/{timestamp}_{query_slug}.md`
     containing query metadata, raw payload, and parsed entities.
  4. **In-Memory Caching**: Cache tool responses in-memory during active execution to eliminate duplicate HTTP requests.
* **Data Engineering & Performance**: Clean separation of transient network traffic and durable session artifacts; full traceability.
* **Cost & FinOps**: Leverages existing deployed MCP infrastructure without additional licensing costs.
* **Security & Reliability**: Adheres strictly to Zero Direct Egress; eliminates secret leakage to external networks; preserves complete replayability of agent discoveries.
* **Pros & Cons**:
  * Good, 100% compliant with course enterprise security and architectural standards.
  * Good, structured audit trail of every tool interaction with timestamped markdown artifacts.
  * Bad / Trade-off, requires active MCP services during execution (with resilient local mock fallback for unit tests).

##### Option 5.2: Direct Container Egress with Local Disk Only (REJECTED)
* **Description**: Making direct `httpx` calls from Cloud Run and writing files to container `/tmp`.
* **Reason for Rejection**: Violates the Zero Direct Egress security pattern and loses session persistence when Cloud Run instances scale down.

#### Consequences
* **Positive**: Complete auditability, enterprise-grade egress control, and persistent replayable session artifacts.
* **Negative / Trade-offs**: Local test suite requires mocking or configuring MCP endpoints.
* **Confirmation**: Verified by checking MCP workspace file listings and BigQuery audit records during integration testing.

---

### Decision 6: Semantic Entity Extraction & Contract-Driven Autonomy (Zero Script Fallbacks)

#### Problem & Drivers
External API endpoints return highly variable, evolving payloads (single dictionary vs. lists, unconventional keys, natural language notes like "Takes 0.7 fuel and 1.0 food per move", or non-standard naming like `wehicles`). Attempting to anticipate every variation via hardcoded Python regexes or heuristics in `tool_discovery_service.py` is brittle (*Ingestion Blindness* anti-pattern). Furthermore, implementing a post-execution Python bypass script (*"deterministic fallback pipeline"*) completely undermines agent autonomy, masking reasoning deficiencies and running counter to the lesson's foundational theme (*"Niedeterministyczna natura modeli jako przewaga"*).

#### Considered Options

##### Option 6.1: Agent-Driven Semantic Parameterization with Zero Heuristic Bypass (ACCEPTED)
* **Description**:
  1. The LLM agent directly inspects raw tool responses returned into the conversation context via `invoke_remote_tool`.
  2. The agent uses its natural language understanding to extract entities (vehicles, fuel consumption, food rations, terrain obstacles, starting point, destination).
  3. The `plan_and_verify_route` meta-tool contract (`PlanRouteInput`) explicitly accepts structured arguments:
     - `vehicle_specs: Optional[list[VehicleSpec]] = None`
     - `terrain_grid: Optional[list[list[str]]] = None`
     - `selected_vehicle: Optional[str] = None`
  4. The deterministic A* solver utilizes the agent's semantically extracted specifications directly.
  5. **Zero Heuristic Fallback**: The secondary automated Python script fallback is completely removed. The agent bears full responsibility for end-to-end task execution and verification.
* **Data Engineering & Performance**: Zero regex parsing latency; minimizes redundant tool queries; prevents silent schema corruption.
* **Cost & FinOps**: Operates within the standard agent conversation budget without requiring an auxiliary LLM extraction sub-step or extra round-trips.
* **Security & Reliability**: Strictly contract-validated via Pydantic (`VehicleSpec` field constraints).
* **Pros & Cons**:
  * Good, 100% faithful to the lesson philosophy: the LLM's non-deterministic cognitive flexibility handles messy real-world APIs, while deterministic math solves the path.
  * Good, eliminates hidden background side-effects and brittle regex coupling.
  * Bad / Trade-off, requires the agent prompt to clearly instruct entity extraction from tool inspection.

##### Option 6.2: Heuristic Regex Parsing with Automated Python Bypass Script (REJECTED)
* **Description**: Python service intercepts tool payloads in `_inspect_and_update_cache`, running complex regular expressions against text notes. If the agent loop ends without capturing a flag, an external deterministic script runs in the background to solve and submit the route.
* **Reason for Rejection**: Classic architectural anti-pattern. Regexes break on linguistic shifts or schema adjustments, and automated bypass scripts defeat the fundamental purpose of evaluating autonomous agent capabilities.

#### Consequences
* **Positive**: Full architectural purity, resilient ingestion of unstructured API data, and genuine agentic decision-making.
* **Negative / Trade-offs**: Agent failure is reported truthfully rather than masked by a background script.
* **Confirmation**: Tested via unit tests and live agent traces in LangSmith and BigQuery audit logs.

---

### Decision 7: Autonomous API Error Adaptation, Endpoint Normalization & Multimodal River Crossing

#### Problem & Drivers
1. **Model URL Confusion**: Exposing `endpoint_url` as a required parameter to LLM agents caused hallucinations (e.g. `http://localhost/api/maps`) and brittle coupling.
2. **Error Masking vs. Egress Fallback**: Masking HTTP 404 responses or falling back to direct `httpx` violated Zero Direct Egress and starved the agent of crucial self-correcting guidance returned by Centrala (e.g. `Allowed values: rocket, horse, walk, car`).
3. **Impassable Water Barrier**: The 10x10 terrain map contains an unbroken river barrier `W` separating the starting base from Skolwin. Pure vehicular travel is mathematically impossible within resource limits.

#### Considered Options

##### Option 7.1: Zero-URL Schema, Error Pass-Through & Multimodal A* River Crossing (ACCEPTED)
* **Description**:
  1. **Zero-URL Schema**: `InvokeRemoteToolInput` strictly requires `tool_name`, `query`, and `reasoning`. The backend resolves endpoints deterministically via `$AIDEVS_BASE_URL` or discovered tools, with automatic interception of any hallucinated localhost URLs.
  2. **Error Pass-Through**: HTTP 404 / 500 error payloads from Centrala via MCP Web Gateway are cleanly parsed as JSON and returned directly to the agent context without falling back to direct egress.
  3. **Multimodal River Traversal**: `SolverService.is_tile_passable` allows `walk`/`foot` to wade/swim across water (`"w"`), while motorized vehicles are blocked. `find_best_route` evaluates multimodal transitions (`rocket` $\to$ `walk`), enabling the envoy to fly 8 steps by rocket to the riverbank and walk the remaining 3 steps across the water to Skolwin within 8.0 fuel and 8.3 food portions.
  4. **Vertex AI Streaming Stability**: Explicitly set `include_thoughts=False` in `ChatGoogleGenerativeAI` to eliminate the serialization freeze across tool turns.
  5. **Session Persistence**: Final mission summary is recorded in `run_notes.md`.
* **Data Engineering & Performance**: Eliminates unnecessary network round-trips and thread-blocking egress timeouts.
* **Cost & FinOps**: Solves the path in 11 steps well within fuel and food constraints.
* **Security & Reliability**: 100% compliant with Zero Direct Egress.
* **Pros & Cons**:
  * Good, true agentic autonomy with dynamic error recovery.
  * Good, mathematically sound multimodal pathfinding.
  * Bad / Trade-off, requires accurate terrain physical rules in the A* engine.

##### Option 7.2: Hardcoded Query Recipes & Direct Egress Retry (REJECTED)
* **Description**: Dictating exact query strings in system prompts and using direct `httpx` retry loops on 404.
* **Reason for Rejection**: Deprives the agent of cognitive autonomy and violates Google Cloud security architecture.

#### Consequences
* **Positive**: Agent successfully discovers tools, self-corrects from API responses, executes multimodal route, and secures verification.
* **Negative / Trade-offs**: None.
* **Confirmation**: Verified by unit tests in `test_solver.py` and live execution against Centrala.

---

## 4. Technical Baseline Alignment (GEMINI.md)
100% Alignment with `GEMINI.md` baseline standards.
- Microservice: `cr-s03e05-savethem`
- Model: Gemini 3.8 Flash (`gemini-3.8-flash`) on Vertex AI (`thinking_level="low"`)
- Dual Framework: LangChain 1.2.15 (`create_agent`) & Google ADK 1.33.0 (`Agent` + `Runner`)
- Audit: BigQuery streaming to `af-aidevs.s03e05.audit`
- MCP Services: `cr-mcp-workspace` and `cr-mcp-web-gateway`
- Python runtime: `==3.13.5` with strict `uv` dependencies

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Agent Readiness Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
  - [Zero-Pollution Telemetry Standards](../../../BEST_PRACTICES.md)
  - [Gemini 3.8 Flash Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
