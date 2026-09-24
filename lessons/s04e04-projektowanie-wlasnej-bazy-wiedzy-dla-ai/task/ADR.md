<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "Accepted"
date: 2026-09-23
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S04E04 - Digital Knowledge Base & Virtual Filesystem (filesystem)

## 1. Context
The system must parse, normalize, and organize Natan Rams' unstructured trade notes into a coherent three-tier virtual knowledge base (`/miasta`, `/osoby`, `/towary`) hosted on Centrala's API (`$AIDEVS_API_VERIFY` with task `"filesystem"`). The target environment requires strict ASCII compliance, discrete integer mappings without measurement units, nominative singular naming, and referential link integrity across all Markdown hyperlinks. The primary architectural objective is to establish an end-to-end, resilient transformation pipeline that stages and tracks progress via a local workspace buffer, reinforces explicit Polish language grammatical framing across all model touchpoints, enforces strict deterministic pre-flight contract validation with a subagent linguistic evaluator before mutating external state, and executes atomic verification via `action: "done"` to securely capture the course flag.

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Architectural Baseline & GCP Alignment | 100% Adherence to GEMINI.md Baseline | Standardizes Cloud Run microservice (`cr-s04e04-filesystem`), BigQuery dataset `s04e04`, Gemini 3.8 Flash, dual framework (LangChain + Google ADK), and Terraform registration. |
| 2 | Data Ingestion & Lemmatization Strategy | LLM-Assisted Structured Extraction (Gemini 3.8 Flash + Pydantic) | Accurately resolves complex Polish inflection, plurals, units, and implicit dialogue references into validated Pydantic models. |
| 3 | Virtual Filesystem Staging & Synchronization | Workspace Staging Buffer + Progress Checklist (`TODOs.md`) + Atomic Batch Push | Stages files cleanly in `cr-mcp-workspace`, tracks progress via `TODOs.md` to prevent agent state loss, resets remote state, and pushes all files in a single atomic HTTP request. |
| 4 | Multi-City Commodity Representation | Multi-Link Newline Markdown Format | Ensures 100% knowledge completeness by listing all seller city links separated by newlines without brittle bullet tokens. |
| 5 | Pre-Flight Quality Gate & Linguistic Subagent | Deterministic Guardrail (`validate_workspace`) + Flash-Lite Subagent with Completeness Validation | Validates ASCII, JSON, and referential link integrity deterministically; delegates noun singular nominative verification to `gemini-3.8-flash-lite`, with a strict contract guard asserting 100% input word coverage before emitting the tool report. |
| 6 | Multilingual Context & Polish Linguistic Framing | Triple-Anchor Polish Linguistic Framing (System Prompts, Subagent Prompts, and Tool Schema Metadata) | Eliminates model ambiguity regarding inflections and transliteration by explicitly grounding the Polish domain context in global system instructions, subagent few-shot prompts, and Pydantic field schemas. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Architectural Baseline Alignment & GCP Standards

#### Problem & Drivers
The system requires deployment as a production-grade Cloud Run service with dual agent framework support (LangChain and Google ADK), auditable BigQuery telemetry, and IaC registration without deviations from project standards.

#### Considered Options

##### Option 1.1: 100% Adherence to GEMINI.md Baseline (ACCEPTED)
* **Description**: Microservice `cr-s04e04-filesystem` packaged with FastAPI, dual agents (`langchain==1.2.15` and `google-adk==1.33.0`), Gemini 3.8 Flash on Vertex AI (`global`, `thinking_level="low"`), streaming BigQuery audit logging to dataset `s04e04`, Python 3.13.5 via `uv`, and complete Terraform provisioning in `terraform/variables.tf`.
* **Data Engineering & Performance**: Zero cold-start bloat due to selective module loading ("Podejście A"); sub-second latency on Vertex AI global endpoint; telemetry streamed asynchronously to BigQuery.
* **Cost & FinOps**: Cloud Run scale-to-zero; Gemini 3.8 Flash low-tier thinking minimizes token consumption; BigQuery free-tier storage.
* **Security & Reliability**: No hardcoded secrets or external URLs; all configuration sourced from Secret Manager and local `.env` fallbacks.
* **Pros & Cons**:
  * Good, because it adheres strictly to repository standards and enables dual framework learning.
  * Good, because automated CI/CD and container scaffolding are 100% uniform.

