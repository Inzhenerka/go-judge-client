"""Reject ambiguous or stale build output before attempting installation."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filenames",
    [
        [],
        ["go_judge_client-0.1.0-py3-none-any.whl"],
        [
            "go_judge_client-0.1.0-py3-none-any.whl",
            "go_judge_client-999.0.0-py3-none-any.whl",
            "go_judge_client-0.1.0.tar.gz",
        ],
        ["go_judge_client-0.1.0-py3-none-any.whl", "go_judge_client-0.2.0.tar.gz"],
    ],
)
def test_rejects_invalid_distribution_selection(tmp_path: Path, filenames: list[str]) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/check_wheel.py", scripts / "check_wheel.py")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "go-judge-client"\nversion = "0.1.0"\n')
    dist = tmp_path / "dist"
    dist.mkdir()
    for filename in filenames:
        (dist / filename).write_bytes(b"not a distribution")
    result = subprocess.run(
        [sys.executable, str(scripts / "check_wheel.py")], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode != 0
    assert "clean dist/ and rebuild" in result.stderr
    assert "Traceback" not in result.stderr
