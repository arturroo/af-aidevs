---
status: "accepted"
date: 2026-09-12
decision-makers: ["Artur"]
consulted: ["Joi"]
informed: ["Joi"]
---

# Architectural Decision Record: High-Throughput Sensor Telemetry Evaluation Engine (`cr-s03e01-evaluator`)

## Context and Problem Statement

In task `evaluation` (lesson `s03e01`), the Żarnowiec nuclear base and resistance infrastructure depend on an extensive network of nearly 10,000 industrial sensors monitoring critical physical metrics: water level, temperature, pressure, electrical voltage supply, and ambient humidity. Following recent flooding and reactor cooling operations, plant firmware is producing corrupted telemetry logs, and human plant operators are suspected of falsifying inspection notes—clearing alarms prematurely or falsely reporting errors to bypass security protocols.

The objective is to audit the entire telemetry archive (~10,000 JSON records), identify all defective files (comprising physical measurement violations, ghost channel signals, and operator discrepancy false alarms), and submit the complete list of anomalous file identifiers (`recheck`) to Centrala's `/verify` endpoint to capture the course flag (`{FLG:...}`).

Auditing 10,000 JSON files presents significant architectural challenges:
1. Sending 10,000 records directly to an LLM would incur immense token overhead, slow execution, and risk hallucinated arithmetic.
2. Ingesting remote data must comply strictly with the project's Zero-Trust egress policy, forbidding direct internet egress and requiring immutable audit records in the session workspace.
3. Reading 10,000 files individually over MCP (`read_file`) represents a severe distributed N+1 RPC network anti-pattern that would exhaust Cloud Run timeouts and connection pools.
4. Telemetry and evaluation decisions must be fully observable across both LangChain and Google ADK frameworks, integrating with BigQuery, LangSmith, and Langfuse.

How should we design the service architecture, ingestion pipeline, hybrid evaluation logic, caching strategy, and telemetry logging to ensure high performance (< 60s), zero-trust security, minimal LLM costs, and high precision?

---

## Decision Drivers

* **Zero-Trust Network Isolation**: 100% of outbound external HTTP requests (`sensors.zip` download and `/verify` submission) must route through `cr-mcp-web-gateway` with authenticated Google OIDC tokens. Direct container egress is strictly forbidden.
* **Cost & Token Optimization (Hybrid Decoupling)**: 100% of physical telemetry checks (sensor ranges and inactive channel zeroing) must execute programmatically in Python (0 LLM tokens, 0 hallucination). LLM inference is strictly reserved for semantic evaluation of operator notes on physically clean records.
* **Deduplication & Structured Response Caching**: Exploit boilerplate phrasing in operator notes by deduplicating unique strings, classifying each unique text exactly once via structured output, and caching decisions in-memory/JSON.
* **Chatty I/O & N+1 Prevention**: Download `sensors.zip` via `cr-mcp-web-gateway` into the session workspace as an audit artifact, then stream/unzip records in RAM via `zipfile.ZipFile` rather than issuing 10,000 individual remote MCP `read_file` network roundtrips.
* **Dual-Framework Parity**: Support both **LangChain 1.2.15** (with LangSmith tracing) and **Google ADK** (with Langfuse tracing), configurable via `--backend` CLI parameter (default `langchain`), driven by **Gemini 3.8 Flash** (`gemini-3.8-flash`) on Vertex AI (`location=global`, `thinking_level="low"`).
* **Comprehensive BigQuery Telemetry**: Stream full execution telemetry (audit events, physical anomaly counts, unique note evaluations, token consumption, and verification outcome) directly to BigQuery dataset `s03e01.audit` via `af_aidevs.audit.bigquery.AuditService`.
* **Microservice Topology & Endpoint Standards**: Deploy as a stateless Cloud Run service `cr-s03e01-evaluator` implementing standard platform endpoints: `@app.get("/health")` and `@app.get("/")` for health checks, `@app.post("/run", response_model=RunTaskResponse)` for triggering task execution, and a local `run_cli` entrypoint via `uv run python main.py --backend [langchain|adk]`, backed by Terraform IaC (`terraform/`).

