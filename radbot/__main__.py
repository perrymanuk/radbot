"""
Entry point for running the radbot agent directly.
"""

import asyncio

from radbot.cli.main import main

if __name__ == "__main__":
    asyncio.run(main())
