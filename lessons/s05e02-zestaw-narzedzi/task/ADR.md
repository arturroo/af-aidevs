<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-27
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S05E02 — Conversational Voice Agent (Phonecall)

## 1. Context

During the evacuation operation to Syjon, the resistance must establish a direct telephone connection to an OKO system operator to identify an uncontaminated evacuation route (among RD224, RD472, and RD820) and persuade the operator to deactivate surveillance monitoring on that route. Centrala exposes an audio-mediated HTTP verification endpoint (`$AIDEVS_API_VERIFY`) requiring session initialization followed by multi-turn Base64-encoded audio exchanges in Polish (`pl-PL`). The conversational protocol enforces strict turn sequencing, conversational brevity, and active session timeout limits, burning the call upon premature disclosure of secrets or conversational anomalies. The architecture must achieve 100% deterministic mission goal attainment, low turn latency ($\le 5{-}7$s), and zero token/byte pollution under Google Cloud Run and Vertex AI constraints.

---

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Outbound Speech Synthesis (TTS) | Google Cloud Text-to-Speech API (`pl-PL-Neural2-B`) | Deterministic MP3 synthesis, pristine native Polish pronunciation, zero external API keys, and \$0.00 cost under GCP Free Tier (1M chars/mo). |
| 2 | Inbound Audio Comprehension & Transcription (STT) | Gemini 3.8 Flash Direct Multimodal Extraction with Pydantic Schema | Single-roundtrip low latency, rich acoustic comprehension (irony, sentiment, suspicion level), and zero transcription drift on road alphanumeric codes. |
| 3 | Conversational State & Dialogue Governance | Declarative `DialogueState` (Slot-Filling / Blackboard) + Deterministic Policy Engine | Eliminates LLM turn order hallucinations while gracefully handling multi-intent operator replies, ensuring 100% protocol adherence without FSM rigidity. |
| 4 | Prompt Engineering & Cache Optimization | Static Persona Rules Top / Recency Objective Bottom | Maximizes KV-cache prefix matching across turns while leveraging Transformer recency bias to condition immediate token generation on turn objectives. |
| 5 | Premature Call Termination Detection (`call_burned`) | Dual-Source Defense-in-Depth (HTTP Code Check + Single Pydantic Call) | Zero latency penalty, 100% deterministic transport safety, and immune to premature restarts on normal conversational hesitation. |
| 6 | Operational Agility & Telephony Runtime Overrides | Comprehensive Dynamic Overrides (`max_iterations`, `voice_name`, `speaking_rate`, `max_restarts`) | Eliminates container rebuild cycles during debugging, allows tuning speech cadence to beat session timeouts, and caps restart budgets. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Outbound Speech Synthesis Engine (TTS)

#### Problem & Drivers
The agent must generate outbound voice messages as Base64-encoded MP3 audio representing operative Tymon Gajewski. Drivers include pronunciation fidelity for Polish military road codes (e.g. `RD472`), turn latency, container complexity, and inference cost.

#### Considered Options

##### Option 1.1: Google Cloud Text-to-Speech API (`pl-PL-Neural2-B`) (ACCEPTED)
* **Description**: Synthesizes speech using Google Cloud Text-to-Speech API configured with the high-fidelity neural voice `pl-PL-Neural2-B`. Uses SSML (`<speak>`, `<say-as interpret-as="characters">RD</say-as> 224`) to enforce flawless phonemic pronunciation.
* **Data Engineering & Performance**: Generates native MP3 byte streams synchronously in $\sim 300{-}600$ ms. Requires zero container audio-transcoding dependencies (`ffmpeg`/`lame`).
* **Cost & FinOps**: 100% free tier compliant (first 1,000,000 characters free monthly; the entire multi-turn call consumes $< 1,000$ characters total).
* **Security & Reliability**: Native GCP IAM authentication using Cloud Run service account credentials (`roles/aiplatform.user` / default compute identity), eliminating external API key leakage.
* **Pros & Cons**:
  * Good, because delivers studio-quality Polish male voice without foreign accent or prosody drift.
  * Good, because enables precise SSML control over pauses, cadence, and acronyms.
  * Bad / Trade-off, because requires network egress to the Cloud TTS regional endpoint.

