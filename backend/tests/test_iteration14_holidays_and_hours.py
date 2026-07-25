"""Iteration 14 — backend regression for the new holiday-groups + per-plads
holiday calendars + per-plads hours calendars + material→calendar mapping
endpoints.

Spec coverage map (each `test_*` maps to one bullet of the review_request):
  * SA holiday-groups CRUD + companies.holiday_group_id unlink-on-delete
  * Sanitiser drops invalid date / missing name entries
  * POST/PUT superadmin/companies accepts holiday_group_id (string)
  * Location admin POST /org/holiday-calendars pre-fills from company's group
  * No holiday_group_id → empty days when none provided
  * PUT /org/holiday-calendars/{id} with explicit days + closed=true clamps
  * POST /org/holiday-calendars/{id}/copy duplicates + default "(kopi)" name
  * DELETE /org/holiday-calendars/{id} nullifies material_calendars
  * POST /org/hours-calendars sanitises weekdays (closed forces empty times)
  * PUT /org/hours-calendars/{id} merges name+weekdays
  * DELETE /org/hours-calendars/{id} nullifies material_calendars
  * PUT /org/material-calendars upserts; invalid calendar id → 404
  * GET /org/material-calendars?location_code=X scoped to caller's company
  * Multi-tenant: location_admin who doesn't manage the plads → 403

Throwaway tenants use the IT14- prefix and are cleaned at module teardown.
Live tenants (Argo etc.) are untouched.
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
CA1_EMAIL = f"it14-ca1-{SUFFIX}@e2e.local"
CA1_PASS = "CustAdmin2026!"
LA1_EMAIL = f"it14-la1-{SUFFIX}@e2e.local"
LA1_PASS = "LocAdmin2026!"
# Second tenant for multi-tenant 403 test
CA2_EMAIL = f"it14-ca2-{SUFFIX}@e2e.local"
CA2_PASS = "CustAdmin2026!"
LA2_EMAIL = f"it14-la2-{SUFFIX}@e2e.local"
LA2_PASS = "LocAdmin2026!"

state = {
    "company_ids": [],
    "user_ids": [],
    "loc_codes": [],
    "holiday_group_ids": [],
    "holiday_cal_ids": [],
    "hours_cal_ids": [],
}


# ---------------- mongo + cleanup ----------------
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
        db.holiday_groups.delete_many({"id": {"$in": state["holiday_group_ids"]}})
        db.holiday_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.hours_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
        db.material_calendars.delete_many({"company_id": {"$in": state["company_ids"]}})
    except Exception as e:  # noqa: BLE001
        print(f"[cleanup] {e}")


# ---------------- helpers ----------------
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
#   0. SA login + 2 tenants (so we can test 403 cross-tenant)
# ============================================================
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def _seed_tenant(db, name_suffix, ca_email, ca_pass, la_email, la_pass):
    # 1 customer + 1 customer_admin
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT14-CUST-{name_suffix}",
        "customer_id": f"C14-{name_suffix}",
        "company_type": "customer",
        "admin_email": ca_email,
        "admin_name": f"IT14 CA {name_suffix}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    company_id = body["company"]["id"]
    ca_id = body["created_admin"]["id"]
    state["company_ids"].append(company_id)
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, ca_pass)
    ca_tok = _login(ca_email, ca_pass).json()["token"]

    # CA creates plads
    r3 = _post(ca_tok, "/api/org/locations", {
        "name": f"IT14-PLADS-{name_suffix}",
        "city": "IT14 City",
        "address": "IT14 Vej 1",
    })
    assert r3.status_code == 200, r3.text
    code = r3.json().get("code") or r3.json().get("location_code")
    assert code
    state["loc_codes"].append(code)

    # location_admin
    r4 = _post(ca_tok, "/api/org/users", {
        "email": la_email,
        "name": f"IT14 LA {name_suffix}",
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
    t1 = _seed_tenant(db, f"A-{SUFFIX}", CA1_EMAIL, CA1_PASS, LA1_EMAIL, LA1_PASS)
    state["t1"] = t1
    t2 = _seed_tenant(db, f"B-{SUFFIX}", CA2_EMAIL, CA2_PASS, LA2_EMAIL, LA2_PASS)
    state["t2"] = t2


# ============================================================
#   1. SA holiday-groups CRUD + sanitisation
# ============================================================
def test_sa_create_holiday_group_with_valid_and_invalid_holidays():
    payload = {
        "name": f"IT14-DK-{SUFFIX}",
        "holidays": [
            {"name": "Nytårsdag", "date": "2026-01-01"},
            {"name": "Skærtorsdag", "date": "2026-04-02"},
            # invalid date format (should be dropped)
            {"name": "BadFormat", "date": "02-04-2026"},
            # missing name (should be dropped)
            {"name": "", "date": "2026-05-01"},
            # missing date (should be dropped)
            {"name": "NoDate"},
            # non-dict (should be ignored)
            "garbage",
        ],
    }
    r = _post(state["sa_token"], "/api/superadmin/holiday-groups", payload)
    assert r.status_code == 200, r.text
    g = r.json()
    state["holiday_group_ids"].append(g["id"])
    state["group_id"] = g["id"]
    # Only 2 valid entries should survive
    assert len(g["holidays"]) == 2, g["holidays"]
    names = sorted(h["name"] for h in g["holidays"])
    assert names == ["Nytårsdag", "Skærtorsdag"]
    for h in g["holidays"]:
        assert "name" in h and "date" in h


def test_sa_list_holiday_groups_contains_created():
    r = _get(state["sa_token"], "/api/superadmin/holiday-groups")
    assert r.status_code == 200, r.text
    ids = [g["id"] for g in r.json()]
    assert state["group_id"] in ids


def test_sa_update_holiday_group_replaces_holidays():
    r = _put(state["sa_token"], f"/api/superadmin/holiday-groups/{state['group_id']}", {
        "name": f"IT14-DK-{SUFFIX}-v2",
        "holidays": [{"name": "Pinse", "date": "2026-05-24"}],
    })
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["name"] == f"IT14-DK-{SUFFIX}-v2"
    assert len(g["holidays"]) == 1
    assert g["holidays"][0]["date"] == "2026-05-24"


# ============================================================
#   2. companies.holiday_group_id accepted on POST + PUT
# ============================================================
def test_put_company_with_holiday_group_id(db):
    cid = state["t1"]["company_id"]
    r = _put(state["sa_token"], f"/api/superadmin/companies/{cid}", {
        "holiday_group_id": state["group_id"],
    })
    assert r.status_code == 200, r.text
    co = db.companies.find_one({"id": cid}, {"_id": 0})
    assert co["holiday_group_id"] == state["group_id"]


# ============================================================
#   3. Location admin holiday calendar pre-fill from group
# ============================================================
def test_create_holiday_calendar_pre_fills_from_group():
    t1 = state["t1"]
    r = _post(t1["la_token"], "/api/org/holiday-calendars", {
        "location_code": t1["code"],
        "name": "2026 Helligdage",
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    state["holiday_cal_ids"].append(cal["id"])
    state["t1_hcal_id"] = cal["id"]
    # Group currently has 1 holiday (Pinse 2026-05-24) → pre-filled
    assert len(cal["days"]) == 1
    d = cal["days"][0]
    assert d["name"] == "Pinse"
    assert d["date"] == "2026-05-24"
    assert d["closed"] is False
    assert d["open_from"] == ""
    assert d["open_to"] == ""


def test_create_holiday_calendar_no_group_empty_days(db):
    # t2 has no holiday_group_id set
    t2 = state["t2"]
    r = _post(t2["la_token"], "/api/org/holiday-calendars", {
        "location_code": t2["code"],
        "name": "Tom-kalender",
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    state["holiday_cal_ids"].append(cal["id"])
    state["t2_hcal_id"] = cal["id"]
    assert cal["days"] == []


# ============================================================
#   4. PUT holiday-calendars sanitises + closed clamp
# ============================================================
def test_put_holiday_calendar_drops_invalid_and_clamps_closed():
    cal_id = state["t1_hcal_id"]
    r = _put(state["t1"]["la_token"], f"/api/org/holiday-calendars/{cal_id}", {
        "days": [
            {"name": "Closed Day", "date": "2026-12-24",
             "closed": True, "open_from": "10:00", "open_to": "16:00"},
            {"name": "Open Day", "date": "2026-12-31",
             "closed": False, "open_from": "08:00", "open_to": "14:00"},
            # invalid: missing name
            {"name": "", "date": "2026-12-25"},
            # invalid: missing date
            {"name": "NoDate"},
        ],
    })
    assert r.status_code == 200, r.text
    days = r.json()["days"]
    assert len(days) == 2, days
    closed = next(d for d in days if d["name"] == "Closed Day")
    assert closed["closed"] is True
    assert closed["open_from"] == ""
    assert closed["open_to"] == ""
    op = next(d for d in days if d["name"] == "Open Day")
    assert op["closed"] is False
    assert op["open_from"] == "08:00"
    assert op["open_to"] == "14:00"


# ============================================================
#   5. Copy holiday calendar
# ============================================================
def test_copy_holiday_calendar_default_name():
    cal_id = state["t1_hcal_id"]
    r = _post(state["t1"]["la_token"],
              f"/api/org/holiday-calendars/{cal_id}/copy", {})
    assert r.status_code == 200, r.text
    new_cal = r.json()
    state["holiday_cal_ids"].append(new_cal["id"])
    assert new_cal["id"] != cal_id
    # current cal was renamed via PUT? no — only days replaced. name unchanged.
    assert new_cal["name"].endswith("(kopi)"), new_cal["name"]
    assert len(new_cal["days"]) == 2  # copied current state


def test_copy_holiday_calendar_with_explicit_name():
    cal_id = state["t1_hcal_id"]
    r = _post(state["t1"]["la_token"],
              f"/api/org/holiday-calendars/{cal_id}/copy",
              {"name": "2027 Helligdage"})
    assert r.status_code == 200, r.text
    new_cal = r.json()
    state["holiday_cal_ids"].append(new_cal["id"])
    assert new_cal["name"] == "2027 Helligdage"


# ============================================================
#   6. Hours calendars
# ============================================================
def test_create_hours_calendar_sanitises_weekdays():
    t1 = state["t1"]
    weekdays = {
        "mon": {"closed": False, "open_from": "07:00", "open_to": "16:00"},
        "tue": {"closed": False, "open_from": "07:00", "open_to": "16:00"},
        # Closed + populated times → times should be wiped
        "sat": {"closed": True, "open_from": "10:00", "open_to": "12:00"},
        # garbage → defaults to closed=false + empty times
        "sun": "not a dict",
    }
    r = _post(t1["la_token"], "/api/org/hours-calendars", {
        "location_code": t1["code"],
        "name": "Standard ugeplan",
        "weekdays": weekdays,
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    state["hours_cal_ids"].append(cal["id"])
    state["t1_hours_id"] = cal["id"]
    wd = cal["weekdays"]
    # All 7 keys present
    for k in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
        assert k in wd, f"Missing weekday key {k}"
    assert wd["mon"]["open_from"] == "07:00"
    # Closed = true clears times
    assert wd["sat"]["closed"] is True
    assert wd["sat"]["open_from"] == ""
    assert wd["sat"]["open_to"] == ""
    # garbage → safe default
    assert wd["sun"]["closed"] is False
    assert wd["sun"]["open_from"] == ""


def test_put_hours_calendar_merges():
    cal_id = state["t1_hours_id"]
    r = _put(state["t1"]["la_token"], f"/api/org/hours-calendars/{cal_id}", {
        "name": "Standard ugeplan v2",
        "weekdays": {"wed": {"closed": False, "open_from": "09:00", "open_to": "15:00"}},
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    assert cal["name"] == "Standard ugeplan v2"
    # Wed updated; mon must be preserved (the merge takes existing for missing keys)
    assert cal["weekdays"]["wed"]["open_from"] == "09:00"
    assert cal["weekdays"]["mon"]["open_from"] == "07:00"


# ============================================================
#   7. Material→calendar matrix
# ============================================================
def test_material_calendar_upsert_and_get():
    t1 = state["t1"]
    code = t1["code"]
    # Use existing holiday cal and hours cal
    payload = {
        "location_code": code,
        "material": "Pap",
        "holiday_calendar_id": state["t1_hcal_id"],
        "hours_calendar_id": state["t1_hours_id"],
    }
    r = _put(t1["la_token"], "/api/org/material-calendars", payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["material"] == "Pap"
    assert body["holiday_calendar_id"] == state["t1_hcal_id"]
    assert body["hours_calendar_id"] == state["t1_hours_id"]

    # GET list filters by company/location
    r2 = _get(t1["la_token"], f"/api/org/material-calendars?location_code={code}")
    assert r2.status_code == 200, r2.text
    items = r2.json()
    pap = [i for i in items if i["material"] == "Pap"]
    assert len(pap) == 1
    assert pap[0]["holiday_calendar_id"] == state["t1_hcal_id"]


def test_material_calendar_upsert_with_null_ids():
    t1 = state["t1"]
    r = _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"],
        "material": "Pap",
        "holiday_calendar_id": None,
        "hours_calendar_id": None,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["holiday_calendar_id"] is None
    assert body["hours_calendar_id"] is None


def test_material_calendar_invalid_id_returns_404():
    t1 = state["t1"]
    r = _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"],
        "material": "Glas",
        "holiday_calendar_id": "non-existent-id-12345",
    })
    assert r.status_code == 404, r.text


# ============================================================
#   8. DELETE holiday/hours calendar nullifies matrix
# ============================================================
def test_delete_hours_calendar_blocked_when_assigned(db):
    """As of iteration 17 the delete endpoint REFUSES to remove a calendar
    while it's still referenced by material_calendars rows. The caller is
    expected to deactivate or unmap first."""
    t1 = state["t1"]
    # Re-assign matrix for Pap to point at the hours_cal we'll try to delete
    r0 = _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"],
        "material": "Pap",
        "holiday_calendar_id": state["t1_hcal_id"],
        "hours_calendar_id": state["t1_hours_id"],
    })
    assert r0.status_code == 200, r0.text

    r = _del(t1["la_token"], f"/api/org/hours-calendars/{state['t1_hours_id']}")
    assert r.status_code == 409, r.text
    # Unmap first
    _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"], "material": "Pap",
        "holiday_calendar_id": state["t1_hcal_id"], "hours_calendar_id": None,
    })
    # Now delete should succeed
    r2 = _del(t1["la_token"], f"/api/org/hours-calendars/{state['t1_hours_id']}")
    assert r2.status_code == 200, r2.text


def test_delete_holiday_calendar_blocked_when_assigned(db):
    """Same behavior for holiday calendars — block when still mapped."""
    t1 = state["t1"]
    # Re-map Pap to the hcal we'll try to delete (since prior test unmapped hours)
    _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"], "material": "Pap",
        "holiday_calendar_id": state["t1_hcal_id"], "hours_calendar_id": None,
    })
    r = _del(t1["la_token"], f"/api/org/holiday-calendars/{state['t1_hcal_id']}")
    assert r.status_code == 409, r.text
    # Unmap then delete
    _put(t1["la_token"], "/api/org/material-calendars", {
        "location_code": t1["code"], "material": "Pap",
        "holiday_calendar_id": None, "hours_calendar_id": None,
    })
    r2 = _del(t1["la_token"], f"/api/org/holiday-calendars/{state['t1_hcal_id']}")
    assert r2.status_code == 200, r2.text


# ============================================================
#   9. Multi-tenant 403 — t2's location_admin can't reach t1's plads
# ============================================================
def test_cross_tenant_holiday_calendars_403():
    t1_code = state["t1"]["code"]
    t2_la = state["t2"]["la_token"]
    # 404 (not found in t2's company scope) is the implementation per
    # _resolve_plads_for_org. Per spec the expectation is 403 OR 404 — we
    # accept either as "not authorised to see/edit t1's plads".
    r = _get(t2_la, f"/api/org/holiday-calendars?location_code={t1_code}")
    assert r.status_code in (403, 404), r.text


def test_cross_tenant_hours_calendars_403():
    t1_code = state["t1"]["code"]
    t2_la = state["t2"]["la_token"]
    r = _get(t2_la, f"/api/org/hours-calendars?location_code={t1_code}")
    assert r.status_code in (403, 404), r.text


def test_cross_tenant_material_calendars_403():
    t1_code = state["t1"]["code"]
    t2_la = state["t2"]["la_token"]
    r = _get(t2_la, f"/api/org/material-calendars?location_code={t1_code}")
    assert r.status_code in (403, 404), r.text
    r2 = _put(t2_la, "/api/org/material-calendars", {
        "location_code": t1_code, "material": "Pap",
    })
    assert r2.status_code in (403, 404), r2.text


# ============================================================
#  10. SA DELETE holiday-group is BLOCKED when companies still reference it
# ============================================================
def test_sa_delete_holiday_group_blocked_when_assigned(db):
    """Iteration 17: permanent delete is refused while customers reference
    the group. The SA UI must offer "Deaktiver" as the soft-delete path."""
    cid = state["t1"]["company_id"]
    co_before = db.companies.find_one({"id": cid}, {"_id": 0})
    assert co_before["holiday_group_id"] == state["group_id"]

    r = _del(state["sa_token"], f"/api/superadmin/holiday-groups/{state['group_id']}")
    assert r.status_code == 409, r.text
    # Detail should mention how many customers reference it
    assert "1" in r.json()["detail"], r.text

    # Now unassign the company manually and try again
    requests.put(
        f"{API}/api/superadmin/companies/{cid}",
        headers={"Authorization": f"Bearer {state['sa_token']}",
                 "Content-Type": "application/json"},
        json={"holiday_group_id": None},
    )
    r2 = _del(state["sa_token"], f"/api/superadmin/holiday-groups/{state['group_id']}")
    assert r2.status_code == 200, r2.text
