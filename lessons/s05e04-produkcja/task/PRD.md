<!-- Source: https://www.industrialempathy.com/posts/design-docs-at-google/ -->
<!-- Based on: Google Design Docs structure by Malte Ubl -->
<!-- Adapted as a Technical PRD for AI-assisted implementation workflows -->

---
status: "approved"
date: 2026-09-28
author: Artur (artur.fejklowicz)
reviewers: Joi
adr: "[ADR.md](ADR.md)"
---

# Product Requirements Document (PRD) - S05E04: Autonomous Rocket Navigation & OKO Radar Neutralization (goingthere)

## Context and Scope

In the culminating offensive of the resistance operations, an autonomous ground-skimming rocket must be dispatched to reach the allied base in Grudziądz. The badlands sector is subject to intense electronic warfare: dense sensor jamming blinds direct optical sensors, masking hazardous rock formations immediately ahead, while the totalitarian regime's automated defense network, **OKO**, actively tracks sector air corridors. Any movement across the grid while targeted by an OKO radar station triggers an immediate surface-to-air missile strike, terminating the rocket.

To navigate successfully, the rocket controller interfaces with three distinct APIs:
1. **OKO Frequency Scanner API (`$AIDEVS_API_FREQUENCY_SCANNER`):** Reports whether the rocket is targeted by an OKO station. When locked, returns distorted telemetry containing a targeting frequency and detection code requiring cryptographic SHA-1 disarming before movement.
2. **Tactical Radio Message API (`$AIDEVS_API_GETMESSAGE`):** Broadcasts cryptic English transmissions describing impending rock obstacles using colloquial and maritime terminology (*port*, *starboard*, *dead ahead*, *shoals*).
3. **Flight Control Verification Gateway (`$AIDEVS_API_VERIFY`):** Accepts mission initialization (`start`) and directional thrust vectors (`go`, `left`, `right`) across a $3 \times 12$ discrete grid, ultimately releasing the mission completion flag (`{FLG:...}`).

This PRD specifies the technical implementation of the `cr-s05e04-goingthere` Cloud Run microservice and developer CLI, implementing a deterministic Finite State Machine (FSM) governed by a Pydantic `FlightState` accumulator, Vertex AI `gemini-3.8-flash` cognitive parsing with `thinking_level="high"` filtered through `cr-model-armor`, egress proxying via `cr-mcp-web-gateway`, and session audit persistence in `cr-mcp-workspace`.

For foundational architectural decisions and trade-offs, refer to the accepted [ADR.md](ADR.md) and [BRD.md](BRD.md).

---

## Goals and Non-Goals

### Goals
* **Deterministic Navigation & Boundary Enforcement:** Traverse the discrete $3 \times 12$ corridor from start position `(col=1, row=2)` to destination `(col=12, row=target)` without ever exceeding vertical boundaries ($Y \in [1, 3]$) or stepping into an obstacle cell.
* **Resilient Distorted Telemetry Parsing:** Route jammed scanner payloads through `cr-model-armor` and extract numeric `frequency` and alphanumeric `detection_code` via `gemini-3.8-flash` using structured Pydantic schemas.
* **Cryptographic Disarm Execution:** Compute $\text{SHA-1}(\text{detection\_code} + \text{"disarm"})$ and submit disarm payloads to `$AIDEVS_API_FREQUENCY_SCANNER` with verified confirmation before every thrust command.
* **Nautical Radio Telemetry Resolution with Historical Context:** Interpret maritime idioms and spatial broadcast hints via `gemini-3.8-flash` (High Thinking), backed by the full cumulative `GameColumn` history map to accurately decode relative and temporal references ("same as start", "two columns back").
* **Corner-Cutting Collision Prevention:** Employ a lookahead heuristic path planner that avoids cutting corners around solid rock obstacles in the current column when splitting from the middle lane.
* **Trajectory Convergence:** Dynamically select collision-free thrusts (`go`, `left`, `right`) steering towards the Grudziądz target row while preventing boundary trapping.
* **Full Baseline Compliance:** Deploy as a containerized Cloud Run microservice (`cr-s05e04-goingthere`), log audit telemetry to BigQuery dataset `s05e04`, persist unredacted run notes to `cr-mcp-workspace`, and route egress through `cr-mcp-web-gateway`.
* **High-Velocity CLI Tooling:** Provide developer-friendly CLI debugging flags (`--step-by-step`, `--probe`, `--direct-egress`, `--verbose`, `--model`, `--thinking-level`, `--session-id`).

