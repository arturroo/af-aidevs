<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-13
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S03E02 Firmware Diagnostics (`cr-s03e02-firmware`)

## 1. Context
Based on the task requirements in BRD.md, the Emergency Core Cooling System (ECCS) controller firmware dump resides on a sandboxed Linux VM accessible exclusively via an HTTP Shell API (`$AIDEVS_API_SHELL`). The environment enforces strict anti-tamper security policies where inspecting `/etc`, `/root`, `/proc/`, or files listed in local `.gitignore` files immediately triggers automated firewall bans and resets the VM state to its initial snapshot. The architectural goal is to safely navigate the non-standard shell, discover authentication credentials, adjust `settings.ini`, and execute `/opt/firmware/cooler/cooler.bin` to retrieve the runtime confirmation token (`ECCS-[a-zA-Z0-9]{40}`). The system operates as a closed-loop autonomous process whose primary fitness function and termination condition is submitting this token to `$AIDEVS_API_VERIFY` and receiving the course verification flag (`{FLG:...}`).

## 2. Decision Summary (Executive Overview)
| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | VM Shell Anti-Tamper & Ban Prevention | Deterministic Client-Side Safety Interceptor | Intercepts forbidden directories and `.gitignore` patterns locally before remote dispatch, eliminating lockout bans and VM resets. |
| 2 | Shell API Error & Rate-Limit Handling | Automatic Backoff & Retry Interceptor | Encapsulates HTTP 429/503 and cooldown ban handling in the client layer, ensuring resilient execution without crashing the reasoning loop. |
| 3 | Agent Execution Strategy & Frameworks | Autonomous ReAct Loop with Dual Framework Parity (LangChain 1.2.15 & Google ADK 1.33.0) | Provides adaptive exploration of non-standard shell utilities while maintaining feature parity across LangChain and Google ADK backends. |
| 4 | LLM Model & Reasoning Configuration | Gemini 3.8 Flash (`thinking_level="low"`) on Vertex AI | Delivers fast inference, cost efficiency, and native tool-calling with configurable higher thinking levels for complex troubleshooting. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: VM Shell Anti-Tamper & Ban Prevention

#### Problem & Drivers
The VM environment strictly penalizes unauthorized access: inspecting `/etc`, `/root`, `/proc/`, or any file/directory matching local `.gitignore` rules results in a temporary IP ban (lockout for specified seconds) and an automatic VM reset to the initial snapshot. We must guarantee that our agent never issues prohibited shell commands.

#### Considered Options

##### Option 1.1: Deterministic Client-Side Safety Interceptor (ACCEPTED)
* **Description**: A pre-flight command analyzer in `services/safety_guardrail.py` that parses shell commands, checks path arguments against forbidden lists (`/etc`, `/root`, `/proc/`, relative traversals like `../etc`), and checks against a dynamic local cache of discovered `.gitignore` rules. Violations are blocked locally and returned as a descriptive tool error message.
* **Data Engineering & Performance**: Sub-millisecond regex and path normalization overhead; completely prevents costly remote VM reset cycles and wasted inference turns.
* **Cost & FinOps**: Saves Vertex AI token budget by preventing failed turns and restarting explorations from scratch.
* **Security & Reliability**: Zero blast radius. Eliminates the risk of model hallucinations triggering remote firewall bans.
* **Pros & Cons**:
  * Good, because it provides 100% deterministic guarantees against security lockouts and VM state resets.
  * Bad / Trade-off, because client-side state must dynamically track `.gitignore` contents as new directories are visited.

##### Option 1.2: System Prompt Natural Language Guardrails (REJECTED)
* **Description**: Relying strictly on negative constraints in `system_prompt.md` instructing the LLM never to access `/etc`, `/root`, `/proc/`, or `.gitignore` entries.
* **Data Engineering & Performance**: Adds token overhead to system instructions on every turn; high latency penalty if a ban wipes progress.
* **Cost & FinOps**: High financial risk due to wasted tokens when the VM resets and the agent must repeat discovery steps.
* **Security & Reliability**: Fragile and non-deterministic. LLMs frequently probe standard system paths (e.g., `cat /etc/passwd` or exploratory `find /`) when diagnosing unfamiliar environments.
* **Pros & Cons**:
  * Good, because it requires no client-side command parsing logic.
  * Bad, because probabilistic models cannot guarantee zero violations against strict anti-tamper security rules.

