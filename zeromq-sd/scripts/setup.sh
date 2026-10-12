#!/usr/bin/env bash
# Prepara uma máquina (EC2, VM, notebook...) para rodar os programas:
# cria um ambiente virtual .venv na raiz do repositório e instala o pyzmq.
#
#   bash scripts/setup.sh && source .venv/bin/activate
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" 2>/dev/null; then
  echo "Instalando python3-venv (precisa de sudo)..."
  sudo apt-get update -y && sudo apt-get install -y python3-venv python3-pip
fi
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import zmq; print('pyzmq', zmq.__version__, '| libzmq', zmq.zmq_version())"
echo "Pronto. Ative com: source .venv/bin/activate"
