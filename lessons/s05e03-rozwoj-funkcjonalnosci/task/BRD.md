# Business Requirements Document (BRD) - S05E03: Remote Shell Access & Time Archive Investigation

## 1. Overview & Business Objectives

In the aftermath of the evacuation operations, the resistance led by Azazel is preparing to activate the time machine to alter the historical timeline and restore order to the world. Before the temporal jump can occur, the resistance must determine the exact time window, city, and geographical coordinates to intercept Rafał before his tragic demise.

The operators of the regime stored an extensive "time archive" (`wielkie archiwum czasu`) in a simple text log format on a dedicated remote Linux machine. The resistance has obtained shell access to this machine via an execution endpoint provided by Centrala.

The objective of the `shellaccess` task is to design an automated system capable of interactively querying and navigating the remote Linux environment, inspecting `/data` logs using standard UNIX utilities (`ls`, `find`, `grep`, `jq`, `awk`), identifying when and where Rafał's body was discovered, computing the target rendezvous date (exactly one day before the discovery), and executing a shell command that outputs the structured JSON rendezvous coordinates to claim the mission flag (`{FLG:...}`).

---

## 2. Functional Requirements

### 2.1 Remote Shell Execution Lifecycle (`shellaccess`)

All interactions with the remote host are mediated through Centrala's verification API endpoint (`$AIDEVS_API_VERIFY`):

1. **Command Dispatch Protocol:**
   - Every request is an HTTP POST containing `task: "shellaccess"` and an `answer` object with the shell command:
     ```json
     {
       "apikey": "...",
       "task": "shellaccess",
       "answer": {
         "cmd": "<linux-command>"
       }
     }
     ```
   - Centrala executes `<linux-command>` within the remote Linux environment and returns the command output (stdout / stderr) inside its response payload.

2. **Reconnaissance & File Discovery:**
   - Explore file system contents starting from `/data` and home directories (`ls -la /data`, `find /data -type f`, etc.).
   - Identify the file formats, log structures, compression (e.g. `.log`, `.txt`, `.tar.gz`, `.json`), and size of files in `/data`.
   - Safely sample and inspect headers/entries without overloading response buffers (e.g., using `head`, `wc -l`, `grep -m 10`).

3. **Dual Execution Scope (Agent vs. Developer REPL):**
   - **Autonomous Agent Scope (`--mode auto` / Cloud Run `POST /run`):** Strictly governed by the `CommandPolicyGate`, in-situ compound wrapper, proactive `cat` interceptor, and 4,000-character context truncation.
   - **Interactive Developer REPL (`--mode repl`):** **Direct Unrestricted Passthrough.** Artur has direct raw access to the machine. No allowlist/denylist restrictions, no mandatory compound wrappers, and no truncation unless explicitly configured. Whatever Artur types is dispatched directly to Centrala.

4. **Pure Shell Execution for Agent (No Interpreters / No Script Files):**
   - The autonomous agent must strictly use native shell commands and standard Linux utilities (`ls`, `find`, `grep`, `awk`, `cut`, `sed`, `sort`, `uniq`, `head`, `tail`, `wc`, `stat`, `date`, `echo`, `jq`).
   - Absolute prohibition against the agent writing or invoking scripts in Python, Node, Perl, Ruby, PHP, or writing ad-hoc script files to disk.

5. **Sudo-Style Command Policy Gate (`CommandPolicyGate` for Agent):**
   - Enforce an enterprise-grade command validation gate inspecting agent commands before dispatch:
     - **Allowed Command Set:** `ls`, `find`, `grep`, `awk`, `cut`, `sed`, `sort`, `uniq`, `head`, `tail`, `wc`, `stat`, `date`, `echo`, `jq`, `pwd`, `file`, `which`.
     - **Blacklisted Binaries:** `python`, `python3`, `node`, `ruby`, `perl`, `php`, `zsh`, `bash -c`, `sh -c`, `csh`, `tcsh`, `fish`, `rm`, `mv`, `chmod`, `chown`, `dd`, `mkfs`, `kill`, `pkill`, `reboot`, `shutdown`, `wget`, `curl`, `nc`, fork-bombs (`:(){ :|:& };:`).

