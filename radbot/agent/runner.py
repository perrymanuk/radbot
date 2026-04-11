"""Custom Runner for RadBot.

Provides RadbotRunner which extends the ADK Runner with any
radbot-specific behavior. Currently a thin passthrough — the V2
Task API (mode='task') handles agent routing natively via
RequestTaskTool/FinishTaskTool without needing Runner modifications.

This module exists as the single import point for Runner across the
codebase, making it easy to add customizations if needed later.
"""

from google.adk.runners import Runner as RadbotRunner  # noqa: F401

__all__ = ["RadbotRunner"]
