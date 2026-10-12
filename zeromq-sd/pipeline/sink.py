"""Coletor (sink) do PIPELINE (componente novo; não existe no original).

  fontes (PUSH :5563, :5564, ...) --> workers (PULL ... PUSH) --> sink (PULL :5565)
                                         ^                           |
                                         +------ KILL (PUB :5566) ---+

  * recebe os avisos START das fontes (quantas tarefas cada uma enviará);
  * recebe os resultados dos workers e, quando todas as tarefas chegaram,
    mede o tempo total do lote, a vazão e como a carga foi distribuída;
  * publica KILL no canal de controle para encerrar os workers;
  * opcionalmente acrescenta uma linha num CSV (para montar tabelas de
    speedup: 1, 2, 4... workers em máquinas diferentes).

Exemplo (2 fontes):
  python3 pipeline/sink.py --sources 2 --csv resultados.csv --label "4 workers"
"""
import argparse
import csv
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import bind_endpoint, env, handle_sigterm, identity, loads  # noqa: E402


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=env("SINK_PORT", "5565"), help="resultados (5565)")
    ap.add_argument("--control-port", default="5566", help="canal de controle (5566)")
    ap.add_argument("--sources", type=int, default=1,
                    help="nº de fontes esperadas no lote (padrão 1)")
    ap.add_argument("--keep-workers", action="store_true",
                    help="não envia KILL ao final")
    ap.add_argument("--csv", help="acrescenta o resultado do lote neste arquivo CSV")
    ap.add_argument("--label", default="", help="rótulo da execução no CSV")
    args = ap.parse_args()

    ctx = zmq.Context()
    pull = ctx.socket(zmq.PULL)
    pull.bind(bind_endpoint(args.port))
    control = ctx.socket(zmq.PUB)
    control.bind(bind_endpoint(args.control_port))
    print("Coletor %s: resultados :%s, controle :%s, esperando %d fonte(s)"
          % (identity(), args.port, args.control_port, args.sources), flush=True)

    started, expected, got = {}, 0, 0
    t_first = None
    per_worker, load_worker = Counter(), Counter()
    per_source = Counter()
    busy = defaultdict(float)
    pairs = defaultdict(Counter)            # worker -> fonte -> nº
    try:
        while len(started) < args.sources or got < expected:
            msg = loads(pull.recv())
            if msg["type"] == "START":
                started[msg["source"]] = msg["tasks"]
                expected = sum(started.values())
                t_first = t_first or time.time()
                print("Fonte %s iniciou lote de %d tarefas (%d/%d fontes)"
                      % (msg["source"], msg["tasks"], len(started), args.sources),
                      flush=True)
                continue
            got += 1
            t_first = t_first or time.time()
            w = msg["worker"]
            per_worker[w] += 1
            load_worker[w] += msg["workload"]
            per_source[msg["source"]] += 1
            busy[w] += msg["elapsed"]
            pairs[w][msg["source"]] += 1
            if got % 50 == 0:
                print("  ... %d/%d resultados" % (got, expected), flush=True)
    except KeyboardInterrupt:
        print("Interrompido.")
    elapsed = time.time() - (t_first or time.time())
    total_busy = sum(busy.values())

    print("\n=== Relatório do lote ===")
    print("Tarefas: %d de %d fonte(s) | tempo total %.2fs | vazão %.1f tarefas/s"
          % (got, len(started), elapsed, got / elapsed if elapsed else 0))
    print("Trabalho somado dos workers: %.2fs  -> paralelismo efetivo %.2fx"
          % (total_busy, total_busy / elapsed if elapsed else 0))
    print("%-34s %8s %8s %9s  %s" % ("worker", "tarefas", "carga", "ocupado", "por fonte"))
    for w in sorted(per_worker):
        print("%-34s %8d %8d %8.2fs  %s" % (w, per_worker[w], load_worker[w], busy[w],
                                            dict(pairs[w])))

    if not args.keep_workers:
        for _ in range(3):                 # repete: PUB não garante entrega
            control.send_string("KILL")
            time.sleep(0.2)
        print("KILL enviado aos workers.")

    if args.csv and got:
        new = not os.path.exists(args.csv)
        with open(args.csv, "a", newline="") as f:
            wr = csv.writer(f)
            if new:
                wr.writerow(["rotulo", "workers", "fontes", "tarefas", "tempo_s",
                             "tarefas_por_s", "trabalho_s", "paralelismo"])
            wr.writerow([args.label, len(per_worker), len(started), got,
                         round(elapsed, 3), round(got / elapsed, 2),
                         round(total_busy, 3), round(total_busy / elapsed, 2)])
        print("Linha acrescentada em", args.csv)
    pull.close(0)
    control.close(linger=500)
    ctx.term()


if __name__ == "__main__":
    main()
