<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-15
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S03E04 Negotiations Tooling (`cr-s03e04-negotiations`)

## 1. Context
To establish autonomous negotiations with survivor safe haven cities in S03E04 (`negotiations`), Centrala's external AI agent must discover cities that currently stock all three essential hardware components required to assemble a wind turbine. The agent communicates over public HTTP POST endpoints using unstructured Polish natural language queries with a strict budget of at most 10 execution turns. The tool responses must comply with a hard size envelope between 4 and 500 bytes (`4 <= len(bytes) <= 500`). The architectural fitness function is successful discovery of the common cities by Centrala's agent, followed by asynchronous verification (`{"action": "check"}`) securing the course flag (`{FLG:...}`) via `$AIDEVS_API_VERIFY`.

---

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Tool Endpoint Topology & Naming | Two Specialized Endpoints: `search_item_in_catalog` and `find_cities_having_items_ids` | 4-word descriptive names provide crystal-clear semantic guidance for Centrala's LLM, cleanly separating catalog item discovery from common city set intersection. |
| 2 | Query Extraction & Retrieval Formulation | Canonical Symmetric Entity Extraction ($0.4 \cdot S_{BM25} + 0.6 \cdot S_{vec}$) | Avoids the "Split-Query Asymmetric Retrieval" anti-pattern; feeds a single specification-rich phrase in parallel to BM25 and vector search to preserve ranking space consistency. |
| 3 | Candidate Ranking & Multi-Object Synthesis | Hierarchical Single-Turn LLM with `co_occurrence_cities` | Evaluates candidates holistically in a single call (~150ms), prioritizing items sharing common cities and formatting codes as `(kod: XXXXXX)`, avoiding isolated champion dead-ends. |
| 4 | Relational City Intersection & Error Policy | Parametric SQL + Deterministic Python Formatter + Fail-Fast 404 Error Guard | Enforces Single Responsibility (rejects charitable name lookups in Tool 2), eliminates LLM latency on city formatting ($<0.001$ ms), and guarantees 100% mathematical set intersection. |
| 5 | Knowledge Base Architecture, Embedding Model & Live Reload | Unified SQLite (`inventory.db`) with `sqlite-vec`, `text-multilingual-embedding-002`, Read-Only Mode, and `POST /reload-db` | Combines relational SQL and vector tables in one file, built locally via `scripts/build_inventory_db.py` and uploaded to GCS (`shared/s03e04/`), cached in `/tmp` in immutable read-only mode (`mode=ro`) with hot-reload support. |
| 6 | Execution Framework & Direct Invocation | Dual Backend Direct Structured Invocation (LangChain `ainvoke` vs. Google GenAI SDK `generate_content`) | Eliminates the agent-in-agent nesting anti-pattern on tool webhooks, maintaining sub-250ms responses while preserving dual framework parity for task orchestration. |
| 7 | Security, Telemetry & Byte Guardrail | Baseline Adherence (Cloud Run, Model Armor, BigQuery Streaming, Pydantic Byte Guardrail) | 100% compliant with `GEMINI.md`: Model Armor prompt sanitization, BigQuery real-time streaming audit (`af-aidevs.s03e04.audit`), and strict Pydantic byte boundaries ($4 \le \text{bytes} \le 500$). |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Tool Endpoint Topology & Naming

#### Problem & Drivers
Centrala's agent receives natural language instructions to locate cities with 3 specific wind turbine parts and is allocated a maximum of 10 interaction steps. The system must register tools with names and descriptions that make the agent's multi-step discovery path completely intuitive.

#### Considered Options

##### Option 1.1: `search_item_in_catalog` and `find_cities_having_items_ids` (ACCEPTED)
* **Description**:
  1. `search_item_in_catalog` (Route: `/api/search-item-in-catalog`):
     - Description: *"Przeszukuje katalog 2137 podzespołów technicznych. W polu params podaj naturalny opis poszukiwanych części (np. 'kabel miedziany 10m', 'silnik krokowy'). Narzędzie zwróci pasujące pozycje wraz z ich 6-znakowymi kodami ID oraz rekomendacją dostępności."*
  2. `find_cities_having_items_ids` (Route: `/api/find-cities-having-items-ids`):
     - Description: *"Zwraca miasta posiadające w magazynie WSZYSTKIE poszukiwane przedmioty jednocześnie. W polu params przekaż kody przedmiotów oddzielone przecinkami (np. 'TRB500, KBL010, FLW12V'). Narzędzie zwróci miasta oferujące pełen komplet."*
