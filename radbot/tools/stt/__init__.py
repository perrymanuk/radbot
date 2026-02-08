"""
Speech-to-Text tools for the radbot agent.

This package provides Google Cloud STT integration for transcribing
user audio input in the web UI.
"""

from .stt_service import STTService

__all__ = ["STTService"]
