#!/usr/bin/env bash
# Деплой MinIO (официальный чарт minio/minio) с учётками из Vault (secret/minio).
#
#   scripts/deploy-minio.sh [дополнительные аргументы helm upgrade]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

helm repo add minio https://charts.min.io/ >/dev/null 2>&1 || true

vault_login
helm_secrets_deploy "${RELEASE:-minio}" "${NAMESPACE:-healthchecks}" minio/minio \
  --version "${MINIO_CHART_VERSION:-5.4.0}" \
  -f "$ROOT_DIR/deploy/minio/values.yaml" \
  -f "$ROOT_DIR/deploy/minio/secrets.yaml" \
  "$@"
