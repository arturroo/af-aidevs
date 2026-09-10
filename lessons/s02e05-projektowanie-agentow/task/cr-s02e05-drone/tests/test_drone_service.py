import pytest
from unittest.mock import AsyncMock, MagicMock
from markdownify import markdownify

from services.drone_service import DroneService
from schemas import DamCoordinates, DroneVerificationResponse


@pytest.mark.asyncio
async def test_markdown_conversion():
    sample_html = """
    <html>
        <body>
            <h1>Drone API Documentation</h1>
            <p>System operational instructions.</p>
            <h2>Flight Controls</h2>
            <ul>
                <li><code>start</code>: Initializes the engines.</li>
                <li><code>flyTo(x, y)</code>: Directs drone to coordinate.</li>
            </ul>
        </body>
    </html>
    """
    md = markdownify(sample_html, heading_style="ATX")
    assert "# Drone API Documentation" in md
    assert "## Flight Controls" in md
    assert "start" in md


@pytest.mark.asyncio
async def test_rag_helpers():
    mock_mcp = MagicMock()
    mock_mcp.read_file = AsyncMock(return_value="""# Drone Manual
This is the manual overview.

## Target Systems
Official target registration:
- setTarget PWR6132PL

## Flight Controls
Standard navigation instructions:
Line 1: engine on
Line 2: flyTo 3,7
Line 3: detonate

## Error Recovery
If locked, issue hardReset to clear state.
""")

    drone = DroneService(mcp_service=mock_mcp, audit_service=MagicMock())

    # 1. list_markdown_sections
    sections = await drone.list_markdown_sections("test_session", "drone.md")
    assert len(sections) == 4
    assert sections[1]["title"] == "Target Systems"

    # 2. read_markdown_section
    body = await drone.read_markdown_section("test_session", "Flight Controls", "drone.md")
    assert "Line 2: flyTo 3,7" in body
    assert "Error Recovery" not in body

    # 3. read_file_lines
    lines_text = await drone.read_file_lines("test_session", start_line=1, line_count=3, file_path="drone.md")
    assert "1: # Drone Manual" in lines_text

    # 4. grep_documentation
    grep_res = await drone.grep_documentation("test_session", "hardReset", "drone.md")
    assert "hardReset" in grep_res


@pytest.mark.asyncio
async def test_verify_drone_success():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(return_value={
        "code": 0,
        "message": "Strike confirmed. Flag: {FLG:STRIKE_CONFIRMED_OK}",
    })

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    drone = DroneService(mcp_service=mock_mcp, audit_service=mock_audit)
    resp = await drone.verify_drone("test_session", ["start", "flyTo 3,7", "detonate"], reasoning="Test verification")

    assert resp.is_success is True
    assert resp.flag == "{FLG:STRIKE_CONFIRMED_OK}"
    assert mock_audit.log_event.called


@pytest.mark.asyncio
async def test_verify_drone_failure_with_hint():
    mock_mcp = MagicMock()
    mock_mcp.post_web_resource = AsyncMock(return_value={
        "code": -1,
        "message": "Error: Drone navigation locked due to invalid configuration state. Reset required.",
    })

    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    drone = DroneService(mcp_service=mock_mcp, audit_service=mock_audit)
    resp = await drone.verify_drone("test_session", ["flyTo 3,7"], reasoning="Test failed verification")

    assert resp.is_success is False
    assert resp.flag is None
    assert resp.hint is not None
    assert "hardReset" in resp.hint
