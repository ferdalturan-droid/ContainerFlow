"""Fase 12 — Driver UI tweaks + manuel tidsregistrering backend.

Krav (2026-06-18):
 - POST /api/driver/time-entries opretter/opdaterer en dag-niveau-post med
   start_time, end_time, beregnet duration_minutes, reason.
 - Idempotent: én post pr. (driver_id, date). Ny POST samme dato → update.
 - Duration overnight håndteres korrekt.
 - GET /api/driver/time-entries returnerer kun egen drivers entries.
 - Tour-fetch UDEN source-filter returnerer ALLE kilder (manuel, argo,
   customer_order) — bekræfter at Planlægning kan vise alle bestillinger.
 - Capacity-validering på admin-side (pre-assignment via driver_id) er IKKE
   påvirket af antal aktive ture — admin må tildele ubegrænset.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p12_"


async def _cleanup(db):
    for col in ("users", "companies", "co2_types", "container_orders",
                "locations", "plads", "tours", "vehicles", "trailers",
                "driver_time_entries", "delivery_addresses"):
        await db[col].delete_many({"$or": [
            {"email": {"$regex": f"^{PREFIX}"}},
            {"name": {"$regex": f"^{PREFIX}"}},
            {"customer_id": {"$regex": f"^{PREFIX}"}},
            {"location_code": {"$regex": f"^{PREFIX}"}},
            {"code": {"$regex": f"^{PREFIX}"}},
            {"plads": {"$regex": f"^{PREFIX}"}},
            {"number": {"$regex": f"^{PREFIX}"}},
            {"driver_name": {"$regex": f"^{PREFIX}"}},
        ]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        cust = str(uuid.uuid4())
        la_co = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}CA",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": la_co, "name": f"{PREFIX}LogA", "company_type": "logistics",
             "active": True, "serves_company_ids": [cust], "managed_company_ids": [cust]},
        ])
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        la_email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@x.test"
        d1_id = str(uuid.uuid4())
        d1_email = f"{PREFIX}d1_{uuid.uuid4().hex[:6]}@x.test"
        d2_id = str(uuid.uuid4())
        d2_email = f"{PREFIX}d2_{uuid.uuid4().hex[:6]}@x.test"
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": la_email, "name": f"{PREFIX}LA",
             "password_hash": ph, "role": "logistics_admin", "company_id": la_co,
             "managed_company_ids": [cust], "active": True, "invitation_status": "accepted"},
            {"id": d1_id, "email": d1_email, "name": f"{PREFIX}Driver1",
             "password_hash": ph, "role": "driver", "company_id": la_co,
             "active": True, "invitation_status": "accepted",
             "active_customer_id": cust},
            {"id": d2_id, "email": d2_email, "name": f"{PREFIX}Driver2",
             "password_hash": ph, "role": "driver", "company_id": la_co,
             "active": True, "invitation_status": "accepted"},
        ])
        plads_id = str(uuid.uuid4())
        location_code = f"{PREFIX}LOC1"
        await db.plads.insert_one({
            "id": plads_id, "location_code": location_code,
            "name": f"{PREFIX}LOC1", "company_id": cust, "active": True,
            "materials": ["Træ"],
            "material_co2_categories": {},
            "assigned_logistics_company_ids": [la_co],
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async def login(email):
                r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
                return {"Authorization": f"Bearer {r.json()['token']}"}
            la_h, d1_h, d2_h = await login(la_email), await login(d1_email), await login(d2_email)

            # ─── Test 1: Driver opretter manuel tidsregistrering ──
            r = await ac.post("/api/driver/time-entries", json={
                "date": "2026-06-18",
                "start_time": "07:00",
                "end_time": "15:30",
                "reason": "Glemte at stemple ind",
            }, headers=d1_h)
            assert r.status_code == 200, r.text
            entry = r.json()
            assert entry["duration_minutes"] == 510  # 8.5 timer = 510 min
            assert entry["driver_id"] == d1_id
            print(f"✓ 1. POST /driver/time-entries opretter post (510 min)")

            # ─── Test 2: Idempotent — POST samme dato igen → update ──
            r = await ac.post("/api/driver/time-entries", json={
                "date": "2026-06-18",
                "start_time": "07:30",
                "end_time": "16:00",
                "reason": "Korrigeret",
            }, headers=d1_h)
            assert r.status_code == 200
            entry2 = r.json()
            assert entry2["id"] == entry["id"], "Samme post-id forventes"
            assert entry2["duration_minutes"] == 510  # 7:30-16:00 = 8.5t
            assert entry2["reason"] == "Korrigeret"
            # Verificér i DB: kun 1 post for (driver, date)
            count = await db.driver_time_entries.count_documents(
                {"driver_id": d1_id, "date": "2026-06-18"})
            assert count == 1, f"Forventede 1 post, fandt {count}"
            print(f"✓ 2. POST samme dato → opdaterer eksisterende (ingen duplikater)")

            # ─── Test 3: Overnight (over midnat) duration ──────────
            r = await ac.post("/api/driver/time-entries", json={
                "date": "2026-06-19",
                "start_time": "22:00",
                "end_time": "02:00",
                "reason": "Nat-tur",
            }, headers=d1_h)
            assert r.status_code == 200, r.text
            assert r.json()["duration_minutes"] == 240  # 4 timer
            print(f"✓ 3. Overnight beregning (22:00→02:00 = 240 min)")

            # ─── Test 4: Ugyldigt input afvises ────────────────────
            r = await ac.post("/api/driver/time-entries", json={
                "date": "", "start_time": "07:00", "end_time": "10:00",
            }, headers=d1_h)
            assert r.status_code == 400
            r = await ac.post("/api/driver/time-entries", json={
                "date": "2026-06-20", "start_time": "10:00", "end_time": "10:00",
            }, headers=d1_h)
            assert r.status_code == 400, "Samme start+slut skal afvises"
            print(f"✓ 4. Ugyldigt input afvises (400)")

            # ─── Test 5: GET /driver/time-entries returnerer kun egne ─
            r = await ac.get("/api/driver/time-entries", headers=d1_h)
            assert r.status_code == 200
            entries = r.json()
            assert len(entries) == 2  # 2026-06-18 + 2026-06-19
            assert all(e["driver_id"] == d1_id for e in entries)
            # D2 ser ingen
            r = await ac.get("/api/driver/time-entries", headers=d2_h)
            assert r.status_code == 200
            assert r.json() == []
            print(f"✓ 5. GET /driver/time-entries returnerer kun egen drivers entries")

            # ─── Test 6: Customer order opretter en tur som SKAL vises ──
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code, "material": "Træ",
                "container_number": "C1", "priority": "normal",
                "order_date": "2026-06-20", "plads_name": f"{PREFIX}LOC1",
                "tour_type": "normal",
            })
            assert r.status_code == 200
            customer_tour_id = r.json()["tour_id"]
            # Hent ture UDEN source-filter (Planlægning-fetch) — skal indeholde tour'en
            r = await ac.get("/api/tours?date=2026-06-20", headers=la_h)
            assert r.status_code == 200
            ids = {t["id"] for t in r.json()}
            assert customer_tour_id in ids, "Customer-order tour skal være synlig i Planlægning"
            # Hent med source=manual,argo — customer-order MÅ IKKE være med
            r = await ac.get("/api/tours?date=2026-06-20&source=manual,argo", headers=la_h)
            ids_filtered = {t["id"] for t in r.json()}
            assert customer_tour_id not in ids_filtered
            print(f"✓ 6. /api/tours uden source-filter inkluderer customer_order ture")

            # ─── Test 7: Admin pre-tildeler ubegrænset ──────────────
            # Opret 5 ture og pre-tildel alle 5 til D1 — admin må gerne uanset kapacitet
            tour_ids = [customer_tour_id]
            for i in range(4):
                r = await ac.post("/api/customer-orders/submit", json={
                    "location_code": location_code, "material": "Træ",
                    "container_number": f"C{i+2}", "priority": "normal",
                    "order_date": "2026-06-20", "plads_name": f"{PREFIX}LOC1",
                    "tour_type": "normal",
                })
                tour_ids.append(r.json()["tour_id"])
            for tid in tour_ids:
                r = await ac.put(f"/api/tours/{tid}", json={"driver_id": d1_id}, headers=la_h)
                assert r.status_code == 200, f"Admin pre-tildeling fejlede for {tid}: {r.text}"
            assigned = await db.tours.count_documents(
                {"driver_id": d1_id, "date": "2026-06-20"})
            assert assigned == 5, f"Forventede 5 pre-tildelte ture, fandt {assigned}"
            print(f"✓ 7. Admin kan pre-tildele 5 ture til D1 uden kapacitets-blokering")

            # ─── Test 8: Driver-side claim VALIDERER kapacitet ─────
            # D1 har ingen hænger valgt → max 1 active tour
            r = await ac.put(f"/api/tours/{tour_ids[0]}", json={
                "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                "on_way": True,
            }, headers=d1_h)
            assert r.status_code == 200, r.text
            # Forsøg claim af tur 2 → blokeret (409)
            r = await ac.put(f"/api/tours/{tour_ids[1]}", json={
                "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                "on_way": True,
            }, headers=d1_h)
            assert r.status_code == 409, f"D1 må kun have 1 aktiv tur uden hænger, got {r.status_code}"
            assert "hænger" in r.json()["detail"].lower()
            print(f"✓ 8. Driver-side claim VALIDERER kapacitet (D1 uden hænger blokeres på 2. claim)")

            # ─── Test 9: Med hænger kan D1 claime flere ────────────
            trailer_id = str(uuid.uuid4())
            await db.trailers.insert_one({
                "id": trailer_id, "number": f"{PREFIX}T1",
                "container_capacity": 2, "company_id": la_co, "active": True,
            })
            await db.users.update_one(
                {"id": d1_id}, {"$set": {"active_trailer_id": trailer_id}})
            # Med capacity=2 + 1 = 3 samtidige ture. D1 har allerede 1 claimet.
            r = await ac.put(f"/api/tours/{tour_ids[1]}", json={
                "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                "on_way": True,
            }, headers=d1_h)
            assert r.status_code == 200, r.text
            r = await ac.put(f"/api/tours/{tour_ids[2]}", json={
                "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                "on_way": True,
            }, headers=d1_h)
            assert r.status_code == 200, r.text
            # 4. claim → blokeret (3+1 = max, current=3)
            r = await ac.put(f"/api/tours/{tour_ids[3]}", json={
                "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                "on_way": True,
            }, headers=d1_h)
            assert r.status_code == 409, f"Forventede 409 efter 3 active, got {r.status_code}"
            assert "max 3" in r.json()["detail"].lower(), r.json()
            print(f"✓ 9. Hænger (cap=2) → max 3 samtidige ture for chauffør ({r.json()['detail']})")

        print()
        print("═══════════════════════════════════════════════════")
        print(" ✅ Fase 12 — Manuel tidsregistrering + kapacitets-flow: 9/9")
        print("    + admin pre-tildeling uden grænse")
        print("    + driver-side hard-stop ved hænger-kapacitet+1")
        print("═══════════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
