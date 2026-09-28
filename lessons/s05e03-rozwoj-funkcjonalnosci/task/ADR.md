<!-- Compound Architectural Decision Record (MADR Compound) -->
<!-- Combines MADR 4.0 clarity with Google Design Doc architectural rigor -->

---
status: "accepted"
date: 2026-09-27
decision-makers: Artur
consulted: Joi
---

# Architecture Decision Record: S05E03 Remote Shell Access & Time Archive Investigation

## 1. Context

The resistance forces under Azazel require the exact rendezvous coordinates and time window to intercept Rafał before his death, enabling the calibration of the time machine. Historical records are preserved on a remote Linux server within `/data` as plain text logs. Shell execution is exposed through an HTTP dispatch gateway at Centrala (`$AIDEVS_API_VERIFY`), returning stdout/stderr per executed command. To achieve mission verification without overloading context windows, running into HTTP timeouts, or polluting LLM context with multi-megabyte log files, the system requires an architecture balancing autonomous agentic exploration, direct interactive developer diagnostics, client-side buffer guardrails, enterprise-grade command authorization (`CommandPolicyGate`), and deterministic verification gates.

## 2. Decision Summary (Executive Overview)

| # | Problem Statement | Chosen Option (Accepted) | Rationale |
|---|-------------------|--------------------------|-----------|
| 1 | Exploration & Execution Architecture | Dual-Mode Engine (Autonomous ReAct + Direct Passthrough CLI REPL) | Provides complete autonomous execution for Cloud Run serverless endpoints while giving Artur direct, raw, unrestricted shell access in interactive REPL mode. |
| 2 | Command Safety & Security Gate | Sudo-Style `CommandPolicyGate` for Agent | Governs autonomous agent commands with strict allowlists, blocking destructive binaries, script interpreters (`python`, `zsh`), while exempting human REPL execution. |
| 3 | Remote Egress & Output Protection | In-Situ Atomic Execution Wrapper & Strict 4,000-Char Cap | Eliminates network egress saturation and HTTP timeouts by executing an atomic `/tmp/_af_aidevs_out_$$` size check and `head -c 4000` truncation directly on the remote Linux host for agent commands without `rm`. |
| 4 | Rendezvous Calculation & Output Gate | Local Pydantic Verification Gate | Deterministically validates coordinates and calculates `discovery_date - 1 day` in Python before generating and executing the final `echo '{"date":...}'` payload. |
| 5 | Post-Deployment Shell Dispatch Evolution | Direct UNIX Command Dispatch with Client-Side 4 kB Envelope (Replaces In-Situ Wrapper) | Remote sandbox rejects compound subshell wrappers (`TMP=...`, `$SZ`, `if [...]`) with `HTTP 403 Forbidden` (`Access denied. Permissions exceeded.`). Dispatches clean UNIX binaries directly to Centrala while extracting `output` and enforcing context envelopes locally in Python. |

---

## 3. Detailed Decisions & Trade-Offs

### Decision 1: Exploration & Execution Architecture

#### Problem & Drivers
The system needs to explore an unknown directory hierarchy under `/data`, identify relevant log files, search for mentions of Rafał, and extract entity metadata. The solution must run autonomously as a production-grade Cloud Run microservice (`POST /run`), while simultaneously offering an intuitive, direct, unrestricted debugging shell for Artur's hands-on engineering inspection and prototyping.

#### Considered Options

##### Option 1.1: Dual-Mode Engine: Autonomous ReAct Agent + Direct Passthrough CLI REPL (ACCEPTED)
* **Description**: Implement a modular architecture with two distinct operational scopes in `main.py`:
  1. `--mode auto` (or Cloud Run `POST /run`): An autonomous ReAct agent loop powered by Gemini 3.8 Flash that inspects directory trees, formulates search queries, extracts parameters, and verifies answers autonomously under strict safety guardrails.
  2. `--mode repl`: An interactive CLI session allowing Artur **direct, unrestricted passthrough access** to the remote server. Artur is exempt from the `CommandPolicyGate`, exempt from the in-situ wrapper, and free to dispatch raw commands directly to Centrala.
