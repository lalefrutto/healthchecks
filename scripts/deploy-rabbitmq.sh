#!/usr/bin/env bash
# Деплой RabbitMQ (чарт cloudpirates/rabbitmq) с учёткой из Vault.
#
#   scripts/deploy-rabbitmq.sh [дополнительные аргументы helm upgrade]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CHART="oci://registry-1.docker.io/cloudpirates/rabbitmq"
CHART_VERSION="${RABBITMQ_CHART_VERSION:-0.21.28}"
VALUES_DIR="$ROOT_DIR/deploy/rabbitmq"

vault_login
helm_secrets_deploy "${RELEASE:-rabbitmq}" "${NAMESPACE:-healthchecks}" "$CHART" \
  --version "$CHART_VERSION" \
  -f "$VALUES_DIR/values.yaml" \
  -f "$VALUES_DIR/secrets.yaml" \
  "$@"
