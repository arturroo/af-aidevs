<!-- Source: https://www.industrialempathy.com/posts/design-docs-at-google/ -->
<!-- Based on: Google Design Docs structure by Malte Ubl -->
<!-- Adapted as a Technical PRD for AI-assisted implementation workflows -->

---
status: "approved"
date: 2026-09-26
author: "Artur <artur.fejklowicz>"
reviewers: ["Joi <antigravity>"]
adr: "[ADR.md](ADR.md)"
---

# Technical Product Requirements Document: S05E01 Radiomonitoring & Multimodal Scatter-Gather Router

## Context and Scope

During the resistance operation against the System led by Azazel and Nathan, survivors must be relocated from destroyed cities to a safe haven known as "Syjon". Nathan's physical records were destroyed in Domatowo, leaving an external listening outpost outside Domatowo as the sole operational facility to intercept radio traffic in a 200–250 km radius. Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) exposes an iterative polling protocol (`action: "start"` $\rightarrow$ sequential `action: "listen"` $\rightarrow$ terminal `action: "transmit"`) streaming heterogenous packets containing acoustic noise, textual transcripts, and Base64-encoded binary payloads (e.g. JSON, images, audio, ZIP archives, SQLite databases).

This document specifies the architecture, data models, services, subagents, and quality gates for the `cr-s05e01-radiomonitoring` Cloud Run microservice. The service implements an Asynchronous Scatter-Gather (Fan-Out / Fan-In) pipeline backed by a 3-Tier Medallion Workspace in `cr-mcp-workspace`, local tmpfs caching, Model Armor guardrails, dedicated multi-modal subagents, and a deterministic mathematical rounding engine. All architectural decisions have been finalized and accepted in [ADR.md](ADR.md) following the requirements set in [BRD.md](BRD.md).

---

## Goals and Non-Goals

### Goals
* **Automated Radio Signal Ingestion:** Poll Centrala iteratively via `action: "start"` and `action: "listen"` until Centrala indicates the packet stream is exhausted or sufficient data is captured.
* **Asynchronous Scatter-Gather Dispatch:** Ingest and decode packets at maximum network throughput, landing raw envelopes into `/raw/` and decoded binaries/transcripts into `/decoded/`, and dispatching analysis tasks concurrently to specialized subagents.
* **Strict Immutability & Zero Poisoning:** Enforce `APPEND_ONLY` mode in `cr-mcp-workspace` (zero file deletions), 100% container statelessness, and session-scoped isolation.
* **Granular Object-Level Findings:** Each subagent produces a typed Pydantic findings document in `/findings/` mirroring `/decoded/`, containing dense 3–4 sentence summaries, OCR, structural schemas/sections, candidate entities, and secret clues.
* **Multi-Modal Subagent Fleet:**
  - `VisionSubagent`: Enriches images via `gemini-3.5-flash-lite` (Thinking: Medium) using native GCS URIs (`gs://...`).
  - `TextSubagent`: Analyzes text transcripts and extracts Markdown outline structures (section numbers and titles).
  - `SQLiteSubagent`: Introspects `sqlite_master` deterministically and queries tables via a restricted `SELECT`-only read-only tool.
  - `AudioSubagent`: Analyzes audio recordings for speech transcripts and Morse code rhythms.
* **Dual-Objective Mission:** Concurrently resolve the 4 primary Syjon parameters and search for Julian Tuwim's telegraphist rhythm / Morse representation of `FLAGA` (`··−·  ·−··  ·−  −−·  ·−`).
* **Deterministic Rounding:** Apply Python's `decimal.Decimal` with `ROUND_HALF_UP` in code to format `cityArea` to exactly two decimal places (e.g. `"12.34"`).
* **Zero-Pollution Observability:** Stream sanitized audit events to BigQuery `s05e01.audit` and full traces to LangSmith with Base64 payloads masked to `<REDACTED_BASE64: length=X bytes>`.

