"""Terminal consumer of the public SDK. No protobuf or transport shortcuts."""

import asyncio
import os
import sys
import tomllib
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from .. import (
    Artifact,
    AsyncGoJudgeClient,
    ClientBudgets,
    ConfigurationError,
    ExecutionRequest,
    ExpectedFile,
    Finished,
    GoJudgeClientError,
    Output,
    RuntimeProfile,
    TextDecoder,
)
from .project_files import load_project, save_artifact

app = typer.Typer(no_args_is_help=True, help="Typed streaming execution on a remote go-judge server.")


class ProfileDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    runtimes: dict[str, RuntimeProfile]


def load_profiles(path: Path | None) -> dict[str, RuntimeProfile]:
    if path is None:
        return {}
    with path.open("rb") as stream:
        return ProfileDocument.model_validate(tomllib.load(stream)).runtimes


def token_from_env(name: str | None) -> SecretStr | None:
    if name is None:
        return None
    value = os.environ.get(name)
    if not value:
        raise ConfigurationError("Requested token environment variable is unset or empty")
    return SecretStr(value)


@app.command()
def profiles(profiles: Annotated[Path, typer.Option(help="Runtime profile TOML file")]) -> None:
    """List configured names locally; this does not discover installed runtimes."""
    try:
        client = AsyncGoJudgeClient("localhost:5051", runtimes=load_profiles(profiles))
        for name in client.runtime_names:
            typer.echo(name)
    except (OSError, ValueError, GoJudgeClientError):
        typer.echo("Unable to validate profile configuration.", err=True)
        raise typer.Exit(2) from None


@app.command()
def check(
    target: str = "localhost:5051", insecure: bool = False, token_env: str | None = None, timeout: float = 5
) -> None:
    """Check gRPC connectivity only; does not authenticate or run a program."""

    async def perform() -> None:
        async with AsyncGoJudgeClient(target, insecure=insecure, token=token_from_env(token_env)) as client:
            await client.wait_ready(timeout_seconds=timeout)

    try:
        asyncio.run(perform())
    except (GoJudgeClientError, ValueError):
        typer.echo("gRPC connectivity check failed.", err=True)
        raise typer.Exit(2) from None
    typer.echo("gRPC transport connected. Authentication, runtimes, isolation and capacity were not checked.")


@app.command()
def run(
    project: Annotated[Path, typer.Argument(help="Local project directory or single file")],
    profiles: Path | None = None,
    runtime: str | None = None,
    entrypoint: str | None = None,
    command: Annotated[list[str] | None, typer.Option(help="Repeat for each direct argv element")] = None,
    arg: Annotated[list[str] | None, typer.Option(help="Additional profile argument")] = None,
    expect: Annotated[list[str] | None, typer.Option()] = None,
    optional_expect: Annotated[list[str] | None, typer.Option()] = None,
    target: str = "localhost:5051",
    insecure: bool = False,
    token_env: str | None = None,
    output_dir: Path = Path("gj-output"),
    include_excluded: bool = False,
    stdin_file: Path | None = None,
    timeout: float = 150,
) -> None:
    """Run once, forward live output, and save explicitly requested artifacts."""

    async def perform() -> int:
        budgets = ClientBudgets()
        files = load_project(project, budgets, include_excluded=include_excluded)
        stdin = b""
        if stdin_file is not None:
            with stdin_file.open("rb") as stream:
                stdin = stream.read(budgets.stdin_bytes + 1)
        request = ExecutionRequest(
            runtime=runtime,
            command=tuple(command) if command else None,
            entrypoint=entrypoint or (project.name if runtime and project.is_file() else None),
            args=tuple(arg or ()),
            files=files,
            stdin=stdin,
            expected_files=tuple(
                [ExpectedFile(path=p) for p in expect or ()]
                + [ExpectedFile(path=p, required=False) for p in optional_expect or ()]
            ),
        )
        decoder = TextDecoder()
        async with AsyncGoJudgeClient(
            target,
            insecure=insecure,
            token=token_from_env(token_env),
            runtimes=load_profiles(profiles),
            budgets=budgets,
        ) as client:
            async with client.stream(request, timeout_seconds=timeout, capture_output=False) as execution:
                async for event in execution:
                    if isinstance(event, Output):
                        destination = sys.stdout if event.stream == "stdout" else sys.stderr
                        destination.write(decoder.decode(event))
                        destination.flush()
                    elif isinstance(event, Artifact):
                        saved = save_artifact(output_dir, event.file)
                        typer.echo(f"Saved: {saved}", err=True)
                    elif isinstance(event, Finished):
                        sys.stdout.write(decoder.finish("stdout"))
                        sys.stderr.write(decoder.finish("stderr"))
                        result = event.result
                        typer.echo(
                            f"\n{result.status}; exit={result.exit_status}; cpu={result.cpu_seconds:.6f}s; "
                            f"elapsed={result.elapsed_seconds:.6f}s; memory={result.memory_bytes} bytes",
                            err=True,
                        )
                        if result.not_received:
                            typer.echo("Not received: " + ", ".join(result.not_received), err=True)
                        return 0 if result.status == "accepted" and result.required_artifacts_satisfied else 1
        return 2

    try:
        code = asyncio.run(perform())
    except KeyboardInterrupt:
        typer.echo("Cancelled. Remote cleanup is not confirmed.", err=True)
        raise typer.Exit(130) from None
    except (GoJudgeClientError, ValidationError, OSError, ValueError):
        typer.echo(
            "Execution failed: check configuration, connection and file budgets. No retry was attempted.", err=True
        )
        raise typer.Exit(2) from None
    raise typer.Exit(code)
