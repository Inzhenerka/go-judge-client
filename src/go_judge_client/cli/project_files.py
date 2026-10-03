"""Bounded local project loading and exclusive artifact writes."""

import os
import stat
import sys
from pathlib import Path

if sys.version_info >= (3, 13):
    from ntpath import isreserved as _windows_reserved
else:
    from pathlib import PureWindowsPath

    def _windows_reserved(path: str) -> bool:
        return PureWindowsPath(path).is_reserved()


from .. import ArtifactFile, ClientBudgets, ClientLimitExceededError, ConfigurationError
from ..models import project_path

EXCLUDED = frozenset({".git", ".venv", "node_modules", "__pycache__", ".env"})


def load_project(path: Path, budgets: ClientBudgets, *, include_excluded: bool = False) -> dict[str, bytes]:
    if path.is_symlink() or path.is_junction():
        raise ConfigurationError("Project source cannot be a symlink or junction")
    root = path if path.is_dir() else path.parent
    paths: list[Path] = []
    if path.is_file():
        paths.append(path)
    elif path.is_dir():
        for parent, directories, filenames in os.walk(path, followlinks=False):
            directories[:] = sorted(
                d
                for d in directories
                if (include_excluded or d not in EXCLUDED)
                and not (Path(parent) / d).is_symlink()
                and not (Path(parent) / d).is_junction()
            )
            for name in sorted(filenames):
                child = Path(parent) / name
                if (include_excluded or name not in EXCLUDED) and not child.is_symlink() and child.is_file():
                    paths.append(child)
                    if len(paths) > budgets.input_files:
                        raise ClientLimitExceededError("Input file count exceeded")
    else:
        raise ConfigurationError("Project source must be a regular file or directory")
    result: dict[str, bytes] = {}
    total = 0
    for file in paths:
        if not include_excluded and file.name in EXCLUDED:
            raise ConfigurationError("Explicitly enable --include-excluded to submit excluded files")
        name = project_path(file.relative_to(root).as_posix())
        if len(name.encode()) > budgets.path_bytes or len(name.split("/")) > budgets.path_depth:
            raise ClientLimitExceededError("Project path budget exceeded")
        if file.is_symlink() or not stat.S_ISREG(file.stat().st_mode):
            raise ConfigurationError("Project file changed during loading")
        with file.open("rb") as stream:
            content = stream.read(budgets.input_bytes - total + 1)
        total += len(content)
        if total > budgets.input_bytes:
            raise ClientLimitExceededError("Input content budget exceeded")
        result[name] = content
    return result


def save_artifact(root: Path, artifact: ArtifactFile) -> Path:
    project_path(artifact.path)
    target = root / artifact.path
    if os.name == "nt" and any(
        part.endswith((" ", "."))
        or _windows_reserved(part)
        or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
        for part in target.absolute().parts[1:]
        if part not in {".", ".."}
    ):
        raise ConfigurationError("Artifact destination contains an unsupported Windows name")
    # Refuse any pre-existing symlink component, including the output directory.
    for parent in (*target.parents, target):
        if parent.is_symlink() or parent.is_junction():
            raise ConfigurationError("Artifact destination contains a symlink or junction")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(artifact.data)
    return target