### Non-Goals
* **Dynamic Arbitrary Code Execution:** The LLM is strictly prohibited from writing or executing dynamic scripts inside the Cloud Run container.
* **Multi-Master Distributed Workspace Synchronization:** No multi-container workspace locking or distributed transactional consensus (single-writer model per session).
* **Dual Framework Runtime Comparison:** The initial delivery implements a single backend (**LangChain**) on Cloud Run to maximize velocity; Google ADK parity is deferred.

---

## The Design

### System Overview

```
                                  ┌────────────────────────────────────────┐
                                  │      Centrala Verification API         │
                                  │        ($AIDEVS_API_VERIFY)            │
                                  └───────────────────┬────────────────────┘
                                                      │
                                                      │ HTTP POST (action: start, listen, transmit)
                                                      ▼
                      ┌────────────────────────────────────────────────────────────────┐
                      │            Cloud Run: cr-s05e01-radiomonitoring                │
                      │                                                                │
                      │  ┌──────────────────────────────────────────────────────────┐  │
                      │  │    Deterministic Ingestion Engine & Smart Router         │  │
                      │  │    - Polls Centrala (action: "listen")                   │  │
                      │  │    - Inspects Magic Bytes (PNG, JPG, SQLite, ZIP, Audio) │  │
                      │  │    - Unpacks ZIPs to /decoded/{archive_stem}/            │  │
                      │  │    - Dispatches async worker tasks (asyncio.gather)      │  │
                      │  └──────────────┬────────────────────────────┬──────────────┘  │
                      │                 │                            │                 │
                      │    (Fan-Out)    │                            │                 │
                      │                 ▼                            ▼                 │
                      │    ┌─────────────────────────┐  ┌─────────────────────────┐   │
                      │    │ Vision / Audio Subagent │  │  SQLite / Text Subagent │   │
                      │    │ (gemini-3.5-flash-lite) │  │  (Schema RO / ModelArmor│   │
                      │    └────────────┬────────────┘  └────────────┬────────────┘   │
                      │                 │                            │                 │
                      │                 └─────────────┬──────────────┘                 │
                      │                               │ Writes /findings/**/*.json     │
                      │                               ▼                                │
                      │  ┌──────────────────────────────────────────────────────────┐  │
                      │  │      Synthesis Subagent (Fan-In Aggregator)              │  │
                      │  │      - Aggregates all /findings/**/*.json                │  │
                      │  │      - Resolves Syjon: cityName, warehouses, phone       │  │
                      │  │      - Executes deterministic ROUND_HALF_UP (cityArea)   │  │
                      │  │      - Solves Morse / Tuwim secret easter egg (FLAGA)    │  │
                      │  │      - Formulates terminal payload (action: "transmit")  │  │
                      │  └──────────────────────────────────────────────────────────┘  │
                      └───────────────────────────────┬────────────────────────────────┘
                                                      │
                     ┌────────────────────────────────┼────────────────────────────────┐
                     ▼                                ▼                                ▼
       ┌───────────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────┐
       │     cr-mcp-workspace      │    │     BigQuery Telemetry    │    │         LangSmith         │
       │  (gs://af-aidevs-workspaces│   │       (s05e01.audit)      │    │  (Masked Binary Tracing)  │
       │   /raw, /decoded, /findings)   │                           │    │                           │
       └───────────────────────────┘    └───────────────────────────┘    └───────────────────────────┘
```

---

### API Design

#### 1. Service REST Endpoints (`cr-s05e01-radiomonitoring`)

* `GET /health` and `GET /`: Health check and container readiness probe.
* `POST /run`: Primary task execution endpoint.
  - **Request Body (`RunTaskRequest`):**
    ```json
    {
      "backend": "langchain",
      "session_id": "optional-custom-session-id",
      "model": "gemini-3.8-flash",
      "enrichment_model": "gemini-3.5-flash-lite",
      "thinking_level": "low",
      "max_iterations": 50
    }
    ```
  - **Response Body (`RunTaskResponse`):**
    ```json
    {
      "status": "success",
      "session_id": "sa-cr-s05e01-radiomonitoring-20260926-123456",
      "city_name": "Opalino",
      "city_area": "14.85",
      "warehouses_count": 12,
      "phone_number": "555-0192",
      "secret_flag": "{FLG:...}",
      "mission_flag": "{FLG:...}",
      "execution_time_seconds": 18.42
    }
    ```

