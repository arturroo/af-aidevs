# Business Requirements Document (BRD) - S03E05: savethem

## Overview
The goal of this task (`savethem`) is to design and implement an autonomous agentic system capable of planning and navigating an optimal route across unknown post-apocalyptic terrain for a human envoy sent from the resistance base to the survivor city of Skolwin. 

Following the tragic destruction of the first contact city due to automated transmission leakage, direct radio negotiation is banned. The human envoy must travel physically across a 10x10 grid map. The envoy has a choice of vehicles at the base, along with a strictly limited budget of **10 food rations** and **10 units of fuel**. The agent must dynamically discover required reconnaissance and telemetry tools via a central tool search engine, acquire the map and movement/vehicle physics, compute a feasible route without exhausting food or fuel or hitting impassable terrain, and submit the sequence of moves to Centrala.

## Requirements

### Functional Requirements
1. **Dynamic Tool Discovery via Toolsearch:**
   - The agent does not start with pre-registered operational tools. Instead, it is provided solely with a tool search endpoint (`$AIDEVS_API_TOOLSEARCH`).
   - The agent must query `$AIDEVS_API_TOOLSEARCH` using natural language or keyword queries (e.g. terrain, movement rules, map, vehicle specifications) to discover domain tools.
   - Toolsearch request format:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "query": "search query string in English"
     }
     ```
   - Toolsearch response returns matching tool definitions, their capabilities, and their dedicated HTTP endpoints.
2. **Standardized Tool Interaction Protocol:**
   - All tools discovered via `toolsearch` adhere to the identical request schema:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "query": "query string in English"
     }
     ```
   - **Language Restriction:** All discovered tools communicate **strictly in English**.
   - **Top-K Limit:** Every discovered tool returns only the **top 3** best-matching results for any given query (they do not dump complete datasets in a single call). Queries must therefore be targeted and iterative.
3. **Map & Terrain Acquisition:**
   - Discover and query the appropriate tool to retrieve the 10x10 grid map.
   - Parse terrain tiles and obstacles (e.g. rivers, trees, rocks, plains/roads, base location, Skolwin destination).
   - Establish coordinates for the starting point (Base) and target point (Skolwin).
4. **Vehicle & Travel Mechanics Resolution:**
   - Query discovered tools to learn about the fleet of available vehicles at the base, their speed, fuel consumption per move, food consumption per move, and terrain restrictions.
   - Account for foot travel: the envoy can exit any vehicle and proceed on foot (which consumes 0 fuel but higher food due to slower travel speed).
   - Starting resource limits: exactly **10 food portions** and **10 fuel units**.
5. **Optimal Route Planning & Validation:**
   - Calculate a collision-free path from the starting base coordinate to Skolwin coordinate $(x_{end}, y_{end})$.
   - Ensure the total cumulative fuel consumed $\le 10$ and total cumulative food consumed $\le 10$ throughout every step of the journey.
   - Generate the final answer array starting with the selected vehicle identifier followed by step directions:
     ```json
     ["vehicle_name", "step_1", "step_2", "..."]
     ```
     Valid directions: `"right"`, `"left"`, `"up"`, `"down"`.
6. **Centrala Verification & Course Flag Extraction:**
   - Submit the planned travel itinerary to `$AIDEVS_API_VERIFY`:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "savethem",
       "answer": ["vehicle_name", "right", "right", "up", "..."]
     }
     ```
   - The route and envoy execution can be visually monitored in real-time on `$AIDEVS_SAVETHEM_PREVIEW_URL`.
   - On reaching the Skolwin terminal cell within budget, extract and store the returned course flag `{FLG:...}`.

### Special Exceptions & Guardrails
- **Strict Budget Constraints:** If fuel drops below 0 or food drops below 0 at any turn, the envoy is stranded and the mission fails.
- **Top-3 Retrieval Blindness:** Because tools only return 3 items per query, naive queries may miss alternative vehicles or map segments. The agent must systematically discover all vehicles and full map topology before path calculation.
- **English-Only Tools:** All queries to discovered tools and toolsearch must be formulated in English, even if the user instructions or story are in Polish.
- **Preview Simulator:** Centrala maintains a visual simulator at `$AIDEVS_SAVETHEM_PREVIEW_URL` providing debugging feedback on route execution.

## System & Token Constraints
- **Primary LLM Standard:** Gemini 3.8 Flash (`gemini-3.8-flash`) via Vertex AI (`thinking_level="low"`) for dynamic tool discovery, query synthesis, and strategy reasoning.
- **Dual Framework Requirement:** Both **LangChain** (`1.2.15` via `create_agent`) and **Google ADK** (`1.33.0` via `Agent` and `Runner`) must be implemented with 100% functional parity.
- **Hybrid Pathfinding Architecture:** While LLM reasoning discovers tools and parameters, the path calculation itself should leverage deterministic graph search (e.g. A* / Dijkstra / BFS with state `(x, y, vehicle, fuel, food)`) to guarantee mathematical optimality and zero hallucinations in coordinate moves.

## Data Input & External Resources
- Tool search entrypoint: `$AIDEVS_API_TOOLSEARCH`
- Discovered tool endpoints: returned dynamically by toolsearch.
- Visual route preview: `$AIDEVS_SAVETHEM_PREVIEW_URL`
- Verification API: `$AIDEVS_API_VERIFY`

## API Integration

### 1. Toolsearch Endpoint (`$AIDEVS_API_TOOLSEARCH`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Request Body:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "query": "terrain map and navigation tools"
  }
  ```
- **Response Body:**
  ```json
  {
    "code": 0,
    "message": "...",
    "tools": [
      {
        "name": "...",
        "url": "...",
        "description": "..."
      }
    ]
  }
  ```

### 2. Discovered Tool Endpoints
- **Method:** `POST`
- **Request Body:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "query": "vehicle specifications and fuel consumption"
  }
  ```
- **Response Body:** JSON payload containing the top 3 relevant records.

### 3. Verification Endpoint (`$AIDEVS_API_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "savethem",
    "answer": [
      "vehicle_name",
      "right",
      "right",
      "up",
      "down"
    ]
  }
  ```
- **Expected Success Response:**
  ```json
  {
    "code": 0,
    "message": "{FLG:...}"
  }
  ```

## Security & Environment Setup
All sensitive keys and external URLs must be sourced strictly from `.env` and Secret Manager:
- `AIDEVS_API_KEY`: Course authentication token.
- `AIDEVS_API_TOOLSEARCH`: Tool search endpoint URL.
- `AIDEVS_API_VERIFY`: Centrala verification endpoint URL.
- `AIDEVS_SAVETHEM_PREVIEW_URL`: Visual route preview simulator URL.
- `GOOGLE_CLOUD_PROJECT`: GCP Project ID (`af-aidevs`).
- `GOOGLE_CLOUD_LOCATION`: Vertex AI location (`global`).

## Verification & Acceptance Criteria
1. Toolsearch dynamically locates all relevant operational tools (map, terrain, vehicles, rules).
2. The agent correctly extracts complete vehicle specs (fuel per move, food per move, restrictions) and map layout (10x10 grid).
3. The routing engine computes a collision-free path from Base to Skolwin with total fuel $\le 10$ and total food $\le 10$.
4. The generated payload `["vehicle_name", ...directions]` is submitted to `$AIDEVS_API_VERIFY` and returns a valid `{FLG:...}` course flag.
