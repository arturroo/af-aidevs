---
status: "accepted"
date: 2026-09-10
decision-makers: ["Artur"]
consulted: ["Joi"]
informed: ["Joi"]
---

# Architectural Decision Record: Zero-Trust Preemptive Strike Drone Agent (`cr-s02e05-drone`)

## Context and Problem Statement

In task `drone` (lesson `s02e05`), the resistance has intercepted remote control over an armed military strike drone. The hostile System is preparing to destroy our base and nuclear power plant in Żarnowiec (Identifier: **`PWR6132PL`**). The plant's reactor core cooling is critically compromised because Lake Żarnowieckie has lost 80% of its water volume and is dammed off.

Our operational objective is to execute a preemptive deception strike:
1. Officially program the drone flight mission registry to target `PWR6132PL` (so the System registers the plant as destroyed on its tactical maps).
2. Physically divert the drone's flight path and explosive payload delivery directly to the **dam** on Lake Żarnowieckie to breach it, flooding the cooling canals and saving the reactor.

The mission requires:
- Multimodal spatial analysis of a terrain grid map (`drone.png`) to extract grid dimensions and locate the dam sector `(column, row)`.
- Technical documentation ingestion (`drone.html`) to identify valid commands, navigate decoys/parameter traps, and formulate an ordered instruction sequence.
- Reactive iteration against Centrala's `/verify` endpoint, consuming diagnostic error feedback and recovering state via `hardReset` when necessary.
- Capturing the course completion flag `{FLG:...}` and recording full-fidelity telemetry in BigQuery dataset `s02e05`.

How should we design the multi-agent architecture, vision extraction, egress routing, Agentic RAG documentation engine, and loop recovery mechanisms to maintain zero-trust security and high execution reliability?

---

## Decision Drivers

* **In-Process Multi-Agent Topology**: Supervisor/Orchestrator and Vision Worker must execute within the same Python container process on Cloud Run (avoiding distributed network A2A latency and overhead).
* **Lean Context & Ephemeral Vision Ingestion**: High-resolution image bytes (`drone.png`) must be processed ephemerally during Stage 1; the resulting `(column, row)` coordinates are extracted into a typed Pydantic object, and raw image data is dropped from subsequent reasoning turns to prevent context bloat.
* **Dual-Framework Mastery (LangChain 1.2.15 & Google ADK)**: Both frameworks must be supported via a `--backend` CLI parameter (defaulting to `langchain`), utilizing **Gemini 3.8 Flash** (`gemini-3.8-flash`) with `thinking_level="low"`.
* **Zero-Trust Egress Isolation**: Container has zero direct internet access; all outbound web fetches and `/verify` submissions route strictly through `cr-mcp-web-gateway` via authenticated OIDC tokens.
* **Agentic RAG for Technical Documentation**: Distill raw HTML documentation into clean, structured Markdown, leveraging targeted RAG tools (`list_markdown_sections`, `read_markdown_section`, `read_file_lines`, `grep`) instead of naive full-file prompt stuffing.
* **Blast Radius & Loop Governance**: Bound the verification feedback loop to a maximum of 10 iterations, equipping the agent with prompt-level awareness and operational capability to issue `hardReset` if cumulative state corruption occurs.
* **Full-Fidelity Telemetry**: Stream unaggregated thoughts, tool calls, error loops, and verification results (including flags) to BigQuery dataset `s02e05`, with API keys masked.

---

## Considered Options

### 1. Agent Architecture & Process Boundary
* **Option 1A (Chosen - In-Process Multi-Agent: Supervisor + Vision Worker)**:
  A single Cloud Run container runs the Python runtime hosting both the Supervisor (orchestrator with delegation and tool access) and the Vision Worker (multimodal extractor). Image retrieval and workspace management are handled by the Supervisor; coordinates are exchanged directly in-memory.
* **Option 1B (Distributed A2A Microservices)**:
  Deploy separate Cloud Run microservices for Supervisor and Vision Agent communicating over HTTP A2A. Rejected due to unnecessary cold starts, network latency, and deployment complexity for a two-turn task.
* **Option 1C (Monolithic Single-Turn Prompt)**:
  A single LLM call attempting vision analysis and drone instruction formulation simultaneously. Rejected due to lack of iterative feedback handling and poor instruction reliability.

