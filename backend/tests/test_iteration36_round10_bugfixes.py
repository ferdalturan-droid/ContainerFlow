"""Iteration 36 — Bug fixes from user round 10:

1. Multi-location employee save roundtrip — verificér at update PUT med
   `location_codes` reelt gemmer alle koder + at GET viser dem korrekt.
2. Kommentar på order — verificér at den persisteres + returneres i alle
   tre endpoints (submit, by-location, customer-orders).
"""
import os
import uuid
import bcrypt
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SUFFIX = uuid.uuid4().hex[:6].upper()
CA_EMAIL = f"it36-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"

state = {"user_ids": [], "company_ids": [], "plads_ids": [], "order_ids": []}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    if state["user_ids"]:
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
    if state["company_ids"]:
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
    if state["plads_ids"]:
        db.plads.delete_many({"id": {"$in": state["plads_ids"]}})
    if state["order_ids"]:
        db.container_orders.delete_many({"id": {"$in": state["order_ids"]}})


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _login(email, pw):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def test_setup(db):
    """Setup: customer + CA + 3 lokationer."""
    cid = str(uuid.uuid4())
    db.companies.insert_one({"id": cid, "name": f"IT36 {SUFFIX}",
                              "company_type": "customer", "active": True})
    state["company_ids"].append(cid)
    state["cid"] = cid

    h = bcrypt.hashpw(CA_PASS.encode(), bcrypt.gensalt()).decode()
    ca_id = str(uuid.uuid4())
    db.users.insert_one({
        "id": ca_id, "email": CA_EMAIL, "name": "IT36 CA",
        "password_hash": h, "role": "customer_admin",
        "company_id": cid, "active": True, "invitation_status": "active",
    })
    state["user_ids"].append(ca_id)

    for code in [f"IT36{SUFFIX}A", f"IT36{SUFFIX}B", f"IT36{SUFFIX}C"]:
        pid = str(uuid.uuid4())
        db.plads.insert_one({
            "id": pid, "location_code": code, "name": f"Plads {code}",
            "company_id": cid, "address": "Vej 1", "city": "Aarhus",
            "active": True, "containers_per_material": 2,
        })
        state["plads_ids"].append(pid)
    state["codes"] = [f"IT36{SUFFIX}A", f"IT36{SUFFIX}B", f"IT36{SUFFIX}C"]
    state["ca_token"] = _login(CA_EMAIL, CA_PASS)


# ============================================================
# Opgave 1: Multi-loc employee SAVE-roundtrip
# ============================================================
def test_create_employee_with_3_locations_roundtrip(db):
    """Opret order-emp med 3 lokationer. Verificér via GET /api/org/users at
    backend returnerer ALLE 3 koder i assigned_plads_ids."""
    emp_email = f"it36-emp-{SUFFIX}@e2e.local"
    r = requests.post(f"{API}/api/org/users", json={
        "name": "IT36 Multi", "email": emp_email,
        "role": "order",
        "location_code": state["codes"][0],
        "location_codes": state["codes"],
        "send_invitation": False,
    }, headers=_h(state["ca_token"]), timeout=15)
    assert r.status_code == 200, r.text
    emp_id = r.json()["id"]
    state["emp_id"] = emp_id
    state["emp_email"] = emp_email
    state["user_ids"].append(emp_id)

    # GET-roundtrip — list users og se medarbejderen
    r = requests.get(f"{API}/api/org/users",
                     headers=_h(state["ca_token"]), timeout=10)
    assert r.status_code == 200
    emps = [u for u in r.json() if u["id"] == emp_id]
    assert len(emps) == 1, f"Forventede 1 medarbejder, fik {len(emps)}"
    emp = emps[0]
    returned_codes = sorted(emp.get("assigned_plads_ids") or [])
    expected = sorted(state["codes"])
    assert returned_codes == expected, \
        f"Forventede {expected}, fik {returned_codes}. Roundtrip fejler!"


def test_update_employee_locations_persists(db):
    """Opdater medarbejderen til kun 2 ud af 3 lokationer.
    Verificér at både DB og GET reflekterer det."""
    target_codes = [state["codes"][0], state["codes"][1]]  # drop C
    r = requests.put(
        f"{API}/api/org/users/{state['emp_id']}",
        json={"location_codes": target_codes},
        headers=_h(state["ca_token"]), timeout=10,
    )
    assert r.status_code == 200, r.text

    # GET-verifikation
    r = requests.get(f"{API}/api/org/users",
                     headers=_h(state["ca_token"]), timeout=10)
    emp = next(u for u in r.json() if u["id"] == state["emp_id"])
    assert sorted(emp.get("assigned_plads_ids") or []) == sorted(target_codes), \
        f"Update fejlede! Fik {emp.get('assigned_plads_ids')}"

    # DB-verifikation
    raw = db.users.find_one({"id": state["emp_id"]}, {"_id": 0})
    assert sorted(raw["assigned_plads_ids"]) == sorted(target_codes)


