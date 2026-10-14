# Security boundary

This package is a client, not a sandbox security boundary. Treat runtime profiles as trusted configuration
and remote output/diagnostics as untrusted data. Report vulnerabilities privately to [info@inzhenerka.tech](mailto:info@inzhenerka.tech).
Include the affected version, expected and actual behavior, and a minimal reproduction using synthetic data.
Do not post credentials, submitted source or artifact contents in public reports.

Use authenticated TLS for remote deployment. The pinned upstream's plaintext listener and token-logging
caveat are documented in `docs/lifecycle-and-security.md`. Test fixtures contain a deliberately public
loopback TLS identity and synthetic tokens only. They must never be used in production.

Application authorization, quotas, durable attempts, sandbox isolation, aggregate admission, mounts,
runtime updates, egress, credential scoping and artifact access control remain deployment responsibilities.
