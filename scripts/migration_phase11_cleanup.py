#!/usr/bin/env python3
"""Migration: Ryd vægt + CO2 fra ordrer/ture hvor opgavetypen IKKE er
`normal` (afhent container).

Reglen (brugerkrav 2026-06-18):
- Vægt udfyldes KUN for opgavetypen 'afhent container' (tour_type='normal').
- CO2 beregnes KUN for opgavetypen 'afhent container'.
- For 'flyt' (byt container), 'vaerksted' (til værksted) og
  'afhent_vaerksted' (afhent fra værksted): ingen vægt, ingen CO2.

Denne migration sætter weight_kg=0, co2_kg=0, co2_factor=0,
co2_type_id="", co2_type_name="" på alle `container_orders` hvor
`tour_type != "normal"`.

Kør:  python /app/scripts/migration_phase11_cleanup.py
Idempotent: kan køres flere gange uden bivirkninger.
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Tving .env-loading uanset arbejdsdir
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Connected to MongoDB: db='{db_name}'")
    print("──────────────────────────────────────────────────")

    # Match orders med tour_type != 'normal' OG som har en non-zero værdi
    # at rydde op i. Vi rører ikke "normal"-ordrer.
    non_normal_filter = {
        "tour_type": {"$nin": ["normal", "", None]},
        "$or": [
            {"weight_kg": {"$gt": 0}},
            {"co2_kg": {"$gt": 0}},
            {"co2_factor": {"$gt": 0}},
            {"co2_type_id": {"$nin": ["", None]}},
            {"co2_type_name": {"$nin": ["", None]}},
        ],
    }

    affected = await db.container_orders.count_documents(non_normal_filter)
    print(f"Container-orders der ryddes: {affected}")

    if affected == 0:
        print("Ingen ordrer kræver oprydning. Færdig.")
        client.close()
        return

    # Vis først eksempel-ordrer (op til 5) til verifikation
    print("\nEksempler på ordrer der bliver berørt:")
    async for doc in db.container_orders.find(non_normal_filter, {
        "_id": 0, "id": 1, "tour_type": 1, "material": 1, "weight_kg": 1,
        "co2_kg": 1, "co2_type_name": 1, "location_code": 1,
    }).limit(5):
        print(f"  - {doc.get('id','?')[:8]}… ({doc.get('tour_type')}) "
              f"{doc.get('material','?')} · "
              f"vægt={doc.get('weight_kg', 0)} kg · "
              f"co2={doc.get('co2_kg', 0)} kg · "
              f"type='{doc.get('co2_type_name','')}'")

    result = await db.container_orders.update_many(
        non_normal_filter,
        {"$set": {
            "weight_kg": 0.0,
            "co2_kg": 0.0,
            "co2_factor": 0.0,
            "co2_type_id": "",
            "co2_type_name": "",
        }},
    )
    print(f"\n✓  Opdaterede {result.modified_count} container_orders")

    # Nogle ture har også co2_kg / weight_kg snapshot — ryd dem også for
    # konsistens (samme regel: kun 'normal' beholder).
    tours_filter = {
        "tour_type": {"$nin": ["normal", "", None]},
        "$or": [
            {"weight": {"$gt": 0}},
            {"co2_kg": {"$gt": 0}},
        ],
    }
    tours_affected = await db.tours.count_documents(tours_filter)
    if tours_affected > 0:
        tres = await db.tours.update_many(
            tours_filter,
            {"$set": {"weight": 0, "co2_kg": 0.0}},
        )
        print(f"✓  Opdaterede {tres.modified_count} tours (snapshot ryddet)")
    else:
        print("Ingen tours-dokumenter kræver oprydning.")

    print("──────────────────────────────────────────────────")
    print("Migration færdig.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
