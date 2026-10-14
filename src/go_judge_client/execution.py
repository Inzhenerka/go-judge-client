"""Pull-based streaming execution with bounded output capture."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Self

import grpc

from ._grpc.response_pb2 import Response
from ._grpc.stream_request_pb2 import StreamRequest
from ._grpc.stream_response_pb2 import StreamResponse
from ._mapping import final_result, wire_request
from ._operation import Operation
from .errors import ClientLimitExceededError, ClientStateError, ProtocolError, rpc_error
from .events import Artifact, ExecutionEvent, Finished, Output, TextExecutionEvent, TextOutput
from .models import ExecutionRequest
from .profiles import ResolvedRequest
from .text import TextDecoder

if TYPE_CHECKING:
    from .client import AsyncGoJudgeClient


class Execution(Operation):
    """Single-use streaming context and iterator.

    Only the consumer reads the RPC. A final response remains provisional until
    terminal OK. Output buffers and the finite request sender belong to this context.
    """

    def __init__(
        self, client: AsyncGoJudgeClient, request: ExecutionRequest, timeout_seconds: float | None, capture_output: bool
    ) -> None:
        super().__init__(client, request, timeout_seconds)
        self._capture = capture_output
        self._call: grpc.aio.StreamStreamCall[StreamRequest, StreamResponse] | None = None
        self._sending: asyncio.Task[None] | None = None
        self._candidate: Response | None = None
        self._pending: deque[ExecutionEvent] = deque()
        self._stdout = bytearray()
        self._stderr = bytearray()
        self.output_bytes = 0
        self.first_output_at: float | None = None
        self._reading = False
        self._reader_mode: str | None = None

    @property
    def _rpc_call(self) -> grpc.aio.Call | None:
        return self._call

    async def _start_rpc(self, resolved: ResolvedRequest) -> None:
        client = self._client
        message = wire_request(resolved, client.budgets)
        remaining = self._remaining_timeout()
        assert client._stream_rpc is not None
        self._call = client._stream_rpc(timeout=remaining, metadata=client._metadata, wait_for_ready=False)
        self._sending = asyncio.create_task(self._send(self._call, StreamRequest(execRequest=message)))
        await self._sending

    def _cancel_transport(self) -> None:
        super()._cancel_transport()
        if self._sending is not None and not self._sending.done():
            self._sending.cancel()

    async def _close_transport(self) -> None:
        if self._sending is not None:
            await asyncio.gather(self._sending, return_exceptions=True)
        await super()._close_transport()

    def _release_transport(self) -> None:
        self._candidate = None
        self._pending.clear()
        self._stdout.clear()
        self._stderr.clear()
        self._call = None
        self._sending = None

    @staticmethod
    async def _send(call: grpc.aio.StreamStreamCall[StreamRequest, StreamResponse], message: StreamRequest) -> None:
        # Own the write waiter too: cancelling the RPC alone may not wake a pending handshake.
        await call.write(message)
        await call.done_writing()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> ExecutionEvent:
        if self._reader_mode == "text":
            raise ClientStateError("Cannot mix byte and text readers")
        self._reader_mode = "bytes"
        return await self._next_event()

    def text_events(self, *, encoding: str = "utf-8", errors: str = "replace") -> AsyncIterator[TextExecutionEvent]:
        """Select a single text reader; flush decoder tails before Finished on successful RPC completion."""
        self._client._check_loop()
        if not self._entered:
            raise ClientStateError("Enter the execution context before iterating")
        self._check_outcome()
        if self._reader_mode is not None:
            raise ClientStateError("Cannot mix or replace execution readers")
        decoder = TextDecoder(encoding, errors)
        self._reader_mode = "text"
        return self._text_events(decoder)

    async def _text_events(self, decoder: TextDecoder) -> AsyncIterator[TextExecutionEvent]:
        try:
            while True:
                try:
                    event = await self._next_event()
                except StopAsyncIteration:
                    return
                if isinstance(event, Output):
                    text = decoder.decode(event)
                    if text:
                        yield TextOutput(event.stream, text)
                else:
                    if isinstance(event, Finished):
                        for stream in ("stdout", "stderr"):
                            text = decoder.finish(stream)
                            if text:
                                yield TextOutput(stream, text)
                    yield event
        except Exception as error:
            await self._cleanup_preserving(error)
            raise

    async def _next_event(self) -> ExecutionEvent:
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
            async with self._guard():
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
                        self._finish(result)
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
        finally:
            self._reading = False
