<!-- Source: https://github.com/adr/madr/blob/4.0.0/template/adr-template.md -->
<!-- MADR project: https://adr.github.io/madr/ -->

---
status: "accepted"
date: 2026-08-23
decision-makers: Artur
consulted: Artur
informed: Artur
---

# Agentic Electrical Circuit Solver with A2A Vision Specialist, Schema Registry in Artifact Registry, Ephemeral Signed URLs, and Modular Clean Architecture

## Context and Problem Statement

In lesson S02E02, the task (`electricity`) requires solving a 3x3 electrical grid puzzle to route emergency power from grid position `3x1` to three nuclear power plant units (`PWR6132PL`, `PWR1593PL`, `PWR7264PL`). The board is supplied as a dynamic PNG image, and the reference solution is also a PNG image. Each 90-degree clockwise rotation of a tile (`AxB`) requires a discrete POST request to the verification endpoint.

Additionally, previous lessons suffered from architectural debt:
1. **Monolithic Scripts:** `s02e01` grew to 424 lines in `main.py`, mixing HTTP routing, LLM prompts, token counting, CSV parsing, MCP clients, and BigQuery auditing.
2. **Boilerplate Duplication:** 60–80 lines of identical GCP OIDC token fetching, caching, and MCP client initialization were copy-pasted across lessons instead of using our shared package.
3. **Multimodal Perception vs. Sandboxing:** We need a way to pass images to multimodal LLMs without breaking session isolation or embedding long-lived cloud credentials in agent contexts.

## Decision Drivers

* **Encapsulated Vision Specialist (A2A Pattern):** Visual processing must be decoupled from puzzle orchestration. A dedicated Vision Specialist Agent handles image manipulation and visual interpretation.
* **Hybrid Vision Tooling (CV + Multimodal LLM):** The Vision Agent has access to fast deterministic CV tools (PIL grid slicing, edge pixel sampling) and a multimodal LLM tool (Gemini on Vertex AI).
* **Zero-Trust Ephemeral Link Security:** Agents operate exclusively on session-relative paths (`electricity.png`, `tiles/1x1.png`). When delegating to multimodal LLMs, the Vision Agent programmatically generates 2-minute expiring Signed URLs (`https://storage.googleapis.com/...`), ensuring zero long-lived data exposure.
* **Centralized Schema Registry & Artifact Registry Packaging:** Shared models (`Generic[T]` envelopes, domain schemas) and client infrastructure (OIDC, MCP Client, BigQuery Audit) reside in `af_aidevs` on GCP Artifact Registry, acting as a single source of truth (CA-like authority) to prevent schema poisoning and code duplication.
* **Multi-layered Workspace Virtual File System (OverlayFS / UnionFS Pattern):** To eliminate direct client-side GCS access and avoid duplicating static reference assets (e.g. `solved_electricity.png`), `cr-mcp-workspace` enforces a dual-layer Virtual File System:
  - **Lower Layer (Read-Only Shared):** `gs://af-aidevs-workspaces/shared/{lesson_id}/`
  - **Upper Layer (Read-Write Session):** `gs://af-aidevs-workspaces/{caller_identity}/{x_session_id}/`
  File reads check the session layer first, falling back to the shared layer. File writes strictly mutate the session layer.
* **Modular Clean Architecture & SOLID Standards:** Every lesson codebase must be split into dedicated modules (< 150 lines per file) utilizing the Factory Pattern (`AgentFactory`) to support dual backends (`--backend [langchain|adk]`).
* **Observability & Auditing Standards:** Deep tracing across frameworks: LangSmith for LangChain 1.2.15, Langfuse for Google ADK, and synchronous BigQuery audit logging into dataset `s02e02`.

## Considered Options

* **Option 1: Monolithic Script with Direct HTTPX & Full-Image Vision Prompting.** A single Python script downloads images directly, sends the entire 3x3 PNG to Gemini in one prompt asking for all 9 rotations, and sends POST requests locally without MCP or BigQuery audit tables.
* **Option 2: Direct MCP Tooling in Main Agent.** The main agent directly invokes MCP tools for cropping and visual inspection without an intermediate subagent.
* **Option 3: Lesson-Specific Hardcoded Vision Subagent.** A vision subagent that has hardcoded schemas for lesson S02E02, requiring redeployment for every subsequent lesson.
* **Option 4: A2A Vision Specialist with Artifact Registry Schema Registry, OverlayFS Multi-layered Workspace, Ephemeral Signed URLs, and Modular Clean Architecture.** (Chosen)

## Decision Outcome

Chosen option: **Option 4**, because:

