"""Phase 15.31 backend tests — Future-blocking on manual punch + soft-delete
for driver/admin manual time entries.

Covers:
- Manual punch (driver + admin) blocks future date/time.
- Driver period POST is exempt from future-blocking.
- Driver PATCH/DELETE on own manual entries with all error cases.
- Soft-delete behavior on GET endpoints (driver + admin, include_deleted).
- Overlap-check ignores soft-deleted entries.
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL is required"

ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASS = "TestPass2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASS = "Driver2026!"
DRIVER_ID = "cbd13b47-0649-4bd9-a79b-9e6d9da7e95a"

LOCAL_TZ = ZoneInfo("Europe/Copenhagen")


def _login(email: str, password: str) -> str:
    """Login with rate-limit aware backoff."""
    for attempt in range(6):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            j = r.json()
            return j.get("token") or j.get("access_token")
        if r.status_code == 429:
            time.sleep(8 + attempt * 2)
            continue
        # 401/etc — still wait then retry; rate-limit may also return 401
        time.sleep(7)
    raise RuntimeError(f"Login failed for {email}: {r.status_code} {r.text[:200]}")


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


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _today_local():
    return datetime.now(tz=LOCAL_TZ).strftime("%Y-%m-%d")


def _now_local_hhmm():
    return datetime.now(tz=LOCAL_TZ).strftime("%H:%M")


def _past_time_today():
    """Returns a HH:MM at least 30 minutes in the past (today local)."""
    now = datetime.now(tz=LOCAL_TZ)
    h = now.hour
    if h < 2:
        # too early — use 00:30
        return "00:05"
    return f"{h-1:02d}:00"


def _hard_delete(admin_tok, entry_id):
    try:
        requests.delete(f"{BASE_URL}/api/admin/time-entries/{entry_id}?hard=true",
                        headers=_h(admin_tok), timeout=15)
    except Exception:
        pass


def _create_driver_owned_period(driver_tok, admin_tok, date, start_hhmm, end_hhmm):
    """Create a driver-owned closed manual entry via two manual-punches (IND + UD).
    Returns the closed entry dict, or None if creation failed."""
    r_in = requests.post(
        f"{BASE_URL}/api/driver/time-entries/manual-punch",
        headers=_h(driver_tok),
        json={"date": date, "time": start_hhmm, "type": "ind", "reason": "TEST_seed"},
        timeout=15,
    )
    if r_in.status_code != 200:
        return None, f"IND failed: {r_in.status_code} {r_in.text[:120]}"
    ind_entry = r_in.json()
    r_out = requests.post(
        f"{BASE_URL}/api/driver/time-entries/manual-punch",
        headers=_h(driver_tok),
        json={"date": date, "time": end_hhmm, "type": "ud", "reason": "TEST_seed"},
        timeout=15,
    )
    if r_out.status_code != 200:
        # Cleanup the IND entry
        _hard_delete(admin_tok, ind_entry.get("id"))
        return None, f"UD failed: {r_out.status_code} {r_out.text[:120]}"
    # manual-punch UD updates the IND entry — refetch
    return r_out.json(), None


# Use an isolated test date with unique driver-id-tag-prefix per test run via the date suffix
# Actual driver_id is fixed (real driver), so we use a slot-by-time approach + cleanup per test


def _create_driver_manual_punch(driver_tok, date, t, type_="ind"):
    return requests.post(
        f"{BASE_URL}/api/driver/time-entries/manual-punch",
        headers=_h(driver_tok),
        json={"date": date, "time": t, "type": type_, "reason": "TEST_phase15_31"},
        timeout=15,
    )


# ============= BACKEND TESTS =============

class TestFutureBlocking:
    def test_driver_manual_punch_future_time_today_blocked(self, driver_token, admin_token):
        # 23:59 should always be in future unless test runs after 23:58 — guard
        now = datetime.now(tz=LOCAL_TZ)
        if now.hour >= 23 and now.minute >= 55:
            pytest.skip("Too close to midnight for 23:59 future test")
        r = _create_driver_manual_punch(driver_token, _today_local(), "23:59", "ind")
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "fremtiden" in r.text.lower()

    def test_driver_manual_punch_future_date_blocked(self, driver_token):
        r = _create_driver_manual_punch(driver_token, "2099-12-31", "10:00", "ind")
        assert r.status_code == 400
        assert "fremtiden" in r.text.lower()

    def test_driver_manual_punch_past_time_today_succeeds(self, driver_token, admin_token):
        t = _past_time_today()
        date = _today_local()
        r = _create_driver_manual_punch(driver_token, date, t, "ind")
        # Tolerate overlap with existing data — accept 200 or 409
        if r.status_code == 409:
            pytest.skip(f"Overlap with existing data at {t}: {r.text[:120]}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("manual") is True
        assert data.get("created_by_role") == "driver"
        assert (data.get("slice_type") or "work") == "work"
        # cleanup hard
        _hard_delete(admin_token, data["id"])

    def test_admin_manual_punch_future_blocked(self, admin_token):
        now = datetime.now(tz=LOCAL_TZ)
        if now.hour >= 23 and now.minute >= 55:
            pytest.skip("Too close to midnight")
        # Admin uses SAME endpoint /driver/time-entries/manual-punch with driver_id in body
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries/manual-punch",
            headers=_h(admin_token),
            json={"driver_id": DRIVER_ID, "date": _today_local(), "time": "23:59",
                  "type": "ind", "reason": "TEST_admin_future"},
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "fremtiden" in r.text.lower()

    def test_admin_period_post_future_end_allowed(self, admin_token):
        """Admin period POST should allow end_time in future (only manual-punch blocks future)."""
        # Use a unique past start_time to avoid overlap
        date = _today_local()
        start = "00:01"
        end = "23:59"
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries",
            headers=_h(admin_token),
            json={"driver_id": DRIVER_ID, "date": date, "start_time": start,
                  "end_time": end, "reason": "TEST_admin_period_future"},
            timeout=15,
        )
        if r.status_code == 409:
            pytest.skip(f"Overlap with existing data 00:01–23:59: {r.text[:120]}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        _hard_delete(admin_token, data["id"])


class TestDriverPatchOwnEntry:
    @pytest.fixture
    def own_entry(self, driver_token, admin_token):
        """Create a driver-owned manual entry via manual-punch IND+UD, yield, then hard-cleanup."""
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        base_h = max(0, now.hour - 3)
        slot_start = f"{base_h:02d}:01"
        slot_end = f"{base_h:02d}:30"
        entry, err = _create_driver_owned_period(driver_token, admin_token, date, slot_start, slot_end)
        if not entry:
            pytest.skip(f"Could not create own entry: {err}")
        yield entry
        _hard_delete(admin_token, entry["id"])

    def test_driver_patch_own_entry_success(self, driver_token, own_entry):
        new_reason = f"TEST_updated_{uuid.uuid4().hex[:6]}"
        r = requests.patch(
            f"{BASE_URL}/api/driver/time-entries/{own_entry['id']}",
            headers=_h(driver_token),
            json={"reason": new_reason, "slice_type": "pause"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["reason"] == new_reason
        assert data["slice_type"] == "pause"

    def test_driver_patch_future_start_blocked(self, driver_token, own_entry):
        r = requests.patch(
            f"{BASE_URL}/api/driver/time-entries/{own_entry['id']}",
            headers=_h(driver_token),
            json={"date": "2099-01-01", "start_time": "10:00"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "fremtiden" in r.text.lower()

    def test_driver_patch_admin_created_blocked(self, driver_token, admin_token):
        # Create an admin-owned manual entry (admin creates for driver)
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - 5)
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries",
            headers=_h(admin_token),
            json={"driver_id": DRIVER_ID, "date": date,
                  "start_time": f"{h:02d}:05", "end_time": f"{h:02d}:25",
                  "reason": "TEST_admin_created"},
            timeout=15,
        )
        if r.status_code != 200:
            pytest.skip(f"Admin entry creation failed: {r.status_code} {r.text[:120]}")
        admin_entry = r.json()
        try:
            r2 = requests.patch(
                f"{BASE_URL}/api/driver/time-entries/{admin_entry['id']}",
                headers=_h(driver_token),
                json={"reason": "TEST_should_fail"},
                timeout=15,
            )
            assert r2.status_code == 403
            assert "admin" in r2.text.lower()
        finally:
            _hard_delete(admin_token, admin_entry["id"])

    def test_driver_patch_nonexistent_returns_404(self, driver_token):
        r = requests.patch(
            f"{BASE_URL}/api/driver/time-entries/non-existent-id-xyz",
            headers=_h(driver_token),
            json={"reason": "x"},
            timeout=15,
        )
        assert r.status_code == 404


class TestDriverDeleteOwnEntry:
    def _make_entry(self, driver_token, admin_token, slot_offset_h=4):
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - slot_offset_h)
        entry, err = _create_driver_owned_period(driver_token, admin_token, date,
                                                  f"{h:02d}:02", f"{h:02d}:28")
        if not entry:
            pytest.skip(f"Cannot create entry for delete test: {err}")
        return entry

    def test_driver_soft_delete_own_entry(self, driver_token, admin_token):
        entry = self._make_entry(driver_token, admin_token, slot_offset_h=4)
        try:
            r = requests.delete(
                f"{BASE_URL}/api/driver/time-entries/{entry['id']}",
                headers=_h(driver_token), timeout=15,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data.get("deleted_count") == 1
            assert data.get("mode") == "soft"

            # Verify via admin include_deleted=true
            r2 = requests.get(
                f"{BASE_URL}/api/admin/time-entries",
                params={"date": _today_local(), "include_deleted": "true"},
                headers=_h(admin_token), timeout=15,
            )
            assert r2.status_code == 200
            found = None
            for drv in r2.json():
                for e in drv.get("entries", []):
                    if e.get("id") == entry["id"]:
                        found = e
                        break
            assert found is not None, "Soft-deleted entry must be visible with include_deleted"
            assert found.get("deleted") is True
            assert found.get("deleted_by_role") == "driver"
            assert found.get("deleted_at")

            # Second delete should return 410
            r3 = requests.delete(
                f"{BASE_URL}/api/driver/time-entries/{entry['id']}",
                headers=_h(driver_token), timeout=15,
            )
            assert r3.status_code == 410
            assert "allerede slettet" in r3.text.lower()
        finally:
            _hard_delete(admin_token, entry["id"])

    def test_driver_delete_admin_created_blocked(self, driver_token, admin_token):
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - 6)
        r = requests.post(
            f"{BASE_URL}/api/driver/time-entries",
            headers=_h(admin_token),
            json={"driver_id": DRIVER_ID, "date": date,
                  "start_time": f"{h:02d}:03", "end_time": f"{h:02d}:22",
                  "reason": "TEST_admin_created2"},
            timeout=15,
        )
        if r.status_code != 200:
            pytest.skip(f"Could not seed admin entry: {r.text[:120]}")
        admin_entry = r.json()
        try:
            r2 = requests.delete(
                f"{BASE_URL}/api/driver/time-entries/{admin_entry['id']}",
                headers=_h(driver_token), timeout=15,
            )
            assert r2.status_code == 403
        finally:
            _hard_delete(admin_token, admin_entry["id"])


class TestSoftDeleteVisibility:
    def test_driver_get_excludes_deleted(self, driver_token, admin_token):
        # Create + soft-delete then verify GET /driver/time-entries excludes it
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - 7)
        entry, err = _create_driver_owned_period(driver_token, admin_token, date,
                                                  f"{h:02d}:04", f"{h:02d}:18")
        if not entry:
            pytest.skip(f"Setup create failed: {err}")
        eid = entry["id"]
        try:
            dr = requests.delete(
                f"{BASE_URL}/api/driver/time-entries/{eid}",
                headers=_h(driver_token), timeout=15,
            )
            assert dr.status_code == 200

            lst = requests.get(
                f"{BASE_URL}/api/driver/time-entries",
                params={"date_from": date, "date_to": date},
                headers=_h(driver_token), timeout=15,
            )
            assert lst.status_code == 200
            ids = [e.get("id") for e in lst.json()]
            assert eid not in ids, "Deleted entry must not appear in driver GET"
        finally:
            _hard_delete(admin_token, eid)

    def test_admin_get_default_excludes_deleted_but_counts(self, driver_token, admin_token):
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - 8)
        entry, err = _create_driver_owned_period(driver_token, admin_token, date,
                                                  f"{h:02d}:05", f"{h:02d}:11")
        if not entry:
            pytest.skip(f"Setup create failed: {err}")
        eid = entry["id"]
        try:
            requests.delete(f"{BASE_URL}/api/driver/time-entries/{eid}",
                            headers=_h(driver_token), timeout=15)

            r = requests.get(
                f"{BASE_URL}/api/admin/time-entries",
                params={"date": date}, headers=_h(admin_token), timeout=15,
            )
            assert r.status_code == 200
            drv = next((d for d in r.json() if d.get("driver_id") == DRIVER_ID), None)
            assert drv is not None
            ids_in_entries = [e.get("id") for e in drv.get("entries", [])]
            assert eid not in ids_in_entries, "Default admin GET must hide soft-deleted"
            assert "deleted_count" in drv
            assert drv["deleted_count"] >= 1

            # include_deleted=true
            r2 = requests.get(
                f"{BASE_URL}/api/admin/time-entries",
                params={"date": date, "include_deleted": "true"},
                headers=_h(admin_token), timeout=15,
            )
            assert r2.status_code == 200
            drv2 = next((d for d in r2.json() if d.get("driver_id") == DRIVER_ID), None)
            ids2 = [e.get("id") for e in (drv2 or {}).get("entries", [])]
            assert eid in ids2, "include_deleted=true must surface soft-deleted entries"
        finally:
            _hard_delete(admin_token, eid)


class TestOverlapIgnoresSoftDeleted:
    def test_new_entry_in_softdeleted_slot(self, driver_token, admin_token):
        date = _today_local()
        now = datetime.now(tz=LOCAL_TZ)
        h = max(0, now.hour - 9)
        slot_start = f"{h:02d}:06"
        slot_end = f"{h:02d}:24"
        entry, err = _create_driver_owned_period(driver_token, admin_token, date, slot_start, slot_end)
        if not entry:
            pytest.skip(f"Setup failed: {err}")
        eid = entry["id"]
        try:
            # Soft-delete it
            requests.delete(f"{BASE_URL}/api/driver/time-entries/{eid}",
                            headers=_h(driver_token), timeout=15)
            # Now create a new entry in the SAME slot — should succeed
            entry2, err2 = _create_driver_owned_period(driver_token, admin_token, date,
                                                       slot_start, slot_end)
            assert entry2 is not None, f"Soft-deleted should not block: {err2}"
            _hard_delete(admin_token, entry2["id"])
        finally:
            _hard_delete(admin_token, eid)
