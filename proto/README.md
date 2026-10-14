# Protocol provenance

Six root `.proto` files are unmodified from criyle/go-judge commit
`4ebd2ffe9474639c665fa21cfb438f68820fe77c` (v1.13.3), verified on 2026-10-14.
These schemas are byte-identical to the previously pinned `e9d70a0` revision.
The upstream MIT license is in `LICENSE`.

`google/protobuf/go_features.proto` is from protocolbuffers/protobuf-go `v1.36.11`;
its BSD license is `PROTOBUF_LICENSE`. `empty.proto` and `descriptor.proto` are the compiler's
well-known definitions shipped with `grpcio-tools==1.84.0`. SHA-256 digests of the LF-normalized vendored files are in `checksums.json`.
The well-known definitions were compared with the pinned compiler package after newline normalization.

Edition 2023, implicit field presence and Go feature options are preserved. Generation compiles the
Go feature descriptor into a private Python module and changes only Python imports/module names.
Well-known runtime descriptors are supplied by the declared protobuf dependency. No global aliases
or `sys.path` modifications are used. See `scripts/generate_proto.py` and `scripts/check_proto.py`.
