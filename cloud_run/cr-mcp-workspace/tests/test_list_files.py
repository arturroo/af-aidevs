import pytest
import os
import shutil
from pathlib import Path
from pydantic import BaseModel
from fastmcp.server.context import Context
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock config before importing tools
import config
test_root = Path(__file__).parent / "test_workspaces"
config.WORKSPACE_MOUNT_ROOT = test_root

from state import SESSION_MAPPING
from tools.list_files import register_list_files

# Mock Context
class MockContext(Context):
    def __init__(self, session_id: str):
        self._session_id = session_id
        
    @property
    def session_id(self) -> str:
        return self._session_id

# We need a dummy FastMCP to capture the registered tool
class DummyMCP:
    def __init__(self):
        self.tools = {}
        
    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup test workspace
    test_root.mkdir(parents=True, exist_ok=True)
    yield
    # Teardown test workspace
    if test_root.exists():
        shutil.rmtree(test_root)
        
@pytest.fixture
def mcp():
    mcp_instance = DummyMCP()
    register_list_files(mcp_instance)
    return mcp_instance

@pytest.mark.asyncio
async def test_list_files_missing_session(mcp):
    list_files_tool = mcp.tools["list_files"]
    ctx = MockContext(session_id="invalid_session")
    
    with pytest.raises(PermissionError, match="Session expired or invalid"):
        await list_files_tool(path=".", ctx=ctx)

@pytest.mark.asyncio
async def test_list_files_path_traversal(mcp):
    # Setup valid session
    session_id = "test_session_123"
    SESSION_MAPPING[session_id] = {
        "caller_identity": "test_user",
        "x_session_id": "test_x_session",
        "last_activity": 0
    }
    
    list_files_tool = mcp.tools["list_files"]
    ctx = MockContext(session_id=session_id)
    
    response = await list_files_tool(path="..", ctx=ctx)
    assert response.status == "error"
    assert "Path traversal attempt detected" in response.message

@pytest.mark.asyncio
async def test_list_files_success_creates_dir(mcp):
    # Setup valid session
    session_id = "test_session_456"
    SESSION_MAPPING[session_id] = {
        "caller_identity": "test_user",
        "x_session_id": "test_x_session",
        "last_activity": 0
    }
    
    list_files_tool = mcp.tools["list_files"]
    ctx = MockContext(session_id=session_id)
    
    response = await list_files_tool(path=".", ctx=ctx)
    assert response.status == "success"
    assert response.files == []
    
    # Check that directory was actually created
    expected_dir = test_root / "test_user" / "test_x_session"
    assert expected_dir.exists()

@pytest.mark.asyncio
async def test_list_files_not_found(mcp):
    # Setup valid session
    session_id = "test_session_789"
    SESSION_MAPPING[session_id] = {
        "caller_identity": "test_user",
        "x_session_id": "test_x_session",
        "last_activity": 0
    }
    
    list_files_tool = mcp.tools["list_files"]
    ctx = MockContext(session_id=session_id)
    
    response = await list_files_tool(path="does_not_exist", ctx=ctx)
    assert response.status == "error"
    assert "not found" in response.message
