from typing import assert_type

from go_judge_client import AsyncGoJudgeClient, Execution, ExecutionRequest, ExecutionResult, Output, RuntimeProfile


async def consumer(client: AsyncGoJudgeClient) -> None:
    assert_type(client.runtime_names, tuple[str, ...])
    assert_type(client.get_runtime("python"), RuntimeProfile)
    request = ExecutionRequest(command=("/bin/true",))
    assert_type(await client.execute(request), ExecutionResult)
    async with client.stream(request) as execution:
        assert_type(execution, Execution)
        assert_type(execution.request_id, str)
        async for event in execution:
            if isinstance(event, Output):
                assert_type(event.data, bytes)
        assert_type(execution.result, ExecutionResult)


def test_exports() -> None:
    import go_judge_client

    assert all(hasattr(go_judge_client, name) for name in go_judge_client.__all__)
