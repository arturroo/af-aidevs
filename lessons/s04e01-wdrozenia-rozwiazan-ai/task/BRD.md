# Business Requirements Document (BRD) - S04E01: okoeditor

## Overview
The objective of this task (`okoeditor`) is to manipulate operational intelligence and incident tracking records inside the authoritarian surveillance system known as **Centrum Operacyjne OKO** without being detected. 

Following an envoy mission to the survivor city of Skolwin where critical wind turbine components were negotiated, the regime's total surveillance network detected irregular movements (a rocket transit across the wasteland). Azazel's resistance gained phished operator credentials to the OKO surveillance panel. However, directly modifying data in the web user interface will immediately trigger intrusion alarms and sever access. Instead, the modifications must be covertly executed via Centrala's backend API (`$AIDEVS_VERIFY`). The agent must inspect the system, discover the API capabilities via `help`, execute three specific data manipulation operations to cover tracks in Skolwin and create a diversion in Komarowo, and finally execute the completion signal (`done`) to obtain the verification flag.

## Requirements

### Functional Requirements
1. **API Discovery & Action Introspection:**
   - Centrala provides a backdoor API at `$AIDEVS_VERIFY` dedicated to `okoeditor`.
   - The agent initiates communication by querying the `help` action:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "okoeditor",
       "answer": {
         "action": "help"
       }
     }
     ```
   - The returned help documentation describes available actions, resource identifiers, query parameters, and update schemas.

2. **Web Panel Read-Only Inspection (Optional/Reconnaissance):**
   - A web interface exists at `$AIDEVS_OKO_PANEL_URL`.
   - Authentication credentials:
     - Login: `Zofia`
     - Password: `Zofia2026!`
     - Key: `$AIDEVS_API_KEY`
   - **CRITICAL RESTRICTION:** The agent/user must **NEVER modify or submit changes directly through the web UI**. The web interface is strictly for visual inspection and verification. All mutations must occur via the Centrala API.

3. **Required Data Mutations (Core Objectives):**
   - **Objective 1 - Reclassify Skolwin Incident Report:**
     - Locate the surveillance report concerning the city of Skolwin.
     - Alter its category / classification so that instead of reporting vehicles and human presence, it classifies the incident as wildlife / animal activity.
   - **Objective 2 - Complete & Update Skolwin Task:**
     - In the task registry, locate the open operational task associated with Skolwin.
     - Mark this task as completed / resolved.
     - Update its content/notes to state that animals (e.g. beavers / bobry) were sighted in the area.
   - **Objective 3 - Plant Diversion Incident in Komarowo:**
     - To distract surveillance operators away from Skolwin, create/inject a new incident report.
     - The report must indicate human movement / activity detected near the uninhabited town of **Komarowo**.
   - **Objective 4 - Submit Verification Action:**
     - Once all three modifications are successfully applied, execute the final verification payload:
       ```json
       {
         "apikey": "$AIDEVS_API_KEY",
         "task": "okoeditor",
         "answer": {
           "action": "done"
         }
       }
       ```
     - On successful validation, Centrala returns the course flag `{FLG:...}`.

### Special Exceptions & Guardrails
- **Zero UI Mutation:** Any POST/PUT/PATCH or form submission performed directly on `$AIDEVS_OKO_PANEL_URL` will blow the cover and revoke access.
- **Idempotency & State Tracking:** Modifications should be verified before triggering `done` (either via API query actions or reading back the records).
- **Zero-Pollution Telemetry:** All audit logs, Cloud Logging events, and BigQuery telemetry must strictly mask API keys, sensitive tokens, and credentials.
- **Course Flag Redaction:** Course flags `{FLG:...}` must be extracted and reported to the user without hardcoding or committing into git history.

## System & Token Constraints
- **Primary LLM Standard:** Gemini 3.8 Flash (`gemini-3.8-flash`) via Vertex AI (`thinking_level="low"`) for parsing API help documentation, generating schema mutations, and synthesizing diversion report descriptions.
- **Dual Framework Requirement:** Both **LangChain** (`1.2.15` via `create_agent`) and **Google ADK** (`1.33.0` via `Agent` and `Runner`) must be implemented with 100% functional parity.
- **Standard Shared Package:** Leverage `af_aidevs` shared package for BigQuery audit logging (`af_aidevs.audit.bigquery`) and MCP connectivity (`af_aidevs.clients.mcp`).

## Data Input & External Resources
- Backdoor Centrala API: `$AIDEVS_VERIFY`
- Surveillance Web Panel: `$AIDEVS_OKO_PANEL_URL`
- Centrala API Authentication Key: `$AIDEVS_API_KEY`

## API Integration

### 1. API Help & Discovery Request (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "okoeditor",
    "answer": {
      "action": "help"
    }
  }
  ```

### 2. Mutation Actions Request Pattern (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "okoeditor",
    "answer": {
      "action": "<action_name>",
      "...": "..."
    }
  }
  ```

### 3. Verification & Completion Request (`$AIDEVS_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "okoeditor",
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
- `AIDEVS_OKO_PANEL_URL`: Web panel URL for operator reconnaissance.
- `GOOGLE_CLOUD_PROJECT`: GCP Project ID (`af-aidevs`).
- `GOOGLE_CLOUD_LOCATION`: Vertex AI location (`global`).

## Verification & Acceptance Criteria
1. The agent queries `$AIDEVS_VERIFY` with `action: help` and resolves the full suite of manipulation commands.
2. The incident report for Skolwin is reclassified from human/vehicle activity to animal activity.
3. The task related to Skolwin is marked as done with description documenting animal sightings.
4. A diversion incident report about human activity near Komarowo is registered.
5. Invoking `action: done` completes verification and retrieves the `{FLG:...}` flag.
