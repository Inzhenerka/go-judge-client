# Protocol provenance

The six root `.proto` files are unmodified from `github.com/criyle/go-judge/pb` v1.4.1,
the module used by Go Judge v1.14.0 (`ad9339e537d3336fb9daf62342d6a73ce27d15c6`).
Compared with the schemas used by v1.13.3, `response.proto` adds the `exitOrder` field.
The upstream MIT license is in `LICENSE`.

`google/protobuf/go_features.proto` is from protocolbuffers/protobuf-go `v1.36.11`;
its BSD license is `PROTOBUF_LICENSE`. `empty.proto` and `descriptor.proto` are the compiler's
well-known definitions shipped with `grpcio-tools==1.84.0`. SHA-256 digests of the LF-normalized vendored files are in `checksums.json`.
The well-known definitions were compared with the pinned compiler package after newline normalization.

Edition 2023, implicit field presence and Go feature options are preserved. Generation compiles the
Go feature descriptor into a private Python module and changes only Python imports/module names.
Well-known runtime descriptors are supplied by the declared protobuf dependency. No global aliases
or `sys.path` modifications are used. See `scripts/generate_proto.py` and `scripts/check_proto.py`.
