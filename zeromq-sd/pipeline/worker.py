"""Worker do PIPELINE (base: Fig. 4.23 / pasta original/04-24/taskwork.py).

O original puxava tarefas de 2 fontes fixas, só imprimia e ficava em laço
infinito. Agora:
  * conecta-se a qualquer lista de fontes (--sources h1:5563 h2:5564 ...);
  * executa trabalho real (modo "primes") ou simulado (modo "sleep");
  * envia o resultado ao coletor (sink.py) -> padrão completo
    ventilador -> workers -> coletor (PUSH/PULL em dois estágios);
  * escuta um canal de controle (PUB/SUB do coletor) e encerra sozinho
    quando o lote termina, imprimindo suas estatísticas.

Exemplo:
  python3 pipeline/worker.py --id A --sources 10.0.0.5:5563 10.0.0.6:5564 \\
          --sink 10.0.0.10
"""
import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (dumps, endpoint, env, handle_sigterm, identity,  # noqa: E402
                         loads, parse_hostport)


def count_primes(n):
    """Conta primos <= n por divisão sucessiva (de propósito em Python puro,
    para gastar CPU de verdade; custo cresce ~ n^1.5)."""
    count = 0
    for k in range(2, n + 1):
        d, prime = 2, True
        while d * d <= k:
            if k % d == 0:
                prime = False
                break
            d += 1
        count += prime
    return count


def do_work(task):
    if task["mode"] == "primes":
        return count_primes(task["workload"] * 400)   # carga 100 ~ 80 ms de CPU
    time.sleep(task["workload"] * 0.01)               # igual ao original
    return task["workload"]


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", default=None, help="nome do worker (padrão: host(ip)/pid)")
    ap.add_argument("--sources", nargs="+",
                    default=env("SOURCES", "localhost:5563").split(","),
                    metavar="HOST:PORTA", help="fontes de tarefas")
    ap.add_argument("--sink", default=env("SINK", "localhost"), metavar="HOST",
                    help="host do coletor (resultados :5565, controle :5566)")
    ap.add_argument("--sink-port", default="5565")
    ap.add_argument("--control-port", default="5566")
    ap.add_argument("--verbose", action="store_true", help="imprime cada tarefa")
    args = ap.parse_args()

    me = args.id or identity()
    ctx = zmq.Context()
    tasks = ctx.socket(zmq.PULL)
    for src in args.sources:
        tasks.connect(endpoint(*parse_hostport(src, 5563)))
    results = ctx.socket(zmq.PUSH)
    sink_host = parse_hostport(args.sink, args.sink_port)[0]
    results.connect(endpoint(sink_host, args.sink_port))
    control = ctx.socket(zmq.SUB)
    control.connect(endpoint(sink_host, args.control_port))
    control.setsockopt_string(zmq.SUBSCRIBE, "KILL")

    print("Worker %s iniciado; fontes %s; coletor %s" % (me, args.sources, sink_host),
          flush=True)
    poller = zmq.Poller()
    poller.register(tasks, zmq.POLLIN)
    poller.register(control, zmq.POLLIN)
    per_source, done, busy = Counter(), 0, 0.0
    try:
        while True:
            events = dict(poller.poll())
            if control in events:
                control.recv()
                print("Worker %s: recebeu KILL do coletor." % me, flush=True)
                break
            if tasks in events:
                task = loads(tasks.recv())
                t0 = time.perf_counter()
                result = do_work(task)
                elapsed = time.perf_counter() - t0
                busy += elapsed
                done += 1
                per_source[task["source"]] += 1
                if args.verbose:
                    print("%s recebeu carga %3d da fonte %s (%.1f ms)"
                          % (me, task["workload"], task["source"], elapsed * 1000),
                          flush=True)
                results.send(dumps({"type": "RESULT", "worker": me,
                                    "source": task["source"], "task": task["task"],
                                    "workload": task["workload"], "result": result,
                                    "elapsed": elapsed}))
    except KeyboardInterrupt:
        pass
    print("Worker %s: %d tarefas, %.2fs ocupado, por fonte %s"
          % (me, done, busy, dict(per_source)), flush=True)
    for sck in (tasks, results, control):
        sck.close(linger=1000)
    ctx.term()


if __name__ == "__main__":
    main()