---

## Considered Options

### 1. Ingestion & Storage Strategy for 10,000 Files
* **Option 1A (Chosen - Zero-Trust Gateway Fetch with Metadata Piggybacking + cr-mcp-workspace.read_binary_file + In-Memory Streaming Unzip)**:
  `cr-s03e01-evaluator` calls `cr-mcp-web-gateway.fetch_web_resource` with `url=$AIDEVS_SENSORS_DATA_URL` and `output_path="sensors.zip"`.
  **Metadata Piggybacking Pattern**: Instead of returning a plain text string, `fetch_web_resource` returns a typed Pydantic model:
  `FetchWebResourceResponse(output_path: str, size_bytes: int, mime_type: str, is_binary: bool, sha256: str, status: str)`.
  This immediately informs the caller of the exact file size, MIME type (`application/zip`), binary classification (`is_binary=True`), and SHA-256 checksum in a single network roundtrip, eliminating the need for an immediate follow-up `get_file_info` call. For existing workspace files, `cr-mcp-workspace` enriches `list_files` and provides `get_file_info` returning identical metadata.
  To access the binary archive without violating architectural boundaries or requiring broad GCS IAM permissions, `cr-mcp-workspace` exposes a typed binary tool:
  `read_binary_file(file_path: str, reasoning: str) -> ReadBinaryFileResponse(data_base64: str, mime_type: str, size_bytes: int, sha256: str)`
  governed by a deterministic 50 MB circuit breaker that rejects oversized files before memory allocation (preventing Cloud Run OOM Exit Code 137).
  Knowing from the fetch response that `is_binary=True` and `size_bytes < 50MB`, the evaluator invokes `read_binary_file("sensors.zip")`, verifies the SHA-256 checksum, decodes the bytes in RAM (`base64.b64decode`), and initializes `zipfile.ZipFile(io.BytesIO(raw_bytes))`. It iterates over `zip_ref.namelist()`, reading each JSON file's bytes on the fly via `zip_ref.read(filename)`. This processes all ~10,000 JSON records in < 1.5 seconds with zero disk I/O, zero network latency, and zero hidden fallbacks.
* **Option 1B (MCP `unzip` + 10,000 Sequential `read_file` RPCs)**:
  Add an `unzip` tool to `cr-mcp-workspace`, extract files into GCS, and invoke `read_file` 10,000 times over MCP. Rejected as a critical distributed systems anti-pattern: 10,000 HTTP roundtrips at ~30–50ms would consume > 300–500 seconds, causing Cloud Run HTTP 504 timeouts, socket exhaustion, and excessive GCS Class B operations.
* **Option 1C (Direct Container Egress Download via httpx)**:
  Download `sensors.zip` directly from the container to memory. Rejected because it violates the repository's Zero-Trust egress policy and bypasses gateway audit logging.

### 2. Semantic Operator Note Evaluation & Caching
* **Option 2A (Chosen - Two-Tier Hybrid Pipeline: Note Deduplication + Pydantic Structured Output + Response Cache)**:
  Extract unique `operator_notes` strings only from files that have passed physical sensor validation. Classify unique strings using `gemini-3.8-flash` with Pydantic structured output (`OperatorNoteEvaluation: is_anomaly: bool, reasoning: str`). Cache results in an in-memory dictionary and persist to JSON. If the unique note count exceeds an unexpected safety ceiling (> 500 unique strings), apply dynamic batching.
* **Option 2B (Windowed Batch Prompts of 50–100 Files)**:
  Bundle batches of 50–100 file records into single prompt windows, asking the model to return IDs of anomalous files. Rejected due to hallucination risks on file IDs, "lost in the middle" degradation, and inability to reuse cached results when a single note changes.
* **Option 2C (Vector Embeddings & Clustering via text-embedding-005)**:
  Generate text embeddings for notes and cluster them using DBSCAN/KMeans. Rejected as overengineering; semantic similarity can conflate subtle antonyms (e.g. *"readings within bounds"* vs *"readings NOT within bounds"*), risking catastrophic false positives in safety-critical evaluations.

