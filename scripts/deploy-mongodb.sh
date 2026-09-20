#!/usr/bin/env bash
# Деплой MongoDB (cloudpirates/mongodb) и mongo-express (cowboysysop/mongo-express)
# с паролями из Vault (secret/mongodb).
#
#   scripts/deploy-mongodb.sh [дополнительные аргументы helm upgrade]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NAMESPACE="${NAMESPACE:-healthchecks}"
VALUES_DIR="$ROOT_DIR/deploy/mongodb"

vault_login

helm_secrets_deploy "${RELEASE:-mongodb}" "$NAMESPACE" oci://registry-1.docker.io/cloudpirates/mongodb \
  --version "${MONGODB_CHART_VERSION:-0.18.14}" \
  -f "$VALUES_DIR/values.yaml" \
  -f "$VALUES_DIR/secrets.yaml" \
  "$@"

helm repo add cowboysysop https://cowboysysop.github.io/charts/ >/dev/null 2>&1 || true
helm_secrets_deploy mongo-express "$NAMESPACE" cowboysysop/mongo-express \
  --version "${MONGO_EXPRESS_CHART_VERSION:-7.0.0}" \
  -f "$VALUES_DIR/mongo-express-values.yaml" \
  -f "$VALUES_DIR/mongo-express-secrets.yaml"
