# Нагрузочное тестирование и ресурсы (Задание 7, Части 1–2)

## Часть 1 — metrics-server и замер

```sh
minikube addons enable metrics-server
kubectl top nodes
kubectl -n healthchecks top pods --containers
```

Потребление в покое (после `helm` деплоя, без нагрузки):

| Контейнер | CPU | RAM |
|---|---|---|
| web (uWSGI, 4 процесса) | 1m | ~370Mi |
| celery-worker | 9m | ~190Mi |
| flower | 1m | ~115Mi |
| worker sendalerts / sendreports | 1m / 1m | 67Mi / 67Mi |
| postgresql | 8m | 52Mi |

## Часть 2 — Locust

[locustfile.py](locustfile.py) бьёт по реальным эндпоинтам: `GET /api/v3/checks/`,
`GET /api/v3/checks/<uuid>`, `POST /ping/<uuid>` (самый горячий путь healthchecks),
`GET /api/v3/tasks/stats/`. Через Ingress + `minikube tunnel`:

```sh
export HC_API_KEY=<rw-ключ проекта>
locust -f loadtest/locustfile.py --host https://healthchecks.local              # web UI :8089
locust -f loadtest/locustfile.py --host https://healthchecks.local \
    --headless -u 200 -r 20 -t 90s --only-summary --csv loadtest/results/users-200
```

### Что нашлось по дороге

1. **Лимит CPU 500m** — при 100 пользователях под упирался в лимит, дальше — 503.
   Поднят до 1000m.
2. **Probes** — на `/` с `timeoutSeconds: 1`: под нагрузкой probe не успевал, ingress
   снимал backend (503), liveness перезапускал под. Переведены на лёгкий
   `/api/v3/status/` с timeout 5 с и более терпимым `failureThreshold`.
3. **8 uWSGI-процессов** вместо 4 → OOMKilled на 640Mi (~90Mi на процесс). Оставлено
   4 процесса на под; рост нагрузки закрывает HPA (Часть 3) — больше подов.

### Результаты (1 под, 4 процесса, лимиты cpu 1000m / mem 640Mi)

| Пользователи | req/s | Ошибки | Avg | p95 | p99 | Max | Вердикт |
|---|---|---|---|---|---|---|---|
| 50 | 38 | 0.06% | 26 мс | 60 мс | 100 мс | 0.2 с | ок |
| 100 | 62 | 0.18% | 358 мс | 620 мс | 750 мс | 0.9 с | ок |
| 150 | 67 | 0.08% | 0.9 с | 1.4 с | 1.7 с | 1.9 с | ок |
| **200** | 68 | 0.02% | 1.6 с | 2.6 с | 3.6 с | 5.8 с | **максимум** (< 5–7 с) |
| 300 | 68 | 0.10% | 2.3 с | 4.6 с | 6.7 с | 64 с | нет |

Пропускная способность одного пода насыщается на ~68 req/s (4 синхронных
uWSGI-воркера); дальше растёт только очередь и время ответа.
Сырые CSV — в [results/](results/).

### Пиковое потребление и итоговые ресурсы web

Пик при 200–300 пользователях: CPU ~550m, RAM ~380Mi (Postgres — до 500m).
В [values.yaml](../charts/healthchecks/values.yaml):

```yaml
web:
  resources:
    requests: {cpu: 250m, memory: 400Mi}
    limits:   {cpu: 1000m, memory: 640Mi}
```
