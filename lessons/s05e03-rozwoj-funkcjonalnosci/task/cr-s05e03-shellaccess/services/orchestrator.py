"""Orchestrator for the autonomous shellaccess agent ReAct loop and local verification gate."""

import logging
import re
import time
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from config import config
from schemas import (
    RafalDiscoveryExtraction,
    RendezvousPayload,
    RunTaskRequest,
    RunTaskResponse,
)
from services.audit_service import AuditService, generate_session_id
from services.centrala_service import CentralaService
from services.prompt_builder import build_system_message
from services.shell_tool import CentralaShellTool, ExecuteShellInput

logger = logging.getLogger("services.orchestrator")
FLAG_REGEX = re.compile(r"\{FLG:[^}]+\}")


def compute_rendezvous(discovery: RafalDiscoveryExtraction) -> RendezvousPayload:
    """Calculates target rendezvous date (strictly ONE DAY BEFORE discovery) and validates bounds."""
    clean_date_str = discovery.discovery_date.strip()
    parsed_date = date.fromisoformat(clean_date_str)
    target_date = parsed_date - timedelta(days=1)

    return RendezvousPayload(
        date=target_date.isoformat(),
        city=discovery.city.strip(),
        longitude=float(discovery.longitude),
        latitude=float(discovery.latitude),
    )


async def save_run_notes(response: RunTaskResponse) -> None:
    """Persists unanonymized execution run notes directly to remote cr-mcp-workspace."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from services.mcp_service import mcp_service

    now_str = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d %H:%M:%S")
    rendezvous_str = (
        response.rendezvous.model_dump_json(indent=2) if response.rendezvous else "None"
    )

    notes_content = f"""Task: {config.TASK_NAME} (S05E03)
