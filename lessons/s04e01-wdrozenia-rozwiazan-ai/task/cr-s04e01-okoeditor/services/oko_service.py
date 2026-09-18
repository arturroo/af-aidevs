import json
import logging
import re
from html.parser import HTMLParser
from typing import Any

import httpx

import config
from schemas import CallOkoApiResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService

logger = logging.getLogger("services.oko")


class SimpleHtmlToMarkdown(HTMLParser):
    """Lightweight streaming HTML to Markdown converter."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.current_line: list[str] = []
        self.in_script: bool = False
        self.in_style: bool = False
        self.current_link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in ("script", "style"):
            self.in_script = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_line()
            level = int(tag[1])
            self.current_line.append("#" * level + " ")
        elif tag in ("p", "div", "li", "tr", "section", "article"):
            self._flush_line()
        elif tag == "a":
            self.current_link = attrs_dict.get("href") or ""
            self.current_line.append("[")
        elif tag in ("strong", "b"):
            self.current_line.append("**")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.in_script = False
        elif tag in (
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "div",
            "li",
            "tr",
            "section",
            "article",
        ):
            self._flush_line()
        elif tag == "a":
            if self.current_link:
                self.current_line.append(f"]({self.current_link})")
                self.current_link = None
            else:
                self.current_line.append("]")
        elif tag in ("strong", "b"):
            self.current_line.append("**")

    def handle_data(self, data: str) -> None:
        if self.in_script or self.in_style:
            return
        text = data.strip()
        if text:
            if self.current_line and not self.current_line[-1].endswith(
                (" ", "[", "(")
            ):
                self.current_line.append(" ")
            self.current_line.append(text)

    def _flush_line(self) -> None:
        if self.current_line:
            line = "".join(self.current_line).strip()
            if line:
                self.lines.append(line)
            self.current_line = []

    def get_markdown(self) -> str:
        self._flush_line()
        return "\n\n".join(self.lines)


class OkoService:
    """Service handling covert operations on OKO surveillance records via Centrala backdoor API."""

    def __init__(
        self,
        mcp_service: MCPService | None = None,
        audit_service: AuditService | None = None,
    ):
        self.mcp = mcp_service or MCPService()
        self.audit = audit_service or AuditService()

    async def call_api(
        self,
        session_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        reasoning: str = "",
    ) -> CallOkoApiResponse:
        """Invokes Centrala backdoor API for task 'okoeditor' with structured auditing and state persistence."""
        answer_payload: dict[str, Any] = {"action": action}
        if params and isinstance(params, dict):
            answer_payload.update(params)

        request_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": answer_payload,
        }

        # Mask API key in audit logs
        masked_payload = {
            **request_payload,
            "apikey": "***" if config.AIDEVS_API_KEY else "MISSING",
        }

        logger.info(
            f"[{session_id}] Calling OKO API: action='{action}' | reasoning='{reasoning}'"
        )
        await self.audit.log_event(
            session_id=session_id,
            actor="oko-service",
            content=f"Invoking action '{action}': {reasoning[:200]}",
            step_type="api_call",
            metadata={"action": action, "payload": masked_payload},
        )

        try:
            res_dict = await self.mcp.post_web_resource(
                session_id=session_id,
                url=config.AIDEVS_VERIFY_URL,
                payload=request_payload,
            )

            # Persist raw response to cr-mcp-workspace
            await self.mcp.write_file(
                session_id=session_id,
                file_path=f"api_calls/{action}_response.json",
                content=json.dumps(res_dict, indent=2, ensure_ascii=False),
                reasoning=f"Persisting response for OKO action {action}",
            )

            code = res_dict.get("code", 0 if "message" in res_dict else -1)
            message = str(res_dict.get("message", res_dict.get("error", "")))
            # Code 0 is standard success, and Centrala help action returns code 120 as valid documentation response
            status = (
                "success"
                if (code == 0 or (action == "help" and code == 120))
                else "error"
            )

            # Check for course flag in message
            flag = message if "{FLG:" in message else None

            await self.audit.log_event(
                session_id=session_id,
                actor="oko-service",
                content=f"Action '{action}' returned code {code}: {message[:200]}",
                step_type="api_response",
                metadata={"action": action, "code": code, "status": status},
                flag=flag,
            )

            hint = self._generate_hint(action, code, message, res_dict)

            return CallOkoApiResponse(
                status=status,
                action=action,
                code=code,
                message=message,
                data=res_dict,
                hint=hint,
            )

        except Exception as e:
            err_msg = str(e)
            logger.error(f"[{session_id}] OKO API action '{action}' failed: {err_msg}")
            await self.audit.log_event(
                session_id=session_id,
                actor="oko-service",
                content=f"Action '{action}' exception: {err_msg[:300]}",
                step_type="api_error",
                metadata={"action": action, "error": err_msg[:300]},
            )
            return CallOkoApiResponse(
                status="error",
                action=action,
                code=-1,
                message=err_msg,
                data=None,
                hint=f"API call encountered an error. Check parameters and retry action '{action}'.",
            )

    @staticmethod
    def _generate_hint(
        action: str, code: int, message: str, res_dict: dict[str, Any]
    ) -> str:
        """Generates dynamic progressive disclosure hints for the LLM."""
        if code != 0 and not (action == "help" and code == 120):
            return f"Action '{action}' failed with code {code}. Analyze the error message and adjust your parameters."

        if action == "help":
            return (
                "Help documentation retrieved. Centrala backdoor accepts 'update' with {page, id, title, content, done}. "
                "To discover 32-char hex IDs for Skolwin and other cities without triggering web UI alarms, "
                "use tool 'fetch_oko_page(page=\"incydenty\")' and 'fetch_oko_page(page=\"zadania\")'."
            )

        if action == "done":
            if "{FLG:" in message:
                return "Mission accomplished! Course flag captured."
            return (
                "Centrala processed 'done'. Verify if the mission objectives were met."
            )

        return f"Action '{action}' completed successfully. Proceed to the next required operation."

    async def fetch_page(
        self,
        session_id: str,
        page: str = "incydenty",
        reasoning: str = "",
    ) -> dict[str, Any]:
        """Covertly fetches a subpage from the operator OKO web panel via read-only GET requests,
        extracts surveillance record IDs and titles, converts HTML to Markdown, and persists both files to workspace.
        """
        clean_page = page.strip("/").strip()
        base_url = (config.AIDEVS_OKO_PANEL_URL or "https://oko.ag3nts.org").rstrip("/")
        target_url = f"{base_url}/{clean_page}" if clean_page else f"{base_url}/"

        logger.info(
            f"[{session_id}] Covertly fetching OKO page '{clean_page}' ({target_url}): {reasoning}"
        )
        await self.audit.log_event(
            session_id=session_id,
            actor="oko-service",
            content=f"Covert page fetch '{clean_page}': {reasoning[:200]}",
            step_type="fetch_page",
            metadata={"page": clean_page, "url": target_url},
        )

        try:
            login_data = {
                "action": "login",
                "login": "Zofia",
                "password": "Zofia2026!",
                "access_key": config.AIDEVS_API_KEY,
            }

            async with httpx.AsyncClient(follow_redirects=True, timeout=25.0) as client:
                # 1. Authenticate to establish session cookie
                login_resp = await client.post(f"{base_url}/", data=login_data)
                if login_resp.status_code >= 400:
                    raise RuntimeError(
                        f"OKO panel authentication failed with status {login_resp.status_code}"
                    )

                # 2. Perform passive GET request to target subpage
                resp = await client.get(target_url)
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Fetching '{target_url}' failed with status {resp.status_code}"
                    )
                html_content = resp.text

            # 3. Convert HTML to clean Markdown
            parser = SimpleHtmlToMarkdown()
            parser.feed(html_content)
            markdown_content = parser.get_markdown()

            # 4. Extract all surveillance record links and 32-char hex IDs
            discovered_links: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for m in re.finditer(
                r'<a\s+[^>]*href=["\']/(?P<page>incydenty|zadania|notatki)/(?P<id>[a-f0-9]{32})["\'][^>]*>(?P<inner>.*?)</a>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            ):
                rec_id = m.group("id")
                if rec_id not in seen_ids:
                    seen_ids.add(rec_id)
                    inner_text = re.sub(r"<[^>]+>", " ", m.group("inner"))
                    clean_title = " ".join(inner_text.split())[:120]
                    discovered_links.append(
                        {
                            "page": m.group("page"),
                            "id": rec_id,
                            "title": clean_title,
                            "url": f"/{m.group('page')}/{rec_id}",
                        }
                    )

            # 5. Persist raw HTML and converted Markdown to workspace
            page_tag = clean_page.replace("/", "_") or "index"
            html_file = f"oko_{page_tag}.html"
            md_file = f"oko_{page_tag}.md"

            await self.mcp.write_file(
                session_id=session_id,
                file_path=html_file,
                content=html_content,
                reasoning=f"Persisting raw HTML for OKO page {clean_page}",
            )
            await self.mcp.write_file(
                session_id=session_id,
                file_path=md_file,
                content=markdown_content,
                reasoning=f"Persisting converted Markdown for OKO page {clean_page}",
            )

            hint = (
                f"Successfully fetched '{clean_page}' and discovered {len(discovered_links)} records with 32-char hex IDs. "
                f"Both '{html_file}' and '{md_file}' are saved in workspace."
            )
            if discovered_links:
                hint += (
                    " Use the discovered IDs with call_oko_api(action='update', ...)!"
                )

            await self.audit.log_event(
                session_id=session_id,
                actor="oko-service",
                content=f"Page '{clean_page}' saved. Discovered {len(discovered_links)} records.",
                step_type="fetch_page_success",
                metadata={
                    "page": clean_page,
                    "discovered_count": len(discovered_links),
                    "html_file": html_file,
                    "md_file": md_file,
                },
            )

            return {
                "status": "success",
                "page": clean_page,
                "html_file": html_file,
                "markdown_file": md_file,
                "discovered_links": discovered_links,
                "preview": markdown_content[:800],
                "hint": hint,
            }

        except Exception as e:
            err_msg = str(e)
            logger.error(
                f"[{session_id}] Error fetching OKO page '{clean_page}': {err_msg}"
            )
            await self.audit.log_event(
                session_id=session_id,
                actor="oko-service",
                content=f"Error fetching page '{clean_page}': {err_msg[:300]}",
                step_type="fetch_page_error",
                metadata={"page": clean_page, "error": err_msg[:300]},
            )
            return {
                "status": "error",
                "page": clean_page,
                "html_file": "",
                "markdown_file": "",
                "discovered_links": [],
                "preview": "",
                "hint": f"Failed to fetch page '{clean_page}': {err_msg}",
            }
