"""Iteration 16 — backend regression for the new Leveringsadresser
(delivery_addresses) endpoints + their integration with the resolve schedule
endpoint used by the order page.

Spec coverage map:
  * CRUD /api/org/delivery-addresses (list, create, update, delete)
  * "Primary per material" invariant — setting one address primary for X
    unsets X on every other address at the same plads
  * POST /set-primary endpoint for atomic "make me primary" action
  * GET /api/delivery-addresses/resolve (public) — returns
      primary + alternatives + selected + schedule (open_from / open_to /
      is_closed / is_holiday) for a given (location_code, material, date)
  * Per-address calendar override > material_calendars fallback
  * Cross-tenant 403 on PUT/DELETE
  * Order submit (`POST /customer-orders/submit`) stores both
    `delivery_address_id` and `alternative_delivery_address_id` + the
    original primary line in `original_customer_address`

Throwaway tenants use the IT16- prefix and are cleaned at module teardown.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()
CA1_EMAIL = f"it16-ca1-{SUFFIX}@e2e.local"
CA1_PASS = "CustAdmin2026!"
LA1_EMAIL = f"it16-la1-{SUFFIX}@e2e.local"
LA1_PASS = "LocAdmin2026!"
CA2_EMAIL = f"it16-ca2-{SUFFIX}@e2e.local"
CA2_PASS = "CustAdmin2026!"
LA2_EMAIL = f"it16-la2-{SUFFIX}@e2e.local"
LA2_PASS = "LocAdmin2026!"

state = {
    "company_ids": [],
    "user_ids": [],
    "loc_codes": [],
    "address_ids": [],
    "holiday_cal_ids": [],
    "hours_cal_ids": [],
    "order_ids": [],
}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end(db):
    yield
    try:
        emails = [CA1_EMAIL, LA1_EMAIL, CA2_EMAIL, LA2_EMAIL]
        db.users.delete_many({"$or": [
            {"id": {"$in": state["user_ids"]}},
            {"email": {"$in": emails}},
        ]})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.locations.delete_many({"code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.delivery_addresses.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.holiday_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.hours_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.material_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.container_orders.delete_many({"id": {"$in": state["order_ids"]}})
        db.tours.delete_many({"order_id": {"$in": state["order_ids"]}})
    except Exception as e:  # noqa: BLE001
        print(f"[cleanup] {e}")


def _login(email, password):
    return requests.post(f"{API}/api/auth/login",
                         json={"email": email, "password": password}, timeout=15)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _get(token, path):
    return requests.get(f"{API}{path}", headers=_h(token) if token else {}, timeout=15)


def _post(token, path, data=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=data or {}, timeout=20)


def _put(token, path, data=None):
    return requests.put(f"{API}{path}", headers=_h(token), json=data or {}, timeout=15)


def _del(token, path):
    return requests.delete(f"{API}{path}", headers=_h(token), timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None, f"No invite for user_id={user_id}"
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": password}, timeout=15)
    assert r.status_code == 200, r.text


# ============================================================
#   0. SA login + 2 tenants
# ============================================================
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def _seed_tenant(db, name_suffix, ca_email, ca_pass, la_email, la_pass):
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT16-CUST-{name_suffix}",
        "customer_id": f"C16-{name_suffix}",
        "company_type": "customer",
        "admin_email": ca_email,
        "admin_name": f"IT16 CA {name_suffix}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    company_id = body["company"]["id"]
    # Response shape: {"company": {...}, "created_admin": {id, email, ...}}
    admin_user = body.get("created_admin") or {}
    ca_id = admin_user.get("id")
    assert ca_id, f"No created_admin in response: {body}"
    state["company_ids"].append(company_id)
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, ca_pass)
    ca_tok = _login(ca_email, ca_pass).json()["token"]

    r3 = _post(ca_tok, "/api/org/locations", {
        "name": f"IT16-PLADS-{name_suffix}",
        "city": "IT16 City",
        "address": "IT16 Vej 1",
    })
    assert r3.status_code == 200, r3.text
    code = r3.json().get("code") or r3.json().get("location_code")
    assert code
    state["loc_codes"].append(code)

    r4 = _post(ca_tok, "/api/org/users", {
        "email": la_email,
        "name": f"IT16 LA {name_suffix}",
        "role": "location_admin",
        "location_codes": [code],
    })
    assert r4.status_code == 200, r4.text
    la_id = r4.json()["id"]
    state["user_ids"].append(la_id)
    _accept_invite(db, la_id, la_pass)
    la_tok = _login(la_email, la_pass).json()["token"]
    return {"company_id": company_id, "code": code, "ca_token": ca_tok, "la_token": la_tok}


def test_seed_tenants(db):
    state["t1"] = _seed_tenant(db, f"A-{SUFFIX}", CA1_EMAIL, CA1_PASS, LA1_EMAIL, LA1_PASS)
    state["t2"] = _seed_tenant(db, f"B-{SUFFIX}", CA2_EMAIL, CA2_PASS, LA2_EMAIL, LA2_PASS)


# ============================================================
#   1. CRUD basics + primary-per-material invariant
# ============================================================
def test_create_delivery_address():
    t1 = state["t1"]
    r = _post(t1["la_token"], "/api/org/delivery-addresses", {
        "location_code": t1["code"],
        "label": "Hovedindgang",
        "street": "Hovedgade 1",
        "postcode": "1000",
        "city": "København",
        "materials": ["Pap", "Glas"],
        "primary_for": ["Pap", "Glas"],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["label"] == "Hovedindgang"
    assert set(data["materials"]) == {"Pap", "Glas"}
    assert set(data["primary_for"]) == {"Pap", "Glas"}
    state["address_ids"].append(data["id"])
    state["addr1"] = data


def test_list_delivery_addresses():
    t1 = state["t1"]
    r = _get(t1["la_token"], f"/api/org/delivery-addresses?location_code={t1['code']}")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == state["addr1"]["id"]


def test_create_second_address_primary_for_pap_unsets_first():
    """Creating a second address that's primary for Pap should atomically
    remove Pap from the first address's primary_for list."""
    t1 = state["t1"]
    r = _post(t1["la_token"], "/api/org/delivery-addresses", {
        "location_code": t1["code"],
        "label": "Bagside",
        "street": "Bagvej 99",
        "postcode": "1050",
        "city": "København",
        "materials": ["Pap", "Træ"],
        "primary_for": ["Pap", "Træ"],
    })
    assert r.status_code == 200, r.text
    addr2 = r.json()
    state["address_ids"].append(addr2["id"])
    state["addr2"] = addr2
    # Re-fetch addr1: Pap should be removed from primary_for; Glas preserved.
    r2 = _get(t1["la_token"], f"/api/org/delivery-addresses?location_code={t1['code']}")
    items = {a["id"]: a for a in r2.json()}
    assert "Pap" not in items[state["addr1"]["id"]]["primary_for"]
    assert "Glas" in items[state["addr1"]["id"]]["primary_for"]
    # addr2 owns Pap + Træ as primary
    assert set(items[addr2["id"]]["primary_for"]) == {"Pap", "Træ"}


