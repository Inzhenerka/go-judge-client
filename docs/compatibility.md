# Compatibility and implementation evidence

Recorded 2026-09-28. This is a local pre-publication implementation, not a production deployment or
a certification of arbitrary go-judge images. No package was published and no remote repository was written.

## Pins

| Component | Verified value |
|---|---|
| go-judge source/protobuf | `e9d70a0d9a3df0c62182a6e7090d7af650a1d5f8` |
| Upstream HEAD at implementation start | Same commit |
| Locally built server image ID | `sha256:e188567b1c162a890cf5725b0a467e99460ac14559d83075bb2ee47810b99ef1` |
| Go build base | `golang:1.26.1-bookworm@sha256:ab3d6955bbc813a0f3fdf220c1d817dd89c0b3f283777db8ece4a32fe7858edd` |
| Python runtime base | `python:3.13-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b` |
| Go feature schema | protobuf-go `v1.36.11` |
| Generator | `grpcio-tools==1.78.0` (Edition 2023 capable) |
| Windows interpreters | CPython 3.12.11, 3.13.7, 3.14.3 |
| Linux test/runtime interpreter | CPython 3.13.15 |
| Locked runtime | grpcio 1.84.0, protobuf 6.33.6, Pydantic 2.13.5 |
| Minimum dependency test | grpcio 1.78.0, protobuf 6.33.5, Pydantic 2.12.0, Typer 0.25.0 |
| Locked tools | uv 0.12.19, Ruff 0.16.9, ty 0.0.84, Poe 0.48.0, Typer 0.27.2 |
| Build | uv integrated backend, wheel metadata `Generator: uv 0.12.19`; declared uv_build range 0.11–0.12 |

The image ID is a local content ID, not a published registry manifest digest. No minimum released
go-judge version is claimed. The server was built from source, not inferred from a release tag.

PumpRoom practices were inspected at specification snapshot `a70cb207cca0149ecdc4b187dc5fabb30115b8d9`
from the local checkout: Pydantic boundaries, uv/Poe/Ruff conventions, explicit `aclose`, `AsyncExitStack`
and the submission/polling interface. Its current local HEAD differed; no production migration or current
application behavior is claimed. No private snapshot or business configuration is included in the package.

## Observed acceptance

- Unit, transport, typing and CLI suite: 81 tests; no required lifecycle skips. Handwritten core line coverage
  95.36%, enforced minimum 90%. Generated bindings and CLI are excluded from that core metric.
- Windows Python matrix: 3.12, 3.13 and 3.14 execute the same suite. Linux runs the installed wheel,
  transport/CLI suite and real integration suite in a separate container.
- Real server: 11 functional tests, including flushed live output, 256 KiB binary stdin, sibling-module
  imports, nested binary input, empty artifacts, required/optional missing paths, file-size rejection,
  nonzero exit, timeout-preserved artifacts, profile execution, isolated writable workspaces, read-only
  runtime path, finite CPU/memory/process-limit probes, and TCP interruption followed by a new successful request.
- A separate marked parent/child probe observed both processes disappear within three seconds of explicit
  cancellation, then verified a new successful execution. This is evidence on one host, not a distributed guarantee.
- Real Linux CLI SIGINT check: output observed before completion, cancellation returned exit 130 without traceback.
- TLS and mTLS succeed with explicit trust against a disposable gRPC fixture; default trust rejects its
  self-signed certificate. Real upstream integration uses explicit loopback plaintext with a synthetic bearer token.
- Missing/invalid bearer tokens fail even after readiness succeeds. Protected execution is never retried.
- Generated sources reproduce byte-for-byte; original schemas have SHA-256 checksums. Installed-wheel imports,
  generated descriptors, protobuf pickling and both console aliases pass outside the source checkout.
