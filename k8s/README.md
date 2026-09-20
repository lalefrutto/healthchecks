# healthchecks на Kubernetes (minikube)

> Начиная с Задания 2 приложение разворачивается Helm-чартом
> [charts/healthchecks](../charts/healthchecks/README.md). Манифесты ниже —
> результат Задания 1, оставлены как справочник; в кластере их ресурсы заменены релизом чарта.

## Состав

| Файл | Ресурс | Назначение |
|---|---|---|
| `00-namespace.yaml` | Namespace | `healthchecks` |
| `01-configmap.yaml` | ConfigMap | несекретные настройки приложения и подключения к БД |
| `02-deployment.yaml` | Deployment | веб-приложение (uWSGI), init-контейнер `wait-for-db` |
| `03-service.yaml` | Service (ClusterIP) | вход на веб-поды, порт 80 → 8000 |
| `04-postgres-pv.yaml`, `05-postgres-pvc.yaml` | PV / PVC | hostPath-том для данных Postgres |
| `06-postgres-secret.yaml` | Secret | пароль БД и `SECRET_KEY` (placeholder, TODO → Vault в Задании 2) |
| `07-postgres-service.yaml` | Service (headless) | стабильное DNS-имя `healthchecks-db` |
| `08-postgres-statefulset.yaml` | StatefulSet | Postgres 16 |
| `09-uwsgi-configmap.yaml` | ConfigMap | `uwsgi.ini` для k8s (без миграций и фоновых демонов внутри веб-пода) |
| `10-migrate-job.yaml` | Job | `manage.py migrate` |
| `11-worker-deployment.yaml` | Deployment | фоновые процессы `sendalerts` и `sendreports --loop` |
| `12-prune-cronjob.yaml` | CronJob | `prunetokenbucket` + `prunepingsslow` каждые 10 минут |
| `13-cert-manager-issuers.yaml` | ClusterIssuer / Certificate | self-signed CA для локальных TLS-сертификатов |
| `14-ingress.yaml` | Ingress | `https://healthchecks.local` → `healthchecks-web`, TLS от cert-manager |
| `15-smtp-externalname.yaml` | Service (ExternalName) | алиас `smtp` → внешний SMTP-сервер |

## Первый запуск

```sh
minikube start --driver=docker
minikube addons enable ingress
minikube addons enable ingress-dns

# cert-manager (CRD + контроллеры)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.19.2/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager-webhook

# образ приложения — только так, docker-env на Windows/containerd не работает
minikube image build -t healthchecks:local -f docker/Dockerfile .

kubectl apply -f k8s/
kubectl -n healthchecks wait --for=condition=complete job/healthchecks-migrate
kubectl -n healthchecks get pods
```

Порядок внутри `kubectl apply -f k8s/` определяется префиксами файлов; init-контейнеры
`wait-for-db` не дают приложению, воркеру и Job упасть, пока Postgres ещё не поднялся.

## Доступ по https://healthchecks.local

DNS для локального кластера — один из вариантов:

1. **hosts-файл** (проще всего на Windows с docker-драйвером). В отдельном
   терминале держим `minikube tunnel` (пробрасывает 80/443 ingress-контроллера на
   127.0.0.1), в `C:\Windows\System32\drivers\etc\hosts` добавляем:
   ```
   127.0.0.1 healthchecks.local
   ```
2. **ingress-dns** — аддон включён; на Linux/macOS достаточно указать
   `minikube ip` как DNS-сервер для зоны `.local` (см. документацию minikube).
   На Windows с docker-драйвером IP minikube недоступен с хоста напрямую,
   поэтому используется вариант 1.
3. В облаке — обычная A-запись на адрес LoadBalancer'а ingress-контроллера.

Сертификат выпускается локальным CA `healthchecks-local-ca`. Чтобы браузер не
предупреждал, экспортируйте CA и добавьте в доверенные корневые:

```sh
kubectl -n cert-manager get secret healthchecks-ca-secret -o jsonpath='{.data.ca\.crt}' | base64 -d > healthchecks-ca.crt
```

Быстрая проверка без DNS и туннеля:

```sh
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8443:443
curl -k --resolve healthchecks.local:8443:127.0.0.1 https://healthchecks.local:8443/
```

## Повседневные операции

```sh
# новая версия кода
minikube image build -t healthchecks:local -f docker/Dockerfile .
kubectl replace --force -f k8s/10-migrate-job.yaml      # Job неизменяем — пересоздаём
kubectl -n healthchecks rollout restart deploy/healthchecks-web deploy/healthchecks-worker

# запустить чистку вне расписания
kubectl -n healthchecks create job --from=cronjob/healthchecks-prune prune-manual

# суперпользователь
kubectl -n healthchecks exec -it deploy/healthchecks-web -- ./manage.py createsuperuser
```
