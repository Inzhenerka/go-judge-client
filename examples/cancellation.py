import asyncio

from go_judge_client import AsyncGoJudgeClient, ExecutionRequest


async def main() -> None:
    async with AsyncGoJudgeClient("localhost:5051", insecure=True) as client:
        async with client.stream(ExecutionRequest(command=("/bin/sh", "-c", "echo ready; sleep 2"))) as execution:
            print(await anext(execution))
            await execution.cancel()
            # Local ownership is finalized. Remote termination is not confirmed.


if __name__ == "__main__":
    asyncio.run(main())