##### Option 1.2: Ad-Hoc Script Execution (REJECTED)
* **Description**: A standalone Python script without containerization or BigQuery telemetry.
* **Pros & Cons**:
  * Good, because it is slightly faster to draft locally.
  * Bad, because it violates core repository architectural requirements and lacks cloud auditability.

#### Consequences
* **Positive**: Complete reproducibility, cloud readiness, and unified telemetry across both LangChain and Google ADK backends.
* **Confirmation**: Verified via `pytest`, `ruff check`, `mypy`, and BigQuery log querying via `bq`.

---

### Decision 2: Data Ingestion, Extraction, and Normalization Strategy

#### Problem & Drivers
Raw intelligence in `natan_notes.zip` consists of three informal Polish text files (`ogloszenia.txt`, `rozmowy.txt`, `transakcje.txt`). Goods are written with inflected quantities and units (e.g. *"55 workow ryzu"*, *"25 porcji wolowiny"*, *"100 kg ziemniakow"*, *"5 wiertarek"*), and persons are mentioned casually within journal logs (*"Kisiel ma do mnie dzwonic... Rafal oddzwonil wieczorem"*). We must transform this into clean, nominative singular, ASCII-only JSON and Markdown entities.

#### Considered Options

##### Option 2.1: LLM-Assisted Structured Extraction via Gemini 3.8 Flash + Pydantic (ACCEPTED)
* **Description**: The service passes the raw text of notes into Gemini 3.8 Flash using structured output (`response_schema` / `with_structured_output`), requesting an explicit `ExtractionPlan` schema containing normalized cities, goods, quantities (integers only), coordinators, and trade pairs.
* **Data Engineering & Performance**: Single prompt inference (~300–400 ms) processing ~1,200 input tokens; output is deterministically validated against Pydantic models.
* **Cost & FinOps**: Negligible cost (< $0.0002 on Gemini 3.8 Flash).
* **Security & Reliability**: Pydantic validation guarantees type safety and strips unknown fields.
* **Pros & Cons**:
  * Good, because LLMs natively handle Polish grammatical cases, units stripping, and contextual deduplication.
  * Good, because it reflects the core lesson philosophy: human/data provides content, AI organizes and standardizes structure.
  * Bad, because it introduces a network dependency on Vertex AI.

##### Option 2.2: Deterministic Regex & Rule-Based Parser (REJECTED)
* **Description**: Manual regular expressions and hardcoded Polish lemmatization dictionaries.
* **Pros & Cons**:
  * Good, because it runs offline in < 5 ms with zero token usage.
  * Bad, because it is extremely brittle; any phrasing variation or unseen inflection breaks the pipeline.

##### Option 2.3: Autonomous Multi-Step Tool Ingestion (REJECTED)
* **Description**: The agent uses file-reading tools in an open-ended conversation loop, inspecting notes file-by-file.
* **Pros & Cons**:
  * Good, because it showcases conversational autonomy.
  * Bad, because it consumes excessive turns, high token overhead, and introduces stochastic risk of omitting files.

#### Consequences
* **Positive**: High semantic accuracy, clean ASCII transliteration, and robust extraction of complex dialogue links.
* **Confirmation**: Unit tests asserting that extracted dictionaries match known grounding numbers from `ogloszenia.txt` and `rozmowy.txt`.

---

### Decision 3: Virtual Filesystem Staging & Synchronization Strategy

#### Problem & Drivers
Centrala's virtual filesystem API provides granular endpoints (`createFile`, `mkdir`, `deleteFile`, `list`, `reset`, `done`) as well as `batch_mode` (`answer: [...]`). Intercepting every write in real-time breaks on order-of-operations (e.g. referencing a city before that city's file is written). Furthermore, executing 30 discrete HTTP calls introduces network latency and risk of inconsistent state if an intermediate request fails.

