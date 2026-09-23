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
# Чарт подставляет storageClassName в PVC как есть, поэтому пустое значение
# даёт null: класс при создании дописывает сам Kubernetes. На повторном деплое
# server-side apply пытается вернуть null и упирается в "spec is immutable
# after creation" — PVC уже связан. Чтобы скрипт оставался идемпотентным,
# имя класса по умолчанию передаём явно.
STORAGE_CLASS="${REDISINSIGHT_STORAGE_CLASS:-$(kubectl get storageclass \
  -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}' \
  | awk '{print $1}')}"
sc_args=()
[ -n "$STORAGE_CLASS" ] && sc_args=(--set "persistentVolumeClaim.storageClassName=$STORAGE_CLASS")

echo "==> helm upgrade --install redisinsight ($NAMESPACE, storageClass=${STORAGE_CLASS:-<по умолчанию>})"
helm upgrade --install redisinsight heywood8/redisinsight \
  --version "${REDISINSIGHT_CHART_VERSION:-0.4.5}" \
  --namespace "$NAMESPACE" \
  -f "$ROOT_DIR/deploy/redis/redisinsight-values.yaml" \
  ${sc_args[@]+"${sc_args[@]}"} \
  --wait --timeout 10m
