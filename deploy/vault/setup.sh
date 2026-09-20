#!/usr/bin/env bash
# Инициализация и настройка Vault для healthchecks (локальный minikube).
#
# Идемпотентен — можно запускать повторно (например, после перезапуска
# кластера, когда Vault снова запечатан):
#   1. vault operator init (один раз) -> ключ и root-токен в deploy/vault/.vault-keys.json
#   2. unseal
#   3. KV v2 secrets engine на пути secret/
#   4. секреты приложения secret/healthchecks (генерируются, если ещё нет)
#   5. policy healthchecks-read (deploy/vault/policies/healthchecks-read.hcl)
#   6. AppRole healthchecks с этой policy -> ROLE_ID / SECRET_ID в .env
#
# Все команды vault выполняются внутри пода vault-0 через kubectl exec, поэтому
# доступ к Vault с хоста для этого скрипта не нужен.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT_NS="${VAULT_NS:-vault}"
VAULT_POD="${VAULT_POD:-vault-0}"
KEYS_FILE="$ROOT_DIR/deploy/vault/.vault-keys.json"
ENV_FILE="$ROOT_DIR/.env"
POLICY_FILE="$ROOT_DIR/deploy/vault/policies/healthchecks-read.hcl"

# Адрес Vault с хоста (через Ingress). Записывается в .env для vals/helm-secrets.
VAULT_EXTERNAL_ADDR="${VAULT_EXTERNAL_ADDR:-https://vault.local}"

vexec() { kubectl -n "$VAULT_NS" exec -i "$VAULT_POD" -- "$@"; }
vault_root() { vexec env VAULT_TOKEN="$ROOT_TOKEN" vault "$@"; }
json_field() { python -c "import sys, json; print(json.load(sys.stdin)$1)"; }
rand_secret() { openssl rand -base64 48 | tr -d '/+=' | cut -c1-"$1"; }

echo "==> Vault: $VAULT_NS/$VAULT_POD"
kubectl -n "$VAULT_NS" wait --for=condition=PodReadyToStartContainers "pod/$VAULT_POD" --timeout=120s >/dev/null

# --- 1. init ---------------------------------------------------------------
status="$(vexec vault status -format=json 2>/dev/null || true)"
if ! grep -q '"initialized": *true' <<<"$status"; then
  echo "==> operator init"
  vexec vault operator init -key-shares=1 -key-threshold=1 -format=json >"$KEYS_FILE"
  echo "    ключи сохранены в $KEYS_FILE (в git не попадает)"
elif [ ! -f "$KEYS_FILE" ]; then
  echo "!! Vault уже инициализирован, но $KEYS_FILE не найден — восстановить unseal key нечем" >&2
  exit 1
fi

UNSEAL_KEY="$(json_field '["unseal_keys_b64"][0]' <"$KEYS_FILE")"
ROOT_TOKEN="$(json_field '["root_token"]' <"$KEYS_FILE")"

# --- 2. unseal -------------------------------------------------------------
if grep -q '"sealed": *true' <<<"$status" || ! grep -q '"initialized"' <<<"$status"; then
  echo "==> unseal"
  vexec vault operator unseal "$UNSEAL_KEY" >/dev/null
fi
kubectl -n "$VAULT_NS" wait --for=condition=Ready "pod/$VAULT_POD" --timeout=60s >/dev/null

# --- 3. KV v2 --------------------------------------------------------------
if ! vault_root secrets list -format=json | grep -q '"secret/"'; then
  echo "==> secrets enable kv-v2 at secret/"
  vault_root secrets enable -path=secret kv-v2 >/dev/null
fi

# --- 4. секреты приложения -------------------------------------------------
if ! vault_root kv get secret/healthchecks >/dev/null 2>&1; then
  echo "==> kv put secret/healthchecks (генерируем новые значения)"
  vault_root kv put secret/healthchecks \
    SECRET_KEY="$(rand_secret 50)" \
    DB_PASSWORD="$(rand_secret 32)" >/dev/null
else
  echo "==> secret/healthchecks уже существует, не трогаем"
fi

# --- 5. policy -------------------------------------------------------------
echo "==> policy write healthchecks-read"
vault_root policy write healthchecks-read - <"$POLICY_FILE" >/dev/null

# --- 6. AppRole ------------------------------------------------------------
if ! vault_root auth list -format=json | grep -q '"approle/"'; then
  echo "==> auth enable approle"
  vault_root auth enable approle >/dev/null
fi
echo "==> approle role healthchecks"
vault_root write auth/approle/role/healthchecks \
  token_policies="healthchecks-read" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0 \
  secret_id_num_uses=0 >/dev/null

ROLE_ID="$(vault_root read -field=role_id auth/approle/role/healthchecks/role-id)"
SECRET_ID="$(vault_root write -f -field=secret_id auth/approle/role/healthchecks/secret-id)"

# --- .env для vals / helm-secrets -------------------------------------------
echo "==> записываем $ENV_FILE"
cat >"$ENV_FILE" <<EOF
# Сгенерировано deploy/vault/setup.sh — не коммитить (см. .env.example)
VAULT_ADDR=$VAULT_EXTERNAL_ADDR
# Локальный self-signed CA; в облаке — VAULT_CACERT=/path/to/ca.crt
VAULT_SKIP_VERIFY=true
VAULT_AUTH_METHOD=approle
VAULT_ROLE_ID=$ROLE_ID
VAULT_SECRET_ID=$SECRET_ID
EOF

echo
echo "Готово. Vault UI: $VAULT_EXTERNAL_ADDR/ui (root-токен — в $KEYS_FILE)"
echo "Деплой приложения: scripts/deploy.sh"
