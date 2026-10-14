"""Ordinary queued execution through the unary Exec RPC."""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc

from ._grpc.request_pb2 import Request
from ._grpc.response_pb2 import Response
from ._mapping import buffered_result, unary_request
from ._operation import Operation
from .models import ExecutionRequest, ExecutionResult
from .profiles import ResolvedRequest

if TYPE_CHECKING:
    from .client import AsyncGoJudgeClient


class UnaryExecution(Operation):
    def __init__(self, client: AsyncGoJudgeClient, request: ExecutionRequest, timeout_seconds: float | None) -> None:
        super().__init__(client, request, timeout_seconds)
        self._call: grpc.aio.UnaryUnaryCall[Request, Response] | None = None

    @property
    def _rpc_call(self) -> grpc.aio.Call | None:
        return self._call

    async def _start_rpc(self, resolved: ResolvedRequest) -> None:
        client = self._client
        message = unary_request(resolved, client.budgets)
        remaining = self._remaining_timeout()
        assert client._exec_rpc is not None
        self._call = client._exec_rpc(message, timeout=remaining, metadata=client._metadata, wait_for_ready=False)

    async def wait(self) -> ExecutionResult:
        """Await a terminal unary response; no streaming events or reader buffers."""
        self._client._check_loop()
        self._check_outcome()
        async with self._guard():
            assert self._call is not None and self._resolved is not None
            response = await self._call
            self._check_outcome()
            result = buffered_result(response, self._resolved, self._client.budgets)
            self._finish(result)
            return result

    def _release_transport(self) -> None:
        self._call = None
