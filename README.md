# Enterprise Multi-Agent & MCP Cloud Platform

[![Course: AI_Devs](https://img.shields.io/badge/Course-AI__Devs-FF5722?logo=rocket&logoColor=white)](https://www.aidevs.pl/)
[![Python](https://img.shields.io/badge/Python-3.13.5-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Google Cloud](https://img.shields.io/badge/GCP-Vertex_AI_%7C_Cloud_Run_%7C_BigQuery-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/)
[![Google ADK](https://img.shields.io/badge/Google_ADK-GenAI_SDK-4285F4?logo=google&logoColor=white)](https://cloud.google.com/vertex-ai/docs)
[![LangChain](https://img.shields.io/badge/LangChain-1.2.15-1C3C3C?logo=langchain&logoColor=white)](https://python.langchain.com/)
[![LangSmith](https://img.shields.io/badge/LangSmith-Observability_%26_Eval-22C55E?logo=langchain&logoColor=white)](https://smith.langchain.com/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.2.4-009688?logo=fastapi&logoColor=white)](https://github.com/jlowin/fastmcp)
[![Terraform](https://img.shields.io/badge/Terraform-1.5+-844FBA?logo=terraform&logoColor=white)](https://www.terraform.io/)

A production-grade, enterprise-ready multi-agent AI ecosystem built for the [AI_Devs](https://www.aidevs.pl/) advanced AI engineering curriculum. The platform demonstrates zero-trust security governance, a dual-framework agent execution engine (LangChain + Google GenAI SDK / Google ADK on Vertex AI), remote tool invocation via the **Model Context Protocol (MCP)**, full-lifecycle LLM observability with **LangSmith**, and real-time analytical auditing in BigQuery.

---

## 🏛️ System Architecture (C4 Container Model)

The platform is designed as an enterprise **C4 Container-level architecture** featuring an active **Model Armor Decision Gate (Policy Enforcement Point)** governing tool execution:

```mermaid
flowchart TB
    %% Enterprise Styling
    classDef clientTier fill:#E8F0FE,stroke:#1A73E8,stroke-width:2px,color:#174EA6,font-weight:bold;
    classDef agentTier fill:#FEF7E0,stroke:#F9AB00,stroke-width:2px,color:#B06000,font-weight:bold;
    classDef gateTier fill:#FCE8E6,stroke:#D93025,stroke-width:2px,color:#A50E0E,font-weight:bold;
    classDef decisionTier fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px,color:#F57F17,font-weight:bold;
    classDef mcpTier fill:#E6F4EA,stroke:#1E8E3E,stroke-width:2px,color:#0D652D,font-weight:bold;
    classDef paasTier fill:#F3E8FD,stroke:#8430CE,stroke-width:2px,color:#681DA8,font-weight:bold;
    classDef obsTier fill:#E0F2F1,stroke:#00796B,stroke-width:2px,color:#004D40,font-weight:bold;
    classDef extTier fill:#F1F3F4,stroke:#5F6368,stroke-width:2px,stroke-dasharray: 4 4,color:#202124,font-weight:bold;

    %% 1. INGRESS TIER
    subgraph TIER_CLIENT ["1. Ingress & Triggers (Client Tier)"]
        CLI["💻 Task Runner / CLI Client<br/>(s02e01 Session Runner)"]:::clientTier
    end

    %% 2. AGENT RUNTIME TIER
    subgraph TIER_AGENT ["2. Agent Runtime Core (Cloud Run)"]
        direction TB
        AGENT["🤖 cr-s02e01-agent<br/>• LangChain 1.2.15 (create_agent)<br/>• Google GenAI SDK / ADK Engine"]:::agentTier
    end

    %% 3. MODEL ARMOR GATE TIER
    subgraph TIER_GATE ["3. Security Inspection Gate (Cloud Run)"]
        direction TB
        MA["🛡️ cr-model-armor (PEP)<br/>• Prompt Injection Scanner<br/>• Payload Sanitizer"]:::gateTier
        DECISION{"⚡ Gate Decision:<br/>is_safe == True?"}:::decisionTier
        MA --> DECISION
    end

    %% 4. MCP TOOL HUB TIER
    subgraph TIER_MCP ["4. Standardized Tool Hub (FastMCP on Cloud Run)"]
        direction TB
        MCP_WS["🗄️ cr-mcp-workspace<br/>• Session Filesystem (read/write/list)<br/>• Chunking RAG (markdown/grep/head/tail)"]:::mcpTier
        MCP_WEB["🌐 cr-mcp-web-gateway<br/>• Egress HTTP Fetcher<br/>• Content Sanitizer"]:::mcpTier
    end

    %% 5. MANAGED CLOUD SERVICES
    subgraph TIER_GCP ["5. Managed Cloud Services (GCP)"]
        VAI[("🧠 Vertex AI Model Garden<br/>Gemini 3 Flash Preview<br/>(europe-west6 / global)")]:::paasTier
        GCS[("📦 Cloud Storage (GCS)<br/>• Session Workspaces<br/>• Terraform State")]:::paasTier
        BQ[("📊 BigQuery Data Lake<br/>• audit_log Tables<br/>• Analytics ELT Views")]:::paasTier
        IAM[("🔑 Cloud IAM & Secrets<br/>• Service Accounts<br/>• Secret Manager")]:::paasTier
    end

    %% 6. EXTERNAL EGRESS & TELEMETRY
    subgraph TIER_EXT ["6. External Egress & Observability"]
        LS["📈 LangSmith<br/>(Tracing & Evaluation)"]:::obsTier
        INET(["☁️ Public Internet & Course APIs"]):::extTier
        BLOCKED["🛑 Security Block & Log Incident"]:::gateTier
    end

    %% RUNTIME EXECUTION FLOW
    CLI -->|1. Run Task with X-Session-ID| AGENT
    AGENT <-->|2. Reasoning & Prompt Inference| VAI
    AGENT -->|3. Inspect Payload / Tool Intent| MA
    
    %% DECISION GATE BRANCHING (The "If" Condition)
    DECISION -->|✅ Safe: Open Channel / Execute| MCP_WS
    DECISION -->|✅ Safe: Open Channel / Execute| MCP_WEB
    DECISION -->|❌ Unsafe: Cutoff Channel| BLOCKED

    %% TOOL BACKENDS
    MCP_WS <-->|Read / Write State| GCS
    MCP_WEB -->|Outbound Fetch| INET

    %% TELEMETRY & GOVERNANCE
    IAM -.->|OIDC Bearer Tokens| AGENT
    AGENT -.->|Distributed Traces| LS
    AGENT -.->|Lean JSON Logs (stdout)| BQ
    MCP_WS -.->|Audit Events| BQ
    BLOCKED -.->|Security Violation Log| BQ
```

---

### 🛡️ The Model Armor "Gate" Logic

The security architecture operates as an active **runtime gate** controlling agent-tool interactions:

> [!TIP]
> **🔌 Electronics Mental Model (FET Gate Control):**  
> Just like the **Gate ($G$)** in a Field-Effect Transistor controls whether current can conduct between **Source ($S$)** and **Drain ($D$)**:
> - **Source ($S$)** $\rightarrow$ **`cr-s02e01-agent`**: Emits raw thoughts and requested tool calls.
> - **Gate ($G$)** $\rightarrow$ **`cr-model-armor`**: Measures threat potential. If `is_safe == True`, it applies positive potential to allow execution. If malicious prompt injection is detected, it cuts off the channel immediately.
> - **Drain ($D$)** $\rightarrow$ **MCP Servers (`cr-mcp-workspace`, `cr-mcp-web-gateway`)**: Target load executing only verified, safe operations into Google Cloud Storage and external networks.

| Pipeline Stage | Component | Enterprise Architecture Role |
| :--- | :--- | :--- |
| **Origin (Source)** | **`cr-s02e01-agent`** | Orchestrates reasoning, evaluates context, and formulates candidate tool invocations. |
| **Security Gate (PEP)** | **`cr-model-armor`** | Evaluates payloads before execution. Emits a binary decision (`safe` vs. `unsafe`) controlling agent execution branches. |
| **Egress (Drain)** | **Common MCP Servers** | Deployed FastMCP services executing authorized filesystem, RAG, and web actions. |

---

## 🚀 Core Architectural Pillars

### 1. Zero-Trust Security & Identity Governance
- **Google Cloud OIDC Service-to-Service IAM**: Direct Cloud Run service invocation authenticated via OIDC identity tokens, cached dynamically through custom HTTPX authentication handlers.
- **Role-Based Token Impersonation**: Fine-grained access using `roles/iam.serviceAccountTokenCreator` without persistent, static service account keys.
- **Model Armor Firewall**: Dedicated microservice (`cr-model-armor`) serving as an active defense layer against direct and indirect prompt injection attacks.
- **Zero Credential Hardcoding**: Strict isolation of secrets and external platform URLs using GCP Secret Manager in production and `.env` files locally.

### 2. Dual-Engine Agent Core
- **Interchangeable Runtime**: Standardized architecture supporting two state-of-the-art backends:
  - **LangChain 1.2.15**: Structured orchestration using `create_agent` with dynamic runtime MCP tool discovery via `langchain-mcp-adapters`.
  - **Google GenAI SDK / Vertex AI ADK**: High-performance, native SDK integration with Gemini 3 Flash Preview (`gemini-3-flash-preview` / `gemini-3.1-flash-lite-preview`).
- **Externalized Prompt Engineering**: System instructions managed in `system_prompt.md` files featuring YAML frontmatter for metadata, temperature, and region configuration.
- **Deterministic Temporal Context**: Dynamic `get_current_date()` tool calls preserve Vertex AI Prompt Context Caching rather than hardcoding timestamps in prompts.

### 3. Standardized Remote Tooling via MCP (FastMCP)
- **`cr-mcp-workspace`**: FastMCP 3.2.4 microservice deployed on Cloud Run:
  - **Filesystem Tools**: Atomic `read_file`, `write_file`, and `list_files` bound to isolated session workspaces.
  - **Document RAG & Chunking Tools**: Structural markdown intelligence (`list_markdown_sections`, `read_markdown_section`, `grep`, `head`, `tail`) preventing context window overflow.
- **`cr-mcp-web-gateway`**: FastMCP microservice providing secured outbound HTTP fetching and web interaction.
- **Contract-First API Design (AIP Standard)**: Strict Pydantic v2 schemas in `schemas.py` with mandatory `reasoning` in all tool inputs and `hint` fields in responses.

### 4. Lean Auditing & High-Throughput Observability
- **LangSmith Tracing & Evaluation**: Centralized agent trajectory inspection, token spend tracking, prompt version lineage, and evaluation runs via unified `LANGSMITH_PROJECT` integration.
- **End-to-End Distributed Tracing**: Mandatory propagation of the `X-Session-ID` HTTP header across clients, agents, Model Armor, and MCP services.
- **ELT Lean Logging**: Container services emit structured JSON directly to `stdout`. Google Cloud Logging Sinks pipe logs asynchronously to **BigQuery** (`audit` tables and analytical views), guaranteeing zero latency impact on agent response times.
- **Persistent Outcome Summary**: Agents record execution metrics, timestamps, and verification flags to `run_notes.txt` in their session workspace.

---

## 📁 Repository Structure

```text
af-aidevs/
├── cloud_run/                  # Centralized Cloud Run microservices
│   ├── cr-mcp-workspace/       # FastMCP filesystem & RAG service
│   ├── cr-mcp-web-gateway/     # FastMCP web interaction gateway
│   └── cr-model-armor/         # Prompt injection & safety inspection proxy
├── lessons/                    # Lesson tasks & agent implementations
│   ├── s01e01-.../             # Lesson-specific agent workspaces
│   ├── s01e02-.../
│   ├── s01e05-.../             # cr-s01e05-agent implementation
│   └── s02e02-.../             # RAG & external document context
├── python_packages/            # Shared internal Python packages
│   └── af_aidevs/              # Published to Google Artifact Registry (GAR)
│       ├── model_armor.py      # Client wrapper for Model Armor
│       └── utils/              # Lean BigQuery audit streaming & prompt loaders
├── terraform/                  # Centralized Infrastructure as Code (GCP Provider ~> 7.0)
│   ├── modules/                # GCS, Cloud Run, GCF, BigQuery, IAM, Pub/Sub
│   ├── bq-schemas/             # BigQuery schema definitions
│   ├── main.tf                 # Core infrastructure orchestration
│   └── variables.tf            # Centralized infrastructure variables & configuration
└── README.md                   # Platform documentation
```

---

## 🛠️ Development & Environment Setup

### Prerequisites
- **Python**: `== 3.13.5` managed via [`uv`](https://github.com/astral-sh/uv)
- **Google Cloud SDK (`gcloud`)**: Authenticated with appropriate IAM permissions
- **Terraform**: `~> 1.5+` with Google Provider `~> 7.0`

### Local Private Package Setup
To resolve dependencies from the private Artifact Registry repository:
```powershell
# Authenticate uv with Google Artifact Registry
$env:UV_INDEX_GAR_USERNAME="oauth2accesstoken"
$env:UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)

# Sync environment dependencies
uv sync
```

---

## 👨‍💻 Author

**Artur Fejklowicz**
- Data Engineer at AXA Switzerland
- Google Cloud Certified Professional Data Engineer
- Google Cloud Certified Professional Machine Learning Engineer
- [LinkedIn Profile](https://www.linkedin.com/in/arturr/) | [Medium Publications](https://medium.com/@artur.fejklowicz)

