"""Unit tests for contract schemas."""

from schemas import (
    CentralaVerifyRequest,
    CentralaVerifyResponse,
    RafalDiscoveryExtraction,
    RemoteCommandPayload,
    RunTaskRequest,
    RunTaskResponse,
)


def test_run_task_request_defaults():
    req = RunTaskRequest()
    assert req.backend == "langchain"
    assert req.max_iterations == 30
    assert req.model is None


def test_remote_command_payload():
    payload = RemoteCommandPayload(cmd="ls -la /data")
    assert payload.cmd == "ls -la /data"


def test_centrala_verify_models():
    req = CentralaVerifyRequest(
        apikey="secret-key",
        answer=RemoteCommandPayload(cmd="cat /data/test.txt"),
    )
    assert req.task == "shellaccess"
    assert req.answer.cmd == "cat /data/test.txt"

    resp = CentralaVerifyResponse(code=0, message="file contents")
    assert resp.code == 0
    assert resp.message == "file contents"
    assert resp.output is None

    resp_with_output = CentralaVerifyResponse(
        code=100, message="Command executed.", output="file1\nfile2"
    )
    assert resp_with_output.output == "file1\nfile2"


def test_rafal_discovery_extraction():
    discovery = RafalDiscoveryExtraction(
        discovery_date="2024-03-01",
        city="Grudziadz",
        latitude=53.4837,
        longitude=18.7533,
        reasoning="Extracted from log",
    )
    assert discovery.discovery_date == "2024-03-01"
    assert discovery.latitude == 53.4837


def test_run_task_response():
    resp = RunTaskResponse(
        session_id="s05e03_test",
        status="completed",
        flag="{FLG:test_flag}",
        total_turns=5,
        execution_time_seconds=3.14,
    )
    assert resp.status == "completed"
    assert resp.flag == "{FLG:test_flag}"
