"""Run against the documented local test image."""

import asyncio

from go_judge_client import AsyncGoJudgeClient, ExecutionRequest, Finished, Output, TextDecoder


async def main() -> None:
    decoder = TextDecoder()
    async with AsyncGoJudgeClient("localhost:5051", insecure=True) as client:
        async with client.stream(ExecutionRequest(command=("/bin/echo", "Hello"))) as execution:
            async for event in execution:
                if isinstance(event, Output):
                    print(decoder.decode(event), end="", flush=True)
                elif isinstance(event, Finished):
                    print(event.result.summary().model_dump(mode="json"))


if __name__ == "__main__":
    asyncio.run(main())
