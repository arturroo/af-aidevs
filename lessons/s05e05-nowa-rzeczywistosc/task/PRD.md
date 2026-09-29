<!-- Source: https://www.industrialempathy.com/posts/design-docs-at-google/ -->
<!-- Based on: Google Design Docs structure by Malte Ubl -->
<!-- Adapted as a Technical PRD for AI-assisted implementation workflows -->

---
status: "approved"
date: 2026-09-29
author: Artur
reviewers: Joi
adr: ADR.md
---

# Technical PRD: S05E05 - Pocket Time Machine Autonomous Operation (timetravel)

## Context and Scope

In the culmination of the resistance campaign, Operative Number Five must operate the ACME CHRONOS-P1 pocket time machine inside the Grudziądz cave system to establish a permanent temporal corridor to **November 12, 2024** — the day prior to resistance leader Rafał being discovered unconscious. 

The CHRONOS-P1 enforces a strict dual-control plane:
1. **Programmatic Register Control:** Coordinates (`day`, `month`, `year`), temporal synchronization ratio (`syncRatio`), and core stabilization (`stabilization`) are configured via the REST API (`$AIDEVS_API_VERIFY`), restricted to when the device is in `standby` mode.
2. **Physical Cockpit Actuation:** Directional port switches (`PT-A` for past, `PT-B` for future, or both for tunnel), radiation shield potentiometer (`PWR`, $0 - 100$), system power toggle (`standby`/`active`), and temporal ignition (clicking the central glowing sphere) are operated exclusively through the web cockpit interface (`$AIDEVS_TIMETRAVEL_PREVIEW_URL`).
3. **Core Oscillation Phase Gate:** The internal core rotates automatically across four discrete operational phases (`internalMode` 1 to 4) every few seconds. An ignition attempt during an incompatible phase triggers immediate shutdown.

Because current battery cells (`XLPWR-A`) carry only 1 charge unit (`batteryStatus: "1/3"`), opening a high-energy tunnel directly is impossible (minimum 60% charge required). The system must execute an autonomous 3-hop mission:
- **Phase 1 (Future Jump):** Jump to `2238-11-05` to meet a resistance contact and acquire fresh power cells (`3/3`).
- **Phase 2 (Return Jump):** Return to the baseline present (`2026-09-29`) with full power.
- **Phase 3 (Tunnel Establishment):** Open and stabilize a permanent bidirectional time tunnel to `2024-11-12`, rendezvous with Rafał, and retrieve the final operational flag (`{FLG:...}`).

As established in the accepted [ADR.md](ADR.md), this system is implemented as two cloud-native Google Cloud Run microservices communicating over private Agent-to-Agent (A2A) HTTP REST with IAM OIDC authentication.

---

## Goals and Non-Goals

### Goals
* **Autonomous 3-Hop Trajectory Execution:** Automatically execute Jump 1 (`2238-11-05`), Jump 2 (`2026-09-29`), and Jump 3 (`2024-11-12`) without human manual intervention.
* **Dual-Service Cloud Run Architecture:**
  - `cr-s05e05-director`: Lightweight brain executing temporal math, Central API configurations, Gemini 3.5 Flash Lite stabilization interpretation, and mission orchestration.
  - `cr-s05e05-cockpit`: Isolated actuator running headless Chromium via Playwright to manipulate cockpit controls in `$AIDEVS_TIMETRAVEL_PREVIEW_URL`.
* **Zero-Latency A2A Coordination:** Direct internal HTTP REST protocol with Google Cloud IAM OIDC tokens (`roles/run.invoker`) for sub-50ms coordination during `internalMode` phase windows.
* **Deterministic Temporal Math:** Hardcoded modular calculation for `syncRatio` and static in-memory lookup table for 1000-year shield protection (`PWR`).
* **Dynamic Model Steering:** Support dynamic overrides in `POST /run` for `model` (default: `"gemini-3.5-flash-lite"`), `thinking_level` (default: `"low"`), and `max_iterations`.
* **BigQuery Streaming Audit:** Stream all state changes, telemetry snapshots, and flag acquisitions to dataset `s05e05`, table `audit`.

