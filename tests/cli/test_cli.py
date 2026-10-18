import builtins
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from go_judge_client import ArtifactFile, ClientBudgets, ClientLimitExceededError, ConfigurationError
from go_judge_client.cli import main
from go_judge_client.cli._app import app, token_from_env
from go_judge_client.cli.project_files import load_project, save_artifact

runner = CliRunner()


def test_help_profiles_and_invalid_configuration(tmp_path: Path) -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    profiles = tmp_path / "runtimes.toml"
    profiles.write_text('[runtimes.python]\ncommand=["python", "-u"]\n[runtimes.python.env]\nKEY="secret-value"')
    result = runner.invoke(app, ["profiles", "--profiles", str(profiles)])
    assert result.exit_code == 0 and "python" in result.stdout and "secret-value" not in result.stdout
    profiles.write_text('[runtimes.python]\nunknown="secret-value"')
    result = runner.invoke(app, ["profiles", "--profiles", str(profiles)])
    assert result.exit_code == 2 and "secret-value" not in result.output


def test_core_only_shim(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    original = builtins.__import__

    def missing(name: str, *args: object, **kwargs: object) -> object:
        if name == "_app":
            raise ModuleNotFoundError("missing", name="typer")
        return original(name, *args, **kwargs)  # ty: ignore[invalid-argument-type]

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "go-judge-client[cli]" in capsys.readouterr().err


def test_project_loading_and_budgets(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"\0\xff")
    (tmp_path / ".env").write_text("secret")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("excluded")
    assert load_project(tmp_path, ClientBudgets()) == {"a.bin": b"\0\xff"}
    assert len(load_project(tmp_path, ClientBudgets(), include_excluded=True)) == 3
    with pytest.raises(ConfigurationError):
        load_project(tmp_path / ".env", ClientBudgets())
    with pytest.raises(ClientLimitExceededError):
        load_project(tmp_path, ClientBudgets(input_bytes=1))
    (tmp_path / "b").touch()
    with pytest.raises(ClientLimitExceededError):
        load_project(tmp_path, ClientBudgets(input_files=1))
    with pytest.raises(ConfigurationError):
        load_project(tmp_path / "absent", ClientBudgets())


def test_artifact_no_overwrite(tmp_path: Path) -> None:
    file = ArtifactFile(path="out/data.bin", data=b"\xff")
    path = save_artifact(tmp_path, file)
    assert path.read_bytes() == b"\xff"
    with pytest.raises(FileExistsError):
        save_artifact(tmp_path, file)


@pytest.mark.skipif(os.name != "nt", reason="Windows destination semantics")
@pytest.mark.parametrize("name", ["NUL", "con.txt", "sub/COM1.bin", "normal.txt.", "dir /file", "bad*file"])
def test_windows_artifact_names_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigurationError, match="Windows name"):
        save_artifact(tmp_path, ArtifactFile(path=name, data=b"must survive"))
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows destination semantics")
def test_windows_output_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Windows name"):
        save_artifact(tmp_path / "NUL", ArtifactFile(path="file", data=b"data"))


def test_token_requires_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_GJ_TOKEN", "synthetic")
    assert token_from_env(None) is None
    token = token_from_env("TEST_GJ_TOKEN")
    assert token is not None and token.get_secret_value() == "synthetic"
    with pytest.raises(ConfigurationError):
        token_from_env("MISSING_GJ_TEST_TOKEN")


def test_cli_errors_are_concise(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("private-source")
    result = runner.invoke(app, ["run", str(tmp_path)])
    assert result.exit_code == 2 and "private-source" not in result.output
    result = runner.invoke(app, ["check", "--target", "127.0.0.1:1", "--insecure", "--timeout", "0.01"])
    assert result.exit_code == 2


def test_project_symlink_policy(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "sub").mkdir(parents=True)
    (real / "sub" / "main.py").write_bytes(b"source")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            pytest.skip("Creating Windows symlinks requires Developer Mode or elevation")
        raise
    with pytest.raises(ConfigurationError):
        load_project(alias, ClientBudgets())
    assert load_project(alias / "sub", ClientBudgets()) == {"main.py": b"source"}
    (real / "file-link").symlink_to(real / "sub" / "main.py")
    (real / "dir-link").symlink_to(real / "sub", target_is_directory=True)
    assert load_project(real, ClientBudgets()) == {"sub/main.py": b"source"}


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_project_junction_policy(tmp_path: Path) -> None:
    import subprocess

    real = tmp_path / "real"
    real.mkdir()
    (real / "main.py").write_bytes(b"source")
    junction = tmp_path / "junction"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(real)], check=True, capture_output=True)
    try:
        with pytest.raises(ConfigurationError):
            load_project(junction, ClientBudgets())
        assert load_project(tmp_path, ClientBudgets()) == {"real/main.py": b"source"}
    finally:
        junction.rmdir()


