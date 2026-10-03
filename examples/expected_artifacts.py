import asyncio

from go_judge_client import AsyncGoJudgeClient, ExecutionRequest, ExpectedFile


async def main() -> None:
    async with AsyncGoJudgeClient("localhost:5051", insecure=True) as client:
        result = await client.execute(
            ExecutionRequest(
                command=("/bin/cp", "input.bin", "output.bin"),
                files={"input.bin": b"\0\xff"},
                expected_files=(ExpectedFile(path="output.bin"),),
            )
        )
        print(result.artifacts["output.bin"].size_bytes)


if __name__ == "__main__":
    asyncio.run(main())
