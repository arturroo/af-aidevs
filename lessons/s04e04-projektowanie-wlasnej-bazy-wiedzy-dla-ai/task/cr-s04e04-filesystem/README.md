# cr-s04e04-filesystem

Cloud Run microservice and agent pipeline for AI_Devs Season 4 Episode 4 (`filesystem`).
Reconstructs, normalizes, and stages Natan Rams' barter trade notes into Centrala's virtual filesystem (`/miasta`, `/osoby`, `/towary`).

## Features
- **Dual Agent Framework:** LangChain (`1.2.15`) & Google ADK (`1.33.0`) selectable via `--backend`.
- **Pre-Flight Quality Gate:** Triple-check validation (`validate_workspace`) combining deterministic Python checks (ASCII purity, JSON format, referential links) and `gemini-3.8-flash-lite` linguistic subagent validation (singular nominative nouns) with 100% word coverage assertions.
- **Workspace Staging Buffer:** Staging in `cr-mcp-workspace` and progress tracking via `workspace/TODOs.md`.
- **Atomic Batch Push:** Centrala API synchronization via `reset`, batch `createFile`, and `done`.
- **Telemetry:** BigQuery dataset `s04e04` audit streaming and LangSmith tracing.

## Quick Start (CLI)
```powershell
uv run python main.py --backend langchain
uv run python main.py --backend adk
```