* **Pros & Cons**:
  * Good, self-documenting 4-word names that unambiguously convey their function.
  * Bad / Trade-off, consumes both available tool slots.

##### Option 1.2: Cryptic or Getter-Style Naming (`check_cities`, `get_item_id`) (REJECTED)
* **Description**: Using short names like `check_cities` or `get_item_id`.
* **Reason for Rejection**: `get_item_id` sounds like a primary-key getter (misleading the model into thinking it must already know the item), while `check_cities` is ambiguous (sounding like a status/population check). Centrala's agent wastes turns clarifying intent.

##### Option 1.3: Monolithic Unified Endpoint (`query_inventory`) (REJECTED)
* **Description**: A single endpoint attempting to handle both item search and city lookups dynamically.
* **Reason for Rejection**: Forces the backend to guess intent, increases prompt ambiguity, and risks misrouting multi-part conversational queries.

---

### Decision 2: Query Extraction & Retrieval Formulation

#### Problem & Drivers
Centrala sends unstructured natural language containing conversational small-talk, quarters, and filler (e.g. *"w 2026Q1 bylo trudno zlapac koniec z koncem... szukam kabla 10m i masztu"*). We must extract clean search intent without falling into retrieval anti-patterns.

#### Considered Options

##### Option 2.1: Canonical Symmetric Entity Extraction ($0.4 \cdot S_{BM25} + 0.6 \cdot S_{vec}$) (ACCEPTED)
* **Description**: Single-turn Gemini 3.8 Flash extracts clean technical hardware entities (`name_with_spec: list[str]`). The exact same canonical phrase (e.g. `"kabel miedziany 10m"`) is queried in parallel against BM25/Fuzzy and vector embeddings, combined via weighted fusion.
* **Pros & Cons**:
  * Good, preserves mathematical consistency of the ranking space; BM25 enforces numerical precision (`10m`), vectors capture synonyms (`przewód`).

##### Option 2.2: Split-Query Asymmetric Retrieval (REJECTED - ANTI-PATTERN)
* **Description**: Prompting the LLM to extract separate keyword phrases "optimized for BM25" and distinct semantic phrases "optimized for vector search".
* **Reason for Rejection**: Known RAG anti-pattern ("Ranking Space Drift"). Because BM25 and vector search evaluate two different queries, their scores represent fundamentally different semantic objects. Weighted fusion ($0.4 \cdot S_{BM25} + 0.6 \cdot S_{vec}$) compares apples to oranges, degrading ranking accuracy and causing hallucinated synonyms.

##### Option 2.3: Pure Naive Regex Parsing (`\b[A-Z0-9]{6}\b`) (REJECTED)
* **Description**: Using regular expressions to extract alphanumeric codes directly without LLM pre-filtering.
* **Reason for Rejection**: Directly refuted by edge cases like `"w 2026Q1..."`, where temporal tokens like `2026Q1` match the 6-character regex and poison database queries with nonexistent part codes.

---

### Decision 3: Multi-Candidate Ranking & Synthesis Architecture (`search_item_in_catalog`)

#### Problem & Drivers
When Centrala asks for multiple items (e.g. cable and mast), candidate items in `items.csv` exist in different subsets of cities. Returning an item that exists in an isolated city where other needed items are absent causes Centrala to hit dead-ends.

#### Considered Options

##### Option 3.1: Hierarchical Context in a Single LLM Call with `co_occurrence_cities` (ACCEPTED)
* **Description**:
  1. Retrieve Top-3 candidates for each requested part via Hybrid RAG.
  2. Query `connections.csv` in SQLite to evaluate shared city overlap between candidates, populating `co_occurrence_cities: list[str]`.
  3. Single-turn LLM receives a hierarchical `Tool1PostFlightInput` containing `search_results: list[EntitySearchResult]`, where each entity contains its own candidates.
  4. LLM performs a global combinatorial synthesis, selecting the optimal combination that maximizes common city overlap, explicitly formatted as `(kod: XXXXXX)`.