##### Option 1.2: Gemini Native Multimodal Audio Output via Generative Audio / Live API (REJECTED)
* **Description**: Generating audio waveforms directly from Gemini's audio output modalities.
* **Data Engineering & Performance**: Emits raw PCM audio (24kHz mono) requiring container-level audio transcoders (`ffmpeg`/`pydub`) to encode into MP3.
* **Cost & FinOps**: Costly audio output token pricing ($\sim \$10.00 - \$20.00$ per 1M audio tokens), incurring financial overhead for simple dialogue.
* **Security & Reliability**: Prone to generative audio non-determinism, background audio artifacts, and occasional English accent drift in Polish pronunciation.
* **Pros & Cons**:
  * Good, because expressive conversational nuances (breaths, laughs).
  * Bad / Trade-off, because non-deterministic and requires extra container transcoding libraries.

##### Option 1.3: ElevenLabs API (REJECTED)
* **Description**: Third-party neural speech synthesis platform.
* **Data Engineering & Performance**: High quality, but requires third-party network egress and additional external API latency.
* **Cost & FinOps**: Requires separate commercial subscription outside GCP billing.
* **Security & Reliability**: Requires managing an external secret (`ELEVENLABS_API_KEY`) in Secret Manager.
* **Pros & Cons**:
  * Good, because hyper-realistic voice cloning.
  * Bad / Trade-off, because unnecessary complexity and credential overhead when GCP Neural2 is already provisioned.

#### Consequences
* **Positive**: Reliable, deterministic, zero-cost Polish MP3 audio generation fully governed by GCP IAM.
* **Negative / Trade-offs**: None; perfectly tailored to Cloud Run architecture.
* **Confirmation**: Verified by synthesizing sample SSML phrases in unit tests and validating MP3 magic bytes (`ID3` / `0xFF 0xFB`).

---

### Decision 2: Inbound Operator Audio Transcription & Comprehension (STT)

#### Problem & Drivers
Operator responses arrive as Base64-encoded audio payloads containing crucial route statuses, challenges for secret passwords (`BARBAKAN`), or suspicion inquiries. The system must extract verbatim transcripts while capturing emotional cues (irony, humor, skepticism) and road entity statuses within a strict session timeout.

#### Considered Options

##### Option 2.1: Gemini 3.8 Flash Direct Multimodal Extraction with Pydantic Schema (ACCEPTED)
* **Description**: Ingest inbound audio bytes directly into Gemini 3.8 Flash via `types.Part.from_bytes(data=raw_audio_bytes, mime_type="audio/mp3")` using a structured Pydantic response schema (`OperatorTurnAnalysis`).
* **Data Engineering & Performance**: Executes in a single network roundtrip ($\sim 1.5{-}2.5$s), drastically reducing turn latency compared to two-stage pipelines. Extracts:
  - `operator_transcript`: Verbatim Polish transcript.
  - `sentence_analyses`: List of sentence-level classifications (sentiment, irony, humor, topic).
  - `overall_sentiment`: Aggregate emotional tone.
  - `suspicion_level`: `Literal["low", "medium", "high", "critical"]`.
  - `auth_requested`: Boolean flag detecting password challenges.
  - `road_statuses`: Explicit dictionary mapping `RD224`, `RD472`, `RD820` to `Literal["passable", "blocked", "contaminated", "unknown"]`.
  - `call_burned`: Boolean flag indicating operator termination or alarm.
* **Cost & FinOps**: Audio input tokens in Gemini 3.8 Flash are exceptionally cost-efficient ($\sim 25{-}32$ tokens per audio second; a 5s audio clip costs $< 200$ tokens $\approx \$0.00003$).
* **Security & Reliability**: Directly evaluates acoustic prosody and tone, preventing phonetic transcription misinterpretations of military alphanumeric codes.
* **Pros & Cons**:
  * Good, because single roundtrip ensures conversation finishes well before session timeout.
  * Good, because simultaneously delivers verbatim text and high-level behavioral telemetry.
  * Bad / Trade-off, because requires strict JSON schema enforcement to avoid parsing failures.

##### Option 2.2: Decoupled Google Cloud Speech-to-Text v2 (Chirp 2) + Gemini Text Prompt (REJECTED)
* **Description**: Inbound audio is transcribed to text via GCP STT v2, then passed as a text prompt to Gemini.
* **Data Engineering & Performance**: Adds a second sequential HTTP/gRPC roundtrip ($\sim 2.0$s STT + $\sim 1.8$s LLM = $\sim 3.8{-}4.5$s latency per turn), increasing session timeout risk.
* **Cost & FinOps**: Incurs additional STT processing billing on top of Vertex AI inference.
* **Security & Reliability**: STT strips acoustic prosody and frequently misspells alphanumeric codes (e.g. transcribing "RD472" as "er de czterysta siedemdziesiąt dwa"), necessitating brittle regex heuristics.
* **Pros & Cons**:
  * Good, because raw text transcript is isolated upfront.
  * Bad / Trade-off, because higher latency, phonetic data loss, and double API billing.

