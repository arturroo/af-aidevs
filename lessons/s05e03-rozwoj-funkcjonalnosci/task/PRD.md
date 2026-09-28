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

# Technical Product Requirements Document: S05E03 Remote Shell Access & Time Archive Investigation (`cr-s05e03-shellaccess`)

## Context and Scope

In the aftermath of the evacuation operations, the resistance forces led by Azazel are preparing to activate the time machine to alter the historical timeline and restore order to the world. Before the temporal jump can occur, the resistance must determine the exact time window, city, and geographical coordinates to intercept Rafał before his tragic death.

The operators of the regime stored an extensive "time archive" (`wielkie archiwum czasu`) in plain text log format on a dedicated remote Linux machine. The resistance has obtained remote shell execution access to this machine via Centrala's verification endpoint (`$AIDEVS_API_VERIFY`), which executes commands and returns stdout/stderr in turn-based HTTP responses.

This document defines the production design, schemas, guardrail policies, agent orchestration, and CLI interfaces for the `cr-s05e03-shellaccess` microservice. All architectural choices have been finalized and accepted in [ADR.md](ADR.md) following the foundational requirements in [BRD.md](BRD.md).

---

## Goals and Non-Goals

### Goals
* **Automated & Interactive Remote Shell Access:** Build a robust client and orchestration layer to execute arbitrary Linux commands on the remote server via Centrala's `$AIDEVS_API_VERIFY` endpoint under task `shellaccess`.
* **Dual-Mode Execution Architecture:** Support two distinct operational modes in `main.py`:
  1. `--mode auto` (or Cloud Run `POST /run`): An autonomous ReAct agent loop powered by **Gemini 3.8 Flash** (`gemini-3.8-flash`) that explores directory trees, formulates search queries, extracts parameters, and verifies answers autonomously under strict safety policies.
  2. `--mode repl`: An interactive CLI terminal for Artur with **direct, unrestricted passthrough access** to the remote Linux machine, free from agent command policies and wrappers.
* **Sudo-Style Command Policy Gate (`CommandPolicyGate` for Agent):** Enforce enterprise Big Data sudoers security principles on autonomous agent operations:
  - Whitelist diagnostics and text processing utilities: `ls`, `find`, `grep`, `awk`, `cut`, `sed`, `sort`, `uniq`, `head`, `tail`, `wc`, `stat`, `date`, `echo`, `jq`, `pwd`, `file`, `which`.
  - Strictly block blacklisted binaries and shell escapes: `python`, `python3`, `node`, `ruby`, `perl`, `php`, `zsh`, `bash -c`, `sh -c`, `csh`, `tcsh`, `fish`, `rm`, `mv`, `chmod`, `chown`, `dd`, `mkfs`, `kill`, `pkill`, `reboot`, `shutdown`, `wget`, `curl`, `nc`, and fork-bombs.
* **Pure Shell Execution Only (Agent):** Explicitly instruct the agent to utilize standard shell one-liners only, prohibiting the creation or execution of scripts in Python or any other interpreted language.
* **In-Situ Atomic Remote Execution Wrapper (Agent):** Wrap exploratory agent commands into a compound bash one-liner executing on the remote host: redirects `stdout` and `stderr` to `/tmp/_af_aidevs_out_$$`, checks size via `wc -c`, and truncates via `head -c 4000` *before* transmission over HTTP, eliminating network egress bloat without `rm`.
* **Proactive `cat` Interceptor & Safety Guardrail (Agent):** Intercept agent commands matching `cat <filepath>`, perform a pre-flight file size check, and block execution if the target file is $\ge 4,000$ bytes, returning actionable guidance to use `head -n 25`, `grep`, or `jq`.
* **Strict 4,000-Character Context Cap (Agent):** Hard-truncate any agent output at **4,000 characters** (~1,000 tokens) to ensure rich log context without context window bloat.
* **System Prompt Embedding of Decoded Lesson Hint:** Embed the exact decoded course hint into the agent's system message to prime the model for `jq`, `grep`, and the critical temporal rule.
* **Local Pydantic Verification Gate:** Deterministically validate extracted coordinates (`latitude`, `longitude`) and calculate the rendezvous date as strictly **one day before discovery** (`discovery_date - 1 day`) in Python before generating and dispatching the final `echo '{"date":...}'` command.
* **Mission Flag Capture:** Capture and return the course flag (`{FLG:...}`) upon Centrala's acceptance of the rendezvous JSON output.
* **Zero-Pollution Observability:** Stream sanitized audit logs to BigQuery dataset `s05e03`, table `audit`, and detailed traces to LangSmith with truncated tool outputs.

