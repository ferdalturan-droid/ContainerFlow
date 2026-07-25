"""Iteration 19 — backend regression for Batch 2:

  * Workshops library: CA-only CRUD on /api/org/workshops, all roles read.
  * Location groups: CA-only CRUD on /api/org/location-groups. Each plads
    may optionally reference a group via location_group_id.
  * Customer-order workshop fields: workshop_id + workshop_name/address/
    phone snapshot + workshop_override persists end-to-end through
    /api/customer-orders/submit.
  * Customer-order edit: PUT /api/customer-orders/{id} with audit log
    entry in customer_orders_history.
  * Customer-order hard delete: DELETE /api/customer-orders/{id} with
    audit log + tour cascade.
  * Customer-order history: GET /api/customer-orders/{id}/history.

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
CA_EMAIL = f"it19-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"
LA_EMAIL = f"it19-la-{SUFFIX}@e2e.local"
LA_PASS = "TestPass2026!"

state = {
    "company_ids": [], "user_ids": [], "loc_codes": [],
    "workshop_ids": [], "group_ids": [], "order_ids": [],
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
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.workshops.delete_many({"id": {"$in": state["workshop_ids"]}})
        db.location_groups.delete_many({"id": {"$in": state["group_ids"]}})
        db.container_orders.delete_many({"id": {"$in": state["order_ids"]}})
        db.tours.delete_many({"order_id": {"$in": state["order_ids"]}})
        db.customer_orders_history.delete_many({"order_id": {"$in": state["order_ids"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password, attempts=5):
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
        "name": f"IT19-CUST-{SUFFIX}", "customer_id": f"C19-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT19 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    cid = body["company"]["id"]
    state["company_ids"].append(cid)
    state["company_id"] = cid
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    r2 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT19-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1",
    })
    code = r2.json()["code"]
    state["loc_codes"].append(code)
    state["code"] = code

    r3 = _post(state["ca_token"], "/api/org/users", {
        "email": LA_EMAIL, "name": f"IT19 LA {SUFFIX}",
        "role": "location_admin", "location_codes": [code],
    })
    la_id = r3.json()["id"]
    state["user_ids"].append(la_id)
    _accept_invite(db, la_id, LA_PASS)
    state["la_token"] = _login(LA_EMAIL, LA_PASS).json()["token"]


# ========================================================
#   WORKSHOPS
# ========================================================
def test_workshops_ca_create():
    r = _post(state["ca_token"], "/api/org/workshops", {
        "name": "Værksted Nord",
        "address": "Hovedvej 21, 4000 Roskilde",
        "phone": "+45 12 34 56 78",
        "comment": "Åbent man-fre 7-15",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "Værksted Nord"
    assert d["address"].startswith("Hovedvej 21")
    state["workshop_ids"].append(d["id"])
    state["ws1_id"] = d["id"]


def test_workshops_validation_missing_address():
    r = _post(state["ca_token"], "/api/org/workshops", {"name": "kun-navn"})
    assert r.status_code == 400


def test_workshops_la_can_read_not_write():
    r = _get(state["la_token"], "/api/org/workshops")
    assert r.status_code == 200
    items = r.json()
    assert any(w["id"] == state["ws1_id"] for w in items)
    # LA cannot create
    r2 = _post(state["la_token"], "/api/org/workshops", {
        "name": "LA forsøg", "address": "X",
    })
    assert r2.status_code == 403


def test_workshops_update_then_delete():
    r = _put(state["ca_token"], f"/api/org/workshops/{state['ws1_id']}", {
        "name": "Værksted Nord (Renoveret)",
        "address": "Hovedvej 21, 4000 Roskilde",
        "phone": "+45 99 88 77 66",
        "comment": "",
    })
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+45 99 88 77 66"

    # Create a 2nd one to keep for the order test
    r2 = _post(state["ca_token"], "/api/org/workshops", {
        "name": "Værksted Syd",
        "address": "Industrivej 5, 6000 Kolding",
        "phone": "70 12 34 56",
    })
    state["workshop_ids"].append(r2.json()["id"])
    state["ws2_id"] = r2.json()["id"]


# ========================================================
#   LOCATION GROUPS
# ========================================================
def test_location_group_ca_create():
    r = _post(state["ca_token"], "/api/org/location-groups", {"name": f"Sjælland-{SUFFIX}"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == f"Sjælland-{SUFFIX}"
    assert d["locations_count"] == 0
    state["group_ids"].append(d["id"])
    state["group_id"] = d["id"]


def test_location_group_duplicate_blocked():
    r = _post(state["ca_token"], "/api/org/location-groups", {"name": f"Sjælland-{SUFFIX}"})
    assert r.status_code == 409


def test_location_group_la_can_read_not_write():
    r = _get(state["la_token"], "/api/org/location-groups")
    assert r.status_code == 200
    assert any(g["id"] == state["group_id"] for g in r.json())
    r2 = _post(state["la_token"], "/api/org/location-groups", {"name": "blokeret"})
    assert r2.status_code == 403


def test_attach_group_to_location():
    # First find the location id (PUT uses id, not code)
    locs = _get(state["ca_token"], "/api/org/locations").json()
    loc = next(l for l in locs if l["location_code"] == state["code"])
    r = _put(state["ca_token"], f"/api/org/locations/{loc['id']}", {
        "location_group_id": state["group_id"],
    })
    assert r.status_code == 200, r.text
    assert r.json().get("location_group_id") == state["group_id"]


def test_group_locations_count_reflects_attachment():
    r = _get(state["ca_token"], "/api/org/location-groups")
    grp = next(g for g in r.json() if g["id"] == state["group_id"])
    assert grp["locations_count"] == 1


def test_detach_group_when_deleted():
    # Deleting the group should auto-detach it from any pladser
    r = _del(state["ca_token"], f"/api/org/location-groups/{state['group_id']}")
    assert r.status_code == 200
    # Verify the location no longer has it
    locs = _get(state["ca_token"], "/api/org/locations").json()
    loc = next(l for l in locs if l["location_code"] == state["code"])
    assert not loc.get("location_group_id")
    # Re-create one for subsequent tests
    r2 = _post(state["ca_token"], "/api/org/location-groups", {"name": f"Jylland-{SUFFIX}"})
    state["group_ids"].append(r2.json()["id"])


# ========================================================
#   CUSTOMER ORDER — workshop snapshot
# ========================================================
def test_submit_order_with_workshop():
    code = state["code"]
    # Login as the LA so the order picks up created_by_*
    ws = _get(state["la_token"], "/api/org/workshops").json()
    ws2 = next(w for w in ws if w["id"] == state["ws2_id"])
    payload = {
        "location_code": code,
        "material": "Pap til HCS",
        "container_number": "Container 1",
        "priority": "normal",
        "comment": "Snapshot-test",
        "tour_type": "vaerksted",
        "workshop_id": ws2["id"],
        "workshop_name": ws2["name"],
        "workshop_address": ws2["address"],
        "workshop_phone": ws2["phone"],
        "workshop_override": False,
    }
    r = requests.post(f"{API}/api/customer-orders/submit",
                      headers=_h(state["la_token"]), json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    state["order_ids"].append(data["order_id"])
    state["order_id"] = data["order_id"]


def test_order_has_workshop_snapshot(db):
    o = db.container_orders.find_one({"id": state["order_id"]}, {"_id": 0})
    assert o is not None
    assert o["workshop_id"] == state["ws2_id"]
    assert o["workshop_name"] == "Værksted Syd"
    assert o["workshop_address"].startswith("Industrivej 5")
    assert o["workshop_phone"] == "70 12 34 56"
    assert o["workshop_override"] is False
    assert o["tour_type"] == "vaerksted"


# ========================================================
#   CUSTOMER ORDER — edit + audit
# ========================================================
def test_edit_order_priority_writes_audit(db):
    r = _put(state["la_token"], f"/api/customer-orders/{state['order_id']}",
             {"priority": "haster", "comment": "Opdateret"})
    assert r.status_code == 200, r.text
    assert "priority" in r.json()["changed_fields"]
    o = db.container_orders.find_one({"id": state["order_id"]}, {"_id": 0})
    assert o["priority"] == "haster"
    assert o["comment"] == "Opdateret"
    h = list(db.customer_orders_history.find({"order_id": state["order_id"]}, {"_id": 0}))
    assert len(h) == 1
    assert h[0]["action"] == "edit"
    assert h[0]["before"]["priority"] == "normal"
    assert h[0]["after"]["priority"] == "haster"


def test_edit_order_disallowed_field_ignored():
    r = _put(state["la_token"], f"/api/customer-orders/{state['order_id']}",
             {"company_id": "hack", "material": "tilsidesat"})
    assert r.status_code == 400  # Nothing valid was sent


def test_edit_order_tour_synced(db):
    """Priority change must propagate to the linked tour."""
    o = db.container_orders.find_one({"id": state["order_id"]}, {"_id": 0})
    if o.get("tour_id"):
        tour = db.tours.find_one({"id": o["tour_id"]}, {"_id": 0})
        assert tour["priority"] == "haster"


def test_history_endpoint():
    r = _get(state["la_token"], f"/api/customer-orders/{state['order_id']}/history")
    assert r.status_code == 200, r.text
    entries = r.json()
    assert len(entries) >= 1
    # Newest first
    assert entries[0]["action"] == "edit"


def test_edit_order_no_change_is_noop(db):
    # Re-send same values; should return no_change
    r = _put(state["la_token"], f"/api/customer-orders/{state['order_id']}",
             {"priority": "haster"})
    assert r.status_code == 200
    assert r.json().get("no_change") is True
    h_count = db.customer_orders_history.count_documents({"order_id": state["order_id"]})
    assert h_count == 1  # No new entry written


def test_edit_order_cross_company_blocked():
    """An LA from a different company must NOT be able to edit our order."""
    # Use SA token to create a 2nd company + LA briefly
    sfx2 = uuid.uuid4().hex[:6].upper()
    ca2_email = f"it19-ca2-{sfx2}@e2e.local"
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT19-OTHER-{sfx2}", "customer_id": f"C19O-{sfx2}",
        "company_type": "customer", "admin_email": ca2_email,
        "admin_name": "Other CA",
    })
    if r.status_code != 200:
        pytest.skip("Could not seed cross-tenant — skipping isolation test")
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    state["user_ids"].append(body["created_admin"]["id"])
    from pymongo import MongoClient
    c = MongoClient(MONGO_URL); db2 = c[DB_NAME]
    _accept_invite(db2, body["created_admin"]["id"], "OtherPass2026!")
    other_tok = _login(ca2_email, "OtherPass2026!").json()["token"]
    r2 = _put(other_tok, f"/api/customer-orders/{state['order_id']}",
              {"priority": "senere"})
    assert r2.status_code == 403
    c.close()


# ========================================================
#   CUSTOMER ORDER — hard delete + audit
# ========================================================
def test_delete_order_writes_audit_and_drops_tour(db):
    o = db.container_orders.find_one({"id": state["order_id"]}, {"_id": 0, "tour_id": 1})
    tour_id = o.get("tour_id")
    r = _del(state["la_token"], f"/api/customer-orders/{state['order_id']}")
    assert r.status_code == 200
    assert db.container_orders.find_one({"id": state["order_id"]}) is None
    if tour_id:
        assert db.tours.find_one({"id": tour_id}) is None
    h = list(db.customer_orders_history.find({"order_id": state["order_id"]}, {"_id": 0}).sort("at", -1))
    # First entry (newest) should be the delete
    assert h[0]["action"] == "delete"
    assert h[0]["before"]["id"] == state["order_id"]


def test_history_endpoint_after_delete():
    """History should still be readable after the order is hard-deleted."""
    r = _get(state["la_token"], f"/api/customer-orders/{state['order_id']}/history")
    assert r.status_code == 200
    entries = r.json()
    # 1 edit + 1 delete = at least 2
    assert len(entries) >= 2
    actions = [e["action"] for e in entries]
    assert "edit" in actions
    assert "delete" in actions
