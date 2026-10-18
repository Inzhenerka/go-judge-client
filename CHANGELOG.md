# CHANGELOG


## v0.3.0 (2026-10-18)

### Continuous Integration

- Raise integration sandbox memory to 2 GiB
  ([`f8c5009`](https://github.com/Inzhenerka/go-judge-client/commit/f8c500944ef9ef213e1c073c761ec9bfc821a55d))

### Features

- Improve execution defaults and expose CLI resource limits
  ([`1606e9d`](https://github.com/Inzhenerka/go-judge-client/commit/1606e9dcb8ae97e1cfe4cf2fa919e4955d1bf5f1))


## v0.2.0 (2026-10-14)

### Features

- Separate queued execution from streaming and add health checks
  ([`764256f`](https://github.com/Inzhenerka/go-judge-client/commit/764256fbb4f662087702cfe67f5b68a9cce8f2e9))


## v0.1.1 (2026-10-14)

### Bug Fixes

- **deps**: Refresh Python dependencies and sandbox runtime
  ([`017f0bf`](https://github.com/Inzhenerka/go-judge-client/commit/017f0bff5af1335375de1d466b5cfd3c2d461708))

### Continuous Integration

- Separate uv cache keys for concurrent jobs
  ([`92d8004`](https://github.com/Inzhenerka/go-judge-client/commit/92d8004f0f88d1e06b61f1f4ec48f0b246922c0e))

- Update actions to Node 24 and pin Ubuntu 24.04
  ([`a086460`](https://github.com/Inzhenerka/go-judge-client/commit/a086460882067e8d91362e9ddaee8a7310898e58))


## v0.1.0 (2026-10-14)

### Bug Fixes

- Clarify CLI file boundaries and preserve safe error diagnostics
  ([`eaa3540`](https://github.com/Inzhenerka/go-judge-client/commit/eaa3540ef063b524b4601595b1ceb32ca2681987))

- Defer wire allocation until admission and share cleanup semantics
  ([`7596033`](https://github.com/Inzhenerka/go-judge-client/commit/75960332541e4579da6c52d8ddd1ce87691df10c))

- Explain configuration failures with safe validation codes
  ([`e693444`](https://github.com/Inzhenerka/go-judge-client/commit/e693444b73aab1c24976b6e44acd4fd73a7d1d09))

- Make protobuf verification portable and complete
  ([`654c356`](https://github.com/Inzhenerka/go-judge-client/commit/654c35609e241aaba908d15c0eacd53f8ad17ad5))

- Make release publication retryable and validate distribution selection
  ([`0013b40`](https://github.com/Inzhenerka/go-judge-client/commit/0013b406562e12178ca8428c19fc1a3565d7fd28))

- Represent unspecified limit overrides explicitly
  ([`d0cbb84`](https://github.com/Inzhenerka/go-judge-client/commit/d0cbb84957c18c36d2044c210ab4fed58d015eda))

### Chores

- Ignore IDE project files
  ([`a9f7ae6`](https://github.com/Inzhenerka/go-judge-client/commit/a9f7ae6fa917d59a7d6d953b81250f161bdf61f4))

- Prepare public package and record release verification
  ([`696f406`](https://github.com/Inzhenerka/go-judge-client/commit/696f40683ccb03c9ad6062431f5659fba87820f2))

### Continuous Integration

- Automate semantic releases and optional PyPI publishing
  ([`0576305`](https://github.com/Inzhenerka/go-judge-client/commit/0576305b3b0985e13ac824cc88150b37cfccb514))

- Limit supported platform and release checks to Linux
  ([`a036fd4`](https://github.com/Inzhenerka/go-judge-client/commit/a036fd48af936e9f1c1d0e808f3a86121325aa51))

### Features

- Add atomic artifact overwrite option to CLI
  ([`1bf4d2d`](https://github.com/Inzhenerka/go-judge-client/commit/1bf4d2d91795fe9c3d1d6d9feea810af3b0a7a88))

- Add text event streaming and captured output helpers
  ([`cced944`](https://github.com/Inzhenerka/go-judge-client/commit/cced944888765e42203664e044b31c8db071d41c))

- Client works
  ([`60aee74`](https://github.com/Inzhenerka/go-judge-client/commit/60aee74019b56fffbf6c33c637868d530095c044))

- Improve limit inheritance and client ergonomics
  ([`8608f17`](https://github.com/Inzhenerka/go-judge-client/commit/8608f1775e67d6a5896b7f84dea0a4e594582b25))