#### Considered Options

##### Option 3.1: Workspace Staging Buffer + `TODOs.md` Checklist + Atomic Batch Push (ACCEPTED)
* **Description**: The agent writes files to `cr-mcp-workspace` (or virtual in-memory tree) while maintaining an explicit `TODOs.md` checklist to track completion across all 8 cities, 8 coordinators, and commodities. Once all files are written, the agent executes `validate_workspace`. Upon receiving `status: VALID`, the agent calls `action: "reset"` on Centrala and dispatches the entire tree in a single `answer: [...]` batch payload, immediately followed by `action: "done"`.
* **Data Engineering & Performance**: Eliminates order-of-operations deadlocks during authoring; reduces ~30 HTTP roundtrips down to 3 calls (`help` -> `reset` + batch `createFile` -> `done`). Entire sync completes in under 2 seconds.
* **Cost & FinOps**: Minimal network egress and CPU utilization.
* **Security & Reliability**: Atomicity guarantees no orphaned or half-written files. `TODOs.md` guarantees the agent never loses working memory state.
* **Pros & Cons**:
  * Good, because staging isolates external API mutation until total internal consistency is proven.
  * Good, because it utilizes Centrala's native `batch_mode` designed specifically for full-filesystem synchronization.
  * Bad, because the entire payload must be validated in memory before dispatch.

##### Option 3.2: Real-time Pre-Write Interceptor (REJECTED)
* **Description**: Validating and rejecting each `create_file` call at write time.
* **Pros & Cons**:
  * Bad, because forward-referencing links fail validation before target files exist, confusing the agent and causing catastrophic loops.

##### Option 3.3: Sequential Step-by-Step API Execution (REJECTED)
* **Description**: The agent makes 25–30 sequential HTTP POST calls for each individual file.
* **Pros & Cons**:
  * Bad, because it is slow, vulnerable to network timeouts, and leaves the remote filesystem corrupted if an error occurs midway.

#### Consequences
* **Positive**: Maximum speed, predictable execution, zero partial state corruption, and transparent agent progress tracking via `TODOs.md`.
* **Confirmation**: Test suite mocking `batch_mode` API response and verifying payload structure.

---

### Decision 4: Multi-City Commodity File Formatting

#### Problem & Drivers
In `transakcje.txt`, several commodities (e.g. `ryz`, `chleb`, `kilof`, `lopata`, `maka`, `mlotek`, `wiertarka`, `ziemniak`) are supplied by multiple cities (e.g. rice is sold by Darzlubie, Opalino, and Karlinkowo). We must decide how to represent multiple sellers in `/towary/<commodity>`.

#### Considered Options

##### Option 4.1: Multi-Link Newline List (`\n` separated) (ACCEPTED)
* **Description**: Every city identified as a seller in `transakcje.txt` is included as a standard Markdown link on its own line:
  ```markdown
  [Darzlubie](/miasta/darzlubie)
  [Opalino](/miasta/opalino)
  [Karlinkowo](/miasta/karlinkowo)
  ```
* **Data Engineering & Performance**: Compact text representation; readily parseable by automated validators.
* **Security & Reliability**: 100% complete knowledge representation; no seller city is omitted.
* **Pros & Cons**:
  * Good, because it strictly adheres to the requirement: *"We wnętrzu każdego pliku powinien znajdować się link do miasta, które oferuje ten towar"*.
  * Good, because it avoids extra markdown punctuation that could break strict regex evaluators.
  * Bad, because none.

##### Option 4.2: Markdown Unordered Bullet List (`- [City](/miasta/city)`) (REJECTED)
* **Description**: Formatting links as bullet points.
* **Pros & Cons**:
  * Good, because it looks neat in rich Markdown previews.
  * Bad, because additional bullet tokens (`- `) may conflict with rigid automated grading regexes.