* **Pros & Cons**:
  * Good, global combinatorial visibility in one call; latency <150ms; explicit `(kod: XXXXXX)` formatting eliminates model confusion.

##### Option 3.2: Multi-Call Isolated Champion Selection (REJECTED)
* **Description**: Running a loop of separate LLM calls for each item to pick a "champion", followed by a final synthesis call (`for each item: choose champion -> synthesize`).
* **Reason for Rejection**: Severe combinatorial flaw: selecting a champion for the cable in isolation has zero visibility into what the mast call will select. It consistently picks parts stocked in disjoint cities, destroying the set intersection. Furthermore, it quadruples HTTP roundtrips and token latency (600–800ms vs 150ms).

##### Option 3.3: Flat Candidate List Structure (REJECTED)
* **Description**: Passing a flat list `candidates: list[ItemCandidate]` with a `query_entity` string field to a single LLM prompt.
* **Reason for Rejection**: High cognitive load on the LLM; models frequently cross-contaminate candidates between parts when flattened, mistaking mast candidates for cable candidates.

##### Option 3.4: Scalar Co-Occurrence Metric (`co_occurrence_count: int` only) (REJECTED)
* **Description**: Providing only an integer count of shared cities without the actual city names.
* **Reason for Rejection**: Conceals critical contextual data. An integer `count: 2` prevents the LLM from telling Centrala: *"Kabel A i Maszt B są dostępne w Krakowie i Warszawie"*. Providing `co_occurrence_cities: list[str]` gives full semantic transparency at negligible token cost (~4 tokens).

---

### Decision 4: Relational City Intersection & Error Policy (`find_cities_having_items_ids`)

#### Problem & Drivers
Centrala's agent invokes the second tool to find cities having all requested parts. We must ensure 100% mathematical precision while maintaining strict API discipline.

#### Considered Options

##### Option 4.1: Parametric SQL + Deterministic Python Formatter + Fail-Fast 404 Guard (ACCEPTED)
* **Description**:
  1. Gemini 3.8 Flash extracts genuine 6-character item codes (`Tool2PreFlightOutput(item_codes=...)`).
  2. **Fail-Fast Error Guard**: If `len(item_codes) == 0`, immediately return deterministic guidance without querying SQL:
     *"Błąd: Nie znaleziono 6-znakowych kodów w wiadomości. Użyj narzędzia search_item_in_catalog, aby uzyskać kody ID na podstawie opisów."*
  3. Parametric SQL execution with `HAVING COUNT(DISTINCT cn.itemCode) = :item_count`.
  4. Deterministic Python Formatter builds the city list in $<0.001$ ms ($\le 90$ bytes).
* **Pros & Cons**:
  * Good, 100% deterministic mathematical set intersection; zero database latency overhead; zero token cost on output formatting.

##### Option 4.2: Charitable Name-to-Code Fallback (`fallback_item_names`) (REJECTED)
* **Description**: Making Tool 2 "charitable" by attempting to resolve item names if Centrala forgets to pass codes.
* **Reason for Rejection**: Violates the Single Responsibility Principle (SRP). Blurring the boundaries between Tool 1 and Tool 2 encourages lazy agent behavior and prompt drift. Failing fast with clear instructions reinforces Centrala's correct multi-step tool usage.

##### Option 4.3: LLM Response Formatter for Cities (REJECTED)
* **Description**: Invoking an LLM to format the resulting list of cities.
* **Reason for Rejection**: Total waste of latency (150–250ms) and token budget. Data analysis proved that 10 city names take only 86 bytes; Python string formatting is instantaneous, 100% reliable, and guarantees the 500-byte cap.

##### Option 4.4: Free-Form Text-to-SQL Generation (REJECTED)
* **Description**: Prompting the LLM to write raw SQL statements directly against SQLite.
* **Reason for Rejection**: Prone to SQL injection, hallucinated table names, and syntax errors, frequently omitting the critical `HAVING COUNT(DISTINCT itemCode) = N` set intersection logic.

