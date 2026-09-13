import base64
import hashlib
from pathlib import Path
import shutil
import sys
import pytest
from fastmcp.server.context import Context

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
test_root = Path(__file__).parent / "test_workspaces_binary"
config.WORKSPACE_MOUNT_ROOT = test_root

from state import SESSION_MAPPING
from tools.filesystem.read_binary_file import register_read_binary_file
from tools.filesystem.get_file_info import register_get_file_info


class MockContext(Context):
    def __init__(self, session_id: str):
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id


class DummyMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_MOUNT_ROOT", test_root)
    test_root.mkdir(parents=True, exist_ok=True)
    yield
    if test_root.exists():
        shutil.rmtree(test_root)


@pytest.fixture
def mcp():
    mcp_instance = DummyMCP()
    register_read_binary_file(mcp_instance)
    register_get_file_info(mcp_instance)
    return mcp_instance


@pytest.mark.asyncio
async def test_read_binary_and_file_info(mcp):
    session_id = "test_mcp_sess"
    x_sess = "s03e01_test"
    caller = "sa-cr-s03e01-agent"
    SESSION_MAPPING[session_id] = {
        "x_session_id": x_sess,
        "caller_identity": caller,
        "cre_ts": 123456.0,
        "last_activity": 123456.0,
    }

    workspace = test_root / caller / x_sess
    workspace.mkdir(parents=True, exist_ok=True)

    # 1. Create a binary file
    binary_payload = b"\x50\x4B\x03\x04\x00\x00\x00\x00testbinarycontent"
    bin_file = workspace / "data.zip"
    bin_file.write_bytes(binary_payload)

    ctx = MockContext(session_id=session_id)

    # Test get_file_info
    info_tool = mcp.tools["get_file_info"]
    info_res = await info_tool(reasoning="Checking binary info", file_path="data.zip", ctx=ctx)
    assert info_res.status == "success"
    assert info_res.size_bytes == len(binary_payload)
    assert info_res.is_binary is True
    assert info_res.sha256 == hashlib.sha256(binary_payload).hexdigest()

    # Test read_binary_file
    read_tool = mcp.tools["read_binary_file"]
    read_res = await read_tool(reasoning="Reading binary archive", file_path="data.zip", ctx=ctx)
    assert read_res.status == "success"
    assert read_res.size_bytes == len(binary_payload)
    assert read_res.sha256 == hashlib.sha256(binary_payload).hexdigest()
    decoded = base64.b64decode(read_res.content_base64)
    assert decoded == binary_payload
