import os
import json
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, ChatSession, Content, Part, GenerationConfig
from google.cloud import bigquery
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

logger = logging.getLogger("adk_agent")
logger.setLevel(logging.INFO)

# BigQuery Logging
bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.getenv("BQ_AUDIT_TABLE") or "bq-s01e03-audit"

from config import load_system_message
SYSTEM_MESSAGE, METADATA = load_system_message()
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]

# Vertex AI Initialization
project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "af-aidevs")
env_loc = os.getenv("GOOGLE_CLOUD_LOCATION")
print(f"==== DEBUG ==== GOOGLE_CLOUD_LOCATION env var is: {env_loc}", flush=True)
location = METADATA.get("model_region") or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
vertexai.init(project=project_id, location=location)

generation_config = GenerationConfig(
    temperature=METADATA.get("temperature", 0.1),
    top_p=METADATA.get("top_p", 0.95),
    top_k=METADATA.get("top_k", 40),
    max_output_tokens=METADATA.get("max_output_tokens", 1000),
)

model = GenerativeModel(
    METADATA.get("model", "gemini-3-flash-preview"),
    system_instruction=[SYSTEM_MESSAGE],
    generation_config=generation_config
)

def create_session(session_id: str):
    # Create an ADK native ChatSession
    chat = model.start_chat()
    return {
        "session_id": session_id,
        "chat": chat
    }

async def mcp_call_tool(tool_name: str, args: dict):
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
    chat: ChatSession = session_data["chat"]
    
    log_to_bq(session_id, "user", msg)
    
    # Send message to Vertex AI ChatSession
    # Students must implement function calling binding via model tools logic here.
    
    response = chat.send_message(msg)
    msg_out = response.text
    
    log_to_bq(session_id, "agent", msg_out)
    
    return msg_out
