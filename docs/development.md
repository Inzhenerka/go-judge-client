# Development

For a local server, first build the runtime image, then run the foreground task:

```sh
docker build -t go-judge-client-test:1.13.3 -f examples/runtime-image/Dockerfile .
```

Release integration requires native Linux amd64. The current pinned server fails functional acceptance
on ARM64 Docker Desktop, and amd64 emulation there fails seccomp initialization. These failures do not
prevent using the Python SDK from an ARM64 client connected to a compatible remote server. See the
[current verification record](compatibility.md#current-checkout-verification-2026-10-14).

Start the server:

```sh
uv run poe judge
```

This foreground task uses the locally built `go-judge-client-test:1.13.3` image, binds gRPC only to
`127.0.0.1:15051`, and enables no authentication token. Stop it with `Ctrl+C`; Docker then removes the
container because the command uses `--rm`.

```sh
uv sync --locked
uv run poe check
uv run pytest tests/unit tests/transport tests/typing tests/cli --cov --cov-report=term-missing
uv run poe check-proto
uv build
```

`poe check` does not modify files. `poe prep` formats then checks; `poe fix` applies Ruff fixes.
Dependency upgrades are explicit (`poe outdated`, `poe upgrade`). CI covers Linux on Python 3.12–3.14;
Windows is not a supported target or a release gate. See the
compatibility report for observed versions. Comments, docs, examples and error messages are English.

Protobuf is generated with `grpcio-tools==1.84.0`, using Edition 2023 sources and the vendored Go feature
descriptor. Run `poe generate-proto` to regenerate. Only generated Python import/module paths are
adapted; protobuf package names, descriptors, service paths and wire fields remain unchanged. `.pyi`
and runtime modules are committed. Neither protoc nor Go is needed by package consumers. `check-proto`
verifies source hashes, the complete generated file set and generated-file byte reproducibility.
Git attributes keep text files in LF form on every platform; schema hashes use those committed bytes. Generated modules remain private.

Core tests enforce at least 90% line coverage; generated bindings and CLI are excluded from that core
metric. CLI has separate functional tests. Critical cancellation and protocol branches have explicit tests.
The type checker includes handwritten source, tests and examples; only generated/vendor directories are
excluded. Consumer fixtures use `assert_type` against exported APIs.

## Execution architecture

`AsyncGoJudgeClient` owns the channel, both RPC callables, and one local semaphore. Its active-operation
registry includes both transports so shutdown stops queued and active work consistently.

- `_operation.Operation` owns request snapshots, local admission, the end-to-end deadline, error
  normalization, and bounded cleanup. Transport hooks submit, cancel, drain, and release RPC resources.
- `_unary.UnaryExecution` submits `Exec` and awaits its final response. It has no event iterator or
  streaming buffers. `execute()` awaits it directly inside the shared operation context.
- `execution.Execution` submits `ExecStream`, owns the finite sender, and exposes the public byte/text
  event iterator. It validates terminal status before publishing the final result.

The mapping layer shares command construction and final-result validation while providing distinct
unary-collector and streaming-descriptor builders. There is no transport-mode switch in operation
ownership. New transport behavior should preserve shared lifecycle guarantees and add its own protocol
tests; interactive stdin/TTY is not implemented by this split.

## Real-server functional acceptance

Use a disposable Linux Docker environment. The example builds one Python runtime without installing
dependencies at execution time. Pin and review all images before production use.

```sh
docker build -t go-judge-client-test:1.13.3 -f examples/runtime-image/Dockerfile .
docker run -d --name gj-client-acceptance --label go-judge-client.test=true --privileged --cgroupns=host \
  --memory 512m --cpus 1 -p 127.0.0.1:15051:5051 go-judge-client-test:1.13.3 \
  -enable-grpc -grpc-addr :5051 -http-addr 127.0.0.1:5050 \
  -auth-token gj-local-test-only -no-fallback -parallelism 1 -pre-fork 1
GO_JUDGE_TEST_TARGET=127.0.0.1:15051 uv run poe test-integration
docker rm -f gj-client-acceptance
```

PowerShell: `$env:GO_JUDGE_TEST_TARGET='127.0.0.1:15051'` before invoking the test command.
An optional `GO_JUDGE_TEST_TOKEN` overrides the synthetic token. Set `GO_JUDGE_TEST_PARALLELISM`
to the server's actual `-parallelism` value (default 1). The concurrency regression opens independent
clients and compares execution intervals measured inside jobs for `execute()` and `stream()`. Integration fails if no target is set;
missing infrastructure is not a silent pass. The outer 90-second watchdog is independent of RPC deadlines.
These are benign functional checks; no hostile workloads or memory/process stress tests are run on shared hosts.

`-no-fallback` makes cgroup setup failure explicit. On the tested Docker Desktop host, a private cgroup
namespace produced `cgroup path is empty`; `--cgroupns=host` allowed nested cgroup v2 creation.
Do not solve that by disabling isolation or mounting the Docker socket into workloads.

Trusted image-build root is not student root. Installed runtimes/shared caches should be read-only;
project files, outputs and writable caches belong to each execution workspace. Keep library and symlink
targets visible in reviewed directories; do not expose all of `/etc`, `/run` or application directories to
fix imports. Adding dependencies needs its own vulnerability review. Profiles are not a security audit,
and the normal privileged deployment requirements remain. Different tool/egress inventories may require
separate deployments; the SDK cannot dynamically switch images.

## Release automation

Use Conventional Commits; versioning, changelog, GitHub Releases and optional PyPI publication are
managed by CI. See [releases](releases.md) for the one-time publisher setup and retry procedure.
