import os
import json
import logging
from datetime import datetime
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain.agents import create_agent

from schemas import AgentResponse
from utils.prompts import load_system_prompt
from utils.audit import log_to_bq
from tools.api_call import APICallTool
from tools.get_current_date import get_current_date

logger = logging.getLogger(__name__)

async def run_langchain_agent(base_dir: Path):
    session_id = f"session_langchain_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Starting Langchain Agent Session: {session_id}")
    
    config = load_system_prompt(base_dir)
    google_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    llm = ChatGoogleGenerativeAI(
        model=config.model,
        temperature=config.temperature,
        project=google_project,
        location=config.model_region,
        vertexai=True
    )
    
    llm_structured = llm.with_structured_output(AgentResponse)
    
    tools = [APICallTool(), get_current_date]
    
    # Optional LangSmith tracking (configured via env variables in main.py)
    agent_executor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=config.system_prompt
    )
    
    messages = [HumanMessage(content="Start the railway task by checking the API help action.")]
    
    async for event in agent_executor.astream({"messages": messages}, stream_mode="values"):
        last_msg = event["messages"][-1]
        
        actor = "agent" if isinstance(last_msg, AIMessage) else "user" if isinstance(last_msg, HumanMessage) else "tool"
        
        content_to_log = str(last_msg.content)
        metadata = None
        
        if isinstance(last_msg, ToolMessage):
            parsed = None
            if isinstance(last_msg.content, dict):
                parsed = last_msg.content
            elif isinstance(last_msg.content, str):
                try:
                    parsed = json.loads(last_msg.content)
                except Exception:
                    pass
            
            if isinstance(parsed, dict):
                if "headers" in parsed:
                    metadata = {
                        "headers": parsed["headers"],
                        "status_code": parsed.get("status_code"),
                        "reasoning_provided": parsed.get("reasoning_provided")
                    }
                if "body" in parsed:
                    content_to_log = str(parsed["body"])
                elif "error" in parsed:
                    content_to_log = f"ERROR: {parsed['error']}"
                else:
                    content_to_log = json.dumps(parsed)
        
        await log_to_bq(session_id, actor, content_to_log, metadata=metadata)
        
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
            logger.info("Generating Structured Final Response...")
            structured_msg = await llm_structured.ainvoke(event["messages"])
            
            await log_to_bq(
                session_id, 
                "agent", 
                structured_msg.answer, 
                metadata={"reasoning": structured_msg.reasoning, "type": "structured_final_response"}
            )
            
            logger.info(f"REASONING:\n{structured_msg.reasoning}")
            logger.info(f"FINAL ANSWER:\n{structured_msg.answer}")
            break
