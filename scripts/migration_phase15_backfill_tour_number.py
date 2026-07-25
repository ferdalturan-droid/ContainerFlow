"""
Phase 15 (2026-06-19) — Backfill `tour_number` på eksisterende ture.

Genererer korte unikke koder ({CUSTOMER_PREFIX}-{nnnn}) for alle ture i DB der
mangler tour_number. Bruger samme `tour_counters`-kollektion som backend's
_generate_tour_number-helper, så fortløbende inserts efter migrationen
fortsætter i den samme sekvens.

Idempotent — kan køres flere gange uden at duplikere kodet på eksisterende
ture med en tour_number.

Kør:
    cd /app/backend && python ../scripts/migration_phase15_backfill_tour_number.py
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME   = os.environ["DB_NAME"]


def _derive_prefix(tour):
    code = (tour.get("customer_code") or "").strip().upper()
    if code:
        return code
    name = tour.get("customer_name") or ""
    letters = "".join(c for c in name.upper() if c.isalpha())
    if letters:
        return letters[:3]
    return "TUR"


async def main():
    cli = AsyncIOMotorClient(MONGO_URL)
    db  = cli[DB_NAME]
    missing = await db.tours.find(
        {"$or": [{"tour_number": ""}, {"tour_number": {"$exists": False}}]},
        {"_id": 0, "id": 1, "customer_code": 1, "customer_name": 1},
    ).to_list(None)
    print(f"Found {len(missing)} tours missing tour_number")
    n_done = 0
    for t in missing:
        prefix = _derive_prefix(t)
        res = await db.tour_counters.find_one_and_update(
            {"_id": prefix},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        seq = (res or {}).get("seq", 1)
        code = f"{prefix}-{seq:04d}"
        await db.tours.update_one({"id": t["id"]}, {"$set": {"tour_number": code}})
        n_done += 1
        if n_done % 50 == 0:
            print(f"  …backfilled {n_done}/{len(missing)}")
    print(f"DONE — backfilled {n_done} tours")
    cli.close()


if __name__ == "__main__":
    asyncio.run(main())
