from google.protobuf import empty_pb2 as _empty_pb2
from . import request_pb2 as _request_pb2
from . import go_features_pb2 as _go_features_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StreamRequest(_message.Message):
    __slots__ = ("execRequest", "execInput", "execResize", "execCancel")
    class Input(_message.Message):
        __slots__ = ("index", "fd", "content")
        INDEX_FIELD_NUMBER: _ClassVar[int]
        FD_FIELD_NUMBER: _ClassVar[int]
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        index: int
        fd: int
        content: bytes
        def __init__(self, index: _Optional[int] = ..., fd: _Optional[int] = ..., content: _Optional[bytes] = ...) -> None: ...
    class Resize(_message.Message):
        __slots__ = ("index", "fd", "rows", "cols", "x", "y")
        INDEX_FIELD_NUMBER: _ClassVar[int]
        FD_FIELD_NUMBER: _ClassVar[int]
        ROWS_FIELD_NUMBER: _ClassVar[int]
        COLS_FIELD_NUMBER: _ClassVar[int]
        X_FIELD_NUMBER: _ClassVar[int]
        Y_FIELD_NUMBER: _ClassVar[int]
        index: int
        fd: int
        rows: int
        cols: int
        x: int
        y: int
        def __init__(self, index: _Optional[int] = ..., fd: _Optional[int] = ..., rows: _Optional[int] = ..., cols: _Optional[int] = ..., x: _Optional[int] = ..., y: _Optional[int] = ...) -> None: ...
    EXECREQUEST_FIELD_NUMBER: _ClassVar[int]
    EXECINPUT_FIELD_NUMBER: _ClassVar[int]
    EXECRESIZE_FIELD_NUMBER: _ClassVar[int]
    EXECCANCEL_FIELD_NUMBER: _ClassVar[int]
    execRequest: _request_pb2.Request
    execInput: StreamRequest.Input
    execResize: StreamRequest.Resize
    execCancel: _empty_pb2.Empty
    def __init__(self, execRequest: _Optional[_Union[_request_pb2.Request, _Mapping]] = ..., execInput: _Optional[_Union[StreamRequest.Input, _Mapping]] = ..., execResize: _Optional[_Union[StreamRequest.Resize, _Mapping]] = ..., execCancel: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ...) -> None: ...