### Non-Goals
* **Full SSH / PTY Terminal Emulation:** The remote server provides command execution via a synchronous HTTP request/response envelope; interactive pseudo-terminals (TTY/pty, ncurses, `top`, `vim`, interactive password prompts) are out of scope.
* **Mass Remote Log Ingestion to Vector DB:** Azazel's time archive is large; pulling hundreds of megabytes into an embedding database or remote workspace is deliberately excluded in favor of fast in-situ Linux tools (`grep`, `jq`).

---

## The Design

### System Overview

```
                                      ┌────────────────────────────────────────┐
                                      │       Centrala Verification API        │
                                      │         ($AIDEVS_API_VERIFY)           │
                                      └───────────────────┬────────────────────┘
                                                          │
                                                          │ HTTP POST {"task":"shellaccess","answer":{"cmd":"..."}}
                                                          ▼
                        ┌──────────────────────────────────────────────────────────────────┐
                        │             Cloud Run: cr-s05e03-shellaccess                     │
                        │                                                                  │
                        │  ┌────────────────────────────────────────────────────────────┐  │
                        │  │                        main.py                             │  │
                        │  │   - FastAPI endpoints: /health, /run                       │  │
                        │  │   - CLI Entrypoint: --mode auto | --mode repl              │  │
                        │  └──────────────┬──────────────────────────────┬──────────────┘  │
                        │                 │                              │                 │
                        │   (Mode: Auto)  │                              │  (Mode: REPL)   │
                        │                 ▼                              │  Direct Access  │
                        │  ┌─────────────────────────────┐               │                 │
                        │  │    ReAct Agent / Runner     │               │                 │
                        │  │  - LangChain / Google ADK   │               │                 │
                        │  │  - Max iterations: 30       │               │                 │
                        │  └──────────────┬──────────────┘               │                 │
                        │                 │                              │                 │
                        │                 │ Policy-Governed Tool         │ Raw Tool        │
                        │                 ▼                              ▼                 │
                        │             ┌─────────────────────┐    ┌─────────────────────┐   │
                        │             │  CommandPolicyGate  │    │ Direct Passthrough  │   │
                        │             │  - Sudo Allowlist   │    │  (Unrestricted CLI) │   │
                        │             │  - Blacklist (zsh..)│    └──────────┬──────────┘   │
                        │             │  - Proactive `cat`  │               │              │
                        │             └──────────┬──────────┘               │              │
                        │                        │ (Allowed)                │              │
                        │                        ▼                          │              │
                        │             ┌─────────────────────┐               │              │
                        │             │   In-Situ Wrapper   │               │              │
                        │             │ TMP=/tmp/_af_out_$$;│               │              │
                        │             │ SZ=$(wc -c < TMP);  │               │              │
                        │             │ if SZ>4000: head    │               │              │
                        │             └──────────┬──────────┘               │              │
                        │                        │                          │              │
                        │                        ▼                          ▼              │
                        │             ┌────────────────────────────────────────┐           │
                        │             │            CentralaService             │           │
                        │             │   - execute_shell_agent(cmd)           │           │
                        │             │   - execute_shell_raw(cmd)             │           │
                        │             └──────────────────┬─────────────────────┘           │
                        │                                │                                 │
                        │                                ▼                                 │
                        │             ┌─────────────────────────────────────┐              │
                        │             │      Local Verification Gate        │              │
                        │             │  - Validates RafałDiscoveryPayload  │              │
                        │             │  - rendezvous_date = date - 1 day   │              │
                        │             │  - Emits: echo '{"date":...}'       │              │
                        │             └──────────────────┬──────────────────┘              │
                        │                                │                                 │
                        └────────────────────────────────┼─────────────────────────────────┘
                                                         │
                                                         ▼
                                       ┌───────────────────────────────────┐
                                       │       Audit & Observability       │
                                       │  - BigQuery: s05e03.audit         │
                                       │  - LangSmith: $LANGSMITH_PROJECT  │
                                       └───────────────────────────────────┘
```

