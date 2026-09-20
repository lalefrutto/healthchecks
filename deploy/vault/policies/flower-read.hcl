# Чтение basic-auth учётки Flower (UI мониторинга Celery)
path "secret/data/flower" {
  capabilities = ["read"]
}

path "secret/metadata/flower" {
  capabilities = ["read", "list"]
}
