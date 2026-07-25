"""Fase 15.48 — Når chaufføren redigerer sin egen time slice (uanset om den
oprindeligt var automatisk eller manuel), skal entry'en auto-markeres som
"manuel" så rapporter og audit kan skelne brugerens manuelle indgriben."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _backend_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if val:
        return val.rstrip("/")
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


def _mongo():
    env = Path("/app/backend/.env")
    url = "mongodb://localhost:27017"
    db = "test_database"
    for line in env.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("DB_NAME="):
            db = line.split("=", 1)[1].strip().strip('"')
    return url, db


API_URL = _backend_url()
MONGO_URL, DB_NAME = _mongo()
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASSWORD = "Driver2026!"


def _login(email, password, attempts=4):
    last = None
    for i in range(attempts):
        try:
            r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
            if r.status_code == 200:
                d = r.json()
                return d.get("token") or d.get("access_token") or ""
            last = (r.status_code, r.text)
        except Exception as e:
            last = ("exc", str(e))
        time.sleep(5 + i * 3)
    raise RuntimeError(f"login failed: {last}")


@pytest.fixture(scope="module")
def driver_ctx():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    user = db.users.find_one({"email": DRIVER_EMAIL})
    assert user, f"missing test driver {DRIVER_EMAIL}"
    token = _login(DRIVER_EMAIL, DRIVER_PASSWORD)
    yield {"db": db, "user": user, "token": token}
    client.close()


_SEED_KEY = "__phase15_48_seed__"


@pytest.fixture(autouse=True)
def cleanup(driver_ctx):
    driver_ctx["db"].driver_time_entries.delete_many({_SEED_KEY: True})
    yield
    driver_ctx["db"].driver_time_entries.delete_many({_SEED_KEY: True})


def _seed_auto_entry(driver_ctx, *, end_time="08:00"):
    db = driver_ctx["db"]; user = driver_ctx["user"]
    eid = str(uuid.uuid4())
    db.driver_time_entries.insert_one({
        "id": eid,
        "driver_id": user["id"],
        "driver_name": user.get("name", "Test"),
        "date": "2026-06-22",
        "start_time": "07:00",
        "end_time": end_time,
        "duration_minutes": 60 if end_time else 0,
        "slice_type": "work",
        "manual": False,
        "manual_type": None,
        "deleted": False,
        "created_by_role": "driver",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "company_id": user.get("company_id"),
        _SEED_KEY: True,
    })
    return eid


def test_T1_edit_auto_entry_marks_manual_period(driver_ctx):
    """Driver redigerer en AUTO-entry med både start + slut → manual=True,
    manual_type='period'."""
    eid = _seed_auto_entry(driver_ctx)
    r = requests.patch(
        f"{API_URL}/api/driver/time-entries/{eid}",
        headers={"Authorization": f"Bearer {driver_ctx['token']}"},
        json={"date": "2026-06-22", "start_time": "07:30", "end_time": "08:30",
              "slice_type": "work", "reason": "Tilrettet"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("manual") is True
    assert d.get("manual_type") == "period"
    assert d.get("edited_by_driver") is True
    assert d.get("start_time") == "07:30"
    assert d.get("end_time") == "08:30"
    assert d.get("reason") == "Tilrettet"


def test_T2_edit_auto_entry_open_slice_marks_punch_ind(driver_ctx):
    """Driver redigerer en åben slice (ingen end_time) → manual=True,
    manual_type='punch_ind'."""
    eid = _seed_auto_entry(driver_ctx, end_time="")
    r = requests.patch(
        f"{API_URL}/api/driver/time-entries/{eid}",
        headers={"Authorization": f"Bearer {driver_ctx['token']}"},
        json={"date": "2026-06-22", "start_time": "06:45", "end_time": "",
              "slice_type": "work", "reason": ""},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("manual") is True
    assert d.get("manual_type") == "punch_ind"
    assert d.get("end_time") == ""


def test_T3_edit_manual_entry_stays_manual(driver_ctx):
    """Eksisterende manuel entry skal forblive manuel efter edit."""
    db = driver_ctx["db"]; user = driver_ctx["user"]
    eid = str(uuid.uuid4())
    db.driver_time_entries.insert_one({
        "id": eid,
        "driver_id": user["id"],
        "driver_name": user.get("name", "Test"),
        "date": "2026-06-22",
        "start_time": "09:00",
        "end_time": "10:00",
        "duration_minutes": 60,
        "slice_type": "pause",
        "manual": True,
        "manual_type": "period",
        "deleted": False,
        "created_by_role": "driver",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "company_id": user.get("company_id"),
        _SEED_KEY: True,
    })
    r = requests.patch(
        f"{API_URL}/api/driver/time-entries/{eid}",
        headers={"Authorization": f"Bearer {driver_ctx['token']}"},
        json={"date": "2026-06-22", "start_time": "09:15", "end_time": "10:15",
              "slice_type": "pause", "reason": "Justeret pause"},
        timeout=15,
    )
    assert r.status_code == 200
    d = r.json()
    assert d.get("manual") is True
    assert d.get("manual_type") == "period"
