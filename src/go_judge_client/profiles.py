"""One deterministic resolution path for direct and profiled requests."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from .errors import ClientLimitExceededError, ConfigurationError, UnknownRuntimeError
from .models import ClientBudgets, ExecutionRequest, Limits, ResolvedLimits, RuntimeProfile, encode, resolve_limits


@dataclass(frozen=True, slots=True)
class ResolvedRequest:
    request: ExecutionRequest
    request_id: str
    command: tuple[str, ...]
    environment: tuple[str, ...]
    limits: ResolvedLimits
    files: tuple[tuple[str, bytes], ...]
    stdin: bytes


def resolve(
    request: ExecutionRequest, profiles: Mapping[str, RuntimeProfile], defaults: Limits, budgets: ClientBudgets
) -> ResolvedRequest:
    # Revalidate even model_copy(update=...) and snapshot mutable dictionaries.
    request = ExecutionRequest.model_validate(request.model_dump())
    profile = None
    if request.runtime is not None:
        try:
            profile = profiles[request.runtime]
        except KeyError:
            raise UnknownRuntimeError("Runtime is not registered") from None
        entry = request.entrypoint if request.entrypoint is not None else profile.default_entrypoint
        if entry is not None and entry not in request.files:
            raise ConfigurationError("Resolved entrypoint must be present in project files")
        command = profile.command + ((entry,) if entry is not None else ()) + request.args
    else:
        assert request.command is not None
        command = request.command
    env = (profile.env if profile else {}) | request.env
    limits = resolve_limits(defaults, profile.limits if profile else None, request.limits)
    files = tuple((path, encode(content)) for path, content in request.files.items())
    stdin = encode(request.stdin)
    environment = tuple(f"{key}={value}" for key, value in sorted(env.items()))
    for actual, maximum, name in (
        (len(files), budgets.input_files, "input file count"),
        (sum(len(data) for _, data in files), budgets.input_bytes, "input bytes"),
        (len(stdin), budgets.stdin_bytes, "stdin bytes"),
        (len(request.expected_files), budgets.expected_files, "expected file count"),
        (len(command), budgets.argument_count, "argument count"),
        (sum(len(arg.encode()) + 1 for arg in command), budgets.argument_bytes, "argument bytes"),
        (len(env), budgets.environment_count, "environment count"),
        (sum(len(value.encode()) + 1 for value in environment), budgets.environment_bytes, "environment bytes"),
    ):
        if actual > maximum:
            raise ClientLimitExceededError(f"Client budget exceeded: {name}")
    for path in [*request.files, *(f.path for f in request.expected_files)]:
        if len(path.encode()) > budgets.path_bytes or len(path.split("/")) > budgets.path_depth:
            raise ClientLimitExceededError("Client path budget exceeded")
    return ResolvedRequest(request, request.request_id or str(uuid4()), command, environment, limits, files, stdin)
