# Business Requirements Document (BRD) - S04E03: domatowo

## Overview
The objective of this task (`domatowo`) is to coordinate and execute an autonomous search-and-rescue operation in the war-torn city of Domatowo. The operation requires locating an injured partisan survivor hiding within the ruins and safely coordinating a helicopter evacuation (`callHelicopter`) before operational action points or resources are exhausted.

According to intercepted radio distress signals and intelligence briefings from Azazel:
> *"Przeżyłem. Bomby zniszczyły miasto. Żołnierze tu byli, szukali surowców, zabrali ropę. Teraz jest pusto. Mam broń, jestem ranny. Ukryłem się w jednym z najwyższych bloków. Nie mam jedzenia. Pomocy."*

The survivor is confirmed to be wounded, armed, starved, and sheltering in one of the city's highest residential blocks. The tactical map preview reveals that the city's highest residential buildings are 3-story blocks marked with symbol **`B3`** (Blok 3P), of which exactly **three clusters** exist across the 11x11 grid. The rescue team must navigate the city grid using motorized armored transporters along the street network (`UL`) and foot reconnaissance scouts across rough terrain, perform field inspections of the `B3` structures, verify the survivor's exact grid coordinate, and summon an evacuation helicopter (`callHelicopter`) to complete the mission and retrieve the flag.

## Requirements

### Functional Requirements

1. **API Discovery & Zero-Prior-Knowledge Bootstrap:**
   - Centrala exposes the task endpoint at `$AIDEVS_API_VERIFY` (or `$AIDEVS_VERIFY`) with task identifier `"domatowo"`.
   - The agent begins with **zero hardcoded assumptions** about the API schema except for the entrypoint `action: "help"`.
   - The agent initiates discovery by issuing an `action: "help"` request:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "domatowo",
       "answer": {
         "action": "help"
       }
     }
     ```
   - The returned manual details available commands, unit constraints, movement schemas, inspection parameters, and response formats.

2. **Cartographic Intelligence & Terrain Analysis (`getMap`):**
   - Retrieve the full 11x11 operational grid using the `getMap` action:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "domatowo",
       "answer": {
         "action": "getMap",
         "symbols": []
       }
     }
     ```
   - **Grid Dimensions:** 11 columns (A to K) x 11 rows (1 to 11) = 121 tiles.
   - **Terrain Symbol Ontology & Canonical TerrainType Mapping:**
     ```python
     class TerrainType(StrEnum):
         ULICA = "UL"            # Street: navigable by transporter (1 AP) & scout (7 AP)
         DRZEWA = "DR"           # Trees: obstacle / rough terrain
         PUSTA_PRZESTRZEN = " "  # Empty / ruins: off-road, passable by scout only (7 AP)
         BLOK_1P = "B1"          # 1-story block
         BLOK_2P = "B2"          # 2-story block
         BLOK_3P = "B3"          # 3-story block: HIGHEST RESIDENTIAL BLOCKS (survivor location!)
         KOSCIOL = "KS"          # Church
         SZKOLA = "SZ"           # School
         PARKING = "PK"          # Parking lot
         BOISKO = "BS"           # Sports field
     ```

3. **High-Rise Target Identification (`BLOK_3P` Clusters & Coordinates):**
   - Matching the radio distress clue (*"Ukryłem się w jednym z najwyższych bloków"*), the survivor is sheltered in one of the **3 distinct `BLOK_3P` high-rise clusters** (3-story residential blocks).
   - Analysis of the 11x11 city map confirms that the highest buildings (`BLOK_3P`) occupy exactly **14 coordinates** across 3 clusters:
     1. **Cluster South-West (A10–C11):** 6 tiles: **`A10`, `B10`, `C10`, `A11`, `B11`, `C11`** (a 3x2 residential complex).
        - Direct street drop-off access: street tiles **`B9`** and **`C9`** immediately adjacent to `B10` and `C10`.
     2. **Cluster South-East (H10–I11):** 4 tiles: **`H10`, `I10`, `H11`, `I11`** (a 2x2 residential complex).
        - Direct street drop-off access: street tiles **`H9`** and **`I9`** immediately adjacent to `H10` and `I10`.
     3. **Cluster North (F1–G2):** 4 tiles: **`F1`, `G1`, `F2`, `G2`** (a 2x2 residential complex).
        - Direct street drop-off access: street tile **`E2`** immediately adjacent to `F2`.
   - **Total Target Space:** Exactly 14 candidate tiles: `["A10", "B10", "C10", "A11", "B11", "C11", "H10", "I10", "H11", "I11", "F1", "G1", "F2", "G2"]`.
   - **Precomputed Tactical Routing Table (All-Pairs Precalculation):**
     - Because the grid is fixed at 11x11 (121 tiles total, ~32 street tiles), all optimal routes from every potential spawn coordinate to each of the 14 `BLOK_3P` tiles are precalculated before gameplay starts.
     - Lookups during execution run in $O(1)$ time, returning the exact road trajectory, optimal drop-off tile, and scout foot entry point with 100% mathematical optimality.
   - **Spawn Location Dynamics:**
     - Transporters are motorized and strictly restricted to `ULICA` (streets); spawning a vehicle on trees or ruins would immobilize it. Vehicle spawn positions will be located on the street network (or specified in `create` if permitted).
     - In the defensive scenario of an off-road foot scout spawn, the precomputed routing table provides immediate pathing to the nearest road or target.

