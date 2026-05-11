"""Structured logging configuration."""

import logging
import json
from typing import Any, Dict
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Outputs structured JSON logs for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "target"):
            log_data["target"] = record.target
        if hasattr(record, "port"):
            log_data["port"] = record.port

        return json.dumps(log_data)


def setup_logging(debug: bool = False, json_format: bool = True) -> None:
    """Configure root logger with structured output."""
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(level)

    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
