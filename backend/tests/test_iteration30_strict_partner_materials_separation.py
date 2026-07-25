"""Iteration 30 — Strict per-partner materialer (Krav 5 fix runde 2)

Brugerklage 2026-06-15:
   "Når jeg skifter mellem distributionspartner, så fejler den stadigvæk.
    den holder dem ikke helt separeret, det er somom det mikser dem nogle gange.
    Det der sker for en (feks slette en materiale efter at vælge logistik
    partner 1) skal ikke ske for en anden logistik partner."

Denne suite verificerer at ADD / EDIT / DELETE af materialer ALDRIG lækker
fra én partner til en anden — uanset rækkefølge.

Test-cases:
  1.  POST `materials` med partner_id="A" tilføjer KUN til A
  2.  POST samme materiale med partner_id="B" tilføjer KUN til B (uafhængigt)
  3.  PUT `materials` med partner_id="A" omdøber KUN i A
  4.  PUT med partner_id="A" rør IKKE legacy `materials`-listen
  5.  DELETE med partner_id="A" sletter KUN fra A
  6.  DELETE i A → ingen ændring i B
  7.  GET med partner_id="A" returnerer KUN A's liste — IKKE legacy fallback
  8.  Samme materiale-navn kan eksistere i begge partner-lister samtidig
  9.  Slet i A med samme navn som i B → kun A's instans forsvinder
  10. PUT med partner_id som ikke har materialet returnerer 404 (separation)
  11. DELETE uden partner_id rør IKKE partner-specifikke lister
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

# Brug eksisterende CA fra iter29 UI-seed (bevaret efter wipe).
# Vi har ikke et fast SA-password mere (brugeren skiftede det) — så vi
# kører via CA-tokenet for at oprette/slette materialer direkte. CA har
# admin-adgang til lokationer i eget firma.
CA_EMAIL = "it29-ui-ca-UI29A@e2e.local"
CA_PASS = "TestPass2026!"

SUFFIX = uuid.uuid4().hex[:6].upper()

state = {"loc_code": None, "partner_a": None, "partner_b": None, "extra_partner_ids": []}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    # Vi forlader IT29-UI seed intakt (brugt af andre tests/UI manuelt),
    # men rydder ekstra partner_materials-keys vi tilføjede.
    if state["loc_code"]:
        # Ryd partner_materials helt så efterfølgende runs starter rent
        db.plads.update_one(
            {"location_code": state["loc_code"]},
            {"$set": {"partner_materials": {}}},
        )
    for pid in state["extra_partner_ids"]:
        db.companies.delete_one({"id": pid})


def _login(email, pw):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Login fejlede for {email}: {r.status_code} {r.text}")
    return r.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _post(token, path, body=None):
    return requests.post(f"{API}{path}", headers=_h(token), json=body or {}, timeout=15)


def _get(token, path):
    return requests.get(f"{API}{path}", headers=_h(token), timeout=15)


def _put(token, path, body):
    return requests.put(f"{API}{path}", headers=_h(token), json=body, timeout=15)


def _delete(token, path):
    return requests.delete(f"{API}{path}", headers=_h(token), timeout=15)


def test_setup_seed_partners(db):
    """Opret 2 logistik-partnere og tilknyt dem til IT29 UI Kunde's første
    lokation. Vi laver vores egen test-partnere så vi ikke forstyrrer
    eksisterende UI-data."""
    token = _login(CA_EMAIL, CA_PASS)
    state["ca_token"] = token

    # Hent lokationer fra CA's firma
    r = _get(token, "/api/org/locations")
    assert r.status_code == 200, r.text
    locs = r.json()
    assert locs, "IT29 UI Kunde har ingen lokationer — gen-seed via /app/tests/ui_seed_iter29.py"
    state["loc_code"] = locs[0].get("code") or locs[0].get("location_code")
    plads_id = locs[0]["id"]

    # Opret to logistik-firmaer direkte i DB (CA kan ikke selv oprette firmaer)
    for label in ["A", "B"]:
        cid = str(uuid.uuid4())
        db.companies.insert_one({
            "id": cid,
            "name": f"IT30 Partner {label} {SUFFIX}",
            "company_type": "logistics",
            "active": True,
        })
        state["extra_partner_ids"].append(cid)
    state["partner_a"] = state["extra_partner_ids"][0]
    state["partner_b"] = state["extra_partner_ids"][1]

    # Tilknyt begge til lokationen + ryd partner_materials til en tom state
    db.plads.update_one(
        {"id": plads_id},
        {"$set": {
            "assigned_logistics_company_ids": [state["partner_a"], state["partner_b"]],
            "partner_materials": {},
        }},
    )

    # Verificer via partners-endpoint
    r2 = _get(token, f"/api/locations/{state['loc_code']}/partners")
    assert r2.status_code == 200, r2.text
    partners_resp = r2.json()
    # Endpointet kan returnere {partners:[...]} eller direkte en liste
    plist = partners_resp.get("partners") if isinstance(partners_resp, dict) else partners_resp
    pids = {p["id"] for p in (plist or [])}
    assert state["partner_a"] in pids and state["partner_b"] in pids, \
        f"Partners ikke korrekt tilknyttet: fandt {pids}, forventede {state['partner_a']}, {state['partner_b']}"


# ===========================================================
#   ADD-tests
# ===========================================================
def test_add_material_to_partner_a_only(db):
    """Tilføj 'Pap A' kun til Partner A."""
    r = _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
              {"material": "Pap A", "partner_id": state["partner_a"]})
    assert r.status_code == 200, r.text
    assert r.json().get("partner_id") == state["partner_a"]
    # DB-verifikation: Pap A er KUN i A
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert pm.get(state["partner_a"]) == ["Pap A"]
    assert pm.get(state["partner_b"], []) == []


def test_add_material_to_partner_b_only(db):
    """Tilføj 'Glas B' kun til Partner B — bekræfter at A ikke ændres."""
    r = _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
              {"material": "Glas B", "partner_id": state["partner_b"]})
    assert r.status_code == 200, r.text
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert pm.get(state["partner_a"]) == ["Pap A"], "A's liste må ikke ændres når vi tilføjer til B"
    assert pm.get(state["partner_b"]) == ["Glas B"]


def test_add_same_name_to_both_partners_allowed(db):
    """Samme materiale-navn kan eksistere i BEGGE partnere på samme lokation."""
    for pid in [state["partner_a"], state["partner_b"]]:
        r = _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
                  {"material": "Plast Fælles", "partner_id": pid})
        assert r.status_code == 200, f"partner {pid}: {r.text}"
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert "Plast Fælles" in pm[state["partner_a"]]
    assert "Plast Fælles" in pm[state["partner_b"]]


def test_add_duplicate_within_same_partner_fails():
    """Add af samme materiale-navn 2x til SAMME partner skal fejle (idempotency)."""
    r = _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
              {"material": "Pap A", "partner_id": state["partner_a"]})
    assert r.status_code == 400


# ===========================================================
#   GET-tests
# ===========================================================
def test_get_returns_only_partner_a_materials(db):
    """GET med partner_id=A returnerer KUN A's materialer (ikke B's, ikke legacy)."""
    r = _get(state["ca_token"],
             f"/api/locations/{state['loc_code']}/containers?partner_id={state['partner_a']}")
    assert r.status_code == 200, r.text
    mats = {m["material"] for m in r.json().get("materials", [])}
    assert "Pap A" in mats
    assert "Plast Fælles" in mats
    assert "Glas B" not in mats, "B's materialer må IKKE lække til A's view"


def test_get_returns_only_partner_b_materials():
    r = _get(state["ca_token"],
             f"/api/locations/{state['loc_code']}/containers?partner_id={state['partner_b']}")
    assert r.status_code == 200, r.text
    mats = {m["material"] for m in r.json().get("materials", [])}
    assert "Glas B" in mats
    assert "Plast Fælles" in mats
    assert "Pap A" not in mats, "A's materialer må IKKE lække til B's view"


def test_get_with_legacy_materials_does_not_leak_to_partner(db):
    """Selv hvis legacy `materials`-listen har data, returnerer GET med
    partner_id stadig KUN partnerens liste (ingen fallback-merging)."""
    db.plads.update_one(
        {"location_code": state["loc_code"]},
        {"$set": {"materials": ["LegacyOnly"]}},
    )
    r = _get(state["ca_token"],
             f"/api/locations/{state['loc_code']}/containers?partner_id={state['partner_a']}")
    mats = {m["material"] for m in r.json().get("materials", [])}
    assert "LegacyOnly" not in mats, "Legacy må IKKE merges ind i partner-view"


# ===========================================================
#   EDIT-tests
# ===========================================================
def test_edit_material_in_partner_a_only(db):
    """PUT med partner_id=A omdøber KUN i A's liste — B forbliver urørt."""
    r = _put(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
             {"old_name": "Pap A", "new_name": "Pap A renamed", "partner_id": state["partner_a"]})
    assert r.status_code == 200, r.text
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert "Pap A" not in pm[state["partner_a"]]
    assert "Pap A renamed" in pm[state["partner_a"]]
    # B uændret
    assert "Glas B" in pm[state["partner_b"]]
    assert "Pap A renamed" not in pm[state["partner_b"]]


