"""Fase 15.28 — Backend tests
- /api/company/punch-reason-settings (any auth user)
- /api/company/payroll-settings (admin-only, must include require_* fields)
- /api/driver/time-entries/manual-punch  (driver + admin variations, FIFO, reason)
- /api/driver/time-entries (admin period creation, driver 403)
- /api/admin/time-entries?date=...  (per-driver structure)
"""
import os
import time
import uuid
import pytest
import requests

_url = os.environ.get("REACT_APP_BACKEND_URL")
if not _url:
    # Fall back to reading from frontend/.env when running tests directly
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    _url = _line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
if not _url:
    raise RuntimeError("REACT_APP_BACKEND_URL not set")
BASE = _url.rstrip("/")
ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASS = "TestPass2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASS = "Driver2026!"
TEST_DRIVER_ID = "cbd13b47-0649-4bd9-a79b-9e6d9da7e95a"


def _login(email, password, retries=4):
    for i in range(retries):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            return r.json().get("token")
        # rate-limited — wait
        time.sleep(6)
    pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def driver_token():
    time.sleep(6)
    return _login(DRIVER_EMAIL, DRIVER_PASS)


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def driver_h(driver_token):
    return {"Authorization": f"Bearer {driver_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def reset_settings_at_end(admin_h):
    yield
    # ensure both flags off after suite to not affect manual tests
    try:
        requests.patch(f"{BASE}/api/company/payroll-settings",
                       json={"require_driver_punch_reason": False,
                             "require_admin_punch_reason": False},
                       headers=admin_h, timeout=15)
    except Exception:
        pass


# ── 1. Settings endpoints ────────────────────────────────────────────────────
class TestPunchReasonSettings:
    def test_get_punch_reason_settings_admin(self, admin_h):
        r = requests.get(f"{BASE}/api/company/punch-reason-settings", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "require_driver_punch_reason" in data
        assert "require_admin_punch_reason" in data
        assert isinstance(data["require_driver_punch_reason"], bool)
        assert isinstance(data["require_admin_punch_reason"], bool)

    def test_get_punch_reason_settings_driver(self, driver_h):
        r = requests.get(f"{BASE}/api/company/punch-reason-settings", headers=driver_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "require_driver_punch_reason" in data
        assert "require_admin_punch_reason" in data

    def test_get_payroll_settings_includes_reason_fields(self, admin_h):
        r = requests.get(f"{BASE}/api/company/payroll-settings", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "require_driver_punch_reason" in data
        assert "require_admin_punch_reason" in data
        assert "payroll_cycle_type" in data

    def test_patch_payroll_settings_partial_update_driver_flag(self, admin_h):
        # first read existing
        before = requests.get(f"{BASE}/api/company/payroll-settings", headers=admin_h, timeout=15).json()
        cycle_before = before.get("payroll_cycle_type")
        # set driver reason flag True
        r = requests.patch(f"{BASE}/api/company/payroll-settings",
                           json={"require_driver_punch_reason": True}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["require_driver_punch_reason"] is True
        # cycle untouched
        assert data["payroll_cycle_type"] == cycle_before
        # toggle off
        r2 = requests.patch(f"{BASE}/api/company/payroll-settings",
                            json={"require_driver_punch_reason": False}, headers=admin_h, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["require_driver_punch_reason"] is False

    def test_patch_payroll_settings_admin_flag(self, admin_h):
        r = requests.patch(f"{BASE}/api/company/payroll-settings",
                           json={"require_admin_punch_reason": True}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["require_admin_punch_reason"] is True
        r2 = requests.patch(f"{BASE}/api/company/payroll-settings",
                            json={"require_admin_punch_reason": False}, headers=admin_h, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["require_admin_punch_reason"] is False


# ── 2. Manual punch (admin & driver) ─────────────────────────────────────────
def _today():
    from datetime import date
    return date.today().isoformat()


def _cleanup_entries(admin_h, driver_id, date_iso):
    # use list endpoint to find entries
    r = requests.get(f"{BASE}/api/admin/time-entries?date={date_iso}", headers=admin_h, timeout=15)
    if r.status_code != 200:
        return
    for d in r.json():
        if d.get("driver_id") != driver_id:
            continue
        for e in d.get("entries", []):
            eid = e.get("id")
            if eid:
                requests.delete(f"{BASE}/api/admin/time-entries/{eid}", headers=admin_h, timeout=15)


class TestManualPunchAdmin:
    @pytest.fixture(autouse=True)
    def _cleanup(self, admin_h):
        _cleanup_entries(admin_h, TEST_DRIVER_ID, _today())
        yield
        _cleanup_entries(admin_h, TEST_DRIVER_ID, _today())

    def test_admin_manual_punch_ind_then_ud_pairs_fifo(self, admin_h):
        today = _today()
        # IND
        r1 = requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                           json={"driver_id": TEST_DRIVER_ID, "date": today,
                                 "time": "09:00", "type": "ind", "reason": "TEST_smoke_in"},
                           headers=admin_h, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["manual"] is True
        assert d1["manual_type"] == "punch_ind"
        assert d1["created_by_role"] == "logistics_admin"
        assert d1["start_time"] == "09:00"
        assert d1["end_time"] in ("", None)
        ind_id = d1["id"]

        # UD
        r2 = requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                           json={"driver_id": TEST_DRIVER_ID, "date": today,
                                 "time": "11:30", "type": "ud", "reason": "TEST_smoke_out"},
                           headers=admin_h, timeout=15)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["id"] == ind_id  # FIFO paired same record
        assert d2["end_time"] == "11:30"
        assert d2["manual_type"] == "punch_ud"
        assert d2["duration_minutes"] == 150

    def test_admin_period_create(self, admin_h):
        today = _today()
        r = requests.post(f"{BASE}/api/driver/time-entries",
                         json={"driver_id": TEST_DRIVER_ID, "date": today,
                               "start_time": "13:00", "end_time": "14:00",
                               "reason": "TEST_period"},
                         headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["manual"] is True
        assert d["manual_type"] == "period"
        assert d["start_time"] == "13:00" and d["end_time"] == "14:00"
        assert d["duration_minutes"] == 60
        assert d["created_by_role"] == "logistics_admin"

    def test_admin_reason_required_when_flag_on(self, admin_h):
        # turn on admin reason requirement
        requests.patch(f"{BASE}/api/company/payroll-settings",
                       json={"require_admin_punch_reason": True}, headers=admin_h, timeout=15)
        try:
            today = _today()
            r = requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                              json={"driver_id": TEST_DRIVER_ID, "date": today,
                                    "time": "08:00", "type": "ind", "reason": ""},
                              headers=admin_h, timeout=15)
            assert r.status_code == 400, r.text
            detail = r.json().get("detail", "")
            assert "Årsag er påkrævet" in detail

            # period also blocked
            r2 = requests.post(f"{BASE}/api/driver/time-entries",
                              json={"driver_id": TEST_DRIVER_ID, "date": today,
                                    "start_time": "08:00", "end_time": "09:00", "reason": ""},
                              headers=admin_h, timeout=15)
            assert r2.status_code == 400
            assert "Årsag er påkrævet" in r2.json().get("detail", "")
        finally:
            requests.patch(f"{BASE}/api/company/payroll-settings",
                           json={"require_admin_punch_reason": False}, headers=admin_h, timeout=15)


# ── 3. Driver-side endpoints ─────────────────────────────────────────────────
class TestDriverPunch:
    @pytest.fixture(autouse=True)
    def _cleanup(self, admin_h):
        _cleanup_entries(admin_h, TEST_DRIVER_ID, _today())
        yield
        _cleanup_entries(admin_h, TEST_DRIVER_ID, _today())

    def test_driver_manual_punch_creates_for_self(self, driver_h):
        today = _today()
        r = requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                          json={"date": today, "time": "07:00", "type": "ind",
                                "reason": "TEST_driver_in",
                                "driver_id": "should-be-ignored-XYZ"},
                          headers=driver_h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["manual_type"] == "punch_ind"
        # driver_id must equal driver's own id (not the bogus one)
        assert d["driver_id"] != "should-be-ignored-XYZ"
        assert d["driver_id"] == TEST_DRIVER_ID

    def test_driver_cannot_use_period_endpoint(self, driver_h):
        today = _today()
        r = requests.post(f"{BASE}/api/driver/time-entries",
                          json={"date": today, "start_time": "10:00", "end_time": "11:00"},
                          headers=driver_h, timeout=15)
        assert r.status_code == 403, r.text

    def test_driver_reason_required_when_flag_on(self, admin_h, driver_h):
        requests.patch(f"{BASE}/api/company/payroll-settings",
                       json={"require_driver_punch_reason": True}, headers=admin_h, timeout=15)
        try:
            today = _today()
            r = requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                              json={"date": today, "time": "07:30", "type": "ind", "reason": ""},
                              headers=driver_h, timeout=15)
            assert r.status_code == 400, r.text
            assert "Årsag er påkrævet" in r.json().get("detail", "")
        finally:
            requests.patch(f"{BASE}/api/company/payroll-settings",
                           json={"require_driver_punch_reason": False}, headers=admin_h, timeout=15)


# ── 4. Per-driver list ───────────────────────────────────────────────────────
class TestAdminTimeEntriesPerDriver:
    def test_get_per_driver_returns_structure(self, admin_h):
        today = _today()
        # Ensure at least one entry exists
        _cleanup_entries(admin_h, TEST_DRIVER_ID, today)
        requests.post(f"{BASE}/api/driver/time-entries/manual-punch",
                      json={"driver_id": TEST_DRIVER_ID, "date": today,
                            "time": "06:00", "type": "ind", "reason": "TEST_list"},
                      headers=admin_h, timeout=15)
        try:
            r = requests.get(f"{BASE}/api/admin/time-entries?date={today}",
                             headers=admin_h, timeout=15)
            assert r.status_code == 200, r.text
            data = r.json()
            assert isinstance(data, list)
            # find Test Driver entry
            row = next((x for x in data if x["driver_id"] == TEST_DRIVER_ID), None)
            assert row is not None
            for k in ("driver_id", "driver_name", "entries", "total_minutes",
                      "first_in", "last_out", "has_open", "entries_count"):
                assert k in row
            assert row["entries_count"] >= 1
            assert row["has_open"] is True
            assert row["first_in"] == "06:00"
        finally:
            _cleanup_entries(admin_h, TEST_DRIVER_ID, today)
