# locust-test — распределённый Locust через locust-k8s-operator

Задание 7, Часть 4. Тот же сценарий, что в ручном прогоне
([loadtest/README.md](../../loadtest/README.md)), но запускается в кластере
оператором: master + N worker'ов, web UI через Ingress.

Предварительно: оператор — [deploy/locust-operator/README.md](../../deploy/locust-operator/README.md).

## Что в чарте

| Шаблон | Ресурс |
|---|---|
| `configmap.yaml` | ConfigMap `<name>-locustfile` с [files/locustfile.py](files/locustfile.py) (монтируется оператором в `/lotest/src/`) |
| `secret.yaml` | Secret `<name>-env` — `HC_API_KEY` (и `HC_CHECK`) для locustfile, прокидывается через `env.secretRefs` |
| `locusttest.yaml` | CR `LocustTest` (`locust.io/v2`): образ, команды master/worker, `--users/--spawn-rate/--run-time` как в Части 2, `autostart`, реплики воркеров, ресурсы |
| `webui.yaml` | Service `<name>-webui:8089` на под мастера (оператор открывает только 5557/5558/9646) + Ingress `https://locust.local` с TLS |

Имя теста — `load-test-v2` (`values.yaml: name`), отсюда `load-test-v2-master`,
`load-test-v2-worker`, `load-test-v2-webui`.

## Запуск

```sh
bash scripts/deploy-locust-test.sh                       # API-ключ проекта берётся из БД
bash scripts/deploy-locust-test.sh --set test.users=300  # переопределить параметры
helm uninstall load-test -n healthchecks                 # остановить
```

Job'ы оператора неизменяемы, поэтому скрипт пересоздаёт релиз целиком.
Проверка: `kubectl -n healthchecks get locusttest` (PHASE Running, CONNECTED = воркеры),
`https://locust.local` — статистика в реальном времени (строка `127.0.0.1 locust.local` в hosts),
`kubectl -n healthchecks get hpa -w` — реакция HPA на нагрузку.

Цель теста — `http://healthchecks` (ClusterIP внутри кластера, без ingress/TLS),
поэтому имя сервиса добавлено в `ALLOWED_HOSTS` приложения.
