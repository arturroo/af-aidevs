<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-26
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S05E01 Radiomonitoring & Multimodal Scatter-Gather Router

## 1. Context

During the resistance operation led by Azazel and Nathan, survivors need to relocate people from fallen cities to a safe haven known as "Syjon". Nathan's physical notes were destroyed during the destruction of Domatowo, leaving an external listening outpost outside Domatowo as the sole operational facility to intercept radio traffic in a 250 km radius. Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) exposes an iterative polling protocol (`action: "start"` $\rightarrow$ sequential `action: "listen"` $\rightarrow$ terminal `action: "transmit"`) streaming heterogenous packets containing acoustic static, textual transcripts, and Base64-encoded binary payloads (e.g. JSON, images, audio, ZIP archives, SQLite databases).

The core architectural challenges are preventing multi-megabyte Base64 token explosion in LLM context windows, guaranteeing 100% Cloud Run container statelessness, enriching multimodal clues (via OCR and scene analysis), actively hunting for a hidden telegraphist/Morse easter egg ("Piosenka telegrafisty"), and enforcing exact mathematical precision (`ROUND_HALF_UP` to two decimal places) for `cityArea`. The architectural fitness function is the zero-loss distillation of all intercepted signals into the four verified parameters (`cityName`, `cityArea`, `warehousesCount`, `phoneNumber`), secondary extraction of the secret flag, and successful submission to Centrala.

---

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Signal Ingestion & Dispatch Architecture | Asynchronous Scatter-Gather Router (Fan-Out / Fan-In) | Maximizes ingestion throughput, decouples network polling from deep multimodal processing, and prevents agent loop stalling. |
| 2 | Workspace Layout & Data Immutability | 3-Tier Medallion Architecture in `cr-mcp-workspace` with Strict `APPEND_ONLY` Mode | Guarantees raw byte replayability, normalizes native binaries, and eliminates catastrophic file deletion risks. |
| 3 | Gold Layer Findings Organization | Granular Object-Level Findings (`/findings/**/*.json` Mirroring `/decoded/`) | Provides strongly typed Pydantic structures per artifact, enables parallel subagent execution, and isolates failures. |
| 4 | Specialized Subagent Fleet | Decoupled Multi-Modal Subagents (Vision, Text, SQLite, Audio) | Each agent focuses strictly on its domain with minimal context, maximizing extraction quality and token economy. |
| 5 | Search Mission Objectives | Dual-Objective Ingestion Strategy (Primary: Syjon; Secondary: Morse Secret Hunter) | Solves primary mission parameters while concurrently analyzing signals for Julian Tuwim's telegraphist rhythm and Morse `FLAGA`. |
| 6 | Compressed Archive Handling | Deterministic In-Memory ZIP Unpacking with Lightweight Manifest Routing | Prevents memory exhaustion and zip-bomb attacks while routing unpacked files purely by lightweight references in RAM. |
| 7 | Indirect Prompt Injection Defense | Model Armor Guardrail Gate on Silver $\rightarrow$ Gold Boundary | Validates untrusted transcripts and SQLite table/column schemas against injection attacks before LLM ingestion. |
| 8 | Structured Database Exploration | Dedicated Read-Only SQLite Subagent with Schema Introspection | Replaces dangerous runtime code generation with a safe, introspected schema and strict `SELECT`-only read-only tool. |
| 9 | Distributed Storage Latency & Network Egress | Session-Scoped Local `/tmp` Cache in `MCPService` (Write-Through & Read-Through) | Turns high-latency remote MCP round-trips into instantaneous tmpfs reads while respecting Cloud Run RAM boundaries. |
| 10 | Multimodal Cloud Ingestion Efficiency | Native Vertex AI GCS URIs (`gs://...`) for Multimodal Ingestion | Eliminates multi-megabyte HTTP Base64 payload transfer by leveraging Google Cloud's internal backbone. |
| 11 | Numerical & Mathematical Precision | Deterministic Python `ROUND_HALF_UP` Tool for `cityArea` | Completely eliminates LLM arithmetic hallucinations by enforcing IEEE/Python `decimal.Decimal` rounding in code. |
| 12 | Telemetry & LLM Observability | Masked Binary Tracing in LangSmith & Structured BigQuery Audit (`s05e01.audit`) | Delivers end-to-end trace visibility and queryable audit logs while strictly adhering to Zero-Pollution telemetry rules. |
| 13 | Service Framework & Deployment | Single-Backend (LangChain) on Cloud Run (`cr-s05e01-radiomonitoring`) | Minimizes codebase surface area and deployment friction while honoring all Google Cloud IAM and quality gates. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Asynchronous Scatter-Gather Router (Fan-Out / Fan-In)

