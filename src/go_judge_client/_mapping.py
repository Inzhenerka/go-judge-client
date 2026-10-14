"""Private protobuf adapter; no generated objects cross the public boundary."""

from ._grpc.request_pb2 import Request
from ._grpc.response_pb2 import Response
from ._grpc.stream_request_pb2 import StreamRequest
from .errors import ClientLimitExceededError, ProtocolError, RemoteServiceError
from .models import ArtifactFile, ArtifactProblem, ClientBudgets, ExecutionResult, ExecutionStatus
from .profiles import ResolvedRequest


def wire_request(resolved: ResolvedRequest, budgets: ClientBudgets) -> Request:
    """Build a command with live output descriptors for ExecStream."""
    message = _command_request(resolved, budgets)
    for file in message.cmd[0].files[1:]:
        file.streamOut.SetInParent()
    _check_send_budget(StreamRequest(execRequest=message).ByteSize(), budgets)
    return message


def unary_request(resolved: ResolvedRequest, budgets: ClientBudgets) -> Request:
    """Build a command with bounded output collectors for Exec."""
    message = _command_request(resolved, budgets)
    for fd, name in enumerate(output_names(resolved), start=1):
        message.cmd[0].files[fd].pipe.CopyFrom(
            Request.PipeCollector(name=name, max=budgets.output_bytes + 1, pipe=True)
        )
    _check_send_budget(message.ByteSize(), budgets)
    return message


def _check_send_budget(size: int, budgets: ClientBudgets) -> None:
    if size > budgets.send_message_bytes - 1024:
        raise ClientLimitExceededError("Serialized request exceeds send budget (including reserved headroom)")


def _command_request(resolved: ResolvedRequest, budgets: ClientBudgets) -> Request:
    limits = resolved.limits
    command = Request.CmdType(
        args=resolved.command,
        env=resolved.environment,
        files=[
            Request.File(memory=Request.MemoryFile(content=resolved.stdin)),
            Request.File(),
            Request.File(),
        ],
        cpuTimeLimit=int(limits.cpu_seconds * 1e9),
        clockTimeLimit=int(limits.wall_seconds * 1e9),
        memoryLimit=limits.memory_bytes,
        stackLimit=limits.stack_bytes,
        procLimit=limits.processes,
        cpuRateLimit=int(limits.cpu_cores * 1000) if limits.cpu_cores else 0,
        copyIn={path: Request.File(memory=Request.MemoryFile(content=data)) for path, data in resolved.files},
        copyOut=[Request.CmdCopyOutFile(name=f.path, optional=not f.required) for f in resolved.request.expected_files],
        copyOutMax=budgets.artifact_bytes,
    )
    return Request(requestID=resolved.request_id, cmd=[command])


def final_result(
    response: Response, resolved: ResolvedRequest, budgets: ClientBudgets, stdout: bytes | None, stderr: bytes | None
) -> ExecutionResult:
    if response.error:
        raise RemoteServiceError("Remote service rejected the execution response")
    if len(response.results) != 1:
        raise ProtocolError("Expected exactly one command result")
    result = response.results[0]
    expected = resolved.request.expected_files
    paths = {file.path for file in expected}
    if result.fileIDs or set(result.files) - paths:
        raise ProtocolError("Unexpected cached IDs or unrequested artifact paths")
    if any(len(data) > budgets.artifact_bytes for data in result.files.values()):
        raise ClientLimitExceededError("Individual artifact budget exceeded")
    if sum(map(len, result.files.values())) > budgets.artifacts_bytes:
        raise ClientLimitExceededError("Aggregate artifact budget exceeded")
    artifacts = {
        f.path: ArtifactFile(path=f.path, data=result.files[f.path]) for f in expected if f.path in result.files
    }
    problems = []
    for error in result.fileError:
        try:
            name = Response.FileError.ErrorType.Name(error.type)
        except ValueError:
            name = "Unknown"
        problems.append(ArtifactProblem(path=error.name, error_type=error.type, error_name=name, message=error.message))
    try:
        upstream_name = Response.Result.StatusType.Name(result.status)
    except ValueError:
        upstream_name = "Unknown"
    status = {
        0: "invalid",
        1: "accepted",
        4: "memory_limit_exceeded",
        5: "time_limit_exceeded",
        6: "output_limit_exceeded",
        7: "file_error",
        8: "nonzero_exit",
        9: "signalled",
        10: "dangerous_syscall",
        13: "internal_error",
    }.get(result.status, "unknown")
    problematic = {problem.path for problem in problems}
    return ExecutionResult(
        request_id=resolved.request_id,
        runtime=resolved.request.runtime,
        status=ExecutionStatus(status),
        upstream_status=result.status,
        upstream_status_name=upstream_name,
        exit_status=result.exitStatus,
        diagnostic=result.error,
        cpu_time_ns=result.time,
        elapsed_time_ns=result.runTime,
        memory_bytes=result.memory,
        peak_processes=result.procPeak or None,
        stdout=stdout,
        stderr=stderr,
        artifacts=artifacts,
        artifact_problems=tuple(problems),
        not_received=tuple(f.path for f in expected if f.path not in artifacts),
        required_artifacts_satisfied=all(
            f.path in artifacts and f.path not in problematic for f in expected if f.required
        ),
    )


def output_names(resolved: ResolvedRequest) -> tuple[str, str]:
    """Collector keys share the artifact namespace; never reserve a user's path."""
    paths = {file.path for file in resolved.request.expected_files}
    names = []
    for stream in ("stdout", "stderr"):
        name = f"__go_judge_{stream}"
        while name in paths:
            name += "_"
        names.append(name)
    return names[0], names[1]


def buffered_result(response: Response, resolved: ResolvedRequest, budgets: ClientBudgets) -> ExecutionResult:
    if response.error or len(response.results) != 1:
        return final_result(response, resolved, budgets, b"", b"")
    # Work on a copy: stripping transport-only collectors must not mutate the RPC response.
    cleaned = Response()
    cleaned.CopyFrom(response)
    result = cleaned.results[0]
    names = output_names(resolved)
    if result.status == Response.Result.Accepted and any(name not in result.files for name in names):
        raise ProtocolError("Successful response is missing output collectors")
    stdout, stderr = (result.files.pop(name, b"") for name in names)
    if len(stdout) + len(stderr) > budgets.output_bytes:
        raise ClientLimitExceededError("Observed output exceeds client budget")
    if any(error.name in names for error in result.fileError):
        raise ProtocolError("Output collector failed; complete output is unavailable")
    return final_result(cleaned, resolved, budgets, stdout, stderr)
