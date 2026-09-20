# Чтение пароля Redis — для деплоя чарта Redis и для приложения (кэш)
path "secret/data/redis" {
  capabilities = ["read"]
}

path "secret/metadata/redis" {
  capabilities = ["read", "list"]
}