#### Consequences
* **Positive**: Minimal latency, rich affective observability (irony, humor, suspicion), and robust alphanumeric road entity extraction.
* **Negative / Trade-offs**: Structured schema must feature safe fallbacks for malformed JSON.
* **Confirmation**: Verified with unit test mocks of `OperatorTurnAnalysis` and synthetic audio evaluation.

---

### Decision 3: Conversational Orchestration & State Governance

#### Problem & Drivers
Centrala requires specific sequencing: Turn 1 must bundle Tymon Gajewski's identity, inquiry on all 3 roads, and the Zygfryd base transport context into a single message. Premature password disclosure burns the call; wrong road selection fails the mission.

#### Considered Options

##### Option 3.1: Declarative `DialogueState` (Slot-Filling / Blackboard) + Deterministic Policy Engine (ACCEPTED)
* **Description**: Centralized Pydantic state model (`DialogueState`) tracking mission milestones:
  - `opening_message_sent: bool` (atomic bundle: identity + 3 roads + Zygfryd base).
  - `roads: dict[RoadCode, RoadAssessment]` (per-road passability, monitoring state, and operator justification).
  - `selected_evacuation_road: RoadCode | None` (the safe road to Syjon).
  - `auth_requested: bool` & `auth_code_provided: bool`.
  - `monitoring_deactivation_requested: bool` & `monitoring_deactivation_confirmed: bool`.
  - `operator_suspicious: bool` & `food_legend_used: bool`.
  - `call_burned: bool` & `turn_count: int`.
  A deterministic Python function (`determine_next_objective(state) -> TurnObjective`) governs the conversation sequence, while Gemini 3.8 Flash handles natural voice generation conditioned on that exact objective.
* **Data Engineering & Performance**: Zero state mutation leaks across Cloud Run concurrent requests by enforcing `Field(default_factory=...)` for mutable collections.
* **Cost & FinOps**: Minimal token usage; eliminates agent loop retries and self-correction loops.
* **Security & Reliability**: 100% deterministic guardrails. Eliminates premature disclosure of secret password `BARBAKAN`. Handles multi-intent operator replies (e.g. operator supplying road status AND demanding password in the same turn) seamlessly.
* **Pros & Cons**:
  * Good, because guarantees strict protocol compliance without rigid FSM lockouts.
  * Good, because enables de-escalation loops (dispelling operator suspicion using the food transport legend).
  * Bad / Trade-off, because requires maintaining explicit state update logic in Python.

##### Option 3.2: Rigid Sequential Finite State Machine (FSM) (REJECTED)
* **Description**: Discrete state transitions (`START` $\to$ `QUERY_ROADS` $\to$ `WAIT_STATUS` $\to$ `AUTH` $\to$ `DISABLE`).
* **Data Engineering & Performance**: Fast and simple.
* **Cost & FinOps**: Identical compute cost.
* **Security & Reliability**: Brittle against real-world human conversation. If an operator provides road status and simultaneously demands authorization, a single-state FSM gets confused or drops the road facts.
* **Pros & Cons**:
  * Good, because simple to conceptualize for linear workflows.
  * Bad / Trade-off, because fragile when handling compound conversational utterances.

##### Option 3.3: Pure Autonomous ReAct Agent Loop (REJECTED)
* **Description**: Gemini operates autonomously with tools (`start_session`, `send_audio`, `submit_password`).
* **Data Engineering & Performance**: Highly dynamic.
* **Cost & FinOps**: High token consumption due to intermediate reasoning steps and tool-call schema overhead.
* **Security & Reliability**: High risk of hallucinated turn order, accidental premature password leakage, or verbose messages that burn the call.
* **Pros & Cons**:
  * Good, because minimal Python orchestration code.
  * Bad / Trade-off, because non-deterministic and prone to burning the call.

#### Consequences
* **Positive**: Absolute mathematical certainty of protocol compliance, robust handling of compound operator statements, and clean testability.
* **Negative / Trade-offs**: None.
* **Confirmation**: Verified through pytest unit tests covering all dialogue state transitions and policy decisions.

---

### Decision 4: Prompt Architecture & KV-Cache / Attention Optimization

#### Problem & Drivers
To ensure fast turn processing and adherence to mission constraints, prompts sent to Gemini 3.8 Flash must maximize Context Caching (KV-cache reuse) while ensuring the model prioritizes the current turn's objective over conversational drift.

#### Considered Options

