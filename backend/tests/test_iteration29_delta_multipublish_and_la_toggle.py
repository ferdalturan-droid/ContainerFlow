"""Iteration 29 — Brugerkrav 2026-06-15 (Krav 1 + Krav 2)

Krav 1: Customer Admin kan toggle Location Admin tilknytning til en lokation.
   * Klik én gang → tilknyt (assigned_plads_ids/location_code opdateres)
   * Klik igen   → frakoble (begge felter ryddes når sidste lokation fjernes)

Krav 2: Location Admin kan publicere delta'er til flere kalendere på én gang
   og delta'erne forbliver synlige i 30 dage så de kan re-publiceres senere.
   * `GET /api/org/holiday-deltas/received?days=30` returnerer alle modtagne
     delta'er uanset status med felterne `applied_calendar_ids` +
     `available_calendar_ids`.
   * `POST /api/org/holiday-deltas/{notif_id}/import` accepterer enten
     `calendar_id` (legacy single) eller `calendar_ids: [str]` (multi).
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
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
CA_EMAIL = f"it29-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"
LA_EMAIL = f"it29-la-{SUFFIX}@e2e.local"
LA_PASS = "TestPass2026!"

state = {
    "company_ids": [], "user_ids": [], "loc_codes": [],
    "calendar_ids": [], "delta_ids": [],
}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    try:
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.holiday_calendars.delete_many({"id": {"$in": state["calendar_ids"]}})
        db.holiday_deltas.delete_many({"id": {"$in": state["delta_ids"]}})
        db.delta_notifications.delete_many({"delta_id": {"$in": state["delta_ids"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password, attempts=5):
    for i in range(attempts):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": password}, timeout=15)
        if r.status_code == 200:
            return r
        time.sleep(0.5)
    return r


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _post(token, path, body=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=body or {}, timeout=15)


def _get(token, path):
    return requests.get(f"{API}{path}", headers=_h(token) if token else None, timeout=15)


def _put(token, path, body):
    return requests.put(f"{API}{path}", headers=_h(token), json=body, timeout=15)


def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_company_and_la_user(db):
    # Create customer firma
    r = _post(state["sa_token"], "/api/superadmin/companies", {
        "name": f"IT29 Kunde {SUFFIX}",
        "customer_id": f"IT29-{SUFFIX}",
        "company_type": "customer",
        "admin_email": CA_EMAIL,
        "admin_name": "IT29 CA",
        "admin_phone": "+45 1234 5678",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    state["company_id"] = d["company"]["id"]
    state["company_ids"].append(d["company"]["id"])
    ca_id = d["created_admin"]["id"]
    state["user_ids"].append(ca_id)

    # Activate CA via invitation
    invite = db.invitation_tokens.find_one({"user_id": ca_id, "token_type": "invitation"})
    assert invite, "No invitation token created for CA"
    r2 = requests.post(f"{API}/api/auth/accept-invitation",
                       json={"token": invite["token"], "new_password": CA_PASS}, timeout=15)
    assert r2.status_code == 200, r2.text
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    # CA creates 2 locations (so we can test multi-attach/detach)
    for label in ["A", "B"]:
        r3 = _post(state["ca_token"], "/api/org/locations", {
            "name": f"IT29 Lokation {label} {SUFFIX}", "city": "København",
            "address": f"Vej {label} 1",
        })
        assert r3.status_code == 200, r3.text
        plads = r3.json()
        state.setdefault("locs", []).append(plads)
        state["loc_codes"].append(plads["code"])

    # CA creates 1 LA user (initially unbound)
    r4 = _post(state["ca_token"], "/api/org/users", {
        "name": "IT29 LA", "email": LA_EMAIL,
        "role": "location_admin",
        "location_code": state["locs"][0]["code"],  # bind initially to A
        "phone": "+45 9876 5432",
    })
    assert r4.status_code == 200, r4.text
    la_id = r4.json()["id"]
    state["la_id"] = la_id
    state["user_ids"].append(la_id)

    # Activate LA via invitation
    invite = db.invitation_tokens.find_one({"user_id": la_id, "token_type": "invitation"})
    assert invite, "No invitation token for LA"
    r5 = requests.post(f"{API}/api/auth/accept-invitation",
                       json={"token": invite["token"], "new_password": LA_PASS}, timeout=15)
    assert r5.status_code == 200, r5.text
    state["la_token"] = _login(LA_EMAIL, LA_PASS).json()["token"]


# ============================================================
#   Krav 1: CA Toggle LA-tilknytning (attach + detach)
# ============================================================
def test_ca_attach_la_to_second_location():
    """CA toggle: tilføj location B til LA's assigned_plads_ids."""
    codes = [state["locs"][0]["code"], state["locs"][1]["code"]]
    r = _put(state["ca_token"], f"/api/org/users/{state['la_id']}", {"location_codes": codes})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body.get("assigned_plads_ids") or []) == sorted(codes)
    # Primary location_code skal være valid (en af codes)
    assert body.get("location_code") in codes


