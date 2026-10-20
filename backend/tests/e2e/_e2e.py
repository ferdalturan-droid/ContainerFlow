"""Fælles hjælpere til end-to-end-tests (2026-10-18).

Testene kører mod den LOKALE app (docker-containeren cf-app) og den lokale
MongoDB, med testdata fra ./scripts/local-test.sh. De opretter egne ture,
kunder og prisaftaler med navne der starter med "E2E" og rydder op efter sig.

Kør (fra repoets rod) - altid i testens egen database og app (port 8081):
    ./scripts/e2e.sh                 # alle flows
    ./scripts/e2e.sh b2b pricing     # udvalgte

Testene nægter at køre mod andet end den lokale database.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient

BASE = os.environ.get("E2E_BASE", "http://localhost:8080/api")
PW = os.environ.get("PW") or os.environ.get("LOCAL_TEST_PASSWORD") or ""
MONGO_URL = os.environ.get("MONGO_URL", "")
if not any(h in MONGO_URL for h in ("cf-mongo", "localhost", "127.0.0.1")):
    sys.exit("Afbrudt: end-to-end-tests må kun køre mod den lokale database (cf-mongo).")
if not PW:
    sys.exit("Sæt PW (LOCAL_TEST_PASSWORD fra .env.local).")
# 2026-10-19: Testene slår firmaets prisregler midlertidigt fra og opretter
# E2E-data. De må derfor aldrig køre mod den database man selv bruger i
# browseren - kun mod testdatabasen fra ./scripts/e2e.sh.
DB_NAME = os.environ.get("DB_NAME", "containerflow")
if not DB_NAME.endswith("_e2e"):
    sys.exit("Afbrudt: kør testene med ./scripts/e2e.sh (egen database og app) - ikke mod din lokale database.")
db = MongoClient(MONGO_URL)[DB_NAME]
DK = ZoneInfo("Europe/Copenhagen")

# Testbrugere (fra local-logins.txt)
ILK_ADMIN = "ferdalturan+ilk.admin@gmail.com"
ILK_DRIVER = "ferdalturan+ilk.chauffoer1@gmail.com"          # Lars Jensen
HANSEN_ADMIN = "ferdalturan+hansen.admin@gmail.com"           # premium
HANSEN_DRIVER = "ferdalturan+hansen.chauffoer1@gmail.com"     # Nikolaj Holm
CITY_DRIVER = "ferdalturan+city.chauffoer1@gmail.com"         # andet firma
HF_ORDER_USER = "ferdalturan+hf.1101.medarbejder1@gmail.com"  # B2B-kunde (Helsingør Forsyning)

RESULTS = {"pass": 0, "fail": 0, "failed": []}
_tokens: dict = {}
_session = requests.Session()


def today() -> str:
    return datetime.now(DK).strftime("%Y-%m-%d")


def in_days(n: int) -> str:
    return (datetime.now(DK).date() + timedelta(days=n)).isoformat()


def next_weekday(after_days: int = 2) -> str:
    """En hverdag mindst `after_days` frem (så pris-tests ikke afhænger af ugedagen)."""
    d = datetime.now(DK).date() + timedelta(days=after_days)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def ok(cond, msg: str):
    if cond:
        RESULTS["pass"] += 1
        print(f"  PASS {msg}")
    else:
        RESULTS["fail"] += 1
        RESULTS["failed"].append(msg)
        print(f"  FAIL {msg}")
    return bool(cond)


def login(email: str) -> str:
    if email in _tokens:
        return _tokens[email]
    r = _session.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    _tokens[email] = r.json()["token"]
    return _tokens[email]


def user_id(email: str) -> str:
    return (db.users.find_one({"email": email}, {"_id": 0, "id": 1}) or {}).get("id", "")


def user_name(email: str) -> str:
    return (db.users.find_one({"email": email}, {"_id": 0, "name": 1}) or {}).get("name", "")


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"{status}: {body}")
        self.status, self.body = status, body


def call(method: str, path: str, body=None, t: str = None, params=None):
    """Kald API'et. Fejl (>=400) kaster ApiError med status + svar."""
    h = {"Authorization": f"Bearer {t}"} if t else {}
    r = _session.request(method, f"{BASE}{path}", json=body, headers=h, params=params, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = r.text
    if r.status_code >= 400:
        raise ApiError(r.status_code, data)
    return data


def status_of(method: str, path: str, body=None, t: str = None, params=None) -> int:
    """HTTP-status for et kald (bruges til at teste at noget bliver afvist)."""
    try:
        call(method, path, body, t, params)
        return 200
    except ApiError as e:
        return e.status


def detail(e: ApiError) -> str:
    b = e.body
    if isinstance(b, dict):
        d = b.get("detail")
        return d.get("message") if isinstance(d, dict) else str(d)
    return str(b)


class Cleanup:
    """Husker hvad en flow har oprettet og fjerner det bagefter."""

    def __init__(self):
        self.tours, self.orders, self.customers, self.bundles, self.rules = [], [], [], [], []
        self.restore = []  # (collection, filter, $set)

    def run(self):
        ids = self.tours
        if ids:
            for c in ("tour_messages", "tour_audit_log", "tour_photos", "tour_change_requests", "receipts"):
                db[c].delete_many({"tour_id": {"$in": ids}})
            db.container_orders.delete_many({"$or": [{"tour_id": {"$in": ids}}, {"id": {"$in": self.orders}}]})
            db.tours.delete_many({"id": {"$in": ids}})
        if self.bundles:
            db.price_rules.delete_many({"bundle_id": {"$in": self.bundles}})
        if self.rules:
            db.price_rules.delete_many({"id": {"$in": self.rules}})
        if self.customers:
            db.logistics_customers.delete_many({"name": {"$in": self.customers}})
        for coll, flt, st in self.restore:
            db[coll].update_one(flt, {"$set": st})


def disable_company_rules(c: "Cleanup", admin_email: str):
    """Slå firmaets egne prisregler fra under testen (genskabes af Cleanup),
    så resultater ikke afhænger af lokale data eller ugedagen."""
    cid = db.users.find_one({"email": admin_email}, {"_id": 0, "company_id": 1})["company_id"]
    ids = [r["id"] for r in db.price_rules.find({"company_id": cid, "active": {"$ne": False}}, {"_id": 0, "id": 1})]
    for rid in ids:
        c.restore.append(("price_rules", {"id": rid}, {"active": True}))
    db.price_rules.update_many({"id": {"$in": ids}}, {"$set": {"active": False}})
    return cid


def free_driver(emails: list) -> str:
    """Første chauffør uden ture i gang (testene må ikke afhænge af andres
    lokale testdata - fx ture man selv har startet i browseren)."""
    for e in emails:
        uid = user_id(e)
        if uid and not db.tours.count_documents({"claimed_by_id": uid, "on_way": True, "completed": {"$ne": True}}):
            return e
    sys.exit(f"Ingen ledig chauffør blandt {emails} - afslut deres ture i gang først")


ILK_DRIVERS = [ILK_DRIVER, "ferdalturan+ilk.chauffoer2@gmail.com", "ferdalturan+ilk.chauffoer3@gmail.com"]


def new_id() -> str:
    return str(uuid.uuid4())


def report_row(t: str, tour_id: str, day: str = None):
    day = day or today()
    rep = call("GET", "/pricing/report", t=t, params={"date_from": in_days(-2) if day == today() else day,
                                                       "date_to": in_days(30)})
    return next((r for r in rep["rows"] if r["tour_id"] == tour_id), None)


def price_of(t: str, tour_id: str) -> dict:
    return call("GET", f"/pricing/tours/{tour_id}", t=t)


__all__ = [n for n in dir() if not n.startswith("__")]
_ = date  # (bruges af flows via import *)
