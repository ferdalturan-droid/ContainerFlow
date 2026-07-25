"""Fase 4 regression test — Tour source-separation.

Verifies:
1. Manuelle ture (POST /api/tours) får source="manual" som default.
2. Customer-orders → tour får source="customer_order".
3. GET /api/tours?source=manual filtrerer korrekt.
4. GET /api/tours?source=customer_order filtrerer korrekt.
5. GET /api/tours?source=manual,argo (CSV) returnerer både manual + argo.

Uses ephemeral `_pytest_p4_` prefix; cleans up after.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p4_"


async def _cleanup(db):
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    await db.tours.delete_many({"$or": [{"facility": {"$regex": f"^{PREFIX}"}}, {"address": {"$regex": f"^{PREFIX}"}}]})
    await db.container_orders.delete_many({"$or": [{"location_code": {"$regex": f"^{PREFIX}"}}, {"customer_name": {"$regex": f"^{PREFIX}"}}]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)

    try:
        cust_id = str(uuid.uuid4())
        log_id = str(uuid.uuid4())
        loc_code = f"{PREFIX}_4242"
        await db.companies.insert_many([
            {"id": cust_id, "name": f"{PREFIX}Customer", "customer_id": f"{PREFIX}c_{uuid.uuid4().hex[:6]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_id, "name": f"{PREFIX}Logistics", "customer_id": f"{PREFIX}l_{uuid.uuid4().hex[:6]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_id]},
        ])
        await db.plads.insert_one({
            "id": str(uuid.uuid4()), "name": f"{PREFIX}Plads", "location_code": loc_code,
            "city": "X", "active": True, "company_id": cust_id,
            "assigned_logistics_company_ids": [log_id],
            "materials": ["Pap"], "containers_per_material": 3,
        })

        la_email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@x.test"
        emp_email = f"{PREFIX}emp_{uuid.uuid4().hex[:6]}@x.test"
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": la_email, "name": "LA",
             "password_hash": ph, "role": "logistics_admin", "company_id": log_id,
             "active": True, "invitation_status": "accepted", "managed_company_ids": []},
            {"id": str(uuid.uuid4()), "email": emp_email, "name": "Emp",
             "password_hash": ph, "role": "order", "company_id": cust_id,
             "active": True, "invitation_status": "accepted",
             "location_code": loc_code, "assigned_plads_ids": [loc_code]},
        ])

        async def login(ac, email):
            r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            return r.json().get("token") or r.json().get("access_token")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            la_t = await login(ac, la_email)
            emp_t = await login(ac, emp_email)

            # ──── 1. Manuel tour via POST /api/tours → source=manual ────
            r = await ac.post("/api/tours", json={
                "fraction": "Pap", "facility": f"{PREFIX}Manual",
                "address": f"{PREFIX} Manual addr",
                "plads": f"{PREFIX}Plads",
            }, headers={"Authorization": f"Bearer {la_t}"})
            assert r.status_code == 200, r.text
            manual_tour = r.json()
            assert manual_tour.get("source") == "manual", f"Expected source=manual, got {manual_tour.get('source')}"
            manual_id = manual_tour["id"]
            print(f"✓ Manuel tour oprettet med source=manual (id={manual_id[:8]}…)")

            # ──── 2. Customer order → tour med source=customer_order ────
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": loc_code,
                "material": "Pap",
                "container_number": "C1",
                "customer_name": f"{PREFIX}CustOrder",
                "customer_phone": "12345678",
                "address": "Test 1",
                "custom_address": "Pytest Vej 1, 3000 Helsingør",
                "comment": "via pytest",
                "priority": "normal",
            }, headers={"Authorization": f"Bearer {emp_t}"})
            assert r.status_code == 200, r.text
            order_resp = r.json()
            order_tour_id = order_resp["tour_id"]
            # Verify the tour's source in DB
            t = await db.tours.find_one({"id": order_tour_id}, {"_id": 0})
            assert t.get("source") == "customer_order", f"Expected source=customer_order, got {t.get('source')}"
            print(f"✓ Customer order opretter tour med source=customer_order (id={order_tour_id[:8]}…)")

            # ──── 3. Insert an "argo" tour directly for filter test ────
            argo_tour_id = str(uuid.uuid4())
            await db.tours.insert_one({
                "id": argo_tour_id, "date": "2026-06-16", "container": "",
                "fraction": "Træ", "facility": f"{PREFIX}Argo", "address": f"{PREFIX} Argo addr",
                "company_id": log_id, "source": "argo",
                "assigned_logistics_company_ids": [log_id],
                "claimed_by": "", "claimed_by_id": "",
                "active": True, "completed": False, "on_way": False,
                "sort_order": 0,
            })

            # ──── 4. Filter source=manual ────
            r = await ac.get("/api/tours?source=manual", headers={"Authorization": f"Bearer {la_t}"})
            assert r.status_code == 200
            tours = r.json()
            tour_ids = [t["id"] for t in tours]
            assert manual_id in tour_ids, "Manual tour skal være i source=manual filter"
            assert argo_tour_id not in tour_ids, "Argo tour skal IKKE være i source=manual"
            assert order_tour_id not in tour_ids, "Customer-order tour skal IKKE være i source=manual"
            print(f"✓ Filter ?source=manual virker (returnerede {len(tours)} ture)")

            # ──── 5. Filter source=customer_order ────
            r = await ac.get("/api/tours?source=customer_order", headers={"Authorization": f"Bearer {la_t}"})
            assert r.status_code == 200
            tour_ids = [t["id"] for t in r.json()]
            assert order_tour_id in tour_ids
            assert manual_id not in tour_ids
            assert argo_tour_id not in tour_ids
            print("✓ Filter ?source=customer_order virker")

            # ──── 6. CSV filter source=manual,argo ────
            r = await ac.get("/api/tours?source=manual,argo", headers={"Authorization": f"Bearer {la_t}"})
            assert r.status_code == 200
            tour_ids = [t["id"] for t in r.json()]
            assert manual_id in tour_ids
            assert argo_tour_id in tour_ids
            assert order_tour_id not in tour_ids
            print("✓ Filter ?source=manual,argo (CSV) returnerer både manual + argo")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 4 — Alle tour-source tests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
