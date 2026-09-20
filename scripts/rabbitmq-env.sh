#!/usr/bin/env bash
# Экспортирует RABBITMQ_URL для producer/consumer, забирая логин/пароль из Vault
# (AppRole из .env, policy rabbitmq-read). Скрипт нужно source'ить:
#
#   source scripts/rabbitmq-env.sh            # брокер через LoadBalancer + minikube tunnel
#   RABBITMQ_HOST=rabbitmq RABBITMQ_PORT=5672 source scripts/rabbitmq-env.sh   # внутри кластера
#
# Значения в терминал не печатаются.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck disable=SC1090
source "$_lib"

vault_login >/dev/null

_user="$(vals get 'ref+vault://secret/rabbitmq#/username')"
_pass="$(vals get 'ref+vault://secret/rabbitmq#/password')"
_host="${RABBITMQ_HOST:-127.0.0.1}"
_port="${RABBITMQ_PORT:-5672}"
_vhost="${RABBITMQ_VHOST:-%2F}"

export RABBITMQ_URL="amqp://${_user}:${_pass}@${_host}:${_port}/${_vhost}"
unset _user _pass _host _port _vhost _lib
echo "RABBITMQ_URL экспортирован (host $(sed -E 's|.*@([^/]+)/.*|\1|' <<<"$RABBITMQ_URL"))"
