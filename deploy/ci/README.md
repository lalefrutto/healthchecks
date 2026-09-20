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
