#!/usr/bin/env bash
# Инициализация и настройка Vault для healthchecks (локальный minikube).
#
# Идемпотентен — можно запускать повторно (например, после перезапуска
# кластера, когда Vault снова запечатан):
#   1. vault operator init (один раз) -> ключ и root-токен в deploy/vault/.vault-keys.json
#   2. unseal
#   3. KV v2 secrets engine на пути secret/
#   4. секреты: secret/healthchecks, secret/rabbitmq, secret/flower, secret/redis, secret/mongodb, secret/minio, secret/registry (генерируются, если ещё нет)
#   5. policies из deploy/vault/policies/*.hcl (по одной на компонент)
#   6. AppRole healthchecks со всеми этими policy -> ROLE_ID / SECRET_ID в .env
#
# Все команды vault выполняются внутри пода vault-0 через kubectl exec, поэтому
# доступ к Vault с хоста для этого скрипта не нужен.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT_NS="${VAULT_NS:-vault}"
VAULT_POD="${VAULT_POD:-vault-0}"
KEYS_FILE="$ROOT_DIR/deploy/vault/.vault-keys.json"
ENV_FILE="$ROOT_DIR/.env"
POLICY_DIR="$ROOT_DIR/deploy/vault/policies"

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

# --- 4. секреты компонентов ------------------------------------------------
# ensure_secret <path> key=value... — создаёт секрет, только если его ещё нет
ensure_secret() {
  local path="$1"; shift
  if vault_root kv get "$path" >/dev/null 2>&1; then
    echo "==> $path уже существует, не трогаем"
  else
    echo "==> kv put $path (генерируем новые значения)"
    vault_root kv put "$path" "$@" >/dev/null
  fi
}

# Django-приложение
ensure_secret secret/healthchecks \
  SECRET_KEY="$(rand_secret 50)" \
  DB_PASSWORD="$(rand_secret 32)"

# RabbitMQ (Задание 3): учётка для чарта и клиентов, erlang cookie для кластера
ensure_secret secret/rabbitmq \
  username="healthchecks" \
  password="$(rand_secret 32)" \
  erlang_cookie="$(rand_secret 40)"

# Flower (Задание 3): HTTP basic auth для UI, формат user:password
ensure_secret secret/flower \
  basic_auth="admin:$(rand_secret 24)"

# Redis (Задание 4): пароль requirepass
ensure_secret secret/redis \
  password="$(rand_secret 32)"

# MongoDB (Задание 5): root для чарта, пользователь приложения, basic auth mongo-express
ensure_secret secret/mongodb \
  root_password="$(rand_secret 32)" \
  username="healthchecks" \
  password="$(rand_secret 32)" \
  express_basic_auth_password="$(rand_secret 24)"

# MinIO (Задание 6): root для чарта и Console, S3-ключи приложения
ensure_secret secret/minio \
  root_user="minioadmin" \
  root_password="$(rand_secret 32)" \
  access_key="healthchecks" \
  secret_key="$(rand_secret 40)"

# Container registry для werf (Задание 9). Локально — registry-аддон minikube
# без авторизации (username/password пустые); для GHCR/Harbor положить сюда
# реальные логин и токен: vault kv put secret/registry url=ghcr.io/<user>/<repo> username=... password=...
ensure_secret secret/registry \
  url="127.0.0.1:5000/healthchecks" \
  username="" \
  password=""

# --- 5. policies -----------------------------------------------------------
POLICIES=""
for f in "$POLICY_DIR"/*.hcl; do
  name="$(basename "$f" .hcl)"
  echo "==> policy write $name"
  vault_root policy write "$name" - <"$f" >/dev/null
  POLICIES="${POLICIES:+$POLICIES,}$name"
done

# --- 6. AppRole ------------------------------------------------------------
if ! vault_root auth list -format=json | grep -q '"approle/"'; then
  echo "==> auth enable approle"
  vault_root auth enable approle >/dev/null
fi
echo "==> approle role healthchecks (policies: $POLICIES)"
vault_root write auth/approle/role/healthchecks \
  token_policies="$POLICIES" \
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