- Core-only wheel installs no Typer and emits a friendly extra-installation hint. Installing `[cli]` enables both aliases.
- Wheel and sdist build locally. Wheel includes `py.typed`, generated modules/typing and third-party licenses;
  sdist also includes source schemas, scripts, docs, examples and tests. No private research snapshots are packaged.

The Linux test host is Docker Desktop 4.80.0, Engine 29.6.1, kernel 6.18, cgroup v2. Available controllers:
`cpuset cpu io memory hugetlb pids rdma`. The disposable server used 512 MiB/one-CPU outer bounds,
`--privileged --cgroupns=host`, default seccomp, and `-no-fallback`. It was not rootless.

## Findings and limits

1. Private Docker cgroup namespaces failed server startup with `cgroup path is empty`. Using the documented
   host cgroup namespace allowed nested cgroups without enabling rlimit fallback.
2. The upstream logs its shared token at startup. This was verified using a synthetic token; server log
   redaction remains a deployment requirement. The SDK cannot fix upstream logs.
3. The tested collector rejected a workspace symlink during Open with `CopyOutOpen` and `not a regular file`.
   Do not extrapolate a universal no-follow guarantee to other revisions/mounts.
4. grpcio 1.78 lacks runtime generic subscription on its callable class. Type-only casts use string annotations;
   the minimum-stack test catches this compatibility issue. Typer 0.25 with current Click emits two upstream
   deprecation warnings; tests pass. The locked Typer version has no such warning in the verified run.
5. The in-process Python gRPC TLS server intermittently stalled in its own shutdown on Linux; a separate
   cache initially helped but did not reliably fix it. TLS tests now use a separately owned server process
   with a bounded shutdown watchdog, retaining real encrypted/authenticated RPCs and trust rejection.
   The root cause in the in-process server was not conclusively established.
   One early Windows run also showed a gRPC poller shutdown warning; the final warning-as-error run passed
   after clearing closed transport references. Neither failure was counted as a passing run.
6. Upstream streaming bypasses ordinary worker parallelism. Local semaphores are not global admission.
   TLS proxy configuration, production isolation review and aggregate capacity remain deployment work.
7. Inline artifacts require one final buffered message. P1 streamed upload/download, owned cached-ID cleanup,
   TTL reconciliation and interactive stdin are documented but not implemented.
8. Remote cleanup under partitions, crashes and hostile filesystem workloads is not proven leak-free.
   Functional process observations are narrower than a full cgroup/temp-file forensic audit. No adversarial
   escape tests or unbounded stress workloads were run on the shared development machine.

## Small performance sample

Run `GO_JUDGE_TEST_TARGET=127.0.0.1:15051 uv run python scripts/benchmark.py` on the documented server.
Windows 11, CPython 3.13.7, grpcio 1.84.0; ten sequential requests per implementation, one reused channel,
zero project/stdin bytes, eight output bytes, no artifacts, 20 ms intentional program sleep:

| Path | Median first output | Median total |
|---|---:|---:|
| Generated stub | 6.76 ms | 30.83 ms |
| SDK | 8.69 ms | 33.11 ms |

Combined Python `tracemalloc` peak was 44,574 bytes for this tiny sample. This excludes native gRPC,
OS/socket buffers and server allocations, and is not a large-payload memory benchmark. No universal latency
or overhead claim follows. The execution path contains no JSON/Base64/archive conversion.

## Reproduction commands

`uv sync --locked`, `uv run poe check`, `uv run pytest tests/unit tests/transport tests/typing tests/cli --cov`,
`uv run poe check-proto`, `uv build`, `uv run poe check-wheel`, `uv run poe test-integration`,
`uv run python scripts/check_cli_signal.py` (Linux), `uv run python scripts/check_remote_cleanup.py`
(labeled disposable Docker server), and `uv run python scripts/benchmark.py`.

The local implementation includes CI workflows but no remote CI run is claimed. See `development.md`
for prerequisites and cleanup commands. No P1 feature is advertised as implemented.
