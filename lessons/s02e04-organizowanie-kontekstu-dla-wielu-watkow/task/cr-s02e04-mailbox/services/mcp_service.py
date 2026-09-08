import os
import json
import logging
import re
import time
import subprocess
from typing import Optional, Dict, Any, List
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient
import config

logger = logging.getLogger("services.mcp")

# Optional LangSmith tracing decorator for Service Layer methods
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator


class SmartOIDCAuth(httpx.Auth):
    """Resilient OIDC Auth fetching identity tokens via Cloud Run metadata, local gcloud CLI, or env overrides."""

    def __init__(self, audience: str, env_var: Optional[str] = None):
        self.audience = audience
        self.env_var = env_var
        self._token: Optional[str] = None
        self._expiry: float = 0.0

    def _get_token(self) -> str:
        # 1. Environment variable override
        if self.env_var:
            env_token = os.getenv(self.env_var)
            if env_token:
                return env_token

        now = time.time()
        # 2. Return cached token if still valid
        if self._token and (now < self._expiry):
            return self._token

        # 3. Try metadata server / ADC (Cloud Run environment)
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
            token = id_token.fetch_id_token(Request(), self.audience)
            if token:
                self._token = token
                self._expiry = now + 3000
                return token
        except Exception:
            pass

        # 4. Try gcloud CLI for local workstation development
        try:
            res = subprocess.run(
                ["gcloud", "auth", "print-identity-token", f"--audiences={self.audience}"],
                capture_output=True,
                text=True,
                check=True,
                shell=True,
            )
            token = res.stdout.strip()
            if token:
                self._token = token
                self._expiry = now + 3000
                logger.info(f"Retrieved fresh identity token for audience {self.audience} via gcloud")
                return token
        except Exception as e:
            logger.warning(f"Could not fetch identity token for {self.audience}: {e}")

        return ""

    def auth_flow(self, request: httpx.Request):
        token = self._get_token()
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        yield request


class MCPService:
    """Unified client service orchestrating outbound network egress and workspace access via MCP microservices."""

    def __init__(
        self,
        workspace_url: Optional[str] = None,
        web_url: Optional[str] = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self._tools_cache: Dict[str, Dict[str, Any]] = {}

    async def get_tools_for_session(self, session_id: str) -> List[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
        server_configs: Dict[str, Any] = {}

        if self.web_url:
            server_configs["web"] = {
                "transport": "http",
                "url": f"{self.web_url.rstrip('/')}/mcp",
                "headers": {"X-Session-ID": session_id},
                "auth": SmartOIDCAuth(self.web_url, env_var="MCP_WEB_GATEWAY_TOKEN"),
            }

        client = MultiServerMCPClient(server_configs)
        tools = await client.get_tools()

        tool_map: Dict[str, Any] = {}
        for t in tools:
            name = t.name
            tool_map[name] = t
            if "_" in name:
                short_name = name.split("_", 1)[1]
                tool_map.setdefault(short_name, t)
        self._tools_cache[session_id] = tool_map
        return tools

    def _get_tool(self, session_id: str, tool_name: str) -> Any:
        session_tools = self._tools_cache.get(session_id)
        if not session_tools:
            raise RuntimeError(f"MCP tools not initialized for session {session_id}. Call get_tools_for_session first.")

        if tool_name in session_tools:
            return session_tools[tool_name]

        for k, v in session_tools.items():
            if k.endswith(tool_name):
                return v

        raise ValueError(f"MCP tool '{tool_name}' not found. Available: {list(session_tools.keys())}")

    @staticmethod
    def _extract_text_content(result: Any) -> str:
        """Robustly unwraps text content from various LangChain/MCP tool return structures."""
        if hasattr(result, "content"):
            return MCPService._extract_text_content(result.content)

        if isinstance(result, list):
            texts = []
            for item in result:
                if isinstance(item, dict):
                    if "text" in item:
                        texts.append(str(item["text"]))
                    elif "content" in item:
                        texts.append(str(item["content"]))
                    else:
                        texts.append(json.dumps(item))
                elif hasattr(item, "text"):
                    texts.append(str(item.text))
                else:
                    texts.append(str(item))
            joined = "\n".join(texts)
            return MCPService._extract_text_content(joined)

        if isinstance(result, dict):
            if "content" in result and result["content"] is not None:
                return MCPService._extract_text_content(result["content"])
            if "text" in result and result["text"] is not None:
                return MCPService._extract_text_content(result["text"])
            return json.dumps(result)

        if isinstance(result, str):
            clean = result.strip()
            if clean.startswith("{") and clean.endswith("}"):
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict):
                        if "content" in parsed and parsed["content"] is not None:
                            return MCPService._extract_text_content(parsed["content"])
                        if "text" in parsed and parsed["text"] is not None:
                            return MCPService._extract_text_content(parsed["text"])
                except Exception:
                    pass
            return result

        return str(result)

    @traceable(run_type="tool", name="mcp.post_web_resource")
    async def post_web_resource(self, session_id: str, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an outbound HTTP POST request via cr-mcp-web-gateway without direct container egress."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        tool = self._get_tool(session_id, "post_web_resource")
        try:
            raw_result = await tool.ainvoke({"url": url, "payload": payload})
            text_result = self._extract_text_content(raw_result)
            try:
                return json.loads(text_result)
            except Exception:
                json_match = re.search(r"(\{.*\})", text_result, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except Exception:
                        pass
                return {"raw_output": text_result}
        except Exception as e:
            err_str = str(e)
            logger.warning(f"post_web_resource caught response error: {err_str}")
            json_match = re.search(r"(\{.*\})", err_str, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    if isinstance(parsed, dict) and ("code" in parsed or "message" in parsed or "error" in parsed):
                        return parsed
                except Exception:
                    pass
            raise e

    async def write_file(self, session_id: str, file_path: str, content: str) -> str:
        """Writes content to a file in the session workspace or local filesystem."""
        try:
            if self.workspace_url and session_id in self._tools_cache:
                tool = self._tools_cache[session_id].get("write_file")
                if tool:
                    result = await tool.ainvoke({
                        "reasoning": f"Writing summary report to '{file_path}'",
                        "file_path": file_path,
                        "content": content,
                    })
                    return self._extract_text_content(result)
        except Exception as e:
            logger.warning(f"Workspace write failed ({e}). Writing locally.")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written locally to {file_path}"