#### 2. External Centrala Protocol (`$AIDEVS_API_VERIFY`)

* **Start Session:** `POST $AIDEVS_API_VERIFY` with `{"apikey": "...", "task": "radiomonitoring", "answer": {"action": "start"}}`.
* **Listen Loop:** `POST $AIDEVS_API_VERIFY` with `{"apikey": "...", "task": "radiomonitoring", "answer": {"action": "listen"}}`.
* **Transmit Report:** `POST $AIDEVS_API_VERIFY` with:
  ```json
  {
    "apikey": "<AIDEVS_API_KEY>",
    "task": "radiomonitoring",
    "answer": {
      "action": "transmit",
      "cityName": "...",
      "cityArea": "12.34",
      "warehousesCount": 123,
      "phoneNumber": "..."
    }
  }
  ```

---

### Data Model / Storage

#### 1. Workspace Layout (`cr-mcp-workspace` & Local `/tmp` Cache)

```
workspace:/
  ├── raw/
  │     ├── packet_001.json           <-- Raw JSON HTTP response from Centrala
  │     └── ...
  ├── decoded/
  │     ├── packet_001.txt            <-- Plain text transcript
  │     ├── packet_002.png            <-- Decoded image binary
  │     ├── archive_01/               <-- Unpacked ZIP contents
  │     │     ├── map.png
  │     │     └── notes.md
  │     └── database.sqlite           <-- Decoded SQLite database
  └── findings/
        ├── packet_001.txt.json       <-- Granular findings per object
        ├── packet_002.png.json
        ├── archive_01/
        │     ├── map.png.json
        │     └── notes.md.json
        └── database.sqlite.json
```

#### 2. Pydantic Findings Contract (`schemas.py`)

```python
class CandidateEntities(BaseModel):
  city_names: list[str] = Field(default_factory=list)
  city_area: str | None = None
  warehouses_count: int | None = None
  phone_numbers: list[str] = Field(default_factory=list)


class SecretClues(BaseModel):
  telegraphist_mentions: bool = False
  morse_detected: bool = False
  raw_clue: str | None = None
  extracted_key: str | None = None


class ObjectFinding(BaseModel):
  source_file: str = Field(
      description="Path to analyzed artifact in /decoded/"
  )
  mime_type: str = Field(description="Detected MIME type")
  summary_sentences: list[str] = Field(
      description="3-4 dense factual sentences describing scene, OCR, structure",
      max_length=4,
  )
  schema_or_structure: dict[str, Any] = Field(
      default_factory=dict,
      description="Extracted table schemas, JSON keys, or MD section titles",
  )
  candidate_entities: CandidateEntities = Field(
      default_factory=CandidateEntities
  )
  secret_clues: SecretClues = Field(default_factory=SecretClues)
  confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

---

### Core Logic & Algorithms

#### 1. Magic Bytes & MIME Router Algorithm
```python
def detect_payload_type(buffer: bytes, meta_hint: str | None) -> str:
  if buffer.startswith(b"SQLite format 3\x00"):
    return "application/x-sqlite3"
  if buffer.startswith(b"PK\x03\x04"):
    return "application/zip"
  if buffer.startswith(b"\x89PNG\r\n\x1a\n"):
    return "image/png"
  if buffer.startswith(b"\xff\xd8\xff"):
    return "image/jpeg"
  if buffer.startswith(b"RIFF") and buffer[8:12] == b"WEBP":
    return "image/webp"
  if buffer.startswith(b"RIFF") and buffer[8:12] == b"WAVE":
    return "audio/wav"
  if buffer.startswith(b"ID3") or buffer.startswith(b"\xff\xfb"):
    return "audio/mpeg"
  if buffer.startswith(b"OggS"):
    return "audio/ogg"

  try:
    decoded_text = buffer.decode("utf-8")
    if (
        decoded_text.strip().startswith("{")
        or decoded_text.strip().startswith("[")
    ):
      json.loads(decoded_text)
      return "application/json"
    return "text/plain"
  except UnicodeDecodeError:
    return meta_hint or "application/octet-stream"
