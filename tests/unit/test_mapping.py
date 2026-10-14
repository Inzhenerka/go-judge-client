from typing import cast

import pytest

from go_judge_client import ClientBudgets, ClientLimitExceededError, ExecutionRequest, ExpectedFile, Limits
from go_judge_client._grpc.response_pb2 import Response
from go_judge_client._mapping import final_result, unary_request, wire_request
from go_judge_client.profiles import resolve


def test_file_error_preservation() -> None:
    resolved = resolve(
        ExecutionRequest(command=("run",), expected_files=(ExpectedFile(path="x"),)), {}, Limits(), ClientBudgets()
    )
    response = Response(
        results=[
            Response.Result(
                status=Response.Result.TimeLimitExceeded,
                fileError=[
                    Response.FileError(name="x", type=Response.FileError.CopyOutOpen, message="missing"),
                    Response.FileError(name="x", type=cast(Response.FileError.ErrorType, 100), message="future"),
                ],
            )
        ]
    )
    result = final_result(response, resolved, ClientBudgets(), b"", b"")
    assert result.status == "time_limit_exceeded"
    assert result.artifact_problems[0].message == "missing"
    assert result.artifact_problems[1].error_name == "Unknown"
    assert not result.required_artifacts_satisfied


def test_serialized_request_size_cap() -> None:
    budgets = ClientBudgets(send_message_bytes=2048)
    resolved = resolve(ExecutionRequest(command=("run",), files={"x": b"x" * 2000}), {}, Limits(), budgets)
    with pytest.raises(ClientLimitExceededError):
        wire_request(resolved, budgets)


@pytest.mark.parametrize(
    ("status", "received", "required", "expected_success"),
    [
        (1, True, True, True),
        (1, False, True, False),
        (1, False, False, True),
        (8, True, True, False),
        (100, True, True, False),
    ],
)
def test_success_and_typed_status(status: int, received: bool, required: bool, expected_success: bool) -> None:
    from go_judge_client import ExecutionStatus

    resolved = resolve(
        ExecutionRequest(command=("run",), expected_files=(ExpectedFile(path="x", required=required),)),
        {},
        Limits(),
        ClientBudgets(),
    )
    response = Response(
        results=[
            Response.Result(
                status=cast(Response.Result.StatusType, status),
                files={"x": b""} if received else {},
            )
        ]
    )
    result = final_result(response, resolved, ClientBudgets(), b"", b"")
    assert isinstance(result.status, ExecutionStatus)
    assert result.success is expected_success
    assert result.summary().model_dump(mode="json")["status"] == str(result.status)
    if status == 100:
        assert result.status is ExecutionStatus.UNKNOWN and result.upstream_status == 100


def test_buffered_collectors_do_not_collide_or_consume_artifact_budget() -> None:
    from go_judge_client._mapping import buffered_result, output_names

    budgets = ClientBudgets(output_bytes=10, artifact_bytes=1, artifacts_bytes=1)
    resolved = resolve(
        ExecutionRequest(command=("run",), expected_files=(ExpectedFile(path="__go_judge_stdout"),)),
        {},
        Limits(),
        budgets,
    )
    wire = unary_request(resolved, budgets)
    out, err = output_names(resolved)
    assert out != "__go_judge_stdout"
    assert wire.cmd[0].files[1].pipe.name == out
    assert wire.cmd[0].files[1].pipe.max == 11
    assert wire.cmd[0].files[1].pipe.pipe
    response = Response(
        results=[
            Response.Result(
                status=Response.Result.Accepted,
                files={
                    out: b"12345",
                    err: b"67890",
                    "__go_judge_stdout": b"x",
                },
            )
        ]
    )
    result = buffered_result(response, resolved, budgets)
    assert result.stdout == b"12345" and result.stderr == b"67890"
    assert set(result.artifacts) == {"__go_judge_stdout"}
    assert len(response.results[0].files) == 3
    response.results[0].files[out] += b"!"
    with pytest.raises(ClientLimitExceededError):
        buffered_result(response, resolved, budgets)


@pytest.mark.parametrize("mode", ["unexpected", "cached", "collector-error", "no-result", "two-results"])
def test_buffered_protocol_validation(mode: str) -> None:
    from go_judge_client import ProtocolError
    from go_judge_client._mapping import buffered_result, output_names

    budgets = ClientBudgets()
    resolved = resolve(ExecutionRequest(command=("run",)), {}, Limits(), budgets)
    out, err = output_names(resolved)
    response = Response(results=[Response.Result(status=Response.Result.Accepted, files={out: b"", err: b""})])
    if mode == "unexpected":
        response.results[0].files["unknown"] = b"x"
    elif mode == "cached":
        response.results[0].fileIDs[out] = "id"
    elif mode == "collector-error":
        response.results[0].fileError.add(name=out, type=Response.FileError.CopyOutOpen)
    elif mode == "no-result":
        response.ClearField("results")
    else:
        response.results.add(status=Response.Result.Accepted)
    with pytest.raises(ProtocolError):
        buffered_result(response, resolved, budgets)


@pytest.mark.parametrize("missing", [(0,), (1,), (0, 1)])
def test_buffered_success_requires_both_output_collectors(missing: tuple[int, ...]) -> None:
    from go_judge_client import ProtocolError
    from go_judge_client._mapping import buffered_result, output_names

    budgets = ClientBudgets()
    resolved = resolve(ExecutionRequest(command=("run",)), {}, Limits(), budgets)
    names = output_names(resolved)
    files = {name: b"" for index, name in enumerate(names) if index not in missing}
    response = Response(results=[Response.Result(status=Response.Result.Accepted, files=files)])
    with pytest.raises(ProtocolError, match="missing output collectors"):
        buffered_result(response, resolved, budgets)


def test_buffered_empty_output_is_valid() -> None:
    from go_judge_client._mapping import buffered_result, output_names

    budgets = ClientBudgets()
    resolved = resolve(ExecutionRequest(command=("run",)), {}, Limits(), budgets)
    files = dict.fromkeys(output_names(resolved), b"")
    result = buffered_result(
        Response(results=[Response.Result(status=Response.Result.Accepted, files=files)]), resolved, budgets
    )
    assert result.success
    assert result.stdout == result.stderr == b""
    assert not result.artifacts


def test_buffered_preparation_failure_can_omit_output() -> None:
    from go_judge_client._mapping import buffered_result

    budgets = ClientBudgets()
    resolved = resolve(ExecutionRequest(command=("run",)), {}, Limits(), budgets)
    result = buffered_result(
        Response(results=[Response.Result(status=Response.Result.InternalError, error="failed to get environment")]),
        resolved,
        budgets,
    )
    assert result.status == "internal_error"
    assert not result.success
    assert result.diagnostic == "failed to get environment"
    assert result.stdout == result.stderr == b""
