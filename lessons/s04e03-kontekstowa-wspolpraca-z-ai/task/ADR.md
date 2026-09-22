<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-21
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S04E03 - Tactical Search & Rescue Mission in Domatowo (`domatowo`)

## 1. Context
The task `domatowo` requires orchestrating and executing an autonomous search-and-rescue operation in the bombed city ruins of Domatowo to locate an injured partisan survivor and call an extraction helicopter (`callHelicopter`) before operational resources are depleted. The operation is bounded by a hard budget constraint: exactly **300 Action Points (AP)** for all actions combined (unit deployment, transit, inspection, and evacuation). Motorized transporters travel rapidly and cheaply across the street network (`UL` - 1 AP/tile) but are strictly forbidden from entering rough terrain, whereas foot scouts can enter buildings and off-road tiles but incur 7x higher movement costs (7 AP/tile). The architectural fitness function is defined by closed-loop verification: the agent must bootstrap with zero prior API knowledge starting only from `action: "help"`, maintain a persistent mission checklist (`todos.md`), inspect the 11x11 city grid, cross-reference radio intelligence clues (*"highest residential blocks"* = symbol **`B3`**), calculate valid AP-minimal routes using a dedicated tactical calculator tool, drive transporters along `UL` streets to drop off scouts adjacent to candidate `B3` clusters, inspect candidate tiles, confirm human presence, and successfully summon the evacuation helicopter to retrieve the course flag `{FLG:...}` within the 300 AP budget.

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Baseline Standards & Stack | Adhere 100% to GEMINI.md Baseline | Guarantees consistency across Terraform, BigQuery telemetry streaming (`s04e03.audit`), Cloud Run (`cr-s04e03-domatowo`), Gemini 3.8 Flash on Vertex AI, and dual framework parity (LangChain + Google ADK). |
| 2 | API Interaction Layer & Zero Prior Knowledge | 1:1 Meta-Tool (`call_domatowo_api`) via `cr-mcp-web-gateway` | Preserves true agentic autonomy starting solely from `action: "help"`, while routing all outbound traffic through the web gateway to uphold the Zero Direct Egress security pattern. |
| 3 | Navigation & Route Planning Tooling | Dedicated Tactical GPS & AP Calculator Tool (`calculate_route`) | Eliminates the severe RCE security risks and code hallucination of an arbitrary Python interpreter, providing a 100% deterministic, sandboxed A* routing tool that validates `UL` road constraints and exact AP costs on demand. |
| 4 | Working Memory & Operational Planning | Stateful Task Checklist (`todos.md`) in `cr-mcp-workspace` | Bootstraps agent execution with an initial single task (`[ ] Read and analyze action "help"`), requiring the agent to update and persist its multi-step operational plan across tool turns. |
| 5 | Target Prioritization & Map Topology | Clue-Driven `B3` Cluster Prioritization via `UL` Arteries | Grounded in the map visualizer, the agent focuses exclusively on the 3 `B3` (Blok 3P) clusters (North F1–G2, SW A10–C11, SE H10–I11), driving transporters via `UL` arteries directly adjacent to drop-off points (E2, B9/C9, H9/I9) to complete the mission in ~50–80 AP. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Architectural Baseline & Standards Adherence

#### Problem & Drivers
The lesson task requires seamless integration into the repository's Google Cloud infrastructure (Terraform registration, BigQuery audit telemetry, Vertex AI IAM, and strict dual-framework support).

#### Considered Options

##### Option 1.1: Adhere 100% to GEMINI.md Baseline (ACCEPTED)
* **Description**: Scaffold and deploy a standard Cloud Run microservice `cr-s04e03-domatowo` registered in `terraform/variables.tf`, BigQuery dataset `s04e03` with streaming `audit` table, Gemini 3.8 Flash (`thinking_level="low"`) on Vertex AI (`location="global"`), dual agent backends (LangChain `1.2.15` and Google ADK `1.33.0`), and Python 3.13.5 managed with `uv`.
* **Data Engineering & Performance**: Structured JSON telemetry streaming to BigQuery via `af_aidevs.audit.bigquery`; deterministic fast cold starts with pinned dependencies in `pyproject.toml`.
* **Cost & FinOps**: Cloud Run scale-to-zero (CPU idle enabled); Vertex AI low thinking level keeps token spend well within free-tier quotas.
* **Security & Reliability**: IAM Workload Identity authentication (`roles/aiplatform.user`, `roles/bigquery.dataEditor`); Zero-Trust secret management via Secret Manager and local `.env`.
* **Pros & Cons**:
  * Good, because it maintains complete structural, deployment, and observability parity across all course lessons.
  * Good, because it fulfills Artur's educational mandate for both LangChain and Google ADK.
  * Trade-off: Requires scaffolding both LangChain and ADK agent implementations.

