import os
import json
import logging
from langchain_google_vertexai import ChatVertexAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from google.cloud import bigquery

# We can import MCP tools if we want to run natively via FastMCP instance
# or we can use the proper MCP client over HTTP. 
# For now, we will structure the boilerplate to connect over HTTP to MCP Tool Server.
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

logger = logging.getLogger("langchain_agent")
logger.setLevel(logging.INFO)

# BigQuery Logging
bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.environ.get("BQ_AUDIT_TABLE", "bq-s01e03-audit")

# System message parsing
SYSTEM_PROMPT = ""
try:
    with open("system_message.md", "r", encoding="utf-8") as f:
        # Simplistic parsing skipping frontmatter based on '---'
        lines = f.readlines()
        in_frontmatter = False
        content_lines = []
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if i == 0:
                    in_frontmatter = True
                    continue
                elif in_frontmatter:
                    in_frontmatter = False
                    continue
            if not in_frontmatter:
                content_lines.append(line)
        SYSTEM_PROMPT = "".join(content_lines).strip()
except Exception as e:
    logger.error(f"Failed to load system_message.md: {e}")
    SYSTEM_PROMPT = "You are a helpful assistant."

# Retrieve MCP Server URL from ENV if we use SSE approach
MCP_SERVER_URL = os.environ["AIDEVS_MCP_HTTP_URL"]

def create_session(session_id: str):
    return {
        "session_id": session_id,
        "messages": [SystemMessage(content=SYSTEM_PROMPT)]
    }

async def mcp_call_tool(tool_name: str, args: dict):
    # This is a generic way to call MCP tools over SSE using mcp SDK
    # In a full robust loop, we setup ClientSession once and keep it alive, but here's a placeholder struct.
    # Note: real use of `sse_client` is an async context manager.
    try:
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                return result.content[0].text if result.content else ""
    except Exception as e:
        logger.error(f"MCP Call error: {e}")
        return json.dumps({"error": str(e)})

def log_to_bq(session_id: str, actor: str, content: str):
    try:
        row = {"session_id": session_id, "actor": actor, "content": content}
        if "." in AUDIT_TABLE_ID:
            errors = bq_client.insert_rows_json(AUDIT_TABLE_ID, [row])
            if errors:
                logger.error(f"BQ Audit Error: {errors}")
        else:
            logger.info(f"Audit log (Dry-Run): {row}")
    except Exception as e:
        logger.error(f"Failed to log to BQ: {e}")

async def process_message(session_data: dict, msg: str) -> str:
    session_id = session_data["session_id"]
    messages = session_data["messages"]
    
    # 1. Append user message
    messages.append(HumanMessage(content=msg))
    log_to_bq(session_id, "user", msg)
    
    # 2. Setup llm
    # We use preview model from system_message.md
    llm = ChatVertexAI(
        model_name="gemini-3.1-flash-lite-preview",
        temperature=0.1
    )
    
    # For a fully dynamic MCP integration, one pulls tools from MCP first.
    # Here we simulate the boilerplate loop.
    
    # Note: students fill in the Tool abstraction logic to map LangChain Tool -> MCP call.
    # This is part of the boilerplate the student has to finish.
    
    response = llm.invoke(messages)
    
    # Very basic return logic, assuming we don't process tool calling logic inside this stub
    # The student will expand this to handle tool_calls.
    
    msg_out = response.content
    messages.append(AIMessage(content=msg_out))
    log_to_bq(session_id, "agent", msg_out)
    
    return msg_out