#### Problem & Drivers
Centrala streams packets sequentially over HTTP. Intercepted signals contain a mix of acoustic noise, transcripts, and heavy binaries. Processing each packet synchronously with an LLM before fetching the next packet creates unacceptable latency, risks Centrala connection timeouts, and balloons the context window.

#### Considered Options

##### Option 1.1: Asynchronous Scatter-Gather Router (ACCEPTED)
* **Description**: A deterministic Python ingestion engine polls Centrala's `/verify` endpoint in a tight loop. As each packet arrives, it is immediately landed in `/raw/`, decoded to `/decoded/`, and dispatched as an asynchronous background worker task (`asyncio.create_task`) to the specialized subagent fleet. When Centrala signals stream exhaustion and all tasks complete, the Synthesis Subagent performs the Fan-In aggregation.
* **Data Engineering & Performance**: Ingestion runs at maximum network speed. Deep analysis runs concurrently across available CPU/thread workers.
* **Cost & FinOps**: Over 90% reduction in agent token overhead compared to sequential conversational loops.
* **Security & Reliability**: Bounded execution; network polling is decoupled from model latency and upstream rate limits.
* **Pros & Cons**:
  * Good, because it prevents agent loop stalling and handles bursty radio packet traffic gracefully.
  * Bad / Trade-off, requires tracking concurrent background task completion.

##### Option 1.2: Synchronous Sequential Agent Tool Loop (REJECTED)
* **Description**: LLM agent calls `listen_radio()`, inspects output, calls next `listen_radio()`.
* **Pros & Cons**:
  * Bad, because it is extremely slow, burns massive tokens on repeated prefix context, and risks loop failure.

---

### Decision 2: 3-Tier Medallion Workspace with Strict `APPEND_ONLY` Mode

#### Problem & Drivers
Writing intermediate files to local container disk causes **Local Disk Poisoning** (leaking stale data into container builds via `COPY . .`). Conversely, destructive agent actions ("cleaning up") have historically caused catastrophic data loss (e.g. Replit DB deletion, Antigravity disk wipe).

#### Considered Options

##### Option 2.1: Remote 3-Tier Medallion Architecture in `cr-mcp-workspace` (APPEND_ONLY) (ACCEPTED)
* **Description**: All session state is stored in `cr-mcp-workspace` under session isolation (`X-Session-ID`):
  - `/raw/`: Immutable, byte-for-byte JSON responses from Centrala (`packet_001.json`).
  - `/decoded/`: De-serialized native files with real extensions (`packet_002.png`, `packet_003.mp3`, `packet_004.json`, `packet_005.txt`).
  - `/findings/`: Standardized Pydantic findings JSON files per object (`packet_002.png.json`).
  The workspace operates in strict **`APPEND_ONLY`** mode: file deletion tools (`delete_file`) are explicitly omitted.
* **Data Engineering & Performance**: Complete data lineage and replayability (Bronze $\rightarrow$ Silver $\rightarrow$ Gold).
* **Security & Reliability**: Zero risk of rogue agents wiping workspace files; Cloud Run container remains 100% stateless.
* **Pros & Cons**:
  * Good, because it adheres to Google Lakehouse principles and completely eliminates destructive literalism.
  * Bad / Trade-off, workspace storage grows monotonically during the session (acceptable for radio bursts $<200$ MB).

##### Option 2.2: Local Container Filesystem Buffering with Agent Deletion (REJECTED)
* **Pros & Cons**:
  * Bad, because it violates container statelessness and risks catastrophic data loss.

---

### Decision 3: Granular Object-Level Findings (`/findings/**/*.json`)

#### Problem & Drivers
Aggregating all findings into a single global file (`findings.json`) creates concurrent write contention among parallel subagents and increases the risk of corrupted JSON.

#### Considered Options

