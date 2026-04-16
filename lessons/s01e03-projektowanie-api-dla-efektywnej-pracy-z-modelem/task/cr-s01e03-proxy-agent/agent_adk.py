import os
import json
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, ChatSession, Content, Part
from google.cloud import bigquery
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

logger = logging.getLogger("adk_agent")
logger.setLevel(logging.INFO)

# BigQuery Logging
bq_client = bigquery.Client()
AUDIT_TABLE_ID = os.environ.get("BQ_AUDIT_TABLE", "bq-s01e03-audit")

# System message parsing
SYSTEM_PROMPT = ""
try:
    with open("system_message.md", "r", encoding="utf-8") as f:
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

MCP_SERVER_URL = os.environ["AIDEVS_MCP_HTTP_URL"]

# Vertex AI Initialization
# Make sure to set GOOGLE_CLOUD_PROJECT or have ADC properly configured.
vertexai.init()
model = GenerativeModel(
    "gemini-3.1-flash-lite-preview",
    system_instruction=[SYSTEM_PROMPT]
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
