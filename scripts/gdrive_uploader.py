#!/usr/bin/env python3
"""
ContainerFlow — Google Drive uploader for MongoDB backup archives.

This module is standalone (no FastAPI imports) so it can be called from
the cron-driven backup_mongo.sh script without touching the running app.

USAGE
-----
    python3 gdrive_uploader.py upload <local_file>   [<remote_subfolder>]
    python3 gdrive_uploader.py prune  [<keep_days>]
    python3 gdrive_uploader.py list

CONFIGURATION (env vars; can also live in /app/scripts/.env)
------------------------------------------------------------
    GOOGLE_DRIVE_SA_JSON_PATH   absolute path to service-account JSON
                                (default: /app/secrets/google_drive_sa.json)
    GOOGLE_DRIVE_FOLDER_ID      ID of the *parent* Drive folder shared
                                with the service account
    GOOGLE_DRIVE_ROOT_NAME      friendly name of the root folder used in
                                logging (default: ContainerFlow-Backups)
    GDRIVE_RETENTION_DAYS       how many days of backups to keep in Drive
                                (default: 30)

The service account email must have *Editor* access on the parent folder.
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# -------------------------------------------------------------------- env load
def _load_env_file(path: str) -> None:
    """Lightweight .env loader (no python-dotenv dependency)."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


_load_env_file("/app/scripts/.env")