##### Option 3.1: Granular Object-Level Findings Mirroring `/decoded/` (ACCEPTED)
* **Description**: For every file `/decoded/path/to/artifact.ext`, the analyzing subagent writes a dedicated JSON file `/findings/path/to/artifact.ext.json`. The structure contains:
  1. `summary_sentences`: Exactly 3–4 dense factual sentences describing the artifact.
  2. `schema_or_structure`: Extracted table schemas (for DBs), keys (for JSON), or section headers (for Markdown).
  3. `candidate_entities`: Extracted candidates for `city_names`, `city_area`, `warehouses_count`, `phone_numbers`.
  4. `secret_clues`: Captured references to Morse code, Tuwim, or telegraph signals.
* **Data Engineering & Performance**: Zero write contention; parallel subagents write independently to distinct keys.
* **Security & Reliability**: If one file analysis fails, all other findings remain intact and queryable.
* **Pros & Cons**:
  * Good, strongly typed, deterministic aggregation by the final Synthesis Subagent.
  * Bad / Trade-off, creates multiple small JSON metadata files in the workspace.

---

### Decision 4: Specialized Multi-Modal Subagent Fleet

#### Problem & Drivers
Passing raw multi-modal buffers (images, audio, databases) to a single monolithic generalist prompt degrades attention (needle-in-a-haystack effect) and inflates token costs.

#### Considered Options

##### Option 4.1: Decoupled Specialist Subagents (ACCEPTED)
* **Description**: Implement dedicated subagent handlers:
  - **`VisionSubagent`**: Analyzes images using `gemini-3.5-flash-lite` (Thinking: Medium). Performs visual OCR, map scaling, and detects telegraphist markings.
  - **`TextSubagent`**: Analyzes text transcripts and Markdown documents. For `.md`, it extracts section numbers/titles (TOC) and context.
  - **`SQLiteSubagent`**: Interacts with SQLite databases via introspected schemas and read-only tools.
  - **`AudioSubagent`**: Detects acoustic Morse code rhythms, dot-dash sequences, and transcribes voice recordings.
* **Cost & FinOps**: Offloads visual reasoning to `gemini-3.5-flash-lite` at a fraction of larger model costs.
* **Pros & Cons**:
  * Good, modular, highly testable, each subagent operates on isolated, minimal prompts.
  * Bad / Trade-off, requires managing routing dispatch logic.

---

### Decision 5: Dual-Objective Search Strategy (Syjon + Morse Secret Hunter)

#### Problem & Drivers
The mission has two distinct goals: (1) Primary: identify Nathan's hidden resistance haven ("Syjon") with 4 verified parameters; (2) Secondary / Easter Egg: decode a hidden mission secret with the sole hint *"Piosenka telegrafisty + wypisz: FLAGA"*.

#### Considered Options

##### Option 5.1: Integrated Dual-Objective Prompting & Detection (ACCEPTED)
* **Description**: Every specialized subagent prompt and deterministic router rule incorporates the dual search target:
  - **Primary**: Search for Syjon city name, administrative area, warehouse counts, contact phone numbers.
  - **Secondary**: Actively scan text, audio rhythms, image annotations, and database records for Julian Tuwim's "Piosenka telegrafisty", telegraphist references, Morse code representations of "FLAGA" (`··−·  ·−··  ·−  −−·  ·−`), and associated hidden keys.
* **Security & Reliability**: Guarantees no secondary easter egg is discarded as "noise".
* **Pros & Cons**:
  * Good, unlocks 100% mission completion and bonus flag discovery.
  * Bad / Trade-off, minor prompt token increase (~50 tokens per prompt).

---

### Decision 6: Deterministic ZIP Unpacking with Lightweight Manifest Routing

#### Problem & Drivers
Intercepted archives may contain multiple nested files or malicious path traversal payloads (`../../etc/passwd` or zip-bombs).

#### Considered Options

##### Option 6.1: Safe In-Memory Unpacking to `/decoded/{archive_stem}/` & Reference Routing (ACCEPTED)
* **Description**: When magic bytes `b"PK\x03\x04"` are detected:
  1. Inspect archive in memory using `zipfile.ZipFile(io.BytesIO(buffer))`.
  2. Enforce safety checks: verify total uncompressed size $<50$ MB, reject any path containing `..` or absolute prefixes.
  3. Extract files into `cr-mcp-workspace` under `/decoded/{archive_stem}/{filename}`.
  4. Pass only a lightweight manifest (`list[dict]` of paths and MIME types) back to the router. The router never handles heavy byte buffers.
