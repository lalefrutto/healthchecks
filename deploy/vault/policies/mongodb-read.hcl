# Чтение секретов MongoDB (root, пользователь приложения, basic auth mongo-express)
path "secret/data/mongodb" {
  capabilities = ["read"]
}

path "secret/metadata/mongodb" {
  capabilities = ["read", "list"]
}
