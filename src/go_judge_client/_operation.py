"""Shared admission, deadline and cleanup ownership for execution transports."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Self
from uuid import uuid4

import grpc

from ._tasks import join_cleanup
from .errors import ClientStateError, ExecutionCancelledError, ExecutionDeadlineExceeded, ResultNotReadyError, rpc_error
from .models import ExecutionRequest, ExecutionResult, timeout_value
from .profiles import ResolvedRequest, resolve

if TYPE_CHECKING:
    from .client import AsyncGoJudgeClient


class Operation(ABC):
    """Own one request from local admission through bounded cleanup.

    Transports supply submission and RPC ownership, not admission policy. A permit is
    released exactly once, after cleanup. Deadlines and client shutdown cancel owned
    work without cancelling the application handler. External cancellation propagates.
    """

    def __init__(self, client: AsyncGoJudgeClient, request: ExecutionRequest, timeout_seconds: float | None) -> None:
        self._client = client
        self._request = request
        self._request_id = request.request_id or str(uuid4())
        self._timeout = timeout_value(
            timeout_seconds if timeout_seconds is not None else client.timeouts.operation_seconds
        )
        self._admission: asyncio.Task[bool] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._permit = False
        self._entered = False
        self._closed = False
        self._cancelled = False
        self._expired = False
        self._timer: asyncio.TimerHandle | None = None
        self._resolved: ResolvedRequest | None = None
        self._result: ExecutionResult | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self._deadline = 0.0

    @property
    @abstractmethod
    def _rpc_call(self) -> grpc.aio.Call | None:
        """The transport call owned by this operation, if submitted."""

    @abstractmethod
    async def _start_rpc(self, resolved: ResolvedRequest) -> None:
        """Build after admission and submit with _remaining_timeout()."""

    @abstractmethod
    def _release_transport(self) -> None:
        """Drop transport references and buffers after cleanup."""

    def _cancel_transport(self) -> None:
        if self._rpc_call is not None:
            self._rpc_call.cancel()

    async def _close_transport(self) -> None:
        if self._rpc_call is not None:
            await self._rpc_call.code()

    def _remaining_timeout(self) -> float:
        # Synchronous request preparation can exhaust the deadline without yielding.
        remaining = self._deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            self._expire()
            self._check_outcome()
        return max(0.000001, remaining)

    def _finish(self, result: ExecutionResult) -> None:
        self._result = result
        self.finished_at = asyncio.get_running_loop().time()
        if self._timer:
            self._timer.cancel()

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
        self._cancel_transport()

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
        client._executions.add(self)
        self._timer = loop.call_at(self._deadline, self._expire)
        async with self._guard():
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
            await self._start_rpc(self._resolved)
            self._check_outcome()
            return self

    @asynccontextmanager
    async def _guard(self) -> AsyncGenerator[None]:
        """Normalize transport failures and finalize ownership on every exceptional exit."""
        try:
            yield
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
        await join_cleanup(self._close_task)

    async def _close(self) -> None:
        try:
            async with asyncio.timeout(self._client.timeouts.cleanup_seconds):
                if self._admission is not None:
                    try:
                        acquired = await self._admission
                        if acquired and not self._permit:
                            self._permit = True
                    except asyncio.CancelledError:
                        if not self._admission.cancelled():
                            raise
                await self._close_transport()
        finally:
            if self._permit:
                self._client._semaphore.release()
                self._permit = False
            self._client._executions.discard(self)
            self._release_transport()
            self._admission = None

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if isinstance(exc, BaseException):
            await self._cleanup_preserving(exc)
            return
        try:
            await self.aclose()
        except TimeoutError:
            if exc is None:
                raise ClientStateError("Local cleanup grace exceeded") from None