#### Consequences
* **Positive**: Complete immunity to lockout bans and VM state wipes during autonomous shell exploration.
* **Negative / Trade-offs**: Requires building and testing path normalization and pattern matching logic in `services/safety_guardrail.py`.
* **Confirmation**: Unit tests verifying that forbidden paths (`/etc`, `/root`, `/proc/`, `../../etc`, `.gitignore` patterns) are blocked before sending HTTP requests.

---

### Decision 2: Shell API Error & Rate-Limit Handling

#### Problem & Drivers
The Shell API (`$AIDEVS_API_SHELL`) is subject to network latency, rate limits (429), transient server hiccups (503), and lockouts with dynamic countdowns. The agent execution loop must gracefully handle these interruptions without crashing or losing state.

#### Considered Options

##### Option 2.1: Automatic Backoff & Retry Interceptor via Tenacity (ACCEPTED)
* **Description**: An HTTP client wrapper in `services/shell_service.py` powered by `tenacity==9.0.0` (using `@retry`, `wait_exponential` for HTTP 429/503 errors, and custom sleep handling for ban countdown payloads). If a ban response is received, the client extracts the remaining ban duration, logs a warning, sleeps for `seconds + 1`, and safely retries.
* **Data Engineering & Performance**: Transparent resilience at the transport layer; keeps context windows clean of raw network error dumps and telemetry coherent.
* **Cost & FinOps**: Minimal compute cost; sleeping during cooldown avoids burning inference tokens on repeated failed requests.
* **Security & Reliability**: Robust fault tolerance against transient infrastructure downtime.
* **Pros & Cons**:
  * Good, because it separates transport-level resilience from LLM cognitive reasoning, preventing hallucinations during outages.
  * Bad / Trade-off, because synchronous/async sleep temporarily pauses task execution during cooldown.

##### Option 2.2: Bubble Errors Directly as Tool Feedback to LLM (REJECTED)
* **Description**: Returning raw HTTP errors and ban notifications directly as `ToolMessage` feedback, leaving the model to decide whether to wait, retry, or reboot.
* **Data Engineering & Performance**: Clutters the LLM context window with repetitive HTTP error traces and non-productive conversational steps.
* **Cost & FinOps**: Burns unnecessary token budget by having the LLM generate "I will wait 10 seconds" thoughts and sleep tool calls.
* **Security & Reliability**: Unpredictable model behavior; under repetitive error stimuli, models frequently loop or issue erratic reset commands.
* **Pros & Cons**:
  * Good, because the model maintains full raw visibility into HTTP status codes.
  * Bad, because transient network retries and cooldown waits are infrastructure concerns that should not burden cognitive context.

#### Consequences
* **Positive**: Seamless handling of transient API issues, rate limits, and security cooldowns without agent loop failure.
* **Negative / Trade-offs**: Requires building retry middleware in `services/shell_service.py`.
* **Confirmation**: Mock integration tests simulating 429, 503, and ban cooldown payloads to verify backoff and sleep behavior.

---

### Decision 3: Agent Execution Strategy & Frameworks

#### Problem & Drivers
The task requires inspecting a non-standard Linux environment, discovering passwords across multiple files, and modifying `settings.ini`. The approach must handle non-deterministic discovery while fulfilling course requirements for dual-framework mastery (LangChain and Google ADK).

#### Considered Options

##### Option 3.1: Autonomous ReAct Loop with Dual Framework Parity (LangChain 1.2.15 & Google ADK 1.33.0) (ACCEPTED)
* **Description**: Modular agent architecture featuring interchangeable runners:
  - **LangChain Backend** (`agents/langchain_agent.py`): LangChain 1.2.15 `create_agent` with `handle_tool_error=True` on all tools.
  - **Google ADK Backend** (`agents/adk_agent.py`): Google Agent Development Kit (`google-adk==1.33.0`) using `google.adk.Agent` and `Runner` with `InMemorySessionService`.
  Both backends share contract-first tools (`execute_shell_command`, `reboot_vm`, `submit_confirmation`), schemas, and BigQuery telemetry.
