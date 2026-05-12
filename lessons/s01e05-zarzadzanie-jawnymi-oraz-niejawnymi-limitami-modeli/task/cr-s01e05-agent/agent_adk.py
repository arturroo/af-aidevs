import os
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

from langfuse.decorators import observe

from schemas import AgentResponse
from utils.prompts import load_system_prompt
from utils.audit import log_to_bq
from tools.api_call import APICallTool
from tools.get_current_date import get_current_date

logger = logging.getLogger(__name__)

api_tool_instance = APICallTool()

@observe(as_type="generation", name="adk_chat")
async def _send_message(chat, message):
    return await asyncio.to_thread(chat.send_message, message)

@observe(as_type="tool", name="api_call")
def adk_api_call(reasoning: str, answer: dict) -> str:
    """Calls the central /verify API to perform tasks. Provide reasoning and the 'answer' payload."""
    try:
        res = api_tool_instance._run(reasoning=reasoning, answer=answer)
        return json.dumps(res)
    except Exception as e:
        return json.dumps({"error": str(e)})

@observe(as_type="tool", name="get_current_date")
def adk_get_current_date() -> str:
    """Returns the current date and time."""
    return get_current_date.invoke({})

@observe(name="run_adk_agent")
async def run_adk_agent(base_dir: Path):
    session_id = f"session_adk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Starting ADK Agent Session: {session_id}")
    
    config = load_system_prompt(base_dir)
    google_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    client = genai.Client(vertexai=True, project=google_project, location=config.model_region)
    
    tools = [adk_api_call, adk_get_current_date]
    
    chat_config = types.GenerateContentConfig(
        system_instruction=config.system_prompt,
        temperature=config.temperature,
        tools=tools,
    )
    
    chat = client.chats.create(
        model=config.model,
        config=chat_config
    )
    
    initial_message = "Start the railway task by checking the API help action."
    await log_to_bq(session_id, "user", initial_message)
    
    logger.info("Sending initial message...")
    response = await _send_message(chat, initial_message)
    
    while True:
        if response.function_calls:
            parts = []
            for function_call in response.function_calls:
                fn_name = function_call.name
                fn_args = function_call.args
                
                logger.info(f"Agent requested tool call: {fn_name}")
                await log_to_bq(session_id, "agent", f"Tool Call: {fn_name}", metadata={"args": fn_args})
                
                if fn_name == "adk_api_call":
                    tool_result_str = adk_api_call(**fn_args)
                elif fn_name == "adk_get_current_date":
                    tool_result_str = adk_get_current_date()
                else:
                    tool_result_str = json.dumps({"error": "Unknown tool"})
                    
                try:
                    res_json = json.loads(tool_result_str)
                    metadata = None
                    if "headers" in res_json:
                        metadata = {
                            "headers": res_json["headers"],
                            "status_code": res_json.get("status_code"),
                        }
                    await log_to_bq(session_id, "tool", tool_result_str, metadata=metadata)
                except Exception:
                    await log_to_bq(session_id, "tool", tool_result_str)
                
                parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": tool_result_str}
                    )
                )
            
            logger.info("Sending tool results back to the model...")
            response = await _send_message(chat, parts)
            
        elif response.text:
            text = response.text
            logger.info(f"Agent reply:\n{text}")
            await log_to_bq(session_id, "agent", text)
            
            if "{FLG:" in text:
                logger.info("Found flag! Task complete.")
                break
            else:
                logger.info("No tool calls and no flag yet. Exiting loop.")
                break
        else:
            logger.warning("Empty response or unknown type.")
            break
