# Cloud Run Service: cr-s05e04-goingthere

Microservice for S05E04: Autonomous Rocket Navigation & OKO Radar Neutralization (`goingthere`).

## Capabilities
- Deterministic Finite State Machine (FSM) with `FlightState` accumulator navigating a 3x12 grid.
- Model Armor screening (`cr-model-armor`) for incoming frequency scanner and radio broadcast payloads.
- Jamming-resilient telemetry extraction via Gemini 3.5 Flash-Lite (`thinking_level="medium"`).
- Cryptographic SHA-1 radar disarming ($\text{SHA-1}(\text{code} + \text{"disarm"}))$ before movement.
- Semantic nautical translation resolving English maritime jargon (*port*, *starboard*, *dead ahead*, *shoals*) to rock rows.
- Dynamic heuristic lookahead path planner converging on Grudziądz target row without wall crashes.
- Egress gateway routing via `cr-mcp-web-gateway` with `--direct-egress` bypass for local development.
- Mandatory session audit persistence in `cr-mcp-workspace` (`run_notes.txt`) and BigQuery (`s05e04.audit`).

## Local Execution

### Full Autonomous Flight (Standard)
```powershell
uv run python main.py --direct-egress
```

### Interactive Step-by-Step Flight
```powershell
uv run python main.py --step-by-step --direct-egress
```

### Pre-Flight Probe (1-second ping)
```powershell
uv run python main.py --probe --direct-egress
```

### Verbose Debug Mode
```powershell
uv run python main.py --verbose --direct-egress
```

### Local API Server
```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```
