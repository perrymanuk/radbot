"""Centralized integration client provider (EX44 / PT111).

Public surface: `get_provider()` returns the process-wide `ClientProvider`
singleton. `reset_provider()` is a test helper. Callers access individual
clients via typed `@property` accessors on the provider (e.g.
`get_provider().ntfy`).
"""

from radbot.clients.provider import (
    ClientProvider,
    get_provider,
    reset_provider,
)

__all__ = ["ClientProvider", "get_provider", "reset_provider"]