##### Option 4.3: Primary / Single Seller Only (REJECTED)
* **Description**: Storing only the first seller encountered.
* **Pros & Cons**:
  * Bad, because it causes substantive information loss, failing Centrala's knowledge completeness audit.

#### Consequences
* **Positive**: Complete knowledge graph connectivity across trade routes without formatting noise.
* **Confirmation**: Contract tests asserting that each `/towary/*` file contains links to all respective seller cities.

---

### Decision 5: Pre-Flight Integrity Check & Linguistic Subagent Validation Gate

#### Problem & Drivers
Centrala's verification script strictly evaluates ASCII compliance, JSON well-formedness, integer quantity types, nominative singular file naming, and Markdown link validity. Submitting invalid files burns attempts and produces verification errors. Relying solely on LLM self-reflection is a recognized anti-pattern. Furthermore, linguistic validation of Polish singular nominative forms in pure Python code would require massive dictionaries.

#### Considered Options

##### Option 5.1: Deterministic Guardrail (`validate_workspace`) + `gemini-3.8-flash-lite` Subagent with Strict Completeness Validation (ACCEPTED)
* **Description**: Follows Google AIP and Vertex AI Agent design standards by implementing a dual-phase pre-flight validator:
  1. **Phase 1: Deterministic Python Invariants**:
     - **ASCII Invariant**: `re.match(r'^[\x00-\x7F]+$', content)` for all paths and contents.
     - **JSON Contract**: `/miasta/*` content must parse to `dict[str, int]` with positive integer values.
     - **Referential Integrity**: Every `/miasta/<slug>` referenced in `/osoby/*` or `/towary/*` must correspond to an existing file in `/miasta/`.
     - **Completeness**: Exactly 8 cities and 8 trade coordinators must be present.
  2. **Phase 2: Linguistic Subagent Evaluation (`gemini-3.8-flash-lite`)**:
     - Extracts all commodity file names from `/towary/*` and sends them in a single batch prompt to `gemini-3.8-flash-lite` asking whether each word is a Polish noun in singular nominative form (`is_singular_nominative: bool`, `suggested_singular: str | None`).
  3. **Phase 3: Subagent Contract & Completeness Invariant Guard**:
     - The Python wrapper validates the subagent's response against a strict Pydantic model (`CommodityValidationReport`), checking:
       - `set(report.words) == set(requested_commodity_names)`: Asserts that 100% of queried words were evaluated (zero dropped words, zero hallucinated words).
       - For any item where `is_singular_nominative is False`, `suggested_singular` must be non-null and non-empty.
     - If the subagent fails completeness verification, the wrapper flags a validation error or re-executes with deterministic fallbacks.
  4. **Phase 4: Unified Tool Feedback**:
     - If any violation occurs in Phase 1 or 2, `validate_workspace` returns a structured report with explicit diagnostic instructions, enabling the main agent to execute self-correction in the workspace before calling `push_filesystem_batch`.
* **Data Engineering & Performance**: Phase 1 runs in < 1 ms; Phase 2 executes via `gemini-3.8-flash-lite` in ~150 ms with negligible token overhead (~100 tokens).
* **Cost & FinOps**: Ultra-low cost (< $0.00005 per check). Prevents failed external API roundtrips.
* **Security & Reliability**: Zero unverified model assumptions; contract guard ensures 100% determinism across the subagent boundary.
* **Pros & Cons**:
  * Good, because it represents Google's canonical engineering pattern for AI agents interacting with mission-critical systems.
  * Good, because deterministic code handles hard syntax while the lightweight subagent handles Polish linguistic nuances.
  * Good, because completeness validation prevents subagent truncation or partial responses.
  * Bad, because it requires implementing the subagent caller and Pydantic completeness assertions.

##### Option 5.2: Pure Heuristic Suffix Checking in Python (REJECTED)
* **Description**: Trying to detect plurals using naive regex patterns (e.g. checking `-y`, `-i`, `-e`).
* **Pros & Cons**:
  * Bad, because Polish nouns have numerous irregular declensions (e.g. `kilof` vs `kilofy`, `wiertarka` vs `wiertarki`, `marchew` vs `marchewie/marchewki`) where naive rules generate high false positives.