# -------------------------------------------------------------------- logging
logging.basicConfig(
    level=os.environ.get("GDRIVE_LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s gdrive: %(message)s",
    datefmt="%F %T",
)
log = logging.getLogger("gdrive")

# -------------------------------------------------------------------- config
SA_JSON_PATH = os.environ.get(
    "GOOGLE_DRIVE_SA_JSON_PATH", "/app/secrets/google_drive_sa.json"
)
PARENT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
ROOT_NAME = os.environ.get("GOOGLE_DRIVE_ROOT_NAME", "ContainerFlow-Backups")
RETENTION_DAYS = int(os.environ.get("GDRIVE_RETENTION_DAYS", "30"))
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB resumable chunks


# ==================================================================== client
def _build_service():
    """Build an authenticated Drive v3 client using a service-account JSON."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover
        log.error(
            "Missing google libraries. Install with: "
            "pip install -r /app/scripts/requirements.txt"
        )
        raise SystemExit(2) from e

    if not os.path.isfile(SA_JSON_PATH):
        log.error("Service-account JSON not found: %s", SA_JSON_PATH)
        log.error(
            "Set GOOGLE_DRIVE_SA_JSON_PATH or place the file at the default path."
        )
        raise SystemExit(3)
    if not PARENT_FOLDER_ID:
        log.error("GOOGLE_DRIVE_FOLDER_ID is not configured.")
        raise SystemExit(4)

    creds = service_account.Credentials.from_service_account_file(
        SA_JSON_PATH, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ==================================================================== helpers
def _find_or_create_subfolder(svc, parent_id: str, name: str) -> str:
    """Return the ID of <parent_id>/<name>, creating it if missing."""
    safe_name = name.replace("'", "\\'")
    q = (
        f"'{parent_id}' in parents and "
        f"name = '{safe_name}' and "
        f"mimeType = '{FOLDER_MIME}' and "
        f"trashed = false"
    )
    res = svc.files().list(
        q=q, fields="files(id, name)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    items = res.get("files", [])
    if items:
        return items[0]["id"]

    log.info("Creating subfolder '%s' under parent %s", name, parent_id)
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    created = svc.files().create(
        body=meta, fields="id", supportsAllDrives=True
    ).execute()
    return created["id"]


# ==================================================================== actions
def upload(local_path: str, remote_subfolder: Optional[str] = None) -> dict:
    """Upload `local_path` into <parent>/<remote_subfolder or today>/."""
    from googleapiclient.http import MediaFileUpload

    p = Path(local_path)
    if not p.is_file():
        log.error("Local file not found: %s", local_path)
        raise SystemExit(5)

    subfolder = remote_subfolder or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    svc = _build_service()

    folder_id = _find_or_create_subfolder(svc, PARENT_FOLDER_ID, subfolder)

    file_size = p.stat().st_size
    log.info(
        "Uploading %s (%.2f MB) → %s/%s/",
        p.name, file_size / 1_048_576, ROOT_NAME, subfolder,
    )

    media = MediaFileUpload(
        str(p),
        mimetype="application/gzip",
        chunksize=CHUNK_SIZE,
        resumable=True,
    )
    request = svc.files().create(
        body={"name": p.name, "parents": [folder_id]},
        media_body=media,
        fields="id, name, size, webViewLink",
        supportsAllDrives=True,
    )

    response = None
    last_pct = -1
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct != last_pct and pct % 10 == 0:
                log.info("  ...%d%%", pct)
                last_pct = pct

    log.info(
        "Upload OK — id=%s name=%s link=%s",
        response.get("id"), response.get("name"), response.get("webViewLink"),
    )
    return response


def list_backups() -> list:
    """List all files in every dated subfolder of the parent folder."""
    svc = _build_service()
    # List subfolders
    q_folders = (
        f"'{PARENT_FOLDER_ID}' in parents and "
        f"mimeType = '{FOLDER_MIME}' and trashed = false"
    )
    folders = svc.files().list(
        q=q_folders, fields="files(id, name, createdTime)", pageSize=200,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    out = []
    for folder in folders:
        q_files = (
            f"'{folder['id']}' in parents and "
            f"mimeType != '{FOLDER_MIME}' and trashed = false"
        )
        files = svc.files().list(
            q=q_files,
            fields="files(id, name, size, createdTime)",
            pageSize=200,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        for f in files:
            out.append({
                "subfolder": folder["name"],
                "id": f["id"],
                "name": f["name"],
                "size": int(f.get("size", 0)),
                "createdTime": f.get("createdTime"),
            })
    for entry in out:
        size_mb = entry["size"] / 1_048_576
        print(
            f"{entry['subfolder']}/{entry['name']:40s}  "
            f"{size_mb:8.2f} MB  {entry['createdTime']}  id={entry['id']}"
        )
    return out


def prune(keep_days: Optional[int] = None) -> int:
    """Delete subfolders whose name (YYYY-MM-DD) is older than `keep_days`."""
    keep = keep_days if keep_days is not None else RETENTION_DAYS
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep)
    log.info("Pruning Drive subfolders older than %s (keep %d days)", cutoff, keep)

    svc = _build_service()
    q = (
        f"'{PARENT_FOLDER_ID}' in parents and "
        f"mimeType = '{FOLDER_MIME}' and trashed = false"
    )
    folders = svc.files().list(
        q=q, fields="files(id, name)", pageSize=200,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])

    deleted = 0
    for folder in folders:
        name = folder["name"]
        try:
            folder_date = datetime.strptime(name, "%Y-%m-%d").date()
        except ValueError:
            log.debug("Skipping non-date folder: %s", name)
            continue
        if folder_date < cutoff:
            log.info("  deleting %s (id=%s)", name, folder["id"])
            svc.files().delete(
                fileId=folder["id"], supportsAllDrives=True
            ).execute()
            deleted += 1
    log.info("Prune done. Deleted %d folder(s).", deleted)
    return deleted


# ==================================================================== cli
def _usage_and_exit():
    print(__doc__)
    raise SystemExit(1)


def main(argv: list) -> None:
    if len(argv) < 2:
        _usage_and_exit()
    cmd = argv[1].lower()

    if cmd == "upload":
        if len(argv) < 3:
            _usage_and_exit()
        local = argv[2]
        sub = argv[3] if len(argv) > 3 else None
        upload(local, sub)
    elif cmd == "prune":
        keep = int(argv[2]) if len(argv) > 2 else None
        prune(keep)
    elif cmd == "list":
        list_backups()
    elif cmd in ("--help", "-h", "help"):
        _usage_and_exit()
    else:
        log.error("Unknown command: %s", cmd)
        _usage_and_exit()


if __name__ == "__main__":
    main(sys.argv)
