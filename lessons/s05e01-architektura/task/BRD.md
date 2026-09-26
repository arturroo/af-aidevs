# Business Requirements Document (BRD) - S05E01: Radiomonitoring & Multi-Modal Routing

## 1. Overview & Business Objectives

During the resistance operation led by Azazel and Nathan, survivors need to relocate people from fallen cities to a safe haven known as "Syjon". Nathan's physical notes on the city's exact location were destroyed during the destruction of Domatowo. However, an external listening outpost outside Domatowo remains operational, intercepting radio traffic in a 200–250 km radius.

The objective of the `radiomonitoring` task is to build an automated, intelligent radio interception and analysis pipeline that:
1. Initiates a radio monitoring session with Centrala.
2. Progressively captures incoming signals (which include noise, text transcripts, and Base64-encoded binary payloads).
3. Implements a 3-tier Medallion architecture inside `cr-mcp-workspace`:
   - `/raw/`: Immutable, byte-for-byte network packets received from Centrala.
   - `/decoded/`: Normalized, native decoded files (Base64 decoded to `.png`, `.mp3`, `.json`, and transcripts saved as `.txt`).
   - `/distilled/`: Curated facts, extracted clues, and enrichment outputs (`findings.json`).
4. Employs a deterministic, cost-effective programmatic router with multimodal context enrichment:
   - Filters out pure acoustic / transmission noise without wasting LLM tokens.
   - Parses structured data (JSON, text) deterministically.
   - Enriches visual/image data using a dedicated multimodal model (`gemini-3.5-flash-lite` with `thinking_level="medium"`) for scene description and OCR extraction.
   - Analyzes audio transmissions, including looking for telegraph / Morse code patterns.
5. Identifies the four critical target parameters of the city:
   - **`cityName`**: The real name of the city colloquially referred to as "Syjon".
   - **`cityArea`**: The city's geographical/administrative area rounded to exactly two decimal places (e.g. `12.34`).
   - **`warehousesCount`**: The total count of warehouses located in the city.
   - **`phoneNumber`**: The contact phone number for the liaison in Syjon.
6. Detects and extracts any hidden easter eggs or secondary mission secrets:
   - Secret telegraph clue: "Piosenka telegrafisty + wypisz: FLAGA".
   - Morse code representation of "FLAGA": `··−·` (F), `·−··` (L), `·−` (A), `−−·` (G), `·−` (A).
7. Submits the verified synthesis to Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) to obtain the mission flag.

---

## 2. Functional Requirements

### 2.1 Multi-Stage Lifecycle Protocol
The system must interact with Centrala using three sequential phases over HTTP POST requests to `$AIDEVS_API_VERIFY`:

1. **Session Initialization (`action: "start"`):**
   - Transmit a startup signal to initialize the buffer and radio packet queue on Centrala.
   - Ensure previous session states are reset.

2. **Signal Capture Loop (`action: "listen"`):**
   - Repeatedly poll packets from the radio receiver until Centrala signals that no more packets remain or that sufficient data has been collected.
   - Handle heterogenous packet payloads:
     - **Voice Transcripts:** Messages containing textual transcripts (`transcription`).
     - **Binary Attachments:** Messages containing MIME-type metadata (`meta`), Base64-encoded byte streams (`attachment`), and file sizes (`filesize`).
     - **Acoustic / Transmission Noise:** Malformed, irrelevant, or scrambled noise packets.

3. **Synthesis & Transmission (`action: "transmit"`):**
   - Once packet ingestion is complete, synthesize and cross-verify the collected facts.
   - Format and submit the final JSON payload containing `cityName`, `cityArea`, `warehousesCount`, and `phoneNumber`.

