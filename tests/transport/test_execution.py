import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import grpc
import pytest
from pydantic import SecretStr

from go_judge_client import (
    Artifact,
    AsyncGoJudgeClient,
    AuthenticationError,
    ClientBudgets,
    ClientLimitExceededError,
    ClientStateError,
    CompatibilityError,
    ExecutionCancelledError,
    ExecutionDeadlineExceeded,
    ExecutionRequest,
    ExpectedFile,
    Finished,
    Output,
    PermissionDeniedError,
    ProtocolError,
    RemoteServiceError,
    ResultNotReadyError,
)
from go_judge_client._grpc.judge_pb2_grpc import ExecutorServicer, add_ExecutorServicer_to_server
from go_judge_client._grpc.response_pb2 import Response
from go_judge_client._grpc.stream_request_pb2 import StreamRequest
from go_judge_client._grpc.stream_response_pb2 import StreamResponse


class FakeExecutor(ExecutorServicer):
    def __init__(self) -> None:
        self.mode = "normal"
        self.status = 1
        self.calls = 0
        self.requests: list[StreamRequest] = []
        self.metadata: dict[str, str | bytes] = {}
        self.release = asyncio.Event()
        self.output_sent = asyncio.Event()
        self.stopped = asyncio.Event()

    async def ExecStream(
        self, request_iterator: AsyncIterator[StreamRequest], context: grpc.aio.ServicerContext
    ) -> AsyncIterator[StreamResponse]:
        self.calls += 1
        self.metadata = {key: value for key, value in (context.invocation_metadata() or ())}
        self.requests = [request async for request in request_iterator]
        # A response only after client half-close proves the write direction is finite.
        if self.mode in {"auth", "permission", "unsupported"}:
            code = {
                "auth": grpc.StatusCode.UNAUTHENTICATED,
                "permission": grpc.StatusCode.PERMISSION_DENIED,
                "unsupported": grpc.StatusCode.UNIMPLEMENTED,
            }[self.mode]
            await context.abort(code, "untrusted diagnostic containing synthetic-secret")
        try:
            if self.mode == "eof":
                return
            if self.mode == "empty":
                yield StreamResponse()
                return
            output = StreamResponse.Output(
                index=1 if self.mode == "index" else 0, fd=3 if self.mode == "fd" else 1, content=b"\xe2\x82"
            )
            yield StreamResponse(execOutput=output)
            self.output_sent.set()
            if self.mode == "wait":
                await self.release.wait()
            yield StreamResponse(execOutput=StreamResponse.Output(fd=1, content=b"\xac"))
            yield StreamResponse(execOutput=StreamResponse.Output(fd=2, content=b"err"))
            files = {
                f.name: (b"" if f.name == "empty" else b"\0\xff")
                for f in self.requests[0].execRequest.cmd[0].copyOut
                if f.name != "missing"
            }
            if self.mode == "unexpected":
                files["../unexpected"] = b"x"
            result = Response.Result(
                status=cast(Response.Result.StatusType, self.status),
                files=files,
                time=123,
                runTime=456,
                memory=789,
                fileIDs={"x": "id"} if self.mode == "cached" else {},
            )
            count = 0 if self.mode == "no-result" else 2 if self.mode == "two-results" else 1
            final = StreamResponse(
                execResponse=Response(results=[result] * count, error="private" if self.mode == "service" else "")
            )
            yield final
            if self.mode == "duplicate":
                yield final
            if self.mode == "late-output":
                yield StreamResponse(execOutput=output)
            if self.mode == "non-ok":
                await context.abort(grpc.StatusCode.UNAVAILABLE, "private")
        finally:
            self.stopped.set()


@pytest.fixture
async def server() -> AsyncIterator[tuple[FakeExecutor, str]]:
    service = FakeExecutor()
    server = grpc.aio.server()
    add_ExecutorServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield service, f"127.0.0.1:{port}"
    finally:
        await server.stop(0)


