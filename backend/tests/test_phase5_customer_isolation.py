"""Fase 5 regression test — Multi-kunde isolation på chauffør-siden (SIKKERHED).

Critical security test cases:
1. Driver must pick an active customer before seeing any tours/plads.
2. Setting active_customer_id to a non-served customer is blocked (403).
3. Tours from Customer B are NEVER visible to driver when active customer = Customer A.
4. Plads from Customer B are NEVER visible to driver when active customer = Customer A.
5. Active customer switching cleanly swaps the data view (no residual A-data in B-view).
6. Real-time tour-status mirror still works (Fase 5 kerne — driver completes → customer sees it).

Uses ephemeral `_pytest_p5_` prefix.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p5_"


async def _cleanup(db):
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    await db.tours.delete_many({"facility": {"$regex": f"^{PREFIX}"}})
    await db.container_orders.delete_many({"customer_name": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        cust_a = str(uuid.uuid4())
        cust_b = str(uuid.uuid4())
        cust_c_forbidden = str(uuid.uuid4())
        log_id = str(uuid.uuid4())  # serves A and B only — NOT C
        await db.companies.insert_many([
            {"id": cust_a, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}A_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": cust_b, "name": f"{PREFIX}CustB", "customer_id": f"{PREFIX}B_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": cust_c_forbidden, "name": f"{PREFIX}CustC", "customer_id": f"{PREFIX}C_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_id, "name": f"{PREFIX}LogX", "customer_id": f"{PREFIX}L_{uuid.uuid4().hex[:4]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_a, cust_b]},
        ])

        # Plads + tours for each customer
        plads_a_id = str(uuid.uuid4())
        plads_b_id = str(uuid.uuid4())
        plads_c_id = str(uuid.uuid4())
        await db.plads.insert_many([
            {"id": plads_a_id, "name": f"{PREFIX}PladsA", "location_code": f"{PREFIX}A1",
             "active": True, "company_id": cust_a, "assigned_logistics_company_ids": [log_id]},
            {"id": plads_b_id, "name": f"{PREFIX}PladsB", "location_code": f"{PREFIX}B1",
             "active": True, "company_id": cust_b, "assigned_logistics_company_ids": [log_id]},
            {"id": plads_c_id, "name": f"{PREFIX}PladsC", "location_code": f"{PREFIX}C1",
             "active": True, "company_id": cust_c_forbidden, "assigned_logistics_company_ids": []},
        ])
        tour_a_id = str(uuid.uuid4())
        tour_b_id = str(uuid.uuid4())
        tour_c_id = str(uuid.uuid4())
        common_tour = {
            "claimed_by": "", "claimed_by_id": "", "active": True,
            "completed": False, "on_way": False, "sort_order": 0,
            "source": "manual", "is_pause": False, "is_private": False,
        }
        await db.tours.insert_many([
            {"id": tour_a_id, "date": "2026-06-17", "fraction": "Pap",
             "facility": f"{PREFIX}PladsA", "address": "Test A",
             "company_id": cust_a, "assigned_logistics_company_ids": [log_id], **common_tour},
            {"id": tour_b_id, "date": "2026-06-17", "fraction": "Glas",
             "facility": f"{PREFIX}PladsB", "address": "Test B",
             "company_id": cust_b, "assigned_logistics_company_ids": [log_id], **common_tour},
            {"id": tour_c_id, "date": "2026-06-17", "fraction": "Træ",
             "facility": f"{PREFIX}PladsC", "address": "Test C",
             "company_id": cust_c_forbidden, "assigned_logistics_company_ids": [],
             **common_tour},
        ])

        # Driver in LogX
        drv_email = f"{PREFIX}drv_{uuid.uuid4().hex[:6]}@x.test"
        pw = "TestPass2026!"
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": drv_email, "name": "Test Driver",
            "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
            "role": "driver", "company_id": log_id,
            "active": True, "invitation_status": "accepted",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/api/auth/login", json={"email": drv_email, "password": pw})
            assert r.status_code == 200
            tok = r.json().get("token") or r.json().get("access_token")
            hdr = {"Authorization": f"Bearer {tok}"}

            # ──── 1. Liste over kunder driveren må vælge ────
            r = await ac.get("/api/driver/customers", headers=hdr)
            assert r.status_code == 200
            custs = r.json()
            ids = sorted(c["id"] for c in custs)
            assert sorted([cust_a, cust_b]) == ids, f"Expected only A + B served, got {ids}"
            assert cust_c_forbidden not in ids
            print(f"✓ /api/driver/customers returns kun servered kunder (A + B), ikke C")

            # ──── 2. Inden active customer er valgt: tours + plads = TOM liste ────
            r = await ac.get("/api/tours?date=2026-06-17", headers=hdr)
            assert r.status_code == 200
            assert r.json() == [], "Driver uden active customer skal få tom liste"
            r = await ac.get("/api/plads", headers=hdr)
            assert r.status_code == 200
            assert r.json() == []
            print("✓ Driver uden active customer → tom tours + tom plads")

            # ──── 3. Forsøg på at vælge ikke-served kunde → 403 ────
            r = await ac.post("/api/driver/active-customer",
                              json={"customer_id": cust_c_forbidden}, headers=hdr)
            assert r.status_code == 403, f"Setting non-served customer must 403, got {r.status_code}"
            print("✓ POST /api/driver/active-customer afviser ikke-served kunde (403)")

            # ──── 4. Vælg kunde A — kun tours/plads fra A vises ────
            r = await ac.post("/api/driver/active-customer",
                              json={"customer_id": cust_a}, headers=hdr)
            assert r.status_code == 200
            assert r.json()["customer_id"] == cust_a

            r = await ac.get("/api/tours?date=2026-06-17", headers=hdr)
            assert r.status_code == 200
            tour_ids = sorted(t["id"] for t in r.json())
            assert tour_ids == [tour_a_id], f"Driver med active=A skal kun se A's tours, fik {tour_ids}"
            r = await ac.get("/api/plads", headers=hdr)
            assert r.status_code == 200
            plads_ids = sorted(p["id"] for p in r.json())
            assert plads_ids == [plads_a_id], f"Driver med active=A skal kun se A's plads, fik {plads_ids}"
            print("✓ Active=A → kun A's tours + A's plads, NUL leakage")

            # ──── 5. Skift til kunde B — komplet data-swap ────
            r = await ac.post("/api/driver/active-customer",
                              json={"customer_id": cust_b}, headers=hdr)
            assert r.status_code == 200
            r = await ac.get("/api/tours?date=2026-06-17", headers=hdr)
            tour_ids = sorted(t["id"] for t in r.json())
            assert tour_ids == [tour_b_id], f"Switch til B → kun B's tours, fik {tour_ids}"
            assert tour_a_id not in tour_ids, "A's data MUST be gone after switch"
            r = await ac.get("/api/plads", headers=hdr)
            plads_ids = sorted(p["id"] for p in r.json())
            assert plads_ids == [plads_b_id]
            print("✓ Switch active customer fra A til B → komplet view-swap (ingen A-rester)")

            # ──── 6. Real-time mirror: driver markerer tour completed → ordre opdateres ────
            # Setup: opret container_order linked to tour_b
            order_id = str(uuid.uuid4())
            await db.container_orders.insert_one({
                "id": order_id, "company_id": cust_b, "location_code": f"{PREFIX}B1",
                "material": "Glas", "customer_name": f"{PREFIX}MirrorOrder",
                "status_label": "afventer", "status": "pending",
                "completed": False, "on_way": False, "claimed_by": "",
                "priority": "normal", "tour_type": "normal",
                "order_date": "2026-06-17",
            })
            await db.tours.update_one(
                {"id": tour_b_id}, {"$set": {"order_id": order_id, "claimed_by": "Test Driver"}}
            )
            # Driver completes the tour
            r = await ac.put(f"/api/tours/{tour_b_id}",
                             json={"completed": True, "weight": 1500, "claimed_by": "Test Driver"},
                             headers=hdr)
            assert r.status_code == 200, r.text
            # Verify mirror to container_orders
            updated_order = await db.container_orders.find_one({"id": order_id}, {"_id": 0})
            assert updated_order.get("completed") is True, f"Order completed should be True: {updated_order}"
            assert updated_order.get("status") == "completed"
            print("✓ Real-time mirror: driver completed → container_order.completed=True")

            # ──── 7. Clear active customer ────
            r = await ac.post("/api/driver/active-customer",
                              json={"customer_id": None}, headers=hdr)
            assert r.status_code == 200
            r = await ac.get("/api/tours?date=2026-06-17", headers=hdr)
            assert r.json() == []
            print("✓ Clearing active customer → tom tour-liste igen")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 5 — Multi-kunde isolation: 7/7 sikkerhedstests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
