"""Authenticated, bounded service probe without executing student code."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import grpc
from google.protobuf.empty_pb2 import Empty  # ty: ignore[unresolved-import]  # Generated protobuf has no stub.

from .models import timeout_value

if TYPE_CHECKING:
    from .client import AsyncGoJudgeClient


async def check_health(client: AsyncGoJudgeClient, timeout_seconds: float | None) -> bool:
    client._check_open()
    duration = timeout_value(timeout_seconds if timeout_seconds is not None else client.timeouts.connection_seconds)
    assert client._file_list_rpc is not None
    call = client._file_list_rpc(Empty(), timeout=duration, metadata=client._metadata, wait_for_ready=False)
    try:
        await call
        return True
    except grpc.aio.AioRpcError:
        return False
    except asyncio.CancelledError:
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            raise
        # Closing the owned channel cancels the RPC, not the application task.
        return False
    finally:
        call.cancel()