def request() -> ExecutionRequest:
    return ExecutionRequest(
        command=("run",),
        stdin=b"",
        expected_files=(
            ExpectedFile(path="binary"),
            ExpectedFile(path="empty"),
            ExpectedFile(path="missing", required=False),
        ),
    )


async def test_live_half_close_and_artifacts(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True, token=SecretStr("synthetic-secret")) as client:
        await client.start()
        await client.wait_ready()
        async with client.stream(request()) as execution:
            with pytest.raises(ResultNotReadyError):
                _ = execution.result
            first = await anext(execution)
            assert first == Output("stdout", b"\xe2\x82")
            assert not service.stopped.is_set()
            service.release.set()
            events = [event async for event in execution]
            assert [e.file.path for e in events if isinstance(e, Artifact)] == ["binary", "empty"]
            assert isinstance(events[-1], Finished)
            result = execution.result
            assert result.stdout == "€".encode() and result.stderr == b"err"
            assert result.artifacts["binary"].data == b"\0\xff"
            assert result.artifacts["empty"].size_bytes == 0
            assert result.not_received == ("missing",) and result.required_artifacts_satisfied
            assert result.cpu_time_ns == 123 and result.elapsed_time_ns == 456
            assert "data" not in result.model_dump()["artifacts"]["binary"]
            assert "stdout" not in result.summary().model_dump(mode="json")
            assert execution.first_output_at is not None and execution.finished_at is not None
        assert not client._executions
        assert service.metadata["authorization"] == "Bearer synthetic-secret"
        assert len(service.requests) == 1
    assert service.calls == 1


@pytest.mark.parametrize(
    "mode",
    ["eof", "empty", "index", "fd", "no-result", "two-results", "unexpected", "cached", "duplicate", "late-output"],
)
async def test_protocol_rejected(server: tuple[FakeExecutor, str], mode: str) -> None:
    service, target = server
    service.mode = mode
    events = []
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        with pytest.raises(ProtocolError):
            async with client.stream(request()) as execution:
                async for event in execution:
                    events.append(event)
        assert not client._executions
    assert not any(isinstance(event, (Artifact, Finished)) for event in events)
    assert service.calls == 1


@pytest.mark.parametrize(
    ("mode", "error"),
    [
        ("auth", AuthenticationError),
        ("permission", PermissionDeniedError),
        ("unsupported", CompatibilityError),
        ("service", RemoteServiceError),
    ],
)
async def test_error_mapping(server: tuple[FakeExecutor, str], mode: str, error: type[Exception]) -> None:
    service, target = server
    service.mode = mode
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        with pytest.raises(error) as caught:
            await client.execute(request())
        assert "synthetic-secret" not in str(caught.value)
    assert service.calls == 1


async def test_non_ok_after_final(server: tuple[FakeExecutor, str]) -> None:
    from go_judge_client import ConnectionError

    service, target = server
    service.mode = "non-ok"
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        with pytest.raises(ConnectionError):
            async with client.stream(request()) as execution:
                async for event in execution:
                    assert isinstance(event, Output)


@pytest.mark.parametrize("capture", [True, False])
async def test_output_budget(server: tuple[FakeExecutor, str], capture: bool) -> None:
    _, target = server
    async with AsyncGoJudgeClient(target, insecure=True, budgets=ClientBudgets(output_bytes=2)) as client:
        with pytest.raises(ClientLimitExceededError):
            async with client.stream(request(), capture_output=capture) as execution:
                async for _ in execution:
                    pass
        assert not client._executions


@pytest.mark.parametrize("budgets", [ClientBudgets(artifact_bytes=1), ClientBudgets(artifacts_bytes=1)])
async def test_artifact_budgets(server: tuple[FakeExecutor, str], budgets: ClientBudgets) -> None:
    _, target = server
    async with AsyncGoJudgeClient(target, insecure=True, budgets=budgets) as client:
        with pytest.raises(ClientLimitExceededError):
            await client.execute(request())


