<!-- Source: https://www.industrialempathy.com/posts/design-docs-at-google/ -->
<!-- Based on: Google Design Docs structure by Malte Ubl -->
<!-- Adapted as a Technical PRD for AI-assisted implementation workflows -->

---
status: "approved"
date: 2026-09-27
author: "Artur <artur.fejklowicz>"
reviewers: ["Joi <antigravity>"]
adr: "[ADR.md](ADR.md)"
---

# Technical Product Requirements Document: S05E02 Conversational Voice Agent (Phonecall)

## Context and Scope

During the resistance operation against Zygfryd's surveillance regime, Azazel and the resistance forces must coordinate an urgent civilian evacuation to Syjon. To prevent triggering automated alerts in the OKO surveillance grid, the resistance has established an audio telephone link to one of the central system operators. The operative Tymon Gajewski must query the status of three potential transit corridors (**RD224**, **RD472**, and **RD820**), identify the single uncontaminated route to Syjon, and persuade the operator to deactivate surveillance monitoring exclusively on that route.

Centrala exposes an audio-mediated HTTP verification endpoint (`$AIDEVS_API_VERIFY`) requiring session initialization followed by multi-turn Base64-encoded audio exchanges in Polish (`pl-PL`). The conversation enforces strict protocol sequencing, brevity, secret password authorization (`BARBAKAN`), cover story de-escalation (food transport to a clandestine base), and active session timeouts.

This document specifies the architecture, data models, state machines, prompt topologies, and integration pipelines for the `cr-s05e02-phonecall` Cloud Run microservice. All architectural choices have been finalized and accepted in [ADR.md](ADR.md) following the foundational requirements in [BRD.md](BRD.md).

---

## Goals and Non-Goals

### Goals
* **Automated Audio-Mediated Dialogue:** Establish an interactive telephone conversation with Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) via `task: "phonecall"`, transmitting and receiving Base64-encoded MP3 audio.
* **Deterministic Opening Message:** Ensure Turn 1 atomically bundles Tymon Gajewski's identity, an inquiry covering all three roads (`RD224`, `RD472`, `RD820`), and justification regarding transport to Zygfryd's base in a single coherent message.
* **Inbound Multimodal Extraction & Affect Analysis (STT):** Ingest operator audio directly into **Gemini 3.8 Flash** via `Part.from_bytes()` in a single roundtrip, extracting verbatim transcripts, sentence-level classifications (sentiment, irony, humor, topic), overall suspicion level (`Literal["low", "medium", "high", "critical"]`), password challenges, and discrete road statuses (`Literal["passable", "blocked", "contaminated", "unknown"]`).
* **Declarative Dialogue State & Policy Engine:** Maintain a centralized `DialogueState` (Slot-Filling / Blackboard Architecture) governed by a deterministic Python `PolicyEngine` (`determine_next_objective`), eliminating LLM turn-order hallucinations while gracefully handling compound operator utterances.
* **Outbound Speech Synthesis (TTS):** Generate studio-quality Polish male speech using **Google Cloud Text-to-Speech API** (`pl-PL-Neural2-B`) with SSML phonetic formatting (`<say-as interpret-as="characters">RD</say-as>`) and accelerated speaking rate (`speaking_rate = 1.05`), achieving $\$0.00$ cost under GCP Free Tier and zero container transcoding dependencies.
* **De-Escalation & Cover Management:** Dynamically trigger the food transport cover story (clandestine base, unlogged mission) if operator suspicion or rationale inquiries are detected.
* **Secret Authorization Clearance:** Provide the secret clearance code `BARBAKAN` exclusively when prompted by the operator.
* **Dual-Source Call Termination Detection:** Detect call termination (`call_burned`) via deterministic HTTP/transport checks and single-roundtrip Pydantic semantic classification, triggering automatic session reset up to `max_restarts = 2`.
* **Zero-Pollution Observability:** Stream sanitized audit logs to BigQuery (`af-aidevs.s05e02.audit`) and full traces to LangSmith with Base64 audio payloads masked to `<REDACTED_BASE64: N chars, ~X KB>`.
* **Dynamic Runtime Overrides:** Support dynamic overrides in `RunTaskRequest` and CLI (`max_iterations`, `voice_name`, `speaking_rate`, `max_restarts`, `model`, `thinking_level`).

