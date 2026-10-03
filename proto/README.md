# Protocol provenance

Six root `.proto` files are unmodified from criyle/go-judge commit
`e9d70a0d9a3df0c62182a6e7090d7af650a1d5f8`, observed upstream HEAD on 2026-09-28.
The upstream MIT license is in `LICENSE`.

`google/protobuf/go_features.proto` is from protocolbuffers/protobuf-go `v1.36.11`;
its BSD license is `PROTOBUF_LICENSE`. `empty.proto` and `descriptor.proto` are the compiler's
well-known definitions shipped with `grpcio-tools==1.78.0`. SHA-256 digests are in `checksums.json`.

Edition 2023, implicit field presence and Go feature options are preserved. Generation compiles the
Go feature descriptor into a private Python module and changes only Python imports/module names.
Well-known runtime descriptors are supplied by the declared protobuf dependency. No global aliases
or `sys.path` modifications are used. See `scripts/generate_proto.py` and `scripts/check_proto.py`.
