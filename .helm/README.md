# healthchecks — Helm-чарт (`.helm/` werf-проекта)

Оборачивает манифесты из `k8s/` (Задание 1) в чарт с настраиваемыми `values.yaml`.
PostgreSQL, Celery-воркер и Flower вынесены в локальные subchart'ы (`charts/*`).
С Задания 9 чарт лежит в `.helm/` — стандартном каталоге werf-проекта
([werf.yaml](../werf.yaml)); для обычного `helm`/CI это тот же чарт по пути `.helm`.

## Структура

```
.helm/
├── Chart.yaml                  # метаданные, зависимость от subchart postgresql
├── values.yaml                 # все настраиваемые параметры (без секретов)
├── secrets.yaml                # ссылки ref+vault:// на секреты, разворачивает helm-secrets
├── templates/
│   ├── _helpers.tpl            # имена, labels, общие блоки env / init-контейнера
│   ├── configmap.yaml          # настройки приложения (SITE_ROOT, DB_*, EMAIL_*)
│   ├── secret.yaml             # SECRET_KEY (значение приходит из Vault)
│   ├── uwsgi-configmap.yaml    # uwsgi.ini для k8s
│   ├── deployment-web.yaml     # веб-приложение + init wait-for-db
│   ├── deployment-worker.yaml  # sendalerts / sendreports
│   ├── job-migrate.yaml        # manage.py migrate — helm-хук post-install/post-upgrade
│   ├── cronjob-prune.yaml      # prunetokenbucket / prunepingsslow
│   ├── service.yaml            # ClusterIP для веб-подов
│   ├── service-smtp.yaml       # ExternalName на внешний SMTP
│   ├── ingress.yaml            # Ingress + TLS от cert-manager
│   ├── cert-manager-issuers.yaml # self-signed CA + ClusterIssuer'ы (локальная разработка)
│   └── NOTES.txt
├── charts/postgresql/          # subchart: Secret, headless Service, PV/PVC, StatefulSet
├── charts/celery-worker/       # subchart: Deployment `celery -A hc worker -Q api-tasks`
└── charts/flower/              # subchart: Flower UI (Deployment + Service + Ingress flower.local, basic auth из Vault)
```

## Окружение из нескольких секретов

Все контейнеры приложения (web, worker, migrate, prune, celery-worker, flower)
получают одинаковое окружение (`_helpers.tpl`, `healthchecks.env`): несекретные
параметры — из ConfigMap, а секреты — **из нескольких Secret'ов**, у каждого
компонента свой:

| Переменная | Источник |
|---|---|
| `SECRET_KEY` | Secret `healthchecks` (значение из Vault `secret/healthchecks`) |
| `DB_PASSWORD` | Secret `healthchecks-postgresql` (subchart postgresql, Vault `secret/healthchecks#DB_PASSWORD`) |
| `RABBITMQ_PASSWORD` | Secret `rabbitmq` (релиз чарта RabbitMQ, Vault `secret/rabbitmq`) |
| `RABBITMQ_HOST/PORT/USER/VHOST`, `CELERY_*` | ConfigMap |
| `CELERY_BROKER_URL` | собирается в манифесте как `amqp://$(RABBITMQ_USER):$(RABBITMQ_PASSWORD)@…` — Kubernetes подставляет ранее объявленные переменные, пароль нигде не дублируется |
| `FLOWER_BASIC_AUTH` | Secret `healthchecks-flower` (Vault `secret/flower`) |
| `REDIS_HOST/PORT/DB` | ConfigMap |
| `REDIS_PASSWORD`, `REDIS_URL` | Secret `redis` (релиз чарта Redis, Vault `secret/redis`); URL собирается через `$(VAR)` |
| `MONGODB_HOST/PORT/DB/USER` | ConfigMap |
| `MONGODB_PASSWORD`, `MONGODB_URL` | Secret `mongodb-custom-user-0-secret` (релиз чарта MongoDB, Vault `secret/mongodb`) |
| `S3_ENDPOINT/BUCKET/REGION/SECURE` | ConfigMap |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Secret `healthchecks-s3` (Vault `secret/minio`) |

Subchart'ы не видят helper'ы родителя, поэтому образ, параметры брокера и имена
ресурсов приложения передаются им через `global.*` в `values.yaml`.