* **Data Engineering & Performance**: Direct REPL passthrough adds zero overhead and gives Artur pure root-level visibility. Autonomous ReAct agent minimizes cognitive latency by chaining targeted Unix commands.
* **Cost & FinOps**: Zero LLM token consumption during REPL mode. Autonomous ReAct loop runs capped at 30 iterations on Gemini 3.8 Flash (`thinking_level="low"`).
* **Security & Reliability**: Dual-mode decoupling ensures production Cloud Run microservices remain 100% guarded and stateless, while Artur possesses absolute administrative control locally.
* **Pros & Cons**:
  * Good, because it provides Artur with complete, unhindered terminal access to the remote machine.
  * Good, because the automated agent remains strictly constrained by safety policies.
  * Bad / Trade-off, because it requires maintaining two execution paths (raw passthrough vs. policy-governed).

##### Option 1.2: Enforce Guardrails Uniformly Across REPL and Agent (REJECTED)
* **Description**: Apply the same `CommandPolicyGate` and in-situ wrapper to both the agent and Artur's manual REPL session.
* **Data Engineering & Performance**: Inhibits Artur's ability to run custom scripts, pipes, or arbitrary diagnostic commands during manual reconnaissance.
* **Cost & FinOps**: No difference.
* **Security & Reliability**: Unnecessary friction for the human engineer.
* **Pros & Cons**:
  * Good, because single execution path.
  * Bad / Trade-off, because it frustrates the human developer by restricting his natural shell exploration.

#### Consequences
* **Positive**: Absolute freedom for Artur in REPL mode, absolute safety for the AI agent in autonomous mode.
* **Negative / Trade-offs**: Two distinct shell dispatch methods in `main.py` and `shell_tool.py`.
* **Confirmation**: Verified via CLI execution tests for `--mode repl` (raw dispatch) and `--mode auto` (policy-governed).

---

### Decision 2: Command Safety & Security Gate (Autonomous Agent Only)

#### Problem & Drivers
Granting an LLM agent unconstrained shell access risks destructive accidental commands (`rm`, `chmod`), shell-escape loops, or attempts to write ad-hoc Python/Perl scripts to disk that fail due to missing dependencies. The agent must be constrained to safe, read-only UNIX diagnostics.

#### Considered Options

##### Option 2.1: Sudo-Style `CommandPolicyGate` & Pure Shell Only for Agent (ACCEPTED)
* **Description**: Implement a pre-execution command validation interceptor in `shell_tool.py` governing all agent invocations:
  1. **Strict Command Allowlist (`Cmnd_Alias` equivalent):** Permitted binaries are strictly read-only diagnostics and filters: `ls`, `find`, `grep`, `awk`, `cut`, `sed`, `sort`, `uniq`, `head`, `tail`, `wc`, `stat`, `date`, `echo`, `jq`, `pwd`, `file`, `which`.
  2. **Blacklisted Binaries & Shell Escapes:** Strictly block `python`, `python3`, `node`, `ruby`, `perl`, `php`, `zsh`, `bash -c`, `sh -c`, `csh`, `tcsh`, `fish`, `rm`, `mv`, `chmod`, `chown`, `dd`, `mkfs`, `kill`, `pkill`, `reboot`, `shutdown`, `wget`, `curl`, `nc`, and fork-bombs (`:(){ :|:& };:`).
  3. **Prompt Hardening:** Explicitly instruct the model to use pure shell utilities only, forbidding script creation or interpreter execution.
  4. **REPL Exemption:** The interactive CLI REPL used by Artur completely bypasses this gate.
* **Data Engineering & Performance**: Zero execution failure due to missing python packages or filesystem file-drop clutter.
* **Cost & FinOps**: Prevents wasted agent iterations caused by attempting to debug failing Python scripts on minimal containers.
* **Security & Reliability**: Eliminates blast radius of destructive file commands or unauthorized shell escapes for autonomous loops.
* **Pros & Cons**:
  * Good, because it enforces standard enterprise Big Data sudoers security principles for AI agents.
  * Good, because it preserves Artur's unrestricted freedom in REPL mode.
  * Bad / Trade-off, because any non-whitelisted binary for the agent requires explicit evaluation in the policy engine.