### Non-Goals
* **Realtime WebRTC / SIP Gateway:** The service communicates over Centrala's turn-based HTTP Base64 audio envelope; native SIP/RTP telephony gateways are excluded.
* **OpenAI / ElevenLabs External Integration:** Voice synthesis relies strictly on GCP Cloud TTS via IAM credentials; external third-party TTS subscriptions are out of scope.
* **Complex Multi-Agent Swarms:** A single orchestrator with modular service clients suffices; multi-agent consensus networks are excluded to prevent latency bloat.

---

## The Design

### System Overview

```
                                  ┌────────────────────────────────────────┐
                                  │      Centrala Verification API         │
                                  │        ($AIDEVS_API_VERIFY)            │
                                  └───────────────────┬────────────────────┘
                                                      │
                                                      │ HTTP POST (action: start | audio: base64)
                                                      ▼
                       ┌────────────────────────────────────────────────────────────────┐
                       │             Cloud Run: cr-s05e02-phonecall                     │
                       │                                                                │
                       │  ┌──────────────────────────────────────────────────────────┐  │
                       │  │         Conversational Dialogue Orchestrator             │  │
                       │  │   - Manages Multi-Turn Call Lifecycle                    │  │
                       │  │   - Maintains session DialogueState (Slot-Filling)       │  │
                       │  │   - Governs Timeout Limits (max_iterations) & Restarts   │  │
                       │  └──────────────┬────────────────────────────┬──────────────┘  │
                       │                 │                            │                 │
                       │                 │ (1) Inbound Audio Bytes    │ (4) Synthesized │
                       │                 │     Single Roundtrip       │     MP3 Audio   │
                       │                 ▼                            ▼                 │
                       │    ┌─────────────────────────┐  ┌─────────────────────────┐   │
                       │    │    Gemini 3.8 Flash     │  │  Google Cloud Text-to-  │   │
                       │    │   Multimodal Analysis   │  │       Speech API        │   │
                       │    │ - OperatorTurnAnalysis  │  │ - pl-PL-Neural2-B       │   │
                       │    │ - Verbatim Transcript   │  │ - SSML Formatting       │   │
                       │    │ - Sentiments & Irony    │  │ - speaking_rate: 1.05   │   │
                       │    │ - Road Statuses (RD*)   │  │ - $0.00 (GCP Free Tier) │   │
                       │    │ - Dual-Source Burn Det. │  └────────────┬────────────┘   │
                       │    └────────────┬────────────┘               │                 │
                       │                 │                            │                 │
                       │                 │ Updates DialogueState      │                 │
                       │                 ▼                            │                 │
                       │    ┌─────────────────────────┐               │                 │
                       │    │  Deterministic Python   │               │                 │
                       │    │      Policy Engine      │               │                 │
                       │    │ - Evaluates Slots       │               │                 │
                       │    │ - Resolves Next Objective               │                 │
                       │    └────────────┬────────────┘               │                 │
                       │                 │                            │                 │
                       │                 │ TurnObjective Directive    │                 │
                       │                 ▼                            │                 │
                       │    ┌─────────────────────────┐               │                 │
                       │    │ PromptBuilder & Speech  │               │                 │
                       │    │       Generation        │               │                 │
                       │    │ - KV-Cache Optimized    │───────────────┘                 │
                       │    │ - Generates SSML text   │  (Generates text for TTS)       │
                       │    └─────────────────────────┘                                 │
                       └───────────────────────────────┬────────────────────────────────┘
                                                       │
                      ┌────────────────────────────────┼────────────────────────────────┐
                      ▼                                ▼                                ▼
        ┌───────────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────┐
        │    BigQuery Telemetry     │    │         LangSmith         │    │       GCS Workspace       │
        │      (s05e02.audit)       │    │  (Masked Binary Tracing)  │    │ (gs://af-aidevs-workspaces│
        │   Masked Payload Logs     │    │   Turn Latency & Calls    │    │    Private Run Notes)     │
        └───────────────────────────┘    └───────────────────────────┘    └───────────────────────────┘
```

