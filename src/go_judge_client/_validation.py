"""Stable validation codes and value-free explanations shared by models and CLI."""

from typing import LiteralString

from pydantic_core import PydanticCustomError

MESSAGES: dict[LiteralString, LiteralString] = {
    "gj_path": "Expected a relative POSIX path without empty, dot or parent components",
    "gj_runtime_name": (
        "Use a lowercase runtime name starting with a letter "
        "(letters, digits, dots, underscores or hyphens; up to 64 characters)"
    ),
    "gj_number": "Expected a numeric value, excluding booleans",
    "gj_duration_precision": "Duration is outside wire precision or range",
    "gj_cpu_precision": "CPU rate must be at least 0.001 cores",
    "gj_null_limit": "Omit the field to inherit; an explicit null is not a limit",
    "gj_timeout": "Timeout must be finite and positive",
    "gj_target": "Invalid gRPC target",
    "gj_tls_insecure": "TLS credentials cannot be used with insecure=True",
    "gj_tls_pair": "Client certificate and key must be supplied together",
    "gj_token": "Token must contain printable ASCII without whitespace",
    "gj_optional_marker": "Expected paths cannot end with a question mark; use required=False",
    "gj_command": "Command must contain a nonempty executable and no NULs",
    "gj_environment": (
        "Environment names must be nonempty and contain no equals sign; names and values must contain no NULs"
    ),
    "gj_file_content": "File content must be str or bytes",
    "gj_stdin_content": "Stdin must be str or bytes",
    "gj_execution_mode": "Provide exactly one of runtime and command",
    "gj_profile_arguments": "Entrypoint and args are profile-only fields",
    "gj_file_collision": "Input file/directory prefix collision",
    "gj_duplicate_artifacts": "Duplicate expected paths",
    "gj_argument_nul": "Arguments cannot contain NUL",
}


def validation_error(code: LiteralString) -> PydanticCustomError:
    key = f"gj_{code}"
    return PydanticCustomError(key, MESSAGES[key])
