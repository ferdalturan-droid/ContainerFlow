#!/usr/bin/env bash
# End-to-end-testene i deres EGEN database og app (2026-10-19).
#
# Før kørte testene mod den lokale database, man selv bruger i browseren. For
# at få faste resultater slår de firmaets egne prisregler midlertidigt fra og
# opretter "E2E ..."-regler - så skiftede priserne på skærmen, mens testene
# kørte. Nu får testene en frisk database (containerflow_e2e) med testdata
# fra seed_local.py og en separat app på port 8081. Din lokale app og dine
# data på http://localhost:8080 røres ikke.
#
#   ./scripts/e2e.sh                alle flows
#   ./scripts/e2e.sh b2b behalf     udvalgte flows
#   KEEP=1 ./scripts/e2e.sh         lad test-appen køre bagefter (http://localhost:8081)
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.local
NET=cf-local
DB_CT=cf-mongo
APP_CT=cf-app-e2e
IMAGE=containerflow:test
DB=containerflow_e2e

[ -f "$ENV_FILE" ] || { echo "Kør ./scripts/local-test.sh først (opretter $ENV_FILE og databasen)."; exit 1; }
docker container inspect "$DB_CT" >/dev/null 2>&1 || { echo "Kør ./scripts/local-test.sh først (databasen $DB_CT findes ikke)."; exit 1; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Kør ./scripts/local-test.sh først (billedet $IMAGE findes ikke)."; exit 1; }
docker start "$DB_CT" >/dev/null
until docker exec "$DB_CT" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; do sleep 1; done

val() { grep "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
PASSWORD=$(val LOCAL_TEST_PASSWORD)

# Frisk testdatabase hver gang
docker exec "$DB_CT" mongosh --quiet "$DB" --eval 'db.dropDatabase()' >/dev/null

# Test-appen: samme billede, egen database, ingen rigtige mails
TMP_ENV=$(mktemp)
grep -v -e '^RESEND_API_KEY=' -e '^DB_NAME=' "$ENV_FILE" > "$TMP_ENV"
echo "DB_NAME=$DB" >> "$TMP_ENV"
docker rm -f "$APP_CT" >/dev/null 2>&1 || true
docker run -d --name "$APP_CT" --network "$NET" -p 8081:8080 --env-file "$TMP_ENV" \
  -e MONGO_URL="mongodb://$DB_CT:27017" -e SUPER_ADMIN_PASSWORD="$PASSWORD" "$IMAGE" >/dev/null
rm -f "$TMP_ENV"
# Backend og tests fra arbejdsmappen (så et nyt docker build ikke er nødvendigt)
docker cp backend/. "$APP_CT":/app/backend/ >/dev/null
docker restart "$APP_CT" >/dev/null
wait_up() {
  until curl -fs http://localhost:8081/api/health >/dev/null 2>&1; do
    docker container inspect -f '{{.State.Running}}' "$APP_CT" 2>/dev/null | grep -q true || { docker logs --tail 40 "$APP_CT"; exit 1; }
    sleep 1
  done
}
wait_up
echo "Testdata (databasen $DB) ..."
docker exec -i -e SEED_PASSWORD="$PASSWORD" -e SEED_EMAIL_BASE="$(val SEED_EMAIL_BASE)" \
  -e SUPER_ADMIN_EMAIL="$(val SUPER_ADMIN_EMAIL)" "$APP_CT" python - < scripts/seed_local.py >/dev/null
docker restart "$APP_CT" >/dev/null   # opstarts-rettelser kører på de nye data
wait_up

set +e
docker exec -e PW="$PASSWORD" -e E2E_DB_OK=1 "$APP_CT" python /app/backend/tests/e2e/run.py "$@"
RC=$?
set -e
[ -n "${KEEP:-}" ] || docker rm -f "$APP_CT" >/dev/null 2>&1 || true
exit $RC
