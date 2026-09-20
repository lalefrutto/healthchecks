#!/usr/bin/env bash
# Деплой healthchecks Helm-чартом с секретами из Vault.
#
#   scripts/deploy.sh [дополнительные аргументы helm upgrade]
#
# Схема:
#   .env (VAULT_ADDR + AppRole)  ->  vault login (AppRole)  ->  короткоживущий токен
#   -> helm-secrets (backend vals) разворачивает ref+vault:// в secrets.yaml
#   -> helm upgrade --install
#
# Требуется: helm, helm-secrets (helm plugin install ...), vals, vault CLI, kubectl.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="$ROOT_DIR/charts/healthchecks"
RELEASE="${RELEASE:-healthchecks}"
NAMESPACE="${NAMESPACE:-healthchecks}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "!! $ENV_FILE не найден. Скопируйте .env.example или запустите deploy/vault/setup.sh" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

# AppRole -> токен. vals умеет логиниться по AppRole сам, но на Windows он
# собирает путь auth\approle\login с обратными слэшами, поэтому логинимся
# через vault CLI и отдаём vals уже готовый токен.
if [ "${VAULT_AUTH_METHOD:-approle}" = "approle" ]; then
  : "${VAULT_ROLE_ID:?VAULT_ROLE_ID не задан в $ENV_FILE}"
  : "${VAULT_SECRET_ID:?VAULT_SECRET_ID не задан в $ENV_FILE}"
  echo "==> vault login (AppRole) at $VAULT_ADDR"
  VAULT_TOKEN="$(vault write -field=token auth/approle/login \
    role_id="$VAULT_ROLE_ID" secret_id="$VAULT_SECRET_ID")"
  export VAULT_TOKEN
  export VAULT_AUTH_METHOD=token
fi

echo "==> helm secrets upgrade --install $RELEASE ($NAMESPACE)"
helm secrets --backend vals upgrade --install "$RELEASE" "$CHART" \
  --namespace "$NAMESPACE" --create-namespace \
  -f "$CHART/values.yaml" \
  -f "$CHART/secrets.yaml" \
  --wait --timeout 10m \
  "$@"
