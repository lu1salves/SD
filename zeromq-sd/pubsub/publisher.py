"""Publicador PUB-SUB estendido (base: Fig. 4.22 / pasta original/04-23/publisher.py).

O original publicava só "TIME <hora>" a cada 5 s. Agora:
  * vários tópicos:
      TIME    hora do publicador (como no original)
      SYS     carga da CPU, memória livre e nº de CPUs da máquina publicadora
      SENSOR  leitura simulada de temperatura (passeio aleatório)
      ALERT   publicado só quando o SENSOR passa do limite (--limite)
  * cada mensagem leva id do publicador, número de sequência por tópico e
    timestamp -> o assinante detecta mensagens perdidas e mede latência;
  * formato continua sendo um único frame "TOPICO <json>", então o
    subscriber.py ORIGINAL (que assina "TIME") continua funcionando;
  * pode fazer bind (como o original) ou conectar-se a um proxy XPUB/XSUB
    (proxy.py), permitindo vários publicadores em máquinas diferentes.

Exemplos:
  python3 pubsub/publisher.py                         # bind em *:5557, 1 msg/s
  python3 pubsub/publisher.py --interval 5 --topics TIME   # igual ao original
  python3 pubsub/publisher.py --connect 10.0.0.10:5561      # via proxy
"""
import argparse
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (bind_endpoint, dumps, endpoint, env, handle_sigterm,  # noqa: E402
                         identity, parse_hostport)

ALL_TOPICS = ["TIME", "SYS", "SENSOR"]


def sys_info():
    load1, load5, _ = os.getloadavg()
    mem_free = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    mem_free = int(line.split()[1]) // 1024   # MiB
    except OSError:
        pass
    return {"load1": load1, "load5": load5, "cpus": os.cpu_count(),
            "mem_livre_mb": mem_free}


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=env("PS_PORT", "5557"),
                    help="porta para bind (padrão 5557)")
    ap.add_argument("--connect", metavar="HOST:PORTA",
                    help="conecta ao proxy (porta XSUB) em vez de fazer bind")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="segundos entre rodadas de publicação (original: 5)")
    ap.add_argument("--topics", nargs="+", default=ALL_TOPICS,
                    choices=ALL_TOPICS, help="tópicos publicados")
    ap.add_argument("--limite", type=float, default=30.0,
                    help="temperatura que dispara ALERT (padrão 30.0)")
    ap.add_argument("--count", type=int, default=0,
                    help="nº de rodadas e depois encerra (0 = infinito)")
    ap.add_argument("--name", help="nome do publicador (padrão: host(ip)/pid)")
    args = ap.parse_args()

    me = args.name or identity()
    ctx = zmq.Context()
    s = ctx.socket(zmq.PUB)
    if args.connect:
        host, port = parse_hostport(args.connect, 5561)
        s.connect(endpoint(host, port))
        where = "conectado ao proxy " + endpoint(host, port)
    else:
        s.bind(bind_endpoint(args.port))
        where = "bind em " + bind_endpoint(args.port)
    print("Publicador %s %s, tópicos %s a cada %.2fs"
          % (me, where, args.topics, args.interval), flush=True)

    seq = {}
    temp = 25.0

    def publish(topic, data):
        seq[topic] = seq.get(topic, 0) + 1
        msg = {"pub": me, "seq": seq[topic], "ts": time.time(), "data": data}
        s.send(topic.encode() + b" " + dumps(msg))

    time.sleep(0.5)  # "slow joiner": dá tempo dos assinantes se conectarem
    rounds = 0
    try:
        while args.count == 0 or rounds < args.count:
            if "TIME" in args.topics:
                publish("TIME", time.asctime())
            if "SYS" in args.topics:
                publish("SYS", sys_info())
            if "SENSOR" in args.topics:
                temp = max(10.0, min(45.0, temp + random.gauss(0, 1.5)))
                publish("SENSOR", {"temperatura": round(temp, 2)})
                if temp > args.limite:
                    publish("ALERT", "temperatura %.2f acima de %.1f" % (temp, args.limite))
            rounds += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print("Publicador encerrado; mensagens por tópico: %s" % seq, flush=True)
    s.close(linger=1000)
    ctx.term()


if __name__ == "__main__":
    main()
