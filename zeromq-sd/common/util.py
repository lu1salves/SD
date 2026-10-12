"""Funções auxiliares compartilhadas pelas três aplicações.

Substitui os arquivos constCS.py / constPS.py / constPipe.py do pacote
original: em vez de editar IPs fixos no código, os endereços vêm de
argumentos de linha de comando ou de variáveis de ambiente.
"""
import json
import os
import socket
import statistics
import time


def env(name, default):
    """Lê uma variável de ambiente ZMQ_<name>, com valor padrão."""
    return os.environ.get("ZMQ_" + name, default)


def endpoint(host, port):
    """Monta um endpoint TCP do ZeroMQ, ex.: tcp://10.0.0.5:5555."""
    return "tcp://%s:%s" % (host, port)


def bind_endpoint(port, host="*"):
    """Endpoint para bind.

    O original fazia bind no IP privado da máquina (172.31.18.70). Aqui o
    padrão é '*' (todas as interfaces): funciona igual em qualquer máquina,
    inclusive na AWS, onde o IP público NÃO aparece na interface de rede.
    """
    return endpoint(host, port)


def parse_hostport(text, default_port):
    """'10.0.0.5:5556' -> ('10.0.0.5', '5556'); '10.0.0.5' -> ('10.0.0.5', default)."""
    if ":" in text:
        host, port = text.rsplit(":", 1)
        return host, port
    return text, str(default_port)


def handle_sigterm():
    """Faz SIGTERM (kill, systemd, fim de sessão SSH) se comportar como Ctrl+C,
    para que os programas encerrem limpos e imprimam suas estatísticas."""
    import signal

    def _raise(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _raise)


def hostname():
    return socket.gethostname()


def local_ip():
    """Melhor palpite do IP local usado para sair da máquina (sem enviar pacotes)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def identity():
    """Identificação legível desta máquina/processo: host(ip)/pid."""
    return "%s(%s)/%d" % (hostname(), local_ip(), os.getpid())


def now():
    return time.time()


def dumps(obj):
    """Serializa em JSON (bytes).

    O original usava pickle; desserializar pickle vindo da rede permite
    execução remota de código, então trocamos por JSON.
    """
    return json.dumps(obj, separators=(",", ":")).encode()


def loads(data):
    return json.loads(data.decode() if isinstance(data, bytes) else data)


def summarize(values):
    """Estatísticas simples de uma lista de números (ms, por exemplo)."""
    if not values:
        return {"n": 0}
    v = sorted(values)
    p95 = v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]
    return {
        "n": len(v),
        "min": v[0],
        "media": statistics.fmean(v),
        "mediana": statistics.median(v),
        "p95": p95,
        "max": v[-1],
    }


def fmt_summary(s, unit="ms"):
    if s.get("n", 0) == 0:
        return "sem amostras"
    return ("n=%d  min=%.3f  média=%.3f  mediana=%.3f  p95=%.3f  max=%.3f %s"
            % (s["n"], s["min"], s["media"], s["mediana"], s["p95"], s["max"], unit))
