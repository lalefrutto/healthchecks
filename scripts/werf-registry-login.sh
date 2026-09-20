#!/usr/bin/env bash
# Интеграция werf с Vault (Задание 9, Часть 2): получить учётку container
# registry из Vault и залогинить werf/docker в registry.
#
#   source scripts/werf-registry-login.sh     # экспортирует WERF_REPO, делает werf cr login
#
# Схема (как в презентации курса): .env (AppRole) -> vault login -> секрет
# secret/registry {url, username, password} -> `werf cr login` (docker-токен
# сохраняется в ~/.docker/config.json). Локально registry-аддон minikube без
# авторизации — password пустой, логин пропускается; для GHCR/Harbor в Vault
# кладутся реальные логин и токен, скрипт не меняется.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck disable=SC1090
source "$_lib"

vault_login >/dev/null

WERF_REPO="$(vals get 'ref+vault://secret/registry#/url')"
_user="$(vals get 'ref+vault://secret/registry#/username' 2>/dev/null || true)"
_pass="$(vals get 'ref+vault://secret/registry#/password' 2>/dev/null || true)"
export WERF_REPO

if [ -n "$_pass" ]; then
  # registry-хост = всё до первого "/"
  _registry="${WERF_REPO%%/*}"
  echo "==> werf cr login $_registry (учётка из Vault secret/registry)"
  echo "$_pass" | "${WERF_BIN:-werf}" cr login "$_registry" -u "$_user" --password-stdin
else
  echo "==> registry $WERF_REPO без авторизации (пароль в Vault пустой), login пропущен"
fi
unset _user _pass _registry _lib
