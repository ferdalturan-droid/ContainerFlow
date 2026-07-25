"""
Phase 15.2 (2026-06-19) — Admin-assigned tour visibility for driver.

Bug: GET /api/tours filtered with `active_cid` strict-AND with company_id
hid LA-created tours from drivers when the LA created them under their own
company (since the driver's active customer is e.g. ARGO, not LA's company).

Fix: partnership_clause is now an $or that also includes
`{driver_id: <driver_uid>}` so pre-assigned tours are ALWAYS visible to
the assigned driver regardless of which customer the tour belongs to.

Test:
- LA (ilkdistadmin) creates a manual tour (company_id = ILK's company).
- LA pre-assigns driver_id to driver test2.
- Driver GET /api/tours → tour MUST be in response.
- Driver PUT /api/tours/{id} with on_way=true → MUST return 200.
"""
import os
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
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {driver_token}"}, timeout=10)
    return r.json().get("id") or r.json().get("sub")


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def test_admin_preassigned_tour_visible_to_driver(la_token, driver_token, driver_id):
    body = {
        "plads": "DBG-vis-fix-15-2",
        "facility": "X",
        "container": "DBGV1",
        "fraction": "DBGVFRAC",
        "tour_type": "normal",
    }
    r = requests.post(f"{API}/tours", headers=_h(la_token), json=body, timeout=15)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    try:
        # LA pre-assigns driver_id
        r = requests.put(f"{API}/tours/{tid}", headers=_h(la_token),
            json={"driver_id": driver_id}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("assigned_by_name"), "assigned_by_name should be populated"

        # Driver fetches tours — pre-assigned tour MUST be in the list
        r = requests.get(f"{API}/tours", headers=_h(driver_token), timeout=15)
        assert r.status_code == 200, r.text
        ids = [t["id"] for t in r.json()]
        assert tid in ids, (
            f"Pre-assigned tour {tid} NOT visible to driver. "
            f"This is the iter37 'På vej' bug. Visible tours: {len(ids)}"
        )

        # Driver presses 'På vej' → must succeed
        r = requests.put(f"{API}/tours/{tid}", headers=_h(driver_token),
            json={"on_way": True, "on_way_time": "12:00",
                  "claimed_by": "testc", "claimed_by_id": driver_id}, timeout=15)
        assert r.status_code == 200, (
            f"Driver could not start admin-assigned tour: {r.status_code} {r.text}"
        )
        assert r.json().get("on_way") is True
    finally:
        requests.delete(f"{API}/tours/{tid}", headers=_h(la_token), timeout=10)
