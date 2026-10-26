"""Segundo servico de aplicacao: TextProcessor.

Roda em um processo (e, tipicamente, maquina) separado do Calculator e
do Servico de Nomes. Ao iniciar, registra seu endereco no Servico de
Nomes com bind(); ao ser encerrado (Ctrl+C), remove o registro com
unbind().

Uso:
    python text_server.py [porta] [host_anunciado] [endereco_name_service]

Exemplo:
    python text_server.py 50052 192.168.0.11 192.168.0.5:50050
"""

import os
import sys
from concurrent import futures

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import text_service_pb2
import text_service_pb2_grpc
import name_client

SERVICE_NAME = "TextService"


class TextProcessorServicer(text_service_pb2_grpc.TextProcessorServicer):
    def Maiuscula(self, request, context):
        return text_service_pb2.TextReply(resultado=request.texto.upper())

    def Inverter(self, request, context):
        return text_service_pb2.TextReply(resultado=request.texto[::-1])


def serve():
    port = sys.argv[1] if len(sys.argv) > 1 else "50052"
    host_anunciado = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    name_service_address = sys.argv[3] if len(sys.argv) > 3 else "localhost:50050"

    endereco_proprio = f"{host_anunciado}:{port}"

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    text_service_pb2_grpc.add_TextProcessorServicer_to_server(TextProcessorServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"TextService escutando em {endereco_proprio}")

    reply = name_client.bind(name_service_address, SERVICE_NAME, endereco_proprio)
    if not reply.success:
        print(f"Aviso: falha ao registrar no Servico de Nomes: {reply.message}")
        print("Tentando rebind (atualizar registro existente)...")
        name_client.rebind(name_service_address, SERVICE_NAME, endereco_proprio)
    else:
        print(f"Registrado no Servico de Nomes como '{SERVICE_NAME}'")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        pass
    finally:
        name_client.unbind(name_service_address, SERVICE_NAME)
        print(f"Registro '{SERVICE_NAME}' removido do Servico de Nomes")


if __name__ == "__main__":
    serve()