##### Option 1.2: Ad-Hoc Standalone Script (REJECTED)
* **Description**: Standalone local Python script without BigQuery audit streaming or Cloud Run packaging.
* **Data Engineering & Performance**: Lacks auditable telemetry or queryable logs.
* **Cost & FinOps**: Zero cloud deployment cost, but loses all observability.
* **Security & Reliability**: Fragile execution without containerized lifecycle guarantees.
* **Pros & Cons**:
  * Good, because fast to hack together.
  * Bad, because violates repo standard architecture and prevents deployment.

#### Consequences
* **Positive**: Predictable CI/CD and container builds via `cloudbuild.yaml`, automated audit tracking in BigQuery dataset `s04e03`.
* **Negative / Trade-offs**: Container scaffolding overhead.
* **Confirmation**: Verified via `uv run pytest` tests, `curl.exe` health checks on `/health`, and BigQuery audit queries.

---

### Decision 2: API Interaction Layer & Zero Prior Knowledge

#### Problem & Drivers
Hardcoding high-level facade tools (`deploy_recon_team`, `scout_and_inspect`) leaks API assumptions a priori and artificially reduces agentic problem-solving. Furthermore, direct outbound HTTP requests from Cloud Run violate the Zero Direct Egress security pattern from `BEST_PRACTICES.md`.

#### Considered Options

##### Option 2.1: 1:1 Meta-Tool (`call_domatowo_api`) via `cr-mcp-web-gateway` (ACCEPTED)
* **Description**: Provide the agent with a single, highly flexible meta-tool `call_domatowo_api(action: str, params: dict, reasoning: str)`. The tool:
  1. Injects `apikey` and `task: "domatowo"`, constructing the final payload `{"apikey": "...", "task": "domatowo", "answer": {"action": action, **params}}`.
  2. Dispatches the POST request to `$AIDEVS_VERIFY` exclusively via `cr-mcp-web-gateway` (`post_web_resource`), falling back to direct httpx only in local dev mode.
  3. Records all requests and responses in BigQuery audit logs (`s04e03.audit`).
  4. Tracks AP consumption and remaining AP balance.
  The agent begins execution knowing **only** that `action: "help"` exists.
* **Data Engineering & Performance**: Centralized gateway logging, zero payload leakage, low latency.
* **Cost & FinOps**: Highly token-efficient; single tool definition in prompt context.
* **Security & Reliability**: Enforces Zero Direct Egress; prevents secret key leakage to the LLM context (key is injected server-side).
* **Pros & Cons**:
  * Good, because the agent genuinely discovers the API surface autonomously.
  * Good, because strictly adheres to Zero Direct Egress security standards.
  * Good, because centralizes BigQuery auditing and error handling.
  * Trade-off: The agent must construct valid `params` dicts based on documentation read from `help`.

##### Option 2.2: Hardcoded High-Level Domain Facade (REJECTED)
* **Description**: Pre-package high-level tools like `deploy_scout`, `move_convoy` that wrap specific assumptions about Centrala's API.
* **Data Engineering & Performance**: Rigid abstractions.
* **Cost & FinOps**: Moderate token overhead.
* **Security & Reliability**: Brittle if Centrala changes parameter names or action semantics.
* **Pros & Cons**:
  * Good, because reduces LLM turns.
  * Bad, because violates the principle of autonomous API discovery and assumes unverified API contracts.

#### Consequences
* **Positive**: Maximum agentic autonomy, robust security, resilient against API parameter changes.
* **Negative / Trade-offs**: Agent must correctly parse `help` and format JSON arguments.
* **Confirmation**: Verified by inspecting LangSmith traces showing agent bootstrapping from `action: "help"`.

---

### Decision 3: Navigation & Route Planning Tooling

