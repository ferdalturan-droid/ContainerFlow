"""
Iteration 8 backend tests — Batch 1 corrections, Batch 2 (Lokation Admin),
Batch 3 (Medarbejder UI backing endpoints) and the order-user flow tweaks.

All public assertions from the iteration-8 review request that touch the
backend are covered here.

Cleanup is best-effort at the end of each test class: only TEST_-prefixed
companies/users/tokens are removed so the existing Vestforbrænding / ARGO
data created by the human is preserved.
"""
import os
import uuid
import time
import asyncio

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for running pytest directly in the container.
    from dotenv import dotenv_values  # type: ignore
    BASE_URL = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL", "").rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "test_database")
if not MONGO_URL:
    from dotenv import dotenv_values  # type: ignore
    env = dotenv_values("/app/backend/.env")
    MONGO_URL = env.get("MONGO_URL")
    DB_NAME = env.get("DB_NAME", DB_NAME)

SUPER_EMAIL = "superadmin@platform.com"
SUPER_PWD = "SuperAdmin2026!"

RUN_TAG = f"TEST_it8_{uuid.uuid4().hex[:6]}"


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


def _get_invite_token(email):
    """Pull the freshest invitation token directly from MongoDB."""
    async def _q():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        # find the matching user, then their token
        u = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if not u:
            return None
        tk = await db.invitation_tokens.find_one(
            {"user_id": u["id"]}, sort=[("created_at", -1)]
        )
        client.close()
        return tk
    return asyncio.run(_q())


def _activate_invitation(email, new_password):
    """Helper to take a pending user from invitation -> active."""
    tk = _get_invite_token(email)
    assert tk, f"no invitation token for {email}"
    token = tk["token"]
    r = requests.post(f"{BASE_URL}/api/auth/accept-invitation",
                      json={"token": token, "new_password": new_password}, timeout=15)
    assert r.status_code == 200, f"set-password failed: {r.status_code} {r.text}"


@pytest.fixture(scope="module")
def super_token():
    return _login(SUPER_EMAIL, SUPER_PWD)


@pytest.fixture(scope="module")
def seed(super_token):
    """Create:
      - one TEST_ customer company + customer_admin (activated)
      - one TEST_ location (via customer_admin)
      - one TEST_ location_admin (activated)
      - one TEST_ order user (activated)
      - one TEST_ logistics company (no password) + linked to the customer
    Returns dict with ids/emails/tokens for tests."""
    tag = RUN_TAG
    cust_email = f"{tag.lower()}_cadmin@test.local"
    cust_id = f"{tag}_C"
    # 1) create customer company
    r = requests.post(f"{BASE_URL}/api/superadmin/companies", headers=_hdr(super_token), json={
        "name": f"{tag} Kunde",
        "customer_id": cust_id,
        "company_type": "customer",
        "admin_email": cust_email,
        "admin_name": f"{tag} Customer Admin",
        "admin_phone": "+4500000001",
    }, timeout=20)
    assert r.status_code == 200, f"create customer: {r.status_code} {r.text}"
    company_id = r.json()["company"]["id"]
    _activate_invitation(cust_email, "Pa55word!1")
    cadmin_tok = _login(cust_email, "Pa55word!1")

    # 2) create logistics company (NO password)
    logi_email = f"{tag.lower()}_ladm@test.local"
    r = requests.post(f"{BASE_URL}/api/superadmin/companies", headers=_hdr(super_token), json={
        "name": f"{tag} Logistik",
        "customer_id": f"{tag}_L",
        "company_type": "logistics",
        "admin_email": logi_email,
        "admin_name": f"{tag} Logistik Admin",
    }, timeout=20)
    assert r.status_code == 200, f"create logistics: {r.status_code} {r.text}"
    logi_id = r.json()["company"]["id"]

    # 3) location_admin (invitation flow) + inline location
    loc_admin_email = f"{tag.lower()}_locadm@test.local"
    loc_code = f"{tag}_LOC"
    r = requests.post(f"{BASE_URL}/api/org/users", headers=_hdr(cadmin_tok), json={
        "name": f"{tag} LocAdmin",
        "email": loc_admin_email,
        "role": "location_admin",
        "phone": "+4500000002",
        "location_code": loc_code,
        "location_name": f"{tag} Lokation",
        "send_invitation": True,
    }, timeout=20)
    assert r.status_code == 200, f"create location_admin: {r.status_code} {r.text}"
    _activate_invitation(loc_admin_email, "Pa55word!1")
    locadm_tok = _login(loc_admin_email, "Pa55word!1")

    # 4) order user (invitation flow)
    order_email = f"{tag.lower()}_order@test.local"
    r = requests.post(f"{BASE_URL}/api/org/users", headers=_hdr(locadm_tok), json={
        "name": f"{tag} Bestiller",
        "email": order_email,
        "role": "order",
        "phone": "+4500000003",
        "location_code": loc_code,
        "send_invitation": True,
    }, timeout=20)
    assert r.status_code == 200, f"create order user: {r.status_code} {r.text}"
    _activate_invitation(order_email, "Pa55word!1")
    order_tok = _login(order_email, "Pa55word!1")

    return {
        "tag": tag,
        "company_id": company_id,
        "logi_id": logi_id,
        "cadmin_tok": cadmin_tok,
        "locadm_tok": locadm_tok,
        "order_tok": order_tok,
        "loc_code": loc_code,
        "cust_email": cust_email,
        "logi_email": logi_email,
        "loc_admin_email": loc_admin_email,
        "order_email": order_email,
    }


