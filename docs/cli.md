# CLI

## Watch streaming in real time

`examples/streaming-demo/main.py` runs for about seven seconds, emitting numbered, timestamped
progress lines every half second, two stderr diagnostics and a deliberate quiet pause. Every line
is flushed immediately. It needs no input or output artifacts:

```sh
export GJ_TOKEN='gj-local-test-only'
uv run gj run examples/streaming-demo --profiles examples/runtimes.toml --runtime python-data --target localhost:15051 --insecure --token-env GJ_TOKEN
```

Use the local test container described in `development.md`, or adjust the target/token for your server.
Sequence numbers show the program's write order; stdout and stderr travel separately, so their merged
terminal order is not guaranteed. Progress should appear during execution, before the final CLI status.

## Commands

Install the `cli` extra for deployed use. Development `uv sync` includes Typer for CLI tests. Both
`go-judge-client` and `gj` invoke exactly the same function. A core-only installation prints a concise
installation hint and exits 2 when either CLI is invoked; importing the library does not import Typer.

```sh
gj profiles --profiles examples/runtimes.toml
gj check --target localhost:5051 --insecure --timeout 5
gj run examples/python-data --profiles examples/runtimes.toml --runtime python-data \
  --expect output/result.bin --optional-expect debug.txt --output-dir gj-output --insecure
gj run ./main.py --insecure -- /usr/local/bin/python -u main.py
```

Pass a direct command after `--`; all following arguments are literal, with no shell expansion by the CLI.
The older repeated `--command` syntax remains supported; use `--command=-x` for flag arguments.
Do not combine the two forms or an explicit `--runtime` with a direct command.

Connection and profile defaults can come from the environment:

```sh
export GJ_TARGET=localhost:15051
export GJ_INSECURE=true
export GJ_PROFILES=examples/runtimes.toml
export GJ_RUNTIME=python-data
uv run gj run examples/python-data
```

Explicit options override environment defaults. A direct command overrides `GJ_RUNTIME`.
`GJ_TOKEN_ENV` names the variable containing a token, for example `GJ_TOKEN_ENV=MY_JUDGE_TOKEN`;
the token itself is read from `MY_JUDGE_TOKEN`. `GJ_TARGET`, `GJ_INSECURE` and `GJ_TOKEN_ENV`
also apply to `check`; `GJ_PROFILES` also applies to `profiles`. `--no-insecure` explicitly enables TLS.

Validation messages show known field paths and safe rules (for example, a nonempty command,
a relative POSIX path, or a positive integer limit). Custom validation codes are mapped to fixed
explanations; unknown codes retain the generic `invalid value` fallback. Messages never include submitted values or dynamic runtime,
environment or file names.
Profile arguments use repeatable `--arg`. `--entrypoint` overrides the profile default. For a single local
file the profile entrypoint defaults explicitly to its basename. Direct commands must name their files
themselves. `--stdin-file` reads bounded binary stdin. `--timeout` covers admission and execution.

The project loader accepts a regular file or recursively reads a directory. The source itself must not be a
symlink/junction. Ancestor aliases are resolved once to establish the canonical source; symlinks/junctions
inside a directory project are skipped. The loader excludes `.git`, `.venv`, `node_modules`, `__pycache__`, and `.env` by default.
`--include-excluded` explicitly includes those names. The selected output directory is always excluded
when nested inside the project, including with `--include-excluded`. A source inside the output directory
is rejected; inspect contents before using it. No filesystem
filter can detect every possible secret filename. Use a stable directory not concurrently modified by
untrusted processes. Files remain bytes and use the same input/path budgets as the SDK.

`--token-env NAME` explicitly reads the named environment variable in the CLI; no token is inferred by
the core SDK. Prefer TLS for remote targets; omit `--insecure`. Custom roots/mTLS are available through
the Python API. Errors distinguish configuration, authentication, transport, budgets and local file failures.
Validation messages name known field paths without printing their values or dynamic dictionary keys.
Environment values, token contents and transport metadata are not included in CLI errors.

Live output uses separate incremental UTF-8 decoders with replacement for undecodable bytes. Raw SDK
events remain lossless. Existing artifact files cause an error by default. Pass `--overwrite` to replace regular files atomically:
each file is staged in its destination directory before replacement. Symlinks, junctions and non-regular
destinations remain forbidden. A write or replacement failure preserves the previous file and removes
the temporary file. Replacement uses a new private file rather than preserving the old permissions.
Atomicity applies per file, not to the entire set of artifacts. Use a private, stable output directory.
The final line reports normalized status, exit status, CPU/elapsed seconds and memory bytes. Missing paths
are reported as not received. No shell, browser, local listener or implicit retry is introduced.

Exit statuses: 0 for accepted execution with required artifacts satisfied; 1 for program/artifact failure;
2 for configuration, connection, protocol or local file errors; 130 for Ctrl+C after local cancellation.
`profiles` is local inspection. `check` proves only transport connectivity and never executes code.

## Execution limits and client budgets

Use `--cpu-seconds`, `--wall-seconds`, `--memory-bytes`, `--stack-bytes`, `--processes`
(includes threads on Linux), and `--cpu-cores` to override individual execution limits.
These work with direct commands and profiles; explicit options override profile values,
while omitted options inherit them. `--timeout` is an independent deadline for the entire
operation including queues; increasing it does not increase CPU or wall limits.

Use repeatable `--budget NAME=VALUE` for any `ClientBudgets` field. Byte budgets use bytes;
count budgets use counts. Budgets apply before local file loading and during execution.
For example, allow 60 CPU seconds, 120 wall seconds and 16 MiB of combined output:

```sh
gj run ./main.py --insecure --cpu-seconds 60 --wall-seconds 120 --timeout 180 \
  --budget output_bytes=16777216 -- /usr/local/bin/python -u main.py
```

The default 2 MiB output budget also applies to live output with capture disabled. Exceeding
it cancels execution; increase `output_bytes` for verbose programs. When increasing file
budgets, also size `send_message_bytes` and `receive_message_bytes` for protobuf overhead.

Byte options also accept integer sizes: `--memory-bytes 1GiB`, `--stack-bytes 64MiB`,
`--budget output_bytes=16MiB`. IEC units (KiB/MiB/GiB/TiB) use powers of 1024;
SI units (KB/MB/GB/TB) use powers of 1000. Units are case-insensitive; fractional
sizes are not supported. Count budgets still require integers.

`--no-cpu-limit` clears an inherited CPU **rate** limit (`cpu_cores`); CPU time and
wall time limits still apply. It cannot be combined with `--cpu-cores`.

The CLI warns when file/output budgets can exceed transport caps or an individual
artifact cap exceeds the aggregate cap. It does not silently raise limits. SDK callers
can inspect the same warnings with `budgets.configuration_warnings()`. These checks
identify potential conflicts, not exact protobuf sizes; actual send/receive checks remain active.