```

#### 2. Deterministic Mathematical Rounding
```python
from decimal import Decimal, ROUND_HALF_UP


def format_city_area(raw_value: float | str | Decimal) -> str:
  clean_str = str(raw_value).strip().replace(",", ".")
  d = Decimal(clean_str)
  rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  return f"{rounded:.2f}"
```

#### 3. Morse Code & Telegraphist Secret Detector
```python
import re

# Sequence for FLAGA: F (..-.), L (.-..), A (.-), G (--.), A (.-)
MORSE_FLAGA_PATTERN = re.compile(
    r"\.{2}-\.\s+\.-\.{2}\s+\.-\s+--\.\s+\.-", re.IGNORECASE
)
TELEGRAPHIST_KEYWORDS = [
    "piosenka telegrafisty",
    "telegrafista",
    "tuwim",
    "stukanie",
    "morse",
    "flaga",
]


def scan_for_secret(text: str) -> tuple[bool, str | None]:
  lower_text = text.lower()
  has_keyword = any(kw in lower_text for kw in TELEGRAPHIST_KEYWORDS)
  has_morse = bool(MORSE_FLAGA_PATTERN.search(text))
  if has_keyword or has_morse:
    return True, text
  return False, None
```

---

### Infrastructure / Deployment

* **Target GCP Project:** `af-aidevs`
* **Cloud Run Microservice:** `cr-s05e01-radiomonitoring`
* **Base Container Image:** `python:3.13.5-slim`
* **CPU / Memory:** 2 vCPU, 2 GiB RAM
* **Scaling:** `min-instances = 0`, `max-instances = 3`
* **Terraform Registration:**
  - Registered under `cr_names.cr-s05e01-radiomonitoring` in `terraform/variables.tf`.
  - Roles: `roles/aiplatform.user`, `roles/bigquery.jobUser`, `roles/secretmanager.secretAccessor`.
  - Bucket Roles: `roles/storage.objectViewer` on `af-aidevs-workspaces`.
  - Secrets: `AIDEVS_API_KEY`, `AIDEVS_VERIFY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `MCP_WORKSPACE_URL`, `MODEL_ARMOR_URL`.

---

## Cross-Cutting Concerns

### Security
* **Zero Hardcoded Secrets & URLs:** All external URLs loaded from `.env` or Secret Manager via `config.py`.
* **Model Armor Gate:** Intercepted transcripts and database schemas pass through `cr-model-armor` before LLM prompt injection.
* **Read-Only SQLite Tooling:** SQLite connection enforces `?mode=ro`, strictly rejecting `UPDATE`, `INSERT`, `DROP`, `DELETE` queries.
* **ZIP Traversal Defense:** Verifies normalized paths against canonical roots; strictly rejects paths containing `..` or absolute prefixes.
* **Flag Protection:** Course flags (`{FLG:...}`) redacted in stdout, Git commits, and public logs.

### Observability
* **BigQuery Streaming:** Every session initialization, signal receipt, subagent finding, and terminal transmission streamed to `af-aidevs.s05e01.audit`.
* **LangSmith Tracing:** Unified project `LANGSMITH_PROJECT=af-aidevs`. All binary payloads wrapped with `@traceable(process_outputs=mask_binary_output)`.

### Performance / Scalability
* **Scatter-Gather Parallelism:** Centrala polling loop decoupled from heavy inference via `asyncio.create_task`.
* **Local `/tmp` Cache:** Avoids repeated MCP HTTP round-trips for the same session. Max cache footprint capped at 100 MB.
* **Native Vertex AI GCS Loading:** Zero client network egress for image payloads.

---

## Edge Cases and Constraints

### Edge Cases
1. **Corrupted / High-Entropy Acoustic Static:** Router detects unparseable binary streams without known headers; flags as noise, writes lightweight metadata to `/raw/`, and skips model invocation ($0 LLM tokens).
2. **Multiple City Candidates in Signals:** Conflicting city names (e.g. fallen cities like Domatowo vs Syjon). Synthesis Subagent cross-references coordinates and context ("the haven survivors flee to", "safe haven erased from maps") to isolate the real name of Syjon.
3. **Floating Point Rounding Boundary (`14.845`):** Standard Python `round()` uses bankers rounding (to even). Deterministic `ROUND_HALF_UP` ensures `14.845` rounds strictly to `14.85`.
4. **Nested Archive Depths:** Archives containing archives. Router unpacks up to 2 recursion depths safely.