4. **Resource & Unit Logistics Management:**
   - Available Assets:
     - Maximum **4 transporters** (`transporter`).
     - Maximum **8 scouts** (`scout`).
     - **300 Action Points (AP)** total operational budget.
   - Asset Deployment Costs:
     - **Create Scout:** 5 AP.
     - **Create Transporter:** 5 AP base fee + 5 AP for each embarked scout (e.g. transporter + 2 scouts = 15 AP).
     - **Move Scout (Foot Patrol):** 7 AP per grid step.
     - **Move Transporter (Motorized Transit):** 1 AP per grid step (roads only).
     - **Inspect Tile:** 1 AP per tile inspection.
     - **Disembark Scouts:** 0 AP.
   - Estimated Mission AP Budget & Worst-Case Guarantee:
     - Initial Deployment (1 Transporter + 1-2 Scouts): 10–15 AP.
     - Transit & Inspection Cluster 1 (North, 4 tiles): ~38–48 AP.
     - Transit & Inspection Cluster 2 (South-West, 6 tiles): ~58–63 AP.
     - Transit & Inspection Cluster 3 (South-East, 4 tiles): ~38–42 AP.
     - Extraction Call (`callHelicopter`): 0–1 AP.
     - **Worst-Case Ceiling (All 14 tiles inspected across all 3 clusters):** **~167 AP** out of 300 AP budget (leaving **> 130 AP reserve**).
     - **Nominal Case (Target found in 1st or 2nd cluster):** **~50–90 AP**.

5. **Field Reconnaissance & Clockwise Inspection Pattern (`inspect` & `getLogs`):**
   - After reaching a cluster drop-off tile and stepping onto the entry tile, the scout executes an autonomous, deterministic **clockwise perimeter sweep** inside the candidate block:
     - **Cluster North (2x2):** `F2 -> G2 -> G1 -> F1`
     - **Cluster South-East (2x2):** `H10 -> I10 -> I11 -> H11`
     - **Cluster South-West (3x2):** `B10 -> A10 -> A11 -> B11 -> C11 -> C10`
   - At each tile, the scout executes `inspect` (cost: 1 AP).
   - Operational findings and survivor confirmation are analyzed via `getLogs`.
   - The LLM Agent records each inspected tile in `todos.md` (`Inspected Tiles`) to guarantee zero backtracking and zero duplicate inspections.
   - Confirm human presence matching the radio transmission profile (wounded partisan, armed, starved).

6. **Helicopter Evacuation Extraction (`callHelicopter`):**
   - Once a scout confirms the survivor's exact grid location (e.g., `"F2"` or `"B10"`), the system triggers immediate air extraction:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "domatowo",
       "answer": {
         "action": "callHelicopter",
         "destination": "F2"
       }
     }
     ```
   - Successful evacuation returns Centrala's response containing the verification flag (`{FLG:...}`).

### Non-Functional & Safety Requirements
1. **AP Budget Guardrails:**
   - Action points cannot exceed 300 AP. Exceeding 300 AP aborts the operation with failure.
   - Absolute worst-case scenario consumes ~167 AP, strictly guaranteeing a safety buffer > 130 AP.
   - A deterministic path and cost calculation tool (`calculate_route`) verifies all transit costs before commands are executed.
2. **Deterministic Route Planning & Dynamic Spawn Resilience:**
   - Transporters must strictly navigate on `UL` road tiles; scouts can traverse all passable terrain.
   - The navigation engine assumes no hardcoded spawn locations. It takes `origin` dynamically from Centrala's unit creation and movement status responses.
   - If a target tile is off-road (e.g. a `BLOK_3P` residential block), the navigation tool autonomously calculates the optimal `recommended_dropoff_tile` (the reachable road tile minimizing combined `transporter_road_ap + scout_foot_ap`).
3. **Monotonic State Checkpointing (`todos.md` in `cr-mcp-workspace`):**
   - The agent maintains a single, unified `todos.md` markdown file tracking both high-level mission milestones and dynamic search state.
   - Search state includes monotonic step counter (`Step: N`), `Checkpoint ID`, `Timestamp`, `Last Action`, `AP Remaining Estimate`, `Visited Clusters`, `Inspected Tiles`, and `Current Position` to eliminate temporal confusion and duplicate tile inspections.
4. **Telemetry & Auditability:**
   - Stream all API payloads, coordinate movements, map snapshots, and Centrala responses to BigQuery dataset `s04e03.audit`.
   - Trace full execution graphs in LangSmith (`LANGSMITH_PROJECT`).
5. **Network Egress Architecture:**
   - All outbound calls to Centrala (`$AIDEVS_VERIFY`) route through **`cr-mcp-web-gateway`** to satisfy the Zero Direct Egress security pattern.
   - Persistent task memory and scratchpad notes (`todos.md`) are stored and managed via **`cr-mcp-workspace`**.

## System & Token Constraints
- **Model Standard:** Gemini 3.8 Flash (`gemini-3.8-flash`) on Vertex AI (`location="global"`, `thinking_level="low"`).
- **AP Budget:** Exactly 300 Action Points for the entire mission.
- **Maximum Units:** 4 transporters, 8 scouts.
- **Map Dimensions:** 11 columns x 11 rows (121 total tiles).

## Data Inputs & Resources
- **Task Verification Endpoint:** `$AIDEVS_API_VERIFY` (or `$AIDEVS_VERIFY`).
- **Tactical Map Visualizer Preview:** `$AIDEVS_DOMATOWO_PREVIEW_URL` (`https://hub.ag3nts.org/domatowo_preview`).
- **Radio Transcript Clues:**
  - *"Przeżyłem. Bomby zniszczyły miasto. Żołnierze tu byli, szukali surowców, zabrali ropę. Teraz jest pusto. Mam broń, jestem ranny. Ukryłem się w jednym z najwyższych bloków. Nie mam jedzenia. Pomocy."*