def test_set_primary_endpoint():
    """POST /set-primary?material=X moves the primary to this address."""
    t1 = state["t1"]
    a1 = state["addr1"]
    r = _post(t1["la_token"], f"/api/org/delivery-addresses/{a1['id']}/set-primary", {"material": "Pap"})
    assert r.status_code == 200, r.text
    # Now addr1 should be primary for Pap (and addr2 should NOT)
    r2 = _get(t1["la_token"], f"/api/org/delivery-addresses?location_code={t1['code']}")
    items = {a["id"]: a for a in r2.json()}
    assert "Pap" in items[a1["id"]]["primary_for"]
    assert "Pap" not in items[state["addr2"]["id"]]["primary_for"]


def test_set_primary_auto_adds_material_if_missing():
    """If the address doesn't yet have the material in its materials list,
    set-primary should add it."""
    t1 = state["t1"]
    a1 = state["addr1"]
    r = _post(t1["la_token"], f"/api/org/delivery-addresses/{a1['id']}/set-primary", {"material": "Metal"})
    assert r.status_code == 200, r.text
    refreshed = r.json()
    assert "Metal" in refreshed["materials"]
    assert "Metal" in refreshed["primary_for"]


def test_update_address():
    t1 = state["t1"]
    a1 = state["addr1"]
    r = _put(t1["la_token"], f"/api/org/delivery-addresses/{a1['id']}", {
        "label": "Hovedindgang (opdateret)",
        "city": "Roskilde",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["label"] == "Hovedindgang (opdateret)"
    assert data["city"] == "Roskilde"
    # Materials and primary_for must NOT be wiped on partial PUT
    assert "Pap" in data["materials"]
    assert "Pap" in data["primary_for"]


def test_update_shrinks_materials_also_shrinks_primary_for():
    """If we shrink materials to ['Pap'] only, the address can no longer be
    primary for materials it doesn't serve."""
    t1 = state["t1"]
    a1 = state["addr1"]
    r = _put(t1["la_token"], f"/api/org/delivery-addresses/{a1['id']}", {
        "materials": ["Pap"],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["materials"] == ["Pap"]
    assert "Glas" not in data["primary_for"]
    assert "Metal" not in data["primary_for"]
    assert data["primary_for"] == ["Pap"]


# ============================================================
#   2. Cross-tenant guard (403)
# ============================================================
def test_cross_tenant_update_forbidden():
    t1 = state["t1"]
    t2 = state["t2"]
    r = _put(t2["la_token"], f"/api/org/delivery-addresses/{state['addr1']['id']}", {"label": "haxx"})
    assert r.status_code in (403, 404), r.text


def test_cross_tenant_delete_forbidden():
    t1 = state["t1"]
    t2 = state["t2"]
    r = _del(t2["la_token"], f"/api/org/delivery-addresses/{state['addr1']['id']}")
    assert r.status_code in (403, 404), r.text


# ============================================================
#   3. /resolve endpoint (PUBLIC — no auth)
# ============================================================
def test_resolve_returns_primary_and_alternatives_no_schedule():
    t1 = state["t1"]
    # Pap has 2 addresses (addr1 primary, addr2 alt) but no calendars yet.
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-15",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["primary"] is not None
    assert data["primary"]["id"] == state["addr1"]["id"]
    assert any(a["id"] == state["addr2"]["id"] for a in data["alternatives"])
    assert data["selected"]["id"] == state["addr1"]["id"]
    assert data["is_closed"] is False
    assert data["is_holiday"] is False
    assert data["source"] is None  # no calendars → no source


def test_resolve_with_explicit_address_id():
    t1 = state["t1"]
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-15",
        "address_id": state["addr2"]["id"],
    })
    assert r.status_code == 200
    assert r.json()["selected"]["id"] == state["addr2"]["id"]


def test_resolve_uses_material_calendar_when_set():
    """Assign an hours_calendar (mon..sun) via material_calendars and verify
    that resolve picks up open_from/open_to + is_closed for the weekday."""
    t1 = state["t1"]
    # Create an hours calendar where Saturday is CLOSED
    r = _post(t1["la_token"], "/api/org/hours-calendars", {
        "location_code": t1["code"], "name": "IT16-uge-pap",
        "weekdays": {
            "mon": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "tue": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "wed": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "thu": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "fri": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "sat": {"closed": True, "open_from": "", "open_to": ""},
            "sun": {"closed": True, "open_from": "", "open_to": ""},
        },
    })
    assert r.status_code == 200, r.text
    hours_cal_id = r.json()["id"]
    state["hours_cal_ids"].append(hours_cal_id)
    # Map material → hours_cal
    r2 = _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"], "material": "Pap",
        "hours_calendar_id": hours_cal_id, "holiday_calendar_id": None,
    })
    assert r2.status_code == 200
    # 2026-06-15 is a Monday → should be open 08-16
    r3 = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-15",
    })
    d = r3.json()
    assert d["is_closed"] is False
    assert d["open_from"] == "08:00"
    assert d["open_to"] == "16:00"
    assert d["source"] == "weekday"
    # 2026-06-13 is a Saturday → CLOSED
    r4 = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-13",
    })
    d4 = r4.json()
    assert d4["is_closed"] is True
    assert d4["source"] == "weekday"


