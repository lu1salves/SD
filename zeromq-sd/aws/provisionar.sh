#!/usr/bin/env bash
# Cria N instâncias EC2 (Ubuntu 24.04) prontas para os experimentos com ZeroMQ.
#
# Pré-requisitos: AWS CLI v2 configurado (aws configure) e um par de chaves
# EC2 já criado na região. Uso:
#
#   KEY_NAME=minha-chave REPO_URL=https://github.com/USUARIO/zeromq-sd.git \
#       bash aws/provisionar.sh
#
# Variáveis opcionais:
#   N=4               nº de instâncias
#   TYPE=t3.micro     tipo de instância
#   AWS_REGION=...    região (padrão: a do 'aws configure')
#   PROJECT=zmq-sd    tag usada para achar/destruir os recursos depois
#   EXTRA_CIDR=x.x.x.x/32  libera as portas ZeroMQ também para este IP/rede
#                     (ex.: IP público de uma instância em OUTRA região)
#
# Regras do security group criado:
#   * SSH (22) apenas a partir do seu IP público atual;
#   * TCP 5555-5570 entre as instâncias do próprio grupo (use os IPs PRIVADOS);
#   * TCP 5555-5570 a partir de EXTRA_CIDR, se informado.
set -euo pipefail
# AWS_REGION, se definida, escolhe a região (vale para o AWS CLI v1 e v2)
[[ -n "${AWS_REGION:-}" ]] && export AWS_DEFAULT_REGION="$AWS_REGION"

: "${KEY_NAME:?defina KEY_NAME com o nome do par de chaves EC2}"
: "${REPO_URL:?defina REPO_URL com a URL (https) do repositório git}"
N=${N:-4}
TYPE=${TYPE:-t3.micro}
PROJECT=${PROJECT:-zmq-sd}
SG_NAME="$PROJECT-sg"
HERE=$(cd "$(dirname "$0")" && pwd)

echo ">> região: ${AWS_REGION:-$(aws configure get region 2>/dev/null || echo "?")}"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
        --query 'Vpcs[0].VpcId' --output text)
[[ "$VPC" == "None" ]] && { echo "Sem VPC padrão nesta região."; exit 1; }

SG=$(aws ec2 describe-security-groups \
       --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC" \
       --query 'SecurityGroups[0].GroupId' --output text)
if [[ "$SG" == "None" ]]; then
  SG=$(aws ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC" \
         --description "ZeroMQ - Sistemas Distribuidos" \
         --tag-specifications "ResourceType=security-group,Tags=[{Key=Project,Value=$PROJECT}]" \
         --query GroupId --output text)
  MYIP=$(curl -s https://checkip.amazonaws.com)
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
      --protocol tcp --port 22 --cidr "$MYIP/32" >/dev/null
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
      --ip-permissions "IpProtocol=tcp,FromPort=5555,ToPort=5570,UserIdGroupPairs=[{GroupId=$SG}]" >/dev/null
  echo ">> security group $SG criado (SSH liberado para $MYIP)"
else
  echo ">> reaproveitando security group $SG"
fi
if [[ -n "${EXTRA_CIDR:-}" ]]; then
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
      --protocol tcp --port 5555-5570 --cidr "$EXTRA_CIDR" >/dev/null 2>&1 || true
  echo ">> portas 5555-5570 liberadas também para $EXTRA_CIDR"
fi

AMI=$(aws ssm get-parameters \
        --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
        --query 'Parameters[0].Value' --output text)
echo ">> AMI Ubuntu 24.04: $AMI"

USERDATA=$(mktemp)
sed "s|__REPO_URL__|$REPO_URL|" "$HERE/user-data.sh" > "$USERDATA"

IDS=$(aws ec2 run-instances --image-id "$AMI" --count "$N" --instance-type "$TYPE" \
        --key-name "$KEY_NAME" --security-group-ids "$SG" \
        --user-data "file://$USERDATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Project,Value=$PROJECT}]" \
        --query 'Instances[].InstanceId' --output text)
rm -f "$USERDATA"
i=1
for id in $IDS; do
  aws ec2 create-tags --resources "$id" --tags "Key=Name,Value=$PROJECT-$i"
  i=$((i + 1))
done
echo ">> aguardando as instâncias ficarem 'running'..."
aws ec2 wait instance-running --instance-ids $IDS

aws ec2 describe-instances --instance-ids $IDS \
  --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value,InstanceId,Placement.AvailabilityZone,PublicIpAddress,PrivateIpAddress]' \
  --output table

cat <<EOF

Pronto. O cloud-init leva ~1-2 min instalando Python/pyzmq e clonando o repo
(quando terminar, existe o arquivo ~/PRONTO). Para entrar numa instância:

  ssh -i ~/.ssh/$KEY_NAME.pem ubuntu@<IP_PUBLICO>

Entre as instâncias use os IPs PRIVADOS (172.31.x.x). Para apagar tudo:

  bash aws/destruir.sh
EOF
