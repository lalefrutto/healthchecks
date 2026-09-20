# CI/CD — semantic-release, GitHub Actions, self-hosted runner

Задание 8.

## Часть 1 — версия образа и пайплайн

[.releaserc.json](../../.releaserc.json) — semantic-release с preset
`conventionalcommits`: версия считается по сообщениям коммитов в `master`
(`feat:` → minor, `fix:`/`perf:`/`refactor:` → patch, `BREAKING CHANGE` → major),
тег `vX.Y.Z` + GitHub Release. Коммиты без такого префикса релиз не создают.

[.github/workflows/release.yml](../../.github/workflows/release.yml), три job'а:

| Job | Где | Что |
|---|---|---|
| `release` | GitHub-hosted | `semantic-release` → тег `vX.Y.Z`, outputs `published`/`tag` |
| `build` | GitHub-hosted | по тегу: `docker/build-push-action` → `ghcr.io/lalefrutto/healthchecks:vX.Y.Z` и `:latest` (кэш слоёв в GHA cache) |
| `deploy` | **self-hosted** (`runs-on: minikube-runners`, Часть 2) | `helm secrets upgrade --install` чарта с `global.image.tag=vX.Y.Z`; секреты — из Vault по AppRole (`VAULT_ROLE_ID`/`VAULT_SECRET_ID` в Secrets репозитория), `kubectl rollout status` |

`deploy` включается переменной репозитория `DEPLOY_ENABLED=true` (пока runner не
подключён — job пропускается, а не висит в очереди).

Проверка: `gh run list --workflow release.yml`, `gh release list`,
`docker manifest inspect ghcr.io/lalefrutto/healthchecks:vX.Y.Z`.

## Часть 2 — self-hosted runner в кластере (ARC)

Actions Runner Controller ставится двумя чартами из GHCR
([deploy/arc](../arc/), `scripts/deploy-arc.sh`):

1. `gha-runner-scale-set-controller` → namespace `arc-systems` (контроллер + listener,
   который держит long-poll к GitHub и просит контроллер создать под под каждый job);
2. `gha-runner-scale-set` → namespace `arc-runners`, релиз **`minikube-runners`** —
   это имя и есть метка для `runs-on`. Регистрация в репозитории по PAT
   (scope `repo`), токен передаётся через `--set`, в values не хранится.
   `minRunners: 0` — в простое подов нет, на job поднимается эфемерный
   runner и удаляется после.

Runner работает **внутри minikube**, поэтому kubeconfig ему не нужен:
[rbac.yaml](../arc/rbac.yaml) даёт его ServiceAccount роль `admin` в namespace
`healthchecks` (+ ClusterIssuer/Certificate/PV для чарта). Docker в runner'е
не нужен (образ собирает GitHub-hosted job), `containerMode` пустой.

Секреты/переменные репозитория для job'а `deploy` (через `gh`):

```sh
gh secret set VAULT_ROLE_ID  --body "$VAULT_ROLE_ID"
gh secret set VAULT_SECRET_ID --body "$VAULT_SECRET_ID"
gh variable set VAULT_ADDR --body http://vault.vault.svc.cluster.local:8200   # Vault изнутри кластера
gh variable set DEPLOY_ENABLED --body true
```

Проверка: `kubectl -n arc-systems get pods` (listener), во время job'а —
`kubectl -n arc-runners get pods` (эфемерный runner), в GitHub: Settings →
Actions → Runners → «minikube-runners», в логе job'а `deploy` — `Runner name: minikube-runners-…`.