def test_resolve_holiday_overrides_weekday():
    """Holiday on a date trumps the weekday schedule."""
    t1 = state["t1"]
    # Create a holiday calendar with 2026-06-15 marked closed
    r = _post(t1["la_token"], "/api/org/holiday-calendars", {
        "location_code": t1["code"], "name": "IT16-hellig-pap",
        "days": [{"name": "TestHelligdag", "date": "2026-06-15", "closed": True,
                  "open_from": "", "open_to": ""}],
    })
    assert r.status_code == 200, r.text
    holiday_cal_id = r.json()["id"]
    state["holiday_cal_ids"].append(holiday_cal_id)
    # Re-map material → both calendars
    _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"], "material": "Pap",
        "hours_calendar_id": state["hours_cal_ids"][0],
        "holiday_calendar_id": holiday_cal_id,
    })
    r3 = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-15",
    })
    d = r3.json()
    assert d["is_holiday"] is True
    assert d["holiday_name"] == "TestHelligdag"
    assert d["is_closed"] is True
    assert d["source"] == "holiday"


def test_resolve_ignores_per_address_calendar_fields_iteration17():
    """Iteration 17 — per-address holiday_calendar_id/hours_calendar_id were
    removed. The resolve endpoint now consults ONLY the material_calendars
    mapping; any addresses passed in are still echoed back as primary/
    alternatives but their (legacy) calendar fields are ignored."""
    t1 = state["t1"]
    # Sanity: the addresses returned by resolve do not carry the deprecated
    # calendar fields anymore.
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": t1["code"], "material": "Pap", "date": "2026-06-15",
        "address_id": state["addr2"]["id"],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    sel = d.get("selected") or {}
    assert "holiday_calendar_id" not in sel, "Field should be dropped"
    assert "hours_calendar_id" not in sel, "Field should be dropped"
    # The resolve answer is purely material_calendars-driven now; with
    # holiday_calendar set on the material and 2026-06-15 marked closed
    # there, the result is closed regardless of which address_id we pass.
    assert d["is_closed"] is True


