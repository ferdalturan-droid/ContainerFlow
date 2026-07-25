"""Fase 15.16 — Estimat-bestilling + dobbeltbestillings-blok.

Tester:
  1. Estimat-bestilling: tour_type="estimat" + estimated_count gemmes korrekt
     uden de normale required-felter (custom_address, container_id osv.).
  2. Dobbeltbestillings-blok: container + tour_type + completed=false matcher
     → ny POST returnerer 409.
  3. Forskellige tour_type på samme container er OK.
  4. Fuldført (completed=true) blokerer ikke.
"""
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env", override=False)
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL skal være sat (frontend/.env)"
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _make_unique_location():
    """Returner en location_code til test — vi springer over kravet om at
    location skal eksistere ved at indsætte direkte i DB."""
    return f"TEST-{uuid.uuid4().hex[:6].upper()}"


@pytest.mark.asyncio
async def test_duplicate_order_blocked_same_container_same_type():
    """Container 222 + Afhentning (normal) blokerer ny container 222 + Afhentning."""
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    # Find en valid plads + tilhørende customer + logistik-firma
    plads = await db.plads.find_one({"name": "Blishøj 1"}, {"_id": 0, "name": 1, "location_code": 1, "company_id": 1})
    assert plads, "Test forudsætter plads 'Blishøj 1'"
    loc_code = plads["location_code"]

    container_id = f"DUP-{uuid.uuid4().hex[:6]}"
    base_payload = {
        "location_code": loc_code,
        "material": "Træ",
        "co2_type_id": "",
        "container_number": "Container 1",
        "priority": "normal",
        "tour_type": "normal",
        "comment": "",
        "custom_address": "Test addr",
        "custom_container_id": container_id,
        "order_date": "2026-06-25",
        "open_from": "08:00",
        "open_to": "16:00",
        "plads_name": plads["name"],
        "delivery_address_id": "",
    }
    created_tour_ids = []
    created_order_ids = []
    # Første bestilling (skal gå igennem)
    r1 = requests.post(f"{API}/customer-orders/submit", json=base_payload, timeout=15)
    assert r1.status_code in (200, 201), f"Første bestilling skal gå igennem: {r1.status_code} {r1.text}"
    tour_id_1 = r1.json().get("tour_id")
    order_id_1 = r1.json().get("order_id")
    created_tour_ids.append(tour_id_1)
    created_order_ids.append(order_id_1)

    try:
        # Anden bestilling — SAMME container + SAMME tour_type → forventer 409
        r2 = requests.post(f"{API}/customer-orders/submit", json=base_payload, timeout=15)
        assert r2.status_code == 409, f"Forventede 409 (blok), fik {r2.status_code} {r2.text}"
        assert "ikke-fuldført" in r2.text.lower() or "duplicate" in r2.text.lower()

        # Forskellig tour_type → SKAL gå igennem
        diff_payload = {**base_payload, "tour_type": "vaerksted", "workshop_name": "Test værksted", "workshop_address": "Test adr"}
        r3 = requests.post(f"{API}/customer-orders/submit", json=diff_payload, timeout=15)
        assert r3.status_code in (200, 201), f"Forskellig tour_type skal gå igennem: {r3.status_code} {r3.text}"
        tour_id_3 = r3.json().get("tour_id")
        order_id_3 = r3.json().get("order_id")
        created_tour_ids.append(tour_id_3)
        created_order_ids.append(order_id_3)

        # Markér første ordre+tur som completed → ny POST samme tour_type → SKAL gå igennem
        # (i produktion sker det via PUT /tours/{id} som spejler status til ordren)
        await db.tours.update_one({"id": tour_id_1}, {"$set": {"completed": True}})
        await db.container_orders.update_one({"id": order_id_1}, {"$set": {"status": "completed"}})
        r4 = requests.post(f"{API}/customer-orders/submit", json=base_payload, timeout=15)
        assert r4.status_code in (200, 201), f"Efter completed, ny bestilling skal gå igennem: {r4.status_code} {r4.text}"
        tour_id_4 = r4.json().get("tour_id")
        order_id_4 = r4.json().get("order_id")
        created_tour_ids.append(tour_id_4)
        created_order_ids.append(order_id_4)
    finally:
        if created_tour_ids:
            await db.tours.delete_many({"id": {"$in": created_tour_ids}})
        if created_order_ids:
            await db.container_orders.delete_many({"id": {"$in": created_order_ids}})
        cli.close()


@pytest.mark.asyncio
async def test_estimat_order_minimal_fields():
    """Estimat — kun materiale, antal, dato, plads. Ingen container/adresse."""
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    plads = await db.plads.find_one({"name": "Blishøj 1"}, {"_id": 0, "name": 1, "location_code": 1})
    assert plads
    payload = {
        "location_code": plads["location_code"],
        "material": "Haveaffald",
        "co2_type_id": "",
        "container_number": "Estimat",
        "priority": "normal",
        "tour_type": "estimat",
        "comment": "",
        "custom_address": "",
        "custom_container_id": "",
        "order_date": "2026-07-01",
        "open_from": "",
        "open_to": "",
        "plads_name": plads["name"],
        "delivery_address_id": "",
        "estimated_count": 5,
    }
    r = requests.post(f"{API}/customer-orders/submit", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"Estimat skal kunne oprettes: {r.status_code} {r.text}"
    tour_id = r.json().get("tour_id")
    order_id = r.json().get("order_id")
    try:
        # Verificer dokumentet
        doc = await db.tours.find_one({"id": tour_id})
        assert doc, "Tour ikke fundet i DB"
        assert doc.get("tour_type") == "estimat"
        assert int(doc.get("estimated_count", 0)) == 5
        assert (doc.get("fraction") or "").lower() == "haveaffald"
    finally:
        await db.tours.delete_one({"id": tour_id})
        if order_id:
            await db.container_orders.delete_one({"id": order_id})
        cli.close()


@pytest.mark.asyncio
async def test_estimat_requires_material_and_count():
    """Estimat uden count → 400. Estimat uden materiale → 400."""
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    plads = await db.plads.find_one({"name": "Blishøj 1"}, {"_id": 0, "name": 1, "location_code": 1})
    assert plads
    base = {
        "location_code": plads["location_code"],
        "material": "Haveaffald",
        "co2_type_id": "",
        "container_number": "Estimat",
        "priority": "normal",
        "tour_type": "estimat",
        "comment": "",
        "custom_address": "",
        "custom_container_id": "",
        "order_date": "2026-07-01",
        "open_from": "",
        "open_to": "",
        "plads_name": plads["name"],
        "delivery_address_id": "",
    }
    # Mangler count
    r1 = requests.post(f"{API}/customer-orders/submit", json={**base, "estimated_count": 0}, timeout=15)
    assert r1.status_code == 400, f"Forventede 400 for count=0: {r1.status_code} {r1.text}"
    # Mangler materiale
    r2 = requests.post(f"{API}/customer-orders/submit", json={**base, "material": "", "estimated_count": 3}, timeout=15)
    assert r2.status_code == 400, f"Forventede 400 for tom materiale: {r2.status_code} {r2.text}"
    cli.close()
