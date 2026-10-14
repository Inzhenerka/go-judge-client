# Application integration example

[`examples/pumproom_adapter.py`](../examples/pumproom_adapter.py) is a framework-neutral example
using Pydantic file models, a runtime registry, `AsyncExitStack`, a storage protocol and in-memory storage.
It has no dependency on a private application and is intended as a starting point, not durable job storage.

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
