"""
Phase 14 (2026-06-19) — Capacity "AKTIV" must count only on_way tours.

Backend bug: PUT /api/tours/{id} counted ALL non-completed claimed tours
as "active" when validating trailer-capacity. This locked drivers out when
they had FÆRDIG (completed) tours from earlier in the day or claimed-but-
not-started tours sitting in their list.

Fix (server.py update_tour, ~line 1730): count_documents now filters by
{on_way: True, completed != True}.

Test plan:
  T1 — Driver has 1 completed tour (claimed_by_id == self, completed == true).
       Driver claims+starts a NEW tour (1 active going on_way). Backend must
       NOT raise 409 — completed tour is NOT "AKTIV".

  T2 — Driver with NO trailer (max_simultaneous = 1) currently has 1 on_way
       tour. Driver tries to start a 2nd → backend MUST return 409.
"""

import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

LA_EMAIL = "ilkdistadmin@gmail.com"
LA_PASS = "TestPass2026!"
DRIVER_LOGIN = "test2"
DRIVER_PASS = "TestC2026!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def la_token():
    return _login(LA_EMAIL, LA_PASS)


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


def _create_tour(la_token, label_suffix=""):
    plads = f"TEST_p14cap_{label_suffix}_{uuid.uuid4().hex[:6]}"
    body = {"plads": plads, "facility": "TEST-FAC", "container": "TEST-C1",
            "fraction": "TEST-FRAC", "tour_type": "normal"}
    r = requests.post(f"{API}/tours", json=body, headers=_h(la_token), timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _cleanup(tid, la_token):
    try:
        requests.delete(f"{API}/tours/{tid}", headers=_h(la_token), timeout=10)
    except Exception:
        pass


def _ensure_no_trailer(driver_token, driver_id):
    """Make sure driver has no active_trailer_id so max_simultaneous = 1."""
    try:
        # Best-effort: clear active trailer via the driver-trailer endpoint if
        # it exists; otherwise rely on the fact that tests run isolated.
        requests.put(
            f"{API}/driver/active-trailer",
            json={"trailer_id": ""},
            headers=_h(driver_token), timeout=10,
        )
    except Exception:
        pass


def _release_all_my_tours(driver_token, driver_id, la_token):
    """Reset state — release any tours currently claimed by the driver so
    capacity tests start from a clean slate."""
    try:
        r = requests.get(f"{API}/tours", headers=_h(la_token), timeout=15)
        for t in (r.json() or []):
            if t.get("claimed_by_id") == driver_id and not t.get("completed"):
                requests.put(
                    f"{API}/tours/{t['id']}",
                    json={"claimed_by": "", "claimed_by_id": "", "on_way": False},
                    headers=_h(la_token), timeout=10,
                )
    except Exception:
        pass


# ---------- T1: COMPLETED tour must NOT block claiming a new on_way ----
def test_completed_tour_does_not_count_as_active(la_token, driver_token, driver_info):
    driver_name = driver_info.get("display_name") or driver_info.get("name") or "testc"
    driver_id = driver_info.get("id") or driver_info.get("sub")
    _release_all_my_tours(driver_token, driver_id, la_token)
    _ensure_no_trailer(driver_token, driver_id)

    t_done = _create_tour(la_token, "done")
    t_new  = _create_tour(la_token, "new")
    try:
        # Claim + complete the first tour
        r = requests.put(f"{API}/tours/{t_done['id']}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id, "on_way": True},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, r.text
        r = requests.put(f"{API}/tours/{t_done['id']}",
            json={"claimed_by": driver_name, "weight": 500, "completed": True, "on_way": False},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, r.text

        # Now claim the NEW tour with on_way=true — must NOT be blocked.
        # Even with NO trailer (max_simultaneous=1) the completed tour
        # should not count as active.
        r = requests.put(f"{API}/tours/{t_new['id']}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id, "on_way": True},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, (
            f"Capacity-check incorrectly blocked claim: {r.status_code} {r.text}"
        )
    finally:
        _cleanup(t_done["id"], la_token)
        _cleanup(t_new["id"], la_token)


# ---------- T2: Two simultaneous on_way (no trailer) must still hit limit
def test_two_onway_tours_without_trailer_blocked(la_token, driver_token, driver_info):
    driver_name = driver_info.get("display_name") or driver_info.get("name") or "testc"
    driver_id = driver_info.get("id") or driver_info.get("sub")
    _release_all_my_tours(driver_token, driver_id, la_token)
    _ensure_no_trailer(driver_token, driver_id)

    t1 = _create_tour(la_token, "active1")
    t2 = _create_tour(la_token, "active2")
    try:
        r = requests.put(f"{API}/tours/{t1['id']}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id, "on_way": True},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, r.text

        # Second simultaneous on_way without trailer → must 409.
        r = requests.put(f"{API}/tours/{t2['id']}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id, "on_way": True},
            headers=_h(driver_token), timeout=15)
        assert r.status_code == 409, (
            f"Capacity-check should have blocked 2nd on_way, got {r.status_code} {r.text}"
        )
    finally:
        # Release first to allow cleanup
        try:
            requests.put(f"{API}/tours/{t1['id']}",
                json={"claimed_by": "", "claimed_by_id": "", "on_way": False},
                headers=_h(la_token), timeout=10)
        except Exception:
            pass
        _cleanup(t1["id"], la_token)
        _cleanup(t2["id"], la_token)