---

### API Design

#### HTTP Endpoints (FastAPI)

1. **`GET /health` & `GET /`**:
   - Status check and service readiness probe.
   - Response: `{"status": "ok", "service": "cr-s05e03-shellaccess"}`.

2. **`POST /run`**:
   - Canonical task execution endpoint.
   - Request Body:
     ```json
     {
       "backend": "langchain",
       "session_id": "optional-custom-session-id",
       "model": "gemini-3.8-flash",
       "max_iterations": 30,
       "thinking_level": "low"
     }
     ```
   - Response Body:
     ```json
     {
       "session_id": "...",
       "status": "completed",
       "flag": "{FLG:...}",
       "rendezvous": {
         "date": "2024-02-29",
         "city": "...",
         "longitude": 10.000001,
         "latitude": 12.345678
       },
       "total_turns": 6,
       "execution_time_seconds": 8.42
     }
     ```

#### CLI Interface (`run_cli`)
- Invocation:
  - `uv run python main.py --mode auto [--backend langchain|adk] [--model gemini-3.8-flash] [--max-iterations 30]`
  - `uv run python main.py --mode repl`: Launches Artur's interactive remote terminal session with **direct raw passthrough** to Centrala.

---

### Data Model / Storage

#### Pydantic Schemas (`schemas.py`)

```python
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field


class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Agent backend orchestration framework",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier for audit tracing and workspace isolation",
        examples=["session-s05e03-abc1234"],
    )
    model: str | None = Field(
        default=None,
        description="Dynamic LLM override for execution",
        examples=["gemini-3.8-flash"],
    )
    max_iterations: int = Field(
        default=30,
        description="Maximum turns in the ReAct exploration loop",
        examples=[30],
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Reasoning effort level for Gemini models",
        examples=["low"],
    )


class RemoteCommandPayload(BaseModel):
    cmd: str = Field(
        ...,
        description="UNIX shell command to execute on the remote Linux host",
        examples=["ls -la /data", "grep -i rafal /data/archive.log | head -n 5"],
    )


class CentralaVerifyRequest(BaseModel):
    apikey: str = Field(..., description="Course API key")
    task: str = Field(default="shellaccess", description="Task identifier")
    answer: RemoteCommandPayload = Field(
        ..., description="Command payload for shell execution"
    )


class CentralaVerifyResponse(BaseModel):
    code: int = Field(
        ..., description="Status code from Centrala (0 for success, -1 for error)"
    )
    message: str = Field(
        ..., description="Stdout, stderr, or system message returned by Centrala"
    )


class RafalDiscoveryExtraction(BaseModel):
    discovery_date: str = Field(
        ...,
        description="Raw ISO-8601 date when Rafał's body was discovered",
        examples=["2024-03-01"],
    )
    city: str = Field(
        ...,
        description="Name of the city where Rafał was discovered",
        examples=["Grudziadz"],
    )
    latitude: float = Field(
        ...,
        description="Geographical latitude of the discovery location",
        examples=[53.4837],
    )
    longitude: float = Field(
        ...,
        description="Geographical longitude of the discovery location",
        examples=[18.7533],
    )


class RendezvousPayload(BaseModel):
    date: str = Field(
        ...,
        description="Rendezvous date exactly ONE DAY BEFORE discovery (YYYY-MM-DD)",
        examples=["2024-02-29"],
    )
    city: str = Field(
        ...,
        description="Target rendezvous city name",
        examples=["Grudziadz"],
    )
    longitude: float = Field(
        ...,
        description="Longitude coordinate",
        examples=[18.7533],
    )
    latitude: float = Field(
        ...,
        description="Latitude coordinate",
        examples=[53.4837],
    )


class RunTaskResponse(BaseModel):
    session_id: str
    status: Literal["completed", "failed"]
    flag: str | None = None
    rendezvous: RendezvousPayload | None = None
    total_turns: int
    execution_time_seconds: float
    error: str | None = None
```

