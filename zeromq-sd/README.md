# ZeroMQ em máquinas diferentes: Req‑Rep, Pub‑Sub e Pipeline estendidos

Trabalho de **Sistemas Distribuídos**: a partir dos exemplos com ZeroMQ das
**Figs. 4.21, 4.22 e 4.23** (capítulo 4, *Comunicação*, do livro *Distributed
Systems* de M. van Steen e A. S. Tanenbaum), as aplicações foram executadas em
máquinas diferentes e ganharam novas funcionalidades.

| Figura | Padrão ZeroMQ | Código original (pacote `.zip`) | Versão estendida |
|---|---|---|---|
| 4.21 | Request‑Reply (`REQ`/`REP`) | [`original/04-22/`](original/04-22) | [`reqrep/`](reqrep) |
| 4.22 | Publish‑Subscribe (`PUB`/`SUB`) | [`original/04-23/`](original/04-23) | [`pubsub/`](pubsub) |
| 4.23 | Pipeline (`PUSH`/`PULL`) | [`original/04-24/`](original/04-24) | [`pipeline/`](pipeline) |

> No pacote fornecido as pastas se chamam `04-22`, `04-23` e `04-24`. Elas
> foram mantidas **sem alteração** em [`original/`](original) para comparação.

---

## Sumário

