#!/usr/bin/env bash
# Установка Actions Runner Controller (ARC) и набора self-hosted runner'ов
# для репозитория в кластер minikube (Задание 8, Часть 2).
#
#   GITHUB_PAT=<токен со scope repo> scripts/deploy-arc.sh
#   (без GITHUB_PAT берётся токен gh CLI: gh auth token)
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARC_VERSION="${ARC_VERSION:-0.13.0}"
PAT="${GITHUB_PAT:-$(gh auth token)}"
[ -n "$PAT" ] || { echo "!! нет токена: задайте GITHUB_PAT или залогиньтесь в gh" >&2; exit 1; }

echo "==> controller (arc-systems)"
helm upgrade --install arc \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller \
  --version "$ARC_VERSION" -n arc-systems --create-namespace \
  -f "$ROOT_DIR/deploy/arc/controller-values.yaml" --wait

echo "==> RBAC для runner'ов"
kubectl create namespace arc-runners --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl apply -f "$ROOT_DIR/deploy/arc/rbac.yaml"

echo "==> runner scale set minikube-runners (arc-runners)"
helm upgrade --install minikube-runners \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \
  --version "$ARC_VERSION" -n arc-runners \
  -f "$ROOT_DIR/deploy/arc/runner-set-values.yaml" \
  --set githubConfigSecret.github_token="$PAT" --wait

kubectl -n arc-systems get pods
kubectl -n arc-runners get autoscalingrunnersets