### 2.2 Mathematical & Formatting Precision
- **`cityArea` Formatting:** Must be formatted as a string representing a decimal number rounded mathematically (`ROUND_HALF_UP`) to exactly two decimal places (e.g., `"12.34"`). Simple string truncation or ceiling/floor clipping is strictly prohibited.
- **`warehousesCount`:** Must be an integer (`int`).
- **`cityName`:** Clean string without extraneous commentary or quotes.
- **`phoneNumber`:** Clean string containing the contact phone digits / standard format.

### 2.3 Medallion Workspace Layout (`cr-mcp-workspace`)
All runtime state and data processing must reside in session-isolated storage via `cr-mcp-workspace`:
- `/raw/packet_{index:03d}.json`: Exact response payloads from `$AIDEVS_API_VERIFY`.
- `/decoded/packet_{index:03d}.{ext}`: Base64-decoded binaries (`.png`, `.mp3`, `.json`) or extracted text transcripts (`.txt`).
- `/distilled/findings.json`: Extracted clues, OCR transcripts, visual descriptions, and candidate parameters.

### 2.4 Programmatic Router & Context Enrichment
- **Base64 Token Explosion Prevention:** Direct ingestion of uninspected, multi-megabyte Base64 buffers into LLM context windows is strictly forbidden.
- **MIME & Content-Type Inspection:** Decouple binary processing:
  - Deterministically decode Base64 in memory or sandbox.
  - If `meta` indicates structured data (e.g. `application/json`), parse deterministically without LLM.
  - If `meta` indicates images (`image/*`), route to `gemini-3.5-flash-lite` with `thinking_level="medium"` for deep scene understanding, OCR text extraction, and entity recognition.
  - If `meta` indicates audio (`audio/*`), inspect for voice transcription and Morse code rhythms.
  - If data is unparseable or irrelevant noise, drop immediately.
- **Hidden Secret & Telegraphist Clue Detection:**
  - Search audio, transcripts, and metadata for references to Julian Tuwim's "Piosenka telegrafisty" or the Morse sequence `··−·  ·−··  ·−  −−·  ·−` ("FLAGA").
  - Log and extract any detected secret flags.

---

## 3. System & Token Constraints

- **Execution Environment:** Google Cloud Run microservice (`cr-s05e01-radiomonitoring`) with local CLI testing capabilities (`main.py --mode cli`).
- **Synthesis LLM:** **Gemini 3.8 Flash** (`gemini-3.8-flash`) via Vertex AI (`vertexai=True`), using `thinking_level="low"` for final synthesis and decision making.
- **Context Enrichment LLM:** **Gemini 3.5 Flash Lite** (`gemini-3.5-flash-lite` or configurable via `ENRICHMENT_MODEL`) with `thinking_level="medium"` for deep visual OCR and multimodal enrichment.
- **Token Budget Optimization:** The listening loop may yield dozens of messages. Passing all raw buffers directly to the model could cost tens of thousands of unnecessary tokens. The programmatic router ensures LLM token consumption remains minimal by preprocessing and discarding irrelevant radio packets before model invocation.
- **Timeouts:** Radio packet ingestion occurs sequentially; HTTP client timeout must accommodate multiple round trips and binary decoding (recommended client timeout: $\ge 60$ seconds).

---

## 4. Data Inputs & External Resources

All external URLs must be configured exclusively via environment variables:

| Resource Description | Environment Variable | Usage in Service |
| :--- | :--- | :--- |
| Centrala Verification API | `$AIDEVS_API_VERIFY` | Endpoint for `start`, `listen`, and `transmit` actions |
| AI_Devs Personal API Key | `$AIDEVS_API_KEY` | Authenticates all requests sent to Centrala |
| GCS Workspace Bucket | `$GCS_WORKSPACE_BUCKET` | Session-isolated artifact persistence |
| LangSmith Observability | `$LANGSMITH_API_KEY` | Distributed LLM tracing and latency monitoring |
| LangSmith Project | `$LANGSMITH_PROJECT` | Canonical LangSmith project (`af-aidevs`) |

---

## 5. API Integration & Schemas

