import json
import logging
import os
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from agents.base import BaseOkoAgent
from schemas import (
    CallOkoApiInput,
    FetchOkoPageInput,
    ListWorkspaceFilesInput,
    RunTaskResponse,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.oko_service import OkoService

logger = logging.getLogger("agents.langchain")


class LangChainOkoAgent(BaseOkoAgent):
    """LangChain 1.2.15 implementation for task okoeditor using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.oko = OkoService(mcp_service=self.mcp, audit_service=self.audit)

        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model or config.GEMINI_MODEL,
            temperature=self.prompt_config.temperature or 0.1,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location or config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=config.THINKING_LEVEL,
            include_thoughts=False,
        )

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        oko = self.oko
        mcp = self.mcp

        @tool(args_schema=CallOkoApiInput)
        async def call_oko_api(
            action: str,
            params: dict[str, Any] | None = None,
            reasoning: str = "",
        ) -> str:
            """Invokes Centrala backdoor API for task 'okoeditor'. Start with action='help', perform the 3 mutations, and finish with action='done'."""
            state_tracker["actions_taken"].append(action)
            try:
                resp = await oko.call_api(
                    session_id=session_id,
                    action=action,
                    params=params,
                    reasoning=reasoning,
                )
                if resp.message and "{FLG:" in resp.message:
                    state_tracker["flag"] = resp.message
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in call_oko_api for action '{action}': {e}")
                return json.dumps(
                    {"status": "error", "action": action, "code": -1, "message": str(e)}
                )

        @tool(args_schema=FetchOkoPageInput)
        async def fetch_oko_page(page: str = "incydenty", reasoning: str = "") -> str:
            """Covertly fetches a subpage from the operator OKO web panel (e.g. 'incydenty', 'zadania', 'notatki').
            Saves the raw HTML and converted Markdown to workspace, and returns discovered record IDs.
            """
            state_tracker["actions_taken"].append(f"fetch_oko_page_{page}")
            try:
                res = await oko.fetch_page(
                    session_id=session_id, page=page, reasoning=reasoning
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in fetch_oko_page for '{page}': {e}")
                return json.dumps({"status": "error", "page": page, "message": str(e)})

        @tool(args_schema=ListWorkspaceFilesInput)
        async def list_workspace_files(path: str = ".", reasoning: str = "") -> str:
            """Lists files and directories in the session workspace."""
            try:
                res = await mcp.list_files(
                    session_id=session_id, path=path, reasoning=reasoning
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in list_workspace_files for '{path}': {e}")
                return json.dumps({"status": "error", "error": str(e), "files": []})

        @tool
        async def write_workspace_file(
            file_path: str, content: str, reasoning: str
        ) -> str:
            """Writes artifacts, notes, or execution logs to cr-mcp-workspace."""
            res = await mcp.write_file(
                session_id=session_id,
                file_path=file_path,
                content=content,
                reasoning=reasoning,
            )
            return json.dumps(res, ensure_ascii=False)

        @tool
        async def read_workspace_file(file_path: str, reasoning: str) -> str:
            """Reads a file from cr-mcp-workspace."""
            res = await mcp.read_file(
                session_id=session_id, file_path=file_path, reasoning=reasoning
            )
            return json.dumps(res, ensure_ascii=False)

        tools = [
            call_oko_api,
            fetch_oko_page,
            list_workspace_files,
            read_workspace_file,
            write_workspace_file,
        ]
        for t in tools:
            t.handle_tool_error = True
        return tools

    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:

        logger.info(
            f"Starting LangChain execution for session {session_id} using {config.GEMINI_MODEL}"
        )

        state_tracker: dict[str, Any] = {
            "flag": None,
            "actions_taken": [],
            "reasoning": "",
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized LangChain session {session_id} for task okoeditor",
            step_type="SESSION_START",
            metadata={"model": config.GEMINI_MODEL, "backend": "langchain"},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)
        bq_callback = BigQueryCallbackHandler(
            audit_service=self.audit, session_id=session_id
        )

        agent_graph = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
        )

        user_goal = (
            "Execute covert record adjustments in Centrum Operacyjne OKO via the backdoor API.\n"
            "1. Query call_oko_api with action='help' to discover available commands, queries, and mutation parameters.\n"
            "2. Locate the incident report for Skolwin and reclassify it from vehicle/human sighting to animal activity.\n"
            "3. Locate the operational task for Skolwin, mark it as completed/done, and record in its notes that animals (e.g. beavers / bobry) were sighted.\n"
            "4. Add a diversion incident report detecting human activity near the uninhabited town of Komarowo.\n"
            "5. Verify everything and trigger action='done' to capture the course flag {FLG:...}.\n"
            "Remember: NEVER access the web panel UI directly. Use only call_oko_api."
        )

        try:
            response = await agent_graph.ainvoke(
                {"messages": [{"role": "user", "content": user_goal}]},
                config={"callbacks": [bq_callback], "recursion_limit": recursion_limit},
            )
            if (
                isinstance(response, dict)
                and "messages" in response
                and response["messages"]
            ):
                last_msg = response["messages"][-1]
                raw_content = getattr(last_msg, "content", str(last_msg))
                if isinstance(raw_content, list):
                    state_tracker["reasoning"] = "\n".join(
                        item.get("text", str(item))
                        if isinstance(item, dict)
                        else str(item)
                        for item in raw_content
                    )
                else:
                    state_tracker["reasoning"] = str(raw_content)

        except Exception as e:
            logger.error(f"LangChain invocation error: {e}")
            await self.audit.log_event(
                session_id=session_id,
                actor="agent",
                content=f"LangChain error: {e}",
                step_type="AGENT_ERROR",
                metadata={"error": str(e)},
            )

        flag = state_tracker["flag"]
        safe_flag = "[REDACTED_FLAG]" if flag else "None"
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Completed task okoeditor. Flag: {safe_flag}",
            step_type="SESSION_COMPLETE",
            flag=flag,
            metadata={"actions_count": len(state_tracker["actions_taken"])},
        )

        return RunTaskResponse(
            status="success" if flag else "error",
            backend="langchain",
            session_id=session_id,
            flag=flag or "[NO_FLAG_OBTAINED]",
            actions_taken=state_tracker["actions_taken"],
            reasoning=state_tracker["reasoning"]
            or "Covert OKO records adjustment sequence executed.",
        )
