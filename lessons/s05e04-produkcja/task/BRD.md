# Business Requirements Document (BRD) - S05E04: Autonomous Rocket Navigation & OKO Radar Neutralization (goingthere)

## 1. Overview & Business Objectives

In the final push of the resistance operations, an automated ground-skimming rocket must be dispatched to reach the resistance stronghold in Grudziądz. Navigating through the badlands is extremely hazardous: active radar jamming blankets the entire flight path, cloaking deadly rock formations immediately ahead and rendering pre-mapped trajectory calculation impossible.

Simultaneously, the totalitarian regime's automated defense network, known as **OKO**, actively tracks ground movement across the sector. If the rocket moves while actively targeted by an OKO radar tracking station without neutralizing the beacon, an interceptor missile is launched immediately, destroying the rocket.

Fortunately, resistance engineers have tapped into:
1. **OKO Frequency Scanner API:** Detecting whether the rocket is currently locked onto by an OKO tracking station, and accepting a cryptographic neutralization hash to disarm the lock before movement.
2. **Short-Range Tactical Radio API:** Broadcasting cryptic, often nautical or colloquial descriptions of rock positions directly ahead in the subsequent column.
3. **Flight Control Verification Gateway:** Dispatching directional thrust commands (`go`, `left`, `right`) and tracking rocket progression across a discrete grid.

The business objective of the `goingthere` task is to engineer an autonomous, fault-tolerant flight navigation microservice capable of:
- Interfacing with the tactical flight control API (`$AIDEVS_API_VERIFY`) to initiate missions and execute step-by-step vector thrusts.
- Proactively querying the frequency scanner (`$AIDEVS_API_FREQUENCY_SCANNER`) before every move, repairing jammed/distorted telemetry packets, computing SHA-1 neutralization hashes, and disarming radar locks.
- Listening to tactical radio transmissions (`$AIDEVS_API_GETMESSAGE`), interpreting cryptic maritime and spatial language to pinpoint rock locations in upcoming columns.
- Navigating the $3 \times 12$ sector grid safely from column 1 (row 2) to column 12 (target base row) while staying within vertical boundaries, avoiding all rock obstacles, surviving random upstream API failures via exponential backoff, and securing the mission completion flag (`{FLG:...}`).

---

## 2. Grid Topology & Rocket Kinematics

### 2.1 Coordinate Space & Dimensions
The airspace corridor is modeled as a discrete 2D grid:
- **Dimensions:** 3 rows $\times$ 12 columns.
  - Rows: Discrete vertical channels: Row 1 (top / high), Row 2 (middle / center), Row 3 (bottom / low).
  - Columns: Longitudinal progression: Column 1 (starting gate) to Column 12 (destination sector).
- **Spawn Coordinates:** Column 1, Row 2 (fixed start position).
- **Destination:** Column 12, Row $R_{\text{target}}$ (where $R_{\text{target}} \in \{1, 2, 3\}$ is dynamically provided in the `start` payload).
- **Obstacle Density:** Exactly **one rock obstacle** per column across columns 1 through 12.

### 2.2 Propulsion & Directional Commands
The rocket engine enforces mandatory forward momentum. Every executed movement advances the rocket exactly **one column to the right** ($X_{t+1} = X_t + 1$):

| Command | Lateral / Vertical Effect | Longitudinal Effect | Coordinate Transformation |
| :--- | :--- | :--- | :--- |
| `start` | Initializes mission state, resets grid, spawns rocket | Resets to Column 1 | $(X, Y) \to (1, 2)$ |
| `go` | Maintains current row altitude | Advances $+1$ column | $(X, Y) \to (X + 1, Y)$ |
| `left` | Ascends to higher row (up / towards row 1) | Advances $+1$ column | $(X, Y) \to (X + 1, Y - 1)$ |
| `right` | Descends to lower row (down / towards row 3) | Advances $+1$ column | $(X, Y) \to (X + 1, Y + 1)$ |

### 2.3 Lethal Failure Conditions & Boundary Constraints
A single miscalculation terminates the flight, requiring a complete mission restart from `start`:
1. **Rock Collision:** Moving into a cell $(X, Y)$ containing a rock formation causes catastrophic structural collapse.
2. **Corridor Boundary Violation:** Attempting to steer outside the corridor grid ($Y < 1$ or $Y > 3$) results in immediate terrain impact.
3. **Active Radar Evasion Failure:** Executing a movement command while targeted by an active OKO radar beacon results in an anti-rocket missile strike.

---

## 3. OKO Frequency Scanner & Radar Neutralization Protocol