##### Option 2.2: Free-Form Shell Execution for Agent (REJECTED)
* **Description**: Allow the agent to run arbitrary commands, including installing Python packages or creating custom script files.
* **Data Engineering & Performance**: High risk of runtime failures on minimal containers lacking Python, pip, or dev tools.
* **Cost & FinOps**: High token waste attempting to debug environmental issues.
* **Security & Reliability**: Severe blast radius on remote host.
* **Pros & Cons**:
  * Good, because no filtering code required.
  * Bad / Trade-off, because it violates least-privilege security and causes frequent agent derailment.

#### Consequences
* **Positive**: Absolute safety for autonomous loops without restricting Artur's manual workflow.
* **Negative / Trade-offs**: Agent commands must be parsed by `CommandPolicyGate` before execution.
* **Confirmation**: Unit tests verifying that blacklisted commands (`python`, `zsh`, `rm`) are blocked for the agent.

---

### Decision 3: Remote Egress & Output Protection

#### Problem & Drivers
The lesson notes emphasize that the "time archive" is a large text file on a fast machine. Reading large files via unconstrained `cat` could return hundreds of megabytes over HTTP, saturating network buffers, causing HTTP timeouts, and overwhelming LLM context windows. Truncating solely in Python on our Cloud Run service still forces Centrala to serialize and transfer megabytes over the wire.

#### Considered Options

##### Option 3.1: In-Situ Atomic Execution Wrapper & Strict 4,000-Char Cap (ACCEPTED)
* **Description**: Implement a dual-layer output protection architecture for agent commands:
  1. **In-Situ Remote Execution Wrapper:** Exploratory agent commands are transparently wrapped before dispatch into an atomic compound bash execution on the remote host without destructive cleanup:
     ```bash
     TMP="/tmp/_af_aidevs_out_$$"; (<cmd>) > "$TMP" 2>&1; SZ=$(wc -c < "$TMP" 2>/dev/null || echo 0); if [ "$SZ" -gt 4000 ]; then head -c 4000 "$TMP"; echo -e "\n\n[OUTPUT TRUNCATED: $SZ bytes. Use grep or head to narrow down]"; else cat "$TMP"; fi
     ```
  2. **Safe Ephemeral Buffer (`/tmp/_af_aidevs_out_$$`):** Uses PID suffix in `/tmp` without issuing dangerous `rm -f` commands, letting Linux OS ephemeral storage rules handle rotation.
  3. **Zero Network Egress Bloat:** If a command generates 50 MB, the remote Linux kernel trims it to 4 kB *before* sending the HTTP response, preventing network timeouts and payload limits.
  4. **Proactive `cat` Interceptor:** If an agent command begins with `cat <filepath>`, the tool performs pre-flight inspection and blocks direct reads if the target file is $\ge 4,000$ bytes, enforcing `head` or `grep`.
  5. **Strict 4,000-Character Context Cap:** ~1,000 tokens per turn in Gemini 3.8 Flash, providing rich context (25–35 log lines) without context window bloat.
* **Data Engineering & Performance**: Remote machine executes filtering at native kernel speeds, transferring only relevant data over the wire.
* **Cost & FinOps**: Drastically reduces LLM context token usage, keeping prompt sizes lean and predictable.
* **Security & Reliability**: Eliminates HTTP 504 gateway timeouts, out-of-memory crashes, and risks associated with issuing `rm` commands.
* **Pros & Cons**:
  * Good, because it prevents multi-megabyte payload dumps *at the source* on the remote machine.
  * Good, because avoiding `rm` eliminates risks of accidental file deletion under unexpected paths.
  * Good, because 4,000 characters provides comfortable room for structured JSON and log snippets.
  * Good, because single roundtrip execution eliminates latency overhead.
  * Bad / Trade-off, because compound bash wrappers require careful quoting of subshell commands.

##### Option 3.2: Client-Side Only Truncation at 2,000 Characters (REJECTED)
* **Description**: Allow commands to run unwrapped and truncate in Python after HTTP receipt, with a 2,000-character cap.
* **Data Engineering & Performance**: Does not protect network egress; Centrala can still time out sending large payloads. 2,000 characters is too cramped (10–12 lines), cutting off JSON objects mid-way.
* **Cost & FinOps**: Wastes egress/ingress bandwidth.
* **Security & Reliability**: High risk of HTTP request timeouts on Centrala's end.
* **Pros & Cons**:
  * Good, because simpler implementation without bash wrapper.
  * Bad / Trade-off, because it fails to protect the network pipe and cuts off crucial log lines prematurely.

