---
status: "accepted"
date: 2026-09-28
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S05E04 - Autonomous Rocket Navigation & OKO Radar Neutralization (goingthere)

## 1. Context

The resistance must navigate an automated rocket through an active electronic-warfare zone to the stronghold in Grudziądz across a 3x12 discrete grid. Every movement requires forward progression while evading column-specific rock formations, surviving active OKO radar locks via cryptographic SHA-1 disarming, and interpreting ambiguous nautical radio transmissions. The flight controller operates under strict closed-loop constraints: any single un-neutralized radar trap or obstacle collision causes an immediate catastrophic crash, while upstream APIs intermittently inject synthetic packet corruption and transient HTTP errors. The system verification goal is to guide the rocket safely from `(col=1, row=2)` to `(col=12, row=target)` and extract the mission completion flag (`{FLG:...}`).

---

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Architectural Baseline Alignment | Adhere 100% to GEMINI.md Baseline | Full alignment with Cloud Run (`cr-s05e04-goingthere`), BigQuery audit (`s05e04.audit`), Model Armor, and `uv` standards. |
| 2 | Model Tier & Distorted Payload Processing | Gemini 3.8 Flash (High Thinking) via Model Armor | Primary workhorse model on Vertex AI; Model Armor neutralizes prompt injection before structured Pydantic extraction. |
| 3 | Radio Telemetry & Nautical Hint Interpretation | Semantic Nautical Prompt with Structured Pydantic Output | Eliminates fragile hardcoded dictionaries; leverages LLM as an expert navigator to resolve maritime jargon directly into grid coordinates. |
| 4 | Trajectory Planning & Execution Architecture | Deterministic FSM with Pydantic `FlightState` Tracker | Guarantees strict phase sequencing (Radar Check -> Disarm -> Radio Hint -> Vector Thrust) with zero forgotten safety steps; single default CLI entrypoint. |
| 5 | Egress Gateway & Session Workspace Persistence | Outbound Egress via `cr-mcp-web-gateway` & Mandatory `run_notes.txt` in `cr-mcp-workspace` | Strictly complies with GEMINI.md anti-patterns: 100% authenticated egress through gateway microservice and mandatory GCS workspace audit persistence with fail-fast validation. |
| 6 | Grid State Modeling & Historical Context Awareness | Native `GameColumn` Sector Map & Python Kinematics Guardrails | FSM stores exact `GameColumn` history (player, stone, free rows) from start and every turn; full map is provided to Gemini 3.8 Flash (High Thinking) to resolve temporal hints ("same as start", "two steps back"), while Python enforces strict no-corner-cutting kinematics. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Architectural Baseline Alignment (GEMINI.md)

#### Problem & Drivers
The playground defines strict cloud-native standards for containerized microservices, infrastructure as code, structured logging, and observability. We must verify whether this mission requires deviations.

#### Considered Options

##### Option 1.1: Adhere 100% to GEMINI.md Baseline (ACCEPTED)
* **Description**: Implement a containerized FastAPI microservice `cr-s05e04-goingthere` deployed to Cloud Run, logging to BigQuery dataset `s05e04`, using `uv` with pinned dependencies (`requires-python = "==3.13.5"`), and exposing `/health`, `/`, and `POST /run`.
* **Data Engineering & Performance**: Native integration with BigQuery audit streaming and LangSmith tracing.
* **Cost & FinOps**: Cloud Run scale-to-zero keeps idle costs at \$0.00.
* **Security & Reliability**: Centralized secret resolution from GCP Secret Manager and local `.env`.
* **Pros & Cons**:
  * Good, because it ensures consistency across the repository and zero deployment surprises.
  * Good, because it enables automated quality gates (`ruff`, `mypy`, `pytest`).

##### Option 1.2: Ad-Hoc Standalone Script (REJECTED)
* **Description**: Run a one-off local Python script without Cloud Run containerization or BigQuery telemetry.
* **Pros & Cons**:
  * Good, because it requires fewer scaffolding files.
  * Bad, because it violates repository standards, lacks telemetry persistence, and prevents serverless verification.

#### Consequences
* **Positive**: 100% compliance with repository standards and automated deployment pipelines.
* **Confirmation**: Verified via quality gate scripts and Terraform variable registration.