1. **Clean Architectural Separation (A2A Protocol):** Decouples visual analysis from game logic. The Vision Agent becomes a reusable service for all future lessons requiring multimodal perception.
2. **Hybrid CV + LLM Efficiency:** Fast deterministic edge pixel sampling solves standard tiles in <1ms with 0 token cost, while multimodal Gemini is invoked only as a fallback for ambiguous tiles with lower confidence scores.
3. **Zero-Trust Ephemeral Links & Multi-Layered Workspace (OverlayFS):** Agents exchange session-relative paths with zero direct GCS bucket IAM permissions. The MCP server seamlessly cascades file lookups between session storage and immutable shared assets (`shared/s02e02/`).
4. **Shared Package Modularization (`af_aidevs` in Artifact Registry):** Eliminates 60-80 lines of repeated boilerplate per lesson by packaging `GoogleOIDCAuth`, `create_mcp_client`, `BigQueryAuditService`, and `AgentResponseEnvelope[T]`.
5. **Robust Google AIP Data Contract:**
   - Standard 2D matrix for grid rotations: `rotations: list[list[int]]` ($3 \times 3$).
   - Granular observability: global `confidence: float` + `tile_confidence: list[list[float]]` ($3 \times 3$).
   - Full audit trail: top-level `reasoning: str` for BigQuery ingestion.
6. **Factory Pattern & Clean Architecture:** Task codebase is organized into clean, single-responsibility files (`config.py`, `schemas.py`, `services/`, `agents/`, `main.py`) keeping `main.py` under 80 lines.

### Consequences

* **Good:** Establishes a true Agent-to-Agent (A2A) paradigm reusable across the entire AI_Devs course.
* **Good:** 2-minute Signed URLs ensure tight security alignment with enterprise cloud best practices.
* **Good:** Deterministic CV tools minimize token costs while multimodal LLM ensures robust fallback.
* **Good:** Eliminates monolithic code bloat across all future lessons.
* **Neutral:** Requires publishing an updated `af_aidevs` package (v0.2.0) to Artifact Registry before task implementation.

### Confirmation

The implementation and compliance will be confirmed by:
1. Successful build and publish of `af_aidevs` v0.2.0 to Google Artifact Registry.
2. Verification of A2A communication over HTTP with OIDC token authentication and `X-Session-ID` propagation.
3. Correct generation of 2-minute Signed URLs from GCS bucket `af-aidevs-workspaces`.
4. Validation of BigQuery audit records in `s02e02.audit`.
5. Successful execution of both `--backend langchain` (LangSmith trace) and `--backend adk` (Langfuse trace).
6. Successful retrieval and capture of the `{FLG:...}` flag upon completing the electrical circuit puzzle.

## Pros and Cons of the Options

### Option 1: Monolithic Script with Direct HTTPX & Single Full-Image Vision

* **Good:** Fast initial script creation.
* **Bad:** High risk of spatial confusion on 3x3 grids.
* **Bad:** Violates DRY and creates unmaintainable monolithic files (400+ lines).
* **Bad:** Bypasses MCP and central audit infrastructure.

### Option 2: Direct MCP Tooling in Main Agent

* **Good:** No subagent network hop.
* **Bad:** Clutters the main agent context with low-level visual parsing tools.
* **Bad:** Does not decouple image processing logic from puzzle solving logic.

### Option 3: Lesson-Specific Hardcoded Vision Subagent

* **Good:** Encapsulates visual logic for S02E02.
* **Bad:** Poor scalability; requires modifying and redeploying the vision service for every future lesson.
* **Bad:** High maintenance overhead.

### Option 4: A2A Vision Specialist with Artifact Registry Schema Registry & Modular Clean Architecture

* **Good:** Maximum reusability across the course.
* **Good:** Strong type safety via `Generic[T]` envelopes and Artifact Registry versioning.
* **Good:** Optimal performance combining 0-token CV edge sampling with Gemini multimodal fallback.
* **Good:** Strict Zero-Trust security with 2-minute Signed URLs.
* **Good:** Clean, modular code following SOLID and Factory design patterns.
* **Neutral:** Upfront refactoring of the shared `af_aidevs` package.

## More Information

- **BigQuery Dataset:** `s02e02`
- **Audit Table:** `s02e02.audit`
- **Vision Agent Deployment:** Cloud Run service `cr-agent-vision` (or local modular service during dev)
- **Signed URL Expiration:** 120 seconds (2 minutes)
- **Target Models:** Vertex AI `gemini-3-flash-preview` / `gemini-2.5-flash`
- **LangChain Version:** `1.2.15`
- **Pydantic Version:** `2.13.4`
