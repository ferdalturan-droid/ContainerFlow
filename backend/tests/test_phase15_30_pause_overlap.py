"""Phase 15.30 — Start pause + overlap-validering.

Tests:
- Punch-in opens work-slice
- Start pause atomic transition (close work + open pause at same time)
- Start arbejde igen atomic transition
- UD closes any open slice
- Cannot start pause without open work
- Cannot start work when work already open
- Overlap-block: manuel-punch overlapping closed period
- Overlap-block: admin period overlapping
- Manuel-punch with slice_type accepted
- Admin period with slice_type=pause
- GET /admin/time-entries returns work_minutes, pause_minutes, total_minutes
- GET /driver/time-entries has slice_type on all entries
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASS = "Driver2026!"
ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASS = "TestPass2026!"
DRIVER_ID = "cbd13b47-0649-4bd9-a79b-9e6d9da7e95a"

TEST_DATE = "2026-01-15"  # isolated date for tests


def _login(email: str, password: str) -> str:
    # Rate-limit on /auth/login: wait >6s between logins
    for attempt in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password})
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(8)
            continue
        pytest.fail(f"Login failed for {email}: {r.status_code} {r.text}")
    pytest.fail(f"Login still rate-limited for {email}")


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PASS)
    time.sleep(7)
    return tok


@pytest.fixture(scope="module")
def driver_token():
    tok = _login(DRIVER_EMAIL, DRIVER_PASS)
    time.sleep(7)
    return tok


@pytest.fixture(scope="module", autouse=True)
def ensure_no_reason_required(admin_token):
    """Disable require_driver_punch_reason + require_admin_punch_reason
    so punch tests don't fail with 'Årsag er påkrævet'."""
    r = requests.patch(
        f"{BASE_URL}/api/company/payroll-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"require_driver_punch_reason": False,
              "require_admin_punch_reason": False},
    )
    assert r.status_code in (200, 204), f"Patch failed: {r.status_code} {r.text}"


def _clean_date(admin_token: str, date: str):
    """Best effort: delete all entries for driver+date via admin endpoint."""
    # Use list endpoint then delete each
    r = requests.get(
        f"{BASE_URL}/api/admin/time-entries?date={date}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if r.status_code != 200:
        return
    for d in r.json():
        if d.get("driver_id") != DRIVER_ID:
            continue
        for e in d.get("entries", []):
            eid = e.get("id")
            if eid:
                requests.delete(
                    f"{BASE_URL}/api/admin/time-entries/{eid}?cascade=true",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )


@pytest.fixture(autouse=True)
def reset_date(admin_token):
    _clean_date(admin_token, TEST_DATE)
    yield
    _clean_date(admin_token, TEST_DATE)


# ============================================================
# Punch flow tests (driver token)
# ============================================================

class TestPunchFlow:
    def test_punch_in_creates_work_slice(self, driver_token):
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries/punch",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={"date": TEST_DATE, "time": "08:00",
                  "type": "ind", "slice_type": "work"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slice_type"] == "work"
        assert d["manual"] is False
        assert d["start_time"] == "08:00"
        assert d["end_time"] == ""

    def test_start_pause_transition(self, driver_token):
        # Open work-slice at 08:00
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries/punch",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={"date": TEST_DATE, "time": "08:00", "type": "ind",
                  "slice_type": "work"},
        )
        assert r.status_code == 200
        # Start pause at 12:00
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries/punch",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={"date": TEST_DATE, "time": "12:00", "type": "ind",
                  "slice_type": "pause"},
        )
        assert r.status_code == 200, r.text
        new_doc = r.json()
        assert new_doc["slice_type"] == "pause"
        assert new_doc["start_time"] == "12:00"
        assert new_doc["end_time"] == ""
        # Verify GET shows 2 docs: work closed + pause open
        r = requests.get(
            f"{BASE_URL}/api/driver/time-entries?date_from={TEST_DATE}&date_to={TEST_DATE}",
            headers={"Authorization": f"Bearer {driver_token}"},
        )
        assert r.status_code == 200
        items = [e for e in r.json() if e["date"] == TEST_DATE]
        assert len(items) == 2, items
        work_items = [e for e in items if e["slice_type"] == "work"]
        pause_items = [e for e in items if e["slice_type"] == "pause"]
        assert len(work_items) == 1
        assert len(pause_items) == 1
        assert work_items[0]["start_time"] == "08:00"
        assert work_items[0]["end_time"] == "12:00"
        assert work_items[0]["duration_minutes"] == 240
        assert pause_items[0]["start_time"] == "12:00"
        assert pause_items[0]["end_time"] == ""

    def test_start_work_again_from_pause(self, driver_token):
        # Setup: work 08-12 closed + pause 12 open
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "08:00",
                            "type": "ind", "slice_type": "work"})
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "12:00",
                            "type": "ind", "slice_type": "pause"})
        # Now start work again at 12:30
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"date": TEST_DATE, "time": "12:30",
                                "type": "ind", "slice_type": "work"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slice_type"] == "work"
        assert d["start_time"] == "12:30"
        assert d["end_time"] == ""
        # Pause should be closed 12:00 → 12:30
        r = requests.get(
            f"{BASE_URL}/api/driver/time-entries?date_from={TEST_DATE}&date_to={TEST_DATE}",
            headers={"Authorization": f"Bearer {driver_token}"})
        items = [e for e in r.json() if e["date"] == TEST_DATE]
        assert len(items) == 3
        pause = [e for e in items if e["slice_type"] == "pause"][0]
        assert pause["start_time"] == "12:00"
        assert pause["end_time"] == "12:30"
        assert pause["duration_minutes"] == 30

    def test_ud_closes_open_slice(self, driver_token):
        # Setup work open at 08:00
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "08:00",
                            "type": "ind", "slice_type": "work"})
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"date": TEST_DATE, "time": "17:00",
                                "type": "ud"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slice_type"] == "work"
        assert d["end_time"] == "17:00"
        assert d["duration_minutes"] == 9 * 60

    def test_cannot_start_pause_without_open_work(self, driver_token):
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"date": TEST_DATE, "time": "10:00",
                                "type": "ind", "slice_type": "pause"})
        assert r.status_code == 409, r.text
        msg = r.json().get("detail", "")
        assert "stemplet ind" in msg.lower() or "arbejde" in msg.lower()
        assert "pause" in msg.lower()

    def test_cannot_start_work_when_work_already_open(self, driver_token):
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "08:00",
                            "type": "ind", "slice_type": "work"})
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                         headers={"Authorization": f"Bearer {driver_token}"},
                         json={"date": TEST_DATE, "time": "09:00",
                               "type": "ind", "slice_type": "work"})
        assert r.status_code == 409, r.text
        msg = r.json().get("detail", "")
        assert "allerede" in msg.lower() and "arbejde" in msg.lower()


