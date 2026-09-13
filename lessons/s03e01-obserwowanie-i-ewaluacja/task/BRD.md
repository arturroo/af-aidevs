# Business Requirements Document (BRD) - Task: `evaluation`

## 1. Overview
The Żarnowiec power plant and resistance base infrastructure rely on an array of nearly 10,000 industrial sensors monitoring critical physical systems (water levels, temperatures, electrical voltage supply, pressure, and ambient humidity). Following the recent influx of cooling water into the plant's intake canals, the plant firmware has been producing corrupted sensor logs and erratic telemetry. Furthermore, plant technicians suspect that the monitoring operator is unreliable—frequently fabricating notes, ignoring critical alarms, or falsely logging errors to bypass safety protocols.

The objective is to audit the entire telemetry archive (comprising approximately 10,000 JSON sensor logs), isolate all compromised readings and operator discrepancies, and submit the complete list of anomalous file identifiers (`recheck`) to Centrala's `/verify` endpoint to earn the course completion flag (`{FLG:...}`).

---

## 2. Business Objectives
- **Comprehensive Telemetry Auditing**: Ingest and audit ~10,000 sensor telemetry JSON records from the plant monitoring system archive.
- **Physical Sensor Reading Validation**: Detect physical sensor hardware failures, including readings outside valid operating ranges and "ghost" signals emitted by inactive sensor channels.
- **Human-in-the-Loop Operator Discrepancy Detection**: Identify false negative operator reports (operator reports everything is OK despite corrupted telemetry) and false positive operator reports (operator reports malfunctions or triggers alarms despite telemetry being completely within normal thresholds).
- **Cost-Optimized & Token-Efficient Hybrid Architecture**: Prevent excessive LLM token expenditure by applying deterministic programmatic filtering to physical metrics and leveraging response caching, deduplication, and batching for semantic operator note evaluation.
- **Automated Centrala Verification**: Submit the consolidated list of anomalous file identifiers to Centrala's `/verify` endpoint under task `evaluation`.
- **Zero-Trust Security & Observability**: Ensure all external web access conforms to project egress standards, all audit events stream to BigQuery dataset `s03e01`, and raw flags (`{FLG:...}`) remain confidential and redacted in logs.

---

## 3. Data & API Requirements

### 3.1 Sensor Telemetry Archive
- **Resource**: ZIP archive (`sensors.zip`) containing ~10,000 individual JSON files named numerically (e.g., `0001.json`, `0002.json`, ..., `9999.json`, etc.).
- **Location Variable**: `$AIDEVS_SENSORS_DATA_URL` (points to the external data source provided in lesson context).
- **Schema per JSON file**:
  ```json
  {
    "sensor_type": "temperature/voltage",
    "timestamp": 1774064280,
    "temperature_K": 612,
    "pressure_bar": 0,
    "water_level_meters": 0,
    "voltage_supply_v": 230.4,
    "humidity_percent": 0,
    "operator_notes": "Readings look stable and within expected range."
  }
  ```
- **Field Definitions**:
  - `sensor_type` (*string*): Identifies the active sensor channel or combination of active channels separated by forward slash `/` (e.g., `temperature`, `water`, `pressure`, `voltage`, `humidity`, `voltage/temperature`, `water/pressure/temperature`).
  - `timestamp` (*integer*): Unix epoch timestamp of the reading.
  - `temperature_K` (*number*): Temperature measurement in Kelvin.
  - `pressure_bar` (*number*): Pressure measurement in bars.
  - `water_level_meters` (*number*): Water level measurement in meters.
  - `voltage_supply_v` (*number*): Electrical supply voltage in Volts.
  - `humidity_percent` (*number*): Ambient humidity measurement in percent.
  - `operator_notes` (*string*): Human operator inspection comments written in English.

### 3.2 Sensor Operating Ranges & Norms
All JSON files contain all 5 measurement fields. For any metric whose corresponding sensor is **inactive** (not listed in `sensor_type`), the reading **must strictly equal 0**.

For **active** sensor channels (present in `sensor_type`), valid operational ranges are:
| Sensor Channel | Corresponding Metric Field | Min Valid Value | Max Valid Value | Inactive Expected Value |
| :--- | :--- | :--- | :--- | :--- |
| `temperature` | `temperature_K` | 553.0 K | 873.0 K | 0 |
| `pressure` | `pressure_bar` | 60.0 bar | 160.0 bar | 0 |
| `water` | `water_level_meters` | 5.0 m | 15.0 m | 0 |
| `voltage` | `voltage_supply_v` | 229.0 V | 231.0 V | 0 |
| `humidity` | `humidity_percent` | 40.0 % | 80.0 % | 0 |

