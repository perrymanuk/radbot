"""Alertmanager integration for autonomous alert remediation.

Receives alerts (via ntfy subscription or direct webhook), tracks them in
PostgreSQL, and dispatches remediation tasks to the agent.
"""

from radbot.tools.alertmanager.db import init_alert_schema

__all__ = ["init_alert_schema"]
