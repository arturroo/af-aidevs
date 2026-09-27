# Business Requirements Document (BRD) - S05E02: Phonecall & Conversational Audio Agent

## 1. Overview & Business Objectives

In the ongoing resistance operation against Zygfryd's regime, Azazel and the resistance forces need to safely evacuate populations from threatened cities to Syjon. To execute this evacuation without triggering alarms in the OKO surveillance network, the resistance must establish a direct telephone connection to one of the system operators.

The objective of the `phonecall` task is to build an automated, conversational audio agent capable of conducting an interactive, multi-turn voice conversation with the OKO system operator over an audio-mediated API to:
1. Establish identity as operative **Tymon Gajewski**.
2. Interrogate the operator regarding the operational status and passability of three prospective evacuation routes: **RD224**, **RD472**, and **RD820**, contextualizing the request as logistical preparation for transport to one of Zygfryd's bases.
3. Transcribe and semantically comprehend the operator's spoken audio responses to identify which road is safe, uncontaminated, and passable.
4. Persuade the operator to deactivate surveillance monitoring on the confirmed safe evacuation route.
5. Provide the operator secret clearance password (**BARBAKAN**) when prompted for authorization.
6. Provide cover rationale if questioned (explaining that food supplies are being routed to a clandestine base whose coordinates cannot be exposed in system logs).
7. Successfully verify the action with Centrala to retrieve the mission flag (`{FLG:...}`).

---

## 2. Functional Requirements

### 2.1 Multi-Stage Conversational Lifecycle Protocol
The conversation with Centrala's verification endpoint (`$AIDEVS_API_VERIFY`) proceeds in distinct phases:

1. **Session Initialization (`action: "start"`):**
   - Transmit an initial JSON payload specifying `task: "phonecall"` and `answer: {"action": "start"}`.
   - Resets any previous session state and initializes the operator's communication channel and state machine.

2. **Interactive Audio Conversation Loop (`answer: {"audio": "<base64>"}`):**
   - Every subsequent turn MUST be transmitted as a Base64-encoded audio payload (MP3 format preferred).
   - The operator responds with Base64-encoded audio (or JSON status/error payloads).
   - Maintain conversational context and state across turns:
     - **Turn 1 (Introduction & Route Query):** Introduce self as Tymon Gajewski, ask for the status of all three roads (`RD224`, `RD472`, `RD820`), and declare that the inquiry is for transport organized to one of Zygfryd's bases (must be bundled into one single coherent message).
     - **Turn 2+ (Comprehension & Route Identification):** Listen to the operator's response, decode/transcribe the audio, extract the status of the three routes, and pinpoint the clear/passable route.
     - **Authorization Challenge Handling:** If the operator demands identity verification or an authorization code, provide the secret password: `BARBAKAN`.
     - **Monitoring Deactivation Request:** Request the operator to turn off monitoring on the specific road identified as passable.
     - **Cover Justification Handling:** If the operator inquires why monitoring must be disabled, explain that this is a food transport to one of Zygfryd's secret bases, whose coordinates must remain confidential, meaning the mission must not appear in monitoring logs.

3. **Session Failure & Recovery:**
   - If the operator detects suspicion, burns the call, or an invalid sequence of requests occurs, the session terminates.
   - The agent must be capable of detecting conversation termination/failure, resetting by issuing `action: "start"`, and restarting the protocol from Turn 1.

