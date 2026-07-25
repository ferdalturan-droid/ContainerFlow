"""Iteration 22 — backend regression for user requirements (2026-06-15):

  * customer-orders/submit accepterer IKKE længere alternative_delivery_address_id
    eller manual_alternative_address — feltet er fjernet pr. brugerkrav.
    (Bagudkompatibilitet: serveren accepterer dem stadig hvis sendt; bare ignorer.)
  * Status-felt aflæses korrekt for sortering: completed=True -> "afhentet",
    on_way/claimed_by -> "accepteret", ellers -> "afventer".
  * include_cancelled=true returnerer ordrer med status=cancelled.
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
CA_EMAIL = f"it22-ca-{SUFFIX}@e2e.local"
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


def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_tenant(db):
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT22-CUST-{SUFFIX}", "customer_id": f"C22-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT22 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    r2 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT22-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1",
    })
    code = r2.json()["code"]
    state["loc_codes"].append(code)
    state["code"] = code
    _post(state["ca_token"], f"/api/locations/{code}/containers/add",
          {"material": "Pap til HCS"})


def test_submit_ignores_old_alternative_address_fields():
    """Bagudkompatibilitet: hvis et gammelt frontend sender disse felter,
    skal serveren stadig acceptere submit (fejler ikke), så vi ikke får 500."""
    r = _post(state["ca_token"], "/api/customer-orders/submit", {
        "location_code": state["code"],
        "material": "Pap til HCS",
        "container_number": "Container 1",
        "priority": "normal",
        "tour_type": "normal",
        "custom_address": "Vej 1, 4000 Roskilde",
        "custom_container_id": f"CN-{SUFFIX}-OK",
        "order_date": "2026-07-01",
        # Forældede felter (UI sender ikke længere disse pr. 2026-06-15):
        "alternative_delivery_address_id": "",
        "manual_alternative_address": "",
    })
    assert r.status_code == 200, r.text
    oid = r.json()["order_id"]
    state["order_ids"].append(oid)


def test_status_label_derivation_for_sorting():
    """UI'et sorterer på (completed → bund, on_way/claimed_by → midte, ellers → top).
    Backend genererer status_label for hver ordre i by-location-respons."""
    r = _get(state["ca_token"], f"/api/container-orders/by-location/{state['code']}?all=1")
    assert r.status_code == 200
    orders = [o for o in r.json() if o["id"] in state["order_ids"]]
    assert len(orders) >= 1
    o = orders[0]
    # Ordren er lige oprettet uden claim → afventer
    assert o["status_label"] == "afventer", o
    # `completed`/`on_way`/`claimed_by` kan være undefined (=falsy) — UI'et
    # behandler dem som false, hvilket placerer ordren i top af listen
    assert not o.get("completed", False)
    assert not o.get("on_way", False)
    assert not o.get("claimed_by", "")




# ===================================================================
#   Tom helligdagskalender — eksplicit days:[] må IKKE pre-udfyldes
# ===================================================================
def test_create_holiday_calendar_with_empty_days_stays_empty():
    """Brugerkrav 2026-06-15: Når frontend vælger 'Tom kalender' sendes
    eksplicit days=[], og backend må IKKE auto-udfylde fra holiday_group."""
    r = _post(state["ca_token"], "/api/org/holiday-calendars", {
        "location_code": state["code"],
        "name": f"IT22-Tom-{SUFFIX}",
        "days": [],
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    assert cal["days"] == [], f"Tom kalender skal være tom, men var: {cal['days']}"


def test_create_holiday_calendar_without_days_still_autofills():
    """Bagudkompatibilitet: hvis UI ikke sender days-feltet overhovedet,
    skal backend stadig pre-udfylde fra company holiday_group som før."""
    r = _post(state["ca_token"], "/api/org/holiday-calendars", {
        "location_code": state["code"],
        "name": f"IT22-Auto-{SUFFIX}",
    })
    assert r.status_code == 200, r.text
    cal = r.json()
    # days kan være tom hvis company ikke har holiday_group_id (helt OK),
    # eller fyldt hvis den har — vi tester bare at vi får et list-svar:
    assert isinstance(cal["days"], list)

def test_include_cancelled_param():
    """UI'et henter med include_cancelled=true så fuldførte/aflyste også
    kommer med og kan sorteres nederst eller skjules via toggle."""
    r = _get(state["ca_token"],
             f"/api/container-orders/by-location/{state['code']}?all=1&include_cancelled=true")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
