"""Safe, payload-free client errors; remote diagnostics remain in results."""

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


class ClientLimitExceededError(GoJudgeClientError):
    pass


class RemoteServiceError(GoJudgeClientError):
    pass


def rpc_error(code: grpc.StatusCode) -> GoJudgeClientError:
    kind = {
        grpc.StatusCode.UNAUTHENTICATED: AuthenticationError,
        grpc.StatusCode.PERMISSION_DENIED: PermissionDeniedError,
        grpc.StatusCode.UNIMPLEMENTED: CompatibilityError,
        grpc.StatusCode.DEADLINE_EXCEEDED: ExecutionDeadlineExceeded,
        grpc.StatusCode.CANCELLED: ExecutionCancelledError,
        grpc.StatusCode.RESOURCE_EXHAUSTED: ClientLimitExceededError,
    }.get(code, ConnectionError)
    return kind(f"gRPC operation failed ({code.name}); remote outcome may be unknown", status_code=code)