async def test_unknown_status_and_no_capture(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.status = 123
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        async with client.stream(request(), capture_output=False) as execution:
            async for _ in execution:
                pass
            assert execution.result.status == "unknown"
            assert execution.result.upstream_status == 123
            assert execution.result.stdout is None


@pytest.mark.parametrize("method", ["break", "handler", "cancel", "external", "close", "deadline"])
async def test_lifecycle_and_reuse(server: tuple[FakeExecutor, str], method: str) -> None:
    service, target = server
    service.mode = "wait"
    client = AsyncGoJudgeClient(target, insecure=True, max_concurrency=1)
    await client.start()

    async def consume() -> None:
        async with client.stream(request(), timeout_seconds=0.2 if method == "deadline" else 5) as execution:
            await anext(execution)
            if method == "break":
                return
            if method == "handler":
                raise RuntimeError("consumer failure")
            if method == "cancel":
                await execution.cancel()
                await execution.cancel()
            if method == "close":
                await client.aclose()
            await anext(execution)

    if method == "external":
        task = asyncio.create_task(consume())
        await asyncio.wait_for(service.output_sent.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif method == "handler":
        with pytest.raises(RuntimeError, match="consumer failure"):
            await consume()
    elif method in {"cancel", "close"}:
        with pytest.raises(ExecutionCancelledError):
            await consume()
    elif method == "deadline":
        with pytest.raises(ExecutionDeadlineExceeded):
            await consume()
    else:
        await consume()
    assert not client._executions
    assert client._semaphore._value == 1
    if method != "close":
        service.mode = "normal"
        assert (await client.execute(request())).status == "accepted"
    await client.aclose()
    await client.aclose()
    with pytest.raises(ClientStateError):
        await client.start()


async def test_queued_deadline_and_close(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        async with client.stream(request()) as first:
            await anext(first)
            with pytest.raises(ExecutionDeadlineExceeded):
                await client.execute(request(), timeout_seconds=0.05)
            assert service.calls == 1
            queued = asyncio.create_task(client.execute(request()))
            await asyncio.sleep(0.01)
            await client.aclose()
            with pytest.raises(ExecutionCancelledError):
                await queued
        assert client._semaphore._value == 1


async def test_state_and_unknown_runtime(server: tuple[FakeExecutor, str]) -> None:
    from go_judge_client import UnknownRuntimeError

    service, target = server
    client = AsyncGoJudgeClient(target, insecure=True)
    with pytest.raises(ClientStateError):
        await client.execute(request())
    await client.start()
    with pytest.raises(UnknownRuntimeError):
        await client.execute(ExecutionRequest(runtime="missing"))
    assert service.calls == 0
    await client.aclose()


@asynccontextmanager
async def tls_peer(mutual: bool = False) -> AsyncIterator[tuple[str, bytes, bytes]]:
    fixtures = Path(__file__).parents[1] / "fixtures"
    cert = (fixtures / "localhost.crt").read_bytes()
    key = (fixtures / "localhost.key").read_bytes()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(fixtures / "tls_server.py"),
        str(fixtures / "localhost.crt"),
        str(fixtures / "localhost.key"),
        "1" if mutual else "0",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        port = int(await asyncio.wait_for(process.stdout.readline(), 5))
        yield f"localhost:{port}", cert, key
    finally:
        try:
            _, error = await asyncio.wait_for(process.communicate(b"stop\n"), 5)
            assert process.returncode == 0, error
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.parametrize("mutual", [False, True])
async def test_tls_and_bearer(mutual: bool) -> None:
    async with tls_peer(mutual) as (target, cert, key):
        async with AsyncGoJudgeClient(
            target,
            root_certificates=cert,
            private_key=key if mutual else None,
            certificate_chain=cert if mutual else None,
            token=SecretStr("synthetic-secret"),
        ) as client:
            await client.wait_ready()
            assert (await client.execute(request())).status == "accepted"
        # The peer accepts execution only when the exact synthetic bearer metadata is present.


async def test_cross_loop_rejected(server: tuple[FakeExecutor, str]) -> None:
    _, target = server
    async with AsyncGoJudgeClient(target, insecure=True) as client:

        def another_loop() -> None:
            with pytest.raises(ClientStateError, match="different event loop"):
                asyncio.run(client.start())

        await asyncio.to_thread(another_loop)


async def test_single_consumer_and_context_reuse(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        execution = client.stream(request())
        with pytest.raises(ClientStateError):
            await anext(execution)
        async with execution:
            await anext(execution)
            reader = asyncio.create_task(anext(execution))
            await asyncio.sleep(0.01)
            with pytest.raises(ClientStateError, match="one execution reader"):
                await anext(execution)
            await execution.cancel()
            with pytest.raises(ExecutionCancelledError):
                await reader
        with pytest.raises(ClientStateError, match="single-use"):
            await execution.__aenter__()


async def test_external_cancellation_while_queued(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        async with client.stream(request()) as first:
            await anext(first)
            task = asyncio.create_task(client.execute(request()))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(client._executions) == 1
        assert client._semaphore._value == 1


async def test_deadline_when_consumer_pauses(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True) as client:
        async with client.stream(request(), timeout_seconds=0.05) as execution:
            await anext(execution)
            await asyncio.sleep(0.1)
            with pytest.raises(ExecutionDeadlineExceeded):
                await anext(execution)


async def test_close_before_entry_cannot_leak_permit(server: tuple[FakeExecutor, str]) -> None:
    _, target = server
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        execution = client.stream(request())
        await execution.aclose()
        with pytest.raises(ClientStateError):
            await execution.__aenter__()
        assert not client._executions and client._semaphore._value == 1


async def test_close_does_not_cancel_application_handler(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    service.mode = "wait"
    entered = asyncio.Event()
    release = asyncio.Event()
    client = AsyncGoJudgeClient(target, insecure=True)
    await client.start()

    async def handler() -> None:
        async with client.stream(request()) as execution:
            await anext(execution)
            entered.set()
            await release.wait()

    task = asyncio.create_task(handler())
    await asyncio.wait_for(entered.wait(), 2)
    await asyncio.wait_for(client.aclose(), 2)
    assert not task.done()
    release.set()
    await task
    assert not client._executions


async def test_tls_does_not_trust_self_signed_by_default() -> None:
    from go_judge_client import ConnectionError

    async with tls_peer() as (target, _, _):
        async with AsyncGoJudgeClient(target) as client:
            with pytest.raises(ConnectionError):
                await client.wait_ready(timeout_seconds=0.1)


async def test_repeated_close_cancellation_joins_owned_task(
    server: tuple[FakeExecutor, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, target = server
    client = AsyncGoJudgeClient(target, insecure=True)
    await client.start()
    entered = asyncio.Event()
    release = asyncio.Event()
    original = client._close

    async def controlled_close() -> None:
        entered.set()
        await release.wait()
        await original()

    monkeypatch.setattr(client, "_close", controlled_close)
    closing = asyncio.create_task(client.aclose())
    await entered.wait()
    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(closing, 2)
    assert client._close_task is not None and client._close_task.done()
    assert client._channel is None


@pytest.mark.parametrize("method", ["deadline", "cancel", "external", "close"])
async def test_cancel_during_real_grpc_handshake(method: str) -> None:
    accepted = asyncio.Event()
    peers: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []

    def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peers.append((reader, writer))
        accepted.set()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with AsyncGoJudgeClient(f"127.0.0.1:{port}", insecure=True) as client:
            execution = client.stream(request(), timeout_seconds=0.2 if method == "deadline" else 5)
            entering = asyncio.create_task(execution.__aenter__())
            await asyncio.wait_for(accepted.wait(), 2)
            if method == "cancel":
                await asyncio.wait_for(execution.cancel(), 2)
            elif method == "external":
                entering.cancel()
            elif method == "close":
                await asyncio.wait_for(client.aclose(), 2)
            error = (
                ExecutionDeadlineExceeded
                if method == "deadline"
                else asyncio.CancelledError
                if method == "external"
                else ExecutionCancelledError
            )
            with pytest.raises(error):
                await asyncio.wait_for(entering, 3)
            assert not client._executions
            assert client._semaphore._value == 8
            assert execution._close_task is not None and execution._close_task.done()
    finally:
        server.close()
        for _, writer in peers:
            writer.close()
            await writer.wait_closed()
        await server.wait_closed()


async def test_execution_concurrent_close_joins_cleanup(
    server: tuple[FakeExecutor, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, target = server
    service.mode = "wait"
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        await client.wait_ready(timeout_seconds=2)
        execution = await client.stream(request(), timeout_seconds=2).__aenter__()
        await anext(execution)
        entered = asyncio.Event()
        release = asyncio.Event()
        original = execution._close

        async def controlled_close() -> None:
            entered.set()
            await release.wait()
            await original()

        monkeypatch.setattr(execution, "_close", controlled_close)
        first = asyncio.create_task(execution.aclose())
        await entered.wait()
        second = asyncio.create_task(execution.aclose())
        await asyncio.sleep(0)
        assert not second.done()
        assert client._semaphore._value == 0
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        await asyncio.sleep(0)
        assert not first.done() and not second.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, 2)
        await asyncio.wait_for(second, 2)
        assert client._semaphore._value == 1
        assert not client._executions


@pytest.mark.parametrize("outcome", ["admitted", "cancelled", "expired"])
async def test_waiting_requests_do_not_build_wire_messages(
    server: tuple[FakeExecutor, str], monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    import go_judge_client.execution as module

    _, target = server
    built = []
    original = module.wire_request

    def tracked(*args, **kwargs):
        built.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "wire_request", tracked)
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        async with client.stream(request()):
            queued = asyncio.create_task(client.execute(request(), timeout_seconds=0.05 if outcome == "expired" else 5))
            await asyncio.sleep(0.01)
            assert len(built) == 1
            if outcome == "cancelled":
                queued.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await queued
            elif outcome == "expired":
                with pytest.raises(ExecutionDeadlineExceeded):
                    await queued
            assert len(built) == 1
        if outcome == "admitted":
            assert (await queued).status == "accepted"
            assert len(built) == 2
        assert client._semaphore._value == 1
        assert not client._executions


async def test_wire_preparation_deadline_prevents_submission(
    server: tuple[FakeExecutor, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    import go_judge_client.execution as module

    service, target = server
    original = module.wire_request

    def slow(*args, **kwargs):
        message = original(*args, **kwargs)
        time.sleep(0.02)
        return message

    monkeypatch.setattr(module, "wire_request", slow)
    async with AsyncGoJudgeClient(target, insecure=True, max_concurrency=1) as client:
        with pytest.raises(ExecutionDeadlineExceeded):
            await client.execute(request(), timeout_seconds=0.01)
        assert service.calls == 0
        assert client._semaphore._value == 1


async def test_wire_budget_failure_releases_admission(server: tuple[FakeExecutor, str]) -> None:
    service, target = server
    async with AsyncGoJudgeClient(
        target, insecure=True, max_concurrency=1, budgets=ClientBudgets(send_message_bytes=2048)
    ) as client:
        with pytest.raises(ClientLimitExceededError):
            await client.execute(ExecutionRequest(command=("run",), files={"large": b"x" * 2000}))
        assert not client._executions and client._semaphore._value == 1
        assert service.calls == 0
        assert (await client.execute(request())).status == "accepted"
