"""Iteration 13 — backend regression for:
  (A) Visibility filter on GET /api/locations/{code}/containers
      * Anonymous (no Authorization header) sees ONLY complete containers
      * super_admin Bearer sees ALL containers + `complete: bool` flag
      * location_admin Bearer (managing the plads) sees ALL
      * order-role Bearer sees only complete (incomplete are hidden)
  (B) `_container_count_for` default is now 0 (was 6) — brand-new plads with
      no container_counts row returns 0 containers per material.
  (C) POST /api/locations/{code}/containers/add increments count by 1
      (or by `delta`). New slot appears for admin but is filtered out for
      anonymous/order users until override completes it.
  (D) PUT /api/locations/{code}/containers/override saves full lock set; the
      new slot then appears as `complete: true` to anonymous callers too.
  (E) GET /api/container-orders/by-location/{code} enriches each order with a
      `container_id_resolved` field. Regular flow → default container_id.
      Custom (tilpasset) flow → user-entered id.

Throwaway tenants use the IT13- prefix and are cleaned at module teardown.
The user's live data (Argo A/S, KØGE etc.) is untouched.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8080").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()
CUST_ADMIN_EMAIL = f"it13-cadm-{SUFFIX}@e2e.local"
CUST_ADMIN_PASS = "CustomerAdmin2026!"
LADMIN_EMAIL = f"it13-ladm-{SUFFIX}@e2e.local"
LADMIN_PASS = "Pernille2026!"
ORDER_EMAIL = f"it13-order-{SUFFIX}@e2e.local"
ORDER_PASS = "OrderUser2026!"

state = {
    "company_ids": [],
    "user_ids": [],
    "loc_codes": [],
    "order_ids": [],
    "tour_ids": [],
}


# ---------- mongo fixture --------------------------------------------------
@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end(db):
    yield
    try:
        emails = [CUST_ADMIN_EMAIL, LADMIN_EMAIL, ORDER_EMAIL]
        db.users.delete_many({"$or": [
            {"id": {"$in": state["user_ids"]}},
            {"email": {"$in": emails}},
        ]})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.locations.delete_many({"code": {"$in": state["loc_codes"]}})
        db.container_orders.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.container_overrides.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.container_counts.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.tours.delete_many({"id": {"$in": state["tour_ids"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
    except Exception as e:  # noqa: BLE001
        print(f"[cleanup] {e}")


# ---------- helpers --------------------------------------------------------
def _login(email, password):
    return requests.post(f"{API}/api/auth/login",
                         json={"email": email, "password": password}, timeout=15)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _get(token, path):
    return requests.get(f"{API}{path}", headers=_h(token) if token else {}, timeout=15)


def _post(token, path, data=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=data or {}, timeout=20)


def _put(token, path, data):
    return requests.put(f"{API}{path}", headers=_h(token), json=data, timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None, f"No invite for user_id={user_id}"
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": password}, timeout=15)
    assert r.status_code == 200, r.text


# ---------- 0. seed: SA login + customer org + multi-role users ------------
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_customer_org_and_users(db):
    # customer company + customer_admin via SA
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT13-CUST-{SUFFIX}",
        "customer_id": f"C13-{SUFFIX}",
        "company_type": "customer",
        "admin_email": CUST_ADMIN_EMAIL,
        "admin_name": "IT13 Customer Admin",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    state["user_ids"].append(body["created_admin"]["id"])
    _accept_invite(db, body["created_admin"]["id"], CUST_ADMIN_PASS)

    r2 = _login(CUST_ADMIN_EMAIL, CUST_ADMIN_PASS)
    assert r2.status_code == 200, r2.text
    state["ca_token"] = r2.json()["token"]

    # CA creates plads
    r3 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT13-PLADS-{SUFFIX}",
        "city": "IT13 City",
        "address": "IT13 Street 1",
    })
    assert r3.status_code == 200, r3.text
    code = r3.json().get("code") or r3.json().get("location_code")
    assert code
    state["loc_codes"].append(code)
    state["code"] = code

    # location_admin
    r4 = _post(state["ca_token"], "/api/org/users", {
        "email": LADMIN_EMAIL,
        "name": "IT13 Loc Admin",
        "role": "location_admin",
        "location_codes": [code],
    })
    assert r4.status_code == 200, r4.text
    state["ladmin_id"] = r4.json()["id"]
    state["user_ids"].append(state["ladmin_id"])
    _accept_invite(db, state["ladmin_id"], LADMIN_PASS)
    state["la_token"] = _login(LADMIN_EMAIL, LADMIN_PASS).json()["token"]

    # order user
    r5 = _post(state["la_token"], "/api/org/users", {
        "email": ORDER_EMAIL,
        "name": "IT13 Order",
        "role": "order",
        "location_code": code,
    })
    assert r5.status_code == 200, r5.text
    state["order_id"] = r5.json()["id"]
    state["user_ids"].append(state["order_id"])
    _accept_invite(db, state["order_id"], ORDER_PASS)
    state["ord_token"] = _login(ORDER_EMAIL, ORDER_PASS).json()["token"]


# =====================================================================
#  PART A — default count == 0
# =====================================================================
def test_default_container_count_is_zero_anonymous():
    """Brand-new plads with no container_counts row should expose 0
    containers per material to anonymous callers."""
    r = requests.get(f"{API}/api/locations/{state['code']}/containers?material=Pap",
                     timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["containers_per"] == 0, \
        f"Expected default 0 containers, got {body['containers_per']}"
    assert body["containers"] == []


def test_default_container_count_is_zero_for_admin():
    r = _get(state["la_token"],
             f"/api/locations/{state['code']}/containers?material=Pap")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["containers_per"] == 0
    assert body["containers"] == []


# =====================================================================
#  PART B — POST /containers/add increments by 1
# =====================================================================
def test_add_container_increments_by_one():
    code = state["code"]
    r = _post(state["la_token"], f"/api/locations/{code}/containers/add",
              {"material": "Pap"})
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == 1

    r2 = _post(state["la_token"], f"/api/locations/{code}/containers/add",
               {"material": "Pap"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["containers_per"] == 2


def test_add_container_with_delta():
    """`delta` query/body should bump by more than 1 in one call."""
    code = state["code"]
    r = _post(state["la_token"], f"/api/locations/{code}/containers/add",
              {"material": "Glas", "delta": 3})
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == 3


# =====================================================================
#  PART C — Visibility filter
# =====================================================================
def test_new_slot_hidden_from_anonymous_until_complete():
    """Slot was added by admin but has no override → anonymous must NOT see
    it. Admin (super_admin/location_admin) DOES see it with complete:false."""
    code = state["code"]

    # Anonymous → 0 visible (none complete)
    r_anon = requests.get(f"{API}/api/locations/{code}/containers?material=Pap",
                          timeout=15)
    assert r_anon.status_code == 200, r_anon.text
    assert r_anon.json()["containers_per"] == 2  # raw count is still 2
    assert r_anon.json()["containers"] == [], "Incomplete slots must be hidden"

    # super_admin → both visible, complete:false on each
    r_sa = _get(state["sa_token"],
                f"/api/locations/{code}/containers?material=Pap")
    assert r_sa.status_code == 200, r_sa.text
    body_sa = r_sa.json()
    assert len(body_sa["containers"]) == 2
    for c in body_sa["containers"]:
        assert c["complete"] is False, \
            f"Expected complete=False for {c['label']}, got {c['complete']}"
        assert c["address"] == "" and c["container_id"] == ""

    # location_admin → also both visible
    r_la = _get(state["la_token"],
                f"/api/locations/{code}/containers?material=Pap")
    assert r_la.status_code == 200, r_la.text
    assert len(r_la.json()["containers"]) == 2

    # order user → only complete (none yet) → empty list
    r_ord = _get(state["ord_token"],
                 f"/api/locations/{code}/containers?material=Pap")
    assert r_ord.status_code == 200, r_ord.text
    assert r_ord.json()["containers"] == [], \
        "Order role should be filtered same as anonymous"


def test_override_makes_slot_complete_visible_to_anon():
    """After PUT /override with non-empty address+id, the slot becomes
    `complete:true` and is returned to anonymous callers."""
    code = state["code"]

    # Save full override on Container 1
    payload = {
        "material": "Pap",
        "container_label": "Container 1",
        "custom_address": "IT13 Saved Addr 5",
        "custom_container_id": "PAP-001",
        "open_from": "07:00",
        "open_to": "17:00",
        "locked_address": True,
        "locked_container_id": True,
        "locked_hours": False,
    }
    r = _put(state["la_token"],
             f"/api/locations/{code}/containers/override", payload)
    assert r.status_code == 200, r.text

    # Anonymous now sees exactly Container 1
    r_anon = requests.get(f"{API}/api/locations/{code}/containers?material=Pap",
                          timeout=15)
    assert r_anon.status_code == 200, r_anon.text
    body = r_anon.json()
    assert len(body["containers"]) == 1
    c = body["containers"][0]
    assert c["label"] == "Container 1"
    assert c["complete"] is True
    assert c["address"] == "IT13 Saved Addr 5"
    assert c["container_id"] == "PAP-001"
    assert c["locked_address"] is True
    assert c["locked_container_id"] is True
    assert c["locked_hours"] is False

    # Order user also sees just Container 1
    r_ord = _get(state["ord_token"],
                 f"/api/locations/{code}/containers?material=Pap")
    assert r_ord.status_code == 200
    assert len(r_ord.json()["containers"]) == 1
    assert r_ord.json()["containers"][0]["container_id"] == "PAP-001"

    # Admin still sees both (Container 2 = incomplete:false)
    r_la = _get(state["la_token"],
                f"/api/locations/{code}/containers?material=Pap")
    assert r_la.status_code == 200
    cs = r_la.json()["containers"]
    assert len(cs) == 2
    by_label = {c["label"]: c for c in cs}
    assert by_label["Container 1"]["complete"] is True
    assert by_label["Container 2"]["complete"] is False
    assert by_label["Container 2"]["address"] == ""
    assert by_label["Container 2"]["container_id"] == ""


def test_invalid_token_falls_back_to_anonymous_filter():
    """A bad/expired Authorization header must NOT crash and must still hide
    incomplete slots (treat as anonymous)."""
    code = state["code"]
    r = requests.get(
        f"{API}/api/locations/{code}/containers?material=Pap",
        headers={"Authorization": "Bearer not-a-real-token"}, timeout=15,
    )
    assert r.status_code == 200, r.text
    # Still only the complete one
    assert len(r.json()["containers"]) == 1


# =====================================================================
#  PART D — container_id_resolved enrichment
# =====================================================================
def test_orders_by_location_resolves_default_container_id(db):
    """An order placed via the regular flow on Container 1 (default id
    'PAP-001') must have container_id_resolved=='PAP-001'."""
    code = state["code"]
    payload = {
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_container_id": "",
        "custom_address": "IT13 Submit Addr A",
        "priority": "normal",
        "comment": "",
        "open_from": "",
        "open_to": "",
        "order_date": "",
        "plads_name": "",
        "tour_type": "normal",
    }
    r = requests.post(f"{API}/api/customer-orders/submit",
                      headers=_h(state["ord_token"]), json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    state["order_ids"].append(body["order_id"])
    state["tour_ids"].append(body["tour_id"])

    r2 = _get(state["la_token"], f"/api/container-orders/by-location/{code}")
    assert r2.status_code == 200, r2.text
    orders = r2.json()
    match = next((o for o in orders if o["id"] == body["order_id"]), None)
    assert match is not None
    assert match.get("container_id_resolved") == "PAP-001", \
        f"Expected 'PAP-001', got {match.get('container_id_resolved')!r}"


def test_orders_by_location_resolves_custom_override_id(db):
    """Custom (tilpasset) order with custom_container_id='HACK-9' must have
    container_id_resolved=='HACK-9' (per-order override wins over default).

    NOTE: Container 1 has locked_container_id=True, so we use Container 2
    (incomplete slot, no lock) to verify the override path. To allow the
    order to actually go through we first complete Container 2 with a
    different default id and locked_container_id=False.
    """
    code = state["code"]
    # Make Container 2 complete with locked_container_id=False so the user's
    # custom value isn't zeroed-out on submit.
    r_pre = _put(state["la_token"],
                 f"/api/locations/{code}/containers/override", {
                     "material": "Pap",
                     "container_label": "Container 2",
                     "custom_address": "IT13 Addr B",
                     "custom_container_id": "PAP-002",
                     "open_from": "07:00",
                     "open_to": "17:00",
                     "locked_address": False,
                     "locked_container_id": False,
                     "locked_hours": False,
                 })
    assert r_pre.status_code == 200, r_pre.text

    payload = {
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 2",
        "custom_container_id": "HACK-9",
        "custom_address": "IT13 Submit Addr B",
        "priority": "normal",
        "comment": "",
        "open_from": "",
        "open_to": "",
        "order_date": "",
        "plads_name": "",
        "tour_type": "normal",
    }
    r = requests.post(f"{API}/api/customer-orders/submit",
                      headers=_h(state["ord_token"]), json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    state["order_ids"].append(body["order_id"])
    state["tour_ids"].append(body["tour_id"])

    r2 = _get(state["la_token"], f"/api/container-orders/by-location/{code}")
    assert r2.status_code == 200, r2.text
    match = next((o for o in r2.json() if o["id"] == body["order_id"]), None)
    assert match is not None
    assert match.get("container_id_resolved") == "HACK-9", \
        f"Expected 'HACK-9', got {match.get('container_id_resolved')!r}"
