"""Fase 15.14 — Multi-tenant isolation: drivers må ALDRIG se ture
fra et andet logistikfirma.

Tester:
  1. To logistikfirmaer (ILK + City Container) der begge betjener samme kunde (X)
  2. Kunden opretter 2 bestillinger: én rettet til ILK, én rettet til City
  3. En ILK-chauffør ser KUN ILK's bestilling, IKKE City's
  4. Tilsvarende skal driver_id-undtagelsen ikke kunne bypasse — selv hvis
     en City-tur havde driver_id sat til ILK-chauffør, skal den IKKE være
     synlig fordi assigned_logistics_company_ids ikke matcher.
"""
import os
import uuid
import asyncio
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def _find_logistics_company_id() -> str:
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    # ILK = vores test-logistik-firma
    doc = await db.users.find_one({"email": "ilkdistadmin@gmail.com"}, {"_id": 0, "company_id": 1})
    cli.close()
    return doc["company_id"]


@pytest.mark.asyncio
async def test_driver_cannot_see_other_logistics_company_tours():
    """En ILK-chauffør må aldrig se ture rettet til City Container,
    selv hvis turen ved en fejl har deres driver_id sat."""
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]

    # Identificer ILK + City Container logistik-firmaer
    ilk = await db.users.find_one({"email": "ilkdistadmin@gmail.com"}, {"_id": 0, "company_id": 1})
    city = await db.users.find_one({"email": "citycontainerdistadmin@gmail.com"}, {"_id": 0, "company_id": 1})
    assert ilk and city, "Begge logistik-admins skal findes for testen"
    ilk_cid = ilk["company_id"]
    city_cid = city["company_id"]
    assert ilk_cid != city_cid, "ILK og City skal have forskellige company_ids"

    # Brug en test-kunde (vælg første customer_admin's company)
    cust = await db.users.find_one({"role": "customer_admin"}, {"_id": 0, "company_id": 1})
    assert cust, "Mindst én customer_admin skal findes"
    customer_cid = cust["company_id"]

    # Opret en test-chauffør i ILK
    driver_id = f"test-driver-{uuid.uuid4().hex[:8]}"
    await db.users.insert_one({
        "id": driver_id,
        "email": f"isolation_test_{driver_id}",
        "name": "Isolation Test Driver",
        "role": "driver",
        "company_id": ilk_cid,
        "active": True,
        "active_customer_id": customer_cid,
        "assigned_customer_ids": [customer_cid],
        "password_hash": "$2b$12$dummy",
    })

    # Opret 2 ture:
    #  - en til ILK (skal være synlig)
    #  - en til City Container (skal IKKE være synlig, selv om driver_id matcher)
    ilk_tour_id = f"test-tour-ilk-{uuid.uuid4().hex[:6]}"
    city_tour_id = f"test-tour-city-{uuid.uuid4().hex[:6]}"
    await db.tours.insert_many([
        {
            "id": ilk_tour_id,
            "company_id": customer_cid,
            "assigned_logistics_company_ids": [ilk_cid],
            "plads": "TestPlads",
            "fraction": "Pap-ILK",
            "date": "2026-02-20",
            "on_way": False,
            "completed": False,
            "is_pause": False,
        },
        {
            "id": city_tour_id,
            "company_id": customer_cid,
            "assigned_logistics_company_ids": [city_cid],  # rettet til City Container!
            "driver_id": driver_id,  # FORSØG på leak: tour er for City, men driver_id peger på ILK-chauffør
            "plads": "TestPlads",
            "fraction": "Pap-CITY",
            "date": "2026-02-20",
            "on_way": False,
            "completed": False,
            "is_pause": False,
        },
    ])

    try:
        # Importer get_tours direkte og kald den med driver-payload
        import sys
        sys.path.insert(0, "/app/backend")
        from server import get_tours

        # Simuler driver-login payload
        driver_payload = {
            "sub": driver_id,
            "user_id": driver_id,
            "role": "driver",
            "company_id": ilk_cid,
            "email": f"isolation_test_{driver_id}",
        }

        # Mock dependency injection ved at kalde funktionen direkte
        # (omgå middleware ved at sætte context vars)
        from auth import current_company_id, current_extra_visible_company_ids
        tok1 = current_company_id.set(ilk_cid)
        tok2 = current_extra_visible_company_ids.set([])

        try:
            result = await get_tours(payload=driver_payload)
        finally:
            current_company_id.reset(tok1)
            current_extra_visible_company_ids.reset(tok2)

        ids = {t["id"] for t in (result or [])}
        assert ilk_tour_id in ids, f"ILK-tur skal være synlig: {ids}"
        assert city_tour_id not in ids, (
            f"LEAK: City Container-tur er synlig for ILK-chauffør, "
            f"selv om driver_id matcher! Tour ids: {ids}"
        )
    finally:
        # Cleanup
        await db.tours.delete_many({"id": {"$in": [ilk_tour_id, city_tour_id]}})
        await db.users.delete_one({"id": driver_id})
        cli.close()