def test_la_update_employee_multi_locations(db):
    """LA der har 2 lokationer kan opdatere medarbejderens lokationer
    (multi-select)."""
    # Opret LA med 2 lokationer
    la_email = f"it36-la-{SUFFIX}@e2e.local"
    h = bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()
    la_id = str(uuid.uuid4())
    db.users.insert_one({
        "id": la_id, "email": la_email, "name": "IT36 LA",
        "password_hash": h, "role": "location_admin",
        "company_id": state["cid"], "active": True,
        "invitation_status": "active",
        "location_code": state["codes"][0],
        "assigned_plads_ids": [state["codes"][0], state["codes"][1]],
    })
    state["user_ids"].append(la_id)
    la_token = _login(la_email, "TestPass2026!")

    # Først reset emp til kun lokation A
    requests.put(
        f"{API}/api/org/users/{state['emp_id']}",
        json={"location_codes": [state["codes"][0]]},
        headers=_h(state["ca_token"]), timeout=10,
    )

    # LA opdaterer emp til lokation A + B
    target = [state["codes"][0], state["codes"][1]]
    r = requests.put(
        f"{API}/api/org/users/{state['emp_id']}",
        json={"location_codes": target},
        headers=_h(la_token), timeout=10,
    )
    assert r.status_code == 200, r.text

    raw = db.users.find_one({"id": state["emp_id"]}, {"_id": 0})
    assert sorted(raw["assigned_plads_ids"]) == sorted(target)


# ============================================================
# Opgave 2: Kommentar persistens
# ============================================================
def test_order_comment_persists_to_db_and_returned_in_get(db):
    """Submit en ordre med kommentar — verificér at den gemmes i DB OG
    returneres i by-location-endpointet."""
    # Opret container_override så vi kan submit
    pid_logi = str(uuid.uuid4())
    db.companies.insert_one({
        "id": pid_logi, "name": "IT36 Logi", "company_type": "logistics",
        "active": True,
    })
    state["company_ids"].append(pid_logi)

    code = state["codes"][0]
    db.plads.update_one(
        {"location_code": code},
        {"$set": {
            "assigned_logistics_company_ids": [pid_logi],
            "partner_materials": {pid_logi: ["Pap"]},
        }},
    )
    db.container_overrides.insert_one({
        "id": str(uuid.uuid4()), "location_code": code,
        "material": "Pap", "container_label": "Container 1",
        "partner_id": pid_logi,
        "custom_address": "Vej 1, 8000 Aarhus",
        "custom_container_id": "PAP-001",
        "locked_address": False, "locked_hours": False, "locked_container_id": False,
    })
    db.container_counts.insert_one({
        "id": str(uuid.uuid4()), "location_code": code,
        "material": "Pap", "partner_id": pid_logi, "count": 1,
    })

    expected_comment = f"Test-kommentar IT36 {SUFFIX} med specialtegn: ÆØÅ"
    r = requests.post(f"{API}/api/customer-orders/submit", json={
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_address": "Vej 1, 8000 Aarhus",
        "priority": "normal",
        "tour_type": "normal",
        "comment": expected_comment,
        "partner_id": pid_logi,
    }, headers=_h(state["ca_token"]), timeout=15)
    assert r.status_code == 200, r.text
    order_id = r.json()["order_id"]
    state["order_ids"].append(order_id)

    # DB-verifikation
    doc = db.container_orders.find_one({"id": order_id}, {"_id": 0})
    assert doc.get("comment") == expected_comment, \
        f"Kommentar IKKE persisteret. Fik: {doc.get('comment')!r}"

    # by-location endpoint
    r = requests.get(
        f"{API}/api/container-orders/by-location/{code}?all=1",
        headers=_h(state["ca_token"]), timeout=10,
    )
    orders = r.json()
    found = next((o for o in orders if o["id"] == order_id), None)
    assert found is not None
    assert found.get("comment") == expected_comment, \
        f"by-location returnerer IKKE comment. Fik: {found.get('comment')!r}"

    # /container-orders endpoint
    r = requests.get(f"{API}/api/container-orders?location_code={code}",
                     headers=_h(state["ca_token"]), timeout=10)
    orders = r.json()
    found = next((o for o in orders if o["id"] == order_id), None)
    if found is not None:
        assert found.get("comment") == expected_comment, \
            f"/container-orders returnerer IKKE comment. Fik: {found.get('comment')!r}"


def test_empty_comment_handled():
    """Submit ordre uden kommentar — backend skal stadig acceptere."""
    code = state["codes"][0]
    pid_logi = state["company_ids"][1]  # vores logi
    r = requests.post(f"{API}/api/customer-orders/submit", json={
        "location_code": code,
        "material": "Pap",
        "container_number": "Container 1",
        "custom_address": "Vej 1, 8000 Aarhus",
        "priority": "normal",
        "tour_type": "normal",
        "comment": "",
        "partner_id": pid_logi,
    }, headers=_h(state["ca_token"]), timeout=15)
    assert r.status_code == 200
    state["order_ids"].append(r.json()["order_id"])