### 3. Execution Framework & Observability
* **Option 3A (Chosen - Dual-Backend: LangChain 1.2.15 + Google ADK with Dual Tracing)**:
  Implement modular evaluation agents for both LangChain 1.2.15 (with LangSmith integration) and Google ADK (with Langfuse integration). Default backend is `langchain`. Both frameworks share schema models, physical evaluation logic, and telemetry pipelines.
* **Option 3B (LangChain Only)**:
  Implement only LangChain 1.2.15. Rejected to maintain parity with course guidelines and dual-framework mastery demonstrated in `s02e04` and `s02e05`.
* **Option 3C (Google GenAI SDK Native Script)**:
  Implement raw Python scripts without agent frameworks. Rejected because it lacks structured callback hooks and agentic telemetry integration.

### 4. Orchestration Paradigm: Autonomous ReAct Agent Loop vs. Augmented Deterministic Pipeline ("Program z AI")
* **Option 4A (Chosen - Augmented Deterministic Pipeline / "Program z AI")**:
  The microservice `cr-s03e01-evaluator` executes a deterministic, code-orchestrated pipeline in Python:
  1. Invokes `cr-mcp-web-gateway.fetch_web_resource` to download `sensors.zip` into the session workspace.
  2. Invokes `cr-mcp-workspace.read_binary_file` (with a 50 MB circuit breaker) to retrieve the archive bytes.
  3. Decompresses and streams 10,000 JSON records in RAM via `zipfile.ZipFile`, completing deterministic physical checks in < 1.5 seconds.
  4. Isolates unique operator notes from physically clean files.
  5. Employs the LLM (`gemini-3.8-flash` via LangChain 1.2.15 or Google ADK) strictly as a specialized **Evaluator / Judge** using Pydantic structured output (`OperatorNoteEvaluation`) with in-memory caching.
  6. Maps evaluated notes back to file IDs, merges with physical anomalies, and submits `recheck` via `cr-mcp-web-gateway.post_web_resource`.
* **Option 4B (Autonomous ReAct Agent Loop with Domain Tools / "Agent Theater" - Declared Obsolete)**:
  Equip an autonomous LLM agent with high-level domain tools (`download_archive`, `audit_telemetry_archive`, `submit_verification`) in an open ReAct loop. Evaluated and declared **obsolete** for this task. Because the sequence of operations across 10,000 files is 100% linear, known, and deterministic, wrapping it in an autonomous ReAct loop constitutes "Agent Theater": it adds unnecessary multi-turn latency, invites tool hallucination, risks non-deterministic skips, and violates the platform's *Workflow vs. Agent Decision Matrix* (`docs/af-aidevs/patterns/agent-readiness-checklist.md`).

---

## Decision Outcome

Chosen combination: **Option 1A + Option 2A + Option 3A + Option 4A**, because:

1. **Zero Egress & High Throughput**: Staging `sensors.zip` via `cr-mcp-web-gateway` maintains Zero-Trust compliance and creates an offline audit artifact, while in-memory streaming through `zipfile.ZipFile` avoids the catastrophic latency of 10,000 MCP network roundtrips.
2. **Extreme Token & Cost Efficiency**: Over 95% of data processing is handled deterministically by Python in milliseconds. Semantic LLM evaluation is restricted to unique operator notes from physically clean files, reducing token usage by > 98%.
3. **Robust Observability**: Dual tracing (LangSmith for LangChain, Langfuse for Google ADK) combined with direct streaming to BigQuery dataset `s03e01.audit` guarantees full auditability of all physical checks, model classifications, and verification outcomes.
4. **Elimination of Agent Theater & Maximal Reliability ("Program z AI")**: In accordance with Google SRE best practices and the platform's *Workflow vs. Agent Decision Matrix* (`docs/af-aidevs/patterns/agent-readiness-checklist.md`), replacing an autonomous ReAct loop with an Augmented Deterministic Pipeline ("Program z AI") eliminates multi-turn tool calling latency, removes hallucination risks, and guarantees deterministic processing of all 10,000 records while leveraging the LLM strictly as a semantic judge with Pydantic structured output.

