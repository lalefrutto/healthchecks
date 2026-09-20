# Чтение секретов MinIO (root для чарта/консоли, access/secret key приложения)
path "secret/data/minio" {
  capabilities = ["read"]
}

path "secret/metadata/minio" {
  capabilities = ["read", "list"]
}
