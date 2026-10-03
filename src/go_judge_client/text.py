"""Incremental decoding independent of transport chunk boundaries."""

import codecs
from typing import Literal

from .events import Output


class TextDecoder:
    def __init__(self, encoding: str = "utf-8", errors: str = "replace") -> None:
        self._decoders = {name: codecs.getincrementaldecoder(encoding)(errors=errors) for name in ("stdout", "stderr")}

    def decode(self, event: Output) -> str:
        return self._decoders[event.stream].decode(event.data)

    def finish(self, stream: Literal["stdout", "stderr"]) -> str:
        return self._decoders[stream].decode(b"", final=True)
