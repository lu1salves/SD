#!/usr/bin/env bash
# Roda os três cenários em 4 "máquinas" simuladas (namespaces de rede) e
# guarda as saídas em logs/. Precisa de root e do scripts/rede_simulada.sh.
#
#   sudo PY=.venv/bin/python scripts/demo_rede_simulada.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY=${PY:-python3}
NET=scripts/rede_simulada.sh
LOG=${LOG:-logs}
mkdir -p "$LOG"
case $PY in /*) ;; */*) PY=$PWD/$PY ;; *) PY=$(command -v "$PY") ;; esac
# on HOST args...   -> roda em primeiro plano na "máquina" HOST
on() { local h=$1; shift; $NET run "$h" "$PY" "$@"; }
# bg HOST LOG args... -> roda em segundo plano; imprime o PID do python
#   (rede_simulada.sh usa exec em cadeia, então o PID é o do próprio python)
bg() { local h=$1 out=$2; shift 2; ( exec $NET run "$h" "$PY" "$@" ) >"$LOG/$out" 2>&1 & echo $!; }
waitpids() { for p in "$@"; do while kill -0 "$p" 2>/dev/null; do sleep 0.2; done; done; }
stop() { kill "$@" 2>/dev/null; waitpids "$@"; }

$NET down >/dev/null 2>&1; $NET up 4

echo "===== 1. REQ-REP: servidor em host1, clientes em host2 ====="
S=$(bg host1 rr_servidor.log reqrep/server.py --quiet); sleep 1
on host2 reqrep/client.py --server 10.20.0.1:5555 HOST
on host2 reqrep/client.py --server 10.20.0.1:5556 CALC "(1+2)*3**4"
echo "--- cliente ORIGINAL (original/04-22/client1.py) contra o servidor novo:"
tmp=$(mktemp -d); cp original/04-22/*.py "$tmp"
sed -i 's/^HOST .*/HOST = "10.20.0.1"/; s/4567/5555/; s/4568/5556/' "$tmp/constCS.py"
$NET run host2 sh -c "cd '$tmp' && exec '$PY' client1.py"
echo "--- benchmark mesma máquina (host1 -> host1):"
on host1 reqrep/client.py --server 127.0.0.1:5555 --bench 1000 --payload 64
echo "--- benchmark máquinas diferentes (host2 -> host1):"
on host2 reqrep/client.py --server 10.20.0.1:5555 --bench 1000 --payload 64
stop "$S"

echo; echo "===== 2. REQ-REP com broker em host1 e servidores em host2..host4 ====="
B=$(bg host1 rr_broker.log reqrep/broker.py --report 0); sleep 0.5
W2=$(bg host2 rr_w2.log reqrep/server.py --connect 10.20.0.1:5560 --quiet --no-stop)
W3=$(bg host3 rr_w3.log reqrep/server.py --connect 10.20.0.1:5560 --quiet --no-stop)
W4=$(bg host4 rr_w4.log reqrep/server.py --connect 10.20.0.1:5560 --quiet --no-stop)
sleep 1
on host1 reqrep/client.py --server 10.20.0.1:5559 --bench 300
echo "--- derrubando o servidor de host3 e repetindo:"
stop "$W3"; sleep 0.5
on host1 reqrep/client.py --server 10.20.0.1:5559 --bench 300
stop "$B" "$W2" "$W4"

echo; echo "===== 3. PUB-SUB: proxy em host1, publicadores em host2 e host3 ====="
X=$(bg host1 ps_proxy.log pubsub/proxy.py --report 0); sleep 0.5
P2=$(bg host2 ps_pub2.log pubsub/publisher.py --connect 10.20.0.1:5561 --interval 0.2 --limite 26)
P3=$(bg host3 ps_pub3.log pubsub/publisher.py --connect 10.20.0.1:5561 --interval 0.2 --limite 26)
on host1 pubsub/subscriber.py --connect 10.20.0.1:5562 --topics ALERT --duration 6 >"$LOG/ps_sub_alert.log" 2>&1 &
SA=$!
on host4 pubsub/subscriber.py --connect 10.20.0.1:5562 --topics TIME SENSOR --duration 6 --quiet
wait $SA; echo "--- assinante de ALERT em host1:"; tail -6 "$LOG/ps_sub_alert.log"
stop "$P2" "$P3"
echo "--- chat entre host2 e host4 via proxy:"
(sleep 1; echo "oi do host2"; sleep 1.5; echo /sair) | \
  on host2 pubsub/chat.py --proxy 10.20.0.1 --nick ana --room sd >"$LOG/chat_ana.log" 2>&1 &
(sleep 1.5; echo "oi ana, aqui é o host4"; sleep 1.5; echo /sair) | \
  on host4 pubsub/chat.py --proxy 10.20.0.1 --nick beto --room sd >"$LOG/chat_beto.log" 2>&1
wait; echo "[ana]"; cat "$LOG/chat_ana.log"; echo "[beto]"; cat "$LOG/chat_beto.log"
echo "--- proxy:"; cat "$LOG/ps_proxy.log"
stop "$X"

echo; echo "===== 4. PIPELINE: speedup com 1, 2 e 3 workers (host2..host4) ====="
rm -f "$LOG/pipeline.csv"
for n in 1 2 3; do
  K=$(bg host1 "pl_sink_$n.log" pipeline/sink.py --sources 2 --csv "$LOG/pipeline.csv" --label "sleep $n worker(s)")
  WS=()
  for h in $(seq 2 $((n + 1))); do
    WS+=("$(bg "host$h" "pl_worker_${n}_$h.log" pipeline/worker.py \
            --sources 10.20.0.1:5563 10.20.0.2:5564 --sink 10.20.0.1)")
  done
  on host1 pipeline/ventilator.py --id 1 --sink 10.20.0.1 --tasks 50 --max-load 20 --seed 1 --wait 1.5 >/dev/null &
  on host2 pipeline/ventilator.py --id 2 --sink 10.20.0.1 --tasks 50 --max-load 20 --seed 2 --wait 1.5 >/dev/null
  waitpids "$K" "${WS[@]}"; wait
  sed -n '/Relatório/,$p' "$LOG/pl_sink_$n.log"
done
echo "--- tabela (CSV):"; cat "$LOG/pipeline.csv"

$NET down