* **Data Engineering & Performance**: High modularity with shared Pydantic schemas, streaming BigQuery audit callbacks, and structured tool definitions.
* **Cost & FinOps**: Free-tier compatible; lightweight session memory with zero heavy external database requirements.
* **Security & Reliability**: Tools run in a strictly scoped client container; contract-first schemas enforce input and output validation.
* **Pros & Cons**:
  * Good, because it satisfies Artur's educational requirements with 100% feature parity between LangChain and Google ADK.
  * Good, because autonomous function calling allows adaptive problem solving when encountering unfamiliar shell utilities.
  * Bad / Trade-off, because dual framework implementation requires maintaining two agent runner wrappers.

##### Option 3.2: Deterministic Hardcoded Discovery Script (REJECTED)
* **Description**: A fixed sequential Python script executing predefined commands (`cat`, `find`, `sed`) with regex matching.
* **Data Engineering & Performance**: Instantaneous execution (<2 seconds), zero token latency.
* **Cost & FinOps**: Zero LLM inference costs.
* **Security & Reliability**: Extremely brittle; the VM features a non-standard custom shell and file editing semantics that fail against hardcoded assumptions.
* **Pros & Cons**:
  * Good, because it has zero inference cost and deterministic execution.
  * Bad, because it lacks adaptability to non-standard shell semantics and provides no pedagogical value for agentic engineering.

#### Consequences
* **Positive**: Adaptive problem-solving capable of self-correcting upon unexpected shell output, combined with full dual-framework parity.
* **Negative / Trade-offs**: Codebase scaffolding includes both LangChain and Google ADK runner implementations.
* **Confirmation**: End-to-end execution verification using both `uv run python main.py --backend langchain` and `uv run python main.py --backend adk`.

---

### Decision 4: LLM Model & Reasoning Configuration

#### Problem & Drivers
Diagnosing non-standard shell utilities and reconfiguring `settings.ini` requires strong logical reasoning, structured tool adherence, and prompt context tracking while maintaining low latency and cost efficiency.

#### Considered Options

##### Option 4.1: Gemini 3.8 Flash (`thinking_level="low"`) on Vertex AI (ACCEPTED)
* **Description**: Google DeepMind's workhorse model (`gemini-3.8-flash`) hosted on Vertex AI (`location="global"`), utilizing `thinking_level="low"` to minimize latency while retaining the ability to escalate thinking if complex troubleshooting arises.
* **Data Engineering & Performance**: Sub-second time-to-first-token, high throughput, and native structured tool calling via Vertex AI.
* **Cost & FinOps**: Extremely cost-efficient token pricing; `low` thinking avoids token bloat while providing sufficient reasoning for shell diagnostics.
* **Security & Reliability**: Enterprise Vertex AI SLAs, global multi-region availability, and zero data retention for model training.
* **Pros & Cons**:
  * Good, because it complies with the course standard model baseline starting from S02E04.
  * Good, because it offers high-speed function calling with low token costs.
  * Bad / Trade-off, because complex non-standard shell troubleshooting might occasionally benefit from higher thinking settings.

##### Option 4.2: Claude 3.7 / 3.5 Sonnet via Anthropic SDK (REJECTED)
* **Description**: Direct Anthropic API integration as informally suggested in the lesson text notes.
* **Data Engineering & Performance**: High reasoning quality, but introduces non-GCP egress latency and fragmented SDK tooling.
* **Cost & FinOps**: Significantly higher per-token inference costs compared to Gemini 3.8 Flash on Vertex AI.
* **Security & Reliability**: Adds an external API boundary requiring separate API key management and billing outside Google Cloud.
* **Pros & Cons**:
  * Good, because Sonnet exhibits strong reasoning in unfamiliar command-line environments.
  * Bad, because it deviates from our standardized Vertex AI and GCP architectural baseline without architectural necessity.

#### Consequences
* **Positive**: Fast, cost-efficient, and enterprise-grade inference fully integrated into Vertex AI.
* **Negative / Trade-offs**: Thinking level parameter must be configurable in `config.py` to allow escalation if edge cases require it.
* **Confirmation**: Measuring token latency, tool-calling accuracy, and successful token retrieval during test runs.

---

## 4. Technical Baseline Divergence (GEMINI.md)
None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [Pre-Flight Agent Readiness Checklist](../../../docs/af-aidevs/patterns/agent-readiness-checklist.md)
  - [Gemini 3.8 Flash Developer Guide](../../../docs/vertex-ai/gemini-3.8-flash-guide.md)
