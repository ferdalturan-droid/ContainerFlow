"""Create persistent seed for Iteration 29 UI testing (CA + LA + 2 locs + 2 calendars + 1 published delta)."""
import os, time, uuid, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
db = MongoClient(MONGO_URL)[DB_NAME]

SA_EMAIL, SA_PASS = "doganmiketuran@gmail.com", "SuperAdmin2026!"
SUFFIX = "UI29A"  # fixed, idempotent-ish
CA_EMAIL, CA_PASS = f"it29-ui-ca-{SUFFIX}@e2e.local", "TestPass2026!"
LA_EMAIL, LA_PASS = f"it29-ui-la-{SUFFIX}@e2e.local", "TestPass2026!"


def login(email, pw):
    return requests.post(f"{API}/api/auth/login", json={"email": email, "password": pw}, timeout=15)


def H(t): return {"Authorization": f"Bearer {t}"}


# 0. Cleanup any prior run
db.users.delete_many({"email": {"$in": [CA_EMAIL, LA_EMAIL]}})
db.companies.delete_many({"customer_id": f"IT29-UI-{SUFFIX}"})
db.plads.delete_many({"name": {"$regex": f"^IT29UI"}})

# 1. SA login
sa = login(SA_EMAIL, SA_PASS).json()["token"]
print("[SA] logged in")

# 2. Create customer company + CA user
r = requests.post(f"{API}/api/superadmin/companies", headers=H(sa), json={
    "name": f"IT29 UI Kunde", "customer_id": f"IT29-UI-{SUFFIX}", "company_type": "customer",
    "admin_email": CA_EMAIL, "admin_name": "IT29 UI CA", "admin_phone": "+45 1111 1111",
}, timeout=15)
assert r.status_code == 200, r.text
company_id = r.json()["company"]["id"]
ca_id = r.json()["created_admin"]["id"]
print(f"[CA] created company {company_id}, ca_id {ca_id}")

# Activate CA
inv = db.invitation_tokens.find_one({"user_id": ca_id, "token_type": "invitation"})
assert inv, "no CA invitation"
r2 = requests.post(f"{API}/api/auth/accept-invitation", json={"token": inv["token"], "new_password": CA_PASS}, timeout=15)
assert r2.status_code == 200, r2.text
ca = login(CA_EMAIL, CA_PASS).json()["token"]
print("[CA] activated + logged in")

# 3. CA creates 2 locations
locs = []
for label in ["A", "B"]:
    r = requests.post(f"{API}/api/org/locations", headers=H(ca), json={
        "name": f"IT29UI Lokation {label}", "city": "København", "address": f"Vej {label} 1",
    }, timeout=15)
    assert r.status_code == 200, r.text
    locs.append(r.json())
    print(f"[CA] loc {label} = {r.json()['code']}")

# 4. CA creates LA bound to Loc A
r = requests.post(f"{API}/api/org/users", headers=H(ca), json={
    "name": "IT29 UI LA", "email": LA_EMAIL, "role": "location_admin",
    "location_code": locs[0]["code"], "phone": "+45 2222 2222",
}, timeout=15)
assert r.status_code == 200, r.text
la_id = r.json()["id"]
inv = db.invitation_tokens.find_one({"user_id": la_id, "token_type": "invitation"})
r2 = requests.post(f"{API}/api/auth/accept-invitation", json={"token": inv["token"], "new_password": LA_PASS}, timeout=15)
assert r2.status_code == 200
la = login(LA_EMAIL, LA_PASS).json()["token"]
print(f"[LA] {la_id} activated, bound to {locs[0]['code']}")

# 5. Attach BOTH locations to LA so we can test toggle/detach in UI
r = requests.put(f"{API}/api/org/users/{la_id}", headers=H(ca),
                 json={"location_codes": [locs[0]["code"], locs[1]["code"]]}, timeout=15)
assert r.status_code == 200, r.text
print(f"[CA] LA now assigned: {r.json().get('assigned_plads_ids')}")

# 6. LA creates 2 holiday calendars (one per location)
la = login(LA_EMAIL, LA_PASS).json()["token"]
cal_ids = []
for i, loc in enumerate(locs):
    r = requests.post(f"{API}/api/org/holiday-calendars", headers=H(la), json={
        "name": f"IT29UI Kalender {i+1} ({loc['code']})", "year": 2027,
        "location_code": loc["code"],
        "days": [{"name": "Juleaften", "date": "2027-12-24", "closed": True,
                  "open_from": "", "open_to": "", "delivery_address_id": None}],
    }, timeout=15)
    assert r.status_code == 200, r.text
    cal_ids.append(r.json()["id"])
print(f"[LA] calendars: {cal_ids}")

# 7. SA creates + publishes a delta to our company
r = requests.post(f"{API}/api/superadmin/holiday-deltas", headers=H(sa), json={
    "name": f"IT29 UI Delta {SUFFIX}", "year": 2027,
    "operations": [{"op": "add", "match_name": "Påskelørdag", "new_date": "2027-04-03"}],
}, timeout=15)
assert r.status_code == 200, r.text
delta_id = r.json()["id"]
r2 = requests.post(f"{API}/api/superadmin/holiday-deltas/{delta_id}/publish",
                   headers=H(sa), json={"company_ids": [company_id]}, timeout=15)
assert r2.status_code == 200, r2.text
print(f"[SA] delta {delta_id} published to {company_id}")

# Print credentials for UI tests
print("\n=== SEED COMPLETE ===")
print(f"CA: {CA_EMAIL} / {CA_PASS}")
print(f"LA: {LA_EMAIL} / {LA_PASS}")
print(f"LA_ID: {la_id}")
print(f"LOC_A_CODE: {locs[0]['code']}")
print(f"LOC_B_CODE: {locs[1]['code']}")
print(f"CAL_IDS: {cal_ids}")
print(f"DELTA_ID: {delta_id}")