# ============================================================
# Overlap tests
# ============================================================

class TestOverlap:
    def test_manual_punch_overlap_blocked(self, driver_token):
        # First create closed work 08-12 via punch
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "08:00",
                            "type": "ind", "slice_type": "work"})
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "12:00",
                            "type": "ud"})
        # Manual-punch IND inside that period (09:00) should be blocked
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"date": TEST_DATE, "time": "09:00",
                                "type": "ind", "reason": "test"})
        assert r.status_code == 409, r.text
        msg = r.json().get("detail", "")
        assert "overlap" in msg.lower(), msg
        assert "08:00" in msg

    def test_admin_period_overlap_blocked(self, admin_token):
        # Create work 08-12 via admin period endpoint
        r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                "start_time": "08:00", "end_time": "12:00",
                                "reason": "admin-test", "slice_type": "work"})
        assert r.status_code in (200, 201), r.text
        # Try to create overlapping 09-10
        r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                "start_time": "09:00", "end_time": "10:00",
                                "reason": "overlap", "slice_type": "work"})
        assert r.status_code == 409, r.text
        msg = r.json().get("detail", "")
        assert "overlapper" in msg.lower()
        assert "09:00" in msg and "10:00" in msg
        assert "08:00" in msg and "12:00" in msg


# ============================================================
# Slice-type acceptance / admin pause period
# ============================================================

class TestSliceTypeAdmin:
    def test_manual_punch_slice_type_work(self, driver_token):
        r = requests.post(f"{BASE_URL}/api/driver/time-entries/manual-punch",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"date": TEST_DATE, "time": "06:00",
                                "type": "ind", "slice_type": "work",
                                "reason": "manuel"})
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("slice_type", "work") == "work"

    def test_admin_period_pause(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                "start_time": "12:00", "end_time": "12:30",
                                "reason": "frokost", "slice_type": "pause"})
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("slice_type") == "pause"
        assert d.get("manual") is True


# ============================================================
# Admin aggregation: work_minutes / pause_minutes / total_minutes
# ============================================================

class TestAdminAggregation:
    def test_admin_time_entries_minutes_split(self, admin_token):
        # Setup: 3 entries via admin period:
        # work 08-12 (240) + pause 12-12:30 (30) + work 12:30-17 (270)
        r1 = requests.post(f"{BASE_URL}/api/driver/time-entries",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                 "start_time": "08:00", "end_time": "12:00",
                                 "slice_type": "work", "reason": "morgen"})
        r2 = requests.post(f"{BASE_URL}/api/driver/time-entries",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                 "start_time": "12:00", "end_time": "12:30",
                                 "slice_type": "pause", "reason": "frokost"})
        r3 = requests.post(f"{BASE_URL}/api/driver/time-entries",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"driver_id": DRIVER_ID, "date": TEST_DATE,
                                 "start_time": "12:30", "end_time": "17:00",
                                 "slice_type": "work", "reason": "eftermiddag"})
        assert r1.status_code in (200, 201), r1.text
        assert r2.status_code in (200, 201), r2.text
        assert r3.status_code in (200, 201), r3.text
        r = requests.get(
            f"{BASE_URL}/api/admin/time-entries?date={TEST_DATE}",
            headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        rec = next((d for d in data if d["driver_id"] == DRIVER_ID), None)
        assert rec is not None, data
        assert rec["work_minutes"] == 510, rec
        assert rec["pause_minutes"] == 30, rec
        assert rec["total_minutes"] == 540, rec


class TestDriverEntriesSliceField:
    def test_slice_type_present(self, driver_token):
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers={"Authorization": f"Bearer {driver_token}"},
                      json={"date": TEST_DATE, "time": "08:00",
                            "type": "ind", "slice_type": "work"})
        r = requests.get(
            f"{BASE_URL}/api/driver/time-entries?date_from={TEST_DATE}&date_to={TEST_DATE}",
            headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 200
        items = [e for e in r.json() if e["date"] == TEST_DATE]
        assert len(items) >= 1
        for e in items:
            assert "slice_type" in e
            assert e["slice_type"] in ("work", "pause")
