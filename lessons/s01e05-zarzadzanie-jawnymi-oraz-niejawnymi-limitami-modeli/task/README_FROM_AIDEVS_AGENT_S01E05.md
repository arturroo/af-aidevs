# Agent API

Multi-provider AI agent server with tool execution, MCP integration, and markdown-based agent templates.

## Quick Start

```bash
npm install
cp .env.example .env   # fill in API keys
npm run db:push         # create SQLite tables
npm run db:seed         # seed default user
npm run dev             # start dev server (http://127.0.0.1:3000)
```

## Example Requests

Send a message to the `alice` agent:

```bash
curl -s http://127.0.0.1:3000/api/chat/completions \
  -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" \
  -H "Content-Type: application/json" \
  -d '{"agent":"alice","input":"What is 42 * 17?"}' | jq
```

Multi-turn conversation — first call returns a `sessionId`, second call continues with streaming:

```bash
SESSION=$(curl -s http://127.0.0.1:3000/api/chat/completions \
  -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" \
  -H "Content-Type: application/json" \
  -d '{"agent":"alice","input":"Remember: my name is Adam"}' | jq -r '.data.sessionId')

curl -N http://127.0.0.1:3000/api/chat/completions \
  -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" \
  -H "Content-Type: application/json" \
  -d "{\"agent\":\"alice\",\"sessionId\":\"$SESSION\",\"input\":\"What is my name?\",\"stream\":true}"
```

Use a specific model without an agent template:

```bash
curl -s http://127.0.0.1:3000/api/chat/completions \
  -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai:gpt-4.1-mini","input":"Say hello"}' | jq
```

Check health:

```bash
curl -s http://127.0.0.1:3000/health | jq
```

List MCP servers:

```bash
curl -s http://127.0.0.1:3000/api/mcp/servers \
  -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" | jq
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | one of | OpenAI API key |
| `GEMINI_API_KEY` | one of | Google Gemini API key |
| `AUTH_TOKEN` | yes | Bearer token for API authentication |
| `DATABASE_URL` | no | SQLite path, e.g. `file:.data/agent.db`. Omit for in-memory. |
| `DATABASE_AUTH_TOKEN` | no | LibSQL auth token (Turso) |
| `WORKSPACE_PATH` | no | Agent templates directory. Default: `./workspace` |
| `PORT` | no | Server port. Default: `3000` |
| `HOST` | no | Bind address. Default: `127.0.0.1` |
| `CORS_ORIGIN` | no | Allowed origins. Default: `*` |
| `BODY_LIMIT` | no | Max request body in bytes. Default: `1048576` |
| `TIMEOUT_MS` | no | Request timeout in ms. Default: `60000` |
| `AGENT_MAX_TURNS` | no | Max agentic loop turns. Default: `10` |
| `LANGFUSE_SECRET_KEY` | no | Langfuse secret key for tracing |
| `LANGFUSE_PUBLIC_KEY` | no | Langfuse public key for tracing |
| `LANGFUSE_BASE_URL` | no | Langfuse API URL. Default: `https://cloud.langfuse.com` |

## Authentication

API requests require a `Bearer` token in the `Authorization` header. Tokens are hashed (SHA-256) and matched against users in the database.

```bash
# Seed creates a default user with this key:
curl -H "Authorization: Bearer 0f47acce-3aa7-4b58-9389-21b2940ecc70" ...
```

## API Endpoints

### Chat

**`POST /api/chat/completions`** — Run an agent turn.

```json
{
  "agent": "alice",
  "input": "What is 42 * 17?",
  "model": "openai:gpt-4.1",
  "stream": false,
  "sessionId": "optional-session-id",
  "temperature": 0.7,
  "maxTokens": 4096,
  "instructions": "Override system prompt",
  "tools": [
    { "type": "function", "name": "my_tool", "description": "...", "parameters": {} },
    { "type": "web_search" }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `agent` | string? | Load agent template from `workspace/agents/{name}.agent.md` |
| `input` | string \| array | User message or structured input items |
| `model` | string? | `provider:model` format. Default: `openai:gpt-4.1` |
| `stream` | boolean? | SSE streaming. Default: `false` |
| `sessionId` | string? | Resume existing session |
| `instructions` | string? | Override system prompt (overrides agent template) |
| `tools` | array? | Override tools (overrides agent template) |
| `temperature` | number? | 0–2 |
| `maxTokens` | number? | Max output tokens |

Response:

```json
{
  "data": {
    "id": "agent-uuid",
    "sessionId": "session-uuid",
    "status": "completed",
    "model": "openai:gpt-4.1",
    "output": [
      { "type": "text", "text": "714" },
      { "type": "function_call", "callId": "...", "name": "calculator", "arguments": {} }
    ],
    "waitingFor": []
  },
  "error": null
}
```

Status `completed` returns `200`. Status `waiting` returns `202` with `waitingFor` describing pending tool calls.

**`POST /api/chat/agents/:agentId/deliver`** — Deliver result to a waiting agent.

```json
{
  "callId": "call-uuid",
  "output": "{\"result\": \"done\"}",
  "isError": false
}
```

**`GET /api/chat/agents/:agentId`** — Get agent status.

### MCP Servers

**`GET /api/mcp/servers`** — List MCP servers and connection status.

```json
{
  "data": {
    "servers": [
      { "name": "files", "status": "connected" },
      { "name": "remote", "status": "auth_required" }
    ]
  }
}
```

**`GET /api/mcp/:server/auth`** — Get OAuth authorization URL for a server that requires auth.

**`GET /mcp/:server/callback`** — OAuth redirect target (public, no auth). Renders a styled HTML page with connection status.

### Health

**`GET /health`** — Returns `{ "status": "ok" }`.

## Agent Templates

Define agents as markdown files in `workspace/agents/`. The filename is `{name}.agent.md`.

```markdown
---
name: alice
model: gemini:gemini-3-flash-preview
tools:
  - calculator
  - web_search
  - files__fs_read
  - files__fs_write