6. **In-Situ Remote Execution Wrapper & 4,000-Character Output Cap (Agent):**
   - **Strict Buffer Limit:** Remote command output returned to the LLM context is capped at **4,000 characters** (~1,000 tokens).
   - **Atomic In-Situ Wrapper:** To prevent multi-megabyte network egress and HTTP timeouts, exploratory agent commands are transparently wrapped into a single compound execution:
     ```bash
     TMP="/tmp/_af_aidevs_out_$$"; (<cmd>) > "$TMP" 2>&1; SZ=$(wc -c < "$TMP" 2>/dev/null || echo 0); if [ "$SZ" -gt 4000 ]; then head -c 4000 "$TMP"; echo -e "\n\n[OUTPUT TRUNCATED: $SZ bytes. Use grep or head to narrow down]"; else cat "$TMP"; fi
     ```
   - **Proactive `cat` Interceptor:** If an agent command matches `cat <filepath>`, the tool performs pre-flight inspection and blocks direct reads if the target file is $\ge 4,000$ bytes, enforcing `head` or `grep`.

7. **Information Extraction & Entity Resolution:**
   - Locate log entries or reports regarding **Rafał** (e.g., searching for "Rafał", "Rafal", discovery of body, incident reports, autopsies, or coroner records).
   - Extract the exact discovery date of Rafał's body (`YYYY-MM-DD`).
   - Extract the city where Rafał was discovered.
   - Extract the precise geographical coordinates of the discovery site:
     - `latitude` (float)
     - `longitude` (float)

8. **Target Rendezvous Date Calculation:**
   - **CRITICAL CONDITION:** The rendezvous date must be **exactly ONE DAY BEFORE** the day Rafał's body was found.
   - Formula: $\text{rendezvous\_date} = \text{discovery\_date} - 1\text{ day}$ (formatted strictly as `YYYY-MM-DD`).

9. **Final Output Emission:**
   - Execute a shell command that prints the final JSON payload directly to standard output:
     ```json
     {
       "date": "YYYY-MM-DD",
       "city": "nazwa miasta",
       "longitude": 10.000001,
       "latitude": 12.345678
     }
     ```
   - Dispatched cleanly via `echo '{"date":"...", ...}'` to Centrala.
   - When the remote command outputs the valid JSON structure matching the correct coordinates, date, and city, Centrala intercepts the output and returns the mission flag (`{FLG:...}`).

---

## 3. Decoded Lesson Hint (Wskazówka z lekcji)

The course notes contained an encoded base64 hint, decoded as follows:

> **Oryginalna wskazówka (po dekodowaniu Base64):**
> 
> *"Do odczytywania i generowania plików JSON możesz użyć narzędzia 'jq' zainstalowanego na serwerze. Niemal wszystkie potrzebne informacje można uzyskać także za pomocą polecenia 'grep'.*
> 
> *Poprawną odpowiedź możesz wyprodukować przez JSON, albo poskładać samodzielnie i wykonać:*
> 
> `echo '{"date":"2020-01-01","city":"nazwa miasta","longitude":10.000001,"latitude":12.345678}'`
> 
> *UWAGA! Pamiętaj, że musisz zwrócić datę DZIEŃ PRZED znalezieniem ciała Rafała."*

---

## 4. System & Token Constraints

- **Execution Runtime:** Google Cloud Run microservice (`cr-s05e03-shellaccess`) with CLI support:
  - `--mode auto`: Fully autonomous ReAct agent loop with full guardrails.
  - `--mode repl` / `--interactive`: Direct unrestricted interactive CLI terminal for Artur without guardrail blocks.
- **Cognitive Workhorse Model:** **Gemini 3.8 Flash** (`gemini-3.8-flash`) via Vertex AI (`vertexai=True`, `thinking_level="low"`).
- **Safety & Guardrail Limits (Autonomous Mode):**
  - Maximum iteration limit for the agent loop (default: 30 iterations) to avoid runaway executions or infinite shell loops.
  - Output truncation capped strictly at **4,000 characters** (~1,000 tokens).
  - Proactive `cat` interception and in-situ `/tmp` compound truncation preventing memory/context saturation on large files.
