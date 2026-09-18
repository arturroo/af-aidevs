"""Verification and submission service for task savethem."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import config
from services.mcp_service import MCPService

logger = logging.getLogger("services.verification")


class VerificationService:
    """Submits the computed route to Centrala verification endpoint via MCP Web Gateway."""

    def __init__(self, mcp_service: MCPService):
        self.mcp = mcp_service
        self.verify_url = config.AIDEVS_VERIFY_URL
        self.api_key = config.AIDEVS_API_KEY
        self.task_name = config.TASK_NAME

    async def submit_route(
        self, session_id: str, itinerary: List[str]
    ) -> Dict[str, Any]:
        """Submits the itinerary array ["vehicle_name", "dir1", ...] to $AIDEVS_API_VERIFY."""
        payload = {
            "apikey": self.api_key,
            "task": self.task_name,
            "answer": itinerary,
        }
        logger.info(f"Submitting route ({len(itinerary)} elements) to verification at {self.verify_url}")

        res = await self.mcp.post_web_resource(
            session_id=session_id,
            url=self.verify_url,
            payload=payload,
        )

        flag = None
        code = res.get("code")
        msg = str(res.get("message") or res.get("text") or res)

        flag_match = re.search(r"(\{FLG:[^}]+\})", msg)
        if flag_match:
            flag = flag_match.group(1)

        # Save verification artifact in cr-mcp-workspace
        status_str = "SUCCESS" if (code == 0 or flag) else "FAILED"
        result_md = (
            f"# Verification Result: {self.task_name}\n\n"
            f"- **Status**: {status_str}\n"
            f"- **Return Code**: {code}\n"
            f"- **Flag Captured**: {'Yes' if flag else 'No'}\n"
            f"- **Steps Count**: {len(itinerary) - 1}\n\n"
            f"### Itinerary\n"
            f"```json\n{json.dumps(itinerary, indent=2)}\n```\n\n"
            f"### Centrala Response\n"
            f"```json\n{json.dumps(res, indent=2, ensure_ascii=False)}\n```\n"
        )
        await self.mcp.write_file(
            session_id=session_id,
            file_path="verification_result.md",
            content=result_md,
            reasoning="Record Centrala verification response",
        )

        return {
            "success": (code == 0 or flag is not None),
            "code": code,
            "message": msg,
            "flag": flag,
            "raw": res,
        }