#### Problem & Drivers
Navigating an 11x11 grid with road restrictions (`UL`) and high foot patrol costs (7 AP/step vs 1 AP/step) requires accurate path calculation. If the model attempts mental coordinate math, it risks illegal off-road vehicle moves or AP exhaustion. However, giving the model an arbitrary Python code interpreter introduces severe Remote Code Execution (RCE) risks, sandbox escaping, and timeout vulnerabilities.

#### Considered Options

##### Option 3.1: Dedicated Tactical GPS & AP Calculator Tool (`calculate_route`) with Autonomous Drop-off Detection (ACCEPTED)
* **Description**: Provide a specialized, deterministic calculation tool:
  - **Precomputed Tactical Routing Table:** Precalculates all optimal paths from all potential spawn coordinates to each of the 14 `BLOK_3P` target tiles at startup (<5 ms for all 1,694 pairs across the 121 tiles). During mission execution, lookups operate in $O(1)$ time with zero arithmetic latency.
  - **Dynamic Origin & Spawn Resilience:** Transporters are motorized and physically restricted to `ULICA` (streets); spawning on trees/ruins would immobilize the vehicle. If Centrala assigns an entrance/road tile, the lookup table resolves the route immediately. If a foot scout spawns off-road, the tool computes foot routing to the nearest road or target.
  - **TerrainType Enum Integration:** Uses clean `TerrainType` enumeration (`ULICA="UL"`, `BLOK_3P="B3"`, `DRZEWA="DR"`, `PUSTA_PRZESTRZEN=" "`, etc.).
  - **Dual-Graph Representation:**
    - Road Graph $G_{\text{road}}$: nodes are road tiles, edge weight = 1 AP.
    - Foot Graph $G_{\text{walk}}$: nodes are all passable tiles, edge weight = 7 AP.
  - **Autonomous Drop-off Detection (`recommended_dropoff_tile`):**
    - If `unit_type == "transporter"` and `destination` is an off-road structure (e.g. a `BLOK_3P` residential block), the tool does not fail or abort.
    - Instead, it performs reverse BFS/Dijkstra on $G_{\text{walk}}$ starting from `destination` to identify candidate road tiles $R \in G_{\text{road}}$ within walking distance.
    - For each candidate road tile $R$, it calculates the shortest road path from `origin` on $G_{\text{road}}$, evaluating the joint objective function:
      $$\text{Total AP}(R) = \left(\text{dist}_{G_{\text{road}}}(\text{origin}, R) \times 1\right) + \left(\text{dist}_{G_{\text{walk}}}(R, \text{destination}) \times 7\right)$$
    - It selects the optimal road tile $R^*$ minimizing total AP, returning a clean, nested schema:
      - **When direct route is possible (`direct_route_possible: true`):**
        - `direct_route_possible`: `true`
        - `route`: `{"path": [...], "steps": int, "ap_cost": int, "unit_type": str}`
        - `tactical_briefing`: human/LLM-readable summary
      - **When direct route is impossible (`direct_route_possible: false`):**
        - `direct_route_possible`: `false`
        - `reason`: `"Destination is off-road for transporter"`
        - `recommended_alternative_route`:
          - `dropoff_tile`: $R^*$ (e.g. `"E2"` for target `"F2"`)
          - `transporter_path`: `["B1", "C1", "D1", "D2", "E2"]`
          - `transporter_ap_cost`: road step count $\times 1$ AP
          - `scout_foot_path`: `["E2", "F2"]`
          - `scout_ap_cost`: foot step count $\times 7$ AP
          - `total_trip_ap_cost`: combined AP expenditure
        - `tactical_briefing`: `"Direct route not possible. Drive transporter to drop-off tile E2 (4 AP), disembark scout (0 AP), walk 1 step to F2 (7 AP). Total: 11 AP."`
  - The agent invokes this tool whenever it plans a move, eliminating arithmetic hallucination and coordinate guesswork while keeping the agent fully in command of execution.
* **Data Engineering & Performance**: Instantaneous $O(1)$ memory lookups backed by sub-5ms precalculation; pure Python; zero sandbox overhead; zero token bloat.
* **Cost & FinOps**: Eliminates wasted LLM tokens and prevents failed API turns.
* **Security & Reliability**: 100% sandboxed, zero RCE risk, impossible to execute illegal off-road vehicle moves.
* **Pros & Cons**:
  * Good, because mathematically guarantees minimal AP paths and zero off-road vehicle violations.
  * Good, because provides immediate, actionable drop-off guidance when targeting buildings.
  * Good, because completely safe (zero RCE risk) and symbol-agnostic.
  * Good, because keeps the agent in the driver's seat (the agent decides where and when to move).
  * Trade-off: Requires implementing the grid graph parser and dual-graph search in Python.

