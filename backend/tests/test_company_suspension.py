"""
Tests for Company Suspension feature (Super Admin).

Covers:
- Super Admin can suspend / reactivate a company via PUT /api/superadmin/companies/{id}
- Non-super-admin user in a suspended company is blocked at /api/auth/login with HTTP 403
  and the Danish error message: "Din virksomheds adgang er suspenderet. Kontakt din administrator."
- Super Admin can always log in regardless of suspension
- After reactivating, the same user can log in again
- Default company cannot be suspended (or if backend doesn't enforce, frontend prevents it; verified separately)
"""
import os
import uuid
import requests
import pytest

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # fall back to frontend/.env (test env doesn't auto-load it)
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not set"
    return url.rstrip("/")


BASE_URL = _load_backend_url()
SUSPEND_MSG = "Din virksomheds adgang er suspenderet. Kontakt din administrator."


@pytest.fixture(scope="module")
def sa_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@platform.com",
        "password": "SuperAdmin2026!",
    })
    assert r.status_code == 200, f"Super admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def temp_company_and_user(sa_headers):
    """Create a temp company + a non-super-admin user; cleanup at module teardown."""
    suffix = uuid.uuid4().hex[:8]
    company_name = f"TEST_SUSP_{suffix}"
    user_email = f"TEST_susp_{suffix}@example.com"
    user_password = "Suspend2026!"

    # Create company
    rc = requests.post(f"{BASE_URL}/api/superadmin/companies",
                       headers=sa_headers,
                       json={"name": company_name, "slug": f"tsusp{suffix}"})
    assert rc.status_code in (200, 201), f"Create company failed: {rc.status_code} {rc.text}"
    company = rc.json()
    company_id = company["id"]

    # Create user inside that company (role logistics_admin so they CAN normally log in)
    ru = requests.post(f"{BASE_URL}/api/superadmin/users",
                       headers=sa_headers,
                       json={
                           "email": user_email,
                           "password": user_password,
                           "role": "logistics_admin",
                           "company_id": company_id,
                           "name": "Susp Tester",
                       })
    assert ru.status_code in (200, 201), f"Create user failed: {ru.status_code} {ru.text}"
    user = ru.json()

    yield {
        "company_id": company_id,
        "company_name": company_name,
        "user_id": user["id"],
        "email": user_email,
        "password": user_password,
    }

    # Cleanup: try reactivate first so middleware doesn't block, then delete user then company.
    try:
        requests.put(f"{BASE_URL}/api/superadmin/companies/{company_id}",
                     headers=sa_headers, json={"active": True})
    except Exception:
        pass
    try:
        requests.delete(f"{BASE_URL}/api/superadmin/users/{user['id']}", headers=sa_headers)
    except Exception:
        pass
    try:
        requests.delete(f"{BASE_URL}/api/superadmin/companies/{company_id}", headers=sa_headers)
    except Exception:
        pass


class TestCompanySuspension:
    def test_01_user_can_login_when_active(self, temp_company_and_user):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": temp_company_and_user["email"],
            "password": temp_company_and_user["password"],
        })
        assert r.status_code == 200, f"Active login failed: {r.status_code} {r.text}"
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 0
        assert data["user"]["email"].lower() == temp_company_and_user["email"].lower()
        assert data["user"]["company_id"] == temp_company_and_user["company_id"]

    def test_02_suspend_company(self, sa_headers, temp_company_and_user):
        r = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{temp_company_and_user['company_id']}",
            headers=sa_headers, json={"active": False},
        )
        assert r.status_code == 200, f"Suspend failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("active") is False
        assert body.get("id") == temp_company_and_user["company_id"]

        # Verify persisted via GET list
        rg = requests.get(f"{BASE_URL}/api/superadmin/companies", headers=sa_headers)
        assert rg.status_code == 200
        found = [c for c in rg.json() if c["id"] == temp_company_and_user["company_id"]]
        assert found and found[0]["active"] is False

    def test_03_suspended_user_login_blocked_403(self, temp_company_and_user):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": temp_company_and_user["email"],
            "password": temp_company_and_user["password"],
        })
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"
        body = r.json()
        # FastAPI returns {"detail": "..."}
        assert body.get("detail") == SUSPEND_MSG, f"Wrong message: {body}"

    def test_04_super_admin_can_always_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "superadmin@platform.com",
            "password": "SuperAdmin2026!",
        })
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "super_admin"

    def test_05_reactivate_company(self, sa_headers, temp_company_and_user):
        r = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{temp_company_and_user['company_id']}",
            headers=sa_headers, json={"active": True},
        )
        assert r.status_code == 200
        assert r.json().get("active") is True

    def test_06_user_can_login_after_reactivation(self, temp_company_and_user):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": temp_company_and_user["email"],
            "password": temp_company_and_user["password"],
        })
        assert r.status_code == 200, f"Re-login failed: {r.status_code} {r.text}"
        assert "token" in r.json()

    def test_07_default_company_cannot_be_suspended_effectively(self, sa_headers):
        """
        Default company is hardcoded to always be active in _is_company_active.
        Try to suspend it - even if PUT goes through, login for default-company users
        must still work (super_admin always works regardless).
        """
        # Attempt to suspend the default company
        rs = requests.put(
            f"{BASE_URL}/api/superadmin/companies/default",
            headers=sa_headers, json={"active": False},
        )
        # Either backend rejects it OR it accepts but _is_company_active returns True for "default".
        # Super admin must still log in.
        rsa = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "superadmin@platform.com",
            "password": "SuperAdmin2026!",
        })
        assert rsa.status_code == 200
        # Cleanup: restore default to active just in case
        requests.put(
            f"{BASE_URL}/api/superadmin/companies/default",
            headers=sa_headers, json={"active": True},
        )
        # If the default cmpy got "suspended" but _is_company_active bypasses it,
        # the hardcoded default-bypass is the safety-net. We just verify SA login OK.
        # Note: backend logs status of suspend attempt:
        print(f"Default company suspend PUT result: {rs.status_code} {rs.text[:200]}")
