from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(structured)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _to_level(level_name: str) -> int:
    level = (level_name or "INFO").strip().upper()
    return getattr(logging, level, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(_to_level(settings.LOG_LEVEL))
    handler = logging.StreamHandler(sys.stdout)
    if (settings.LOG_FORMAT or "json").strip().lower() == "text":
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        formatter = JsonFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, level: str = "info", **fields: Any) -> None:
    payload = {"event": event, **fields}
    message = fields.get("message") or event
    method = getattr(logger, level.lower(), logger.info)
    method(str(message), extra={"structured": payload})
