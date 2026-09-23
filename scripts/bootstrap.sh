#!/usr/bin/env bash
# Подъём всего стенда с нуля одной командой.
#
#   bash scripts/bootstrap.sh              # на существующем кластере (идемпотентно)
#   bash scripts/bootstrap.sh --recreate   # minikube delete + start начисто
#   bash scripts/bootstrap.sh --no-arc     # без self-hosted runner'а (Задание 8, Часть 2)
#
# Порядок продиктован зависимостями, а не удобством:
#   cert-manager -> Vault (секреты) -> RabbitMQ/Redis/MongoDB/MinIO (их Secret'ы
#   читает чарт приложения) -> VPA (CRD для объекта VPA в чарте) -> приложение
#   (оно же создаёт ClusterIssuer'ы, по которым выпускаются все остальные
#   сертификаты) -> locust-operator -> тестовые данные -> ARC.
#
# Требуется: docker (запущенный), minikube, kubectl, helm + плагин secrets,
# vault, vals, python, openssl, curl; для ARC — авторизованный gh или GITHUB_PAT.
#
# Права администратора НЕ нужны: вместо `minikube tunnel` скрипт поднимает
# kubectl port-forward к Vault и передаёт адрес через VAULT_ADDR_OVERRIDE
# (scripts/lib.sh). Для доступа к UI из браузера туннель и hosts всё же нужны —
# команды печатаются в конце.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RECREATE=0
WITH_ARC=1
for arg in "$@"; do
  case "$arg" in
    --recreate) RECREATE=1 ;;
    --no-arc)   WITH_ARC=0 ;;
    -h|--help)  sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "!! неизвестный аргумент: $arg" >&2; exit 1 ;;
  esac
done

MINIKUBE_CPUS="${MINIKUBE_CPUS:-6}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-12288}"
MINIKUBE_DISK="${MINIKUBE_DISK:-40g}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.19.2}"
VAULT_PF_PORT="${VAULT_PF_PORT:-8200}"

step() { echo; echo "############ $* ############"; }

# --- 0. проверки ------------------------------------------------------------
step "0. проверка инструментов"
for t in docker minikube kubectl helm vault vals python openssl curl; do
  command -v "$t" >/dev/null || { echo "!! не найден $t" >&2; exit 1; }
done
docker version >/dev/null 2>&1 || {
  echo "!! docker-демон не отвечает — запустите Docker Desktop и повторите" >&2; exit 1; }
helm plugin list 2>/dev/null | grep -q '^secrets' || {
  echo "!! нет плагина helm-secrets (см. deploy/vault/README.md)" >&2; exit 1; }
echo "ок"

# --- 1. кластер -------------------------------------------------------------
step "1. кластер minikube"
if [ "$RECREATE" = "1" ]; then
  minikube delete || true
fi
if minikube status >/dev/null 2>&1; then
  echo "кластер уже запущен"
else
  minikube start --driver=docker --container-runtime=containerd \
    --cpus="$MINIKUBE_CPUS" --memory="$MINIKUBE_MEMORY" --disk-size="$MINIKUBE_DISK"
fi

# registry — для werf (Задание 9), ingress-dns и dashboard — для удобства
for addon in ingress ingress-dns metrics-server registry dashboard; do
  echo "==> addon $addon"
  minikube addons enable "$addon" >/dev/null
done

# --- 2. cert-manager --------------------------------------------------------
step "2. cert-manager $CERT_MANAGER_VERSION"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VERSION/cert-manager.yaml" >/dev/null
for d in cert-manager-webhook cert-manager cert-manager-cainjector; do
  kubectl -n cert-manager rollout status "deploy/$d" --timeout=300s
done

# --- 3. Vault ---------------------------------------------------------------
step "3. Vault"
helm repo add hashicorp https://helm.releases.hashicorp.com >/dev/null 2>&1 || true
helm upgrade --install vault hashicorp/vault -n vault --create-namespace \
  -f deploy/vault/values.yaml >/dev/null
echo "==> ждём контейнер vault-0"
kubectl -n vault wait --for=condition=PodReadyToStartContainers pod/vault-0 --timeout=300s >/dev/null
until kubectl -n vault get pod vault-0 \
    -o jsonpath='{.status.containerStatuses[0].state.running.startedAt}' 2>/dev/null | grep -q .; do
  sleep 3
done

# Ключи от прежнего (уничтоженного) Vault мешают: setup.sh не станет
# переинициализировать чужой keys-файл. Уводим их в *.old, они в .gitignore.
if [ -f deploy/vault/.vault-keys.json ] && \
   ! kubectl -n vault exec vault-0 -- vault status -format=json 2>/dev/null | grep -q '"initialized": *true'; then
  echo "==> Vault чистый, а ключи от старого есть -> deploy/vault/.vault-keys.json.old"
  mv deploy/vault/.vault-keys.json "deploy/vault/.vault-keys.json.old"
  [ -f .env ] && mv .env ".env.old"
fi

bash deploy/vault/setup.sh

