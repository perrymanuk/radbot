"""
Command-line entry point for RadBot web interface.

Usage:
    python -m radbot.web [--host HOST] [--port PORT] [--reload]
"""

import argparse
import logging
import os
import sys

from radbot.web.app import start_server

# Set up logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    """Parse arguments and start the web server."""
    parser = argparse.ArgumentParser(description="Start the RadBot web interface")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Reload on code changes")

    args = parser.parse_args()

    # Start the server
    start_server(host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
