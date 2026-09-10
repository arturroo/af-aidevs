# Business Requirements Document (BRD) - Task: `drone`

## 1. Overview
The Security Department of the hostile System is preparing a targeted bombardment to wipe out the resistance's temporary base and nuclear power plant located in Żarnowiec (Power Plant Identification Code: **`PWR6132PL`**). The facility faces critical core cooling failure due to the depletion of Lake Żarnowieckie, which has lost 80% of its water volume and is walled off by a concrete dam.

The resistance has successfully hijacked remote control over an armed military strike drone equipped with an explosive payload. The operational objective is to execute a preemptive strike:
1. Program the drone's official flight mission registry to target the Żarnowiec power plant (`PWR6132PL`), satisfying the automated System's mission logs so the facility is marked as destroyed on System maps.
2. Divert the actual flight path and explosive payload delivery directly onto the nearby **dam** on Lake Żarnowieckie.
3. Breaching the dam will release the reservoir water into the plant's intake canals, restoring reactor cooling while staging the illusion of the plant's destruction.

The autonomous agent must perform multimodal visual analysis of the terrain grid map, parse the drone API technical documentation, construct the valid sequence of drone commands, and iteratively interact with Centrala's verification hub until the mission succeeds and the course flag is captured.

---

## 2. Business Objectives
- **Multimodal Terrain & Sector Localization**: Perform vision analysis on the high-resolution grid map of the Żarnowiec area to determine grid dimensions (columns and rows) and locate the exact coordinates (column, row, 1-indexed) of the dam (identifiable by enhanced water color intensity).
- **API Documentation Ingestion & Trap Avoidance**: Fetch and parse the drone API documentation (`drone.html`), navigating conflicting function definitions, decoy instructions, and strict parameter-dependent behaviors to identify the minimal required command sequence.
- **Preemptive Flight & Strike Sequence Formulation**: Assemble an ordered sequence of drone instructions that officially registers the attack on `PWR6132PL` while physically navigating to and detonating upon the dam sector.
- **Reactive Iterative Verification Loop**: Submit instruction batches to Centrala's `/verify` endpoint, consuming diagnostic error responses to dynamically correct and refine the instruction sequence (utilizing `hardReset` if accumulated state becomes corrupted).
- **Zero-Trust Egress & Security Sanitization**: Route all external HTTP interactions (HTML docs, PNG map, verification submissions) through authorized infrastructure (`cr-mcp-web-gateway`), avoiding direct container egress.
- **Flag Capture & Telemetry Logging**: Capture the course completion flag (`{FLG:...}`), stream all tool interactions and LLM reasoning to BigQuery (`s02e05`), and record a mission summary in `run_notes.txt`.

---

## 3. Data & API Requirements

### 3.1 Drone Terrain Map
- **Resource**: High-resolution PNG image overlaying a coordinate grid across the Żarnowiec power plant territory.
- **Location Variable**: `$AIDEVS_DRONE_MAP_URL` (constructed from `$AIDEVS_API_BASE_URL/data/$AIDEVS_API_KEY/drone.png`).
- **Visual Features**:
  - Grid lines segmenting the terrain into discrete sectors.
  - 1-indexed coordinate system (column 1..N, row 1..M).
  - Power plant complex (`PWR6132PL`).
  - Lake Żarnowieckie and dam structure (accentuated with intensified water coloration near the dam to aid visual detection).

### 3.2 Drone API Documentation
- **Resource**: HTML technical manual describing drone hardware commands, flight instructions, payload controls, and state management.
- **Location Variable**: `$AIDEVS_DRONE_DOCS_URL` (e.g. `$AIDEVS_API_BASE_URL/dane/drone.html`).
- **Key Characteristics**:
  - Contains conflicting and decoy function names designed to trap naive prompt execution.
  - Parameter-sensitive instructions that behave differently based on configuration order and arguments.
  - Reset command (`hardReset`) to clear accumulated drone state when invalid configurations cause cascading errors.

