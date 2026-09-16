# cr-s03e04-negotiations

Cloud Run microservice providing autonomous negotiation tools for S03E04 (`negotiations`).

## Features
- **Tool 1 (`/api/search-item-in-catalog`)**: 4-stage pipeline (LLM extraction -> Hybrid RAG BM25 + Vector Cosine -> Co-occurrence ranking -> LLM synthesis).
- **Tool 2 (`/api/find-cities-having-items-ids`)**: Relational set intersection using SQLite parametric SQL (`HAVING COUNT = N`).
- **Response Bounds**: Strictly enforces $4 \le \text{len(bytes)} \le 500$.
- **Database**: Local SQLite `/tmp/inventory.db` in immutable read-only mode (`mode=ro`).
- **Dual Framework Orchestrator**: LangChain 1.2.15 and Google ADK 1.33.0 / GenAI SDK.
- **Model Tiering**: `gemini-3.5-flash-lite` for entity extraction and `gemini-3.8-flash` for synthesis.
- **Deterministic Fast-Path**: Direct regex + local SQL validation in Tool 2 bypassing LLM in 0.05 ms.
- **In-Transit gzip**: On-the-fly decompression of `inventory.db.gz` (68 ms).
- **Zero-Pollution Telemetry**: Recursive Base64 masking for LangSmith and BigQuery audit streaming (`s03e04.audit`).

## Autonomous Execution Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Centrala Agent
    participant CR as cr-s03e04-negotiations
    participant FP as Fast-Path / Local SQLite
    participant V_EXT as Vertex AI (Gemini 3.5 Flash-Lite)
    participant V_SYN as Vertex AI (Gemini 3.8 Flash)
    participant LS as LangSmith / BigQuery

    Note over C, CR: Turn 1: Initial Discovery
    C->>CR: POST /api/search-item-in-catalog ("wind turbine elements 2026Q1")
    CR->>V_EXT: Extract technical entities (kabel, maszt, turbina)
    V_EXT-->>CR: ["kabel", "maszt", "turbina"]
    CR->>FP: Hybrid Search (Fuzz + sqlite-vec 768d + Co-occurrence)
    FP-->>CR: Top Candidates: WITR48, 06OTEA, A94MAZ
    CR->>V_SYN: Synthesize Polish recommendation <= 500 bytes
    V_SYN-->>CR: Formatted string with (kod: XXXXXX)
    CR->>LS: Stream trace (Masked Base64, metrics)
    CR-->>C: Response (420 bytes, HTTP 200)

    Note over C, CR: Turn 2: Item Disambiguation
    C->>CR: POST /api/search-item-in-catalog ("specifications for WITR48")
    CR->>FP: Direct catalog query
    CR->>V_SYN: Format concise confirmation <= 500 bytes
    CR-->>C: Response (215 bytes, HTTP 200)

    Note over C, CR: Turn 3: City Location Query (Sub-Millisecond Fast-Path)
    C->>CR: POST /api/find-cities-having-items-ids ("WITR48, 06OTEA, A94MAZ")
    Note over CR, FP: Deterministic Fast-Path Triggered!
    CR->>FP: Regex extraction \b[A-Z0-9]{6}\b -> candidate codes
    CR->>FP: SQL: SELECT city FROM inventory WHERE item_code IN (...) GROUP BY city HAVING count=:N
    FP-->>CR: Matched Cities: [REDACTED_CITIES] (0.05 ms, 0 tokens)
    CR-->>C: "[REDACTED_CITIES]" (HTTP 200)

    Note over C, CR: Turn 4: Purchase Finalization
    C->>C: Selects target location & finishes negotiation loop
    C-->>CR: Task completed with flag {FLG:...}
```

## API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` / `/` | `GET` | Canonical health check and readiness probe. |
| `/reload-db` | `POST` | Downloads `inventory.db.gz` from MCP/GCS and decompresses in-transit to `/tmp/inventory.db`. |
| `/api/search-item-in-catalog` | `POST` | Tool 1: Hybrid catalog search with contract-first 500-byte output bounds. |
| `/api/find-cities-having-items-ids` | `POST` | Tool 2: Fast-path relational intersection for items co-occurrence. |
| `/run` | `POST` | Canonical task orchestrator registering tools with Centrala and polling verification status. |
