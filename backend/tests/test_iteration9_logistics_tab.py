"""
Iteration 9 backend smoke — verifies the dedicated logistics-partners
catalog flows used by the new SuperAdmin "Tilføj logistik partner" tab.

These are extra checks on top of /app/backend/tests/test_iteration8_batch2_batch3.py
(which already covers no-password logistics creation + first_admin in
GET /superadmin/companies). Here we additionally verify that
/api/org/logistics-companies (customer-admin's picker) sees the new partner.

Cleanup: every created company/user/token is tagged with RUN_TAG and
removed in teardown_module.
"""
import os
import uuid
import asyncio

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values  # type: ignore

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL", "").rstrip("/")

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or env.get("DB_NAME", "test_database")

SUPER_EMAIL = "superadmin@platform.com"
SUPER_PWD = "SuperAdmin2026!"

RUN_TAG = f"TEST_it9_{uuid.uuid4().hex[:6]}"


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


def _get_invite_token(email):
    async def _q():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        u = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if not u:
            client.close()
            return None
        tk = await db.invitation_tokens.find_one(
            {"user_id": u["id"]}, sort=[("created_at", -1)]
        )
        client.close()
        return tk
    return asyncio.run(_q())


def _accept(email, pw):
    tk = _get_invite_token(email)
    assert tk, f"no invite for {email}"
    r = requests.post(f"{BASE_URL}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": pw}, timeout=15)
    assert r.status_code == 200


@pytest.fixture(scope="module")
def super_token():
    return _login(SUPER_EMAIL, SUPER_PWD)


@pytest.fixture(scope="module")
def state():
    return {}


# -- ITERATION 9 CHECKS ------------------------------------------------------

def test_create_logistics_partner_no_password(super_token, state):
    """POST /api/superadmin/companies w/ company_type=logistics + admin_email."""
    payload = {
        "name": f"{RUN_TAG} Logi ApS",
        "company_type": "logistics",
        "customer_id": f"L9{uuid.uuid4().hex[:3].upper()}",
        "active": True,
        "admin_name": f"{RUN_TAG} Admin",
        "admin_email": f"{RUN_TAG}.adm@test.dk".lower(),
        "admin_phone": "+45 22 22 22 22",
    }
    r = requests.post(f"{BASE_URL}/api/superadmin/companies",
                      json=payload, headers=_hdr(super_token), timeout=15)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    company = j.get("company") or j
    admin = j.get("created_admin") or {}
    assert company.get("id")
    assert company.get("company_type") == "logistics"
    assert company.get("customer_id") == payload["customer_id"]
    state["company_id"] = company["id"]
    state["admin_email"] = payload["admin_email"]
    # The admin must be in pending status (invitation flow, no password).
    assert admin.get("invitation_status") == "pending" or admin.get("email") == payload["admin_email"]
    # And an invitation token row must exist
    tk = _get_invite_token(payload["admin_email"])
    assert tk and tk.get("token"), "expected an invitation_tokens row"


def test_get_superadmin_companies_includes_first_admin(super_token, state):
    r = requests.get(f"{BASE_URL}/api/superadmin/companies",
                     headers=_hdr(super_token), timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    logi = next((c for c in rows if c.get("id") == state["company_id"]), None)
    assert logi is not None, "newly-created logistics company not in /superadmin/companies"
    assert logi.get("company_type") == "logistics"
    fa = logi.get("first_admin") or {}
    assert fa.get("email") == state["admin_email"], f"first_admin mismatch: {fa}"
    assert fa.get("invitation_status") == "pending"


def test_catalog_visible_to_customer_admin(super_token, state):
    """Create a temporary customer + admin, log in as that admin, then verify
    /api/org/logistics-companies returns our new logistics partner."""
    cust_email = f"{RUN_TAG}.cust@test.dk".lower()
    cust_payload = {
        "name": f"{RUN_TAG} Kunde A/S",
        "company_type": "customer",
        "customer_id": f"K9{uuid.uuid4().hex[:3].upper()}",
        "active": True,
        "admin_name": f"{RUN_TAG} Kunde Admin",
        "admin_email": cust_email,
    }
    r = requests.post(f"{BASE_URL}/api/superadmin/companies",
                      json=cust_payload, headers=_hdr(super_token), timeout=15)
    assert r.status_code in (200, 201), r.text
    state["customer_company_id"] = (r.json().get("company") or r.json())["id"]
    state["customer_admin_email"] = cust_email

    # Activate the customer admin via invitation
    pw = "Customer2026!"
    _accept(cust_email, pw)
    tok = _login(cust_email, pw)

    # Customer-admin picker endpoint
    r2 = requests.get(f"{BASE_URL}/api/org/logistics-companies",
                      headers=_hdr(tok), timeout=15)
    assert r2.status_code == 200, r2.text
    rows = r2.json()
    found = next((c for c in rows if c.get("id") == state["company_id"]), None)
    assert found is not None, "logistics partner not found in /api/org/logistics-companies catalog"
    assert "linked" in found and found["linked"] is False  # not yet linked
    assert found.get("name", "").startswith(RUN_TAG)


def teardown_module(module):
    """Best-effort cleanup of all RUN_TAG-prefixed rows."""
    async def _clean():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        comps = await db.companies.find({"name": {"$regex": f"^{RUN_TAG}"}}, {"_id": 0, "id": 1}).to_list(50)
        cids = [c["id"] for c in comps]
        if cids:
            await db.companies.delete_many({"id": {"$in": cids}})
            users = await db.users.find({"company_id": {"$in": cids}}, {"_id": 0, "id": 1}).to_list(200)
            uids = [u["id"] for u in users]
            if uids:
                await db.users.delete_many({"id": {"$in": uids}})
                await db.invitation_tokens.delete_many({"user_id": {"$in": uids}})
        # belt-and-suspenders: kill any leftover users by email regex
        await db.users.delete_many({"email": {"$regex": RUN_TAG.lower()}})
        client.close()
    try:
        asyncio.run(_clean())
    except Exception as exc:  # pragma: no cover
        print(f"[teardown] warning: {exc}")
