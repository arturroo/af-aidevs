import os
import json
import logging
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
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
AUDIT_TABLE_ID = os.getenv("BQ_AUDIT_TABLE") or "bq-s01e03-audit"

from config import load_system_message
SYSTEM_MESSAGE, METADATA = load_system_message()
# Retrieve MCP Server URL from ENV if we use SSE approach
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]

def create_session(session_id: str):
    return {
        "session_id": session_id,
        "messages": [SystemMessage(content=SYSTEM_MESSAGE)]
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
    env_loc = os.getenv("GOOGLE_CLOUD_LOCATION")
    print(f"==== DEBUG ==== GOOGLE_CLOUD_LOCATION env var is: {env_loc}", flush=True)
    location = METADATA.get("model_region") or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "af-aidevs")
    llm = ChatVertexAI(
        model_name=METADATA.get("model_name", "gemini-3.1-flash-lite-preview"),
        temperature=METADATA.get("temperature", 0.1),
        location=location,
        project=project_id
    )
    
    # For a fully dynamic MCP integration, one pulls tools from MCP first.
    # Here we simulate the boilerplate loop.
    
    # Note: students fill in the Tool abstraction logic to map LangChain Tool -> MCP call.
    # This is part of the boilerplate the student has to finish.
    
    response = llm.invoke(messages)
    
    # Very basic return logic, assuming we don't process tool calling logic inside this stub
    # The student will expand this to handle tool_calls.
    
    # Extract string from complex content block (e.g. Gemini 3.1 thought signatures)
    if isinstance(response.content, list):
        msg_out = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in response.content
        )
    else:
        msg_out = str(response.content)
        
    messages.append(AIMessage(content=msg_out))
    log_to_bq(session_id, "agent", msg_out)
    
    return msg_out
