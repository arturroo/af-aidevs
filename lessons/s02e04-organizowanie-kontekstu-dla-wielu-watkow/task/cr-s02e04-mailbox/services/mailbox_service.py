import logging
import re
from typing import Optional, Dict, Any, List
from af_aidevs import model_armor
import config
from schemas import (
    ZmailCallRequest,
    ZmailCallResponse,
    GetEmailDetailsRequest,
    GetEmailDetailsResponse,
    VerifyTaskRequest,
    VerifyTaskResponse,
)
from services.mcp_service import MCPService
from services.audit_service import AuditService

logger = logging.getLogger("services.mailbox")


class MailboxService:
    """Core domain service orchestrating Zmail API interactions, Model Armor screening, and Centrala verification."""

    def __init__(self, mcp_service: MCPService, audit_service: AuditService):
        self.mcp = mcp_service
        self.audit = audit_service

    async def call_zmail(
        self,
        session_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        reasoning: str = "",
    ) -> ZmailCallResponse:
        """Invokes an arbitrary action on the compromised operator Zmail API via cr-mcp-web-gateway."""
        if not config.AIDEVS_API_ZMAIL:
            raise ValueError("AIDEVS_API_ZMAIL endpoint is not configured in environment.")

        payload: Dict[str, Any] = {
            "apikey": config.AIDEVS_API_KEY,
            "action": action,
        }
        if params:
            payload.update(params)

        await self.audit.log_event(
            session_id=session_id,
            actor="mailbox_service",
            content=f"Calling Zmail action '{action}' with reasoning: {reasoning}",
            step_type="zmail_api_call",
            metadata={"action": action, "params": params, "reasoning": reasoning},
        )

        response_dict = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_API_ZMAIL,
            payload=payload,
        )

        hint = None
        if action == "help":
            hint = "Review available actions and parameter keys. Next use search or getInbox to find emails."
        elif action == "search" or "search" in action:
            hint = "Inspect message subjects and IDs. Use get_email_details on high-relevance IDs to read bodies."

        return ZmailCallResponse(
            action=action,
            result=response_dict,
            hint=hint,
        )

    async def get_email_details(
        self,
        session_id: str,
        message_id: str,
        fetch_action: str = "getMessages",
        id_param_key: str = "ids",
        reasoning: str = "",
    ) -> GetEmailDetailsResponse:
        """Fetches full email message content and screens the body through cr-model-armor before passing to LLM."""
        await self.audit.log_event(
            session_id=session_id,
            actor="mailbox_service",
            content=f"Fetching email details for message_id '{message_id}'. Reasoning: {reasoning}",
            step_type="email_fetch_request",
            metadata={"message_id": message_id, "fetch_action": fetch_action},
        )

        # The Zmail API requires action="getMessages" with parameter "ids": [message_id]
        ids_val = [message_id] if isinstance(message_id, (str, int)) else list(message_id)
        payload = {
            "apikey": config.AIDEVS_API_KEY,
            "action": fetch_action,
            id_param_key: ids_val if id_param_key == "ids" else message_id,
        }

        raw_response = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_API_ZMAIL,
            payload=payload,
        )

        # Extract subject, sender, and body from various possible response formats
        items = raw_response.get("items") or []
        if items and isinstance(items, list):
            msg_data = items[0]
        else:
            msg_data = raw_response.get("message") or raw_response.get("result") or raw_response

        if isinstance(msg_data, dict):
            subject = str(msg_data.get("subject") or msg_data.get("title") or "")
            sender = str(msg_data.get("from") or msg_data.get("sender") or "")
            body = str(msg_data.get("message") or msg_data.get("body") or msg_data.get("content") or msg_data.get("text") or str(msg_data))
        else:
            subject = ""
            sender = ""
            body = str(msg_data)

        # Zero-Trust Model Armor Screening
        logger.info(f"Screening email {message_id} ({len(body)} chars) via cr-model-armor")
        is_safe = await model_armor.verify(
            text=body,
            policy_context="zmail_body",
            session_id=session_id,
        )

        if not is_safe:
            logger.warning(f"MODEL ARMOR ALERT: Email {message_id} flagged as unsafe! Quarantining content.")
            await self.audit.log_event(
                session_id=session_id,
                actor="model_armor",
                content=f"Email {message_id} flagged as potentially malicious. Content quarantined.",
                step_type="safety_alert",
                metadata={"message_id": message_id, "subject": subject, "sender": sender},
            )
            body = "[QUARANTINED BY MODEL ARMOR - ADVERSARIAL OR INJECTION CONTENT DETECTED]"
        else:
            await self.audit.log_event(
                session_id=session_id,
                actor="model_armor",
                content=f"Email {message_id} successfully verified as safe by Model Armor.",
                step_type="safety_passed",
                metadata={"message_id": message_id},
            )

        hint = "Inspect body for: attack date (YYYY-MM-DD), employee system password, and confirmation code (starting with SEC-)."
        return GetEmailDetailsResponse(
            message_id=str(message_id),
            subject=subject,
            sender=sender,
            body=body,
            is_sanitized=is_safe,
            hint=hint,
        )

    async def verify_task(
        self,
        session_id: str,
        date: str,
        password: str,
        confirmation_code: str,
        reasoning: str = "",
    ) -> VerifyTaskResponse:
        """Submits candidate date, password, and confirmation_code to Centrala verification hub."""
        verify_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "date": date,
                "password": password,
                "confirmation_code": confirmation_code,
            },
        }

        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"Submitting verification payload: date={date}, confirmation_code={confirmation_code[:8]}...",
            step_type="verification_attempt",
            metadata={"answer": verify_payload["answer"], "reasoning": reasoning},
        )

        resp_dict = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=verify_payload,
        )

        resp_text = str(resp_dict)
        flag = None
        flag_match = re.search(r"(\{FLG:[^}]+\})", resp_text)
        if flag_match:
            flag = flag_match.group(1)

        code = resp_dict.get("code")
        message = resp_dict.get("message") or resp_dict.get("feedback") or resp_text

        if flag or code == 0:
            status = "success"
            hint = "Verification accepted! Course flag obtained."
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content="Verification succeeded with course flag.",
                step_type="verification_success",
                flag="[REDACTED_FLAG]",
                metadata={"response": resp_dict},
            )
        else:
            status = "rejected"
            hint = f"Centrala feedback: {message}. Review extracted fields and poll for new emails."
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Verification rejected: {message}",
                step_type="verification_rejected",
                metadata={"response": resp_dict},
            )

        return VerifyTaskResponse(
            status=status,
            flag=flag,
            feedback=message if status == "rejected" else None,
            hint=hint,
        )
