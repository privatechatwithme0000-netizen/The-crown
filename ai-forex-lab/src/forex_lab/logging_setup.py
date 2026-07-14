"""Structured logging with secret redaction.

Emits JSON lines (or plain text) with UTC timestamps. A filter scrubs values
that look like OANDA tokens, authorization headers, or DB/Redis passwords so
credentials never reach the log stream.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(authorization\s*[:=]\s*)(Bearer\s+)?[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?token\s*[:=]\s*)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*)[^\s,'\"]+", re.IGNORECASE),
    # OANDA practice tokens look like <hex>-<hex>; redact defensively.
    re.compile(r"\b[0-9a-f]{16,}-[0-9a-f]{16,}\b", re.IGNORECASE),
)

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Scrub secret-looking substrings from a string."""
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + _REDACTED, text)
        else:
            text = pattern.sub(_REDACTED, text)
    return text


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure root logging. Idempotent enough for app + test reuse."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RedactionFilter())
    if json_output:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root.addHandler(handler)
