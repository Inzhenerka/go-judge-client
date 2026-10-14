FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS build
ARG GO_JUDGE_REV=4ebd2ffe9474639c665fa21cfb438f68820fe77c
ADD https://github.com/criyle/go-judge/archive/${GO_JUDGE_REV}.tar.gz /tmp/source.tar.gz
RUN mkdir /src && tar xzf /tmp/source.tar.gz --strip-components=1 -C /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /go-judge ./cmd/go-judge

FROM python:3.13-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
RUN python -m venv /usr/local/runtimes/python-data
COPY --from=build /go-judge /usr/local/bin/go-judge
ENTRYPOINT ["/usr/local/bin/go-judge"]
CMD ["-enable-grpc", "-grpc-addr", ":5051"]
