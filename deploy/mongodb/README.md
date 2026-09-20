# MongoDB и mongo-express

Задание 5. В методичке подпункты не расписаны, поэтому сделан разумный минимум
по аналогии с RabbitMQ/Redis: секреты в Vault → чарт → UI → параметры в подах
приложения → использование в коде (Часть 2: журнал событий задач отдельно от
Postgres). Если от преподавателя придут уточнения — доработать.

## Секреты

Vault `secret/mongodb`: `root_password` (для чарта и mongo-express),
`username`/`password` (пользователь приложения), `express_basic_auth_password`
(вход в UI). Policy `mongodb-read`; AppRole `healthchecks` — уже 5 policy.
В [secrets.yaml](secrets.yaml) и [mongo-express-secrets.yaml](mongo-express-secrets.yaml) — только `ref+vault://`.

## MongoDB — чарт `cloudpirates/mongodb`

Bitnami-образы отдают 403, Cloud Pirates ставит официальный `mongo:8`.
[values.yaml](values.yaml): StatefulSet + PVC 1Gi + headless Service, root `admin`,
`customUsers` — пользователь `healthchecks` с ролью `readWrite` только на БД
`healthchecks`; `service.type: LoadBalancer` (снаружи `127.0.0.1:27017` через `minikube tunnel`).

## mongo-express — чарт `cowboysysop/mongo-express`

[mongo-express-values.yaml](mongo-express-values.yaml): Ingress `https://mongo-express.local`
с TLS от cert-manager, вход по basic auth (`admin` / пароль из Vault),
подключение к MongoDB под root, чтобы видеть все БД.

## Деплой

```sh
bash scripts/deploy-mongodb.sh   # релизы mongodb и mongo-express
bash scripts/deploy.sh           # приложение: подхватывает MONGODB_* (см. ниже)
```

Строка в hosts: `127.0.0.1 mongo-express.local`.

## Параметры в подах приложения

Чарт healthchecks (`global.mongodb.*`) прокидывает во все контейнеры приложения:

| Переменная | Источник |
|---|---|
| `MONGODB_HOST`, `MONGODB_PORT`, `MONGODB_DB`, `MONGODB_USER` | ConfigMap |
| `MONGODB_PASSWORD` | Secret `mongodb-custom-user-0-secret` (создаёт чарт MongoDB из values, ключ `CUSTOM_PASSWORD`) |
| `MONGODB_URL` | `mongodb://$(MONGODB_USER):$(MONGODB_PASSWORD)@$(MONGODB_HOST):$(MONGODB_PORT)/$(MONGODB_DB)?authSource=$(MONGODB_DB)` |

## Часть 2 — журнал событий задач в MongoDB

[hc/lib/mongo.py](../../hc/lib/mongo.py) — `EventLog` поверх `pymongo`, коллекция
`task_events` в БД `healthchecks`:

- `record(event, task_id, **fields)` — документ `{event, task_id, ts, ...}`;
  структура свободная (аргументы, результат, текст ошибки) — то, что неудобно
  раскладывать по реляционной схеме Postgres;
- `recent(limit, task_id=None)` — последние события, новые первыми;
- индексы создаются при первой записи: `ts`, `(task_id, ts)` и **TTL-индекс**
  (`MONGODB_EVENTS_RETENTION_DAYS`, по умолчанию 30 дней — MongoDB чистит старое сама);
- MongoDB недоступна → событие теряется с предупреждением, приложение работает.

Кто пишет:

| Событие | Откуда | Поля |
|---|---|---|
| `enqueued` | `POST /api/v3/tasks/<name>/` ([hc/mq/views.py](../../hc/mq/views.py)) | `task`, `kwargs`, `project` |
| `started` | сигнал Celery `task_prerun` ([hc/mq/celery_tasks.py](../../hc/mq/celery_tasks.py)) | `task`, `kwargs` |
| `succeeded` | `task_postrun` | `task`, `runtime_ms`, `result` |
| `failed` | `task_failure` | `task`, `error` |

Кто читает: `GET /api/v3/tasks/history/?task_id=<id>&limit=<n>` (X-Api-Key) —
и mongo-express (`healthchecks` → `task_events`).

```sh
curl -k "https://healthchecks.local/api/v3/tasks/history/?limit=5" -H "X-Api-Key: $API_KEY"
```

Тесты: `./manage.py test hc.lib.tests.test_mongo hc.mq`.
