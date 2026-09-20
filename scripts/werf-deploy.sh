#!/usr/bin/env bash
# Деплой werf-проекта (Задание 9, Часть 2): сборка образа + публикация в
# registry + выкат чарта .helm одной командой `werf converge`.
#
#   scripts/werf-deploy.sh [доп. аргументы werf converge]
#
# Секреты: ссылки ref+vault:// из .helm/secrets.yaml разворачивает vals во
# временный values-файл (werf не умеет helm-secrets), учётка registry — из
# Vault (scripts/werf-registry-login.sh).
#
# На Windows werf запускается в контейнере registry.werf.io/werf/werf
# (нативный werf.exe требует привилегии на symlink), с docker-сокетом хоста и в
# сети minikube — так registry-аддон доступен как 192.168.49.2:5000.
# На Linux/macOS с нативным werf: WERF_NATIVE=1 scripts/werf-deploy.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NAMESPACE="${NAMESPACE:-healthchecks}"
RELEASE="${RELEASE:-healthchecks}"
WERF_IMAGE="${WERF_IMAGE:-registry.werf.io/werf/werf:2-stable}"

cd "$ROOT_DIR"
git diff --quiet HEAD -- werf.yaml .helm docker || {
  echo "!! werf собирает только закоммиченные файлы (giterminism): закоммитьте изменения в werf.yaml/.helm/docker" >&2
  exit 1
}

# --- секреты из Vault -> временный values ------------------------------------
vault_login
SECRETS_TMP="$(mktemp "$ROOT_DIR/.helm/.secrets.XXXXXX.yaml")"
trap 'rm -f "$SECRETS_TMP"' EXIT
vals eval -f .helm/secrets.yaml > "$SECRETS_TMP"

# --- registry (docker-токен из Vault) -----------------------------------------
if [ "${WERF_NATIVE:-0}" = "1" ]; then
  source "$ROOT_DIR/scripts/werf-registry-login.sh"
  werf converge --repo "$WERF_REPO" --insecure-registry \
    --namespace "$NAMESPACE" --release "$RELEASE" \
    --values ".helm/$(basename "$SECRETS_TMP")" "$@"
  exit 0
fi

# Контейнерный werf: логинимся его же бинарём внутри контейнера, docker
# config пробрасываем, чтобы токен из Vault попал в werf
DOCKER_CFG="$(mktemp -d)"
trap 'rm -rf "$SECRETS_TMP" "$DOCKER_CFG"' EXIT
WERF_BIN="docker run --rm --network minikube --user 0:0 --entrypoint werf \
  -v $DOCKER_CFG:/root/.docker $WERF_IMAGE" \
  source "$ROOT_DIR/scripts/werf-registry-login.sh"

# kubeconfig minikube указывает на 127.0.0.1:<порт docker>; из контейнера в сети
# minikube API-сервер доступен по IP узла
KUBECONFIG_B64="$(kubectl config view --flatten --minify   | sed -E 's|server: https://127\.0\.0\.1:[0-9]+|server: https://192.168.49.2:8443|' | base64 -w0)"

echo "==> werf converge ($WERF_REPO -> $NAMESPACE/$RELEASE)"
MSYS_NO_PATHCONV=1 docker run --rm --network minikube --user 0:0 --entrypoint werf \
  -e WERF_BUILDAH_MODE=docker \
  -e WERF_PLATFORM=linux/amd64 \
  -e WERF_INSECURE_REGISTRY=1 \
  -e WERF_REPO="$WERF_REPO" \
  -e WERF_NAMESPACE="$NAMESPACE" \
  -e WERF_RELEASE="$RELEASE" \
  -e WERF_KUBE_CONFIG_BASE64="$KUBECONFIG_B64" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$DOCKER_CFG:/root/.docker" \
  -v "$(pwd -W 2>/dev/null || pwd):/app" -w /app \
  "$WERF_IMAGE" converge --values ".helm/$(basename "$SECRETS_TMP")" "$@"
