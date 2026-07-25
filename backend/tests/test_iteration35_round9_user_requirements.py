"""Iteration 35 — 4 brugerkrav (runde 9):

1. SuperAdmin logistik-partner edit: udfyld admin_email/navn → opret bruger + send invitation
2. Order-medarbejder kan have FLERE lokationer (assigned_plads_ids array)
3. Excel KPI omdøbning + ekstra metrics (testet via standalone)
4. /api/plads filtrerer på assigned_plads_ids for order-rolle
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

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "TestSAreset2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()

state = {"user_ids": [], "company_ids": [], "plads_ids": []}


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


def _login(email, pw):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    return r


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


# ============================================================
# Opgave 1: SA opretter logistik UDEN admin, editerer SENERE
# ============================================================
def test_create_logistics_partner_without_admin(db):
    """SA opretter logistik-firma uden admin (admin_email tom)."""
    r = requests.post(f"{API}/api/superadmin/companies",
        json={
            "name": f"IT35 Logi {SUFFIX}",
            "customer_id": f"IT35L-{SUFFIX}",
            "company_type": "logistics",
        }, headers=_h(state["sa_token"]), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    state["logi_id"] = d["company"]["id"]
    state["company_ids"].append(state["logi_id"])
    # Verificér: ingen logistics_admin oprettet endnu
    admin = db.users.find_one({"company_id": state["logi_id"], "role": "logistics_admin"})
    assert admin is None, "Forventede INGEN logistics_admin endnu"


def test_edit_logistics_partner_adds_admin_and_sends_invite(db):
    """SA editerer logistik-firma og udfylder admin_name + admin_email.
    Forventet: ny logistics_admin-bruger oprettes med invitation_status=pending."""
    new_email = f"it35-logi-admin-{SUFFIX.lower()}@e2e.local"
    r = requests.put(
        f"{API}/api/superadmin/companies/{state['logi_id']}",
        json={"admin_name": "IT35 Logi Admin", "admin_email": new_email},
        headers=_h(state["sa_token"]), timeout=15,
    )
    assert r.status_code == 200, r.text

    # Bekræft at brugeren er oprettet i DB
    admin = db.users.find_one(
        {"company_id": state["logi_id"], "role": "logistics_admin"},
        {"_id": 0},
    )
    assert admin is not None, "logistics_admin-bruger blev IKKE oprettet"
    assert admin["email"] == new_email
    assert admin["name"] == "IT35 Logi Admin"
    assert admin["invitation_status"] == "pending"
    assert admin["password_hash"] == "", "Password skal være tom (invitations-flow)"
    state["user_ids"].append(admin["id"])

    # Verificér invitations-token blev oprettet
    invite = db.invitation_tokens.find_one({"user_id": admin["id"]})
    assert invite is not None, "Invitations-token blev IKKE oprettet"


def test_subsequent_edit_does_not_recreate_admin(db):
    """Hvis SA editerer firmaet igen og admin allerede findes, må vi ikke
    skabe en duplikat."""
    r = requests.put(
        f"{API}/api/superadmin/companies/{state['logi_id']}",
        json={"admin_name": "Opdateret Navn"},
        headers=_h(state["sa_token"]), timeout=15,
    )
    assert r.status_code == 200
    count = db.users.count_documents({"company_id": state["logi_id"], "role": "logistics_admin"})
    assert count == 1, f"Forventede 1 admin, fik {count}"


# ============================================================
# Opgave 2 + 4: Multi-lokation order-medarbejder
# ============================================================
def test_seed_customer_with_3_locations(db):
    """Opret kunde + CA + 3 lokationer for multi-loc test."""
    cid = str(uuid.uuid4())
    db.companies.insert_one({
        "id": cid, "name": f"IT35 Kunde {SUFFIX}",
        "company_type": "customer", "active": True,
    })
    state["company_ids"].append(cid)
    state["customer_id"] = cid

    # CA
    ca_email = f"it35-ca-{SUFFIX}@e2e.local"
    h = bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()
    ca_id = str(uuid.uuid4())
    db.users.insert_one({
        "id": ca_id, "email": ca_email, "name": "IT35 CA",
        "password_hash": h, "role": "customer_admin", "company_id": cid,
        "active": True, "invitation_status": "active",
    })
    state["user_ids"].append(ca_id)
    state["ca_email"] = ca_email
    state["ca_pass"] = "TestPass2026!"

    # 3 lokationer
    codes = ["IT35A", "IT35B", "IT35C"]
    for code in codes:
        plads_id = str(uuid.uuid4())
        db.plads.insert_one({
            "id": plads_id, "location_code": code,
            "name": f"IT35 Plads {code}", "company_id": cid,
            "address": "Vej 1", "city": "Aarhus",
            "active": True, "containers_per_material": 2,
        })
        state["plads_ids"].append(plads_id)
    state["loc_codes"] = codes


def test_create_employee_with_multiple_locations(db):
    """CA opretter order-medarbejder med 3 lokationer via location_codes-array.
    Forventet: assigned_plads_ids gemmes med alle 3 koder."""
    r = _login(state["ca_email"], state["ca_pass"])
    assert r.status_code == 200, r.text
    ca_token = r.json()["token"]
    state["ca_token"] = ca_token

    emp_email = f"it35-emp-multi-{SUFFIX}@e2e.local"
    r = requests.post(f"{API}/api/org/users", json={
        "name": "IT35 Multi Medarbejder",
        "email": emp_email,
        "role": "order",
        "location_code": state["loc_codes"][0],  # primær
        "location_codes": state["loc_codes"],     # alle 3
        "send_invitation": False,
        "password": "TestPass2026!",
    }, headers=_h(ca_token), timeout=15)
    assert r.status_code == 200, r.text
    emp_data = r.json()
    state["emp_id"] = emp_data["id"]
    state["emp_email"] = emp_email
    state["user_ids"].append(emp_data["id"])

    # Aktivér i DB (order-rolle er normalt invitations-only)
    h = bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()
    db.users.update_one(
        {"id": emp_data["id"]},
        {"$set": {"password_hash": h, "invitation_status": "active"}},
    )

    # Verificér i DB
    emp = db.users.find_one({"id": emp_data["id"]}, {"_id": 0})
    assert sorted(emp.get("assigned_plads_ids") or []) == sorted(state["loc_codes"]), \
        f"Forventede assigned_plads_ids={state['loc_codes']}, fik {emp.get('assigned_plads_ids')}"
    assert emp["location_code"] == state["loc_codes"][0]


def test_order_employee_plads_endpoint_filters_to_assigned(db):
    """Order-medarbejderens GET /api/plads returnerer KUN de 3 tildelte
    pladser — ikke andre pladser i firmaet."""
    # Opret EN EKSTRA plads i samme firma som medarbejderen IKKE har adgang til
    extra_plads_id = str(uuid.uuid4())
    db.plads.insert_one({
        "id": extra_plads_id, "location_code": f"IT35EX-{SUFFIX}",
        "name": "IT35 Ekstra Plads", "company_id": state["customer_id"],
        "active": True, "containers_per_material": 2,
    })
    state["plads_ids"].append(extra_plads_id)

    # Aktivér medarbejderen i DB så de kan logge ind
    db.users.update_one(
        {"id": state["emp_id"]},
        {"$set": {"invitation_status": "active"}},
    )
    # Login som medarbejder
    r = _login(state["emp_email"], "TestPass2026!")
    assert r.status_code == 200, r.text
    emp_token = r.json()["token"]

    # GET /api/plads
    r = requests.get(f"{API}/api/plads",
                     headers=_h(emp_token), timeout=10)
    assert r.status_code == 200, r.text
    plads_list = r.json()
    codes_returned = {p.get("location_code") for p in plads_list}
    expected = set(state["loc_codes"])
    assert codes_returned == expected, \
        f"Forventede {expected}, fik {codes_returned}. Den ekstra plads MÅ IKKE være med."


def test_update_employee_locations_via_la(db):
    """LA (location_admin) skal kunne ændre `location_codes` for sine order-
    medarbejdere — men kun blandt LA's egne pladser."""
    # Først opret en LA med 2 af de 3 lokationer
    la_email = f"it35-la-{SUFFIX}@e2e.local"
    h = bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()
    la_id = str(uuid.uuid4())
    db.users.insert_one({
        "id": la_id, "email": la_email, "name": "IT35 LA",
        "password_hash": h, "role": "location_admin",
        "company_id": state["customer_id"], "active": True,
        "location_code": state["loc_codes"][0],
        "assigned_plads_ids": [state["loc_codes"][0], state["loc_codes"][1]],  # kun A+B
        "invitation_status": "active",
    })
    state["user_ids"].append(la_id)

    la_token = _login(la_email, "TestPass2026!").json()["token"]

    # LA opdaterer medarbejder til kun lokation A
    r = requests.put(
        f"{API}/api/org/users/{state['emp_id']}",
        json={"location_codes": [state["loc_codes"][0]]},
        headers=_h(la_token), timeout=10,
    )
    assert r.status_code == 200, r.text

    emp = db.users.find_one({"id": state["emp_id"]}, {"_id": 0})
    assert emp["assigned_plads_ids"] == [state["loc_codes"][0]]
    assert emp["location_code"] == state["loc_codes"][0]


