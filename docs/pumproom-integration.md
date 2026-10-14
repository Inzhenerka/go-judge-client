# Application integration example

[`examples/pumproom_adapter.py`](../examples/pumproom_adapter.py) is a framework-neutral example
using Pydantic file models, a runtime registry, `AsyncExitStack`, a storage protocol and in-memory storage.
It has no dependency on a private application and is intended as a starting point, not durable job storage.

For a request/response API that does not need live output, use `await client.execute(request)` and
persist the returned result. This submits through go-judge's ordinary server queue: `-parallelism` is
shared across API processes and client instances. `max_concurrency` additionally limits each client.
Allow time for queueing in the operation timeout. Cancellation during API restart is supported; durable
recovery is a separate application concern and does not require changing the execution transport.

The adapter below demonstrates the streaming scenario. `stream()` deliberately keeps `ExecStream`
semantics, bypassing server `parallelism`. Moving to live output later requires reviewing aggregate
capacity; the ordinary queue does not cap mixed traffic. Live output is supported today, while dynamic
stdin/TTY interaction would need a separate public API.

Create one long-lived client in the application lifespan and assign an attempt ID before submitting.
The example owns its async generator with `aclosing`, so early exit or handler cancellation also closes
the execution context. A disconnected request cannot establish whether remote execution finished;
persist an interrupted or unknown state when completion is not verified.

Forward individual stdout/stderr events, preserving order within each stream. Store selected artifacts
under application-owned identifiers with access checks. Program success is not an assessment grade;
required artifact availability is a separate result field.

For jobs that must survive HTTP disconnects or application restarts, use an application worker with
persistent job state and an explicit reconciliation policy. The SDK does not provide a durable queue.
When migrating from another engine, record the engine per attempt so existing jobs retain their own
completion and polling semantics.

Only expose approved profiles, arguments and resource limits to users. Files supplied to executing code
are visible to that code, including hidden test inputs. Profiles do not install runtimes or configure
sandbox mounts, credentials or network access; those remain deployment responsibilities.