### 2. Framework & LLM Engine
* **Option 2A (Chosen - Dual Framework: LangChain 1.2.15 & Google ADK 1.33.0)**:
  Implement modular agent runners for both LangChain (`create_agent`) and Google ADK (`google-adk`), sharing tool definitions and schemas, powered by `gemini-3.8-flash` on Vertex AI with `thinking_level="low"`.
* **Option 2B (Google GenAI SDK Native Script)**:
  Use raw `google-genai` SDK without orchestration abstractions. Rejected in favor of Google ADK to align with production agentic frameworks established in `s02e04`.

### 3. Documentation Ingestion & Agentic RAG Engine
* **Option 3A (Chosen - Deterministic Markdown Conversion + Targeted Workspace RAG Tools)**:
  Download `drone.html` via `cr-mcp-web-gateway`, convert to clean Markdown deterministically using `markdownify` / `html2text` (0 tokens, 0 hallucination), and store in `cr-mcp-workspace`. Expose targeted RAG tools: `list_markdown_sections`, `read_markdown_section`, `read_file_lines(path, start_line, limit)`, and `grep`.
* **Option 3B (SQLite with FTS5 BM25 & sqlite-vec in `cr-mcp-workspace`)**:
  Build an embedded SQLite database inside `cr-mcp-workspace` using Full-Text Search (FTS5 BM25) and vector embeddings (`sqlite-vec`). Excellent for large-scale multi-megabyte corpora, but adds unnecessary dependency weight for a ~30KB single HTML document. Retained as an architectural reference for large future corpora.
* **Option 3C (External `cr-mcp-sqlite` Proxy over GCS FUSE)**:
  Store `.sqlite` on GCS and access it via a dedicated `cr-mcp-sqlite` microservice over GCS FUSE. Evaluated and identified as an architectural anti-pattern due to GCS FUSE lacking POSIX byte-range locking (`fcntl`/`flock`) and container cache invalidation issues.
* **Option 3D (Raw Prompt Ingestion)**:
  Dump the entire raw HTML or converted text into the LLM system prompt. Rejected because decoy functions and conflicting instructions induce hallucinations and bloat the prompt window.

### 4. Blast Radius & State Recovery Strategy
* **Option 4A (Chosen - Model-Autonomous `hardReset` with Hard Circuit Breaker)**:
  Provide the agent with explicit knowledge of the `hardReset` command and its purpose (restoring drone factory state upon persistent failure) in `system_prompt.md`. Allow the LLM to autonomously prepend `hardReset` when observing configuration lockup, backed by a hard ceiling of 10 iterations in the orchestrator.
* **Option 4B (Programmatic Prepend on Error)**:
  Automatically inject `hardReset` in Python code after 3 consecutive failures. Rejected because it takes strategic control away from the agent and may conflict with cumulative multi-step configuration procedures.
* **Option 4C (Always Prepend `hardReset`)**:
  Start every instruction sequence with `hardReset`. Rejected as it may violate API validation rules if reset is forbidden after initialization.

### 5. Multimodal Image Ingestion & Storage URI Resolution
* **Option 5A (Chosen - Canonical Unsigned `gs://` URI via `cr-mcp-workspace.get_file_uri`)**:
  `cr-mcp-workspace` stores `drone.png` in the session's workspace layer and provides `get_file_uri(file_path: str)`, which returns the authoritative, canonical `gs://af-aidevs-workspaces/...` URI. Because our primary model is internal to GCP (Gemini 3.8 Flash on Vertex AI), the Vertex AI Service Agent natively reads the blob directly from GCS using internal GCP IAM. This approach guarantees Zero-Trust compliance (the client agent has zero direct GCS bucket permissions), zero internet egress, zero RAM bloat in Cloud Run via `Part.from_uri()`, and zero signing overhead or URL expiration risk.
* **Option 5B (Temporary Time-Limited Signed URLs via `cr-mcp-workspace.generate_signed_url`)**:
  `cr-mcp-workspace` generates a short-lived HTTPS Signed URL (e.g. 15-minute TTL) with restricted read access. This pattern is indispensable when delegating visual analysis to external public LLMs (such as OpenAI or Anthropic) without exposing the entire bucket publicly. Evaluated and rejected for `s02e05` because our target model is internal Vertex AI, but retained as a platform capability for future multi-provider hybrid workflows.
* **Option 5C (Inline Binary Ingestion into Container RAM)**:
  Agent reads the image bytes into container memory and passes base64 raw bytes (`Part.from_bytes()`) over HTTP to Vertex AI. Rejected due to unnecessary Cloud Run memory consumption and redundant network upload bandwidth, though token billing on Vertex AI is identical.