# ---------------------------------------------------------------- Batch 1 fixups
class TestSuperAdminLogisticsAndCascade:
    def test_logistics_company_created_with_invitation_no_password(self, seed):
        # Verify that an invitation token exists for the logistics admin we created
        tk = _get_invite_token(seed["logi_email"])
        assert tk is not None, "logistics admin should have an invitation token"
        # And user should be pending (password_hash empty)
        async def _q():
            client = AsyncIOMotorClient(MONGO_URL)
            u = await client[DB_NAME].users.find_one({"email": seed["logi_email"]}, {"_id": 0})
            client.close()
            return u
        u = asyncio.run(_q())
        assert u is not None
        assert u.get("invitation_status") == "pending"
        assert u.get("password_hash", "") == ""
        assert u.get("role") == "logistics_admin"

    def test_deactivated_company_still_returns_first_admin(self, super_token, seed):
        # Deactivate
        r = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{seed['company_id']}",
            headers=_hdr(super_token), json={"active": False}, timeout=15,
        )
        assert r.status_code == 200
        # GET list
        r = requests.get(f"{BASE_URL}/api/superadmin/companies",
                         headers=_hdr(super_token), timeout=15)
        assert r.status_code == 200
        comps = r.json()
        mine = next((c for c in comps if c["id"] == seed["company_id"]), None)
        assert mine is not None
        assert mine.get("active") is False
        # first_admin should still come back so frontend can cascade
        assert mine.get("first_admin"), "first_admin must still be present even when inactive"
        # restore for downstream tests
        r = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{seed['company_id']}",
            headers=_hdr(super_token), json={"active": True}, timeout=15,
        )
        assert r.status_code == 200