### 5.1 Outgoing Request Schema (`POST $AIDEVS_API_VERIFY`)
```json
{
  "apikey": "<AIDEVS_API_KEY>",
  "task": "radiomonitoring",
  "answer": {
    "action": "start | listen | transmit",
    "...": "action-specific fields"
  }
}
```

### 5.2 Phase 1: Start Request & Response
**Request Payload:**
```json
{
  "apikey": "<AIDEVS_API_KEY>",
  "task": "radiomonitoring",
  "answer": {
    "action": "start"
  }
}
```
**Expected Response:** Status acknowledgment confirming session initialization.

### 5.3 Phase 2: Listen Request & Responses
**Request Payload:**
```json
{
  "apikey": "<AIDEVS_API_KEY>",
  "task": "radiomonitoring",
  "answer": {
    "action": "listen"
  }
}
```
**Response Variant A (Transcription):**
```json
{
  "code": 100,
  "message": "Signal captured.",
  "transcription": "fragment przechwyconej rozmowy radiowej..."
}
```
**Response Variant B (Binary Attachment):**
```json
{
  "code": 100,
  "message": "Signal captured.",
  "meta": "application/json",
  "attachment": "<BASE64_ENCODED_STRING>",
  "filesize": 12345
}
```
**Response Variant C (Stream Completion):**
Status message indicating that the radio stream buffer is exhausted or sufficient data has been captured.

### 5.4 Phase 3: Transmit Final Report
**Request Payload:**
```json
{
  "apikey": "<AIDEVS_API_KEY>",
  "task": "radiomonitoring",
  "answer": {
    "action": "transmit",
    "cityName": "Opalino",
    "cityArea": "12.34",
    "warehousesCount": 12,
    "phoneNumber": "555-0192"
  }
}
```
**Expected Response:**
```json
{
  "code": 0,
  "message": "OK",
  "flag": "{FLG:...}"
}
```

---

## 6. Security, Privacy & Observability

1. **Secret Management:**
   - Production: `AIDEVS_API_KEY`, `AIDEVS_API_VERIFY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` stored in GCP Secret Manager.
   - Development: Loaded from local `.env` (strictly excluded from git).
2. **Flag Protection:**
   - Received course flags (`{FLG:...}`) must never be logged to stdout, committed to Git, or exposed in documentation.
3. **Zero-Pollution Telemetry Standard:**
   - Large Base64 payloads received in `attachment` must be masked prior to logging or storing in BigQuery audit tables (`<REDACTED_BASE64: length=X bytes>`).
   - LangSmith runs must mask binary attachments in trace inputs/outputs using `@traceable(process_outputs=mask_binary_output)`.
4. **Audit Logging:**
   - Stream structured event logs to BigQuery dataset `s05e01`, table `audit`.

---

## 7. Acceptance & Verification Criteria

1. **End-to-End Execution:** The microservice completes the full workflow (`start` -> iterative `listen` -> analysis -> `transmit`) and successfully extracts the flag.
2. **Accuracy & Precision:**
   - `cityArea` matches the exact two-decimal mathematical rounding criteria (`ROUND_HALF_UP`).
   - `warehousesCount` is a valid positive integer.
   - `cityName` and `phoneNumber` correctly identify the hidden settlement.
3. **Context Enrichment & Secret Detection:**
   - Multimodal files (images, audio) are decoded, enriched, and stored in `/decoded/` and `/distilled/`.
   - Any telegraph / Morse code patterns matching "Piosenka telegrafisty" or "FLAGA" (`··−·  ·−··  ·−  −−·  ·−`) are captured.
4. **Observability & Auditability:**
   - All session actions and signal summaries are logged to BigQuery dataset `s05e01` in table `audit`.
   - Traces are streamed to LangSmith with zero unmasked binary payloads.
5. **Code Quality Gates:**
   - `ruff check` and `ruff format` pass cleanly.
   - `mypy` passes with zero type errors.
   - Comprehensive unit and contract tests in `pytest`.
