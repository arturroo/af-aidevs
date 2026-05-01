# create_agent

> **Function** in `langchain`

📖 [View in docs](https://reference.langchain.com/python/langchain/agents/factory/create_agent)

Creates an agent graph that calls tools in a loop until a stopping condition is met.

For more details on using `create_agent`,
visit the [Agents](https://docs.langchain.com/oss/python/langchain/agents) docs.

## Signature

```python
create_agent(
    model: str | BaseChatModel,
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]] = (),
    response_format: ResponseFormat[ResponseT] | type[ResponseT] | dict[str, Any] | None = None,
    state_schema: type[AgentState[ResponseT]] | None = None,
    context_schema: type[ContextT] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache[Any] | None = None,
) -> CompiledStateGraph[AgentState[ResponseT], ContextT, _InputAgentState, _OutputAgentState[ResponseT]]
```

## Description

The agent node calls the language model with the messages list (after applying
the system prompt). If the resulting [`AIMessage`][langchain.messages.AIMessage]
contains `tool_calls`, the graph will then call the tools. The tools node executes
the tools and adds the responses to the messages list as
[`ToolMessage`][langchain.messages.ToolMessage] objects. The agent node then calls
the language model again. The process repeats until no more `tool_calls` are present
in the response. The agent then returns the full list of messages.

**Example:**

```python
from langchain.agents import create_agent

def check_weather(location: str) -> str:
    '''Return the weather forecast for the specified location.'''
    return f"It's always sunny in {location}"

graph = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    tools=[check_weather],
    system_prompt="You are a helpful assistant",
)
inputs = {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
for chunk in graph.stream(inputs, stream_mode="updates"):
    print(chunk)
```

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `model` | `str \| BaseChatModel` | Yes | The language model for the agent.  Can be a string identifier (e.g., `"openai:gpt-4"`) or a direct chat model instance (e.g., [`ChatOpenAI`][langchain_openai.ChatOpenAI] or other another [LangChain chat model](https://docs.langchain.com/oss/python/integrations/chat)).  For a full list of supported model strings, see [`init_chat_model`][langchain.chat_models.init_chat_model(model_provider)].  !!! tip ""      See the [Models](https://docs.langchain.com/oss/python/langchain/models)     docs for more information. |
| `tools` | `Sequence[BaseTool \| Callable[..., Any] \| dict[str, Any]] \| None` | No | A list of tools, `dict`, or `Callable`.  If `None` or an empty list, the agent will consist of a model node without a tool calling loop.   !!! tip ""      See the [Tools](https://docs.langchain.com/oss/python/langchain/tools)     docs for more information. (default: `None`) |
| `system_prompt` | `str \| SystemMessage \| None` | No | An optional system prompt for the LLM.  Can be a `str` (which will be converted to a `SystemMessage`) or a `SystemMessage` instance directly. The system message is added to the beginning of the message list when calling the model. (default: `None`) |
| `middleware` | `Sequence[AgentMiddleware[StateT_co, ContextT]]` | No | A sequence of middleware instances to apply to the agent.  Middleware can intercept and modify agent behavior at various stages.  !!! tip ""      See the [Middleware](https://docs.langchain.com/oss/python/langchain/middleware)     docs for more information. (default: `()`) |
| `response_format` | `ResponseFormat[ResponseT] \| type[ResponseT] \| dict[str, Any] \| None` | No | An optional configuration for structured responses.  Can be a `ToolStrategy`, `ProviderStrategy`, or a Pydantic model class.  If provided, the agent will handle structured output during the conversation flow.  Raw schemas will be wrapped in an appropriate strategy based on model capabilities.  !!! tip ""      See the [Structured output](https://docs.langchain.com/oss/python/langchain/structured-output)     docs for more information. (default: `None`) |
| `state_schema` | `type[AgentState[ResponseT]] \| None` | No | An optional `TypedDict` schema that extends `AgentState`.  When provided, this schema is used instead of `AgentState` as the base schema for merging with middleware state schemas. This allows users to add custom state fields without needing to create custom middleware.  Generally, it's recommended to use `state_schema` extensions via middleware to keep relevant extensions scoped to corresponding hooks / tools. (default: `None`) |
| `context_schema` | `type[ContextT] \| None` | No | An optional schema for runtime context. (default: `None`) |
| `checkpointer` | `Checkpointer \| None` | No | An optional checkpoint saver object.  Used for persisting the state of the graph (e.g., as chat memory) for a single thread (e.g., a single conversation). (default: `None`) |
| `store` | `BaseStore \| None` | No | An optional store object.  Used for persisting data across multiple threads (e.g., multiple conversations / users). (default: `None`) |
| `interrupt_before` | `list[str] \| None` | No | An optional list of node names to interrupt before.  Useful if you want to add a user confirmation or other interrupt before taking an action. (default: `None`) |
| `interrupt_after` | `list[str] \| None` | No | An optional list of node names to interrupt after.  Useful if you want to return directly or run additional processing on an output. (default: `None`) |
| `debug` | `bool` | No | Whether to enable verbose logging for graph execution.  When enabled, prints detailed information about each node execution, state updates, and transitions during agent runtime. Useful for debugging middleware behavior and understanding agent execution flow. (default: `False`) |
| `name` | `str \| None` | No | An optional name for the `CompiledStateGraph`.  This name will be automatically used when adding the agent graph to another graph as a subgraph node - particularly useful for building multi-agent systems. (default: `None`) |
| `cache` | `BaseCache[Any] \| None` | No | An optional `BaseCache` instance to enable caching of graph execution. (default: `None`) |

## Returns

`CompiledStateGraph[AgentState[ResponseT], ContextT, _InputAgentState, _OutputAgentState[ResponseT]]`

A compiled `StateGraph` that can be used for chat interactions.

---

[View source on GitHub](https://github.com/langchain-ai/langchain/blob/666dc16b00070ec0184b9cfdafc0b212f5456762/libs/langchain_v1/langchain/agents/factory.py#L691)