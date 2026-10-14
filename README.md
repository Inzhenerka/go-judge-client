# go-judge-client

An asynchronous, typed Python SDK for running programs on an existing **go-judge** server.
Live stdout/stderr, named runtime profiles, binary project files, expected artifacts and explicit cancellation.
Python 3.12+, Pydantic v2, `grpc.aio`. No web service or sandbox installer is included.
Linux is the supported deployment platform; CI tests Python 3.12–3.14. Windows is outside the support scope.

Install and check a local checkout (PyPI publication is enabled separately; see [releases](docs/releases.md)):

```sh
uv sync
uv run poe check
```

For another uv project, use `uv add /path/to/go-judge-client`. The CLI is optional:
`uv add '/path/to/go-judge-client[cli]'`. The core dependencies do not include Typer.

## Run a command

The server must already be running and contain the requested executable:

```python
import asyncio
from go_judge_client import AsyncGoJudgeClient, ExecutionRequest


async def main() -> None:
    async with AsyncGoJudgeClient("localhost:15051", insecure=True) as client:
        result = await client.execute(ExecutionRequest(command=("/bin/echo", "Hello")))
        print(result.stdout_text())
        print(result.success, result.status)


asyncio.run(main())
```

`result.success` means the program was accepted and all required artifacts were received without
file errors. Program failures are results; transport failures raise exceptions. `ExecutionStatus`
is a string enum, so existing comparisons such as `result.status == "accepted"` also work.

## Streaming Python API

The endpoint must already have the selected runtime installed. This example matches the
[runtime image](examples/runtime-image/Dockerfile), using explicit loopback plaintext:

```python
import asyncio
from go_judge_client import (
    AsyncGoJudgeClient,
    ExecutionRequest,
    RuntimeProfile,
    ExpectedFile,
    TextOutput,
    Artifact,
    Finished,
)


async def main() -> None:
    profiles = {
        "python": RuntimeProfile(
            command=("/usr/local/runtimes/python-data/bin/python", "-u"),
            default_entrypoint="main.py",
        ),
    }
    async with AsyncGoJudgeClient(
        "localhost:15051",
        insecure=True,
        runtimes=profiles,
        max_concurrency=4,
    ) as client:
        request = ExecutionRequest(
            runtime="python",
            files={
                "main.py": "from pathlib import Path\nprint('Hello', flush=True)\n"
                "Path('result.bin').write_bytes(Path('input.bin').read_bytes())\n",
                "input.bin": b"\x00\xff",
            },
            expected_files=(ExpectedFile(path="result.bin"),),
        )
        async with client.stream(request) as execution:
            async for event in execution.text_events():
                match event:
                    case TextOutput(stream=stream, text=text):
                        print(stream, text, end="")
                    case Artifact(file=file):
                        print(file.path, file.size_bytes)
                    case Finished(result=result):
                        print(result.summary().model_dump(mode="json"))


asyncio.run(main())
```

`await client.execute(ExecutionRequest(command=("/bin/echo", "Hello")))` consumes this same
stream and returns a bounded captured result. `execution.text_events()` handles split UTF-8 sequences and decoder finalization automatically.
Iterating `execution` directly retains the byte-preserving `Output` API. Choose one reader per execution.
`result.stdout_text()` and `result.stderr_text()` decode captured output, returning `None` if capture was disabled.
Use `capture_output=False` when forwarding logs without retaining another transcript.

## Terminal playground

The canonical executable is `go-judge-client`; `gj` is an exact alias.

Build the test image once, then start the local server in the foreground, without authentication
(Docker with Linux containers is required):

```sh
docker build -t go-judge-client-test:e9d70a0 -f examples/runtime-image/Dockerfile .
uv run poe judge
```

The pinned server currently fails functional acceptance on native ARM64 Docker Desktop; amd64
emulation on that host also fails seccomp initialization. Use a native Linux amd64 server for release
acceptance; see [current verification](docs/compatibility.md#current-checkout-verification-2026-10-14).
The Python SDK itself is tested on macOS ARM64 and Linux ARM64.

Keep that terminal open. Press `Ctrl+C` to stop and remove the container. The server is exposed only on
`127.0.0.1:15051`, so local CLI commands do not need `--token-env`.

```sh
uv run gj profiles --profiles examples/runtimes.toml
uv run gj check --target localhost:15051 --insecure
uv run gj run examples/python-data --profiles examples/runtimes.toml \
  --runtime python-data --expect output/result.bin --target localhost:15051 --insecure
```

`check` proves transport connectivity only. `run` streams output and saves artifacts under `gj-output/`
without silently overwriting existing files. The development group installs the CLI for local tests.

## Contracts worth knowing

- Input strings are UTF-8 content; bytes remain bytes. Paths are sandbox-relative POSIX paths.
- An operation owns its RPC and local permit. Exit its context, including on handler errors and disconnects.
- `await execution.cancel()` performs bounded local cleanup. It does not prove remote process termination.
- Artifacts and `Finished` are emitted only after a valid final response **and** successful RPC termination.
- Missing required files and nonzero program exits are results; transport/configuration failures are exceptions.
- Readiness is not authentication or sandbox health. TLS is the default; plaintext is an explicit local choice.
- There is no execution retry or fallback to polling. A failed connection can leave the remote outcome unknown.

Read [CLI usage](docs/cli.md), [profiles](docs/profiles.md), [artifacts](docs/artifacts.md),
[lifecycle and security](docs/lifecycle-and-security.md), [compatibility evidence](docs/compatibility.md),
[development](docs/development.md), and [application integration](docs/pumproom-integration.md).
