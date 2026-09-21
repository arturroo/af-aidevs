# Business Requirements Document (BRD) - S04E02: windpower

## Overview
The objective of this task (`windpower`) is to program an optimal and safe operational schedule for a newly acquired wind turbine to generate the electricity required to start the power plant's control computers while protecting the turbine from destructive atmospheric storms.

Following the acquisition of wind turbine components, Azazel's resistance team is operating under severe constraints: the turbine's backup battery is running on critical reserves and no compatible charger is available. Consequently, the turbine's control system can only be placed into a live configuration / service window for at most **40 seconds**. During this 40-second window, the system must interact with Centrala's API (`$AIDEVS_VERIFY`), query asynchronous diagnostic and telemetry reports (weather forecast, turbine specifications, power plant energy deficits), calculate protective feathering configurations for storm hours, determine the first viable power production window meeting the energy deficit, generate cryptographic unlock codes via `unlockCodeGenerator`, execute a turbine self-test (`turbinecheck`), transmit the schedule (`config`), and submit the completion signal (`done`) to obtain the verification flag.

## Requirements

### Functional Requirements

1. **API Discovery & Help Inspection:**
   - Centrala provides an interactive task API at `$AIDEVS_VERIFY` dedicated to `windpower`.
   - The system initiates discovery by querying `help` to inspect available actions and async routines:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "windpower",
       "answer": {
         "action": "help"
       }
     }
     ```
   - Documentation describes async queueable actions, parameters, response formats, and generator functions.

2. **Asynchronous Request Queueing & Polling Pattern:**
   - Diagnostic and telemetry functions on the turbine/centrala run asynchronously.
   - Calling an action queues it for background execution.
   - Results are retrieved by issuing the `getResult` action.
   - **Crucial Rule:** Responses from `getResult` are delivered in random/non-deterministic order, and each generated report can be retrieved **strictly once** (one-time read).
   - Because of the strict 40-second time budget, sequential/blocking execution will fail; calls must be pipelined or queued concurrently.

3. **Service Window Lifecycle Management:**
   - The turbine service window must be initiated by executing `start`:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "windpower",
       "answer": {
         "action": "start"
       }
     }
     ```
   - Initiating `start` starts the hardware countdown timer (40 seconds maximum lifetime). All queries, computations, testing, configuration submissions, and final completion signals must finish within this window.

4. **Atmospheric & Weather Analysis (Turbine Defense):**
   - Retrieve the weather forecast and turbine physical tolerances / durability limits.
   - Identify every hour where predicted wind speed exceeds the structural durability limit of the turbine (definition of a gale / storm).
   - For every storm hour, activate the protective defense mode:
     - Set pitch angle such that blades offer no aerodynamic resistance (feathered/flagged position, e.g. 90° or 0° as defined by turbine specs).
     - Set `turbineMode` to non-productive safe state (`idle`).
   - **Reset Guardrail:** The turbine rotor resets to standard pitch approximately one hour after each storm period. If a storm spans multiple consecutive hours, each storm hour must have an explicit protective configuration entry.

5. **Power Generation Window Identification:**
   - Retrieve the power plant's real-time energy deficit requirements (which fluctuate over time).
   - Evaluate weather forecast windows where wind conditions allow producing the required power without exceeding safe limits.
   - Locate the **earliest possible time window** that satisfies the required power quota.
   - Configure the turbine for power generation:
     - Set `pitchAngle` to optimal power production angle.
     - Set `turbineMode` to `"production"`.

6. **Cryptographic Signing via `unlockCodeGenerator`:**
   - Every individual configuration timestamp entry requires a valid cryptographic signature (`unlockCode`).
   - Signatures are acquired by querying the `unlockCodeGenerator` function with the required parameters (e.g., MD5-based or function-derived token).

7. **Turbine Health Self-Test (`turbinecheck`):**
   - Prior to final submission (`done`), the system must run a mandatory hardware verification test:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "windpower",
       "answer": {
         "action": "turbinecheck"
       }
     }
     ```

8. **Schedule Transmission (`config`):**
   - Submit configurations to Centrala using single or bulk format. Bulk transmission is strongly preferred to conserve round-trips and time:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "windpower",
       "answer": {
         "action": "config",
         "configs": {
           "YYYY-MM-DD HH:00:00": {
             "pitchAngle": 90,
             "turbineMode": "idle",
             "unlockCode": "signature-token-1"
           },
           "YYYY-MM-DD HH:00:00": {
             "pitchAngle": 45,
             "turbineMode": "production",
             "unlockCode": "signature-token-2"
           }
         }
       }
     }
     ```
   - **Timestamp Rule:** In all configured hours, minutes and seconds must strictly be formatted as zeros (`HH:00:00`).