---

You are Alice, a helpful assistant.

## Guidelines

1. Always use tools when appropriate.
2. Be concise.
```

**Frontmatter fields:**

| Field | Description |
|---|---|
| `name` | Agent name (defaults to filename) |
| `model` | `provider:model` format. Default: `openai:gpt-4.1` |
| `tools` | Array of tool names |

**Body** is the system prompt (instructions).

Templates are read from disk on every request — edit and test without restart.

## Tools

### Built-in

| Name | Type | Description |
|---|---|---|
| `calculator` | sync | Basic math: `add`, `subtract`, `multiply`, `divide` |
| `web_search` | native | Provider-native web search (OpenAI: `web_search_preview`, Gemini: `google_search`) |

### MCP Tools

MCP tools are prefixed with `server__toolName`. Reference them in agent templates:

```yaml
tools:
  - files__fs_read
  - files__fs_write
```

Available MCP tools depend on connected servers. Use `GET /api/mcp/servers` to check status.

## MCP Configuration

### `.mcp.json`

Place in project root. Defines MCP server connections.

```json
{
  "mcpServers": {
    "files": {
      "transport": "stdio",
      "command": "npx",
      "args": ["tsx", "../mcp/files-mcp/src/index.ts"],
      "env": {
        "LOG_LEVEL": "info",
        "FS_ROOT": "./workspace"
      }
    },
    "remote": {
      "transport": "http",
      "url": "https://mcp-server.example.com/mcp",
      "headers": {
        "X-Custom": "value"
      }
    }
  }
}
```

**Stdio servers** spawn a child process. Fields: `command`, `args`, `env`, `cwd`.

**HTTP servers** connect over Streamable HTTP. Fields: `url`, `headers`. OAuth is handled automatically — if the server returns `401`, the OAuth flow starts.

### `.mcp.oauth.json`

Auto-generated. Stores OAuth tokens per server. **Gitignored** — never commit.

### OAuth Flow

1. Server starts → connects to MCP servers
2. HTTP server returns 401 → status becomes `auth_required`
3. `GET /api/mcp/:server/auth` → returns `authorizationUrl`
4. Open URL in browser → authorize → redirected to `/mcp/:server/callback`
5. Callback exchanges code for tokens → connection established
6. Tokens persist in `.mcp.oauth.json` across restarts

## Providers

Models use `provider:model` format:

| Provider | Example models |
|---|---|
| `openai` | `openai:gpt-4.1`, `openai:gpt-4.1-mini` |
| `gemini` | `gemini:gemini-3-flash-preview`, `gemini:gemini-2.5-pro-preview-05-06` |

## Database

SQLite via Drizzle ORM. Tables: `users`, `sessions`, `agents`, `items`.

```bash
npm run db:push      # apply schema to database
npm run db:seed      # seed default user
npm run db:generate  # generate migration files
npm run db:migrate   # run migrations
npm run db:studio    # open Drizzle Studio UI
```

## Project Structure

```
src/
  index.ts              # entry point
  lib/
    app.ts              # Hono app, middleware
    config.ts           # env config
    runtime.ts          # runtime init (providers, tools, MCP, agents)
  routes/
    chat.ts             # chat endpoints
    chat.schema.ts      # request validation
    chat.service.ts     # chat business logic
    mcp.ts              # MCP OAuth endpoints
  runtime/
    runner.ts           # agentic loop (turn execution, tool handling)
    context.ts          # runtime + execution context types
  providers/
    openai/adapter.ts   # OpenAI Responses API adapter
    gemini/adapter.ts   # Gemini Interactions API adapter
    registry.ts         # provider registry
  domain/
    agent.ts            # agent entity, state transitions
    session.ts          # session entity
    item.ts             # conversation items (message, function_call, etc.)
  tools/
    registry.ts         # tool registry
    definitions/        # built-in tool implementations
  mcp/
    client.ts           # MCP client manager
    oauth.ts            # OAuth provider (file-backed tokens)
    types.ts            # MCP config types
  workspace/
    loader.ts           # agent template loader (frontmatter + markdown)
  repositories/
    sqlite/             # Drizzle ORM repository implementation
    memory.ts           # in-memory repository (no database)
  middleware/
    auth.ts             # bearer token authentication
  db/
    seed.ts             # database seeder

workspace/
  agents/
    alice.agent.md      # agent template
```