* **Data Engineering & Performance**: Memory consumption is strictly bounded; routing occurs purely by reference.
* **Pros & Cons**:
  * Good, 100% safe, fast, zero RAM duplication.
  * Bad / Trade-off, requires recursive routing for nested files.

---

### Decision 7: Model Armor Guardrail Gate on Silver $\rightarrow$ Gold Boundary

#### Problem & Drivers
Radio traffic originates from untrusted sources in the field. Attackers (e.g. System operators) can transmit indirect prompt injections or jailbreaks disguised as transcripts or database metadata.

#### Considered Options

##### Option 7.1: Model Armor Pre-LLM Inspection Gate (ACCEPTED)
* **Description**: Before passing any decoded text transcript, Markdown content, or SQLite table/column schema to an LLM prompt:
  - Query `cr-model-armor` (via `$MODEL_ARMOR_URL`).
  - If malicious instructions or injection patterns are detected, mark the artifact with `injection_flag: true` in its findings and sanitize the input before LLM reasoning.
* **Security & Reliability**: Directly defends against Confused Deputy attacks (e.g. *InjectAgent*, *TerminalDilma*).
* **Pros & Cons**:
  * Good, enterprise-grade defense-in-depth as mandated by lesson concepts.
  * Bad / Trade-off, adds a lightweight HTTP verification hop (~50 ms).

---

### Decision 8: Dedicated Read-Only SQLite Subagent

#### Problem & Drivers
If a database binary lands, allowing the LLM to write and run dynamic execution scripts in Cloud Run risks infinite loops, container resource exhaustion, and security breaches ("Giving agents hands").

#### Considered Options

##### Option 8.1: Introspected Schema + Read-Only SQLite Subagent (ACCEPTED)
* **Description**:
  1. Deterministic Python code inspects the database in read-only mode (`?mode=ro` or memory deserialization) to extract `sqlite_master` schemas and table names ($0 tokens).
  2. The schema is validated through Model Armor.
  3. A specialized `SQLiteSubagent` is initialized with the verified schema in its system prompt and a single read-only tool: `query_sqlite(sql: str) -> list[dict]` (enforcing `SELECT`-only and `LIMIT 50`).
  4. The subagent queries for Syjon parameters and secret telegraphist records, writing its conclusions to `/findings/{db_name}.json`.
* **Data Engineering & Performance**: Prevents dumping thousands of raw database rows into the main agent context.
* **Security & Reliability**: Read-only connection guarantees zero data corruption or side-effects.
* **Pros & Cons**:
  * Good, minimal token footprint, highly secure, zero arbitrary code execution.
  * Bad / Trade-off, requires implementing the restricted query tool.

---

### Decision 9: Session-Scoped Local `/tmp` Cache in `MCPService`

#### Problem & Drivers
Repeatedly fetching the same heavy images or database binaries from `cr-mcp-workspace` across subagents wastes network bandwidth and introduces hundreds of milliseconds of HTTP latency per call.

#### Considered Options

##### Option 9.1: Write-Through & Read-Through Cache in `/tmp/mcp_cache/{session_id}/` (ACCEPTED)
* **Description**:
  - Cloud Run container is the **sole writer** to its session workspace prefix, guaranteeing zero multi-writer cache drift.
  - `read_file(path)`: checks `/tmp/mcp_cache/{session_id}/{path}`. On hit, serves from tmpfs in $<1$ ms. On miss, fetches from remote MCP and populates cache.
  - `write_file(path, content)`: writes to remote MCP and immediately updates local cache (Write-Through).
  - Safety guardrail: Enforce a 100 MB max cache limit to protect Cloud Run container RAM (`tmpfs`).
* **Data Engineering & Performance**: Drastically cuts internal network traffic; subagents read shared artifacts at RAM speeds.
* **Pros & Cons**:
  * Good, transparent to subagents, huge latency reduction.
  * Bad / Trade-off, consumes a slice of container RAM.

---

### Decision 10: Native Vertex AI GCS URIs (`gs://...`) for Multimodal Ingestion

#### Problem & Drivers
Inlining multi-megabyte images as Base64 strings in Gemini API requests saturates outbound container network egress and inflates request latency.

#### Considered Options