---

### Core Logic / Algorithms

#### 1. Sudo-Style `CommandPolicyGate` (Autonomous Agent Only)
Before dispatching an agent command:
1. Parse the command string to extract the base binary executable.
2. Check against `BLACKLISTED_BINARIES`:
   `{"python", "python3", "node", "ruby", "perl", "php", "zsh", "bash -c", "sh -c", "rm", "mv", "chmod", "chown", "dd", "mkfs", "kill", "pkill", "wget", "curl", "nc"}`.
   If blacklisted, reject immediately with a security violation message.
3. Check against `ALLOWED_BINARIES`:
   `{"ls", "find", "grep", "awk", "cut", "sed", "sort", "uniq", "head", "tail", "wc", "stat", "date", "echo", "jq", "pwd", "file", "which", "cat"}`.
   If the base command is not whitelisted, reject with policy error.
4. If command is `cat <filepath>`:
   Tool executes pre-flight: `stat -c %s "<filepath>" 2>/dev/null || wc -c < "<filepath>"`.
   If size $\ge 4,000$ bytes, reject with:
   `"[SECURITY GUARD: Direct 'cat' blocked. Target file is {size} bytes >= 4,000B limit. Use 'head -n 25' or 'grep -i' instead.]"`

#### 2. In-Situ Atomic Remote Execution Wrapper (Agent Only)
When an agent non-submission command passes `CommandPolicyGate`, wrap it in bash compound execution:
```bash
TMP="/tmp/_af_aidevs_out_$$"
(<original_cmd>) > "$TMP" 2>&1
SZ=$(wc -c < "$TMP" 2>/dev/null || echo 0)
if [ "$SZ" -gt 4000 ]; then
  head -c 4000 "$TMP"
  echo -e "\n\n[OUTPUT TRUNCATED: $SZ bytes. Use grep or head to narrow down]"
else
  cat "$TMP"
fi
```
This guarantees that even if a command generates 50 MB, the remote machine truncates it to 4 kB *before* sending HTTP response bytes over the wire, without issuing risky `rm` commands.

#### 3. Direct Passthrough Mode (Artur's REPL)
In `--mode repl`:
- Artur types any command directly into the terminal prompt.
- The command bypasses `CommandPolicyGate` and bypasses the compound wrapper.
- `CentralaService.execute_shell_raw(cmd)` dispatches the raw command to Centrala.
- The raw `stdout`/`stderr` returned by Centrala is printed directly to Artur's console.