#### Consequences
* **Positive**: Absolute protection of LLM context window, HTTP connection stability, and zero risk of accidental `rm` deletion.
* **Negative / Trade-offs**: Command interceptor and wrapper must handle subshell quoting reliably.
* **Confirmation**: Unit tests verifying command wrapping, output truncation, and `cat` interception.

---

### Decision 4: Rendezvous Calculation & Output Gate

#### Problem & Drivers
The final response requires extracting Rafał's body discovery date, city, and geographical coordinates, and outputting a JSON payload where the date is **strictly ONE DAY BEFORE** discovery. Leaving date arithmetic and float validation entirely to unconstrained LLM shell commands introduces risk of arithmetic hallucination (e.g. leap years, month boundaries) and syntax errors.

#### Considered Options

##### Option 4.1: Local Pydantic Verification Gate (ACCEPTED)
* **Description**: When the agent locates the discovery log entry, it extracts the raw facts into a structured tool call or schema:
  - `discovery_date: str` (`YYYY-MM-DD`)
  - `city: str`
  - `latitude: float`
  - `longitude: float`
  Python deterministically parses the date using `datetime.date`, subtracts `datetime.timedelta(days=1)`, validates the coordinate ranges, and formats the exact shell command:
  `echo '{"date":"YYYY-MM-DD","city":"...","longitude":...,"latitude":...}'`.
  The command is dispatched cleanly without wrapping to Centrala, capturing the flag response directly.
* **Data Engineering & Performance**: Deterministic calendar math in Python eliminates date arithmetic hallucinations.
* **Cost & FinOps**: Prevents wasted iterations due to subtle date calculation errors.
* **Security & Reliability**: Pydantic models guarantee strict type validation (`float`, valid ISO-8601 date format) before submitting the final verification command.
* **Pros & Cons**:
  * Good, because calendar calculations (e.g. 2024-03-01 minus 1 day = 2024-02-29) are mathematically guaranteed.
  * Good, because coordinate types and non-empty string checks are strictly validated.
  * Bad / Trade-off, because it introduces a dedicated extraction/validation step before final emission.

##### Option 4.2: Direct Unconstrained LLM Shell Emission (REJECTED)
* **Description**: Let the LLM directly execute `echo '{"date": ...}'` on the remote server using its own internal calculation.
* **Data Engineering & Performance**: No intermediate Python step.
* **Cost & FinOps**: Risk of repeated failed attempts if LLM hallucinates date subtraction across month boundaries.
* **Security & Reliability**: Subject to subtle LLM calculation mistakes.
* **Pros & Cons**:
  * Good, because agent operates completely free-form.
  * Bad / Trade-off, because LLMs occasionally stumble on calendar arithmetic across month/year boundaries.

#### Consequences
* **Positive**: Guaranteed temporal math accuracy and strict schema validation.
* **Negative / Trade-offs**: Minimal added code for date parsing in Python.
* **Confirmation**: Unit tests verifying date subtraction edge cases (e.g., month start, leap year).

---

### Decision 5: Post-Deployment Evolution: Direct UNIX Command Dispatch vs. Remote Shell In-Situ Wrapper (HTTP 403 / "Permissions Exceeded")

#### Problem & Post-Deployment Discovery
During initial live deployment verification on Google Cloud Run and Centrala integration testing:
1. **Remote Sandbox Security Rejections (`HTTP 403 Forbidden`):** The remote sandbox at Centrala (`$AIDEVS_API_VERIFY`) enforces its own AST/shell policy interceptor. When agent commands were wrapped with our Decision 3 in-situ bash compound script (`TMP="/tmp/_af_aidevs_out_$$"; (...) > "$TMP" && if [...]`), Centrala immediately rejected all invocations with:
   `HTTP 403 Forbidden: {"code": -1, "message": "Access denied. Permissions exceeded."}`
   The remote sandbox forbids shell variable assignments (`TMP=...`), subshell expansions (`$$`), and multi-line conditional logic (`if [ "$SZ" -gt 4000 ]`).
