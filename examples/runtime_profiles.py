import asyncio

from go_judge_client import AsyncGoJudgeClient, ExecutionRequest, RuntimeProfile


async def main() -> None:
    profiles = {
        "python": RuntimeProfile(
            command=("/usr/local/runtimes/python-data/bin/python", "-u"), default_entrypoint="main.py"
        )
    }
    async with AsyncGoJudgeClient("localhost:5051", insecure=True, runtimes=profiles) as client:
        result = await client.execute(ExecutionRequest(runtime="python", files={"main.py": "print('Hello')"}))
        print(result.stdout)


if __name__ == "__main__":
    asyncio.run(main())
