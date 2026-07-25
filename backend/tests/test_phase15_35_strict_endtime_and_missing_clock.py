"""Phase 15.35 — Strict end>start validation + missing-clock detection.

Tests:
  T1: POST /driver/time-entries with end<start → 400
  T2: POST /driver/time-entries/manual-punch (UD) with time before open IND → 400
  T3: PATCH /driver/time-entries/{id} with end<start → 400
  T4: PATCH /admin/time-entries/{id} with end<start → 400
  T5: missing_clock=true on YESTERDAY's open entry; missing_clock_count>0
  T6: missing_only=true filter returns ONLY drivers with missing_clock_count>0
  T7: Pairing UD on same date removes missing_clock flag
  T8: TODAY's open entry has missing_clock=false (regression)
  T9: _compute_duration_minutes returns -1 when end<=start (verified via 400 endpoint behavior)
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

def _resolve_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        # Fallback: read frontend/.env
        try:
            with open("/app/frontend/.env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE_URL = _resolve_base_url()
assert BASE_URL.startswith("http"), f"BASE_URL invalid: {BASE_URL!r}"
ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASSWORD = "TestPass2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASSWORD = "Driver2026!"
DRIVER_ID = "cbd13b47-0649-4bd9-a79b-9e6d9da7e95a"


def _login(email: str, password: str) -> str:
    """Login with retry on 429 rate limit."""
    for attempt in range(4):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(8 + attempt * 4)
            continue
        pytest.fail(f"Login failed for {email}: {r.status_code} {r.text}")
    pytest.fail(f"Login rate-limited persistently for {email}")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def driver_token():
    time.sleep(7)  # avoid rate limit between admin and driver login
    return _login(DRIVER_EMAIL, DRIVER_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def driver_headers(driver_token):
    return {"Authorization": f"Bearer {driver_token}", "Content-Type": "application/json"}


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _yesterday():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _hard_delete(admin_headers, entry_id):
    try:
        requests.delete(f"{BASE_URL}/api/admin/time-entries/{entry_id}?hard=true",
                        headers=admin_headers, timeout=10)
    except Exception:
        pass


# ─── T1: POST /driver/time-entries periode with end<start ────────────────
def test_t1_post_period_end_before_start_returns_400(admin_headers):
    r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                      headers=admin_headers,
                      json={
                          "driver_id": DRIVER_ID,
                          "date": _today(),
                          "start_time": "12:00",
                          "end_time": "10:00",
                          "reason": "TEST_T1_end_before_start",
                      }, timeout=15)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    assert "starttidspunkt" in r.text.lower() or "efter" in r.text.lower(), \
        f"Expected Danish error mentioning start/efter: {r.text}"


# ─── T2: manual-punch UD with time before open IND ───────────────────────
def test_t2_manual_punch_ud_before_ind_returns_400(admin_headers):
    today = _today()
    # First, ensure clean state: hard-delete any existing entries for driver today.
    r_list = requests.get(f"{BASE_URL}/api/admin/time-entries?date={today}",
                          headers=admin_headers, timeout=15)
    if r_list.status_code == 200:
        for drv in r_list.json():
            if drv.get("driver_id") == DRIVER_ID:
                for e in drv.get("entries", []):
                    _hard_delete(admin_headers, e.get("id"))

    # Create an open IND at 18:00 — use a future-safe past-time approach.
    # Choose a punch time of 06:00 (well in the past for today). But the test
    # requires "IND=18:00 and UD payload=17:00". If 18:00 is in the future
    # locally, manual-punch IND will reject with future-time. So instead use
    # YESTERDAY where 18:00 is definitively past.
    yest = _yesterday()
    r_ind = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                          headers=admin_headers,
                          json={"driver_id": DRIVER_ID, "type": "ind",
                                "date": yest, "time": "18:00",
                                "reason": "TEST_T2_ind"},
                          timeout=15)
    assert r_ind.status_code == 200, f"Seed IND failed: {r_ind.status_code} {r_ind.text}"
    ind_id = r_ind.json().get("id")

    # Now try UD at 17:00 (before IND 18:00)
    r_ud = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                         headers=admin_headers,
                         json={"driver_id": DRIVER_ID, "type": "ud",
                               "date": yest, "time": "17:00",
                               "reason": "TEST_T2_ud"},
                         timeout=15)
    assert r_ud.status_code == 400, f"Expected 400, got {r_ud.status_code}: {r_ud.text}"
    assert "17:00" in r_ud.text and "18:00" in r_ud.text, \
        f"Error should mention both times: {r_ud.text}"

    # cleanup
    _hard_delete(admin_headers, ind_id)


# ─── T3: PATCH /driver/time-entries (driver) with end<start ──────────────
def test_t3_driver_patch_end_before_start_returns_400(admin_headers, driver_headers):
    today = _today()
    # Use a punch IND in the past (e.g., 06:00), close it via UD at 07:00, so
    # driver owns a non-admin entry that they can patch.
    # Cleanup first
    r_list = requests.get(f"{BASE_URL}/api/admin/time-entries?date={today}",
                          headers=admin_headers, timeout=15)
    if r_list.status_code == 200:
        for drv in r_list.json():
            if drv.get("driver_id") == DRIVER_ID:
                for e in drv.get("entries", []):
                    _hard_delete(admin_headers, e.get("id"))

    # Driver creates own punch IND (so created_by_role='driver')
    r_ind = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                          headers=driver_headers,
                          json={"type": "ind", "date": today, "time": "06:00",
                                "reason": "TEST_T3"}, timeout=15)
    if r_ind.status_code != 200:
        pytest.skip(f"Driver IND seed failed: {r_ind.status_code} {r_ind.text}")
    entry_id = r_ind.json().get("id")

    # Close with UD at 07:00
    r_ud = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                         headers=driver_headers,
                         json={"type": "ud", "date": today, "time": "07:00",
                               "reason": "TEST_T3"}, timeout=15)
    assert r_ud.status_code == 200, f"UD failed: {r_ud.text}"

    # Now PATCH to set end<start
    r_patch = requests.patch(f"{BASE_URL}/api/driver/time-entries/{entry_id}",
                             headers=driver_headers,
                             json={"start_time": "12:00", "end_time": "10:00"},
                             timeout=15)
    assert r_patch.status_code == 400, f"Expected 400, got {r_patch.status_code}: {r_patch.text}"
    assert "starttidspunkt" in r_patch.text.lower() or "efter" in r_patch.text.lower(), \
        f"Danish error expected: {r_patch.text}"

    _hard_delete(admin_headers, entry_id)


# ─── T4: PATCH /admin/time-entries with end<start ────────────────────────
def test_t4_admin_patch_end_before_start_returns_400(admin_headers):
    today = _today()
    # Cleanup
    r_list = requests.get(f"{BASE_URL}/api/admin/time-entries?date={today}",
                          headers=admin_headers, timeout=15)
    if r_list.status_code == 200:
        for drv in r_list.json():
            if drv.get("driver_id") == DRIVER_ID:
                for e in drv.get("entries", []):
                    _hard_delete(admin_headers, e.get("id"))

    # Seed via admin period
    r_seed = requests.post(f"{BASE_URL}/api/driver/time-entries",
                           headers=admin_headers,
                           json={"driver_id": DRIVER_ID, "date": today,
                                 "start_time": "08:00", "end_time": "09:00",
                                 "reason": "TEST_T4"}, timeout=15)
    assert r_seed.status_code == 200, f"Seed failed: {r_seed.text}"
    entry_id = r_seed.json().get("id")

    r_patch = requests.patch(f"{BASE_URL}/api/admin/time-entries/{entry_id}",
                             headers=admin_headers,
                             json={"start_time": "12:00", "end_time": "10:00"},
                             timeout=15)
    assert r_patch.status_code == 400, f"Expected 400, got {r_patch.status_code}: {r_patch.text}"
    assert "starttidspunkt" in r_patch.text.lower() or "efter" in r_patch.text.lower(), \
        f"Danish error expected: {r_patch.text}"

    _hard_delete(admin_headers, entry_id)


# ─── T5+T6+T7+T8 missing-clock detection ─────────────────────────────────
def test_t5_t6_t7_t8_missing_clock_lifecycle(admin_headers):
    yest = _yesterday()
    today = _today()

    # Cleanup yesterday + today for driver
    for d in (yest, today):
        r_list = requests.get(f"{BASE_URL}/api/admin/time-entries?date={d}",
                              headers=admin_headers, timeout=15)
        if r_list.status_code == 200:
            for drv in r_list.json():
                if drv.get("driver_id") == DRIVER_ID:
                    for e in drv.get("entries", []):
                        _hard_delete(admin_headers, e.get("id"))

    # ── Seed: open IND yesterday at 22:00 (no UD)
    r_ind = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                          headers=admin_headers,
                          json={"driver_id": DRIVER_ID, "type": "ind",
                                "date": yest, "time": "22:00",
                                "reason": "TEST_T5_open_yesterday"},
                          timeout=15)
    assert r_ind.status_code == 200, f"Seed yesterday IND failed: {r_ind.text}"
    yest_entry_id = r_ind.json().get("id")

    # ── T5: GET yesterday → missing_clock=true on entry, count>=1
    r_y = requests.get(f"{BASE_URL}/api/admin/time-entries?date={yest}",
                       headers=admin_headers, timeout=15)
    assert r_y.status_code == 200
    drivers_y = r_y.json()
    test_drv = next((d for d in drivers_y if d.get("driver_id") == DRIVER_ID), None)
    assert test_drv is not None, "Test driver not in yesterday list"
    assert test_drv.get("missing_clock_count", 0) >= 1, \
        f"Expected missing_clock_count>=1, got {test_drv.get('missing_clock_count')}"
    flagged = [e for e in test_drv.get("entries", []) if e.get("missing_clock") is True]
    assert len(flagged) >= 1, "Expected at least one entry flagged missing_clock=true"

    # ── T6: missing_only=true returns ONLY drivers with missing_clock
    r_filter = requests.get(
        f"{BASE_URL}/api/admin/time-entries?date={yest}&missing_only=true",
        headers=admin_headers, timeout=15)
    assert r_filter.status_code == 200
    filtered = r_filter.json()
    for d in filtered:
        assert d.get("missing_clock_count", 0) > 0, \
            f"Driver {d.get('driver_name')} in missing_only list but count=0"
    assert any(d.get("driver_id") == DRIVER_ID for d in filtered), \
        "Test driver should be in missing_only filtered list"

    # ── T8: TODAY's open entry should NOT be missing_clock
    r_today_ind = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                                headers=admin_headers,
                                json={"driver_id": DRIVER_ID, "type": "ind",
                                      "date": today, "time": "05:00",
                                      "reason": "TEST_T8_open_today"},
                                timeout=15)
    assert r_today_ind.status_code == 200, f"Today IND seed failed: {r_today_ind.text}"
    today_entry_id = r_today_ind.json().get("id")

    r_t = requests.get(f"{BASE_URL}/api/admin/time-entries?date={today}",
                       headers=admin_headers, timeout=15)
    assert r_t.status_code == 200
    drv_today = next((d for d in r_t.json() if d.get("driver_id") == DRIVER_ID), None)
    assert drv_today is not None
    today_open = [e for e in drv_today.get("entries", []) if not e.get("end_time")]
    assert len(today_open) >= 1
    assert all(not e.get("missing_clock") for e in today_open), \
        "Today's open entry must NOT be flagged missing_clock"

    # ── T7: Pair UD on yesterday → missing_clock removed on next GET
    # Use a UD time after 22:00, e.g. 23:30
    r_ud = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                         headers=admin_headers,
                         json={"driver_id": DRIVER_ID, "type": "ud",
                               "date": yest, "time": "23:30",
                               "reason": "TEST_T7_pair"}, timeout=15)
    assert r_ud.status_code == 200, f"Pair UD failed: {r_ud.text}"

    r_y2 = requests.get(f"{BASE_URL}/api/admin/time-entries?date={yest}",
                        headers=admin_headers, timeout=15)
    assert r_y2.status_code == 200
    drv_y2 = next((d for d in r_y2.json() if d.get("driver_id") == DRIVER_ID), None)
    assert drv_y2 is not None
    paired = [e for e in drv_y2.get("entries", []) if e.get("id") == yest_entry_id]
    assert len(paired) == 1
    assert paired[0].get("end_time"), "Entry should now be closed (have end_time)"
    assert not paired[0].get("missing_clock"), \
        "Entry should no longer be missing_clock after pairing"

    # cleanup
    _hard_delete(admin_headers, yest_entry_id)
    _hard_delete(admin_headers, today_entry_id)
