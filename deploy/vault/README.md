# Vault + helm-secrets

Секреты приложения (Django `SECRET_KEY`, пароль Postgres) хранятся в HashiCorp
Vault, а не в git. В values чарта лежат только ссылки `ref+vault://...`
([charts/healthchecks/secrets.yaml](../../charts/healthchecks/secrets.yaml)),
которые при деплое разворачивает `helm-secrets` с backend'ом `vals`.

```
.env (VAULT_ADDR, AppRole)
   │
   ▼
scripts/deploy.sh ── vault login (AppRole) ──► токен с policy healthchecks-read
   │
   ▼
helm secrets -b vals upgrade --install ... -f secrets.yaml
   │  vals: ref+vault://secret/healthchecks#/SECRET_KEY  ──►  значение из KV v2
   ▼
Secret'ы в кластере (healthchecks, healthchecks-postgresql)
```

## Установка инструментов

```sh
scoop install vals vault            # или любой другой способ, см. сайты проектов
helm plugin install https://github.com/jkroepke/helm-secrets/releases/download/v4.7.7/secrets-4.7.7.tgz \
  --keyring <(curl -fsSL https://github.com/jkroepke.gpg | gpg --dearmor)
```

## Развёртывание Vault

```sh
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault -n vault --create-namespace -f deploy/vault/values.yaml
```

[values.yaml](values.yaml): standalone-режим, file-хранилище на PVC, UI включён,
API и UI наружу через Ingress `https://vault.local` (TLS от того же CA-issuer'а
cert-manager, что и у приложения). Для доступа с хоста — `minikube tunnel` и
строка `127.0.0.1 vault.local` в hosts.

## Инициализация и настройка

```sh
bash deploy/vault/setup.sh
```

[setup.sh](setup.sh) идемпотентен и делает всё через `kubectl exec` в под `vault-0`:

1. `vault operator init` (1 ключ / порог 1 — только для локальной разработки) →
   `deploy/vault/.vault-keys.json` (в `.gitignore`);
2. `vault operator unseal` — повторный запуск скрипта после рестарта кластера
   просто распечатает Vault;
3. secrets engine **KV v2** на `secret/`;
4. секреты компонентов (генерируются один раз, повторный запуск их не трогает):
   `secret/healthchecks` (`SECRET_KEY`, `DB_PASSWORD`),
   `secret/rabbitmq` (`username`, `password`, `erlang_cookie`);
5. policies из [policies/](policies/) — по одной на компонент, только чтение
   своего пути: `healthchecks-read`, `rabbitmq-read`;
6. auth-метод **AppRole**, роль `healthchecks` со всеми policy из п.5
   (список собирается из файлов, новая policy = новый `.hcl`);
   `role_id`/`secret_id` записываются в `.env` (шаблон — [.env.example](../../.env.example)).

Root-токен используется только этим скриптом; деплой ходит в Vault под AppRole.

## Деплой приложения

```sh
bash scripts/deploy.sh                 # приложение: helm upgrade --install с секретами из Vault
bash scripts/deploy-rabbitmq.sh        # RabbitMQ (deploy/rabbitmq)
bash scripts/deploy.sh --dry-run       # доп. аргументы уходят в helm
```

Общая логика (загрузка `.env`, AppRole-логин, `helm secrets ... upgrade --install`)
вынесена в [scripts/lib.sh](../../scripts/lib.sh).

Проверить, что vals резолвит ссылку (значение не печатаем):

```sh
set -a; . .env; set +a
VAULT_TOKEN=$(vault write -field=token auth/approle/login role_id=$VAULT_ROLE_ID secret_id=$VAULT_SECRET_ID)
VAULT_AUTH_METHOD=token vals get 'ref+vault://secret/healthchecks#/SECRET_KEY' | wc -c
```

## Ротация секрета

```sh
vault kv patch secret/healthchecks SECRET_KEY=$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)
bash scripts/deploy.sh
```

На подах есть аннотация `checksum/secrets`, поэтому смена значения в Vault
после `deploy.sh` перекатывает web и worker. Пароль Postgres так менять нельзя:
образ `postgres` читает `POSTGRES_PASSWORD` только при первой инициализации
данных, поэтому сначала `ALTER USER healthchecks PASSWORD '...'`, затем Vault.

## Примечания

- `vals` на Windows собирает путь AppRole-логина с `\` (`auth\approle\login`),
  поэтому `deploy.sh` логинится через `vault` CLI и отдаёт vals готовый токен.
- `helm lint charts/healthchecks` предупреждает про пустые `secrets.secretKey`
  и `postgresql.auth.password` — это ожидаемо: значения обязательны (`required`)
  и приходят из `secrets.yaml`. Для чистого lint: `helm lint charts/healthchecks -f charts/healthchecks/secrets.yaml`.
