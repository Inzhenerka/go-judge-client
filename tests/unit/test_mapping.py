from typing import cast

import pytest

from go_judge_client import ClientBudgets, ClientLimitExceededError, ExecutionRequest, ExpectedFile, Limits
from go_judge_client._grpc.response_pb2 import Response
from go_judge_client._mapping import final_result, wire_request
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
