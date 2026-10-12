"""Testes de integração: sobem os processos de verdade em localhost.

Rodar a partir da raiz do repositório:
    python3 -m pytest -v tests/
"""
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest
import zmq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reqrep.server import safe_calc  # noqa: E402

PY = sys.executable


def ports(n):
    base = random.randint(20000, 40000)
    return [str(base + i) for i in range(n)]


def start(*args):
    return subprocess.Popen([PY, *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def run(*args, timeout=30):
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout)


@pytest.fixture
def procs():
    started = []
    yield started
    for p in started:
        p.terminate()
    for p in started:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


# ------------------------------------------------------------------ REQ-REP
def test_safe_calc():
    assert safe_calc("(2+3)*7") == 35
    assert safe_calc("2**10 - 1") == 1023
    for bad in ("__import__('os')", "open('x')", "9**9999", "a+1"):
        with pytest.raises(ValueError):
            safe_calc(bad)


def test_reqrep_comandos_e_protocolo_original(procs):
    p1, p2 = ports(2)
    procs.append(start("reqrep/server.py", "--bind", p1, p2))
    time.sleep(0.8)
    out = run("reqrep/client.py", "--server", "localhost:" + p1, "CALC", "6*7").stdout
    assert out.startswith("OK  42")
    out = run("reqrep/client.py", "--server", "localhost:" + p2, "UPPER", "sd ufg").stdout
    assert "SD UFG" in out
    # cliente "original": texto puro num socket REQ -> resposta com "*"
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.REQ)
    s.connect("tcp://localhost:" + p1)
    s.send(b"Hello world 1")
    assert s.recv() == b"Hello world 1*"
    s.send(b"STOP")                       # STOP original encerra o servidor
    s.close(linger=1000)
    procs[0].wait(timeout=5)
    assert procs[0].returncode == 0


def test_cliente_desiste_sem_servidor():
    (p,) = ports(1)
    t0 = time.time()
    r = run("reqrep/client.py", "--server", "localhost:" + p, "--timeout", "0.3",
            "--retries", "2", "TIME")
    assert r.returncode == 2
    assert "não responderam" in r.stderr
    assert time.time() - t0 < 5


def test_broker_distribui_entre_servidores(procs):
    fe, be = ports(2)
    procs.append(start("reqrep/broker.py", "--frontend", fe, "--backend", be,
                       "--report", "0"))
    for _ in range(2):
        procs.append(start("reqrep/server.py", "--connect", "localhost:" + be,
                           "--quiet", "--no-stop"))
    # espera os dois servidores se conectarem ao broker (até ~10 s)
    seen = set()
    for _ in range(40):
        r = run("reqrep/client.py", "--server", "localhost:" + fe, "--timeout", "1", "HOST")
        seen.add(r.stdout.split()[1] if r.returncode == 0 else None)
        if len(seen - {None}) == 2:
            break
        time.sleep(0.25)
    out = run("reqrep/client.py", "--server", "localhost:" + fe, "--bench", "40").stdout
    shares = [line for line in out.splitlines() if "(50%)" in line]
    assert len(shares) == 2, out


# ------------------------------------------------------------------ PUB-SUB
def test_pubsub_via_proxy_filtra_topicos(procs):
    xsub, xpub = ports(2)
    procs.append(start("pubsub/proxy.py", "--xsub", xsub, "--xpub", xpub, "--report", "0"))
    time.sleep(0.5)
    procs.append(start("pubsub/publisher.py", "--connect", "localhost:" + xsub,
                       "--interval", "0.05", "--name", "pubA"))
    procs.append(start("pubsub/publisher.py", "--connect", "localhost:" + xsub,
                       "--interval", "0.05", "--name", "pubB"))
    r = run("pubsub/subscriber.py", "--connect", "localhost:" + xpub,
            "--topics", "SENSOR", "--count", "20")
    lines = [line for line in r.stdout.splitlines() if line.startswith(("SENSOR", "TIME", "SYS"))]
    assert len(lines) == 20
    assert all(line.startswith("SENSOR") for line in lines)
    assert "de pubA" in r.stdout and "de pubB" in r.stdout   # fan-in dos dois


# ----------------------------------------------------------------- PIPELINE
def test_pipeline_completo(procs):
    src1, src2, sink, ctrl = ports(4)
    sink_p = start("pipeline/sink.py", "--port", sink, "--control-port", ctrl,
                   "--sources", "2")
    workers = [start("pipeline/worker.py", "--id", w,
                     "--sources", "localhost:" + src1, "localhost:" + src2,
                     "--sink", "localhost", "--sink-port", sink, "--control-port", ctrl)
               for w in ("W1", "W2")]
    procs.extend([sink_p, *workers])
    vents = [start("pipeline/ventilator.py", "--id", i, "--port", port,
                   "--sink", "localhost:" + sink, "--tasks", "15", "--max-load", "3",
                   "--wait", "1")
             for i, port in (("1", src1), ("2", src2))]
    for v in vents:
        v.wait(timeout=30)
    out, _ = sink_p.communicate(timeout=30)
    assert "Tarefas: 30 de 2 fonte(s)" in out
    assert "KILL enviado" in out
    for w in workers:                       # workers encerram sozinhos com KILL
        w.wait(timeout=10)
        assert "recebeu KILL" in w.stdout.read()
