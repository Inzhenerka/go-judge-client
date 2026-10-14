"""Shared cancellation semantics for owned cleanup tasks."""

import asyncio


async def join_cleanup(task: asyncio.Task[None]) -> None:
    """Finish cleanup before propagating cancellation of this waiter.

    Shielding alone would let a cancelled waiter return while cleanup is still running.
    Repeated cancellation is remembered without cancelling the shared cleanup task.
    Cancellation of the cleanup task itself must propagate immediately.
    """
    interrupted: asyncio.CancelledError | None = None
    while True:
        try:
            await asyncio.shield(task)
            break
        except asyncio.CancelledError as error:
            if task.cancelled():
                raise
            interrupted = error
        except Exception:
            if interrupted is not None:
                raise interrupted from None
            raise
    if interrupted is not None:
        raise interrupted
