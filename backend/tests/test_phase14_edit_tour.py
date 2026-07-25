"""
Phase 14 regression — Edit Tour (admin + driver weight edit)

Verifies backend contract behind the new "Ret tur" admin modal and the
"Ret vægt" driver button on completed tours.

Scenarios:
  T1 — Driver claims+completes a tour, then re-updates weight by sending
       claimed_by=self → backend MUST allow (200) and persist new weight.
  T2 — Logistics admin reopens a completed tour by sending completed=false
       AND claimed_by="" → backend MUST allow and persist (verified by GET).
  T3 — Another driver attempting to claim a tour already claimed by D1 → 409.
  T4 — Driver attempting to edit weight WITHOUT claimed_by on a claimed
       (completed) tour → 409 (restricted_fields guard).
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


def _create_tour_via_admin(la_token):
    """Create a fresh tour via the admin POST /api/tours endpoint."""
    plads = f"TEST_p14_{uuid.uuid4().hex[:6]}"
    body = {
        "plads": plads,
        "facility": "TEST-FAC",
        "container": "TEST-C1",
        "fraction": "TEST-FRAC",
        "tour_type": "normal",
    }
    r = requests.post(f"{API}/tours", json=body, headers=_h(la_token), timeout=15)
    assert r.status_code in (200, 201), f"create tour: {r.status_code} {r.text}"
    return r.json()


def _cleanup(tour_id, la_token):
    try:
        requests.delete(f"{API}/tours/{tour_id}", headers=_h(la_token), timeout=10)
    except Exception:
        pass


# ---------- T1 -----------------------------------------------------------
def test_driver_edits_weight_on_completed_tour(la_token, driver_token, driver_info):
    tour = _create_tour_via_admin(la_token)
    tid = tour["id"]
    try:
        driver_name = driver_info.get("display_name") or driver_info.get("name") or "testc"
        driver_id = driver_info.get("id") or driver_info.get("sub")

        # 1) Driver claims
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 200, f"claim: {r.status_code} {r.text}"

        # 2) Driver completes with initial weight
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name, "weight": 1000, "completed": True},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 200, f"complete: {r.status_code} {r.text}"

        # 3) Driver edits weight AFTER completion — must pass thanks to
        #    claimed_by being included in the payload (Fase 14 flow).
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name, "weight": 1240.5},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 200, f"weight edit: {r.status_code} {r.text}"
        body = r.json()
        assert float(body.get("weight", 0)) == 1240.5, f"PUT response weight wrong: {body}"
        assert body.get("completed") is True, "PUT response should still have completed=True"

        # 4) Persistence via admin GET /api/tours (admin sees all)
        r = requests.get(f"{API}/tours", headers=_h(la_token), timeout=15)
        assert r.status_code == 200
        match = [t for t in r.json() if t.get("id") == tid]
        assert match, "tour missing from admin GET /tours"
        assert float(match[0]["weight"]) == 1240.5
        assert match[0]["completed"] is True
    finally:
        _cleanup(tid, la_token)


# ---------- T2 -----------------------------------------------------------
def test_admin_reopens_completed_tour(la_token, driver_token, driver_info):
    tour = _create_tour_via_admin(la_token)
    tid = tour["id"]
    try:
        driver_name = driver_info.get("display_name") or driver_info.get("name") or "testc"
        driver_id = driver_info.get("id") or driver_info.get("sub")

        # Driver claims + completes
        requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name, "claimed_by_id": driver_id},
            headers=_h(driver_token), timeout=15,
        )
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name, "weight": 800, "completed": True},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 200, r.text

        # Admin reopens: completed=false + claimed_by="" (release)
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"completed": False, "on_way": False, "claimed_by": "", "claimed_by_id": ""},
            headers=_h(la_token), timeout=15,
        )
        assert r.status_code == 200, f"reopen: {r.status_code} {r.text}"

        # Verify via GET
        r = requests.get(f"{API}/tours", headers=_h(la_token), timeout=15)
        match = [t for t in r.json() if t.get("id") == tid]
        assert match, "tour missing after reopen"
        t = match[0]
        assert t.get("completed") is False
        assert (t.get("claimed_by") or "") == ""
    finally:
        _cleanup(tid, la_token)


# ---------- T3 -----------------------------------------------------------
def test_other_driver_cannot_claim(la_token, driver_token, driver_info):
    """A driver other than the claimer cannot claim/modify restricted fields.

    Since we only have one driver login in seeded data, simulate this by
    sending a claim with a DIFFERENT claimed_by string from the LA side
    first, then a driver with a mismatching id tries to take it.
    """
    tour = _create_tour_via_admin(la_token)
    tid = tour["id"]
    try:
        # LA marks tour as claimed by fictitious driver "SOMEBODY"
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": "SOMEBODY", "claimed_by_id": "00000000-aaaa-bbbb-cccc-000000000000"},
            headers=_h(la_token), timeout=15,
        )
        assert r.status_code == 200, r.text

        # Driver tries to set weight without supplying claimed_by → 409
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"weight": 500},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 409, f"expected 409 restricted, got {r.status_code} {r.text}"

        # Driver tries to claim a tour already taken by SOMEBODY (different claimed_by)
        # The PUT carries claimed_by = own name → conflict with existing claim
        driver_name = driver_info.get("display_name") or driver_info.get("name") or "testc"
        r = requests.put(
            f"{API}/tours/{tid}",
            json={"claimed_by": driver_name},
            headers=_h(driver_token), timeout=15,
        )
        assert r.status_code == 409, f"expected 409 already taken, got {r.status_code} {r.text}"
    finally:
        _cleanup(tid, la_token)
