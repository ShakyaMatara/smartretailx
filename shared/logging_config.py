"""Structured JSON logging.

Logs are emitted as JSON lines so that a log aggregator (CloudWatch
Logs Insights, ELK) can query on fields rather than parsing free text.
"""
import json
import logging
import os
import sys
from contextvars import ContextVar

# Holds the correlation id for the current request or event, so log
# calls anywhere in the call stack pick it up without being passed it.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": os.getenv("SERVICE_NAME", "unknown"),
            "correlation_id": correlation_id_var.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    return logging.getLogger(os.getenv("SERVICE_NAME", "service"))