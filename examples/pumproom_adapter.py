"""Framework-neutral request-linked adapter with synthetic, in-memory storage."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from go_judge_client import (
    Artifact,
    ArtifactFile,
    AsyncGoJudgeClient,
    ExecutionEvent,
    ExecutionRequest,
    ExpectedFile,
    Finished,
    RuntimeProfile,
)


class TaskFiles(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    text: dict[str, str] = Field(default_factory=dict, repr=False)
    binary: dict[str, bytes] = Field(default_factory=dict, repr=False)


class ArtifactStorage(Protocol):
    async def save(self, attempt_id: str, artifact: ArtifactFile) -> None: ...


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], bytes] = {}

    async def save(self, attempt_id: str, artifact: ArtifactFile) -> None:
        self.files[attempt_id, artifact.path] = artifact.data


async def run_attempt(
    client: AsyncGoJudgeClient, attempt_id: str, files: TaskFiles, storage: ArtifactStorage
) -> AsyncGenerator[ExecutionEvent]:
    if files.text.keys() & files.binary.keys():
        raise ValueError("Duplicate text/binary project paths")
    request = ExecutionRequest(
        request_id=attempt_id,
        runtime="python",
        files=files.text | files.binary,
        expected_files=(ExpectedFile(path="result.bin"),),
    )
    async with client.stream(request, capture_output=False) as execution:
        async for event in execution:
            if isinstance(event, Artifact):
                await storage.save(attempt_id, event.file)
            yield event


async def main() -> None:
    from contextlib import aclosing

    async with AsyncExitStack() as lifespan:
        client = await lifespan.enter_async_context(
            AsyncGoJudgeClient(
                "localhost:5051",
                insecure=True,
                runtimes={
                    "python": RuntimeProfile(
                        command=("/usr/local/runtimes/python-data/bin/python", "-u"), default_entrypoint="main.py"
                    )
                },
            )
        )
        files = TaskFiles(
            text={
                "main.py": "from pathlib import Path\nPath('result.bin').write_bytes(Path('input.bin').read_bytes())\n"
            },
            binary={"input.bin": b"\0\xff"},
        )
        # Handler must own/close the async generator on disconnect or early exit.
        async with aclosing(run_attempt(client, "local-attempt-1", files, MemoryStorage())) as events:
            async for event in events:
                if isinstance(event, Finished):
                    print(event.result.summary().model_dump(mode="json"))
                # Forward Output deltas to the frontend here. Never resend the full transcript.


if __name__ == "__main__":
    asyncio.run(main())
