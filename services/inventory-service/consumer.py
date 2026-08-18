import json
import threading
import time
from decimal import Decimal

from botocore.exceptions import ClientError

from config import settings
from db import inventory_table
from shared.events import (
    ORDER_CREATED, STOCK_INSUFFICIENT, STOCK_RELEASED, STOCK_RESERVED,
    delete_message, ensure_queue, publish, receive,
)
from shared.logging_config import configure_logging, correlation_id_var

logger = configure_logging()

SUBSCRIBED_EVENTS = [ORDER_CREATED, STOCK_RELEASED]


def _reserve(items: list[dict]) -> tuple[bool, str]:
    """
    Attempt to reserve stock for every item.

    Uses a DynamoDB conditional update so the decrement only succeeds
    if sufficient stock remains. The check and the write are a single
    atomic operation, which prevents the race condition where two
    concurrent orders both read the same stock level and both proceed.
    """
    table = inventory_table()
    reserved: list[dict] = []

    for item in items:
        try:
            table.update_item(
                Key={"product_id": item["product_id"]},
                UpdateExpression="SET available = available - :q, reserved = reserved + :q",
                ConditionExpression="available >= :q",
                ExpressionAttributeValues={":q": Decimal(str(item["quantity"]))},
            )
            reserved.append(item)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Roll back the items already reserved in this loop -
                # a local compensation before the saga even reports back.
                for done in reserved:
                    table.update_item(
                        Key={"product_id": done["product_id"]},
                        UpdateExpression="SET available = available + :q, reserved = reserved - :q",
                        ExpressionAttributeValues={
                            ":q": Decimal(str(done["quantity"]))
                        },
                    )
                return False, f"Insufficient stock for {item['product_id']}"
            raise

    return True, ""


def _release(items: list[dict]) -> None:
    """Compensating action: return reserved stock to available."""
    table = inventory_table()
    for item in items:
        table.update_item(
            Key={"product_id": item["product_id"]},
            UpdateExpression="SET available = available + :q, reserved = reserved - :q",
            ExpressionAttributeValues={":q": Decimal(str(item["quantity"]))},
        )


def _handle(envelope: dict) -> None:
    event_type = envelope["event_type"]
    payload = envelope["payload"]
    correlation_id = envelope["correlation_id"]
    correlation_id_var.set(correlation_id)

    if event_type == ORDER_CREATED:
        ok, reason = _reserve(payload["items"])

        if ok:
            logger.info(f"Stock reserved for order {payload['order_id']}")
            publish(STOCK_RESERVED, {"order_id": payload["order_id"]}, correlation_id)
        else:
            logger.warning(f"Stock reservation failed: {reason}")
            publish(STOCK_INSUFFICIENT, {
                "order_id": payload["order_id"], "reason": reason,
            }, correlation_id)

    elif event_type == STOCK_RELEASED:
        logger.info(f"Releasing stock for cancelled order {payload['order_id']}")
        _release(payload["items"])


def _poll_loop() -> None:
    queue_url = ensure_queue(settings.queue_name, SUBSCRIBED_EVENTS)
    logger.info("Inventory consumer started")

    while True:
        try:
            for message in receive(queue_url):
                try:
                    _handle(json.loads(message["Body"]))
                    delete_message(queue_url, message["ReceiptHandle"])
                except Exception:
                    logger.exception("Failed to process event")
        except Exception:
            logger.exception("Consumer poll failed")
            time.sleep(5)


def start_consumer() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()
