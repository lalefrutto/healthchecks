# Политика для деплоя healthchecks: только чтение секретов приложения
# из KV v2 (mount "secret"). Для kv-v2 в путях появляется "data/" и "metadata/".
path "secret/data/healthchecks" {
  capabilities = ["read"]
}

path "secret/data/healthchecks/*" {
  capabilities = ["read"]
}

path "secret/metadata/healthchecks" {
  capabilities = ["read", "list"]
}

path "secret/metadata/healthchecks/*" {
  capabilities = ["read", "list"]
}