---

### API Design

#### Endpoints Exposed by `cr-s05e02-phonecall`

1. **`GET /` & `GET /health`**
   - Readiness and liveness probes.
   - Response: `{"status": "ok", "service": "cr-s05e02-phonecall", "version": "1.0.0"}`

2. **`POST /run`**
   - Canonical task execution endpoint.
   - Request Body (`RunTaskRequest`):
     ```python
     class RunTaskRequest(BaseModel):
         backend: Literal["langchain", "adk"] = "langchain"
         session_id: str | None = None
         model: str | None = None
         thinking_level: Literal["low", "medium", "high"] | None = None
         max_iterations: int = Field(default=15, description="Max conversation turns before timeout")
         voice_name: str = Field(default="pl-PL-Neural2-B", description="TTS voice identifier")
         speaking_rate: float = Field(default=1.05, description="TTS speaking rate (1.05-1.10 speeds delivery)")
         max_restarts: int = Field(default=2, description="Max session restarts if call gets burned")
     ```
   - Response Body (`RunTaskResponse`):
     ```python
     class RunTaskResponse(BaseModel):
         status: Literal["SUCCESS", "FAILED"]
         session_id: str
         turns_completed: int
         restarts_used: int
         selected_road: Literal["RD224", "RD472", "RD820"] | None
         monitoring_disabled: bool
         flag: str | None = None
         error: str | None = None
     ```

3. **CLI Mode**
   - Direct execution via:
     ```powershell
     uv run python main.py --mode cli --max-iterations 15 --voice-name pl-PL-Neural2-B --speaking-rate 1.05
     ```

#### External API Protocol (`$AIDEVS_API_VERIFY`)
- **Step 1: Session Start:**
  `POST $AIDEVS_API_VERIFY` with `{"apikey": "$AIDEVS_API_KEY", "task": "phonecall", "answer": {"action": "start"}}`
- **Step 2+: Audio Turn:**
  `POST $AIDEVS_API_VERIFY` with `{"apikey": "$AIDEVS_API_KEY", "task": "phonecall", "answer": {"audio": "<base64_mp3>"}}`
- **Centrala Responses:**
  - Success / In Progress: `{"code": 0, "message": "...", "audio": "<base64_mp3>"}`
  - Mission Accomplished: `{"code": 0, "message": "{FLG:...}"}`
  - Call Burned / Error: `{"code": -1, "message": "Rozmowa zerwana..."}`

---

### Data Model & Schemas

#### Strict PEP 585 / PEP 604 & Mutable Default Isolation (`schemas.py`)