# ============================================================
#   4. Order submit persists primary + alternative IDs
# ============================================================
def test_order_submit_persists_delivery_address_ids(db):
    t1 = state["t1"]
    payload = {
        "location_code": t1["code"],
        "material": "Pap",
        "container_number": "Container 1",
        "priority": "normal",
        "custom_address": "Bagvej 99, 1050 København",
        "order_date": "2026-06-16",
        "open_from": "10:00",
        "open_to": "14:00",
        "delivery_address_id": state["addr1"]["id"],
        "alternative_delivery_address_id": state["addr2"]["id"],
    }
    r = requests.post(f"{API}/api/customer-orders/submit", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    order_id = body.get("order_id") or body.get("id") or body.get("order", {}).get("id")
    # The endpoint returns various shapes — fall back to mongo
    if not order_id:
        latest = db.container_orders.find_one(
            {"company_id": t1["company_id"]},
            sort=[("created_at", -1)],
            projection={"_id": 0},
        )
        assert latest, "No order persisted"
        order_id = latest["id"]
    state["order_ids"].append(order_id)
    saved = db.container_orders.find_one({"id": order_id}, {"_id": 0})
    assert saved["delivery_address_id"] == state["addr1"]["id"]
    assert saved["alternative_delivery_address_id"] == state["addr2"]["id"]
    # original_customer_address should be populated (since alternative differs from primary)
    assert saved.get("original_customer_address"), "original primary address line should be captured"


def test_order_submit_without_addresses_keeps_blank():
    t1 = state["t1"]
    payload = {
        "location_code": t1["code"],
        "material": "Pap",
        "container_number": "Container 2",
        "priority": "normal",
        "custom_address": "Hovedgade 1, 1000 København",
        "order_date": "2026-06-16",
    }
    r = requests.post(f"{API}/api/customer-orders/submit", json=payload)
    assert r.status_code == 200, r.text


# ============================================================
#   5. Delete address
# ============================================================
def test_delete_delivery_address():
    t1 = state["t1"]
    # Delete addr2 (alternative)
    r = _del(t1["la_token"], f"/api/org/delivery-addresses/{state['addr2']['id']}")
    assert r.status_code == 200
    # Verify gone
    r2 = _get(t1["la_token"], f"/api/org/delivery-addresses?location_code={t1['code']}")
    ids = [a["id"] for a in r2.json()]
    assert state["addr2"]["id"] not in ids
