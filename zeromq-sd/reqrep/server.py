"""Servidor REQ-REP estendido (base: Fig. 4.21 / pasta original/04-22/server.py).

Novidades em relação ao original:
  * endereços/portas por argumento (sem editar constCS.py) e bind em '*';
  * protocolo de comandos em JSON (ECHO, UPPER, REVERSE, WORDS, CALC, TIME,
    HOST, SLEEP, STATS, HELP, STOP), com resposta que identifica a máquina
    que atendeu;
  * compatível com o protocolo antigo: texto puro recebe "*" no final e
    "STOP" encerra o servidor -> os clientes originais continuam funcionando;
  * modo "worker": em vez de bind, conecta-se a um broker (broker.py), o que
    permite ter vários servidores em máquinas diferentes atrás de um único
    endereço, com balanceamento de carga.

Exemplos:
  python3 reqrep/server.py                         # bind em *:5555 e *:5556
  python3 reqrep/server.py --bind 6000             # outra porta
  python3 reqrep/server.py --connect 10.0.0.10:5560  # worker atrás do broker
"""
import argparse
import ast
import operator
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import (bind_endpoint, dumps, endpoint, env, handle_sigterm, identity,  # noqa: E402
                         loads, parse_hostport)

# ---------------------------------------------------------------- CALC seguro
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_calc(expr):
    """Avalia expressões aritméticas sem usar eval() (que executaria código)."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("expoente grande demais")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("expressão não permitida")
    if len(expr) > 200:
        raise ValueError("expressão longa demais")
    return ev(ast.parse(expr, mode="eval"))


# ------------------------------------------------------------------ servidor
class Service:
    HELP = {
        "ECHO": "devolve o texto com '*' no final (comportamento original)",
        "UPPER": "texto em maiúsculas",
        "REVERSE": "texto invertido",
        "WORDS": "conta palavras do texto",
        "CALC": "avalia expressão aritmética, ex.: CALC (2+3)*7",
        "TIME": "hora do servidor",
        "HOST": "identificação da máquina que respondeu",
        "SLEEP": "dorme N segundos (máx. 10) - simula serviço lento",
        "STATS": "estatísticas do servidor",
        "HELP": "esta lista",
        "STOP": "encerra o servidor (se permitido)",
    }

    def __init__(self, allow_stop=True, quiet=False):
        self.quiet = quiet
        self.me = identity()
        self.started = time.time()
        self.by_cmd = Counter()
        self.by_client = Counter()
        self.total = 0
        self.allow_stop = allow_stop
        self.stop_requested = False

    def handle(self, cmd, arg):
        cmd = (cmd or "").upper()
        if cmd == "ECHO":
            return arg + "*"
        if cmd == "UPPER":
            return arg.upper()
        if cmd == "REVERSE":
            return arg[::-1]
        if cmd == "WORDS":
            return len(arg.split())
        if cmd == "CALC":
            return safe_calc(arg)
        if cmd == "TIME":
            return {"asctime": time.asctime(), "epoch": time.time()}
        if cmd == "HOST":
            return self.me
        if cmd == "SLEEP":
            secs = min(float(arg or 1), 10.0)
            time.sleep(secs)
            return "dormi %.2fs" % secs
        if cmd == "STATS":
            return {"uptime_s": round(time.time() - self.started, 1),
                    "total": self.total,
                    "por_comando": dict(self.by_cmd),
                    "por_cliente": dict(self.by_client)}
        if cmd == "HELP":
            return self.HELP
        if cmd == "STOP":
            if not self.allow_stop:
                raise PermissionError("STOP desabilitado neste servidor")
            self.stop_requested = True
            return "servidor encerrando"
        raise ValueError("comando desconhecido: %r (use HELP)" % cmd)

    def process(self, raw):
        """Recebe bytes, devolve bytes. Detecta protocolo antigo x JSON."""
        self.total += 1
        text = raw.decode(errors="replace")
        try:
            req = loads(text)
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:
            # ---- protocolo original: texto puro --------------------------
            self.by_cmd["LEGACY"] += 1
            self.by_client["legado"] += 1
            if "STOP" in text and self.allow_stop:
                self.stop_requested = True
                return None          # original não respondia ao STOP
            return (text + "*").encode()

        cmd = str(req.get("cmd", "")).upper()
        client = str(req.get("client", "?"))
        self.by_cmd[cmd] += 1
        self.by_client[client] += 1
        reply = {"id": req.get("id"), "server": self.me, "served": self.total}
        try:
            reply["result"] = self.handle(cmd, str(req.get("arg", "")))
            reply["ok"] = True
        except Exception as exc:  # erro vira resposta, servidor não cai
            reply["ok"] = False
            reply["error"] = "%s: %s" % (type(exc).__name__, exc)
        if not self.quiet:
            print("[%s] %-7s de %-28s -> %s" % (time.strftime("%H:%M:%S"), cmd,
                  client, "ok" if reply["ok"] else reply["error"]), flush=True)
        return dumps(reply)


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", nargs="+", default=env("RR_PORTS", "5555 5556").split(),
                    metavar="PORTA", help="portas para bind (padrão: 5555 5556)")
    ap.add_argument("--bind-host", default=env("BIND_HOST", "*"),
                    help="interface para bind (padrão: * = todas)")
    ap.add_argument("--connect", metavar="HOST:PORTA",
                    help="conecta ao backend de um broker em vez de fazer bind")
    ap.add_argument("--no-stop", action="store_true",
                    help="ignora pedidos de STOP (útil com vários clientes)")
    ap.add_argument("--quiet", action="store_true",
                    help="não registra cada pedido (use em benchmarks)")
    args = ap.parse_args()

    ctx = zmq.Context()
    s = ctx.socket(zmq.REP)
    if args.connect:
        host, port = parse_hostport(args.connect, 5560)
        s.connect(endpoint(host, port))
        where = "conectado ao broker %s" % endpoint(host, port)
    else:
        for port in args.bind:
            s.bind(bind_endpoint(port, args.bind_host))
        where = "bind em " + ", ".join(bind_endpoint(p, args.bind_host) for p in args.bind)

    svc = Service(allow_stop=not args.no_stop, quiet=args.quiet)
    print("Servidor %s (pid %d) %s" % (svc.me, os.getpid(), where), flush=True)
    try:
        while not svc.stop_requested:
            msg = s.recv()
            out = svc.process(msg)
            if out is not None:
                s.send(out)
    except KeyboardInterrupt:
        pass
    print("Servidor encerrado após %d requisições." % svc.total, flush=True)
    s.close(linger=500)
    ctx.term()


if __name__ == "__main__":
    main()