### Constraints
1. **Session Timeouts:** Centrala listening loop must execute without multi-minute gaps to prevent session reset.
2. **Cloud Run tmpfs Limits:** Local `/tmp` shares the 2 GiB container RAM. Staging buffers must not exceed 100 MB.

---

## Implementation Plan

### Phases / Milestones

| Phase | Scope | Deliverable |
|:---|:---|:---|
| **Phase 1: Scaffolding & Schemas** | Microservice folder, dependencies, Pydantic contracts, config | `cr-s05e01-radiomonitoring` base scaffold |
| **Phase 2: Core Services** | Centrala client, Router, MCP service with `/tmp` cache, BigQuery audit | Ingestion & staging pipeline |
| **Phase 3: Subagents Fleet** | Vision (Gemini 3.5), Text (MD TOC), SQLite (RO tool), Audio | Multi-modal finding generators |
| **Phase 4: Synthesis & Rounding** | Fan-In aggregator, `ROUND_HALF_UP` tool, Morse secret solver | Complete end-to-end task runner |
| **Phase 5: CLI, Tests & Terraform** | Unit/mock tests, CLI execution, Terraform variables registration | Passing quality gates |

---

## Implementation Spec

> This section is consumed by the AI coding agent executing `/implement` against this PRD.

### File Structure

```
lessons/s05e01-architektura/task/
├── BRD.md
├── ADR.md
├── PRD.md
└── cr-s05e01-radiomonitoring/
    ├── .dockerignore
    ├── .gcloudignore
    ├── .python-version
    ├── Dockerfile
    ├── cloudbuild.yaml
    ├── pyproject.toml
    ├── config.py
    ├── schemas.py
    ├── system_prompt.md
    ├── main.py
    ├── services/
    │   ├── __init__.py
    │   ├── centrala_service.py
    │   ├── router_service.py
    │   ├── mcp_service.py
    │   ├── audit_service.py
    │   └── model_armor_service.py
    ├── agents/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── vision_subagent.py
    │   ├── text_subagent.py
    │   ├── sqlite_subagent.py
    │   ├── audio_subagent.py
    │   └── synthesis_subagent.py
    └── tests/
        ├── __init__.py
        ├── test_schemas.py
        ├── test_router.py
        ├── test_rounding.py
        ├── test_sqlite_subagent.py
        └── test_agent_smoke.py
```

### Technology Stack & Exact Library Versions (`pyproject.toml`)

```toml
[project]
name = "cr-s05e01-radiomonitoring"
version = "0.1.0"
description = "Cloud Run service for S05E01 Radiomonitoring & Multimodal Scatter-Gather Ingestion"
readme = "README.md"
requires-python = "==3.13.5"
dependencies = [
    "af-aidevs==0.1.0",
    "fastapi==0.115.8",
    "google-cloud-bigquery==3.29.0",
    "google-cloud-secret-manager==2.22.0",
    "google-cloud-storage==2.19.0",
    "google-genai==1.3.0",
    "httpx==0.28.1",
    "langchain==0.3.19",
    "langchain-core==0.3.37",
    "langchain-google-genai==2.0.10",
    "langsmith==0.3.10",
    "pydantic==2.10.6",
    "python-dotenv==1.0.1",
    "tenacity==9.0.0",
    "uvicorn==0.34.0",
]

[dependency-groups]
dev = [
    "mypy==1.15.0",
    "pytest==8.3.4",
    "pytest-asyncio==0.25.3",
    "ruff==0.9.7",
]

[[tool.uv.index]]
name = "gar"
url = "https://europe-west6-python.pkg.dev/af-aidevs/python-packages/simple/"
```

### Step-by-Step Implementation Order