```python
from typing import Literal
from pydantic import BaseModel, Field

RoadCode = Literal["RD224", "RD472", "RD820"]
RoadStatus = Literal["passable", "blocked", "contaminated", "unknown"]
MonitoringState = Literal["active", "disabled", "pending_auth", "refused", "unknown"]
TurnObjective = Literal[
    "SEND_OPENING_MESSAGE",
    "EXPLAIN_FOOD_LEGEND",
    "ANSWER_AUTH_CHALLENGE",
    "REQUEST_MONITORING_DEACTIVATION",
    "AWAIT_CONFIRMATION_AND_FLAG"
]

class RoadAssessment(BaseModel):
    status: RoadStatus = Field(default="unknown", description="Przejezdność drogi")
    monitoring: MonitoringState = Field(default="active", description="Stan monitoringu na trasie")
    operator_justification: str | None = Field(default=None, description="Uzasadnienie operatora")

def create_default_roads() -> dict[RoadCode, RoadAssessment]:
    return {
        "RD224": RoadAssessment(status="unknown", monitoring="active"),
        "RD472": RoadAssessment(status="unknown", monitoring="active"),
        "RD820": RoadAssessment(status="unknown", monitoring="active"),
    }

class SentenceAnalysis(BaseModel):
    sentence: str
    sentiment: Literal["positive", "neutral", "negative", "sarcastic"]
    is_irony: bool = False
    is_humor: bool = False
    topic: Literal["mission_logistics", "small_talk", "security_auth", "weather_other"]

class OperatorTurnAnalysis(BaseModel):
    operator_transcript: str = Field(description="Verbatim Polish transcript of operator speech")
    sentence_analyses: list[SentenceAnalysis] = Field(default_factory=list)
    overall_sentiment: Literal["cooperative", "neutral", "suspicious", "hostile"]
    suspicion_level: Literal["low", "medium", "high", "critical"]
    auth_requested: bool = Field(default=False, description="True if operator challenged for clearance/password")
    monitoring_disabled_confirmed: bool = Field(default=False, description="True if operator confirmed monitoring off")
    road_statuses: dict[RoadCode, RoadStatus] = Field(default_factory=dict)
    operator_justifications: dict[RoadCode, str] = Field(default_factory=dict)
    call_burned: bool = Field(
        default=False,
        description=(
            "Set to True ONLY if operator EXPLICITLY terminated conversation (hung up, sounded alarm, "
            "screamed spy/imposter, or permanently refused further interaction). Hesitation, gruffness, "
            "demanding the BARBAKAN password, or asking why monitoring must be disabled are strictly False!"
        )
    )
    call_burned_reason: str | None = None

class DialogueState(BaseModel):
    # Milestone 1: Opening
    opening_message_sent: bool = Field(
        default=False,
        description="Whether Tymon Gajewski + 3 roads + Zygfryd base transport was sent in Turn 1"
    )
    # Milestone 2: Route evaluation
    roads: dict[RoadCode, RoadAssessment] = Field(default_factory=create_default_roads)
    selected_evacuation_road: RoadCode | None = Field(default=None)
    
    # Milestone 3: Authorization
    auth_requested: bool = False
    auth_code_provided: bool = False
    
    # Milestone 4: Monitoring deactivation
    monitoring_deactivation_requested: bool = False
    monitoring_deactivation_confirmed: bool = False
    
    # Milestone 5: Suspicion & Cover story
    operator_suspicious: bool = False
    food_legend_used: bool = False
    
    # Safety & Telemetry
    call_burned: bool = False
    turn_count: int = 0
    mission_flag: str | None = None
    conversation_history: list[str] = Field(default_factory=list)
```

---

### Core Logic & Orchestration

#### 1. Deterministic Policy Engine (`services/policy_engine.py`)

```python
class PolicyEngine:
    @staticmethod
    def determine_next_objective(state: DialogueState) -> TurnObjective:
        # Priority 1: Mandatory Opening
        if not state.opening_message_sent:
            return "SEND_OPENING_MESSAGE"
        
        # Priority 2: Clear Authorization Challenge Immediately
        if state.auth_requested and not state.auth_code_provided:
            return "ANSWER_AUTH_CHALLENGE"
            
        # Priority 3: De-escalate Suspicion / Cover Story
        if state.operator_suspicious and not state.food_legend_used:
            return "EXPLAIN_FOOD_LEGEND"
            
        # Priority 4: Request Monitoring Deactivation on Confirmed Safe Road
        if state.selected_evacuation_road and not state.monitoring_deactivation_requested:
            return "REQUEST_MONITORING_DEACTIVATION"
            
        # Priority 5: Await Confirmation & Terminal Flag Extraction
        return "AWAIT_CONFIRMATION_AND_FLAG"
```

#### 2. KV-Cache Optimized Prompt Architecture (`services/prompt_builder.py`)

To maximize prefix cache hits across turns and condition generation directly on the immediate goal via the Transformer Attention Recency Effect, prompts are strictly segmented:

