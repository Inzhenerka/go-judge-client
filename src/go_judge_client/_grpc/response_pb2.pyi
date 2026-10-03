from . import go_features_pb2 as _go_features_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Response(_message.Message):
    __slots__ = ("requestID", "results", "error")
    class FileError(_message.Message):
        __slots__ = ("name", "type", "message")
        class ErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            CopyInOpenFile: _ClassVar[Response.FileError.ErrorType]
            CopyInCreateFile: _ClassVar[Response.FileError.ErrorType]
            CopyInCopyContent: _ClassVar[Response.FileError.ErrorType]
            CopyOutOpen: _ClassVar[Response.FileError.ErrorType]
            CopyOutNotRegularFile: _ClassVar[Response.FileError.ErrorType]
            CopyOutSizeExceeded: _ClassVar[Response.FileError.ErrorType]
            CopyOutCreateFile: _ClassVar[Response.FileError.ErrorType]
            CopyOutCopyContent: _ClassVar[Response.FileError.ErrorType]
            CollectSizeExceeded: _ClassVar[Response.FileError.ErrorType]
            Symlink: _ClassVar[Response.FileError.ErrorType]
        CopyInOpenFile: Response.FileError.ErrorType
        CopyInCreateFile: Response.FileError.ErrorType
        CopyInCopyContent: Response.FileError.ErrorType
        CopyOutOpen: Response.FileError.ErrorType
        CopyOutNotRegularFile: Response.FileError.ErrorType
        CopyOutSizeExceeded: Response.FileError.ErrorType
        CopyOutCreateFile: Response.FileError.ErrorType
        CopyOutCopyContent: Response.FileError.ErrorType
        CollectSizeExceeded: Response.FileError.ErrorType
        Symlink: Response.FileError.ErrorType
        NAME_FIELD_NUMBER: _ClassVar[int]
        TYPE_FIELD_NUMBER: _ClassVar[int]
        MESSAGE_FIELD_NUMBER: _ClassVar[int]
        name: str
        type: Response.FileError.ErrorType
        message: str
        def __init__(self, name: _Optional[str] = ..., type: _Optional[_Union[Response.FileError.ErrorType, str]] = ..., message: _Optional[str] = ...) -> None: ...
    class Result(_message.Message):
        __slots__ = ("status", "exitStatus", "error", "time", "runTime", "procPeak", "memory", "files", "fileIDs", "fileError")
        class StatusType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            Invalid: _ClassVar[Response.Result.StatusType]
            Accepted: _ClassVar[Response.Result.StatusType]
            WrongAnswer: _ClassVar[Response.Result.StatusType]
            PartiallyCorrect: _ClassVar[Response.Result.StatusType]
            MemoryLimitExceeded: _ClassVar[Response.Result.StatusType]
            TimeLimitExceeded: _ClassVar[Response.Result.StatusType]
            OutputLimitExceeded: _ClassVar[Response.Result.StatusType]
            FileError: _ClassVar[Response.Result.StatusType]
            NonZeroExitStatus: _ClassVar[Response.Result.StatusType]
            Signalled: _ClassVar[Response.Result.StatusType]
            DangerousSyscall: _ClassVar[Response.Result.StatusType]
            JudgementFailed: _ClassVar[Response.Result.StatusType]
            InvalidInteraction: _ClassVar[Response.Result.StatusType]
            InternalError: _ClassVar[Response.Result.StatusType]
        Invalid: Response.Result.StatusType
        Accepted: Response.Result.StatusType
        WrongAnswer: Response.Result.StatusType
        PartiallyCorrect: Response.Result.StatusType
        MemoryLimitExceeded: Response.Result.StatusType
        TimeLimitExceeded: Response.Result.StatusType
        OutputLimitExceeded: Response.Result.StatusType
        FileError: Response.Result.StatusType
        NonZeroExitStatus: Response.Result.StatusType
        Signalled: Response.Result.StatusType
        DangerousSyscall: Response.Result.StatusType
        JudgementFailed: Response.Result.StatusType
        InvalidInteraction: Response.Result.StatusType
        InternalError: Response.Result.StatusType
        class FilesEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: bytes
            def __init__(self, key: _Optional[str] = ..., value: _Optional[bytes] = ...) -> None: ...
        class FileIDsEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: str
            def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
        STATUS_FIELD_NUMBER: _ClassVar[int]
        EXITSTATUS_FIELD_NUMBER: _ClassVar[int]
        ERROR_FIELD_NUMBER: _ClassVar[int]
        TIME_FIELD_NUMBER: _ClassVar[int]
        RUNTIME_FIELD_NUMBER: _ClassVar[int]
        PROCPEAK_FIELD_NUMBER: _ClassVar[int]
        MEMORY_FIELD_NUMBER: _ClassVar[int]
        FILES_FIELD_NUMBER: _ClassVar[int]
        FILEIDS_FIELD_NUMBER: _ClassVar[int]
        FILEERROR_FIELD_NUMBER: _ClassVar[int]
        status: Response.Result.StatusType
        exitStatus: int
        error: str
        time: int
        runTime: int
        procPeak: int
        memory: int
        files: _containers.ScalarMap[str, bytes]
        fileIDs: _containers.ScalarMap[str, str]
        fileError: _containers.RepeatedCompositeFieldContainer[Response.FileError]
        def __init__(self, status: _Optional[_Union[Response.Result.StatusType, str]] = ..., exitStatus: _Optional[int] = ..., error: _Optional[str] = ..., time: _Optional[int] = ..., runTime: _Optional[int] = ..., procPeak: _Optional[int] = ..., memory: _Optional[int] = ..., files: _Optional[_Mapping[str, bytes]] = ..., fileIDs: _Optional[_Mapping[str, str]] = ..., fileError: _Optional[_Iterable[_Union[Response.FileError, _Mapping]]] = ...) -> None: ...
    REQUESTID_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    requestID: str
    results: _containers.RepeatedCompositeFieldContainer[Response.Result]
    error: str
    def __init__(self, requestID: _Optional[str] = ..., results: _Optional[_Iterable[_Union[Response.Result, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...