### Non-Goals
* **No Local CLI Mode:** CLI execution has been explicitly dropped per ADR Decision 7 in favor of 100% cloud-native Cloud Run execution.
* **No Firestore Database:** State is passed directly between agents via A2A; long-term telemetry is stored in BigQuery, eliminating Firestore complexity.
* **No Militaristic Endpoint Names:** Actuation endpoints use canonical domain names (`/activate-jump`), strictly rejecting `/detonate`.
* **No Hardcoded URLs or Secrets:** All URLs and API keys must be injected via Secret Manager or environment variables.

---

## The Design

### System Overview

```
 [ Artur / CI / Client ]
            |
            | 1. POST /run (with OIDC Bearer Token)
            v
 +---------------------------------------------------------------------------------+
 | GOOGLE CLOUD RUN ENVIRONMENT                                                    |
 |                                                                                 |
 |   +-------------------------------------------------------------------------+   |
 |   | cr-s05e05-director (The Brain - Port 8080)                              |   |
 |   | - Runtime: Python 3.13.5-slim (512 MiB RAM, 1 vCPU)                    |   |
 |   | - Modules: State Machine, Temporal Math, PWR Table, LLM Resolver        |   |
 |   | - Identity: sa-cr-s05e05-director                                       |   |
 |   +------------------------------------+------------------------------------+   |
 |                                        |                                        |
 |                                        | 3. Private A2A (HTTP REST + IAM OIDC)  |
 |                                        v                                        |
 |   +-------------------------------------------------------------------------+   |
 |   | cr-s05e05-cockpit (The Hands - Port 8080)                               |   |
 |   | - Runtime: Python 3.13.5 + Playwright Chromium (2 GiB RAM, 2 vCPU)      |   |
 |   | - Modules: Browser Automation, DOM Watcher, Sphere Actuator             |   |
 |   | - Identity: sa-cr-s05e05-cockpit                                        |   |
 |   +------------------------------------+------------------------------------+   |
 |                                        |                                        |
 +----------------------------------------|----------------------------------------+
              |                           |
              | 2. Programmatic           | 4. Headless Web Actuation
              |    Registers              |    (DOM Clicks & Polling)
              v                           v
 +---------------------------------------------------------------------------------+
 | CENTRALA AI_DEVS INFRASTRUCTURE (hub.ag3nts.org)                                |
 |                                                                                 |
 |   $AIDEVS_API_VERIFY                        $AIDEVS_TIMETRAVEL_PREVIEW_URL      |
 |   (REST API: configure, getConfig)          (Interactive HTML5 Cockpit GUI)     |
 +---------------------------------------------------------------------------------+
              |
              | 5. Telemetry Streaming (af_aidevs.audit.bigquery)
              v
 +---------------------------------------------------------------------------------+
 | BIGQUERY TELEMETRY (af-aidevs.s05e05.audit)                                     |
 +---------------------------------------------------------------------------------+
```

---

### API Design

#### 1. Public Ingestion API (`cr-s05e05-director`)

##### `POST /run`
Main entrypoint to trigger the autonomous 3-hop temporal mission.

* **Request (`RunTaskRequest`):**
  ```json
  {
    "model": "gemini-3.5-flash-lite",
    "thinking_level": "low",
    "session_id": "session-20260929-001",
    "max_iterations": 50
  }
  ```
* **Response (`RunTaskResponse`):**
  ```json
  {
    "success": true,
    "session_id": "session-20260929-001",
    "flag": "{FLG:TIMETRAVEL_COMPLETED_REDACTED}",
    "execution_time_seconds": 18.4,
    "phases_completed": [
      { "phase": 1, "target": "2238-11-05", "status": "COMPLETED", "battery": "3/3" },
      { "phase": 2, "target": "2026-09-29", "status": "COMPLETED", "battery": "2/3" },
      { "phase": 3, "target": "2024-11-12", "status": "COMPLETED", "battery": "0/3" }
    ],
    "message": "Time tunnel locked. Rendezvous with Rafał accomplished."
  }
  ```

##### `GET /health` and `GET /`
Readiness and health status check returning service metadata.

