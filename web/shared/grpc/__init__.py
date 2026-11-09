"""The messages the parties' web apps send each other over gRPC
(web/shared/grpc/messages.proto).

messages_pb2*.py and .pyi are generated from the proto, never edited. After
changing the proto, regenerate them from the repository's root:

    uv run python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
        --mypy_out=. --mypy_grpc_out=. web/shared/grpc/messages.proto
"""

# The command above, used by the test that checks the generated code is current.
GENERATE = (
    "grpc_tools.protoc",
    "-I.",
    "--python_out=.",
    "--grpc_python_out=.",
    "--mypy_out=.",
    "--mypy_grpc_out=.",
    "web/shared/grpc/messages.proto",
)