def test_edit_material_not_in_partner_returns_404():
    """PUT i partner B for et materiale der KUN findes i A → 404."""
    r = _put(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
             {"old_name": "Pap A renamed", "new_name": "Whatever", "partner_id": state["partner_b"]})
    assert r.status_code == 404, r.text


def test_edit_same_name_in_both_partners_isolated(db):
    """Når 'Plast Fælles' findes i BÅDE A og B, og vi omdøber i A,
    skal B's instans IKKE påvirkes."""
    r = _put(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
             {"old_name": "Plast Fælles", "new_name": "Plast (kun A)", "partner_id": state["partner_a"]})
    assert r.status_code == 200, r.text
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert "Plast (kun A)" in pm[state["partner_a"]]
    assert "Plast Fælles" not in pm[state["partner_a"]]
    assert "Plast Fælles" in pm[state["partner_b"]], "B's instans af 'Plast Fælles' skal være intakt"


# ===========================================================
#   DELETE-tests
# ===========================================================
def test_delete_material_in_partner_a_only(db):
    """DELETE med partner_id=A fjerner KUN fra A — B er urørt."""
    r = _delete(state["ca_token"],
                f"/api/locations/{state['loc_code']}/materials?material=Pap%20A%20renamed&partner_id={state['partner_a']}")
    assert r.status_code == 200, r.text
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert "Pap A renamed" not in pm[state["partner_a"]]
    # B's liste skal være præcis som før
    assert "Glas B" in pm[state["partner_b"]]
    assert "Plast Fælles" in pm[state["partner_b"]]