---

#### 2. Private Agent-to-Agent (A2A) API (`cr-s05e05-cockpit`)
All endpoints are private (`public = false`) requiring an OIDC bearer token generated by `sa-cr-s05e05-director`.

##### `POST /controls`
Instructs Cockpit to adjust physical switches and potentiometers on `$AIDEVS_TIMETRAVEL_PREVIEW_URL`.

* **Request (`CockpitControlsRequest`):**
  ```json
  {
    "session_id": "session-20260929-001",
    "pta": false,
    "ptb": true,
    "pwr": 91,
    "mode": "active"
  }
  ```
* **Response (`CockpitControlsResponse`):**
  ```json
  {
    "success": true,
    "current_pta": false,
    "current_ptb": true,
    "current_pwr": 91,
    "current_mode": "active",
    "flux_density": 100
  }
  ```

##### `GET /telemetry`
Queries live DOM readings extracted by Playwright.

* **Response (`CockpitTelemetryResponse`):**
  ```json
  {
    "flux_density": 100,
    "sync_ratio_display": 82,
    "current_imode": 3,
    "battery_status": "1/3",
    "orb_state": "ready",
    "condition_text": "STAN: DOSKONAŁY // TRYB AKTYWNY"
  }
  ```

##### `POST /activate-jump`
Commands Cockpit to monitor `internalMode` and click the glowing sphere the instant conditions are met.

* **Request (`ActivateJumpRequest`):**
  ```json
  {
    "session_id": "session-20260929-001",
    "target_imode": 3,
    "timeout_seconds": 25.0
  }
  ```
* **Response (`ActivateJumpResponse`):**
  ```json
  {
    "success": true,
    "jump_code": 13,
    "battery_status": "3/3",
    "flag": null,
    "message": "Jump completed successfully. Battery replenished."
  }
  ```

---

#### 3. Central Verification Gateway API (`$AIDEVS_API_VERIFY`)
Used by `cr-s05e05-director` to configure programmatic registers.
* **Envelope:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "timetravel",
    "answer": {
      "action": "configure",
      "param": "year",
      "value": 2238
    }
  }
  ```
* Supported actions: `getConfig`, `configure` (`day`, `month`, `year`, `syncRatio`, `stabilization`), `help`, `reset`.

---

### Data Model / Storage

#### 1. Static In-Memory PWR Knowledge Base (`services/temporal_table.py`)
Pre-compiled dictionary mapping target year ($1500 \le Y \le 2499$) to radiation protection index:
```python
PWR_TABLE: dict[int, int] = {
    1500: 3, 1501: 3, 1502: 1, 1503: 3, ...,
    2024: 19,
    2026: 28,
    2238: 91,
    ...
}
```

#### 2. BigQuery Telemetry Schema (`af-aidevs.s05e05.audit`)
```sql
CREATE TABLE IF NOT EXISTS `af-aidevs.s05e05.audit` (
    timestamp TIMESTAMP NOT NULL,
    session_id STRING NOT NULL,
    actor STRING NOT NULL,          -- 'director', 'cockpit', 'central'
    phase INT64,                    -- 1, 2, 3
    event_type STRING NOT NULL,     -- 'CONFIGURE', 'SET_CONTROLS', 'JUMP_TRIGGER', 'FLAG_CAPTURED'
    content STRING NOT NULL,        -- JSON or descriptive payload (max 500 chars)
    latency_ms FLOAT64,
    metadata JSON
)
PARTITION BY DATE(timestamp)
CLUSTER BY session_id, actor;
```

---

### Core Logic / Algorithms

#### 1. Temporal Math Calculation
```python
def compute_sync_ratio(year: int, month: int, day: int) -> float:
    """Computes decimal temporal synchronization ratio according to ACME formula."""
    raw_sync = (day * 8 + month * 12 + year * 7) % 101
    return round(raw_sync / 100.0, 2)
```

#### 2. Target Mode Mapping
```python
def get_target_internal_mode(year: int) -> int:
    """Resolves required hardware internalMode phase from target year."""
    if year < 2000:
        return 1
    elif 2000 <= year <= 2150:
        return 2
    elif 2151 <= year <= 2300:
        return 3
    else:
        return 4
