import asyncio
from collections.abc import Coroutine
from typing import Any

from src.db import engine


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """
    Run a coroutine from synchronous Celery task code.

    Each call gets a fresh event loop, so the connection pool has to be
    disposed before that loop closes: asyncpg connections are bound to
    the loop that opened them, and a pooled connection handed to the
    next task would point at a loop that no longer exists.

    Args:
        coro: Coroutine to run to completion.

    Returns:
        Whatever the coroutine returns.
    """

    async def _run() -> T:
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(_run())