```python
STATIC_PERSONA_AND_RULES = """
Jesteś Tymonem Gajewskim, oficerem logistyki Zygfryda.
Rozmawiasz przez telefon z operatorem systemu OKO. Rozmowa odbywa się w turach.

ZASADY:
1. Odpowiadaj wyłącznie w języku polskim.
2. Twoje wypowiedzi muszą być krótkie, naturalne i rzeczowe (maksymalnie 1-2 zwięzłe zdania).
3. Nie proś o wiele rzeczy w jednej wypowiedzi.
4. Generuj tekst gotowy do syntezy mowy (SSML). Używaj tagu <speak>...</speak>.
   Dla nazw dróg ZAWSZE stosuj zapis: <say-as interpret-as="characters">RD</say-as> [numer], np. <say-as interpret-as="characters">RD</say-as> 224.
5. Jeśli operator rzucił krótki small-talk lub żart, odnieś się do niego naturalnie (maksymalnie pół zdania), ale natychmiast zrealizuj CEL TEJ TURY.
"""

OBJECTIVE_INSTRUCTIONS: dict[TurnObjective, str] = {
    "SEND_OPENING_MESSAGE": (
        "Przedstaw się jako Tymon Gajewski. W jednej nierozerwalnej wiadomości zapytaj o status wszystkich "
        "trzech dróg (RD224, RD472 i RD820) i poinformuj, że pytasz ze względu na organizowany transport "
        "do jednej z baz Zygfryda."
    ),
    "ANSWER_AUTH_CHALLENGE": (
        "Operator zażądał autoryzacji lub hasła. Podaj natychmiast tajne hasło operatorów: BARBAKAN. "
        "Zrób to krótko i pewnie."
    ),
    "EXPLAIN_FOOD_LEGEND": (
        "Operator dopytuje dlaczego chcesz wyłączyć monitoring lub wykazuje podejrzenia. Wyjaśnij, że jest to "
        "w ramach transportu żywności do jednej z tajnych baz Zygfryda. Nie wolno zdradzić jej lokalizacji, "
        "dlatego ta misja nie może być odnotowana w logach systemu."
    ),
    "REQUEST_MONITORING_DEACTIVATION": (
        "Zażądaj od operatora wyłączenia monitoringu na bezpiecznej drodze ({selected_road}). "
        "Zrób to profesjonalnie i zwięźle."
    ),
    "AWAIT_CONFIRMATION_AND_FLAG": (
        "Podziękuj operatorowi za współpracę i poproś o ostateczne potwierdzenie wyłączenia systemu."
    ),
}
```

#### 3. Conversational Orchestration Loop (`services/orchestrator.py`)
1. **Initialize:** Call `CentralaService.start_call()` (`action: "start"`).
2. **Turn Loop (`turn = 1 ... max_iterations`):**
   - Check if response contains `{FLG:...}` $\rightarrow$ Terminate `SUCCESS`.
   - Inbound Audio $\rightarrow$ Call `Gemini 3.8 Flash` with `OperatorTurnAnalysis` schema.
   - Update `DialogueState` with extracted facts:
     - Record road statuses; if single passable road found $\rightarrow$ set `selected_evacuation_road`.
     - Update `auth_requested`, `operator_suspicious`, `monitoring_deactivation_confirmed`.
   - **Dual-Source Call Burn Check:** If `centrala_error` or `turn_analysis.call_burned == True`:
     - If `restarts_used < max_restarts`: log warning, increment `restarts_used`, reset state, call `start_call()`, continue.
     - Else: fail session.
   - **Determine Next Objective:** Run `PolicyEngine.determine_next_objective(state)`.
   - **Build Prompt & Generate Speech Text:** Format prompt via `PromptBuilder`, invoke `ChatGoogleGenerativeAI(vertexai=True, thinking_level="low")`.
   - **Speech Synthesis (TTS):** Pass SSML text to `TTSService.synthesize_mp3(text, voice_name, speaking_rate)`.
   - **Egress:** Encode MP3 to Base64, transmit to Centrala (`answer: {"audio": "<base64>"}`).
   - Record turn in `conversation_history` and stream audit event to BigQuery.

