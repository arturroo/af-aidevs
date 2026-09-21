import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from agents.base import BaseWindpowerAgent
from schemas import (
    ExecuteTurbineScheduleInput,
    ProbeWindpowerApiInput,
    RunTaskResponse,
    SaveDiscoveryNotesInput,
    TurbineConfigPoint,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.windpower_service import WindpowerService

logger = logging.getLogger("agents.langchain")


class LangChainWindpowerAgent(BaseWindpowerAgent):
    """LangChain 1.2.15 implementation for task windpower using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.windpower = WindpowerService(
            mcp_service=self.mcp, audit_service=self.audit
        )

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
        wp = self.windpower

        @tool(args_schema=ProbeWindpowerApiInput)
        async def probe_windpower_api(
            action: str,
            params: dict[str, Any] | None = None,
            auto_drain: bool = True,
            reasoning: str = "",
        ) -> str:
            """Probes Centrala's windpower API during Phase 1 (unbounded time) starting with action='help'. When action='get', automatically drains asynchronous reports."""
            state_tracker["actions_taken"].append(f"probe_{action}")
            try:
                resp = await wp.probe_api(
                    session_id=session_id,
                    action=action,
                    params=params,
                    reasoning=reasoning,
                    auto_drain=auto_drain,
                )
                if resp.message and "{FLG:" in resp.message:
                    state_tracker["flag"] = resp.message
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in probe_windpower_api for action '{action}': {e}")
                return json.dumps(
                    {"status": "error", "action": action, "code": -1, "message": str(e)}
                )

        @tool(args_schema=SaveDiscoveryNotesInput)
        async def save_discovery_notes(
            file_path: str = "discovery_notes.md",
            notes_content: str = "",
            reasoning: str = "",
        ) -> str:
            """Saves discovered API specifications and turbine parameters into the session workspace."""
            state_tracker["actions_taken"].append(f"save_notes_{file_path}")
            try:
                res = await wp.save_discovery_notes(
                    session_id=session_id,
                    file_path=file_path,
                    notes_content=notes_content,
                    reasoning=reasoning,
                )
                return json.dumps(res.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in save_discovery_notes: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        @tool(args_schema=ExecuteTurbineScheduleInput)
        async def execute_turbine_schedule(
            reasoning: str,
            configs: list[TurbineConfigPoint] | None = None,
        ) -> str:
            """Executes the high-speed Phase 2 hardware configuration within the 40s battery window using the agent's scheduled configuration points."""
            state_tracker["actions_taken"].append("execute_turbine_schedule")
            try:
                res = await wp.execute_schedule(
                    session_id=session_id,
                    configs=configs,
                    reasoning=reasoning,
                )
                if res.flag and "{FLG:" in res.flag:
                    state_tracker["flag"] = res.flag
                state_tracker["scheduled_points"] = res.scheduled_points
                state_tracker["solver_duration"] = res.execution_time_seconds
                return json.dumps(res.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in execute_turbine_schedule: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        return [
            probe_windpower_api,
            save_discovery_notes,
            execute_turbine_schedule,
        ]

    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        """Executes the two-phase wind turbine autonomous workflow via LangChain 1.2.15."""
        start_time = time.monotonic()
        state_tracker: dict[str, Any] = {
            "actions_taken": [],
            "flag": None,
            "scheduled_points": [],
            "solver_duration": 0.0,
        }

        tools = self._create_tools(session_id, state_tracker)
        bq_handler = BigQueryCallbackHandler(
            audit_service=self.audit, session_id=session_id
        )

        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
        )

        initial_user_message = (
            "Zainicjuj zadanie 'windpower'. Utrzymuj na bieżąco listę zadań w `todo.md` w workspace (wzorzec S02). "
            "Rozpocznij od badania API z action='help' (Faza 1). Zbadaj dokumentację ('get: documentation'), "
            "zapisz specyfikację w workspace ('turbine_specs.md'), pobierz prognozę pogody ('get: weather') i deficyt "
            "elektrowni ('get: powerplantcheck'). Zaplanuj pełny harmonogram punktów konfiguracji turbiny w pamięci "
            "(zabezpieczenie przed wichurami > 14 m/s kątem 90° idle oraz zaspokojenie deficytu elektrowni kątem 0° production) "
            "i dopiero mając gotowy plan wywołaj narzędzie `execute_turbine_schedule` (Faza 2), aby zmieścić się w 40-sekundowym oknie sprzętowym. "
            "Po zdobyciu flagi zapisz `run_notes.txt` w workspace."
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="user",
            content=initial_user_message,
            step_type="mission_start",
        )

        try:
            result = await agent.ainvoke(
                {"messages": [("user", initial_user_message)]},
                config={
                    "callbacks": [bq_handler],
                    "recursion_limit": recursion_limit,
                },
            )

            # Extract reasoning/answer from messages
            messages = result.get("messages", [])
            final_content = ""
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content:
                    final_content = str(msg.content)
                    break

            duration = round(time.monotonic() - start_time, 2)
            flag = state_tracker["flag"]
            if not flag and "{FLG:" in final_content:
                import re

                match = re.search(r"(\{FLG:[^\}]+\})", final_content)
                if match:
                    flag = match.group(1)

            status = "success" if flag else "error"
            await self.audit.log_event(
                session_id=session_id,
                actor="agent",
                content=final_content[:1000],
                step_type="mission_complete",
                metadata={"status": status, "duration_seconds": duration},
                flag=flag,
            )

            return RunTaskResponse(
                status=status,
                backend="langchain",
                session_id=session_id,
                flag=flag or "[NO_FLAG]",
                actions_taken=state_tracker["actions_taken"],
                reasoning=final_content or "LangChain agent finished execution.",
                execution_time_seconds=duration,
                scheduled_points_count=len(state_tracker["scheduled_points"]),
            )

        except Exception as e:
            logger.error(f"LangChain execution error: {e}", exc_info=True)
            duration = round(time.monotonic() - start_time, 2)
            await self.audit.log_event(
                session_id=session_id,
                actor="system",
                content=f"Execution error: {e!s}",
                step_type="error",
                metadata={"error": str(e)},
            )
            return RunTaskResponse(
                status="error",
                backend="langchain",
                session_id=session_id,
                flag=state_tracker.get("flag") or "[ERROR]",
                actions_taken=state_tracker["actions_taken"],
                reasoning=f"Execution failed: {e!s}",
                execution_time_seconds=duration,
                scheduled_points_count=len(state_tracker["scheduled_points"]),
            )
