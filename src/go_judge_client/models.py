"""Validated public boundaries. Text input means UTF-8 content, never a filename."""

import math
import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from ._validation import validation_error

type PositiveInt = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
type Seconds = Annotated[float, Field(gt=0, le=(2**63 - 1) / 1e9, allow_inf_nan=False)]


def project_path(value: str) -> str:
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise validation_error("path")
    return value


def runtime_name(value: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", value) is None:
        raise validation_error("runtime_name")
    return value


def encode(value: str | bytes) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else value


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, validate_default=True)


class ResolvedLimits(Model):
    cpu_seconds: Seconds = 10
    wall_seconds: Seconds = 30
    memory_bytes: PositiveInt = 1024**3
    stack_bytes: PositiveInt = 64 * 1024**2
    processes: PositiveInt = 128
    cpu_cores: Annotated[float, Field(gt=0, le=1_000_000, allow_inf_nan=False)] | None = None

    @field_validator("cpu_seconds", "wall_seconds", "cpu_cores", mode="before")
    @classmethod
    def numeric(cls, value: object) -> object:
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise validation_error("number")
        return value

    @model_validator(mode="after")
    def precision(self) -> Self:
        if any(not 1 <= int(value * 1e9) <= 2**63 - 1 for value in (self.cpu_seconds, self.wall_seconds)):
            raise validation_error("duration_precision")
        if self.cpu_cores is not None and int(self.cpu_cores * 1000) < 1:
            raise validation_error("cpu_precision")
        return self


