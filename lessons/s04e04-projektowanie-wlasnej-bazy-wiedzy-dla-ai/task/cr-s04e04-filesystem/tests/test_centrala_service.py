"""Unit tests for CentralaService."""

from unittest.mock import AsyncMock, patch

import pytest

from schemas import FilesystemFile
from services.centrala_service import CentralaService


@pytest.mark.asyncio
async def test_batch_payload_format():
    service = CentralaService(api_key="test-key", task_name="filesystem")
    files = [
        FilesystemFile(path="/miasta/opalino", content='{"chleb": 45}'),
        FilesystemFile(
            path="/osoby/iga_kapecka", content="Iga [Opalino](/miasta/opalino)"
        ),
    ]

    with (
        patch.object(service, "create_directory", new_callable=AsyncMock) as mock_mkdir,
        patch.object(service, "_post_verify", new_callable=AsyncMock) as mock_post,
    ):
        mock_mkdir.return_value = {"code": 0, "message": "OK"}
        mock_post.return_value = {"code": 0, "message": "OK"}
        await service.batch_create_files(files)

        assert mock_mkdir.call_count == 2
        mock_mkdir.assert_any_call("/miasta")
        mock_mkdir.assert_any_call("/osoby")

        mock_post.assert_called_once()
        batch_arg = mock_post.call_args[0][0]
        assert isinstance(batch_arg, list)
        # 2 files in batch_mode
        assert len(batch_arg) == 2
        assert batch_arg[0]["action"] == "createFile"
        assert batch_arg[0]["path"] == "/miasta/opalino"
        assert batch_arg[1]["action"] == "createFile"
        assert batch_arg[1]["path"] == "/osoby/iga_kapecka"


@pytest.mark.asyncio
async def test_done_flag_extraction():
    service = CentralaService(api_key="test-key", task_name="filesystem")

    with patch.object(service, "_post_verify", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "code": 0,
            "message": "Task verified! Your flag is {{FLG:KNOWLEDGE_BASE_MASTER}}",
        }
        _resp, flag = await service.done()
        assert flag == "{FLG:KNOWLEDGE_BASE_MASTER}"


@pytest.mark.asyncio
async def test_create_file_exists_deletes_and_retries():
    service = CentralaService(api_key="test-key", task_name="filesystem")

    with (
        patch.object(service, "_post_verify", new_callable=AsyncMock) as mock_post,
        patch.object(service, "delete_file", new_callable=AsyncMock) as mock_delete,
    ):
        # 1st attempt returns file already exists, 2nd attempt succeeds
        mock_post.side_effect = [
            {"code": -950, "message": "File already exists"},
            {"code": 0, "message": "OK"},
        ]
        mock_delete.return_value = {"code": 0, "message": "OK"}

        res = await service.create_file("/miasta/opalino", '{"chleb": 45}')

        assert res.get("code") == 0
        mock_delete.assert_called_once_with("/miasta/opalino")
        assert mock_post.call_count == 2
