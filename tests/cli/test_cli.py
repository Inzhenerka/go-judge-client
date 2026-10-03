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
