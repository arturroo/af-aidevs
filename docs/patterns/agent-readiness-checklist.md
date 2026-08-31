# Pre-Flight Agent Readiness & Security Checklist

- **Status**: Accepted
- **Approved by**: Artur Fejklowicz
- **Date**: 2026-08-31
- **Scope**: Platform-wide Agent Architecture, Security Governance & Deployment

A standardized engineering checklist and decision framework to be evaluated before designing, granting access to, or deploying any AI Agent within the platform.

Based on course materials from AI_Devs 4, Google Cloud Best Practices, and OWASP Top 10 for LLMs / Agentic Architectures (2025/2026).

---

## 1. Safety & Access: "Before Granting AI Access" (Threat Modeling)

Before connecting an LLM to external systems, databases, filesystems, email, or CRMs, answer these four fundamental questions:

### 1. What can go wrong? (*Threat Modeling & Blast Radius*)
- **Blast Radius Evaluation:** If the agent behaves unexpectedly, hallucinates, or is compromised via prompt injection, what is the maximum potential damage it can cause?
- **Destructive Actions:** Can it delete databases/files, overwrite critical configurations, send unauthorized emails, or leak confidential customer data?
- **Prompt Leakage:** Can it expose internal system prompts, business logic, or tool schemas?
- **Time to Impact:** How much damage can the agent inflict in 10–30 seconds before any human or monitoring system detects the anomaly?

### 2. How do I revert it? (*Disaster Recovery & Rollback*)
- **Reversibility:** Are all operations performed by the agent fully reversible?
- **Pre-Execution Backups:** Do write operations automatically snapshot the previous state (e.g., OverlayFS layers, pre-mutation database logs)?
- **Human-in-the-Loop (HITL):** Are destructive or external-facing actions (e.g., sending emails, deleting blobs) protected by a `draft` status or a dry-run confirmation step?
- **Disaster Recovery Plan (DRP):** Is there an automated procedure to restore system integrity if an agent makes incorrect mutations?

### 3. Who will see it? (*Audit Trail & Observability*)
- **Full Traceability:** If queried 30 days from now about an action taken at a specific second, can we reconstruct the exact sequence of events?
- **Logged Artifacts:** Are prompt inputs, outputs, chain-of-thought tokens, tool arguments, tool responses, and `X-Session-ID` headers permanently logged into BigQuery audit tables and LangSmith?

### 4. What does the law say? (*Legal Compliance, GDPR & AI Act*)
- **Lawful Basis:** Is there a clear legal basis (consent, contractual necessity, legitimate interest) for processing this specific data through third-party LLMs?
- **Data Minimization:** Does the agent process only the data strictly required for the specific task?
- **Transparency Obligations:** Do end-users receive clear disclosure that they are interacting with an AI system (EU AI Act requirement)?
- **72-Hour Breach Notification:** Is there a documented incident response procedure if an agent causes a personal data breach?

---

## 2. Tool Architecture & Vulnerability Defense (Defense-in-Depth)

Every tool attached to an agent expands the overall attack surface. Apply the following checks:

### 1. Principle of Least Privilege
- **Read-Only by Default:** Start all agent integrations with read-only access. Grant write permissions surgically only to explicit tables or fields.
- **Resource Scoping:** Limit access to individual entities (e.g., a single lead/ticket ID) rather than whole tables or CRM instances (preventing *Force Leak* exploits).
- **Short-Lived Tokens:** Use short-lived OAuth / Google Cloud OIDC tokens with strict scopes, rotated frequently and stored in Secret Manager.

### 2. Indirect Prompt Injection & Tool Poisoning
- **Untrusted External Content:** Treat all external data (emails, PDFs, crawled websites, database records, MCP server responses) as untrusted inputs that could contain adversarial instructions.
- **Model Armor Inspection:** Route candidate tool calls and prompts through validation gates (`cr-model-armor`) before invoking downstream execution.
- **MCP Tool Poisoning:** Verify tool definitions and ensure MCP server descriptions do not contain hidden prompt overrides or privilege escalation prompts.

### 3. Data Boundaries & Secrets Isolation
- **No Secrets in Prompts:** API keys, database credentials, and service tokens must NEVER be placed inside system prompts, tool descriptions, or repo configs.
- **Output Sanitization:** Validate and filter agent outputs and tool responses before passing them back to the user or downstream microservices.

### 4. Anomaly Monitoring & Kill Switch
- **Behavioral Thresholds:** Configure alerts for sudden spikes in tool invocations, token consumption, or requests to unusual resources.
- **Hardware/Logical Kill Switch:** Maintain a single zero-step mechanism (feature flag or IAM toggle) to immediately sever agent access to all tools and external APIs.

---

## 3. Architecture & Feasibility: Workflow vs. Agent

Before writing any agent code, justify the architectural pattern:

```
                  +-----------------------------------+
                  | Can the problem be solved with    |
                  | deterministic code or 5-line regex?|
                  +-----------------+-----------------+
                                    |
                    +---------------+---------------+
                    | YES                           | NO
                    v                               v
         +--------------------+     +-----------------------------------+
         | Traditional Code   |     | Does the task have dynamic loops, |
         | (Deterministic)    |     | tool choices, or unknown steps?   |
         +--------------------+     +---------------+-------------------+
                                                    |
                                    +---------------+---------------+
                                    | NO                            | YES
                                    v                               v
                         +--------------------+          +--------------------+
                         | LLM Workflow       |          | Autonomous Agent   |
                         | (Code-driven pipe) |          | (Model-driven loop)|
                         +--------------------+          +--------------------+
```

### 1. Do you really need an autonomous agent?
- **Predictability vs. Adaptability:** If the workflow is a fixed sequence of steps with structured inputs, use a **Workflow** (code controls flow, LLM serves as a parser/extractor).
- **Agent Selection:** Use an **Autonomous Agent** only when the model must dynamically formulate plans, choose from tools, and iterate based on dynamic execution feedback.

### 2. Which model is "good enough"? (*Model Routing*)
- **Tiered Selection:** Route simple classification and structured extraction tasks to fast/cheap models (e.g., `gemini-3.5-flash-lite`, `gpt-4o-mini`).
- **Reserve Reasoning Models:** Restrict heavy reasoning models (`gemini-3-flash-preview`, `claude-3-7-sonnet`) to complex multi-hop decomposition and ambiguity resolution.

### 3. How much context do you actually need? (*Context Hygiene*)
- **Context Pruning:** Avoid dumping entire conversation histories and multi-megabyte reference documents into every prompt.
- **Prompt Caching & Batch API:** Utilize Prompt Caching on stable system instructions and leverage Batch API (50% discount) for non-real-time asynchronous workloads.

---

## 4. Production Deployment Lifecycle (4 Steps)

```
[ Step 1: Map Access ]
  └── List all target systems, evaluate Blast Radius, enforce Read-Only baseline.

[ Step 2: Configure Controls ]
  └── Issue scoped OIDC/OAuth tokens, enable BigQuery ELT audit logging, set quotas.

[ Step 3: Build Safety Net ]
  └── Add pre-write backups, require Human-in-the-Loop for critical actions, enable Kill Switch.

[ Step 4: Verify Compliance ]
  └── Confirm legal basis, ensure AI transparency disclosure, verify 72h incident response plan.
```
