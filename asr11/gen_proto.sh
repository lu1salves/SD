#!/usr/bin/env bash
# Regenera os stubs gRPC a partir dos arquivos .proto em proto/.
set -e
cd "$(dirname "$0")"
python -m grpc_tools.protoc \
  -I proto \
  --python_out=generated \
  --grpc_python_out=generated \
  proto/name_service.proto proto/calculator_service.proto proto/text_service.proto
