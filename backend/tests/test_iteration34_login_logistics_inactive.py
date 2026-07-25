"""Iteration 34 — Login-fix for inaktiveret logistik-partner + KPI-tæl-aktive

Brugerklage 2026-06-15 (runde 8):
   "Når en logistik partner inaktiveres i systemet, og man så prøver at logge
    ind som en location admin eller anden som historisk har refereret til denne
    logistik partner, så får man en fejl ved login 'blevet suspenseret'."

   "Det skal kun påvirke fremadrettet så man ikke kan bestille eller se denne
    logistik partner."

Fix: `_is_company_active` returnerer nu altid True for `company_type=logistics`
firmaer. Kun KUNDE-firmaer (customer_type=customer) blokeres ved suspension.

Tests:
   1. logistics_admin for AKTIV logistik-partner → login lykkes ✓
   2. logistics_admin for INAKTIV logistik-partner → login lykkes alligevel ✓
   3. customer_admin for AKTIV kunde → login lykkes ✓
   4. customer_admin for INAKTIV (suspenderet) kunde → login fejler 403 ✓
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

state = {"user_ids": [], "company_ids": []}


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


def _seed_company(db, company_type, active=True):
    cid = str(uuid.uuid4())
    db.companies.insert_one({
        "id": cid,
        "name": f"IT34 {company_type} {SUFFIX} {uuid.uuid4().hex[:4]}",
        "company_type": company_type,
        "active": active,
    })
    state["company_ids"].append(cid)
    return cid


def _seed_user(db, email, password, role, company_id):
    uid = str(uuid.uuid4())
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.users.insert_one({
        "id": uid,
        "email": email,
        "name": f"IT34 user {role}",
        "password_hash": h,
        "role": role,
        "company_id": company_id,
        "active": True,
        "managed_company_ids": [],
        "assigned_plads_ids": [],
        "location_code": "",
    })
    state["user_ids"].append(uid)
    return uid


def _login(email, pw):
    return requests.post(f"{API}/api/auth/login",
                         json={"email": email, "password": pw}, timeout=15)


# ============================================================
def test_logistics_admin_login_when_company_active(db):
    """Sanity: logistics_admin for AKTIV logistik-firma kan logge ind."""
    cid = _seed_company(db, "logistics", active=True)
    email = f"it34-logi-active-{SUFFIX}@e2e.local"
    pw = "TestPass2026!"
    _seed_user(db, email, pw, "logistics_admin", cid)

    r = _login(email, pw)
    assert r.status_code == 200, f"Forventede 200, fik {r.status_code}: {r.text}"
    assert "token" in r.json()


def test_logistics_admin_login_when_company_inactive(db):
    """KERNE-FIX: logistics_admin for INAKTIV logistik-firma SKAL stadig kunne
    logge ind. Inaktivering af logistik-partner er "kun for UI-listing", ikke
    en login-blokering."""
    cid = _seed_company(db, "logistics", active=False)
    email = f"it34-logi-inactive-{SUFFIX}@e2e.local"
    pw = "TestPass2026!"
    _seed_user(db, email, pw, "logistics_admin", cid)

    r = _login(email, pw)
    assert r.status_code == 200, \
        f"Forventede 200, fik {r.status_code}: {r.text}\n" \
        f"BUG: Login blev fejlagtigt blokeret pga. logistik-partner deaktivering."
    assert "token" in r.json()


def test_customer_admin_login_when_company_active(db):
    """Sanity: customer_admin for AKTIV kunde kan logge ind."""
    cid = _seed_company(db, "customer", active=True)
    email = f"it34-cust-active-{SUFFIX}@e2e.local"
    pw = "TestPass2026!"
    _seed_user(db, email, pw, "customer_admin", cid)

    r = _login(email, pw)
    assert r.status_code == 200, r.text


def test_customer_admin_login_blocked_when_company_inactive(db):
    """KRITISK: customer_admin for SUSPENDERET kunde SKAL blokeres.
    (Det er den ægte 'suspender'-funktion vi vil bevare.)"""
    cid = _seed_company(db, "customer", active=False)
    email = f"it34-cust-inactive-{SUFFIX}@e2e.local"
    pw = "TestPass2026!"
    _seed_user(db, email, pw, "customer_admin", cid)

    r = _login(email, pw)
    assert r.status_code == 403, \
        f"Forventede 403 (suspenderet kunde), fik {r.status_code}: {r.text}"
    assert "suspender" in r.json().get("detail", "").lower() or "suspens" in r.json().get("detail", "").lower()


def test_location_admin_login_works_regardless_of_unrelated_logistics_partner(db):
    """Brugerens KONKRETE klage: LA for kunde X (med historisk reference til en
    NU-INAKTIV logistik-partner) skal kunne logge ind uden problemer."""
    # Aktiv kunde
    customer_cid = _seed_company(db, "customer", active=True)
    # Inaktiv logistik-partner som "historisk" var tilknyttet
    logi_cid = _seed_company(db, "logistics", active=False)

    # LA hører til kunden — IKKE til logistik-firmaet
    email = f"it34-la-{SUFFIX}@e2e.local"
    pw = "TestPass2026!"
    _seed_user(db, email, pw, "location_admin", customer_cid)

    r = _login(email, pw)
    assert r.status_code == 200, \
        f"LA login fejlede UANSET KUNDEN ER AKTIV — fejl: {r.status_code}: {r.text}"
