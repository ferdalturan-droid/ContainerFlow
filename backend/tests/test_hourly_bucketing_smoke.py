"""Smoke test: hourly bucketing uses created_at in Danish local time.

Bug fix verification:
- 3 orders with created_at at UTC times that map to local Danish hours 14, 14, 08
- Expected: pattern shows {"14:00": 2, "08:00": 1}
- Old buggy behavior (open_from=00:00) would yield {"00:00": 3}
"""
import os
import sys
import uuid
import bcrypt
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from server import app

PREFIX = "_smoke_hourly_"
DK_TZ = ZoneInfo("Europe/Copenhagen")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    async def cleanup():
        await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
        await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
        await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})
        await db.container_orders.delete_many({"location_code": {"$regex": f"^{PREFIX}"}})

    await cleanup()

    try:
        company_id = str(uuid.uuid4())
        la_id = str(uuid.uuid4())
        loc_code = f"{PREFIX}5544"
        email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@example.test"
        password = "TestPass2026!"

        await db.companies.insert_one({
            "id": company_id, "name": f"{PREFIX}Co", "customer_id": f"{PREFIX}{uuid.uuid4().hex[:6]}",
            "company_type": "customer", "active": True, "serves_company_ids": [],
            "haster_fee": 200, "from_library": False, "slug": "",
        })
        await db.users.insert_one({
            "id": la_id, "email": email, "name": "Smoke LA Hours",
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "role": "location_admin", "company_id": company_id,
            "active": True, "managed_company_ids": [],
            "invitation_status": "accepted",
            "location_code": loc_code, "assigned_plads_ids": [loc_code],
        })
        await db.plads.insert_one({
            "id": str(uuid.uuid4()), "company_id": company_id,
            "location_code": loc_code, "name": f"{PREFIX}Plads",
            "city": "Helsingør",
        })

        # Build TODAY's date in Denmark so we hit the "day" period (hour granularity)
        today_dk = datetime.now(DK_TZ).date()
        # 3 orders at local DK hours 14:01, 14:35, 08:15
        local_times = [
            datetime.combine(today_dk, datetime.min.time()).replace(hour=14, minute=1, tzinfo=DK_TZ),
            datetime.combine(today_dk, datetime.min.time()).replace(hour=14, minute=35, tzinfo=DK_TZ),
            datetime.combine(today_dk, datetime.min.time()).replace(hour=8, minute=15, tzinfo=DK_TZ),
        ]
        for lt in local_times:
            utc_iso = lt.astimezone(timezone.utc).isoformat()
            await db.container_orders.insert_one({
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "location_code": loc_code,
                "material": "Pap",
                "order_date": today_dk.isoformat(),
                "priority": "normal",
                "status": "pending",
                "status_label": "afventer",
                "tour_type": "normal",
                "created_at": utc_iso,
                "open_from": "",  # Empty (the field that USED to be incorrectly read)
            })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/api/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, r.text
            token = r.json().get("token") or r.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(f"/api/org/reports/orders?location_code={loc_code}&period=day", headers=headers)
            assert r.status_code == 200, r.text
            data = r.json()
            print("granularity:", data.get("granularity"))
            print("pattern:", data.get("pattern"))
            buckets = {p["bucket"]: p["count"] for p in (data.get("pattern") or [])}
            assert buckets.get("14:00") == 2, f"Expected 2 at 14:00, got {buckets}"
            assert buckets.get("08:00") == 1, f"Expected 1 at 08:00, got {buckets}"
            assert "00:00" not in buckets, f"00:00 must NOT appear (was the bug), got {buckets}"
            print("✓ hourly buckets read created_at, floored to local DK hour")
    finally:
        await cleanup()
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
