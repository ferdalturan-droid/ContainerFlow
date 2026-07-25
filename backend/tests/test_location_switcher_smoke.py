"""Smoke test: confirm /api/plads returns multi-location list for an order-user
   with multiple assigned_plads_ids — what powers the new Lokation-switcher."""
import os, sys, uuid, bcrypt, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_smoke_locsw_"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    async def cleanup():
        await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
        await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
        await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})

    await cleanup()
    try:
        company_id = str(uuid.uuid4())
        # 3 plads: emp has access to 2 of them (multi-loc), 1 forbidden
        codes = [f"{PREFIX}A", f"{PREFIX}B", f"{PREFIX}C_forbidden"]
        await db.companies.insert_one({
            "id": company_id, "name": f"{PREFIX}Co", "customer_id": f"{PREFIX}cust",
            "company_type": "customer", "active": True, "serves_company_ids": [],
            "haster_fee": 200, "from_library": False, "slug": "",
        })
        for c in codes:
            await db.plads.insert_one({
                "id": str(uuid.uuid4()), "company_id": company_id,
                "location_code": c, "name": f"{PREFIX}Plads {c[-1]}",
                "city": "Helsingør", "active": True,
            })
        emp_id = str(uuid.uuid4())
        email = f"{PREFIX}emp_{uuid.uuid4().hex[:6]}@example.test"
        password = "TestPass2026!"
        await db.users.insert_one({
            "id": emp_id, "email": email, "name": "Multi Loc Emp",
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "role": "order", "company_id": company_id, "active": True,
            "managed_company_ids": [], "invitation_status": "accepted",
            "location_code": codes[0],
            "assigned_plads_ids": [codes[0], codes[1]],  # NOT C
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/api/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, r.text
            token = r.json().get("token") or r.json().get("access_token")
            r = await ac.get("/api/plads", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            plads = r.json()
            returned_codes = sorted([p.get("location_code") for p in plads])
            print("Returned plads codes:", returned_codes)
            assert codes[0] in returned_codes
            assert codes[1] in returned_codes
            assert codes[2] not in returned_codes, "Forbidden plads must NOT leak"
            print("✓ /api/plads correctly filters to assigned_plads_ids — switcher list is secure")
    finally:
        await cleanup()
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
