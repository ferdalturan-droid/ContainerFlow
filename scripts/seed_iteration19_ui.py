"""Seed a tenant for Iteration 19 UI testing (Batch 2: workshops + groups + order edits).

Creates: 1 customer company + CA + 1 location + 1 order user.
Prints credentials JSON to stdout so the test runner can pick them up.
Cleanup: run with --wipe SUFFIX to clean up.
"""
import os, sys, uuid, json, time, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"


def _login(email, pw):
    for _ in range(5):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": pw}, timeout=15)
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(3)
            continue
        raise SystemExit(f"login {email} failed {r.status_code}: {r.text}")
    raise SystemExit("login retries exhausted")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _accept(db, user_id, new_pw):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False}, sort=[("created_at", -1)])
    if not tk:
        raise SystemExit(f"no invite for {user_id}")
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": new_pw}, timeout=15)
    assert r.status_code == 200, r.text


def wipe(suffix):
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    users = list(db.users.find({"email": {"$regex": suffix.lower()}}))
    user_ids = [u["id"] for u in users]
    comps = list(db.companies.find({"name": {"$regex": suffix}}))
    comp_ids = [x["id"] for x in comps]
    db.users.delete_many({"id": {"$in": user_ids}})
    db.companies.delete_many({"id": {"$in": comp_ids}})
    db.plads.delete_many({"company_id": {"$in": comp_ids}})
    db.invitation_tokens.delete_many({"user_id": {"$in": user_ids}})
    db.workshops.delete_many({"company_id": {"$in": comp_ids}})
    db.location_groups.delete_many({"company_id": {"$in": comp_ids}})
    db.container_orders.delete_many({"company_id": {"$in": comp_ids}})
    db.tours.delete_many({"company_id": {"$in": comp_ids}})
    db.customer_orders_history.delete_many({"company_id": {"$in": comp_ids}})
    print(json.dumps({"wiped": {"users": len(user_ids), "companies": len(comp_ids)}}))


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--wipe":
        wipe(sys.argv[2])
        return

    suffix = uuid.uuid4().hex[:6].upper()
    ca_email = f"it19ui-ca-{suffix.lower()}@e2e.local"
    order_email = f"it19ui-ord-{suffix.lower()}@e2e.local"
    pw = "TestPass2026!"

    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]

    sa = _login(SA_EMAIL, SA_PASS)
    r = requests.post(f"{API}/api/superadmin/companies",
                      headers=_h(sa),
                      json={"name": f"IT19UI-CUST-{suffix}", "customer_id": f"C19UI-{suffix}",
                            "company_type": "customer", "admin_email": ca_email,
                            "admin_name": f"IT19UI CA {suffix}"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    company_id = body["company"]["id"]
    ca_id = body["created_admin"]["id"]
    _accept(db, ca_id, pw)
    ca = _login(ca_email, pw)

    # Create a location
    r2 = requests.post(f"{API}/api/org/locations", headers=_h(ca),
                       json={"name": f"IT19UI-PLADS-{suffix}", "city": "Aarhus", "address": "Testvej 5"}, timeout=15)
    assert r2.status_code == 200, r2.text
    loc_code = r2.json()["code"]

    # Create order user
    r3 = requests.post(f"{API}/api/org/users", headers=_h(ca),
                       json={"email": order_email, "name": f"IT19UI Order {suffix}",
                             "role": "order", "location_code": loc_code}, timeout=15)
    assert r3.status_code == 200, r3.text
    ord_id = r3.json()["id"]
    _accept(db, ord_id, pw)

    print(json.dumps({
        "suffix": suffix,
        "company_id": company_id,
        "ca_email": ca_email,
        "order_email": order_email,
        "password": pw,
        "location_code": loc_code,
    }))


if __name__ == "__main__":
    main()