### Non-Goals
* **Multi-Turn Stochastic ReAct Agent:** No unconstrained autonomous tool-calling loop where the LLM decides the execution sequence. Rocket navigation requires strict, deterministic phase ordering where missing a disarm step causes immediate destruction.
* **Custom Static Nautical Lexicon:** No maintenance of hardcoded dictionaries translating sailing terms. The model natively resolves maritime language within prompt context.
* **Local Container Disk Persistence:** No saving of `run_notes.txt` or scratch files to the local container disk or git repository. Persistence is strictly managed via remote `cr-mcp-workspace`.
* **Direct External Egress in Production:** No direct HTTP requests from Cloud Run containers to external APIs; egress is routed through `cr-mcp-web-gateway` via Google Cloud OIDC tokens.

---

## The Design

### System Overview

The system architecture decouples deterministic state machine control from cognitive natural language interpretation:

```
                            ┌───────────────────────────────────────────────┐
                            │                 Client / CLI                  │
                            │   - Cloud Run: POST /run                      │
                            │   - Terminal: uv run python main.py [flags]   │
                            └───────────────────────┬───────────────────────┘
                                                    │
                                                    ▼
                            ┌───────────────────────────────────────────────┐
                            │             FastAPI App / Runner              │
                            │           cr-s05e04-goingthere                │
                            └───────────────────────┬───────────────────────┘
                                                    │
                                                    ▼
                            ┌───────────────────────────────────────────────┐
                            │          FlightController (FSM Engine)        │
                            │     - Tracks FlightState (col, row, target)   │
                            │     - Strict 4-Phase Iteration Loop           │
                            └───────┬───────────────┬───────────────┬───────┘
                                    │               │               │
        ┌───────────────────────────┘               │               └───────────────────────────┐
        ▼                                           ▼                                           ▼
┌──────────────────────────┐            ┌──────────────────────────┐            ┌──────────────────────────┐
│   Phase 1: Radar Check   │            │   Phase 2: Radio Hint    │            │ Phase 3: Path & Thrust   │
│ - GET scanner status     │            │ - POST getmessage        │            │ - Heuristic A* selector  │
│ - Model Armor sanitize   │            │ - Model Armor sanitize   │            │ - Collision avoidance    │
│ - Gemini 3.5 Flash-Lite  │            │ - Gemini 3.5 Flash-Lite  │            │ - POST thrust command    │
│ - SHA-1 disarm if locked │            │   (Naval Officer Persona)│            │ - Update FlightState     │
└─────────────┬────────────┘            └─────────────┬────────────┘            └─────────────┬────────────┘
              │                                       │                                       │
              └───────────────────────────────────────┼───────────────────────────────────────┘
                                                      │
                                                      ▼
                            ┌───────────────────────────────────────────────┐
                            │             GatewayService (Egress)           │
                            │  Routes requests through cr-mcp-web-gateway   │
                            │  (Fallback: direct httpx via --direct-egress) │
                            └───────────────────────┬───────────────────────┘
                                                    │
                         ┌──────────────────────────┴──────────────────────────┐
                         ▼                                                     ▼
        ┌───────────────────────────────────┐                 ┌───────────────────────────────────┐
        │       External Course APIs        │                 │      Workspace & Observability    │
        │ - $AIDEVS_API_FREQUENCY_SCANNER   │                 │ - cr-mcp-workspace (run_notes.txt)│
        │ - $AIDEVS_API_GETMESSAGE          │                 │ - BigQuery: s05e04.audit          │
        │ - $AIDEVS_API_VERIFY              │                 │ - LangSmith Tracing               │
        └───────────────────────────────────┘                 └───────────────────────────────────┘
```

---

### API Design

#### Cloud Run HTTP Endpoints (FastAPI)

1. **`GET /health` & `GET /`**:
   - Status probe and service readiness check.
   - Response:
     ```json
     {
       "status": "ok",
       "service": "cr-s05e04-goingthere"
     }
     ```

