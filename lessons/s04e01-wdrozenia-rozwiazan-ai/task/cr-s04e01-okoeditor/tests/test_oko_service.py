"""Unit tests for OkoService with mocked MCP interactions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.oko_service import OkoService


@pytest.mark.asyncio
async def test_oko_service_call_api_success():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(
        return_value={
            "code": 0,
            "message": "Command executed successfully",
            "data": {"actions": ["help"]},
        }
    )
    mock_mcp.write_file = AsyncMock(return_value={"status": "success"})

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    service = OkoService(mcp_service=mock_mcp, audit_service=mock_audit)
    response = await service.call_api(
        session_id="test_session",
        action="help",
        params=None,
        reasoning="Testing help discovery",
    )

    assert response.status == "success"
    assert response.code == 0
    assert response.action == "help"
    assert "help" in response.hint.lower()
    assert mock_mcp.post_web_resource.called
    assert mock_audit.log_event.called


@pytest.mark.asyncio
async def test_oko_service_call_api_error_response():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(
        return_value={"code": -1, "message": "Unknown action"}
    )
    mock_mcp.write_file = AsyncMock(return_value={"status": "success"})

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    service = OkoService(mcp_service=mock_mcp, audit_service=mock_audit)
    response = await service.call_api(
        session_id="test_session",
        action="invalid_cmd",
        reasoning="Testing invalid command",
    )

    assert response.status == "error"
    assert response.code == -1
    assert "Unknown action" in response.message
    assert "failed with code -1" in response.hint


@pytest.mark.asyncio
async def test_oko_service_flag_detection():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(
        return_value={"code": 0, "message": "{FLG:SECRET_OKO_VERIFIED}"}
    )
    mock_mcp.write_file = AsyncMock(return_value={"status": "success"})

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    service = OkoService(mcp_service=mock_mcp, audit_service=mock_audit)
    response = await service.call_api(
        session_id="test_session",
        action="done",
        reasoning="Concluding mission",
    )

    assert response.status == "success"
    assert "{FLG:SECRET_OKO_VERIFIED}" in response.message
    assert "Mission accomplished" in response.hint


@pytest.mark.asyncio
async def test_oko_service_help_code_120():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(
        return_value={
            "code": 120,
            "message": "OKO Editor API help.",
            "commands": {"action": "help|update|done"},
        }
    )
    mock_mcp.write_file = AsyncMock(return_value={"status": "success"})

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    service = OkoService(mcp_service=mock_mcp, audit_service=mock_audit)
    response = await service.call_api(
        session_id="test_session",
        action="help",
        reasoning="Discovering API via help",
    )

    assert response.status == "success"
    assert response.code == 120
    assert "fetch_oko_page" in response.hint


@pytest.mark.asyncio
async def test_oko_service_fetch_page():
    mock_mcp = MagicMock()
    mock_mcp.write_file = AsyncMock(return_value={"status": "success"})
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    service = OkoService(mcp_service=mock_mcp, audit_service=mock_audit)

    mock_html = """
    <html><body>
    <h1>Ostatnie incydenty</h1>
    <div class="list">
      <a href="/incydenty/380792b2c86d9c5be670b3bde48e187b" class="entry-link">
        <div class="list-item">
          <strong>MOVE03 Trudne do klasyfikacji ruchy nieopodal miasta Skolwin</strong>
          <p>Czujniki zarejestrowały obiekt.</p>
        </div>
      </a>
    </div>
    </body></html>
    """

    class MockResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, data=None):
            return MockResponse("OK", 200)

        async def get(self, url):
            return MockResponse(mock_html, 200)

    import httpx

    original_client = httpx.AsyncClient
    httpx.AsyncClient = MockAsyncClient  # type: ignore
    try:
        res = await service.fetch_page(
            session_id="test_session",
            page="incydenty",
            reasoning="Testing fetch",
        )
        assert res["status"] == "success"
        assert res["html_file"] == "oko_incydenty.html"
        assert res["markdown_file"] == "oko_incydenty.md"
        assert len(res["discovered_links"]) == 1
        assert res["discovered_links"][0]["id"] == "380792b2c86d9c5be670b3bde48e187b"
        assert "MOVE03" in res["discovered_links"][0]["title"]
        assert mock_mcp.write_file.call_count == 2
    finally:
        httpx.AsyncClient = original_client  # type: ignore