---

### Decision 2: Model Tier & Distorted Radar Telemetry Parsing

#### Problem & Drivers
Under electronic jamming, the OKO frequency scanner returns distorted payloads containing `frequency` and `detectionCode`. The payload must be sanitized and parsed to compute the SHA-1 disarm hash (`sha1(f"{detectionCode}disarm")`). Furthermore, all external raw inputs must pass through safety filtering.

#### Considered Options

##### Option 2.1: Gemini 3.5 Flash-Lite with Model Armor & Structured Schema (ACCEPTED)
* **Description**: Raw scanner responses are first sanitized via `cr-model-armor` (`$MODEL_ARMOR_URL`). The cleaned string is passed to Vertex AI `gemini-3.5-flash-lite` configured with `thinking_level="medium"` and Pydantic structured output (`RadarTelemetryExtraction`).
* **Data Engineering & Performance**: Sub-second execution (< 500ms) with lightweight token footprint (~100 tokens per invocation).
* **Cost & FinOps**: Flash-Lite operates within the lowest pricing tier, consuming minimal budget across the 11 columns.
* **Security & Reliability**: Model Armor shields against malicious injection embedded in scanner payloads; Pydantic guarantees type-safe numeric frequencies and string detection codes.
* **Pros & Cons**:
  * Good, because it handles arbitrarily distorted JSON, missing braces, or obfuscated keys effortlessly.
  * Good, because Model Armor ensures defensive compliance.
  * Bad / Trade-off, because it introduces an external LLM call over a pure regex extractor (mitigated by Flash-Lite's negligible latency and cost).

##### Option 2.2: Pure Deterministic Regex Parser (REJECTED)
* **Description**: Parse payloads exclusively using regular expressions matching digits and hex tokens.
* **Pros & Cons**:
  * Good, because it requires 0 API calls.
  * Bad, because synthetic jamming with perturbed keys or nested structures breaks regex rules unpredictably.

##### Option 2.3: Gemini 3.8 Flash (Full Model) (REJECTED)
* **Description**: Use standard Gemini 3.8 Flash for scanner telemetry extraction.
* **Pros & Cons**:
  * Good, because of high reasoning capacity.
  * Bad, because it is over-engineered for a simple 2-field extraction task and increases token cost needlessly.

#### Consequences
* **Positive**: High resilience to noisy jamming payloads with guaranteed schema conformance.
* **Confirmation**: Unit tests with synthetic malformed JSON inputs validating `RadarTelemetryExtraction`.

---

### Decision 3: Radio Telemetry & Nautical Hint Interpretation Strategy

#### Problem & Drivers
Radio broadcasts from `$AIDEVS_API_GETMESSAGE` describe the rock position in column $X+1$ using colloquial and nautical terminology ("port side", "starboard", "dead ahead", "shoals on the left", etc.). The system must translate this relative direction into an absolute grid row $Y_{\text{rock}} \in \{1, 2, 3\}$.

#### Considered Options

##### Option 3.1: Expert Maritime Navigator System Prompt with Structured Schema (ACCEPTED)
* **Description**: Prompt `gemini-3.5-flash-lite` (filtered through Model Armor) with a dedicated persona as an expert naval navigator. Provide current rocket position $(X, Y)$ and the raw radio hint, requesting structured output `RadioNavigationExtraction(rock_relative_direction, rock_absolute_row, reasoning)`.
* **Data Engineering & Performance**: Minimal prompt (~150 tokens), structured JSON generation without Markdown backticks.
* **Cost & FinOps**: Flash-Lite handles all 11 transitions for less than \$0.001 total.
* **Security & Reliability**: No brittle keyword matching; easily interprets diverse idioms, sailing terms, and colloquial phrasing.
* **Pros & Cons**:
  * Good, because it naturally resolves nautical nuances ("port" = left/higher row, "starboard" = right/lower row, "dead ahead" = current row).
  * Good, because it eliminates the maintenance burden of an incomplete static lexicon.
  * Bad / Trade-off, because it requires an LLM call per column (acceptable given the 600s task budget).

##### Option 3.2: Hybrid Static Lexicon + LLM Fallback (REJECTED)
* **Description**: Maintain an in-memory dictionary of nautical terms and call LLM only on miss.
* **Pros & Cons**:
  * Good, because it saves ~10 LLM calls if keywords match.
  * Bad, because nautical directions are contextual (e.g. "steer clear of the port bow" vs "port is safe") and keyword mapping easily causes false positives leading to crashes.

#### Consequences
* **Positive**: Context-aware, fault-tolerant interpretation of complex nautical hints.
* **Confirmation**: Unit test suite covering a broad spectrum of maritime test phrases.

---

### Decision 4: Trajectory Planning & Execution Architecture (FSM with FlightState Tracker)

#### Problem & Drivers
The flight controller must execute a strict 4-phase loop across 11 column transitions. We need to decide between a deterministic Finite State Machine (FSM) with explicit state tracking versus an autonomous ReAct tool-calling agent loop.

#### Considered Options

##### Option 4.1: Deterministic FSM with Pydantic `FlightState` Accumulator (ACCEPTED)
* **Description**: Implement a deterministic state machine managed by `FlightController`. A Pydantic model `FlightState` maintains the telemetry snapshot: current column, current row, target base row, radar status, obstacle predictions, and action history. In each iteration, the FSM deterministically enforces:
  1. Poll scanner -> if targeted, parse & disarm.
  2. Poll radio message -> extract rock row for column $X+1$.
  3. Path Planning: Choose safe command (`go`, `left`, `right`) minimizing $|Y_{\text{target}} - Y_{\text{candidate}}|$ and avoiding boundary out-of-bounds ($Y \notin [1, 3]$).
  4. Dispatch vector thrust via `$AIDEVS_API_VERIFY`.
* **Data Engineering & Performance**: Zero redundant iterations, linear $O(N)$ execution time, deterministic telemetry streaming to BigQuery.
* **Cost & FinOps**: Only 2 LLM calls per column (scanner + radio), total runtime ~15-20 seconds.
* **Security & Reliability**: 100% guarantee that the radar is disarmed before movement. Zero risk of an autonomous agent "forgetting" to disarm or issuing hallucinated commands.
* **Pros & Cons**:
  * Good, because rocket navigation in a discrete grid is a safety-critical deterministic process where sequence violations mean instant death.
  * Good, because `FlightState` provides complete auditability and state replay for debugging.
  * Good, because eliminating redundant CLI flags (`--mode`) simplifies execution (`uv run python main.py` directly executes the mission).
  * Bad / Trade-off, because it lacks the emergent adaptability of a free-form ReAct loop (not needed for this deterministic game).

##### CLI Interface & Developer Evaluation Flags
The command-line interface provides high-velocity debugging without server overhead:
* **Evaluation Flags (Dual CLI & `POST /run` API):**
  * `--model <name>`: Dynamic LLM override (default `gemini-3.5-flash-lite`).
  * `--thinking-level <low|medium|high>`: Reasoning effort override (default `medium`).
  * `--session-id <id>`: Session identifier for BigQuery audit and `cr-mcp-workspace`.
* **CLI-Only Rapid Debugging Flags:**
  * `--step-by-step` (or `-i`): Interactive column-by-column stepping pausing before each thrust to inspect scanner status, disarm confirmation, radio hint, and vector selection.
  * `--probe`: Fast 1-second pre-flight check sending `start`, printing starting coordinates and Grudziądz target row, and exiting immediately.
  * `--direct-egress`: Direct HTTP calls via `httpx` with tenacity retry, bypassing `cr-mcp-web-gateway` (indispensable for local development where user IAM tokens cannot impersonate gateway service accounts).
  * `--verbose` (or `-v`): Detailed debug output exposing raw distorted scanner payloads, Model Armor sanitized strings, and SHA-1 disarm hashes.
* *Note on Server Mode:* Server execution is decoupled from CLI parsing; uvicorn runs directly (`uv run uvicorn main:app --host 0.0.0.0 --port 8080`) per standard container patterns.

##### Option 4.2: Autonomous ReAct Tool-Calling Agent Loop (REJECTED AS PRIMARY, AVAILABLE AS OPTIONAL BACKEND)
* **Description**: Bind tools (`scan_radar`, `disarm_radar`, `get_hint`, `steer_rocket`) to an LLM and let the model decide every step in a ReAct loop.
* **Pros & Cons**:
  * Good, because it showcases autonomous agent tool use.
  * Bad, because across 11 columns it takes 30-45 LLM turns, risking turn limit exhaustion, context window bloat, and accidental movement without disarming.

#### Consequences
* **Positive**: Mission success rate approaches 100% due to deterministic safety enforcement and mathematical path planning.
* **Negative / Trade-offs**: Fixed workflow architecture tailored specifically to the `goingthere` mission protocol.
* **Confirmation**: Integration tests verifying end-to-end grid traversal from `(1, 2)` to `(12, Y_target)`.

---

### Decision 5: Outbound Egress Routing via `cr-mcp-web-gateway` & Mandatory `run_notes.txt` in `cr-mcp-workspace`

#### Problem & Drivers
GEMINI.md strictly prohibits two core architectural anti-patterns:
1. **Direct External Egress from Agent Containers**: External API calls must not bypass security infrastructure; egress must route through dedicated gateway microservices (`cr-mcp-web-gateway`) using authenticated Google Cloud OIDC tokens.
2. **Local Disk Poisoning & Silent Local Storage Fallback**: Cloud Run containers must remain 100% stateless. Intermediate artifacts and execution traces (`run_notes.txt`) must never be written to local container disk (`workspace/` or repository roots) as they get baked into Docker images. Persistence operations must strictly target session-isolated GCS workspaces (`cr-mcp-workspace`), failing fast with an explicit exception if the service is unreachable.

#### Considered Options

##### Option 5.1: Centralized MCP Integration via `af_aidevs.clients.mcp` (ACCEPTED)
* **Description**: 
  1. **Egress Gateway (`cr-mcp-web-gateway`):** Route external HTTP calls (`$AIDEVS_API_VERIFY`, `$AIDEVS_API_GETMESSAGE`, `$AIDEVS_API_FREQUENCY_SCANNER`) through `cr-mcp-web-gateway` using authenticated Google Cloud OIDC tokens and `af_aidevs.clients.mcp` (with fallback to direct resilient `httpx` with tenacity backoff strictly during isolated local offline unit testing if gateway URL is empty).
  2. **Mandatory Workspace Persistence (`cr-mcp-workspace`):** Upon flight completion or failure, the flight controller invokes `mcp_service.write_file(session_id=..., file_path="run_notes.txt", content=...)` to persist unanonymized course flags (`{FLG:...}`), complete flight path coordinates, radar neutralization counts, and execution metrics to `gs://af-aidevs-workspaces/sa-cr-s05e04-goingthere/<session_id>/run_notes.txt`.
  3. **Strict Zero Disk Poisoning & Fail-Fast:** No fallback to local Python `open("run_notes.txt", "w")`. If `cr-mcp-workspace` fails, raise an explicit `RuntimeError` to ensure immediate developer visibility.
* **Data Engineering & Performance**: Centralized egress visibility in Google Cloud Logging; zero container disk bloating; complete persistent execution traces.
* **Cost & FinOps**: Minimal MCP call overhead; GCS workspace storage conforms to micro-cent pricing.
* **Security & Reliability**: 100% compliance with GEMINI.md security guardrails and container statelessness standards. Unredacted course flags remain isolated in private GCS buckets and never leak to Git.
* **Pros & Cons**:
  * Good, because it adheres strictly to repository architectural policies.
  * Good, because it prevents local `.venv`/workspace contamination in Docker images.
  * Good, because unredacted flags are safely audited without git leakage risks.
  * Bad / Trade-off, because it requires OIDC token acquisition and MCP client connection setup.

##### Option 5.2: Direct Container Egress and Ephemeral Local Disk Writes (REJECTED)
* **Description**: Call external APIs directly via unproxied `httpx` and write `run_notes.txt` to local container disk.
* **Pros & Cons**:
  * Bad, because it violates GEMINI.md rules against direct external egress and local disk poisoning.
  * Bad, because local files can get accidentally committed or baked into images.

#### Consequences
* **Positive**: Complete compliance with GEMINI.md egress and workspace rules; clean container hygiene; reliable remote audit trail.
* **Confirmation**: Verified by inspecting Cloud Logging for OIDC gateway calls and verifying `run_notes.txt` presence in GCS via `cr-mcp-workspace`.

---

### Decision 6: Grid State Modeling (`GameColumn`) & Historical Context Awareness

#### Problem & Drivers
1. **Temporal & Relative Radio Clues**: In columns 6 through 11, the resistance tactical radio employs advanced relative spatial and historical references (e.g. *"the stone is in the same channel as at launch"*, *"hazard returned to the row from two sectors ago"*). Without an immutable, structured history of previous columns, the LLM hallucinates obstacle positions.
2. **Corner-Cutting Collision Hazard**: In discrete grid kinematics, moving diagonally past a rock located in the current column (e.g. from `(6, 2)` to `(7, 1)` when a rock is at `(6, 1)`) collides with the solid obstacle corner. Python trajectory planning must strictly penalize or prevent corner-cutting past known current obstacles.

#### Considered Options

##### Option 6.1: Native `GameColumn` State History & Deep Cognitive Thinking (ACCEPTED)
* **Description**:
  1. Define a Pydantic schema `GameColumn(column, your_row, stone_row, free_rows)` exactly mirroring Centrala's start and trajectory contracts.
  2. Maintain `columns_history: dict[int, GameColumn]` in `FlightState`, populated on start (`column 1`) and updated sequentially across all columns.
  3. Format and inject the complete cumulative flight sector map (`=== KNOWN FLIGHT SECTOR MAP ===`) into `NavigatorService` prompt on every turn.
  4. Use **Gemini 3.8 Flash** with `thinking_level="high"` to provide ample reasoning capacity for complex maritime metaphors and historical comparisons.
  5. Enforce separation of concerns: LLM specializes strictly in semantic perception (`rock_absolute_row: 1 | 2 | 3`), while deterministic Python logic evaluates valid moves, boundary checks ($1 \le Y \le 3$), and strictly prevents corner-cutting past rocks in the current column.
* **Data Engineering & Performance**: Total token footprint per column remains modest (~300 tokens prompt history). Latency increases by ~1-2 seconds per step, completing all 11 transitions in ~25-35 seconds (well within the 600s Cloud Run budget).
* **Cost & FinOps**: Vertex AI Gemini 3.8 Flash costs remain negligible (< $0.01 per full flight).
* **Security & Reliability**: 100% immune to historical hallucination; zero corner-cutting collisions; rock solid algebraic boundary verification.
* **Pros & Cons**:
  * Good, because it directly resolves temporal hints like "same as start" without guesswork.
  * Good, because it prevents corner-cutting crashes on middle lane splits.
  * Good, because Python handles kinematics while LLM handles linguistics.

##### Option 6.2: Stateless Per-Turn Extraction (REJECTED)
* **Description**: Pass only the current row/column to the LLM without past column history.
* **Pros & Cons**:
  * Bad, because relative hints referencing past columns fail immediately.
  * Bad, because without current rock memory, corner-cutting cannot be evaluated.

#### Consequences
* **Positive**: Absolute context fidelity for LLM navigation; zero historical hallucinations; zero corner-cutting crashes.
* **Confirmation**: Integration tests verifying resolution of temporal hints ("same as start") and trajectory selection avoiding corner rocks.

---

## 4. Technical Baseline Alignment (GEMINI.md)

100% Alignment. No deviations from the architectural baseline.

* **Frameworks**: FastAPI, Pydantic v2, LangChain Google GenAI (`ChatGoogleGenerativeAI`).
* **Models**: `gemini-3.8-flash` on Vertex AI (`location="global"`, `thinking_level="high"`).
* **Security**: `cr-model-armor` proxying for all external scanner/radio inputs, GCP Secret Manager.
* **Storage & Telemetry**: BigQuery dataset `s05e04`, table `audit`.
* **Runtime**: Cloud Run (`cr-s05e04-goingthere`, `concurrency=80`, `memory=1Gi`, `timeout=600s`).

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
  - [GEMINI.md](../../../GEMINI.md)
