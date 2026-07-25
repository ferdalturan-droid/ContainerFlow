"""Iteration 21 — backend regression for user requirements (2026-06-14):

  * /api/container-orders/by-location/{code}?all=1 returnerer ordrer fra
    alle datoer (uden date-filter).
  * /api/container-orders/by-location/{code}?date=X virker stadig.
  * Ordre-doc indeholder fortsat `custom_container_id` til at vise container-nr
    i Mine/Alle bestillinger.
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
CA_EMAIL = f"it21-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"

state = {"company_ids": [], "user_ids": [], "loc_codes": [], "order_ids": []}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL); yield c[DB_NAME]; c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    try:
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.container_orders.delete_many({"id": {"$in": state["order_ids"]}})
        db.tours.delete_many({"order_id": {"$in": state["order_ids"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password, attempts=8):
    for i in range(attempts):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": password}, timeout=15)
        if r.status_code == 200: return r
        if r.status_code == 429:
            time.sleep(3 + i * 2); continue
        return r
    return r


def _h(t): return {"Authorization": f"Bearer {t}"} if t else {}
def _post(t, p, d=None): return requests.post(f"{API}{p}", headers=_h(t), json=d or {}, timeout=20)
def _get(t, p): return requests.get(f"{API}{p}", headers=_h(t), timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None
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
        "name": f"IT21-CUST-{SUFFIX}", "customer_id": f"C21-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT21 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    r2 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT21-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1",
    })
    code = r2.json()["code"]
    state["loc_codes"].append(code)
    state["code"] = code

    # Tilføj container-slot så vi kan oprette ordrer
    _post(state["ca_token"], f"/api/locations/{code}/containers/add",
          {"material": "Pap til HCS"})


# ========================================================
#   Lav 3 ordrer med 3 forskellige datoer
# ========================================================
def test_create_orders_on_different_dates(db):
    for i, (date, prio) in enumerate([("2026-06-10", "normal"),
                                       ("2026-06-14", "haster"),
                                       ("2026-07-01", "normal")]):
        r = _post(state["ca_token"], "/api/customer-orders/submit", {
            "location_code": state["code"],
            "material": "Pap til HCS",
            "container_number": "Container 1",
            "priority": prio,
            "tour_type": "normal",
            "custom_address": "Test 1, 4000 Roskilde",
            "custom_container_id": f"CN-{SUFFIX}-{i}",
            "order_date": date,
        })
        assert r.status_code == 200, r.text
        state["order_ids"].append(r.json()["order_id"])


# ========================================================
#   ?date= virker stadig
# ========================================================
def test_by_location_with_date_filter():
    r = _get(state["ca_token"],
             f"/api/container-orders/by-location/{state['code']}?date=2026-06-14")
    assert r.status_code == 200, r.text
    orders = r.json()
    # Filtreret til vores tre + andre evt orders på den dato
    our = [o for o in orders if o["id"] in state["order_ids"]]
    assert len(our) == 1
    assert our[0]["order_date"] == "2026-06-14"


# ========================================================
#   ?all=1 virker — returnerer alle 3 vores
# ========================================================
def test_by_location_all_flag_returns_all_dates():
    r = _get(state["ca_token"],
             f"/api/container-orders/by-location/{state['code']}?all=1")
    assert r.status_code == 200, r.text
    orders = r.json()
    our = [o for o in orders if o["id"] in state["order_ids"]]
    assert len(our) == 3, f"forventede 3 ordrer, fik {len(our)}"
    # ?all=1 har højere precedence end ?date= — selv hvis date sendes
    r2 = _get(state["ca_token"],
              f"/api/container-orders/by-location/{state['code']}?all=1&date=1999-01-01")
    our2 = [o for o in r2.json() if o["id"] in state["order_ids"]]
    assert len(our2) == 3


# ========================================================
#   Ordre-doc bevarer container-nummer (gemt som container_id_override /
#   eksponeret som container_id_resolved efter endpoint-berigelse)
# ========================================================
def test_orders_carry_custom_container_id():
    r = _get(state["ca_token"],
             f"/api/container-orders/by-location/{state['code']}?all=1")
    our = [o for o in r.json() if o["id"] in state["order_ids"]]
    assert len(our) == 3
    for o in our:
        cid = (o.get("container_id_override") or o.get("container_id_resolved") or o.get("custom_container_id") or "").strip()
        assert cid.startswith(f"CN-{SUFFIX}-"), \
            f"order missing container nr: {o}"