##### Option 4.1: Static Rules Top / Recency Objective Bottom (Prefix Caching & Recency Bias Alignment) (ACCEPTED)
* **Description**: Structure the voice generation prompt into three distinct contiguous segments:
  1. **Static System Persona & Rules (Top)**: Static string defining Tymon Gajewski's role, conciseness limits, and SSML instructions. Remains 100% identical across all turns, maximizing left-to-right KV-cache prefix hits.
  2. **Conversation History (Middle)**: Sequentially appended dialogue turns. Each turn appends to the already cached KV prefix.
  3. **Immediate Operator Utterance & Turn Objective (Bottom)**: Placed at the very end of the prompt:
     ```text
     OSTATNIA WYPOWIEDŹ OPERATORA: "{operator_transcript}"
     CEL TEJ TURY: {current_objective.instruction}
     ```
* **Data Engineering & Performance**: Exploits the Transformer attention mechanism's **Recency Effect** (attention sink at the sequence boundary) to strongly condition generation on the immediate goal while achieving maximum KV-cache hit rates.
* **Cost & FinOps**: Substantially reduces time-to-first-token (TTFT) and input token inference costs via cached tokens.
* **Security & Reliability**: Prevents the model from getting distracted by earlier conversation banter.
* **Pros & Cons**:
  * Good, because aligns prompt layout with physical hardware caching and Transformer attention dynamics.
  * Bad / Trade-off, because requires strict templating discipline in the prompt builder.

##### Option 4.2: Free-form Dynamic Context with Objectives at the Top (REJECTED)
* **Description**: Placing dynamic instructions at the beginning of the prompt and conversation history at the end.
* **Data Engineering & Performance**: Destroys the KV-cache prefix on every single turn, forcing full recomputation of attention matrices.
* **Cost & FinOps**: Higher latency and zero cache savings.
* **Pros & Cons**:
  * Bad / Trade-off, because causes cache thrashing and dilutes attention on the immediate objective.

#### Consequences
* **Positive**: Ultra-fast token generation, lower cost, and laser-focused adherence to the turn objective.
* **Negative / Trade-offs**: None.
* **Confirmation**: Validated through LangSmith trace latency benchmarks and prompt inspection.

---

### Decision 5: Premature Call Termination Detection (`call_burned`) via Dual-Source Defense-in-Depth

#### Problem & Drivers
If an operative mishandles the protocol or triggers suspicion, the operator may hang up or sound an alarm. Centrala specifies: *"Jeśli rozmowa pójdzie źle, musisz ponownie wywołać start i przejść całość scenariusza od początku"*. However, normal human conversational friction (operator hesitation, gruff tone, asking for authorization code, or asking why monitoring must be disabled) must NOT be misconstrued as call termination, otherwise the system will trigger infinite premature restart loops.

#### Considered Options

##### Option 5.1: Dual-Source Defense-in-Depth in a Single Roundtrip (ACCEPTED)
* **Description**:
  1. **Transport Layer Check (Deterministic Python)**: If Centrala HTTP status $\neq 200$, JSON response has `code != 0`, or audio payload is missing/empty, Python immediately flags `call_burned = True` without invoking LLM evaluation.
  2. **Semantic Affect Check (Pydantic Field in Primary Gemini Extraction)**: Within the single multimodal extraction call (`OperatorTurnAnalysis`), Gemini extracts `call_burned: bool` backed by explicit negative constraint prompt instructions:
     ```python
     call_burned: bool = Field(
         default=False,
         description=(
             "Set to True ONLY if the operator EXPLICITLY terminates the conversation "
             "(hangs up, triggers an alarm, screams spy/imposter, or definitively refuses to talk). "
             "Normal hesitation, skepticism, requesting the secret password BARBAKAN, or asking why "
             "monitoring should be disabled are strictly False and must be handled via dialogue!"
         )
     )
     call_burned_reason: str | None = None
     ```
  3. **Auto-Recovery**: If `call_burned == True`, the orchestrator resets state, invokes `action: "start"`, and restarts up to `max_restarts` times.
* **Data Engineering & Performance**: Zero additional network latency! Evaluation occurs within the same single Gemini 3.8 Flash turn extraction call.
* **Cost & FinOps**: Zero additional token overhead.
* **Security & Reliability**: Dual-layer verification eliminates false positives from benign conversational friction while instantly catching real disconnections or API rejections.
* **Pros & Cons**:
  * Good, because adds zero latency penalty to the time-sensitive audio session.
  * Good, because deterministic transport checks catch infrastructure failures immediately.
  * Bad / Trade-off, because requires strict negative prompt engineering in Pydantic schema field description.

