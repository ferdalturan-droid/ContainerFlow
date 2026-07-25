"""Phase 15.32 backend tests — Driver can edit/delete OWN AUTO punch entries +
NEW PATCH /admin/time-entries/{id} endpoint.

Key rules (15.32):
- _verify_driver_owns_manual now allows ANY entry where driver_id==self AND
  created_by_role NOT IN ('logistics_admin','super_admin').
- Admin PATCH endpoint updates entry fields with overlap-check (exclude self),
  rejects soft-deleted (410), rejects cross-company (403).
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL is required"

ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASS = "TestPass2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASS = "Driver2026!"
DRIVER_ID = "cbd13b47-0649-4bd9-a79b-9e6d9da7e95a"

LOCAL_TZ = ZoneInfo("Europe/Copenhagen")


# ------------------- helpers -------------------

def _login(email: str, password: str) -> str:
    for attempt in range(6):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            j = r.json()
            return j.get("token") or j.get("access_token")
        if r.status_code == 429:
            time.sleep(8 + attempt * 2)
            continue
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


def _past_window():
    """Return a (start, end) past window today, well before noon to avoid clashes."""
    # Use very early morning slots, varying minutes to avoid overlap across tests
    m = (uuid.uuid4().int % 50)
    return (f"01:{m:02d}", f"01:{m+5:02d}")


def _next_window(prev_end="HH:MM"):
    """Returns a non-overlapping past window for a 2nd entry."""
    now = datetime.now(tz=LOCAL_TZ)
    if now.hour < 4:
        return ("00:35", "00:50")
    return (f"{now.hour-3:02d}:00", f"{now.hour-3:02d}:30")


# ------------------- AUTO entry seeding -------------------

def _seed_auto_punch_entry(driver_tok, admin_tok) -> str:
    """Use POST /driver/time-entries/punch to create an IND+UD auto pair, then
    return a CLOSED auto entry id. Uses an early-morning hour to avoid overlap.
    """
    date = _today_local()
    # Always use 02:xx range with random minutes
    mm = (uuid.uuid4().int % 50)
    t_in = f"02:{mm:02d}"
    t_out = f"02:{mm+5:02d}"
    # Punch IND
    r1 = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                       headers=_h(driver_tok),
                       json={"type": "ind", "date": date, "time": t_in},
                       timeout=20)
    # If 400 due to existing open slice → try cleanup via punch UD first
    if r1.status_code == 400 and ("åben" in r1.text.lower() or "open" in r1.text.lower()):
        requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                      headers=_h(driver_tok),
                      json={"type": "ud", "date": date, "time": t_in},
                      timeout=20)
        r1 = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                           headers=_h(driver_tok),
                           json={"type": "ind", "date": date, "time": t_in},
                           timeout=20)
    if r1.status_code == 409:
        pytest.skip(f"punch in overlap: {r1.text[:200]}")
    assert r1.status_code in (200, 201), f"punch in failed: {r1.status_code} {r1.text[:200]}"
    time.sleep(0.3)
    # Punch UD to close it
    r2 = requests.post(f"{BASE_URL}/api/driver/time-entries/punch",
                       headers=_h(driver_tok),
                       json={"type": "ud", "date": date, "time": t_out},
                       timeout=20)
    if r2.status_code == 409:
        pytest.skip(f"punch out overlap: {r2.text[:200]}")
    assert r2.status_code in (200, 201), f"punch out failed: {r2.status_code} {r2.text[:200]}"
    time.sleep(0.3)
    # Get today's driver entries
    r3 = requests.get(f"{BASE_URL}/api/driver/time-entries",
                      headers=_h(driver_tok),
                      params={"date": _today_local()}, timeout=20)
    assert r3.status_code == 200, f"driver list failed: {r3.status_code} {r3.text[:200]}"
    body = r3.json()
    entries = body.get("entries") if isinstance(body, dict) else body
    assert isinstance(entries, list) and len(entries) >= 1, f"no entries returned: {body}"
    # Prefer a closed auto entry
    auto_closed = [e for e in entries
                   if not e.get("deleted")
                   and (e.get("created_by_role") or "") not in ("logistics_admin", "super_admin")
                   and not e.get("manual", False)
                   and e.get("end_time")]
    if auto_closed:
        return auto_closed[-1]["id"]
    # fallback: any auto entry
    auto_any = [e for e in entries
                if not e.get("deleted")
                and (e.get("created_by_role") or "") not in ("logistics_admin", "super_admin")
                and not e.get("manual", False)]
    assert auto_any, f"could not find auto entry in {entries}"
    return auto_any[-1]["id"]


# ------------------- TESTS: Driver PATCH/DELETE on OWN AUTO -------------------

class TestDriverEditsOwnAutoEntry:
    """Phase 15.32: driver can PATCH/DELETE own AUTO IND/UD entries."""

    def test_driver_patch_own_auto_entry(self, driver_token, admin_token):
        eid = _seed_auto_punch_entry(driver_token, admin_token)
        try:
            # Update reason field only — safest, no overlap risk
            new_reason = f"15.32-test-{uuid.uuid4().hex[:6]}"
            r = requests.patch(f"{BASE_URL}/api/driver/time-entries/{eid}",
                               headers=_h(driver_token),
                               json={"reason": new_reason}, timeout=20)
            assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text[:300]}"
            body = r.json()
            assert body.get("reason") == new_reason
            # Verify via GET
            r2 = requests.get(f"{BASE_URL}/api/driver/time-entries",
                              headers=_h(driver_token),
                              params={"date": _today_local()}, timeout=20)
            assert r2.status_code == 200
            entries = r2.json().get("entries") if isinstance(r2.json(), dict) else r2.json()
            matched = [e for e in entries if e.get("id") == eid]
            assert matched, "patched entry missing from GET"
            assert matched[0].get("reason") == new_reason
        finally:
            requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                            headers=_h(admin_token), params={"hard": "true"}, timeout=20)

    def test_driver_delete_own_auto_entry(self, driver_token, admin_token):
        eid = _seed_auto_punch_entry(driver_token, admin_token)
        r = requests.delete(f"{BASE_URL}/api/driver/time-entries/{eid}",
                            headers=_h(driver_token), timeout=20)
        assert r.status_code == 200, f"DELETE failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        # Mode 'soft' per spec
        assert body.get("mode") == "soft", f"expected soft delete, got {body}"
        # Verify entry no longer appears in default GET (deleted=true filter)
        r2 = requests.get(f"{BASE_URL}/api/driver/time-entries",
                          headers=_h(driver_token),
                          params={"date": _today_local()}, timeout=20)
        assert r2.status_code == 200
        entries = r2.json().get("entries") if isinstance(r2.json(), dict) else r2.json()
        alive_ids = [e["id"] for e in entries if not e.get("deleted")]
        assert eid not in alive_ids, "soft-deleted entry still visible"

    def test_driver_cannot_patch_admin_created_entry(self, driver_token, admin_token):
        """Admin-created entry must be 403 for driver PATCH."""
        # Admin creates a period entry for the test driver via admin period POST
        s, e = _past_window()
        payload = {
            "driver_id": DRIVER_ID,
            "date": _today_local(),
            "start_time": s,
            "end_time": e,
            "reason": "admin-seed-15.32",
        }
        r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                          headers=_h(admin_token), json=payload, timeout=20)
        # If overlap with existing, bail out & skip
        if r.status_code == 409:
            pytest.skip(f"admin seed blocked by overlap: {r.text[:200]}")
        assert r.status_code in (200, 201), f"admin create failed: {r.status_code} {r.text[:300]}"
        admin_entry = r.json()
        admin_entry_id = admin_entry.get("id") or admin_entry.get("entry", {}).get("id")
        assert admin_entry_id, f"no id in admin create response: {admin_entry}"

        try:
            # Driver tries to patch -> should be 403
            r2 = requests.patch(f"{BASE_URL}/api/driver/time-entries/{admin_entry_id}",
                                headers=_h(driver_token),
                                json={"reason": "nope"}, timeout=20)
            assert r2.status_code == 403, f"expected 403, got {r2.status_code}: {r2.text[:200]}"
        finally:
            # Cleanup — hard delete by admin
            requests.delete(
                f"{BASE_URL}/api/admin/time-entries/{admin_entry_id}",
                headers=_h(admin_token), params={"hard": "true"}, timeout=20)


# ------------------- TESTS: Admin PATCH endpoint -------------------

class TestAdminPatchEndpoint:
    """Phase 15.32: NEW PATCH /admin/time-entries/{id}."""

    def _create_admin_entry(self, admin_token):
        s, e = _past_window()
        payload = {
            "driver_id": DRIVER_ID,
            "date": _today_local(),
            "start_time": s,
            "end_time": e,
            "reason": "admin-patch-seed",
        }
        r = requests.post(f"{BASE_URL}/api/driver/time-entries",
                          headers=_h(admin_token), json=payload, timeout=20)
        if r.status_code == 409:
            pytest.skip(f"admin seed blocked by overlap: {r.text[:200]}")
        assert r.status_code in (200, 201), f"admin create failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        eid = body.get("id") or body.get("entry", {}).get("id")
        assert eid
        return eid

    def test_admin_patch_updates_fields(self, admin_token):
        eid = self._create_admin_entry(admin_token)
        try:
            new_reason = f"admin-patch-{uuid.uuid4().hex[:6]}"
            r = requests.patch(f"{BASE_URL}/api/admin/time-entries/{eid}",
                               headers=_h(admin_token),
                               json={"reason": new_reason, "slice_type": "pause"},
                               timeout=20)
            assert r.status_code == 200, f"admin PATCH failed: {r.status_code} {r.text[:300]}"
            body = r.json()
            assert body.get("reason") == new_reason
            assert body.get("slice_type") == "pause"
            # duration_minutes should be recalculated > 0 since end_time present
            assert body.get("duration_minutes", 0) > 0
        finally:
            requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                            headers=_h(admin_token), params={"hard": "true"}, timeout=20)

    def test_admin_patch_overlap_excludes_self(self, admin_token, driver_token):
        """Patching the same entry with the same times must NOT trip overlap on itself."""
        eid = self._create_admin_entry(admin_token)
        try:
            r0 = requests.get(f"{BASE_URL}/api/driver/time-entries",
                              headers=_h(driver_token),
                              params={"date": _today_local()}, timeout=20)
            entries = []
            if r0.status_code == 200:
                rj = r0.json()
                entries = rj.get("entries", []) if isinstance(rj, dict) else rj
            same = next((e for e in entries if e.get("id") == eid), None)
            if same:
                payload = {"start_time": same["start_time"], "end_time": same["end_time"]}
                r = requests.patch(f"{BASE_URL}/api/admin/time-entries/{eid}",
                                   headers=_h(admin_token), json=payload, timeout=20)
                assert r.status_code == 200, \
                    f"self-overlap check failed (should exclude self): {r.status_code} {r.text[:200]}"
        finally:
            requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                            headers=_h(admin_token), params={"hard": "true"}, timeout=20)

    def test_admin_patch_soft_deleted_returns_410(self, admin_token):
        eid = self._create_admin_entry(admin_token)
        # Soft-delete first
        r1 = requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                             headers=_h(admin_token), timeout=20)
        assert r1.status_code in (200, 204), f"soft delete failed: {r1.status_code}"
        # Now PATCH should fail with 410
        r2 = requests.patch(f"{BASE_URL}/api/admin/time-entries/{eid}",
                            headers=_h(admin_token),
                            json={"reason": "after-delete"}, timeout=20)
        assert r2.status_code == 410, f"expected 410, got {r2.status_code}: {r2.text[:200]}"
        # Cleanup hard
        requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                        headers=_h(admin_token), params={"hard": "true"}, timeout=20)

    def test_admin_patch_nonexistent_returns_404(self, admin_token):
        bogus = "deadbeef-0000-0000-0000-000000000000"
        r = requests.patch(f"{BASE_URL}/api/admin/time-entries/{bogus}",
                           headers=_h(admin_token),
                           json={"reason": "x"}, timeout=20)
        assert r.status_code == 404, f"expected 404, got {r.status_code}"

    def test_admin_patch_requires_date_and_start(self, admin_token):
        """If existing entry has values, omitting them should NOT 400 — falls back to existing."""
        eid = self._create_admin_entry(admin_token)
        try:
            r = requests.patch(f"{BASE_URL}/api/admin/time-entries/{eid}",
                               headers=_h(admin_token),
                               json={"reason": "fallback-test"}, timeout=20)
            assert r.status_code == 200, f"expected fallback OK, got {r.status_code}: {r.text[:200]}"
        finally:
            requests.delete(f"{BASE_URL}/api/admin/time-entries/{eid}",
                            headers=_h(admin_token), params={"hard": "true"}, timeout=20)

    def test_driver_cannot_call_admin_patch(self, driver_token):
        bogus = "deadbeef-0000-0000-0000-000000000001"
        r = requests.patch(f"{BASE_URL}/api/admin/time-entries/{bogus}",
                           headers=_h(driver_token),
                           json={"reason": "x"}, timeout=20)
        # Either 401/403 — must NOT be 200/404 (404 would imply lookup happened)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
