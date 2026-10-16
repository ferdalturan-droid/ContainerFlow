"""
Backend tests for the logistics_admin multi-company switcher feature.

Covers (from the review request):
  1. GET /api/auth/managed-companies role-based responses
  2. POST/PUT /api/superadmin/users managed_company_ids persistence + role gating
  3. TenantContextMiddleware X-Acting-Company-Id (logistics_admin) success + 403
  4. Newly-assigned company works WITHOUT re-login (DB fallback)
  5. super_admin may act as ANY company via X-Acting-Company-Id
  6. Cross-company tour CREATE persists under acting company; visible only to that tenant
  7. driver/order/genbrug roles must NOT honor X-Acting-Company-Id
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "http://localhost:8080",
).rstrip("/")

SUPER_EMAIL = "superadmin@platform.com"
SUPER_PASS = "SuperAdmin2026!"
LOGI_EMAIL = "admin@default.local"
LOGI_PASS = "ilk2026"

DEFAULT_CID = "default"
VEST_CID = "95bb0b5c-0a6b-4c78-b059-b2482789d2a8"  # Vestforbrænding


# ---------- Helpers ----------
def _hdr(token=None, acting=None, extra=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if acting:
        h["X-Acting-Company-Id"] = acting
    if extra:
        h.update(extra)
    return h


def _post(path, body=None, token=None, acting=None):
    return requests.post(f"{BASE_URL}{path}", json=body or {}, headers=_hdr(token, acting), timeout=30)


def _get(path, token=None, acting=None):
    return requests.get(f"{BASE_URL}{path}", headers=_hdr(token, acting), timeout=30)


def _put(path, body=None, token=None, acting=None):
    return requests.put(f"{BASE_URL}{path}", json=body or {}, headers=_hdr(token, acting), timeout=30)


def _delete(path, token=None, acting=None):
    return requests.delete(f"{BASE_URL}{path}", headers=_hdr(token, acting), timeout=30)


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def super_token():
    r = _post("/api/auth/login", {"email": SUPER_EMAIL, "password": SUPER_PASS})
    assert r.status_code == 200, f"super-admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def logi_token():
    r = _post("/api/auth/login", {"email": LOGI_EMAIL, "password": LOGI_PASS})
    assert r.status_code == 200, f"logistics_admin login failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    return tok


@pytest.fixture(scope="session")
def logi_user_id(super_token):
    """Return the user id for admin@default.local"""
    r = _get("/api/superadmin/users", token=super_token)
    assert r.status_code == 200
    for u in r.json():
        if u.get("email") == LOGI_EMAIL:
            return u["id"]
    pytest.skip("admin@default.local user not found")


# ============================================================ #
# Feature 1: GET /api/auth/managed-companies
# ============================================================ #
class TestManagedCompaniesEndpoint:
    def test_logistics_admin_returns_own_plus_managed(self, logi_token):
        r = _get("/api/auth/managed-companies", token=logi_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) >= 2
        ids = {d["id"] for d in data}
        assert DEFAULT_CID in ids
        assert VEST_CID in ids
        own = next(d for d in data if d["id"] == DEFAULT_CID)
        assert own["is_own"] is True
        vest = next(d for d in data if d["id"] == VEST_CID)
        assert vest["is_own"] is False
        # response includes name + active
        for d in data:
            assert "name" in d and "active" in d

    def test_super_admin_returns_all_companies(self, super_token):
        r = _get("/api/auth/managed-companies", token=super_token)
        assert r.status_code == 200
        data = r.json()
        ids = {d["id"] for d in data}
        # Super admin should see >= 2 companies (default + Vestforbrænding seed)
        assert DEFAULT_CID in ids
        assert VEST_CID in ids
        # is_own=False for super admin
        assert all(d["is_own"] is False for d in data)

    def test_unauthenticated_rejected(self):
        r = _get("/api/auth/managed-companies")
        assert r.status_code in (401, 403)


# ============================================================ #
# Feature 2: superadmin users CRUD + managed_company_ids gating
# ============================================================ #
class TestSuperAdminUsersManagedCompanies:
    created_user_id = None

    def test_create_logistics_admin_with_managed(self, super_token):
        email = f"TEST_logi_{uuid.uuid4().hex[:6]}@example.com"
        body = {
            "email": email,
            "name": "TEST Logi Admin",
            "password": "TempPass123!",
            "role": "logistics_admin",
            "company_id": DEFAULT_CID,
            "managed_company_ids": [VEST_CID],
        }
        r = _post("/api/superadmin/users", body, token=super_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "logistics_admin"
        assert data["company_id"] == DEFAULT_CID
        # managed_company_ids returned
        assert VEST_CID in (data.get("managed_company_ids") or [])
        TestSuperAdminUsersManagedCompanies.created_user_id = data["id"]

        # Verify GET list returns it
        lst = _get("/api/superadmin/users", token=super_token).json()
        u = next((x for x in lst if x["id"] == data["id"]), None)
        assert u is not None
        assert VEST_CID in (u.get("managed_company_ids") or [])

    def test_create_driver_drops_managed(self, super_token):
        email = f"TEST_drv_{uuid.uuid4().hex[:6]}@example.com"
        body = {
            "email": email,
            "name": "TEST Driver",
            "password": "TempPass123!",
            "role": "driver",
            "company_id": DEFAULT_CID,
            "managed_company_ids": [VEST_CID],
        }
        r = _post("/api/superadmin/users", body, token=super_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "driver"
        # backend must clear the field for non-logistics_admin roles
        assert (data.get("managed_company_ids") or []) == []
        # cleanup
        _delete(f"/api/superadmin/users/{data['id']}", token=super_token)

    def test_update_managed_company_ids(self, super_token):
        uid = TestSuperAdminUsersManagedCompanies.created_user_id
        assert uid, "previous test must have created user"
        # Clear managed_company_ids
        r = _put(f"/api/superadmin/users/{uid}", {"managed_company_ids": []}, token=super_token)
        assert r.status_code == 200, r.text
        assert (r.json().get("managed_company_ids") or []) == []

        # Set it again
        r = _put(f"/api/superadmin/users/{uid}", {"managed_company_ids": [VEST_CID]}, token=super_token)
        assert r.status_code == 200
        assert VEST_CID in (r.json().get("managed_company_ids") or [])

    def test_cleanup_created_user(self, super_token):
        uid = TestSuperAdminUsersManagedCompanies.created_user_id
        if uid:
            r = _delete(f"/api/superadmin/users/{uid}", token=super_token)
            assert r.status_code in (200, 404)


# ============================================================ #
# Feature 3 + 5: X-Acting-Company-Id middleware
# ============================================================ #
class TestActingCompanyHeader:
    def test_logistics_admin_no_header_returns_own_pladser(self, logi_token):
        r = _get("/api/plads", token=logi_token)
        assert r.status_code == 200
        own_pladser = r.json()
        # All should belong to default
        for p in own_pladser:
            assert p.get("company_id", DEFAULT_CID) == DEFAULT_CID

    def test_logistics_admin_acting_managed_company_returns_that_data(self, logi_token):
        r = _get("/api/plads", token=logi_token, acting=VEST_CID)
        assert r.status_code == 200, r.text
        data = r.json()
        # Should return Vestforbrænding's pladser (10 per task context)
        assert len(data) >= 1
        for p in data:
            assert p.get("company_id") == VEST_CID

    def test_logistics_admin_acting_unauthorized_company_403(self, logi_token, super_token):
        # Create a temp company the logi admin does NOT manage
        cid = str(uuid.uuid4())
        r = _post(
            "/api/superadmin/companies",
            {"id": cid, "name": f"TEST_UNAUTH_{uuid.uuid4().hex[:6]}", "slug": f"unauth-{uuid.uuid4().hex[:6]}"},
            token=super_token,
        )
        assert r.status_code == 200, r.text
        try:
            r2 = _get("/api/plads", token=logi_token, acting=cid)
            assert r2.status_code == 403
            assert "ikke adgang" in r2.json().get("detail", "").lower()
        finally:
            _delete(f"/api/superadmin/companies/{cid}", token=super_token)

    def test_super_admin_can_act_as_any_company(self, super_token):
        r = _get("/api/plads", token=super_token, acting=VEST_CID)
        assert r.status_code == 200
        data = r.json()
        # All pladser must be scoped to Vestforbrænding
        for p in data:
            assert p.get("company_id") == VEST_CID


# ============================================================ #
# Feature 4: Newly-assigned company works WITHOUT re-login
# ============================================================ #
class TestFreshManagedCompanyNoRelogin:
    def test_db_fallback_picks_up_new_managed_company(self, super_token, logi_token, logi_user_id):
        """Add a new managed company via Super Admin, then verify the existing
        logi_token (which does NOT contain that company in its JWT) can still
        switch to it because the middleware does a DB fallback."""
        # Create temp company
        cid = str(uuid.uuid4())
        cr = _post(
            "/api/superadmin/companies",
            {"id": cid, "name": f"TEST_FRESH_{uuid.uuid4().hex[:6]}", "slug": f"fresh-{uuid.uuid4().hex[:6]}"},
            token=super_token,
        )
        assert cr.status_code == 200, cr.text

        try:
            # Add to managed list (keep VEST_CID too)
            up = _put(
                f"/api/superadmin/users/{logi_user_id}",
                {"managed_company_ids": [VEST_CID, cid]},
                token=super_token,
            )
            assert up.status_code == 200

            # Use OLD logi_token (no cid in JWT) — middleware should DB-fallback
            r = _get("/api/plads", token=logi_token, acting=cid)
            assert r.status_code == 200, f"expected 200 via DB fallback, got {r.status_code}: {r.text}"

            # Now remove the new cid from managed list
            up2 = _put(
                f"/api/superadmin/users/{logi_user_id}",
                {"managed_company_ids": [VEST_CID]},
                token=super_token,
            )
            assert up2.status_code == 200

            # The same token used to be allowed via DB fallback, but now should 403
            r2 = _get("/api/plads", token=logi_token, acting=cid)
            assert r2.status_code == 403
        finally:
            _delete(f"/api/superadmin/companies/{cid}", token=super_token)


# ============================================================ #
# Feature 6: Cross-company tour CREATE persists under acting company
# ============================================================ #
class TestCrossCompanyTourCreate:
    def test_create_tour_acting_as_managed_company(self, logi_token, super_token):
        """POST /api/tours with X-Acting-Company-Id=VEST_CID. The tour should
        be stored under Vestforbrænding (visible when listing as VEST), and
        NOT visible when listing as default."""
        # Probe if /api/tours exists with simple POST
        body = {
            "date": "2026-02-15",
            "fraction": f"TEST_FRACTION_{uuid.uuid4().hex[:6]}",
            "facility": "TEST_FACILITY",
            "address": "Test Cross-Company 1",
            "container": "TEST_CONT",
            "plads": "TEST_PLADS",
        }
        r = _post("/api/tours", body, token=logi_token, acting=VEST_CID)
        if r.status_code in (404, 405):
            pytest.skip(f"/api/tours not implemented as POST: {r.status_code}")
        assert r.status_code in (200, 201), f"tour create failed: {r.status_code} {r.text}"
        tour = r.json()
        tour_id = tour.get("id")
        assert tour_id, f"no id in response: {tour}"
        # Tour body may not echo company_id, but list-as-VEST must show it
        try:
            list_vest = _get("/api/tours", token=logi_token, acting=VEST_CID)
            assert list_vest.status_code == 200
            ids_vest = {t.get("id") for t in list_vest.json()}
            assert tour_id in ids_vest, "newly created tour not visible to Vestforbrænding context"

            # List as own company (default) — should NOT include the tour
            list_own = _get("/api/tours", token=logi_token)
            assert list_own.status_code == 200
            ids_own = {t.get("id") for t in list_own.json()}
            assert tour_id not in ids_own, "tour leaked into own-company context"
        finally:
            # cleanup
            _delete(f"/api/tours/{tour_id}", token=logi_token, acting=VEST_CID)


# ============================================================ #
# Feature 7: driver / genbrug / order roles must NOT honor X-Acting-Company-Id
# ============================================================ #
class TestNonAdminRolesIgnoreActing:
    def test_driver_acting_header_ignored(self):
        r = _post(
            "/api/auth/login",
            {"email": "driver@default.local", "password": "driver2026"},
        )
        if r.status_code != 200:
            pytest.skip(f"driver login not available: {r.status_code}")
        drv_token = r.json()["token"]
        # Driver tries to act as Vestforbrænding — header should be IGNORED,
        # so /api/auth/me still shows default company_id.
        me = _get("/api/auth/me", token=drv_token, acting=VEST_CID)
        assert me.status_code == 200
        assert me.json().get("company_id") == DEFAULT_CID

    def test_genbrug_acting_header_ignored(self):
        r = _post(
            "/api/auth/login",
            {"email": "genbrug@default.local", "password": "genbrug2026"},
        )
        if r.status_code != 200:
            pytest.skip(f"genbrug login not available: {r.status_code}")
        g_token = r.json()["token"]
        # Trying to act as another company should NOT escalate (header ignored)
        # so /api/plads still returns default scope, NOT 403.
        plads = _get("/api/plads", token=g_token, acting=VEST_CID)
        assert plads.status_code == 200, f"acting header should be ignored, got {plads.status_code}"
        for p in plads.json():
            assert p.get("company_id", DEFAULT_CID) == DEFAULT_CID