Timestamp: {now_str}
Session ID: {response.session_id}
Status: {response.status.upper()}
Turns: {response.total_turns}
Execution Time: {response.execution_time_seconds}s
Rendezvous:
{rendezvous_str}
Flag: {response.flag or "[NONE]"}
Error: {response.error or "None"}
"""
    try:
        await mcp_service.write_file(
            session_id=response.session_id,
            file_path="run_notes.txt",
            content=notes_content,
            reasoning="Persisting session run notes",
        )
        logger.info(
            f"Successfully persisted run_notes.txt to cr-mcp-workspace for session {response.session_id}"
        )
    except Exception as e:
        logger.warning(f"Could not persist run_notes.txt to cr-mcp-workspace: {e}")


class ShellAccessOrchestrator:
    """Coordinates autonomous exploration of the remote Linux host and verification submission."""

    def __init__(
        self,
        request: RunTaskRequest,
        audit_service: AuditService | None = None,
        centrala_service: CentralaService | None = None,
    ) -> None:
        self.request = request
        self.session_id = request.session_id or generate_session_id(request.backend)
        self.model = request.model or config.GEMINI_MODEL
        self.thinking_level = request.thinking_level or config.THINKING_LEVEL
        self.max_iterations = request.max_iterations or config.MAX_ITERATIONS

        self.audit = audit_service or AuditService()
        self.centrala = centrala_service or CentralaService()
        self.shell_tool = CentralaShellTool(self.centrala)

        self.flag: str | None = None
        self.rendezvous: RendezvousPayload | None = None

    async def _handle_submit_discovery(
        self, extraction: RafalDiscoveryExtraction
    ) -> str:
        """Local Pydantic Verification Gate: computes rendezvous and dispatches final payload."""
        logger.info(
            f"Local Verification Gate invoked with discovery: date={extraction.discovery_date}, "
            f"city={extraction.city}, lat={extraction.latitude}, lon={extraction.longitude}"
        )

        try:
            rendezvous = compute_rendezvous(extraction)
            self.rendezvous = rendezvous
        except Exception as exc:
            err = f"Failed to compute rendezvous from discovery data: {exc}"
            logger.error(err)
            return f"[VERIFICATION ERROR: {err}]"

        submission_cmd = f"echo '{rendezvous.model_dump_json()}'"
        logger.info(
            f"Submitting final clean verification command to Centrala: {submission_cmd}"
        )

        resp = await self.centrala.execute_shell_raw(
            submission_cmd, caller="VERIFICATION_GATE"
        )
        msg = resp.message or ""

        # Check for course flag
        flag_match = FLAG_REGEX.search(msg)
        if flag_match:
            self.flag = flag_match.group(0)
            logger.info("Successfully acquired mission flag: [REDACTED_FLAG]")
            await self.audit.alog_event(
                session_id=self.session_id,
                actor="verification_gate",
                content="Mission flag acquired successfully",
                metadata={"status": "completed", "rendezvous": rendezvous.model_dump()},
            )
            return f"[SUCCESS: Flag received! Result: {self.flag}]"

        logger.warning(
            f"Submission accepted by Centrala but no flag found in response: {msg[:200]}"
        )
        return f"[SUBMISSION RESPONSE: {msg}]"

    def _build_tools(self):
        """Constructs closed set of tools exposed strictly to the agent."""
        shell_tool_inst = self.shell_tool

        @tool("execute_shell", args_schema=ExecuteShellInput)
        async def execute_shell(cmd: str) -> str:
            """Executes a UNIX shell command on the remote Linux host.
            Use this tool to explore directories, inspect files, and search logs using grep, jq, head, awk, etc.
            Destructive commands (rm, mv, chmod) and script interpreters (python, zsh) are strictly prohibited.
            """
            return await shell_tool_inst.execute_agent_command(cmd)

        @tool("submit_discovery", args_schema=RafalDiscoveryExtraction)
        async def submit_discovery(
            discovery_date: str,
            city: str,
            latitude: float,
            longitude: float,
            reasoning: str = "",
        ) -> str:
            """Submits the extracted discovery parameters of Rafał's body.
            Call this tool ONCE you locate the record in /data.
            The verification gate will automatically compute the date exactly ONE DAY BEFORE discovery,
            validate coordinate bounds, and issue the final answer to Centrala.
            """
            extraction = RafalDiscoveryExtraction(
                discovery_date=discovery_date,
                city=city,
                latitude=latitude,
                longitude=longitude,
                reasoning=reasoning,
            )
            return await self._handle_submit_discovery(extraction)

        return [execute_shell, submit_discovery]

    async def run(self) -> RunTaskResponse:
        """Executes the autonomous agent loop."""
        start_time = time.perf_counter()
        logger.info(
            f"Starting shellaccess agent session {self.session_id} using model {self.model}"
        )

        # Initialize audit table
        self.audit.ensure_table()
        await self.audit.alog_event(
            session_id=self.session_id,
            actor="orchestrator",
            content=f"Session started with model={self.model}, max_iterations={self.max_iterations}",
            metadata={"request": self.request.model_dump()},
        )

        tools = self._build_tools()
        tools_map = {t.name: t for t in tools}

        llm = ChatGoogleGenerativeAI(
            model=self.model,
            temperature=0.1,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=self.thinking_level,
        )
        llm_with_tools = llm.bind_tools(tools)

        messages = [
            SystemMessage(content=build_system_message()),
            HumanMessage(
                content="Begin your investigation. List the files in /data, identify the log structure, "
                "and find when and where Rafał's body was discovered."
            ),
        ]

        total_turns = 0
        error_msg: str | None = None

        for iteration in range(1, self.max_iterations + 1):
            total_turns = iteration
            logger.info(f"--- Iteration {iteration}/{self.max_iterations} ---")

            try:
                ai_response: AIMessage = await llm_with_tools.ainvoke(messages)
            except Exception as e:
                error_msg = f"LLM invocation failed at iteration {iteration}: {e}"
                logger.error(error_msg)
                await self.audit.alog_event(
                    session_id=self.session_id,
                    actor="agent_error",
                    content=error_msg,
                )
                break

            messages.append(ai_response)
            ai_text = (
                ai_response.content
                if isinstance(ai_response.content, str)
                else str(ai_response.content)
            )

            await self.audit.alog_event(
                session_id=self.session_id,
                actor="agent_turn",
                content=ai_text[:500] if ai_text else "(Tool calls triggered)",
                metadata={
                    "iteration": iteration,
                    "tool_calls_count": len(ai_response.tool_calls or []),
                },
            )

            # Check if agent issued any tool calls
            tool_calls = ai_response.tool_calls or []
            if not tool_calls:
                logger.info("Agent provided plain message without tool calls.")
                if self.flag:
                    break
                # Prompt the agent to continue tool use
                messages.append(
                    HumanMessage(
                        content="Please use the 'execute_shell' tool to investigate or 'submit_discovery' if found."
                    )
                )
                continue

            for tc in tool_calls:
                tool_name = tc.get("name")
                tool_args = tc.get("args") or {}
                tool_id = tc.get("id") or f"call_{iteration}"

                logger.info(f"Executing tool {tool_name} with args: {tool_args}")
                tool_target = tools_map.get(tool_name)

                if not tool_target:
                    tool_output = f"[ERROR: Tool '{tool_name}' is not recognized.]"
                else:
                    try:
                        tool_output = await tool_target.ainvoke(tool_args)
                    except Exception as e:
                        tool_output = f"[TOOL EXECUTION ERROR: {e}]"
                        logger.error(f"Tool {tool_name} failed: {e}")

                messages.append(
                    ToolMessage(
                        content=str(tool_output),
                        tool_call_id=tool_id,
                    )
                )

                await self.audit.alog_event(
                    session_id=self.session_id,
                    actor="tool_result",
                    content=str(tool_output)[:500],
                    metadata={"tool": tool_name, "args": tool_args},
                )

            if self.flag:
                logger.info("Goal reached: Flag successfully captured!")
                break

        elapsed = round(time.perf_counter() - start_time, 2)
        status = "completed" if self.flag else "failed"

        await self.audit.alog_event(
            session_id=self.session_id,
            actor="orchestrator",
            content=f"Execution finished with status={status} in {elapsed}s",
            metadata={
                "status": status,
                "total_turns": total_turns,
                "flag_acquired": bool(self.flag),
            },
        )

        response_obj = RunTaskResponse(
            session_id=self.session_id,
            status=status,
            flag=self.flag,
            rendezvous=self.rendezvous,
            total_turns=total_turns,
            execution_time_seconds=elapsed,
            error=error_msg
            or (
                "Max iterations reached without finding flag" if not self.flag else None
            ),
        )
        await save_run_notes(response_obj)
        return response_obj
