#!/usr/bin/env bash
# Run ContainerFlow locally in Docker against a local MongoDB with test data.
# Nothing here touches Scaleway/production. Emails are only logged (no Resend key).
#
#   ./scripts/local-test.sh           build current code + (re)start app on http://localhost:8080
#   ./scripts/local-test.sh --reset   same, but first reload test data from data-migration/dump
#   ./scripts/local-test.sh --stop    stop app + database
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.local          # gitignored; holds local-only secrets
NET=cf-local
DB_CT=cf-mongo
APP_CT=cf-app
IMAGE=containerflow:test

if [ "${1:-}" = "--stop" ]; then
  docker stop "$APP_CT" "$DB_CT" >/dev/null 2>&1 || true
  echo "Stopped."
  exit 0
fi

docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and retry."; exit 1; }

# Local-only secrets, generated once
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
DB_NAME=containerflow
JWT_SECRET=$(openssl rand -hex 32)
CORS_ORIGINS=http://localhost:8080
APP_PUBLIC_URL=http://localhost:8080
LOCAL_SUPERADMIN_PASSWORD=$(openssl rand -base64 12 | tr -d '/+=')
EOF
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
fi
LOCAL_SUPERADMIN_PASSWORD=$(grep '^LOCAL_SUPERADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)

# Database
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
if docker container inspect "$DB_CT" >/dev/null 2>&1; then
  docker start "$DB_CT" >/dev/null
else
  docker run -d --name "$DB_CT" --network "$NET" -p 27017:27017 -v cf-mongo-data:/data/db mongo:7 >/dev/null
fi
until docker exec "$DB_CT" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; do sleep 1; done

USERS=$(docker exec "$DB_CT" mongosh --quiet containerflow --eval 'db.users.countDocuments()')
if [ "${1:-}" = "--reset" ] || [ "$USERS" = "0" ]; then
  echo "Loading test data from data-migration/dump ..."
  docker exec "$DB_CT" rm -rf /dump
  docker cp data-migration/dump "$DB_CT":/dump
  docker exec "$DB_CT" mongorestore --quiet --drop --nsFrom 'test_database.*' --nsTo 'containerflow.*' /dump
fi

# App
echo "Building image (first time takes a few minutes) ..."
docker build -q -t "$IMAGE" . >/dev/null

# Give the local super admin a known local-only password
HASH=$(docker run --rm -e PW="$LOCAL_SUPERADMIN_PASSWORD" "$IMAGE" \
  python -c "import bcrypt,os;print(bcrypt.hashpw(os.environ['PW'].encode(),bcrypt.gensalt()).decode())")
docker exec -e H="$HASH" "$DB_CT" mongosh --quiet containerflow \
  --eval 'db.users.updateMany({role:"super_admin"},{$set:{password_hash:process.env.H}})' >/dev/null

docker rm -f "$APP_CT" >/dev/null 2>&1 || true
docker run -d --name "$APP_CT" --network "$NET" -p 8080:8080 \
  --env-file "$ENV_FILE" -e MONGO_URL="mongodb://$DB_CT:27017" "$IMAGE" >/dev/null

printf "Starting"
until curl -fs http://localhost:8080/api/health >/dev/null 2>&1; do
  if ! docker container inspect -f '{{.State.Running}}' "$APP_CT" 2>/dev/null | grep -q true; then
    echo; echo "App crashed. Logs:"; docker logs --tail 40 "$APP_CT"; exit 1
  fi
  printf "."; sleep 2
done

SA_EMAIL=$(docker exec "$DB_CT" mongosh --quiet containerflow --eval 'db.users.findOne({role:"super_admin"}).email')
echo
echo "ContainerFlow is running:  http://localhost:8080"
echo "Super admin login:         $SA_EMAIL  (password: LOCAL_SUPERADMIN_PASSWORD in $ENV_FILE)"
echo "Logs:                      docker logs -f $APP_CT"
