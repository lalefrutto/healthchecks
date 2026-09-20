# werf

Задание 9. werf собирает образ из `docker/Dockerfile`, публикует его в
container registry и выкатывает Helm-чарт `.helm/` одной командой `werf converge`.

## Часть 1 — структура werf-проекта

```
werf.yaml              # проект healthchecks, образ healthchecks (dockerfile: docker/Dockerfile), namespace/release
werf-giterminism.yaml  # исключения из giterminism (временный values с секретами)
.helm/                 # Helm-чарт приложения (перенесён из charts/healthchecks)
  Chart.yaml           #   зависимости — subchart'ы (postgresql, celery-worker, flower)
  values.yaml          #   глобальные values проекта (global.* видят subchart'ы)
  secrets.yaml         #   ссылки ref+vault:// (разворачиваются перед converge)
  templates/, charts/  #   манифесты и subchart'ы
docker/Dockerfile      # исходники образа
```

Образ в шаблонах: `{{ .Values.werf.image.healthchecks }}` (в subchart'ах —
`global.werf.image.healthchecks`) — werf подставляет полное имя с
content-based тегом; без werf (helm/CI) используется `global.image.*`.

werf читает только **закоммиченные** файлы (giterminism): перед `converge`
изменения в `werf.yaml`, `.helm/`, `docker/` должны быть в git.

## Часть 2 — Vault и деплой

**Docker-токен из Vault** — [scripts/werf-registry-login.sh](../../scripts/werf-registry-login.sh):
`.env` (AppRole) → `vault login` → `secret/registry` `{url, username, password}`
(policy `registry-read`) → `werf cr login <registry>` (токен попадает в docker
config, которым пользуется werf). Локально registry — аддон minikube без
авторизации (пароль пустой, login пропускается); для GHCR/Harbor достаточно
положить в Vault реальный логин и токен, скрипт не меняется:

```sh
vault kv put secret/registry url=ghcr.io/<user>/healthchecks username=<user> password=<PAT write:packages>
```

**Деплой** — [scripts/werf-deploy.sh](../../scripts/werf-deploy.sh):

1. `vault login` (AppRole из `.env`), `vals eval -f .helm/secrets.yaml` →
   временный `.helm/.secrets.*.yaml` (в `.gitignore`, разрешён в
   `werf-giterminism.yaml`) — werf не умеет helm-secrets, поэтому секреты
   разворачиваются заранее;
2. registry login (см. выше);
3. `werf converge --repo <registry> --values <секреты>` — сборка (с кэшем стадий
   в registry), публикация, `helm upgrade`-эквивалент с ожиданием готовности ресурсов.

### Особенности Windows

Нативный `werf.exe` требует привилегии на создание symlink'ов (Developer Mode
или администратор), поэтому скрипт запускает werf в официальном контейнере
`registry.werf.io/werf/werf:2-stable` с **Buildah**-backend'ом (`--privileged`,
сборка и push внутри контейнера, docker-демон хоста не участвует).

Контейнер делит сетевой namespace с узлом minikube (`--network container:minikube`),
поэтому registry-аддон доступен как `127.0.0.1:5000` — то же имя, по которому
kubelet тянет образ через registry-proxy аддона, — а API-сервер как
`127.0.0.1:8443` (kubeconfig передаётся через `WERF_KUBE_CONFIG_BASE64` с
переписанным адресом). Docker Desktop при таком подходе не нужно настраивать
на insecure-registry: попытка демона ходить в plain-HTTP registry по HTTPS
виснет (registry на TLS-мусор молчит), и fallback на HTTP не срабатывает.

```sh
minikube addons enable registry
bash scripts/werf-deploy.sh                # сборка + деплой
bash scripts/werf-deploy.sh --dry-run      # что изменится
```

На Linux/macOS с нативным werf: `WERF_NATIVE=1 bash scripts/werf-deploy.sh`.

Проверка: `kubectl -n healthchecks get deploy healthchecks-web -o jsonpath='{.spec.template.spec.containers[0].image}'`
→ `127.0.0.1:5000/healthchecks:<content-based tag>`; `helm -n healthchecks history healthchecks`.
