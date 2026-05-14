import os
import json
import asyncio
import base64
import logging
import importlib
import sys
from typing import List, Dict, Any, Optional, Annotated, Sequence, Union
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery

# LangChain / LangGraph imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain.agents import create_agent
from schemas import AgentResponse

load_dotenv()

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SPK_Agent_v5")

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[2]
sys.path.extend([str(BASE_DIR), str(ROOT_DIR / "python_packages")])

from af_aidevs.utils.prompts import load_system_prompt

# Constants from environment
AIDEVS_VERIFY = os.getenv("AIDEVS_VERIFY")
BQ_AUDIT_TABLE = os.getenv("BQ_AUDIT_TABLE") or "af-aidevs.s01e04.audit"
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

bq_client = bigquery.Client(project=GOOGLE_CLOUD_PROJECT, location="europe-west6")
ZURICH_TZ = ZoneInfo("Europe/Zurich")

# Debug Environment
gc_location = os.getenv("GOOGLE_CLOUD_LOCATION") or "undefined"
print(f"==== DEBUG ==== GOOGLE_CLOUD_LOCATION env var is: {gc_location}", flush=True)
print(f"==== DEBUG ==== Current Working Directory (CWD) is: {os.getcwd()}", flush=True)
print(f"==== DEBUG ==== Sandbox (DATA_DIR) path is: {BASE_DIR / 'data'}", flush=True)

async def log_to_bq(session_id: str, actor: str, content: str, metadata: Optional[Dict] = None):
    """Audits interaction to BigQuery asynchronously."""
    
    def _do_insert():
        try:
            row = {
                "timestamp": datetime.now(ZURICH_TZ).isoformat(),
                "session_id": session_id,
                "actor": actor,
                "content": content,
                "metadata": json.dumps(metadata) if metadata else None
            }
            if BQ_AUDIT_TABLE and "." in BQ_AUDIT_TABLE:
                errors = bq_client.insert_rows_json(BQ_AUDIT_TABLE, [row])
                if errors:
                    logger.error(f"BQ Audit Error: {errors}")
            else:
                logger.info(f"[Audit Log] {actor}: {content[:100]}...")
        except Exception as e:
            logger.error(f"Failed to log to BQ: {e}")

    # Run the blocking BQ call in a separate thread to keep the event loop free
    await asyncio.to_thread(_do_insert)

# --- Tool Discovery ---

# --- Tool Discovery ---

def load_all_tools():
    """Dynamically loads all tools from the tools/ directory for the Agent Graph."""
    tools_list = []
    tools_path = Path(BASE_DIR) / "tools"

    print(f"==== DEBUG ==== tools_path: {tools_path}", flush=True)

    for file_path in tools_path.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        module_name = f"tools.{file_path.stem}"
        try:
            module = importlib.import_module(module_name)
            tool_func = getattr(module, file_path.stem)
            # LangChain @tool decorator creates objects that may not pass callable()
            # We check if they have the standard tool attributes instead
            if hasattr(tool_func, "name") and hasattr(tool_func, "invoke"):
                tools_list.append(tool_func)
                print(f"==== DEBUG ==== [Discovery] Registered tool: {file_path.stem}", flush=True)
                logger.info(f"[Discovery] Registered tool: {file_path.stem}")
            else:
                print(f"==== DEBUG ==== [Discovery] Tool {file_path.stem} is not a valid LangChain Tool", flush=True)
                logger.error(f"[Discovery] Tool {file_path.stem} is not a valid LangChain Tool")
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load tool {file_path.name}: {e}")
            
    return tools_list

# Register ALL tools in the graph, but tell the agent to DISCOVER them
ALL_TOOLS = load_all_tools()

# Load System Prompt and Configuration
config = load_system_prompt(BASE_DIR)

# Initialize Model (Dynamic from frontmatter config)
llm = ChatGoogleGenerativeAI(
    model=config.model,
    temperature=config.temperature,
    project=GOOGLE_CLOUD_PROJECT,
    location=config.location,
    vertexai=True
)

# Create structured variant for final answers
llm_structured = llm.with_structured_output(AgentResponse)

# Create the Agent using the Factory Pattern
agent_executor = create_agent(
    model=llm,
    tools=ALL_TOOLS,
    system_prompt=config.system_prompt + "\n\nIMPORTANT: At the start of the session, you MUST use the 'discover_tools' capability to learn about your specialized skills. Do not assume tool names."
)

async def run_autonomous_loop():
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting Modern Agent Session: {session_id}")
    
    # Initial state
    messages = [HumanMessage(content="Start investigation of local files and the Hub to fill the declaration.")]
    
    # We run the agent. LangGraph's create_agent (internally ReAct) handles the loop.
    async for event in agent_executor.astream({"messages": messages}, stream_mode="values"):
        last_msg = event["messages"][-1]
        
        # Auditing every interaction
        actor = "agent" if isinstance(last_msg, AIMessage) else "user" if isinstance(last_msg, HumanMessage) else "tool"
        
        # content can be str or list (multimodal)
        raw_content = last_msg.content
        content_to_log = str(raw_content)
        metadata = None
        
        # Special handling for structured tool outputs
        if isinstance(last_msg, ToolMessage):
            parsed = None
            if isinstance(raw_content, dict):
                parsed = raw_content
            elif isinstance(raw_content, str):
                try:
                    parsed = json.loads(raw_content)
                except json.JSONDecodeError:
                    pass
            
            if isinstance(parsed, dict):
                # Extract headers for metadata if present (from http_get or submit)
                if "headers" in parsed:
                    metadata = parsed["headers"]
                    if "status" in parsed:
                        metadata["status"] = parsed["status"]
                
                # Determine what to show in 'content' column in BQ
                if "body" in parsed:
                    content_to_log = str(parsed["body"])
                elif "content" in parsed:
                    content_to_log = str(parsed["content"])
                elif "filename" in parsed and actor == "tool":
                    content_to_log = f"File processed: {parsed['filename']}"
                elif "files" in parsed:
                    content_to_log = f"Files found: {', '.join(parsed['files'])}"
                elif "error" in parsed and parsed["error"]:
                    content_to_log = f"ERROR: {parsed['error']}"
                else:
                    content_to_log = json.dumps(parsed)
        
        await log_to_bq(session_id, actor, content_to_log, metadata=metadata)
        
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
            # Enforce Structured Output for the final response to get reasoning
            print("\n--- Generating Structured Final Response ---")
            structured_msg = await llm_structured.ainvoke(event["messages"])
            
            # Log final structured response with reasoning
            await log_to_bq(
                session_id, 
                "agent", 
                structured_msg.answer, 
                metadata={"reasoning": structured_msg.reasoning, "type": "structured_final_response"}
            )
            
            print(f"\nREASONING:\n{structured_msg.reasoning}")
            print(f"\nFINAL ANSWER:\n{structured_msg.answer}")
            break

if __name__ == "__main__":
    asyncio.run(run_autonomous_loop())