1. **Scaffolding & Config (`config.py`, `schemas.py`, `pyproject.toml`, Docker/CloudBuild):**
   - Create directories and files.
   - Define Pydantic contracts: `RunTaskRequest`, `RunTaskResponse`, `ObjectFinding`, `CentralaListenResponse`.
   - Setup `config.py` with fallback lookups (`os.getenv("AIDEVS_VERIFY") or os.getenv("AIDEVS_API_VERIFY")`).
2. **Core Services:**
   - `services/centrala_service.py`: Implements `start()`, `listen()`, `transmit()` with tenacity retries.
   - `services/mcp_service.py`: Remote client to `cr-mcp-workspace` with `/tmp/mcp_cache/` Write-Through and Read-Through caching.
   - `services/model_armor_service.py`: Client for `cr-model-armor` validation.
   - `services/audit_service.py`: Structured event streaming to `af-aidevs.s05e01.audit`.
   - `services/router_service.py`: Magic bytes classifier, ZIP decompression, Base64 decoding, dispatch logic.
3. **Specialized Subagents Fleet (`agents/`):**
   - `agents/vision_subagent.py`: Uses `gemini-3.5-flash-lite` (medium thinking) with GCS URI or `/tmp` buffer. Generates 3-sentence description, OCR, and metrics.
   - `agents/text_subagent.py`: Handles transcripts and `.md` structure extraction.
   - `agents/sqlite_subagent.py`: Introspects `sqlite_master` in read-only mode and executes `query_sqlite` tool.
   - `agents/audio_subagent.py`: Scans audio for Morse sequences (`FLAGA`) and speech.
4. **Synthesis Subagent & Mathematical Rounding:**
   - `agents/synthesis_subagent.py`: Aggregates all `/findings/`, resolves parameters, calls `format_city_area` (`ROUND_HALF_UP`), extracts Morse secret flag, and calls `centrala_service.transmit()`.
5. **Main Entrypoint & Endpoints (`main.py`):**
   - FastAPI endpoints `@app.get("/health")`, `@app.get("/")`, `@app.post("/run")`.
   - CLI execution mode `run_cli()` with `--model`, `--thinking-level`, `--max-iterations` argument parsing.
6. **Tests & Quality Verification:**
   - Unit tests for Pydantic parsing, router classification, `ROUND_HALF_UP` precision, and mock end-to-end execution.
   - Run `ruff check`, `ruff format`, and `mypy`.
7. **Terraform Registration:**
   - Add `cr-s05e01-radiomonitoring` configuration to `terraform/variables.tf`.

---

### Acceptance Criteria (Testable)

* [ ] `cr-s05e01-radiomonitoring` scaffolds cleanly with zero dependency conflicts (`uv lock`).
* [ ] Magic bytes router accurately classifies JSON, text, PNG, JPEG, WebP, WAV, MP3, ZIP, and SQLite buffers.
* [ ] In-memory ZIP decompressor unpacks safely to `/decoded/{archive_stem}/` and rejects path traversal attacks.
* [ ] SQLite subagent connects exclusively in read-only mode and extracts schema and candidate records without arbitrary code execution.
* [ ] Vision subagent generates dense 3-sentence descriptions and extracts OCR/metrics via `gemini-3.5-flash-lite`.
* [ ] Model Armor gate scans incoming text and table schemas before LLM prompt injection.
* [ ] Local `/tmp` cache reduces repeated MCP read latency to $<1$ ms.
* [ ] `format_city_area` applies strict `ROUND_HALF_UP` arithmetic (e.g. `14.845` becomes `"14.85"`).
* [ ] Morse code detector identifies Julian Tuwim's telegraphist rhythm and the Morse sequence for `FLAGA`.
* [ ] BigQuery audit logs stream sanitized events with zero raw Base64 strings.
* [ ] LangSmith traces mask all binary payloads via `@traceable(process_outputs=mask_binary_output)`.
* [ ] Microservice passes `ruff check`, `ruff format`, and `mypy` with zero errors.
* [ ] Microservice successfully obtains the flag from Centrala via both CLI mode and HTTP `POST /run`.

---

### Out-of-Scope for Agent (Human Required)

* Applying production Terraform changes (`terraform apply` in GCP).
* Granting production IAM roles outside the automated Terraform module.