def test_delete_does_not_affect_other_partner_with_same_name(db):
    """Slet 'Plast Fælles' i B → A's 'Plast (kun A)' skal IKKE blive berørt."""
    r = _delete(state["ca_token"],
                f"/api/locations/{state['loc_code']}/materials?material=Plast%20F%C3%A6lles&partner_id={state['partner_b']}")
    assert r.status_code == 200, r.text
    plads = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0, "partner_materials": 1})
    pm = plads.get("partner_materials") or {}
    assert "Plast Fælles" not in pm[state["partner_b"]]
    assert "Plast (kun A)" in pm[state["partner_a"]], \
        "A's 'Plast (kun A)' skal være urørt — vi rørte kun ved B's 'Plast Fælles'"


def test_delete_not_in_partner_returns_404():
    """DELETE i B for materiale der kun er i A → 404."""
    r = _delete(state["ca_token"],
                f"/api/locations/{state['loc_code']}/materials?material=Plast%20(kun%20A)&partner_id={state['partner_b']}")
    assert r.status_code == 404, r.text


def test_delete_without_partner_id_does_not_touch_partner_lists(db):
    """DELETE uden partner_id → rør IKKE partner_materials, kun legacy."""
    # Vi har LegacyOnly i legacy listen (sat tidligere)
    plads_before = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0})
    pm_before = plads_before.get("partner_materials") or {}

    r = _delete(state["ca_token"],
                f"/api/locations/{state['loc_code']}/materials?material=LegacyOnly")
    assert r.status_code == 200, r.text

    plads_after = db.plads.find_one({"location_code": state["loc_code"]}, {"_id": 0})
    pm_after = plads_after.get("partner_materials") or {}
    assert pm_before == pm_after, \
        "Legacy DELETE må IKKE røre partner_materials"
    assert "LegacyOnly" not in (plads_after.get("materials") or [])


# ===========================================================
#   Real-world flow regression test
# ===========================================================
def test_user_reported_flow_a_delete_then_switch_to_b(db):
    """
    Brugerens KONKRETE klage:
       1. Vælg Partner A
       2. Slet et materiale i A
       3. Switch til Partner B
       4. → B's materialer skal vises uberørt (i UI: ingen tom liste, ingen
            forkert sletning, ingen fallback-leakage)

    Vi reproducerer via API: sæt B op med 3 materialer, slet i A, GET B.
    """
    # Setup: B har nu kun "Glas B" tilbage. Tilføj 2 mere.
    for m in ["Karton B", "Træ B"]:
        _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
              {"material": m, "partner_id": state["partner_b"]})

    # Snapshot B før
    r_b_before = _get(state["ca_token"],
                      f"/api/locations/{state['loc_code']}/containers?partner_id={state['partner_b']}")
    b_before = {m["material"] for m in r_b_before.json()["materials"]}
    assert b_before == {"Glas B", "Karton B", "Træ B"}

    # Tilføj noget i A, slet det igen
    _post(state["ca_token"], f"/api/locations/{state['loc_code']}/materials",
          {"material": "Midlertidig A", "partner_id": state["partner_a"]})
    r_del = _delete(state["ca_token"],
                    f"/api/locations/{state['loc_code']}/materials?material=Midlertidig%20A&partner_id={state['partner_a']}")
    assert r_del.status_code == 200, r_del.text

    # B's view skal være EKSAKT som før
    r_b_after = _get(state["ca_token"],
                     f"/api/locations/{state['loc_code']}/containers?partner_id={state['partner_b']}")
    b_after = {m["material"] for m in r_b_after.json()["materials"]}
    assert b_after == b_before, \
        f"B's materialer ændrede sig efter operationer på A — separation brudt!\n" \
        f"Før: {b_before}\nEfter: {b_after}"
