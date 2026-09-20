# healthchecks — Helm-чарт

Оборачивает манифесты из `k8s/` (Задание 1) в чарт с настраиваемыми `values.yaml`.
PostgreSQL вынесен в локальный subchart `charts/postgresql`.

## Структура

```
charts/healthchecks/
├── Chart.yaml                  # метаданные, зависимость от subchart postgresql
├── values.yaml                 # все настраиваемые параметры
├── templates/
│   ├── _helpers.tpl            # имена, labels, общие блоки env / init-контейнера
│   ├── configmap.yaml          # настройки приложения (SITE_ROOT, DB_*, EMAIL_*)
│   ├── secret.yaml             # SECRET_KEY (TODO: Vault, Задание 2 Часть 2)
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
└── charts/postgresql/          # subchart: Secret, headless Service, PV/PVC, StatefulSet
```

## Установка

Предварительно (один раз): minikube с аддоном `ingress`, установленный
cert-manager и собранный образ — см. [k8s/README.md](../../k8s/README.md).

```sh
helm lint charts/healthchecks
helm install healthchecks charts/healthchecks -n healthchecks --create-namespace --dry-run
helm install healthchecks charts/healthchecks -n healthchecks --create-namespace --wait
```

Обновление (после пересборки образа или правки values) — миграции прогонит
хук автоматически:

```sh
helm upgrade healthchecks charts/healthchecks -n healthchecks --wait
```

Удаление (PV/PVC с данными Postgres помечены `helm.sh/resource-policy: keep`
и остаются):

```sh
helm uninstall healthchecks -n healthchecks
```

## Основные параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `image.repository`, `image.tag` | `healthchecks`, `local` | образ приложения |
| `config.siteRoot` | `https://healthchecks.local` | внешний URL, должен совпадать с `ingress.host` |
| `config.allowedHosts` | `healthchecks.local,localhost,127.0.0.1` | `ALLOWED_HOSTS` |
| `secrets.secretKey` / `secrets.existingSecret` | placeholder / `""` | Django `SECRET_KEY` |
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
| `postgresql.enabled` | `true` | развернуть subchart Postgres |
| `postgresql.auth.*` | `healthchecks` / placeholder | БД, пользователь, пароль |
| `postgresql.persistence.hostPath.path` | `/data/healthchecks-postgres` | hostPath для minikube |
| `externalDatabase.*` | — | внешняя БД при `postgresql.enabled=false` |

Пример для облака: `--set postgresql.persistence.hostPath.enabled=false --set postgresql.persistence.storageClass=""`
(динамический provisioning по default StorageClass) и `--set ingress.tls.clusterIssuer=letsencrypt-prod --set certManager.createIssuers=false`.
