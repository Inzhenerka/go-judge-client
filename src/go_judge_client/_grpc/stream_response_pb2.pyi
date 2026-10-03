from . import response_pb2 as _response_pb2
from . import go_features_pb2 as _go_features_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StreamResponse(_message.Message):
    __slots__ = ("execResponse", "execOutput")
    class Output(_message.Message):
        __slots__ = ("index", "fd", "content")
        INDEX_FIELD_NUMBER: _ClassVar[int]
        FD_FIELD_NUMBER: _ClassVar[int]
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        index: int
        fd: int
        content: bytes
        def __init__(self, index: _Optional[int] = ..., fd: _Optional[int] = ..., content: _Optional[bytes] = ...) -> None: ...
    EXECRESPONSE_FIELD_NUMBER: _ClassVar[int]
    EXECOUTPUT_FIELD_NUMBER: _ClassVar[int]
    execResponse: _response_pb2.Response
    execOutput: StreamResponse.Output
    def __init__(self, execResponse: _Optional[_Union[_response_pb2.Response, _Mapping]] = ..., execOutput: _Optional[_Union[StreamResponse.Output, _Mapping]] = ...) -> None: ...