##### Option 3.2: General-Purpose Python Code Interpreter Tool (REJECTED)
* **Description**: Provide a Python REPL tool allowing the model to write and execute arbitrary Python scripts to calculate paths.
* **Data Engineering & Performance**: High latency; heavy resource overhead.
* **Cost & FinOps**: High risk of infinite loops and token waste debugging code.
* **Security & Reliability**: Extreme security risk (RCE, blast radius, container escape, host file access).
* **Pros & Cons**:
  * Good, because theoretically flexible.
  * Bad, because dangerous in production, difficult to sandbox securely in Cloud Run, and prone to syntax/logic bugs generated by the LLM.

#### Consequences
* **Positive**: Absolute security, reliable deterministic navigation, seamless integration with agent decision loop.
* **Negative / Trade-offs**: Fixed tool capability limited to path and cost calculation.
* **Confirmation**: Validated through comprehensive unit tests covering road-only constraints, obstacle avoidance, autonomous drop-off selection, and AP summation.

---

### Decision 4: Working Memory & Operational Planning

#### Problem & Drivers
Multi-turn autonomous operations often suffer from context drift or forgotten goals. The agent needs a structured, durable way to maintain its task checklist across turns.

#### Considered Options

##### Option 4.1: Stateful Task Checklist & Monotonic State Checkpointing (`todos.md`) in `cr-mcp-workspace` (ACCEPTED)
* **Description**: The agent is provided with file management tools connecting to `cr-mcp-workspace` (`read_file`, `write_file`).
  - At startup, `todos.md` is initialized with a single item:
    ```markdown
    # Mission Checklist - Domatowo
    - [ ] 1. Query and analyze action "help" from Centrala API
    ```
  - System instructions mandate that after executing `help`, the agent must read the API documentation, formulate its operational strategy, and update `todos.md` with concrete milestones and a dedicated **Monotonic State Checkpoint** block:
    ```markdown
    # Mission Checklist - Domatowo
    - [x] 1. Query and analyze action "help" from Centrala API
    - [x] 2. Retrieve tactical map and identify BLOK_3P clusters
    - [x] 3. Deploy transporter with scout
    - [/] 4. Sweep BLOK_3P clusters clockwise
    - [ ] 5. Call helicopter extraction

    ## Tactical Search State
    - Checkpoint ID: `cp-04-north-cleared`
    - Step: 4
    - Timestamp: 2026-09-21 23:27:30
    - Last Action: `inspect("F1") -> survivor not found`
    - AP Remaining Estimate: 258 / 300
    - Visited Clusters: ["North (F1-G2)"]
    - Inspected Tiles: ["F2", "G2", "G1", "F1"]
    - Current Position: Transporter at "E2", Scout at "F1"
    - Next Objective: Drive to South-West Cluster (drop-off "B9")
    - Remaining Target Clusters: ["South-West (A10-C11)", "South-East (H10-I11)"]
    - Survivor Found: False
    ```
  - The monotonic `Step: N` counter and semantic `Checkpoint ID` anchor the LLM's temporal awareness, preventing temporal confusion across long multi-turn execution and preventing duplicate tile inspections.
* **Data Engineering & Performance**: Persistent session storage in GCS via `cr-mcp-workspace` with local disk fallback.
* **Cost & FinOps**: Negligible storage cost; prevents circular loops and wasted LLM turns.
* **Security & Reliability**: Fully auditable trace of agent's planned vs executed tasks.
* **Pros & Cons**:
  * Good, because enforces disciplined, step-by-step agentic problem-solving.
  * Good, because allows human operators to inspect current agent progress in real time.
  * Good, because provides memory continuity across multiple LLM turns.
  * Trade-off: Adds tool calls for reading/updating `todos.md`.

##### Option 4.2: Implicit LLM Internal Working Memory (REJECTED)
* **Description**: Rely entirely on the LLM's conversation history to remember what it has done and what it needs to do next.
* **Data Engineering & Performance**: Fragile across 15+ turns; token context grows cluttered.
* **Cost & FinOps**: Higher token costs per turn.
* **Security & Reliability**: Prone to context compaction loss and goal drift.
* **Pros & Cons**:
  * Good, because zero tool overhead.
  * Bad, because high failure rate on long multi-step agent trajectories.

