"""Ensure checked-in generated files match the pinned compiler output."""

import hashlib
import json
import tempfile
from pathlib import Path

from generate_proto import DEST, ROOT, generate

manifest = json.loads((ROOT / "proto/checksums.json").read_text())
for name, digest in manifest.items():
    assert hashlib.sha256((ROOT / "proto" / name).read_bytes()).hexdigest() == digest, name
with tempfile.TemporaryDirectory() as temporary:
    out = Path(temporary)
    generate(out)
    for path in out.iterdir():
        assert path.read_bytes() == (DEST / path.name).read_bytes(), path.name
print("Protocol checksums and generated bindings match.")