### 3.1 Radar Interrogation Endpoint
Before **every single movement**, the flight controller must poll the OKO frequency scanner via HTTP GET:
- **Method:** `GET`
- **Target:** `$AIDEVS_API_FREQUENCY_SCANNER?key=$AIDEVS_API_KEY`
- **Possible Responses:**
  1. **Clear Airspace:** Returns a text confirmation indicating safe passage (e.g., `"It's clear!"`). In this state, no neutralization is required; the rocket may proceed to radio telemetry and movement.
  2. **Active Radar Lock:** Returns a payload indicating an active OKO radar trap. Contains telemetry including target `frequency` and `detectionCode`.
  3. **Upstream Transient Faults:** The OKO electronic warfare system injects synthetic network interference; the endpoint intermittently returns HTTP errors or malformed connection drops even on valid requests.

### 3.2 Distorted & Jammed Telemetry Recovery
Under active jamming, radar lock packets returned by the scanner are deliberately distorted, corrupting standard JSON formatting (e.g., missing quotes, extraneous control characters, truncated brackets, or noise tokens).
- **Requirement:** The microservice must implement a resilient telemetry parser (utilizing dirty-JSON regex extractors and fallback parsing) to reliably extract:
  - `frequency`: Numeric identifier of the targeting radar beacon (integer or float).
  - `detectionCode`: Alphanumeric token representing the radar lock signature.

### 3.3 Cryptographic Disarm Protocol
When an active radar lock is detected, the flight system must neutralize the targeting beacon before moving:
- **Method:** `POST`
- **Target:** `$AIDEVS_API_FREQUENCY_SCANNER`
- **Payload Schema:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "frequency": 123,
    "disarmHash": "<computed-sha1-hash>"
  }
  ```
- **Disarm Hash Computation:**
  $$\text{disarmHash} = \text{SHA1}(\text{detectionCode} + \text{"disarm"})$$
  *(Standard lowercase 40-character hexadecimal representation).*
- **Confirmation:** The flight controller must verify the disarming confirmation from the scanner before issuing any movement command.

---

## 4. Tactical Radio Telemetry & Nautical Hint Interpretation

### 4.1 Radio Interrogation Endpoint
Because forward line-of-sight is blinded by particle scattering, the rocket listens to encrypted tactical radio broadcasts to ascertain the rock obstacle location in the impending column ($X + 1$):
- **Method:** `POST`
- **Target:** `$AIDEVS_API_GETMESSAGE`
- **Payload Schema:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY"
  }
  ```
- **Response Schema:**
  ```json
  {
    "hint": "<cryptic-english-transmission>"
  }
  ```

### 4.2 Semantic Interpretation & Nautical Jargon Resolution
Radio hints are communicated in English, frequently utilizing maritime, naval, or colloquial directional terminology relative to the rocket's current heading:
- **Spatial Orientations:**
  - *Dead Ahead / Center / Straight / Bow:* Rock is in the same row as current rocket altitude ($Y_{\text{rock}} = Y_{\text{rocket}}$).
  - *Port / Left / Top / High / Above:* Rock is located in the row above current altitude ($Y_{\text{rock}} < Y_{\text{rocket}}$).
  - *Starboard / Right / Bottom / Low / Below:* Rock is located in the row below current altitude ($Y_{\text{rock}} > Y_{\text{rocket}}$).
- **Interpretation Engine:**
  - A specialized LLM-backed cognitive parser (utilizing Vertex AI Gemini 3.8 Flash with low thinking level and strict structured schema) or a resilient deterministic nautical lexicon must decode the transmission into an absolute grid coordinate for the obstacle in column $X + 1$:
    $$Y_{\text{rock}} \in \{1, 2, 3\}$$

---

## 5. Path Planning & Autonomous Decision Engine

### 5.1 Dynamic Obstacle Avoidance & Corridor Reachability
With the rock row $Y_{\text{rock}}$ in column $X + 1$ identified:
- **Available Actions from Row $Y$:**
  - Candidate 1: `go` $\to$ Target row $Y$ (Valid if $Y \neq Y_{\text{rock}}$)
  - Candidate 2: `left` $\to$ Target row $Y - 1$ (Valid if $Y > 1$ and $Y - 1 \neq Y_{\text{rock}}$)
  - Candidate 3: `right` $\to$ Target row $Y + 1$ (Valid if $Y < 3$ and $Y + 1 \neq Y_{\text{rock}}$)

### 5.2 Destination Convergence Heuristic (Grudziądz Trajectory)
When multiple candidate thrusts are safe:
1. **Target Altitude Proximity:** Prioritize actions that minimize the vertical distance $|Y_{\text{target}} - Y_{\text{candidate}}|$ to the Grudziądz base row, especially as the rocket nears Column 12.
2. **Dead-End Elimination:** Ensure that choosing a row does not trap the rocket against boundary walls when subsequent rock predictions force vertical transitions.
3. **Deterministic Verification:** In a 3-row grid with exactly 1 rock per column, at least one and often two vertical channels are safe in any column transition.

---

## 6. Functional Workflow Lifecycle

The end-to-end autonomous navigation cycle operates as a deterministic finite state machine (FSM):