def test_output_directory_is_not_resubmitted(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_bytes(b"source")
    output = tmp_path / "custom-output"
    output.mkdir()
    (output / "artifact").write_bytes(b"old output")
    assert load_project(tmp_path, ClientBudgets(), output_dir=output, include_excluded=True) == {"main.py": b"source"}
    with pytest.raises(ConfigurationError, match="outside"):
        load_project(tmp_path, ClientBudgets(), output_dir=tmp_path)


def test_errors_distinguish_causes_without_values(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from go_judge_client import ExecutionRequest
    from go_judge_client.cli._app import error_message

    source = tmp_path / "main.py"
    source.write_text("private-source")
    missing_command = runner.invoke(app, ["run", str(source)])
    missing_file = runner.invoke(app, ["run", str(tmp_path / "missing"), "--command", "run"])
    unknown_runtime = runner.invoke(app, ["run", str(source), "--runtime", "unknown"])
    assert "--runtime and --command" in missing_command.output
    assert "not found" in missing_file.output
    assert "UnknownRuntimeError" in unknown_runtime.output
    assert all(result.exit_code == 2 for result in (missing_command, missing_file, unknown_runtime))
    with pytest.raises(ValidationError) as caught:
        ExecutionRequest.model_validate({"command": ["run"], "env": {"private-key": 123}, "private-extra": "secret"})
    message = error_message(caught.value)
    assert "env: expected a string" in message
    assert "private" not in message and "secret" not in message and "123" not in message
    assert "already exists" in error_message(FileExistsError("secret filename"))


@pytest.mark.parametrize(
    ("error_type", "label"),
    [
        ("AuthenticationError", "AuthenticationError"),
        ("PermissionDeniedError", "PermissionDeniedError"),
        ("ConnectionError", "ConnectionError"),
        ("ExecutionDeadlineExceeded", "ExecutionDeadlineExceeded"),
        ("ClientLimitExceededError", "ClientLimitExceededError"),
    ],
)
def test_sdk_error_categories_hide_exception_causes(error_type: str, label: str) -> None:
    import go_judge_client
    from go_judge_client.cli._app import error_message

    error = getattr(go_judge_client, error_type)("Safe local message")
    error.__cause__ = RuntimeError("private-remote-details")
    assert error_message(error) == f"{label}: Safe local message"


def test_cli_direct_argv_and_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from go_judge_client import AsyncGoJudgeClient, Execution, ExecutionRequest
    from go_judge_client.cli import _app

    captured: list[tuple[ExecutionRequest, str, bool]] = []

    class RecordingClient(AsyncGoJudgeClient):
        async def start(self) -> None:
            pass

        def stream(
            self, request: ExecutionRequest, *, timeout_seconds: float | None = None, capture_output: bool = True
        ) -> Execution:
            captured.append((request, self._config.target, self._config.insecure))
            raise ConfigurationError("Recorded without executing")

    monkeypatch.setattr(_app, "AsyncGoJudgeClient", RecordingClient)
    monkeypatch.setenv("GJ_TARGET", "example.invalid:5051")
    monkeypatch.setenv("GJ_INSECURE", "true")
    monkeypatch.setenv("GJ_RUNTIME", "python")
    profiles = tmp_path / "runtimes.toml"
    profiles.write_text('[runtimes.python]\ncommand=["python"]')
    monkeypatch.setenv("GJ_PROFILES", str(profiles))
    source = tmp_path / "main.py"
    source.write_text("print('hello')")
    result = runner.invoke(app, ["run", str(source), "--", "python", "-u", "main.py", "--target", "literal"])
    assert "Recorded" in result.output
    request, target, insecure = captured[-1]
    assert request.command == ("python", "-u", "main.py", "--target", "literal")
    assert request.runtime is None and target == "example.invalid:5051" and insecure
    result = runner.invoke(app, ["run", str(source), "--target", "override:1", "--no-insecure"])
    assert "Recorded" in result.output
    request, target, insecure = captured[-1]
    assert request.runtime == "python" and target == "override:1" and not insecure
    result = runner.invoke(app, ["run", str(source), "--command", "python", "--command=-u", "--command", "main.py"])
    assert "Recorded" in result.output and captured[-1][0].command == ("python", "-u", "main.py")
    for arguments in [
        ["--runtime", "python", "--", "python"],
        ["--command", "python", "--", "python"],
    ]:
        before = len(captured)
        result = runner.invoke(app, ["run", str(source), *arguments])
        assert result.exit_code == 2 and len(captured) == before
    assert runner.invoke(app, ["profiles"]).stdout.strip() == "python"


def test_nested_profile_diagnostics_hide_names_and_values(tmp_path: Path) -> None:
    profile = tmp_path / "profiles.toml"
    profile.write_text('[runtimes.private-name]\ncommand=["python"]\n[runtimes.private-name.limits]\nmemory_bytes=-731')
    result = runner.invoke(app, ["profiles", "--profiles", str(profile)])
    assert result.exit_code == 2
    assert "runtimes.limits.memory_bytes: must be greater than zero" in result.output
    assert "private-name" not in result.output and "731" not in result.output


def test_artifact_overwrite_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    original_replace = os.replace

    def observe_replace(source: str | Path, destination: str | Path) -> None:
        assert target.read_bytes() == b"old"
        assert Path(source).read_bytes() == b"new"
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", observe_replace)
    assert save_artifact(tmp_path, ArtifactFile(path="out.bin", data=b"new"), overwrite=True) == target
    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_artifact_overwrite_failure_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("replacement failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        save_artifact(tmp_path, ArtifactFile(path="out.bin", data=b"new"), overwrite=True)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_artifact_overwrite_rejects_links_and_directories(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.write_bytes(b"preserved")
    (tmp_path / "link").symlink_to(original)
    (tmp_path / "directory").mkdir()
    for name in ("link", "directory"):
        with pytest.raises(ConfigurationError):
            save_artifact(tmp_path, ArtifactFile(path=name, data=b"new"), overwrite=True)
    assert original.read_bytes() == b"preserved"
    saved = save_artifact(tmp_path, ArtifactFile(path="new/file", data=b"new"), overwrite=True)
    assert saved.read_bytes() == b"new"


@pytest.mark.parametrize(
    ("data", "code", "explanation"),
    [
        ({"command": []}, "gj_command", "nonempty executable"),
        ({"runtime": "PRIVATE_RUNTIME"}, "gj_runtime_name", "lowercase runtime name"),
        ({"runtime": "python", "entrypoint": "../private-path"}, "gj_path", "relative POSIX path"),
        ({"runtime": "python", "command": ["private-command"]}, "gj_execution_mode", "exactly one"),
        ({"command": ["run"], "limits": {"cpu_seconds": "private-value"}}, "gj_number", "numeric value"),
        ({"command": ["run"], "limits": {"memory_bytes": 1.5}}, "int_type", "expected an integer"),
    ],
)
def test_actionable_validation_without_values(data: dict[str, object], code: str, explanation: str) -> None:
    from pydantic import ValidationError

    from go_judge_client import ExecutionRequest
    from go_judge_client.cli._app import error_message

    with pytest.raises(ValidationError) as caught:
        ExecutionRequest.model_validate(data)
    assert caught.value.errors()[0]["type"] == code
    message = error_message(caught.value)
    assert explanation in message
    assert "private" not in message.lower()
    assert "invalid value" not in message


def test_unknown_validation_code_uses_safe_fallback() -> None:
    from pydantic import BaseModel, ValidationError, field_validator
    from pydantic_core import PydanticCustomError

    from go_judge_client.cli._app import error_message

    class FutureModel(BaseModel):
        field: str

        @field_validator("field")
        @classmethod
        def reject(cls, value: str) -> str:
            raise PydanticCustomError("future_code", "private value: {value}", {"value": value})

    with pytest.raises(ValidationError) as caught:
        FutureModel(field="private-secret")
    assert error_message(caught.value) == "Invalid configuration: configuration: invalid value."


def test_direct_validation_code_is_readable() -> None:
    from go_judge_client._validation import validation_error
    from go_judge_client.cli._app import error_message

    assert "Timeout must be finite and positive" in error_message(validation_error("timeout"))


@pytest.mark.parametrize("profiled", [False, True])
def test_cli_limits_and_budgets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profiled: bool) -> None:
    from go_judge_client import AsyncGoJudgeClient, Execution, ExecutionRequest
    from go_judge_client.cli import _app

    observed = []

    class RecordingClient(AsyncGoJudgeClient):
        async def start(self) -> None:
            pass

        def stream(
            self, request: ExecutionRequest, *, timeout_seconds: float | None = None, capture_output: bool = True
        ) -> Execution:
            observed.append((self.effective_limits(request), self.budgets, timeout_seconds))
            raise ConfigurationError("Recorded without executing")

    monkeypatch.setattr(_app, "AsyncGoJudgeClient", RecordingClient)
    source = tmp_path / "main.py"
    source.write_text("print('hello')")
    profiles = tmp_path / "runtimes.toml"
    profiles.write_text(
        '[runtimes.python]\ncommand=["python"]\n[runtimes.python.limits]\ncpu_seconds=1\nstack_bytes=123456'
    )
    mode = ["--profiles", str(profiles), "--runtime", "python"] if profiled else ["--command", "python"]
    result = runner.invoke(
        app,
        [
            "run",
            str(source),
            *mode,
            "--cpu-seconds",
            "60",
            "--wall-seconds",
            "120",
            "--memory-bytes",
            "2147483648",
            "--processes",
            "256",
            "--cpu-cores",
            "2",
            "--budget",
            "output_bytes=8388608",
            "--budget",
            "input_bytes=100",
            "--timeout",
            "180",
        ],
    )
    assert "Recorded" in result.output
    limits, budgets, timeout = observed[0]
    assert (limits.cpu_seconds, limits.wall_seconds, limits.memory_bytes) == (60, 120, 2147483648)
    assert (limits.processes, limits.cpu_cores, timeout) == (256, 2, 180)
    assert limits.stack_bytes == (123456 if profiled else 64 * 1024**2)
    assert (budgets.output_bytes, budgets.input_bytes) == (8388608, 100)
    observed.clear()
    result = runner.invoke(app, ["run", str(source), *mode, "--budget", "input_bytes=1"])
    assert result.exit_code == 2 and not observed


@pytest.mark.parametrize("value", ["unknown=1", "output_bytes=oops", "output_bytes=0", "output_bytes"])
def test_cli_invalid_budget(value: str, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(tmp_path), "--command", "true", "--budget", value])
    assert result.exit_code == 2
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("value", "expected"), [("1GiB", 1024**3), ("16MiB", 16 * 1024**2), ("1GB", 10**9), ("64", 64), ("2kib", 2048)]
)
def test_cli_size_units(value: str, expected: int) -> None:
    from go_judge_client.cli._app import parse_size

    assert parse_size(value) == expected


