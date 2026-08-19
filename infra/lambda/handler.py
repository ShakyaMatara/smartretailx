"""Order event processor.

Consumes OrderCreated events from SQS and writes a structured audit
record to CloudWatch Logs, demonstrating the serverless path running
alongside the containerised services.
"""
import json
import os
from datetime import datetime, timezone


def lambda_handler(event, context):
    processed = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
        except (KeyError, json.JSONDecodeError):
            continue

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "service": os.getenv("SERVICE_NAME", "order-event-processor"),
            "correlation_id": body.get("correlation_id", "-"),
            "event_type": body.get("event_type", "unknown"),
            "message": "Order event processed",
        }
        print(json.dumps(entry))
        processed.append(entry["event_type"])

    return {"statusCode": 200,
            "body": json.dumps({"processed": len(processed), "types": processed})}