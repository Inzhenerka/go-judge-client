FROM golang:1.26.1-bookworm@sha256:ab3d6955bbc813a0f3fdf220c1d817dd89c0b3f283777db8ece4a32fe7858edd AS build
ARG GO_JUDGE_REV=e9d70a0d9a3df0c62182a6e7090d7af650a1d5f8
ADD https://github.com/criyle/go-judge/archive/${GO_JUDGE_REV}.tar.gz /tmp/source.tar.gz
RUN mkdir /src && tar xzf /tmp/source.tar.gz --strip-components=1 -C /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /go-judge ./cmd/go-judge

FROM python:3.13-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN python -m venv /usr/local/runtimes/python-data
COPY --from=build /go-judge /usr/local/bin/go-judge
ENTRYPOINT ["/usr/local/bin/go-judge"]
CMD ["-enable-grpc", "-grpc-addr", ":5051"]
