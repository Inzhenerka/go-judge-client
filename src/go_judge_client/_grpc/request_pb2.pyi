from google.protobuf import empty_pb2 as _empty_pb2
from . import go_features_pb2 as _go_features_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Request(_message.Message):
    __slots__ = ("requestID", "cmd", "pipeMapping")
    class LocalFile(_message.Message):
        __slots__ = ("src",)
        SRC_FIELD_NUMBER: _ClassVar[int]
        src: str
        def __init__(self, src: _Optional[str] = ...) -> None: ...
    class MemoryFile(_message.Message):
        __slots__ = ("content",)
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        content: bytes
        def __init__(self, content: _Optional[bytes] = ...) -> None: ...
    class CachedFile(_message.Message):
        __slots__ = ("fileID",)
        FILEID_FIELD_NUMBER: _ClassVar[int]
        fileID: str
        def __init__(self, fileID: _Optional[str] = ...) -> None: ...
    class PipeCollector(_message.Message):
        __slots__ = ("name", "max", "pipe")
        NAME_FIELD_NUMBER: _ClassVar[int]
        MAX_FIELD_NUMBER: _ClassVar[int]
        PIPE_FIELD_NUMBER: _ClassVar[int]
        name: str
        max: int
        pipe: bool
        def __init__(self, name: _Optional[str] = ..., max: _Optional[int] = ..., pipe: _Optional[bool] = ...) -> None: ...
    class File(_message.Message):
        __slots__ = ("local", "memory", "cached", "pipe", "streamIn", "streamOut")
        LOCAL_FIELD_NUMBER: _ClassVar[int]
        MEMORY_FIELD_NUMBER: _ClassVar[int]
        CACHED_FIELD_NUMBER: _ClassVar[int]
        PIPE_FIELD_NUMBER: _ClassVar[int]
        STREAMIN_FIELD_NUMBER: _ClassVar[int]
        STREAMOUT_FIELD_NUMBER: _ClassVar[int]
        local: Request.LocalFile
        memory: Request.MemoryFile
        cached: Request.CachedFile
        pipe: Request.PipeCollector
        streamIn: _empty_pb2.Empty
        streamOut: _empty_pb2.Empty
        def __init__(self, local: _Optional[_Union[Request.LocalFile, _Mapping]] = ..., memory: _Optional[_Union[Request.MemoryFile, _Mapping]] = ..., cached: _Optional[_Union[Request.CachedFile, _Mapping]] = ..., pipe: _Optional[_Union[Request.PipeCollector, _Mapping]] = ..., streamIn: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ..., streamOut: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ...) -> None: ...
    class CmdType(_message.Message):
        __slots__ = ("args", "env", "files", "tty", "cpuTimeLimit", "clockTimeLimit", "memoryLimit", "stackLimit", "procLimit", "cpuRateLimit", "cpuSetLimit", "dataSegmentLimit", "addressSpaceLimit", "copyIn", "symlinks", "copyOut", "copyOutCached", "copyOutDir", "copyOutMax", "copyOutTruncate")
        class CopyInEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: Request.File
            def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Request.File, _Mapping]] = ...) -> None: ...
        class SymlinksEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: str
            def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
        ARGS_FIELD_NUMBER: _ClassVar[int]
        ENV_FIELD_NUMBER: _ClassVar[int]
        FILES_FIELD_NUMBER: _ClassVar[int]
        TTY_FIELD_NUMBER: _ClassVar[int]
        CPUTIMELIMIT_FIELD_NUMBER: _ClassVar[int]
        CLOCKTIMELIMIT_FIELD_NUMBER: _ClassVar[int]
        MEMORYLIMIT_FIELD_NUMBER: _ClassVar[int]
        STACKLIMIT_FIELD_NUMBER: _ClassVar[int]
        PROCLIMIT_FIELD_NUMBER: _ClassVar[int]
        CPURATELIMIT_FIELD_NUMBER: _ClassVar[int]
        CPUSETLIMIT_FIELD_NUMBER: _ClassVar[int]
        DATASEGMENTLIMIT_FIELD_NUMBER: _ClassVar[int]
        ADDRESSSPACELIMIT_FIELD_NUMBER: _ClassVar[int]
        COPYIN_FIELD_NUMBER: _ClassVar[int]
        SYMLINKS_FIELD_NUMBER: _ClassVar[int]
        COPYOUT_FIELD_NUMBER: _ClassVar[int]
        COPYOUTCACHED_FIELD_NUMBER: _ClassVar[int]
        COPYOUTDIR_FIELD_NUMBER: _ClassVar[int]
        COPYOUTMAX_FIELD_NUMBER: _ClassVar[int]
        COPYOUTTRUNCATE_FIELD_NUMBER: _ClassVar[int]
        args: _containers.RepeatedScalarFieldContainer[str]
        env: _containers.RepeatedScalarFieldContainer[str]
        files: _containers.RepeatedCompositeFieldContainer[Request.File]
        tty: bool
        cpuTimeLimit: int
        clockTimeLimit: int
        memoryLimit: int
        stackLimit: int
        procLimit: int
        cpuRateLimit: int
        cpuSetLimit: str
        dataSegmentLimit: bool
        addressSpaceLimit: bool
        copyIn: _containers.MessageMap[str, Request.File]
        symlinks: _containers.ScalarMap[str, str]
        copyOut: _containers.RepeatedCompositeFieldContainer[Request.CmdCopyOutFile]
        copyOutCached: _containers.RepeatedCompositeFieldContainer[Request.CmdCopyOutFile]
        copyOutDir: str
        copyOutMax: int
        copyOutTruncate: bool
        def __init__(self, args: _Optional[_Iterable[str]] = ..., env: _Optional[_Iterable[str]] = ..., files: _Optional[_Iterable[_Union[Request.File, _Mapping]]] = ..., tty: _Optional[bool] = ..., cpuTimeLimit: _Optional[int] = ..., clockTimeLimit: _Optional[int] = ..., memoryLimit: _Optional[int] = ..., stackLimit: _Optional[int] = ..., procLimit: _Optional[int] = ..., cpuRateLimit: _Optional[int] = ..., cpuSetLimit: _Optional[str] = ..., dataSegmentLimit: _Optional[bool] = ..., addressSpaceLimit: _Optional[bool] = ..., copyIn: _Optional[_Mapping[str, Request.File]] = ..., symlinks: _Optional[_Mapping[str, str]] = ..., copyOut: _Optional[_Iterable[_Union[Request.CmdCopyOutFile, _Mapping]]] = ..., copyOutCached: _Optional[_Iterable[_Union[Request.CmdCopyOutFile, _Mapping]]] = ..., copyOutDir: _Optional[str] = ..., copyOutMax: _Optional[int] = ..., copyOutTruncate: _Optional[bool] = ...) -> None: ...
    class CmdCopyOutFile(_message.Message):
        __slots__ = ("name", "optional")
        NAME_FIELD_NUMBER: _ClassVar[int]
        OPTIONAL_FIELD_NUMBER: _ClassVar[int]
        name: str
        optional: bool
        def __init__(self, name: _Optional[str] = ..., optional: _Optional[bool] = ...) -> None: ...
    class PipeMap(_message.Message):
        __slots__ = ("out", "proxy", "name", "max", "disableZeroCopy")
        class PipeIndex(_message.Message):
            __slots__ = ("index", "fd")
            INDEX_FIELD_NUMBER: _ClassVar[int]
            FD_FIELD_NUMBER: _ClassVar[int]
            index: int
            fd: int
            def __init__(self, index: _Optional[int] = ..., fd: _Optional[int] = ...) -> None: ...
        IN_FIELD_NUMBER: _ClassVar[int]
        OUT_FIELD_NUMBER: _ClassVar[int]
        PROXY_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        MAX_FIELD_NUMBER: _ClassVar[int]
        DISABLEZEROCOPY_FIELD_NUMBER: _ClassVar[int]
        out: Request.PipeMap.PipeIndex
        proxy: bool
        name: str
        max: int
        disableZeroCopy: bool
        def __init__(self, out: _Optional[_Union[Request.PipeMap.PipeIndex, _Mapping]] = ..., proxy: _Optional[bool] = ..., name: _Optional[str] = ..., max: _Optional[int] = ..., disableZeroCopy: _Optional[bool] = ..., **kwargs) -> None: ...
    REQUESTID_FIELD_NUMBER: _ClassVar[int]
    CMD_FIELD_NUMBER: _ClassVar[int]
    PIPEMAPPING_FIELD_NUMBER: _ClassVar[int]
    requestID: str
    cmd: _containers.RepeatedCompositeFieldContainer[Request.CmdType]
    pipeMapping: _containers.RepeatedCompositeFieldContainer[Request.PipeMap]
    def __init__(self, requestID: _Optional[str] = ..., cmd: _Optional[_Iterable[_Union[Request.CmdType, _Mapping]]] = ..., pipeMapping: _Optional[_Iterable[_Union[Request.PipeMap, _Mapping]]] = ...) -> None: ...
