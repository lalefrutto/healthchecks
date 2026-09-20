#!/usr/bin/env bash
# Запуск распределённого нагрузочного теста через locust-k8s-operator.
# API-ключ проекта берётся из БД приложения (в git/Vault не хранится).
#
#   scripts/deploy-locust-test.sh [аргументы helm, например --set test.users=300]
#   helm uninstall load-test -n healthchecks     # остановить/убрать
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-healthchecks}"
PROJECT="${HC_PROJECT:-e2e}"

API_KEY="${HC_API_KEY:-$(kubectl -n "$NAMESPACE" exec deploy/healthchecks-web -c healthchecks -- \
  ./manage.py shell -c "from hc.accounts.models import Project; print(Project.objects.get(name='$PROJECT').api_key)" 2>/dev/null | tail -1)}"
[ ${#API_KEY} -eq 32 ] || { echo "!! не удалось получить API-ключ проекта '$PROJECT'" >&2; exit 1; }

# Job'ы оператора неизменяемы — пересоздаём релиз целиком
helm uninstall load-test -n "$NAMESPACE" >/dev/null 2>&1 || true
helm upgrade --install load-test "$ROOT_DIR/charts/locust-test" -n "$NAMESPACE" \
  --set env.HC_API_KEY="$API_KEY" "$@"
