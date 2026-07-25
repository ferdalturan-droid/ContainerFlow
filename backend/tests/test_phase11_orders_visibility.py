"""Fase 11 — Bestillingstidspunkt + vægt/CO2 kun for 'normal' opgavetype +
real-time pre-assignment + claim-isolation.

Krav (2026-06-18):
 - Hver bestilling/tur har: created_at, order_date, capacity_label, tour_type.
 - weight_kg + co2_kg er KUN tilladt for tour_type='normal'. De andre 3
   typer (flyt, vaerksted, afhent_vaerksted) må ALDRIG få vægt/CO2 — selv
   hvis chaufføren prøver at sætte det.
 - Når en chauffør CLAIMET en tur (claimed_by_id), må andre chauffører ikke
   længere se den i deres `/api/tours`-respons.
 - Når admin pre-tildeler en tur (driver_id) er den synlig KUN for den
   pågældende chauffør.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p11_"


async def _cleanup(db):
    for col in ("users", "companies", "co2_types", "container_orders",
                "locations", "plads", "tours", "vehicles", "trailers",
                "delivery_addresses"):
        await db[col].delete_many({"$or": [
            {"email": {"$regex": f"^{PREFIX}"}},
            {"name": {"$regex": f"^{PREFIX}"}},
            {"customer_id": {"$regex": f"^{PREFIX}"}},
            {"location_code": {"$regex": f"^{PREFIX}"}},
            {"code": {"$regex": f"^{PREFIX}"}},
            {"plads": {"$regex": f"^{PREFIX}"}},
            {"number": {"$regex": f"^{PREFIX}"}},
        ]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        # Setup customer + LA company + plads + 2 drivers
        cust = str(uuid.uuid4())
        la_co = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}CA",
             "company_type": "customer", "active": True,
             "serves_company_ids": []},
            {"id": la_co, "name": f"{PREFIX}LogA",
             "company_type": "logistics", "active": True,
             "managed_company_ids": [cust],
             # Vigtig: LA-firmaet's `serves_company_ids` skal indeholde
             # kunden så chauffører i LA kan se kundens ture (jf.
             # _driver_serves_customer i server.py).
             "serves_company_ids": [cust]},
        ])
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        ca_email = f"{PREFIX}ca_{uuid.uuid4().hex[:6]}@x.test"
        la_email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@x.test"
        d1_id = str(uuid.uuid4())
        d2_id = str(uuid.uuid4())
        d1_email = f"{PREFIX}d1_{uuid.uuid4().hex[:6]}@x.test"
        d2_email = f"{PREFIX}d2_{uuid.uuid4().hex[:6]}@x.test"
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": ca_email, "name": f"{PREFIX}CA",
             "password_hash": ph, "role": "customer_admin", "company_id": cust,
             "active": True, "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": la_email, "name": f"{PREFIX}LA",
             "password_hash": ph, "role": "logistics_admin", "company_id": la_co,
             "managed_company_ids": [cust], "active": True,
             "invitation_status": "accepted"},
            {"id": d1_id, "email": d1_email, "name": f"{PREFIX}Driver1",
             "password_hash": ph, "role": "driver", "company_id": la_co,
             "active": True, "invitation_status": "accepted"},
            {"id": d2_id, "email": d2_email, "name": f"{PREFIX}Driver2",
             "password_hash": ph, "role": "driver", "company_id": la_co,
             "active": True, "invitation_status": "accepted"},
        ])
        plads_id = str(uuid.uuid4())
        location_code = f"{PREFIX}LOC1"
        await db.plads.insert_one({
            "id": plads_id, "location_code": location_code,
            "name": f"{PREFIX}LOC1", "company_id": cust, "active": True,
            "materials": ["Træ", "Beton"],
            "material_co2_categories": {},
            "assigned_logistics_company_ids": [la_co],
        })
        # Trailer med kapacitet=3 så D1 kan tage flere ture i testen
        trailer_id = str(uuid.uuid4())
        await db.trailers.insert_one({
            "id": trailer_id, "number": f"{PREFIX}T1",
            "container_capacity": 3, "company_id": la_co, "active": True,
        })
        # D1 har trailer'en valgt — kan tage 4 samtidige ture (capacity+1)
        # Sæt også active_customer_id så driver-tour endpoint kan finde
        # tours fra kunde-virksomheden via partnership-clause.
        await db.users.update_one(
            {"id": d1_id},
            {"$set": {"active_trailer_id": trailer_id, "active_customer_id": cust}},
        )
        await db.users.update_one(
            {"id": d2_id},
            {"$set": {"active_customer_id": cust}},
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async def login(email):
                r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
                return {"Authorization": f"Bearer {r.json()['token']}"}

            ca_h, la_h, d1_h, d2_h = await login(ca_email), await login(la_email), await login(d1_email), await login(d2_email)

            # ─── Test 1: Bestilling lander med created_at + order_date + ──
            #     capacity_label + tour_type
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code,
                "material": "Træ",
                "container_number": "C1",
                "priority": "normal",
                "order_date": "2026-06-20",
                "plads_name": f"{PREFIX}LOC1",
                "tour_type": "vaerksted",
                "workshop_name": "Test Workshop",
                "workshop_address": "Vej 1, 2100 Kbh",
            })
            assert r.status_code == 200, r.text
            order_id_workshop = r.json()["order_id"]
            tour_id_workshop = r.json()["tour_id"]
            assert r.json()["tour_type"] == "vaerksted"
            # Verificer at DB-doc'en har de 4 felter
            doc = await db.container_orders.find_one({"id": order_id_workshop}, {"_id": 0})
            assert doc.get("created_at"), "created_at mangler"
            assert doc.get("order_date") == "2026-06-20"
            assert doc.get("tour_type") == "vaerksted"
            print("✓ 1. Bestilling lander med created_at + order_date + tour_type")

            # ─── Test 2: Værksted-tur har INGEN CO2-snapshot (selv hvis ──
            #     materialet er linked til en CO2-kategori)
            assert doc.get("co2_type_id", "") == "", "Værksted-tur må ikke have CO2-type"
            assert doc.get("co2_kg", 0) == 0
            print("✓ 2. Værksted-bestilling har ingen CO2-snapshot")

            # ─── Test 3: Indsæt CO2-type, sæt på materiale, opret 'normal'──
            #     ordre → CO2 snapshottes automatisk
            r = await ac.post("/api/co2-types", json={"name": "Træ", "factor": 80}, headers=ca_h)
            tree = r.json()
            r = await ac.put(f"/api/locations/{location_code}/materials",
                             json={"old_name": "Træ", "new_name": "Træ", "co2_category_id": tree["id"]},
                             headers=ca_h)
            assert r.status_code == 200
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code,
                "material": "Træ", "container_number": "C2",
                "priority": "normal", "order_date": "2026-06-20",
                "plads_name": f"{PREFIX}LOC1",
                "tour_type": "normal",
            })
            order_id_norm = r.json()["order_id"]
            tour_id_norm = r.json()["tour_id"]
            norm_doc = await db.container_orders.find_one({"id": order_id_norm}, {"_id": 0})
            assert norm_doc.get("co2_type_id") == tree["id"]
            assert norm_doc.get("co2_factor") == 80.0
            print("✓ 3. Normal-bestilling henter CO2 automatisk fra materialet")

            # ─── Test 4: Forsøg at sætte vægt på værksted-ordre via ────
            #     /api/container-orders/{id} → server skal tvinge 0
            r = await ac.put(f"/api/container-orders/{order_id_workshop}",
                             json={"weight_kg": 999}, headers=ca_h)
            assert r.status_code == 200
            assert r.json()["weight_kg"] == 0.0, f"Værksted-tur må aldrig få vægt, got {r.json()['weight_kg']}"
            assert r.json()["co2_kg"] == 0.0
            print("✓ 4. PUT /container-orders blokerer vægt for værksted-tur")

            # ─── Test 5: Sæt vægt på normal-tur via /api/tours/{id} ────
            r = await ac.put(f"/api/tours/{tour_id_norm}",
                             json={"weight": 500.0, "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id},
                             headers=d1_h)
            assert r.status_code == 200, r.text
            # Forventet: ordren mirroreres med 500kg vægt + 40kg CO2 (80*500/1000)
            norm_after = await db.container_orders.find_one({"id": order_id_norm}, {"_id": 0})
            assert norm_after.get("weight_kg") == 500.0
            assert norm_after.get("co2_kg") == 40.0
            print("✓ 5. Normal-tur: vægt+CO2 spejles korrekt til ordren")

            # ─── Test 6: Forsøg at sætte vægt på værksted-tur via /tours ─
            r = await ac.put(f"/api/tours/{tour_id_workshop}",
                             json={"weight": 1234.0, "claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id},
                             headers=d1_h)
            assert r.status_code == 200, r.text
            ws_tour = await db.tours.find_one({"id": tour_id_workshop}, {"_id": 0})
            assert ws_tour.get("weight", 0) == 0, f"Værksted-tur må ikke have weight, got {ws_tour.get('weight')}"
            print("✓ 6. Værksted-tur: vægt tvinges til 0 selv ved direkte PUT")

            # ─── Test 7: Real-time / claim-isolation. Bestil 2 normal-ture──
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code, "material": "Beton",
                "container_number": "C3", "priority": "normal",
                "order_date": "2026-06-20", "plads_name": f"{PREFIX}LOC1",
                "tour_type": "normal",
            })
            tour_open_1 = r.json()["tour_id"]
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code, "material": "Træ",
                "container_number": "C4", "priority": "normal",
                "order_date": "2026-06-20", "plads_name": f"{PREFIX}LOC1",
                "tour_type": "normal",
            })
            tour_open_2 = r.json()["tour_id"]
            # Begge chauffører kan se BÅDE ture (ikke-claimet, ikke-tildelt)
            r1 = await ac.get("/api/tours?date=2026-06-20", headers=d1_h)
            r2 = await ac.get("/api/tours?date=2026-06-20", headers=d2_h)
            ids1 = {t["id"] for t in r1.json()}
            ids2 = {t["id"] for t in r2.json()}
            assert tour_open_1 in ids1 and tour_open_1 in ids2
            assert tour_open_2 in ids1 and tour_open_2 in ids2
            print("✓ 7. Begge chauffører ser åbne ture før claim")

            # ─── Test 8: D1 claimer tour_open_1 → kun D1 ser den ────────
            r = await ac.put(f"/api/tours/{tour_open_1}",
                             json={"claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                                   "on_way": True, "on_way_time": "08:00"},
                             headers=d1_h)
            assert r.status_code == 200, r.text
            r1 = await ac.get("/api/tours?date=2026-06-20", headers=d1_h)
            r2 = await ac.get("/api/tours?date=2026-06-20", headers=d2_h)
            ids1 = {t["id"] for t in r1.json()}
            ids2 = {t["id"] for t in r2.json()}
            assert tour_open_1 in ids1, "D1 mister sin egen claimede tur"
            assert tour_open_1 not in ids2, "D2 ser stadig D1's claimede tur (skal være skjult)"
            print("✓ 8. Claimet tur er KUN synlig for den claimende chauffør")

            # ─── Test 9: LA pre-tildeler tour_open_2 til D2 → D1 mister den
            r = await ac.put(f"/api/tours/{tour_open_2}",
                             json={"driver_id": d2_id}, headers=la_h)
            assert r.status_code == 200, r.text
            r1 = await ac.get("/api/tours?date=2026-06-20", headers=d1_h)
            r2 = await ac.get("/api/tours?date=2026-06-20", headers=d2_h)
            ids1 = {t["id"] for t in r1.json()}
            ids2 = {t["id"] for t in r2.json()}
            assert tour_open_2 not in ids1, "D1 må IKKE se tour pre-tildelt D2"
            assert tour_open_2 in ids2, "D2 skal se tour pre-tildelt sig selv"
            print("✓ 9. Pre-tildelt tur er KUN synlig for den tildelte chauffør")

            # ─── Test 10: D1 kan ikke claime tour_open_2 (pre-tildelt D2) ──
            r = await ac.put(f"/api/tours/{tour_open_2}",
                             json={"claimed_by": f"{PREFIX}Driver1", "claimed_by_id": d1_id,
                                   "on_way": True},
                             headers=d1_h)
            assert r.status_code == 403, f"D1 må ikke claime pre-assigned tour, got {r.status_code}"
            print("✓ 10. Pre-tildelt tur kan ikke claimes af forkert chauffør (403)")

            # ─── Test 11: LA frigiver tour_open_2 → begge ser den igen ──
            r = await ac.put(f"/api/tours/{tour_open_2}",
                             json={"driver_id": ""}, headers=la_h)
            assert r.status_code == 200, r.text
            r1 = await ac.get("/api/tours?date=2026-06-20", headers=d1_h)
            r2 = await ac.get("/api/tours?date=2026-06-20", headers=d2_h)
            ids1 = {t["id"] for t in r1.json()}
            ids2 = {t["id"] for t in r2.json()}
            assert tour_open_2 in ids1 and tour_open_2 in ids2
            print("✓ 11. Frigivet tour er åben igen for alle chauffører")

            # ─── Test 12: Skift tour_type fra 'normal' til 'flyt' nulstiller
            #     vægt+CO2 (ingen dataforurening)
            r = await ac.put(f"/api/container-orders/{order_id_norm}",
                             json={"tour_type": "flyt"}, headers=ca_h)
            assert r.status_code == 200
            ordr = await db.container_orders.find_one({"id": order_id_norm}, {"_id": 0})
            assert ordr.get("weight_kg") == 0
            assert ordr.get("co2_kg") == 0
            assert ordr.get("co2_type_id", "") == ""
            print("✓ 12. Skift til ikke-normal opgavetype nulstiller vægt+CO2")

        print()
        print("═══════════════════════════════════════════════════")
        print(" ✅ Fase 11 — Bestillingstidspunkt + tur-type-regler: 12/12")
        print("    + claim-isolation + pre-tildelings-synlighed")
        print("═══════════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
