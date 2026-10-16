"""Iteration 11 — backend regression tests for:
  - blank-state super_admin login
  - super_admin creates customer org -> invitation row used=False
  - accept-invitation flow lets customer_admin login
  - customer_admin creates 2 locations
  - customer_admin creates location_admin with MULTIPLE location_codes
  - PUT /api/org/users/{id} can ADD or REMOVE plads from location_admin
  - location_admin GET /api/org/locations returns BOTH managed pladser
  - location_admin creates order user in managed plads (200) / outside (403)
  - location_admin GET /api/org/users -> employees across ALL managed pladser
  - location_admin DELETE /api/org/users/{id} on ACTIVE user (no inactivate-first)
  - GET /api/locations/{code}/containers default containers_per=6
  - POST /api/locations/{code}/containers/add increments
  - PUT  /api/locations/{code}/containers/override saves custom + lock fields
  - POST /api/customer-orders/submit with custom_container_id only affects
    THAT single order + the matching tour (default override NOT touched)

Cleans up ALL created data at the end so the DB stays "blank" except
for the super_admin.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8080").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"

SUFFIX = uuid.uuid4().hex[:6]
CUST_ADMIN_EMAIL = f"testadmin-{SUFFIX}@e2e.local"
CUST_ADMIN_PASS = "CustomerAdmin2026!"
LADMIN_EMAIL = f"tester-{SUFFIX}@e2e.local"
LADMIN_PASS = "Pernille2026!"
ORDER_EMAIL = f"orderuser-{SUFFIX}@e2e.local"
ORDER_PASS = "OrderUser2026!"

state = {}  # shared across tests in this module


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end(db):
    """Wipe any test-created data after the module is done so the env stays blank."""
    yield
    try:
        db.users.delete_many({"email": {"$ne": SA_EMAIL}})
        db.companies.delete_many({})
        db.plads.delete_many({})
        db.locations.delete_many({})
        db.container_orders.delete_many({})
        db.container_overrides.delete_many({})
        db.container_counts.delete_many({})
        db.tours.delete_many({})
        db.invitation_tokens.delete_many({})
    except Exception as e:  # noqa: BLE001
        print(f"[cleanup] {e}")


def _login(email, password):
    return requests.post(f"{API}/api/auth/login",
                         json={"email": email, "password": password}, timeout=15)


def _post(token, path, data=None):
    return requests.post(f"{API}{path}",
                         headers={"Authorization": f"Bearer {token}"},
                         json=data or {}, timeout=20)


def _get(token, path):
    return requests.get(f"{API}{path}",
                        headers={"Authorization": f"Bearer {token}"}, timeout=15)


def _put(token, path, data):
    return requests.put(f"{API}{path}",
                        headers={"Authorization": f"Bearer {token}"},
                        json=data, timeout=15)


def _delete(token, path):
    return requests.delete(f"{API}{path}",
                           headers={"Authorization": f"Bearer {token}"}, timeout=15)


# ----- baseline ---------------------------------------------------------------
def test_blank_state_only_super_admin(db):
    """Pre-test invariant: only super_admin exists."""
    user_count = db.users.count_documents({})
    assert user_count == 1, f"Expected 1 user, found {user_count}"
    only = db.users.find_one({}, {"_id": 0, "email": 1, "role": 1})
    assert only["email"] == SA_EMAIL
    assert only["role"] == "super_admin"


def test_super_admin_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "super_admin"
    state["sa_token"] = body["token"]


# ----- create customer org + invitation ----------------------------------------
def test_super_admin_creates_customer_org(db):
    name = f"ARGO-IT11-{SUFFIX}"
    cust_id = f"K-IT11-{SUFFIX.upper()}"
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": name,
        "customer_id": cust_id,
        "company_type": "customer",
        "admin_email": CUST_ADMIN_EMAIL,
        "admin_name": "Test Customer Admin",
        "admin_phone": "+45 11 22 33 44",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company"]["name"] == name
    assert body["created_admin"]["email"] == CUST_ADMIN_EMAIL
    state["company_id"] = body["company"]["id"]
    state["ca_user_id"] = body["created_admin"]["id"]

    # Token row must exist and be unused
    tk = db.invitation_tokens.find_one({"user_id": state["ca_user_id"], "used": False})
    assert tk is not None, "invitation_tokens row missing or already used"
    assert tk["used"] is False
    state["ca_invite_token"] = tk["token"]


def test_login_blocked_until_invitation_accepted():
    r = _login(CUST_ADMIN_EMAIL, CUST_ADMIN_PASS)
    # Account is invitation_status=pending so login MUST fail
    assert r.status_code in (401, 403), r.text


def test_accept_invitation_sets_password():
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": state["ca_invite_token"],
                            "new_password": CUST_ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("email") == CUST_ADMIN_EMAIL


def test_customer_admin_can_login_now():
    r = _login(CUST_ADMIN_EMAIL, CUST_ADMIN_PASS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "customer_admin"
    state["ca_token"] = body["token"]


# ----- customer_admin creates 2 locations --------------------------------------
def test_customer_admin_creates_two_locations():
    for label in ("KOGE-IT11", "ROSKILDE-IT11"):
        r = _post(state["ca_token"], "/api/org/locations", {
            "name": f"{label}-{SUFFIX}",
            "city": label,
            "address": f"{label}vej 1",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        code_key = "code" if body.get("code") else "location_code"
        state.setdefault("loc_codes", []).append(body.get(code_key) or body.get("location_code"))
    assert len(state["loc_codes"]) == 2
    assert all(state["loc_codes"]), f"Empty codes returned: {state['loc_codes']}"


# ----- location_admin multi-location -------------------------------------------
def test_customer_admin_creates_location_admin_with_multi_locations(db):
    r = _post(state["ca_token"], "/api/org/users", {
        "email": LADMIN_EMAIL,
        "name": "Test Location Admin",
        "role": "location_admin",
        "location_codes": state["loc_codes"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["ladmin_user_id"] = body["id"]

    # Fetch full user record from DB for assigned_plads_ids check
    udoc = db.users.find_one({"id": state["ladmin_user_id"]}, {"_id": 0})
    assert udoc is not None
    assert set(udoc["assigned_plads_ids"]) == set(state["loc_codes"]), \
        f"assigned_plads_ids={udoc['assigned_plads_ids']} expected {state['loc_codes']}"

    # GET /org/users returns the user with both codes
    r2 = _get(state["ca_token"], "/api/org/users")
    assert r2.status_code == 200, r2.text
    matches = [u for u in r2.json() if u.get("id") == state["ladmin_user_id"]]
    assert len(matches) == 1
    assert set(matches[0].get("assigned_plads_ids") or []) == set(state["loc_codes"])

    # Capture invitation token + accept it so the location_admin can login
    tk = db.invitation_tokens.find_one(
        {"user_id": state["ladmin_user_id"], "used": False},
        sort=[("created_at", -1)],
    )
    assert tk is not None, "No invitation token created for location_admin"
    r3 = requests.post(f"{API}/api/auth/accept-invitation",
                       json={"token": tk["token"], "new_password": LADMIN_PASS}, timeout=15)
    assert r3.status_code == 200, r3.text


def test_put_org_user_can_remove_then_re_add_plads(db):
    """customer_admin can shrink + grow the location_admin's assigned pladser."""
    # Remove second plads
    keep = [state["loc_codes"][0]]
    r = _put(state["ca_token"], f"/api/org/users/{state['ladmin_user_id']}",
             {"location_codes": keep})
    assert r.status_code == 200, r.text
    udoc = db.users.find_one({"id": state["ladmin_user_id"]}, {"_id": 0})
    assert udoc["assigned_plads_ids"] == keep

    # Add it back
    r2 = _put(state["ca_token"], f"/api/org/users/{state['ladmin_user_id']}",
              {"location_codes": state["loc_codes"]})
    assert r2.status_code == 200, r2.text
    udoc2 = db.users.find_one({"id": state["ladmin_user_id"]}, {"_id": 0})
    assert set(udoc2["assigned_plads_ids"]) == set(state["loc_codes"])


