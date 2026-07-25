"""Iteration 12 — backend regression for:
  (A) `from_library` separation on /api/superadmin/companies
      * POST with from_library=True hides from default list
      * POST without from_library defaults to False (appears in default list)
      * GET ?include_library=true returns library entries
      * /api/org/logistics-companies returns BOTH regular + library partners

  (B) Role-checks on container/material endpoints:
      * POST /api/locations/{code}/containers/add — 401 / 403 / 200
      * PUT  /api/locations/{code}/containers/override — 403 for order, 200 for ladmin,
              400 if custom_address or custom_container_id missing (merged with existing)
      * DELETE /api/locations/{code}/containers/slot — requires admin; decrements
              count (min 1); removes matching override doc.
      * POST/PUT/DELETE /api/locations/{code}/materials — 401 / 403 / 200

  (C) `locked_container_id`:
      * PUT /containers/override accepts it; GET /containers returns it

  (D) Submit lock enforcement:
      * Order user submits with custom_container_id='HACK' while override has
        locked_container_id=true → resulting order.container_id_override is ''
      * Order user submits with custom_address='HACK' while override has
        locked_address=true → resulting order.customer_address uses override

NOTE: live data MUST NOT be wiped. We track every id/email we created and
clean only those in the module teardown.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

API = os.environ.get("REACT_APP_BACKEND_URL", "https://role-analysis-flow.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()
CUST_ADMIN_EMAIL = f"it12-cadm-{SUFFIX}@e2e.local"
CUST_ADMIN_PASS = "CustomerAdmin2026!"
LADMIN_EMAIL = f"it12-ladm-{SUFFIX}@e2e.local"
LADMIN_PASS = "Pernille2026!"
ORDER_EMAIL = f"it12-order-{SUFFIX}@e2e.local"
ORDER_PASS = "OrderUser2026!"

state = {
    "company_ids": [],          # all companies created by this test (cleanup)
    "user_ids": [],             # all users created by this test (cleanup)
    "loc_codes": [],            # plads codes (cleanup)
    "extra_emails": set(),      # additional users we want to wipe (e.g. SA-created admin)
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
    """Tear down ONLY the entities created by this test module. Live data
    untouched."""
    yield
    try:
        # users by id + by tracked emails (covers admins created via SA POST)
        emails = set(state["extra_emails"]) | {CUST_ADMIN_EMAIL, LADMIN_EMAIL, ORDER_EMAIL}
        db.users.delete_many({"$or": [
            {"id": {"$in": state["user_ids"]}},
            {"email": {"$in": list(emails)}},
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
    return requests.get(f"{API}{path}", headers=_h(token), timeout=15)


def _post(token, path, data=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=data or {}, timeout=20)


def _put(token, path, data):
    return requests.put(f"{API}{path}", headers=_h(token), json=data, timeout=15)


def _delete(token, path):
    return requests.delete(f"{API}{path}", headers=_h(token), timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None, f"No invite for user_id={user_id}"
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": password}, timeout=15)
    assert r.status_code == 200, r.text


# ---------- 0. login super_admin -------------------------------------------
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


# =====================================================================
#  PART A — from_library separation
# =====================================================================
def test_create_library_logistics_partner_hidden_from_default_list():
    name = f"IT12-LIB-{SUFFIX}"
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": name,
        "customer_id": f"LIB-{SUFFIX}",
        "company_type": "logistics",
        "from_library": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    comp = body["company"]
    state["company_ids"].append(comp["id"])
    state["library_company_id"] = comp["id"]
    state["library_company_name"] = name
    assert comp.get("from_library") is True

    # default list (no params) should EXCLUDE this library entry
    r2 = _get(state["sa_token"], "/api/superadmin/companies")
    assert r2.status_code == 200
    names = [c["name"] for c in r2.json()]
    assert name not in names, \
        f"Library partner '{name}' should NOT appear in default list. Got: {names}"

    # include_library=true should INCLUDE it
    r3 = _get(state["sa_token"], "/api/superadmin/companies?include_library=true")
    assert r3.status_code == 200
    names3 = [c["name"] for c in r3.json()]
    assert name in names3, \
        f"Library partner '{name}' must appear with include_library=true. Got: {names3}"


def test_create_normal_company_appears_in_default_list():
    name = f"IT12-NORM-LOGI-{SUFFIX}"
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": name,
        "customer_id": f"NRM-{SUFFIX}",
        "company_type": "logistics",
        # from_library NOT sent — should default to False
    })
    assert r.status_code == 200, r.text
    comp = r.json()["company"]
    state["company_ids"].append(comp["id"])
    state["normal_logi_company_id"] = comp["id"]
    state["normal_logi_company_name"] = name
    # The "from_library" field should be False (or missing in response)
    assert not comp.get("from_library", False)

    r2 = _get(state["sa_token"], "/api/superadmin/companies")
    assert r2.status_code == 200
    names = [c["name"] for c in r2.json()]
    assert name in names, f"Normal logistics '{name}' must show in default list. Got: {names}"


# =====================================================================
#  PART B — seed a customer org + multi-role users
# =====================================================================
def test_create_customer_org_and_users(db):
    # 1) customer company + customer_admin via SA
    name = f"IT12-CUST-{SUFFIX}"
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": name,
        "customer_id": f"CUS-{SUFFIX}",
        "company_type": "customer",
        "admin_email": CUST_ADMIN_EMAIL,
        "admin_name": "IT12 Customer Admin",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    state["cust_company_id"] = body["company"]["id"]
    state["user_ids"].append(body["created_admin"]["id"])
    _accept_invite(db, body["created_admin"]["id"], CUST_ADMIN_PASS)

    # 2) customer_admin logs in
    r2 = _login(CUST_ADMIN_EMAIL, CUST_ADMIN_PASS)
    assert r2.status_code == 200, r2.text
    state["ca_token"] = r2.json()["token"]

    # 3) ca creates one location
    r3 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT12-PLADS-{SUFFIX}",
        "city": "IT12 City",
        "address": "IT12 Street 1",
    })
    assert r3.status_code == 200, r3.text
    code = r3.json().get("code") or r3.json().get("location_code")
    assert code
    state["loc_codes"].append(code)
    state["code"] = code

    # 4) ca creates a location_admin in that plads
    r4 = _post(state["ca_token"], "/api/org/users", {
        "email": LADMIN_EMAIL,
        "name": "IT12 Loc Admin",
        "role": "location_admin",
        "location_codes": [code],
    })
    assert r4.status_code == 200, r4.text
    state["ladmin_id"] = r4.json()["id"]
    state["user_ids"].append(state["ladmin_id"])
    _accept_invite(db, state["ladmin_id"], LADMIN_PASS)
    state["la_token"] = _login(LADMIN_EMAIL, LADMIN_PASS).json()["token"]

    # 5) ladmin creates an order user
    r5 = _post(state["la_token"], "/api/org/users", {
        "email": ORDER_EMAIL,
        "name": "IT12 Order",
        "role": "order",
        "location_code": code,
    })
    assert r5.status_code == 200, r5.text
    state["order_id"] = r5.json()["id"]
    state["user_ids"].append(state["order_id"])
    _accept_invite(db, state["order_id"], ORDER_PASS)
    state["ord_token"] = _login(ORDER_EMAIL, ORDER_PASS).json()["token"]


def test_org_logistics_companies_returns_normal_and_library():
    """Customer admin must see BOTH regular + library logistics partners so
    they can link library partners to their plads."""
    r = _get(state["ca_token"], "/api/org/logistics-companies")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}
    assert state["library_company_id"] in ids, \
        "Library partner missing from /api/org/logistics-companies"
    assert state["normal_logi_company_id"] in ids, \
        "Normal logistics company missing from /api/org/logistics-companies"


# =====================================================================
#  PART C — role checks on /containers/add
# =====================================================================
def test_containers_add_requires_auth():
    code = state["code"]
    r = requests.post(f"{API}/api/locations/{code}/containers/add",
                      json={"material": "Pap"}, timeout=10)
    assert r.status_code == 401, r.text


def test_containers_add_forbidden_for_order_user():
    r = _post(state["ord_token"],
              f"/api/locations/{state['code']}/containers/add",
              {"material": "Pap"})
    assert r.status_code == 403, r.text


def test_containers_add_succeeds_for_location_admin():
    # Capture the current count first — the default was changed from 6 → 0
    # in iteration_13 so we can no longer assume "7 after +1".
    g = requests.get(f"{API}/api/locations/{state['code']}/containers?material=Pap",
                     headers=_h(state["la_token"]))
    before = g.json().get("containers_per", 0)
    r = _post(state["la_token"],
              f"/api/locations/{state['code']}/containers/add",
              {"material": "Pap"})
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == before + 1


def test_containers_add_succeeds_for_customer_admin():
    g = requests.get(f"{API}/api/locations/{state['code']}/containers?material=Pap",
                     headers=_h(state["ca_token"]))
    before = g.json().get("containers_per", 0)
    r = _post(state["ca_token"],
              f"/api/locations/{state['code']}/containers/add",
              {"material": "Pap"})
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == before + 1


# =====================================================================
#  PART D — role checks on /containers/override + locked_container_id
# =====================================================================
def test_override_forbidden_for_order_user():
    r = _put(state["ord_token"],
             f"/api/locations/{state['code']}/containers/override",
             {"material": "Pap", "container_label": "Container 1",
              "custom_address": "X", "custom_container_id": "Y"})
    assert r.status_code == 403, r.text


def test_override_400_missing_address():
    r = _put(state["la_token"],
             f"/api/locations/{state['code']}/containers/override",
             {"material": "Pap", "container_label": "Container 2",
              "custom_address": "", "custom_container_id": "ID-123"})
    assert r.status_code == 400, r.text


def test_override_400_missing_container_id():
    r = _put(state["la_token"],
             f"/api/locations/{state['code']}/containers/override",
             {"material": "Pap", "container_label": "Container 2",
              "custom_address": "Addr 9", "custom_container_id": ""})
    assert r.status_code == 400, r.text


def test_override_success_with_locked_container_id():
    r = _put(state["la_token"],
             f"/api/locations/{state['code']}/containers/override", {
                 "material": "Pap",
                 "container_label": "Container 1",
                 "custom_address": "Locked Lane 7",
                 "custom_container_id": "FORCED-DEFAULT",
                 "open_from": "08:00",
                 "open_to": "15:00",
                 "locked_address": True,
                 "locked_container_id": True,
             })
    assert r.status_code == 200, r.text

    # GET must echo locked_container_id=true + the values
    r2 = _get(state["la_token"],
              f"/api/locations/{state['code']}/containers?material=Pap")
    assert r2.status_code == 200, r2.text
    c1 = next(c for c in r2.json()["containers"] if c["label"] == "Container 1")
    assert c1["locked_container_id"] is True
    assert c1["locked_address"] is True
    assert c1["container_id"] == "FORCED-DEFAULT"
    assert c1["address"] == "Locked Lane 7"


# =====================================================================
#  PART E — DELETE /containers/slot
# =====================================================================
def test_delete_container_slot_requires_admin():
    r = requests.delete(
        f"{API}/api/locations/{state['code']}/containers/slot"
        f"?material=Pap&container_label=Container%208", timeout=10)
    assert r.status_code == 401, r.text

    r2 = _delete(state["ord_token"],
                 f"/api/locations/{state['code']}/containers/slot"
                 f"?material=Pap&container_label=Container%208")
    assert r2.status_code == 403, r2.text


def test_delete_container_slot_decrements_and_drops_override():
    code = state["code"]
    # First save an override on "Container 8" so we can confirm it's deleted
    r0 = _put(state["la_token"],
              f"/api/locations/{code}/containers/override", {
                  "material": "Pap",
                  "container_label": "Container 8",
                  "custom_address": "Slot8 Addr",
                  "custom_container_id": "SLOT-8",
              })
    assert r0.status_code == 200, r0.text

    before = _get(state["la_token"], f"/api/locations/{code}/containers?material=Pap").json()
    before_count = before["containers_per"]
    assert before_count >= 2

    r = _delete(state["la_token"],
                f"/api/locations/{code}/containers/slot"
                f"?material=Pap&container_label=Container%208")
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == before_count - 1

    # confirm override doc gone
    after = _get(state["la_token"], f"/api/locations/{code}/containers?material=Pap").json()
    labels_with_override = [c["label"] for c in after["containers"] if c.get("has_override")]
    assert "Container 8" not in labels_with_override


def test_delete_container_slot_min_one():
    """Repeatedly delete from a different material — count never drops below 1."""
    code = state["code"]
    # Use 'Glas' which still has the default 6
    for _ in range(10):
        r = _delete(state["la_token"],
                    f"/api/locations/{code}/containers/slot"
                    f"?material=Glas&container_label=Container%201")
        assert r.status_code == 200, r.text
    final = _get(state["la_token"], f"/api/locations/{code}/containers?material=Glas").json()
    assert final["containers_per"] == 1, f"Expected min 1, got {final['containers_per']}"


# =====================================================================
#  PART F — role checks on /materials POST/PUT/DELETE
# =====================================================================
def test_materials_add_requires_auth():
    code = state["code"]
    r = requests.post(f"{API}/api/locations/{code}/materials",
                      json={"material": "TestMat"}, timeout=10)
    assert r.status_code == 401, r.text


def test_materials_add_forbidden_for_order():
    r = _post(state["ord_token"],
              f"/api/locations/{state['code']}/materials",
              {"material": "TestMatX"})
    assert r.status_code == 403, r.text


def test_materials_add_put_delete_succeeds_for_ladmin():
    code = state["code"]
    mat = f"IT12Mat-{SUFFIX}"
    new_mat = f"IT12Mat-{SUFFIX}-renamed"

    r1 = _post(state["la_token"], f"/api/locations/{code}/materials", {"material": mat})
    assert r1.status_code == 200, r1.text
    assert mat in r1.json()["materials"]

    r2 = _put(state["la_token"], f"/api/locations/{code}/materials",
              {"old_name": mat, "new_name": new_mat})
    assert r2.status_code == 200, r2.text
    assert new_mat in r2.json()["materials"]

    r3 = _delete(state["la_token"],
                 f"/api/locations/{code}/materials?material={new_mat}")
    assert r3.status_code == 200, r3.text


def test_materials_put_forbidden_for_order():
    r = _put(state["ord_token"],
             f"/api/locations/{state['code']}/materials",
             {"old_name": "Pap", "new_name": "PapX"})
    assert r.status_code == 403, r.text


def test_materials_delete_forbidden_for_order():
    r = _delete(state["ord_token"],
                f"/api/locations/{state['code']}/materials?material=Pap")
    assert r.status_code == 403, r.text


# =====================================================================
#  PART G — submit lock enforcement
# =====================================================================
def test_submit_with_locked_container_id_clears_override(db):
    """When override.locked_container_id=true and an order POSTs
    custom_container_id='HACK', the resulting order's container_id_override
    MUST be empty (the system forces the default)."""
    code = state["code"]
    payload = {
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_container_id": "HACK-VALUE",
        "custom_address": "ORDER-SIDE-HACK ADDR",
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

    order = db.container_orders.find_one({"id": body["order_id"]}, {"_id": 0})
    assert order is not None
    # locked_container_id is True → container_id_override must be ''
    assert order.get("container_id_override", "") == "", \
        f"Expected empty container_id_override, got {order.get('container_id_override')!r}"


def test_submit_with_locked_address_uses_override(db):
    """When locked_address=true on the override, the resulting order's
    customer_address must equal the override's saved address, regardless of
    the user-supplied custom_address."""
    code = state["code"]
    payload = {
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_container_id": "",
        "custom_address": "USER-TRYING-TO-CHANGE",
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

    order = db.container_orders.find_one({"id": body["order_id"]}, {"_id": 0})
    assert order is not None
    assert order.get("customer_address") == "Locked Lane 7", \
        f"Expected locked address 'Locked Lane 7', got {order.get('customer_address')!r}"
