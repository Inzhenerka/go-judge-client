"""Pull-based execution owner with bounded local finalization."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Self
from uuid import uuid4

import grpc

from ._grpc.response_pb2 import Response
from ._grpc.stream_request_pb2 import StreamRequest
from ._grpc.stream_response_pb2 import StreamResponse
from ._mapping import final_result, wire_request
from .errors import (
    ClientLimitExceededError,
    ClientStateError,
    ExecutionCancelledError,
    ExecutionDeadlineExceeded,
    ProtocolError,
    ResultNotReadyError,
    rpc_error,
)
from .events import Artifact, ExecutionEvent, Finished, Output
from .models import ExecutionRequest, ExecutionResult, timeout_value
from .profiles import ResolvedRequest, resolve

if TYPE_CHECKING:
    from .client import AsyncGoJudgeClient


class Execution:
    """Single-use async context and iterator. Cancellation finalizes local ownership."""

    def __init__(
        self, client: AsyncGoJudgeClient, request: ExecutionRequest, timeout_seconds: float | None, capture_output: bool
    ) -> None:
        self._client = client
        self._request = request
        self._request_id = request.request_id or str(uuid4())
        self._timeout = timeout_value(
            timeout_seconds if timeout_seconds is not None else client.timeouts.operation_seconds
        )
        self._capture = capture_output
        self._call: grpc.aio.StreamStreamCall[StreamRequest, StreamResponse] | None = None
        self._admission: asyncio.Task[bool] | None = None
        self._sending: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._permit = False
        self._entered = False
        self._closed = False
        self._cancelled = False
        self._expired = False
        self._timer: asyncio.TimerHandle | None = None
        self._resolved: ResolvedRequest | None = None
        self._result: ExecutionResult | None = None
        self._candidate: Response | None = None
        self._pending: deque[ExecutionEvent] = deque()
        self._stdout = bytearray()
        self._stderr = bytearray()
        self.output_bytes = 0
        self.started_at: float | None = None
        self.first_output_at: float | None = None
        self.finished_at: float | None = None
        self._reading = False
        self._deadline = 0.0

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def result(self) -> ExecutionResult:
        if self._result is None:
            raise ResultNotReadyError("No verified complete result is available")
        return self._result

    def _expire(self) -> None:
        if self._result is None:
            self._expired = True
            self._request_cancel()

    def _request_cancel(self) -> None:
        if self._closed or self._result is not None:
            return
        self._cancelled = True
        if self._admission is not None and not self._admission.done():
            self._admission.cancel()
        if self._call is not None:
            self._call.cancel()
        if self._sending is not None and not self._sending.done():
            self._sending.cancel()

    async def cancel(self) -> None:
        self._client._check_loop()
        self._request_cancel()
        await self.aclose()

    def _check_outcome(self) -> None:
        if self._expired:
            raise ExecutionDeadlineExceeded("Operation deadline exceeded; remote outcome may be unknown")
        if self._cancelled:
            raise ExecutionCancelledError("Execution cancelled; remote cleanup is not confirmed")
        if self._closed:
            raise ClientStateError("Execution context is closed")

    async def __aenter__(self) -> Self:
        if self._entered or self._closed:
            raise ClientStateError("Execution contexts are single-use")
        self._entered = True
        client = self._client
        client._check_open()
        loop = asyncio.get_running_loop()
        self.started_at = loop.time()
        self._deadline = self.started_at + self._timeout
        self._resolved = resolve(
            self._request.model_copy(update={"request_id": self.request_id}),
            client._runtimes,
            client.default_limits,
            client.budgets,
        )
        message = wire_request(self._resolved, client.budgets)
        client._executions.add(self)
        self._timer = loop.call_at(self._deadline, self._expire)
        try:
            self._admission = asyncio.create_task(client._semaphore.acquire())
            try:
                await self._admission
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                self._check_outcome()
                raise
            self._permit = True
            self._check_outcome()
            client._check_open()
            assert client._rpc is not None
            self._call = client._rpc(
                timeout=max(0.000001, self._deadline - loop.time()), metadata=client._metadata, wait_for_ready=False
            )
            self._sending = asyncio.create_task(self._send(self._call, message))
            await self._sending
            self._check_outcome()
            return self
        except BaseException as error:
            await self._cleanup_preserving(error)
            if isinstance(error, asyncio.CancelledError):
                task = asyncio.current_task()
                if task is None or not task.cancelling():
                    self._check_outcome()
                    raise ExecutionCancelledError("RPC cancelled") from None
            if isinstance(error, grpc.aio.AioRpcError):
                raise rpc_error(error.code()) from error
            raise

    @staticmethod
    async def _send(call: grpc.aio.StreamStreamCall[StreamRequest, StreamResponse], message: StreamRequest) -> None:
        # Own the write waiter too: cancelling the RPC alone may not wake a pending handshake.
        await call.write(message)
        await call.done_writing()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> ExecutionEvent:
        self._client._check_loop()
        if not self._entered:
            raise ClientStateError("Enter the execution context before iterating")
        self._check_outcome()
        if self._reading:
            raise ClientStateError("Only one execution reader is allowed")
        if self._pending:
            return self._pending.popleft()
        if self._result is not None:
            raise StopAsyncIteration
        self._reading = True
        try:
            assert self._call is not None and self._resolved is not None
            while True:
                message = await self._call.read()
                self._check_outcome()
                if message is grpc.aio.EOF:
                    code = await self._call.code()
                    if code != grpc.StatusCode.OK:
                        raise rpc_error(code)
                    if self._candidate is None:
                        raise ProtocolError("RPC ended without a final response")
                    result = final_result(
                        self._candidate,
                        self._resolved,
                        self._client.budgets,
                        bytes(self._stdout) if self._capture else None,
                        bytes(self._stderr) if self._capture else None,
                    )
                    self._result = result
                    self.finished_at = asyncio.get_running_loop().time()
                    if self._timer:
                        self._timer.cancel()
                    self._candidate = None
                    self._stdout.clear()
                    self._stderr.clear()
                    self._pending.extend(Artifact(file) for file in result.artifacts.values())
                    self._pending.append(Finished(result))
                    return self._pending.popleft()
                if not isinstance(message, StreamResponse):
                    raise ProtocolError("Invalid response message")
                kind = message.WhichOneof("response")
                if self._candidate is not None:
                    raise ProtocolError("Received a message after final response")
                if kind == "execResponse":
                    self._candidate = message.execResponse
                elif kind == "execOutput":
                    output = message.execOutput
                    if output.index != 0 or output.fd not in (1, 2):
                        raise ProtocolError("Unexpected command index or output descriptor")
                    self.output_bytes += len(output.content)
                    if self.output_bytes > self._client.budgets.output_bytes:
                        raise ClientLimitExceededError("Observed output exceeds client budget")
                    if self.first_output_at is None:
                        self.first_output_at = asyncio.get_running_loop().time()
                    if self._capture:
                        (self._stdout if output.fd == 1 else self._stderr).extend(output.content)
                    return Output("stdout" if output.fd == 1 else "stderr", output.content)
                else:
                    raise ProtocolError("Response has no recognized payload")
        except asyncio.CancelledError as error:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                await self._cleanup_preserving(error)
                raise
            try:
                self._check_outcome()
            finally:
                await self.aclose()
            raise ExecutionCancelledError("RPC cancelled") from None
        except grpc.aio.AioRpcError as error:
            await self._cleanup_preserving(error)
            raise rpc_error(error.code()) from error
        except BaseException as error:
            await self._cleanup_preserving(error)
            raise
        finally:
            self._reading = False

    async def _cleanup_preserving(self, primary: BaseException) -> None:
        try:
            await self.aclose()
        except Exception:
            primary.add_note("Secondary local cleanup failure; remote cleanup is not confirmed")

    async def aclose(self) -> None:
        self._client._check_loop()
        if self._close_task is None:
            self._request_cancel()
            self._closed = True
            if self._timer:
                self._timer.cancel()
            self._close_task = asyncio.create_task(self._close())
        interrupted: asyncio.CancelledError | None = None
        while True:
            try:
                await asyncio.shield(self._close_task)
                break
            except asyncio.CancelledError as error:
                if self._close_task.cancelled():
                    raise
                interrupted = error
            except Exception:
                if interrupted is not None:
                    raise interrupted from None
                raise
        if interrupted is not None:
            raise interrupted

    async def _close(self) -> None:
        try:
            async with asyncio.timeout(self._client.timeouts.cleanup_seconds):
                if self._sending is not None:
                    await asyncio.gather(self._sending, return_exceptions=True)
                if self._admission is not None:
                    try:
                        acquired = await self._admission
                        if acquired and not self._permit:
                            self._permit = True
                    except asyncio.CancelledError:
                        if not self._admission.cancelled():
                            raise
                if self._call is not None:
                    await self._call.code()
        finally:
            if self._permit:
                self._client._semaphore.release()
                self._permit = False
            self._client._executions.discard(self)
            self._candidate = None
            self._pending.clear()
            self._stdout.clear()
            self._stderr.clear()
            self._call = None
            self._admission = None
            self._sending = None

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if isinstance(exc, BaseException):
            await self._cleanup_preserving(exc)
            return
        try:
            await self.aclose()
        except TimeoutError:
            if exc is None:
                raise ClientStateError("Local cleanup grace exceeded") from None
