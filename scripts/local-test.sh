#!/usr/bin/env bash
# Run ContainerFlow locally in Docker against a local MongoDB.
# Nothing here touches Scaleway/production.
#
#   ./scripts/local-test.sh          build current code + (re)start app on http://localhost:8080
#                                    (an empty database gets clean test data automatically)
#   ./scripts/local-test.sh --seed   wipe the local database and create clean test data
#   ./scripts/local-test.sh --mails  show the latest emails (invitation/reset links) the app made
#   ./scripts/local-test.sh --stop   stop app + database
#
# Logins for the test data are written to local-logins.txt. All test users share
# one password: LOCAL_TEST_PASSWORD in .env.local. Without RESEND_API_KEY in
# .env.local, emails are only written to the app log (see --mails).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.local          # gitignored; holds local-only secrets
NET=cf-local
DB_CT=cf-mongo
APP_CT=cf-app
IMAGE=containerflow:test

case "${1:-}" in
  --stop)
    docker stop "$APP_CT" "$DB_CT" >/dev/null 2>&1 || true
    echo "Stopped."; exit 0 ;;
  --mails)
    # The app logs only the first 500 chars of a mail (no link), so build the
    # links from the open invitation/reset tokens in the local database.
    docker exec "$DB_CT" mongosh --quiet containerflow --eval '
      const rows = db.invitation_tokens.find({used: false}).sort({expires_at: -1}).limit(10).toArray();
      if (!rows.length) print("No open invitation or password-reset links.");
      rows.reverse().forEach(t => {
        const u = db.users.findOne({id: t.user_id}) || {};
        const page = t.token_type === "reset" ? "reset-password" : "set-password";
        const kind = t.token_type === "reset" ? "Nulstil adgangskode" : "Invitation";
        print(kind + " -> " + (u.email || "?") + "  (valid until " + String(t.expires_at).slice(0, 16) + ")");
        print("   http://localhost:8080/" + page + "?token=" + t.token);
      });'
    exit 0 ;;
esac

docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and retry."; exit 1; }

# Local-only settings, generated once
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
DB_NAME=containerflow
JWT_SECRET=$(openssl rand -hex 32)
CORS_ORIGINS=http://localhost:8080
APP_PUBLIC_URL=http://localhost:8080
EOF
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
fi
# One password for every local test user (older files called it LOCAL_SUPERADMIN_PASSWORD)
if ! grep -q '^LOCAL_TEST_PASSWORD=' "$ENV_FILE"; then
  OLD=$(grep '^LOCAL_SUPERADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2- || true)
  echo "LOCAL_TEST_PASSWORD=${OLD:-$(openssl rand -base64 12 | tr -d '/+=')}" >> "$ENV_FILE"
fi
grep -q '^SUPER_ADMIN_EMAIL=' "$ENV_FILE" || echo "SUPER_ADMIN_EMAIL=doganmiketuran@gmail.com" >> "$ENV_FILE"
grep -q '^SEED_EMAIL_BASE=' "$ENV_FILE" || echo "SEED_EMAIL_BASE=ferdalturan@gmail.com" >> "$ENV_FILE"
val() { grep "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
PASSWORD=$(val LOCAL_TEST_PASSWORD)
SA_EMAIL=$(val SUPER_ADMIN_EMAIL)

# Database
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
if docker container inspect "$DB_CT" >/dev/null 2>&1; then
  docker start "$DB_CT" >/dev/null
else
  docker run -d --name "$DB_CT" --network "$NET" -p 27017:27017 -v cf-mongo-data:/data/db mongo:7 >/dev/null
fi
until docker exec "$DB_CT" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; do sleep 1; done

SEED=no
USERS=$(docker exec "$DB_CT" mongosh --quiet containerflow --eval 'db.users.countDocuments()')
if [ "${1:-}" = "--seed" ] || [ "${1:-}" = "--reset" ] || [ "$USERS" = "0" ]; then
  SEED=yes
  docker rm -f "$APP_CT" >/dev/null 2>&1 || true
  docker exec "$DB_CT" mongosh --quiet containerflow --eval 'db.dropDatabase()' >/dev/null
  echo "Local database wiped."
fi

echo "Building image (first time takes a few minutes) ..."
docker build -q -t "$IMAGE" . >/dev/null

start_app() {  # $1 = env file to use
  docker rm -f "$APP_CT" >/dev/null 2>&1 || true
  docker run -d --name "$APP_CT" --network "$NET" -p 8080:8080 \
    --env-file "$1" -e MONGO_URL="mongodb://$DB_CT:27017" \
    -e SUPER_ADMIN_PASSWORD="$PASSWORD" "$IMAGE" >/dev/null
  printf "Starting"
  until curl -fs http://localhost:8080/api/health >/dev/null 2>&1; do
    if ! docker container inspect -f '{{.State.Running}}' "$APP_CT" 2>/dev/null | grep -q true; then
      echo; echo "App crashed. Logs:"; docker logs --tail 40 "$APP_CT"; exit 1
    fi
    printf "."; sleep 2
  done
  echo
}

if [ "$SEED" = yes ]; then
  # Seed with real email sending switched off, so no invitation mails go out
  NOMAIL=$(mktemp); grep -v '^RESEND_API_KEY=' "$ENV_FILE" > "$NOMAIL"
  start_app "$NOMAIL"; rm -f "$NOMAIL"
  echo "Creating clean test data ..."
  OUT=$(docker exec -i -e SEED_PASSWORD="$PASSWORD" -e SEED_EMAIL_BASE="$(val SEED_EMAIL_BASE)" \
        -e SUPER_ADMIN_EMAIL="$SA_EMAIL" "$APP_CT" python - < scripts/seed_local.py)
  echo "${OUT%%@@LOGINS@@*}" | head -8
  echo "${OUT#*@@LOGINS@@}" | sed 1d > local-logins.txt
fi

# Keep the super admin's local password in sync with .env.local
HASH=$(docker run --rm -e PW="$PASSWORD" "$IMAGE" \
  python -c "import bcrypt,os;print(bcrypt.hashpw(os.environ['PW'].encode(),bcrypt.gensalt()).decode())")
docker exec -e H="$HASH" "$DB_CT" mongosh --quiet containerflow \
  --eval 'db.users.updateMany({role:"super_admin"},{$set:{password_hash:process.env.H}})' >/dev/null

start_app "$ENV_FILE"

echo "ContainerFlow is running:  http://localhost:8080"
echo "Logins:                    local-logins.txt  (password: LOCAL_TEST_PASSWORD in $ENV_FILE)"
RESEND_KEY=$(val RESEND_API_KEY || true)
if [ -z "$RESEND_KEY" ]; then
  echo "Emails:                    not sent - see them with ./scripts/local-test.sh --mails"
elif [[ "$RESEND_KEY" != re_* ]]; then
  echo "Emails:                    WARNING - RESEND_API_KEY in $ENV_FILE does not look like a Resend key (should start with re_)"
else
  echo "Emails:                    sent for real via Resend"
fi
