"""
Centralized logging configuration for RadBot.

Call ``setup_logging()`` once from each entry point (web/__main__.py,
cli/main.py).  Every other module should just do::

    import logging
    logger = logging.getLogger(__name__)

No module besides an entry point should call ``logging.basicConfig()``.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(*, level: str | None = None) -> None:
    """Configure the root logger with a JSON formatter on *stdout*.

    Parameters
    ----------
    level:
        Log level name (DEBUG, INFO, WARNING, ...).
        Falls back to the ``LOG_LEVEL`` env-var, then ``INFO``.
    """
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    root = logging.getLogger()
    # Avoid adding duplicate handlers if called more than once.
    if any(isinstance(h, logging.StreamHandler) and
           isinstance(h.formatter, _JSONFormatter) for h in root.handlers):
        root.setLevel(resolved_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)
