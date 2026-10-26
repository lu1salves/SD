"""Servico de Nomes (Name Service).

Mantem, em memoria, um mapa nome -> endereco e expoe as operacoes
bind / lookup / unbind / rebind via gRPC para que servidores de
aplicacao se registrem e clientes descubram seus enderecos.
"""

import os
import sys
import threading
from concurrent import futures

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import name_service_pb2
import name_service_pb2_grpc

PORT = 50050


class NameServiceServicer(name_service_pb2_grpc.NameServiceServicer):
    def __init__(self):
        self._registro = {}
        self._lock = threading.Lock()

    def Bind(self, request, context):
        with self._lock:
            if request.name in self._registro:
                return name_service_pb2.BindReply(
                    success=False,
                    message=f"Nome '{request.name}' ja esta registrado",
                )
            self._registro[request.name] = request.address
            print(f"[BIND] {request.name} -> {request.address}")
            return name_service_pb2.BindReply(success=True, message="ok")

    def Lookup(self, request, context):
        with self._lock:
            address = self._registro.get(request.name)
        if address is None:
            return name_service_pb2.LookupReply(
                found=False, address="", message=f"Nome '{request.name}' nao encontrado"
            )
        print(f"[LOOKUP] {request.name} -> {address}")
        return name_service_pb2.LookupReply(found=True, address=address, message="ok")

    def Unbind(self, request, context):
        with self._lock:
            if request.name not in self._registro:
                return name_service_pb2.UnbindReply(
                    success=False,
                    message=f"Nome '{request.name}' nao encontrado",
                )
            del self._registro[request.name]
            print(f"[UNBIND] {request.name}")
            return name_service_pb2.UnbindReply(success=True, message="ok")

    def Rebind(self, request, context):
        with self._lock:
            existia = request.name in self._registro
            self._registro[request.name] = request.address
            print(f"[REBIND] {request.name} -> {request.address}")
            return name_service_pb2.RebindReply(
                success=True,
                message="atualizado" if existia else "criado",
            )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    name_service_pb2_grpc.add_NameServiceServicer_to_server(NameServiceServicer(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"Servico de Nomes rodando na porta {PORT}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
