#!/usr/bin/env bash
# Деплой Redis (charts/redis) с паролем из Vault и RedisInsight (heywood8/redisinsight).
#
#   scripts/deploy-redis.sh [дополнительные аргументы helm upgrade]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NAMESPACE="${NAMESPACE:-healthchecks}"

vault_login
helm_secrets_deploy "${RELEASE:-redis}" "$NAMESPACE" "$ROOT_DIR/charts/redis" \
  -f "$ROOT_DIR/deploy/redis/secrets.yaml" \
  "$@"

# RedisInsight — UI для Redis; секретов не требует (подключение к Redis задаётся в UI)
helm repo add heywood8 https://heywood8.github.io/helm-charts >/dev/null 2>&1 || true
echo "==> helm upgrade --install redisinsight ($NAMESPACE)"
helm upgrade --install redisinsight heywood8/redisinsight \
  --version "${REDISINSIGHT_CHART_VERSION:-0.4.5}" \
  --namespace "$NAMESPACE" \
  -f "$ROOT_DIR/deploy/redis/redisinsight-values.yaml" \
  --wait --timeout 10m
