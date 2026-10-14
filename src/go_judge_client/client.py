"""Long-lived gRPC transport and operation ownership."""

import asyncio
from collections.abc import Mapping
from typing import Self, cast

import grpc
from pydantic import SecretStr

from ._grpc.judge_pb2_grpc import ExecutorStub
from ._grpc.stream_request_pb2 import StreamRequest
from ._grpc.stream_response_pb2 import StreamResponse
from ._tasks import join_cleanup
from .errors import ClientStateError, ConnectionError, UnknownRuntimeError
from .execution import Execution
from .models import (
    ClientBudgets,
    ConnectionConfig,
    ExecutionRequest,
    ExecutionResult,
    Limits,
    ResolvedLimits,
    RuntimeProfile,
    Timeouts,
    resolve_limits,
    runtime_name,
    timeout_value,
)


class AsyncGoJudgeClient:
    def __init__(
        self,
        target: str,
        *,
        insecure: bool = False,
        token: SecretStr | None = None,
        root_certificates: bytes | None = None,
        private_key: bytes | None = None,
        certificate_chain: bytes | None = None,
        runtimes: Mapping[str, RuntimeProfile] | None = None,
        max_concurrency: int = 8,
        timeouts: Timeouts | None = None,
        budgets: ClientBudgets | None = None,
        default_limits: Limits | None = None,
    ) -> None:
        self._config = ConnectionConfig(
            target=target,
            insecure=insecure,
            token=token,
            root_certificates=root_certificates,
            private_key=private_key,
            certificate_chain=certificate_chain,
        )
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        self._max_concurrency = max_concurrency
        self.timeouts = Timeouts.model_validate((timeouts or Timeouts()).model_dump())
        self.budgets = ClientBudgets.model_validate((budgets or ClientBudgets()).model_dump())
        self.default_limits = Limits.model_validate((default_limits or Limits()).model_dump())
        self._runtimes = {
            runtime_name(name): RuntimeProfile.model_validate(profile.model_dump())
            for name, profile in (runtimes or {}).items()
        }
        self._loop: asyncio.AbstractEventLoop | None = None
        self._channel: grpc.aio.Channel | None = None
        self._rpc: grpc.aio.StreamStreamMultiCallable[StreamRequest, StreamResponse] | None = None
        self._metadata: tuple[tuple[str, str], ...] = ()
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._executions: set[Execution] = set()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def runtime_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._runtimes))

    def get_runtime(self, name: str) -> RuntimeProfile:
        runtime_name(name)
        try:
            return self._runtimes[name].model_copy(deep=True)
        except KeyError:
            raise UnknownRuntimeError("Runtime is not registered") from None

    def effective_limits(self, request: ExecutionRequest) -> ResolvedLimits:
        """Inspect inherited execution limits without opening a connection or running code."""
        request = ExecutionRequest.model_validate(request.model_dump())
        profile = self.get_runtime(request.runtime) if request.runtime is not None else None
        return resolve_limits(self.default_limits, profile.limits if profile else None, request.limits)

    def _check_loop(self) -> None:
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise ClientStateError("Client belongs to a different event loop")

    def _check_open(self) -> None:
        self._check_loop()
        if self._closed or self._channel is None:
            raise ClientStateError("Client must be started and not closed")

    async def start(self) -> None:
        self._check_loop()
        if self._closed:
            raise ClientStateError("Closed clients cannot be restarted")
        if self._channel is not None:
            return
        self._loop = asyncio.get_running_loop()
        config = self._config
        options = (
            ("grpc.max_receive_message_length", self.budgets.receive_message_bytes),
            ("grpc.max_send_message_length", self.budgets.send_message_bytes),
            ("grpc.enable_retries", 0),
            ("grpc.enable_http_proxy", 0),
        )
        if config.insecure:
            self._channel = grpc.aio.insecure_channel(config.target, options=options)
            if config.token:
                self._metadata = (("authorization", f"Bearer {config.token.get_secret_value()}"),)
        else:
            credentials = grpc.ssl_channel_credentials(
                config.root_certificates, config.private_key, config.certificate_chain
            )
            if config.token:
                credentials = grpc.composite_channel_credentials(
                    credentials, grpc.access_token_call_credentials(config.token.get_secret_value())
                )
            self._channel = grpc.aio.secure_channel(config.target, credentials, options=options)
        # grpcio-tools does not type its service stub; narrow this single boundary.
        self._rpc = cast(
            "grpc.aio.StreamStreamMultiCallable[StreamRequest, StreamResponse]", ExecutorStub(self._channel).ExecStream
        )

    async def wait_ready(self, *, timeout_seconds: float | None = None) -> None:
        self._check_open()
        duration = timeout_value(timeout_seconds if timeout_seconds is not None else self.timeouts.connection_seconds)
        assert self._channel is not None
        try:
            async with asyncio.timeout(duration):
                await self._channel.channel_ready()
        except TimeoutError:
            raise ConnectionError("gRPC readiness deadline exceeded") from None

    def stream(
        self, request: ExecutionRequest, *, timeout_seconds: float | None = None, capture_output: bool = True
    ) -> Execution:
        return Execution(self, request, timeout_seconds, capture_output)

    async def execute(self, request: ExecutionRequest, *, timeout_seconds: float | None = None) -> ExecutionResult:
        async with self.stream(request, timeout_seconds=timeout_seconds) as execution:
            async for _ in execution:
                pass
            return execution.result

    async def _close(self) -> None:
        for execution in tuple(self._executions):
            execution._request_cancel()
        try:
            async with asyncio.timeout(self.timeouts.cleanup_seconds):
                await asyncio.gather(*(e.aclose() for e in tuple(self._executions)))
        finally:
            if self._channel is not None:
                await self._channel.close()
                self._channel = None
                self._rpc = None

    async def aclose(self) -> None:
        self._check_loop()
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close())
        await join_cleanup(self._close_task)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            await self.aclose()
        except Exception:
            if not isinstance(exc, BaseException):
                raise
            exc.add_note("Secondary client cleanup failure; remote cleanup is not confirmed")