---

### Decision 5: Knowledge Base Architecture, Embedding Model & Live Reload

#### Problem & Drivers
The inventory consists of `cities.csv` (51 rows), `items.csv` (2,137 rows), and `connections.csv` (5,349 rows). We must choose an optimal embedding model for Polish technical terms, combine relational and vector search within SQLite, secure the database against attacks on a public Cloud Run instance, and enable live data reloads without container redeployments.

#### Considered Options

##### Option 5.1: Unified SQLite (`inventory.db`) with `sqlite-vec`, `gemini-embedding-2` (768d MRL), Read-Only Mode & Live Reload (ACCEPTED)
* **Description**:
  1. **Offline Ingestion & Embedding Generation via `gemini-embedding-2`**:
     - Local script `scripts/build_inventory_db.py` parses CSV files and generates embeddings using Google's newest omnimodal embedding model **`gemini-embedding-2`** via the `google-genai` SDK.
     - **Matryoshka Representation Learning (MRL):** Configured with `output_dimensionality=768` to compress embeddings into 768 dimensions without performance penalty, perfectly matching `sqlite-vec float[768]`.
     - **Asymmetric Information Retrieval Protocol:**
       - Database document indexing format: `title: none | text: {item_name}`
       - Runtime query search format: `task: search result | query: {query_entity}`
     - **Shared Lineage with Gemini 3.8 Flash:** Uses the same underlying tokenizer and concept representations as the generative LLM. Single SDK client (`google-genai`). Clean separation of concerns: vectors stay inside SQLite; the generative model receives only structured text results.
     - **Cost:** ~25,000 tokens @ $0.20/1M tokens = **~$0.005 USD** (or $0.00 within Google AI Studio free tier).
     - Uploads `inventory.db` to GCS: `gs://af-aidevs-workspaces/shared/s03e04/inventory.db`.
  2. **Unified Database Architecture (`sqlite-vec`)**:
     - Relational tables: `cities(code, name)`, `items(code, name)`, `connections(itemCode, cityCode)`.
     - Vector virtual table: `vec_items USING vec0(item_code TEXT PRIMARY KEY, embedding float[768])`.
     - Supports unified single-query joins between semantic vector distance and relational item/city tables.
  3. **Cloud Run Security (Immutable Read-Only Mode)**:
     - The database is cached locally in container memory/tmpfs (`/tmp/inventory.db`).
     - Opened strictly with SQLite URI read-only flag:
       `sqlite3.connect("file:/tmp/inventory.db?mode=ro", uri=True)`
     - Physically prevents data mutation, table dropping, or SQL injection tampering.
  4. **Live Operational Reload (`POST /reload-db`)**:
     - Exposes an admin endpoint that re-downloads `inventory.db` from `cr-mcp-workspace` and refreshes the in-memory connection pool without container restarts.
* **Pros & Cons**:
  * Good, cutting-edge SOTA retrieval accuracy with MRL 768d, shared Gemini tokenizer, ultra-fast local joins (<1ms), unhackable read-only posture, negligible cost ($0.005), and zero-downtime updates.

##### Option 5.2: Symmetric Semantic Textual Similarity (STS) Prefix (`task: sentence similarity`) (REJECTED - ANTI-PATTERN)
* **Description**: Using `task: sentence similarity | query: ...` for both database documents and search queries.
* **Reason for Rejection**: Google documentation strictly states: *"Do not use this for search or retrieval. It is intended for semantic textual similarity."* STS optimizes for paraphrase equivalence (Text A and Text B meaning the exact same sentence). In Information Retrieval (catalog search), query intents and catalog technical specs are asymmetric. Using STS results in severe recall degradation.

##### Option 5.3: Classical Vertex AI Text Embedding (`text-multilingual-embedding-002` / `text-embedding-004`) (REJECTED AS SECOND CHOICE)
* **Description**: Using older text-only models `text-multilingual-embedding-002` or `text-embedding-004` with `task_type=RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`.
* **Reason for Rejection**: Requires separate task_type enum bindings across SDK versions and lacks the latest unified omnimodal latent space improvements of `gemini-embedding-2`. Replaced by `gemini-embedding-2` with 768d MRL.

