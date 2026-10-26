"""Funcoes auxiliares para falar com o Servico de Nomes.

Usado tanto pelos servidores de aplicacao (para fazer bind/rebind/unbind
do seu endereco) quanto pelo cliente final (para fazer lookup).
"""

import os
import sys

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import name_service_pb2
import name_service_pb2_grpc


def bind(name_service_address, name, address):
    with grpc.insecure_channel(name_service_address) as channel:
        stub = name_service_pb2_grpc.NameServiceStub(channel)
        return stub.Bind(name_service_pb2.BindRequest(name=name, address=address))


def lookup(name_service_address, name):
    with grpc.insecure_channel(name_service_address) as channel:
        stub = name_service_pb2_grpc.NameServiceStub(channel)
        return stub.Lookup(name_service_pb2.LookupRequest(name=name))


def unbind(name_service_address, name):
    with grpc.insecure_channel(name_service_address) as channel:
        stub = name_service_pb2_grpc.NameServiceStub(channel)
        return stub.Unbind(name_service_pb2.UnbindRequest(name=name))


def rebind(name_service_address, name, address):
    with grpc.insecure_channel(name_service_address) as channel:
        stub = name_service_pb2_grpc.NameServiceStub(channel)
        return stub.Rebind(name_service_pb2.RebindRequest(name=name, address=address))
