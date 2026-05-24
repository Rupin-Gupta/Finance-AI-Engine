"""Structured JSON logging for production. Call configure_logging() once at startup."""
import logging
import logging.config
import uuid
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True


def configure_logging(service: str = "api", level: str = "INFO") -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    formatter = jsonlogger.JsonFormatter(
        fmt,
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        static_fields={"service": service},
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    for noisy in ("uvicorn.access", "apscheduler", "httpx", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
