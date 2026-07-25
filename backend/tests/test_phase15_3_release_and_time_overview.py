"""
Phase 15.3 (2026-06-19) — Admin release clears on_way; admin time-entries
endpoint returns per-driver timeline.

Tests:
- T1: Admin frigør en tildelt tur via driver_id='' → backend rydder også
       on_way + claim. Sikrer at andre chauffører ikke ser en "PÅ VEJ"
       orphan-tur efter admin har frigjort den.
- T2: GET /api/admin/time-entries?date=... returnerer liste med entries pr
       chauffør for dagen — role-gated til LA/SA.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def la_token():
    return _login("ilkdistadmin@gmail.com", "TestPass2026!")


@pytest.fixture(scope="module")
def driver_token():
    return _login("test2", "TestC2026!")


@pytest.fixture(scope="module")
def driver_id(driver_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {driver_token}"}, timeout=15)
    return r.json().get("id") or r.json().get("sub")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# T1 — Admin release clears on_way + claim
def test_admin_release_clears_on_way_and_claim(la_token, driver_token, driver_id):
    body = {"plads": "DBG-release-15-3", "facility": "X", "container": "RLS1",
            "fraction": "RLSFRAC", "tour_type": "normal"}
    r = requests.post(f"{API}/tours", headers=_h(la_token), json=body, timeout=15)
    assert r.status_code == 200
    tid = r.json()["id"]
    try:
        # LA pre-assigns
        requests.put(f"{API}/tours/{tid}", headers=_h(la_token),
            json={"driver_id": driver_id}, timeout=15)
        # Driver starts (on_way=true, claims it)
        r = requests.put(f"{API}/tours/{tid}", headers=_h(driver_token),
            json={"on_way": True, "on_way_time": "08:00",
                  "claimed_by": "testc", "claimed_by_id": driver_id}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("on_way") is True

        # LA frigør via driver_id=""
        r = requests.put(f"{API}/tours/{tid}", headers=_h(la_token),
            json={"driver_id": ""}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Verify ALL claim/on_way state is cleared
        assert body.get("driver_id") == "", f"driver_id not cleared: {body.get('driver_id')}"
        assert body.get("on_way") is False, f"on_way not cleared: {body.get('on_way')}"
        assert body.get("claimed_by") == "", f"claimed_by not cleared: {body.get('claimed_by')}"
        assert body.get("claimed_by_id") == "", f"claimed_by_id not cleared: {body.get('claimed_by_id')}"
        assert body.get("assigned_by_name") == "", "assigned_by_name not cleared"
    finally:
        requests.delete(f"{API}/tours/{tid}", headers=_h(la_token), timeout=10)


# T2 — Admin time-entries endpoint
def test_admin_time_entries_endpoint(la_token, driver_token):
    from datetime import datetime as _dt
    import zoneinfo
    DK = zoneinfo.ZoneInfo("Europe/Copenhagen")
    today = _dt.now(DK).strftime("%Y-%m-%d")

    # LA can fetch
    r = requests.get(f"{API}/admin/time-entries?date={today}", headers=_h(la_token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    # Each row has expected keys
    for row in data:
        assert "driver_id" in row
        assert "driver_name" in row
        assert "entries" in row
        assert "total_minutes" in row
        assert "has_open" in row
        assert "entries_count" in row

    # Driver may NOT call admin endpoint
    r = requests.get(f"{API}/admin/time-entries?date={today}", headers=_h(driver_token), timeout=15)
    assert r.status_code == 403, f"Driver should get 403, got {r.status_code}: {r.text}"
