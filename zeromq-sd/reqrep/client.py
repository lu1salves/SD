"""Cliente REQ-REP estendido (base: Fig. 4.21 / pasta original/04-22/client*.py).

Novidades em relação ao original:
  * servidor(es) por argumento; um mesmo socket REQ pode se conectar a
    vários servidores e o ZeroMQ distribui os pedidos em round-robin;
  * modo interativo (REPL), modo de comando único e modo benchmark;
  * confiabilidade "Lazy Pirate": timeout + novas tentativas. No original,
    se o servidor estivesse fora do ar o cliente ficava bloqueado para sempre
    em recv();
  * benchmark de latência (RTT) e vazão, para comparar mesma máquina x
    máquinas diferentes x regiões diferentes da AWS.

Exemplos:
  python3 reqrep/client.py --server 10.0.0.5:5555                 # interativo
  python3 reqrep/client.py --server 10.0.0.5:5555 CALC "2**10 + 1"
  python3 reqrep/client.py --server 10.0.0.5:5555 --server 10.0.0.6:5555 \\
          --bench 1000 --payload 256
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (dumps, endpoint, env, fmt_summary, identity,  # noqa: E402
                         loads, parse_hostport, summarize)


class ReliableClient:
    """Cliente REQ com timeout e reenvio (padrão Lazy Pirate do ZGuide)."""

    def __init__(self, servers, timeout=2.5, retries=3, name=None):
        self.ctx = zmq.Context.instance()
        self.servers = [endpoint(*parse_hostport(s, 5555)) for s in servers]
        self.timeout_ms = int(timeout * 1000)
        self.retries = retries
        self.name = name or identity()
        self.ids = itertools.count(1)
        self.sock = None
        self._connect()

    def _connect(self):
        if self.sock is not None:
            # descarta o socket "travado": um REQ que não recebeu resposta
            # não pode enviar de novo (máquina de estados send/recv).
            self.sock.close(linger=0)
        self.sock = self.ctx.socket(zmq.REQ)
        for ep in self.servers:
            self.sock.connect(ep)

    def request(self, cmd, arg=""):
        """Envia um comando e devolve (resposta_dict, rtt_ms)."""
        msg = {"cmd": cmd, "arg": arg, "id": next(self.ids), "client": self.name}
        payload = dumps(msg)
        for attempt in range(1, self.retries + 1):
            t0 = time.perf_counter()
            self.sock.send(payload)
            if self.sock.poll(self.timeout_ms, zmq.POLLIN):
                reply = loads(self.sock.recv())
                return reply, (time.perf_counter() - t0) * 1000
            print("  ! sem resposta em %.1fs (tentativa %d/%d), reconectando..."
                  % (self.timeout_ms / 1000, attempt, self.retries), file=sys.stderr)
            self._connect()
        raise TimeoutError("servidor(es) %s não responderam após %d tentativas"
                           % (", ".join(self.servers), self.retries))

    def close(self):
        self.sock.close(linger=0)


def show(reply, rtt):
    status = "OK " if reply.get("ok") else "ERRO"
    body = reply.get("result") if reply.get("ok") else reply.get("error")
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False)
    print("%s %-40s  [%s, %.2f ms]" % (status, body, reply.get("server"), rtt))


def interactive(cli):
    print("Conectado a %s. Digite comandos (HELP para ajuda, QUIT para sair)."
          % ", ".join(cli.servers))
    while True:
        try:
            line = input("zmq> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.upper() in ("QUIT", "EXIT"):
            break
        parts = line.split(None, 1)
        try:
            show(*cli.request(parts[0], parts[1] if len(parts) > 1 else ""))
        except TimeoutError as exc:
            print("FALHA:", exc)


def bench(cli, n, cmd, payload_size):
    arg = "x" * payload_size
    rtts, servers = [], {}
    cli.request("HOST")                       # aquecimento (conexão TCP)
    t0 = time.perf_counter()
    for _ in range(n):
        reply, rtt = cli.request(cmd, arg)
        rtts.append(rtt)
        servers[reply.get("server")] = servers.get(reply.get("server"), 0) + 1
    elapsed = time.perf_counter() - t0
    print("Benchmark: %d pedidos %s com %d bytes de carga" % (n, cmd, payload_size))
    print("  RTT   :", fmt_summary(summarize(rtts)))
    print("  Vazão : %.1f req/s (sequencial, 1 pedido por vez)" % (n / elapsed))
    print("  Distribuição entre servidores:")
    for srv, count in sorted(servers.items()):
        print("    %-36s %6d (%.0f%%)" % (srv, count, 100.0 * count / n))
    return rtts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", action="append", metavar="HOST:PORTA",
                    help="servidor ou broker (pode repetir). Padrão: $ZMQ_SERVER "
                         "ou localhost:5555")
    ap.add_argument("--timeout", type=float, default=2.5, help="segundos (padrão 2.5)")
    ap.add_argument("--retries", type=int, default=3, help="tentativas (padrão 3)")
    ap.add_argument("--name", help="nome do cliente que aparece nas estatísticas")
    ap.add_argument("--bench", type=int, metavar="N", help="executa N pedidos e mede RTT")
    ap.add_argument("--cmd", default="ECHO", help="comando usado no benchmark")
    ap.add_argument("--payload", type=int, default=32, help="bytes de carga no benchmark")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="comando único, ex.: UPPER ola mundo")
    args = ap.parse_args()

    servers = args.server or env("SERVER", "localhost:5555").split(",")
    cli = ReliableClient(servers, args.timeout, args.retries, args.name)
    try:
        if args.bench:
            bench(cli, args.bench, args.cmd, args.payload)
        elif args.command:
            show(*cli.request(args.command[0], " ".join(args.command[1:])))
        else:
            interactive(cli)
    except TimeoutError as exc:
        print("FALHA:", exc, file=sys.stderr)
        sys.exit(2)
    finally:
        cli.close()


if __name__ == "__main__":
    main()
