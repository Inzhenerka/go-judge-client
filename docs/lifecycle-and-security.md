# Lifecycle, deadlines and security

Construction performs no network I/O. `start()` creates one owned `grpc.aio` channel in the current event
loop and is idempotent while open. `aclose()` stops admission, cancels operations, joins local cleanup and
closes that channel. Closed clients cannot restart; cross-loop calls raise `ClientStateError`. This release
owns its channel; accepting externally owned channels/metadata is deliberately not an API surface.

Each `client.stream()` is single-use and requires `async with`. It validates and snapshots the request at
entry, acquires a local permit, sends one execution, reads directly as the consumer pulls, verifies final
RPC completion and delivers results. There is no unbounded background output queue or reader. Concurrent
readers fail. Context exit cleans up after early breaks, handler exceptions, deadlines and task cancellation.
The local permit remains held until context finalization, including while delivering artifacts/results.

`request_id` is available before sending and is correlation only. It is not durable storage, an idempotency
key or proof of process start. `result` raises `ResultNotReadyError` until a complete verified result exists.
`await execution.cancel()` is idempotent and finalizes local ownership; subsequent reads raise
`ExecutionCancelledError`. External task cancellation remains `asyncio.CancelledError`.
Concurrent close calls join the same bounded cleanup task. Cancellation of a close waiter is propagated
after that cleanup completes. The finite request sender is also owned and cancelled, so a stalled gRPC
handshake cannot leave its write waiter running after an operation deadline or cancellation.

Timeouts default to 5 seconds for readiness, 150 seconds for the end-to-end operation, and 5 additional
seconds for cleanup. The operation deadline starts at context entry, covers waiting for a local permit,
and is passed to the RPC as remaining time. A timer cancels even while the consumer is paused. Quiet
programs need not emit heartbeat output. If a consumer keeps its context open, it retains ownership and
backpressure; it must exit the context to release its permit. No destructor cleanup is used.

Local concurrency defaults to 8. It is not a distributed queue or a count of remote live processes after
network loss. The pinned upstream ExecStream uses worker.Execute and bypasses the ordinary server
parallelism gate. Global admission and aggregate capacity must be enforced by the deployment.

## Failure semantics

Program failures/resource limits and missing artifacts are results. Configuration, protocol, client-budget
and transport failures are exceptions under `GoJudgeClientError`. Transport errors retain `status_code`
and the original exception cause but avoid copying remote error details into the public message. Treat
exception causes/raw gRPC objects as untrusted and potentially sensitive when configuring logging.

There is no application retry or reconnect-and-replay. The owned channel sets `grpc.enable_retries=0`,
disables HTTP proxy environment inference, and submits with `wait_for_ready=False`; no retry service config
is supplied. These settings are not an exactly-once guarantee. Transport internals and connection loss
cannot prove whether remote code began or finished. Caller-controlled retries can repeat side effects.

## Authentication and TLS

Pass `token=SecretStr(...)` explicitly. The SDK reads no token/environment configuration automatically.
TLS is the default. Custom roots and optional client key/certificate pairs use standard gRPC credentials;
bearer call credentials are composed with TLS credentials. Plaintext requires `insecure=True` and sends
the same bearer metadata once per RPC. Contradictory TLS/plaintext settings fail locally. No certificate
verification bypass or inferred endpoint is provided. Public metadata injection is not supported, so there
is no duplicate authorization path. P0's only remote RPC is ExecStream; readiness is channel-level.

The pinned upstream listener itself is plaintext. Use a real gRPC-capable TLS proxy for remote TLS, keep
the backend private, and configure client certificates there if needed. Client TLS does not enable server
TLS. TLS and mutual TLS are tested against a disposable Python gRPC fixture, not claimed as native go-judge support.

`wait_ready()` proves connectivity only. It does not validate credentials, Executor support, interpreters,
cgroups or capacity. No HTTP /version, implicit execution, standard health service, or FileList probe is used.
Authentication failure maps to `AuthenticationError`; proxy permission errors remain `PermissionDeniedError`;
unimplemented methods become `CompatibilityError`. There is no login/refresh retry.

**Verified upstream logging issue:** startup logs expose AuthToken in full configuration and in `Attach token auth`.
This was reproduced with a synthetic test token. Redact the chosen server build or configure/review an
appropriate logging mitigation before deployment. Client-side redaction cannot repair server logs.

The application owns user authorization, profile selection, quotas, secrets intentionally granted to code,
durable job state, grades and artifact access controls. Hidden input files are visible to the executing code.
No client path validation proves sandbox isolation. This SDK does not configure mounts, egress or cgroups.
Raw output itself may contain student-controlled secrets; forwarding output is an intentional data flow.
