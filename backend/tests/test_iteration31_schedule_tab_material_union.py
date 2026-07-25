"""Iteration 31 — Materiale-union for LA's schedule-tabs.

Brugerklage 2026-06-15:
   "Materialerne på bestillingsiden skal være optioner i 'åbnings- og
    lukketidspunkter' tab i location admin siden for følgende to:
    'tilknyt helligdagskalender til materialer' og 'tilknyt åbnings- og
    lukketidspunkter for ikke-helligdage' i nuværende version referere
    den til nogle tidligere materialer (de blev slettet på bestillingssiden)
    så sørg for at optioner reflektere materialer der findes på bestillings-
    siden on real time."

Bug: `GET /api/locations/{code}/containers` (uden partner_id) returnerede
legacy `location.materials` — en gammel global liste som ofte havde
forældede navne fra før partner-arkitekturen. Schedule-tabbene viste
disse i deres dropdown.

Fix: Når pladsen har MINDST ÉN partner med materialer
(`partner_materials[X]` non-tom), returnerer endpointet nu UNIONEN af
alle partneres materialer — og IGNORERER helt legacy-listen. Det er
præcis hvad bestillingssiden viser når man cykler igennem partnerne.
"""
import os
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

CA_EMAIL = "it29-ui-ca-UI29A@e2e.local"
CA_PASS = "TestPass2026!"

state = {"extra_partner_ids": [], "loc_code": None}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    for pid in state["extra_partner_ids"]:
        db.companies.delete_one({"id": pid})
    if state["loc_code"]:
        db.plads.update_one(
            {"location_code": state["loc_code"]},
            {"$set": {"partner_materials": {}, "materials": []}},
        )


def _login(email, pw):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_setup_partners_with_distinct_materials(db):
    """Lokation med 2 partnere — A har materialer [X, Y], B har [Y, Z].
    Sæt OGSÅ en legacy materials-liste med en gammel slettet entry."""
    token = _login(CA_EMAIL, CA_PASS)
    state["ca_token"] = token

    locs = requests.get(f"{API}/api/org/locations", headers=_h(token), timeout=10).json()
    loc = locs[0]
    state["loc_code"] = loc["code"] if loc.get("code") else loc["location_code"]
    plads_id = loc["id"]

    # Opret 2 logistik-partnere
    for label in ["A", "B"]:
        pid = str(uuid.uuid4())
        db.companies.insert_one({
            "id": pid, "name": f"IT31 Partner {label}", "company_type": "logistics",
            "active": True,
        })
        state["extra_partner_ids"].append(pid)
    pa, pb = state["extra_partner_ids"]
    state["partner_a"] = pa
    state["partner_b"] = pb

    # Setup:
    #  * partner_materials[A] = [Pap A, Plast Fælles]
    #  * partner_materials[B] = [Plast Fælles, Glas B]
    #  * legacy materials = ["GammelMatSomBrugeren_slettede"]
    db.plads.update_one(
        {"id": plads_id},
        {"$set": {
            "assigned_logistics_company_ids": [pa, pb],
            "partner_materials": {
                pa: ["Pap A", "Plast Fælles"],
                pb: ["Plast Fælles", "Glas B"],
            },
            "materials": ["GammelMatSomBrugeren_slettede"],
        }},
    )


def test_with_partner_id_returns_only_that_partner():
    """Sanity: partner_id-scope er stadig strict."""
    t = state["ca_token"]
    r = requests.get(
        f"{API}/api/locations/{state['loc_code']}/containers?partner_id={state['partner_a']}",
        headers=_h(t), timeout=10,
    )
    mats = {m["material"] for m in r.json()["materials"]}
    assert mats == {"Pap A", "Plast Fælles"}, mats


def test_without_partner_id_returns_union_when_partner_aware():
    """Krav: Schedule-tabbens dropdown (henter UDEN partner_id) skal vise
    UNIONEN af partneres materialer — og IKKE den gamle legacy-entry."""
    t = state["ca_token"]
    r = requests.get(
        f"{API}/api/locations/{state['loc_code']}/containers",
        headers=_h(t), timeout=10,
    )
    mats = {m["material"] for m in r.json()["materials"]}
    assert mats == {"Pap A", "Plast Fælles", "Glas B"}, mats
    assert "GammelMatSomBrugeren_slettede" not in mats, \
        "Legacy/slettet materiale MÅ IKKE lække ind i schedule-dropdownen"


def test_legacy_only_location_still_works(db):
    """Bagudkompat: En lokation der ALDRIG har brugt partner_materials skal
    stadig se sin legacy `materials`-liste i GET uden partner_id."""
    # Sæt en tom partner_materials og legacy med rigtige materialer
    db.plads.update_one(
        {"location_code": state["loc_code"]},
        {"$set": {
            "partner_materials": {},
            "materials": ["Legacy Mat 1", "Legacy Mat 2"],
        }},
    )
    t = state["ca_token"]
    r = requests.get(
        f"{API}/api/locations/{state['loc_code']}/containers",
        headers=_h(t), timeout=10,
    )
    mats = {m["material"] for m in r.json()["materials"]}
    assert "Legacy Mat 1" in mats
    assert "Legacy Mat 2" in mats


def test_partner_aware_legacy_is_completely_ignored(db):
    """Vigtig regression: Selv hvis legacy `materials` har VIRKELIG mange
    forældede entries (10+), så længe der findes ÉN partner_material entry,
    SKAL legacy IGNORERES."""
    pa = state["partner_a"]
    db.plads.update_one(
        {"location_code": state["loc_code"]},
        {"$set": {
            "partner_materials": {pa: ["KunDenne"]},
            "materials": ["Old1", "Old2", "Old3", "Old4", "Old5"],
        }},
    )
    t = state["ca_token"]
    r = requests.get(
        f"{API}/api/locations/{state['loc_code']}/containers",
        headers=_h(t), timeout=10,
    )
    mats = {m["material"] for m in r.json()["materials"]}
    assert mats == {"KunDenne"}, \
        f"Forventede kun {{'KunDenne'}}, fik {mats}. Legacy lækker stadig!"