---

### Infrastructure & Deployment

* **Cloud Run Microservice:** `cr-s05e02-phonecall` deployed in `europe-west1` or `europe-west6`.
  - Service Account: `sa-cr-s05e02-phonecall`
  - IAM Roles:
    - `roles/aiplatform.user` (Vertex AI inference for Gemini 3.8 Flash)
    - `roles/bigquery.dataEditor` (Dataset `s05e02`, Table `audit`)
    - `roles/bigquery.jobUser`
    - `roles/secretmanager.secretAccessor` (accessing `AIDEVS_API_KEY`, `AIDEVS_VERIFY`, `LANGSMITH_API_KEY`)
  - Concurrency: `80` (with strict `default_factory` memory isolation).
* **BigQuery Audit Dataset:** `s05e02` with table `audit` partitioned by ingestion time.
* **Terraform Registration:** Fully declared in `terraform/variables.tf` under `cr_names.cr-s05e02-phonecall` and `datasets.s05e02`.

---

## Cross-Cutting Concerns

### Security
* **Zero Hardcoded Secrets & URLs:** Canonical binding to `$AIDEVS_API_VERIFY` and `$AIDEVS_API_KEY` from Secret Manager in Cloud Run and `.env` in local development.
* **Course Flag Redaction:** Flag `{FLG:...}` strictly excluded from public logs, Git commits, and PR descriptions; persisted exclusively in private GCS run notes.

### Observability & Zero-Pollution Telemetry
* **Base64 Payload Masking:** Outbound and inbound Base64 MP3 payloads are masked in all logs, exceptions, and LangSmith traces (`<REDACTED_BASE64: length=X chars, ~Y KB>`).
* **Audit Streaming:** Every turn logs: `session_id`, `turn_index`, `objective`, `operator_sentiment`, `selected_road`, `latency_ms`.

