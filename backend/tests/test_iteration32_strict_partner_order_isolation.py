"""Iteration 32 — Strict per-partner ordre-isolation

Brugerklage 2026-06-15:
   "På bestillingssiden, når man opretter en bestilling for den ene logistik
    partner, så vises bestillingen (under 'mine bestillinger' og 'alle
    bestillinger') for begge logistik partnere. Det skal isoleres så
    bestillinger der oprettes kun vises for den valgte logistik partner."

Root cause: Frontend sendte `partner_id` ved submit, men backend's
`StructuredOrderCreate`-model accepterede det ikke (Pydantic droppede det
silently). Ordrer blev gemt uden `partner_id`, og `by-location`-endpointet
filtrerede ikke på partner.

Fix:
   1. `StructuredOrderCreate.partner_id` tilføjet
   2. `ContainerOrder.partner_id` tilføjet (persisteres på doc'en)
   3. `submit_customer_order` sætter `partner_id` på doc'en
   4. `GET /container-orders/by-location/{code}?partner_id=X` filtrerer strikt

Tests:
   1. Submit ordrer for Partner A og B — verificér at hver gemmes med
      korrekt partner_id
   2. GET med partner_id=A returnerer KUN A's ordrer
   3. GET med partner_id=B returnerer KUN B's ordrer
   4. GET uden partner_id returnerer ALLE (bagudkompat)
   5. Legacy ordrer (uden partner_id) returneres KUN i unfiltered mode
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

SUFFIX = uuid.uuid4().hex[:6].upper()

state = {
    "extra_partner_ids": [],
    "extra_order_ids": [],
    "loc_code": None,
}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    if state["extra_order_ids"]:
        db.container_orders.delete_many({"id": {"$in": state["extra_order_ids"]}})
    for pid in state["extra_partner_ids"]:
        db.companies.delete_one({"id": pid})
    if state["loc_code"]:
        db.plads.update_one(
            {"location_code": state["loc_code"]},
            {"$set": {"partner_materials": {}, "assigned_logistics_company_ids": []}},
        )


def _login(email, pw):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_setup_partners_and_containers(db):
    token = _login(CA_EMAIL, CA_PASS)
    state["ca_token"] = token

    locs = requests.get(f"{API}/api/org/locations",
                        headers=_h(token), timeout=10).json()
    loc = locs[0]
    state["loc_code"] = loc["code"] if loc.get("code") else loc["location_code"]
    plads_id = loc["id"]

    # 2 logistik-partnere
    for label in ["A", "B"]:
        pid = str(uuid.uuid4())
        db.companies.insert_one({
            "id": pid, "name": f"IT32 Partner {label} {SUFFIX}",
            "company_type": "logistics", "active": True,
        })
        state["extra_partner_ids"].append(pid)
    pa, pb = state["extra_partner_ids"]
    state["pa"], state["pb"] = pa, pb

    # Tilknyt + ryd materialer
    db.plads.update_one(
        {"id": plads_id},
        {"$set": {
            "assigned_logistics_company_ids": [pa, pb],
            "partner_materials": {pa: ["Pap A"], pb: ["Glas B"]},
        }},
    )

    # Opret container_overrides så bestillingssiden har "Container-nummer" at
    # bestille på (containers er knyttet til partner via partner_id).
    for label_partner in [("Container A1", pa, "Pap A"), ("Container B1", pb, "Glas B")]:
        label, pid, mat = label_partner
        db.container_overrides.insert_one({
            "id": str(uuid.uuid4()),
            "location_code": state["loc_code"],
            "material": mat,
            "container_label": label,
            "partner_id": pid,
            "custom_address": f"Test Adresse {SUFFIX}",
            "custom_container_id": label.replace(" ", "-"),
            "locked_address": False, "locked_hours": False, "locked_container_id": False,
        })


def _submit_order(material, container_label, partner_id):
    """Submit via /api/customer-orders/submit (kræver custom_address fordi vi
    autentificerer som CA — anonyme QR-kald har anden flow)."""
    r = requests.post(f"{API}/api/customer-orders/submit", json={
        "location_code": state["loc_code"],
        "material": material,
        "container_number": container_label,
        "priority": "normal",
        "tour_type": "normal",
        "custom_address": "Test Leveringsadresse 1, 8000 Aarhus",
        "custom_container_id": "",
        "order_date": "",
        "open_from": "", "open_to": "",
        "plads_name": "",
        "delivery_address_id": "",
        "partner_id": partner_id,
    }, headers=_h(state["ca_token"]), timeout=15)
    return r


def test_submit_orders_for_each_partner(db):
    """Submit 2 ordrer — en for hver partner — og verificér at partner_id
    persisteres på doc'en."""
    r_a = _submit_order("Pap A", "Container A1", state["pa"])
    assert r_a.status_code == 200, f"submit A: {r_a.status_code} {r_a.text}"

    r_b = _submit_order("Glas B", "Container B1", state["pb"])
    assert r_b.status_code == 200, f"submit B: {r_b.status_code} {r_b.text}"

    # Verificér på DB-niveau at partner_id er persisteret
    orders = list(db.container_orders.find(
        {"location_code": state["loc_code"]},
        {"_id": 0, "id": 1, "partner_id": 1, "material": 1},
    ).sort("created_at", -1).limit(2))
    assert len(orders) >= 2, f"Forventede mindst 2 ordrer, fik {len(orders)}"
    for o in orders[:2]:
        state["extra_order_ids"].append(o["id"])
        assert o.get("partner_id") in (state["pa"], state["pb"]), \
            f"Ordre mangler partner_id: {o}"


