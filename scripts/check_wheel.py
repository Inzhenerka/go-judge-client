"""Install the built wheel outside the checkout, with and without the optional CLI."""

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wheel = next((ROOT / "dist").glob("*.whl"))
sdist = next((ROOT / "dist").glob("*.tar.gz"))
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    assert any(name.endswith("py.typed") for name in names)
    assert any(name.endswith("go_features_pb2.py") for name in names)
    assert any("licenses/proto/LICENSE" in name for name in names)
    assert not any(".research" in name or "fixtures" in name or "pumproom_api" in name for name in names)
with tarfile.open(sdist) as archive:
    names = archive.getnames()
    assert any(name.endswith("proto/judge.proto") for name in names)
    assert not any(".research/" in name or ".venv/" in name for name in names)

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    environment = root / "venv"
    subprocess.run(["uv", "venv", str(environment), "--python", sys.executable], check=True, cwd=root)
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True, cwd=root)
    subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.util, pickle; import go_judge_client; "
            "from go_judge_client._grpc import judge_pb2, request_pb2; "
            "assert importlib.util.find_spec('typer') is None; "
            "assert pickle.loads(pickle.dumps(request_pb2.Request())).ByteSize() == 0; "
            "assert judge_pb2.DESCRIPTOR.services_by_name['Executor'].full_name == 'pb.Executor'",
        ],
        check=True,
        cwd=root,
    )
    for command in ("gj", "go-judge-client"):
        executable = scripts / (command + (".exe" if os.name == "nt" else ""))
        result = subprocess.run([str(executable), "--help"], capture_output=True, text=True, cwd=root)
        assert result.returncode == 2 and "go-judge-client[cli]" in result.stderr and "Traceback" not in result.stderr
    subprocess.run(["uv", "pip", "install", "--python", str(python), f"{wheel}[cli]"], check=True, cwd=root)
    for command in ("gj", "go-judge-client"):
        executable = scripts / (command + (".exe" if os.name == "nt" else ""))
        result = subprocess.run([str(executable), "--help"], capture_output=True, text=True, cwd=root)
        assert result.returncode == 0 and "profiles" in result.stdout
print("Clean wheel, core-only imports, optional CLI and both aliases verified.")
