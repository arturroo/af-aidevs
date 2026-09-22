"""Mission coordination service for Domatowo: AP ledger, Centrala communication, and tool backend."""

import logging
import re
from typing import Any, Literal

import config
from schemas import (
    CalculateRouteResponse,
    DomatowoApiResponse,
    WorkspaceFileReadResponse,
    WorkspaceFileWriteResponse,
)
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.navigation_service import NavigationService

logger = logging.getLogger("services.domatowo")


class DomatowoService:
    """Manages Centrala communication, Action Point accounting, and tool operations."""

    def __init__(
        self,
        audit_service: AuditService | None = None,
        mcp_service: MCPService | None = None,
        navigation_service: NavigationService | None = None,
    ):
        self.audit = audit_service or AuditService()
        self.mcp = mcp_service or MCPService()
        self.nav = navigation_service or NavigationService()

        # State tracking per session
        self.ap_spent: dict[str, int] = {}
        self.extracted_flags: dict[str, str] = {}
        self.survivor_tile: dict[str, str] = {}

    def get_ap_spent(self, session_id: str) -> int:
        return self.ap_spent.get(session_id, 0)

    def get_ap_remaining(self, session_id: str) -> int:
        return max(0, config.MAX_AP_BUDGET - self.get_ap_spent(session_id))

    def _estimate_ap_cost(self, action: str, params: dict[str, Any]) -> int:
        """Estimates AP cost according to Domatowo operational pricing."""
        action_lower = action.lower()
        if action_lower == "create":
            unit_type = str(params.get("type", "")).lower()
            if unit_type == "scout":
                return 5
            if unit_type == "transporter":
                passengers = int(params.get("passengers", 0))
                return 5 + (passengers * 5)
            return 5
        if action_lower == "move":
            # If path provided, count steps; else default to 1 step
            path = params.get("path")
            steps = (
                len(path) - 1
                if isinstance(path, list) and len(path) > 1
                else int(params.get("steps", 1))
            )
            unit_type = str(
                params.get("unit_type", params.get("type", "transporter"))
            ).lower()
            if "scout" in unit_type:
                return steps * 7
            return steps * 1
        if action_lower == "inspect":
            return 1
        if action_lower in ("disembark", "getmap", "help", "getlogs", "reset"):
            return 0
        if action_lower == "callhelicopter":
            return 0
        return 0

    async def execute_action(
        self, session_id: str, action: str, params: dict[str, Any], reasoning: str
    ) -> DomatowoApiResponse:
        """Dispatches an action to Centrala via cr-mcp-web-gateway, updates AP ledger, and checks for flag."""
        # 1. Deduct estimated AP
        cost = self._estimate_ap_cost(action, params)
        curr_spent = self.get_ap_spent(session_id)
        new_spent = curr_spent + cost
        self.ap_spent[session_id] = new_spent

        # 2. Build signed payload
        payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"action": action, **params},
        }

        # 3. Audit log
        await self.audit.log_event(
            session_id=session_id,
            actor="agent_tool:call_domatowo_api",
            content=f"Action: {action}, Params: {params}, Reasoning: {reasoning}, AP Cost: {cost}",
            step_type="tool_execution",
        )

        # 4. Dispatch via MCP web gateway
        res_dict = await self.mcp.post_web_resource(
            session_id=session_id, url=config.AIDEVS_VERIFY_URL, payload=payload
        )

        # 5. Check for AP usage reported by Centrala in response
        if isinstance(res_dict, dict):
            if action.lower() == "reset":
                self.ap_spent[session_id] = 0
            elif "ap_spent" in res_dict:
                self.ap_spent[session_id] = int(res_dict["ap_spent"])
            elif "ap_remaining" in res_dict:
                self.ap_spent[session_id] = config.MAX_AP_BUDGET - int(
                    res_dict["ap_remaining"]
                )

            # 6. Check for flag
            resp_str = str(res_dict)
            flag_match = re.search(r"(\{FLG:[^\}]+\})", resp_str)
            if flag_match:
                extracted = flag_match.group(1)
                self.extracted_flags[session_id] = extracted
                logger.info(f"[{session_id}] EXTRACTED COURSE FLAG: {extracted}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="system:flag_extracted",
                    content=f"Flag captured: {extracted}",
                    flag=extracted,
                )

            # Check if survivor confirmed
            if (
                action.lower() == "getlogs"
                or "survivor" in resp_str.lower()
                or "partyzant" in resp_str.lower()
                or "człowiek" in resp_str.lower()
            ):
                # Inspect for tile mention
                tile_match = re.search(r"\b([A-K](?:1[0-1]|[1-9]))\b", resp_str)
                if tile_match:
                    self.survivor_tile[session_id] = tile_match.group(1)

        status: Literal["success", "error"] = (
            "success" if res_dict.get("code") == 0 or "message" in res_dict else "error"
        )
        hint = "Analyze response and continue mission."
        if status == "error":
            hint = f"Action '{action}' returned an error. Review response details and adapt strategy."
        elif action.lower() == "help":
            hint = "Documentation retrieved. Save api_manual.md, execute reset to clear previous units and restore 300 AP, then update todos.md."
        elif action.lower() == "reset":
            hint = "Board reset complete. 300 AP restored, board state cleared, survivor coordinates rolled. Update todos.md and retrieve tactical map via getMap."
        elif action.lower() == "getmap":
            hint = (
                "Map loaded. Identify candidate BLOK_3P clusters and calculate route."
            )
        elif action.lower() == "inspect":
            hint = "Tile inspected. Query getLogs to verify findings."

        return DomatowoApiResponse(
            status=status,
            response=res_dict,
            ap_spent_estimate=self.get_ap_spent(session_id),
            ap_remaining_estimate=self.get_ap_remaining(session_id),
            hint=hint,
        )

    def calculate_route(
        self,
        origin: str,
        destination: str | None = None,
        target_symbol: str | None = None,
        unit_type: str = "transporter",
        reasoning: str = "",
    ) -> CalculateRouteResponse:
        """Calculates optimal path and AP expenditure using precomputed routing tables."""
        return self.nav.calculate_route(
            origin=origin,
            destination=destination,
            target_symbol=target_symbol,
            unit_type=unit_type,
            reasoning=reasoning,
        )

    async def read_workspace_file(
        self, session_id: str, file_path: str, reasoning: str
    ) -> WorkspaceFileReadResponse:
        """Reads mission file from workspace."""
        res = await self.mcp.read_file(
            session_id=session_id, file_path=file_path, reasoning=reasoning
        )
        read_status: Literal["success", "error", "not_found"] = (
            "success"
            if res.get("status") == "success"
            else ("not_found" if res.get("status") == "not_found" else "error")
        )
        return WorkspaceFileReadResponse(
            status=read_status,
            file_path=file_path,
            content=res.get("content", ""),
            hint="Review todos.md and update checkpoints as operations progress.",
        )

    async def update_workspace_file(
        self, session_id: str, file_path: str, content: str, reasoning: str
    ) -> WorkspaceFileWriteResponse:
        """Writes or updates mission file in workspace."""
        res = await self.mcp.write_file(
            session_id=session_id,
            file_path=file_path,
            content=content,
            reasoning=reasoning,
        )
        write_status: Literal["success", "error"] = (
            "success" if res.get("status") == "success" else "error"
        )
        return WorkspaceFileWriteResponse(
            status=write_status,
            file_path=file_path,
            bytes_written=res.get("bytes_written", len(content)),
            hint="Workspace file updated. Proceed to next operational step.",
        )
