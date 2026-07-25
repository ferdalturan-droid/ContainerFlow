#!/usr/bin/env bash
# ContainerFlow — MongoDB restore script
# Restores a backup archive produced by backup_mongo.sh
#
# LOCAL USAGE:
#   ./restore_mongo.sh <path-to-archive.gz>
#   ./restore_mongo.sh /app/backups/latest.archive.gz
#   ./restore_mongo.sh /app/backups/2026-05-17/test_database-031200.archive.gz
#
# GOOGLE DRIVE USAGE (downloads to /tmp first, then restores):
#   ./restore_mongo.sh drive:latest
#   ./restore_mongo.sh drive:2026-05-17
#   ./restore_mongo.sh drive:id:<file-id-from-Drive>
#
# Optional: pass --drop to drop existing collections before restoring.
#   ./restore_mongo.sh latest.archive.gz --drop
#   ./restore_mongo.sh drive:latest --drop

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <archive.gz | drive:latest | drive:YYYY-MM-DD | drive:id:<id>> [--drop]"
  exit 1
fi

ARG="$1"
DROP_FLAG=""
if [[ "${2:-}" == "--drop" ]]; then
  DROP_FLAG="--drop"
fi

# Load Drive env if present
if [[ -f /app/scripts/.env ]]; then
  set -a; source /app/scripts/.env; set +a
fi

# Resolve ARCHIVE: handle drive: prefix
if [[ "${ARG}" == drive:* ]]; then
  TMP_DEST="/tmp/cf-restore-$(date +%s).archive.gz"
  case "${ARG}" in
    drive:latest)
      python3 /app/scripts/gdrive_download.py latest "${TMP_DEST}"
      ;;
    drive:id:*)
      FID="${ARG#drive:id:}"
      python3 /app/scripts/gdrive_download.py by-id "${FID}" "${TMP_DEST}"
      ;;
    drive:*)
      DATE="${ARG#drive:}"
      python3 /app/scripts/gdrive_download.py by-date "${DATE}" "${TMP_DEST}"
      ;;
  esac
  ARCHIVE="${TMP_DEST}"
else
  ARCHIVE="${ARG}"
fi

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "Archive not found: ${ARCHIVE}"
  exit 2
fi

MONGO_URL="${MONGO_URL:-$(grep -E '^MONGO_URL=' /app/backend/.env 2>/dev/null | cut -d'=' -f2- | tr -d '"')}"
MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"
DB_NAME="${DB_NAME:-$(grep -E '^DB_NAME=' /app/backend/.env 2>/dev/null | cut -d'=' -f2- | tr -d '"')}"
DB_NAME="${DB_NAME:-test_database}"

echo "Restoring ${ARCHIVE} → ${MONGO_URL}/${DB_NAME}"
echo "    drop existing: ${DROP_FLAG:-no}"
echo
echo "Press Enter to continue, Ctrl-C to cancel..."
read -r _

mongorestore \
  --uri="${MONGO_URL}" \
  --nsInclude="${DB_NAME}.*" \
  --archive="${ARCHIVE}" \
  --gzip \
  ${DROP_FLAG}

echo "Restore complete."