### Performance & Timeouts
* **Low Latency Budget:**
  - Inbound Multimodal Extraction: $\sim 1.5{-}2.2$s
  - Python Policy & Prompt Builder: $\sim 0.01$s
  - Outbound Text Generation: $\sim 0.8{-}1.2$s
  - Cloud TTS Synthesis: $\sim 0.3{-}0.6$s
  - Network Egress: $\sim 0.3$s
  - **Total Turn Latency:** $\sim 3.0{-}4.3$s per turn (well within Centrala's telephone session timeout).

---

## Implementation Plan

### File Structure
```
lessons/s05e02-zestaw-narzedzi/task/
├── ADR.md                                 # Accepted architecture decision record
├── BRD.md                                 # Business requirements document
├── PRD.md                                 # This specification document
└── cr-s05e02-phonecall/                   # Cloud Run microservice directory
    ├── .dockerignore                      # Scaffolding ignore rules
    ├── .gcloudignore                      # Scaffolding ignore rules
    ├── .python-version                    # Pinned to 3.13.5
    ├── Dockerfile                         # Official python:3.13.5-slim container
    ├── cloudbuild.yaml                    # Automated container build manifest
    ├── pyproject.toml                     # Alphabetically sorted precise dependencies
    ├── README.md                          # Microservice documentation
    ├── config.py                          # Environment and configuration provider
    ├── schemas.py                         # Strict Pydantic contracts & state schemas
    ├── main.py                            # FastAPI app, /run endpoint & CLI runner
    ├── services/
    │   ├── __init__.py
    │   ├── audit_service.py               # BigQuery telemetry streaming
    │   ├── centrala_service.py            # Centrala HTTP verification client
    │   ├── policy_engine.py               # Deterministic turn objective selector
    │   ├── prompt_builder.py              # KV-cache aligned prompt generator
    │   ├── tts_service.py                 # Google Cloud Text-to-Speech API client
    │   └── orchestrator.py                # Main conversation lifecycle manager
    └── tests/
        ├── __init__.py
        ├── test_schemas.py                # State transitions & validation tests
        ├── test_policy_engine.py          # Decision table logic tests
        ├── test_prompt_builder.py         # Prompt format and SSML verification
        └── test_dual_source_burn.py       # Call burned detection tests
```

### Technology Stack (`pyproject.toml`)
* `requires-python = "==3.13.5"`
* Alphabetically sorted precise dependencies:
  - `fastapi==0.115.8`
  - `google-cloud-bigquery==3.29.0`
  - `google-cloud-texttospeech==2.23.0`
  - `google-genai==1.3.0`
  - `httpx==0.28.1`
  - `langchain==1.2.15`
  - `langchain-google-genai==2.0.10`
  - `langsmith==0.3.11`
  - `pydantic==2.10.6`
  - `pytest==8.3.4`
  - `pytest-asyncio==0.25.3`
  - `uvicorn==0.34.0`

### Step-by-Step Implementation Order
1. **Directory Scaffolding:** Create service directory structure and container scaffolding files (`.dockerignore`, `.gcloudignore`, `cloudbuild.yaml`, `Dockerfile`, `.python-version`, `pyproject.toml`).
2. **Configuration & Schemas:** Implement `config.py` and `schemas.py` with strict Pydantic models and mutable default isolation.
3. **Core Services:**
   - Implement `services/policy_engine.py` with deterministic decision table.
   - Implement `services/prompt_builder.py` with KV-cache prefix structure.
   - Implement `services/tts_service.py` with Cloud TTS `pl-PL-Neural2-B`.
   - Implement `services/centrala_service.py` with masked logging.
   - Implement `services/audit_service.py` with BigQuery streaming.
4. **Dialogue Orchestrator:** Implement `services/orchestrator.py` integrating turn loop, restart handling, and flag extraction.
5. **Entrypoints:** Implement `main.py` with FastAPI endpoints (`/`, `/health`, `/run`) and CLI runner.
6. **Unit Tests:** Implement comprehensive unit test suite in `tests/` verifying schemas, policy rules, and burn detection.
7. **Terraform Registration:** Register `cr-s05e02-phonecall` and BigQuery dataset `s05e02` in `terraform/variables.tf`.
8. **Quality Gate:** Pass the 5-point quality gate (`ruff check`, `ruff format`, `mypy`, `pytest`).

---

## Acceptance Criteria (Testable)

* [ ] **Turn 1 Opening Parity:** Opening utterance strictly introduces Tymon Gajewski, queries roads `RD224`, `RD472`, and `RD820`, and states the Zygfryd base transport reason in a single message.
* [ ] **Multimodal Inbound Extraction:** Ingests operator audio without external STT libraries and extracts typed `OperatorTurnAnalysis` (transcripts, sentiment, irony, road statuses).
* [ ] **Deterministic Authorization:** Supplies secret code `BARBAKAN` exclusively when operator issues an authorization challenge.
* [ ] **Food Transport Cover Story:** Supplies clandestine food transport justification when operator expresses suspicion or inquires why monitoring must be deactivated.
* [ ] **Target Road Deactivation:** Correctly instructs operator to disable monitoring on the single passable road confirmed by the operator.
* [ ] **GCP Cloud TTS Audio Egress:** Generates valid Base64-encoded MP3 audio using `pl-PL-Neural2-B` with valid SSML road tags (`<say-as interpret-as="characters">RD</say-as>`).
* [ ] **Dual-Source Call Burn Resilience:** Automatic session restart triggers upon explicit operator disconnect or Centrala error without false-triggering on normal hesitation.
* [ ] **Dynamic Overrides Parity:** Service respects `max_iterations`, `voice_name`, `speaking_rate`, and `max_restarts` passed via `POST /run` or CLI.
* [ ] **Zero Hardcoded Secrets & URLs:** All URLs and credentials bound strictly to environment variables.
* [ ] **Pre-Flight Quality Gate:** 100% pass on `ruff check`, `ruff format`, `mypy`, and `pytest`.
