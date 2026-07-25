#!/usr/bin/env python3
"""Migration: Backfill tour-niveau felter fra ordren — created_by_name,
created_by_email, capacity_label, capacity_volume_m3, order_date.

Tidligere blev disse felter kun gemt på `container_orders`. Fra Fase 13
gemmes de også på selve `tours`-doc'en så chaufføren og logistik-admin
kan se "Bestilt af" + kapacitetsmål direkte i tour-listen uden et ekstra
join-opslag.

Kør:  python /app/scripts/migration_phase13_tour_fields.py
Idempotent: kan køres flere gange uden bivirkninger.
"""
import os, asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    print(f"Connected to MongoDB: db='{db_name}'")
    print("──────────────────────────────────────────────────")

    # Find tours linked to a customer-order doc
    cursor = db.tours.find(
        {"order_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "id": 1, "order_id": 1, "created_by_name": 1,
         "capacity_label": 1, "order_date": 1},
    )
    updated = 0
    skipped = 0
    async for tour in cursor:
        need_backfill = not all(tour.get(k) for k in (
            "created_by_name", "capacity_label", "order_date",
        ))
        if not need_backfill:
            skipped += 1
            continue
        order = await db.container_orders.find_one(
            {"id": tour["order_id"]},
            {"_id": 0, "created_by_name": 1, "created_by_email": 1,
             "capacity_label": 1, "capacity_volume_m3": 1, "order_date": 1},
        )
        if not order:
            skipped += 1
            continue
        await db.tours.update_one(
            {"id": tour["id"]},
            {"$set": {
                "created_by_name": order.get("created_by_name", ""),
                "created_by_email": order.get("created_by_email", ""),
                "capacity_label": order.get("capacity_label", ""),
                "capacity_volume_m3": order.get("capacity_volume_m3"),
                "order_date": order.get("order_date", ""),
            }},
        )
        updated += 1

    print(f"✓  Opdaterede {updated} tours")
    print(f"   Sprang {skipped} over (allerede fyldt eller ingen ordre fundet)")
    print("──────────────────────────────────────────────────")
    print("Migration færdig.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
