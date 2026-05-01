"""Centralized DB schema initialization for radbot.

`init_all_schemas()` runs every `init_*_schema()` (or equivalent) registered
below. Idempotent — each underlying init uses `CREATE TABLE IF NOT EXISTS`.

Called at FastAPI startup (`web/app.py`) and once per pytest session
(`tests/conftest.py`). Replaces the earlier `setup_before_agent_call`
fallback path that ran a subset of these on first agent invocation.

Failure mode: fail-loud. A schema module that fails to import or whose init
function raises is a structural code defect, not a missing API key — let it
crash the boot so the bug surfaces immediately.
"""

from __future__ import annotations

import importlib
import logging
from typing import Callable, List, Tuple

logger = logging.getLogger(__name__)


# (label, module_path, function_name) — ordered roughly by dependency.
# Chat history runs first because the chat-history pool is separate from
# the main pool; everything else uses the shared pool.
SCHEMA_INITS: List[Tuple[str, str, str]] = [
    ("chat history", "radbot.web.db.chat_operations", "create_schema_if_not_exists"),
    ("scheduler", "radbot.tools.scheduler.db", "init_scheduler_schema"),
    (
        "scheduler pending results",
        "radbot.tools.scheduler.db",
        "init_pending_results_schema",
    ),
    ("webhook", "radbot.tools.webhooks.db", "init_webhook_schema"),
    ("reminder", "radbot.tools.reminders.db", "init_reminder_schema"),
    ("telos", "radbot.tools.telos.db", "init_telos_schema"),
    ("coder workspaces", "radbot.tools.claude_code.db", "init_coder_schema"),
    ("notification", "radbot.tools.notifications.db", "init_notification_schema"),
    ("alert", "radbot.tools.alertmanager.db", "init_alert_schema"),
    ("usage telemetry", "radbot.telemetry.db", "init_usage_schema"),
    ("telemetry events", "radbot.tools.telemetry", "init_telemetry_schema"),
    ("session workers", "radbot.worker.db", "init_session_workers_schema"),
    ("workspace workers", "radbot.worker.db", "init_workspace_workers_schema"),
    ("credential store", "radbot.credentials.store", "CredentialStore.init_schema"),
]


def _resolve(module_path: str, attr_path: str) -> Callable:
    """Resolve `module_path.attr_path` (supports `Class.method`)."""
    mod = importlib.import_module(module_path)
    obj = mod
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


def init_all_schemas() -> None:
    """Run every registered schema initializer.

    Raises on import or invocation failure. See module docstring.
    """
    for label, module_path, func_name in SCHEMA_INITS:
        fn = _resolve(module_path, func_name)
        fn()
    logger.info("All %d database schemas initialized", len(SCHEMA_INITS))
