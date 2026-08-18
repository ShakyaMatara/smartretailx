"""Shared event publishing and consuming helpers.

Every service uses the same envelope format so that any consumer can
parse any event without knowing the producer.
"""
import json
import os
import uuid
from datetime import datetime, timezone

import boto3

TOPIC_NAME = "smartretailx-events"

# Event type constants - a single source of truth prevents the classic
# distributed-systems bug where a producer publishes "OrderCreated" and
# a consumer listens for "order_created".
ORDER_CREATED = "OrderCreated"
STOCK_RESERVED = "StockReserved"
STOCK_INSUFFICIENT = "StockInsufficient"
STOCK_RELEASED = "StockReleased"
PAYMENT_REQUESTED = "PaymentRequested"
PAYMENT_SUCCEEDED = "PaymentSucceeded"
PAYMENT_FAILED = "PaymentFailed"
ORDER_CONFIRMED = "OrderConfirmed"
ORDER_CANCELLED = "OrderCancelled"
DELIVERY_UPDATED = "DeliveryUpdated"
PRICE_CHANGED = "PriceChanged"


def _endpoint():
    return os.getenv("AWS_ENDPOINT_URL", "http://localstack:4566")


def _region():
    return os.getenv("AWS_DEFAULT_REGION", "eu-west-1")


def sns_client():
    return boto3.client("sns", endpoint_url=_endpoint(), region_name=_region())


def sqs_client():
    return boto3.client("sqs", endpoint_url=_endpoint(), region_name=_region())


def ensure_topic() -> str:
    """Create the topic if absent and return its ARN. Idempotent."""
    return sns_client().create_topic(Name=TOPIC_NAME)["TopicArn"]


def ensure_queue(queue_name: str, event_types: list[str]) -> str:
    """
    Create a queue with a dead-letter queue, subscribe it to the topic,
    and filter the subscription to the given event types.

    Returns the queue URL.
    """
    sqs = sqs_client()
    sns = sns_client()

    # Dead-letter queue: messages that fail repeatedly land here instead
    # of being retried forever or silently lost.
    dlq_url = sqs.create_queue(QueueName=f"{queue_name}-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    queue_url = sqs.create_queue(
        QueueName=queue_name,
        Attributes={
            # After 3 failed processing attempts the message is moved
            # to the DLQ for inspection rather than blocking the queue.
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
            ),
            # How long a message stays invisible to other consumers
            # while one consumer is processing it.
            "VisibilityTimeout": "30",
        },
    )["QueueUrl"]

    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    topic_arn = ensure_topic()

    subscription = sns.subscribe(
        TopicArn=topic_arn,
        Protocol="sqs",
        Endpoint=queue_arn,
        ReturnSubscriptionArn=True,
    )

    # Filter policy: SNS only delivers matching event types to this
    # queue, so a service is not woken by events it does not handle.
    sns.set_subscription_attributes(
        SubscriptionArn=subscription["SubscriptionArn"],
        AttributeName="FilterPolicy",
        AttributeValue=json.dumps({"event_type": event_types}),
    )

    # RawMessageDelivery strips the SNS envelope so the consumer reads
    # the message body directly.
    sns.set_subscription_attributes(
        SubscriptionArn=subscription["SubscriptionArn"],
        AttributeName="RawMessageDelivery",
        AttributeValue="true",
    )

    return queue_url


def publish(event_type: str, payload: dict, correlation_id: str) -> str:
    """
    Publish an event.

    The correlation_id travels with the event through every downstream
    service, so one business transaction can be traced across all of
    them in the logs. This is what makes distributed debugging possible.
    """
    event_id = str(uuid.uuid4())

    envelope = {
        "event_id": event_id,
        "event_type": event_type,
        "correlation_id": correlation_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    sns_client().publish(
        TopicArn=ensure_topic(),
        Message=json.dumps(envelope),
        MessageAttributes={
            # Attribute, not body - SNS filter policies match on
            # attributes only.
            "event_type": {"DataType": "String", "StringValue": event_type}
        },
    )

    return event_id


def receive(queue_url: str, max_messages: int = 5) -> list[dict]:
    """
    Long-poll the queue. Long polling (WaitTimeSeconds) avoids the
    cost and latency of tight-loop short polling.
    """
    response = sqs_client().receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=5,
    )
    return response.get("Messages", [])


def delete_message(queue_url: str, receipt_handle: str) -> None:
    """Acknowledge a message. Until this is called the message becomes
    visible again after the visibility timeout and is redelivered -
    this is what gives at-least-once delivery."""
    sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)