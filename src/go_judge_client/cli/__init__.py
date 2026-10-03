"""Optional CLI entry point: importing the library never imports Typer."""

import sys


def main() -> None:
    try:
        from ._app import app
    except ModuleNotFoundError as error:
        if error.name != "typer":
            raise
        print('CLI support is not installed.\nInstall it with: uv add "go-judge-client[cli]"', file=sys.stderr)
        raise SystemExit(2) from None
    app()
