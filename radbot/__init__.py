"""
RadBot - A modular AI agent framework using Google ADK, Qdrant, MCP, and A2A.
"""

__version__ = "0.1.0"

# Lazy re-exports: avoid eagerly building the full agent (and its DB pool,
# scheduler init, etc.) just because something imported a leaf submodule like
# ``radbot.tools.github.github_app_client``. Resolve on first attribute access.
_LAZY_EXPORTS = {
    "RadBotAgent": ("radbot.agent", "RadBotAgent"),
    "create_agent": ("radbot.agent", "create_agent"),
    "create_memory_enabled_agent": ("radbot.agent", "create_memory_enabled_agent"),
}


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'radbot' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(target[0])
    return getattr(module, target[1])
