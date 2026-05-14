# Task S01E02 - "findhim" with Tool Discovery

This directory contains the implementation for the "findhim" task from Lesson S01E02 ("Techniki łączenia modelu z narzędziami"). The goal was to build an agent that can track down a specific person using dynamically discovered tools.

## Implementations

The solution is prepared in two versions to compare modern approaches:
1. **Google GenAI SDK**: Native implementation using the new SDK with a manual agent loop.
2. **LangChain / LangGraph**: Automated implementation using `create_react_agent` from LangGraph.

Both versions utilize **Dynamic Tool Discovery**, where the `tools/` directory is scanned and functions are registered automatically.

## Architectural Reflections & Best Practices

During the implementation of this task, several critical architectural questions arose regarding scaling tool usage in production:

### 1. Tool Discovery vs. Progressive Disclosure
* **Dynamic Tool Discovery** (what we implemented here) automatically loads all available tools into the model's prompt. While useful for automation, it exposes all tools at once.
* **Progressive Disclosure** means revealing tools to the model step-by-step or only when needed. Dumping too many tools into a single prompt leads to context pollution, higher costs, and increased risk of model hallucinations.

To implement *true* Progressive Disclosure, we could have used approaches like:
* **The Meta-Tool Approach (Most Token-Efficient)**: Expose only two tools to the LLM:
    1. `list_available_actions_and_params(action_name: Optional[str])` - To list available actions or to get the specific parameter schema for a chosen action.
    2. `execute_action(name: str, payload: dict)` - To execute the chosen action.
    This approach is highly efficient as the model does not need to load the full schema of all tools upfront. It only requests the parameters for the specific action it intends to use, drastically reducing token usage.
* **The Extreme Agentic Approach (Code Execution)**: Give the agent tools to list files, read files, and execute Python code. The agent would then:
    1. List the files in the `tools/` folder.
    2. Read the source code of a specific file (e.g., `get_access_level.py`) to discover its required parameters.
    3. Use a tool like `exec_python` to execute that logic with the discovered parameters.
    This is a highly autonomous pattern where the model discovers and uses tools directly from code.

### 2. The Monolithic Agent vs. Multi-Agent Systems
When a system scales to dozens or hundreds of tools, a monolithic agent becomes unreliable:
* **The Generic Tool Approach** (e.g., exposing a single `execute_action` tool) scales well but sacrifices strict type validation. Models handle structure well but can hallucinate parameter values when not bounded by a strict Pydantic/JSON schema in the tool definition itself.
* **The Multi-Agent Delegation Approach** (Sub-agents as Tools) is often the best production pattern. Instead of giving one agent 50 tools, we give it a few tools that trigger specialized sub-agents. Each sub-agent has a narrow domain and only 2-3 strictly typed tools. This preserves clean context, avoids hallucinations, and maintains full scalability.

### 3. Emerging Standards: A2A vs. MCP
As multi-agent systems mature, standardized protocols are emerging to handle communication boundaries:
* **MCP (Model Context Protocol)**: Focuses on the **Agent-to-Tool** relationship. It connects an agent to local files, databases, and APIs.
* **A2A (Agent-to-Agent Protocol)**: Introduced by Google (and donated to the Linux Foundation), it focuses on the **Agent-to-Agent** relationship. It provides a common language (via JSON-RPC and Agent Cards) for agents built on different frameworks to discover, authenticate, and collaborate with each other.

In production, they are complementary: an agent might use MCP to retrieve context from a secure database and then use A2A to securely delegate a subtask to another specialized agent in a different domain.
