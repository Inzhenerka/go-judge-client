"""Verify actual SIGINT handling on POSIX against the disposable real server."""

import asyncio
import os
import signal
import sys
import tempfile
from pathlib import Path


async def main() -> None:
    if os.name != "posix":
        raise SystemExit("Run this signal check on the disposable Linux integration host")
    target = os.environ["GO_JUDGE_TEST_TARGET"]
    environment = os.environ | {"GJ_SIGNAL_TEST_TOKEN": os.environ.get("GO_JUDGE_TEST_TOKEN", "gj-local-test-only")}
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory) / "main.py"
        project.write_text("import time\nprint('ready', flush=True)\ntime.sleep(10)\n")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from go_judge_client.cli import main; main()",
            "run",
            str(project),
            "--command",
            "/usr/local/runtimes/python-data/bin/python",
            "--command=-u",
            "--command",
            "main.py",
            "--target",
            target,
            "--insecure",
            "--token-env",
            "GJ_SIGNAL_TEST_TOKEN",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        try:
            assert process.stdout is not None
            line = await asyncio.wait_for(process.stdout.readline(), 10)
            assert line == b"ready\n", line
            process.send_signal(signal.SIGINT)
            _, stderr = await asyncio.wait_for(process.communicate(), 10)
            assert process.returncode == 130, (process.returncode, stderr)
            assert b"Cancelled" in stderr and b"Traceback" not in stderr
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    print("CLI output arrived before completion; SIGINT finalized the process with exit 130.")


if __name__ == "__main__":
    asyncio.run(main())
