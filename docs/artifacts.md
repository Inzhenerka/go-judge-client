# Files, artifacts and budgets

`ExecutionRequest.files` explicitly maps paths to UTF-8 text or bytes. Strings never denote local paths
or URLs. Finite stdin is a memory file at descriptor 0; descriptors 1 and 2 stream byte-preserving output.
The client sends one request and half-closes its sending direction without cancelling execution.

Paths cannot be absolute, drive-prefixed, contain backslashes, NULs, colons, empty components, `.` or `..`.
Input file/directory prefix collisions and duplicate expected paths are rejected. Expected paths cannot
end with `?`, the upstream optional marker. Unicode and spaces are supported within configured bounds.

Request artifacts using `ExpectedFile(path=..., required=True/False)`. The SDK uses inline `copyOut` with a
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
The CLI retains defensive Windows path checks, although Windows is not a supported target.
These checks reject reserved device names, invalid characters and components ending in a
space or dot, including in the output directory. These names remain valid remote POSIX names where
applicable; they can still be consumed as bytes through the SDK.

The pinned real server rejected a workspace symlink during `Open` with `CopyOutOpen: ... not a regular file`.
This observation does not establish general no-follow guarantees for other server versions or mounts.

## File transfer limitations

Artifacts are inline in one final response. Cached file IDs, streamed upload/download and interactive
stdin are not implemented. Large-file workflows need a separate transfer design with explicit ownership,
size limits, deletion and server-side expiry; the client does not switch transfer modes automatically.

## Text output

Use `execution.text_events(encoding="utf-8", errors="replace")` inside the execution context to
receive `TextOutput(stream="stdout" | "stderr", text=...)` instead of byte `Output` events.
`Artifact` and `Finished` pass through unchanged. Decoders are independent for stdout and stderr;
characters split across wire messages are joined, empty text events are suppressed, and trailing
text is emitted before `Finished` only after successful RPC termination. Events are chunks, not lines.
Transport errors propagate without a final flush or `Finished`; already delivered text remains provisional.
With `errors="strict"`, decoding errors propagate and close the local execution.

Choose byte iteration or one text iterator for the lifetime of an execution; switching readers midway
or creating a second text iterator raises `ClientStateError`. Always keep the execution context around
the loop, including when breaking early. Text decoding does not change byte-based output budgets or
captured results. `TextDecoder` remains available for manual decoding.

`result.stdout_text(encoding="utf-8", errors="replace")` and `result.stderr_text(...)` decode captured
bytes. They return `None` when capture was disabled and `""` for empty captured output.
