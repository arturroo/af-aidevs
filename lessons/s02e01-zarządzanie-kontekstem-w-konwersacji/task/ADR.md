<!-- Source: https://github.com/adr/madr/blob/4.0.0/template/adr-template.md -->
<!-- MADR project: https://adr.github.io/madr/ -->

---
status: "accepted"
date: 2026-07-06
decision-makers: Joi, Artur
consulted: Artur
informed: Artur
---

# Categorization Agent with MCP Ecosystem Integration (Web & Agentic RAG)

## Context and Problem Statement

The immediate goal is to classify 10 items into Dangerous (`DNG`) or Neutral (`NEU`) categories, ensuring that nuclear reactor items are classified as `NEU` to bypass inspection. The remote system enforces a strict **100-token context window** per request and a tight financial budget of **1.5 PP**. 

However, a broader architectural problem arose during design: how should the agent interact with the external world (e.g., downloading the source CSV and posting to the VERIFY API) and read files? Should every lesson's agent implement its own `httpx` logic and file parsers, or should we decouple this into reusable components?

## Decision Drivers

* **100-Token Limit & Budget:** Token usage (input, cached, output) must be strictly managed to stay within the 1.5 PP budget.
* **Dual Backend Support:** The framework needs to support both LangChain (v1.2.15) and Google ADK with a runtime switch.
* **DRY & Separation of Concerns:** Agents should be lightweight orchestrators, delegating internet access and file processing to specialized tools.
* **Secure Agentic RAG:** Exposing shell utilities (grep) via GCS FUSE requires strict security to prevent command injection and catastrophic latency (e.g., preventing recursive scans on remote buckets).
* **Robust Parsing:** Extracting specific sections from large Markdown documents must be reliable and context-aware.

## Considered Options

* **Option 1: Monolithic Agent.** The agent handles HTTP requests (`httpx`) to fetch the CSV and POST verification directly in the Python code, alongside the LLM orchestration.
* **Option 2: MCP Ecosystem Driven Agent.** The agent relies entirely on two external MCP servers:
  1. `cr-mcp-web-gateway`: A new dedicated internet gateway for HTTP GET/POST. It mounts the `af-aidevs-workspaces` GCS FUSE bucket so it can download large files directly to the workspace and return only the file path to the LLM.
  2. `cr-mcp-workspace`: Enhanced with Agentic RAG capabilities, including safe system tools (`grep`, `head`, `tail`) and an AST-based Markdown parser.

## Decision Outcome

Chosen option: "Option 2", because:
* It completely abstracts HTTP communication out of the agent, making the `s02e01` codebase incredibly lean and focused solely on prompt optimization.
* The new `cr-mcp-web-gateway` server provides a unified, reusable interface for all future lessons to interact with the internet.
* By downloading files directly to the GCS FUSE bucket via `cr-mcp-web-gateway`, the agent avoids pushing massive files through the LLM context.
* We decided to use `markdown-it-py` (AST parsing) over standard Regex for `read_markdown_section` because AST guarantees 100% accuracy with nested headers and code blocks, unlike fragile Regex solutions.
* We decided to implement system tools (`grep`, `head`, `tail`) using a strict, multi-layered security model natively supported in Python and FastMCP:
  * **Command Injection Protection:** All system calls will use `subprocess.run(["command", ...], shell=False)` to prevent any shell evaluation of user input.
  * **Path Traversal Protection:** We will reuse the proven `pathlib` pattern already established in `cr-mcp-workspace` (e.g., in `read_file.py` using `.resolve()` and boundary checks like `.is_relative_to()`) to strictly contain all file operations within the agent's dedicated workspace directory.
  * **Parameter Constraints:** Tools like `head` and `tail` will enforce limits directly at the MCP schema level using Pydantic (e.g., `Field(ge=1, le=10)`) to natively reject requests for excessively large chunks.
  * **Resource Exhaustion Protection:** For `system_grep`, the recursive `-r` flag is explicitly blocked to protect the GCS FUSE mount from catastrophic latency and unpredictable GCP Class B operation billing. Only a whitelist of safe flags (`-i`, `-n`, `-v`, `-C`, `-A`, `-B`) will be permitted.
* **Token Counter Tool (Pre-flight Check):** To guarantee we never exceed the 100-token limit, we decided to provide the Agent with a `count_tokens` tool. Since `Google ADK` is an orchestration layer, this tool will directly utilize the underlying `google-genai` SDK API (`client.models.count_tokens()`) or LangChain's native `get_num_tokens()` to provide 100% accurate, model-specific token counts before any API calls are made. 
  * *Dependency Management:* As a software engineering best practice, we will explicitly define `google-genai` in `pyproject.toml` and instantiate a standalone `genai.Client()` strictly for the token counter, rather than relying on ADK's transitive dependencies. While this ensures code clarity and explicit imports, it introduces a trade-off: future updates to ADK might require manual version synchronization with `google-genai` to prevent dependency conflicts (dependency pinning).
* **Prompt Design Strategy (Few-Shot Prompting):** Given the extreme 100-token limit, the Agent will utilize a minimalistic few-shot prompting technique instead of verbose instructions. For example, providing a highly suggestive mapping like `"reactor": "NEU"` naturally forces the remote evaluating LLM to classify reactor items as neutral, drastically reducing prompt size while maximizing instruction adherence.

### Consequences

* **Good:** Agents across all lessons become simpler, relying on standard MCP tools for I/O.
* **Good:** `markdown-it-py` ensures our agents can reliably extract APIs and instructions from complex BRDs/READMEs.
* **Good:** Strict security on `system_grep` protects the infrastructure from command injection and runaway Cloud Storage costs.
* **Bad:** This architectural pivot requires pausing `s02e01` implementation to first build and deploy `cr-mcp-web-gateway` and update `cr-mcp-workspace` in Terraform and Cloud Run.

### Confirmation

Confirmation will be verified by:
1. Deploying `cr-mcp-web-gateway` and validating it can download a test CSV to the shared FUSE bucket.
2. Testing `system_grep` in `cr-mcp-workspace` to ensure `-r` fails and `shell=False` prevents command injection.
3. Testing the AST Markdown parser on a complex document.
4. Completing the `s02e01` categorization task exclusively using these MCP tools without native `httpx` code in the agent.

## Pros and Cons of the Options

### Option 1: Monolithic Agent

The agent does everything itself.

* **Good**, because it is faster to implement immediately for this single lesson.
* **Bad**, because we will rewrite `httpx` boilerplate and custom file parsers in every subsequent lesson.

### Option 2: MCP Ecosystem Driven Agent

The LLM is provided tools from `cr-mcp-web` and `cr-mcp-workspace`.

* **Good**, because it establishes a scalable, Agentic RAG foundation for the entire course.
* **Good**, because AST parsing (`markdown-it-py`) is significantly more robust than manual Regex for extracting sections.
* **Neutral**, requires an upfront investment in infrastructure (Terraform updates, new Cloud Run service).
