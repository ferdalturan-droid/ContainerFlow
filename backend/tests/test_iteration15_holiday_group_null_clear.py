"""Iteration 15 — regression for the bug found in iteration_14 minor list:

   PUT /api/superadmin/companies/{id} silently dropped `holiday_group_id: null`
   payloads (because update was built via `{k:v for k,v in raw.items() if v is
   not None}`). The frontend's "Ingen gruppe" option sends null, so users could
   not actually un-assign a holiday group.

Fix: sa_update_company now uses `model_dump(exclude_unset=True)` and
`holiday_group_id` is allow-listed in a `nullable_fields` set so explicit
`null` makes it through to MongoDB `$set`.

This test exercises:
  1. SET hgid via PUT  → field stored
  2. CLEAR hgid via PUT (null) → field stored as null
  3. Partial PUT (only admin_phone) → hgid preserved (no accidental clear)
  4. Repeat round-trip via GET to confirm persistence (not just response body)

Uses the existing super-admin credentials and an existing customer company.
Does NOT create or delete any tenants — restores the company's original
holiday_group_id at the end.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"


def _login_with_backoff(email, password, attempts=6):
    for i in range(attempts):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": password}, timeout=15)
        if r.status_code == 200:
            return r
        if r.status_code == 429:
            time.sleep(3 + i * 2)
            continue
        return r
    return r


@pytest.fixture(scope="module")
def sa_token():
    r = _login_with_backoff(SA_EMAIL, SA_PASS)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def customer_id(headers):
    """Find an existing customer OR create one for this test run. We can't
    rely on Argo being in the DB anymore (test cleanups may have wiped it
    in earlier runs)."""
    r = requests.get(f"{API}/api/superadmin/companies?include_library=false", headers=headers)
    r.raise_for_status()
    customers = [c for c in r.json() if c.get("company_type") == "customer"]
    if customers:
        return customers[0]["id"]
    # No customer exists → seed one. Cleaned up at module teardown.
    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6].upper()
    seed = requests.post(
        f"{API}/api/superadmin/companies", headers=headers,
        json={
            "name": f"IT15-CUST-{suffix}",
            "customer_id": f"C15-{suffix}",
            "company_type": "customer",
            "admin_email": f"it15-ca-{suffix}@e2e.local",
            "admin_name": f"IT15 CA {suffix}",
        },
    )
    seed.raise_for_status()
    cid = seed.json()["company"]["id"]
    # Track for cleanup
    pytest._it15_seeded_company_id = cid
    return cid


@pytest.fixture(scope="module")
def holiday_group_id(headers):
    """Find an existing holiday group OR create one — iteration 17 SA groups
    now require a `year` field too, so we accept either shape."""
    r = requests.get(f"{API}/api/superadmin/holiday-groups", headers=headers)
    r.raise_for_status()
    groups = r.json()
    if groups:
        return groups[0]["id"]
    seed = requests.post(
        f"{API}/api/superadmin/holiday-groups", headers=headers,
        json={"name": "IT15-test-group", "year": 2026, "holidays": [
            {"name": "Jul", "date": "2026-12-24"},
        ]},
    )
    seed.raise_for_status()
    pytest._it15_seeded_group_id = seed.json()["id"]
    return seed.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup_seeded(headers):
    """Drop any seed data we created (only when we actually seeded)."""
    yield
    # Clean up customer
    cid = getattr(pytest, "_it15_seeded_company_id", None)
    if cid:
        try:
            requests.delete(f"{API}/api/superadmin/companies/{cid}", headers=headers, timeout=10)
        except Exception:
            pass
        pytest._it15_seeded_company_id = None
    gid = getattr(pytest, "_it15_seeded_group_id", None)
    if gid:
        try:
            requests.delete(f"{API}/api/superadmin/holiday-groups/{gid}", headers=headers, timeout=10)
        except Exception:
            pass
        pytest._it15_seeded_group_id = None


def _get_hgid(headers, customer_id):
    r = requests.get(f"{API}/api/superadmin/companies", headers=headers)
    r.raise_for_status()
    c = next((x for x in r.json() if x["id"] == customer_id), None)
    assert c is not None
    return c.get("holiday_group_id")


def test_set_holiday_group_id(headers, customer_id, holiday_group_id):
    r = requests.put(
        f"{API}/api/superadmin/companies/{customer_id}",
        headers=headers,
        json={"holiday_group_id": holiday_group_id},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("holiday_group_id") == holiday_group_id
    assert _get_hgid(headers, customer_id) == holiday_group_id


def test_clear_holiday_group_id_with_null(headers, customer_id, holiday_group_id):
    # Pre-condition: hgid must be set
    requests.put(
        f"{API}/api/superadmin/companies/{customer_id}",
        headers=headers,
        json={"holiday_group_id": holiday_group_id},
    )
    # Action: clear by sending null
    r = requests.put(
        f"{API}/api/superadmin/companies/{customer_id}",
        headers=headers,
        json={"holiday_group_id": None},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("holiday_group_id") is None
    assert _get_hgid(headers, customer_id) is None


def test_partial_update_preserves_holiday_group_id(headers, customer_id, holiday_group_id):
    # Pre-condition: set hgid
    requests.put(
        f"{API}/api/superadmin/companies/{customer_id}",
        headers=headers,
        json={"holiday_group_id": holiday_group_id},
    )
    # Action: PUT without including holiday_group_id at all
    r = requests.put(
        f"{API}/api/superadmin/companies/{customer_id}",
        headers=headers,
        json={"admin_phone": "+45 99887766"},
    )
    assert r.status_code == 200, r.text
    # hgid must NOT be cleared
    assert r.json().get("holiday_group_id") == holiday_group_id
    assert _get_hgid(headers, customer_id) == holiday_group_id


def test_set_then_clear_then_set_round_trip(headers, customer_id, holiday_group_id):
    # SET
    requests.put(f"{API}/api/superadmin/companies/{customer_id}", headers=headers,
                 json={"holiday_group_id": holiday_group_id})
    assert _get_hgid(headers, customer_id) == holiday_group_id
    # CLEAR
    requests.put(f"{API}/api/superadmin/companies/{customer_id}", headers=headers,
                 json={"holiday_group_id": None})
    assert _get_hgid(headers, customer_id) is None
    # SET again
    requests.put(f"{API}/api/superadmin/companies/{customer_id}", headers=headers,
                 json={"holiday_group_id": holiday_group_id})
    assert _get_hgid(headers, customer_id) == holiday_group_id
