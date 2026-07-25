"""Iteration 25 — Customer Admin Reports (cross-location).

Tester /api/org/reports/orders-multi:
  * Returnerer aggregeret data på tværs af alle lokationer i kundens selskab
  * by_location-feltet bryder ned pr. lokation (count, pending, weight)
  * location_codes-filter virker (CSV)
  * Kun customer_admin må kalde endpointet (location_admin = 403)
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
CA_EMAIL = f"it25-ca-{SUFFIX}@e2e.local"
LA_EMAIL = f"it25-la-{SUFFIX}@e2e.local"
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
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password):
    for i in range(3):
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


def test_seed(db):
    r = _login(SA_EMAIL, SA_PASS); assert r.status_code == 200, r.text
    sa_token = r.json()["token"]; state["sa_token"] = sa_token

    r = _post(sa_token, "/api/superadmin/companies", {
        "name": f"IT25-CUST-{SUFFIX}", "customer_id": f"C25-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT25 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    # Opret 2 lokationer
    for i in range(2):
        r2 = _post(state["ca_token"], "/api/org/locations", {
            "name": f"IT25-PLADS-{i}-{SUFFIX}", "city": "By", "address": f"Vej {i}",
        })
        assert r2.status_code in (200, 201), r2.text
        code = r2.json()["code"]
        state["loc_codes"].append(code)
        _post(state["ca_token"], f"/api/locations/{code}/containers/add",
              {"material": f"Materiale-{i}"})

    # Opret 3 bestillinger på første lokation, 2 på den anden
    for i in range(3):
        r3 = _post(state["ca_token"], "/api/customer-orders/submit", {
            "location_code": state["loc_codes"][0],
            "material": "Materiale-0", "container_number": f"C-{i}",
            "priority": "normal", "tour_type": "normal",
            "custom_address": "Vej 0", "order_date": "2026-07-15",
        })
        assert r3.status_code == 200, r3.text
        state["order_ids"].append(r3.json()["order_id"])
    for i in range(2):
        r3 = _post(state["ca_token"], "/api/customer-orders/submit", {
            "location_code": state["loc_codes"][1],
            "material": "Materiale-1", "container_number": f"C-{i}",
            "priority": "normal", "tour_type": "normal",
            "custom_address": "Vej 1", "order_date": "2026-07-15",
        })
        assert r3.status_code == 200, r3.text
        state["order_ids"].append(r3.json()["order_id"])


def test_cross_location_report_aggregates_all():
    r = _get(state["ca_token"],
             "/api/org/reports/orders-multi?period=custom&start=2026-07-01&end=2026-07-31")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_orders"] == 5, d
    assert d["location_count"] == 2, d
    # by_location har præcis 2 lokationer
    by_loc = {l["location_code"]: l for l in d["by_location"]}
    assert state["loc_codes"][0] in by_loc and state["loc_codes"][1] in by_loc
    assert by_loc[state["loc_codes"][0]]["count"] == 3
    assert by_loc[state["loc_codes"][1]]["count"] == 2


def test_cross_location_report_with_filter():
    """Filtrér til kun den første lokation."""
    code = state["loc_codes"][0]
    r = _get(state["ca_token"],
             f"/api/org/reports/orders-multi?period=custom&start=2026-07-01&end=2026-07-31&location_codes={code}")
    assert r.status_code == 200
    d = r.json()
    assert d["total_orders"] == 3
    assert d["location_count"] == 1
    assert len(d["by_location"]) == 1
    assert d["by_location"][0]["location_code"] == code


def test_cross_location_report_location_admin_forbidden(db):
    """Endpointet er udelukkende for customer_admin."""
    # Opret en location_admin
    r = _post(state["ca_token"], "/api/org/users", {
        "email": LA_EMAIL, "role": "location_admin",
        "name": f"IT25 LA {SUFFIX}", "location_code": state["loc_codes"][0],
        "plads_codes": [state["loc_codes"][0]],
    })
    assert r.status_code in (200, 201), r.text
    la_id = r.json()["id"]
    state["user_ids"].append(la_id)
    _accept_invite(db, la_id, CA_PASS)
    la_token = _login(LA_EMAIL, CA_PASS).json()["token"]
    r2 = _get(la_token, "/api/org/reports/orders-multi?period=month")
    assert r2.status_code == 403, r2.text
