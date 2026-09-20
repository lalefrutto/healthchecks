# MinIO — S3-хранилище для тел пингов

Задание 6. В методичке подпункты не расписаны, поэтому выбран сценарий, для
которого у healthchecks есть **штатная** поддержка: тела входящих пингов
(> 100 байт) приложение умеет складывать в S3-совместимое хранилище вместо
Postgres (настройки `S3_*`, [hc/lib/s3.py](../../hc/lib/s3.py)). MinIO —
это S3 в кластере.

## Часть 1 — MinIO

Секреты в Vault `secret/minio`: `root_user`/`root_password` (чарт и Console),
`access_key`/`secret_key` (пользователь приложения). Policy `minio-read`;
AppRole `healthchecks` — 6 policy. В [secrets.yaml](secrets.yaml) — `ref+vault://`.

Чарт — официальный `minio/minio` (https://charts.min.io/), [values.yaml](values.yaml):

- `mode: standalone`, 1 реплика, PVC 2Gi (в облаке — `distributed`, ≥ 4 реплик);
- S3 API — `service.type: LoadBalancer` (внутри `minio:9000`, снаружи `127.0.0.1:9000`);
- Web Console — Ingress `https://minio.local` с TLS от cert-manager;
- post-install job'ы чарта создают bucket `healthchecks`, политику
  `healthchecks-rw` (доступ **только** к этому bucket'у) и пользователя
  приложения с этой политикой — root-учётка приложению не выдаётся.

```sh
bash scripts/deploy-minio.sh
```

Строка в hosts: `127.0.0.1 minio.local`. Вход в Console — root из Vault
(`vault kv get -field=root_password secret/minio`).

## Часть 2 — приложение

Чарт healthchecks (`global.s3.*`) прокидывает в поды:

| Переменная | Источник |
|---|---|
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_REGION`, `S3_SECURE` | ConfigMap (`minio:9000`, `healthchecks`, `False` — plain HTTP внутри кластера) |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Secret `healthchecks-s3`, создаёт чарт из `secrets.s3AccessKey/s3SecretKey` (Vault `secret/minio`) |

Проверка: пинг с телом > 100 байт → в Postgres у `Ping` заполнен `object_size`,
а `body_raw` пуст; объект `<check uuid>/zi-<n>` лежит в bucket'е (видно в Console),
`ping.get_body()` читает его из MinIO. Чистка тел удалённых проверок —
штатная команда `manage.py pruneobjects`.