##### Option 5.2: Dedicated Secondary Guardrail Judge LLM (REJECTED)
* **Description**: Transcribing the utterance first, then firing a second sequential LLM call to judge whether the call was terminated.
* **Data Engineering & Performance**: Doubles LLM network roundtrips on every single turn (adding $\sim 1.2{-}1.8$s latency), multiplying the risk of Centrala session timeout.
* **Cost & FinOps**: Doubles token consumption and increases Vertex AI rate limit (429) exposure.
* **Pros & Cons**:
  * Bad / Trade-off, because severe latency penalty in a real-time telephony scenario.

##### Option 5.3: Pure Regex / Keyword Matching (REJECTED)
* **Description**: Python scans transcript for keywords like "alarm", "rozłączam", "oszust".
* **Data Engineering & Performance**: Instantaneous.
* **Security & Reliability**: Catastrophic false positive risk. If the operator says *"Spokojnie Tymon, nie ma żadnego alarmu, droga jest czysta"*, the regex detects "alarm" and triggers a false restart!
* **Pros & Cons**:
  * Bad / Trade-off, because lacks syntactic and negation comprehension.

#### Consequences
* **Positive**: Absolute transport reliability, zero latency overhead, and robust protection against premature restarts.
* **Negative / Trade-offs**: None.
* **Confirmation**: Verified with unit tests covering benign operator skepticism vs explicit termination payloads.

---

### Decision 6: Operational Agility & Telephony Runtime Overrides

#### Problem & Drivers
In production voice agent development, tuning speech pacing, voice models, or iteration limits via container redeployments causes 3–5 minute iteration lag.

#### Considered Options

##### Option 6.1: Comprehensive Telephony Overrides via `RunTaskRequest` & CLI (ACCEPTED)
* **Description**: Implement dynamic runtime overrides in `schemas.py` and CLI parser (`main.py`):
  ```python
  class RunTaskRequest(BaseModel):
      backend: Literal["langchain", "adk"] = "langchain"
      session_id: str | None = None
      model: str | None = None
      thinking_level: Literal["low", "medium", "high"] | None = None
      max_iterations: int = Field(default=15, description="Max conversation turns before timeout")
      voice_name: str = Field(default="pl-PL-Neural2-B", description="TTS voice identifier")
      speaking_rate: float = Field(default=1.05, description="TTS speaking rate (1.05-1.10 speeds audio delivery)")
      max_restarts: int = Field(default=2, description="Max session restarts if call gets burned")
  ```
* **Data Engineering & Performance**: Zero redeployment delay; enables tuning parameters on the fly via `curl.exe` or CLI flags (`--max-iterations 20 --speaking-rate 1.08`).
* **Cost & FinOps**: Caps maximum session restarts (`max_restarts = 2`), preventing infinite retry loops.
* **Security & Reliability**: Fully adheres to `GEMINI.md` dynamic runtime override standards.
* **Pros & Cons**:
  * Good, because cuts debug and benchmarking cycle to 0 seconds.
  * Good, because allows fine-tuning speech cadence to beat Centrala's timeout.
  * Bad / Trade-off, because requires schema and CLI argument parity.

##### Option 6.2: Static Constants in `config.py` (REJECTED)
* **Description**: Hardcoding voice name, speaking rate, and turn limits in environment files or source code.
* **Pros & Cons**:
  * Bad / Trade-off, because forces repeated container build & deploy cycles during testing.

#### Consequences
* **Positive**: Instantaneous tuning of voice models, pacing, and loop caps directly during evaluation.
* **Negative / Trade-offs**: None.
* **Confirmation**: Verified by passing custom overrides in CLI test suite.

---

## 4. Technical Baseline Alignment (GEMINI.md)

100% adherence to `GEMINI.md`. Zero intentional deviations:
- **Cloud Run Service**: `cr-s05e02-phonecall` registered in `terraform/variables.tf`.
- **BigQuery Audit**: Streamed telemetry into `af-aidevs.s05e02.audit`.
- **Model**: `gemini-3.8-flash` on Vertex AI (`vertexai=True`, `thinking_level="low"`).
- **TTS**: `google-cloud-texttospeech` with IAM authentication.
- **Python & Packaging**: Python 3.13.5, `uv` package manager with exact pinned versions.
- **Security**: Zero hardcoded URLs; all endpoints bound to `$AIDEVS_API_VERIFY`.

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [GEMINI.md](../../../GEMINI.md)
  - [BEST_PRACTICES.md](../../../BEST_PRACTICES.md)
