"""Outer watchdog independent of RPC deadlines; never silently skip integration."""

import subprocess
import sys

try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration", "-m", "integration", "-q"], timeout=90
    )
except subprocess.TimeoutExpired:
    raise SystemExit("Integration watchdog expired after 90 seconds") from None
raise SystemExit(result.returncode)