2. **`POST /run`**:
   - Canonical execution endpoint for the autonomous flight mission.
   - **Request Payload (`RunTaskRequest`):**
     ```json
     {
       "session_id": "optional-custom-session-id",
       "model": "gemini-3.5-flash-lite",
       "thinking_level": "medium",
       "direct_egress": false
     }
     ```
   - **Response Payload (`RunTaskResponse`):**
     ```json
     {
       "session_id": "session-s05e04-20260928-183000",
       "status": "completed",
       "flag": "{FLG:...}",
       "target_row": 1,
       "total_steps": 11,
       "radar_disarms": 3,
       "trajectory": [
         {"column": 1, "row": 2, "command": "start", "rock_row": 3},
         {"column": 2, "row": 1, "command": "left", "rock_row": 2},
         {"column": 3, "row": 1, "command": "go", "rock_row": 3}
       ],
       "execution_time_seconds": 18.42,
       "error": null
     }
     ```

#### Developer CLI Interface (`main.py`)

Executing `uv run python main.py` directly initiates the navigation run without requiring a `--mode` flag:

```powershell
# Standard production run via cr-mcp-web-gateway
uv run python main.py

# Local development run with direct egress and verbose debug logging
uv run python main.py --direct-egress --verbose

# Interactive step-by-step flight pausing before each column thrust
uv run python main.py --step-by-step --direct-egress

# 1-second pre-flight connectivity probe (checks start and destination without flight)
uv run python main.py --probe --direct-egress
```

---

### Data Model & Schemas

The contract definitions are implemented in `schemas.py`:

```python
from typing import Literal
from pydantic import BaseModel, Field


class GameColumn(BaseModel):
    """Exact representation of Centrala's currentColumn state."""

    column: int = Field(..., description="Grid column index (1-12)")
    your_row: int = Field(..., description="Rocket vertical row (1-3)")
    stone_row: int = Field(..., description="Lethal rock formation row (1-3)")
    free_rows: list[int] = Field(
        ..., description="List of safe vertical channels in this column"
    )


class TrajectoryStep(BaseModel):
    """Snapshot of rocket state and telemetry at a specific column."""

    column: int = Field(..., description="Longitudinal column index (1-12)")
    row: int = Field(..., description="Vertical row coordinate (1-3)")
    command: Literal["start", "go", "left", "right"] = Field(
        ..., description="Movement thrust dispatched to advance to this column"
    )
    rock_row: int | None = Field(
        default=None, description="Observed rock row in this column"
    )
    radar_locked: bool = Field(
        default=False, description="Whether an OKO radar lock was active"
    )
    disarm_hash: str | None = Field(
        default=None, description="SHA-1 disarm hash submitted if locked"
    )


class FlightState(BaseModel):
    """Accumulator state tracked across the entire mission by the FSM."""

    session_id: str = Field(..., description="Unique flight session identifier")
    current_column: int = Field(default=1, description="Current column position (1-12)")
    current_row: int = Field(default=2, description="Current row position (1-3)")
    target_row: int = Field(
        default=2, description="Grudziądz destination row at column 12"
    )
    current_rock_row: int | None = Field(
        default=None, description="Rock row in the current column (for corner-cutting safety)"
    )
    columns_history: dict[int, GameColumn] = Field(
        default_factory=dict, description="Historical map of all discovered columns (1-12)"
    )
    history: list[TrajectoryStep] = Field(
        default_factory=list, description="Historical flight progression"
    )
    radar_disarms_count: int = Field(
        default=0, description="Total active radar traps disarmed"
    )
    is_completed: bool = Field(
        default=False, description="Whether Grudziądz has been reached"
    )
    flag: str | None = Field(
        default=None, description="Extracted course flag token upon mission success"
    )


class RadarTelemetryExtraction(BaseModel):
    """Structured extraction of OKO frequency scanner status from distorted payloads."""

    is_clear: bool = Field(
        ...,
        description="True if airspace is clear ('It's clear!'), False if targeted by OKO radar",
    )
    frequency: int | float | None = Field(
        default=None, description="Targeting frequency identifier extracted from payload"
    )
    detection_code: str | None = Field(
        default=None,
        description="Alphanumeric detection code required for disarming hash",
    )
    reasoning: str = Field(
        default="", description="Extraction chain-of-thought analysis"
    )


class RadioNavigationExtraction(BaseModel):
    """Structured resolution of tactical maritime radio hints into grid coordinates."""

    rock_relative_direction: Literal["left", "ahead", "right", "unknown"] = Field(
        ...,
        description="Obstacle direction relative to rocket heading: left (higher row), ahead (same row), right (lower row)",
    )
    rock_absolute_row: int = Field(
        ...,
        description="Calculated absolute row (1, 2, or 3) containing the rock in next column",
    )
    safe_commands: list[Literal["go", "left", "right"]] = Field(
        ..., description="List of safe thrust commands that avoid the rock"
    )
    reasoning: str = Field(
        default="",
        description="Naval interpretation explaining maritime phrases (port/starboard/bow/shoals)",
    )


class DisarmPayload(BaseModel):
    """Payload sent to $AIDEVS_API_FREQUENCY_SCANNER to neutralize radar."""

    apikey: str
    frequency: int | float
    disarmHash: str


class VerifyCommandAnswer(BaseModel):
    command: Literal["start", "go", "left", "right"]


class VerifyEnvelope(BaseModel):
    apikey: str
    task: str = "goingthere"
    answer: VerifyCommandAnswer
```

