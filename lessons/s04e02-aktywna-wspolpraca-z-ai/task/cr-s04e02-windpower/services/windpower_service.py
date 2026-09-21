import asyncio
import logging
import time
from typing import Any

import config
from schemas import (
    ExecuteTurbineScheduleResponse,
    ProbeWindpowerApiResponse,
    SaveDiscoveryNotesResponse,
    SolveAndExecuteResponse,
    TurbineConfigPoint,
)
from services.audit_service import AuditService
from services.mcp_service import MCPService

logger = logging.getLogger("services.windpower")


class WindpowerService:
    """Core domain service for discovering, scheduling, and executing Centrala's windpower task."""

    def __init__(
        self,
        mcp_service: MCPService | None = None,
        audit_service: AuditService | None = None,
    ):
        self.mcp = mcp_service or MCPService()
        self.audit = audit_service or AuditService()
        self.session_started = False
        self.cached_weather: dict[str, Any] | None = None
        self.cached_powerplant: dict[str, Any] | None = None
        self.cached_documentation: dict[str, Any] | None = None
        self.cached_turbinecheck: dict[str, Any] | None = None

    async def probe_api(
        self,
        session_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        reasoning: str = "",
        auto_drain: bool = True,
    ) -> ProbeWindpowerApiResponse:
        """Dispatches an exploratory action to Centrala API via MCP Web Gateway (Phase 1)."""
        answer_payload: dict[str, Any] = {"action": action}
        if params:
            answer_payload.update(params)

        # Guardrail: Prevent premature 40-second hardware battery timer expiration
        if action == "start":
            return ProbeWindpowerApiResponse(
                status="error",
                action="start",
                code=-1,
                message="Direct invocation of 'start' via probe_windpower_api is blocked to prevent premature battery expiration. Call execute_turbine_schedule() directly, which automatically pipelines start, telemetry, unlock codes, and bulk configuration safely within 25 seconds.",
                data={},
                hint="Proceed immediately to execute_turbine_schedule().",
            )

        param_name = params.get("param") if params else None
        if action == "get" and param_name in ("weather", "powerplantcheck"):
            return ProbeWindpowerApiResponse(
                status="error",
                action="get",
                code=-1,
                message=f"Direct polling of '{param_name}' via probe_windpower_api is blocked to conserve the 40s battery window. Live telemetry is automatically pipelined inside execute_turbine_schedule(). Please invoke execute_turbine_schedule() directly.",
                data={},
                hint="Proceed immediately to execute_turbine_schedule().",
            )

        request_body = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": answer_payload,
        }

        masked_request = {
            "apikey": "***" if config.AIDEVS_API_KEY else "MISSING",
            "task": config.TASK_NAME,
            "answer": answer_payload,
        }
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"probe_api action '{action}'",
            step_type=f"probe_{action}",
            metadata={"request": masked_request, "reasoning": reasoning},
        )

        resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=request_body,
        )

        code = resp.get("code")
        message = str(
            resp.get("message") or resp.get("description") or resp.get("output") or ""
        )
        data = resp.get("data") if isinstance(resp.get("data"), dict) else resp

        if action == "start" and (code is None or code >= 0):
            self.session_started = True

        # If action is 'get' and param is asynchronous (e.g. weather, powerplantcheck, turbinecheck) and auto_drain is enabled:
        param_name = params.get("param") if params else None
        if (
            auto_drain
            and action == "get"
            and param_name in ["weather", "powerplantcheck", "turbinecheck"]
        ):
            logger.info(
                f"Auto-draining queued report for {param_name} (timeout=45s)..."
            )
            drain_res = await self.drain_queued_results(
                session_id=session_id,
                expected_sources={param_name},
                timeout_seconds=45.0,
            )
            report_data = drain_res.get(param_name)
            if report_data:
                data = report_data
                message = f"Successfully retrieved live {param_name} report"
                if param_name == "weather":
                    self.cached_weather = report_data
                elif param_name == "powerplantcheck":
                    self.cached_powerplant = report_data
                elif param_name == "turbinecheck":
                    self.cached_turbinecheck = report_data
        elif action == "get" and param_name == "documentation":
            self.cached_documentation = data if isinstance(data, dict) else {}

        flag = message if "{FLG:" in message else None
        await self.audit.log_event(
            session_id=session_id,
            actor="centrala",
            content=f"probe_api response for '{action}': {message[:200]}",
            step_type=f"probe_{action}_response",
            metadata={
                "code": code,
                "data_keys": list(resp.keys()) if isinstance(resp, dict) else [],
            },
            flag=flag,
        )

        is_success = (code is None or code >= 0) and not (code is not None and code < 0)
        return ProbeWindpowerApiResponse(
            status="success" if is_success else "error",
            action=action,
            code=code,
            message=message,
            data=data,
            hint="Inspect the discovered parameters before proceeding to the solver.",
        )

    async def save_discovery_notes(
        self,
        session_id: str,
        file_path: str,
        notes_content: str,
        reasoning: str = "",
    ) -> SaveDiscoveryNotesResponse:
        """Persists discovered API schemas and technical parameters to workspace."""
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"save_discovery_notes to {file_path}",
            step_type="save_notes",
            metadata={"file_path": file_path, "reasoning": reasoning},
        )

        res = await self.mcp.write_file(
            session_id=session_id,
            file_path=file_path,
            content=notes_content,
            reasoning=reasoning,
        )

        return SaveDiscoveryNotesResponse(
            status="success" if res.get("status") != "error" else "error",
            file_path=file_path,
            message=f"Notes saved to workspace at {file_path}",
            hint="Specifications stored. Ready for solve_and_execute_windpower.",
        )

    async def drain_queued_results(
        self,
        session_id: str,
        expected_sources: set[str],
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        """Continuously drains single-read responses from getResult and categorizes by sourceFunction."""
        collected: dict[str, Any] = {}
        unlock_codes: list[dict[str, Any]] = []
        start_t = time.monotonic()

        while expected_sources - collected.keys():
            if (time.monotonic() - start_t) > timeout_seconds:
                missing = expected_sources - collected.keys()
                logger.warning(f"Timeout draining queued results. Missing: {missing}")
                break

            payload = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {"action": "getResult"},
            }
            resp = await self.mcp.post_web_resource(
                session_id=session_id,
                url=config.AIDEVS_VERIFY_URL,
                payload=payload,
            )

            # Resilient source detection across different Centrala payload structures
            src = (
                resp.get("sourceFunction")
                or resp.get("source")
                or resp.get("function")
                or resp.get("action")
            )
            data_dict = resp.get("data") if isinstance(resp.get("data"), dict) else {}
            if not src:
                if (
                    "weather" in resp
                    or "forecast" in resp
                    or "weather" in data_dict
                    or "forecast" in data_dict
                ):
                    src = "weather"
                elif (
                    "powerplantcheck" in resp
                    or "deficit" in resp
                    or "powerplantcheck" in data_dict
                    or "deficit" in data_dict
                ):
                    src = "powerplantcheck"
                elif (
                    "turbinecheck" in resp
                    or "turbine" in resp
                    or "turbinecheck" in data_dict
                    or "turbine" in data_dict
                ):
                    src = "turbinecheck"
                elif "unlockCode" in resp or "unlockCode" in data_dict:
                    src = "unlockCodeGenerator"

            if src:
                if src == "unlockCodeGenerator":
                    unlock_codes.append(resp)
                    collected.setdefault("unlockCodeGenerator", unlock_codes)
                else:
                    collected[src] = resp
                logger.info(f"Drained queued result for sourceFunction: {src}")
            else:
                # Queue might be empty or item still processing
                poll_delay = 0.2 if "weather" in expected_sources else 0.08
                await asyncio.sleep(poll_delay)

        return collected

    async def execute_schedule(
        self,
        session_id: str,
        configs: list[TurbineConfigPoint] | None = None,
        reasoning: str = "",
    ) -> ExecuteTurbineScheduleResponse:
        """Executes the high-speed Phase 2 hardware configuration within the 40-second window."""
        t0 = time.monotonic()
        logger.info(
            f"Starting execute_schedule (custom_configs_provided={len(configs) if configs else 0})"
        )

        # 1. Start service window ONLY if not already started
        if not self.session_started:
            start_payload = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {"action": "start"},
            }
            start_resp = await self.mcp.post_web_resource(
                session_id=session_id,
                url=config.AIDEVS_VERIFY_URL,
                payload=start_payload,
            )
            self.session_started = True
            logger.info(f"Hardware service window started: {start_resp}")
        else:
            logger.info(
                "Service window already active, preserving active hardware session without duplicate start"
            )

        # 2. Ensure weather, powerplantcheck, and turbinecheck telemetry are available.
        # Note: Centrala strictly requires turbinecheck to be executed in the current session window before startup.
        needed: set[str] = {"turbinecheck"}
        if not self.cached_weather:
            needed.add("weather")
        if not self.cached_powerplant:
            needed.add("powerplantcheck")

            async def _queue(p_name: str):
                p = {
                    "apikey": config.AIDEVS_API_KEY,
                    "task": config.TASK_NAME,
                    "answer": {"action": "get", "param": p_name},
                }
                return await self.mcp.post_web_resource(
                    session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=p
                )

            if needed:
                logger.info(f"Pipelining missing telemetry requests: {needed}")
                await asyncio.gather(*[_queue(p) for p in needed])
                drain_res = await self.drain_queued_results(
                    session_id=session_id,
                    expected_sources=needed,
                    timeout_seconds=25.0,
                )
                if "weather" in drain_res:
                    self.cached_weather = drain_res["weather"]
                if "powerplantcheck" in drain_res:
                    self.cached_powerplant = drain_res["powerplantcheck"]
                if "turbinecheck" in drain_res:
                    self.cached_turbinecheck = drain_res["turbinecheck"]

        # 3. Deterministic weather normalization and schedule calculation
        weather_list = self._normalize_weather(self.cached_weather or {})
        logger.info(
            f"Normalized {len(weather_list)} weather forecast rows for deterministic scheduling"
        )

        # Map storm protection points (windMs > 14.0 m/s -> pitch 90, mode idle)
        storm_configs: dict[str, dict[str, Any]] = {}
        for row in weather_list:
            if row["windMs"] > 14.0:
                ts = f"{row['startDate']} {row['startHour']}"
                storm_configs[ts] = {
                    "startDate": row["startDate"],
                    "startHour": row["startHour"],
                    "windMs": row["windMs"],
                    "pitchAngle": 90,
                    "turbineMode": "idle",
                }
        logger.info(
            f"Identified {len(storm_configs)} storm gale hours requiring 90° idle feathering"
        )

        # Find earliest viable production window (4.0 <= windMs <= 14.0, pitch 0, mode production)
        production_candidate: dict[str, Any] | None = None
        for row in weather_list:
            if 4.0 <= row["windMs"] <= 14.0:
                production_candidate = {
                    "startDate": row["startDate"],
                    "startHour": row["startHour"],
                    "windMs": row["windMs"],
                    "pitchAngle": 0,
                    "turbineMode": "production",
                }
                break

        # Fallback if no window in [4.0, 14.0]
        if not production_candidate and weather_list:
            for row in weather_list:
                if row["windMs"] <= 14.0:
                    production_candidate = {
                        "startDate": row["startDate"],
                        "startHour": row["startHour"],
                        "windMs": row["windMs"],
                        "pitchAngle": 0,
                        "turbineMode": "production",
                    }
                    break

        # Merge configs:
        # Base: all storm protection points
        final_points_map: dict[str, dict[str, Any]] = dict(storm_configs)

        # Include production candidate
        if production_candidate:
            ts_prod = f"{production_candidate['startDate']} {production_candidate['startHour']}"
            if ts_prod not in storm_configs:
                final_points_map[ts_prod] = production_candidate

        # If agent provided custom configs, integrate them while strictly enforcing storm protections
        if configs:
            for pt in configs:
                ts = f"{pt.startDate} {pt.startHour}"
                if ts in storm_configs:
                    # Enforce storm guardrail: MUST be pitch 90 and idle
                    final_points_map[ts] = {
                        "startDate": pt.startDate,
                        "startHour": pt.startHour,
                        "windMs": pt.windMs,
                        "pitchAngle": 90,
                        "turbineMode": "idle",
                    }
                else:
                    final_points_map[ts] = {
                        "startDate": pt.startDate,
                        "startHour": pt.startHour,
                        "windMs": pt.windMs,
                        "pitchAngle": pt.pitchAngle,
                        "turbineMode": pt.turbineMode,
                    }

        points_to_sign = list(final_points_map.values())
        logger.info(
            f"Final schedule formulated: {len(points_to_sign)} total configuration points"
        )

        # 4. Concurrently queue unlockCodeGenerator for all points and turbinecheck if needed
        async def _queue_unlock(pt: dict[str, Any]):
            p = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {
                    "action": "unlockCodeGenerator",
                    "startDate": pt["startDate"],
                    "startHour": pt["startHour"],
                    "windMs": pt["windMs"],
                    "pitchAngle": pt["pitchAngle"],
                },
            }
            return await self.mcp.post_web_resource(
                session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=p
            )

        async def _queue_turbinecheck():
            p = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {"action": "get", "param": "turbinecheck"},
            }
            return await self.mcp.post_web_resource(
                session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=p
            )

        tasks = [_queue_unlock(pt) for pt in points_to_sign]
        if not self.cached_turbinecheck:
            tasks.append(_queue_turbinecheck())

        await asyncio.gather(*tasks)
        logger.info(f"Queued {len(points_to_sign)} unlockCodeGenerator requests")

        # 5. Drain unlock codes
        unlock_codes = await self._drain_unlock_codes(
            session_id=session_id,
            count=len(points_to_sign),
            timeout_seconds=15.0,
        )

        # 6. Map unlock codes and prepare final configs dict
        final_configs: dict[str, dict[str, Any]] = {}
        scheduled_points: list[dict[str, Any]] = []

        for p_dict in points_to_sign:
            ts = f"{p_dict['startDate']} {p_dict['startHour']}"
            code_sig = self._match_unlock_code(p_dict, unlock_codes)
            final_configs[ts] = {
                "pitchAngle": p_dict["pitchAngle"],
                "turbineMode": p_dict["turbineMode"],
                "unlockCode": code_sig,
            }
            scheduled_points.append(
                {
                    "timestamp": ts,
                    "pitchAngle": p_dict["pitchAngle"],
                    "turbineMode": p_dict["turbineMode"],
                    "unlockCode": code_sig,
                }
            )

        # 7. Submit bulk configuration
        config_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "action": "config",
                "configs": final_configs,
            },
        }
        config_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=config_payload,
        )
        logger.info(f"Bulk config transmission response: {config_resp}")

        # 8. Submit final verification action 'done'
        done_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"action": "done"},
        }
        done_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=done_payload,
        )
        logger.info(f"Verification done response: {done_resp}")

        duration = round(time.monotonic() - t0, 2)
        done_msg = str(done_resp.get("message") or "")
        flag = None
        if "{FLG:" in done_msg:
            import re

            m = re.search(r"(\{FLG:[^\}]+\})", done_msg)
            flag = m.group(1) if m else done_msg

        await self.audit.log_event(
            session_id=session_id,
            actor="solver",
            content=f"Phase 2 execute_schedule complete in {duration}s: {done_msg[:200]}",
            step_type="execute_schedule_done",
            metadata={
                "duration_seconds": duration,
                "scheduled_points_count": len(scheduled_points),
                "configs": final_configs,
                "reasoning": reasoning,
            },
            flag=flag,
        )

        is_success = bool(flag or done_resp.get("code") == 0)
        if not is_success:
            self.session_started = False

        return ExecuteTurbineScheduleResponse(
            status="success" if is_success else "error",
            code=done_resp.get("code", 0),
            message=done_msg or "Execution completed",
            flag=flag or "[NO_FLAG]",
            scheduled_points=scheduled_points,
            execution_time_seconds=duration,
            hint="Windpower configuration confirmed by Centrala.",
        )

    async def solve_and_execute_schedule(
        self,
        session_id: str,
        reasoning: str = "",
        max_safe_wind_speed: float | None = None,
        feathering_pitch_angle: int | None = None,
        production_pitch_angle: int | None = None,
    ) -> SolveAndExecuteResponse:
        """Executes the high-speed Phase 2 workflow within the 40-second hardware battery window."""
        t0 = time.monotonic()
        feather_angle = (
            feathering_pitch_angle if feathering_pitch_angle is not None else 90
        )
        prod_angle = (
            production_pitch_angle if production_pitch_angle is not None else 45
        )

        logger.info(
            f"Starting Phase 2 solver (override_max_safe_wind={max_safe_wind_speed}, feather={feather_angle}, prod={prod_angle})"
        )

        # 1. Start the service window (initiates 40s hardware timer)
        start_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"action": "start"},
        }
        start_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=start_payload,
        )
        logger.info(f"Service window started: {start_resp}")

        # 2. Queue all diagnostic and telemetry queries concurrently
        telemetry_requests = [
            {"action": "get", "param": "weather"},
            {"action": "get", "param": "powerplantcheck"},
            {"action": "get", "param": "turbinecheck"},
        ]

        async def _queue(req: dict[str, Any]):
            p = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": req,
            }
            return await self.mcp.post_web_resource(
                session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=p
            )

        await asyncio.gather(*[_queue(req) for req in telemetry_requests])
        logger.info("Queued weather, powerplantcheck, turbinecheck in parallel")

        # 3. Drain queued results with extended 22.0s budget
        expected = {"weather", "powerplantcheck", "turbinecheck"}
        results = await self.drain_queued_results(
            session_id=session_id, expected_sources=expected, timeout_seconds=22.0
        )

        weather_raw = results.get("weather", {})
        _power_raw = results.get("powerplantcheck", {})
        _turbine_raw = results.get("turbinecheck", {})

        # Extract weather rows
        weather_list = self._normalize_weather(weather_raw)
        logger.info(f"Parsed {len(weather_list)} weather forecast rows")

        # Guard: If weather forecast failed to drain, do not submit an empty schedule!
        if not weather_list:
            duration = round(time.monotonic() - t0, 2)
            logger.error(
                "Weather forecast rows unavailable. Aborting schedule submission to prevent turbine failure."
            )
            return SolveAndExecuteResponse(
                status="error",
                code=-1,
                message="Weather forecast unavailable within drain window. Aborted to protect turbine.",
                flag="[NO_FLAG]",
                scheduled_points=[],
                execution_time_seconds=duration,
                hint="Weather data was empty. Do not retry manually; inspect Centrala status.",
            )

        # Sort weather forecast strictly in chronological order
        weather_list.sort(key=lambda r: f"{r['startDate']} {r['startHour']}")

        # Determine safe wind limit: check override, then turbinecheck, fallback to 10.0 m/s
        safe_wind_limit = max_safe_wind_speed
        if safe_wind_limit is None:
            t_data = _turbine_raw.get("data") or _turbine_raw
            if isinstance(t_data, dict):
                for k in [
                    "maxSafeWindSpeed",
                    "durability",
                    "maxWind",
                    "cutOffSpeed",
                    "windLimit",
                ]:
                    if k in t_data:
                        try:
                            safe_wind_limit = float(t_data[k])
                            break
                        except (ValueError, TypeError):
                            pass
        if safe_wind_limit is None:
            safe_wind_limit = 10.0  # conservative safe threshold

        logger.info(f"Resolved effective safe_wind_limit: {safe_wind_limit} m/s")

        # 4. Determine storm feathering points (wind > safe_wind_limit) and first production point
        configs_map: dict[str, dict[str, Any]] = {}
        scheduled_points: list[dict[str, Any]] = []

        storm_rows = []
        production_candidate = None

        for row in weather_list:
            wind = row["windMs"]
            date_str = row["startDate"]
            hour_str = row["startHour"]  # strictly HH:00:00
            ts_key = f"{date_str} {hour_str}"

            if wind > safe_wind_limit:
                storm_rows.append(row)
                configs_map[ts_key] = {
                    "startDate": date_str,
                    "startHour": hour_str,
                    "windMs": wind,
                    "pitchAngle": feather_angle,
                    "turbineMode": "idle",
                }
            elif production_candidate is None and 3.5 <= wind <= safe_wind_limit:
                # First viable production window
                production_candidate = {
                    "startDate": date_str,
                    "startHour": hour_str,
                    "windMs": wind,
                    "pitchAngle": prod_angle,
                    "turbineMode": "production",
                }

        # If no candidate found in [3.5, safe_wind_limit], pick first non-storm hour
        if not production_candidate and weather_list:
            for row in weather_list:
                if row["windMs"] <= safe_wind_limit:
                    production_candidate = {
                        "startDate": row["startDate"],
                        "startHour": row["startHour"],
                        "windMs": row["windMs"],
                        "pitchAngle": prod_angle,
                        "turbineMode": "production",
                    }
                    break

        if production_candidate:
            ts_prod = f"{production_candidate['startDate']} {production_candidate['startHour']}"
            configs_map[ts_prod] = production_candidate

        logger.info(
            f"Identified {len(storm_rows)} storm hours and production hour: {production_candidate}"
        )

        # 5. Concurrently queue unlockCodeGenerator for each configuration point
        async def _queue_unlock(pt: dict[str, Any]):
            p = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {
                    "action": "unlockCodeGenerator",
                    "startDate": pt["startDate"],
                    "startHour": pt["startHour"],
                    "windMs": pt["windMs"],
                    "pitchAngle": pt["pitchAngle"],
                },
            }
            return await self.mcp.post_web_resource(
                session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=p
            )

        points_to_sign = list(configs_map.values())
        if points_to_sign:
            await asyncio.gather(*[_queue_unlock(pt) for pt in points_to_sign])
            logger.info(f"Queued {len(points_to_sign)} unlock code requests")

        # 6. Drain unlock codes
        unlock_codes = await self._drain_unlock_codes(
            session_id=session_id,
            count=len(points_to_sign),
            timeout_seconds=12.0,
        )

        # Match unlock codes to configs
        final_configs: dict[str, dict[str, Any]] = {}
        for pt in points_to_sign:
            ts = f"{pt['startDate']} {pt['startHour']}"
            code_sig = self._match_unlock_code(pt, unlock_codes)
            final_configs[ts] = {
                "pitchAngle": pt["pitchAngle"],
                "turbineMode": pt["turbineMode"],
                "unlockCode": code_sig,
            }
            scheduled_points.append(
                {
                    "timestamp": ts,
                    "pitchAngle": pt["pitchAngle"],
                    "turbineMode": pt["turbineMode"],
                    "unlockCode": code_sig,
                }
            )

        # 7. Submit bulk configuration
        config_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "action": "config",
                "configs": final_configs,
            },
        }
        config_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=config_payload,
        )
        logger.info(f"Transmitted bulk config: {config_resp}")

        # 8. Submit final verification action 'done'
        done_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"action": "done"},
        }
        done_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=done_payload,
        )
        logger.info(f"Verification done response: {done_resp}")

        duration = round(time.monotonic() - t0, 2)
        done_msg = str(done_resp.get("message") or "")
        flag = None
        if "{FLG:" in done_msg:
            import re

            m = re.search(r"(\{FLG:[^\}]+\})", done_msg)
            flag = m.group(1) if m else done_msg

        await self.audit.log_event(
            session_id=session_id,
            actor="solver",
            content=f"Phase 2 complete in {duration}s: {done_msg[:200]}",
            step_type="solve_and_execute_done",
            metadata={
                "duration_seconds": duration,
                "scheduled_points_count": len(scheduled_points),
                "configs": final_configs,
            },
            flag=flag,
        )

        return SolveAndExecuteResponse(
            status="success" if flag or done_resp.get("code") == 0 else "error",
            code=done_resp.get("code", 0),
            message=done_msg or "Execution completed",
            flag=flag or "[NO_FLAG]",
            scheduled_points=scheduled_points,
            execution_time_seconds=duration,
            hint="Windpower configuration confirmed by Centrala.",
        )

    def _normalize_weather(self, weather_resp: dict[str, Any]) -> list[dict[str, Any]]:
        """Extracts and normalizes forecast items into [{startDate, startHour, windMs}, ...]."""
        items = (
            weather_resp.get("data")
            or weather_resp.get("weather")
            or weather_resp.get("forecast")
            or []
        )
        if isinstance(weather_resp, list):
            items = weather_resp

        normalized = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    ts_raw = it.get("timestamp") or it.get("dateTime") or it.get("time")
                    if ts_raw and " " in str(ts_raw):
                        date_val, hour_val = str(ts_raw).split(" ", 1)
                    else:
                        date_val = str(
                            it.get("startDate") or it.get("date") or "2026-09-21"
                        )
                        hour_val = str(
                            it.get("startHour") or it.get("hour") or "00:00:00"
                        )
                    # Force HH:00:00 format
                    if ":" in hour_val:
                        parts = hour_val.split(":")
                        hour_val = f"{parts[0].zfill(2)}:00:00"
                    else:
                        hour_val = f"{hour_val.zfill(2)}:00:00"

                    wind_val = float(
                        it.get("windMs") or it.get("wind") or it.get("speed") or 0.0
                    )
                    normalized.append(
                        {
                            "startDate": date_val,
                            "startHour": hour_val,
                            "windMs": wind_val,
                        }
                    )
        elif isinstance(items, dict):
            for k, v in items.items():
                # Formats like "2026-03-24 18:00:00": 18.5
                date_part, hour_part = "2026-03-24", "00:00:00"
                if " " in k:
                    date_part, hour_part = k.split(" ", 1)
                wind_val = float(v.get("windMs", v) if isinstance(v, dict) else v)
                normalized.append(
                    {
                        "startDate": date_part,
                        "startHour": hour_part,
                        "windMs": wind_val,
                    }
                )

        return normalized

    async def _drain_unlock_codes(
        self, session_id: str, count: int, timeout_seconds: float = 15.0
    ) -> list[dict[str, Any]]:
        """Drains expected number of unlockCodeGenerator responses."""
        collected: list[dict[str, Any]] = []
        start_t = time.monotonic()

        while len(collected) < count:
            if (time.monotonic() - start_t) > timeout_seconds:
                logger.warning(
                    f"Timeout waiting for unlock codes. Got {len(collected)} of {count}"
                )
                break

            payload = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {"action": "getResult"},
            }
            resp = await self.mcp.post_web_resource(
                session_id=session_id,
                url=config.AIDEVS_VERIFY_URL,
                payload=payload,
            )
            src = resp.get("sourceFunction") or resp.get("source")
            data_dict = resp.get("data") if isinstance(resp.get("data"), dict) else {}
            if (
                src == "unlockCodeGenerator"
                or "unlockCode" in resp
                or "unlockCode" in data_dict
            ):
                collected.append(resp)
                logger.info(f"Drained unlock code: {resp}")
            else:
                await asyncio.sleep(0.1)

        return collected

    def _match_unlock_code(
        self, point: dict[str, Any], unlock_codes: list[dict[str, Any]]
    ) -> str:
        """Finds matching unlockCode for point by timestamp or returns available signature, popping matched item."""

        def _get_sig(uc: dict[str, Any]) -> str | None:
            raw_data = uc.get("data")
            data_dict: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
            for field in ("unlockCode", "signature", "token", "hash"):
                val = uc.get(field) or data_dict.get(field)
                if val and isinstance(val, str):
                    return str(val)
            for k, v in uc.items():
                if (
                    k
                    not in (
                        "code",
                        "status",
                        "message",
                        "sourceFunction",
                        "source",
                        "action",
                        "task",
                        "apikey",
                    )
                    and isinstance(v, str)
                    and len(v) > 4
                ):
                    return v
            for k, v in data_dict.items():
                if (
                    k not in ("code", "status", "message")
                    and isinstance(v, str)
                    and len(v) > 4
                ):
                    return v
            return None

        for i, uc in enumerate(unlock_codes):
            signed_p = uc.get("signedParams")
            params: dict[str, Any] = signed_p if isinstance(signed_p, dict) else uc
            uc_date = (
                params.get("startDate")
                or params.get("date")
                or uc.get("startDate")
                or uc.get("date")
            )
            uc_hour = (
                params.get("startHour")
                or params.get("hour")
                or uc.get("startHour")
                or uc.get("hour")
            )
            if uc_date == point["startDate"] and uc_hour == point["startHour"]:
                code = _get_sig(uc)
                if code:
                    unlock_codes.pop(i)
                    return code

        # Fallback to first available unused code
        while unlock_codes:
            uc = unlock_codes.pop(0)
            code = _get_sig(uc)
            if code:
                return code

        return "UNVERIFIED_SIG"