2. **Response Field Separation (`output` vs. `message`):** When executing standard UNIX binaries directly (e.g. `ls -la /data`), Centrala returns `HTTP 200 OK` with JSON structure:
   ```json
   {
     "code": 100,
     "message": "Command executed.",
     "output": "total 884\n-rw-r--r-- ... gps.json\n-rw-r--r-- ... locations.json\n-rw-r--r-- ... time_logs.csv\n"
   }
   ```
   Centrala isolates the execution acknowledgment in `message` while persisting the actual command standard output in `output`. Reading solely `message` produced misleading `"Command executed."` strings without stdout text.

#### Considered Options

##### Option 5.1: Direct UNIX Command Dispatch with Client-Side 4 kB Envelope (ACCEPTED)
* **Description**:
  1. **Direct Clean Execution:** Discard the remote bash compound wrapper. Dispatch the agent's validated command (e.g. `ls -la /data`, `head -n 25 /data/locations.json`, `grep -i "rafal" /data/time_logs.csv`) directly to Centrala without injected subshell wrappers or variable assignments.
  2. **Canonical Output Parsing:** Update `CentralaService` and `schemas.py` to prioritize `data.get("output")` over `data.get("message")`, guaranteeing that stdout is seamlessly exposed to both the AI agent and the developer REPL.
  3. **Client-Side Context Envelope:** Retain the 4,000-character safety envelope by truncating large command outputs in Python before returning to the LLM context:
     ```python
     raw_output = resp.message or ""
     if len(raw_output) > config.OUTPUT_CHAR_LIMIT:
         raw_output = raw_output[:config.OUTPUT_CHAR_LIMIT] + f"\n\n[CLIENT TRUNCATED AT {config.OUTPUT_CHAR_LIMIT} CHARS]"
     ```
  4. **Proactive `cat` File Size Inspection:** Preserve `_check_file_size` using `stat -c %s "<file>"`, which runs cleanly on Centrala and returns the exact byte count, blocking direct `cat` invocations on multi-hundred kilobyte files (e.g. `gps.json` at 497 kB, `time_logs.csv` at 376 kB).
* **Data Engineering & Performance**: Zero subshell syntax rejection. Clean single-command execution at native speeds with sub-second response times.
* **Cost & FinOps**: 4,000-character client truncation protects Gemini 3.8 Flash token budgets from context inflation.
* **Security & Reliability**: 100% compliance with Centrala's remote sandbox policy while preserving the local `CommandPolicyGate` allowlist.
* **Pros & Cons**:
  * Good, because it resolves all `HTTP 403 Forbidden` permission errors from Centrala.
  * Good, because stdout output is fully captured and formatted for the agent.
  * Good, because proactive `stat` checks prevent runaway reads of 500 kB log files.
  * Bad / Trade-off, because if an unconstrained command is run without filtering (e.g. unconstrained `grep`), the full output travels over the wire before client-side truncation.

##### Option 5.2: Attempt Obfuscating or Escaping the Remote Wrapper (REJECTED)
* **Description**: Try alternative remote bash syntaxes (e.g. piping to `head` in every command: `<cmd> | head -c 4000`).
* **Data Engineering & Performance**: Brittle. Chaining pipes interferes with commands that already use pipes (`grep | awk | head`).
* **Security & Reliability**: Still risks triggering Centrala's sandbox heuristic filters.
* **Pros & Cons**:
  * Bad, because it causes fragile syntax bugs across complex multi-pipe queries.

#### Consequences
* **Positive**: Full interoperability with Centrala's remote execution sandbox, complete stdout visibility in both REPL and autonomous ReAct agent, and zero token waste.
* **Negative / Trade-offs**: Egress protection shifts from in-situ remote truncation to client-side truncation + proactive file size pre-flight guards.
* **Confirmation**: Verified via live Centrala execution returning `code: 100` and actual directory listings (`locations.json`, `gps.json`, `time_logs.csv`).

---

## 4. Technical Baseline Divergence (GEMINI.md)

None

---

## 5. More Information

* **Related Documents**:
  - [BRD.md](BRD.md)
  - [s05e03-rozwoj-funkcjonalnosci-1775596919.md](../s05e03-rozwoj-funkcjonalnosci-1775596919.md)
