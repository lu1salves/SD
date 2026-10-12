"""Assinante PUB-SUB estendido (base: Fig. 4.22 / pasta original/04-23/subscriber.py).

O original assinava só "TIME" de um único publicador e parava após 5
mensagens. Agora:
  * escolhe os tópicos por argumento (--topics TIME SENSOR ALERT ...);
  * conecta-se a VÁRIOS publicadores ao mesmo tempo (fan-in) ou a um proxy;
  * detecta mensagens perdidas por lacunas no número de sequência
    (PUB-SUB do ZeroMQ não garante entrega: se o assinante ficar lento
    ou entrar atrasado, perde mensagens);
  * mede latência de ponta a ponta (agora - timestamp do publicador).
    Entre máquinas diferentes isso exige relógios sincronizados (na AWS o
    chrony usa o Amazon Time Sync Service, com erro tipicamente < 1 ms);
  * ao final imprime estatísticas por tópico e por publicador.

Exemplos:
  python3 pubsub/subscriber.py --connect 10.0.0.5:5557 --topics TIME --count 5
  python3 pubsub/subscriber.py --connect 10.0.0.5:5557 --connect 10.0.0.6:5557
  python3 pubsub/subscriber.py --connect 10.0.0.10:5562 --topics ALERT  # via proxy
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (endpoint, env, fmt_summary, handle_sigterm, loads,  # noqa: E402
                         parse_hostport, summarize)


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connect", action="append", metavar="HOST:PORTA",
                    help="publicador ou proxy (pode repetir). Padrão: $ZMQ_PUBLISHER "
                         "ou localhost:5557")
    ap.add_argument("--topics", nargs="+", default=[""],
                    help="prefixos assinados (padrão: todos)")
    ap.add_argument("--count", type=int, default=0,
                    help="encerra após N mensagens (0 = sem limite)")
    ap.add_argument("--duration", type=float, default=0,
                    help="encerra após N segundos (0 = sem limite)")
    ap.add_argument("--quiet", action="store_true", help="não imprime cada mensagem")
    args = ap.parse_args()

    targets = args.connect or env("PUBLISHER", "localhost:5557").split(",")
    ctx = zmq.Context()
    s = ctx.socket(zmq.SUB)
    for t in targets:
        s.connect(endpoint(*parse_hostport(t, 5557)))
    for topic in args.topics:
        s.setsockopt_string(zmq.SUBSCRIBE, topic)
    print("Assinante conectado a %s, tópicos %s"
          % (targets, args.topics if args.topics != [""] else "TODOS"), flush=True)

    last_seq = {}                       # (publicador, tópico) -> último seq
    received = defaultdict(int)         # tópico -> nº de mensagens
    lost = defaultdict(int)             # tópico -> nº de mensagens perdidas
    per_pub = defaultdict(int)
    latencies = defaultdict(list)       # tópico -> latências em ms
    total = 0
    t_end = time.time() + args.duration if args.duration else None
    try:
        while args.count == 0 or total < args.count:
            timeout = 1000 if t_end is None else max(0, int((t_end - time.time()) * 1000))
            if t_end is not None and timeout == 0:
                break
            if not s.poll(min(timeout, 1000)):
                continue
            raw = s.recv()
            arrived = time.time()
            topic, _, body = raw.partition(b" ")
            topic = topic.decode()
            total += 1
            received[topic] += 1
            try:
                msg = loads(body)
            except ValueError:          # publicador original: "TIME <asctime>"
                if not args.quiet:
                    print(raw.decode())
                continue
            key = (msg["pub"], topic)
            if key in last_seq and msg["seq"] > last_seq[key] + 1:
                gap = msg["seq"] - last_seq[key] - 1
                lost[topic] += gap
                print("  ! %d mensagem(ns) %s de %s perdida(s)" % (gap, topic, msg["pub"]))
            last_seq[key] = msg["seq"]
            per_pub[msg["pub"]] += 1
            lat = (arrived - msg["ts"]) * 1000
            latencies[topic].append(lat)
            if not args.quiet:
                print("%-6s #%-5d de %-28s %7.2f ms  %s"
                      % (topic, msg["seq"], msg["pub"], lat,
                         json.dumps(msg["data"], ensure_ascii=False)), flush=True)
    except KeyboardInterrupt:
        pass

    print("\n=== Resumo do assinante (%d mensagens) ===" % total)
    for topic in sorted(received):
        print("  %-6s recebidas=%-5d perdidas=%-4d latência: %s"
              % (topic, received[topic], lost[topic],
                 fmt_summary(summarize(latencies[topic]))))
    for pub, n in sorted(per_pub.items()):
        print("  de %-30s %d" % (pub, n))
    s.close(0)
    ctx.term()


if __name__ == "__main__":
    main()
