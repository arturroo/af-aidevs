<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-29
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S05E05 - Pocket Time Machine Autonomous Operation (timetravel)

## 1. Context

To rendezvous with resistance leader Rafał on November 12, 2024, Operative Number Five must operate the ACME CHRONOS-P1 pocket time machine across a hazardous 3-hop temporal trajectory: (1) jump to 2238-11-05 to retrieve fresh power cells, (2) jump back to the device's baseline present (2026-09-29), and (3) establish a sustained temporal tunnel to 2024-11-12. The device enforces a hybrid split between REST API registers (`$AIDEVS_API_VERIFY`) and physical cockpit controls (`$AIDEVS_TIMETRAVEL_PREVIEW_URL`), gated by a core `internalMode` phase cycle that rotates automatically every few seconds. The architectural fitness function requires a 100% autonomous, cloud-native dual-agent system capable of synchronizing temporal math, interpreting dynamic stabilization advice, actuating physical cockpit controls via browser automation, and capturing the final verification flag without human intervention.

---

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Service Architecture & Separation of Concerns | **Dual Cloud Run Microservices (`cr-s05e05-director` & `cr-s05e05-cockpit`)** | Isolates heavy Chromium/Playwright browser automation (2 GiB RAM, CPU 2) from fast, lightweight LLM orchestration (512 MiB RAM, CPU 1), preventing browser memory leaks from impacting mission logic and optimizing cold starts. |
| 2 | Inter-Agent Communication Protocol (A2A) | **Direct HTTP REST with GCP IAM OIDC Authentication** | Provides synchronous, sub-50ms deterministic command-and-control with zero intermediate messaging overhead, allowing instantaneous reaction to the 2-3 second hardware `internalMode` rotation window. Rejects formal A2A Protocol (`a2a-protocol.org`) discovery/Agent Card overhead since both agents are owned and deployed within a single-tenant GCP topology. |
| 3 | Cockpit Trigger Endpoint Naming | **Canonical `/activate-jump` Endpoint (Rejecting `/detonate`)** | Conforms accurately to ACME technical specifications ("Właściwy skok w czasie następuje po kliknięciu sfery") and API domain concepts (`action: "timeTravel"`). |
| 4 | Telemetry, State Persistence & Storage | **BigQuery Telemetry Only (`s05e05.audit`) — Zero Firestore Dependency** | Leverages the established BigQuery streaming pipeline for audit trails and telemetry without adding the operational overhead and complexity of an intermediate Firestore database. |
| 5 | Temporal Stabilization Parameter Resolution | **Pure LLM Interpretation via Gemini 3.5 Flash Lite (`thinking_level="low"`) with Dynamic Steering** | Accurately interprets conversational temporal distortion advice from the API while maintaining low latency and minimal token costs, with dynamic model and thinking level overrides supported in `RunTaskRequest`. |
| 6 | Radiation Shield (PWR) Knowledge Base Storage | **Pre-Compiled In-Memory Python Lookup Table ($1500 - 2499$)** | Grants $O(1)$ zero-IO lookup for shield potentiometer settings across all 1000 documented years, avoiding runtime file parsing or database queries. |
| 7 | Local Execution & Deployment Scope | **Cloud-Native Cloud Run Execution (Dropping Local CLI Mode)** | Focuses implementation strictly on production Cloud Run containers, eliminating local multi-process CLI harness complexity. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Service Architecture & Separation of Concerns (Dual Cloud Run vs Monolith)

#### Problem & Drivers
Browser automation with Playwright requires bundling a full Chromium binary and OS-level shared libraries (~1.2 GB container layer, $\ge 2\text{ GiB}$ RAM, 2 vCPUs). Conversely, the Temporal Flight Director only requires lightweight Python runtime, HTTP clients, and LLM SDKs (512 MiB RAM, 1 vCPU). Hosting both in a single container inflates cold starts, increases blast radius, and risks out-of-memory crashes if Chromium experiences memory leaks during page navigation.

#### Considered Options

##### Option 1.1: Dual Cloud Run Microservices (`cr-s05e05-director` + `cr-s05e05-cockpit`) (ACCEPTED)
* **Description**: Deploys two discrete Cloud Run services:
  1. `cr-s05e05-director`: Implements canonical `@app.post("/run")`, trajectory state machine, BigQuery streaming audit, and LLM stabilization resolver.
  2. `cr-s05e05-cockpit`: Dedicated Playwright/Chromium container exposing private REST endpoints to manipulate `$AIDEVS_TIMETRAVEL_PREVIEW_URL`.
