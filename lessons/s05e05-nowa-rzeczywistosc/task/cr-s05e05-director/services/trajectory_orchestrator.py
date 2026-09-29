import asyncio
import logging
import time
from typing import Any

from schemas import PhaseResult, RunTaskRequest, RunTaskResponse
from services.audit_service import audit_service, generate_session_id
from services.central_api_service import central_api
from services.cockpit_client import cockpit_client
from services.stabilization_service import stabilization_service
from services.temporal_math import compute_sync_ratio, get_target_internal_mode
from services.temporal_table import lookup_pwr

logger = logging.getLogger("trajectory_orchestrator")


class TrajectoryOrchestrator:
    """Master flight controller managing the 3-hop temporal displacement trajectory."""

    async def execute_phase(
        self,
        phase_num: int,
        target_date: str,
        pta: bool,
        ptb: bool,
        session_id: str,
        model: str | None = None,
        thinking_level: str | None = None,
    ) -> PhaseResult:
        """Executes a single discrete trajectory hop or tunnel establishment."""
        logger.info(
            "=== Starting Trajectory Phase %d: Target %s (session=%s) ===",
            phase_num,
            target_date,
            session_id,
        )

        parts = target_date.split("-")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])

        sync_ratio = compute_sync_ratio(year, month, day)
        pwr = lookup_pwr(year)
        target_imode = get_target_internal_mode(year)

        logger.info(
            "Phase %d Calculated Physics: year=%d, month=%d, day=%d -> syncRatio=%.2f, PWR=%d, internalMode=%d",
            phase_num,
            year,
            month,
            day,
            sync_ratio,
            pwr,
            target_imode,
        )

        await audit_service.log_event(
            session_id=session_id,
            actor="director",
            phase=phase_num,
            event_type="CALCULATE_PHYSICS",
            content=f"Target {target_date}: syncRatio={sync_ratio}, PWR={pwr}, imode={target_imode}",
        )

        # Step 1: Ensure Cockpit is in standby mode for safe API reconfiguration
        logger.info(
            "Ensuring device is in standby mode prior to register configuration..."
        )
        try:
            await cockpit_client.set_controls(
                pta=pta,
                ptb=ptb,
                pwr=pwr,
                mode="standby",
                session_id=session_id,
            )
        except Exception as e:
            logger.warning("Unable to set preliminary standby mode on Cockpit: %s", e)

        # Step 2: Configure Central API registers
        logger.info("Injecting temporal coordinates into Central registers...")
        await central_api.configure("year", year)
        await central_api.configure("month", month)
        await central_api.configure("day", day)
        await central_api.configure("syncRatio", sync_ratio)

        # Step 3: Read stabilization guidance and resolve parameter
        config_status = await central_api.get_config()
        logger.info("Central getConfig full payload: %s", config_status)
        raw_data = config_status.get("data")
        data_payload: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        raw_msg = config_status.get("message") or ""
        advice_hint = (
            config_status.get("needConfig")
            or data_payload.get("needConfig")
            or config_status.get("advice")
            or data_payload.get("advice")
            or config_status.get("hint")
            or data_payload.get("hint")
            or config_status.get("stabilizationAdvice")
            or data_payload.get("stabilizationAdvice")
            or (raw_msg if raw_msg != "Current configuration returned." else None)
            or "Nominal conditions. No additional offset required."
        )

        logger.info("Received Central stabilization hint: '%s'", advice_hint)
        resolved_stabilization = await stabilization_service.resolve_stabilization(
            api_hint=advice_hint,
            target_date=target_date,
            model=model,
            thinking_level=thinking_level,
        )

        logger.info("Configuring resolved stabilization: '%s'", resolved_stabilization)
        await central_api.configure("stabilization", resolved_stabilization)

        await audit_service.log_event(
            session_id=session_id,
            actor="director",
            phase=phase_num,
            event_type="CONFIGURE_REGISTERS",
            content=f"Registers configured: sync={sync_ratio}, stab={resolved_stabilization}",
        )

        # Step 4: Instruct Cockpit to engage active controls and shield
        logger.info(
            "A2A dispatch: Setting active flight controls on Cockpit (PTA=%s, PTB=%s, PWR=%d, mode=active)",
            pta,
            ptb,
            pwr,
        )
        controls_res = await cockpit_client.set_controls(
            pta=pta, ptb=ptb, pwr=pwr, mode="active", session_id=session_id
        )

        reported_flux = controls_res.get("flux_density", 0)
        logger.info("Cockpit reports core flux density: %d%%", reported_flux)

        # Step 5: Instruct Cockpit to wait for matching internalMode and click ignition sphere
        logger.info("A2A dispatch: Activating jump on internalMode=%d...", target_imode)
        jump_res = await cockpit_client.activate_jump(
            target_imode=target_imode,
            timeout_seconds=30.0,
            session_id=session_id,
        )

        success = jump_res.get("success", False)
        jump_code = jump_res.get("jump_code")
        battery = jump_res.get("battery_status")
        flag = jump_res.get("flag")
        msg = jump_res.get("message", "")

        logger.info(
            "Phase %d Jump Result: success=%s, code=%s, battery=%s, flag=%s, msg='%s'",
            phase_num,
            success,
            jump_code,
            battery,
            flag,
            msg,
        )

        await audit_service.log_event(
            session_id=session_id,
            actor="director",
            phase=phase_num,
            event_type="JUMP_RESULT",
            content=f"Phase {phase_num} finished: success={success}, battery={battery}, flag={flag}",
            metadata={"jump_code": jump_code, "flag": flag},
        )

        if not success:
            raise RuntimeError(f"Phase {phase_num} time travel failed: {msg}")

        return PhaseResult(
            phase=phase_num,
            target=target_date,
            status="COMPLETED",
            battery=battery,
            details=f"Jump successful. Code={jump_code}, Flag={flag}",
        )

    async def run_mission(self, request: RunTaskRequest) -> RunTaskResponse:
        """Executes full autonomous 3-hop trajectory to establish time tunnel to 2024."""
        session_id = request.session_id or generate_session_id()
        start_time = time.monotonic()
        completed_phases: list[PhaseResult] = []
        captured_flag: str | None = None

        logger.info("================================================================")
        logger.info(
            "INITIATING AUTONOMOUS TEMPORAL DISPLACEMENT MISSION: %s", session_id
        )
        logger.info("================================================================")

        await audit_service.log_event(
            session_id=session_id,
            actor="director",
            event_type="MISSION_START",
            content="Initiating 3-phase trajectory navigation.",
            metadata={
                "model": request.model,
                "thinking_level": request.thinking_level,
            },
        )

        try:
            if request.targets:
                hops: list[dict[str, Any]] = []
                if request.recharge_first:
                    hops.append({"target": "2238-11-05", "is_tunnel": False})

                for i, target in enumerate(request.targets):
                    is_last = i == len(request.targets) - 1
                    hops.append(
                        {
                            "target": target,
                            "is_tunnel": is_last and request.is_tunnel_last,
                        }
                    )

                cfg_initial = await central_api.get_config()
                current_date = cfg_initial.get("config", {}).get(
                    "currentDate", "2026-09-29"
                )
                logger.info(
                    "Executing dynamic trajectory: current=%s, total_hops=%d",
                    current_date,
                    len(hops),
                )

                for idx, hop in enumerate(hops, 1):
                    target_date = hop["target"]
                    is_tunnel = hop["is_tunnel"]

                    if is_tunnel:
                        pta = True
                        ptb = True
                    elif target_date < current_date:
                        pta = True
                        ptb = False
                    else:
                        pta = False
                        ptb = True

                    logger.info(
                        "Dynamic Hop %d/%d: %s -> %s (PTA=%s, PTB=%s, Tunnel=%s)",
                        idx,
                        len(hops),
                        current_date,
                        target_date,
                        pta,
                        ptb,
                        is_tunnel,
                    )

                    phase_res = await self.execute_phase(
                        phase_num=idx,
                        target_date=target_date,
                        pta=pta,
                        ptb=ptb,
                        session_id=session_id,
                        model=request.model,
                        thinking_level=request.thinking_level,
                    )
                    completed_phases.append(phase_res)

                    if "Flag=" in (phase_res.details or ""):
                        import re

                        flag_match = re.search(
                            r"Flag=(\{FLG:[^}]+\})", phase_res.details or ""
                        )
                        if flag_match:
                            captured_flag = flag_match.group(1)

                    current_date = target_date
                    await asyncio.sleep(1.0)
            else:
                # -------------------------------------------------------------
                # Canonical 3-Phase Course Trajectory
                # -------------------------------------------------------------
                phase1_res = await self.execute_phase(
                    phase_num=1,
                    target_date="2238-11-05",
                    pta=False,
                    ptb=True,  # Future transit
                    session_id=session_id,
                    model=request.model,
                    thinking_level=request.thinking_level,
                )
                completed_phases.append(phase1_res)

                await asyncio.sleep(1.0)

                phase2_res = await self.execute_phase(
                    phase_num=2,
                    target_date="2026-09-29",
                    pta=True,  # Past transit from 2238 to 2026
                    ptb=False,
                    session_id=session_id,
                    model=request.model,
                    thinking_level=request.thinking_level,
                )
                completed_phases.append(phase2_res)

                await asyncio.sleep(1.0)

                phase3_res = await self.execute_phase(
                    phase_num=3,
                    target_date="2024-11-12",
                    pta=True,
                    ptb=True,  # Both ports engaged for Tunnel mode!
                    session_id=session_id,
                    model=request.model,
                    thinking_level=request.thinking_level,
                )
                completed_phases.append(phase3_res)

                if "Flag=" in (phase3_res.details or ""):
                    import re

                    flag_match = re.search(
                        r"Flag=(\{FLG:[^}]+\})", phase3_res.details or ""
                    )
                    if flag_match:
                        captured_flag = flag_match.group(1)

            elapsed = round(time.monotonic() - start_time, 2)
            logger.info(
                "MISSION COMPLETE! Duration=%.2fs, Flag=%s",
                elapsed,
                captured_flag,
            )

            await audit_service.log_event(
                session_id=session_id,
                actor="director",
                event_type="MISSION_SUCCESS",
                content=f"Temporal tunnel established in {elapsed}s. Flag captured.",
                metadata={"flag": captured_flag, "duration_s": elapsed},
            )

            return RunTaskResponse(
                success=True,
                session_id=session_id,
                flag=captured_flag,
                execution_time_seconds=elapsed,
                phases_completed=completed_phases,
                message="Time tunnel to 2024-11-12 locked. Rendezvous with Rafał accomplished.",
            )

        except Exception as e:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.error("Mission failed after %.2fs: %s", elapsed, e)
            await audit_service.log_event(
                session_id=session_id,
                actor="director",
                event_type="MISSION_FAILED",
                content=f"Mission terminated with error: {e}",
            )
            return RunTaskResponse(
                success=False,
                session_id=session_id,
                flag=None,
                execution_time_seconds=elapsed,
                phases_completed=completed_phases,
                message=f"Mission failed: {e}",
            )


orchestrator = TrajectoryOrchestrator()
