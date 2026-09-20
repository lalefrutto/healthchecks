# hc.mq — Producer / Consumer на прямом AMQP-клиенте

Задание 3, Часть 2. Без Celery: только `pika` и стандартная библиотека,
Django не импортируется — скрипты запускаются как снаружи кластера (через
LoadBalancer-сервис RabbitMQ и `minikube tunnel`), так и внутри.

| Файл | Что делает |
|---|---|
| [tasks.py](tasks.py) | «Работа»: два публичных API из [public-apis](https://github.com/public-apis/public-apis) без ключей — `cat_fact` (catfact.ninja) и `weather` (open-meteo.com) |
| [common.py](common.py) | подключение по `RABBITMQ_URL`, имя/тип exchange |
| [producer.py](producer.py) | объявляет **durable direct exchange** `healthchecks.tasks`, публикует **persistent** JSON-сообщения с publisher confirms |
| [consumer.py](consumer.py) | имя очереди из CLI → **durable queue** → bind к exchange по routing key → callback с ручным **ack**; результат API-вызова пишется в JSON-файл |

## Запуск

```sh
source scripts/rabbitmq-env.sh          # RABBITMQ_URL из Vault (логин/пароль secret/rabbitmq)

# терминал 1 — consumer (очередь api-results, ключ привязки api-tasks)
python -m hc.mq.consumer api-results

# терминал 2 — producer
python -m hc.mq.producer cat_fact --count 2
python -m hc.mq.producer weather --latitude 55.79 --longitude 49.11
```

Результаты — `results/<очередь>/<время>-<задача>-<id>.json` (каталог в `.gitignore`):

```json
{
  "message": {"id": "…", "task": "weather", "args": {"latitude": 55.79, "longitude": 49.11}, "created_at": "…"},
  "queue": "api-results",
  "processed_at": "…",
  "status": "ok",
  "result": {"latitude": 55.8125, "longitude": 49.125, "time": "…", "temperature_c": 14.2, "windspeed_kmh": 2.5, "weathercode": 2},
  "error": null
}
```

## Гарантии доставки

- exchange и очередь `durable`, сообщения `delivery_mode=persistent` — переживают рестарт брокера;
- producer включает `confirm_delivery()` — брокер подтверждает приём;
- consumer: `prefetch_count=1`, `basic_ack` только после записи файла; ошибка задачи →
  файл со `status: error` и `basic_nack(requeue=False)`, чтобы битое сообщение не зациклилось;
- direct exchange отбрасывает сообщения, для которых нет привязанной очереди —
  consumer должен быть запущен (объявить очередь) до первого сообщения.

Проверить состояние через Management API (`https://rabbitmq.local`):
`/api/exchanges/%2F/healthchecks.tasks`, `/api/queues/%2F/api-results`.

## Celery (Части 3–4)

Те же задачи обёрнуты в Celery ([celery_tasks.py](celery_tasks.py)): `hc.mq.cat_fact`,
`hc.mq.weather`. Конфигурация — [hc/celeryconfig.py](../celeryconfig.py)
(брокер RabbitMQ из `CELERY_BROKER_URL`, результаты в Postgres через
`django-celery-results`, очередь `api-tasks`, `acks_late`). Воркер и Flower
разворачиваются subchart'ами чарта healthchecks.

### API-роуты ([views.py](views.py), [urls.py](urls.py))

Авторизация — как у остального API healthchecks: заголовок `X-Api-Key`
(ключ проекта из Settings → API access).

```sh
# поставить задачу (rw-ключ), аргументы — JSON в теле
curl -k -X POST https://healthchecks.local/api/v3/tasks/weather/ \
  -H "X-Api-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"latitude": 55.79, "longitude": 49.11}'
# -> 202 {"task_id": "…", "task": "hc.mq.weather", "state": "PENDING"}

curl -k -X POST https://healthchecks.local/api/v3/tasks/cat_fact/ -H "X-Api-Key: $API_KEY"

# состояние / результат по AsyncResult (rw- или ro-ключ)
curl -k https://healthchecks.local/api/v3/tasks/result/<task_id>/ -H "X-Api-Key: $API_KEY"
# -> {"task_id": "…", "state": "SUCCESS", "ready": true, "result": {"temperature_c": 14.2, …}}
# -> {"task_id": "…", "state": "FAILURE", "ready": true, "error": "…"} при ошибке
```

Тесты: `./manage.py test hc.mq` (в кластере —
`kubectl -n healthchecks exec deploy/healthchecks-web -- ./manage.py test hc.mq`).