class Limits(Model):
    """Field overrides. Omitted fields inherit; explicit cpu_cores=None clears its limit."""

    cpu_seconds: Seconds | None = Field(default=None, validate_default=False)
    wall_seconds: Seconds | None = Field(default=None, validate_default=False)
    memory_bytes: PositiveInt | None = Field(default=None, validate_default=False)
    stack_bytes: PositiveInt | None = Field(default=None, validate_default=False)
    processes: PositiveInt | None = Field(default=None, validate_default=False)
    cpu_cores: Annotated[float, Field(gt=0, le=1_000_000, allow_inf_nan=False)] | None = None

    @field_validator("cpu_seconds", "wall_seconds", "memory_bytes", "stack_bytes", "processes", mode="before")
    @classmethod
    def required_when_supplied(cls, value: object) -> object:
        if value is None:
            raise validation_error("null_limit")
        return value

    @field_validator("cpu_seconds", "wall_seconds", "cpu_cores", mode="before")
    @classmethod
    def numeric(cls, value: object) -> object:
        return ResolvedLimits.numeric(value)

    @model_validator(mode="after")
    def precision(self) -> Self:
        # Validate supplied values with the same wire constraints as effective limits.
        ResolvedLimits.model_validate(self.model_dump())
        return self

    @model_serializer(mode="wrap")
    def serialize_overrides(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        values = handler(self)
        return {key: value for key, value in values.items() if key in self.model_fields_set}


def resolve_limits(*layers: Limits | None) -> ResolvedLimits:
    values = ResolvedLimits().model_dump()
    for layer in layers:
        if layer is not None:
            values.update(layer.model_dump())
    return ResolvedLimits.model_validate(values)


class ExecutionStatus(StrEnum):
    INVALID = "invalid"
    ACCEPTED = "accepted"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    FILE_ERROR = "file_error"
    NONZERO_EXIT = "nonzero_exit"
    SIGNALLED = "signalled"
    DANGEROUS_SYSCALL = "dangerous_syscall"
    INTERNAL_ERROR = "internal_error"
    UNKNOWN = "unknown"


class Timeouts(Model):
    connection_seconds: Seconds = 5
    operation_seconds: Seconds = 150
    cleanup_seconds: Seconds = 5

    @field_validator("*", mode="before")
    @classmethod
    def numeric(cls, value: object) -> object:
        return Limits.numeric(value)


def timeout_value(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise validation_error("timeout")
    return value


class ClientBudgets(Model):
    input_files: PositiveInt = 256
    input_bytes: PositiveInt = 8 * 1024**2
    stdin_bytes: PositiveInt = 1024**2
    # Client collector and upstream pipe buffering each add one byte.
    output_bytes: Annotated[int, Field(strict=True, gt=0, le=2**63 - 3)] = 2 * 1024**2
    expected_files: PositiveInt = 32
    artifact_bytes: PositiveInt = 8 * 1024**2
    artifacts_bytes: PositiveInt = 16 * 1024**2
    receive_message_bytes: Annotated[int, Field(strict=True, gt=1024, le=2**31 - 1)] = 32 * 1024**2
    send_message_bytes: Annotated[int, Field(strict=True, gt=1024, le=2**31 - 1)] = 16 * 1024**2
    path_bytes: PositiveInt = 240
    path_depth: PositiveInt = 16
    argument_count: PositiveInt = 128
    argument_bytes: PositiveInt = 16 * 1024
    environment_count: PositiveInt = 64
    environment_bytes: PositiveInt = 32 * 1024

    def configuration_warnings(self) -> tuple[str, ...]:
        """Report potentially conflicting caps; smaller transport caps remain valid."""
        warnings = []
        if self.artifact_bytes > self.artifacts_bytes:
            warnings.append("artifact_bytes exceeds artifacts_bytes; the aggregate cap takes precedence")
        if min(self.artifact_bytes, self.artifacts_bytes) + 1024 > self.receive_message_bytes:
            warnings.append("An allowed artifact may exceed receive_message_bytes; increase the receive cap")
        if self.artifacts_bytes + self.output_bytes + 1024 > self.receive_message_bytes:
            warnings.append("Combined artifacts/output may exceed receive_message_bytes; allow protobuf headroom")
        if self.input_bytes + self.stdin_bytes + 1024 > self.send_message_bytes:
            warnings.append("Combined input/stdin may exceed send_message_bytes; allow protobuf headroom")
        return tuple(warnings)


class ConnectionConfig(Model):
    target: str
    insecure: bool = False
    token: SecretStr | None = Field(default=None, repr=False)
    root_certificates: bytes | None = Field(default=None, repr=False)
    private_key: bytes | None = Field(default=None, repr=False)
    certificate_chain: bytes | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def tls(self) -> Self:
        if not self.target or "\x00" in self.target or "@" in self.target:
            raise validation_error("target")
        if self.insecure and any(
            x is not None for x in (self.root_certificates, self.private_key, self.certificate_chain)
        ):
            raise validation_error("tls_insecure")
        if (self.private_key is None) != (self.certificate_chain is None):
            raise validation_error("tls_pair")
        if self.token is not None:
            token = self.token.get_secret_value()
            if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
                raise validation_error("token")
        return self


class ExpectedFile(Model):
    path: str
    required: bool = True

    @field_validator("path")
    @classmethod
    def path_valid(cls, value: str) -> str:
        project_path(value)
        if value.endswith("?"):
            raise validation_error("optional_marker")
        return value


class RuntimeProfile(Model):
    command: tuple[str, ...]
    default_entrypoint: str | None = None
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    limits: Limits | None = None

    @field_validator("command")
    @classmethod
    def argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or not value[0] or any("\x00" in part for part in value):
            raise validation_error("command")
        return value

    @field_validator("default_entrypoint")
    @classmethod
    def entry(cls, value: str | None) -> str | None:
        return project_path(value) if value is not None else None

    @field_validator("env")
    @classmethod
    def environment(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not k or "=" in k or "\x00" in k or "\x00" in v for k, v in value.items()):
            raise validation_error("environment")
        return value


class ExecutionRequest(Model):
    request_id: Annotated[str, Field(max_length=128)] | None = None
    runtime: str | None = None
    command: tuple[str, ...] | None = None
    entrypoint: str | None = None
    args: tuple[str, ...] = ()
    files: dict[str, str | bytes] = Field(default_factory=dict, repr=False)
    stdin: str | bytes = Field(default=b"", repr=False)
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    limits: Limits | None = None
    expected_files: tuple[ExpectedFile, ...] = ()

    @field_validator("files", mode="before")
    @classmethod
    def content_types(cls, value: object) -> object:
        from collections.abc import Mapping

        if isinstance(value, Mapping) and any(type(item) not in (str, bytes) for item in value.values()):
            raise validation_error("file_content")
        return value

    @field_validator("stdin", mode="before")
    @classmethod
    def stdin_type(cls, value: object) -> object:
        if type(value) not in (str, bytes):
            raise validation_error("stdin_content")
        return value

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (self.runtime is None) == (self.command is None):
            raise validation_error("execution_mode")
        if self.runtime is not None:
            runtime_name(self.runtime)
        if self.command is not None:
            RuntimeProfile.argv(self.command)
            if self.entrypoint is not None or self.args:
                raise validation_error("profile_arguments")
        if self.entrypoint is not None:
            project_path(self.entrypoint)
        RuntimeProfile.environment(self.env)
        for path in self.files:
            project_path(path)
            parts = path.split("/")
            if any("/".join(parts[:i]) in self.files for i in range(1, len(parts))):
                raise validation_error("file_collision")
        paths = [f.path for f in self.expected_files]
        if len(set(paths)) != len(paths):
            raise validation_error("duplicate_artifacts")
        if any("\x00" in part for part in self.args):
            raise validation_error("argument_nul")
        return self


class ArtifactFile(Model):
    path: str
    data: bytes = Field(repr=False, exclude=True)

    @field_validator("path")
    @classmethod
    def path_valid(cls, value: str) -> str:
        return project_path(value)

    @property
    def size_bytes(self) -> int:
        return len(self.data)


class ArtifactProblem(Model):
    path: str
    error_type: int
    error_name: str
    message: str = Field(repr=False)


class ResultSummary(Model):
    request_id: str
    runtime: str | None
    status: ExecutionStatus
    exit_status: int
    cpu_time_ns: int
    elapsed_time_ns: int
    memory_bytes: int
    artifact_sizes: dict[str, int]
    not_received: tuple[str, ...]
    required_artifacts_satisfied: bool


class ExecutionResult(Model):
    request_id: str
    runtime: str | None
    status: ExecutionStatus
    upstream_status: int
    upstream_status_name: str
    exit_status: int
    diagnostic: str = Field(default="", repr=False, exclude=True)
    cpu_time_ns: Annotated[int, Field(ge=0)]
    elapsed_time_ns: Annotated[int, Field(ge=0)]
    memory_bytes: Annotated[int, Field(ge=0)]
    peak_processes: int | None
    stdout: bytes | None = Field(repr=False, exclude=True)
    stderr: bytes | None = Field(repr=False, exclude=True)
    artifacts: dict[str, ArtifactFile]
    artifact_problems: tuple[ArtifactProblem, ...]
    not_received: tuple[str, ...]
    required_artifacts_satisfied: bool

    @property
    def success(self) -> bool:
        """Accepted execution with every required artifact received without a file error."""
        return self.status == ExecutionStatus.ACCEPTED and self.required_artifacts_satisfied

    @property
    def cpu_seconds(self) -> float:
        return self.cpu_time_ns / 1e9

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_time_ns / 1e9

    def stdout_text(self, *, encoding: str = "utf-8", errors: str = "replace") -> str | None:
        """Decode captured stdout; None means output capture was disabled."""
        return self.stdout.decode(encoding, errors) if self.stdout is not None else None

    def stderr_text(self, *, encoding: str = "utf-8", errors: str = "replace") -> str | None:
        """Decode captured stderr; None means output capture was disabled."""
        return self.stderr.decode(encoding, errors) if self.stderr is not None else None

    def summary(self) -> ResultSummary:
        return ResultSummary(
            request_id=self.request_id,
            runtime=self.runtime,
            status=self.status,
            exit_status=self.exit_status,
            cpu_time_ns=self.cpu_time_ns,
            elapsed_time_ns=self.elapsed_time_ns,
            memory_bytes=self.memory_bytes,
            artifact_sizes={p: f.size_bytes for p, f in self.artifacts.items()},
            not_received=self.not_received,
            required_artifacts_satisfied=self.required_artifacts_satisfied,
        )