@pytest.mark.parametrize("value", ["1.5GiB", "-1", "nan", "1G", "secret"])
def test_cli_size_rejects_invalid(value: str) -> None:
    from go_judge_client.cli._app import parse_size

    with pytest.raises(ConfigurationError):
        parse_size(value)


def test_cli_clear_cpu_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from go_judge_client import AsyncGoJudgeClient, Execution, ExecutionRequest
    from go_judge_client.cli import _app

    observed = []

    class RecordingClient(AsyncGoJudgeClient):
        async def start(self) -> None:
            pass

        def stream(
            self, request: ExecutionRequest, *, timeout_seconds: float | None = None, capture_output: bool = True
        ) -> Execution:
            observed.append((self.effective_limits(request), self.budgets))
            raise ConfigurationError("Recorded")

    monkeypatch.setattr(_app, "AsyncGoJudgeClient", RecordingClient)
    source = tmp_path / "main.py"
    source.write_text("pass")
    profiles = tmp_path / "runtimes.toml"
    profiles.write_text('[runtimes.python]\ncommand=["python"]\n[runtimes.python.limits]\ncpu_cores=1')
    args = [
        "run",
        str(source),
        "--profiles",
        str(profiles),
        "--runtime",
        "python",
        "--memory-bytes",
        "1GiB",
        "--stack-bytes",
        "32MiB",
        "--budget",
        "output_bytes=4MiB",
    ]
    assert "Recorded" in runner.invoke(app, args).output
    assert observed[-1][0].cpu_cores == 1
    assert "Recorded" in runner.invoke(app, [*args, "--no-cpu-limit"]).output
    limits, budgets = observed[-1]
    assert limits.cpu_cores is None
    assert (limits.memory_bytes, limits.stack_bytes, budgets.output_bytes) == (1024**3, 32 * 1024**2, 4 * 1024**2)
    before = len(observed)
    assert runner.invoke(app, [*args, "--no-cpu-limit", "--cpu-cores", "2"]).exit_code == 2
    assert len(observed) == before
    result = runner.invoke(app, [*args, "--budget", "artifact_bytes=64MiB", "--budget", "artifacts_bytes=128MiB"])
    assert "Warning:" in result.output and "receive_message_bytes" in result.output
