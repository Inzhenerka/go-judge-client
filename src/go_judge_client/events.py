"""Byte-preserving events in delivery order."""

from dataclasses import dataclass, field
from typing import Literal

from .models import ArtifactFile, ExecutionResult


@dataclass(frozen=True, slots=True)
class Output:
    stream: Literal["stdout", "stderr"]
    data: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class Artifact:
    file: ArtifactFile


@dataclass(frozen=True, slots=True)
class Finished:
    result: ExecutionResult


type ExecutionEvent = Output | Artifact | Finished
