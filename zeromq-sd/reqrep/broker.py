"""Broker ROUTER/DEALER para o REQ-REP (funcionalidade nova).

No original o cliente precisava saber o IP de cada servidor. Com o broker:

    clientes (REQ) --> [ROUTER :5559 | broker | DEALER :5560] <-- servidores (REP)

  * clientes só conhecem o endereço do broker (porta de frontend);
  * servidores em quaisquer máquinas se conectam ao backend
    (server.py --connect BROKER:5560) e podem entrar/sair a qualquer momento;
  * o DEALER distribui os pedidos em round-robin entre os servidores
    conectados (escalabilidade horizontal).

O laço abaixo faz o mesmo que zmq.proxy(), mas contando mensagens para
mostrar estatísticas periódicas.

Exemplo:
  python3 reqrep/broker.py                       # frontend 5559, backend 5560
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
    ap.add_argument("--frontend", default=env("RR_FRONTEND", "5559"),
                    help="porta para clientes (padrão 5559)")
    ap.add_argument("--backend", default=env("RR_BACKEND", "5560"),
                    help="porta para servidores (padrão 5560)")
    ap.add_argument("--report", type=float, default=10.0,
                    help="intervalo (s) entre relatórios; 0 desliga")
    args = ap.parse_args()

    ctx = zmq.Context()
    front = ctx.socket(zmq.ROUTER)
    back = ctx.socket(zmq.DEALER)
    front.bind(bind_endpoint(args.frontend))
    back.bind(bind_endpoint(args.backend))
    print("Broker %s: clientes -> :%s | servidores -> :%s"
          % (identity(), args.frontend, args.backend), flush=True)

    poller = zmq.Poller()
    poller.register(front, zmq.POLLIN)
    poller.register(back, zmq.POLLIN)
    requests = replies = 0
    last = time.time()
    try:
        while True:
            events = dict(poller.poll(1000))
            if front in events:                      # pedido de cliente
                back.send_multipart(front.recv_multipart())
                requests += 1
            if back in events:                       # resposta de servidor
                front.send_multipart(back.recv_multipart())
                replies += 1
            if args.report and time.time() - last >= args.report:
                print("[%s] pedidos=%d respostas=%d pendentes=%d"
                      % (time.strftime("%H:%M:%S"), requests, replies,
                         requests - replies), flush=True)
                last = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        front.close(0)
        back.close(0)
        ctx.term()


if __name__ == "__main__":
    main()
