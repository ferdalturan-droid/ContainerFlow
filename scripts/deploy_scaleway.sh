#!/usr/bin/env bash
# Build the production image and push it to the Scaleway registry.
#
#   ./scripts/deploy_scaleway.sh v3
#
# One-time login first (paste the Scaleway secret key when asked):
#   docker login rg.fr-par.scw.cloud/containerflow -u nologin
#
# After the push: Scaleway Console -> Serverless Containers -> containerflow ->
# Edit -> change the image tag to the new one -> Deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?Usage: $0 <tag>, e.g. $0 v3}"
IMAGE="rg.fr-par.scw.cloud/containerflow/app:${TAG}"

if [ -n "$(git status --porcelain)" ]; then
  echo "Warning: you have uncommitted changes; they WILL be included in the image."
  read -r -p "Continue? [y/N] " ok; [ "$ok" = "y" ] || exit 1
fi

docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
echo "Pushed $IMAGE (from commit $(git rev-parse --short HEAD))."
echo "Now set the image tag to '${TAG}' in the Scaleway console and Deploy."
