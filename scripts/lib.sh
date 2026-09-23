#!/usr/bin/env bash
# Общая часть deploy-скриптов: .env -> AppRole-логин в Vault -> helm secrets.
# Подключается через `source "$(dirname "$0")/lib.sh"`.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

# Загружает .env и получает токен Vault по AppRole.
# vals умеет логиниться по AppRole сам, но на Windows собирает путь
# auth\approle\login с обратными слэшами, поэтому логинимся через vault CLI
# и отдаём vals уже готовый токен.
vault_login() {
  if [ ! -f "$ENV_FILE" ]; then
    echo "!! $ENV_FILE не найден. Скопируйте .env.example или запустите deploy/vault/setup.sh" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a

  # Адрес Vault из .env можно перекрыть снаружи. Нужно, когда https://vault.local
  # недоступен (нет `minikube tunnel` — он требует прав администратора на Windows):
  #   VAULT_ADDR_OVERRIDE=http://127.0.0.1:8200  (kubectl port-forward -n vault svc/vault 8200:8200)
  # Так работает scripts/bootstrap.sh; сам .env при этом остаётся штатным.
  if [ -n "${VAULT_ADDR_OVERRIDE:-}" ]; then
    export VAULT_ADDR="$VAULT_ADDR_OVERRIDE"
  fi

  if [ "${VAULT_AUTH_METHOD:-approle}" = "approle" ]; then
    : "${VAULT_ROLE_ID:?VAULT_ROLE_ID не задан в $ENV_FILE}"
    : "${VAULT_SECRET_ID:?VAULT_SECRET_ID не задан в $ENV_FILE}"
    echo "==> vault login (AppRole) at $VAULT_ADDR"
    VAULT_TOKEN="$(vault write -field=token auth/approle/login \
      role_id="$VAULT_ROLE_ID" secret_id="$VAULT_SECRET_ID")"
    export VAULT_TOKEN
    export VAULT_AUTH_METHOD=token
  fi
}

# helm_secrets_deploy <release> <namespace> <chart> [helm args...]
# Ссылки ref+vault:// в -f файлах разворачивает helm-secrets с backend'ом vals.
helm_secrets_deploy() {
  local release="$1" namespace="$2" chart="$3"; shift 3
  echo "==> helm secrets upgrade --install $release ($namespace)"
  helm secrets --backend vals upgrade --install "$release" "$chart" \
    --namespace "$namespace" --create-namespace \
    --wait --timeout 10m \
    "$@"
}
