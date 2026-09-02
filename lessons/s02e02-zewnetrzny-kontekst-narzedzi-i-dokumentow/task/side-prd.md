# Side PRD: Reusable Architecture, Shared Packages (`af_aidevs`), and Clean Code Standards

## 1. Overview
This provisional document captures shared architectural enhancements to be merged into the final PRD for S02E02 and subsequent lessons. It specifies the modularization of the shared `af_aidevs` Python package (deployed to Google Artifact Registry) and sets strict Clean Code / SOLID design standards to prevent monolithic scripts.

---

## 2. Shared Library Refactoring (`python_packages/af_aidevs`)

To eliminate boilerplate duplication (60–80 lines per lesson for OIDC tokens, MCP setup, and BigQuery logging), the `af_aidevs` library will be expanded and versioned:

### 2.1 Package Module Hierarchy
```text
python_packages/af_aidevs/
├── __init__.py
├── auth/
│   ├── __init__.py
│   └── oidc.py            # GoogleOIDCAuth: Thread-safe, cached Google OIDC id_token provider
├── clients/
│   ├── __init__.py
│   └── mcp.py             # MultiServerMCPClient factory with X-Session-ID & OIDC auth injection
├── audit/
│   ├── __init__.py
│   └── bigquery.py        # BigQueryAuditService: Async, parameterized table logger with ZoneInfo
└── utils/
    ├── __init__.py
    └── prompts.py         # load_system_prompt with YAML frontmatter parsing
```

### 2.2 Reusable Interfaces
- **`GoogleOIDCAuth(audience: str)`**: Custom `httpx.Auth` managing token refresh and local env overrides (`MCP_WORKSPACE_TOKEN`).
- **`create_mcp_client(workspace_url: str, web_url: str, session_id: str)`**: One-line helper returning an initialized `MultiServerMCPClient`.
- **`BigQueryAuditService(dataset_id: str, table_id: str)`**: Async logger with `log(session_id, actor, content, metadata)` method.

---

## 3. Modular Architecture Standards for Lesson Tasks

Every lesson task must adhere to the following modular structure instead of monolithic scripts:

```text
lessons/s02e02-.../task/cr-s02e02-electricity-solver/
├── config.py              # Environment variables & constants
├── schemas.py             # Method-specific Pydantic schemas (I/O, contracts, reasoning)
├── services/              # Pure domain logic (framework-independent)
│   ├── image_service.py   # Image slicing / PIL transformations
│   └── puzzle_service.py  # Rotation calculation & circuit validation
├── agents/                # LLM orchestration
│   ├── base.py            # BaseSolverAgent Protocol
│   ├── factory.py         # AgentFactory (instantiates langchain vs adk)
│   ├── langchain_agent.py # LangChain 1.2.15 (create_agent + LangSmith)
│   └── adk_agent.py       # Google ADK + Langfuse
├── system_prompt.md       # Prompt with YAML frontmatter
└── main.py                # Ultra-lean CLI/Entrypoint (<80 lines)
```

### 3.1 Design Patterns Enforced
1. **Factory Pattern (`AgentFactory`):** Decouples CLI invocation from specific LLM orchestration frameworks (`--backend langchain|adk`).
2. **Singleton / Service Pattern:** Reusable connections for BigQuery and MCP.
3. **Single Responsibility Principle (SRP):** Files kept strictly under ~150 lines, isolating schemas, visual processing, and agent reasoning.
