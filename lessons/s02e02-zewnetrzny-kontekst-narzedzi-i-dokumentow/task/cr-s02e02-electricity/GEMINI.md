# S02E02 Electricity Solver Context & Architectural Guidelines

## In-Process Multi-Agent Architecture (Single Cloud Run Service)

### Architectural Decision
Rather than creating separate Cloud Run microservices for each specialist (e.g. an external `cr-agent-vision` over HTTP A2A), this service adopts an **In-Process Multi-Agent Architecture hosted entirely within a single Cloud Run container**.

### Why In-Process Multi-Agent over Standalone Microservices (A2A)?
1. **Zero Network Latency & No Extra Cold Starts**: Communication between the Primary Orchestrator and the Vision Specialist happens in-process (in-memory) rather than crossing HTTP boundaries.
2. **Unified Deployment & Resource Footprint**: Single container lifecycle, single Terraform definition, and single IAM service account (`sa-cr-s02e02-electricity`).
3. **In-Memory Image Transfer**: Raw high-resolution image buffers (`electricity.png`, `solved_electricity.png`) can be passed directly between agents in RAM or through the local FUSE mount (`/mnt/workspaces`) without generating unnecessary external network traffic or public signed URLs.
4. **Hierarchical Tracing in LangSmith**: Every subagent invocation is automatically traced as a nested child run span under the root orchestrator run, giving full visibility into thoughts, subagent delegations, and tool calls in LangSmith.

---

## Supported Multi-Agent Framework Patterns

### 1. LangChain / LangSmith Pattern (Supervisor & Subagents)
* **Framework**: LangChain 1.2.15 / LangGraph `StateGraph`.
* **Topology**:
  * **Supervisor Agent (Orchestrator)**: Manages high-level goal, MCP Web Gateway calls (`fetch_web_resource`, `post_web_resource`), and final report generation (`write_file`).
  * **Vision Specialist Subagent (Node/Chain)**: In-process agent equipped with domain image analysis tools (`extract_board_pinouts`, `compute_board_rotations`). Receives image paths and returns structured `GridCircuitSolverData`.
* **Observability**: Automatically nested spans in LangSmith via `AsyncCallbackHandler` / `RunTree`.

### 2. Google ADK / GenAI Agent Pattern (Hierarchical Agents)
* **Framework**: Google ADK (`google-adk` / `google-genai`).
* **Topology**:
  * **Root Orchestrator**: Runs the main execution loop.
  * **Sub-Agents**: Subagent functions / inner agent instances invoked directly as specialized agents within the parent tool execution loop.
* **Observability**: Structured audit events streamed directly to BigQuery `af-aidevs.s02e02.audit`.

---

## Implementation Rules
1. **Contract-First Interfaces**: All data exchanged between the orchestrator and subagents must strictly adhere to Pydantic models from `af_aidevs.schemas.vision` (`TilePinout`, `GridCircuitSolverData`).
2. **No External HTTP for Subagents**: In-process subagents must not expose public HTTP endpoints; all subagent invocations remain internal Python coroutines.
3. **Graceful Error Recovery**: All subagent tool calls must set `handle_tool_error = True` to enable self-correction if an image path or format is invalid.
