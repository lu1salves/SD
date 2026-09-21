from socket  import *
from constCS import * #-

s = socket(AF_INET, SOCK_STREAM)
s.connect((HOST, PORT)) # connect to server (block until accepted)

# Uma unica requisicao chamando varias funcionalidades diferentes do
# servidor, separadas por ';'. Cada comando tem o formato NOME:arg1:arg2
requisicao = "SOMA:3:4;SUB:10:2;MAIUSCULA:ola mundo;INVERTER:distribuidos"

s.send(str.encode(requisicao))  # send some data
data = s.recv(1024)     # receive the response
print (bytes.decode(data))            # print the result
s.close()               # close the connection