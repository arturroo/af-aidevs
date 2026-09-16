# cr-s03e04-negotiations

Cloud Run microservice providing autonomous negotiation tools for S03E04 (`negotiations`).

## Features
- **Tool 1 (`/api/search-item-in-catalog`)**: 4-stage pipeline (LLM extraction -> Hybrid RAG BM25 + Vector Cosine -> Co-occurrence ranking -> LLM synthesis).
- **Tool 2 (`/api/find-cities-having-items-ids`)**: Relational set intersection using SQLite parametric SQL (`HAVING COUNT = N`).
- **Response Bounds**: Strictly enforces $4 \le \text{len(bytes)} \le 500$.
- **Database**: Local SQLite `/tmp/inventory.db` in immutable read-only mode (`mode=ro`).
- **Dual Framework Orchestrator**: LangChain 1.2.15 and Google ADK 1.33.0 / GenAI SDK.
