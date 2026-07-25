#!/usr/bin/env python3
"""
ContainerFlow — download a MongoDB backup archive from Google Drive.

Standalone helper (no FastAPI imports) used by restore_mongo.sh to fetch
an archive before invoking mongorestore. Can also be used manually.

USAGE
-----
    python3 gdrive_download.py latest [<dest_path>]
        # Download the newest archive across all subfolders.

    python3 gdrive_download.py by-id <file_id> <dest_path>
        # Download a specific Drive file by its file ID.

    python3 gdrive_download.py by-date <YYYY-MM-DD> <dest_path>
        # Download the newest archive inside that date subfolder.

Loads config from /app/scripts/.env (same vars as gdrive_uploader.py).
"""

from __future__ import annotations

import io
import os
import sys
import logging
from typing import Optional

# Reuse the same loader / config from gdrive_uploader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdrive_uploader import _build_service, PARENT_FOLDER_ID, FOLDER_MIME  # noqa: E402

logging.basicConfig(
    level=os.environ.get("GDRIVE_LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s gdrive-dl: %(message)s",
    datefmt="%F %T",
)
log = logging.getLogger("gdrive-dl")


def _download_file(svc, file_id: str, dest: str) -> str:
    from googleapiclient.http import MediaIoBaseDownload

    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    last_pct = -1
    with io.FileIO(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct != last_pct and pct % 10 == 0:
                    log.info("  ...%d%%", pct)
                    last_pct = pct
    log.info("Downloaded → %s", dest)
    return dest


def _newest_in_folder(svc, folder_id: str) -> Optional[dict]:
    res = svc.files().list(
        q=f"'{folder_id}' in parents and mimeType != '{FOLDER_MIME}' and trashed = false",
        fields="files(id, name, createdTime, size)",
        orderBy="createdTime desc",
        pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    return res[0] if res else None


def download_latest(dest: Optional[str] = None) -> str:
    svc = _build_service()
    # find the newest subfolder by name (YYYY-MM-DD sorts lexicographically)
    folders = svc.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and mimeType = '{FOLDER_MIME}' and trashed = false",
        fields="files(id, name)",
        orderBy="name desc",
        pageSize=200,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    if not folders:
        log.error("No subfolders found in parent %s", PARENT_FOLDER_ID)
        raise SystemExit(6)

    for folder in folders:
        newest = _newest_in_folder(svc, folder["id"])
        if newest:
            dest_path = dest or f"/tmp/{newest['name']}"
            log.info(
                "Newest archive: %s/%s (%s)",
                folder["name"], newest["name"], newest["createdTime"],
            )
            return _download_file(svc, newest["id"], dest_path)
    log.error("No archive files found in any subfolder")
    raise SystemExit(7)


def download_by_date(date_str: str, dest: str) -> str:
    svc = _build_service()
    folders = svc.files().list(
        q=(
            f"'{PARENT_FOLDER_ID}' in parents and "
            f"name = '{date_str}' and "
            f"mimeType = '{FOLDER_MIME}' and trashed = false"
        ),
        fields="files(id, name)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    if not folders:
        log.error("No subfolder named '%s'", date_str)
        raise SystemExit(8)
    newest = _newest_in_folder(svc, folders[0]["id"])
    if not newest:
        log.error("Subfolder '%s' is empty", date_str)
        raise SystemExit(9)
    log.info("Downloading %s/%s", date_str, newest["name"])
    return _download_file(svc, newest["id"], dest)


def download_by_id(file_id: str, dest: str) -> str:
    return _download_file(_build_service(), file_id, dest)


def main(argv: list) -> None:
    if len(argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd = argv[1].lower()
    if cmd == "latest":
        dest = argv[2] if len(argv) > 2 else None
        download_latest(dest)
    elif cmd == "by-id":
        if len(argv) < 4:
            print(__doc__)
            raise SystemExit(1)
        download_by_id(argv[2], argv[3])
    elif cmd == "by-date":
        if len(argv) < 4:
            print(__doc__)
            raise SystemExit(1)
        download_by_date(argv[2], argv[3])
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv)
