"""Fase 15.18 — Estimat-bestilling: estimated_count + comment persistence.

Verificerer at:
  1. POST /api/customer-orders/submit (public) med tour_type='estimat',
     estimated_count=3, comment='' gemmer eksakt comment='' (ingen auto-tekst)
     og estimated_count=3 på container_orders.
  2. Estimat med brugerens egen kommentar gemmes uændret.
  3. Eksisterende estimat-orders har IKKE auto-comment 'Estimat — N container(e)'.

DB-verifikation bruges (i stedet for GET /container-orders/by-location) fordi
endpointet er tenant-scoped og kræver auth — POST submit er public.
"""
import os
import uuid
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env", override=False)
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.mark.asyncio
async def test_estimat_empty_comment_persists_as_empty():
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
        "order_date": "2026-08-01",
        "open_from": "",
        "open_to": "",
        "plads_name": plads["name"],
        "delivery_address_id": "",
        "estimated_count": 3,
    }
    r = requests.post(f"{API}/customer-orders/submit", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
    body = r.json()
    tour_id = body["tour_id"]
    order_id = body["order_id"]
    try:
        order_doc = await db.container_orders.find_one({"id": order_id})
        assert order_doc
        assert int(order_doc.get("estimated_count", 0)) == 3
        # Comment skal være tom — IKKE 'Estimat — 3 container(e)'
        c = order_doc.get("comment", "")
        assert c == "", f"comment skal være tom: {c!r}"
        assert not c.lower().startswith("estimat —"), f"auto-comment fundet: {c!r}"
    finally:
        await db.tours.delete_one({"id": tour_id})
        await db.container_orders.delete_one({"id": order_id})
        cli.close()


@pytest.mark.asyncio
async def test_estimat_user_comment_preserved():
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    plads = await db.plads.find_one({"name": "Blishøj 1"}, {"_id": 0, "name": 1, "location_code": 1})
    user_comment = f"Test comment {uuid.uuid4().hex[:6]}"
    payload = {
        "location_code": plads["location_code"],
        "material": "Træ",
        "co2_type_id": "",
        "container_number": "Estimat",
        "priority": "normal",
        "tour_type": "estimat",
        "comment": user_comment,
        "custom_address": "",
        "custom_container_id": "",
        "order_date": "2026-08-02",
        "open_from": "",
        "open_to": "",
        "plads_name": plads["name"],
        "delivery_address_id": "",
        "estimated_count": 8,
    }
    r = requests.post(f"{API}/customer-orders/submit", json=payload, timeout=15)
    assert r.status_code in (200, 201)
    body = r.json()
    tour_id = body["tour_id"]
    order_id = body["order_id"]
    try:
        order_doc = await db.container_orders.find_one({"id": order_id})
        assert order_doc.get("comment") == user_comment
        assert int(order_doc.get("estimated_count", 0)) == 8
        tour_doc = await db.tours.find_one({"id": tour_id})
        assert int(tour_doc.get("estimated_count", 0)) == 8
    finally:
        await db.tours.delete_one({"id": tour_id})
        await db.container_orders.delete_one({"id": order_id})
        cli.close()


@pytest.mark.asyncio
async def test_no_existing_estimat_has_auto_comment():
    """Alle eksisterende estimat-orders må IKKE have 'Estimat — N' auto-tekst."""
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    bad = []
    async for o in db.container_orders.find({"tour_type": "estimat"}):
        c = (o.get("comment") or "").strip().lower()
        if c.startswith("estimat —") or c.startswith("estimat -"):
            bad.append({"id": o.get("id"), "comment": o.get("comment")})
    assert not bad, f"Auto-comment 'Estimat — N' fundet på {len(bad)} orders: {bad[:3]}"
    cli.close()
