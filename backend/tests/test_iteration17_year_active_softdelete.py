"""Iteration 17 — backend regression for the new soft-delete/activate flows
across Super Admin holiday-groups, LA holiday + hours calendars, and
materials. Also exercises the new free-text manual_alternative_address on
the customer-orders submit endpoint.

Spec coverage map:
  * SA holiday_groups now carry `year` + `active`
  * SA copy endpoint preserves names+dates and bumps the year suffix
  * SA toggle-active flips the `active` flag (deactivated groups remain
    usable for existing references but UI should hide them for new assignment)
  * SA delete is BLOCKED when any company references the group (409)
  * LA holiday + hours calendars carry `is_active` and `assigned_count`
  * LA holiday-calendar copy-from-group endpoint creates calendar pre-filled from SA group
  * LA hours-calendar copy endpoint creates a duplicate
  * LA toggle-active flips `is_active`
  * LA delete blocked when material_calendars row references it (409)
  * Material delete now blocked when orders/overrides/calendars reference
    it (409); toggle-active flow works as a soft-delete fallback
  * Order submit accepts manual_alternative_address and persists it
"""
import os
import time
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


def _login_resilient(email, password, attempts=5):
    """Login with backoff on 429 (brute-force throttle hit by parallel tests)."""
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

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()
CA_EMAIL = f"it17-ca-{SUFFIX}@e2e.local"
CA_PASS = "CustAdmin2026!"
LA_EMAIL = f"it17-la-{SUFFIX}@e2e.local"
LA_PASS = "LocAdmin2026!"

