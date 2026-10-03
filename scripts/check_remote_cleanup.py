"""Observe only synthetic marked processes in the disposable test container."""

import asyncio
import json
import os
import subprocess
import time
from uuid import uuid4

from pydantic import SecretStr

from go_judge_client import AsyncGoJudgeClient, ExecutionRequest, Output


async def main() -> None:
    container = os.environ["GO_JUDGE_TEST_CONTAINER"]
    target = os.environ["GO_JUDGE_TEST_TARGET"]
    identity = (
        await asyncio.to_thread(
            subprocess.check_output,
            ["docker", "inspect", container, "--format", '{{ index .Config.Labels "go-judge-client.test" }}'],
            text=True,
            timeout=5,
        )
    ).strip()
    if identity != "true":
        raise SystemExit("Refusing to inspect a container without the dedicated test label")
    marker = "gj-cleanup-" + uuid4().hex
    probe = (
        "import pathlib,sys,json; marker=sys.argv[1].encode(); found=[]; "
        "files=pathlib.Path('/proc').glob('[0-9]*/cmdline'); "
        "[(found.append(p.parent.name) if marker in p.read_bytes().split(b'\\0') "
        "and p.parent.name!=str(__import__('os').getpid()) else None) for p in files if p.exists()]; "
        "print(json.dumps(found))"
    )

    def marked_processes() -> list[str]:
        output = subprocess.check_output(
            ["docker", "exec", container, "python", "-c", probe, marker], text=True, timeout=5
        )
        return json.loads(output)

    source = (
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)',sys.argv[1]])\n"
        "print('ready',flush=True)\ntime.sleep(10)\n"
    )
    async with AsyncGoJudgeClient(
        target, insecure=True, token=SecretStr(os.environ.get("GO_JUDGE_TEST_TOKEN", "gj-local-test-only"))
    ) as client:
        async with client.stream(
            ExecutionRequest(command=("/usr/local/bin/python", "-u", "main.py", marker), files={"main.py": source})
        ) as execution:
            assert isinstance(await anext(execution), Output)
            assert len(await asyncio.to_thread(marked_processes)) >= 2
            await execution.cancel()
        deadline = time.monotonic() + 3
        while await asyncio.to_thread(marked_processes):
            if time.monotonic() > deadline:
                raise AssertionError("Marked descendants remained after cancellation")
            await asyncio.sleep(0.05)
        assert (await client.execute(ExecutionRequest(command=("/bin/true",)))).status == "accepted"
    print("Marked parent and child disappeared within 3 seconds of cancellation; subsequent execution passed.")


if __name__ == "__main__":
    asyncio.run(main())
