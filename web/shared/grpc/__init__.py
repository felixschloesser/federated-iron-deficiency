"""The messages between the parties' web apps over gRPC
(web/shared/grpc/messages.proto).

messages_pb2*.py and .pyi are generated from the proto, never edited. After
changing the proto, regenerate them from the repository's root:

    uv run python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
        --mypy_out=. --mypy_grpc_out=. buf/validate/validate.proto \
        web/shared/grpc/messages.proto

buf/validate/validate.proto is protovalidate's (Buf, Apache 2.0, v1.2.2),
copied unchanged: its path is the one every validator expects.
"""

# The command above, for the test that checks the generated code is current.
GENERATE = (
    "grpc_tools.protoc",
    "-I.",
    "--python_out=.",
    "--grpc_python_out=.",
    "--mypy_out=.",
    "--mypy_grpc_out=.",
    "buf/validate/validate.proto",
    "web/shared/grpc/messages.proto",
)
