"""
Text-to-Speech tools for the radbot agent.

This package provides Google Cloud TTS integration for synthesizing
agent responses as audio in the web UI.
"""

from .tts_service import TTSService

__all__ = ["TTSService"]