def test_location_admin_login_sees_both_locations():
    r = _login(LADMIN_EMAIL, LADMIN_PASS)
    assert r.status_code == 200, r.text
    state["la_token"] = r.json()["token"]

    rl = _get(state["la_token"], "/api/org/locations")
    assert rl.status_code == 200, rl.text
    items = rl.json()
    returned_codes = {it.get("code") or it.get("location_code") for it in items}
    assert set(state["loc_codes"]).issubset(returned_codes), \
        f"got {returned_codes}, expected {state['loc_codes']}"


# ----- location_admin order-user creation --------------------------------------
def test_location_admin_creates_order_user_in_managed_plads(db):
    target_code = state["loc_codes"][0]
    r = _post(state["la_token"], "/api/org/users", {
        "email": ORDER_EMAIL,
        "name": "Test Order User",
        "role": "order",
        "location_code": target_code,
    })
    assert r.status_code == 200, r.text
    state["order_user_id"] = r.json()["id"]

    # accept its invitation so we know the active-delete path works on
    # a TRULY active account
    tk = db.invitation_tokens.find_one(
        {"user_id": state["order_user_id"], "used": False},
        sort=[("created_at", -1)],
    )
    assert tk is not None
    racc = requests.post(f"{API}/api/auth/accept-invitation",
                         json={"token": tk["token"], "new_password": ORDER_PASS}, timeout=15)
    assert racc.status_code == 200, racc.text


def test_location_admin_cannot_create_user_outside_managed():
    r = _post(state["la_token"], "/api/org/users", {
        "email": f"forbid-{SUFFIX}@e2e.local",
        "name": "Should Fail",
        "role": "order",
        "location_code": "9999",  # not in managed set
    })
    assert r.status_code in (403, 404), r.text


