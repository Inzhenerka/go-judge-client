import math

import pytest
from pydantic import SecretStr, ValidationError

from go_judge_client import (
    AsyncGoJudgeClient,
    ClientBudgets,
    ClientLimitExceededError,
    ConfigurationError,
    ConnectionConfig,
    ExecutionRequest,
    ExpectedFile,
    Limits,
    Output,
    RuntimeProfile,
    TextDecoder,
    Timeouts,
    UnknownRuntimeError,
)
from go_judge_client._mapping import wire_request
from go_judge_client.profiles import resolve


@pytest.mark.parametrize("path", ["", "/tmp/a", "../a", "a/../b", "a/./b", "a//b", "a/", "C:a", "a\\b", "a\0"])
def test_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ExecutionRequest(command=("run",), files={path: b""})
    with pytest.raises(ValidationError):
        ExpectedFile(path=path)


@pytest.mark.parametrize("value", [True, -1, 0, math.inf, math.nan, 1e100, 1e-12, "1"])
def test_duration_validation(value: object) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate({"cpu_seconds": value})


def test_shape_validation() -> None:
    for data in [
        {},
        {"runtime": "python", "command": ["x"]},
        {"command": []},
        {"command": ["x"], "args": ["a"]},
        {"command": ["x"], "entrypoint": "a"},
        {"command": ["x"], "files": {"a": b"", "a/b": b""}},
        {"command": ["x"], "files": {"a": 42}},
        {"command": ["x"], "env": {"BAD=KEY": "x"}},
        {"command": ["x"], "extra": 1},
        {"runtime": "INVALID"},
        {"command": ["x"], "expected_files": [{"path": "x"}, {"path": "x"}]},
    ]:
        with pytest.raises(ValidationError):
            ExecutionRequest.model_validate(data)
    with pytest.raises(ValidationError):
        ExpectedFile(path="maybe?")
    with pytest.raises(ValidationError):
        ClientBudgets(input_bytes=True)
    with pytest.raises(ValidationError):
        Timeouts.model_validate({"operation_seconds": "1"})


def test_profile_snapshot_resolution_and_wire_equivalence() -> None:
    profile = RuntimeProfile(command=("python", "-u"), default_entrypoint="main.py", env={"X": "original"})
    registry = {"python": profile}
    client = AsyncGoJudgeClient("localhost:1", runtimes=registry)
    registry.clear()
    profile.env["X"] = "changed"
    detached = client.get_runtime("python")
    detached.env["X"] = "another"
    assert client.get_runtime("python").env == {"X": "original"}
    assert client.runtime_names == ("python",)
    request = ExecutionRequest(
        runtime="python",
        request_id="same",
        files={"main.py": "λ"},
        args=("$X; literal",),
        env={"X": "request"},
        stdin=b"\0\xff",
    )
    resolved = resolve(request, client._runtimes, Limits(), ClientBudgets())
    direct = ExecutionRequest(
        command=("python", "-u", "main.py", "$X; literal"),
        request_id="same",
        files={"main.py": "λ"},
        env={"X": "request"},
        stdin=b"\0\xff",
    )
    wire = wire_request(resolved, ClientBudgets())
    assert wire == wire_request(resolve(direct, {}, Limits(), ClientBudgets()), ClientBudgets())
    assert wire.cmd[0].files[0].WhichOneof("file") == "memory"
    assert wire.cmd[0].files[1].WhichOneof("file") == "streamOut"
    assert wire.cmd[0].copyIn["main.py"].memory.content == "λ".encode()


def test_resolution_errors_and_limits_precedence() -> None:
    profile = RuntimeProfile(command=("x",), default_entrypoint="main.py", limits=Limits(cpu_seconds=2))
    with pytest.raises(UnknownRuntimeError):
        resolve(ExecutionRequest(runtime="missing"), {}, Limits(), ClientBudgets())
    with pytest.raises(ConfigurationError):
        resolve(ExecutionRequest(runtime="x"), {"x": profile}, Limits(), ClientBudgets())
    req = ExecutionRequest(runtime="x", files={"main.py": ""})
    assert resolve(req, {"x": profile}, Limits(), ClientBudgets()).limits.cpu_seconds == 2
    req = req.model_copy(update={"limits": Limits(cpu_seconds=3)})
    assert resolve(req, {"x": profile}, Limits(), ClientBudgets()).limits.cpu_seconds == 3
    with pytest.raises(ValidationError):
        resolve(req.model_copy(update={"command": ("bad",)}), {"x": profile}, Limits(), ClientBudgets())


