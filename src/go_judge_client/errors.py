"""Safe, payload-free client errors; remote diagnostics remain in results."""

from enum import StrEnum

import grpc


class GoJudgeClientError(Exception):
    def __init__(self, message: str, *, status_code: grpc.StatusCode | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConfigurationError(GoJudgeClientError):
    pass


class UnknownRuntimeError(ConfigurationError):
    pass


class ClientStateError(GoJudgeClientError):
    pass


class ResultNotReadyError(ClientStateError):
    pass


class ConnectionError(GoJudgeClientError):
    pass


class AuthenticationError(GoJudgeClientError):
    pass


class PermissionDeniedError(GoJudgeClientError):
    pass


class CompatibilityError(GoJudgeClientError):
    pass


class ProtocolError(GoJudgeClientError):
    pass


class ExecutionDeadlineExceeded(GoJudgeClientError):
    pass


class ExecutionCancelledError(GoJudgeClientError):
    pass


class ClientLimitReason(StrEnum):
    OUTPUT_BYTES = "output_bytes"
    ARTIFACT_BYTES = "artifact_bytes"
    ARTIFACTS_BYTES = "artifacts_bytes"
    RESOURCE_EXHAUSTED = "resource_exhausted"


class ClientLimitExceededError(GoJudgeClientError):
    def __init__(
        self,
        message: str,
        *,
        status_code: grpc.StatusCode | None = None,
        reason: ClientLimitReason | None = None,
        limit_bytes: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.reason = reason
        self.limit_bytes = limit_bytes


class RemoteServiceError(GoJudgeClientError):
    pass


def rpc_error(code: grpc.StatusCode) -> GoJudgeClientError:
    message = f"gRPC operation failed ({code.name}); remote outcome may be unknown"
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return ClientLimitExceededError(message, status_code=code, reason=ClientLimitReason.RESOURCE_EXHAUSTED)
    kind = {
        grpc.StatusCode.UNAUTHENTICATED: AuthenticationError,
        grpc.StatusCode.PERMISSION_DENIED: PermissionDeniedError,
        grpc.StatusCode.UNIMPLEMENTED: CompatibilityError,
        grpc.StatusCode.DEADLINE_EXCEEDED: ExecutionDeadlineExceeded,
        grpc.StatusCode.CANCELLED: ExecutionCancelledError,
    }.get(code, ConnectionError)
    return kind(message, status_code=code)