# port-forward живёт до конца скрипта: через него ходят vals и vault CLI
echo "==> port-forward vault 127.0.0.1:$VAULT_PF_PORT"
kubectl -n vault port-forward "svc/vault" "$VAULT_PF_PORT:8200" >/dev/null 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT
export VAULT_ADDR_OVERRIDE="http://127.0.0.1:$VAULT_PF_PORT"
until curl -s "$VAULT_ADDR_OVERRIDE/v1/sys/health" 2>/dev/null | grep -q '"sealed"'; do sleep 2; done
echo "Vault доступен"

# --- 4. образ приложения ----------------------------------------------------
step "4. образ healthchecks:local"
# docker-env на Windows с containerd не работает — только minikube image build
minikube image build -t healthchecks:local -f docker/Dockerfile . 2>&1 | tail -3

# --- 5. репозитории чартов --------------------------------------------------
step "5. helm-репозитории"
# последовательно: параллельный `helm repo add` гоняется за repositories.yaml
helm repo add minio https://charts.min.io/ >/dev/null 2>&1 || true
helm repo add heywood8 https://heywood8.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add cowboysysop https://cowboysysop.github.io/charts/ >/dev/null 2>&1 || true
helm repo add fairwinds-stable https://charts.fairwinds.com/stable >/dev/null 2>&1 || true
helm repo add locust-k8s-operator https://abdelrhmanhamouda.github.io/locust-k8s-operator/ >/dev/null 2>&1 || true
helm repo update >/dev/null

# --- 6. компоненты ----------------------------------------------------------
# Их Secret'ы (rabbitmq, redis, mongodb-custom-user-0-secret) монтирует чарт
# приложения — без них поды не стартуют
step "6. RabbitMQ, Redis, MongoDB, MinIO"
bash scripts/deploy-rabbitmq.sh
bash scripts/deploy-redis.sh
bash scripts/deploy-mongodb.sh
bash scripts/deploy-minio.sh

step "7. VPA (recommender) и locust-operator"
# VPA — до приложения: чарт создаёт объект VerticalPodAutoscaler, нужен CRD
helm upgrade --install vpa fairwinds-stable/vpa -n vpa --create-namespace \
  -f deploy/vpa/values.yaml --wait --timeout 10m >/dev/null
helm upgrade --install locust-operator locust-k8s-operator/locust-k8s-operator \
  -n locust-operator --create-namespace --wait --timeout 10m >/dev/null
echo "ок"

# --- 8. приложение ----------------------------------------------------------
step "8. чарт приложения"
bash scripts/deploy.sh

# Job миграций — post-install хук, то есть стартует уже после worker'а:
# на чистой БД тот успевает упасть с "relation ... does not exist". Таблицы
# теперь на месте — перекатываем, чтобы не ждать backoff.
echo "==> перезапуск worker после миграций"
kubectl -n healthchecks rollout restart deploy/healthchecks-worker >/dev/null
kubectl -n healthchecks rollout status deploy/healthchecks-worker --timeout=300s

# --- 9. тестовые данные -----------------------------------------------------
step "9. тестовые данные (проект e2e)"
bash scripts/seed-e2e.sh

# --- 10. ARC ----------------------------------------------------------------
if [ "$WITH_ARC" = "1" ]; then
  step "10. Actions Runner Controller"
  if [ -n "${GITHUB_PAT:-}" ] || gh auth status >/dev/null 2>&1; then
    # AppRole пересоздан -> в Secrets репозитория лежат чужие значения
    set -a; . ./.env; set +a
    gh secret set VAULT_ROLE_ID   --body "$VAULT_ROLE_ID"   >/dev/null
    gh secret set VAULT_SECRET_ID --body "$VAULT_SECRET_ID" >/dev/null
    echo "==> VAULT_ROLE_ID / VAULT_SECRET_ID в Secrets репозитория обновлены"
    bash scripts/deploy-arc.sh
  else
    echo "!! gh не авторизован и нет GITHUB_PAT — ARC пропущен"
    echo "   запустите позже: bash scripts/deploy-arc.sh"
  fi
fi

# --- итог -------------------------------------------------------------------
step "готово"
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded 2>/dev/null \
  | grep -v "^NAMESPACE" && echo "^^ поды не в Running (обычно догоняют сами)" || echo "все поды Running/Completed"
echo
helm list -A
echo
cat <<'EOF'
Дальше — то, что требует прав администратора на Windows:

1. В отдельном терминале «от имени администратора»:
     minikube tunnel

2. В C:\Windows\System32\drivers\etc\hosts (блокнот от администратора):
     127.0.0.1 healthchecks.local
     127.0.0.1 flower.local
     127.0.0.1 vault.local
     127.0.0.1 rabbitmq.local
     127.0.0.1 redisinsight.local
     127.0.0.1 mongo-express.local
     127.0.0.1 minio.local
     127.0.0.1 locust.local

Затем открыть https://healthchecks.local (сертификат от локального CA
healthchecks-local-ca — браузер предупредит, это ожидаемо).
EOF