---

### Core Logic & Navigation Algorithm

#### 1. Pre-Flight Initialization (`start`)
1. Dispatch `{"command": "start"}` to `$AIDEVS_API_VERIFY`.
2. Parse response JSON:
   - Verify spawn coordinates: Column 1, Row 2.
   - Extract destination base row: `target_row` at Column 12.
   - Record initial obstacle position in Column 1.
3. Initialize `FlightState(current_column=1, current_row=2, target_row=target_row)`.

#### 2. The 4-Phase Column Traversal Loop (`while current_column < 12`)
For each column transition from $X \to X + 1$:

##### Phase 1: Radar Interrogation & Disarm
1. Poll `$AIDEVS_API_FREQUENCY_SCANNER?key=$AIDEVS_API_KEY` via `GET`.
2. Inspect raw response:
   - If contains `"It's clear!"` $\implies$ `is_clear = True`.
   - Else $\implies$ route raw distorted text through `cr-model-armor`, then prompt `gemini-3.5-flash-lite` with structured output `RadarTelemetryExtraction`.
3. If `is_clear == False`:
   - Validate `detection_code` and `frequency` exist.
   - Compute disarm hash:
     $$\text{disarmHash} = \text{SHA1}(\text{detection\_code} + \text{"disarm"})$$
   - Dispatch `POST` to `$AIDEVS_API_FREQUENCY_SCANNER` with payload `DisarmPayload`.
   - Verify disarm confirmation from scanner before proceeding.
   - Increment `FlightState.radar_disarms_count`.

##### Phase 2: Radio Telemetry & Obstacle Localization
1. Dispatch `POST` to `$AIDEVS_API_GETMESSAGE` with `{"apikey": "$AIDEVS_API_KEY"}`.
2. Extract raw transmission text from `hint`.
3. Sanitize transmission through `cr-model-armor`.
4. Prompt `gemini-3.5-flash-lite` with the Naval Officer system instruction:
   - Provide current altitude: `current_row`.
   - Map nautical references:
     - *Port / Left / Top / High / Shoals to port:* $Y_{\text{rock}} = \text{current\_row} - 1$
     - *Dead Ahead / Bow / Straight / Bearing ahead:* $Y_{\text{rock}} = \text{current\_row}$
     - *Starboard / Right / Bottom / Low / Reef to starboard:* $Y_{\text{rock}} = \text{current\_row} + 1$
   - Generate structured `RadioNavigationExtraction` specifying $Y_{\text{rock}} \in \{1, 2, 3\}$.

##### Phase 3: Trajectory Planning (Lookahead Heuristic)
Determine candidate vector thrusts from current row $Y$:
* Candidate `go`: Results in row $Y$. Valid if $Y \neq Y_{\text{rock}}$.
* Candidate `left`: Results in row $Y - 1$. Valid if $Y > 1$ and $Y - 1 \neq Y_{\text{rock}}$.
* Candidate `right`: Results in row $Y + 1$. Valid if $Y < 3$ and $Y + 1 \neq Y_{\text{rock}}$.

**Selection Heuristic:**
1. Filter candidates to valid, collision-free moves.
2. If multiple candidates are safe, score each candidate $c$ by vertical distance to Grudziądz destination:
   $$\text{cost}(c) = |Y_{\text{target}} - Y_{\text{candidate}}|$$
3. Tie-breaking / Wall-Trap Prevention: If remaining columns $D = 12 - (X + 1)$ equals the required vertical delta $|Y_{\text{target}} - Y_{\text{candidate}}|$, prioritize the move directly reducing the delta.
4. Select optimal candidate command $C^* \in \{\text{"go"}, \text{"left"}, \text{"right"}\}$.

