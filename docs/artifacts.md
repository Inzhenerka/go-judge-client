# Files, artifacts and budgets

`ExecutionRequest.files` explicitly maps paths to UTF-8 text or bytes. Strings never denote local paths
or URLs. Finite stdin is a memory file at descriptor 0; descriptors 1 and 2 stream byte-preserving output.
The client sends one request and half-closes its sending direction without cancelling execution.

Paths cannot be absolute, drive-prefixed, contain backslashes, NULs, colons, empty components, `.` or `..`.
Input file/directory prefix collisions and duplicate expected paths are rejected. Expected paths cannot
end with `?`, the upstream optional marker. Unicode and spaces are supported within configured bounds.

Request artifacts using `ExpectedFile(path=..., required=True/False)`. P0 uses inline `copyOut` with a
common per-file cap; it does not use cached IDs or recursive discovery. Received files are delivered in
requested order. Empty bytes are a received file. Unrequested returned paths or cached IDs are protocol errors.

`result.not_received` means exactly that, not necessarily ENOENT. Required failures retain original file
error type/name/message. Upstream suppresses optional open errors more broadly than missing-file errors.
`required_artifacts_satisfied` is independent of program status and is not a grade. A timeout is never
replaced by a generic missing-file status. Unknown future statuses retain their numeric value and normalize to `unknown`.

Artifacts remain provisional until terminal gRPC OK. A final response followed by failure cannot produce
`Artifact` or `Finished`. Already-forwarded stdout cannot be retracted. All artifacts arrive in one final
protobuf message; gRPC materializes it before aggregate validation. This is bounded buffering, not file-chunk streaming.

| ClientBudgets field | Default |
|---|---:|
| input_files / input_bytes | 256 / 8 MiB |
| stdin_bytes | 1 MiB |
| output_bytes | 2 MiB combined stdout/stderr |
| expected_files | 32 |
| artifact_bytes / artifacts_bytes | 8 MiB / 16 MiB |
| receive_message_bytes / send_message_bytes | 32 MiB / 16 MiB |
| path_bytes / path_depth | 240 UTF-8 bytes / 16 components |
| argument_count / argument_bytes | 128 / 16 KiB |
| environment_count / environment_bytes | 64 / 32 KiB |

Send validation reserves 1024 bytes of headroom. `copyOutMax` is per-file, not aggregate. The receive cap
bounds message allocation; there are additional Python/protobuf object allocations. Output accounting applies
even with `capture_output=False`. Exceeding a client budget cancels and raises `ClientLimitExceededError`;
it never silently truncates a supposedly complete transcript.

SDK results do not save files. The CLI writes requested paths exclusively under the chosen output directory,
rejecting existing symlink/junction components and existing files. Use a private directory that other processes
cannot mutate during writes; path checks are not a substitute for OS-level directory ownership.
On Windows, the CLI also rejects reserved device names, invalid characters and components ending in a
space or dot, including in the output directory. These names remain valid remote POSIX names where
applicable; they can still be consumed as bytes through the SDK.

The pinned real server rejected a workspace symlink during `Open` with `CopyOutOpen: ... not a regular file`.
This observation does not establish general no-follow guarantees for other server versions or mounts.

## Deferred P1 file streams

P1 may use `FileAddStream`, `copyOutCached`, `FileGetStream` and deletion on the same channel. These are
separate RPCs owned by one Python context, not one wire stream. Check support before submitting code.
Track only IDs created by that operation, never sweep `FileList`. Validate download paths against the
manifest, enforce per-file/aggregate budgets and bounded transfer concurrency, and commit only completed
artifacts. Delete known IDs with an independent bounded cleanup context on every exit path. Unknown IDs
lost before acknowledgement require server TTL and monitoring. TTL must cover legitimate transfer duration.
No automatic cached-mode fallback or execution replay is allowed. None of these P1 APIs is implemented yet.
