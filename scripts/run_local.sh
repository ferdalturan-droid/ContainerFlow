#!/usr/bin/env bash
# Run ContainerFlow locally in Docker: a local MongoDB + the same image that goes
# to Scaleway. Nothing here touches the production database.
#
#   ./scripts/run_local.sh          build + (re)start, open http://localhost:8080
#   ./scripts/run_local.sh stop     stop both containers
#   ./scripts/run_local.sh reset    delete the local database and start fresh
#
# First run loads data-migration/dump into the local DB. No RESEND_API_KEY is
# set, so emails are only written to the log (`docker logs cf-app`), never sent.
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  stop)  docker stop cf-app cf-mongo >/dev/null 2>&1 || true; echo "Stopped."; exit 0 ;;
  reset) docker rm -f cf-app cf-mongo >/dev/null 2>&1 || true
         docker volume rm cf-mongo-data >/dev/null 2>&1 || true
         echo "Local database deleted." ;;
esac

docker network inspect cf-local >/dev/null 2>&1 || docker network create cf-local >/dev/null

if docker ps -a --format '{{.Names}}' | grep -qx cf-mongo; then
  docker start cf-mongo >/dev/null
else
  echo "Starting local MongoDB..."
  docker run -d --name cf-mongo --network cf-local -p 27017:27017 \
    -v cf-mongo-data:/data/db mongo:7 >/dev/null
  until docker exec cf-mongo mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; do sleep 1; done
  echo "Loading data-migration/dump into the local database..."
  docker cp data-migration/dump cf-mongo:/dump
  docker exec cf-mongo mongorestore --quiet --nsFrom='test_database.*' --nsTo='containerflow.*' /dump
fi

echo "Building app image (first time takes a few minutes)..."
docker build -t containerflow:local .

docker rm -f cf-app >/dev/null 2>&1 || true
docker run -d --name cf-app --network cf-local -p 8080:8080 \
  -e MONGO_URL="mongodb://cf-mongo:27017" \
  -e DB_NAME="containerflow" \
  -e JWT_SECRET="local-dev-only-not-for-production" \
  -e CORS_ORIGINS="http://localhost:8080" \
  -e APP_PUBLIC_URL="http://localhost:8080" \
  containerflow:local >/dev/null

until curl -sf -o /dev/null http://localhost:8080/api/health; do sleep 1; done
echo "ContainerFlow is running: http://localhost:8080   (logs: docker logs -f cf-app)"
