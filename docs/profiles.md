# Runtime profiles

Profiles are trusted local configuration, snapshotted deeply when the client is constructed.
`runtime_names` returns sorted names. `get_runtime(name)` returns a detached copy; changing it cannot
alter the registered profile. Names match `[a-z][a-z0-9._-]{0,63}`. No global registry or hot reload exists.

```toml
[runtimes.python-data]
command = ["/usr/local/runtimes/python-data/bin/python", "-u"]
default_entrypoint = "main.py"

[runtimes.python-data.env]
PYTHONPATH = "/w/src:/w"

[runtimes.python-data.limits]
cpu_seconds = 10
wall_seconds = 30
memory_bytes = 1073741824
stack_bytes = 67108864
processes = 128
```

The TOML document has exactly one top-level table, `runtimes`. Python callers pass a mapping of names
to `RuntimeProfile` directly. Profiles do not install dependencies or select a different server image.

Exactly one of `runtime` and `command` is required. A direct command is complete argv: `args` and
`entrypoint` are forbidden. Profile argv is `command + (entrypoint,) + args`, omitting the entrypoint
when neither an override nor a default exists. `None` selects the default; it does not suppress it.
The resolved entrypoint must be present in project files. No shell expansion or `/box` prefix is added.

Environment precedence is profile followed by request. The client never inherits its process environment.
Limits inherit **per field**: built-in defaults → client `default_limits` → profile → request.
Only explicitly supplied fields override earlier layers. `Limits()` and `limits=None` inherit everything.
For example, a profile with `Limits(memory_bytes=1024**3)` and a request with `Limits(cpu_seconds=2)`
produce 1 GiB of memory and 2 CPU seconds, preserving other client defaults.

Zero, negative values and explicit `None` for mandatory fields are invalid. For optional `cpu_cores`,
omitting the field inherits the rate limit; explicitly setting `None` removes that rate limit only.
`Limits.model_dump()` and nested request/profile serialization retain only explicitly supplied fields,
including an explicit `cpu_cores=None`; copy/JSON round trips preserve inheritance.
Unspecified attributes on `Limits` are `None`, not built-in values. For example,
`Limits(cpu_seconds=2).memory_bytes is None`: this object does not override memory.
For `cpu_cores`, `model_fields_set` distinguishes omission from an explicit `None` that clears the rate.
To inspect concrete values after inheritance, use
`client.effective_limits(request)`, which returns a complete `ResolvedLimits` without connecting or
executing code. Its `model_dump()` includes every effective field.

Profiles provide defaults, not security ceilings: requests may raise limits. Enforce mandatory maximums
separately in your application or server.
Limits default to 10 CPU seconds, 30 wall seconds, 1 GiB memory, 64 MiB stack and 128 processes/threads.
Optional `cpu_cores` maps one core to 1000 wire units and requires a deployment with CPU-rate control enabled.
CPU time and wall time are distinct from the operation deadline.

Pydantic rejects unknown fields and invalid paths/numbers. Configuration resolution raises
`ConfigurationError` or `UnknownRuntimeError`. Pydantic construction errors remain `ValidationError`.
Only explicitly allowed profiles, argv, environment and limits should be exposed to end users.
