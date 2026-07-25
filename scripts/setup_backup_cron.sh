#!/usr/bin/env bash
# ContainerFlow — install a daily cron job for MongoDB backup
# Runs every day at 03:00 server time. Logs to /var/log/cf-backup.log.

set -euo pipefail

SCRIPT_PATH="/app/scripts/backup_mongo.sh"
CRON_LINE="0 3 * * * ${SCRIPT_PATH} >> /var/log/cf-backup.log 2>&1"
CRON_TAG="# containerflow-mongo-backup"

if [[ ! -x "${SCRIPT_PATH}" ]]; then
  chmod +x "${SCRIPT_PATH}"
fi

# Replace any existing entry to keep idempotent
TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "${CRON_TAG}" > "${TMP}" || true
{
  echo "${CRON_TAG}"
  echo "${CRON_LINE}"
} >> "${TMP}"
crontab "${TMP}"
rm -f "${TMP}"

touch /var/log/cf-backup.log
echo "Cron installed:"
crontab -l | grep -A1 "${CRON_TAG}"
echo
echo "First backup logs will appear in /var/log/cf-backup.log"