### Consequences

* **Good**: End-to-end audit of all 10,000 files completes in under 30 seconds.
* **Good**: Zero direct internet egress from the evaluation container; all external communication flows through `cr-mcp-web-gateway`.
* **Good**: `sensors.zip` and `run_notes.txt` are preserved in the session workspace for offline reproducibility.
* **Good**: Low token expenditure; only distinct unique operator notes from healthy files trigger LLM inference.
* **Good**: Full-fidelity audit trail in BigQuery `s03e01.audit`.
* **Bad/Trade-off**: Requires sufficient container RAM (minimum 1 GiB) to hold `sensors.zip` and unpacked JSON structures simultaneously during the in-memory stream.

### Confirmation

1. **Unit Tests (`tests/test_sensor_evaluation.py`)**: Validate deterministic range checks, ghost reading detection (inactive channel != 0), and operator note discrepancy logic against fixture datasets.
2. **Integration Verification**: Verify that `fetch_web_resource` stages `sensors.zip` through `cr-mcp-web-gateway` and `post_web_resource` dispatches the `/verify` payload.
3. **End-to-End Execution**: Execute both `--backend langchain` and `--backend adk` to verify identical anomaly detection results, flag capture (`{FLG:...}`), and `run_notes.txt` generation.
4. **BigQuery Audit Validation**: Query BigQuery table `s03e01.audit` to confirm all session events, physical anomaly counts, unique note evaluations, and verification responses are logged.

---

## Pros and Cons of the Options

### In-Memory Streaming Unzip (Option 1A) vs Chatty MCP `read_file` (Option 1B)
* **Good (1A)**: Sub-second parsing of ~10,000 JSON files without disk or network I/O latency.
* **Good (1A)**: Zero risk of Cloud Run HTTP 504 timeouts or connection pool exhaustion.
* **Good (1A)**: Preserves `sensors.zip` in session workspace as a single immutable audit artifact.
* **Bad (1A)**: Peak memory footprint of ~200–300 MB during archive decompression.
* **Bad (1B)**: 10,000 HTTP roundtrips over MCP create a severe distributed systems bottleneck (~5–8 minutes latency), risking container failure and generating thousands of redundant log rows.

### Note Deduplication & Caching (Option 2A) vs Batching Prompts (Option 2B)
* **Good (2A)**: 100% evaluation consistency across repeated note texts; zero redundant tokens spent on duplicate phrases.
* **Good (2A)**: Structured Pydantic schema guarantees type-safe boolean outputs without regex extraction.
* **Good (2A)**: Safe against prompt injection in batch contexts; each note is evaluated in its own isolated turn.
* **Bad (2A)**: Requires two-pass processing (aggregation of unique texts followed by reverse ID mapping).
* **Bad (2B)**: LLM may hallucinate or truncate file IDs in large batches; batch-level prompt cache is invalidated if any single note changes.

### Augmented Deterministic Pipeline / "Program z AI" (Option 4A) vs Autonomous ReAct Loop / "Agent Theater" (Option 4B)
* **Good (4A)**: 100% predictable execution path; eliminates infinite tool-calling loops and non-deterministic skipping of files.
* **Good (4A)**: Sub-second latency for physical telemetry processing across 10,000 files in Python.
* **Good (4A)**: Minimal token spend; LLM is invoked strictly as a structured evaluator for unique semantic strings.
* **Good (4A)**: Direct alignment with Google DeepMind SRE principles ("Workflow over Agent when steps are fixed").
* **Bad (4A)**: Less "autonomous agentic discovery" — requires upfront software engineering of the pipeline stages.
* **Bad (4B)**: "Agent Theater" — introduces artificial multi-turn latency, risks context overflow if agent attempts to inspect files individually, and provides zero operational benefit for a deterministic 10,000-record batch workload.

---

## More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Pre-Flight Agent Readiness Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
* **Status**: Set to `Proposed`. Requires review and transition to `Accepted` by Artur before PRD generation.