### 3.3 Verification API
Final and iterative drone instruction batches are submitted to the Centrala verification endpoint:
- **Endpoint**: `$AIDEVS_API_VERIFY`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Payload Schema**:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "drone",
    "answer": {
      "instructions": [
        "instruction_1",
        "instruction_2",
        "..."
      ]
    }
  }
  ```

### 3.4 Feedback & Verification Mechanics
- **Diagnostic Feedback**: If the submitted instruction array fails drone flight validation, target mismatch, coordinate bounds, or sequence logic, the endpoint returns an informative error message.
- **Dynamic Adaptation**: The autonomous agent must read the error message, analyze which instruction triggered the fault, update the instruction set, and retry.
- **Completion Signal**: When the flight plan and detonation criteria are satisfied, the endpoint responds with HTTP 200 containing the course completion flag `{FLG:...}`.

---

## 4. Functional Requirements & Extraction Rules

### 4.1 Visual Grid Analysis (Vision Phase)
1. **Model Capability**: Must employ a multimodal vision-capable model (Gemini 3.8 Flash via Vertex AI).
2. **Grid Geometry Discovery**:
   - Determine total number of grid columns ($W$) and rows ($H$).
   - Identify index numbering convention (strictly 1-indexed, starting from top-left or specified origin).
3. **Target Sector Localization**:
   - Locate the dam sector adjacent to Lake Żarnowieckie where water saturation is intentionally heightened.
   - Output exact integer coordinates: `(column, row)`.

### 4.2 Documentation Parsing & Instruction Selection
1. **Minimal Surface Configuration**: Filter out irrelevant, conflicting, or superfluous instructions to conserve token budget and prevent configuration collisions.
2. **Mandatory Mission Parameters**:
   - Registered mission target: Żarnowiec power plant identifier `PWR6132PL`.
   - Detonation/Strike target: Identified dam grid sector coordinates.
3. **Failure Recovery (`hardReset`)**:
   - If consecutive submissions fail due to persistent state corruption or invalid configuration overrides, the agent must prepend or invoke `hardReset` to re-initialize the drone state.

### 4.3 Iterative Agent Loop
1. The agent formulates an initial hypothesis instruction list based on documentation and visual coordinates.
2. The agent submits the payload to `$AIDEVS_API_VERIFY`.
3. If an error is returned:
   - The agent ingests the error text into its context.
   - Adjusts command names, argument formatting, or ordering.
   - Resubmits the updated instruction array.
4. Process terminates successfully when `{FLG:...}` is present in the response body.

### 4.4 Context Minimization & Ephemeral Ingestion (Token & Privacy Hygiene)
1. **Transient Multimodal Ingestion**: The high-resolution terrain map (`drone.png`) is processed ephemerally during the visual grid analysis stage. Raw image payloads and pixel data are discarded immediately once the grid dimensions and dam coordinates `(column, row)` are determined, preventing bloated token consumption in subsequent conversation turns.
2. **Lean Command Extraction**: The drone API documentation (`drone.html`) is distilled to isolate active command prototypes. Decoy and conflicting instructions are filtered before presenting options to the agent context, eliminating hallucination loops and instruction pollution.

---

## 5. System & Model Constraints

- **Primary LLM**: **Gemini 3.8 Flash** (`gemini-3.8-flash`) on Google Cloud Vertex AI via the modern `google-genai` SDK and `langchain-google-genai`.
- **Thinking Configuration**: Default setting is `thinking_level="low"` (or `types.ThinkingLevel.LOW`) to balance low latency and high precision.
- **Dual Framework Architecture**: Implementation must support both **LangChain (1.2.15)** and **Google GenAI SDK** via the `--backend` CLI parameter (defaulting to `langchain`).
- **Granular Debugging & Telemetry Policy (Private Cloud)**:
  - **Full-Fidelity Unaggregated Auditing**: Because BigQuery operates entirely within our secure, private GCP project boundary (`af-aidevs`) with restricted access, telemetry must NOT aggregate or truncate operational data. Detailed records of every tool execution, thought trace, raw verification response, and captured course flag (`{FLG:...}`) must be streamed directly to BigQuery dataset `s02e05` via `af_aidevs.audit.bigquery` to support comprehensive post-mortem debugging and verification.
  - **Credential Masking**: Authentication secrets (`AIDEVS_API_KEY`) must be masked (e.g. `***` or redacted) in telemetry payloads, while API responses and flags are preserved in full fidelity.
  - **Standardized Session ID**: Traceable session identifier format: `s02e05_{backend}_{YYYYMMDD_HHMMSS}` in timezone `Europe/Zurich`.
- **Zero-Trust Egress**:
  - No direct outbound socket connections from agent containers to public endpoints.
  - All web fetches and API calls routed through `cr-mcp-web-gateway` (`af_aidevs.clients.mcp`).
- **Pre-Flight Governance & Security (Aligned with `docs/af-aidevs/patterns/agent-readiness-checklist.md`)**:
  - **Blast Radius & Loop Kill Switch**: Enforce a strict iteration ceiling (`max_iterations = 10`) on the verification loop to prevent runaway token spend, API cost spikes, or rate-limit bans.
  - **Least-Privilege Scoping**: The agent is provisioned with surgical tool access only (coordinate retrieval, documentation ingestion, drone verification). No destructive filesystem or general OS tools.
  - **Untrusted Documentation Defense**: Treat `drone.html` as external untrusted input; strip markup and sanitize to prevent potential prompt injections from hijacking mission parameters.
  - **Disaster Recovery**: Systematic trigger of `hardReset` if consecutive parameter collisions corrupt drone state.
- **Service-to-Service Token Efficiency (Aligned with `docs/af-aidevs/patterns/cloud-run-token-caching.md`)**:
  - Internal Cloud Run service calls (`cr-mcp-web-gateway`, `cr-mcp-workspace`) utilize TTL-cached Google OIDC identity tokens (50-minute TTL) to minimize metadata server latency overhead.

---

## 6. Environment Setup & Security Requirements

In strict compliance with repository policies:
- **Zero Raw URLs in Code or Docs**: All external service URLs and secrets must be injected solely via `.env` variables or GCP Secret Manager.
- **Flag Secrecy**: Course flags (`{FLG:...}`) must never be committed to Git, exposed in PR descriptions, or written into public markdown logs.

### Required Environment Variables

| Variable | Description |
|---|---|
| `AIDEVS_API_KEY` | Course platform authentication token |
| `AIDEVS_API_VERIFY` | Central verification hub endpoint URL |
| `AIDEVS_DRONE_DOCS_URL` | Drone API HTML documentation URL |
| `AIDEVS_DRONE_MAP_URL` | Terrain grid map image URL (or template with `$AIDEVS_API_KEY`) |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID hosting Vertex AI and BigQuery (`af-aidevs`) |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI regional endpoint (`global`) |
| `BQ_DATASET` | Target BigQuery dataset for telemetry (`s02e05`) |
| `MCP_WEB_GATEWAY_URL` | Cloud Run URL for authenticated web proxy gateway |
| `MCP_WORKSPACE_URL` | Cloud Run URL for persistent session workspace storage |

---

## 7. Success Criteria

1. Visual grid inspection accurately counts grid dimensions and extracts the 1-indexed `(column, row)` coordinates of the dam on Lake Żarnowieckie.
2. Drone API documentation is retrieved, stripped of markup, and parsed to identify valid mission setup and targeting commands.
3. Drone instructions are formulated with power plant identifier `PWR6132PL` as the registered mission objective, while guiding the strike to the dam coordinates.
4. Autonomous feedback loop correctly intercepts verification hub error messages and refines instruction parameters until accepted.
5. Central verification endpoint returns HTTP 200 with the `{FLG:...}` token.
6. Telemetry and step-by-step logs are persisted in BigQuery dataset `s02e05`.
7. Mission outcome, backend selection, and sanitized flag capture are documented in `run_notes.txt`.