def test_get_with_partner_a_returns_only_a_orders():
    """Strict scope: partner_id=A returnerer KUN A's ordrer."""
    r = requests.get(
        f"{API}/api/container-orders/by-location/{state['loc_code']}"
        f"?all=1&include_cancelled=true&partner_id={state['pa']}",
        headers=_h(state["ca_token"]), timeout=10,
    )
    assert r.status_code == 200, r.text
    orders = r.json()
    # Alle returnerede ordrer skal være partner A's
    for o in orders:
        assert o.get("partner_id") == state["pa"], \
            f"Cross-partner leak: ordre {o.get('id')} har partner_id={o.get('partner_id')}, forventede {state['pa']}"
    # Mindst én ordre skal være vores test-ordre for A
    a_ids = [o["id"] for o in orders if o["id"] in state["extra_order_ids"]]
    assert len(a_ids) == 1, f"Forventede præcis 1 A-ordre i resultatet, fik {len(a_ids)}"


def test_get_with_partner_b_returns_only_b_orders():
    """Symmetri-test for Partner B."""
    r = requests.get(
        f"{API}/api/container-orders/by-location/{state['loc_code']}"
        f"?all=1&include_cancelled=true&partner_id={state['pb']}",
        headers=_h(state["ca_token"]), timeout=10,
    )
    assert r.status_code == 200, r.text
    orders = r.json()
    for o in orders:
        assert o.get("partner_id") == state["pb"], \
            f"Cross-partner leak: ordre {o.get('id')} har partner_id={o.get('partner_id')}, forventede {state['pb']}"
    b_ids = [o["id"] for o in orders if o["id"] in state["extra_order_ids"]]
    assert len(b_ids) == 1, f"Forventede præcis 1 B-ordre, fik {len(b_ids)}"


def test_get_without_partner_id_returns_both_legacy_and_partner_orders():
    """Bagudkompat: GET uden partner_id returnerer alle ordrer (legacy + alle
    partnere) — for at LA-dashboardet stadig kan se overblik."""
    r = requests.get(
        f"{API}/api/container-orders/by-location/{state['loc_code']}"
        f"?all=1&include_cancelled=true",
        headers=_h(state["ca_token"]), timeout=10,
    )
    assert r.status_code == 200, r.text
    orders = r.json()
    # Vi forventer mindst BÅDE vores 2 nye ordrer
    found_ids = {o["id"] for o in orders}
    assert state["extra_order_ids"][0] in found_ids
    assert state["extra_order_ids"][1] in found_ids


def test_legacy_order_without_partner_id_is_excluded_when_filtering(db):
    """En ordre uden `partner_id` (legacy) må IKKE dukke op når man
    filtrerer på en specifik partner."""
    legacy_id = str(uuid.uuid4())
    db.container_orders.insert_one({
        "id": legacy_id,
        "location_code": state["loc_code"],
        "material": "Pap A",
        "container_number": "Container A1",
        "order_date": "2026-06-15",
        "priority": "normal", "status": "pending",
        "company_id": "default",
        # BEMÆRK: ingen partner_id
        "created_at": "2026-06-15T00:00:00Z",
    })
    state["extra_order_ids"].append(legacy_id)

    # Filter for A → legacy må IKKE være med
    r = requests.get(
        f"{API}/api/container-orders/by-location/{state['loc_code']}"
        f"?all=1&include_cancelled=true&partner_id={state['pa']}",
        headers=_h(state["ca_token"]), timeout=10,
    )
    ids = {o["id"] for o in r.json()}
    assert legacy_id not in ids, \
        "Legacy-ordre (uden partner_id) lækkede ind i Partner A's view"


def test_user_reported_flow_a_order_invisible_to_b():
    """Brugerens KONKRETE klage reproduceret:
    1. Opret bestilling for Partner A
    2. Switch til Partner B
    3. → A's ordre må IKKE dukke op i "Mine bestillinger" / "Alle bestillinger" for B
    """
    # Submit en ny ordre for A
    r = _submit_order("Pap A", "Container A1", state["pa"])
    assert r.status_code == 200, r.text
    new_a_id = r.json().get("order_id") or r.json().get("id")
    if new_a_id:
        state["extra_order_ids"].append(new_a_id)

    # Hent B's view
    r_b = requests.get(
        f"{API}/api/container-orders/by-location/{state['loc_code']}"
        f"?all=1&include_cancelled=true&partner_id={state['pb']}",
        headers=_h(state["ca_token"]), timeout=10,
    )
    b_orders = r_b.json()
    for o in b_orders:
        assert o.get("partner_id") == state["pb"], \
            f"A's ordre lækkede til B! {o.get('id')} partner_id={o.get('partner_id')}"