9. **Verification & Completion (`done`):**
   - Finalize the schedule by issuing `action: "done"`:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "windpower",
       "answer": {
         "action": "done"
       }
     }
     ```
   - On success within the 40-second window, Centrala returns the verification flag `{FLG:...}`.

### Special Exceptions & Guardrails

- **Strict 40-Second Hard Deadline:** Total elapsed execution time from `action: "start"` to successful response of `action: "done"` must strictly not exceed 40 seconds.
- **Pipelined Asynchronous IO:** Linear, sequential polling is strictly prohibited as it breaches the 40s timeout. All independent queueing requests must be fired concurrently.
- **Single-Consumption Reports:** Because `getResult` returns each completed report only once, the result collector must demultiplex and route incoming reports to their appropriate state parsers.
- **Consecutive Storm Protection:** Storms lasting multiple continuous hours must each receive explicit protection entries because the turbine auto-resets after one hour.
- **Zero-Pollution Telemetry:** All audit logs, Cloud Logging events, and BigQuery telemetry must strictly mask API keys, sensitive tokens, and credentials.
- **Course Flag Redaction:** Course flags `{FLG:...}` must be captured and reported to the user without hardcoding or committing into git history.

## System & Token Constraints

- **Primary LLM Standard:** Gemini 3.8 Flash (`gemini-3.8-flash`) via Vertex AI (`thinking_level="low"`) for parsing API help documentation, calculating aerodynamic angles if needed, and determining optimal power production formulas.
- **Deterministic Math & Orchestration Engine:** Power deficit calculations, wind speed threshold checks, and unlock code processing should leverage high-performance deterministic Python routines where appropriate to eliminate unnecessary LLM round-trip latency within the critical 40s window.
- **Dual Framework Requirement:** Both **LangChain** (`1.2.15` via `create_agent`) and **Google ADK** (`1.33.0` via `Agent` and `Runner`) must be implemented with 100% functional parity.
- **Standard Shared Package:** Leverage `af_aidevs` shared package for BigQuery audit logging (`af_aidevs.audit.bigquery`).

## Data Input & External Resources

- Centrala Verification & Turbine API: `$AIDEVS_VERIFY`
- Centrala API Authentication Key: `$AIDEVS_API_KEY`

## API Integration

### 1. Help & Introspection Request (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "help"
    }
  }
  ```
- **Discovered API Capabilities:**
  - `start`: Starts a new service window (40-second hardware timer) and initializes task state.
  - `get`: Requests diagnostic and telemetry data with parameter `param` (`"weather"`, `"turbinecheck"`, `"powerplantcheck"`, `"documentation"`).
    - `documentation`: Returned synchronously / directly.
    - `weather`, `turbinecheck`, `powerplantcheck`: Queued asynchronously; results collected via `getResult`.
  - `getResult`: Pops and returns one completed queued response containing `sourceFunction` (e.g. `"weather"`, `"powerplantcheck"`, `"unlockCodeGenerator"`). Retrieved items are removed from queue.
  - `unlockCodeGenerator`: Asynchronously generates digital cryptographic signature (`unlockCode`) for given config. Requires `startDate`, `startHour`, `windMs`, `pitchAngle`. Results collected via `getResult`.
  - `config`: Stores configuration points. Accepts single point or bulk dictionary `configs`. Requires `unlockCode` for every point.
  - `done`: Finalizes validation and returns course flag `{FLG:...}` on success.

### 2. Service Window Initiation Request (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "start"
    }
  }
  ```

### 3. Asynchronous Execution & Result Polling (`$AIDEVS_VERIFY`)
- **Queue Action Method:** `POST`
- **Queue Payload Example:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "get",
      "param": "weather"
    }
  }
  ```
- **Poll Result Method:** `POST`
- **Poll Result Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "getResult"
    }
  }
  ```

### 4. Cryptographic Signature Generation (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "unlockCodeGenerator",
      "startDate": "YYYY-MM-DD",
      "startHour": "HH:00:00",
      "windMs": 14.5,
      "pitchAngle": 90
    }
  }
  ```

### 5. Bulk Configuration Submission (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "config",
      "configs": {
        "YYYY-MM-DD HH:00:00": {
          "pitchAngle": 90,
          "turbineMode": "idle",
          "unlockCode": "<signature>"
        }
      }
    }
  }
  ```

### 6. Final Verification Request (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "windpower",
    "answer": {
      "action": "done"
    }
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
All sensitive credentials and external endpoints must be configured via `.env` and Google Cloud Secret Manager:
- `AIDEVS_API_KEY`: Course authorization token.
- `AIDEVS_VERIFY`: Centrala verification endpoint URL.
- `MCP_WEB_GATEWAY_URL`: Cloud Run MCP Web Gateway URL (Zero Direct Egress).
- `MCP_WORKSPACE_URL`: Cloud Run MCP Workspace URL (persistent storage).
- `GOOGLE_CLOUD_PROJECT`: GCP Project ID (`af-aidevs`).
- `GOOGLE_CLOUD_LOCATION`: Vertex AI location (`global`).

## Verification & Acceptance Criteria
1. The agent inspects `$AIDEVS_VERIFY` with `action: help` prior to launching the countdown to establish all function signatures.
2. The service window is successfully triggered with `action: start`.
3. All asynchronous telemetry calls (weather, power plant requirements, turbine parameters) are queued and drained via `getResult`.
4. High-wind danger hours (> turbine threshold) are detected and feathered (`pitchAngle` safe, `turbineMode: idle`) for every affected consecutive hour.
5. The earliest time window satisfying the energy deficit is calculated and scheduled (`pitchAngle` production, `turbineMode: production`).
6. Valid cryptographic unlock codes are generated for all timestamps via `unlockCodeGenerator`.
7. Hardware self-test `action: turbinecheck` is executed.
8. The schedule is transmitted via `config` (bulk).
9. Completion signal `done` is submitted within the 40-second execution budget, yielding `{FLG:...}`.
