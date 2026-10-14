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
    assert "env: invalid value" in message
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
