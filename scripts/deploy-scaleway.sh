#!/usr/bin/env bash
# Build the production image and push it to the Scaleway container registry.
#
#   ./scripts/deploy-scaleway.sh v3
#
# One-time login first (paste the Scaleway secret key when asked):
#   docker login rg.fr-par.scw.cloud/containerflow -u nologin
#
# After the push: Scaleway console → Serverless Containers → containerflow →
# Edit → change the image tag to the new version → Deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG=${1:?"usage: ./scripts/deploy-scaleway.sh <tag, e.g. v3>"}
IMAGE=rg.fr-par.scw.cloud/containerflow/app:$TAG

if [ -n "$(git status --porcelain)" ]; then
  echo "You have uncommitted changes. Commit them first so the deployed version is known."
  exit 1
fi
if git rev-parse -q --verify "refs/tags/deploy-$TAG" >/dev/null; then
  echo "Tag $TAG was already deployed (git tag deploy-$TAG). Pick a new tag."
  exit 1
fi

# Scaleway runs amd64; Macs with Apple chips build arm64 by default
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

# Remember which commit this tag contains
git tag "deploy-$TAG"

echo
echo "Pushed $IMAGE (commit $(git rev-parse --short HEAD))."
echo "Now in the Scaleway console: container → Edit → image tag '$TAG' → Deploy."
