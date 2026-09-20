# Чтение секретов RabbitMQ (логин/пароль/erlang cookie) для деплоя чарта RabbitMQ
# и для приложения (Celery broker URL).
path "secret/data/rabbitmq" {
  capabilities = ["read"]
}

path "secret/metadata/rabbitmq" {
  capabilities = ["read", "list"]
}