#### 4. System Prompt & Embedded Decoded Hint (`prompt_builder.py`)
```python
SYSTEM_PROMPT = """You are an elite Linux systems reconnaissance agent assisting the resistance.
Your objective is to explore the remote host environment via the 'execute_shell' tool, locate when and where Rafał's body was discovered in the historical records in /data, and retrieve the rendezvous parameters.

CRITICAL LESSON HINT:
"Do odczytywania i generowania plików JSON możesz użyć narzędzia 'jq' zainstalowanego na serwerze. Niemal wszystkie potrzebne informacje można uzyskać także za pomocą polecenia 'grep'.
Poprawną odpowiedź możesz wyprodukować przez JSON, albo poskładać samodzielnie i wykonać:
echo '{"date":"2020-01-01","city":"nazwa miasta","longitude":10.000001,"latitude":12.345678}'
UWAGA! Pamiętaj, że musisz zwrócić datę DZIEŃ PRZED znalezieniem ciała Rafała."

STRICT OPERATIONAL RULES:
1. ONLY pure shell commands and standard UNIX utilities (ls, find, grep, awk, cut, sed, sort, uniq, head, tail, wc, stat, date, echo, jq) are permitted.
2. ABSOLUTELY FORBIDDEN: Writing or running scripts in python, python3, zsh, perl, node, or creating temporary script files.
3. Start by listing files in /data (`ls -la /data`). Check file sizes.
4. The archive is large. NEVER attempt unconstrained 'cat' on large files.
5. Use 'grep -i rafal /data/...' or 'head -n 25' or 'jq' directly on the server to search efficiently.
6. Once you locate the record containing Rafał's discovery date, city, and coordinates, call the 'submit_discovery' tool with the exact extracted data.
7. The local verification gate will compute the date exactly ONE DAY BEFORE discovery, validate all coordinates, and issue the final echo command to obtain the flag.
"""
```

#### 5. Local Pydantic Verification Gate
When the agent extracts `RafalDiscoveryExtraction`:
```python
from datetime import date, datetime, timedelta


def compute_rendezvous(discovery: RafalDiscoveryExtraction) -> RendezvousPayload:
    parsed_date = datetime.strptime(discovery.discovery_date, "%Y-%m-%d").date()
    rendezvous_date = parsed_date - timedelta(days=1)

    return RendezvousPayload(
        date=rendezvous_date.isoformat(),
        city=discovery.city.strip(),
        longitude=float(discovery.longitude),
        latitude=float(discovery.latitude),
    )
```
The verification gate emits the clean, unwrapped submission:
```python
cmd = f"echo '{rendezvous.model_dump_json()}'"
response = await centrala_service.execute_shell_raw(cmd)
# Regex extract {FLG:...} from response.message
```

---

### Infrastructure / Deployment

* **Cloud Run Microservice:** `cr-s05e03-shellaccess`.
* **Terraform Registration (`terraform/variables.tf`):**
  - Register under `cr_names.cr-s05e03-shellaccess`:
    ```hcl
    cr-s05e03-shellaccess = {
      image_name = "cr-s05e03-shellaccess"
      source_dir = "../lessons/s05e03-rozwoj-funkcjonalnosci/task/cr-s05e03-shellaccess"
      use_pack   = false
      cpu        = "1"
      memory     = "1Gi"
      timeout    = "600s"
      max_instances = 1
      cpu_idle   = true
      concurrency = 80
      secrets    = ["AIDEVS_API_KEY", "AIDEVS_API_VERIFY", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT"]
      env_vars   = {
        GOOGLE_CLOUD_LOCATION = "global"
        GEMINI_MODEL          = "gemini-3.8-flash"
        THINKING_LEVEL        = "low"
        BQ_DATASET            = "s05e03"
        OUTPUT_CHAR_LIMIT     = "4000"
      }
    }
    ```
  - Dataset: `datasets.s05e03`
  - Audit Table: `tables.s05e03_audit` (`schema = "bq-schemas/s01e04.audit.json"`, `table_id = "audit"`)
* **Container Scaffolding:** Standardized Dockerfile, `cloudbuild.yaml` with `$_IMAGE` and `--build-arg UV_INDEX_GAR_PASSWORD=$_TOKEN`, `.dockerignore`, `.gcloudignore`.

---

## Cross-Cutting Concerns

### Security
* **Zero Hardcoded External URLs:** `$AIDEVS_API_VERIFY` is injected strictly via environment variables / Secret Manager.
* **No Course Flags in Code/Commits:** Flag tokens (`{FLG:...}`) are redacted in all logs and documentation.
* **Sudo-Style Command Policy Gate:** Prevents destructive file operations, unauthorized interpreters (`python`, `zsh`), and subshell escapes during autonomous agent execution.
* **Direct Passthrough REPL:** Artur retains full administrative execution power in manual mode.

