"""Small reproducible loopback benchmark; not a universal performance claim."""

import asyncio
import json
import os
import platform
import statistics
import tracemalloc
from typing import cast

import grpc
from pydantic import SecretStr

from go_judge_client import AsyncGoJudgeClient, ClientBudgets, ExecutionRequest, Limits, Output
from go_judge_client._grpc.judge_pb2_grpc import ExecutorStub
from go_judge_client._grpc.stream_request_pb2 import StreamRequest
from go_judge_client._grpc.stream_response_pb2 import StreamResponse
from go_judge_client._mapping import wire_request
from go_judge_client.profiles import resolve


async def main() -> None:
    target = os.environ["GO_JUDGE_TEST_TARGET"]
    token = os.environ.get("GO_JUDGE_TEST_TOKEN", "gj-local-test-only")
    request = ExecutionRequest(command=("/bin/sh", "-c", "printf start; sleep 0.02; printf end"))
    wire = wire_request(resolve(request, {}, Limits(), ClientBudgets()), ClientBudgets())
    results: dict[str, list[tuple[float, float]]] = {"generated_stub": [], "sdk": []}
    loop = asyncio.get_running_loop()
    tracemalloc.start()
    async with grpc.aio.insecure_channel(target, options=(("grpc.enable_retries", 0),)) as channel:
        rpc = cast(
            "grpc.aio.StreamStreamMultiCallable[StreamRequest, StreamResponse]", ExecutorStub(channel).ExecStream
        )
        for _ in range(10):
            start = loop.time()
            call = rpc(timeout=5, metadata=(("authorization", f"Bearer {token}"),))
            await call.write(StreamRequest(execRequest=wire))
            await call.done_writing()
            first = None
            while True:
                event = await call.read()
                if event is grpc.aio.EOF:
                    break
                if isinstance(event, StreamResponse) and event.WhichOneof("response") == "execOutput" and first is None:
                    first = loop.time()
            assert await call.code() == grpc.StatusCode.OK and first is not None
            results["generated_stub"].append((first - start, loop.time() - start))
    async with AsyncGoJudgeClient(target, insecure=True, token=SecretStr(token)) as client:
        for _ in range(10):
            start = loop.time()
            first = None
            async with client.stream(request) as execution:
                async for event in execution:
                    if isinstance(event, Output) and first is None:
                        first = loop.time()
                assert first is not None and execution.result.stdout == b"startend"
            results["sdk"].append((first - start, loop.time() - start))
    _, peak = tracemalloc.get_traced_memory()
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "grpc": grpc.__version__,
                "runs_each": 10,
                "concurrency": 1,
                "input_bytes": 0,
                "output_bytes": 8,
                "python_tracemalloc_peak_bytes_both": peak,
                "measurements": {
                    name: {
                        "median_first_output_ms": statistics.median(x[0] for x in rows) * 1000,
                        "median_total_ms": statistics.median(x[1] for x in rows) * 1000,
                    }
                    for name, rows in results.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
