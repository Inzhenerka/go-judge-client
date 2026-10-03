from . import go_features_pb2 as _go_features_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FileID(_message.Message):
    __slots__ = ("fileID",)
    FILEID_FIELD_NUMBER: _ClassVar[int]
    fileID: str
    def __init__(self, fileID: _Optional[str] = ...) -> None: ...

class FileContent(_message.Message):
    __slots__ = ("name", "content")
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    name: str
    content: bytes
    def __init__(self, name: _Optional[str] = ..., content: _Optional[bytes] = ...) -> None: ...

class FileListType(_message.Message):
    __slots__ = ("fileIDs",)
    class FileIDsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    FILEIDS_FIELD_NUMBER: _ClassVar[int]
    fileIDs: _containers.ScalarMap[str, str]
    def __init__(self, fileIDs: _Optional[_Mapping[str, str]] = ...) -> None: ...
