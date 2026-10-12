#!/bin/bash
# Executado pelo cloud-init na PRIMEIRA inicialização de cada instância EC2
# (Ubuntu). O provisionar.sh troca __REPO_URL__ pela URL do seu repositório.
# Log: /var/log/cloud-init-output.log
set -eux
apt-get update -y
apt-get install -y python3-venv python3-pip git
cd /home/ubuntu
sudo -H -u ubuntu git clone "__REPO_URL__" zeromq-sd
cd zeromq-sd
sudo -H -u ubuntu python3 -m venv .venv
sudo -H -u ubuntu .venv/bin/pip install -r requirements.txt
# ativa o venv automaticamente ao entrar por SSH
echo 'cd ~/zeromq-sd && source .venv/bin/activate' >> /home/ubuntu/.bashrc
touch /home/ubuntu/PRONTO