#### Consequences
* **Positive**: Clear mission trajectory, self-documenting execution, reproducible debugging.
* **Negative / Trade-offs**: Small overhead of updating markdown notes.
* **Confirmation**: Verified by checking that `todos.md` exists and contains checked milestones in the session workspace.

---

### Decision 5: Target Prioritization & Map Topology

#### Problem & Drivers
The city grid contains 121 tiles and numerous structures (`B1`, `B2`, `B3`, `KS`, `SZ`, `PK`, `BS`, `DR`, ` `). Searching all structures blindly would rapidly burn through the 300 AP budget.

#### Considered Options

##### Option 5.1: Clue-Driven `B3` Cluster Prioritization via `UL` Arteries (ACCEPTED)
* **Description**: The map visualizer and symbol legend confirm that the highest residential blocks are designated **`B3`** (Blok 3P - 3-story block), occupying exactly 14 tiles across 3 clusters:
  1. **Cluster South-West (A10–C11):** 6 tiles (`A10, B10, C10, A11, B11, C11`). Directly adjacent to street tiles `B9, C9`.
  2. **Cluster South-East (H10–I11):** 4 tiles (`H10, I10, H11, I11`). Directly adjacent to street tiles `H9, I9`.
  3. **Cluster North (F1–G2):** 4 tiles (`F1, G1, F2, G2`). Directly adjacent to street tile `E2`.
  The operational strategy & LLM Agent Tactical Doctrine:
  - Deploy 1 Transporter with 1-2 Scouts (10-15 AP).
  - Drive along the `ULICA` street grid directly to the adjacent drop-off street tile (e.g. `E2`).
  - Disembark scout (0 AP) and step onto entry building tile (e.g. `F2`, 7 AP), then execute `inspect` (1 AP).
  - **LLM Responsibility for Clockwise Scout Sweep:**
    - The LLM Agent is strictly responsible for directing the scout's turn-by-turn movement inside the candidate high-rise cluster following a **deterministic clockwise perimeter sweep**:
      - **Cluster North (2x2):** `F2 -> G2 -> G1 -> F1`
      - **Cluster South-East (2x2):** `H10 -> I10 -> I11 -> H11`
      - **Cluster South-West (3x2):** `B10 -> A10 -> A11 -> B11 -> C11 -> C10`
    - At each tile, the LLM executes `inspect(tile)` (1 AP), analyzes logs via `getLogs`, and records the visited tile into `Inspected Tiles` in `todos.md`.
    - If survivor is confirmed: LLM immediately issues `callHelicopter(destination=current_tile)`.
    - If cluster is fully swept without survivor: LLM commands transporter advance to the next closest `BLOK_3P` cluster.
  - **Financial / AP Budget Verification:**
    - Nominal case (finding target in 1st or 2nd cluster): **~50–90 AP**.
    - Absolute worst-case ceiling (sweeping all 14 tiles across all 3 clusters clockwise + worst possible spawn point): **~167 AP** out of 300 AP.
    - Guaranteed minimum safety margin: **> 130 AP reserve** even under worst-case conditions.
* **Data Engineering & Performance**: Maximum mission velocity and minimal AP consumption.
* **Cost & FinOps**: Optimal resource utilization with provable guarantee of never breaching the 300 AP ceiling.
* **Security & Reliability**: Leaves massive margin of error (>130 AP) under the 300 AP limit.
* **Pros & Cons**:
  * Good, because perfectly aligns radio intelligence with cartographic ground truth.
  * Good, because guarantees mission success well within budget.
  * Trade-off: None.

##### Option 5.2: Blind Random or Exhaustive Search (REJECTED)
* **Description**: Inspect random buildings or low-rise `B1`/`B2` blocks.
* **Data Engineering & Performance**: Inefficient.
* **Cost & FinOps**: Guarantees AP depletion and mission failure.
* **Security & Reliability**: Unacceptable risk.

#### Consequences
* **Positive**: High probability of finding the survivor on the first or second cluster inspection.
* **Negative / Trade-offs**: None.
* **Confirmation**: Verified by checking final AP consumption in run notes.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
  - [Pre-Flight Agent Readiness Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