Настройки Celery — в [hc/celeryconfig.py](../../hc/celeryconfig.py): всё читается
из этих же переменных окружения (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
`CELERY_TASK_DEFAULT_QUEUE`).

## Установка

Предварительно (один раз): minikube с аддоном `ingress`, установленный
cert-manager и собранный образ — см. [k8s/README.md](../../k8s/README.md);
Vault с секретами приложения — см. [deploy/vault/README.md](../../deploy/vault/README.md).

Штатный способ — `scripts/deploy.sh`: он подставляет секреты из Vault через
helm-secrets/vals и делает `helm upgrade --install`. Команды ниже — «ручной»
вариант, секреты тогда нужно передать самому (`--set secrets.secretKey=...
--set postgresql.auth.password=...`), иначе `required` в шаблонах остановит деплой.

```sh
helm lint .helm
helm install healthchecks .helm -n healthchecks --create-namespace --dry-run
helm install healthchecks .helm -n healthchecks --create-namespace --wait
```

Обновление (после пересборки образа или правки values) — миграции прогонит
хук автоматически:

```sh
helm upgrade healthchecks .helm -n healthchecks --wait
```

Удаление (PV/PVC с данными Postgres помечены `helm.sh/resource-policy: keep`
и остаются):

```sh
helm uninstall healthchecks -n healthchecks
```

## Основные параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `config.siteRoot` | `https://healthchecks.local` | внешний URL, должен совпадать с `ingress.host` |
| `config.allowedHosts` | `healthchecks.local,localhost,127.0.0.1` | `ALLOWED_HOSTS` |
| `secrets.secretKey` / `secrets.existingSecret` | `""` (из Vault через `secrets.yaml`) | Django `SECRET_KEY` |
| `extraEnv` | `[]` | доп. переменные окружения для всех контейнеров |
| `web.replicaCount`, `web.resources` | `1` | веб-поды |
| `worker.enabled` | `true` | Deployment с `sendalerts`/`sendreports` |
| `migrate.enabled` | `true` | Job миграций (helm-хук) |
| `prune.enabled`, `prune.schedule` | `true`, `*/10 * * * *` | CronJob чистки |
| `waitForDb.enabled` | `true` | init-контейнер `pg_isready` |
| `ingress.enabled`, `ingress.host` | `true`, `healthchecks.local` | Ingress |
| `ingress.tls.clusterIssuer` | `healthchecks-ca-issuer` | ClusterIssuer cert-manager'а |
| `certManager.createIssuers` | `true` | создать self-signed CA и issuer'ы |
| `email.host`, `email.externalName.*` | `smtp`, `smtp.gmail.com` | ExternalName-сервис для SMTP |
| `global.image.*` | `healthchecks:local` | образ приложения (для всех компонентов и subchart'ов) |
| `global.rabbitmq.*` | `rabbitmq:5672`, secret `rabbitmq` | параметры брокера |
| `global.celery.resultBackend`, `global.celery.queue` | `django-db`, `api-tasks` | backend результатов и очередь Celery |
| `global.redis.*` | `redis:6379/0`, secret `redis` | параметры кэша Redis |
| `global.mongodb.*` | `mongodb:27017/healthchecks` | параметры MongoDB |
| `global.s3.*` | `minio:9000`, bucket `healthchecks` | S3-хранилище тел пингов (MinIO) |
| `celery-worker.enabled`, `celery-worker.replicaCount`, `celery-worker.concurrency` | `true`, `1`, `2` | subchart Celery-воркера |
| `flower.enabled`, `flower.ingress.host`, `flower.basicAuth` | `true`, `flower.local`, из Vault | subchart Flower |
| `postgresql.enabled` | `true` | развернуть subchart Postgres |
| `postgresql.auth.*` | `healthchecks` / пароль из Vault | БД, пользователь, пароль |
| `postgresql.persistence.hostPath.path` | `/data/healthchecks-postgres` | hostPath для minikube |
| `externalDatabase.*` | — | внешняя БД при `postgresql.enabled=false` |

Пример для облака: `--set postgresql.persistence.hostPath.enabled=false --set postgresql.persistence.storageClass=""`
(динамический provisioning по default StorageClass) и `--set ingress.tls.clusterIssuer=letsencrypt-prod --set certManager.createIssuers=false`.