1. [Estrutura do repositório](#1-estrutura-do-repositório)
2. [Instalação](#2-instalação)
3. [Request‑Reply (Fig. 4.21)](#3-request-reply-fig-421)
4. [Publish‑Subscribe (Fig. 4.22)](#4-publish-subscribe-fig-422)
5. [Pipeline (Fig. 4.23)](#5-pipeline-fig-423)
6. [Executando em máquinas diferentes na AWS](#6-executando-em-máquinas-diferentes-na-aws)
7. [Teste multi‑máquina local (rede simulada) e resultados](#7-teste-multi-máquina-local-rede-simulada-e-resultados)
8. [Testes automatizados](#8-testes-automatizados)
9. [Observações sobre o ZeroMQ](#9-observações-sobre-o-zeromq-aprendidas-nos-testes)

---

## 1. Estrutura do repositório

```
original/          código do pacote, sem alterações (referência)
common/util.py     endereços, serialização JSON, identificação da máquina, estatísticas
reqrep/            server.py, client.py, broker.py          (Fig. 4.21)
pubsub/            publisher.py, subscriber.py, proxy.py, chat.py   (Fig. 4.22)
pipeline/          ventilator.py, worker.py, sink.py        (Fig. 4.23)
aws/               provisionar.sh, destruir.sh, user-data.sh (EC2 via AWS CLI)
scripts/           setup.sh (venv + pyzmq), rede_simulada.sh, demo_rede_simulada.sh
tests/             testes de integração (pytest)
docs/              saída completa da demonstração em rede simulada
```

Mudança comum às três aplicações: **os IPs não ficam mais fixos no código**
(`constCS.py`, `constPS.py`, `constPipe.py`). Tudo é passado por argumentos
(`--server`, `--connect`, `--sources`, `--sink`...) ou variáveis de ambiente,
e quem faz *bind* usa `*` (todas as interfaces). Isso é o que permite rodar o
mesmo código em qualquer máquina, inclusive na AWS, onde o IP público não
aparece na interface de rede da instância. Todo programa aceita `--help`.

## 2. Instalação

Em **cada máquina** que for rodar os programas (Python ≥ 3.8):

```bash
git clone <URL-deste-repositório> zeromq-sd
cd zeromq-sd
python3 -m venv .venv            # ambiente virtual, como recomendado
source .venv/bin/activate
pip install -r requirements.txt  # = pip install pyzmq
```

Ou simplesmente `bash scripts/setup.sh` (faz o mesmo e instala o `python3-venv`
se faltar). Na AWS isso é feito automaticamente pelo `aws/user-data.sh`.

---

## 3. Request‑Reply (Fig. 4.21)

**Original:** o servidor faz *bind* em duas portas num IP fixo, devolve a
mensagem recebida com um `*` no final e para quando recebe `STOP`. Os clientes
mandam uma única mensagem.

**Funcionalidades novas**

| | Descrição |
|---|---|
| Protocolo de comandos | Pedidos em JSON: `ECHO`, `UPPER`, `REVERSE`, `WORDS`, `CALC <expr>`, `TIME`, `HOST`, `SLEEP <s>`, `STATS`, `HELP`, `STOP`. Toda resposta diz **qual máquina** atendeu. |
| Compatibilidade | Texto puro continua recebendo `*` e `STOP` continua parando o servidor: **os clientes originais funcionam com o servidor novo**. |
| `CALC` seguro | Avalia aritmética com `ast` (sem `eval`), rejeitando nomes, chamadas e expoentes enormes. |
| Erros não derrubam o servidor | Comando inválido vira resposta `ok=false`. |
| Cliente confiável (*Lazy Pirate*) | Timeout + novas tentativas. No original, se o servidor estivesse fora, o cliente ficava bloqueado para sempre em `recv()`. |
| Vários servidores | Um `REQ` pode se conectar a vários servidores (`--server A --server B`); o ZeroMQ distribui em round‑robin. |
| Broker `ROUTER/DEALER` | `broker.py`: clientes só conhecem o broker; servidores em qualquer máquina se conectam ao backend e entram/saem a qualquer momento (balanceamento e tolerância a falha de um servidor). |
| Benchmark | `--bench N` mede RTT (mín/média/mediana/p95/máx), vazão e distribuição entre servidores. |
| REPL | Sem comando, o cliente abre um prompt interativo. |
| Estatísticas | `STATS` mostra uptime e contagem por comando e por cliente. |

**Como usar** (troque `IP_M1` pelo IP da máquina do servidor):

```bash
# Máquina 1 – servidor (bind em *:5555 e *:5556, como o original)
python3 reqrep/server.py

# Máquina 2 – cliente
python3 reqrep/client.py --server IP_M1:5555 CALC "(2+3)*7"     # OK 35 [servidor...]
python3 reqrep/client.py --server IP_M1:5556 UPPER sistemas distribuidos
python3 reqrep/client.py --server IP_M1:5555                     # modo interativo
python3 reqrep/client.py --server IP_M1:5555 --bench 1000 --payload 64
```

**Com broker** (vários servidores em máquinas diferentes):

```bash
python3 reqrep/broker.py                                   # M1: clientes :5559, servidores :5560
python3 reqrep/server.py --connect IP_M1:5560 --no-stop   # M2, M3, M4 ...
python3 reqrep/client.py --server IP_M1:5559 --bench 300  # qualquer máquina
```

O benchmark mostra a divisão dos pedidos (33 % para cada um de 3 servidores).
Se um servidor for derrubado, os seguintes vão para os que sobraram.

## 4. Publish‑Subscribe (Fig. 4.22)

**Original:** o publicador envia `TIME <hora>` a cada 5 s; o assinante assina
`TIME`, imprime 5 mensagens e termina.

**Funcionalidades novas**

| | Descrição |
|---|---|
| Vários tópicos | `TIME` (como antes), `SYS` (carga de CPU e memória da máquina publicadora), `SENSOR` (temperatura simulada) e `ALERT` (só quando o sensor passa de `--limite`). |
| Metadados | Cada mensagem leva publicador, **nº de sequência** por tópico e **timestamp**. Continua sendo um frame `"TOPICO <json>"`, então **o `subscriber.py` original ainda funciona**. |
| Detecção de perdas | O assinante acusa lacunas na sequência (o PUB‑SUB do ZeroMQ não garante entrega). |
| Latência | Calcula a latência ponta a ponta por tópico (requer relógios sincronizados; veja §9). |
| Fan‑in | O assinante pode se conectar a vários publicadores ao mesmo tempo. |
| Proxy `XSUB/XPUB` | `proxy.py`: publicadores e assinantes só conhecem o proxy; o proxy mostra as assinaturas que sobem dos assinantes para os publicadores. |
| Chat | `chat.py`: chat em grupo por salas (tópico `CHAT.<sala>`) usando o proxy. |
| Resumo | Ao final, recebidas/perdidas/latência por tópico e mensagens por publicador. |

**Como usar:**

```bash
# Direto, como no original (M1 publica, M2 assina)
python3 pubsub/publisher.py                       # bind *:5557, 1 rodada/s
python3 pubsub/publisher.py --interval 5 --topics TIME   # comportamento original
python3 pubsub/subscriber.py --connect IP_M1:5557 --topics TIME SENSOR --count 20

# Com proxy (M1) e publicadores em M2 e M3
python3 pubsub/proxy.py                                     # M1: pubs :5561, subs :5562
python3 pubsub/publisher.py --connect IP_M1:5561            # M2 e M3
python3 pubsub/subscriber.py --connect IP_M1:5562 --topics ALERT        # M4
python3 pubsub/subscriber.py --connect IP_M1:5562 --duration 30 --quiet # só o resumo

# Chat (uma pessoa em cada máquina)
python3 pubsub/chat.py --proxy IP_M1 --nick ana --room sd
```

## 5. Pipeline (Fig. 4.23)

**Original:** exatamente duas fontes (`tasksrc.py 1` e `tasksrc.py 2`, IPs fixos)
mandam 100 cargas aleatórias (pickle) a 1 por segundo; os workers só imprimem
o que receberam e dormem `carga × 10 ms`, em laço infinito.

**Funcionalidades novas**

| | Descrição |
|---|---|
| Coletor (`sink.py`) | Terceiro estágio: os workers enviam resultados a um coletor, que mede **tempo total, vazão, paralelismo efetivo** e a distribuição de tarefas por worker e por fonte. |
| Fim de lote | Cada fonte avisa ao coletor quantas tarefas vai mandar; quando todas chegam, o coletor publica `KILL` (canal `PUB/SUB`) e os workers encerram sozinhos com suas estatísticas. |
| N fontes, N workers | `--sources h1:5563 h2:5564 ...` — qualquer quantidade, em qualquer máquina. |
| Trabalho real | `--mode primes`: o worker conta primos (CPU de verdade) em vez de dormir; assim o ganho de colocar workers em máquinas diferentes é real. `--mode sleep` mantém o comportamento original. |
| JSON em vez de pickle | Desserializar pickle recebido da rede permite execução remota de código. |
| Slow joiner | A fonte espera os workers se conectarem (`--wait` ou `--enter`) antes de enviar. |
| Experimentos | `--tasks`, `--rate`, `--max-load`, `--seed` e `sink.py --csv` geram tabelas de speedup. |

**Como usar** (coletor em M1; fontes em M1 e M2; workers em M2..M4):

```bash
python3 pipeline/sink.py --sources 2 --csv resultados.csv --label "3 workers"  # M1
python3 pipeline/worker.py --sources IP_M1:5563 IP_M2:5564 --sink IP_M1       # M2, M3, M4
python3 pipeline/ventilator.py --id 1 --sink IP_M1 --tasks 100 --mode primes   # M1 (bind :5563)
python3 pipeline/ventilator.py --id 2 --sink IP_M1 --tasks 100 --mode primes   # M2 (bind :5564)
```

A fonte com `--id N` faz bind na porta `5562 + N` (1 → 5563, 2 → 5564), como
`PORT1`/`PORT2` do original. Repita com 1, 2 e 3 workers para montar a tabela
de speedup em `resultados.csv`.

---

## 6. Executando em máquinas diferentes na AWS

### 6.1 Topologia sugerida (4 instâncias EC2 `t3.micro`, Ubuntu 24.04)

| Instância | Req‑Rep | Pub‑Sub | Pipeline |
|---|---|---|---|
| `zmq-sd-1` (M1) | servidor / broker | proxy, assinante de `ALERT` | coletor, fonte 1 |
| `zmq-sd-2` (M2) | cliente / servidor | publicador | fonte 2, worker |
| `zmq-sd-3` (M3) | servidor | publicador | worker |
| `zmq-sd-4` (M4) | servidor | assinante, chat | worker |

### 6.2 Criando as instâncias

**Opção A – script (AWS CLI):** com o AWS CLI configurado (`aws configure`) e
um par de chaves EC2 existente:

```bash
KEY_NAME=minha-chave REPO_URL=https://github.com/<usuario>/zeromq-sd.git \
    bash aws/provisionar.sh          # cria SG + 4 instâncias, já com venv e pyzmq
# ... experimentos ...
bash aws/destruir.sh                 # encerra tudo (evita cobranças)
```

**Opção B – console da AWS:**

1. *EC2 → Launch instances*: Ubuntu Server 24.04, `t3.micro`, *Number of
   instances* = 4, seu par de chaves.
2. *Security group* novo com as regras de entrada:
   - SSH (TCP 22) — origem: *My IP*;
   - TCP **5555–5570** — origem: **o próprio security group** (`sg-...`).
     Assim só as instâncias do grupo conversam nessas portas.
3. Em *Advanced details → User data*, cole o conteúdo de `aws/user-data.sh`
   (o repositório precisa ser **público** para o clone automático funcionar)
   trocando `__REPO_URL__` pela URL do repositório (ou rode
   `bash scripts/setup.sh` depois de clonar em cada instância).
4. Anote o **IP privado** (`172.31.x.x`) de cada instância.

> **IP privado × público.** Dentro da mesma VPC use os IPs **privados**: o
> tráfego não sai da AWS, é mais rápido e não precisa abrir portas para a
> internet. O IP público só é usado para SSH (ou para testes entre regiões,
> §6.4). Como os programas fazem bind em `*`, não é preciso configurar IP algum
> no lado do servidor — a causa nº 1 de "não conecta" na AWS é fazer bind no
> IP público, que não existe na interface da instância.

### 6.3 Roteiro de experimentos

Em cada instância: `ssh -i chave.pem ubuntu@<IP_PUBLICO>`, depois
`cd ~/zeromq-sd && source .venv/bin/activate`. Abaixo, `M1`... são os IPs
privados.

```bash
# --- Req-Rep: mesma máquina x máquinas diferentes
M1$ python3 reqrep/server.py --quiet
M1$ python3 reqrep/client.py --server 127.0.0.1:5555 --bench 1000 --payload 64
M2$ python3 reqrep/client.py --server $M1:5555     --bench 1000 --payload 64
M2$ cd original/04-22 && sed -i "s/^HOST .*/HOST = \"$M1\"/; s/4567/5555/" constCS.py \
      && python3 client1.py && git checkout constCS.py && cd -   # cliente ORIGINAL

# --- Req-Rep com broker e 3 servidores (depois derrube um com Ctrl+C e repita)
M1$ python3 reqrep/broker.py
M2,M3,M4$ python3 reqrep/server.py --connect $M1:5560 --no-stop --quiet
M1$ python3 reqrep/client.py --server $M1:5559 --bench 300

# --- Pub-Sub com proxy
M1$ python3 pubsub/proxy.py
M2,M3$ python3 pubsub/publisher.py --connect $M1:5561 --interval 0.5
M4$ python3 pubsub/subscriber.py --connect $M1:5562 --topics TIME SENSOR --duration 30 --quiet
M1$ python3 pubsub/subscriber.py --connect $M1:5562 --topics ALERT

# --- Pipeline: speedup com 1, 2 e 3 workers (modo CPU)
M1$ python3 pipeline/sink.py --sources 2 --csv pipeline.csv --label "N workers"
M2..M4$ python3 pipeline/worker.py --sources $M1:5563 $M2:5564 --sink $M1
M1$ python3 pipeline/ventilator.py --id 1 --sink $M1 --tasks 100 --mode primes --seed 1
M2$ python3 pipeline/ventilator.py --id 2 --sink $M1 --tasks 100 --mode primes --seed 2
```

Tabela para registrar os resultados obtidos na AWS:

| Experimento | Métrica | Resultado na AWS |
|---|---|---|
| Req‑Rep, mesma máquina (M1→M1) | RTT mediano / vazão | _preencher_ |
| Req‑Rep, máquinas diferentes (M2→M1) | RTT mediano / vazão | _preencher_ |
| Req‑Rep via broker, 3 servidores | distribuição / RTT mediano | _preencher_ |
| Pub‑Sub via proxy | latência mediana / perdas | _preencher_ |
| Pipeline `primes`, 1 / 2 / 3 workers | tempo total (s) | _preencher_ |

### 6.4 (Opcional) Teste entre regiões

Para sentir o efeito da distância, crie uma instância em outra região (ex.:
`sa-east-1` × `us-east-1`) e libere as portas para o IP público dela:

```bash
AWS_REGION=sa-east-1 N=1 KEY_NAME=chave-sp REPO_URL=... bash aws/provisionar.sh
AWS_REGION=us-east-1 N=1 KEY_NAME=chave-va REPO_URL=... EXTRA_CIDR=<IP_publico_SP>/32 bash aws/provisionar.sh
```

(para apagar depois: `AWS_REGION=<região> bash aws/destruir.sh` em cada uma)
e rode o benchmark do cliente em São Paulo contra o **IP público** do servidor
na Virgínia. O RTT passa de décimos de milissegundo para ~100 ms, e a vazão do
cliente sequencial cai na mesma proporção — o custo da comunicação síncrona.

---

## 7. Teste multi‑máquina local (rede simulada) e resultados

Para desenvolver e validar sem a AWS, `scripts/rede_simulada.sh` cria
"máquinas" num único Linux usando **namespaces de rede**: cada host tem pilha
TCP/IP, interface, IP (`10.20.0.1`–`10.20.0.4`) e hostname próprios, ligados
por uma bridge, como numa sub‑rede de VPC. A demonstração completa roda os
quatro cenários de uma vez:

```bash
sudo PY=.venv/bin/python scripts/demo_rede_simulada.sh   # saída em logs/
```

Resultados de uma execução (saída integral em
[`docs/demo_rede_simulada.txt`](docs/demo_rede_simulada.txt)):

| Cenário | Resultado |
|---|---|
| Cliente **original** (`client1.py`) em host2 → servidor novo em host1 | `Hello world 1*` (compatível) |
| Req‑Rep host1→host1 / host2→host1, 1000 pedidos | RTT mediano 0,239 ms / 0,239 ms; ~3.850 req/s |
| Broker em host1 + servidores em host2, host3, host4 | 100/100/100 pedidos (33 % cada) |
| … após derrubar o servidor de host3 | 150/150 entre host2 e host4, sem erro no cliente |
| Pub‑Sub via proxy, 2 publicadores, 6 s | 112 mensagens, **0 perdidas**, latência mediana 0,44–0,72 ms |
| Assinante só de `ALERT` | recebeu apenas os alertas (8), dos dois publicadores |
| Chat host2 ↔ host4 via proxy | mensagens entregues em ~1 ms |
| Pipeline `sleep`, 100 tarefas, 1 / 2 / 3 workers | **10,53 s / 5,74 s / 3,87 s** → speedup 1,83× e 2,72× |

Limitações honestas desta simulação: as "máquinas" compartilham o mesmo
kernel e os mesmos 2 núcleos de CPU, e a rede virtual não tem a latência de
uma rede física — por isso mesma máquina e máquinas diferentes dão RTT quase
igual aqui, e o pipeline foi medido no modo `sleep` (no modo `primes` o ganho
ficaria limitado aos 2 núcleos). Na AWS, cada instância tem CPU própria e a
rede real da VPC, então é lá que o modo `primes` e a comparação de RTT fazem
sentido (§6.3). Para imitar uma WAN localmente, `rede_simulada.sh up 4 20ms`
adiciona atraso com `tc netem` (requer o módulo `sch_netem` do kernel).

## 8. Testes automatizados

```bash
pip install pytest
python3 -m pytest -v tests/
```

Os testes sobem os processos de verdade em `localhost` (portas aleatórias) e
verificam: comandos e `CALC` seguro, compatibilidade com o protocolo original
(texto + `*` e `STOP`), timeout do cliente sem servidor, distribuição 50/50 do
broker entre dois servidores, filtro de tópicos e *fan‑in* via proxy, e o
pipeline completo com 2 fontes, 2 workers, coletor e `KILL`.

## 9. Observações sobre o ZeroMQ aprendidas nos testes

- **REQ é estritamente alternado** (`send`, `recv`, `send`...). Se a resposta
  nunca chega, o socket fica inutilizável; por isso o cliente confiável fecha
  e recria o socket a cada nova tentativa (padrão *Lazy Pirate*).
- **"Slow joiner"**: no PUB‑SUB, mensagens publicadas antes de a conexão e a
  assinatura chegarem ao publicador são simplesmente descartadas. No pipeline,
  se a fonte começar antes de todos os workers conectarem, o primeiro worker
  recebe quase tudo. Daí as pequenas esperas antes de publicar/enviar.
- **PUB‑SUB não garante entrega**: o nº de sequência torna as perdas visíveis.
  O canal de `KILL` do pipeline repete a mensagem por esse motivo.
- **A filtragem de tópicos é por prefixo** e acontece no lado do publicador
  (as assinaturas "sobem" — o `proxy.py` mostra isso). Assinar `"CHAT.sd "`
  com espaço evita casar também `CHAT.sdx`.
- **PUSH distribui por quantidade, não por carga** (round‑robin). Na tabela do
  pipeline os workers receberam 34/33/33 tarefas, mas cargas totais diferentes
  (341, 322, 386), e o mais carregado define o tempo do lote.
- **Bind em `*` e IP privado**: na AWS, faça bind em todas as interfaces e
  conecte usando o IP privado; libere as portas no security group.
- **Latência entre máquinas exige relógios sincronizados**. Nas instâncias EC2
  o `chrony` pode usar o *Amazon Time Sync Service* (`169.254.169.123`), com
  erro tipicamente abaixo de 1 ms (confira com `chronyc sources`); sem
  sincronização a latência medida pode até sair negativa.
- **Não use `pickle` na rede** (o original usava): JSON é seguro e legível de
  qualquer linguagem.

---

Código original: exemplos do livro *Distributed Systems* (M. van Steen e
A. S. Tanenbaum), distribuídos pela disciplina. Biblioteca:
[pyzmq](https://pyzmq.readthedocs.io) / [ZeroMQ](https://zeromq.org). Padrões
*Lazy Pirate*, broker e proxy baseados no [ZeroMQ Guide](https://zguide.zeromq.org).
