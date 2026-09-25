import pytest
from pydantic import ValidationError

from schemas import (
    CentralaApiInput,
    OrdersManifest,
    RunTaskRequest,
    StagedOrderItem,
    ValidationReport,
)


def test_run_task_request_default():
    req = RunTaskRequest()
    assert req.backend == "langchain"
    assert req.session_id is None
    assert req.model is None
    assert req.max_iterations is None
    assert req.thinking_level is None


def test_run_task_request_dynamic_fields():
    req = RunTaskRequest(
        backend="adk",
        model="gemini-3.5-flash-lite",
        max_iterations=120,
        thinking_level="low",
    )
    assert req.backend == "adk"
    assert req.model == "gemini-3.5-flash-lite"
    assert req.max_iterations == 120
    assert req.thinking_level == "low"


def test_run_task_request_invalid_backend():
    with pytest.raises(ValidationError):
        RunTaskRequest(backend="invalid")


def test_staged_order_item_valid():
    item = StagedOrderItem(
        city="opalino",
        title="Dostawa dla Opalino",
        creatorID=2,
        destination="DEST_123",
        signature="sha1_sig_12345",
        items={"chleb": 45, "woda": 120},
    )
    assert item.city == "opalino"
    assert item.creatorID == 2
    assert item.items["chleb"] == 45


def test_orders_manifest():
    manifest = OrdersManifest(
        orders=[
            StagedOrderItem(
                city="opalino",
                title="Dostawa",
                creatorID=2,
                destination="D1",
                signature="sig1",
                items={"chleb": 45},
            )
        ]
    )
    assert len(manifest.orders) == 1


def test_centrala_api_input():
    inp = CentralaApiInput(
        tool="database",
        params={"query": "show tables"},
        reasoning="Exploration",
    )
    assert inp.tool == "database"
    assert inp.params["query"] == "show tables"


def test_validation_report():
    rep = ValidationReport(
        valid=True,
        orders_count=8,
        errors=[],
        warnings=["Non-fatal test"],
        hint="All good",
    )
    assert rep.valid is True
    assert rep.orders_count == 8
