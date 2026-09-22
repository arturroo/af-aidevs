# S04E03: Tactical Search & Rescue Operation in Domatowo (`cr-s04e03-domatowo`)

Cloud Run microservice implementing an autonomous search-and-rescue mission in the ruined city of Domatowo for lesson S04E03 of the AI_Devs course.

## Architecture
- **Framework Parity**: Dual-backend support for **LangChain 1.2.15** (`create_agent`) and **Google ADK 1.33.0** (`google.adk.Agent`, `Runner`).
- **Autonomous Discovery**: Bootstraps with zero prior knowledge from `action: "help"`.
- **Zero Direct Egress**: Interacts with Centrala via `cr-mcp-web-gateway` with tenacity retry for rate limits (`-9999`, HTTP 429).
- **Workspace Memory**: Manages monotonic state checkpoints in `todos.md` via `cr-mcp-workspace`.
- **Deterministic Tactical Navigation**: Precomputes dual routing tables ($O(1)$ lookups) for transporters (33 street tiles) and scouts (121 tiles), automatically resolving off-road drop-offs.
- **Clockwise Sweep**: LLM drives turn-by-turn perimeter sweep of `BLOK_3P` clusters (`F2->G2->G1->F1`, `H10->I10->I11->H11`, `B10->A10->A11->B11->C11->C10`).
- **Telemetry**: Streams structured audit logs to BigQuery dataset `s04e03` (`audit` table) and LangSmith.

## Endpoints
- `GET /health` & `GET /`: Health checks.
- `POST /run`: Execute mission with payload `{"backend": "langchain" | "adk", "session_id": "..."}`.

## Local CLI Execution
```powershell
uv run python main.py --backend langchain
uv run python main.py --backend adk
```
