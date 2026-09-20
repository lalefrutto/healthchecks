# RabbitMQ

Брокер сообщений для Задания 3 (Producer/Consumer, Celery). Ставится чартом
**cloudpirates/rabbitmq** (bitnami-образы с 2025 года отдают 403 без подписки,
Cloud Pirates — тот же подход на официальном образе `rabbitmq:*-management`).

## Секреты

Логин, пароль и erlang cookie лежат в Vault в `secret/rabbitmq`
(генерирует `deploy/vault/setup.sh`), читаются policy `rabbitmq-read`
([deploy/vault/policies/rabbitmq-read.hcl](../vault/policies/rabbitmq-read.hcl)).
AppRole `healthchecks` теперь выдаёт токен сразу с двумя policy —
`healthchecks-read,rabbitmq-read`. В [secrets.yaml](secrets.yaml) — только
`ref+vault://` ссылки, значения подставляет helm-secrets/vals при деплое.

## Деплой

```sh
bash scripts/deploy-rabbitmq.sh          # релиз rabbitmq в namespace healthchecks
```

[values.yaml](values.yaml):

- `service.type: LoadBalancer` — снаружи кластера AMQP доступен на
  `127.0.0.1:5672` при запущенном `minikube tunnel` (в облаке — внешний IP провайдера);
- Ingress `https://rabbitmq.local` на Management UI, TLS от cert-manager
  (строка `127.0.0.1 rabbitmq.local` в hosts);
- внутри кластера: `amqp://<user>:<pass>@rabbitmq.healthchecks.svc.cluster.local:5672/`.

Проверка:

```sh
kubectl -n healthchecks get pods,svc,ingress -l app.kubernetes.io/instance=rabbitmq
curl -k -u "$USER:$PASS" https://rabbitmq.local/api/overview
```

## RabbitMQ 4.x и Celery

RabbitMQ 4 по умолчанию запрещает transient non-exclusive очереди
(`transient_nonexcl_queues`), а Celery (pidbox для remote control) и Flower
(очередь событий `celeryev.*`) объявляют именно такие — воркер и Flower падали
с `Queue.declare: (541) INTERNAL_ERROR`. В [values.yaml](values.yaml) это
разрешено через `config.extraConfiguration`:

```
deprecated_features.permit.transient_nonexcl_queues = true
```
