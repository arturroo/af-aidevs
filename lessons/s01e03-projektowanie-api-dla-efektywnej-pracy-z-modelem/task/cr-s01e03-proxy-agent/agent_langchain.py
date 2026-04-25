import os
import json
import logging
from google.cloud import bigquery
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# following latest langchain docs: https://reference.langchain.com/python/langchain/agents/factory/create_agent
from langchain.agents import create_agent

# Use the proper MCP client over HTTP. 
from langchain_core.tools import tool
from fastmcp import Client as FastMCPClient
from fastmcp.client.transports import StreamableHttpTransport

logger = logging.getLogger("langchain_agent")
logger.setLevel(logging.INFO)

# BigQuery Logging
bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.getenv("BQ_AUDIT_TABLE") or "bq-s01e03-audit"

from config import load_system_message
SYSTEM_MESSAGE, METADATA = load_system_message()
# Retrieve MCP Server URL from ENV if we use SSE approach
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]

@tool
async def check_package(packageid: str) -> str:
    """Check the contents and current destination of a package."""
    return await mcp_call_tool("check_package", {"packageid": packageid})

@tool
async def redirect_package(packageid: str, destination: str, code: str) -> str:
    """Redirect a package using the confirmation code obtained from the operator."""
    return await mcp_call_tool("redirect_package", {"packageid": packageid, "destination": destination, "code": code})

def create_session(session_id: str):
    return {
        "session_id": session_id,
        "messages": [SystemMessage(content=SYSTEM_MESSAGE)]
    }

async def mcp_call_tool(tool_name: str, args: dict):
    # Use FastMCP native client with Streamable HTTP transport
    mcp_endpoint = f"{MCP_SERVER_URL}/mcp"
    transport = StreamableHttpTransport(url=mcp_endpoint)
    
    try:
        async with FastMCPClient(transport) as client:
            result = await client.call_tool(tool_name, args)
            # FastMCP Client returns a string result directly or a CallToolResult object
            if hasattr(result, 'content'):
                return result.content[0].text if result.content else ""
            return str(result)
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
    gc_location = os.getenv("GOOGLE_CLOUD_LOCATION") or "undefined"
    print(f"==== DEBUG ==== GOOGLE_CLOUD_LOCATION env var is: {gc_location}", flush=True)
    location = METADATA.get("model_region") or gc_location
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
    llm = ChatGoogleGenerativeAI(
        model=METADATA.get("model", "gemini-3.1-flash-lite-preview"),
        temperature=METADATA.get("temperature", 0.1),
        location=location,
        project=project_id,
        vertexai=True
    )
    
    # Fully dynamic MCP integration - tools are proxying to MCP server
    tools = [check_package, redirect_package]
    
    # We use the factory mentioned by the user
    proxy_agent_graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_MESSAGE
    )
    
    # Since tools are async, we MUST use ainvoke
    proxy_agent_run = await proxy_agent_graph.ainvoke({"messages": messages})
    print(f"==== DEBUG ==== proxy_agent_run is: {proxy_agent_run}", flush=True)

    # 3. Extract output message and handle complex content (list of blocks)
    last_ai_msg = proxy_agent_run.get("messages", [])[-1]
    
    if isinstance(last_ai_msg.content, list):
        msg_out = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in last_ai_msg.content
        )
    else:
        msg_out = str(last_ai_msg.content)
    
    # 4. Update session history and log
    messages.append(AIMessage(content=msg_out))
    log_to_bq(session_id, "agent", msg_out)
    
    return msg_out