def test_location_admin_list_users_union_of_pladser():
    r = _get(state["la_token"], "/api/org/users")
    assert r.status_code == 200, r.text
    users = r.json()
    ids = {u["id"] for u in users}
    assert state["order_user_id"] in ids
    # only role=order should be returned for location_admin
    assert all(u.get("role") == "order" for u in users), \
        f"got non-order roles: {[u.get('role') for u in users]}"


def test_location_admin_can_delete_active_order_user(db):
    """No more 'Inaktivér først' — DELETE on an active user must succeed."""
    udoc = db.users.find_one({"id": state["order_user_id"]}, {"_id": 0})
    assert udoc is not None and udoc.get("active") is True, \
        f"Pre-condition failed: order user is not active: {udoc}"

    r = _delete(state["la_token"], f"/api/org/users/{state['order_user_id']}")
    assert r.status_code == 200, r.text

    # Verify it's gone (hard delete per spec)
    udoc2 = db.users.find_one({"id": state["order_user_id"]})
    assert udoc2 is None, "Expected hard delete; user still present"


# ----- container endpoints -----------------------------------------------------
def test_get_location_containers_default_six():
    code = state["loc_codes"][0]
    r = _get(state["ca_token"], f"/api/locations/{code}/containers?material=Pap")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["containers_per"] == 6
    assert len(body["containers"]) == 6


def test_add_container_to_material_increments():
    code = state["loc_codes"][0]
    r = _post(state["ca_token"],
              f"/api/locations/{code}/containers/add",
              {"material": "Pap"})
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == 7

    r2 = _get(state["ca_token"], f"/api/locations/{code}/containers?material=Pap")
    assert r2.status_code == 200
    assert r2.json()["containers_per"] == 7


def test_container_override_persists_lock_and_fields():
    code = state["loc_codes"][0]
    payload = {
        "material": "Pap",
        "container_label": "Container 1",
        "custom_address": "Special Lane 9, 4600 KOGE",
        "custom_container_id": "PAP-DEFAULT-001",
        "open_from": "07:00",
        "open_to": "16:00",
        "locked_address": True,
        "locked_hours": True,
    }
    r = _put(state["ca_token"], f"/api/locations/{code}/containers/override", payload)
    assert r.status_code == 200, r.text

    r2 = _get(state["ca_token"], f"/api/locations/{code}/containers?material=Pap")
    assert r2.status_code == 200, r2.text
    entry = next(c for c in r2.json()["containers"] if c["label"] == "Container 1")
    assert entry["address"] == payload["custom_address"]
    assert entry["container_id"] == payload["custom_container_id"]
    assert entry["open_from"] == "07:00"
    assert entry["open_to"] == "16:00"
    assert entry["locked_address"] is True
    assert entry["locked_hours"] is True


def test_submit_order_with_override_does_not_modify_default(db):
    """Submitting an order with custom_container_id must ONLY affect:
       - container_orders.container_id_override = 'OVERRIDE-XYZ'
       - the corresponding tour.container = 'OVERRIDE-XYZ'
    The container_overrides default doc must remain unchanged ('PAP-DEFAULT-001').
    """
    code = state["loc_codes"][0]
    override_id = f"OVERRIDE-{SUFFIX.upper()}"
    payload = {
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_container_id": override_id,
        "custom_address": "One-off Address 42",
        "priority": "normal",
        "comment": "",
        "open_from": "",
        "open_to": "",
        "order_date": "",
        "plads_name": "",
        "tour_type": "normal",
    }
    # Need an authenticated context (so 'Leveringsadresse er påkrævet' is exercised)
    r = requests.post(f"{API}/api/customer-orders/submit",
                      headers={"Authorization": f"Bearer {state['ca_token']}"},
                      json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    state["order_id"] = body["order_id"]
    state["tour_id"] = body["tour_id"]

    # 1. container_orders has container_id_override = override_id
    order = db.container_orders.find_one({"id": state["order_id"]}, {"_id": 0})
    assert order is not None
    assert order.get("container_id_override") == override_id, \
        f"container_id_override={order.get('container_id_override')}"

    # 2. tour.container == override_id (not the default "PAP-DEFAULT-001")
    tour = db.tours.find_one({"id": state["tour_id"]}, {"_id": 0})
    assert tour is not None
    assert tour.get("container") == override_id, \
        f"tour.container={tour.get('container')} expected {override_id}"

    # 3. The base override doc for Pap / Container 1 is UNCHANGED.
    base = db.container_overrides.find_one(
        {"location_code": code, "material": "Pap", "container_label": "Container 1"},
        {"_id": 0},
    )
    assert base is not None
    assert base.get("custom_container_id") == "PAP-DEFAULT-001", \
        f"Default override was overwritten: {base}"


# ----- sanity: super_admin remaining unchanged ---------------------------------
def test_super_admin_still_only_admin_in_users_table(db):
    """Super admin row exists and still has role=super_admin."""
    udoc = db.users.find_one({"email": SA_EMAIL}, {"_id": 0})
    assert udoc is not None
    assert udoc["role"] == "super_admin"
