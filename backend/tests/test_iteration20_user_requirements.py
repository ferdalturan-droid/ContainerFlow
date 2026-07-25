"""Iteration 20 — backend regression for user requirements (2026-06-14):

  * Slet-knapper for helligdags-delta virker (selv på publicerede).
  * Publish accepterer company_ids og scopes til de valgte kunder.
  * ContainerOverride kan gemmes UDEN custom_address (Leveringsadresse fjernet
    fra container-definitionen).
  * StructuredOrderCreate accepterer/persisterer capacity-snapshot fra
    container_overrides.

Cleans up own seed data on module teardown.
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
CA1_EMAIL = f"it20-ca1-{SUFFIX}@e2e.local"
CA2_EMAIL = f"it20-ca2-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"
LA1_EMAIL = f"it20-la1-{SUFFIX}@e2e.local"
LA2_EMAIL = f"it20-la2-{SUFFIX}@e2e.local"
LA_PASS = "TestPass2026!"

state = {
    "company_ids": [], "user_ids": [], "loc_codes": [], "delta_ids": [],
    "cm_ids": [],
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
        db.holiday_deltas.delete_many({"id": {"$in": state["delta_ids"]}})
        db.delta_notifications.delete_many({"delta_id": {"$in": state["delta_ids"]}})
        db.container_overrides.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.capacity_measures.delete_many({"id": {"$in": state["cm_ids"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _login(email, password, attempts=8):
    for i in range(attempts):
        r = requests.post(f"{API}/api/auth/login",
                          json={"email": email, "password": password}, timeout=15)
        if r.status_code == 200:
            return r
        if r.status_code == 429:
            time.sleep(3 + i * 2); continue
        return r
    return r


def _h(tok): return {"Authorization": f"Bearer {tok}"} if tok else {}
def _post(t, p, d=None): return requests.post(f"{API}{p}", headers=_h(t), json=d or {}, timeout=20)
def _put(t, p, d=None): return requests.put(f"{API}{p}", headers=_h(t), json=d or {}, timeout=15)
def _get(t, p): return requests.get(f"{API}{p}", headers=_h(t), timeout=15)
def _del(t, p): return requests.delete(f"{API}{p}", headers=_h(t), timeout=15)


def _accept_invite(db, user_id, password):
    tk = db.invitation_tokens.find_one({"user_id": user_id, "used": False},
                                       sort=[("created_at", -1)])
    assert tk is not None
    r = requests.post(f"{API}/api/auth/accept-invitation",
                      json={"token": tk["token"], "new_password": password}, timeout=15)
    assert r.status_code == 200, r.text


# ========================================================
#   Bootstrap two customer tenants + LAs
# ========================================================
def test_sa_login():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    state["sa_token"] = r.json()["token"]


def test_seed_two_tenants(db):
    for slot, ca_email, la_email in [(1, CA1_EMAIL, LA1_EMAIL), (2, CA2_EMAIL, LA2_EMAIL)]:
        sfx = f"{SUFFIX}-{slot}"
        r = _post(state["sa_token"], "/api/superadmin/companies", {
            "name": f"IT20-CUST-{sfx}", "customer_id": f"C20-{sfx}",
            "company_type": "customer", "admin_email": ca_email,
            "admin_name": f"CA-{slot}",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        cid = body["company"]["id"]
        state["company_ids"].append(cid)
        ca_id = body["created_admin"]["id"]
        state["user_ids"].append(ca_id)
        _accept_invite(db, ca_id, CA_PASS)
        ca_tok = _login(ca_email, CA_PASS).json()["token"]
        state[f"ca{slot}_id"] = cid
        state[f"ca{slot}_token"] = ca_tok

        # Plads
        r2 = _post(ca_tok, "/api/org/locations", {
            "name": f"IT20-PLADS-{sfx}", "city": "By", "address": "Vej 1",
        })
        code = r2.json()["code"]
        state["loc_codes"].append(code)
        state[f"code{slot}"] = code

        # LA
        r3 = _post(ca_tok, "/api/org/users", {
            "email": la_email, "name": f"LA-{slot}",
            "role": "location_admin", "location_codes": [code],
        })
        la_id = r3.json()["id"]
        state["user_ids"].append(la_id)
        _accept_invite(db, la_id, LA_PASS)
        state[f"la{slot}_token"] = _login(la_email, LA_PASS).json()["token"]


# ========================================================
#   1) Helligdags-delta SLET virker — også på publiceret
# ========================================================
def test_create_delta_and_publish_to_ca1_only(db):
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": f"Delta {SUFFIX}",
        "operations": [{"op": "add", "match_name": "Test Helligdag", "new_date": "2027-04-15"}],
    })
    assert r.status_code == 200, r.text
    delta = r.json()
    state["delta_ids"].append(delta["id"])
    state["delta_id"] = delta["id"]

    # Publish to CA1 only — CA2 should NOT receive
    r2 = _post(state["sa_token"], f"/api/superadmin/holiday-deltas/{delta['id']}/publish",
               {"company_ids": [state["ca1_id"]]})
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert out["scope_company_ids"] == [state["ca1_id"]]
    assert out["total_recipients"] == 1  # only LA1
    assert out["notifications_created"] == 1


def test_la2_does_NOT_see_notification():
    r = _get(state["la2_token"], "/api/org/holiday-deltas/pending")
    assert r.status_code == 200
    pending = r.json()
    assert not any(n["delta_id"] == state["delta_id"] for n in pending), \
        f"LA2 saw a delta scoped only to CA1: {pending}"


def test_la1_DOES_see_notification():
    r = _get(state["la1_token"], "/api/org/holiday-deltas/pending")
    assert r.status_code == 200
    assert any(n["delta_id"] == state["delta_id"] for n in r.json())


def test_delete_published_delta_now_works(db):
    """Tidligere returnerede dette 409. Pr. 2026-06-14 brugerkrav skal alle
    slet-knapper virke. Notifikationer ryddes automatisk."""
    r = _del(state["sa_token"], f"/api/superadmin/holiday-deltas/{state['delta_id']}")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert r.json()["deleted_notifications"] >= 1

    # Delta + notifications must be gone
    assert db.holiday_deltas.find_one({"id": state["delta_id"]}) is None
    assert db.delta_notifications.count_documents({"delta_id": state["delta_id"]}) == 0


def test_la1_pending_list_no_longer_has_deleted_delta():
    r = _get(state["la1_token"], "/api/org/holiday-deltas/pending")
    assert r.status_code == 200
    assert not any(n["delta_id"] == state["delta_id"] for n in r.json())


# ========================================================
#   2) Publish til ALLE (tomt list) skal stadig virke
# ========================================================
def test_publish_to_all_when_company_ids_empty():
    r = _post(state["sa_token"], "/api/superadmin/holiday-deltas", {
        "name": f"Delta-all {SUFFIX}",
        "operations": [{"op": "add", "match_name": "Alle", "new_date": "2027-06-01"}],
    })
    delta = r.json()
    state["delta_ids"].append(delta["id"])

    r2 = _post(state["sa_token"], f"/api/superadmin/holiday-deltas/{delta['id']}/publish", {})
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert out["scope_company_ids"] == []
    # Both LA1 and LA2 should be notified
    assert out["total_recipients"] >= 2


# ========================================================
#   3) ContainerOverride uden adresse — kun container-nummer kræves
# ========================================================
def test_create_container_override_without_address():
    code = state["code1"]
    # Materiale "Pap til HCS" findes som default på alle nye pladser
    r = _put(state["la1_token"],
             f"/api/locations/{code}/containers/override",
             {"material": "Pap til HCS",
              "container_label": "Container 1",
              "custom_container_id": "ID-12345",
              # adresse mangler bevidst — det skal være tilladt nu
              "custom_address": "",
              "open_from": "08:00", "open_to": "17:00"})
    assert r.status_code == 200, r.text


def test_create_container_override_blocks_when_id_missing():
    code = state["code1"]
    r = _put(state["la1_token"],
             f"/api/locations/{code}/containers/override",
             {"material": "Pap til HCS",
              "container_label": "Container 2",
              "custom_container_id": ""})
    assert r.status_code == 400
    assert "Container-nummer" in r.json()["detail"]


# ========================================================
#   4) Kapacitetsmål snapshot fra container_overrides
# ========================================================
def test_capacity_measure_snapshotted_on_order(db):
    code = state["code1"]
    # Først tilføj en container-slot til materialet (default containers_per = 0
    # på en nyoprettet plads — LA skal selv tilføje pladserne).
    rx = _post(state["la1_token"], f"/api/locations/{code}/containers/add",
               {"material": "Pap til HCS"})
    assert rx.status_code == 200, rx.text
    # Opret kapacitetsmål
    r = _post(state["la1_token"], "/api/org/capacity-measures", {
        "location_code": code, "label": "20m³ open-top", "volume_m3": 20,
    })
    assert r.status_code == 200, r.text
    cm = r.json()
    state["cm_ids"].append(cm["id"])

    # Knyt det til container 1
    r2 = _put(state["la1_token"], f"/api/locations/{code}/containers/override", {
        "material": "Pap til HCS", "container_label": "Container 1",
        "custom_container_id": "ID-12345",
        "capacity_measure_id": cm["id"],
    })
    assert r2.status_code == 200

    # Resolv container-data — capacity_label/volume skal være med
    r3 = _get(state["la1_token"],
              f"/api/locations/{code}/containers?material=Pap%20til%20HCS")
    assert r3.status_code == 200
    payload = r3.json()
    c1 = next((c for c in payload.get("containers", []) if c["label"] == "Container 1"), None)
    assert c1 is not None, f"Container 1 not found in {payload}"
    assert c1["capacity_label"] == "20m³ open-top"
    assert c1["capacity_volume_m3"] == 20

    # Submit bestilling — backend skal kopiere capacity-snapshot ind på ordren
    r4 = _post(state["la1_token"], "/api/customer-orders/submit", {
        "location_code": code, "material": "Pap til HCS",
        "container_number": "Container 1", "priority": "normal",
        "tour_type": "normal", "custom_address": "Testvej 1, 4000 Roskilde",
    })
    assert r4.status_code == 200, r4.text
    order_id = r4.json()["order_id"]
    # Verify persisted snapshot
    d = db.container_orders.find_one({"id": order_id}, {"_id": 0})
    assert d["capacity_label"] == "20m³ open-top"
    assert d["capacity_volume_m3"] == 20
    # Verify submit response surfaces it (for success popup)
    assert r4.json()["capacity_label"] == "20m³ open-top"
    assert r4.json()["capacity_volume_m3"] == 20
