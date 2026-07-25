"""Regression test for the delta import bug fix (2026-06-15, runde 11).

Bug: When SA published a delta with `op: 'add'` and `match_name` equal to an
existing holiday name in the LA's calendar, the operation was silently skipped
because match was on NAME only. LA saw success-toast but nothing was added.

Fix: `add` operations now match on (name + date), so the same holiday for a
different date/year is correctly added. Re-publishing the exact same entry is
idempotent (true duplicates are skipped).

Uses ephemeral test data with `_pytest_` prefix that is cleaned up after.
Production data is NEVER touched.
"""
import os
import sys
import uuid
import bcrypt
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app  # noqa: E402

PREFIX = "_pytest_delta_"


async def _cleanup(db):
    delta_ids = [d["id"] async for d in db.holiday_deltas.find(
        {"name": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    if delta_ids:
        await db.delta_notifications.delete_many({"delta_id": {"$in": delta_ids}})
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.holiday_calendars.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    await db.holiday_deltas.delete_many({"name": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)

    try:
        company_id = str(uuid.uuid4())
        la_id = str(uuid.uuid4())
        cal_id = str(uuid.uuid4())
        delta_id = str(uuid.uuid4())
        notif_id = str(uuid.uuid4())
        cust_id = f"{PREFIX}{uuid.uuid4().hex[:6]}"
        email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@example.test"
        password = "TestPass2026!"

        await db.companies.insert_one({
            "id": company_id, "name": f"{PREFIX}Company", "customer_id": cust_id,
            "company_type": "customer", "active": True, "serves_company_ids": [],
            "haster_fee": 200, "from_library": False, "slug": "",
        })
        await db.users.insert_one({
            "id": la_id, "email": email, "name": "PyTest LA",
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "role": "location_admin", "company_id": company_id,
            "active": True, "managed_company_ids": [],
            "invitation_status": "accepted",
        })
        # Calendar with existing Juledag 2026-12-24
        await db.holiday_calendars.insert_one({
            "id": cal_id, "company_id": company_id, "location_code": "9999",
            "name": f"{PREFIX}Calendar", "year": 2026, "is_active": True,
            "days": [{
                "name": "Juledag", "date": "2026-12-24",
                "closed": False, "open_from": "09:00", "open_to": "11:00",
                "delivery_address_id": None,
            }],
        })
        # Delta tries to add Juledag 2027-12-24 (same name, different date)
        await db.holiday_deltas.insert_one({
            "id": delta_id, "name": f"{PREFIX}Delta", "year": 2027,
            "status": "published",
            "operations": [{
                "op": "add", "match_name": "Juledag",
                "new_name": "Juledag", "new_date": "2027-12-24",
            }],
        })
        await db.delta_notifications.insert_one({
            "id": notif_id, "delta_id": delta_id, "user_id": la_id,
            "status": "pending",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Login
            r = await ac.post("/api/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, r.text
            token = r.json().get("token") or r.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}

            # FIRST PUBLISH — Juledag 2027 should be added (different date)
            r = await ac.post(
                f"/api/org/holiday-deltas/{notif_id}/import",
                json={"calendar_ids": [cal_id]},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["added"] == 1, f"Expected 1 added (same name diff date), got {body}"

            cal = await db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
            pairs = sorted([(d["name"], d["date"]) for d in cal["days"]])
            assert ("Juledag", "2026-12-24") in pairs
            assert ("Juledag", "2027-12-24") in pairs

            # SECOND PUBLISH — exact duplicate, should be 0 added (idempotent)
            r = await ac.post(
                f"/api/org/holiday-deltas/{notif_id}/import",
                json={"calendar_ids": [cal_id]},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["added"] == 0, f"Expected idempotent 0 added, got {body}"

            cal = await db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
            juledag_count = sum(1 for d in cal["days"] if d["name"] == "Juledag" and d["date"] == "2027-12-24")
            assert juledag_count == 1, f"Expected exactly 1 Juledag 2027, got {juledag_count}"

        print("✓ Test passed: date-aware add + idempotent retry both work")
    finally:
        await _cleanup(db)
        client.close()


def test_delta_import_date_aware():
    asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(_run())