##### Phase 4: Vector Thrust Dispatch & State Transition
1. Dispatch $C^*$ to `$AIDEVS_API_VERIFY`.
2. Parse response and update `FlightState`:
   - `current_column = current_column + 1`
   - `current_row = updated_row`
   - Append `TrajectoryStep` to history.
3. If `current_column == 12`:
   - Check if response contains course flag (`{FLG:...}`).
   - Set `FlightState.is_completed = True` and extract flag.

#### 3. Post-Flight Auditing & Workspace Persistence
1. Construct comprehensive `run_notes.txt` markdown buffer containing:
   - Session ID, execution timestamp, and status.
   - Unanonymized flag token (`{FLG:...}`).
   - Complete trajectory table (column, row, action, rock row, radar lock).
   - Radar disarm count and total latency.
2. Persist `run_notes.txt` to `cr-mcp-workspace` at:
   `gs://af-aidevs-workspaces/sa-cr-s05e04-goingthere/<session_id>/run_notes.txt`
   *(Strictly raises `RuntimeError` if workspace persistence fails — zero local container disk fallback).*
3. Stream structured execution event to BigQuery dataset `s05e04`, table `audit`.

---

### Infrastructure and Deployment

#### Cloud Run Microservice Configuration
* **Service Name:** `cr-s05e04-goingthere`
* **CPU / Memory:** 1 vCPU / 1 GiB RAM
* **Concurrency:** 80 concurrent requests
* **Scaling:** `min_instances = 0`, `max_instances = 1`, `cpu_idle = true`
* **Timeout:** 600s
* **Service Account:** `sa-cr-s05e04-goingthere@af-aidevs.iam.gserviceaccount.com`
* **Roles:** `roles/aiplatform.user`, `roles/bigquery.dataEditor`, `roles/secretmanager.secretAccessor`

#### Terraform Registration (`terraform/variables.tf`)
The service is registered in `cr_names` adhering strictly to standards:
```hcl
"cr-s05e04-goingthere" = {
  image_name = "cr-s05e04-goingthere"
  source_dir = "../lessons/s05e04-produkcja/task/cr-s05e04-goingthere"
  use_pack   = false
  secrets    = ["AIDEVS_API_KEY", "AIDEVS_VERIFY", "AIDEVS_API_GETMESSAGE", "AIDEVS_API_FREQUENCY_SCANNER", "MODEL_ARMOR_URL", "MCP_WORKSPACE_URL", "MCP_WEB_GATEWAY_URL", "LANGSMITH_API_KEY"]
  env_vars = {
    GOOGLE_CLOUD_PROJECT   = "af-aidevs"
    GOOGLE_CLOUD_LOCATION  = "global"
    GEMINI_MODEL           = "gemini-3.5-flash-lite"
    THINKING_LEVEL         = "medium"
    BQ_DATASET             = "s05e04"
    BQ_TABLE               = "audit"
    LANGSMITH_PROJECT      = "af-aidevs"
    GCS_WORKSPACE_BUCKET   = "af-aidevs-workspaces"
  }
}
```
BigQuery dataset `s05e04` and audit table `tables.s05e04_audit` are registered reusing `bq-schemas/s01e04.audit.json`.

---

## Cross-Cutting Concerns

### Security
* **Zero Hardcoded URLs & Keys:** All external URLs (`$AIDEVS_API_VERIFY`, `$AIDEVS_API_GETMESSAGE`, `$AIDEVS_API_FREQUENCY_SCANNER`) and `$AIDEVS_API_KEY` are retrieved exclusively from Secret Manager or local `.env`.
* **Ingestion Safety via Model Armor:** Raw scanner payloads and untrusted radio transmissions are screened through `cr-model-armor` before LLM processing, neutralizing prompt injection attacks.
* **Egress Gateway Protection:** All external outbound HTTP calls route through `cr-mcp-web-gateway` with authenticated Google Cloud OIDC tokens in cloud environments.
* **Flag Confidentiality:** Course flags (`{FLG:...}`) are never printed in public commit messages or markdown documentation; they are stored exclusively in private GCS workspaces (`run_notes.txt`).

### Observability & Telemetry
* **BigQuery Audit Streaming:** Every flight phase, radar disarm, radio hint, and movement transition is streamed to `s05e04.audit` with session tracing (`X-Session-ID`).
* **LangSmith Tracing:** Semantic inference calls for radar telemetry and radio hint interpretation are traced under `af-aidevs` project.
* **Granular Tool Observability:** Every column step logs `[Col X/12] Radar: CLEAR/DISARMED | Rock: Row Y | Move: COMMAND`.