```

#### 3. LLM Dynamic Stabilization Resolver (`services/stabilization_service.py`)
```python
async def resolve_stabilization(
    api_hint: str,
    target_date: str,
    model: str = "gemini-3.5-flash-lite",
    thinking_level: str = "low",
) -> str | int:
    """Interprets conversational temporal distortion hints using Vertex AI."""
    prompt = f"""You are the CHRONOS-P1 Temporal Stabilization Coprocessor.
Target Date: {target_date}
Central API Hint: "{api_hint}"

Extract or determine the exact stabilization parameter value required by the device.
Return strictly the required stabilization value."""
    # Invokes Vertex AI via google-genai SDK with Pydantic structured output
    ...
```

#### 4. Master Trajectory State Machine (`services/trajectory_orchestrator.py`)
1. **Initialize Mission:** Ensure device is in `standby` via Cockpit. Fetch `getConfig` from `/verify` to assert initial baseline present date (`2026-09-29`) and battery (`1/3`).
2. **Phase 1: Jump to 2238-11-05 (Battery Procurement)**
   - Director calls `/verify` to set `day=5`, `month=11`, `year=2238`, `syncRatio=0.82`.
   - Director reads stabilization hint, invokes Gemini 3.5 Flash Lite, configures `stabilization`.
   - Director calls Cockpit `POST /controls`: `{ pta: false, ptb: true, pwr: 91, mode: "active" }`.
   - Director calls Cockpit `POST /activate-jump`: `{ target_imode: 3 }`.
   - Cockpit polls DOM for `imode == 3` and `flux == 100%`, clicks glowing sphere.
   - Central updates battery to `3/3` (`batteryStatus: "3/3"`).
3. **Phase 2: Jump to 2026-09-29 (Return to Baseline Present)**
   - Director sets Cockpit mode to `standby`.
   - Director calls `/verify` to set `day=29`, `month=9`, `year=2026`, `syncRatio=0.79`.
   - Director resolves and configures `stabilization`.
   - Director calls Cockpit `POST /controls`: `{ pta: true, ptb: false, pwr: 28, mode: "active" }`.
   - Director calls Cockpit `POST /activate-jump`: `{ target_imode: 2 }`.
   - Cockpit waits for `imode == 2`, clicks sphere. Battery transitions to `2/3`.
4. **Phase 3: Time Tunnel to 2024-11-12 (Rendezvous with Rafał)**
   - Director sets Cockpit mode to `standby`.
   - Director calls `/verify` to set `day=12`, `month=11`, `year=2024`, `syncRatio=0.54`.
   - Director resolves and configures `stabilization`.
   - Director calls Cockpit `POST /controls`: `{ pta: true, ptb: true, pwr: 19, mode: "active" }` (Both ports ON for Tunnel!).
   - Director calls Cockpit `POST /activate-jump`: `{ target_imode: 2 }`.
   - Cockpit waits for `imode == 2`, clicks sphere.
   - Central returns `code: 13` and `flag: "{FLG:...}"`.
   - Mission marked COMPLETE.

---

### Infrastructure / Deployment

* **Project ID:** `af-aidevs`
* **Region:** `europe-west1` (or `global` for Vertex AI model endpoints)
* **Terraform Module:** Defined under `terraform/` using `modules/cloud_run`:
  - `cr-s05e05-director`:
    - Service Account: `sa-cr-s05e05-director`
    - Roles: `roles/aiplatform.user`, `roles/bigquery.dataEditor`, `roles/run.invoker`
    - Resources: 512 MiB RAM, 1 vCPU, concurrency 80
  - `cr-s05e05-cockpit`:
    - Service Account: `sa-cr-s05e05-cockpit`
    - Roles: `roles/secretmanager.secretAccessor`
    - Resources: 2 GiB RAM, 2 vCPU, concurrency 10
* **Networking:** Private Cloud Run ingress (`public = false` for Cockpit, invocable strictly by Director service account).

---

## Cross-Cutting Concerns

### Security
* **Zero Hardcoded Endpoints:** External endpoints (`$AIDEVS_API_VERIFY`, `$AIDEVS_TIMETRAVEL_PREVIEW_URL`) and `AIDEVS_API_KEY` stored exclusively in GCP Secret Manager.
* **IAM Service-to-Service Authentication:** Director generates GCP OIDC identity tokens using Google Auth libraries (`google.auth.transport.requests.Request()`) targeted at Cockpit's Cloud Run URI.
* **Flag Redaction:** Flags captured during runs are masked in public logs and documentation (`{FLG:...}`).

### Observability
* **Granular Entity Progress Logging:** Cockpit logs individual DOM step changes (e.g. `[Cockpit] Port PT-B engaged [PASS]`, `[Cockpit] PWR slider set to 91 [PASS]`, `[Cockpit] Flux Density 100% verified [PASS]`).
* **BigQuery Streaming:** Every A2A payload, configuration step, and API error is streamed to `af-aidevs.s05e05.audit`.
* **Zero Binary Telemetry:** No screenshots or binary payloads dumped to Cloud Logging or BigQuery.

### Error Handling / Resilience
* **Standby Lock Protection:** Director verifies device is in `standby` before dispatching `action: "configure"`.
* **Adaptive Phase Timeout:** Cockpit enforces a 25-second timeout waiting for `internalMode` rotation. If missed, it retries on the subsequent rotation cycle up to 3 times before raising `TemporalPhaseTimeoutError`.
* **Emergency Reset Protocol:** If battery reaches `0/3` or an unrecoverable desynchronization occurs, Director dispatches `action: "reset"` to restore factory baseline.

### Performance / Scalability
* **A2A In-Region Latency:** Direct Cloud Run to Cloud Run within `europe-west1` averages 12–25 ms.
* **Cold Start Strategy:** Director warms up Cockpit via `GET /health` upon receiving `POST /run` before starting temporal calculations.

---

## Edge Cases and Constraints

### Edge Cases
1. **Mid-Flight Battery Exhaustion:** Attempting to engage both `PT-A` and `PT-B` when battery is $< 60\%$ triggers a browser alert toast. Cockpit validates battery telemetry before engaging tunnel mode.
2. **Phase Window Race Condition:** If `internalMode` rotates away at the exact millisecond of clicking the sphere, Central returns a phase error. Cockpit catches this error and waits for the next cycle.
3. **Ambiguous Stabilization Advice:** If API hint is humorous or metaphorical, Gemini 3.5 Flash Lite uses semantic reasoning to deduce the numerical compensation.

### Constraints
1. **No Local CLI:** Must deploy and run on Cloud Run.
2. **Chromium in Container:** Dockerfile for `cr-s05e05-cockpit` must install Playwright and required Debian Linux libraries (`libnss3`, `libatk1.0-0`, etc.).

---

## Implementation Plan

### Phases / Milestones

| Phase | Scope | Deliverable |
| :--- | :--- | :--- |
| **Phase 1: Schemas & Temporal Math** | Pydantic models for A2A and Central API; `temporal_table.py` with 1000-year table; `sync_ratio` calculator. | Unit test suite passing 100%. |
| **Phase 2: Cockpit Service (`cr-cockpit`)** | FastAPI app with Playwright browser manager; endpoints `/controls`, `/telemetry`, `/activate-jump`. | Mocked and headless integration tests. |
| **Phase 3: Director Service (`cr-director`)** | State machine, `/verify` client, Gemini stabilization resolver, A2A client, BigQuery audit streaming. | Director integration tests with mocked Cockpit. |
| **Phase 4: Terraform & IAM Registration** | Register both services in `terraform/variables.tf`, configure service accounts and `roles/run.invoker`. | Terraform manifests ready. |
| **Phase 5: Cloud Deployment & Live Execution** | Deploy both services to Cloud Run, trigger `POST /run`, capture `{FLG:...}`. | Mission complete with flag verification. |

---

## Implementation Spec

### File Structure
```
lessons/s05e05-nowa-rzeczywistosc/task/
├── BRD.md
├── ADR.md
├── PRD.md
├── cr-s05e05-director/
│   ├── .dockerignore
│   ├── .gcloudignore
│   ├── .python-version
│   ├── Dockerfile
│   ├── cloudbuild.yaml
│   ├── pyproject.toml
│   ├── config.py
│   ├── main.py
│   ├── schemas.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audit_service.py
│   │   ├── central_api_service.py
│   │   ├── cockpit_client.py
│   │   ├── stabilization_service.py
│   │   ├── temporal_math.py
│   │   ├── temporal_table.py
│   │   └── trajectory_orchestrator.py
│   └── tests/
│       ├── __init__.py
│       ├── test_schemas.py
│       ├── test_temporal_math.py
│       └── test_trajectory.py
└── cr-s05e05-cockpit/
    ├── .dockerignore
    ├── .gcloudignore
    ├── .python-version
    ├── Dockerfile
    ├── cloudbuild.yaml
    ├── pyproject.toml
    ├── config.py
    ├── main.py
    ├── schemas.py
    ├── services/
    │   ├── __init__.py
    │   └── browser_actuator.py
    └── tests/
        ├── __init__.py
        └── test_schemas.py
