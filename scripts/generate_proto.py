"""Generate pinned Edition 2023 bindings, adapting only Python module imports."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/go_judge_client/_grpc"


def generate(destination: Path) -> None:
    import grpc_tools

    includes = Path(grpc_tools.__file__).parent / "_proto"
    with tempfile.TemporaryDirectory() as temporary:
        out = Path(temporary)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{ROOT / 'proto'}",
                f"-I{includes}",
                f"--python_out={out}",
                f"--pyi_out={out}",
                f"--grpc_python_out={out}",
                *[str(p) for p in sorted((ROOT / "proto").glob("*.proto"))],
                str(ROOT / "proto/google/protobuf/go_features.proto"),
            ],
            check=True,
        )
        destination.mkdir(parents=True, exist_ok=True)
        for source in out.rglob("*"):
            if source.suffix not in {".py", ".pyi"}:
                continue
            text = source.read_text(encoding="utf-8")
            text = re.sub(r"^import (\w+_pb2) as", r"from . import \1 as", text, flags=re.MULTILINE)
            text = text.replace("from google.protobuf import go_features_pb2", "from . import go_features_pb2")
            # Generated classes must be importable/pickleable under their installed name.
            text = re.sub(
                r"(BuildTopDescriptorsAndMessages\(DESCRIPTOR, )'([^']+)'",
                lambda m: m[1] + repr("go_judge_client._grpc." + m[2].split(".")[-1]),
                text,
            )
            (destination / source.name).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    generate(DEST)
