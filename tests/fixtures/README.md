# Synthetic test TLS identity

`localhost.crt` and `localhost.key` are a public, self-signed test identity for loopback gRPC fixtures only.
They are not production credentials. Never trust this certificate outside disposable tests.

Generated with OpenSSL using RSA-2048 and SAN `DNS:localhost,IP:127.0.0.1`, valid for ten years from
2026-09-28. Regenerate if test clock falls outside the validity interval.
