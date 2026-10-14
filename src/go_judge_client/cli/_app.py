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


def error_message(error: Exception) -> str:
    """Expose local error categories without remote details, values or dynamic map keys."""
    if isinstance(error, ValidationError):
        fields = ExecutionRequest.model_fields.keys() | RuntimeProfile.model_fields.keys() | {"runtimes"}
        issues = []
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            location = item["loc"]
            field = str(location[0]) if location and location[0] in fields else "configuration"
            reason = {"missing": "required field", "extra_forbidden": "unexpected field"}.get(
                item["type"], "invalid value"
            )
            issues.append(f"{field}: {reason}")
        return "Invalid configuration: " + "; ".join(dict.fromkeys(issues)) + "."
    if isinstance(error, GoJudgeClientError):
        return f"{type(error).__name__}: {error}"
    if isinstance(error, FileExistsError):
        return "Artifact destination already exists. Choose a new --output-dir or remove the existing file."
    if isinstance(error, FileNotFoundError):
        return "Local file or directory was not found. Check the project, --profiles and --stdin-file paths."
    if isinstance(error, PermissionError):
        return "Local file access denied. Check read permissions and --output-dir write permissions."
    if isinstance(error, OSError):
        return "Local file operation failed. Check file types, available space and destination permissions."
    if isinstance(error, tomllib.TOMLDecodeError):
        return "Invalid TOML syntax in the profiles file."
    return "Invalid configuration. Check option values and path syntax."


@app.command()
def profiles(profiles: Annotated[Path, typer.Option(help="Runtime profile TOML file")]) -> None:
    """List configured names locally; this does not discover installed runtimes."""
    try:
        client = AsyncGoJudgeClient("localhost:5051", runtimes=load_profiles(profiles))
        for name in client.runtime_names:
            typer.echo(name)
    except (OSError, ValueError, GoJudgeClientError) as error:
        typer.echo(error_message(error), err=True)
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
    except (GoJudgeClientError, ValueError) as error:
        typer.echo(error_message(error), err=True)
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
        if (runtime is None) == (command is None):
            raise ConfigurationError("Provide exactly one of --runtime and --command")
        files = load_project(project, budgets, include_excluded=include_excluded, output_dir=output_dir)
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
    except (GoJudgeClientError, OSError, ValueError) as error:
        typer.echo(error_message(error), err=True)
        raise typer.Exit(2) from None
    raise typer.Exit(code)
