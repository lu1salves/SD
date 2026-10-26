"""Cliente que descobre os servicos via Servico de Nomes e faz chamadas gRPC.

Fluxo:
  1. lookup("CalculatorService") e lookup("TextService") no Servico de Nomes
  2. abre um canal gRPC para cada endereco retornado
  3. chama as funcionalidades de cada servico de aplicacao

Uso:
    python client.py [endereco_name_service]

Exemplo:
    python client.py 192.168.0.5:50050
"""

import os
import sys

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import calculator_service_pb2
import calculator_service_pb2_grpc
import text_service_pb2
import text_service_pb2_grpc
import name_client


def descobrir_servico(name_service_address, nome):
    reply = name_client.lookup(name_service_address, nome)
    if not reply.found:
        raise RuntimeError(f"Servico '{nome}' nao encontrado no Servico de Nomes: {reply.message}")
    print(f"Lookup('{nome}') -> {reply.address}")
    return reply.address


def main():
    name_service_address = sys.argv[1] if len(sys.argv) > 1 else "localhost:50050"

    calc_address = descobrir_servico(name_service_address, "CalculatorService")
    text_address = descobrir_servico(name_service_address, "TextService")

    with grpc.insecure_channel(calc_address) as channel:
        calc_stub = calculator_service_pb2_grpc.CalculatorStub(channel)
        soma = calc_stub.Soma(calculator_service_pb2.TwoNumbersRequest(a=3, b=4))
        sub = calc_stub.Subtracao(calculator_service_pb2.TwoNumbersRequest(a=10, b=2))
        print(f"Soma(3, 4) = {soma.result}")
        print(f"Subtracao(10, 2) = {sub.result}")

    with grpc.insecure_channel(text_address) as channel:
        text_stub = text_service_pb2_grpc.TextProcessorStub(channel)
        maiuscula = text_stub.Maiuscula(text_service_pb2.TextRequest(texto="ola mundo"))
        inverso = text_stub.Inverter(text_service_pb2.TextRequest(texto="distribuidos"))
        print(f"Maiuscula('ola mundo') = {maiuscula.resultado}")
        print(f"Inverter('distribuidos') = {inverso.resultado}")


if __name__ == "__main__":
    main()
