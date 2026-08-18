import asyncio
import json
import threading
import time

from config import settings
from hub import hub
from shared.events import (
    DELIVERY_UPDATED, ORDER_CANCELLED, ORDER_CONFIRMED, ORDER_CREATED,
    PAYMENT_FAILED, PAYMENT_SUCCEEDED, PRICE_CHANGED, STOCK_INSUFFICIENT,
    STOCK_RESERVED, delete_message, ensure_queue, publish, receive,
)
from shared.logging_config import configure_logging, correlation_id_var

logger = configure_logging()

# Subscribes to everything - this service is the system's window.
SUBSCRIBED_EVENTS = [
    ORDER_CREATED, STOCK_RESERVED, STOCK_INSUFFICIENT,
    PAYMENT_SUCCEEDED, PAYMENT_FAILED,
    ORDER_CONFIRMED, ORDER_CANCELLED,
    DELIVERY_UPDATED, PRICE_CHANGED,
]


def _poll_loop(loop: asyncio.AbstractEventLoop) -> None:
    queue_url = ensure_queue(settings.queue_name, SUBSCRIBED_EVENTS)
    logger.info("Notification consumer started")

    while True:
        try:
            for message in receive(queue_url):
                try:
                    envelope = json.loads(message["Body"])
                    correlation_id_var.set(envelope["correlation_id"])
                    logger.info(f"Broadcasting {envelope['event_type']}")

                    # The consumer runs on a background thread; the
                    # WebSocket connections live on the asyncio event
                    # loop. This hands the broadcast across safely.
                    asyncio.run_coroutine_threadsafe(
                        hub.broadcast(envelope), loop
                    )

                    delete_message(queue_url, message["ReceiptHandle"])
                except Exception:
                    logger.exception("Failed to process event")
        except Exception:
            logger.exception("Consumer poll failed")
            time.sleep(5)


def start_consumer(loop: asyncio.AbstractEventLoop) -> None:
    threading.Thread(target=_poll_loop, args=(loop,), daemon=True).start()