### 2.2 Conversational & Speech Engineering Rules
- **Language:** Polish exclusively (`pl-PL`). Both operator speech and agent speech must be natural, fluent Polish.
- **Persona:** Tymon Gajewski.
- **Conciseness & Message Granularity:** Keep utterances concise, focused, and credible. Do not bundle multiple unrelated requests into a single utterance (except Turn 1's requirement to query all three roads and state the transport reason together).
- **Time Sensitivity:** Centrala enforces an active session timeout. Processing pipelines (STT transcription, reasoning/dialogue policy, and TTS synthesis) must maintain low latency ($\le 5{-}10$ seconds per turn) to avoid session expiration.
- **Audio Encoding Standards:**
  - Ingestion (STT): Support Base64-encoded MP3/WAV/OGG payloads returned by the operator.
  - Egress (TTS): Synthesize natural Polish speech formatted as Base64-encoded MP3 (`audio/mp3` or `audio/mpeg`).

---

## 3. System & Token Constraints

- **Execution Environment:** Google Cloud Run microservice (`cr-s05e02-phonecall`) with local CLI testing mode (`main.py --mode cli` / `uv run python main.py`).
- **Cognitive Workhorse Model:** **Gemini 3.8 Flash** (`gemini-3.8-flash`) via Vertex AI (`vertexai=True`, `thinking_level="low"`) for:
  - Multimodal audio comprehension / STT transcription of operator utterances.
  - Conversational dialogue management and policy decisions.
- **Speech-to-Text (STT):**
  - Primary: Gemini 3.8 Flash native multimodal audio understanding (processing Base64/raw audio parts directly, eliminating external STT service latency).
  - Alternative / Fallback: Google Cloud Speech-to-Text API or ElevenLabs / Whisper.
- **Text-to-Speech (TTS):**
  - Primary: Text-to-Speech synthesis generating clean Polish male speech (e.g. ElevenLabs API or Google Cloud Text-to-Speech).
- **Session State & Telemetry:**
  - Cloud Run microservice remains stateless; active session conversation history and turn states tracked per execution / session ID.
  - Structured BigQuery audit logging in dataset `s05e02`, table `audit`.
  - Zero-pollution logging: raw Base64 audio strings must NEVER be dumped into stdout, Cloud Logging, BigQuery audit tables, or LangSmith traces (use output masking: `<REDACTED_BASE64: N chars, ~X KB>`).

---

## 4. Data Inputs & External Resources

All external endpoints and credentials must be injected exclusively via environment variables:

| Resource Description | Environment Variable | Usage in Service |
| :--- | :--- | :--- |
| Centrala Verification API | `$AIDEVS_API_VERIFY` | Endpoint for session initiation and audio turns |
| AI_Devs Personal API Key | `$AIDEVS_API_KEY` | Authenticates all requests sent to Centrala |
| Text-to-Speech API Key (if external) | `$ELEVENLABS_API_KEY` or GCP TTS | Speech synthesis for agent utterances |
| BigQuery Project / Dataset | `$GOOGLE_CLOUD_PROJECT` / `$BQ_DATASET` | Audit telemetry logging (`af-aidevs.s05e02.audit`) |
| LangSmith Observability | `$LANGSMITH_API_KEY` | Distributed LLM call tracing |
| LangSmith Project | `$LANGSMITH_PROJECT` | Tracing namespace (`af-aidevs`) |

---

## 5. API Integration Schemas

### 5.1 Step 1: Session Start Request
**POST** `$AIDEVS_API_VERIFY`
```json
{
  "apikey": "your-api-key",
  "task": "phonecall",
  "answer": {
    "action": "start"
  }
}
```

### 5.2 Step 2+: Conversational Turn Request
**POST** `$AIDEVS_API_VERIFY`
```json
{
  "apikey": "your-api-key",
  "task": "phonecall",
  "answer": {
    "audio": "base64_encoded_audio_data"
  }
}
```

### 5.3 Centrala Response Schemas
- **Operator Audio Turn Response (Success / In Progress):**
  ```json
  {
    "code": 0,
    "message": "...",
    "audio": "base64_encoded_audio_data",
    "description": "..."
  }
  ```
  *(Or direct audio string/object depending on Centrala's format; service must handle both).*
- **Mission Accomplished Response (Flag):**
  ```json
  {
    "code": 0,
    "message": "{FLG:...}"
  }
  ```
- **Session Failure / Burned Call:**
  ```json
  {
    "code": -1,
    "message": "Rozmowa została przerwana / podejrzana..."
  }
  ```

---

## 6. Acceptance & Verification Criteria

1. **Identity & Opening Protocol:** The agent initiates the call with `start`, introduces itself as Tymon Gajewski, and inquires about roads `RD224`, `RD472`, and `RD820` for transport to Zygfryd's base in the opening turn.
2. **Audio Turn Resilience:** All inbound operator audio is transcribed and evaluated; all outbound agent messages are converted to Base64 MP3 audio.
3. **Dialogue Policy Adherence:**
   - Detects the passable road without hallucinations.
   - Appropriately supplies the password `BARBAKAN` when challenged.
   - Provides the food transport cover justification if pressed for rationale.
   - Directs the operator to disable monitoring on the passable road.
4. **Mission Flag Acquisition:** Successfully guides the operator to disable monitoring and extracts the course flag (`{FLG:...}`).
5. **Observability & Code Quality:**
   - Full trace visibility in LangSmith with masked Base64 payloads.
   - Zero hardcoded URLs or credentials.
   - 100% compliance with Ruff formatting, Ruff linting, and mypy static type checking.
