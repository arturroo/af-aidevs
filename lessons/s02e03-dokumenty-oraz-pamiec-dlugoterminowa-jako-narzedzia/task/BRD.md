# Business Requirements Document (BRD) - Task: `failure`

## 1. Overview
Yesterday, a critical failure occurred at the power plant. Technicians initiated system startup around 06:00 in the morning, and the power plant spontaneously shut down just before 22:00. The full diagnostic log file covering the entire operation is massive and exceeds the context window capacity of the Centrala analysis systems.

The objective of this task is to analyze the full operational log, filter out noise, and construct a condensed, multi-line summary of events strictly relevant to the failure (focusing on power generation, cooling systems, water pumps, software systems, and core components). The resulting summary must strictly satisfy a hard ceiling of **1,500 tokens** while retaining essential diagnostic telemetry (date, time, severity level, component identifiers, and key incident descriptions). The condensed log is submitted to Centrala, which provides feedback on missing or ambiguous components, enabling iterative refinement until the technicians validate the diagnostic payload and grant the completion flag (`{FLG:...}`).

---

## 2. Business Objectives
- **Failure Root Cause Compression:** Extract and condense critical operational anomalies, errors, warnings, and protection trips that explain the power plant shutdown between 06:00 and 22:00.
- **Strict Context Optimization:** Ensure the submitted payload does not exceed the **1,500 token limit** enforced by Centrala.
- **Preservation of Key Diagnostic Indicators:** Retain timestamp (`YYYY-MM-DD HH:MM` or `H:MM`), severity tag (e.g., `[CRIT]`, `[WARN]`, `[ERRO]`), and component IDs (e.g., `ECCS8`, `PWR01`, `WTANK07`) while paraphrasing or shortening verbose descriptions.
- **Autonomous Iterative Feedback Loop:** Ingest technician feedback from Centrala responses, dynamically retrieve missing telemetry for flagged components, adjust token density, and re-verify until the solution is accepted.
- **Flag Extraction:** Capture the final confirmation flag (`{FLG:...}`) upon successful technician sign-off.

---

## 3. Data & API Requirements

### 3.1 Input Data
- **Operational Log File:**
  - **Source URL:** `$AIDEVS_FAILURE_DATA_URL` (points to `failure.log` parametrized by `$AIDEVS_API_KEY`).
  - **Format:** Plaintext log file (`.log`).
  - **Structure:** Chronological log entries spanning system startup (~06:00) to shutdown (~22:00), containing normal operating noise (`INFO`) mixed with warnings (`WARN`), errors (`ERRO`), critical alarms (`CRIT`), and system interlocks.

### 3.2 Verification API
Submissions are evaluated by the Centrala verification endpoint:
- **Endpoint:** `$AIDEVS_API_VERIFY`
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload Schema:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "failure",
    "answer": {
      "logs": "[YYYY-MM-DD HH:MM] [SEVERITY] COMPONENT_ID Description...\n[YYYY-MM-DD HH:MM] [SEVERITY] COMPONENT_ID Description..."
    }
  }
  ```
- **Field Specifications:**
  - `logs`: A single multiline string with newline (`\n`) delimiters between entries.

### 3.3 Feedback & Verification Mechanics
- **Success Response:** When the submitted log contains sufficient and accurate event coverage within the token limit, Centrala returns a success confirmation containing the course flag `{FLG:...}`.
- **Technician Feedback Response:** If specific subsystems or root-cause events are missing or insufficiently clear, Centrala returns descriptive feedback identifying the missing components (e.g., specific pumps, tank levels, electrical buses, or cooling loops) and issues that need clarification.
- **Error Handling:** If the payload exceeds 1,500 tokens, the request is rejected immediately by Centrala.

---

## 4. Requirements & Formatting Rules

### 4.1 Log Entry Structure
Every line in the condensed log output must follow a strict, standardized format:
- **Single Event Per Line:** Exactly one event per line (`\n` separated). No multiline wrapping for a single event.
- **Date Format:** `YYYY-MM-DD` (must reflect the actual operating date found in the source logs).
- **Time Format:** `HH:MM` or `H:MM` (preserving chronological order from startup to shutdown).
- **Severity Tag:** Keep standardized brackets such as `[CRIT]`, `[WARN]`, `[ERRO]`, or `[INFO]` where relevant to the incident chain.
- **Component Identifiers:** Mandatory alphanumeric component tags must be preserved verbatim (e.g., `PWR01`, `ECCS8`, `WTANK07`, `PUMP02`, `COOL3`).
- **Paraphrasing & Compression:** Verbose log sentences can and should be summarized or paraphrased, preserving technical fidelity (e.g., "coolant below critical threshold, hard trip initiated").

### 4.2 Subsystem Focus
The analysis must prioritize subsystems that directly impact operational safety and led to the reactor trip:
- Power supply, transformers, and electrical buses (`PWR`, grid ripple, bus faults).
- Reactor cooling systems and emergency core cooling (`ECCS`, coolant temperatures, flow rates).
- Water storage and supply pumps (`WTANK`, `PUMP`, pressure differentials).
- Automation, software controllers, safety interlocks, and trip circuits.

---

## 5. System & Token Constraints
- **Hard Token Limit:** The final condensed log string must be **$\le 1,500$ tokens**.
- **Token Estimation Standard:** Token calculation should use OpenAI compatible tokenizers (e.g., `tiktoken` with `cl100k_base` or `o200k_base`) with a conservative safety margin (e.g., target 1,350–1,450 tokens max) to prevent rejection.
- **Source Log Size:** The source file is large and cannot be loaded directly into a standard LLM prompt without filtering. Efficient search, grep/regex extraction, or hierarchical chunk scanning is necessary to manage latency and cost.

---

## 6. Environment Setup & Security Requirements
All endpoints and sensitive keys must be read exclusively from `.env` files or GCP Secret Manager. No raw URLs or API keys may be committed to version control:

| Environment Variable | Description |
|---|---|
| `AIDEVS_API_KEY` | User API authentication key for AI_Devs |
| `AIDEVS_API_VERIFY` | Central verification endpoint URL |
| `AIDEVS_FAILURE_DATA_URL` | Dedicated data URL for downloading `failure.log` |

---

## 7. Success Criteria
1. Full `failure.log` is successfully retrieved from `$AIDEVS_FAILURE_DATA_URL` and cached locally or in session storage.
2. Anomalous events, warnings, errors, and critical trips are systematically identified across all power plant subsystems.
3. A condensed multiline log string is generated satisfying:
   - One event per line.
   - Date format `YYYY-MM-DD` and time `HH:MM`.
   - Preserved component identifiers and severity tags.
   - Total token count $< 1,500$ tokens.
4. If Centrala returns technician feedback regarding missing components, the system autonomously searches the raw log for those components and updates the condensed log.
5. The verification response returns HTTP 200 with the completion flag `{FLG:...}`.