* **Data Engineering & Performance**: Director cold starts in $< 2\text{s}$; Cockpit cold starts in $\approx 5-8\text{s}$. Memory isolation guarantees browser crashes cannot terminate the Director.
* **Cost & FinOps**: Cloud Run scale-to-zero applies independently; Director scales down instantly; Cockpit consumes higher RAM tier only during active actuation.
* **Security & Reliability**: Cockpit is strictly private (`public = false`), accessible only via IAM service-to-service authentication (`roles/run.invoker`).
* **Pros & Cons**:
  * Good, because it adheres to clean microservice isolation and zero memory contamination.
  * Bad / Trade-off, because it requires managing two service definitions in Terraform and independent deployment manifests.

##### Option 1.2: Single Monolithic Cloud Run Container (REJECTED)
* **Description**: Packages both LLM flight orchestration and Chromium/Playwright in one container.
* **Data Engineering & Performance**: Heavy container image (~1.5 GB), sluggish cold starts for all requests.
* **Cost & FinOps**: Forces high resource allocations (2 GiB RAM, 2 vCPUs) even for lightweight API polling steps.
* **Security & Reliability**: Browser crash terminates entire flight controller.
* **Pros & Cons**:
  * Good, because single Terraform resource.
  * Bad / Trade-off, because heavy coupling, slow cold starts, and higher resource footprint.

#### Consequences
* **Positive**: Clean architectural separation, optimal resource utilization, resilience against browser runtime faults.
* **Negative / Trade-offs**: Requires two Cloud Run services registered in `terraform/variables.tf`.
* **Confirmation**: Verified by independent health checks (`GET /health`) on both services and private IAM service invocation.

---

### Decision 2: Inter-Agent Communication Protocol (A2A over HTTP/OIDC vs Pub/Sub vs Firestore)

#### Problem & Drivers
The CHRONOS-P1 hardware cycles its `internalMode` phase autonomously every few seconds. When the matching mode aligns with `Flux Density = 100%`, the system has an activation window of approximately 2–4 seconds to actuate the jump sphere before the core rotates to the next phase. The inter-agent communication channel must guarantee minimal latency, deterministic request-response handshakes, and strict serverless CPU allocation.

#### Considered Options

##### Option 2.1: Direct Agent-to-Agent (A2A) via HTTP REST + IAM OIDC (ACCEPTED)
* **Description**: `cr-s05e05-director` authenticates via Google Cloud IAM OIDC tokens (`Authorization: Bearer <oidc_token>`) to invoke private REST endpoints on `cr-s05e05-cockpit`:
  - `POST /controls`: Sets `PTA`, `PTB`, `PWR`, and operating mode (`standby`/`active`).
  - `GET /telemetry`: Queries live DOM state (`flux_density`, `sync_ratio`, `imode`, `battery`, `sphere_state`).
  - `POST /activate-jump`: Instructs Cockpit to monitor `internalMode` and click the glowing sphere the instant conditions are satisfied.
* **Data Engineering & Performance**: Direct internal GCP network latency is $\approx 10-25\text{ ms}$. Cockpit receives active Cloud Run CPU allocation during incoming HTTP invocations.
* **Cost & FinOps**: Zero messaging broker fees; operates within standard Cloud Run request pricing.
* **Security & Reliability**: Strong authentication enforced via Google IAM `roles/run.invoker`.
* **Pros & Cons**:
  * Good, because deterministic, ultra-low latency, and simple error propagation.
  * Bad / Trade-off, because Director must know Cockpit's target service URL.

##### Option 2.2: Event Mesh via Google Cloud Pub/Sub (REJECTED)
* **Description**: Asynchronous message queues with Push Subscriptions between Director and Cockpit.
* **Data Engineering & Performance**: Message routing latency (150–400 ms) introduces unacceptable jitter during narrow `internalMode` activation windows.
* **Cost & FinOps**: Additional Pub/Sub topic and subscription management.
* **Security & Reliability**: Asynchronous delivery complicates step-by-step lockstep trajectory verification.
* **Pros & Cons**:
  * Good, because completely decoupled.
  * Bad / Trade-off, because timing unpredictability risks missing the time-jump ignition window.