##### Option 10.1: Native GCS URI Referencing (ACCEPTED)
* **Description**: When invoking Gemini 3.5 Flash Lite for visual analysis, pass `Part.from_uri(file_uri="gs://af-aidevs-workspaces/...", mime_type="image/png")` directly. Gemini loads the image internally across Google's high-speed datacenter backbone.
* **Data Engineering & Performance**: Near-zero client network egress; image loading happens inside Google Cloud infrastructure.
* **Pros & Cons**:
  * Good, fastest, most cost-effective Google-native pattern.
  * Bad / Trade-off, requires service account permissions on the GCS workspace bucket (`roles/storage.objectViewer`).

---

### Decision 11: Deterministic Python `ROUND_HALF_UP` Tool for `cityArea`

#### Problem & Drivers
Centrala strictly enforces: *"wynik musi mieć dokładnie dwa miejsca po przecinku, chodzi o prawdziwe matematyczne zaokrąglenie, a nie o obcięcie wartości, format: 12.34"*. LLMs are notoriously unreliable at exact floating-point rounding and decimal truncation.

#### Considered Options

##### Option 11.1: Deterministic Python Rounding Function (ACCEPTED)
* **Description**: In code, apply Python's `decimal` module:
  ```python
  from decimal import Decimal, ROUND_HALF_UP


  def format_city_area(raw_value: float | str | Decimal) -> str:
      d = Decimal(str(raw_value).strip())
      rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
      return f"{rounded:.2f}"
```
  The Synthesis Subagent identifies the raw candidate value, but the final string formatting is strictly performed by this deterministic tool before constructing the Centrala payload.
* **Security & Reliability**: 100% mathematical guarantee against truncation bugs (e.g. `12.345` $\rightarrow$ `12.35`, never `12.34`).
* **Pros & Cons**:
  * Good, mathematically hermetic, eliminates evaluation failure risk.
  * Bad / Trade-off, none.

##### Option 11.2: Relying on LLM Prompt Instructions for Rounding (REJECTED)
* **Pros & Cons**:
  * Bad, prone to string slicing hallucinations and rounding failures.

---

### Decision 12: Masked Binary Tracing in LangSmith & BigQuery Audit

#### Problem & Drivers
Radio packets contain large Base64 blobs. Directly logging these payloads to BigQuery or LangSmith violates the repository's Zero-Pollution telemetry rules and causes trace timeouts.

#### Considered Options

##### Option 12.1: Output Masking Decorators & Structured Metadata Logging (ACCEPTED)
* **Description**:
  - LangSmith tracing applied via `@traceable` with custom `process_outputs` replacing Base64 payloads with `<REDACTED_BASE64: length=X bytes, sha256=...>`.
  - BigQuery audit service streams event records to `s05e01.audit` containing packet metadata (index, MIME type, size, truncated text preview).
* **Data Engineering & Performance**: Clean, lightweight traces and fast BigQuery querying.
* **Security & Reliability**: Zero sensitive data or multi-megabyte garbage leaks into monitoring platforms.
* **Pros & Cons**:
  * Good, full trace visibility with zero bloat.
  * Bad / Trade-off, requires wrapping tool outputs in masking handlers.

---

### Decision 13: Service Framework & Deployment

#### Problem & Drivers
Balancing delivery speed with enterprise engineering standards.

#### Considered Options

##### Option 13.1: Single-Backend (LangChain) on Cloud Run (`cr-s05e01-radiomonitoring`) (ACCEPTED)
* **Description**: Implement the microservice using LangChain (`langchain-google-genai` with `ChatGoogleGenerativeAI`, `vertexai=True`), exposing `/health`, `/run`, and CLI execution (`run_cli()`).
* **Data Engineering & Performance**: Lean codebase; fast cold starts in Cloud Run.
* **Pros & Cons**:
  * Good, maximizes development velocity on the core data routing architecture.
  * Bad / Trade-off, intentional deviation from dual-framework parity (recorded below).

---

## 4. Technical Baseline Alignment (GEMINI.md)

**Baseline Alignment: 95%**

Divergences:
- **Framework Parity**: Implemented with a single backend (**LangChain**) instead of dual-framework parity (LangChain + Google ADK).
  - *Reason*: Explicit architectural decision by Artur to minimize development footprint and accelerate delivery on the core data routing challenge.

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Lesson Source Markdown](../s05e01-architektura-1775412680.md)
  - [Video Transcript](../S05E01%20%5B1179919808%5D.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
