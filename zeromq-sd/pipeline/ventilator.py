"""Fonte de tarefas do PIPELINE (base: Fig. 4.23 / pasta original/04-24/tasksrc.py).

O original tinha exatamente 2 fontes com IPs fixos (SRC1/SRC2) e enviava
100 cargas aleatórias com pickle, 1 por segundo. Agora:
  * qualquer número de fontes (cada uma com --id e --port próprios);
  * nº de tarefas, ritmo de envio e tipo de trabalho configuráveis:
      sleep   -> o worker "finge" trabalhar: dorme carga*10 ms (original)
      primes  -> o worker conta primos até carga*2000 (uso real de CPU,
                 mostra o ganho de colocar workers em máquinas diferentes);
  * avisa o coletor (sink.py) quantas tarefas vai mandar, para que ele saiba
    quando o lote terminou e possa medir o tempo total;
  * mensagens em JSON em vez de pickle (pickle vindo da rede é inseguro);
  * espera os workers se conectarem antes de enviar (--wait), senão o
    primeiro worker conectado recebe tudo ("slow joiner").

Exemplo (fonte 1, 200 tarefas de CPU, o mais rápido possível):
  python3 pipeline/ventilator.py --id 1 --sink 10.0.0.10 --tasks 200 \\
          --mode primes --rate 0
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (bind_endpoint, dumps, endpoint, env, handle_sigterm,  # noqa: E402
                         identity, parse_hostport)


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", default="1", help="identificador da fonte (original: argv[1])")
    ap.add_argument("--port", default=None,
                    help="porta para bind (padrão 5563 + id - 1; fonte 1 -> 5563)")
    ap.add_argument("--sink", default=env("SINK", "localhost"), metavar="HOST[:PORTA]",
                    help="coletor de resultados (padrão localhost:5565)")
    ap.add_argument("--tasks", type=int, default=100, help="nº de tarefas (padrão 100)")
    ap.add_argument("--rate", type=float, default=0.0,
                    help="segundos entre tarefas (original: 1.0; padrão 0 = sem pausa)")
    ap.add_argument("--mode", choices=["sleep", "primes"], default="sleep")
    ap.add_argument("--max-load", type=int, default=100,
                    help="carga máxima de cada tarefa (original: 100)")
    ap.add_argument("--wait", type=float, default=3.0,
                    help="segundos esperando workers antes de começar (padrão 3)")
    ap.add_argument("--enter", action="store_true",
                    help="espera ENTER em vez de --wait")
    ap.add_argument("--seed", type=int, help="semente aleatória (experimentos repetíveis)")
    args = ap.parse_args()

    port = args.port or str(5563 + int(args.id) - 1 if args.id.isdigit() else 5563)
    rnd = random.Random(args.seed)
    ctx = zmq.Context()
    push = ctx.socket(zmq.PUSH)
    push.bind(bind_endpoint(port))
    sink = ctx.socket(zmq.PUSH)
    sink.connect(endpoint(*parse_hostport(args.sink, 5565)))
    print("Fonte %s (%s) bind em :%s, coletor %s"
          % (args.id, identity(), port, args.sink), flush=True)

    if args.enter:
        input("Inicie os workers e pressione ENTER para enviar as tarefas...")
    else:
        print("Aguardando %.1fs para os workers se conectarem..." % args.wait, flush=True)
        time.sleep(args.wait)

    # avisa o coletor: início do lote e quantas tarefas virão desta fonte
    sink.send(dumps({"type": "START", "source": args.id, "tasks": args.tasks,
                     "ts": time.time()}))
    total_load = 0
    t0 = time.time()
    for i in range(1, args.tasks + 1):
        workload = rnd.randint(1, args.max_load)   # original: 1..100
        total_load += workload
        push.send(dumps({"source": args.id, "task": i, "workload": workload,
                         "mode": args.mode}))
        if args.rate:
            time.sleep(args.rate)
    print("Fonte %s: %d tarefas enviadas em %.2fs (carga total %d)"
          % (args.id, args.tasks, time.time() - t0, total_load), flush=True)
    # linger: garante que as mensagens na fila saiam antes de fechar
    push.close(linger=-1)
    sink.close(linger=-1)
    ctx.term()


if __name__ == "__main__":
    main()
