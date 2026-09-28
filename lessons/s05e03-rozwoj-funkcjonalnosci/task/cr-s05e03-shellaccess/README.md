# Cloud Run Service: cr-s05e03-shellaccess

Microservice for S05E03: Remote Shell Access & Time Archive Investigation (`shellaccess`).

## Capabilities
- Autonomous ReAct Agent exploring `/data` logs with Gemini 3.8 Flash (`--mode auto`).
- Direct Passthrough Interactive CLI REPL for human exploration (`--mode repl`).
- Sudo-Style `CommandPolicyGate` (whitelisting safe commands, blocking dangerous binaries and script interpreters).
- In-Situ Remote Execution Wrapper (`/tmp/_af_aidevs_out_$$` with `wc -c` check and `head -c 4000` truncation without `rm`).
- Local Pydantic Verification Gate deterministically computing `date - 1 day` and coordinates before emitting `echo '{"date":...}'`.
- BigQuery streaming audit telemetry (`af-aidevs.s05e03.audit`) and LangSmith distributed tracing.

## Local Execution

### Autonomous Mode
```powershell
uv run python main.py --mode auto --model gemini-3.8-flash --max-iterations 30
```

### Interactive REPL Mode (Artur Direct Access)
```powershell
uv run python main.py --mode repl
```

### API Server
```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```
