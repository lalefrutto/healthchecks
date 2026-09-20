# Чтение учётки container registry для werf (werf cr login)
path "secret/data/registry" {
  capabilities = ["read"]
}

path "secret/metadata/registry" {
  capabilities = ["read", "list"]
}
