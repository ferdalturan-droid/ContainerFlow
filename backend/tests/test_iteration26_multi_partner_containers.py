"""Iteration 26 — Per-partner container setup (brugerkrav 2026-06-15).

Tester:
  * GET /api/locations/{code}/partners returnerer listen af linkede logistik-partnere
  * POST /api/locations/{code}/containers/add kræver partner_id når lokationen har 2+ partnere
  * Auto-vælger partner når kun én er knyttet
  * Container-listen filtreres på partner_id (en partners materialer skjules for en anden)
  * Bagudkompatibilitet: gamle rækker uden partner_id stadig fungerer
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
CA_EMAIL = f"it26-ca-{SUFFIX}@e2e.local"
CA_PASS = "TestPass2026!"

state = {"company_ids": [], "user_ids": [], "loc_codes": [], "logistics_ids": []}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL); yield c[DB_NAME]; c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    try:
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.companies.delete_many({"id": {"$in": state["company_ids"] + state["logistics_ids"]}})
        db.plads.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.invitation_tokens.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.container_overrides.delete_many({"location_code": {"$in": state["loc_codes"]}})
        db.container_counts.delete_many({"location_code": {"$in": state["loc_codes"]}})
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


def test_seed(db):
    r = _login(SA_EMAIL, SA_PASS); assert r.status_code == 200, r.text
    sa_token = r.json()["token"]; state["sa_token"] = sa_token

    # Opret kunde
    r = _post(sa_token, "/api/superadmin/companies", {
        "name": f"IT26-CUST-{SUFFIX}", "customer_id": f"C26-{SUFFIX}",
        "company_type": "customer", "admin_email": CA_EMAIL,
        "admin_name": f"IT26 CA {SUFFIX}",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    state["company_ids"].append(body["company"]["id"])
    ca_id = body["created_admin"]["id"]
    state["user_ids"].append(ca_id)
    _accept_invite(db, ca_id, CA_PASS)
    state["ca_token"] = _login(CA_EMAIL, CA_PASS).json()["token"]

    # Opret 2 logistik-firmaer
    for i in range(2):
        r2 = _post(sa_token, "/api/superadmin/companies", {
            "name": f"IT26-LOG-{i}-{SUFFIX}", "customer_id": f"L26-{i}-{SUFFIX}",
            "company_type": "logistics", "admin_email": f"it26-log{i}-{SUFFIX}@e2e.local",
            "admin_name": f"IT26 Log {i} {SUFFIX}",
        })
        assert r2.status_code == 200, r2.text
        log_data = r2.json()
        state["logistics_ids"].append(log_data["company"]["id"])
        state["user_ids"].append(log_data["created_admin"]["id"])

    # Opret 1 lokation, tilknyt BEGGE partnere
    r3 = _post(state["ca_token"], "/api/org/locations", {
        "name": f"IT26-PLADS-{SUFFIX}", "city": "By", "address": "Vej 1",
    })
    assert r3.status_code in (200, 201), r3.text
    plads = r3.json()
    state["code"] = plads["code"]
    state["loc_codes"].append(plads["code"])
    plads_id = plads["id"]

    # Sæt 2 logistik-partnere på lokationen
    r4 = requests.put(f"{API}/api/org/locations/{plads_id}/logistics-partners",
                      headers=_h(state["ca_token"]),
                      json={"logistics_company_ids": state["logistics_ids"]})
    assert r4.status_code == 200, r4.text


def test_list_partners_endpoint():
    """Public endpoint returnerer linkede partnere."""
    r = _get(None, f"/api/locations/{state['code']}/partners")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["location_code"] == state["code"]
    assert len(d["partners"]) == 2
    ids = {p["id"] for p in d["partners"]}
    assert ids == set(state["logistics_ids"])


def test_add_container_requires_partner_when_multiple():
    """Når lokationen har 2+ partnere, må vi IKKE acceptere container/material
    uden partner_id."""
    r = _post(state["ca_token"], f"/api/locations/{state['code']}/containers/add", {
        "material": "Pap"
    })
    assert r.status_code == 400, r.text
    assert "partner" in r.text.lower()


def test_add_container_with_partner_succeeds():
    """Korrekt: partner_id sendt → container oprettes."""
    partner_a = state["logistics_ids"][0]
    r = _post(state["ca_token"], f"/api/locations/{state['code']}/containers/add", {
        "material": "Pap", "partner_id": partner_a,
    })
    assert r.status_code == 200, r.text
    assert r.json()["containers_per"] == 1
    assert r.json()["partner_id"] == partner_a


def test_add_container_rejects_unknown_partner():
    """partner_id der ikke er knyttet til lokationen ⇒ 400."""
    r = _post(state["ca_token"], f"/api/locations/{state['code']}/containers/add", {
        "material": "Glas", "partner_id": "00000000-aaaa-bbbb-cccc-000000000000",
    })
    assert r.status_code == 400


def test_containers_filtered_by_partner():
    """Tilføj endnu en container til samme materiale men for partner B.
    Verificér at GET /containers?partner_id= returnerer KUN den valgte partners
    containere."""
    partner_a = state["logistics_ids"][0]
    partner_b = state["logistics_ids"][1]
    # 1 container til partner B
    r1 = _post(state["ca_token"], f"/api/locations/{state['code']}/containers/add", {
        "material": "Pap", "partner_id": partner_b,
    })
    assert r1.status_code == 200, r1.text

    # Partner A view (allerede 1 oprettet i forrige test)
    r2 = _get(state["ca_token"],
              f"/api/locations/{state['code']}/containers?material=Pap&partner_id={partner_a}")
    assert r2.status_code == 200
    assert r2.json()["containers_per"] == 1

    # Partner B view
    r3 = _get(state["ca_token"],
              f"/api/locations/{state['code']}/containers?material=Pap&partner_id={partner_b}")
    assert r3.status_code == 200
    assert r3.json()["containers_per"] == 1

    # Uden partner_id (LA-overblik) — bemærk legacy-filter; her 0 da begge
    # rækker har partner_id sat.
    r4 = _get(state["ca_token"],
              f"/api/locations/{state['code']}/containers?material=Pap")
    assert r4.status_code == 200


def test_material_list_filtered_by_partner():
    """Med partner_id filter skal kun materialer der har data for den partner
    returneres."""
    partner_a = state["logistics_ids"][0]
    # Tilføj et materiale der KUN findes hos partner B
    r0 = _post(state["ca_token"], f"/api/locations/{state['code']}/containers/add", {
        "material": "EkstraMatB", "partner_id": state["logistics_ids"][1],
    })
    assert r0.status_code == 200
    r = _get(state["ca_token"],
             f"/api/locations/{state['code']}/containers?partner_id={partner_a}")
    assert r.status_code == 200
    mats = [m["material"] for m in r.json().get("materials", [])]
    # Pap er knyttet til både A og B; EkstraMatB er KUN B → må ikke være i listen
    assert "EkstraMatB" not in mats



def test_legacy_data_NOT_visible_when_partner_selected_strict_separation(db):
    """Brugerkrav 2026-06-15 (runde 4): STRICT separation per partner.
    Materialer uden partner_id (legacy) er IKKE synlige når en partner er
    valgt — partneren har sin egen liste i `plads.partner_materials[partner_id]`.

    Sletter al legacy/fallback-logik; partner ser kun sine egne materialer.
    """
    partner_a = state["logistics_ids"][0]
    code = state["code"]
    # Indsæt legacy-data direkte i DB (uden partner_id)
    db.container_counts.insert_one({
        "location_code": code, "material": "LegacyMat",
        "count": 1,
    })
    db.container_overrides.insert_one({
        "id": "legacy-test-1",
        "location_code": code, "material": "LegacyMat",
        "container_label": "Container 1",
        "custom_address": "Legacy Vej 1",
        "custom_container_id": "L1",
        "open_from": "08:00", "open_to": "16:00",
        "locked_address": False, "locked_hours": False, "locked_container_id": False,
        "capacity_measure_id": "",
        "updated_at": "2026-06-15T00:00:00+00:00",
    })

    # Partner A view skal IKKE vise LegacyMat (strict separation)
    r = _get(state["ca_token"],
             f"/api/locations/{code}/containers?partner_id={partner_a}")
    assert r.status_code == 200
    mats = [m["material"] for m in r.json().get("materials", [])]
    assert "LegacyMat" not in mats, \
        f"Strict separation: legacy materialer må IKKE være synlige for partner: {mats}"

    # Cleanup
    db.container_counts.delete_one({"location_code": code, "material": "LegacyMat"})
    db.container_overrides.delete_one({"id": "legacy-test-1"})


def test_copy_on_write_no_duplicate_count_after_partner_add(db):
    """Brugerkrav 2026-06-15 (runde 3): Når en partner tilføjer en container
    til et materiale der har legacy-data, skal totalet ALENE være det
    per-partner count (legacy ignoreres). Den anden partner skal stadig se
    sit eget tal (legacy fallback).

    Trin:
      1. Lokationen har legacy data (count=1) for material 'CopyMat'.
      2. Partner A's view viser 1 container (legacy fallback). ✓
      3. Partner A klikker '+ Tilføj container' (delta=1).
      4. Partner A's view skal NU vise 2 containere (ikke 3 — ingen dobbelt-tælling).
      5. Partner B's view skal stadig vise 1 container (legacy uberørt).
    """
    code = state["code"]
    partner_a = state["logistics_ids"][0]
    partner_b = state["logistics_ids"][1]

    # Tilføj materiale + legacy count=1 direkte i DB
    r0 = _post(state["ca_token"], f"/api/locations/{code}/materials",
               {"material": "CopyMat"})
    assert r0.status_code == 200, r0.text
    db.container_counts.insert_one({
        "location_code": code, "material": "CopyMat", "count": 1,
    })

    # Step 2: partner A ser 1 container (legacy fallback)
    r1 = _get(state["ca_token"],
              f"/api/locations/{code}/containers?material=CopyMat&partner_id={partner_a}")
    assert r1.status_code == 200
    assert r1.json()["containers_per"] == 1, r1.json()

    # Step 3: partner A tilføjer 1 container
    r2 = _post(state["ca_token"], f"/api/locations/{code}/containers/add", {
        "material": "CopyMat", "partner_id": partner_a, "delta": 1,
    })
    assert r2.status_code == 200, r2.text

    # Step 4: partner A skal nu se 2 containere — IKKE 3 (ingen sum-bug)
    r3 = _get(state["ca_token"],
              f"/api/locations/{code}/containers?material=CopyMat&partner_id={partner_a}")
    assert r3.status_code == 200
    assert r3.json()["containers_per"] == 2, \
        f"Forventede 2 containers efter +1, men fik {r3.json()['containers_per']}"

    # Step 5: partner B skal stadig se 1 container (legacy uberørt)
    r4 = _get(state["ca_token"],
              f"/api/locations/{code}/containers?material=CopyMat&partner_id={partner_b}")
    assert r4.status_code == 200
    assert r4.json()["containers_per"] == 1, \
        f"Partner B skal se uændret legacy count=1, men fik {r4.json()['containers_per']}"

    # Cleanup
    db.container_counts.delete_many({"location_code": code, "material": "CopyMat"})
    db.container_overrides.delete_many({"location_code": code, "material": "CopyMat"})


def test_copy_on_write_override_does_not_mutate_legacy(db):
    """Brugerkrav 2026-06-15 (runde 3): Når partner A redigerer en
    legacy-container, opdateres legacy-rækken IKKE — i stedet oprettes en
    ny per-partner override. Partner B ser stadig den oprindelige legacy.
    """
    code = state["code"]
    partner_a = state["logistics_ids"][0]
    partner_b = state["logistics_ids"][1]

    # Tilføj legacy material + override
    r0 = _post(state["ca_token"], f"/api/locations/{code}/materials",
               {"material": "CowMat"})
    assert r0.status_code == 200
    db.container_counts.insert_one({
        "location_code": code, "material": "CowMat", "count": 1,
    })
    db.container_overrides.insert_one({
        "id": "cow-legacy-1",
        "location_code": code, "material": "CowMat",
        "container_label": "Container 1",
        "custom_address": "Legacy Vej 1",
        "custom_container_id": "LEGACY-ABC",
        "open_from": "07:00", "open_to": "15:00",
        "locked_address": False, "locked_hours": False, "locked_container_id": False,
        "capacity_measure_id": "",
        "updated_at": "2026-06-15T00:00:00+00:00",
    })

    # Partner A redigerer Container 1
    r1 = requests.put(
        f"{API}/api/locations/{code}/containers/override",
        headers=_h(state["ca_token"]),
        json={
            "material": "CowMat", "container_label": "Container 1",
            "partner_id": partner_a,
            "custom_container_id": "PARTNER-A-XYZ",
            "open_from": "09:00", "open_to": "17:00",
            "locked_hours": True,
        },
        timeout=15,
    )
    assert r1.status_code == 200, r1.text

    # Legacy override må IKKE være ændret
    legacy = db.container_overrides.find_one({"id": "cow-legacy-1"})
    assert legacy is not None
    assert legacy["custom_container_id"] == "LEGACY-ABC", "Legacy må ikke muteres"
    assert legacy["open_from"] == "07:00"
    assert legacy.get("partner_id", "") == "", "Legacy partner_id skal forblive tom"

    # En NY per-partner override skal være oprettet
    partner_ov = db.container_overrides.find_one({
        "location_code": code, "material": "CowMat",
        "container_label": "Container 1", "partner_id": partner_a,
    })
    assert partner_ov is not None
    assert partner_ov["custom_container_id"] == "PARTNER-A-XYZ"

    # Partner B's view bruger stadig legacy override (LEGACY-ABC)
    r2 = _get(state["ca_token"],
              f"/api/locations/{code}/containers?material=CowMat&partner_id={partner_b}")
    assert r2.status_code == 200
    cs = r2.json()["containers"]
    # Find Container 1
    c1 = next((c for c in cs if c["label"] == "Container 1"), None)
    assert c1 is not None
    assert c1["container_id"] == "LEGACY-ABC", \
        f"Partner B skal se den uændrede legacy override (LEGACY-ABC), men fik {c1['container_id']}"

    # Partner A's view bruger NU sin egen override (PARTNER-A-XYZ)
    r3 = _get(state["ca_token"],
              f"/api/locations/{code}/containers?material=CowMat&partner_id={partner_a}")
    assert r3.status_code == 200
    cs = r3.json()["containers"]
    c1 = next((c for c in cs if c["label"] == "Container 1"), None)
    assert c1 is not None
    assert c1["container_id"] == "PARTNER-A-XYZ"

    # Cleanup
    db.container_counts.delete_many({"location_code": code, "material": "CowMat"})
    db.container_overrides.delete_many({"location_code": code, "material": "CowMat"})


def test_legacy_cleanup_after_copy_on_write_tests(db):
    """Final cleanup after the COW tests above — sletter den tidligere
    LegacyMat-test-data der blev tilbage fra test_legacy_global_data_visible..."""
    code = state["code"]
    db.container_counts.delete_one({"location_code": code, "material": "LegacyMat"})
    db.container_overrides.delete_one({"id": "legacy-test-1"})



def test_partner_materials_strict_separation(db):
    """Brugerkrav 2026-06-15 (runde 4): Tilføj materiale under partner A
    må IKKE oprette/vise det under partner B. Samme for sletning.
    """
    code = state["code"]
    partner_a = state["logistics_ids"][0]
    partner_b = state["logistics_ids"][1]

    # 1. Partner A: tilføj materiale "PartnerA-Only"
    r1 = _post(state["ca_token"], f"/api/locations/{code}/materials",
               {"material": "PartnerA-Only", "partner_id": partner_a})
    assert r1.status_code == 200, r1.text
    assert r1.json()["partner_id"] == partner_a
    assert "PartnerA-Only" in r1.json()["materials"]

    # 2. Partner A view: ser PartnerA-Only
    r2 = _get(state["ca_token"], f"/api/locations/{code}/containers?partner_id={partner_a}")
    assert r2.status_code == 200
    mats_a = [m["material"] for m in r2.json().get("materials", [])]
    assert "PartnerA-Only" in mats_a, mats_a

    # 3. Partner B view: ser IKKE PartnerA-Only (strict separation)
    r3 = _get(state["ca_token"], f"/api/locations/{code}/containers?partner_id={partner_b}")
    assert r3.status_code == 200
    mats_b = [m["material"] for m in r3.json().get("materials", [])]
    assert "PartnerA-Only" not in mats_b, \
        f"STRICT separation: PartnerA-Only må IKKE være synlig for B: {mats_b}"

    # 4. Slet materialet fra partner A
    r4 = requests.delete(
        f"{API}/api/locations/{code}/materials?material=PartnerA-Only&partner_id={partner_a}",
        headers=_h(state["ca_token"]), timeout=15,
    )
    assert r4.status_code == 200, r4.text


def test_partner_materials_duplicate_name_allowed_across_partners(db):
    """Brugerkrav 2026-06-15: Hvis to partnere har samme materialenavn (fx Pap)
    skal det oprettes to gange — ét pr. partner. Begge lister er uafhængige.
    """
    code = state["code"]
    partner_a = state["logistics_ids"][0]
    partner_b = state["logistics_ids"][1]

    # Tilføj "DupMat" til BÅDE partner A og B
    r1 = _post(state["ca_token"], f"/api/locations/{code}/materials",
               {"material": "DupMat", "partner_id": partner_a})
    assert r1.status_code == 200, r1.text
    r2 = _post(state["ca_token"], f"/api/locations/{code}/materials",
               {"material": "DupMat", "partner_id": partner_b})
    assert r2.status_code == 200, r2.text

    # Slet DupMat KUN fra partner A
    rd = requests.delete(
        f"{API}/api/locations/{code}/materials?material=DupMat&partner_id={partner_a}",
        headers=_h(state["ca_token"]), timeout=15,
    )
    assert rd.status_code == 200, rd.text

    # Partner A: DupMat væk. Partner B: stadig der.
    r5 = _get(state["ca_token"], f"/api/locations/{code}/containers?partner_id={partner_a}")
    r6 = _get(state["ca_token"], f"/api/locations/{code}/containers?partner_id={partner_b}")
    assert "DupMat" not in [m["material"] for m in r5.json().get("materials", [])]
    assert "DupMat" in [m["material"] for m in r6.json().get("materials", [])], \
        "B's DupMat må IKKE forsvinde når A slettes"