### Observability
* **BigQuery Audit Logging:** Every remote shell invocation, input command, status, latency, and sanitized output preview is streamed to `af-aidevs.s05e03.audit`.
* **LangSmith Tracing:** Full agent trajectory tracing under project `$LANGSMITH_PROJECT`.
* **Zero-Pollution Logging:** Tool outputs are capped to 4,000 characters; no unbounded dumps in logs.

### Error Handling & Resilience
* **Centrala Transient Retries:** Wrap calls to `$AIDEVS_API_VERIFY` with exponential backoff on HTTP 429, 500, 502, 503, 504 (up to 3 retries).
* **Agent Loop Iteration Capping:** Hard cap at `max_iterations = 30` to prevent infinite loops.

---

## Edge Cases and Constraints

### Edge Cases
* **Month Boundary Subtraction:** If discovery date is `2024-03-01` (leap year), date must correctly roll back to `2024-02-29`. Python's `datetime.timedelta(days=1)` deterministically guarantees correct leap-year arithmetic.
* **Compound Commands with `cat`:** E.g. `cat /data/foo | grep bar`. The proactive `cat` interceptor inspects the first target file; if size $\ge 4,000$ bytes, it guides the model to use `grep -i bar /data/foo` directly, preventing `cat` from buffering the whole file into the pipe.
* **Special Characters in City Name:** Polish diacritics in city names (e.g. `Grudziądz`, `Gdańsk`, `Toruń`) must be preserved in UTF-8 without unicode escape mangling.

### Constraints
* **Output Buffer Limit:** Exactly 4,000 characters (~1,000 tokens).
* **Max Iterations:** Default 30 turns.

---

## Implementation Plan

### Phases / Milestones

| Phase | Scope | Deliverable |
|---|---|---|
| 1 | Scaffolding & Schemas | `Dockerfile`, `cloudbuild.yaml`, `pyproject.toml`, `schemas.py`, `config.py` |
| 2 | Services & Guardrails | `centrala_service.py` (`execute_shell_agent`, `execute_shell_raw`), `policy_gate.py`, `shell_tool.py`, `audit_service.py` |
| 3 | Core Orchestrator & CLI | `prompt_builder.py`, `orchestrator.py` (ReAct agent + verification gate), `main.py` (`--mode auto`, `--mode repl`) |
| 4 | Test Suite & Validation | Unit tests (`test_command_policy.py`, `test_in_situ_wrapper.py`, `test_verification_gate.py`, `test_schemas.py`) |
| 5 | Quality Gate & Terraform | `ruff`, `mypy`, `pytest`, `terraform/variables.tf` registration |

---

## Implementation Spec

> This section is consumed by the AI coding agent executing `/implement-prd` against this PRD.

### File Structure

```
lessons/s05e03-rozwoj-funkcjonalnosci/task/cr-s05e03-shellaccess/
├── .dockerignore
├── .gcloudignore
├── .python-version
├── Dockerfile
├── README.md
├── cloudbuild.yaml
├── config.py
├── main.py
├── pyproject.toml
├── schemas.py
├── services/
│   ├── __init__.py
│   ├── audit_service.py
│   ├── centrala_service.py
│   ├── orchestrator.py
│   ├── policy_gate.py
│   ├── prompt_builder.py
│   └── shell_tool.py
└── tests/
    ├── __init__.py
    ├── test_in_situ_wrapper.py
    ├── test_policy_gate.py
    ├── test_prompt_builder.py
    ├── test_schemas.py
    └── test_verification_gate.py
```

### Technology Stack

* **Language:** Python 3.13.5 (`requires-python = "==3.13.5"`)
* **Agent Frameworks:**
  * LangChain 1.2.15 (`langchain`, `langchain-core`, `langchain-google-genai`)
  * Google ADK 1.33.0 (`google-adk`, `google-genai == 1.62.0`)