### 3.3 Verification API
Final audit findings must be transmitted to Centrala's verification endpoint:
- **Endpoint**: `$AIDEVS_API_VERIFY`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Payload Schema**:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "evaluation",
    "answer": {
      "recheck": ["0001", "0002", "0003", "..."]
    }
  }
  ```
- **Accepted Identifier Formats**:
  - Padded string identifiers: `["0001", "0002", "4321"]` (standard recommendation).
  - Unpadded integer values: `[1, 2, 4321]`.
  - Filename strings: `["0001.json", "0002.json"]`.
  - Mixed formats are tolerated by Centrala, but standard zero-padded 4-digit strings (`"0001"`) or stem IDs are preferred.

---

## 4. Functional Requirements & Anomaly Definition

### 4.1 Definition of Anomaly
A file is deemed an **anomaly** and must be included in the `recheck` list if it meets ANY of the following four conditions:
1. **Physical Out-of-Bounds Metric**: An active sensor channel produces a measurement below its designated minimum or above its designated maximum threshold.
2. **Ghost / Unauthorized Reading**: A metric field corresponding to an inactive sensor channel (not declared in `sensor_type`) contains a non-zero value (e.g., a pure water sensor returning voltage readings).
3. **False Negative Operator Note**: The physical telemetry is abnormal (conditions 1 or 2 are violated), but the operator's note falsely states that everything is normal, healthy, or within expected limits. *(Note: Since conditions 1 and 2 already classify the file as an anomaly, this confirms recheck status).*
4. **False Positive Operator Note**: The physical telemetry is completely valid and healthy (all active metrics within bounds, all inactive metrics equal 0), but the operator's note claims there is an issue, error, warning, abnormal behavior, or alarm.

### 4.2 Decoupled Hybrid Evaluation Logic

#### Phase A: Deterministic Programmatic Audit (Sensor Telemetry)
1. For each of the ~10,000 JSON files:
   - Parse `sensor_type` by splitting on `/` and stripping whitespace.
   - For every metric field:
     - If the channel is active, verify: `min_val <= reading <= max_val`.
     - If the channel is inactive, verify: `reading == 0`.
   - If any metric check fails, immediately mark the file as an **anomaly** (`is_physical_anomaly = True`).
2. **Deterministic Partitioning**:
   - Files with `is_physical_anomaly = True`: Automatically added to the `recheck` set. They do not require semantic note analysis because the hardware reading is already definitively faulty.
   - Files with `is_physical_anomaly = False`: Sensor readings are healthy. These files proceed to Phase B to check for operator false alarms (condition 4).

#### Phase B: Semantic Operator Note Evaluation (LLM / NLP)
1. In the set of physically healthy files, the operator note must be analyzed:
   - Does the operator note claim or imply an anomaly, failure, error, threshold breach, or need for inspection?
   - Or does it indicate normal, expected, stable, or optimal operation?
2. **Deduplication & Local Response Caching**:
   - Out of thousands of valid files, operators use repetitive, boilerplate phrasing.
   - Extract unique `operator_notes` strings across the healthy candidate pool.
   - Evaluate each unique note text exactly once (using LLM structured classification or exact text caching).
   - If a unique note is classified as indicating an error/alarm despite the data being clean, all file IDs associated with that note text are flagged for `recheck`.

#### Phase C: Consolidation & Verification
1. Merge all file IDs identified from Phase A and Phase B into a deduplicated list.
2. Sort file IDs in ascending order for audit transparency.
3. Transmit payload to `$AIDEVS_API_VERIFY`.
4. Validate response status and extract the course completion flag `{FLG:...}`.

---

## 5. System & Token Constraints

- **Dataset Scale**: ~10,000 JSON files.
- **LLM Token Budget & Cost Avoidance**:
  - Processing 10,000 full JSON objects through an LLM would consume megabytes of input tokens and incur substantial latency and financial cost.
  - Passing raw numbers to an LLM introduces hallucination risk and rounding ambiguity.
  - **Requirement**: Zero raw telemetry numbers may be evaluated by the LLM. 100% of numerical boundary checks and ghost channel checks must be executed programmatically in Python.
  - **Optimization**: The LLM is strictly reserved for evaluating unique, distinct operator note texts that cannot be resolved via exact deterministic matching.
- **Model Selection**: Gemini 3.8 Flash (`gemini-3.8-flash`) on Vertex AI (`location=global`), configured with `thinking_level="low"`.
- **Latency Target**: Full end-to-end processing of all 10,000 files, unique note classification, and verification submission should complete within < 60 seconds.

---

## 6. Security & Environment Setup

### 6.1 Environment Variables
All external endpoints, keys, and cloud configurations must be read exclusively from environment variables:
| Variable Name | Description | Example / Fallback |
| :--- | :--- | :--- |
| `AIDEVS_API_KEY` | Course platform authentication key | *Stored in GCP Secret Manager or local `.env`* |
| `AIDEVS_API_VERIFY` | Centrala verification URL | *Endpoint for task submission* |
| `AIDEVS_SENSORS_DATA_URL` | Download URL for `sensors.zip` | *Mapped to `$AIDEVS_SENSORS_DATA_URL`* |
| `GOOGLE_CLOUD_PROJECT` | Target GCP project ID | `af-aidevs` |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI model location | `global` |
| `LANGSMITH_API_KEY` | LangSmith tracing key (optional/monitoring) | *Secret Manager* |
| `LANGSMITH_PROJECT` | Shared LangSmith project name | `af-aidevs` |

### 6.2 Security Rules
- **No Hardcoded URLs**: Never hardcode `$AIDEVS_API_VERIFY` or `$AIDEVS_SENSORS_DATA_URL` in code, docs, or logs.
- **Zero-Trust Course Flag Protection**: Course flags (`{FLG:...}`) must never be committed to Git or printed in plain text in public logs. Always redact as `[REDACTED_FLAG]` or `{FLG:...}`.
- **Safe Extraction**: Decompress `sensors.zip` in an isolated scratch/temporary working directory with path traversal protection.

---

## 7. Non-Functional & Observability Requirements

- **BigQuery Telemetry**: All execution steps, model classifications, token usage metrics, and verification results must be persisted to the lesson dataset in BigQuery (`s03e01.audit`).
- **Session Identification**: Traceability session ID must adhere to the standard schema:
  `s03e01_{backend}_{YYYYMMDD_HHMMSS}` in `Europe/Zurich` timezone.
- **Execution Summary (`run_notes.txt`)**: Upon task completion, write a concise execution report containing timestamp, total files parsed, count of physical anomalies, count of operator note discrepancies, total unique notes evaluated, and verification result.
