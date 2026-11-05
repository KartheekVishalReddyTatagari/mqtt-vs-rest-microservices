"""Run an asyncio program on uvloop when it is installed (Linux containers).

uvicorn uses uvloop automatically when present; the simulators use the same
loop so all asyncio services in the benchmark run on the same event loop
implementation. On Windows (local tests) it falls back to plain asyncio.
"""

import asyncio
from typing import Awaitable


def run(main: Awaitable) -> None:
    try:
        import uvloop
    except ImportError:
        asyncio.run(main)
    else:
        uvloop.run(main)
