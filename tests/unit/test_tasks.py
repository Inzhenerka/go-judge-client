import asyncio

import pytest

from go_judge_client._tasks import join_cleanup


@pytest.mark.parametrize("cancel_waiter", [False, True])
async def test_cleanup_failure_preserves_waiter_cancellation(cancel_waiter: bool) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def cleanup() -> None:
        started.set()
        await release.wait()
        raise RuntimeError("cleanup failure")

    task = asyncio.create_task(cleanup())
    waiter = asyncio.create_task(join_cleanup(task))
    await started.wait()
    if cancel_waiter:
        waiter.cancel()
        await asyncio.sleep(0)
        assert not waiter.done()
    release.set()
    with pytest.raises(asyncio.CancelledError if cancel_waiter else RuntimeError):
        await asyncio.wait_for(waiter, 1)
    assert task.done() and not task.cancelled()


async def test_cancelled_cleanup_task_does_not_leave_waiter_running() -> None:
    task = asyncio.create_task(asyncio.sleep(10))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(join_cleanup(task), 1)
