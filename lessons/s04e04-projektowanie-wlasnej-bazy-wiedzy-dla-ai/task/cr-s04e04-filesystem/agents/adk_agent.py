"""Google ADK 1.33.0 agent implementation for task filesystem using Gemini 3.8 Flash."""

import asyncio
import concurrent.futures
import json
import logging
import re
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import config
from agents.base import BaseFilesystemAgent
from schemas import (
    RunTaskResponse,
    TaskStats,
)
from services.audit_service import AuditService
from services.centrala_service import CentralaService
from services.extraction_service import ExtractionService
from services.linguistic_service import LinguisticService
from services.mcp_service import MCPService
from services.validation_service import ValidationService

logger = logging.getLogger("agents.adk")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKFilesystemAgent(BaseFilesystemAgent):
    """Google ADK 1.33.0 agent for S04E04 filesystem."""

    def __init__(self):
        base_dir = str(Path(__file__).parent.parent)
        self.prompt_config = load_system_prompt(base_dir=base_dir)
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.centrala = CentralaService()
        self.extraction = ExtractionService()
        self.linguistic = LinguisticService()
        self.validation = ValidationService(linguistic_service=self.linguistic)

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        audit = self.audit
        mcp = self.mcp
        centrala = self.centrala
        extraction = self.extraction
        validation = self.validation

        def prepare_and_stage_filesystem() -> str:
            """Pobiera notatki Natana, wyodrebnia encje przez Gemini 3.8 Flash, buduje pliki wirtualne i zapisuje je w sesyjnym cr-mcp-workspace wraz z checklistą TODOs.md."""

            async def _run():
                notes = await extraction.fetch_notes()
                plan = await extraction.extract_structured_plan(notes)
                files = extraction.build_virtual_files(plan)

                for idx, f in enumerate(files):
                    logger.info(
                        f"Staging file [{idx + 1}/{len(files)}] into cr-mcp-workspace: '{f.path}'"
                    )
                    await mcp.write_file(
                        session_id=session_id, file_path=f.path, content=f.content
                    )

                todos_content = f"""# Filesystem Staging Checklist
- [x] Extracted {len(plan.cities)} Cities: {[c.city_name for c in plan.cities]}
- [x] Extracted {len(plan.coordinators)} Coordinators: {[c.person_name for c in plan.coordinators]}
- [x] Extracted {len({t.commodity for t in plan.transactions})} Unique Commodities
- [x] Total Staged Files: {len(files)}
- [ ] Pre-Flight Validation Gate (validate_all_files)
- [ ] Centrala Atomic Batch Push (push_filesystem_batch)
"""
                await mcp.write_file(
                    session_id=session_id, file_path="TODOs.md", content=todos_content
                )

                state_tracker["staged_files"] = files
                state_tracker["cities_count"] = len(plan.cities)
                state_tracker["persons_count"] = len(plan.coordinators)
                state_tracker["commodities_count"] = len(
                    {t.commodity for t in plan.transactions}
                )

                await audit.log_event(
                    session_id=session_id,
                    actor="adk_tool:prepare_and_stage_filesystem",
                    content=f"Staged {len(files)} files into cr-mcp-workspace.",
                )
                return json.dumps(
                    {
                        "status": "success",
                        "files_staged": len(files),
                        "cities": len(plan.cities),
                        "coordinators": len(plan.coordinators),
                        "message": "Pliki zostaly przygotowane w cr-mcp-workspace. Wywolaj validate_all_files przed wysylka.",
                    }
                )

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                logger.error(
                    f"Error in prepare_and_stage_filesystem: {e}", exc_info=True
                )
                return json.dumps({"status": "error", "message": str(e)})

        def read_file(file_path: str, reasoning: str = "") -> str:
            """Odczytuje zawartosc pliku z cr-mcp-workspace (np. TODOs.md lub dowolnego pliku w miastach, osobach, towarach)."""
            try:
                return _run_coroutine_sync(
                    mcp.read_file(
                        session_id=session_id, file_path=file_path, reasoning=reasoning
                    )
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def write_file(file_path: str, content: str, reasoning: str = "") -> str:
            """Zapisuje lub aktualizuje plik w cr-mcp-workspace (np. TODOs.md lub korekta pliku w miastach, osobach, towarach)."""

            async def _run():
                res = await mcp.write_file(
                    session_id=session_id,
                    file_path=file_path,
                    content=content,
                    reasoning=reasoning,
                )
                return json.dumps(res, ensure_ascii=False)

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def list_files(path: str = ".", reasoning: str = "") -> str:
            """Listuje pliki w danym katalogu cr-mcp-workspace (np. '.', 'miasta', 'osoby', 'towary')."""

            async def _run():
                files = await mcp.list_files(
                    session_id=session_id, path=path, reasoning=reasoning
                )
                return json.dumps({"status": "success", "files": files})

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def validate_all_files() -> str:
            """Uruchamia trojfazowy Pre-Flight Quality Gate na wszystkich plikach w cr-mcp-workspace (ASCII, JSON, Markdown linki, mianownik l.p.). Jesli wykryje bledy, zwraca je wraz z instrukcja zapisania zadan naprawczych do TODOs.md."""

            async def _run():
                files = await mcp.list_all_workspace_files(session_id=session_id)
                if not files:
                    files = state_tracker.get("staged_files", [])

                report = await validation.validate_filesystem(files)
                state_tracker["last_validation_report"] = report

                await audit.log_event(
                    session_id=session_id,
                    actor="adk_tool:validate_all_files",
                    content=f"Validation valid={report.valid}, errors={len(report.errors)}",
                )
                return json.dumps(report.model_dump(), ensure_ascii=False)

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                logger.error(f"Error in validate_all_files: {e}", exc_info=True)
                return json.dumps({"status": "error", "message": str(e)})

        def create_remote_directory(path: str) -> str:
            """Tworzy katalog w wirtualnym filesystemie Centrali. Jesli katalog juz istnieje (kod -960), informuje, ze katalog jest juz gotowy."""

            async def _run():
                res = await centrala.create_directory(path)
                code = res.get("code", 0)
                if (
                    code == -960
                    or "already exists" in str(res.get("message", "")).lower()
                ):
                    msg = f"Katalog '{path}' juz istnieje w Centrali. Mozesz bez przeszkod przejsc do wgrywania plikow."
                    logger.info(msg)
                    return json.dumps({"status": "success", "message": msg})
                return json.dumps(res, ensure_ascii=False)

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                logger.error(f"Error creating directory {path}: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def push_filesystem_batch() -> str:
            """Atomowo synchronizuje wirtualny system plikow z Centrala: wykonuje reset, batch upload wszystkich plikow z cr-mcp-workspace i action: done."""

            async def _run():
                files = await mcp.list_all_workspace_files(session_id=session_id)
                if not files:
                    files = state_tracker.get("staged_files", [])

                report = await validation.validate_filesystem(files)
                if not report.valid:
                    return json.dumps(
                        {
                            "status": "rejected",
                            "reason": "Pre-flight validation failed. Fix errors before pushing to Centrala.",
                            "errors": report.errors,
                            "hint": report.hint,
                        },
                        ensure_ascii=False,
                    )

                logger.info("Resetting Centrala virtual filesystem...")
                await centrala.reset()

                logger.info(f"Pushing {len(files)} files to Centrala in batch mode...")
                batch_res = await centrala.batch_create_files(files)
                batch_code = batch_res.get("code", 0)
                if batch_code < 0:
                    logger.error(f"Centrala rejected batch upload: {batch_res}")
                    return json.dumps(
                        {
                            "status": "error",
                            "reason": f"Centrala rejected batch file upload: {batch_res.get('message', 'Unknown error')} (code: {batch_code})",
                            "details": batch_res,
                            "hint": "Zbadaj błąd zwrócony przez Centralę. Popraw odpowiedni plik w cr-mcp-workspace za pomocą write_file i spróbuj ponownie.",
                        },
                        ensure_ascii=False,
                    )

                logger.info("Triggering verification via action: done...")
                done_resp, flag = await centrala.done()
                done_code = done_resp.get("code", 0)
                if done_code < 0 and not flag:
                    logger.warning(f"Centrala verification rejected: {done_resp}")
                    return json.dumps(
                        {
                            "status": "verification_failed",
                            "reason": done_resp.get("message", "Verification failed"),
                            "details": done_resp,
                            "hint": "Centrala odrzuciła weryfikację bazy wiedzy. Sprawdź komunikat błędu, skoryguj pliki przez write_file i wywołaj ponownie push_filesystem_batch.",
                        },
                        ensure_ascii=False,
                    )

                if flag:
                    state_tracker["flag"] = flag

                todos_current = await mcp.read_file(
                    session_id=session_id, file_path="TODOs.md"
                )
                todos_update = (
                    todos_current
                    + f"\n- [x] Centrala Batch Upload: {len(files)} files\n- [x] Verified Flag: {flag}\n"
                )
                await mcp.write_file(
                    session_id=session_id, file_path="TODOs.md", content=todos_update
                )

                await audit.log_event(
                    session_id=session_id,
                    actor="adk_tool:push_filesystem_batch",
                    content=f"Batch push complete. Flag: {flag}",
                    flag=flag,
                )
                return json.dumps(
                    {
                        "status": "success",
                        "flag": flag,
                        "centrala_response": done_resp,
                    },
                    ensure_ascii=False,
                )

            try:
                return _run_coroutine_sync(_run())
            except Exception as e:
                logger.error(f"Error in push_filesystem_batch: {e}", exc_info=True)
                return json.dumps({"status": "error", "message": str(e)})

        return [
            prepare_and_stage_filesystem,
            read_file,
            write_file,
            list_files,
            validate_all_files,
            create_remote_directory,
            push_filesystem_batch,
        ]

    async def execute(
        self, session_id: str, recursion_limit: int = 60
    ) -> RunTaskResponse:
        state_tracker: dict[str, Any] = {
            "flag": None,
            "staged_files": [],
            "cities_count": 0,
            "persons_count": 0,
            "commodities_count": 0,
        }

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)

        agent = Agent(
            name="adk_filesystem_agent",
            model=self.prompt_config.model or config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            session_service=session_service,
            max_iterations=recursion_limit,
        )

        initial_user_prompt = (
            f"Agent, execute operation 'filesystem' (Session: {session_id}).\n"
            "Procedura wykonania:\n"
            "1. Wywolaj narzedzie `prepare_and_stage_filesystem` (pobierze notatki, wyekstrahuje encje i przygotuje pliki w cr-mcp-workspace).\n"
            "2. Wywolaj narzedzie `validate_all_files` (przeprowadzi automatyczna walidacje wszystkich plikow naraz).\n"
            "3. Jesli walidacja zwroci jakiekolwiek bledy (`valid: false`):\n"
            "   - Zapisz liste zadan naprawczych do `TODOs.md` przez `write_file`.\n"
            "   - Popraw wskazane pliki uzywajac `write_file`.\n"
            "   - Po ukonczeniu poprawek wywolaj `validate_all_files` ponownie, aby upewnic sie, ze `valid: true`.\n"
            "4. Gdy walidacja jest w pelni poprawna ('valid': true), wywolaj `push_filesystem_batch`, aby wyslac cala strukture do Centrali i odebrac flage.\n"
            "5. Zwroc ostateczna odpowiedz zawierajaca zdobyta flage {{FLG:...}}."
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="user",
            content=initial_user_prompt,
            step_type="mission_start",
        )

        try:
            session = await session_service.create_session(
                session_id=session_id, user_id="commander"
            )

            user_msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text=initial_user_prompt)],
            )

            async for event in runner.run_async(
                user_id="commander",
                session_id=session.id,
                message=user_msg,
            ):
                if hasattr(event, "content") and event.content:
                    text_out = str(event.content)
                    match = re.search(r"(\{FLG:[^\}]+\})", text_out)
                    if match:
                        state_tracker["flag"] = match.group(1)

            flag = state_tracker.get("flag")
            success = bool(flag)
            stats = TaskStats(
                cities_count=state_tracker.get("cities_count", 8),
                persons_count=state_tracker.get("persons_count", 8),
                commodities_count=state_tracker.get("commodities_count", 13),
                files_uploaded=len(state_tracker.get("staged_files", [])),
            )

            return RunTaskResponse(
                status="success" if success else "error",
                backend="adk",
                flag=flag,
                stats=stats,
                audit_logged=True,
                error=None
                if success
                else "Operation completed without retrieving verification flag.",
            )
        except Exception as e:
            logger.error(f"Google ADK execution error: {e}", exc_info=True)
            return RunTaskResponse(
                status="error",
                backend="adk",
                flag=state_tracker.get("flag"),
                stats=None,
                audit_logged=True,
                error=str(e),
            )