### Error Handling & Resilience
* **Synthetic Jamming & Upstream Transient Errors:** The scanner and verify endpoints deliberately inject random HTTP failures. All gateway calls utilize `tenacity` exponential backoff (retry on 429, 500, 502, 503, 504 up to 5 attempts with jitter).
* **Dirty-JSON Fallback:** If Model Armor or the LLM encounters syntax anomalies in radar payloads, regex extractors provide secondary token recovery.
* **Fail-Fast Workspace Integrity:** In accordance with GEMINI.md, if `cr-mcp-workspace` is unreachable during `save_run_notes`, an explicit `RuntimeError` is raised.

---

## Edge Cases and Constraints

### Edge Cases
1. **Vertical Boundary Stepping:** When rocket is in Row 1, command `left` is physically prohibited. When in Row 3, command `right` is prohibited. The path planner strictly filters candidates against grid boundaries.
2. **Double-Trapped Escape:** In rare cases where forward and upward cells are blocked, the single remaining lateral move is deterministically selected. In a 3-row grid with 1 rock per column, at least two rows are always safe for each column transition.
3. **Scanner Clear False Positive:** If scanner payload does not contain `"It's clear!"`, it is unconditionally treated as an active radar lock requiring parsing and SHA-1 disarming.
4. **Nautical Linguistic Ambiguities:** Compound phrasing (e.g., *"steer clear of starboard shoals"*) is disambiguated by prompting the model to explicitly identify the *obstacle's* row rather than the recommended path.

### Constraints
* **Session Execution Budget:** Cloud Run timeout is 600s. Flight execution takes $\approx 15-25$ seconds.
* **Token Cost:** Gemini 3.5 Flash-Lite consumes $\approx 300$ tokens per column $\times 11$ columns $\approx 3,300$ tokens total ($< \$0.001$).
* **Local Development Identity:** When executing locally without service account impersonation, `--direct-egress` enables direct `httpx` execution against course APIs.

---

## Implementation Plan

### Phases / Milestones

| Phase | Scope | Deliverable |
| :--- | :--- | :--- |
| **Phase 1: Scaffolding & Configuration** | Directory structure, pyproject.toml, Dockerfile, cloudbuild.yaml, config.py, schemas.py | Scaffolding passing `ruff check` |
| **Phase 2: Service Layer** | Model Armor service, gateway service (MCP + direct egress), scanner service, navigator service | Service unit tests with mocked payloads |
| **Phase 3: FSM Flight Controller** | Finite State Machine, 4-phase loop, heuristic lookahead path planner, workspace persistence | Simulation flight tests on 3x12 synthetic grid |
| **Phase 4: Entrypoints & CLI** | FastAPI endpoints (`/health`, `/run`), CLI arguments (`--step-by-step`, `--probe`, `--direct-egress`, `--verbose`) | Working `main.py` CLI and server |
| **Phase 5: Terraform & Quality Gate** | Infrastructure registration, dataset/audit tables, `ruff`, `mypy`, `pytest` 5-point gate | Verified production deployment readiness |

---

## Implementation Spec

> This section is consumed by the AI coding agent executing `/implement-prd` against this PRD.

### File Structure

```
lessons/s05e04-produkcja/task/cr-s05e04-goingthere/
├── .dockerignore
├── .gcloudignore
├── .python-version
├── Dockerfile
├── README.md
├── cloudbuild.yaml
├── config.py
├── main.py
├── pyproject.toml
├── schemas.py
├── services/
│   ├── __init__.py
│   ├── audit_service.py
│   ├── flight_controller.py
│   ├── gateway_service.py
│   ├── mcp_service.py
│   ├── model_armor_service.py
│   ├── navigator_service.py
│   └── scanner_service.py
└── tests/
    ├── __init__.py
    ├── test_flight_controller.py
    ├── test_nautical_interpreter.py
    ├── test_radar_disarm.py
    └── test_schemas.py
```

### Technology Stack & Exact Dependencies (`pyproject.toml`)

