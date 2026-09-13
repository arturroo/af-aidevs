# Business Requirements Document (BRD) — S03E02: Firmware (`firmware`)

## 1. Overview
During the power plant crisis investigation, diagnostic logs revealed critical issues related to controller firmware. Specialists dumped the memory of the **Emergency Core Cooling System (ECCS)** controller into a sandboxed virtual machine running a restricted Linux distribution. 

The objective of this task is to troubleshoot and successfully launch the cooling system software located at `/opt/firmware/cooler/cooler.bin` via an HTTP Shell API, extract the resulting runtime confirmation token, and submit it to the central verification server to stabilize the reactor cooling systems.

---

## 2. Requirements

### 2.1 Functional Requirements
1. **Interactive Shell Navigation**:
   - Communicate with the VM through the Shell API (`$AIDEVS_API_SHELL`) by executing shell commands sequentially.
   - Start exploration by invoking `help` to discover the custom shell command set available in the restricted distribution.
2. **Access Discovery**:
   - Inspect authorized directories to discover the access password required by the cooling application. (Note: The password is saved in multiple system locations).
3. **Application Execution & Diagnostics**:
   - Attempt running the binary `/opt/firmware/cooler/cooler.bin`.
   - Diagnose why execution fails or halts.
4. **Configuration Adjustment**:
   - Inspect and adjust the application configuration file (`settings.ini`) using available file modification commands in the restricted shell.
5. **Confirmation Code Extraction**:
   - Run `/opt/firmware/cooler/cooler.bin` with proper configuration and authentication.
   - Extract the generated confirmation code matching the pattern:
     ```
     ECCS-[a-zA-Z0-9]{40}
     ```
6. **Task Verification**:
   - Submit the extracted confirmation code to the verification endpoint (`$AIDEVS_API_VERIFY`) under the task name `firmware`.
7. **System Recovery**:
   - If the system state becomes corrupted or blocked, trigger the `reboot` command to restore the virtual machine to its initial snapshot.

### 2.2 Safety & Security Constraints (Hard Rules)
- **Non-Root Execution**: Commands run as a standard unprivileged user.
- **Forbidden Paths**: It is strictly forbidden to inspect, list, read, or access:
  - `/etc`
  - `/root`
  - `/proc/`
- **Strict `.gitignore` Adherence**:
  - Whenever entering a directory containing a `.gitignore` file, all paths and patterns listed in `.gitignore` MUST be strictly respected.
  - Touching, reading, or modifying ignored files or directories is strictly forbidden.
- **Consequence of Violations**:
  - Accessing forbidden paths or `.gitignore` entries triggers automated security defense mechanisms: a temporary IP/API ban (lockout for a specific duration in seconds) and an automatic VM reset to the initial state.
- **Read-Only vs. Writable Volumes**:
  - Most of the root filesystem is mounted as read-only.
  - The application directory (`/opt/firmware/cooler/` or software volume) allows write operations.

---

## 3. System & Operational Constraints

### 3.1 LLM Reasoning & Autonomy
- Requires adaptive reasoning and state tracking to navigate non-standard shell commands and interpret non-zero return codes.
- High context fidelity is needed to remember discovered credentials, modified configurations, and blacklist constraints.

### 3.2 Rate Limiting & Resilience
- Shell API may return specific error statuses:
  - Rate limiting / 429 / 503 HTTP status codes.
  - Security ban lockout with remaining duration.
- The system must incorporate error handling, exponential backoff, or structured pause loops when encountering ban/rate-limit responses.

---

## 4. Data Inputs & Environment Setup

### 4.1 Environment Variables
All sensitive keys and external URLs must be loaded strictly via environment variables (`.env`):

| Variable Name | Description | Example / Fallback |
|---|---|---|
| `AIDEVS_API_KEY` | Personal course API key | `[SECRET]` |
| `AIDEVS_API_SHELL` | Remote VM Shell execution API endpoint | Configured in `.env` |
| `AIDEVS_API_VERIFY` | Central verification API endpoint | Configured in `.env` |

*(Note: Raw URLs must never be hardcoded in documentation or code).*

---

## 5. API Integration

### 5.1 Remote Shell API (`$AIDEVS_API_SHELL`)
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Request Payload**:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "cmd": "help"
  }
  ```
- **Response Format**:
  - JSON payload containing command standard output, error output, or status codes.
  - Error/ban response includes message and cooldown time.

### 5.2 Central Verification API (`$AIDEVS_API_VERIFY`)
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Request Payload**:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "firmware",
    "answer": {
      "confirmation": "ECCS-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    }
  }
  ```
- **Response Format**:
  - JSON payload with status code, feedback message, and course verification flag `{FLG:...}` upon success.

---

## 6. Success Criteria
1. VM shell successfully queried without triggering security bans on `/etc`, `/root`, `/proc/`, or `.gitignore` entries.
2. Credentials and `settings.ini` adjustments determined and applied accurately.
3. `/opt/firmware/cooler/cooler.bin` executed cleanly, yielding valid `ECCS-...` token.
4. Central verification API returns status `200` with the lesson flag.