```
       +---------------------------------------------+
       |                  [START]                    |
       |  POST $AIDEVS_API_VERIFY {"command":"start"} |
       +---------------------------------------------+
                              |
                              v
                 Record Start State & Destination
                 (Col 1, Row 2 -> Col 12, Row Target)
                              |
                              v
        +-------------------->+
        |                     |
        |      Col == 12 & Row == Target ? ---[YES]---> CLAIM FLAG & FINISH!
        |                     | [NO]
        |                     v
        |      +--------------------------------+
        |      | 1. Query Frequency Scanner     |
        |      |    (GET with exponential retry)|
        |      +--------------------------------+
        |                     |
        |          Active Radar Trap Detected?
        |             /              \
        |          [YES]             [NO]
        |           /                  \
        |    +--------------------+     |
        |    | 2. Parse Jammed    |     |
        |    |    Telemetry       |     |
        |    | 3. Compute SHA1    |     |
        |    |    disarmHash      |     |
        |    | 4. POST Disarm     |     |
        |    +--------------------+     |
        |           \                  /
        |            v                v
        |      +--------------------------------+
        |      | 5. Query Radio Hint API        |
        |      |    (POST with retry)           |
        |      +--------------------------------+
        |                     |
        |      +--------------------------------+
        |      | 6. Decode Rock Position        |
        |      |    (LLM / Semantic Resolver)   |
        |      +--------------------------------+
        |                     |
        |      +--------------------------------+
        |      | 7. Compute Optimal Move        |
        |      |    (go / left / right)         |
        |      +--------------------------------+
        |                     |
        |      +--------------------------------+
        |      | 8. Dispatch Thrust Command     |
        |      |    (POST $AIDEVS_API_VERIFY)   |
        |      +--------------------------------+
        |                     |
        +---------------------+ (Advance Column: X = X + 1)
```

---

## 7. System & Token Constraints

1. **Deterministic Retry & Resilience:**
   - The scanner API and radio API are explicitly designed to introduce random transient failures and HTTP drops.
   - All external HTTP calls must use an exponential backoff policy (minimum 3–5 retries with randomized jitter).
2. **Latency & Execution Budget:**
   - Cloud Run service execution timeout is configured to 600s (`timeout = "600s"`).
   - Across 11 movement transitions, total HTTP latency (including radar interrogations, disarm post, radio hint, and verify calls) averages 15–30 seconds.
3. **LLM Cognitive Overhead & Token Optimization:**
   - Radio hint parsing is lightweight ($\approx 50$ prompt tokens per column, 11 calls $\approx 550$ input tokens total).
   - Gemini 3.8 Flash (`gemini-3.8-flash`) with `thinking_level="low"` provides near-zero latency (< 600ms per semantic call) and sub-cent economics.

---

## 8. Security & Environment Setup

In accordance with strict security standards, no external service URLs are hardcoded in source code or documentation:

### Required Environment Variables
| Variable Name | Description | Environment |
| :--- | :--- | :--- |
| `AIDEVS_API_KEY` | Course platform authentication token | Secret Manager / `.env` |
| `AIDEVS_API_VERIFY` | Flight command verification gateway endpoint | Secret Manager / `.env` |
| `AIDEVS_API_GETMESSAGE` | Tactical radio hint broadcast endpoint | Secret Manager / `.env` |
| `AIDEVS_API_FREQUENCY_SCANNER` | OKO frequency scanner & radar disarming endpoint | Secret Manager / `.env` |
| `AIDEVS_GOINGTHERE_PREVIEW_URL` | Visual flight inspection URL (for web UI preview) | Optional / Reference |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID (`af-aidevs`) | Deployed env / `.env` |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI model deployment region (`global`) | Deployed env / `.env` |
| `GEMINI_MODEL` | Primary vision/language workhorse (`gemini-3.8-flash`) | Deployed env / `.env` |

---

## 9. Acceptance Criteria & Verification Protocol

1. **Radar Neutralization Verification:**
   - Scanner responses containing "It's clear!" are recognized immediately without disarming calls.
   - Jammed scanner JSON responses containing noise or syntax defects are successfully cleaned and parsed to obtain `frequency` and `detectionCode`.
   - The SHA1 hash is computed accurately with the trailing `"disarm"` string and submitted to `$AIDEVS_API_FREQUENCY_SCANNER`.
2. **Radio Hint Interpretation Verification:**
   - Test suite verifies maritime phrases (e.g., "starboard", "port side", "bearing down the middle", "dead ahead", "shoals on the left") correctly map to the corresponding rock row.
3. **Flight Trajectory Integrity:**
   - Rocket never executes an out-of-bounds move ($Y \in \{1, 2, 3\}$ at all times).
   - Rocket never steps into the rock row of the impending column.
   - Rocket converges on the target row at Column 12.
4. **Mission Success & Flag Retrieval:**
   - The system successfully reaches Grudziądz (Column 12, Target Row) and extracts the course flag (`{FLG:...}`).
   - Audit event telemetry is streamed to BigQuery dataset `s05e04`.
