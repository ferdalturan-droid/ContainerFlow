#!/usr/bin/env bash
# ContainerFlow — MongoDB daily backup script
# 1) Creates a compressed mongodump in $BACKUP_DIR/YYYY-MM-DD/
# 2) Optionally uploads the same archive to Google Drive (via gdrive_uploader.py)
# 3) Rotates local + Drive copies according to RETENTION_DAYS / GDRIVE_RETENTION_DAYS
#
# Usage:
#   ./backup_mongo.sh                       # backup with defaults + upload
#   BACKUP_DIR=/var/backups/cf ./backup_mongo.sh
#   RETENTION_DAYS=14 ./backup_mongo.sh
#   GDRIVE_UPLOAD_ENABLED=0 ./backup_mongo.sh   # skip Drive upload
#
# Cron (daily at 03:00):
#   0 3 * * *  /app/scripts/backup_mongo.sh >> /var/log/cf-backup.log 2>&1

set -euo pipefail

# ---- Load config (env-overridable) -------------------------------------------
# Source /app/scripts/.env if present so Google Drive config is picked up.
if [[ -f /app/scripts/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /app/scripts/.env
  set +a
fi

MONGO_URL="${MONGO_URL:-$(grep -E '^MONGO_URL=' /app/backend/.env 2>/dev/null | cut -d'=' -f2- | tr -d '"')}"
MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"

DB_NAME="${DB_NAME:-$(grep -E '^DB_NAME=' /app/backend/.env 2>/dev/null | cut -d'=' -f2- | tr -d '"')}"
DB_NAME="${DB_NAME:-test_database}"

BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
GDRIVE_UPLOAD_ENABLED="${GDRIVE_UPLOAD_ENABLED:-1}"
GDRIVE_RETENTION_DAYS="${GDRIVE_RETENTION_DAYS:-30}"

TODAY="$(date +%F)"             # 2026-05-17
TS="$(date +%H%M%S)"            # 154212
OUT_DIR="${BACKUP_DIR}/${TODAY}"
ARCHIVE="${OUT_DIR}/${DB_NAME}-${TS}.archive.gz"
LATEST_LINK="${BACKUP_DIR}/latest.archive.gz"

mkdir -p "${OUT_DIR}"

echo "[$(date '+%F %T')] Backing up '${DB_NAME}' from ${MONGO_URL}"
echo "[$(date '+%F %T')] → ${ARCHIVE}"

# ---- Local dump (compressed, single archive, restore-compatible) ------------
mongodump \
  --uri="${MONGO_URL}" \
  --db="${DB_NAME}" \
  --archive="${ARCHIVE}" \
  --gzip \
  --quiet

ln -sf "${ARCHIVE}" "${LATEST_LINK}"

SIZE_HUMAN="$(du -h "${ARCHIVE}" | cut -f1)"
echo "[$(date '+%F %T')] Local backup OK — size=${SIZE_HUMAN}"

# ---- Google Drive upload (optional, non-fatal) ------------------------------
if [[ "${GDRIVE_UPLOAD_ENABLED}" == "1" ]]; then
  if [[ -z "${GOOGLE_DRIVE_FOLDER_ID:-}" ]]; then
    echo "[$(date '+%F %T')] GDRIVE: skipping upload — GOOGLE_DRIVE_FOLDER_ID not set"
  else
    echo "[$(date '+%F %T')] GDRIVE: uploading ${ARCHIVE}"
    if python3 /app/scripts/gdrive_uploader.py upload "${ARCHIVE}" "${TODAY}"; then
      echo "[$(date '+%F %T')] GDRIVE: upload OK"

      echo "[$(date '+%F %T')] GDRIVE: pruning > ${GDRIVE_RETENTION_DAYS} day(s)"
      python3 /app/scripts/gdrive_uploader.py prune "${GDRIVE_RETENTION_DAYS}" || \
        echo "[$(date '+%F %T')] GDRIVE: prune failed (non-fatal)"
    else
      echo "[$(date '+%F %T')] GDRIVE: upload FAILED (local copy is intact)"
    fi
  fi
else
  echo "[$(date '+%F %T')] GDRIVE: upload disabled (GDRIVE_UPLOAD_ENABLED=0)"
fi

# ---- Local rotation: delete day-folders older than RETENTION_DAYS -----------
find "${BACKUP_DIR}" -maxdepth 1 -type d -name '20*' -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} \; || true

echo "[$(date '+%F %T')] Done. Local retention=${RETENTION_DAYS}d, Drive retention=${GDRIVE_RETENTION_DAYS}d."