* **HTTP & API Framework:** FastAPI 0.135.3, Uvicorn 0.44.0, httpx 0.28.1
* **Validation & Schemas:** Pydantic 2.13.1, Pydantic-Settings 2.13.1
* **Internal Shared Package:** `af_aidevs` (`audit.bigquery`)

### Step-by-Step Implementation Order

1. **Step 1: Container Scaffolding & Pyproject:** Create `.python-version`, `pyproject.toml`, `.dockerignore`, `.gcloudignore`, `Dockerfile`, and `cloudbuild.yaml`.
2. **Step 2: Configuration & Contracts:** Implement `config.py` and `schemas.py`.
3. **Step 3: Centrala & Audit Services:** Implement `centrala_service.py` with dual methods (`execute_shell_agent` and `execute_shell_raw` with exponential backoff) and `audit_service.py`.
4. **Step 4: Policy Gate & Shell Tool:** Implement `policy_gate.py` (`CommandPolicyGate` allowlist/blacklist with `zsh`, `python`, etc.) and `shell_tool.py` (in-situ `/tmp/_af_aidevs_out_$$` compound wrapper, proactive `cat` interceptor, 4,000-character cap, zero `rm` calls).
5. **Step 5: Prompt Builder & System Messages:** Implement `prompt_builder.py` incorporating the verbatim decoded lesson hint and pure-shell rules.
6. **Step 6: Orchestrator & Local Verification Gate:** Implement `orchestrator.py` supporting autonomous ReAct loop, date math (`date - 1 day`), and clean submission.
7. **Step 7: Entrypoints & REPL:** Implement `main.py` with FastAPI endpoints (`/health`, `/run`) and CLI modes:
   - `--mode auto`: Launches autonomous ReAct agent.
   - `--mode repl`: Launches Artur's direct, unfiltered interactive shell.
8. **Step 8: Automated Test Suite:** Implement unit tests for `policy_gate`, in-situ wrapper, date calculation across month/leap-year boundaries, and schemas.
9. **Step 9: Terraform Registration & Quality Gate:** Add `cr-s05e03-shellaccess`, dataset `s05e03`, and audit table to `terraform/variables.tf`. Run `ruff`, `mypy`, and `pytest`.

### Acceptance Criteria (Testable)

- [ ] `pyproject.toml` pins exact versions without `^` and dependencies are sorted alphabetically.
- [ ] Centrala HTTP client uses `$AIDEVS_API_VERIFY` and never hardcodes raw external URLs.
- [ ] `CommandPolicyGate` allows safe diagnostics (`ls`, `grep`, `jq`, `awk`) and strictly blocks blacklisted commands (`zsh`, `python`, `node`, `rm`, etc.) for the autonomous agent.
- [ ] In-situ remote execution wrapper executes on the remote host, redirects to `/tmp/_af_aidevs_out_$$`, checks size via `wc -c`, and truncates via `head -c 4000`, protecting network egress without using `rm`.
- [ ] Direct Passthrough REPL allows Artur to run arbitrary, raw, unfiltered commands directly on the remote machine.
- [ ] Proactive `cat` interceptor blocks direct agent reads on files $\ge 4,000$ bytes, guiding the agent to `head` or `grep`.
- [ ] Decoded course hint is embedded verbatim in `prompt_builder.py`.
- [ ] Local verification gate calculates `discovery_date - 1 day` using deterministic Python date arithmetic and validates coordinate bounds.
- [ ] Automated tests in `tests/` pass with 100% success rate.
- [ ] Pre-flight quality gates (`ruff check --fix`, `ruff format`, `mypy`) pass with zero errors.
- [ ] Resource registered in `terraform/variables.tf` under `cr_names`, `datasets`, and `tables`.

### Out-of-Scope for Agent (Human Required)

* Performing live `terraform apply` or manual IAM role grants in production.
* Manual execution of `git push` unless requested by Artur.