- **Session State & Telemetry:**
  - Stateless Cloud Run container architecture.
  - BigQuery audit logging in dataset `s05e03`, table `audit`.
  - Full trace observability via LangSmith (`$LANGSMITH_PROJECT`).
  - Zero-pollution logging: truncate dynamic tool outputs and error messages in logs and traces.

---

## 5. Data Inputs & External Resources

All external endpoints and credentials must be injected exclusively via environment variables:

| Resource Description | Environment Variable | Usage in Service |
| :--- | :--- | :--- |
| Centrala Verification API | `$AIDEVS_API_VERIFY` | HTTP endpoint executing remote commands and verifying the task |
| AI_Devs Personal API Key | `$AIDEVS_API_KEY` | Authenticates all requests sent to Centrala |
| BigQuery Project / Dataset | `$GOOGLE_CLOUD_PROJECT` / `$BQ_DATASET` | Audit telemetry logging (`af-aidevs.s05e03.audit`) |
| LangSmith Observability | `$LANGSMITH_API_KEY` | Distributed LLM call tracing |
| LangSmith Project | `$LANGSMITH_PROJECT` | Tracing namespace (`af-aidevs`) |

---

## 6. API Integration Schemas

### 6.1 Remote Shell Execution Request
**POST** `$AIDEVS_API_VERIFY`
```json
{
  "apikey": "your-api-key",
  "task": "shellaccess",
  "answer": {
    "cmd": "ls -la /data"
  }
}
```

### 6.2 Centrala Responses
- **Intermediate Command Output Response:**
  ```json
  {
    "code": 0,
    "message": "output from remote command execution..."
  }
  ```
- **Error / Invalid Command Response:**
  ```json
  {
    "code": -1,
    "message": "Error description or command failure..."
  }
  ```
- **Mission Accomplished Response (Course Flag):**
  ```json
  {
    "code": 0,
    "message": "{FLG:...}"
  }
  ```

---

## 7. Acceptance & Verification Criteria

1. **Automated Remote Navigation:** The service autonomously executes exploratory Linux commands (`ls`, `find`, `grep`, `jq`) on the remote server via `$AIDEVS_API_VERIFY`.
2. **Buffer Protection & In-Situ Wrapper (Agent):** Enforces a strict 4,000-character stdout cap and executes agent commands wrapped with in-situ `/tmp` size inspection (`/tmp/_af_aidevs_out_$$`), protecting network egress and LLM context without destructive `rm` commands.
3. **Sudo-Style Command Policy Gate (Agent):** Validates agent commands against an allowlist and strictly blocks blacklisted binaries (`zsh`, `python`, `node`, `rm`, etc.).
4. **Pure Shell Execution (Agent):** Prompt enforces strict shell-only commands, forbidding ad-hoc scripts.
5. **Direct Passthrough REPL:** Artur's `--mode repl` bypasses all agent restrictions, providing direct, raw command execution to the remote Linux machine.
6. **Entity Discovery Accuracy:** Correctly parses the logs in `/data` to extract Rafał's discovery date, city, and geographical coordinates (`latitude`, `longitude`).
7. **Temporal Calculation Integrity:** Deterministically computes the rendezvous date as strictly one day before the discovery date (`date - 1 day`).
8. **Valid Terminal Output Formatting:** Dispatches a shell command that outputs the target JSON schema (`date`, `city`, `longitude`, `latitude`) to standard output.
9. **Flag Retrieval:** Successfully receives and captures the `{FLG:...}` token from Centrala.
10. **Dual-Mode CLI Operation:** Supports autonomous execution (`--mode auto`) and interactive terminal exploration (`--mode repl`).
11. **Code Quality & Architecture Standards:** Passes all 5 pre-flight quality gates (`ruff check`, `ruff format`, `mypy`, `pytest`, Secret Manager alignment), adheres to `GEMINI.md` baseline standards, and persists execution traces in LangSmith and BigQuery audit logs.
