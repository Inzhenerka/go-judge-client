from typing import assert_type

from go_judge_client import (
    AsyncGoJudgeClient,
    Execution,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    Output,
    ResolvedLimits,
    RuntimeProfile,
    TextOutput,
)


async def consumer(client: AsyncGoJudgeClient) -> None:
    assert_type(await client.check_health(), bool)
    assert_type(client.runtime_names, tuple[str, ...])
    assert_type(client.get_runtime("python"), RuntimeProfile)
    request = ExecutionRequest(command=("/bin/true",))
    result = await client.execute(request)
    assert_type(result, ExecutionResult)
    assert_type(result.success, bool)
    assert_type(result.stdout_text(), str | None)
    assert_type(result.stderr_text(), str | None)
    assert_type(result.status, ExecutionStatus)
    assert_type(client.effective_limits(request), ResolvedLimits)
    async with client.stream(request) as execution:
        assert_type(execution, Execution)
        assert_type(execution.request_id, str)
        async for event in execution:
            if isinstance(event, Output):
                assert_type(event.data, bytes)
        assert_type(execution.result, ExecutionResult)
    async with client.stream(request) as execution:
        async for event in execution.text_events():
            if isinstance(event, TextOutput):
                assert_type(event.text, str)


def test_exports() -> None:
    import go_judge_client

    assert all(hasattr(go_judge_client, name) for name in go_judge_client.__all__)
