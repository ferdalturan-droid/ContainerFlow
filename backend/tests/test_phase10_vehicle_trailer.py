"""Fase 10 — Vognnummer + Hænger flåde-administration.

1.  LA opretter Vehicle/Trailer for sin logistik-virksomhed
2.  Vognnummer auto-uppercase + duplikat-blokering (409)
3.  Trailer.container_capacity validation (>=1)
4.  Driver kan læse listerne (men ikke skrive)
5.  Cross-LA isolation: LA-Y ser ikke LA-X's vehicles/trailers
6.  Driver sætter active_vehicle_id + active_trailer_id
7.  Simultan-tur limit: 0 trailer → max 1 aktiv tur
8.  Trailer capacity=1 → max 2 aktive ture
9.  Trailer capacity=2 → max 3 aktive ture
10. Forsøg på 2. claim uden trailer → 409 med trailer-hint
11. Færdige ture tæller ikke
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p10_"


async def _cleanup(db):
    for col in ("users", "companies", "vehicles", "trailers", "tours", "plads"):
        await db[col].delete_many({"$or": [
            {"email": {"$regex": f"^{PREFIX}"}},
            {"name": {"$regex": f"^{PREFIX}"}},
            {"customer_id": {"$regex": f"^{PREFIX}"}},
            {"number": {"$regex": f"^{PREFIX}"}},
            {"facility": {"$regex": f"^{PREFIX}"}},
        ]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        log_x, log_y, cust = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": log_x, "name": f"{PREFIX}LogX", "customer_id": f"{PREFIX}LX",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust]},
            {"id": log_y, "name": f"{PREFIX}LogY", "customer_id": f"{PREFIX}LY",
             "company_type": "logistics", "active": True, "serves_company_ids": []},
            {"id": cust,  "name": f"{PREFIX}Cust", "customer_id": f"{PREFIX}CC",
             "company_type": "customer",  "active": True, "serves_company_ids": []},
        ])

        plads_id = str(uuid.uuid4())
        await db.plads.insert_one({
            "id": plads_id, "name": f"{PREFIX}Plads", "company_id": cust,
            "assigned_logistics_company_ids": [log_x], "active": True,
        })

        pw, ph = "TestPass2026!", bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()
        la_x_email = f"{PREFIX}la_x_{uuid.uuid4().hex[:6]}@x.test"
        la_y_email = f"{PREFIX}la_y_{uuid.uuid4().hex[:6]}@x.test"
        drv_id = str(uuid.uuid4())
        drv_email = f"{PREFIX}drv_{uuid.uuid4().hex[:6]}@x.test"
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": la_x_email, "name": "LA-X", "password_hash": ph,
             "role": "logistics_admin", "company_id": log_x, "active": True, "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": la_y_email, "name": "LA-Y", "password_hash": ph,
             "role": "logistics_admin", "company_id": log_y, "active": True, "invitation_status": "accepted"},
            {"id": drv_id, "email": drv_email, "name": "DrvX", "password_hash": ph,
             "role": "driver", "company_id": log_x, "active_customer_id": cust,
             "active": True, "invitation_status": "accepted"},
        ])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async def login(email):
                r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
                return {"Authorization": f"Bearer {r.json()['token']}"}

            la_x_h, la_y_h, drv_h = await login(la_x_email), await login(la_y_email), await login(drv_email)

            # ──── 1. LA-X opretter vognnummer ────
            r = await ac.post("/api/vehicles", json={"number": "ab 12 345"}, headers=la_x_h)
            assert r.status_code == 200, r.text
            v1 = r.json()
            assert v1["number"] == "AB 12 345", f"Auto-uppercase, got {v1['number']}"
            print(f"✓  1. LA-X opretter vogn (auto-uppercase): {v1['number']}")

            # ──── 2. Duplikat blokering ────
            r = await ac.post("/api/vehicles", json={"number": "AB 12 345"}, headers=la_x_h)
            assert r.status_code == 409, f"Duplikat skal 409, got {r.status_code}"
            print(f"✓  2. Duplikat vognnummer afvist (409)")

            # ──── 3. Trailer capacity validation ────
            r = await ac.post("/api/trailers", json={"number": "TR-1", "container_capacity": 0}, headers=la_x_h)
            assert r.status_code == 400, f"capacity=0 afvises, got {r.status_code}"
            r = await ac.post("/api/trailers", json={"number": "TR-1", "container_capacity": 1}, headers=la_x_h)
            assert r.status_code == 200, r.text
            tr1 = r.json()
            r = await ac.post("/api/trailers", json={"number": "TR-2", "container_capacity": 2}, headers=la_x_h)
            tr2 = r.json()
            print(f"✓  3. Trailer-validering (capacity>=1) + TR-1(cap=1), TR-2(cap=2) oprettet")

            # ──── 4. LA-Y ser INGEN af LA-X's vehicles/trailers ────
            r = await ac.get("/api/vehicles", headers=la_y_h)
            y_vehicles = [v for v in r.json() if v.get("number", "").startswith("AB ")]
            assert len(y_vehicles) == 0, f"LA-Y må IKKE se LA-X's vogne, got {y_vehicles}"
            r = await ac.get("/api/trailers", headers=la_y_h)
            y_trailers = [t for t in r.json() if t.get("number", "").startswith("TR-")]
            assert len(y_trailers) == 0
            print(f"✓  4. Cross-LA isolation: LA-Y ser ingen af LA-X's flåde")

            # ──── 5. Driver kan læse listerne ────
            r = await ac.get("/api/vehicles", headers=drv_h)
            assert any(v["id"] == v1["id"] for v in r.json())
            r = await ac.get("/api/trailers", headers=drv_h)
            assert any(t["id"] == tr1["id"] for t in r.json())
            print(f"✓  5. Driver kan læse vehicles + trailers")

            # ──── 6. Driver kan IKKE oprette/redigere ────
            r = await ac.post("/api/vehicles", json={"number": "HACK"}, headers=drv_h)
            assert r.status_code == 403
            r = await ac.delete(f"/api/vehicles/{v1['id']}", headers=drv_h)
            assert r.status_code == 403
            print(f"✓  6. Driver blokeret fra at oprette/slette flåde (403)")

            # ──── 7. Driver sætter active_vehicle + ingen trailer ────
            r = await ac.post("/api/driver/active-vehicle-trailer",
                              json={"active_vehicle_id": v1["id"], "active_trailer_id": ""},
                              headers=drv_h)
            assert r.status_code == 200
            print(f"✓  7. Driver vælger vogn (uden hænger)")

            # ──── 8. Simultan-tur limit uden trailer = max 1 ────
            # Opret 3 åbne ture
            tour_ids = []
            for i in range(3):
                tid = str(uuid.uuid4())
                tour_ids.append(tid)
                await db.tours.insert_one({
                    "id": tid, "date": "2026-06-17", "fraction": f"Frac{i}",
                    "facility": f"{PREFIX}Plads", "address": f"Adr{i}",
                    "company_id": cust, "assigned_logistics_company_ids": [log_x],
                    "claimed_by": "", "claimed_by_id": "", "completed": False,
                    "on_way": False, "active": True, "source": "manual",
                    "is_pause": False, "is_private": False, "driver_id": "", "driver_name": "",
                })
            # 1st claim OK
            r = await ac.put(f"/api/tours/{tour_ids[0]}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 200
            # 2nd claim should fail (no trailer)
            r = await ac.put(f"/api/tours/{tour_ids[1]}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 409, f"Uden trailer skal 2. claim afvises, got {r.status_code}: {r.text}"
            assert "hænger" in r.json()["detail"].lower(), r.json()
            print(f"✓  8. Uden hænger: 2. claim afvist (409) med 'vælg hænger'-hint")

            # ──── 9. Vælg TR-1 (cap=1) → max 2 samtidige ture ────
            await ac.post("/api/driver/active-vehicle-trailer",
                          json={"active_trailer_id": tr1["id"]}, headers=drv_h)
            # 2nd claim should now work (1 + 1 = max 2)
            r = await ac.put(f"/api/tours/{tour_ids[1]}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 200, f"Med TR-1 (cap=1) skal 2. claim virke, got {r.status_code}"
            # 3rd claim should fail
            r = await ac.put(f"/api/tours/{tour_ids[2]}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 409, f"TR-1 (cap=1) max 2 ture, 3. afvises, got {r.status_code}"
            assert "max 2 samtidige" in r.json()["detail"].lower(), r.json()
            print(f"✓  9. TR-1 (cap=1): max 2 samtidige; 3. claim afvist (409)")

            # ──── 10. Færdige ture tæller IKKE — skift første til completed ────
            await db.tours.update_one({"id": tour_ids[0]}, {"$set": {"completed": True, "weight": 100}})
            # Nu er kun 1 aktiv tur; vi kan claime den 3.
            r = await ac.put(f"/api/tours/{tour_ids[2]}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 200, f"Færdige ture skal ikke tælle, got {r.status_code}: {r.text}"
            print(f"✓ 10. Færdige ture tæller IKKE — 3. tur claimet efter 1. blev færdig")

            # ──── 11. Skift til TR-2 (cap=2) → max 3 samtidige ────
            # Tilbagestil status: gør tur[0] aktiv igen, så vi har 3 aktive
            await db.tours.update_one({"id": tour_ids[0]},
                                      {"$set": {"completed": False, "claimed_by": "DrvX", "claimed_by_id": drv_id}})
            # Nu er der 3 aktive ture (alle 3). Med TR-2 (cap=2 → max 3) skal det stadig være OK.
            # Opret tur #4 og prøv claim
            tid4 = str(uuid.uuid4())
            await db.tours.insert_one({
                "id": tid4, "date": "2026-06-17", "fraction": "Frac4",
                "facility": f"{PREFIX}Plads", "address": "Adr4",
                "company_id": cust, "assigned_logistics_company_ids": [log_x],
                "claimed_by": "", "claimed_by_id": "", "completed": False,
                "on_way": False, "active": True, "source": "manual",
                "is_pause": False, "is_private": False, "driver_id": "", "driver_name": "",
            })
            await ac.post("/api/driver/active-vehicle-trailer",
                          json={"active_trailer_id": tr2["id"]}, headers=drv_h)
            # 3 aktive allerede; max=3 → 4. afvises
            r = await ac.put(f"/api/tours/{tid4}",
                             json={"claimed_by": "DrvX", "claimed_by_id": drv_id}, headers=drv_h)
            assert r.status_code == 409, f"TR-2 max=3, 4. afvises, got {r.status_code}: {r.text}"
            print(f"✓ 11. TR-2 (cap=2): max 3 samtidige; 4. afvises (409)")

        print()
        print("═══════════════════════════════════════════════════")
        print(" ✅ Fase 10 — Vehicle + Trailer + Simultan-limit: 11/11 tests bestået")
        print("═══════════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
