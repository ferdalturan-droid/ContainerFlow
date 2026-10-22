#!/usr/bin/env bash
# Demo-data på containerflow.dk (2026-10-22).
#
#   ./scripts/seed-production.sh
#
# SLETTER alle firmaer, kunder, brugere og ture (super admin og
# systemindstillinger bevares) og opretter demo-datasættet fra
# scripts/seed_demo.py - samme data som ./scripts/local-test.sh --demo.
# Alle oprettede brugere får koden 123456; super admins kode ændres ikke.
#
# Før du kører det:
#   1. Deploy den nyeste version (./scripts/deploy-scaleway.sh + Scaleway-konsollen).
#      Scriptet stopper selv, hvis serveren kører en ældre version.
#   2. Hav databasens MONGO_URL (fra Scaleway-containerens miljøvariabler) og
#      super admin-login klar. Du bliver spurgt - intet vises eller gemmes.
#
# En JSON-backup af hele databasen lægges i ~/containerflow-backups først.
# Tager et par minutter.
set -euo pipefail
cd "$(dirname "$0")/.."

CF_URL=${CF_URL:-https://containerflow.dk}
IMAGE=${IMAGE:-containerflow:test}
BACKUP=${BACKUP:-$HOME/containerflow-backups}

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Billedet $IMAGE mangler. Kør ./scripts/local-test.sh én gang (den bygger det)."
  exit 1
fi

echo "Dette SLETTER alle firmaer, kunder, brugere og ture på $CF_URL"
echo "og opretter demo-data. Backup: $BACKUP"
echo
[ -n "${MONGO_URL:-}" ] || { read -r -s -p "MONGO_URL (vises ikke): " MONGO_URL; echo; }
[ -n "${DB_NAME:-}" ] || { read -r -p "DB_NAME [containerflow]: " DB_NAME; DB_NAME=${DB_NAME:-containerflow}; }
[ -n "${SA_EMAIL:-}" ] || read -r -p "Super admin email: " SA_EMAIL
[ -n "${SA_PASSWORD:-}" ] || { read -r -s -p "Super admin adgangskode (vises ikke): " SA_PASSWORD; echo; }
read -r -p "Skriv SLET for at fortsætte: " OK
[ "$OK" = "SLET" ] || { echo "Afbrudt - intet er ændret."; exit 1; }

mkdir -p "$BACKUP"
export MONGO_URL DB_NAME SA_EMAIL SA_PASSWORD
LOG="$BACKUP/demo-seed-$(date +%Y%m%d-%H%M%S).log"
echo "Opretter demo-data (et par minutter) ..."
docker run --rm -i -v "$BACKUP:/backup" \
  -e SEED_API="$CF_URL/api" -e MONGO_URL -e DB_NAME -e SA_EMAIL -e SA_PASSWORD \
  -e SEED_PASSWORD=123456 -e SEED_WIPE=ja-slet-alt \
  "$IMAGE" python - < scripts/seed_demo.py | tee "$LOG"
echo
echo "Færdig. Log og logins: $LOG"
