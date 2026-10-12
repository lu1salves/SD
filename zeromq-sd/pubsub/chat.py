"""Chat em grupo sobre PUB-SUB + proxy (aplicação nova).

Cada participante tem um socket PUB (fala) e um SUB (ouve), ambos ligados
ao proxy.py. O tópico é a sala: "CHAT.<sala>". Rode em máquinas
diferentes apontando para o mesmo proxy.

  python3 pubsub/chat.py --proxy 10.0.0.10 --nick ana  --room sd
  python3 pubsub/chat.py --proxy 10.0.0.10 --nick beto --room sd

Comandos dentro do chat:  /sair   /quem (lista quem falou recentemente)
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zmq  # noqa: E402

from common.util import dumps, endpoint, env, hostname, loads  # noqa: E402


def listener(ctx, url, topic, me, seen, stop):
    """Thread que recebe mensagens. Cada thread usa seu próprio socket
    (sockets ZeroMQ não devem ser compartilhados entre threads)."""
    sub = ctx.socket(zmq.SUB)
    sub.connect(url)
    sub.setsockopt_string(zmq.SUBSCRIBE, topic + " ")
    while not stop.is_set():
        if not sub.poll(200):
            continue
        _, _, body = sub.recv().partition(b" ")
        msg = loads(body)
        seen[msg["nick"]] = (msg["host"], time.time())
        if msg["uid"] == me:
            continue                      # não repete minhas próprias mensagens
        lat = (time.time() - msg["ts"]) * 1000
        print("\r[%s] %s@%s: %s   (%.1f ms)" % (time.strftime("%H:%M:%S"),
              msg["nick"], msg["host"], msg["text"], lat), flush=True)
    sub.close(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proxy", default=env("PROXY", "localhost"), help="host do proxy")
    ap.add_argument("--xsub", default="5561")
    ap.add_argument("--xpub", default="5562")
    ap.add_argument("--nick", default=os.environ.get("USER", "anon"))
    ap.add_argument("--room", default="geral")
    args = ap.parse_args()

    ctx = zmq.Context()
    topic = "CHAT." + args.room
    me = "%s-%s-%d" % (args.nick, hostname(), os.getpid())
    seen, stop = {}, threading.Event()
    t = threading.Thread(target=listener, daemon=True,
                         args=(ctx, endpoint(args.proxy, args.xpub), topic, me, seen, stop))
    t.start()

    pub = ctx.socket(zmq.PUB)
    pub.connect(endpoint(args.proxy, args.xsub))
    time.sleep(0.5)                        # slow joiner

    def say(text):
        pub.send(topic.encode() + b" " + dumps(
            {"nick": args.nick, "host": hostname(), "uid": me,
             "text": text, "ts": time.time()}))

    print("Sala '%s' via proxy %s. /sair para sair, /quem para listar."
          % (args.room, args.proxy), flush=True)
    say("*** entrou na sala ***")
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            if line == "/sair":
                break
            if line == "/quem":
                for nick, (host, ts) in sorted(seen.items()):
                    print("  %-12s @ %-20s há %.0fs" % (nick, host, time.time() - ts))
                continue
            say(line)
    except KeyboardInterrupt:
        pass
    say("*** saiu da sala ***")
    time.sleep(0.3)
    stop.set()
    t.join()
    pub.close(linger=500)
    ctx.term()


if __name__ == "__main__":
    main()