```

### Technology Stack
* **Language & Runtime:** Python `==3.13.5` (`requires-python = "==3.13.5"`).
* **Package Manager:** `uv` with pinned precise versions (alphabetically sorted).
* **Director Dependencies (`cr-s05e05-director`):**
  - `fastapi == 0.115.11`
  - `google-auth == 2.38.0`
  - `google-cloud-bigquery == 3.29.0`
  - `google-genai == 1.5.0`
  - `httpx == 0.28.1`
  - `pydantic == 2.10.6`
  - `uvicorn == 0.34.0`
* **Cockpit Dependencies (`cr-s05e05-cockpit`):**
  - `fastapi == 0.115.11`
  - `playwright == 1.50.0`
  - `pydantic == 2.10.6`
  - `uvicorn == 0.34.0`

### Step-by-Step Implementation Order
1. **Cockpit Schemas & Actuator:** Build `cr-s05e05-cockpit` Pydantic models and Playwright automation logic for port toggling, slider movement, and sphere click detection.
2. **Director Temporal Engine:** Build `temporal_math.py`, `temporal_table.py`, and `central_api_service.py`.
3. **Stabilization Service:** Build `stabilization_service.py` integrating Vertex AI Gemini 3.5 Flash Lite (`thinking_level="low"`).
4. **Trajectory Orchestrator & A2A Client:** Wire the 3-phase state machine with Google Cloud IAM OIDC bearer token injection.
5. **FastAPI Endpoints:** Implement `@app.post("/run")` on Director and A2A endpoints on Cockpit.
6. **Container Scaffolding & Quality Gates:** Ensure `Dockerfile`, `cloudbuild.yaml`, `.dockerignore`, `.gcloudignore` match standards. Run `ruff check`, `ruff format`, `mypy`, and `pytest`.
7. **Terraform Registration:** Register `cr-s05e05-director` and `cr-s05e05-cockpit` in `terraform/variables.tf`.

---

### Acceptance Criteria (Testable)

* [ ] `test_temporal_math.py` validates `syncRatio`:
  - `2238-11-05` evaluates to exactly `0.82`.
  - `2026-09-29` evaluates to exactly `0.79`.
  - `2024-11-12` evaluates to exactly `0.54`.
* [ ] `PWR_TABLE` correctly matches ACME specifications ($2238 \to 91$, $2026 \to 28$, $2024 \to 19$).
* [ ] Cockpit service passes headless Playwright tests setting switches, sliders, and reading telemetry.
* [ ] Director service properly authenticates to Cockpit via Google Cloud IAM OIDC.
* [ ] `cr-s05e05-director` and `cr-s05e05-cockpit` build cleanly in Cloud Build (`cloudbuild.yaml`).
* [ ] BigQuery telemetry streaming records all mission events to `af-aidevs.s05e05.audit`.
* [ ] Execution of `POST /run` traverses all 3 phases and captures the mission flag `{FLG:...}`.
