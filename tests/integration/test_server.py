"""Benign functional acceptance. Use a disposable Linux server, not production."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

from go_judge_client import (
    AsyncGoJudgeClient,
    AuthenticationError,
    ExecutionCancelledError,
    ExecutionRequest,
    ExpectedFile,
    Limits,
    Output,
    RuntimeProfile,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def target() -> str:
    value = os.environ.get("GO_JUDGE_TEST_TARGET")
    if value is None:
        pytest.fail("Set GO_JUDGE_TEST_TARGET explicitly; integration skips are not acceptance passes")
    return value


def token() -> SecretStr:
    return SecretStr(os.environ.get("GO_JUDGE_TEST_TOKEN", "gj-local-test-only"))


def client(target: str) -> AsyncGoJudgeClient:
    return AsyncGoJudgeClient(
        target,
        insecure=True,
        token=token(),
        runtimes={
            "python": RuntimeProfile(
                command=("/usr/local/runtimes/python-data/bin/python", "-u"), default_entrypoint="main.py"
            )
        },
    )


async def test_real_live_binary_stdin_and_artifacts(target: str) -> None:
    code = """import sys, time
from pathlib import Path
data = sys.stdin.buffer.read()
print('early', flush=True)
sys.stderr.write('diagnostic\\n'); sys.stderr.flush()
time.sleep(0.5)
Path('binary').write_bytes(Path('input.bin').read_bytes() + data)
Path('empty').touch()
print('late', flush=True)
"""
    async with client(target) as sdk:
        await sdk.wait_ready()
        async with sdk.stream(
            ExecutionRequest(
                runtime="python",
                files={"main.py": code, "input.bin": b"\0\xff"},
                stdin=b"\x80",
                expected_files=(
                    ExpectedFile(path="binary"),
                    ExpectedFile(path="empty"),
                    ExpectedFile(path="missing"),
                    ExpectedFile(path="optional", required=False),
                ),
            )
        ) as execution:
            early_at = None
            late_at = None
            async for event in execution:
                if isinstance(event, Output) and b"early" in event.data:
                    early_at = asyncio.get_running_loop().time()
                if isinstance(event, Output) and b"late" in event.data:
                    late_at = asyncio.get_running_loop().time()
            result = execution.result
        assert early_at is not None and late_at is not None and late_at - early_at > 0.3
        assert result.stdout == b"early\nlate\n"
        assert result.stderr == b"diagnostic\n"
        assert result.artifacts["binary"].data == b"\0\xff\x80"
        assert result.artifacts["empty"].data == b""
        assert result.not_received == ("missing", "optional")
        assert not result.required_artifacts_satisfied
        assert any(p.path == "missing" for p in result.artifact_problems)


async def test_real_auth_and_readiness(target: str) -> None:
    for credential in (None, SecretStr("wrong-synthetic-token")):
        async with AsyncGoJudgeClient(target, insecure=True, token=credential) as sdk:
            await sdk.wait_ready()
            with pytest.raises(AuthenticationError):
                await sdk.execute(ExecutionRequest(command=("/bin/true",)))


async def test_real_cancel_and_reuse(target: str) -> None:
    async with client(target) as sdk:
        for _ in range(3):
            async with sdk.stream(ExecutionRequest(command=("/bin/sh", "-c", "echo ready; sleep 2"))) as execution:
                assert isinstance(await anext(execution), Output)
                await execution.cancel()
                with pytest.raises(ExecutionCancelledError):
                    await anext(execution)
            assert (await sdk.execute(ExecutionRequest(command=("/bin/true",)))).status == "accepted"


async def test_real_program_failure_and_wall_limit(target: str) -> None:
    async with client(target) as sdk:
        result = await sdk.execute(ExecutionRequest(command=("/bin/sh", "-c", "exit 7")))
        assert result.status == "nonzero_exit" and result.exit_status == 7
        result = await sdk.execute(ExecutionRequest(command=("/bin/sleep", "2"), limits=Limits(wall_seconds=0.15)))
        assert result.status == "time_limit_exceeded"


async def test_real_symlink_collector_behavior(target: str) -> None:
    async with client(target) as sdk:
        result = await sdk.execute(
            ExecutionRequest(
                command=("/bin/sh", "-c", "printf value > source; ln -s source link"),
                expected_files=(ExpectedFile(path="link"),),
            )
        )
        # Verified on this pin: sandbox Open rejects the symlink before collector Stat.
        assert "link" not in result.artifacts
        assert result.artifact_problems[0].error_name == "CopyOutOpen"
        assert "not a regular file" in result.artifact_problems[0].message


async def test_real_multifile_and_large_finite_stdin(target: str) -> None:
    payload = bytes(range(256)) * 1024
    async with client(target) as sdk:
        result = await sdk.execute(
            ExecutionRequest(
                runtime="python",
                files={
                    "main.py": "import helper, sys\nfrom pathlib import Path\n"
                    "Path('result').write_bytes(helper.data + sys.stdin.buffer.read())\n",
                    "helper.py": "from pathlib import Path\ndata=Path('nested/data.bin').read_bytes()\n",
                    "nested/data.bin": b"\xff\x00",
                    "empty-input": b"",
                },
                stdin=payload,
                expected_files=(ExpectedFile(path="result"),),
            )
        )
        assert result.status == "accepted"
        assert result.artifacts["result"].data == b"\xff\x00" + payload


async def test_real_artifacts_survive_program_failure(target: str) -> None:
    async with client(target) as sdk:
        for tail in ("exit 7", "sleep 2"):
            result = await sdk.execute(
                ExecutionRequest(
                    command=("/bin/sh", "-c", f"printf value > result; {tail}"),
                    limits=Limits(wall_seconds=0.15),
                    expected_files=(ExpectedFile(path="result"),),
                )
            )
            assert result.status in {"nonzero_exit", "time_limit_exceeded"}
            assert result.artifacts["result"].data == b"value"


async def test_real_artifact_size_and_workspace_isolation(target: str) -> None:
    from go_judge_client import ClientBudgets

    async with AsyncGoJudgeClient(target, insecure=True, token=token(), budgets=ClientBudgets(artifact_bytes=2)) as sdk:
        result = await sdk.execute(
            ExecutionRequest(
                command=("/bin/sh", "-c", "printf long > result; touch empty"),
                expected_files=(ExpectedFile(path="result"), ExpectedFile(path="empty")),
            )
        )
        assert "result" not in result.artifacts
        assert result.artifacts["empty"].data == b""
        assert any(problem.error_name == "CopyOutSizeExceeded" for problem in result.artifact_problems)
        result = await sdk.execute(ExecutionRequest(command=("/bin/sh", "-c", "test ! -e empty")))
        assert result.status == "accepted"
        result = await sdk.execute(
            ExecutionRequest(command=("/bin/sh", "-c", "test ! -w /usr/local/runtimes/python-data/bin/python"))
        )
        assert result.status == "accepted"


async def test_real_cli_profile(target: str, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(
        "from pathlib import Path\nprint('live', flush=True)\nPath('result.bin').write_bytes(bytes(range(256)))\n"
    )
    profiles = tmp_path / "profiles.toml"
    profiles.write_text(
        '[runtimes.python]\ncommand=["/usr/local/runtimes/python-data/bin/python", "-u"]\n'
        'default_entrypoint="main.py"\n'
    )
    destination = tmp_path / "saved"
    command = [
        sys.executable,
        "-c",
        "from go_judge_client.cli import main; main()",
        "run",
        str(tmp_path / "main.py"),
        "--profiles",
        str(profiles),
        "--runtime",
        "python",
        "--expect",
        "result.bin",
        "--output-dir",
        str(destination),
        "--target",
        target,
        "--insecure",
        "--token-env",
        "GJ_CLI_TEST_TOKEN",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ | {"GJ_CLI_TEST_TOKEN": token().get_secret_value()},
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
    assert process.returncode == 0, stderr
    assert stdout.splitlines() == [b"live"] and b"accepted" in stderr
    assert (destination / "result.bin").read_bytes() == bytes(range(256))


async def test_real_small_resource_limits(target: str) -> None:
    """Finite, small probes: at most 0.5 CPU seconds, 64 MiB and eight children attempted."""
    async with client(target) as sdk:
        result = await sdk.execute(
            ExecutionRequest(
                runtime="python",
                files={"main.py": "import time\nend=time.monotonic()+0.5\nwhile time.monotonic()<end: pass\n"},
                limits=Limits(cpu_seconds=0.08, wall_seconds=2),
            )
        )
        assert result.status == "time_limit_exceeded"
        result = await sdk.execute(
            ExecutionRequest(
                runtime="python",
                files={"main.py": "data=bytearray(64*1024*1024)\nprint(len(data))\n"},
                limits=Limits(memory_bytes=32 * 1024**2),
            )
        )
        assert result.status == "memory_limit_exceeded"
        source = """import subprocess
