# PumpRoom integration plan

The SDK is independent of PumpRoom. `examples/pumproom_adapter.py` uses Pydantic file models, a local
profile registry, `AsyncExitStack`, a storage Protocol and an in-memory implementation. It is executable
and type-checkable without private imports. No production PumpRoom code is modified.

Create a long-lived client in application lifespan, register its `aclose`, and allocate a local attempt ID
before submitting. Save the engine alongside each attempt so old Judge0 attempts keep their old polling
path. Preserve submission quotas, hidden-file rules, analytics and assessment classifications. Existing
`judge0` strings also occur in business branches and must not be blindly renamed.

Add a live request-owned path alongside existing submission/polling contracts rather than forcing all
quiz/chat/agent backends to change. Close the stream on frontend disconnect or handler cancellation;
the example uses `aclosing` for its event generator. Persist interrupted/unknown outcomes when transport
completion is not verified. On process restart reconcile stale running records rather than reporting
them as still successfully running forever. Durable grading requires an independently owned application
worker and persistent state, not a hidden SDK task.

Convert text and binary task files explicitly. A text-only helper discards binary inputs and is unsuitable.
Forward individual stdout/stderr deltas to the frontend, never the full growing transcript. Preserve per-stream
order without promising exact cross-stream chronology. Keep protobuf out of browser messages.

Keep source/editor inputs distinct from generated artifacts. Persist selected artifacts under application-owned
identifiers with access checks. Artifact metadata may be represented in existing backend output, but program
success is not a grade and missing artifacts are educational feedback. Hidden files supplied to code are not
secret from that code. Never put reusable application credentials into profiles; intentionally granted
per-execution credentials require separate scoping and policy.

Reuse task-specific knowledge about Python, Cargo, dbt, Java and Playwright in profiles or small application
wrappers. Profiles do not install tools, change images or configure network isolation. Deploy network-enabled
tasks to appropriately reviewed egress environments. Compile/run stages remain distinguishable application
operations; multiple go-judge commands are not a sequential pipeline. Prefer native expected-file collection
over appending export commands after an `exec` that can prevent them from running.
