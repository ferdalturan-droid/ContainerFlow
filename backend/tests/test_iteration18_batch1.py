"""Iteration 18 — backend regression for the Batch 1 features:

  * delivery_addresses simplified to {label, street, postcode, city}
  * holiday_calendars + hours_calendars carry delivery_address_id on
    day-entries (optional for helligdag, required for ugedag)
  * resolve endpoint: holiday → weekday fallback for delivery_address_id
  * capacity_measures CRUD (Kapacitetsmål-bibliotek)
  * SA companies list includes locations_count + partners_count +
    active_users_incl_partners
  * SA helligdags-delta CRUD + publish → fans out notifications to all LAs
  * LA pending deltas endpoint + reject + import (applies operations
    to a target calendar)

Cleans up all seed data at module teardown so the user's real data is
preserved.
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

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()
CA_EMAIL = f"it18-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"
LA_EMAIL = f"it18-la-{SUFFIX}@e2e.local"
LA_PASS = "TestPass2026!"

state = {
    "company_ids": [], "user_ids": [], "loc_codes": [],
    "address_ids": [], "calendar_ids": [], "cap_ids": [],
    "delta_ids": [],
}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    try:
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.locations.delete_many({"code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.delivery_addresses.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.holiday_calendars.delete_many({"id": {"$in": state["calendar_ids"]}})
        db.hours_calendars.delete_many({"id": {"$in": state["calendar_ids"]}})
        db.material_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.capacity_measures.delete_many({"id": {"$in": state["cap_ids"]}})
        db.holiday_deltas.delete_many({"id": {"$in": state["delta_ids"]}})
        db.delta_notifications.delete_many({"delta_id": {"$in": state["delta_ids"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password, attempts=5):
    for i in range(attempts):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": password}, timeout=15)
        if r.status_code == 200:
            return r
        if r.status_code == 429:
            time.sleep(3 + i * 2); continue
        return r
    return r


def _h(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _post(tok, p, d=None):
    return requests.post(f"{API}{p}", headers=_h(tok), json=d or {}, timeout=20)


def _put(tok, p, d=None):
    return requests.put(f"{API}{p}", headers=_h(tok), json=d or {}, timeout=15)


def _get(tok, p):
    return requests.get(f"{API}{p}", headers=_h(tok), timeout=15)


def _del(tok, p):
    return requests.delete(f"{API}{p}", headers=_h(tok), timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None, f"no invite for {user_id}"
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": password}, timeout=15)
    assert r.status_code == 200, r.text


# ========================================================
#   Bootstrap
# ========================================================
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_tenant(db):
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT18-CUST-{SUFFIX}", "customer_id": f"C18-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT18 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    cid = body["company"]["id"]
    state["company_ids"].append(cid)
    state["company_id"] = cid
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    ca_tok = _login(CA_EMAIL, CA_PASS).json()["token"]
    state["ca_token"] = ca_tok

    r2 = _post(ca_tok, "/api/org/locations", {
        "name": f"IT18-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1",
    })
    code = r2.json()["code"]
    state["loc_codes"].append(code); state["code"] = code

    r3 = _post(ca_tok, "/api/org/users", {
        "email": LA_EMAIL, "name": f"IT18 LA {SUFFIX}",
        "role": "location_admin", "location_codes": [code],
    })
    la_id = r3.json()["id"]
    state["user_ids"].append(la_id)
    _accept_invite(db, la_id, LA_PASS)
    state["la_token"] = _login(LA_EMAIL, LA_PASS).json()["token"]


# ========================================================
#   1. delivery_addresses → simplified bibliotek
# ========================================================
def test_delivery_address_create_strips_materials():
    code = state["code"]
    r = _post(state["la_token"], "/api/org/delivery-addresses", {
        "location_code": code, "label": "Hovedindgang",
        "street": "Hovedgade 1", "postcode": "1000", "city": "København",
        # The following legacy keys must be SILENTLY IGNORED (not stored).
        "materials": ["Pap"], "primary_for": ["Pap"],
        "holiday_calendar_id": "should-be-ignored",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    state["address_ids"].append(d["id"])
    state["addr1_id"] = d["id"]
    assert "materials" not in d
    assert "primary_for" not in d
    assert "holiday_calendar_id" not in d
    assert d["label"] == "Hovedindgang"


def test_delivery_address_second():
    code = state["code"]
    r = _post(state["la_token"], "/api/org/delivery-addresses", {
        "location_code": code, "label": "Bagside",
        "street": "Bagvej 9", "postcode": "1050", "city": "København",
    })
    assert r.status_code == 200
    state["address_ids"].append(r.json()["id"])
    state["addr2_id"] = r.json()["id"]


# ========================================================
#   2. Calendars carry delivery_address_id on entries
# ========================================================
def test_holiday_calendar_with_delivery_address_on_day():
    code = state["code"]
    r = _post(state["la_token"], "/api/org/holiday-calendars", {
        "location_code": code, "name": "IT18 Helligdage",
        "days": [
            # Helligdag MED address override
            {"name": "Juleaften", "date": "2026-12-24", "closed": False,
             "open_from": "08:00", "open_to": "12:00",
             "delivery_address_id": state["addr2_id"]},
            # Helligdag UDEN address — should fall back to weekday's address
            {"name": "Nytårsaftensdag", "date": "2026-12-31", "closed": False,
             "open_from": "08:00", "open_to": "14:00"},
        ],
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    state["calendar_ids"].append(cal["id"])
    state["hcal_id"] = cal["id"]
    # Verify field stored
    assert cal["days"][0]["delivery_address_id"] == state["addr2_id"]
    assert cal["days"][1]["delivery_address_id"] is None


def test_hours_calendar_with_delivery_address_per_weekday():
    code = state["code"]
    # Build all 7 weekdays with delivery_address_id required
    wd = {
        k: {"closed": False, "open_from": "08:00", "open_to": "16:00",
            "delivery_address_id": state["addr1_id"]}
        for k in ["mon", "tue", "wed", "thu", "fri"]
    }
    wd["sat"] = {"closed": True, "open_from": "", "open_to": "",
                 "delivery_address_id": None}
    wd["sun"] = {"closed": True, "open_from": "", "open_to": "",
                 "delivery_address_id": None}
    r = _post(state["la_token"], "/api/org/hours-calendars", {
        "location_code": code, "name": "IT18 Ugentligt", "weekdays": wd,
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    state["calendar_ids"].append(cal["id"])
    state["hours_id"] = cal["id"]
    assert cal["weekdays"]["mon"]["delivery_address_id"] == state["addr1_id"]
    assert cal["weekdays"]["sat"]["closed"] is True


def test_link_calendars_to_material():
    code = state["code"]
    r = _put(state["la_token"], "/api/org/material-calendars", {
        "location_code": code, "material": "Pap til HCS",
        "holiday_calendar_id": state["hcal_id"],
        "hours_calendar_id": state["hours_id"],
    })
    assert r.status_code == 200, r.text


# ========================================================
#   3. Resolve endpoint: holiday→weekday delivery_address fallback
# ========================================================
def test_resolve_holiday_with_own_address_wins():
    code = state["code"]
    # 2026-12-24 is the Juleaften helligdag with addr2 override
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": code, "material": "Pap til HCS", "date": "2026-12-24",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_holiday"] is True
    assert d["resolved_delivery_address_id"] == state["addr2_id"]
    assert d["source"] == "holiday"
    assert d.get("resolved_delivery_address", {}).get("label") == "Bagside"


def test_resolve_holiday_without_address_falls_back_to_weekday():
    code = state["code"]
    # 2026-12-31 is the Nytårsaften helligdag WITHOUT address → fall back to
    # the weekday (Thursday) address = addr1.
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": code, "material": "Pap til HCS", "date": "2026-12-31",
    })
    d = r.json()
    assert d["is_holiday"] is True
    assert d["source"] == "holiday"
    assert d["resolved_delivery_address_id"] == state["addr1_id"], d
    assert d.get("resolved_delivery_address", {}).get("label") == "Hovedindgang"


def test_resolve_regular_weekday():
    code = state["code"]
    # 2026-12-15 is a Tuesday → weekday entry → addr1
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": code, "material": "Pap til HCS", "date": "2026-12-15",
    })
    d = r.json()
    assert d["is_holiday"] is False
    assert d["source"] == "weekday"
    assert d["resolved_delivery_address_id"] == state["addr1_id"]


def test_resolve_closed_weekend():
    code = state["code"]
    # 2026-12-19 is a Saturday → closed
    r = requests.get(f"{API}/api/delivery-addresses/resolve", params={
        "location_code": code, "material": "Pap til HCS", "date": "2026-12-19",
    })
    d = r.json()
    assert d["is_closed"] is True
    # Sat had no delivery_address_id → resolved is null
    assert d["resolved_delivery_address_id"] is None


# ========================================================
#   4. Delete blocked when address is in use
# ========================================================
def test_delivery_address_delete_blocked_when_referenced():
    # addr1 is used in weekday entries → cannot delete
    r = _del(state["la_token"], f"/api/org/delivery-addresses/{state['addr1_id']}")
    assert r.status_code == 409, r.text


def test_delivery_address_delete_works_after_unlinking():
    # Wipe weekday references, then delete should pass for addr1.
    # Quickest path: PUT the hours_calendar with empty delivery_address_id
    # on every weekday.
    code = state["code"]
    wd = {k: {"closed": False, "open_from": "08:00", "open_to": "16:00",
              "delivery_address_id": None}
          for k in ["mon", "tue", "wed", "thu", "fri"]}
    wd["sat"] = {"closed": True, "open_from": "", "open_to": "", "delivery_address_id": None}
    wd["sun"] = {"closed": True, "open_from": "", "open_to": "", "delivery_address_id": None}
    _put(state["la_token"], f"/api/org/hours-calendars/{state['hours_id']}", {
        "weekdays": wd,
    })
    # addr1 was only used in hours → now safe to delete
    r = _del(state["la_token"], f"/api/org/delivery-addresses/{state['addr1_id']}")
    assert r.status_code == 200, r.text


# ========================================================
#   5. Capacity Measures (Kapacitetsmål-bibliotek)
# ========================================================
def test_capacity_measure_crud():
    code = state["code"]
    r = _post(state["la_token"], "/api/org/capacity-measures", {
        "location_code": code, "label": "20 m³", "volume_m3": 20.0,
    })
    assert r.status_code == 200, r.text
    cm = r.json()
    assert cm["volume_m3"] == 20.0
    state["cap_ids"].append(cm["id"])

    # List
    r2 = _get(state["la_token"], f"/api/org/capacity-measures?location_code={code}")
    assert r2.status_code == 200
    assert any(x["id"] == cm["id"] for x in r2.json())

    # Update
    r3 = _put(state["la_token"], f"/api/org/capacity-measures/{cm['id']}",
              {"label": "20,0 m³", "volume_m3": 20.0})
    assert r3.status_code == 200
    assert r3.json()["label"] == "20,0 m³"

    # Delete
    r4 = _del(state["la_token"], f"/api/org/capacity-measures/{cm['id']}")
    assert r4.status_code == 200


# ========================================================
#   6. SA companies → Kundeoverblik counts
# ========================================================
def test_companies_list_has_overview_counts():
    r = _get(state["sa_token"], "/api/superadmin/companies?include_library=false")
    assert r.status_code == 200
    cid = state["company_id"]
    me = next((c for c in r.json() if c["id"] == cid), None)
    assert me is not None
    assert me.get("locations_count", 0) >= 1
    assert me.get("partners_count", 0) == 0  # no partners assigned yet
    assert me.get("active_users_incl_partners", 0) >= 2  # CA + LA


# ========================================================
#   7. Helligdags-deltas (SA → LA fan-out)
# ========================================================
def test_create_holiday_delta_draft():
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": "IT18 Delta",
        "year": 2027,
        "operations": [
            {"op": "modify", "match_name": "Juleaften", "new_name": "Juleaften",
             "new_date": "2027-12-24"},
            {"op": "add", "match_name": "Påskeløverdag", "new_date": "2027-04-03"},
            {"op": "delete", "match_name": "Nytårsaftensdag"},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "draft"
    assert len(d["operations"]) == 3
    state["delta_ids"].append(d["id"])
    state["delta_id"] = d["id"]


def test_publish_delta_fans_out_notifications_to_all_las():
    r = _post(state["sa_token"],
              f"/api/superadmin/holiday-deltas/{state['delta_id']}/publish")
    assert r.status_code == 200, r.text
    body = r.json()
    # at least our LA got notified
    assert body["notifications_created"] >= 1
    assert body["total_recipients"] >= 1


def test_la_sees_pending_delta():
    r = _get(state["la_token"], "/api/org/holiday-deltas/pending")
    assert r.status_code == 200, r.text
    pending = r.json()
    ours = [n for n in pending if n["delta"]["id"] == state["delta_id"]]
    assert len(ours) == 1, pending
    state["notif_id"] = ours[0]["id"]


def test_la_import_delta_applies_to_calendar(db):
    # Use the existing IT18 Helligdage calendar (has 2 days: Juleaften, Nytårsaftensdag)
    cal_before = db.holiday_calendars.find_one({"id": state["hcal_id"]}, {"_id": 0})
    assert len(cal_before["days"]) == 2

    r = _post(state["la_token"],
              f"/api/org/holiday-deltas/{state['notif_id']}/import",
              {"calendar_id": state["hcal_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["modified"] == 1  # Juleaften modified
    assert body["added"] == 1     # Påskeløverdag added
    assert body["deleted"] == 1   # Nytårsaftensdag deleted

    cal_after = db.holiday_calendars.find_one({"id": state["hcal_id"]}, {"_id": 0})
    names = sorted([d["name"] for d in cal_after["days"]])
    assert "Juleaften" in names
    assert "Påskeløverdag" in names
    assert "Nytårsaftensdag" not in names


def test_pending_clears_after_accept():
    r = _get(state["la_token"], "/api/org/holiday-deltas/pending")
    pending = r.json()
    ours = [n for n in pending if n["delta"]["id"] == state["delta_id"]]
    assert len(ours) == 0


# ========================================================
#   8. LA Reports endpoint
# ========================================================
def test_report_orders_endpoint(db):
    # Seed a single order so the aggregator has something to chew on.
    from datetime import datetime, timezone as _tz
    today_iso = datetime.now(_tz.utc).date().isoformat()
    db.container_orders.insert_one({
        "id": str(uuid.uuid4()),
        "company_id": state["company_id"],
        "location_code": state["code"],
        "material": "Pap til HCS", "container_number": "Container 1",
        "priority": "normal", "tour_type": "normal",
        "status_label": "afventer",
        "order_date": today_iso,
        "open_from": "10:00", "open_to": "14:00",
        "created_by_name": "Test Employee",
        "weight": 350.0,
        "created_at": datetime.now(_tz.utc).isoformat(),
    })
    r = _get(state["la_token"], f"/api/org/reports/orders?location_code={state['code']}&period=month")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_orders"] >= 1
    assert any(m["name"] == "Pap til HCS" for m in d["by_material"])
    assert d["workshop_count"] == 0
    assert d["pending_in_period"] >= 1
    assert d["pending_all_time"] >= 1


def test_reject_delta_path():
    # Create + publish another delta, then reject it as LA
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": "IT18 Delta REJECT",
        "operations": [{"op": "add", "match_name": "TestDay", "new_date": "2027-05-05"}],
    })
    state["delta_ids"].append(r.json()["id"])
    d2_id = r.json()["id"]
    _post(state["sa_token"], f"/api/superadmin/holiday-deltas/{d2_id}/publish")
    pending = _get(state["la_token"], "/api/org/holiday-deltas/pending").json()
    notif = next(n for n in pending if n["delta"]["id"] == d2_id)
    r2 = _post(state["la_token"], f"/api/org/holiday-deltas/{notif['id']}/reject")
    assert r2.status_code == 200
    # Pending no longer surfaces it
    pending2 = _get(state["la_token"], "/api/org/holiday-deltas/pending").json()
    assert not any(n["delta"]["id"] == d2_id for n in pending2)