@pytest.mark.parametrize(
    "budget",
    [
        {"input_files": 1},
        {"input_bytes": 1},
        {"stdin_bytes": 1},
        {"argument_count": 1},
        {"argument_bytes": 1},
        {"environment_count": 1},
        {"environment_bytes": 1},
        {"expected_files": 1},
        {"path_bytes": 1},
        {"path_depth": 1},
    ],
)
def test_budgets(budget: dict[str, int]) -> None:
    request = ExecutionRequest(
        command=("run", "arg"),
        files={"a/b": b"xx", "c": b"xx"},
        stdin=b"xx",
        env={"X": "1", "Y": "2"},
        expected_files=(ExpectedFile(path="a"), ExpectedFile(path="b")),
    )
    with pytest.raises(ClientLimitExceededError):
        resolve(request, {}, Limits(), ClientBudgets.model_validate(budget))


def test_secret_repr_and_tls() -> None:
    secret = "synthetic-secret"
    assert secret not in repr(Output("stdout", secret.encode()))
    assert secret not in repr(ExecutionRequest(command=("x",), files={"a": secret}, stdin=secret, env={"X": secret}))
    assert secret not in repr(RuntimeProfile(command=("x",), env={"X": secret}))
    assert secret not in repr(ConnectionConfig(target="localhost:1", token=SecretStr(secret)))
    for fields in [
        {"insecure": True, "root_certificates": b"x"},
        {"private_key": b"x"},
        {"token": "line\nbreak"},
        {"target": "user:pass@host"},
    ]:
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate({"target": "localhost:1"} | fields)


def test_decoder_split_streams() -> None:
    decoder = TextDecoder()
    assert decoder.decode(Output("stdout", b"\xe2")) == ""
    assert decoder.decode(Output("stderr", b"error")) == "error"
    assert decoder.decode(Output("stdout", b"\x82\xac")) == "€"
    assert decoder.decode(Output("stderr", b"\xff")) == "�"
    assert decoder.finish("stdout") == ""


def test_limit_inheritance_survives_snapshots_and_serialization() -> None:
    from go_judge_client import ResolvedLimits

    profile = RuntimeProfile(command=("python",), limits=Limits(memory_bytes=1024**3, cpu_cores=2))
    profile = RuntimeProfile.model_validate_json(profile.model_dump_json())
    client = AsyncGoJudgeClient("localhost:1", default_limits=Limits(wall_seconds=60), runtimes={"python": profile})
    request = ExecutionRequest(runtime="python", limits=Limits(cpu_seconds=2, cpu_cores=None))
    request = ExecutionRequest.model_validate_json(request.model_copy(deep=True).model_dump_json())
    effective = client.effective_limits(request)
    assert isinstance(effective, ResolvedLimits)
    assert effective.cpu_seconds == 2
    assert effective.memory_bytes == 1024**3
    assert effective.wall_seconds == 60
    assert effective.cpu_cores is None
    resolved = resolve(request, client._runtimes, client.default_limits, client.budgets)
    assert resolved.limits == effective
    assert wire_request(resolved, client.budgets).cmd[0].cpuRateLimit == 0
    inherited = client.effective_limits(ExecutionRequest(runtime="python", limits=Limits()))
    assert inherited.cpu_cores == 2 and inherited.memory_bytes == 1024**3
    assert Limits().model_dump() == {}
    assert Limits(cpu_cores=None).model_dump() == {"cpu_cores": None}
    # Even an explicit value equal to the built-in default overrides its parent.
    assert (
        client.effective_limits(ExecutionRequest(runtime="python", limits=Limits(wall_seconds=30))).wall_seconds == 30
    )
    assert client.effective_limits(ExecutionRequest(command=("true",))).memory_bytes == 256 * 1024**2


@pytest.mark.parametrize("field", ["cpu_seconds", "wall_seconds", "memory_bytes", "stack_bytes", "processes"])
def test_mandatory_limits_reject_none(field: str) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate({field: None})


def test_overrides_do_not_present_defaults_as_explicit_values() -> None:
    from go_judge_client import ResolvedLimits

    overrides = Limits(cpu_seconds=2)
    assert overrides.cpu_seconds == 2
    assert overrides.memory_bytes is None
    assert overrides.wall_seconds is None
    assert not isinstance(overrides, ResolvedLimits)
    assert overrides.model_dump() == {"cpu_seconds": 2}
    restored = Limits.model_validate_json(overrides.model_dump_json())
    assert restored.memory_bytes is None and restored.model_fields_set == {"cpu_seconds"}
    assert "cpu_cores" not in Limits().model_fields_set
    assert "cpu_cores" in Limits(cpu_cores=None).model_fields_set
