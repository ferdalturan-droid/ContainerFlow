"""Seed data for iteration 18 UI testing via API.
Creates: customer + plads + LA, plus a published delta, so UI test can log in
as LA and immediately see the delta pop-up.
Prints CA/LA emails + plads code to stdout.
"""
import os, uuid, requests, json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]; DB_NAME = os.environ["DB_NAME"]
SA_EMAIL = "doganmiketuran@gmail.com"; SA_PASS = "SuperAdmin2026!"
SUFFIX = "B1UI" + uuid.uuid4().hex[:4].upper()

def post(tok, p, d=None):
    return requests.post(f"{API}{p}",
        headers={"Authorization": f"Bearer {tok}"} if tok else {},
        json=d or {}, timeout=20)

def login(e, p):
    return requests.post(f"{API}/api/auth/login",
        json={"email": e, "password": p}, timeout=15).json()["token"]

sa_tok = login(SA_EMAIL, SA_PASS)
print(f"SA OK")

ca_email = f"ui-ca-{SUFFIX.lower()}@e2e.local"
la_email = f"ui-la-{SUFFIX.lower()}@e2e.local"
PWD = "TestPass2026!"

r = post(sa_tok, "/api/superadmin/companies", {
    "name": f"UI-CUST-{SUFFIX}", "customer_id": f"UC-{SUFFIX}",
    "company_type": "customer",
    "admin_email": ca_email, "admin_name": f"UI CA {SUFFIX}",
})
assert r.status_code == 200, r.text
body = r.json()
cid = body["company"]["id"]; ca_id = body["created_admin"]["id"]
print(f"COMPANY id={cid} customer_id=UC-{SUFFIX}")

db = MongoClient(MONGO_URL)[DB_NAME]
tk = db.invitation_tokens.find_one({"user_id": ca_id, "used": False},
                                   sort=[("created_at", -1)])
requests.post(f"{API}/api/auth/accept-invitation",
    json={"token": tk["token"], "new_password": PWD}, timeout=15)
ca_tok = login(ca_email, PWD)
print(f"CA OK email={ca_email}")

r2 = post(ca_tok, "/api/org/locations", {
    "name": f"UI-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1"})
code = r2.json()["code"]
print(f"PLADS code={code}")

r3 = post(ca_tok, "/api/org/users", {
    "email": la_email, "name": f"UI LA {SUFFIX}",
    "role": "location_admin", "location_codes": [code]})
la_id = r3.json()["id"]
tk2 = db.invitation_tokens.find_one({"user_id": la_id, "used": False},
                                    sort=[("created_at", -1)])
requests.post(f"{API}/api/auth/accept-invitation",
    json={"token": tk2["token"], "new_password": PWD}, timeout=15)
print(f"LA OK email={la_email}")

# Create + publish a delta so the pop-up has something to show
r4 = post(sa_tok, "/api/superadmin/holiday-deltas", {
    "name": f"UI Delta {SUFFIX}", "year": 2027,
    "operations": [
        {"op": "add", "match_name": "Test Helligdag", "new_date": "2027-04-15"},
        {"op": "modify", "match_name": "Foo", "new_name": "Bar",
         "new_date": "2027-05-01"},
        {"op": "delete", "match_name": "Foo"},
    ],
})
dlt = r4.json(); did = dlt["id"]
post(sa_tok, f"/api/superadmin/holiday-deltas/{did}/publish")
print(f"DELTA id={did} published")
print(json.dumps({
    "ca_email": ca_email, "la_email": la_email, "pwd": PWD,
    "code": code, "delta_id": did, "company_id": cid,
    "customer_id": f"UC-{SUFFIX}",
}))
