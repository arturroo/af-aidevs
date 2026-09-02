import os
from typing import Optional, Dict, Any, List
from langchain_mcp_adapters.client import MultiServerMCPClient
from af_aidevs.auth.oidc import GoogleOIDCAuth


def create_mcp_client(
    session_id: str,
    workspace_url: Optional[str] = None,
    web_url: Optional[str] = None,
) -> MultiServerMCPClient:
    """Creates an initialized MultiServerMCPClient configured with OIDC auth and X-Session-ID headers."""
    resolved_workspace_url = workspace_url or os.getenv("MCP_WORKSPACE_URL") or "https://cr-mcp-workspace-qsvqxjqyrq-oa.a.run.app"
    resolved_web_url = web_url or os.getenv("MCP_WEB_GATEWAY_URL") or "https://cr-mcp-web-gateway-qsvqxjqyrq-oa.a.run.app"

    server_configs: Dict[str, Any] = {}

    if resolved_workspace_url:
        server_configs["workspace"] = {
            "transport": "http",
            "url": f"{resolved_workspace_url}/mcp",
            "headers": {"X-Session-ID": session_id},
            "auth": GoogleOIDCAuth(resolved_workspace_url),
        }

    if resolved_web_url:
        server_configs["web"] = {
            "transport": "http",
            "url": f"{resolved_web_url}/mcp",
            "headers": {"X-Session-ID": session_id},
            "auth": GoogleOIDCAuth(resolved_web_url),
        }

    return MultiServerMCPClient(server_configs)


async def get_all_mcp_tools(
    session_id: str,
    workspace_url: Optional[str] = None,
    web_url: Optional[str] = None,
) -> List[Any]:
    """Convenience helper to create a client and retrieve all MCP tools in one call."""
    client = create_mcp_client(session_id=session_id, workspace_url=workspace_url, web_url=web_url)
    return await client.get_tools()
