"""Structured logging with bounded output (master directive §17).

JSON lines to stdout/stderr; rotation is left to the process manager
(dev: none, prod: journald/file handler). Context fields are passed via
logging extras.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_CONTEXT_KEYS = ("node_id", "conn_id", "event_type", "error_code", "severity", "details")


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                obj[key] = value
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonLineFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    # Keep third-party noise down
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
