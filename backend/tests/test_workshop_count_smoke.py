"""Smoke test: workshop_count counts ONLY tour_type='vaerksted', NOT 'afhent_vaerksted'."""
import os
import sys
import uuid
import bcrypt
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_smoke_workshop_"


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
        loc_code = f"{PREFIX}7711"
        email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@example.test"
        password = "TestPass2026!"

        await db.companies.insert_one({
            "id": company_id, "name": f"{PREFIX}Co", "customer_id": f"{PREFIX}{uuid.uuid4().hex[:6]}",
            "company_type": "customer", "active": True, "serves_company_ids": [],
            "haster_fee": 200, "from_library": False, "slug": "",
        })
        await db.users.insert_one({
            "id": la_id, "email": email, "name": "Smoke LA WS",
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
        # Seed: 2 vaerksted, 3 afhent_vaerksted, 1 normal → workshop_count must be 2
        from datetime import date
        today = date.today().isoformat()
        for tt in ["vaerksted", "vaerksted", "afhent_vaerksted", "afhent_vaerksted", "afhent_vaerksted", "normal"]:
            await db.container_orders.insert_one({
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "location_code": loc_code,
                "material": "Pap",
                "order_date": today,
                "priority": "normal",
                "status": "pending",
                "status_label": "afventer",
                "tour_type": tt,
            })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/api/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, r.text
            token = r.json().get("token") or r.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(f"/api/org/reports/orders?location_code={loc_code}&period=year", headers=headers)
            assert r.status_code == 200, r.text
            data = r.json()
            print(f"total_orders: {data.get('total_orders')}, workshop_count: {data.get('workshop_count')}")
            assert data.get("total_orders") == 6
            assert data.get("workshop_count") == 2, f"Expected 2 (only 'vaerksted'), got {data.get('workshop_count')}"
            print("✓ workshop_count counts only 'vaerksted', not 'afhent_vaerksted'")
    finally:
        await cleanup()
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
