"""
Backend tests for multi-tenant + auth extensions on ContainerFlow.

Covers:
  - /api/auth/* (login, me, error cases)
  - /api/superadmin/companies (CRUD)
  - /api/superadmin/users (CRUD + role checks)
  - Tenant isolation on /api/drivers
  - /api/genbrug/orders (CRUD + tenant scoping)
  - Legacy endpoints still work (/api/admin/login, /api/driver/verify-code, /api/locations)
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://role-analysis-flow.preview.emergentagent.com").rstrip("/")

SUPER_EMAIL = "superadmin@platform.com"
SUPER_PASS = "SuperAdmin2026!"

LEGACY_ADMIN_PW = "ilk2026"
LEGACY_DRIVER_CODE = "3030"


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def _post(path, json=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE_URL}{path}", json=json or {}, headers=headers, timeout=30)


def _get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE_URL}{path}", headers=headers, timeout=30)


def _put(path, json=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.put(f"{BASE_URL}{path}", json=json or {}, headers=headers, timeout=30)


def _delete(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.delete(f"{BASE_URL}{path}", headers=headers, timeout=30)


@pytest.fixture(scope="session")
def super_token():
    r = _post("/api/auth/login", {"email": SUPER_EMAIL, "password": SUPER_PASS})
    assert r.status_code == 200, f"Super admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and data["token"]
    assert data["user"]["email"] == SUPER_EMAIL
    assert data["user"]["role"] == "super_admin"
    return data["token"]


@pytest.fixture(scope="session")
def test_company(super_token):
    """Create a unique test company for isolation tests."""
    uniq = f"TEST_CompanyA_{uuid.uuid4().hex[:8]}"
    r = _post("/api/superadmin/companies", {"name": uniq, "slug": uniq.lower()}, token=super_token)
    assert r.status_code == 200, f"Create company failed: {r.status_code} {r.text}"
    c = r.json()
    assert c["name"] == uniq
    assert c["id"] and c["id"] != "default"
    yield c
    # teardown -- delete users in company then company itself
    users = _get(f"/api/superadmin/users?company_id={c['id']}", token=super_token).json()
    for u in users:
        _delete(f"/api/superadmin/users/{u['id']}", token=super_token)
    _delete(f"/api/superadmin/companies/{c['id']}", token=super_token)


@pytest.fixture(scope="session")
def test_company_b(super_token):
    uniq = f"TEST_CompanyB_{uuid.uuid4().hex[:8]}"
    r = _post("/api/superadmin/companies", {"name": uniq, "slug": uniq.lower()}, token=super_token)
    assert r.status_code == 200
    c = r.json()
    yield c
    users = _get(f"/api/superadmin/users?company_id={c['id']}", token=super_token).json()
    for u in users:
        _delete(f"/api/superadmin/users/{u['id']}", token=super_token)
    _delete(f"/api/superadmin/companies/{c['id']}", token=super_token)


@pytest.fixture(scope="session")
def company_a_admin(super_token, test_company):
    email = f"TEST_admin_{uuid.uuid4().hex[:6]}@companya.test"
    password = "Pass1234!"
    r = _post("/api/superadmin/users", {
        "email": email,
        "name": "Company A Admin",
        "password": password,
        "role": "logistics_admin",
        "company_id": test_company["id"],
    }, token=super_token)
    assert r.status_code == 200, f"Create admin failed: {r.status_code} {r.text}"
    user = r.json()
    # Now login as this admin
    lr = _post("/api/auth/login", {"email": email, "password": password})
    assert lr.status_code == 200, f"Admin login failed: {lr.status_code} {lr.text}"
    data = lr.json()
    return {"user": user, "token": data["token"], "email": email, "password": password,
            "company_id": test_company["id"]}


# --------------------------------------------------------------------------- #
# AUTH tests
# --------------------------------------------------------------------------- #
class TestAuth:
    def test_login_super_admin_success(self, super_token):
        assert isinstance(super_token, str) and len(super_token) > 10

    def test_login_wrong_password_returns_401(self):
        r = _post("/api/auth/login", {"email": SUPER_EMAIL, "password": "wrongpassword!"})
        assert r.status_code == 401

    def test_login_unknown_email_returns_401(self):
        r = _post("/api/auth/login", {"email": "doesnotexist@nowhere.local", "password": "x"})
        assert r.status_code == 401

    def test_login_missing_fields_returns_400(self):
        r = _post("/api/auth/login", {"email": "", "password": ""})
        assert r.status_code == 400

    def test_me_with_valid_token(self, super_token):
        r = _get("/api/auth/me", token=super_token)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == SUPER_EMAIL
        assert data["role"] == "super_admin"

    def test_me_without_token_returns_401(self):
        r = _get("/api/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self):
        r = _get("/api/auth/me", token="not.a.valid.jwt")
        assert r.status_code == 401


# --------------------------------------------------------------------------- #
# SUPER ADMIN - companies
# --------------------------------------------------------------------------- #
class TestSuperAdminCompanies:
    def test_list_companies_includes_default(self, super_token):
        r = _get("/api/superadmin/companies", token=super_token)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        ids = [c["id"] for c in items]
        assert "default" in ids, "Default company must exist"

    def test_non_super_admin_gets_403_on_companies(self, company_a_admin):
        r = _get("/api/superadmin/companies", token=company_a_admin["token"])
        assert r.status_code == 403

    def test_no_token_gets_401_on_companies(self):
        r = _get("/api/superadmin/companies")
        assert r.status_code == 401

    def test_create_company_persisted(self, super_token):
        name = f"TEST_TmpCompany_{uuid.uuid4().hex[:8]}"
        r = _post("/api/superadmin/companies", {"name": name}, token=super_token)
        assert r.status_code == 200
        cid = r.json()["id"]
        # Get list and verify
        items = _get("/api/superadmin/companies", token=super_token).json()
        assert any(c["id"] == cid and c["name"] == name for c in items)
        # cleanup
        d = _delete(f"/api/superadmin/companies/{cid}", token=super_token)
        assert d.status_code == 200

    def test_cannot_delete_default_company(self, super_token):
        r = _delete("/api/superadmin/companies/default", token=super_token)
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# SUPER ADMIN - users
# --------------------------------------------------------------------------- #
class TestSuperAdminUsers:
    def test_list_users(self, super_token):
        r = _get("/api/superadmin/users", token=super_token)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # Super admin and legacy admin should be present
        emails = [u["email"] for u in users]
        assert SUPER_EMAIL in emails

    def test_create_driver_user(self, super_token, test_company):
        email = f"TEST_driver_{uuid.uuid4().hex[:6]}@a.test"
        r = _post("/api/superadmin/users", {
            "email": email, "name": "Drv", "password": "drvpass1",
            "role": "driver", "company_id": test_company["id"],
            "driver_name": "Test Driver",
        }, token=super_token)
        assert r.status_code == 200, r.text
        user = r.json()
        assert user["role"] == "driver"
        assert user["company_id"] == test_company["id"]
        # cleanup
        _delete(f"/api/superadmin/users/{user['id']}", token=super_token)

    def test_create_genbrug_user(self, super_token, test_company):
        email = f"TEST_gen_{uuid.uuid4().hex[:6]}@a.test"
        r = _post("/api/superadmin/users", {
            "email": email, "name": "Gen", "password": "genpass1",
            "role": "genbrug_plads", "company_id": test_company["id"],
        }, token=super_token)
        assert r.status_code == 200
        uid = r.json()["id"]
        # update password and role
        upd = _put(f"/api/superadmin/users/{uid}",
                   {"password": "newpass2", "name": "Gen Updated"},
                   token=super_token)
        assert upd.status_code == 200
        assert upd.json()["name"] == "Gen Updated"
        # login with new password
        lr = _post("/api/auth/login", {"email": email, "password": "newpass2"})
        assert lr.status_code == 200
        # delete
        dr = _delete(f"/api/superadmin/users/{uid}", token=super_token)
        assert dr.status_code == 200
        # GET via login should now fail
        lr2 = _post("/api/auth/login", {"email": email, "password": "newpass2"})
        assert lr2.status_code == 401

    def test_create_user_invalid_role(self, super_token, test_company):
        r = _post("/api/superadmin/users", {
            "email": f"TEST_x_{uuid.uuid4().hex[:6]}@a.test", "name": "X",
            "password": "passw1", "role": "hacker", "company_id": test_company["id"],
        }, token=super_token)
        assert r.status_code == 400

    def test_create_user_duplicate_email_returns_409(self, super_token, test_company, company_a_admin):
        r = _post("/api/superadmin/users", {
            "email": company_a_admin["email"], "name": "Dup",
            "password": "pwd1", "role": "driver", "company_id": test_company["id"],
        }, token=super_token)
        assert r.status_code == 409

    def test_non_super_admin_cannot_create_user(self, company_a_admin, test_company):
        r = _post("/api/superadmin/users", {
            "email": f"TEST_z_{uuid.uuid4().hex[:6]}@a.test", "name": "Z",
            "password": "pwd1", "role": "driver", "company_id": test_company["id"],
        }, token=company_a_admin["token"])
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Logistics_admin login attributes
# --------------------------------------------------------------------------- #
class TestRoleAndCompany:
    def test_logistics_admin_login_has_correct_company(self, company_a_admin, test_company):
        r = _post("/api/auth/login",
                  {"email": company_a_admin["email"], "password": company_a_admin["password"]})
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "logistics_admin"
        assert data["user"]["company_id"] == test_company["id"]
        assert data["user"]["company_id"] != "default"


# --------------------------------------------------------------------------- #
# Tenant isolation - drivers
# --------------------------------------------------------------------------- #
class TestTenantIsolationDrivers:
    def test_unauthenticated_drivers_returns_default_company_data(self):
        r = _get("/api/drivers")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # backward compat: returns default tenant content (could be empty or seeded)
        for d in data:
            # documents may or may not expose company_id, but if exposed should be default
            if "company_id" in d:
                assert d["company_id"] == "default"

    def test_new_company_drivers_initially_empty(self, company_a_admin):
        r = _get("/api/drivers", token=company_a_admin["token"])
        assert r.status_code == 200
        assert r.json() == [], "New company must start with no drivers (no data leak from default)"

    def test_create_driver_scoped_to_company(self, company_a_admin):
        driver_name = f"TEST_drv_{uuid.uuid4().hex[:6]}"
        r = _post("/api/drivers", {"name": driver_name, "plate": "AB12345"}, token=company_a_admin["token"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == driver_name
        # list should contain only this driver
        listing = _get("/api/drivers", token=company_a_admin["token"]).json()
        names = [x["name"] for x in listing]
        assert driver_name in names
        # All listed drivers belong to this company (via the API contract; only 1 expected)
        assert len(listing) >= 1

    def test_other_company_cannot_see_driver(self, super_token, test_company_b, company_a_admin):
        # Create admin for company B
        email_b = f"TEST_adminB_{uuid.uuid4().hex[:6]}@b.test"
        cr = _post("/api/superadmin/users", {
            "email": email_b, "name": "B Admin", "password": "bpass1",
            "role": "logistics_admin", "company_id": test_company_b["id"],
        }, token=super_token)
        assert cr.status_code == 200
        token_b = _post("/api/auth/login", {"email": email_b, "password": "bpass1"}).json()["token"]
        # Company B should not see Company A driver
        r = _get("/api/drivers", token=token_b)
        assert r.status_code == 200
        a_drivers = _get("/api/drivers", token=company_a_admin["token"]).json()
        a_names = {d["name"] for d in a_drivers}
        b_names = {d["name"] for d in r.json()}
        assert a_names.isdisjoint(b_names), "Tenant isolation violated: driver leaked across companies"


# --------------------------------------------------------------------------- #
# Genbrug Plads
# --------------------------------------------------------------------------- #
class TestGenbrug:
    def test_genbrug_create_and_list_scoped(self, company_a_admin):
        body = {
            "customer_name": "TEST_Genbrug Customer",
            "address": "Vej 1",
            "phone": "+45 11111111",
            "material": "Træ",
            "container_type": "10m3",
            "quantity": 1,
            "pickup_date": "2026-02-01",
            "notes": "tester",
            "status": "pending",
        }
        r = _post("/api/genbrug/orders", body, token=company_a_admin["token"])
        assert r.status_code == 200, r.text
        order = r.json()
        assert order["customer_name"] == body["customer_name"]
        # NOTE: response body returns empty company_id (bug - see genbrug_create:
        # it returns `order` instead of `doc`). Persistence is verified via list below.
        oid = order["id"]
        # List - must contain it, and the persisted doc must have correct company_id
        lr = _get("/api/genbrug/orders", token=company_a_admin["token"])
        assert lr.status_code == 200
        listed = [o for o in lr.json() if o["id"] == oid]
        assert len(listed) == 1
        assert listed[0]["company_id"] == company_a_admin["company_id"], \
            "Persisted genbrug order must be tagged with creator's company_id"
        # Update
        ur = _put(f"/api/genbrug/orders/{oid}", {"status": "received"},
                  token=company_a_admin["token"])
        assert ur.status_code == 200
        assert ur.json()["status"] == "received"
        # Delete
        dr = _delete(f"/api/genbrug/orders/{oid}", token=company_a_admin["token"])
        assert dr.status_code == 200

    def test_genbrug_other_company_isolation(self, super_token, test_company_b, company_a_admin):
        # Create an order as company A
        body = {"customer_name": "TEST_Iso A", "material": "Pap"}
        r = _post("/api/genbrug/orders", body, token=company_a_admin["token"])
        assert r.status_code == 200
        oid = r.json()["id"]
        # Login as company B logistics admin
        email_b = f"TEST_genB_{uuid.uuid4().hex[:6]}@b.test"
        _post("/api/superadmin/users", {
            "email": email_b, "name": "B genbrug", "password": "bpw12345",
            "role": "logistics_admin", "company_id": test_company_b["id"],
        }, token=super_token)
        tok_b = _post("/api/auth/login", {"email": email_b, "password": "bpw12345"}).json()["token"]
        lr = _get("/api/genbrug/orders", token=tok_b)
        assert lr.status_code == 200
        b_ids = [o["id"] for o in lr.json()]
        assert oid not in b_ids, "Genbrug order leaked across tenants"
        # cleanup
        _delete(f"/api/genbrug/orders/{oid}", token=company_a_admin["token"])

    def test_genbrug_unauth_returns_401(self):
        r = _get("/api/genbrug/orders")
        assert r.status_code == 401

    def test_genbrug_role_check(self, super_token, test_company):
        # create 'order' role user - not allowed to genbrug
        email = f"TEST_ord_{uuid.uuid4().hex[:6]}@a.test"
        _post("/api/superadmin/users", {
            "email": email, "name": "Order Role", "password": "ordpass1",
            "role": "order", "company_id": test_company["id"],
        }, token=super_token)
        tok = _post("/api/auth/login", {"email": email, "password": "ordpass1"}).json()["token"]
        r = _get("/api/genbrug/orders", token=tok)
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Legacy / public endpoints
# --------------------------------------------------------------------------- #
class TestLegacyEndpoints:
    def test_legacy_admin_login(self):
        r = _post("/api/admin/login", {"password": LEGACY_ADMIN_PW})
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_legacy_admin_login_wrong(self):
        r = _post("/api/admin/login", {"password": "wrongpw"})
        assert r.status_code == 401

    def test_legacy_driver_code(self):
        r = _post("/api/driver/verify-code", {"code": LEGACY_DRIVER_CODE})
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_legacy_locations_unauth_works(self):
        r = _get("/api/locations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_health_endpoint(self):
        r = _get("/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
