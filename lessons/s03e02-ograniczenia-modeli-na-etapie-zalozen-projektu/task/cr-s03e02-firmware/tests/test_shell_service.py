import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from services.shell_service import ShellService
from services.safety_guardrail import SafetyGuardrailService


def test_extract_cooldown_seconds():
    service = ShellService()
    
    assert service._extract_cooldown_seconds("You are banned. Please wait 15 seconds.") == 15
    assert service._extract_cooldown_seconds("Banned for 30s.") == 30
    assert service._extract_cooldown_seconds("Cooldown: 45 sec.") == 45
    assert service._extract_cooldown_seconds("All systems normal.") is None
    assert service._extract_cooldown_seconds("") is None


@pytest.mark.asyncio
async def test_guardrail_blocks_dangerous_command_without_http():
    service = ShellService()
    with patch.object(service, "_post_shell_request", new_callable=AsyncMock) as mock_post:
        res = await service.execute_command("cat /etc/passwd", reasoning="Testing security")
        
        # HTTP client should NOT be called at all
        mock_post.assert_not_called()
        
        assert res.code == 1
        assert "BLOCKED" in res.error
        assert "safety policy" in res.hint.lower()


@pytest.mark.asyncio
async def test_execute_command_success():
    service = ShellService()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"output": "Available commands: help, ls, cat", "code": 0}
    mock_resp.text = '{"output": "Available commands: help, ls, cat", "code": 0}'

    with patch.object(service, "_post_shell_request", new_callable=AsyncMock, return_value=mock_resp):
        res = await service.execute_command("help", reasoning="Listing commands")
        assert res.code == 0
        assert "help, ls, cat" in res.output
        assert res.error is None