---

## Decision Outcome

Chosen combination: **Option 1A + Option 2A + Option 3A + Option 4A + Option 5A**, because:

1. **Optimal Latency & Cohesion**: Running Supervisor and Vision Worker in the same Python process eliminates distributed serialization overhead while maintaining clean separation of concerns.
2. **Minimalist & Zero-Hallucination RAG**: Deterministic HTML-to-Markdown conversion (`markdownify`) combined with `list_markdown_sections` and `read_file_lines` empowers the agent to inspect command signatures selectively without prompt overflow or hallucinated syntax.
3. **Resilient Feedback & Safe Recovery**: Equipping the agent with prompt-level awareness of `hardReset` and error diagnosis enables rapid, autonomous self-correction within a strictly enforced 10-iteration ceiling.
4. **Consistency with Platform Standards**: Dual-backend support (LangChain 1.2.15 and Google ADK) and full unaggregated telemetry in BigQuery (`s02e05`) guarantee continuity with lessons `s02e02` through `s02e04`.
5. **Zero-Trust Storage & Lean Multimodal Ingestion**: Delegating GCS URI resolution to `cr-mcp-workspace.get_file_uri` preserves the Principle of Least Privilege (no direct bucket-wide IAM for client agents) and avoids RAM bloat via `Part.from_uri()`.

### Consequences

* **Good**: High execution speed due to in-process execution and low thinking level (`low`).
* **Good**: Clean prompt context; image bytes discarded immediately after Vision Worker produces typed coordinates.
* **Good**: Zero-trust compliance; all outbound calls pass through `cr-mcp-web-gateway` with OIDC identity tokens cached via `cachetools` (50 min TTL).
* **Good**: Resilient self-healing via `hardReset` without hardcoding command sequences in Python code.
* **Bad/Trade-off**: Requires implementing two additional generic RAG tools in `cr-mcp-workspace` (`html_to_markdown` and `read_file_lines`).

### Confirmation

1. **Unit & Contract Testing**: Verify that `DamCoordinates` schema accurately models grid dimensions and 1-indexed coordinates.
2. **Vision Stage Verification**: Verify Vision Worker correctly isolates the dam coordinates from `drone.png`.
3. **RAG Tool Verification**: Confirm `html_to_markdown` and `read_file_lines` function deterministically on `cr-mcp-workspace`.
4. **End-to-End Simulation**: Execute both `--backend langchain` and `--backend adk` to verify autonomous error recovery and `{FLG:...}` capture.
5. **Audit Traceability**: Query BigQuery table `s02e05.audit` to confirm all thoughts, tool calls, and masked credentials are recorded.

---

## Pros and Cons of the Options

### In-Process Multi-Agent (Option 1A) vs Distributed A2A (Option 1B)
* **Good (1A)**: Sub-second invocation latency between Supervisor and Vision Worker.
* **Good (1A)**: Shared in-memory Pydantic state without remote serialization.
* **Bad (1A)**: Shared container memory footprint.
* **Bad (1B)**: Additional Cloud Run service deployments, IAM policies, and cold-start latencies.

### Deterministic Workspace RAG (Option 3A) vs SQLite FTS5 (Option 3B) vs GCS FUSE Proxy (Option 3C)
* **Good (3A)**: Pure Python standard processing, zero external DB dependencies, instant execution for small-to-medium docs.
* **Good (3B)**: Native BM25 ranking and SQL queries for massive multi-document corpora.
* **Bad (3B)**: Over-engineering for a single 30KB HTML manual.
* **Bad (3C)**: Anti-pattern on GCP. Cloud Storage FUSE does not support POSIX byte-range locking (`fcntl`/`flock`), risking stale reads and database corruption across concurrent Cloud Run instances.

---

## More Information

* **Related Documents**:
  - [BRD.md](file:///c:/Users/admin/git/arturroo/af-aidevs/lessons/s02e05-projektowanie-agentow/task/BRD.md)
  - [Pre-Flight Agent Readiness Checklist](file:///c:/Users/admin/git/arturroo/af-aidevs/docs/af-aidevs/patterns/agent-readiness-checklist.md)
  - [Cloud Run Token Caching](file:///c:/Users/admin/git/arturroo/af-aidevs/docs/af-aidevs/patterns/cloud-run-token-caching.md)
* **Status**: Set to `Proposed`. Requires review and transition to `Accepted` by Artur before PRD generation.