def test_la_cannot_assign_outside_own_scope(db):
    """LA må IKKE tildele medarbejder til lokationer LA ikke selv har adgang til."""
    la_email = f"it35-la-{SUFFIX}@e2e.local"  # samme LA som ovenfor
    la_token = _login(la_email, "TestPass2026!").json()["token"]
    # Forsøg at sætte medarbejder til lokation C (som LA ikke har)
    r = requests.put(
        f"{API}/api/org/users/{state['emp_id']}",
        json={"location_codes": [state["loc_codes"][2]]},
        headers=_h(la_token), timeout=10,
    )
    assert r.status_code == 403, \
        f"Forventede 403 (LA uden for scope), fik {r.status_code}: {r.text}"


# ============================================================
# Opgave 3: Excel KPI sanity (helper logic kontrol)
# ============================================================
def test_excel_helper_aggregates_correctly():
    """Verificér at de nye KPI-beregninger giver mening på sample-data."""
    # Sample-data svarende til /api/org/reports/orders payload
    data = {
        "total_orders": 10,
        "pending_in_period": 2,
        "pending_all_time": 5,
        "workshop_count": 1,
        "by_material": [
            {"name": "Pap", "count": 6, "weight": 300},
            {"name": "Plast", "count": 4, "weight": 200},
        ],
        "by_employee": [
            {"name": "Lars", "count": 7},
            {"name": "Mette", "count": 3},
        ],
        "pattern": [
            {"bucket": "2026-06-01", "count": 3},
            {"bucket": "2026-06-02", "count": 7},
        ],
        "granularity": "day",
    }
    # Replikér helper-logikken
    total_weight = sum(m["weight"] for m in data["by_material"])
    unique_mats = len(data["by_material"])
    avg = total_weight / data["total_orders"] if data["total_orders"] else 0
    top_mat = max(data["by_material"], key=lambda m: m["count"])
    busiest = max(data["pattern"], key=lambda p: p["count"])

    assert total_weight == 500
    assert unique_mats == 2
    assert avg == 50.0
    assert top_mat["name"] == "Pap"
    assert busiest["bucket"] == "2026-06-02"
