import pytest
from pydantic import ValidationError
from schemas import (
    ZmailCallRequest,
    ZmailCallResponse,
    GetEmailDetailsRequest,
    GetEmailDetailsResponse,
    VerifyTaskRequest,
    VerifyTaskResponse,
    RunTaskResponse,
)


def test_verify_task_request_valid():
    req = VerifyTaskRequest(
        date="2026-02-28",
        password="mysecretpassword",
        confirmation_code="SEC-1234567890123456789012345678",
        reasoning="Valid credentials and confirmation code extracted.",
    )
    assert req.date == "2026-02-28"
    assert req.password == "mysecretpassword"
    assert len(req.confirmation_code) == 32
    assert req.confirmation_code.startswith("SEC-")


def test_verify_task_request_valid_extended_code():
    req = VerifyTaskRequest(
        date="2026-03-23",
        password="RABARBAR25",
        confirmation_code="SEC-c1e598764329cc9c377ef1d029be8ceb",
        reasoning="Valid 36-char code extracted from active thread 62045.",
    )
    assert req.date == "2026-03-23"
    assert req.password == "RABARBAR25"
    assert len(req.confirmation_code) == 36
    assert req.confirmation_code.startswith("SEC-")


def test_verify_task_request_invalid_date():
    with pytest.raises(ValidationError):
        VerifyTaskRequest(
            date="28-02-2026",  # invalid format
            password="pass",
            confirmation_code="SEC-1234567890123456789012345678",
            reasoning="Testing invalid date",
        )


def test_verify_task_request_invalid_code():
    with pytest.raises(ValidationError):
        VerifyTaskRequest(
            date="2026-02-28",
            password="pass",
            confirmation_code="SEC-short",  # invalid length
            reasoning="Testing short code",
        )

    with pytest.raises(ValidationError):
        VerifyTaskRequest(
            date="2026-02-28",
            password="pass",
            confirmation_code="NON-1234567890123456789012345678",  # missing SEC- prefix
            reasoning="Testing invalid prefix",
        )


def test_zmail_call_request_defaults():
    req = ZmailCallRequest(
        action="help",
        reasoning="Discovering API schema",
    )
    assert req.action == "help"
    assert req.params == {}
    assert "Discovering" in req.reasoning


def test_get_email_details_response():
    resp = GetEmailDetailsResponse(
        message_id="msg_001",
        subject="Test Subject",
        sender="wiktor@proton.me",
        body="Attacking power plant on 2026-03-01",
        is_sanitized=True,
    )
    assert resp.is_sanitized is True
    assert resp.message_id == "msg_001"
