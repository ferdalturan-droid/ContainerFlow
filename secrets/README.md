# /app/secrets

Place server-only credentials here (chmod 600).

Files expected:
- `google_drive_sa.json` — Service Account JSON for Google Drive backups.
  Path is configurable via `GOOGLE_DRIVE_SA_JSON_PATH` in `/app/scripts/.env`.

This directory is gitignored.
