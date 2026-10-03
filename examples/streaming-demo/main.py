"""A short, visibly incremental stdout/stderr demonstration."""

import sys
import time
from itertools import count


def main() -> None:
    started = time.monotonic()
    sequence = count(1)

    def emit(message: str, *, stderr: bool = False) -> None:
        destination = sys.stderr if stderr else sys.stdout
        name = "stderr" if stderr else "stdout"
        elapsed = time.monotonic() - started
        print(f"{next(sequence):02d} | +{elapsed:5.2f}s | {name} | {message}", file=destination, flush=True)

    emit("STREAMING DEMO -- new lines should appear while the program is running")
    emit("Ten steps, a deliberate quiet pause, and two stderr messages. About 7 seconds.")

    for step in range(1, 11):
        time.sleep(0.5)
        bar = "#" * (step * 2) + "." * ((10 - step) * 2)
        emit(f"[{bar}] {step * 10:3d}% -- completed step {step:02d}/10")
        if step == 3:
            emit("Diagnostic checkpoint: stderr is live too; this is not an error.", stderr=True)
        if step == 5:
            emit("Quiet for 1.5 seconds now -- the process is still running...")
            time.sleep(1.5)
            emit("Resuming after the quiet pause.")
        if step == 8:
            emit("Diagnostic checkpoint: two steps remain.", stderr=True)

    emit("DONE -- if you saw the progress gradually, streaming worked.")


if __name__ == "__main__":
    main()
