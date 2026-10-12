#!/usr/bin/env bash
# Simula N "máquinas" numa única máquina Linux usando namespaces de rede.
# Cada host tem sua própria pilha TCP/IP, interface e IP (10.20.0.X) e um
# hostname próprio; todos ligados por uma bridge, como numa sub-rede (VPC).
# Opcionalmente adiciona atraso de rede (tc netem) para imitar WAN/regiões.
#
# Uso (como root):
#   sudo scripts/rede_simulada.sh up 4            # cria host1..host4
#   sudo scripts/rede_simulada.sh up 4 20ms       # idem, +20 ms em cada sentido
#   sudo scripts/rede_simulada.sh run host2 python3 reqrep/client.py --server 10.20.0.1:5555
#   sudo scripts/rede_simulada.sh down
#
# Requer: iproute2 (ip, tc) e unshare (util-linux).
set -euo pipefail

BR=br-zmq
NET=10.20.0

up() {
  local n=${1:-4} delay=${2:-}
  ip link add "$BR" type bridge 2>/dev/null || true
  ip addr add "$NET.254/24" dev "$BR" 2>/dev/null || true
  ip link set "$BR" up
  # Se o Docker estiver instalado, a política FORWARD do iptables é DROP e
  # bloquearia o tráfego entre os hosts da bridge: libera só esta bridge.
  if command -v iptables >/dev/null; then
    iptables -C FORWARD -i "$BR" -o "$BR" -j ACCEPT 2>/dev/null ||
      iptables -I FORWARD -i "$BR" -o "$BR" -j ACCEPT
  fi
  for i in $(seq 1 "$n"); do
    local ns="host$i"
    ip netns add "$ns"
    ip link add "veth$i" type veth peer name eth0 netns "$ns"
    ip link set "veth$i" master "$BR" up
    ip -n "$ns" addr add "$NET.$i/24" dev eth0
    ip -n "$ns" link set eth0 up
    ip -n "$ns" link set lo up
    ip -n "$ns" route add default via "$NET.254"   # "roteador" da sub-rede
    if [[ -n "$delay" ]]; then
      ip netns exec "$ns" tc qdisc add dev eth0 root netem delay "$delay"
    fi
    echo "$ns -> $NET.$i ${delay:+(atraso $delay por sentido)}"
  done
}

down() {
  for ns in $(ip netns list | awk '/^host[0-9]+/{print $1}'); do
    ip netns del "$ns"
  done
  ip link del "$BR" 2>/dev/null || true
  command -v iptables >/dev/null && iptables -D FORWARD -i "$BR" -o "$BR" -j ACCEPT 2>/dev/null || true
  echo "rede simulada removida"
}

run() {
  local ns=$1; shift
  # unshare --uts dá a cada "máquina" o próprio hostname (aparece nos logs)
  exec ip netns exec "$ns" unshare --uts sh -c 'hostname "$0"; exec "$@"' "$ns" "$@"
}

case "${1:-}" in
  up)   shift; up "$@" ;;
  down) down ;;
  run)  shift; run "$@" ;;
  *) echo "uso: $0 up [N] [atraso] | run hostX comando... | down"; exit 1 ;;
esac