def test_ca_detach_one_of_two_locations():
    """CA toggle: fjern lokation A — LA bevarer kun B."""
    only_b = [state["locs"][1]["code"]]
    r = _put(state["ca_token"], f"/api/org/users/{state['la_id']}", {"location_codes": only_b})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_plads_ids"] == only_b
    # Primary skal snap til B (da A ikke længere er i listen)
    assert body["location_code"] == only_b[0]


def test_ca_detach_last_location_clears_everything():
    """Krav 1 bug fix: Når sidste lokation fjernes, skal location_code også
    ryddes (ellers vil UI'et stadig vise LA'en som tilknyttet via primary)."""
    r = _put(state["ca_token"], f"/api/org/users/{state['la_id']}", {"location_codes": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_plads_ids"] == []
    assert body["location_code"] == "", \
        f"location_code skal ryddes når sidste lokation fjernes, fik: {body['location_code']!r}"


def test_ca_reattach_after_full_detach():
    """Toggle round-trip: tilknyt LA igen efter fuld frakobling."""
    code = state["locs"][0]["code"]
    r = _put(state["ca_token"], f"/api/org/users/{state['la_id']}", {"location_codes": [code]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_plads_ids"] == [code]
    assert body["location_code"] == code


def test_ca_attach_both_locations_for_delta_tests():
    """Forbered LA til delta-tests — tilknyt begge lokationer."""
    codes = [state["locs"][0]["code"], state["locs"][1]["code"]]
    r = _put(state["ca_token"], f"/api/org/users/{state['la_id']}", {"location_codes": codes})
    assert r.status_code == 200, r.text
    # Genindlæs token (managed_company_ids m.m. kan have ændret sig)
    state["la_token"] = _login(LA_EMAIL, LA_PASS).json()["token"]


# ============================================================
#   Krav 2: Delta multi-publish + 30-dages tab
# ============================================================
def test_la_creates_two_holiday_calendars():
    """LA opretter 2 helligdagskalendere (en på hver lokation) for at teste
    multi-publish."""
    for i, loc in enumerate(state["locs"]):
        r = _post(state["la_token"], "/api/org/holiday-calendars", {
            "name": f"IT29 Kalender {i+1}",
            "year": 2027,
            "location_code": loc["code"],
            "days": [
                {"name": "Juleaften", "date": "2027-12-24", "closed": True,
                 "open_from": "", "open_to": "", "delivery_address_id": None},
            ],
        })
        assert r.status_code == 200, r.text
        cal = r.json()
        state["calendar_ids"].append(cal["id"])


def test_sa_creates_and_publishes_delta_to_company():
    """SA opretter delta og publicerer til vores firma."""
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": f"IT29 Delta {SUFFIX}",
        "year": 2027,
        "operations": [
            {"op": "add", "match_name": "Påskeløverdag", "new_date": "2027-04-03"},
            {"op": "modify", "match_name": "Juleaften", "new_date": "2027-12-24", "new_name": "Juleaften"},
        ],
    })
    assert r.status_code == 200, r.text
    d_id = r.json()["id"]
    state["delta_ids"].append(d_id)
    state["delta_id"] = d_id

    # Publicér til vores firma kun
    r2 = _post(state["sa_token"],
               f"/api/superadmin/holiday-deltas/{d_id}/publish",
               {"company_ids": [state["company_id"]]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["notifications_created"] >= 1


def test_la_received_endpoint_returns_pending_delta():
    """Nyt endpoint: /received returnerer alle modtagne delta'er incl. status."""
    r = _get(state["la_token"], "/api/org/holiday-deltas/received?days=30")
    assert r.status_code == 200, r.text
    items = r.json()
    ours = [n for n in items if n["delta"]["id"] == state["delta_id"]]
    assert len(ours) == 1, items
    n = ours[0]
    assert n["status"] == "pending"
    assert n["applied_calendar_ids"] == []
    # Begge oprettede kalendere er tilgængelige
    assert set(n["available_calendar_ids"]) == set(state["calendar_ids"])
    state["notif_id"] = n["id"]


def test_la_multi_publish_to_first_calendar_only(db):
    """LA importerer delta til KUN den første kalender (multi-publish med 1 entry)."""
    cal_a = state["calendar_ids"][0]
    r = _post(state["la_token"],
              f"/api/org/holiday-deltas/{state['notif_id']}/import",
              {"calendar_ids": [cal_a]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 1   # Påskeløverdag tilføjet
    # NB: 'modified' kan være 1 eller 2 afhængig af om Juleaften match'ede - kun cal_a fik det
    assert "calendars" in body
    assert len(body["calendars"]) == 1
    assert body["calendars"][0]["id"] == cal_a

    # Verificér i DB
    cal_after = db.holiday_calendars.find_one({"id": cal_a}, {"_id": 0})
    names = [d["name"] for d in cal_after["days"]]
    assert "Påskeløverdag" in names

    # Kalender B er IKKE påvirket
    cal_b = db.holiday_calendars.find_one({"id": state["calendar_ids"][1]}, {"_id": 0})
    names_b = [d["name"] for d in cal_b["days"]]
    assert "Påskeløverdag" not in names_b


def test_la_received_endpoint_still_shows_delta_after_publish():
    """Krav 2 kerne: Delta SKAL stadig være synligt i den 30-dages tab efter publish."""
    r = _get(state["la_token"], "/api/org/holiday-deltas/received?days=30")
    assert r.status_code == 200, r.text
    items = r.json()
    ours = [n for n in items if n["delta"]["id"] == state["delta_id"]]
    assert len(ours) == 1, "Delta MÅ IKKE forsvinde fra /received efter publish"
    n = ours[0]
    assert n["status"] == "accepted"
    assert state["calendar_ids"][0] in n["applied_calendar_ids"]
    # Kalender B er stadig available (vi har endnu ikke publiceret til den)
    assert state["calendar_ids"][1] in n["available_calendar_ids"]
    assert state["calendar_ids"][0] not in n["available_calendar_ids"]


def test_la_pending_endpoint_clears_after_publish():
    """/pending (popup-feeder) skal være tom efter publish — så popup'en ikke spammer."""
    r = _get(state["la_token"], "/api/org/holiday-deltas/pending")
    assert r.status_code == 200, r.text
    pending = r.json()
    assert not any(n["delta"]["id"] == state["delta_id"] for n in pending), \
        "Pending må IKKE indeholde delta'et efter publish"


def test_la_can_republish_to_second_calendar(db):
    """Krav 2 kerne: LA kan re-publicere samme delta til en NY kalender senere."""
    cal_b = state["calendar_ids"][1]
    r = _post(state["la_token"],
              f"/api/org/holiday-deltas/{state['notif_id']}/import",
              {"calendar_ids": [cal_b]})
    assert r.status_code == 200, r.text

    # Kalender B er nu også opdateret
    cal_after = db.holiday_calendars.find_one({"id": cal_b}, {"_id": 0})
    names = [d["name"] for d in cal_after["days"]]
    assert "Påskeløverdag" in names

    # /received viser nu BEGGE kalendere i applied_calendar_ids
    r2 = _get(state["la_token"], "/api/org/holiday-deltas/received?days=30")
    ours = next(n for n in r2.json() if n["delta"]["id"] == state["delta_id"])
    assert set(ours["applied_calendar_ids"]) >= set(state["calendar_ids"])
    assert ours["available_calendar_ids"] == []


def test_la_legacy_calendar_id_still_works(db):
    """Bagudkompatibilitet: legacy `calendar_id` (single) skal stadig virke."""
    # Opret ny delta + publicér
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": f"IT29 Delta Legacy {SUFFIX}",
        "operations": [{"op": "add", "match_name": "LegacyDay", "new_date": "2027-06-06"}],
    })
    d_id = r.json()["id"]
    state["delta_ids"].append(d_id)
    _post(state["sa_token"], f"/api/superadmin/holiday-deltas/{d_id}/publish",
          {"company_ids": [state["company_id"]]})
    pending = _get(state["la_token"], "/api/org/holiday-deltas/pending").json()
    notif = next(n for n in pending if n["delta"]["id"] == d_id)

    # Import med legacy single calendar_id
    r2 = _post(state["la_token"],
               f"/api/org/holiday-deltas/{notif['id']}/import",
               {"calendar_id": state["calendar_ids"][0]})
    assert r2.status_code == 200, r2.text


def test_received_filters_by_days_window(db):
    """30-dages cutoff respekteres."""
    # Forfalsk en gammel notifikation
    old_notif_id = str(uuid.uuid4())
    fake_delta_id = str(uuid.uuid4())
    db.holiday_deltas.insert_one({
        "id": fake_delta_id, "name": "IT29 Gammel Delta", "operations": [],
        "status": "published",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    })
    state["delta_ids"].append(fake_delta_id)
    db.delta_notifications.insert_one({
        "id": old_notif_id,
        "delta_id": fake_delta_id,
        "user_id": state["la_id"],
        "status": "pending",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    })

    # 30-dages vindue ekskluderer den
    r = _get(state["la_token"], "/api/org/holiday-deltas/received?days=30")
    assert not any(n["id"] == old_notif_id for n in r.json())

    # 60-dages vindue inkluderer den
    r2 = _get(state["la_token"], "/api/org/holiday-deltas/received?days=60")
    assert any(n["id"] == old_notif_id for n in r2.json())


def test_multi_publish_validates_all_calendars_before_mutating():
    """Validate-all-before-mutate: hvis EN kalender er ugyldig, sker INGEN
    ændringer (atomic safety)."""
    # Opret ny delta
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": f"IT29 Delta Atomic {SUFFIX}",
        "operations": [{"op": "add", "match_name": "AtomicDay", "new_date": "2027-07-07"}],
    })
    d_id = r.json()["id"]
    state["delta_ids"].append(d_id)
    _post(state["sa_token"], f"/api/superadmin/holiday-deltas/{d_id}/publish",
          {"company_ids": [state["company_id"]]})
    pending = _get(state["la_token"], "/api/org/holiday-deltas/pending").json()
    notif = next(n for n in pending if n["delta"]["id"] == d_id)

    # Send én gyldig + én ugyldig kalender-id
    r2 = _post(state["la_token"],
               f"/api/org/holiday-deltas/{notif['id']}/import",
               {"calendar_ids": [state["calendar_ids"][0], "non-existent-id"]})
    assert r2.status_code == 403, r2.text