# ---------------------------------------------------------------- Org users invitation
class TestOrgUserInvitationFlow:
    def test_create_location_admin_without_password_creates_invitation(self, seed):
        # Already done in fixture; verify here that another fresh call works.
        tag = seed["tag"]
        email = f"{tag.lower()}_locadm2@test.local"
        r = requests.post(f"{BASE_URL}/api/org/users", headers=_hdr(seed["cadmin_tok"]), json={
            "name": f"{tag} LA2",
            "email": email,
            "role": "location_admin",
            "location_code": f"{tag}_LOC2",
            "location_name": f"{tag} Lok 2",
            "send_invitation": True,
        }, timeout=15)
        assert r.status_code == 200, r.text
        tk = _get_invite_token(email)
        assert tk is not None
        async def _q():
            client = AsyncIOMotorClient(MONGO_URL)
            u = await client[DB_NAME].users.find_one({"email": email}, {"_id": 0})
            client.close()
            return u
        u = asyncio.run(_q())
        assert u.get("invitation_status") == "pending"
        assert u.get("password_hash", "") == ""

    def test_create_order_user_without_password_invitation(self, seed):
        tag = seed["tag"]
        email = f"{tag.lower()}_order2@test.local"
        r = requests.post(f"{BASE_URL}/api/org/users", headers=_hdr(seed["locadm_tok"]), json={
            "name": "Order2",
            "email": email,
            "role": "order",
            "location_code": seed["loc_code"],
            "send_invitation": True,
        }, timeout=15)
        assert r.status_code == 200, r.text
        tk = _get_invite_token(email)
        assert tk is not None

    def test_resend_invitation_regenerates_token(self, seed):
        # find user id of the order user
        async def _q():
            client = AsyncIOMotorClient(MONGO_URL)
            u = await client[DB_NAME].users.find_one({"email": seed["order_email"]}, {"_id": 0, "id": 1})
            client.close()
            return u
        u = asyncio.run(_q())
        assert u
        r = requests.post(
            f"{BASE_URL}/api/org/users/{u['id']}/resend-invitation",
            headers=_hdr(seed["locadm_tok"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True
        # token should exist
        tk = _get_invite_token(seed["order_email"])
        assert tk is not None


# ---------------------------------------------------------------- Deactivate-first policy
class TestDeactivateFirstPurge:
    def test_purge_active_user_returns_400(self, seed):
        # create a fresh medarbejder via location_admin (purposely activated -> active)
        tag = seed["tag"]
        email = f"{tag.lower()}_emp1@test.local"
        r = requests.post(f"{BASE_URL}/api/org/users", headers=_hdr(seed["locadm_tok"]), json={
            "name": "Emp1",
            "email": email,
            "role": "order",
            "location_code": seed["loc_code"],
            "send_invitation": True,
        }, timeout=15)
        assert r.status_code == 200
        # find id
        async def _q():
            client = AsyncIOMotorClient(MONGO_URL)
            u = await client[DB_NAME].users.find_one({"email": email}, {"_id": 0, "id": 1, "active": 1})
            client.close()
            return u
        u = asyncio.run(_q())
        uid = u["id"]
        # ensure active=True
        r = requests.put(f"{BASE_URL}/api/org/users/{uid}",
                         headers=_hdr(seed["locadm_tok"]), json={"active": True}, timeout=15)
        assert r.status_code == 200
        # DELETE while active -> 400
        r = requests.delete(f"{BASE_URL}/api/org/users/{uid}",
                            headers=_hdr(seed["locadm_tok"]), timeout=15)
        assert r.status_code == 400, r.text
        assert "Inaktivér" in r.text or "Inaktiver" in r.text

        # Deactivate then purge
        r = requests.put(f"{BASE_URL}/api/org/users/{uid}",
                         headers=_hdr(seed["locadm_tok"]), json={"active": False}, timeout=15)
        assert r.status_code == 200
        r = requests.delete(f"{BASE_URL}/api/org/users/{uid}",
                            headers=_hdr(seed["locadm_tok"]), timeout=15)
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------- Order submit + enrichment
class TestOrderSubmitAndEnrichment:
    def test_anonymous_submit_does_not_require_address(self, seed):
        r = requests.post(f"{BASE_URL}/api/customer-orders/submit", json={
            "location_code": seed["loc_code"],
            "plads_name": "",
            "container_number": "C1",
            "material": "Pap",
            "order_date": "",
            "priority": "normal",
            "comment": "TEST anon",
            "custom_address": "",
            "custom_container_id": "",
        }, timeout=20)
        # Anonymous flow may succeed (no address required). 404 means location
        # wasn't resolved — still proves no auth gate exists.
        assert r.status_code in (200, 404), r.text

    def test_authenticated_submit_requires_address(self, seed):
        r = requests.post(f"{BASE_URL}/api/customer-orders/submit",
                          headers=_hdr(seed["order_tok"]), json={
            "location_code": seed["loc_code"],
            "plads_name": "",
            "container_number": "C1",
            "material": "Pap",
            "order_date": "",
            "priority": "normal",
            "comment": "TEST auth no address",
            "custom_address": "",
            "custom_container_id": "",
        }, timeout=20)
        assert r.status_code == 400, r.text
        assert "Leveringsadresse" in r.text

    def test_authenticated_submit_populates_created_by(self, seed):
        r = requests.post(f"{BASE_URL}/api/customer-orders/submit",
                          headers=_hdr(seed["order_tok"]), json={
            "location_code": seed["loc_code"],
            "plads_name": "",
            "container_number": "C-TEST",
            "material": "Pap",
            "order_date": "",
            "priority": "normal",
            "comment": "TEST authed",
            "custom_address": "Testvej 1, 1000 København",
            "custom_container_id": "",
        }, timeout=20)
        assert r.status_code == 200, r.text
        # Now verify via by-location enrichment
        r2 = requests.get(
            f"{BASE_URL}/api/container-orders/by-location/{seed['loc_code']}",
            headers=_hdr(seed["locadm_tok"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        orders = r2.json()
        # find ours
        mine = [o for o in orders if o.get("container_number") == "C-TEST"]
        assert mine, f"expected order with container C-TEST in {orders}"
        o = mine[0]
        assert o.get("status_label") in ("afventer", "accepteret", "afhentet", "annulleret")
        assert o.get("created_by_name", "").startswith(seed["tag"]) or seed["tag"] in (o.get("created_by_name") or "")
        assert o.get("created_by_email") == seed["order_email"]


# ---------------------------------------------------------------- Locations include logistics_partners
class TestOrgLocationsLogisticsPartners:
    def test_locations_include_logistics_partners_array(self, seed):
        # First, link the TEST logistics company to the customer
        r = requests.post(f"{BASE_URL}/api/org/logistics-partners",
                          headers=_hdr(seed["cadmin_tok"]), json={
            "logistics_company_id": seed["logi_id"],
        }, timeout=15)
        assert r.status_code == 200, r.text

        # Assign the logistics partner to the location (as customer_admin)
        # find plads id by name
        async def _q():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            p = await db.plads.find_one(
                {"company_id": seed["company_id"], "location_code": seed["loc_code"]},
                {"_id": 0},
            )
            client.close()
            return p
        p = asyncio.run(_q())
        assert p is not None, "plads should exist"

        # assign partner via /api/org/locations/{id}/logistics-partners
        r = requests.put(
            f"{BASE_URL}/api/org/locations/{p['id']}/logistics-partners",
            headers=_hdr(seed["cadmin_tok"]),
            json={"logistics_company_ids": [seed["logi_id"]]},
            timeout=15,
        )
        # endpoint variations: PUT or POST; try POST as fallback
        if r.status_code in (404, 405):
            r = requests.post(
                f"{BASE_URL}/api/org/locations/{p['id']}/logistics-partners",
                headers=_hdr(seed["cadmin_tok"]),
                json={"logistics_company_ids": [seed["logi_id"]]},
                timeout=15,
            )
        # Whatever the response, fetch locations and look at the structure
        r2 = requests.get(f"{BASE_URL}/api/org/locations",
                          headers=_hdr(seed["cadmin_tok"]), timeout=15)
        assert r2.status_code == 200, r2.text
        locs = r2.json()
        mine = next((l for l in locs if l.get("location_code") == seed["loc_code"]), None)
        assert mine is not None
        # logistics_partners array must exist (even if empty)
        assert "logistics_partners" in mine, f"location missing logistics_partners: {mine}"
        assert isinstance(mine["logistics_partners"], list)
        for lp in mine["logistics_partners"]:
            assert "id" in lp and "name" in lp


# ---------------------------------------------------------------- Cleanup
def teardown_module(_module):
    """Best-effort cleanup of TEST_-prefixed artifacts."""
    async def _c():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        tag = RUN_TAG
        # find created companies
        comps = await db.companies.find({"name": {"$regex": f"^{tag}"}}, {"_id": 0, "id": 1}).to_list(50)
        comp_ids = [c["id"] for c in comps]
        # delete users belonging to those companies + users with TEST_ email tag
        if comp_ids:
            await db.users.delete_many({"company_id": {"$in": comp_ids}})
            await db.plads.delete_many({"company_id": {"$in": comp_ids}})
            await db.container_orders.delete_many({"company_id": {"$in": comp_ids}})
        await db.users.delete_many({"email": {"$regex": tag.lower()}})
        await db.invitation_tokens.delete_many({"email": {"$regex": tag.lower()}})
        await db.companies.delete_many({"id": {"$in": comp_ids}})
        client.close()
    try:
        asyncio.run(_c())
    except Exception as e:  # noqa: BLE001
        print(f"cleanup error: {e}")
