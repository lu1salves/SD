"""Proxy XSUB/XPUB para o PUB-SUB (funcionalidade nova).

No original, o assinante precisava conhecer o IP do publicador. Com o
proxy, publicadores e assinantes só conhecem o endereço do proxy:

  publicadores (PUB) --> [XSUB :5561 | proxy | XPUB :5562] <-- assinantes (SUB)

O proxy também mostra as ASSINATURAS que passam por ele: no ZeroMQ quem
filtra os tópicos é o lado publicador, então os pedidos de assinatura
"sobem" dos SUBs até os PUBs (byte 1 = assinar, 0 = cancelar).

Exemplo:
  python3 pubsub/proxy.py
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import bind_endpoint, env, handle_sigterm, identity  # noqa: E402


def main():
    handle_sigterm()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xsub", default=env("PS_XSUB", "5561"),
                    help="porta para publicadores (padrão 5561)")
    ap.add_argument("--xpub", default=env("PS_XPUB", "5562"),
                    help="porta para assinantes (padrão 5562)")
    ap.add_argument("--report", type=float, default=10.0,
                    help="intervalo (s) entre relatórios; 0 desliga")
    args = ap.parse_args()

    ctx = zmq.Context()
    xsub = ctx.socket(zmq.XSUB)
    xpub = ctx.socket(zmq.XPUB)
    xpub.setsockopt(zmq.XPUB_VERBOSE, 1)   # repassa todas as assinaturas
    xsub.bind(bind_endpoint(args.xsub))
    xpub.bind(bind_endpoint(args.xpub))
    print("Proxy %s: publicadores -> :%s | assinantes -> :%s"
          % (identity(), args.xsub, args.xpub), flush=True)

    poller = zmq.Poller()
    poller.register(xsub, zmq.POLLIN)
    poller.register(xpub, zmq.POLLIN)
    forwarded = 0
    last = time.time()
    try:
        while True:
            events = dict(poller.poll(1000))
            if xsub in events:                       # dado: PUB -> SUBs
                xpub.send_multipart(xsub.recv_multipart())
                forwarded += 1
            if xpub in events:                       # assinatura: SUB -> PUBs
                frames = xpub.recv_multipart()
                sub = frames[0]
                if sub and sub[0] in (0, 1):
                    print("[%s] %s '%s'" % (time.strftime("%H:%M:%S"),
                          "ASSINOU  " if sub[0] == 1 else "CANCELOU ",
                          sub[1:].decode(errors="replace") or "(todos)"), flush=True)
                xsub.send_multipart(frames)
            if args.report and time.time() - last >= args.report:
                print("[%s] mensagens repassadas: %d"
                      % (time.strftime("%H:%M:%S"), forwarded), flush=True)
                last = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        xsub.close(0)
        xpub.close(0)
        ctx.term()


if __name__ == "__main__":
    main()