children = []
try:
    for _ in range(8):
        children.append(subprocess.Popen(['/bin/sleep', '0.2']))
except BlockingIOError:
    print('limited', flush=True)
finally:
    for child in children:
        child.wait()
"""
        result = await sdk.execute(
            ExecutionRequest(runtime="python", files={"main.py": source}, limits=Limits(processes=4))
        )
        assert result.stdout == b"limited\n"
        assert (await sdk.execute(ExecutionRequest(command=("/bin/true",)))).status == "accepted"


async def test_real_socket_interruption_and_reconnect(target: str) -> None:
    """TCP fault injection only: the product still uses generated grpc.aio transport."""
    from go_judge_client import ConnectionError

    host, _, port = target.rpartition(":")
    writers: set[asyncio.StreamWriter] = set()
    handlers: set[asyncio.Task[None]] = set()

    async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def bridge(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        handlers.add(task)
        remote_reader, remote_writer = await asyncio.open_connection(host, int(port))
        writers.update((writer, remote_writer))
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(pump(reader, remote_writer))
                group.create_task(pump(remote_reader, writer))
        finally:
            writers.difference_update((writer, remote_writer))
            handlers.discard(task)

    proxy = await asyncio.start_server(bridge, "127.0.0.1", 0)
    proxy_port = proxy.sockets[0].getsockname()[1]
    try:
        async with client(f"127.0.0.1:{proxy_port}") as sdk:
            async with sdk.stream(ExecutionRequest(command=("/bin/sh", "-c", "echo early; sleep 1"))) as execution:
                assert isinstance(await anext(execution), Output)
                for writer in tuple(writers):
                    writer.transport.abort()
                with pytest.raises(ConnectionError):
                    await anext(execution)
            await sdk.wait_ready()
            assert (await sdk.execute(ExecutionRequest(command=("/bin/true",)))).status == "accepted"
    finally:
        proxy.close()
        await proxy.wait_closed()
        for writer in tuple(writers):
            writer.close()
        async with asyncio.timeout(5):
            await asyncio.gather(*tuple(handlers))
