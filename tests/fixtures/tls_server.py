"""Disposable TLS peer in a separate process, matching deployed transport ownership."""

import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import grpc

from go_judge_client._grpc.judge_pb2_grpc import ExecutorServicer, add_ExecutorServicer_to_server
from go_judge_client._grpc.response_pb2 import Response
from go_judge_client._grpc.stream_request_pb2 import StreamRequest
from go_judge_client._grpc.stream_response_pb2 import StreamResponse


class Executor(ExecutorServicer):
    def ExecStream(
        self, request_iterator: Iterator[StreamRequest], context: grpc.ServicerContext
    ) -> Iterator[StreamResponse]:
        metadata = dict(context.invocation_metadata())
        if metadata.get("authorization") != "Bearer synthetic-secret":
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Test credential required")
        assert len(list(request_iterator)) == 1
        yield StreamResponse(execResponse=Response(results=[Response.Result(status=Response.Result.Accepted)]))


def main() -> None:
    cert = Path(sys.argv[1]).read_bytes()
    key = Path(sys.argv[2]).read_bytes()
    mutual = sys.argv[3] == "1"
    with ThreadPoolExecutor(max_workers=2) as pool:
        server = grpc.server(pool)
        add_ExecutorServicer_to_server(Executor(), server)
        port = server.add_secure_port(
            "127.0.0.1:0",
            grpc.ssl_server_credentials(
                ((key, cert),), root_certificates=cert if mutual else None, require_client_auth=mutual
            ),
        )
        server.start()
        print(port, flush=True)
        sys.stdin.readline()
        assert server.stop(0).wait(3), "TLS peer did not stop"


if __name__ == "__main__":
    main()
