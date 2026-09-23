#!/usr/bin/env bash
# Тестовые данные для e2e-проверок, Locust и демонстрации (Задание 7).
#
#   scripts/seed-e2e.sh
#
# Создаёт (идемпотентно):
#   * суперпользователя $HC_EMAIL — вход в веб-UI;
#   * проект $HC_PROJECT с плоским API-ключом $HC_API_KEY (32 символа).
#     Ключи с префиксом hcw_/hcr_ хранятся в БД хэшем, а ключ без префикса
#     ProjectManager.for_api_key ищет как есть (legacy-ветка) — поэтому
#     значение из 32 "k" работает и его видно в БД;
#   * проверку "e2e" — готовый ping URL для ручной демонстрации.
#
# Ключ читает scripts/deploy-locust-test.sh (по имени проекта), а locustfile.py
# получает его в переменной HC_API_KEY и сам заводит себе проверку "locust".
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-healthchecks}"
PROJECT="${HC_PROJECT:-e2e}"
API_KEY="${HC_API_KEY:-$(printf 'k%.0s' $(seq 32))}"
EMAIL="${HC_EMAIL:-e2e@healthchecks.local}"
# Пароль задаётся только при создании пользователя; у существующего не трогаем
PASSWORD="${HC_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)}"

[ ${#API_KEY} -eq 32 ] || { echo "!! HC_API_KEY должен быть длиной 32, а не ${#API_KEY}" >&2; exit 1; }

echo "==> тестовые данные в $NAMESPACE (проект '$PROJECT', пользователь $EMAIL)"

kubectl -n "$NAMESPACE" exec -i deploy/healthchecks-web -c healthchecks -- \
  ./manage.py shell <<PYTHON
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import User

from hc.accounts.models import Profile, Project
from hc.api.models import Check

email, password = "$EMAIL", "$PASSWORD"
project_name, api_key = "$PROJECT", "$API_KEY"

user = User.objects.filter(email=email).first()
if user is None:
    user = User(username=str(uuid4())[:30], email=email)
    user.set_password(password)
    user.is_staff = user.is_superuser = True
    user.save()
    print("user: создан", email, "пароль:", password)
else:
    print("user: уже есть", email, "(пароль не менялся)")

# Profile с большими лимитами — иначе Locust упрётся в check_limit
Profile.objects.for_user(user)

project = Project.objects.filter(name=project_name).first()
if project is None:
    project = Project(owner=user, name=project_name)
    project.badge_key = user.username
    project.save()
    print("project: создан", project_name)
else:
    print("project: уже есть", project_name)

if project.api_key != api_key:
    project.api_key = api_key
    project.save()
    print("api_key: записан (32 символа)")
else:
    print("api_key: уже верный")

check, created = Check.objects.get_or_create(
    project=project,
    name="e2e",
    defaults={"slug": "e2e", "timeout": timedelta(hours=1)},
)
print("check:", "создана" if created else "уже есть", "ping_url:", check.url())
PYTHON

echo
echo "Готово. API-ключ проекта '$PROJECT' — 32 символа 'k'."
echo "Нагрузочный тест: scripts/deploy-locust-test.sh"
