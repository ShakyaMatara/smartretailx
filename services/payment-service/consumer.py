import json
import threading
import time
import uuid
from decimal import Decimal

from config import settings
from database import SessionLocal
from models import Payment
from shared.events import (
    PAYMENT_FAILED, PAYMENT_REQUESTED, PAYMENT_SUCCEEDED,
    delete_message, ensure_queue, publish, receive,
)
from shared.logging_config import configure_logging, correlation_id_var

logger = configure_logging()

SUBSCRIBED_EVENTS = [PAYMENT_REQUESTED]


def _call_gateway(amount: Decimal) -> tuple[bool, str, str]:
    """
    Simulated third-party payment gateway.

    Returns (success, gateway_token, last_four). A real integration
    would post to the provider over TLS; the card number would go
    directly from the client to the gateway and never transit this
    service, which is what keeps PCI-DSS scope minimal.
    """
    if settings.force_payment_failure:
        return False, "", ""
    return True, f"tok_{uuid.uuid4().hex[:24]}", "4242"


def _handle(envelope: dict) -> None:
    payload = envelope["payload"]
    correlation_id = envelope["correlation_id"]
    correlation_id_var.set(correlation_id)

    db = SessionLocal()
    try:
        # Idempotency: a redelivered PaymentRequested must not charge
        # twice. SQS guarantees at-least-once delivery, so consumers
        # must be idempotent by design.
        existing = db.query(Payment).filter(
            Payment.order_id == payload["order_id"]
        ).first()
        if existing is not None:
            logger.info(f"Payment already processed for order {payload['order_id']}")
            return

        amount = Decimal(payload["amount"])
        ok, token, last_four = _call_gateway(amount)

        payment = Payment(
            order_id=payload["order_id"],
            user_id=payload["user_id"],
            amount=amount,
            currency=payload["currency"],
            status="SUCCEEDED" if ok else "FAILED",
            gateway_token=token or "none",
            card_last_four=last_four or "0000",
        )
        db.add(payment)
        db.commit()

        if ok:
            logger.info(f"Payment succeeded for order {payload['order_id']}")
            publish(PAYMENT_SUCCEEDED, {
                "order_id": payload["order_id"], "payment_id": payment.id,
            }, correlation_id)
        else:
            logger.warning(f"Payment declined for order {payload['order_id']}")
            publish(PAYMENT_FAILED, {
                "order_id": payload["order_id"],
                "reason": "Payment declined by gateway",
            }, correlation_id)
    finally:
        db.close()


def _poll_loop() -> None:
    queue_url = ensure_queue(settings.queue_name, SUBSCRIBED_EVENTS)
    logger.info("Payment consumer started")

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