state = {
    "company_ids": [],
    "user_ids": [],
    "loc_codes": [],
    "group_ids": [],
    "calendar_ids": [],
    "address_ids": [],
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
        emails = [CA_EMAIL, LA_EMAIL]
        db.users.delete_many({"$or": [
            {"id": {"$in": state["user_ids"]}},
            {"email": {"$in": emails}},
        ]})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.delivery_addresses.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.holiday_calendars.delete_many({"id": {"$in": state["calendar_ids"]}})
        db.hours_calendars.delete_many({"id": {"$in": state["calendar_ids"]}})
        db.holiday_groups.delete_many({"id": {"$in": state["group_ids"]}})
        db.material_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.container_orders.delete_many({"id": {"$in": state["order_ids"]}})
    except Exception as e:  # noqa: BLE001
        print(f"[cleanup] {e}")


def _h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _post(token, path, data=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=data or {}, timeout=20)


def _put(token, path, data=None):
    return requests.put(f"{API}{path}", headers=_h(token), json=data or {}, timeout=15)


def _get(token, path):
    return requests.get(f"{API}{path}", headers=_h(token), timeout=15)


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
#   0. SA login + 1 tenant
# ============================================================
def test_sa_login():
    r = requests.post(f"{API}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_tenant(db):
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT17-CUST-{SUFFIX}",
        "customer_id": f"C17-{SUFFIX}",
        "company_type": "customer",
        "admin_email": CA_EMAIL,
        "admin_name": f"IT17 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    company_id = r.json()["company"]["id"]
    state["company_ids"].append(company_id)
    state["company_id"] = company_id
    ca_id = r.json()["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    ca_tok = requests.post(f"{API}/api/auth/login",
                           json={"email": CA_EMAIL, "password": CA_PASS}, timeout=15).json()["token"]
    state["ca_token"] = ca_tok

    r2 = _post(ca_tok, "/api/org/locations", {
        "name": f"IT17-PLADS-{SUFFIX}", "city": "IT17 By",
        "address": "IT17 Vej 1",
    })
    assert r2.status_code == 200, r2.text
    code = r2.json()["code"]
    state["loc_codes"].append(code)
    state["code"] = code
    # Default materials seeded by org_create_location are the Danish ones.
    # Use these names for the rest of the test.
    state["material_pap"] = "Pap til HCS"
    state["material_glas"] = "Glas til HCS"
    state["material_trae"] = "Træ til HCS"

    r3 = _post(ca_tok, "/api/org/users", {
        "email": LA_EMAIL, "name": f"IT17 LA {SUFFIX}",
        "role": "location_admin", "location_codes": [code],
    })
    assert r3.status_code == 200, r3.text
    la_id = r3.json()["id"]
    state["user_ids"].append(la_id)
    _accept_invite(db, la_id, LA_PASS)
    state["la_token"] = requests.post(
        f"{API}/api/auth/login",
        json={"email": LA_EMAIL, "password": LA_PASS}, timeout=15,
    ).json()["token"]


# ============================================================
#   1. SA holiday_groups — year + active + copy + soft-delete
# ============================================================
def test_create_holiday_group_with_year():
    r = _post(state["sa_token"], "/api/superadmin/holiday-groups", {
        "name": "Helligdage i Danmark – 2026",
        "year": 2026,
        "holidays": [
            {"name": "Juleaften", "date": "2026-12-24"},
            {"name": "Nytårsdag", "date": "2026-01-01"},
        ],
    })
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["year"] == 2026
    assert g["active"] is True
    assert len(g["holidays"]) == 2
    state["group_ids"].append(g["id"])
    state["g2026"] = g


def test_list_holiday_groups_has_assigned_count():
    r = _get(state["sa_token"], "/api/superadmin/holiday-groups")
    assert r.status_code == 200
    g = next((x for x in r.json() if x["id"] == state["g2026"]["id"]), None)
    assert g is not None
    assert g.get("assigned_count") == 0


def test_copy_holiday_group_to_new_year():
    r = _post(state["sa_token"],
              f"/api/superadmin/holiday-groups/{state['g2026']['id']}/copy",
              {"target_year": 2027})
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["year"] == 2027
    assert "2027" in g["name"]
    assert g["id"] != state["g2026"]["id"]
    # Dates copied as-is (user adjusts later)
    assert any(d["date"] == "2026-12-24" for d in g["holidays"])
    state["group_ids"].append(g["id"])
    state["g2027"] = g


def test_assign_group_to_customer_and_delete_blocked():
    cid = state["company_id"]
    # Assign group to customer
    r = _put(state["sa_token"], f"/api/superadmin/companies/{cid}", {
        "holiday_group_id": state["g2026"]["id"],
    })
    assert r.status_code == 200, r.text
    # assigned_count should now read 1
    lst = _get(state["sa_token"], "/api/superadmin/holiday-groups").json()
    g = next(x for x in lst if x["id"] == state["g2026"]["id"])
    assert g["assigned_count"] == 1
    # Delete should be blocked (409)
    r2 = _del(state["sa_token"], f"/api/superadmin/holiday-groups/{state['g2026']['id']}")
    assert r2.status_code == 409, r2.text
    assert "1" in r2.json()["detail"]


def test_toggle_active_holiday_group():
    r = _post(state["sa_token"],
              f"/api/superadmin/holiday-groups/{state['g2026']['id']}/toggle-active",
              {"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    # Re-activate
    r2 = _post(state["sa_token"],
               f"/api/superadmin/holiday-groups/{state['g2026']['id']}/toggle-active",
               {"active": True})
    assert r2.json()["active"] is True


def test_delete_holiday_group_after_unassign():
    cid = state["company_id"]
    # Unassign
    _put(state["sa_token"], f"/api/superadmin/companies/{cid}", {"holiday_group_id": None})
    # g2027 was never assigned → delete works
    r = _del(state["sa_token"], f"/api/superadmin/holiday-groups/{state['g2027']['id']}")
    assert r.status_code == 200, r.text


# ============================================================
#   2. LA holiday-calendars — is_active + copy-from-group + safe delete
# ============================================================
def test_copy_holiday_calendar_from_sa_group():
    # Re-assign group to customer so LA can derive
    _put(state["sa_token"], f"/api/superadmin/companies/{state['company_id']}",
         {"holiday_group_id": state["g2026"]["id"]})
    r = _post(state["la_token"], "/api/org/holiday-calendars/copy-from-group", {
        "location_code": state["code"],
        "group_id": state["g2026"]["id"],
        "name": "Pap-helligdage 2026",
        "year": 2026,
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    assert cal["year"] == 2026
    assert cal["is_active"] is True
    assert len(cal["days"]) == 2
    state["calendar_ids"].append(cal["id"])
    state["hcal_id"] = cal["id"]


def test_holiday_calendars_list_has_assigned_count_and_active_flag():
    r = _get(state["la_token"], f"/api/org/holiday-calendars?location_code={state['code']}")
    assert r.status_code == 200
    c = next(x for x in r.json() if x["id"] == state["hcal_id"])
    assert c.get("assigned_count") == 0
    assert c.get("is_active") is True


def test_link_calendar_to_material_and_delete_blocked():
    # Link to Pap via material_calendars
    r = _put(state["la_token"], "/api/org/material-calendars", {
        "location_code": state["code"], "material": state["material_pap"],
        "holiday_calendar_id": state["hcal_id"],
        "hours_calendar_id": None,
    })
    assert r.status_code == 200, r.text
    # Now delete should fail
    r2 = _del(state["la_token"], f"/api/org/holiday-calendars/{state['hcal_id']}")
    assert r2.status_code == 409, r2.text
    assert "1" in r2.json()["detail"]
    # assigned_count = 1
    lst = _get(state["la_token"], f"/api/org/holiday-calendars?location_code={state['code']}").json()
    c = next(x for x in lst if x["id"] == state["hcal_id"])
    assert c["assigned_count"] == 1


def test_toggle_active_holiday_calendar():
    r = _post(state["la_token"],
              f"/api/org/holiday-calendars/{state['hcal_id']}/toggle-active",
              {"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    # Re-activate
    _post(state["la_token"],
          f"/api/org/holiday-calendars/{state['hcal_id']}/toggle-active",
          {"active": True})


# ============================================================
#   3. LA hours-calendars — copy + toggle-active + safe delete
# ============================================================
def test_create_hours_calendar():
    r = _post(state["la_token"], "/api/org/hours-calendars", {
        "location_code": state["code"], "name": "IT17 Hours",
        "weekdays": {
            "mon": {"closed": False, "open_from": "08:00", "open_to": "16:00"},
            "sat": {"closed": True, "open_from": "", "open_to": ""},
        },
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    assert cal["is_active"] is True
    state["calendar_ids"].append(cal["id"])
    state["hours_id"] = cal["id"]


def test_copy_hours_calendar():
    r = _post(state["la_token"],
              f"/api/org/hours-calendars/{state['hours_id']}/copy",
              {"name": "IT17 Hours (kopi)"})
    assert r.status_code == 200, r.text
    copy = r.json()
    assert copy["id"] != state["hours_id"]
    assert copy["weekdays"]["mon"]["open_from"] == "08:00"
    assert copy["weekdays"]["sat"]["closed"] is True
    state["calendar_ids"].append(copy["id"])


def test_toggle_active_hours_calendar():
    r = _post(state["la_token"],
              f"/api/org/hours-calendars/{state['hours_id']}/toggle-active",
              {"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


def test_hours_calendar_delete_blocked_when_referenced():
    # Re-activate first then link to Pap, then verify delete is blocked
    _post(state["la_token"], f"/api/org/hours-calendars/{state['hours_id']}/toggle-active", {"active": True})
    _put(state["la_token"], "/api/org/material-calendars", {
        "location_code": state["code"], "material": state["material_pap"],
        "holiday_calendar_id": state["hcal_id"],
        "hours_calendar_id": state["hours_id"],
    })
    r = _del(state["la_token"], f"/api/org/hours-calendars/{state['hours_id']}")
    assert r.status_code == 409, r.text


# ============================================================
#   4. Materials soft-delete on plads
# ============================================================
def test_toggle_material_active():
    code = state["code"]
    pap = state["material_pap"]
    # Pap is currently active. Deactivate it.
    r = _post(state["la_token"], f"/api/locations/{code}/materials/toggle-active",
              {"material": pap, "active": False})
    assert r.status_code == 200, r.text
    assert pap in r.json()["inactive_materials"]
    # Active-only endpoint must hide it
    r2 = requests.get(f"{API}/api/locations/{code}/materials/active", timeout=10)
    assert r2.status_code == 200
    assert pap not in r2.json()["materials"]
    # Re-activate
    r3 = _post(state["la_token"], f"/api/locations/{code}/materials/toggle-active",
               {"material": pap, "active": True})
    assert r3.status_code == 200
    assert pap not in r3.json()["inactive_materials"]


def test_material_delete_blocked_when_referenced():
    code = state["code"]
    pap = state["material_pap"]
    # Pap is mapped via material_calendars → delete must be blocked
    r = requests.delete(f"{API}/api/locations/{code}/materials?material={pap}",
                        headers=_h(state["la_token"]), timeout=15)
    assert r.status_code == 409, r.text


def test_material_delete_allowed_when_no_refs():
    code = state["code"]
    glas = state["material_glas"]
    # Glas is unmapped → delete allowed
    r = requests.delete(f"{API}/api/locations/{code}/materials?material={glas}",
                        headers=_h(state["la_token"]), timeout=15)
    assert r.status_code == 200, r.text


# ============================================================
#   5. Order submit persists manual_alternative_address
# ============================================================
def test_la_can_read_holiday_groups_via_org_endpoint():
    """LA must be able to fetch SA holiday-groups (active only) so the
    'Kopiér fra SA-gruppe' optgroup in the new-calendar form can populate.
    The SA-only /api/superadmin/holiday-groups would 403 here."""
    r = requests.get(f"{API}/api/org/holiday-groups",
                     headers=_h(state["la_token"]), timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()
    # Should at least include the 2026 group we created earlier (which we
    # re-assigned to the customer in test_copy_holiday_calendar_from_sa_group)
    assert any(i["id"] == state["g2026"]["id"] for i in items), items


def test_order_submit_with_manual_alternative_address(db):
    code = state["code"]
    pap = state["material_pap"]
    payload = {
        "location_code": code,
        "material": pap,
        "container_number": "Container 1",
        "priority": "normal",
        "custom_address": "Sjøvej 7, 9999 Custom By",
        "order_date": "2026-06-16",
        "open_from": "10:00",
        "open_to": "14:00",
        "manual_alternative_address": "Sjøvej 7, 9999 Custom By (selvindtastet)",
    }
    r = requests.post(f"{API}/api/customer-orders/submit", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    # Pick most recent order on this plads
    saved = db.container_orders.find_one(
        {"company_id": state["company_id"], "location_code": code},
        sort=[("created_at", -1)],
        projection={"_id": 0},
    )
    assert saved is not None
    state["order_ids"].append(saved["id"])
    assert saved.get("manual_alternative_address") == "Sjøvej 7, 9999 Custom By (selvindtastet)"


# ============================================================
#   6. Delivery-addresses payload no longer accepts calendar overrides
# ============================================================
def test_delivery_address_create_ignores_calendar_fields():
    code = state["code"]
    trae = state["material_trae"]
    r = _post(state["la_token"], "/api/org/delivery-addresses", {
        "location_code": code, "label": "Hovedindgang",
        "materials": [trae],
        "primary_for": [trae],
        # These fields should be SILENTLY IGNORED post-iteration-17
        "holiday_calendar_id": "fake-id",
        "hours_calendar_id": "fake-id",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    state["address_ids"].append(data["id"])
    # Returned doc must NOT contain the deprecated fields
    assert "holiday_calendar_id" not in data, data
    assert "hours_calendar_id" not in data, data
