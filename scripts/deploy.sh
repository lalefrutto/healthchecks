#!/usr/bin/env bash
# Деплой healthchecks Helm-чартом с секретами из Vault.
#
#   scripts/deploy.sh [дополнительные аргументы helm upgrade]
#
# .env (VAULT_ADDR + AppRole) -> vault login -> helm-secrets (vals) разворачивает
# ref+vault:// в .helm/secrets.yaml -> helm upgrade --install.
# Требуется: helm, helm-secrets, vals, vault CLI, kubectl.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CHART="$ROOT_DIR/.helm"

vault_login
helm_secrets_deploy "${RELEASE:-healthchecks}" "${NAMESPACE:-healthchecks}" "$CHART" \
  -f "$CHART/values.yaml" \
  -f "$CHART/secrets.yaml" \
  "$@"
