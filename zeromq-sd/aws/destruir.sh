#!/usr/bin/env bash
# Encerra as instâncias e apaga o security group criados por provisionar.sh,
# para não deixar nada cobrando na conta AWS.
#
#   bash aws/destruir.sh            (mesma região usada no provisionamento)
set -euo pipefail
# AWS_REGION, se definida, escolhe a região (vale para o AWS CLI v1 e v2)
[[ -n "${AWS_REGION:-}" ]] && export AWS_DEFAULT_REGION="$AWS_REGION"
PROJECT=${PROJECT:-zmq-sd}

IDS=$(aws ec2 describe-instances \
        --filters Name=tag:Project,Values="$PROJECT" \
                  Name=instance-state-name,Values=pending,running,stopping,stopped \
        --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -n "$IDS" ]]; then
  echo ">> encerrando: $IDS"
  aws ec2 terminate-instances --instance-ids $IDS >/dev/null
  aws ec2 wait instance-terminated --instance-ids $IDS
else
  echo ">> nenhuma instância com Project=$PROJECT"
fi

SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$PROJECT-sg" \
       --query 'SecurityGroups[0].GroupId' --output text)
if [[ "$SG" != "None" ]]; then
  aws ec2 delete-security-group --group-id "$SG"
  echo ">> security group $SG removido"
fi
echo "Tudo limpo."
