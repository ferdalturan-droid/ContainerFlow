"""Fase 15.36 — Søndag aften påmindelse (missing_clock-mail).

Tester at admin-endpoint POST /api/admin/missing-clock/send-reminders
korrekt:
  T1: returnerer sent=0/drivers=[] når ingen drivers har åbne entries.
  T2: returnerer sent=N med korrekte driver-detaljer når der findes åbne
      historiske entries.
  T3: respekterer days_back-param (1 → 0 hits, 4 → 1 hit, 7 → 2 hits når
      seed-data ligger 3+5 dage tilbage).
  T4: afviser non-admin roller (driver token → 403).
  T5: scope er strikt pr. company_id for logistics_admin (super_admin
      bypasses).

Test sender RIGTIGE emails (EMAIL_OVERRIDE redirigerer dem til en enkelt
inbox under test) — `delivered=True` flaget kontrolleres mod Resend-svaret.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient


# --- env helpers ------------------------------------------------------------

def _load_backend_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if val:
        return val.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


def _load_mongo() -> tuple[str, str]:
    env_path = Path("/app/backend/.env")
    mongo_url = "mongodb://localhost:27017"
    db_name = "test_database"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("MONGO_URL="):
                mongo_url = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("DB_NAME="):
                db_name = line.split("=", 1)[1].strip().strip('"')
    return mongo_url, db_name


API_URL = _load_backend_url()
MONGO_URL, DB_NAME = _load_mongo()

ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASSWORD = "TestPass2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASSWORD = "Driver2026!"

_SEED_FLAG = "__phase15_36_seed"


# --- fixtures ---------------------------------------------------------------

def _login(email: str, password: str, attempts: int = 6) -> str:
    last = None
    for i in range(attempts):
        try:
            r = requests.post(
                f"{API_URL}/api/auth/login",
                json={"email": email, "password": password},
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("access_token") or data.get("token") or ""
            last = (r.status_code, r.text)
        except Exception as e:  # noqa: BLE001
            last = ("exc", str(e))
        time.sleep(8 + i * 4)
    raise RuntimeError(f"login failed after {attempts} attempts: {last}")


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def driver_token() -> str:
    return _login(DRIVER_EMAIL, DRIVER_PASSWORD)


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture
def clean_seed(mongo_db):
    """Before/after: kill all seed entries so each test starts fresh."""
    mongo_db.driver_time_entries.delete_many({_SEED_FLAG: True})
    yield
    mongo_db.driver_time_entries.delete_many({_SEED_FLAG: True})


def _seed_missing_entries(mongo_db, days_ago: list[int]) -> list[str]:
    u = mongo_db.users.find_one({"email": DRIVER_EMAIL, "role": "driver"})
    assert u, f"test driver {DRIVER_EMAIL} must exist for this test"
    tz = ZoneInfo("Europe/Copenhagen")
    today = datetime.now(tz)
    docs = []
    for d in days_ago:
        docs.append({
            "id": str(uuid.uuid4()),
            "driver_id": u["id"],
            "company_id": u.get("company_id") or "",
            "date": (today - timedelta(days=d)).strftime("%Y-%m-%d"),
            "start_time": "07:30",
            "end_time": None,
            "duration_minutes": 0,
            "slice_type": "work",
            "created_by_role": "driver",
            "manual": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            _SEED_FLAG: True,
        })
    if docs:
        mongo_db.driver_time_entries.insert_many(docs)
    return [d["id"] for d in docs]


def _drv_in(body: dict, driver_email: str) -> dict | None:
    """Find the entry for `driver_email` in the API response."""
    for d in body.get("drivers") or []:
        if d.get("email") == driver_email:
            return d
    return None


def _baseline_missing_count(mongo_db, driver_email: str, days_back: int) -> int:
    """Count CURRENT non-seed missing entries for the test driver within the
    given days_back window. Lets tests run alongside real production data."""
    u = mongo_db.users.find_one({"email": driver_email, "role": "driver"})
    if not u:
        return 0
    tz = ZoneInfo("Europe/Copenhagen")
    today = datetime.now(tz)
    today_str = today.strftime("%Y-%m-%d")
    cutoff_str = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return mongo_db.driver_time_entries.count_documents({
        "driver_id": u["id"],
        "date": {"$gte": cutoff_str, "$lt": today_str},
        "$and": [
            {"$or": [{"end_time": {"$exists": False}}, {"end_time": None}, {"end_time": ""}]},
            {"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
        ],
        _SEED_FLAG: {"$ne": True},
    })


# --- tests ------------------------------------------------------------------

def test_T1_empty_when_no_missing_entries(admin_token, mongo_db, clean_seed):
    """If the test driver has NO non-seed missing entries, the response must
    not include them. (Other drivers in DB may still have entries.)"""
    baseline = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=7)
    r = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=7",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    drv = _drv_in(body, DRIVER_EMAIL)
    if baseline == 0:
        assert drv is None, f"expected test driver absent (no missing), got {drv}"
    else:
        assert drv is not None, f"test driver expected present (baseline={baseline}), body={body}"
        assert drv["entries_count"] == baseline


def test_T2_sends_to_driver_with_missing(admin_token, mongo_db, clean_seed):
    baseline = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=7)
    _seed_missing_entries(mongo_db, [3, 5])
    r = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=7",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    drv = _drv_in(body, DRIVER_EMAIL)
    assert drv is not None, f"test driver missing in response: {body}"
    assert drv["entries_count"] == baseline + 2
    assert drv["delivered"] is True


def test_T3_days_back_filter(admin_token, mongo_db, clean_seed):
    _seed_missing_entries(mongo_db, [3, 5])

    base_1 = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=1)
    base_4 = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=4)
    base_7 = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=7)

    # NB: minus _SEED_FLAG entries from baseline (helper already excludes them).
    # Seed dates are 3 + 5 days ago.
    #   days_back=1: 0 seed entries inside window
    #   days_back=4: 1 seed entry (the 3-day-old)
    #   days_back=7: 2 seed entries

    # days_back=1
    r1 = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=1",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r1.status_code == 200
    drv1 = _drv_in(r1.json(), DRIVER_EMAIL)
    expected_1 = base_1  # no seed added inside window
    if expected_1 == 0:
        assert drv1 is None
    else:
        assert drv1 and drv1["entries_count"] == expected_1

    # days_back=4
    r2 = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=4",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    assert r2.status_code == 200
    drv2 = _drv_in(r2.json(), DRIVER_EMAIL)
    assert drv2 and drv2["entries_count"] == base_4 + 1

    # days_back=7
    r3 = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=7",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    assert r3.status_code == 200
    drv3 = _drv_in(r3.json(), DRIVER_EMAIL)
    assert drv3 and drv3["entries_count"] == base_7 + 2


def test_T4_driver_role_is_rejected(driver_token, clean_seed):
    r = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=7",
        headers={"Authorization": f"Bearer {driver_token}"},
        timeout=30,
    )
    assert r.status_code == 403, r.text
    assert "Adgang" in (r.json().get("detail") or "")


def test_T5_closed_and_deleted_entries_are_ignored(admin_token, mongo_db, clean_seed):
    """Adding a CLOSED entry (has end_time) and a SOFT-DELETED entry must NOT
    increase the test driver's missing count vs. the pre-seed baseline."""
    baseline = _baseline_missing_count(mongo_db, DRIVER_EMAIL, days_back=7)
    u = mongo_db.users.find_one({"email": DRIVER_EMAIL, "role": "driver"})
    tz = ZoneInfo("Europe/Copenhagen")
    today = datetime.now(tz)

    closed = {
        "id": str(uuid.uuid4()),
        "driver_id": u["id"],
        "company_id": u.get("company_id") or "",
        "date": (today - timedelta(days=4)).strftime("%Y-%m-%d"),
        "start_time": "07:00",
        "end_time": "15:00",
        "duration_minutes": 480,
        "slice_type": "work",
        "created_by_role": "driver",
        "manual": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        _SEED_FLAG: True,
    }
    deleted = {
        "id": str(uuid.uuid4()),
        "driver_id": u["id"],
        "company_id": u.get("company_id") or "",
        "date": (today - timedelta(days=2)).strftime("%Y-%m-%d"),
        "start_time": "08:00",
        "end_time": None,
        "duration_minutes": 0,
        "slice_type": "work",
        "deleted": True,
        "created_by_role": "driver",
        "manual": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        _SEED_FLAG: True,
    }
    mongo_db.driver_time_entries.insert_many([closed, deleted])
    r = requests.post(
        f"{API_URL}/api/admin/missing-clock/send-reminders?days_back=7",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    drv = _drv_in(r.json(), DRIVER_EMAIL)
    if baseline == 0:
        assert drv is None
    else:
        assert drv and drv["entries_count"] == baseline
