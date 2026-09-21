from socket import *
from constCS import * #-

# Funcionalidades que o servidor disponibiliza ao cliente.
# Cada uma recebe os argumentos já como strings (vindos da rede).
def soma(a, b):
    return str(float(a) + float(b))

def subtracao(a, b):
    return str(float(a) - float(b))

def maiuscula(texto):
    return texto.upper()

def inverter(texto):
    return texto[::-1]

FUNCOES = {
    'SOMA': soma,
    'SUB': subtracao,
    'MAIUSCULA': maiuscula,
    'INVERTER': inverter,
}

def processar_comando(comando):
    # Formato de cada comando: NOME:arg1:arg2:...
    partes = comando.strip().split(':')
    nome = partes[0].upper()
    args = partes[1:]
    funcao = FUNCOES.get(nome)
    if funcao is None:
        return f"ERRO: funcionalidade '{nome}' desconhecida"
    try:
        return funcao(*args)
    except Exception as e:
        return f"ERRO: {e}"

def processar_requisicao(requisicao):
    # Uma requisicao pode conter varios comandos separados por ';',
    # permitindo chamar mais de uma funcionalidade de uma vez.
    comandos = requisicao.split(';')
    resultados = [processar_comando(c) for c in comandos if c.strip()]
    return ';'.join(resultados)

s = socket(AF_INET, SOCK_STREAM)
s.bind((HOST, PORT))  #-
s.listen(1)           #-
(conn, addr) = s.accept()  # returns new socket and addr. client
while True:                # forever
    data = conn.recv(1024)   # receive data from client
    if not data: break       # stop if client stopped
    requisicao = bytes.decode(data)
    print("Requisicao recebida:", requisicao)
    resposta = processar_requisicao(requisicao)
    print("Resposta enviada:", resposta)
    conn.send(str.encode(resposta))  # return the processed result
conn.close()               # close the connection