* **Python Version:** `requires-python = "==3.13.5"`
* **Dependencies:**
  ```toml
  dependencies = [
      "af-aidevs==0.2.1",
      "fastapi==0.136.1",
      "google-cloud-bigquery==3.41.0",
      "google-cloud-secret-manager==2.23.1",
      "google-genai==1.74.0",
      "httpx==0.28.1",
      "langchain==1.2.15",
      "langchain-google-genai==4.2.2",
      "langchain-mcp-adapters==0.2.2",
      "langsmith==0.14.0",
      "mcp==1.30.0",
      "pydantic==2.13.4",
      "pytest==8.3.5",
      "pytest-asyncio==0.25.3",
      "python-dotenv==1.2.2",
      "tenacity==9.0.0",
      "tzdata==2026.2",
      "uvicorn==0.46.0",
  ]
  ```

### Step-by-Step Implementation Order

1. **Scaffolding:** Create `.python-version`, `pyproject.toml`, `.dockerignore`, `.gcloudignore`, `Dockerfile`, and `cloudbuild.yaml`.
2. **Configuration & Contracts:** Implement `config.py` (with resilient `os.getenv` fallbacks) and `schemas.py` (strict Pydantic models).
3. **Audit & Workspace Services:** Implement `services/audit_service.py` (BigQuery audit) and `services/mcp_service.py` (`cr-mcp-workspace` connection and `save_run_notes`).
4. **Model Armor & Security Gate:** Implement `services/model_armor_service.py` to sanitize incoming scanner strings and radio hints.
5. **Gateway & Egress Client:** Implement `services/gateway_service.py` with dual-mode dispatch (routing via `cr-mcp-web-gateway` OIDC in production, direct `httpx` with tenacity when `--direct-egress` is active).
6. **Radar Scanner & Disarm Service:** Implement `services/scanner_service.py` for polling scanner, LLM extraction of jammed payloads, and SHA-1 disarm calculation.
7. **Nautical Navigator Service:** Implement `services/navigator_service.py` prompting Gemini 3.5 Flash-Lite with maritime persona and computing safe vector moves.
8. **Flight Controller FSM:** Implement `services/flight_controller.py` orchestrating the 4-phase traversal loop, boundary checks, and `run_notes.txt` persistence.
9. **Entrypoints & CLI:** Implement `main.py` with FastAPI (`/health`, `/run`) and CLI argument parser (`--step-by-step`, `--probe`, `--direct-egress`, `--verbose`).
10. **Test Suite:** Implement comprehensive unit tests in `tests/` covering SHA-1 disarm math, maritime phrase parsing, FSM state updates, and boundary clamping.
11. **Terraform Registration & Quality Gate:** Register `cr-s05e04-goingthere`, dataset `s05e04`, and audit table in `terraform/variables.tf`. Run `ruff check`, `ruff format`, `mypy`, and `pytest`.

### Acceptance Criteria (Testable)

- [ ] `pyproject.toml` pins exact versions without `^` and dependencies are alphabetically sorted.
- [ ] Container scaffolding (`Dockerfile`, `cloudbuild.yaml`, `.dockerignore`, `.gcloudignore`) satisfies Cloud Run stateless standards.
- [ ] No external API URLs are hardcoded; all endpoints map to `$AIDEVS_*` environment variables.
- [ ] Scanner payloads containing active radar traps are sanitized via Model Armor and parsed by `gemini-3.5-flash-lite` into `frequency` and `detection_code`.
- [ ] Disarm hash computation strictly satisfies $\text{SHA-1}(\text{detection\_code} + \text{"disarm"})$.
- [ ] Radio hints with maritime terminology (*port*, *starboard*, *dead ahead*, *shoals*) correctly resolve into rock row coordinates ($Y_{\text{rock}} \in \{1, 2, 3\}$).
- [ ] Rocket never steps out of bounds ($Y \in [1, 3]$) and never collides with a rock obstacle.
- [ ] Flight controller converges on destination column 12 and target base row, extracting `{FLG:...}`.
- [ ] `run_notes.txt` is persisted to `cr-mcp-workspace` in GCS; zero local container disk fallback.
- [ ] CLI supports `--step-by-step`, `--probe`, `--direct-egress`, `--verbose`, `--model`, `--thinking-level`, and `--session-id`.
- [ ] All unit tests pass and code cleanly passes `ruff check`, `ruff format`, and `mypy`.

### Out-of-Scope for Agent (Human Required)
* Course platform API credentials (`AIDEVS_API_KEY`) provisioned in GCP Secret Manager.
* Visual observation of flight path on course platform preview web page (`$AIDEVS_GOINGTHERE_PREVIEW_URL`).
