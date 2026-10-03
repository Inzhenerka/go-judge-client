# Development

For a quick local server on Windows, macOS or Linux with Docker Desktop/Linux containers, run:

```sh
uv run poe judge
```

This foreground task uses the locally built `go-judge-client-test:e9d70a0` image, binds gRPC only to
`127.0.0.1:15051`, and enables no authentication token. Stop it with `Ctrl+C`; Docker then removes the
container because the command uses `--rm`. Build the image first with the command below if it is absent.

```sh
uv sync --locked
uv run poe check
uv run pytest tests/unit tests/transport tests/typing tests/cli --cov --cov-report=term-missing
uv run poe check-proto
uv build
```

`poe check` does not modify files. `poe prep` formats then checks; `poe fix` applies Ruff fixes.
Dependency upgrades are explicit (`poe outdated`, `poe upgrade`). Python support is 3.12–3.14; see the
compatibility report for observed versions. Comments, docs, examples and error messages are English.

Protobuf is generated with `grpcio-tools==1.78.0`, using Edition 2023 sources and the vendored Go feature
descriptor. Run `poe generate-proto` to regenerate. Only generated Python import/module paths are
adapted; protobuf package names, descriptors, service paths and wire fields remain unchanged. `.pyi`
and runtime modules are committed. Neither protoc nor Go is needed by package consumers. `check-proto`
verifies source hashes and generated-file byte reproducibility. Generated modules remain private.

Core tests enforce at least 90% line coverage; generated bindings and CLI are excluded from that core
metric. CLI has separate functional tests. Critical cancellation and protocol branches have explicit tests.
The type checker includes handwritten source, tests and examples; only generated/vendor directories are
excluded. Consumer fixtures use `assert_type` against exported APIs.

## Real-server functional acceptance

Use a disposable Linux Docker environment. The example builds one Python runtime without installing
dependencies at execution time. Pin and review all images before production use.

```sh
docker build -t go-judge-client-test:e9d70a0 -f examples/runtime-image/Dockerfile .
docker run -d --name gj-client-acceptance --label go-judge-client.test=true --privileged --cgroupns=host \
  --memory 512m --cpus 1 -p 127.0.0.1:15051:5051 go-judge-client-test:e9d70a0 \
  -enable-grpc -grpc-addr :5051 -http-addr 127.0.0.1:5050 \
  -auth-token gj-local-test-only -no-fallback -parallelism 1 -pre-fork 1
GO_JUDGE_TEST_TARGET=127.0.0.1:15051 uv run poe test-integration
docker rm -f gj-client-acceptance
```

PowerShell: `$env:GO_JUDGE_TEST_TARGET='127.0.0.1:15051'` before invoking the test command.
An optional `GO_JUDGE_TEST_TOKEN` overrides the synthetic token. Integration fails if no target is set;
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
separate deployments; P0 cannot dynamically switch images.
