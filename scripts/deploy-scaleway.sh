#!/usr/bin/env bash
# Build the production image and push it to the Scaleway container registry.
#
#   ./scripts/deploy-scaleway.sh        show used versions + the next one to use
#   ./scripts/deploy-scaleway.sh v4     build + push version v4
#
# One-time login first (paste the Scaleway secret key when asked):
#   docker login rg.fr-par.scw.cloud/containerflow -u nologin
#
# After the push: Scaleway console → Serverless Containers → containerflow →
# Edit → change the image tag to the new version → Deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=rg.fr-par.scw.cloud/containerflow/app

# Versions already built on this Mac (v1-v3 predate this script and have no git tag)
used_tags() {
  { git tag -l 'deploy-*' | sed 's/^deploy-//'
    docker images "$REPO" --format '{{.Tag}}' 2>/dev/null; } | grep -E '^v[0-9]+$' | sort -uV
}

if [ -z "${1:-}" ]; then
  LAST=$(used_tags | tail -1)
  NEXT="v$(( ${LAST#v} + 1 ))"
  echo "Already used: $(used_tags | tr '\n' ' ')"
  echo "Latest:       $LAST   (roll back to the one before it if $LAST breaks)"
  echo "Next:         ./scripts/deploy-scaleway.sh $NEXT"
  exit 0
fi

TAG=$1
IMAGE=$REPO:$TAG

if [ -n "$(git status --porcelain)" ]; then
  echo "You have uncommitted changes. Commit them first so the deployed version is known."
  exit 1
fi
if used_tags | grep -qx "$TAG"; then
  echo "$TAG was already used. Run ./scripts/deploy-scaleway.sh (no version) to see the next one."
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
