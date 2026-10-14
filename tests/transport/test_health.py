import asyncio
from collections.abc import AsyncIterator

import grpc
import pytest
from google.protobuf.empty_pb2 import Empty  # ty: ignore[unresolved-import]  # Generated protobuf has no stub.
from pydantic import SecretStr

from go_judge_client import AsyncGoJudgeClient, ClientStateError
from go_judge_client._grpc.file_pb2 import FileListType
from go_judge_client._grpc.judge_pb2_grpc import ExecutorServicer, add_ExecutorServicer_to_server


class HealthExecutor(ExecutorServicer):
    def __init__(self) -> None:
        self.status: grpc.StatusCode | None = None
        self.wait = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.metadata: dict[str, str | bytes] = {}
        self.calls = 0

    async def FileList(self, request: Empty, context: grpc.aio.ServicerContext) -> FileListType:
        self.calls += 1
        self.metadata = dict(context.invocation_metadata() or ())
        self.started.set()
        if self.status is not None:
            await context.abort(self.status, "synthetic-secret diagnostic")
        if self.wait:
            await self.release.wait()
        return FileListType(fileIDs={"existing": "private-file"})


@pytest.fixture
async def health_server() -> AsyncIterator[tuple[HealthExecutor, str]]:
    service = HealthExecutor()
    server = grpc.aio.server()
    add_ExecutorServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield service, f"127.0.0.1:{port}"
    finally:
        await server.stop(0)


async def test_authenticated_health_does_not_execute_or_use_execution_permits(health_server):
    service, target = health_server
    async with AsyncGoJudgeClient(target, insecure=True, token=SecretStr("test-token"), max_concurrency=1) as client:
        await client._semaphore.acquire()
        try:
            assert await client.check_health(timeout_seconds=1) is True
            assert client._semaphore._value == 0 and not client._executions
        finally:
            client._semaphore.release()
    assert service.calls == 1 and service.metadata["authorization"] == "Bearer test-token"


@pytest.mark.parametrize(
    "status",
    [
        grpc.StatusCode.UNAUTHENTICATED,
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.UNIMPLEMENTED,
        grpc.StatusCode.UNAVAILABLE,
    ],
)
async def test_health_reports_rpc_failures_without_remote_diagnostics(health_server, status):
    service, target = health_server
    service.status = status
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        assert await client.check_health(timeout_seconds=1) is False


async def test_health_deadline_is_bounded(health_server):
    service, target = health_server
    service.wait = True
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        await client.wait_ready()
        assert await client.check_health(timeout_seconds=0.02) is False


async def test_health_external_cancellation_propagates(health_server):
    service, target = health_server
    service.wait = True
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        task = asyncio.create_task(client.check_health())
        await asyncio.wait_for(service.started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_close_finishes_health_without_cancelling_caller(health_server):
    service, target = health_server
    service.wait = True
    client = AsyncGoJudgeClient(target, insecure=True)
    await client.start()
    task = asyncio.create_task(client.check_health())
    await asyncio.wait_for(service.started.wait(), 1)
    await client.aclose()
    assert await asyncio.wait_for(task, 1) is False
    assert not task.cancelled()


async def test_health_requires_open_client(health_server):
    _, target = health_server
    client = AsyncGoJudgeClient(target, insecure=True)
    with pytest.raises(ClientStateError):
        await client.check_health()
    await client.aclose()
    with pytest.raises(ClientStateError):
        await client.check_health()
