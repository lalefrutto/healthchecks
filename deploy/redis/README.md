# Redis и RedisInsight

Задание 4, Часть 1. Кэш для приложения (Часть 2 — `CacheManager`).

## Секреты

Пароль Redis — в Vault `secret/redis` (генерирует `deploy/vault/setup.sh`),
policy `redis-read` ([deploy/vault/policies/redis-read.hcl](../vault/policies/redis-read.hcl)).
AppRole `healthchecks` выдаёт токен уже с четырьмя policy:
`flower-read,healthchecks-read,rabbitmq-read,redis-read`. В [secrets.yaml](secrets.yaml) —
только `ref+vault://` ссылка.

## Redis — собственный чарт [charts/redis](../../charts/redis)

Bitnami-образы отдают 403, поэтому по методичке — свой чарт на образе
`redis/redis-stack-server` (Redis 7.4 + модули RedisJSON/RediSearch/…):

- **StatefulSet** (1 реплика) с `volumeClaimTemplates` → PVC `data-redis-0`
  на default StorageClass, `--appendonly yes`;
- **headless Service** `redis-headless` — стабильное DNS-имя пода;
- **LoadBalancer Service** `redis` — внутри кластера `redis:6379`, снаружи
  `127.0.0.1:6379` при `minikube tunnel`;
- `--requirepass` из Secret'а (через переменную окружения, не в args пода),
  `maxmemory 128mb` + `allkeys-lru` — как кэшу и положено.

## RedisInsight — чарт `heywood8/redisinsight`

[redisinsight-values.yaml](redisinsight-values.yaml): Ingress `https://redisinsight.local`
с TLS от cert-manager, PVC 256Mi под настройки/подключения, `RITRUSTEDORIGINS`.
Подключение к Redis добавляется в UI: host `redis`, port `6379`, пароль —
из Vault (`vault kv get -field=password secret/redis`).

## Деплой

```sh
bash scripts/deploy-redis.sh     # релизы redis (с паролем из Vault) и redisinsight
bash scripts/deploy.sh           # приложение: подхватывает REDIS_* (см. ниже)
```

Строки в hosts: `127.0.0.1 redisinsight.local`.

## Параметры в подах приложения

Чарт healthchecks (`global.redis.*`) прокидывает во все контейнеры приложения
(web, worker, migrate, prune, celery-worker, flower):

| Переменная | Источник |
|---|---|
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | ConfigMap |
| `REDIS_PASSWORD` | Secret `redis` (релиз чарта Redis) |
| `REDIS_URL` | `redis://:$(REDIS_PASSWORD)@$(REDIS_HOST):$(REDIS_PORT)/$(REDIS_DB)` — собирается Kubernetes'ом |

## Часть 2 — CacheManager и cache-aside

[hc/lib/cache.py](../../hc/lib/cache.py) — `CacheManager` поверх `redis-py`:

- подключение из окружения (`CacheManager.from_env()`): `REDIS_URL`, либо
  `REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_PASSWORD`;
- `get`, `set(key, value, ttl)`, `exists`, `delete`, `ttl`, `get_or_set(key, producer, ttl)`;
  значения — JSON, ключи с префиксом `hc:`;
- TTL: по умолчанию `CACHE_DEFAULT_TTL` (300 c), `ttl=0` — без истечения;
- Redis недоступен → всегда «промах» + предупреждение в лог, приложение работает.

Где применяется (паттерн **cache-aside**: сначала кэш, при промахе — источник, результат в кэш):

| Что | Ключ | TTL | Файл |
|---|---|---|---|
| результаты внешних API (Celery-задачи) | `hc:api:weather:<lat>:<lon>`, `hc:api:cat_fact` | `CACHE_TTL_API` = 300 c | [hc/mq/celery_tasks.py](../../hc/mq/celery_tasks.py) |
| SQL: готовый `AsyncResult` (django-celery-results) | `hc:task_result:<task_id>` | `CACHE_TTL_RESULT` = 3600 c | [hc/mq/views.py](../../hc/mq/views.py) |
| SQL: агрегат `GROUP BY task_name, status` — `GET /api/v3/tasks/stats/` | `hc:task_stats` | `CACHE_TTL_STATS` = 30 c | [hc/mq/views.py](../../hc/mq/views.py) |

Ответ, пришедший из кэша, помечен полем `"cached": true`. Посмотреть ключи:

```sh
kubectl -n healthchecks exec redis-0 -- redis-cli -a "$PW" --no-auth-warning --scan --pattern 'hc:*'
kubectl -n healthchecks exec redis-0 -- redis-cli -a "$PW" --no-auth-warning ttl hc:task_stats
```

Тесты: `./manage.py test hc.lib.tests.test_cache hc.mq`.
