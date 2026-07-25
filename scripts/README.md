# ContainerFlow — Backup & Restore (with Google Drive)

Automated daily MongoDB backups for ContainerFlow.
Local copy is always kept; Google Drive upload is optional and runs after a
successful local dump. Restoring works directly from a local archive **or**
straight from Google Drive.

```
/app/
├── backups/                       <- local archives (auto-created)
│   ├── 2026-02-18/
│   │   └── test_database-030100.archive.gz
│   └── latest.archive.gz          <- symlink to most recent archive
├── scripts/
│   ├── backup_mongo.sh            <- dump + (optional) Drive upload + rotate
│   ├── restore_mongo.sh           <- restore local OR drive:* sources
│   ├── setup_backup_cron.sh       <- install daily 03:00 cron
│   ├── gdrive_uploader.py         <- upload / list / prune Drive backups
│   ├── gdrive_download.py         <- download a backup from Drive
│   ├── requirements.txt           <- google-api-python-client, google-auth
│   ├── .env.example               <- copy to .env and fill in values
│   └── .env                       <- (you create; gitignored)
└── secrets/
    └── google_drive_sa.json       <- (you create; chmod 600; gitignored)
```

## 1. One-time Google Cloud setup (Service Account)

1. Go to **<https://console.cloud.google.com>** → create / pick a project.
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **IAM & Admin → Service Accounts** → **Create service account**
   * Name: `containerflow-backup`
   * Role: *(no project roles needed — Drive permissions are granted via
     folder sharing in step 5)*.
4. Open the new service account → **Keys** → **Add key → Create new key →
   JSON**. A JSON file is downloaded.
   * Save it as `/app/secrets/google_drive_sa.json`, then `chmod 600`.
5. In your normal Google Drive, **create a folder** (e.g.
   `ContainerFlow-Backups`) and **share it** with the
   `client_email` from the JSON (e.g. `containerflow-backup@<project>.iam.gserviceaccount.com`)
   with **Editor** access.
6. Copy the folder ID from the URL
   (`https://drive.google.com/drive/folders/<THIS_IS_THE_ID>`).

## 2. Configure

```bash
cp /app/scripts/.env.example /app/scripts/.env
chmod 600 /app/scripts/.env
# Edit /app/scripts/.env and set at minimum:
#   GOOGLE_DRIVE_SA_JSON_PATH=/app/secrets/google_drive_sa.json
#   GOOGLE_DRIVE_FOLDER_ID=<the-folder-id-from-step-6>
```

Install Python dependencies for the scripts (one-time):

```bash
pip install -r /app/scripts/requirements.txt
```

## 3. First manual backup (verify everything works)

```bash
/app/scripts/backup_mongo.sh
```

Expected output (truncated):

```
[2026-02-18 03:00:01] Backing up 'test_database' from mongodb://localhost:27017
[2026-02-18 03:00:01] → /app/backups/2026-02-18/test_database-030001.archive.gz
[2026-02-18 03:00:04] Local backup OK — size=4.2M
[2026-02-18 03:00:04] GDRIVE: uploading /app/backups/2026-02-18/test_database-030001.archive.gz
[2026-02-18 03:00:08] INFO gdrive: Upload OK — id=1Ab... name=test_database-030001.archive.gz
[2026-02-18 03:00:08] GDRIVE: upload OK
[2026-02-18 03:00:08] GDRIVE: pruning > 30 day(s)
[2026-02-18 03:00:09] Done. Local retention=30d, Drive retention=30d.
```

If Drive is not configured yet, only the local backup runs:

```
[2026-02-18 03:00:04] GDRIVE: skipping upload — GOOGLE_DRIVE_FOLDER_ID not set
```

## 4. Schedule the daily cron

```bash
/app/scripts/setup_backup_cron.sh
```

This installs **`0 3 * * *  /app/scripts/backup_mongo.sh >> /var/log/cf-backup.log 2>&1`**.

## 5. Restore

### From local
```bash
/app/scripts/restore_mongo.sh /app/backups/latest.archive.gz
/app/scripts/restore_mongo.sh /app/backups/2026-02-18/test_database-030001.archive.gz --drop
```

### From Google Drive
```bash
/app/scripts/restore_mongo.sh drive:latest               # newest available
/app/scripts/restore_mongo.sh drive:2026-02-18           # newest of that day
/app/scripts/restore_mongo.sh drive:id:1AbCd...          # specific Drive file ID
/app/scripts/restore_mongo.sh drive:latest --drop        # wipe DB first
```

The script downloads the archive to `/tmp/cf-restore-<ts>.archive.gz`, then
runs `mongorestore --archive --gzip` against it (identical to the local path
— full restore compatibility preserved).

## 6. Inspect Drive backups

```bash
# List everything in the parent folder
python3 /app/scripts/gdrive_uploader.py list

# Manually prune older than 14 days (overrides .env)
python3 /app/scripts/gdrive_uploader.py prune 14

# Manually upload an existing local archive to a custom subfolder
python3 /app/scripts/gdrive_uploader.py upload /path/to/file.archive.gz 2026-02-18
```

## 7. How credentials/config can be updated later

Everything reads from environment variables, in this precedence:

1. Variables already in the shell environment (highest)
2. `/app/scripts/.env` (auto-loaded by both `backup_mongo.sh` and
   `gdrive_uploader.py`)
3. Built-in defaults

To rotate the service account: drop a new JSON at the path pointed to by
`GOOGLE_DRIVE_SA_JSON_PATH` and run a manual `./backup_mongo.sh` to verify.

To switch Drive folders: change `GOOGLE_DRIVE_FOLDER_ID` in
`/app/scripts/.env` — no script changes required.

## 8. Security notes

* `/app/secrets/` and `/app/scripts/.env` should be `chmod 600` and are
  gitignored.
* The service account has access **only** to the folder you shared with it
  — it cannot see the rest of your Drive.
* Drive upload failure does **NOT** delete or invalidate the local backup
  (idempotent retry on the next cron run).
* `mongodump --gzip --archive` produces one single, encrypted-safe
  compressed file — no temp directory artifacts left behind.
