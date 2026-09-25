import asyncio
import concurrent.futures
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import config
from agents.base import BaseWarehouseAgent
from schemas import (
    RunTaskResponse,
    TaskStats,
)
from services.audit_service import AuditService
from services.centrala_service import CentralaService
from services.mcp_service import MCPService
from services.validation_service import ValidationService

logger = logging.getLogger("agents.adk")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKWarehouseAgent(BaseWarehouseAgent):
    """Google ADK 1.33.0 agent implementation for S04E05 foodwarehouse using Gemini 3.8 Flash."""

    def __init__(self, model: str | None = None, thinking_level: str | None = None):
        base_dir = str(Path(__file__).parent.parent)
        self.prompt_config = load_system_prompt(base_dir=base_dir)
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.centrala = CentralaService(mcp_service=self.mcp)
        self.validation = ValidationService()

        self.model_name = model or self.prompt_config.model or config.GEMINI_MODEL
        self.thinking_level = thinking_level or config.THINKING_LEVEL

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        audit = self.audit
        mcp = self.mcp
        centrala = self.centrala
        validation = self.validation

        def call_centrala_api(
            tool: str, params: dict[str, Any] | None = None, reasoning: str = ""
        ) -> str:
            """Uniwersalny meta-tool do odpytywania API Centrali w celach eksploracyjnych i odczytowych ('help', 'database', 'signatureGenerator', 'orders' z action='get', 'reset'). UWAGA: Pojedyncze create/append oraz direct done sa blokowane."""

            async def _run():
                state_tracker["discovery_queries"] += 1
                params_dict = params or {}
                try:
                    res = await centrala.execute_tool(tool=tool, params=params_dict)
                    await audit.log_event(
                        session_id=session_id,
                        actor=f"adk_tool:call_centrala_api:{tool}",
                        content=f"Tool call {tool} params={params_dict} result={str(res)[:300]}",
                    )
                    return json.dumps(res, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Error in call_centrala_api: {e}", exc_info=True)
                    return json.dumps({"status": "error", "message": str(e)})

            return _run_coroutine_sync(_run())

        def read_file(file_path: str, reasoning: str = "") -> str:
            """Odczytuje plik z cr-mcp-workspace (np. 'food4cities.json', 'orders_manifest.json', 'TODOs.md')."""

            async def _run():
                try:
                    return await mcp.read_file(
                        session_id=session_id, file_path=file_path, reasoning=reasoning
                    )
                except Exception as e:
                    return json.dumps({"status": "error", "message": str(e)})

            return _run_coroutine_sync(_run())

        def write_file(file_path: str, content: str, reasoning: str = "") -> str:
            """Zapisuje lub aktualizuje plik w cr-mcp-workspace (np. 'orders_manifest.json', 'TODOs.md', 'docs/api_spec.md')."""

            async def _run():
                try:
                    res = await mcp.write_file(
                        session_id=session_id,
                        file_path=file_path,
                        content=content,
                        reasoning=reasoning,
                    )
                    return json.dumps(res, ensure_ascii=False)
                except Exception as e:
                    return json.dumps({"status": "error", "message": str(e)})

            return _run_coroutine_sync(_run())

        def list_files(path: str = ".", reasoning: str = "") -> str:
            """Listuje pliki w przestrzeni roboczej cr-mcp-workspace."""

            async def _run():
                try:
                    files = await mcp.list_files(
                        session_id=session_id, path=path, reasoning=reasoning
                    )
                    return json.dumps({"status": "success", "files": files})
                except Exception as e:
                    return json.dumps({"status": "error", "message": str(e)})

            return _run_coroutine_sync(_run())

        def validate_staged_orders() -> str:
            """Uruchamia Pre-Flight Quality Gate na pliku orders_manifest.json wzgledem food4cities.json."""

            async def _run():
                try:
                    manifest_raw = await mcp.read_file(
                        session_id=session_id, file_path="orders_manifest.json"
                    )
                    demands_raw = await mcp.read_file(
                        session_id=session_id, file_path="food4cities.json"
                    )
                    if not demands_raw:
                        expected_demands = await centrala.fetch_food4cities()
                    else:
                        expected_demands = json.loads(demands_raw)

                    report = validation.validate_manifest_data(
                        manifest_raw=manifest_raw, expected_demands=expected_demands
                    )
                    state_tracker["last_validation_report"] = report

                    await audit.log_event(
                        session_id=session_id,
                        actor="adk_tool:validate_staged_orders",
                        content=f"Validation valid={report.valid}, errors={len(report.errors)}",
                    )
                    return json.dumps(report.model_dump(), ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Error in validate_staged_orders: {e}", exc_info=True)
                    return json.dumps({"valid": False, "errors": [str(e)]})

            return _run_coroutine_sync(_run())

        def dispatch_staged_orders() -> str:
            """Atomowo synchronizuje zwalidowany manifest z Centrala: asertuje walidacje, wykonuje reset, tworzy 8 zamowien, wgrywa towary w trybie batch i zglasza zakonczenie misji narzedziem done."""

            async def _run():
                try:
                    manifest_raw = await mcp.read_file(
                        session_id=session_id, file_path="orders_manifest.json"
                    )
                    demands_raw = await mcp.read_file(
                        session_id=session_id, file_path="food4cities.json"
                    )
                    if not demands_raw:
                        expected_demands = await centrala.fetch_food4cities()
                    else:
                        expected_demands = json.loads(demands_raw)

                    # Strict Pre-Flight assertion before mutating Centrala
                    report = validation.validate_manifest_data(
                        manifest_raw=manifest_raw, expected_demands=expected_demands
                    )
                    if not report.valid:
                        return json.dumps(
                            {
                                "status": "rejected",
                                "reason": "Pre-flight validation failed. Fix errors before dispatching to Centrala.",
                                "errors": report.errors,
                                "hint": report.hint,
                            },
                            ensure_ascii=False,
                        )

                    manifest_data = json.loads(manifest_raw)
                    if isinstance(manifest_data, list):
                        orders_list = manifest_data
                    elif isinstance(manifest_data, dict) and "orders" in manifest_data:
                        orders_list = manifest_data["orders"]
                    elif isinstance(manifest_data, dict):
                        orders_list = [
                            {"city": k, **v} if isinstance(v, dict) else v
                            for k, v in manifest_data.items()
                        ]
                    else:
                        orders_list = []

                    dispatch_rep = await centrala.dispatch_orders_batch(orders_list)
                    state_tracker["orders_created"] = dispatch_rep.orders_processed
                    state_tracker["items_appended"] = dispatch_rep.items_appended
                    if dispatch_rep.flag:
                        state_tracker["flag"] = dispatch_rep.flag

                    # Update TODOs.md
                    todos_current = await mcp.read_file(
                        session_id=session_id, file_path="TODOs.md"
                    )
                    todos_update = (
                        todos_current
                        + f"\n- [x] Centrala Batch Dispatch: {dispatch_rep.orders_processed} orders, {dispatch_rep.items_appended} items\n- [x] Verified Flag: {dispatch_rep.flag}\n"
                    )
                    await mcp.write_file(
                        session_id=session_id,
                        file_path="TODOs.md",
                        content=todos_update,
                    )

                    await audit.log_event(
                        session_id=session_id,
                        actor="adk_tool:dispatch_staged_orders",
                        content=f"Dispatch complete. Status: {dispatch_rep.status}, Flag: {dispatch_rep.flag}",
                        flag=dispatch_rep.flag,
                    )
                    return json.dumps(dispatch_rep.model_dump(), ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Error in dispatch_staged_orders: {e}", exc_info=True)
                    return json.dumps({"status": "error", "message": str(e)})

            return _run_coroutine_sync(_run())

        return [
            call_centrala_api,
            read_file,
            write_file,
            list_files,
            validate_staged_orders,
            dispatch_staged_orders,
        ]

    async def execute(
        self,
        session_id: str,
        recursion_limit: int | None = None,
        model: str | None = None,
        thinking_level: str | None = None,
    ) -> RunTaskResponse:
        """Executes autonomous warehouse logistics mission using Google ADK."""
        start_time = time.time()
        effective_limit = recursion_limit or config.MAX_AGENT_ITERATIONS
        effective_model = model or self.model_name
        effective_thinking = thinking_level or self.thinking_level

        state_tracker: dict[str, Any] = {
            "discovery_queries": 0,
            "signatures_generated": 0,
            "orders_created": 0,
            "items_appended": 0,
            "flag": None,
        }

        # Pre-seed food4cities.json in workspace
        try:
            food_demands = await self.centrala.fetch_food4cities()
            await self.mcp.write_file(
                session_id=session_id,
                file_path="food4cities.json",
                content=json.dumps(food_demands, indent=2),
                reasoning="Pre-seeding municipal resource demands into workspace.",
            )
            initial_todos = """# S04E05 Food Warehouse Logistics Checklist
- [x] Pre-seeded food4cities.json in cr-mcp-workspace
- [ ] Phase 1: API Discovery (help) and SQLite Schema Inspection (docs/api_spec.md, docs/db_schema.md)
- [ ] Phase 2: Manifest Assembly & Signature Staging (orders_manifest.json)
- [ ] Phase 3: Pre-Flight Quality Gate (validate_staged_orders)
- [ ] Phase 4: Atomic Batch Dispatch & Done (dispatch_staged_orders)
"""
            await self.mcp.write_file(
                session_id=session_id,
                file_path="TODOs.md",
                content=initial_todos,
                reasoning="Initializing operational checklist in workspace.",
            )
        except Exception as e:
            logger.warning(f"Could not pre-seed food4cities.json: {e}")

        tools = self._create_tools(session_id, state_tracker)

        system_instruction = (
            self.prompt_config.system_prompt
            or "Jesteś agentem Centrali odpowiedzialnym za misję foodwarehouse."
        )

        agent = Agent(
            name="adk_warehouse_agent",
            model=effective_model,
            instruction=system_instruction,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name="foodwarehouse",
            session_service=session_service,
        )

        initial_user_prompt = (
            "Rozpocznij misję foodwarehouse. Przeprowadź pełną 4-fazową procedurę zgodnie z SOP: "
            "1) Zbadaj API (help) oraz tabele SQLite (database: show tables, PRAGMA) i zapisz dokumentację do docs/api_spec.md oraz docs/db_schema.md. "
            "2) Odczytaj zapotrzebowanie z food4cities.json, wygeneruj podpisy przez signatureGenerator i zapisz 8 zamówień w orders_manifest.json. "
            "3) Uruchom validate_staged_orders i upewnij się, że valid=true. "
            "4) Wywołaj dispatch_staged_orders, aby zresetować magazyn, utworzyć zamówienia i odebrać flagę."
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="user",
            content=initial_user_prompt,
            step_type="mission_start",
        )

        try:
            session = await session_service.create_session(
                session_id=session_id, user_id="operator"
            )
            user_msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text=initial_user_prompt)],
            )

            logger.info(
                f"Starting Google ADK runner for session {session_id} "
                f"(model={effective_model}, thinking={effective_thinking}, max_iterations={effective_limit})..."
            )
            async for event in runner.run_async(
                user_id="operator",
                session_id=session.id,
                message=user_msg,
            ):
                if hasattr(event, "content") and event.content:
                    text_out = str(event.content)
                    match = re.search(r"(\{FLG:[^\}]+\})", text_out)
                    if match:
                        state_tracker["flag"] = match.group(1)

        except Exception as e:
            logger.error(f"Google ADK execution error: {e}", exc_info=True)

        duration = time.time() - start_time
        flag = state_tracker.get("flag")
        orders_cnt = state_tracker.get("orders_created", 0)

        stats = TaskStats(
            discovery_queries=state_tracker.get("discovery_queries", 0),
            signatures_generated=state_tracker.get("signatures_generated", 0),
            orders_created=orders_cnt,
            items_appended=state_tracker.get("items_appended", 0),
            duration_seconds=round(duration, 2),
        )

        status = "success" if flag else "error"
        msg = (
            f"Mission complete. Flag: {flag}"
            if flag
            else "Mission finished without capturing verification flag."
        )

        return RunTaskResponse(
            status=status,
            flag=flag,
            session_id=session_id,
            backend="adk",
            orders_count=orders_cnt,
            stats=stats,
            message=msg,
        )
