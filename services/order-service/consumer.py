import json
import threading
import time

from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Order
from shared.events import (
    ORDER_CANCELLED, ORDER_CONFIRMED, PAYMENT_FAILED, PAYMENT_REQUESTED,
    PAYMENT_SUCCEEDED, STOCK_INSUFFICIENT, STOCK_RELEASED, STOCK_RESERVED,
    delete_message, ensure_queue, publish, receive,
)
from shared.logging_config import configure_logging, correlation_id_var

logger = configure_logging()

# Only the event types this service acts on.
SUBSCRIBED_EVENTS = [STOCK_RESERVED, STOCK_INSUFFICIENT,
                     PAYMENT_SUCCEEDED, PAYMENT_FAILED]


def _handle(envelope: dict, db: Session) -> None:
    event_type = envelope["event_type"]
    payload = envelope["payload"]
    correlation_id = envelope["correlation_id"]
    correlation_id_var.set(correlation_id)

    order = db.query(Order).filter(Order.id == payload["order_id"]).first()
    if order is None:
        logger.warning(f"Event {event_type} for unknown order")
        return

    if event_type == STOCK_RESERVED:
        # Stock is held. Next saga step: request payment.
        order.status = "STOCK_RESERVED"
        db.commit()
        logger.info(f"Stock reserved for order {order.id}, requesting payment")
        publish(PAYMENT_REQUESTED, {
            "order_id": order.id,
            "user_id": order.user_id,
            "amount": str(order.total_amount),
            "currency": order.currency,
        }, correlation_id)

    elif event_type == STOCK_INSUFFICIENT:
        # Saga fails at the first step. Nothing to compensate - no
        # stock was reserved and no payment taken.
        order.status = "CANCELLED"
        order.failure_reason = payload.get("reason", "Insufficient stock")
        db.commit()
        logger.warning(f"Order {order.id} cancelled: insufficient stock")
        publish(ORDER_CANCELLED, {
            "order_id": order.id, "user_id": order.user_id,
            "reason": order.failure_reason,
        }, correlation_id)

    elif event_type == PAYMENT_SUCCEEDED:
        order.status = "CONFIRMED"
        db.commit()
        logger.info(f"Order {order.id} confirmed")
        publish(ORDER_CONFIRMED, {
            "order_id": order.id, "user_id": order.user_id,
            "total_amount": str(order.total_amount),
        }, correlation_id)

    elif event_type == PAYMENT_FAILED:
        # COMPENSATING TRANSACTION.
        # Payment failed after stock was already reserved, so the
        # reservation must be undone. This is what a saga does instead
        # of a distributed rollback.
        order.status = "CANCELLED"
        order.failure_reason = payload.get("reason", "Payment failed")
        db.commit()
        logger.warning(
            f"Order {order.id} payment failed - compensating: releasing stock"
        )
        publish(STOCK_RELEASED, {
            "order_id": order.id,
            "items": [
                {"product_id": i.product_id, "quantity": i.quantity}
                for i in order.items
            ],
        }, correlation_id)
        publish(ORDER_CANCELLED, {
            "order_id": order.id, "user_id": order.user_id,
            "reason": order.failure_reason,
        }, correlation_id)


def _poll_loop() -> None:
    queue_url = ensure_queue(settings.queue_name, SUBSCRIBED_EVENTS)
    logger.info("Order consumer started")

    while True:
        try:
            for message in receive(queue_url):
                db = SessionLocal()
                try:
                    _handle(json.loads(message["Body"]), db)
                    # Only delete after successful handling. If this
                    # raises, the message becomes visible again and is
                    # retried, then eventually moves to the DLQ.
                    delete_message(queue_url, message["ReceiptHandle"])
                except Exception:
                    logger.exception("Failed to process event")
                finally:
                    db.close()
        except Exception:
            logger.exception("Consumer poll failed")
            time.sleep(5)


def start_consumer() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()