##### Option 5.3: Direct Remote MCP Call on Every Request (REJECTED)
* **Description**: Calling `cr-mcp-workspace` via HTTP for every single item lookup and join.
* **Reason for Rejection**: Incurs a 150–300ms network roundtrip penalty per query, risking Centrala agent timeouts.

##### Option 5.4: Static Bundling in Docker Image without Live Reload (REJECTED)
* **Description**: Hardcoding the SQLite file into the Docker container image.
* **Reason for Rejection**: Requires a full container rebuild, image push, and Cloud Run redeployment for any minor dataset modification or re-indexing.

---

### Decision 6: Execution Framework & Direct Invocation

#### Problem & Drivers
`GEMINI.md` defaults to multi-turn agent frameworks (`create_agent` / Google ADK `Agent`). However, for incoming HTTP tool webhooks where Centrala's external agent is already the multi-turn driver, wrapping each request in an internal autonomous ReAct loop introduces high latency and unpredictable timeouts.

#### Considered Options

##### Option 6.1: Direct Structured Invocation with Dual Backend Parity (ACCEPTED)
* **Description**:
  - Webhooks use **Direct Structured LLM Invocations**:
    - **Backend `langchain`:** `ChatGoogleGenerativeAI(model="gemini-3.8-flash")` with `.ainvoke(...)` and `.with_structured_output(...)`.
    - **Backend `adk`:** Google GenAI SDK (`google-genai`) with `client.aio.models.generate_content(...)` and `response_schema`.
  - Canonical endpoints:
    - `@app.get("/health")` and `@app.get("/")`: Canonical health and readiness probe (exact mirror).
    - `@app.post("/run")` and `run_cli()` in `main.py`: Task orchestrator registering tools with Centrala and polling verification status.
* **Pros & Cons**:
  * Good, eliminates latency overhead on incoming webhooks while honoring dual framework learning objectives.

##### Option 6.2: Autonomous Multi-Turn ReAct Agent Loop on Tool Webhooks (REJECTED - ANTI-PATTERN)
* **Description**: Launching a full `create_agent` / ADK `Runner` session for every incoming tool HTTP request.
* **Reason for Rejection**: Known anti-pattern ("Agent-in-Agent Nesting"). Centrala is already running an autonomous turn-based ReAct loop. Embedding an internal multi-turn agent inside each tool turn creates unpredictable latency (>1000ms), ballooning token costs, and risking Centrala step timeouts.

---

### Decision 7: Security, Telemetry & Byte Guardrail

#### Problem & Drivers
Must comply with `GEMINI.md` zero-trust security, telemetry logging, and Centrala's strict byte bounds.

#### Considered Options

##### Option 7.1: Full Baseline Adherence (ACCEPTED)
* **Description**: Cloud Run `cr-s03e04-negotiations`, Model Armor sanitization (`af_aidevs.model_armor`), BigQuery streaming audit (`af-aidevs.s03e04.audit`), SQLite read-only mode (`mode=ro`), and deterministic Pydantic validator enforcing $4 \le \text{len(output.encode('utf-8'))} \le 500$.

---

## 4. Technical Baseline Divergence (GEMINI.md)
* **Intentional Architectural Simplification:**
  - **Divergence:** Instead of wrapping tool endpoints in multi-turn autonomous ReAct agent loops (`create_agent` or `google.adk.Agent`), the service implements direct, single-turn structured LLM invocations (`ChatGoogleGenerativeAI.ainvoke` for LangChain and `google-genai` `client.aio.models.generate_content` for ADK/GenAI SDK).
  - **Reason:** Centrala's agent is already the external autonomous driver. Running an internal multi-turn agent on incoming tool webhooks is a known anti-pattern (agent-in-agent nesting) causing high latency (>1000ms) and risking Centrala step timeouts. Single-turn structured calls provide sub-250ms deterministic responses.

---

## 5. More Information
* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Gemini 3.8 Flash Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
  - [Agent Readiness Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
