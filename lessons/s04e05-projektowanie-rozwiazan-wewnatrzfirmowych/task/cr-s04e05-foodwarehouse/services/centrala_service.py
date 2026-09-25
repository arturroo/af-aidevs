import logging
import re
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

import config
from schemas import DispatchReport, OrdersManifest, StagedOrderItem

logger = logging.getLogger("services.centrala")


class CentralaRateLimitError(Exception):
    """Raised when Centrala returns HTTP 429, application code -9999, or throttle message."""

    def __init__(self, message: str):
        super().__init__(message)


class CentralaService:
    """Centrala API client for task foodwarehouse with Circuit Breaker, rate-limit retry, and batch dispatch."""

    def __init__(
        self,
        verify_url: str = config.AIDEVS_VERIFY_URL,
        api_key: str = config.AIDEVS_API_KEY,
        task_name: str = config.TASK_NAME,
        mcp_service: Any = None,
    ):
        self.verify_url = verify_url
        self.api_key = api_key
        self.task_name = task_name
        self.mcp = mcp_service

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(multiplier=1.0, min=1.0, max=10.0),
        retry=retry_if_exception_type(CentralaRateLimitError),
        reraise=True,
    )
    async def post_verify(
        self, answer: dict[str, Any], session_id: str | None = None
    ) -> dict[str, Any]:
        """Dispatches an answer payload to Centrala /verify/ with rate-limit retry."""
        payload = {
            "apikey": self.api_key,
            "task": self.task_name,
            "answer": answer,
        }

        # Try routing via cr-mcp-web-gateway if available
        if self.mcp and hasattr(self.mcp, "post_web_resource"):
            try:
                res = await self.mcp.post_web_resource(
                    url=self.verify_url,
                    json_payload=payload,
                    session_id=session_id or "default",
                )
                if isinstance(res, dict):
                    code = res.get("code", 0)
                    msg = str(res.get("message", ""))
                    if (
                        code == -9999
                        or "rate limit" in msg.lower()
                        or "throttle" in msg.lower()
                    ):
                        logger.warning(
                            f"Centrala throttled request via gateway (code {code}): {msg}"
                        )
                        raise CentralaRateLimitError(msg)
                    return res
            except CentralaRateLimitError:
                raise
            except Exception as e:
                logger.warning(
                    f"Failed to post via MCP gateway ({e}). Falling back to direct httpx."
                )

        # Fallback to direct httpx
        logger.info(
            f"POST {self.verify_url} (task={self.task_name}, tool={answer.get('tool')})"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.verify_url, json=payload)
            try:
                data = resp.json()
            except Exception:
                data = {"code": resp.status_code, "message": resp.text}

            # Check rate limiting / throttling
            code = data.get("code", 0) if isinstance(data, dict) else 0
            msg = str(data.get("message", "")) if isinstance(data, dict) else ""
            if (
                resp.status_code == 429
                or code == -9999
                or "rate limit" in msg.lower()
                or "throttle" in msg.lower()
            ):
                logger.warning(
                    f"Centrala rate limit hit ({resp.status_code}, code {code}): {msg}"
                )
                raise CentralaRateLimitError(msg or f"HTTP {resp.status_code}")

            if resp.status_code >= 400:
                logger.warning(f"Centrala error response ({resp.status_code}): {data}")
                return data

            return data

    async def execute_tool(
        self, tool: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Universal meta-tool executor with Circuit Breaker on mutative single-order operations."""
        params_dict = params or {}
        tool_clean = tool.strip()

        # Mutative Interception Circuit Breaker: single order create / append
        if tool_clean == "orders" and params_dict.get("action") in ["create", "append"]:
            logger.info("Circuit breaker blocked individual order manipulation.")
            return {
                "status": "blocked",
                "message": (
                    "Pojedyncza modyfikacja zamówień jest zablokowana ze względów bezpieczeństwa i limitów transakcyjnych. "
                    "Zbierz wszystkie 8 zamówień w 'orders_manifest.json' w cr-mcp-workspace, "
                    "zwaliduj je narzędziem 'validate_staged_orders', a następnie wyślij atomowo za pomocą 'dispatch_staged_orders'."
                ),
            }

        # Mutative Interception Circuit Breaker: premature 'done'
        if tool_clean == "done":
            logger.info("Circuit breaker blocked direct 'done' invocation.")
            return {
                "status": "blocked",
                "message": (
                    "Bezpośrednie wywołanie 'done' jest zablokowane. Wywołaj dedykowane narzędzie "
                    "'dispatch_staged_orders', które automatycznie przeprowadzi walidację, zresetuje magazyn, "
                    "wgra wszystkie 8 zamówień w batchu i zweryfikuje rozwiązanie."
                ),
            }

        # Safe read/discovery operations
        answer = {"tool": tool_clean, **params_dict}
        return await self.post_verify(answer)

    async def fetch_food4cities(
        self, url: str = config.AIDEVS_FOOD4CITIES_URL
    ) -> dict[str, dict[str, int]]:
        """Downloads municipal resource demands manifest."""
        logger.info(f"Fetching food demands from {url}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data

    async def dispatch_orders_batch(
        self,
        orders: list[StagedOrderItem] | OrdersManifest | list[dict[str, Any]],
    ) -> DispatchReport:
        """Executes reset, creates 8 orders, appends item batches, and captures verification flag."""
        items_list: list[StagedOrderItem] = []
        if isinstance(orders, OrdersManifest):
            items_list = orders.orders
        elif isinstance(orders, list):
            for it in orders:
                if isinstance(it, StagedOrderItem):
                    items_list.append(it)
                elif isinstance(it, dict):
                    items_list.append(StagedOrderItem(**it))

        logger.info(
            f"Dispatching batch of {len(items_list)} municipal orders to Centrala..."
        )

        # Step 1: Pre-emptive Reset
        logger.info("Issuing pre-emptive warehouse reset...")
        reset_resp = await self.post_verify({"tool": "reset"})
        logger.info(f"Warehouse reset response: {reset_resp}")

        orders_created = 0
        total_items_appended = 0

        # Step 2: Create each order and batch-append commodities
        for idx, ord_item in enumerate(items_list):
            logger.info(
                f"Creating order [{idx + 1}/{len(items_list)}] for city '{ord_item.city}' "
                f"(destination={ord_item.destination}, creatorID={ord_item.creatorID})..."
            )
            dest_val: int | str = ord_item.destination
            try:
                dest_val = int(dest_val)
            except Exception:
                pass
            create_payload = {
                "tool": "orders",
                "action": "create",
                "title": ord_item.title,
                "creatorID": ord_item.creatorID,
                "destination": dest_val,
                "signature": ord_item.signature,
            }
            create_resp = await self.post_verify(create_payload)
            logger.info(f"Create response for {ord_item.city}: {create_resp}")

            # Extract order ID from response (handle various possible Centrala response shapes)
            order_id = None
            if isinstance(create_resp, dict):
                if "order" in create_resp and isinstance(create_resp["order"], dict):
                    order_id = create_resp["order"].get("id") or create_resp[
                        "order"
                    ].get("order_id")
                if not order_id:
                    order_id = (
                        create_resp.get("id")
                        or create_resp.get("orderId")
                        or create_resp.get("order_id")
                    )
                if not order_id and "message" in create_resp:
                    match = re.search(
                        r"([0-9a-fA-F-]{16,})", str(create_resp["message"])
                    )
                    if match:
                        order_id = match.group(1)

            if not order_id:
                msg = f"Nie udalo sie uzyskac order_id dla miasta {ord_item.city}: {create_resp}"
                logger.error(msg)
                return DispatchReport(
                    status="error",
                    orders_processed=orders_created,
                    items_appended=total_items_appended,
                    message=msg,
                )

            orders_created += 1

            # Step 2b: Batch append items
            logger.info(
                f"Batch appending {len(ord_item.items)} items to order {order_id} ({ord_item.city})..."
            )
            append_payload = {
                "tool": "orders",
                "action": "append",
                "id": order_id,
                "items": ord_item.items,
            }
            append_resp = await self.post_verify(append_payload)
            logger.info(f"Append response for {ord_item.city}: {append_resp}")
            total_items_appended += len(ord_item.items)

        # Step 3: Trigger Final Verification via done
        logger.info("Triggering final verification via tool: done...")
        done_resp = await self.post_verify({"tool": "done"})
        logger.info(f"Done response: {done_resp}")

        # Extract flag
        flag = None
        done_text = str(done_resp)
        match_flag = re.search(r"\{FLG:[^}]+\}", done_text)
        if match_flag:
            flag = match_flag.group(0)

        status = "success" if flag or done_resp.get("code") == 0 else "error"
        msg = (
            done_resp.get("message", str(done_resp))
            if isinstance(done_resp, dict)
            else str(done_resp)
        )

        return DispatchReport(
            status=status,
            orders_processed=orders_created,
            items_appended=total_items_appended,
            flag=flag,
            message=msg,
        )