##### Option 2.3: Blackboard Architecture via Firestore (REJECTED)
* **Description**: Both agents synchronize by reading and writing document state in Firestore.
* **Data Engineering & Performance**: DB polling/listener roundtrips (50–150 ms) plus Firestore write pricing overhead. Cloud Run CPU throttling suspends background listeners unless expensive `always_allocated: true` is configured.
* **Cost & FinOps**: High Firestore read/write costs for rapid state polling.
* **Security & Reliability**: Introduces schema-level coupling across database documents.
* **Pros & Cons**:
  * Good, because state is persistent and observable in console.
  * Bad / Trade-off, because unnecessary complexity given existing BigQuery telemetry pipeline.

##### Option 2.4: Formal A2A Protocol Standard with Agent Card (a2a-protocol.org) (REJECTED / FUTURE CANDIDATE)
* **Description**: Strictly follows the formal open standard [A2A Protocol](https://a2a-protocol.org/latest/topics/what-is-a2a/#a2a-request-lifecycle) (now part of the Agentic AI Foundation / Linux Foundation). Under this protocol:
  1. **Agent Discovery**: The actuator service (`cr-s05e05-cockpit`) serves an **Agent Card** at `GET /.well-known/agent-card` (or `/.well-known/agent.json`), advertising its identity, schema version, capabilities, discrete skills (`set_controls`, `activate_jump`), and security schemes.
  2. **Authentication**: The client parses the card's `securitySchemes` and acquires an appropriate token (e.g., OpenID Connect JWT).
  3. **Task Execution**: Communication happens via standardized envelope endpoints (`POST /sendMessage` and `POST /sendMessageStream`).
* **Why Rejected in S05E05**:
  1. **Total Single-Tenant Ownership**: We design, build, and control both the Director and Cockpit agents from day zero within the same hermetic Google Cloud project. Dynamic discovery and capability negotiation are superfluous when the topology is fully known at build and deploy time.
  2. **Latency & Execution Deadlines**: CHRONOS-P1 hardware enforces narrow 2–4 second `internalMode` phase windows. Introducing standard A2A JSON envelope parsing, message dispatch wrappers, and dynamic capability resolution adds unnecessary latency and serialization overhead compared to direct, typed Pydantic REST calls (`POST /controls`, `POST /activate-jump`).
  3. **Native Cloud Run IAM**: Direct service-to-service calls authenticated via Google Cloud IAM OIDC tokens (`Authorization: Bearer $(gcloud auth print-identity-token)`) are significantly simpler and more robust than implementing custom A2A auth handshake layers.
* **Pros & Cons**:
  * Good, because it adheres to the formal industry-standard A2A Protocol specification, facilitating open federation with third-party multi-agent ecosystems.
  * Bad / Trade-off, because it introduces unnecessary protocol bloat, envelope nesting, and discovery overhead for an internal, tightly-coupled microservice pair with strict microsecond physical timing constraints.
* **Reference Implementation (Agent Card Specification for Future Adoption)**:
  Should the system be opened to external or federated autonomous agents in the future, `cr-s05e05-cockpit` would expose the following canonical Agent Card at `/.well-known/agent-card`:

```json
{
  "$schema": "https://a2a-protocol.org/latest/schemas/agent-card.json",
  "name": "CHRONOS-P1 Cockpit Actuator Agent",
  "description": "Autonomous browser-based hardware actuator managing physical directional switches (PT-A, PT-B), PWR shields, core flux stabilization, and ignition orb trigger for CHRONOS-P1.",
  "version": "1.0.0",
  "url": "https://cr-s05e05-cockpit-qsvqxjqyrq-oa.a.run.app/a2a",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "set_controls",
      "name": "Set Physical Cockpit Controls",
      "description": "Configures directional switches PT-A, PT-B, PWR shield slider, and hardware operational mode (standby/active).",
      "parameters": {
        "pta": { "type": "boolean", "description": "Engage past transit" },
        "ptb": { "type": "boolean", "description": "Engage future transit" },
        "pwr": { "type": "integer", "minimum": 0, "maximum": 100, "description": "Radiation shield potentiometer power" },
        "mode": { "type": "string", "enum": ["standby", "active"], "description": "Hardware operational state" }
      }
    },
    {
      "id": "activate_jump",
      "name": "Execute Ignition Sequence",
      "description": "Monitors core flux density until 100%, awaits target internalMode phase window, and actuates physical ignition orb.",
      "parameters": {
        "target_imode": { "type": "integer", "minimum": 1, "maximum": 4, "description": "Required internalMode phase for destination epoch" },
        "timeout_seconds": { "type": "number", "default": 30.0, "description": "Maximum seconds to await core phase alignment" }
      }
    }
  ],
  "securitySchemes": {
    "googleOidc": {
      "type": "openIdConnect",
      "openIdConnectUrl": "https://accounts.google.com/.well-known/openid-configuration"
    }
  }
}
```

#### Consequences
* **Positive**: Sub-second execution, deterministic sequencing, zero message-broker latency.
* **Negative / Trade-offs**: Director requires Cockpit's service URL passed via environment variable (`COCKPIT_SERVICE_URL`).
* **Confirmation**: Contract unit tests with `httpx` mock transports and end-to-end integration test validating IAM token generation.

---

### Decision 3: Cockpit Trigger Endpoint Naming (`/activate-jump` vs `/detonate`)

#### Problem & Drivers
Initial drafts proposed `/detonate` for triggering the time jump sphere. However, CHRONOS-P1 is a precision temporal displacement device, not an explosive ordnance. The documentation canonically terms this operation *"Właściwy skok w czasie"* via clicking the activation sphere, matching API `action: "timeTravel"`.

#### Considered Options

##### Option 3.1: Canonical Endpoint `/activate-jump` (ACCEPTED)
* **Description**: The endpoint on `cr-s05e05-cockpit` responsible for clicking the sphere and initiating temporal displacement is named `POST /activate-jump`.
* **Data Engineering & Performance**: Clean semantic alignment with domain logic.
* **Pros & Cons**:
  * Good, because it reflects the exact technical manual terminology without sensationalized militaristic metaphors.

##### Option 3.2: Legacy Metaphor Endpoint `/detonate` (REJECTED)
* **Description**: Misleading endpoint name implying destruction rather than navigation.
* **Pros & Cons**:
  * Bad, because confusing and inconsistent with course domain vocabulary.

#### Consequences
* **Positive**: High readability and domain accuracy across API contracts and schemas.
* **Confirmation**: OpenAPI schema generated at `/docs` confirms `/activate-jump`.

---

### Decision 4: Telemetry, State Persistence & Storage (BigQuery Only vs Firestore)

#### Problem & Drivers
Telemetry, execution tracing, and step-by-step audit records are essential for debugging and compliance. While Firestore was considered, the repository already enforces BigQuery as the canonical enterprise audit store.

#### Considered Options

##### Option 4.1: BigQuery Telemetry Pipeline Only (`s05e05.audit`) (ACCEPTED)
* **Description**: All flight events, parameter configurations, API responses, stabilization inferences, and flag captures are streamed directly to BigQuery dataset `s05e05` (table `audit`) using the existing `af_aidevs` telemetry framework.
* **Data Engineering & Performance**: High-throughput streaming inserts (`google-cloud-bigquery`), zero impact on real-time request latencies, standard SQL queryability via `bq` CLI.
* **Cost & FinOps**: Free tier covers BigQuery ingestion and queries for course workloads.
* **Security & Reliability**: Append-only tamper-resistant audit trail.
* **Pros & Cons**:
  * Good, because zero new infrastructure dependencies; reuses established BigQuery patterns.
  * Bad / Trade-off, because BigQuery is not an operational state store (which is not needed anyway with A2A).

##### Option 4.2: Hybrid Firestore + BigQuery Architecture (REJECTED)
* **Description**: Firestore for operational session state + BigQuery for long-term telemetry.
* **Data Engineering & Performance**: Redundant double-write overhead.
* **Cost & FinOps**: Unnecessary resource allocation.
* **Pros & Cons**:
  * Bad, because unjustified over-engineering.

#### Consequences
* **Positive**: Lean infrastructure footprint, standard SQL audit verification.
* **Confirmation**: Standard PowerShell verification query:
  ```powershell
  bq query --use_legacy_sql=false --project_id=af-aidevs 'SELECT timestamp, session_id, actor, SUBSTR(content, 1, 60) AS preview FROM `af-aidevs.s05e05.audit` ORDER BY timestamp DESC LIMIT 10'
  ```

---

### Decision 5: Temporal Stabilization Parameter Resolution (Gemini 3.5 Flash Lite)

#### Problem & Drivers
When coordinates (`day`, `month`, `year`) are set via `/verify`, the API generates contextual temporal distortion hints. These hints are conversational and non-deterministic, varying with environmental noise.

#### Considered Options

##### Option 5.1: Pure LLM Interpretation via Gemini 3.5 Flash Lite (`thinking_level="low"`) with Dynamic Overrides (ACCEPTED)
* **Description**: Routes the API response message and configuration snapshot to Vertex AI Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite`) with structured Pydantic output. Supports dynamic runtime steering via `RunTaskRequest(model=..., thinking_level=...)`.
* **Data Engineering & Performance**: Ultra-fast latency (~400 ms), token economics $< \$0.0001$ per invocation.
* **Cost & FinOps**: Highly optimized on Vertex AI global endpoints.
* **Security & Reliability**: Enforces strict Pydantic parsing (`StabilizationDecision(stabilization_value=...)`).
* **Pros & Cons**:
  * Good, because robust against linguistic variations in API advice; allows immediate fallback to `gemini-3.8-flash` if quota is saturated.

##### Option 5.2: Rigid Regex Rule Parser (REJECTED)
* **Description**: Regex pattern matching looking for numeric digits or keywords.
* **Pros & Cons**:
  * Bad, because brittle when hints describe conditions metaphorically or relatively.

#### Consequences
* **Positive**: High resilience to API prompt changes, flexible runtime model selection.
* **Confirmation**: Unit tests covering diverse mocked stabilization advice strings.

---

### Decision 6: Radiation Shield (PWR) Knowledge Base Storage

#### Problem & Drivers
The ACME hardware manual contains a 1000-year lookup table ($1500 - 2499$) mapping each year to its required shield protection value (`PWR`, $0 - 100$).

#### Considered Options

##### Option 6.1: Pre-Compiled In-Memory Python Dictionary (ACCEPTED)
* **Description**: Pre-compiles the entire 1000-entry table into a static dictionary in `services/temporal_table.py` (`PWR_TABLE: dict[int, int] = { 1500: 3, ..., 2024: 19, 2026: 28, 2238: 91, ... }`).
* **Data Engineering & Performance**: $O(1)$ memory lookup ($< 0.001\text{ ms}$), zero disk I/O, zero network calls.
* **Cost & FinOps**: Negligible memory footprint (< 50 KB).
* **Pros & Cons**:
  * Good, because deterministic, instantaneous, and zero external dependencies.

##### Option 6.2: Dynamic Markdown Parser on Startup (REJECTED)
* **Description**: Parses `timetravel.md` at runtime during service container startup.
* **Pros & Cons**:
  * Bad, because risks container startup failure if markdown structure is altered or file is missing.

#### Consequences
* **Positive**: Flawless reliability and instant execution.
* **Confirmation**: Unit tests asserting `PWR_TABLE[2238] == 91`, `PWR_TABLE[2024] == 19`, and `PWR_TABLE[2026] == 28`.

---

### Decision 7: Cloud-Native Cloud Run Execution (Dropping Local CLI Mode)

#### Problem & Drivers
Artur explicitly determined that local CLI execution is not required for this task. Building dual-agent local terminal harnesses and managing multiple local ports/processes adds maintenance overhead without production value.

#### Considered Options

##### Option 7.1: Pure Cloud-Native Cloud Run Execution (ACCEPTED)
* **Description**: System execution is triggered strictly via `@app.post("/run")` on `cr-s05e05-director`, which coordinates with `cr-s05e05-cockpit` across private Google Cloud infrastructure.
* **Data Engineering & Performance**: Native Cloud Logging, Cloud Trace, and BigQuery telemetry integration.
* **Pros & Cons**:
  * Good, because eliminates redundant local CLI scaffolding; focuses 100% on production container reliability.

##### Option 7.2: Hybrid CLI + Cloud Run Support (REJECTED)
* **Description**: Maintaining a dual-purpose CLI runner with local Playwright launcher.
* **Pros & Cons**:
  * Bad, because unnecessary complexity explicitly declined by the decision-maker.

#### Consequences
* **Positive**: Leaner codebase, zero terminal UI dependencies (e.g. curses/rich loops).
* **Confirmation**: Verified via private `POST /run` invocation using identity tokens.

---

## 4. Technical Baseline Divergence (GEMINI.md)

Divergences:
1. **Multi-Service Architecture (2 Cloud Run Microservices instead of 1):**
   - Reason: Cleanly isolates the heavy Chromium/Playwright container (`cr-s05e05-cockpit`) from the fast, lightweight LLM orchestration container (`cr-s05e05-director`), optimizing cold starts, memory usage, and blast radius.
2. **CLI Mode Dropped:**
   - Reason: Explicit architectural decision by Artur to operate 100% cloud-natively, eliminating local terminal orchestration harnesses.

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [ACME CHRONOS-P1 Manual (gitignored)](../timetravel.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