##### Option 5.3: LLM Self-Evaluation / Reflection Prompt on Main Agent (REJECTED)
* **Description**: Asking the main agent in a follow-up prompt: *"Review your generated files and tell me if everything is correct"*.
* **Pros & Cons**:
  * Bad, because it is a known anti-pattern: models suffer from confirmation bias and consistently hallucinate that their own outputs are error-free.

#### Consequences
* **Positive**: 100% first-pass verification success rate, automated error recovery, robust contract hermeticism, and zero ungrounded model assumptions.
* **Confirmation**: Unit test suite testing:
  - Phase 1 deterministic syntax checks.
  - Phase 2 subagent linguistic evaluation on edge cases (`wiertarki` -> error with suggestion `wiertarka`).
  - Phase 3 subagent response completeness validator.

---

### Decision 6: Multilingual Context & Triple-Anchor Polish Linguistic Framing

#### Problem & Drivers
Source intelligence is authored in Polish, requiring lemmatization into singular nominative Polish forms, which are subsequently transliterated to ASCII (stripping diacritics). Without explicit multilingual grounding, English-centric LLMs can misinterpret transliterated Polish strings (e.g. interpreting `lopata` or `maka` as foreign/unknown tokens or applying English morphology).

#### Considered Options

##### Option 6.1: Triple-Anchor Polish Linguistic Framing (ACCEPTED)
* **Description**: Context is explicitly anchored across three distinct layers:
  1. **Global Layer (`system_prompt.md` of Main Agent):**
     - Explains that the domain documents Polish municipal trade notes.
     - States the core linguistic rule: all commodity entities must represent Polish nouns in singular nominative form (`mianownik liczby pojedynczej`) stripped of diacritics into ASCII (`lopata`, `ziemniak`, `wiertarka`).
     - Declares measurement unit omission: integers only, stripping words like `kg`, `butelek`, `porcji`, `workow`.
  2. **Subagent Layer (Prompt of `gemini-3.8-flash-lite`):**
     - Explicitly designates the subagent as an expert in Polish morphology and grammar.
     - Supplies targeted few-shot examples of Polish transliterated words (`wiertarka` -> valid, `wiertarki` -> invalid plural, `ziemniak` -> valid, `ziemniaki` -> invalid plural).
  3. **Tool & Schema Layer (Pydantic `Field(description=..., examples=...)`):**
     - Annotates every tool parameter and output field with explicit descriptions denoting Polish singular nominative ASCII rules and concrete examples.
* **Data Engineering & Performance**: Zero runtime latency penalty; minimal prompt token footprint (< 120 tokens across prompts).
* **Cost & FinOps**: Negligible token cost; drastically reduces retry loops and invalid entity creation.
* **Security & Reliability**: Aligns with Google's Contract-First design (AIP-compliant schema metadata), guaranteeing prompt-schema convergence.
* **Pros & Cons**:
  * Good, because it establishes unequivocal grammatical guidance across all reasoning steps.
  * Good, because both coordination agent, subagent, and tool calling functions share the same invariant assumptions.
  * Bad, because prompts and schemas must be maintained in sync.

##### Option 6.2: Implicit Language Assumptions (REJECTED)
* **Description**: Relying on the model to infer Polish grammatical rules from the raw source text alone.
* **Pros & Cons**:
  * Bad, because transliterated ASCII tokens frequently trigger cross-lingual ambiguity and declension errors in LLMs.

#### Consequences
* **Positive**: Flawless transliteration, accurate singular nominative normalization, zero units leakage into JSON, and unified multi-agent context alignment.
* **Confirmation**: Verified via unit tests asserting correct lemmatization of all 13 trade commodities from `transakcje.txt` and `ogloszenia.txt`.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None. 100% aligned with `GEMINI.md`.

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
  - [Right Model for the Job Guide](../../../RIGHT_MODEL_FOR_THE_JOB.md)
