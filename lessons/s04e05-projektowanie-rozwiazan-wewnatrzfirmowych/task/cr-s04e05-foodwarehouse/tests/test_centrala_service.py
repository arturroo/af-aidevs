from unittest.mock import AsyncMock

import pytest

from schemas import StagedOrderItem
from services.centrala_service import CentralaService


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_single_order_mutation():
    svc = CentralaService(api_key="test_key", verify_url="https://mock/verify")
    svc.post_verify = AsyncMock()

    # Block create
    res_create = await svc.execute_tool("orders", {"action": "create", "title": "Test"})
    assert res_create["status"] == "blocked"
    assert "Pojedyncza modyfikacja" in res_create["message"]
    svc.post_verify.assert_not_called()

    # Block append
    res_append = await svc.execute_tool(
        "orders", {"action": "append", "id": "1", "items": {}}
    )
    assert res_append["status"] == "blocked"
    assert "Pojedyncza modyfikacja" in res_append["message"]
    svc.post_verify.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_direct_done():
    svc = CentralaService(api_key="test_key", verify_url="https://mock/verify")
    svc.post_verify = AsyncMock()

    res_done = await svc.execute_tool("done")
    assert res_done["status"] == "blocked"
    assert "Bezpośrednie wywołanie 'done' jest zablokowane" in res_done["message"]
    svc.post_verify.assert_not_called()


@pytest.mark.asyncio
async def test_permitted_tools_pass_through():
    svc = CentralaService(api_key="test_key", verify_url="https://mock/verify")
    svc.post_verify = AsyncMock(return_value={"code": 0, "message": "OK"})

    # help
    await svc.execute_tool("help")
    svc.post_verify.assert_called_with({"tool": "help"})

    # database
    await svc.execute_tool("database", {"query": "show tables"})
    svc.post_verify.assert_called_with({"tool": "database", "query": "show tables"})

    # signatureGenerator
    await svc.execute_tool("signatureGenerator", {"username": "admin"})
    svc.post_verify.assert_called_with(
        {"tool": "signatureGenerator", "username": "admin"}
    )

    # orders get
    await svc.execute_tool("orders", {"action": "get"})
    svc.post_verify.assert_called_with({"tool": "orders", "action": "get"})


@pytest.mark.asyncio
async def test_dispatch_orders_batch_happy_path():
    svc = CentralaService(api_key="test_key", verify_url="https://mock/verify")

    # Mock post_verify sequences
    async def mock_post_verify(answer):
        tool = answer.get("tool")
        if tool == "reset":
            return {"code": 0, "message": "Reset OK"}
        if tool == "orders" and answer.get("action") == "create":
            return {
                "code": 110,
                "message": "Order created.",
                "order": {"id": f"ord_{answer.get('title')}"},
            }
        if tool == "orders" and answer.get("action") == "append":
            return {"code": 0, "message": "Appended"}
        if tool == "done":
            return {"code": 0, "message": "Gratulacje {FLG:TEST_FLAG}"}
        return {"code": 0}

    svc.post_verify = AsyncMock(side_effect=mock_post_verify)

    orders = [
        StagedOrderItem(
            city="opalino",
            title="Dostawa dla Opalino",
            creatorID=2,
            destination="DEST1",
            signature="sig1",
            items={"chleb": 45, "woda": 120},
        ),
        StagedOrderItem(
            city="domatowo",
            title="Dostawa dla Domatowo",
            creatorID=2,
            destination="DEST2",
            signature="sig2",
            items={"makaron": 60, "lopata": 8},
        ),
    ]

    report = await svc.dispatch_orders_batch(orders)
    assert report.status == "success"
    assert report.orders_processed == 2
    assert report.items_appended == 4
    assert report.flag == "{FLG:TEST_FLAG}"