## API Integration

### Centrala Task Verification Protocol
- **Endpoint:** `$AIDEVS_API_VERIFY`
- **Method:** `POST`
- **Header:** `Content-Type: application/json`
- **Authentication:** `apikey: "$AIDEVS_API_KEY"`

### Core Payloads

1. **Help Discovery Request:**
   ```json
   {
     "apikey": "$AIDEVS_API_KEY",
     "task": "domatowo",
     "answer": {
       "action": "help"
     }
   }
   ```

2. **Map Retrieval Request:**
   ```json
   {
     "apikey": "$AIDEVS_API_KEY",
     "task": "domatowo",
     "answer": {
       "action": "getMap",
       "symbols": []
     }
   }
   ```

3. **Unit Creation Request (Transporter + Scouts):**
   ```json
   {
     "apikey": "$AIDEVS_API_KEY",
     "task": "domatowo",
     "answer": {
       "action": "create",
       "type": "transporter",
       "passengers": 2
     }
   }
   ```

4. **Evacuation Call Request:**
   ```json
   {
     "apikey": "$AIDEVS_API_KEY",
     "task": "domatowo",
     "answer": {
       "action": "callHelicopter",
       "destination": "F2"
     }
   }
   ```

## Security & Environment Setup
| Environment Variable | Secret Manager Secret Name | Description |
| :--- | :--- | :--- |
| `AIDEVS_API_KEY` | `AIDEVS_API_KEY` | Personal course API key for task authentication |
| `AIDEVS_VERIFY` / `AIDEVS_API_VERIFY` | `AIDEVS_VERIFY` | Centrala task verification endpoint URL |
| `AIDEVS_DOMATOWO_PREVIEW_URL` | `AIDEVS_DOMATOWO_PREVIEW_URL` | Visualizer preview URL for the Domatowo map |
| `MCP_WEB_GATEWAY_URL` | `MCP_WEB_GATEWAY_URL` | URL of the cr-mcp-web-gateway microservice |
| `MCP_WORKSPACE_URL` | `MCP_WORKSPACE_URL` | URL of the cr-mcp-workspace microservice |
| `LANGSMITH_API_KEY` | `LANGSMITH_API_KEY` | Tracing telemetry API key |
| `LANGSMITH_PROJECT` | `LANGSMITH_PROJECT` | Shared LangSmith project name |
| `GOOGLE_CLOUD_PROJECT` | N/A (IAM) | Target Google Cloud project ID (`af-aidevs`) |
| `GOOGLE_CLOUD_LOCATION` | N/A (Env) | Target GCP region (`global` for Gemini 3.8 Flash) |

## Acceptance & Verification Criteria
1. **Target Identification:** Identify and target the 3 `B3` (Blok 3P) clusters based on the radio transmission clue (*"jeden z najwyższych bloków"*).
2. **Action Point Conservation:** Complete the entire mission using well under the 300 AP ceiling (estimated ~50–80 AP).
3. **Safe Navigation:** Transporters strictly navigate on `UL` road tiles; scouts disembark immediately adjacent to target blocks.
4. **Extraction Confirmation:** Inspect the target tile, verify survivor presence, and execute `callHelicopter` with valid coordinates.
5. **Flag Retrieval:** Successfully extract and record Centrala's verification flag (`{FLG:...}`) in BigQuery audit logs and local execution run notes.
6. **Framework Parity:** Support dual-framework execution (LangChain and Google ADK) with parity across CLI and Cloud Run microservice interfaces.
