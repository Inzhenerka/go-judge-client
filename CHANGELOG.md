# Changelog

## 0.1.0 — unreleased

- Add an asynchronous gRPC streaming client with explicit operation ownership and no execution retries.
- Add validated runtime profiles, direct commands, finite binary stdin/project files and bounded inline artifacts.
- Add deadlines, cancellation, bearer/TLS configuration, transport readiness and incremental text decoding.
- Add optional Typer commands (`go-judge-client`, alias `gj`), examples, uv tooling and compatibility tests.
- Make protobuf checks portable across checkout platforms and reject stale generated files.
- Build wire messages only after admission; enforce deadlines after synchronous request preparation.
- Clarify project-root symlink handling and exclude the artifact destination from subsequent uploads.
- Distinguish CLI error causes without exposing input values or remote exception details.
