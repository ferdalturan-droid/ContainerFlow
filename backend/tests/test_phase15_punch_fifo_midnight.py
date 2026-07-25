"""
Phase 15.1 (2026-06-19) — Punch FIFO pairing + midnight block.

Tests:
- T1: When multiple open IN entries exist (legacy data) and OUT comes in,
       the OLDEST open IN is matched first (FIFO via sort=[("start_time",1)]).
- T2: When the only open IN is on a PRIOR date and driver tries to OUT
       today → 409 with message containing "Brug Manuel tidsregistrering".

We use direct MongoDB writes to simulate the multi-open scenario the
backend itself blocks (1 open at a time), which validates the FIFO sort
behaviour anyway.
"""
import os
import asyncio
import uuid
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

DRIVER_LOGIN = "test2"
DRIVER_PASS = "TestC2026!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def driver_token():
    return _login(DRIVER_LOGIN, DRIVER_PASS)


@pytest.fixture(scope="module")
def driver_info(driver_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {driver_token}"}, timeout=15)
    r.raise_for_status()
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _clear_today_entries(driver_id, date_str):
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    await db.driver_time_entries.delete_many({"driver_id": driver_id, "date": date_str})
    cli.close()


async def _insert_open_entry(driver_id, date_str, start_time):
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    eid = str(uuid.uuid4())
    await db.driver_time_entries.insert_one({
        "id": eid, "driver_id": driver_id, "date": date_str,
        "start_time": start_time, "end_time": "", "duration_minutes": 0,
        "manual": False, "reason": "",
    })
    cli.close()
    return eid


def test_fifo_pairing_picks_oldest_open_in(driver_token, driver_info):
    """Insert 2 OPEN IN entries (08:00 and 10:00) directly into Mongo, then
    POST OUT at 12:00 — the 08:00 entry must be closed first (FIFO)."""
    from datetime import datetime as _dt, timezone as _tz
    import zoneinfo
    DK = zoneinfo.ZoneInfo("Europe/Copenhagen")
    today = _dt.now(DK).strftime("%Y-%m-%d")
    driver_id = driver_info.get("id") or driver_info.get("sub")

    asyncio.run(_clear_today_entries(driver_id, today))
    eid_a = asyncio.run(_insert_open_entry(driver_id, today, "08:00"))
    eid_b = asyncio.run(_insert_open_entry(driver_id, today, "10:00"))

    try:
        r = requests.post(f"{API}/driver/time-entries/punch",
            json={"type": "ud", "date": today, "time": "12:00"},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # The closed entry MUST be the 08:00 one (FIFO)
        assert body["start_time"] == "08:00", f"Expected 08:00 closed first (FIFO), got {body}"
        assert body["end_time"] == "12:00"
        # duration = 240 min
        assert body["duration_minutes"] == 240
    finally:
        asyncio.run(_clear_today_entries(driver_id, today))


def test_midnight_block_redirects_to_manuel(driver_token, driver_info):
    """Insert an open IN for YESTERDAY, then try OUT for TODAY — must 409 with
    'Brug Manuel tidsregistrering' text."""
    from datetime import datetime as _dt, timedelta as _td
    import zoneinfo
    DK = zoneinfo.ZoneInfo("Europe/Copenhagen")
    today = _dt.now(DK).strftime("%Y-%m-%d")
    yesterday = (_dt.now(DK) - _td(days=1)).strftime("%Y-%m-%d")
    driver_id = driver_info.get("id") or driver_info.get("sub")

    asyncio.run(_clear_today_entries(driver_id, today))
    asyncio.run(_clear_today_entries(driver_id, yesterday))
    asyncio.run(_insert_open_entry(driver_id, yesterday, "22:00"))

    try:
        r = requests.post(f"{API}/driver/time-entries/punch",
            json={"type": "ud", "date": today, "time": "01:00"},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Brug Manuel" in detail or "manuel" in detail.lower(), (
            f"Expected midnight-block message, got: {detail}"
        )
    finally:
        asyncio.run(_clear_today_entries(driver_id, today))
        asyncio.run(_clear_today_entries(driver_id, yesterday))
