"""Fase 9 — CO2-beregning på bestillinger (refaktoreret 2026-06-18).

Refactor: CO2-kategori knyttes nu til MATERIALET (i `plads.material_co2_categories`)
i stedet for at brugeren skal vælge typen pr. bestilling. Eksisterende ordrer som
fortsat sender `co2_type_id` bevarer den gamle adfærd (bagudkompatibilitet),
men nye ordrer henter automatisk CO2-faktoren fra materialets kategori.

Sikkerhedstests for CO2-type library (per-kunde) + auto-beregning:

 1. Kunde Admin (CA-A) kan oprette CO2-type i sin egen kunde
 2. Order-user kan LÆSE CO2-types fra sin kunde
 3. Order-user kan IKKE oprette CO2-types (403)
 4. CA-A kan IKKE læse/redigere CA-B's CO2-types (tenant-isolation)
 5. Duplikat-navn inden for samme kunde blokeres (409)
 6. Negativ faktor afvises (400)
 7. CO2-type med faktor=0 er tilladt (jord, beton)
 8. POST /api/locations/{code}/materials accepterer `co2_category_id` og persisterer i plads-doc
 9. PUT /api/locations/{code}/materials kan opdatere co2_category_id på eksisterende materiale
10. Beregningseksempel: Træ-materiale linket til faktor=80, vægt=500kg → co2_kg=40.0
11. Beregningseksempel: Metal-materiale linket til faktor=22, vægt=1200kg → co2_kg=26.4
12. Beregningseksempel: Beton-materiale linket til faktor=0, vægt=3000kg → co2_kg=0.0
13. Sletning blokeres hvis aktive ordrer bruger CO2-type
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p9_"


async def _cleanup(db):
    for col in ("users", "companies", "co2_types", "container_orders",
                "locations", "plads", "delivery_addresses"):
        await db[col].delete_many({"$or": [
            {"email": {"$regex": f"^{PREFIX}"}},
            {"name": {"$regex": f"^{PREFIX}"}},
            {"customer_id": {"$regex": f"^{PREFIX}"}},
            {"location_code": {"$regex": f"^{PREFIX}"}},
            {"code": {"$regex": f"^{PREFIX}"}},
        ]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        cust_a = str(uuid.uuid4())
        cust_b = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust_a, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}CA",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": cust_b, "name": f"{PREFIX}CustB", "customer_id": f"{PREFIX}CB",
             "company_type": "customer", "active": True, "serves_company_ids": []},
        ])

        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        ca_a_email = f"{PREFIX}ca_a_{uuid.uuid4().hex[:6]}@x.test"
        ca_b_email = f"{PREFIX}ca_b_{uuid.uuid4().hex[:6]}@x.test"
        ord_a_email = f"{PREFIX}ord_a_{uuid.uuid4().hex[:6]}@x.test"
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": ca_a_email, "name": "CA-A", "password_hash": ph,
             "role": "customer_admin", "company_id": cust_a, "active": True, "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": ca_b_email, "name": "CA-B", "password_hash": ph,
             "role": "customer_admin", "company_id": cust_b, "active": True, "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": ord_a_email, "name": "OrdA", "password_hash": ph,
             "role": "order", "company_id": cust_a, "location_codes": [f"{PREFIX}AL1"],
             "active": True, "invitation_status": "accepted"},
        ])

        # Opret en plads til cust_a med materialer
        plads_id = str(uuid.uuid4())
        location_code = f"{PREFIX}AL1"
        await db.plads.insert_one({
            "id": plads_id, "location_code": location_code, "name": f"{PREFIX}AL1",
            "company_id": cust_a, "active": True,
            "materials": ["Træ-fraktion", "Metal-fraktion", "Beton-fraktion"],
            "material_co2_categories": {},
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async def login(email):
                r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
                return {"Authorization": f"Bearer {r.json()['token']}"}

            ca_a_h, ca_b_h, ord_a_h = await login(ca_a_email), await login(ca_b_email), await login(ord_a_email)

            # ──── 1. CA-A opretter CO2-type "Træ" faktor=80 ──────────
            r = await ac.post("/api/co2-types", json={"name": "Træ", "factor": 80}, headers=ca_a_h)
            assert r.status_code == 200, r.text
            tree = r.json()
            assert tree["name"] == "Træ" and tree["factor"] == 80 and tree["company_id"] == cust_a
            print(f"✓  1. CA-A opretter Træ faktor=80 → id={tree['id'][:8]}")

            # Opret også Metal og Beton (faktor=0)
            r = await ac.post("/api/co2-types", json={"name": "Metal", "factor": 22}, headers=ca_a_h)
            metal = r.json()
            r = await ac.post("/api/co2-types", json={"name": "Beton", "factor": 0}, headers=ca_a_h)
            assert r.status_code == 200, "Faktor=0 skal være tilladt for jord/beton"
            beton = r.json()
            print(f"✓  2. CA-A opretter Metal (22) + Beton (faktor=0 — tilladt for jord/beton)")

            # ──── 2. Order-user læser CO2-types fra sin kunde ──────────
            r = await ac.get("/api/co2-types", headers=ord_a_h)
            assert r.status_code == 200, r.text
            names = sorted(t["name"] for t in r.json())
            assert names == ["Beton", "Metal", "Træ"], f"Order ser kun cust_a's typer, got {names}"
            print(f"✓  3. Order-user læser {len(r.json())} CO2-typer fra cust_a")

            # ──── 3. Order-user kan IKKE oprette ──────────
            r = await ac.post("/api/co2-types", json={"name": "Hack", "factor": 1}, headers=ord_a_h)
            assert r.status_code == 403, f"Order skal blokeres, got {r.status_code}"
            print(f"✓  4. Order-user blokeret fra at oprette CO2-type (403)")

            # ──── 4. CA-B kan IKKE læse CA-A's typer (tenant isolation) ──────
            r = await ac.get("/api/co2-types", headers=ca_b_h)
            b_names = [t["name"] for t in r.json()]
            assert all(n not in ["Træ", "Metal", "Beton"] for n in b_names), \
                f"CA-B må IKKE se cust_a's typer, got {b_names}"
            print(f"✓  5. CA-B isoleret fra CA-A's CO2-typer ({len(b_names)} egne typer)")

            # ──── 5. Duplikat-navn blokeres ──────────
            r = await ac.post("/api/co2-types", json={"name": "Træ", "factor": 99}, headers=ca_a_h)
            assert r.status_code == 409, f"Duplikat skal 409, got {r.status_code}"
            print(f"✓  6. Duplikat navn 'Træ' i samme kunde blokeres (409)")

            # ──── 6. Negativ faktor afvises ──────────
            r = await ac.post("/api/co2-types", json={"name": "BadType", "factor": -5}, headers=ca_a_h)
            assert r.status_code == 400, f"Negativ faktor skal 400, got {r.status_code}"
            print(f"✓  7. Negativ faktor afvises (400)")

            # ──── 7. CA-B kan IKKE redigere CA-A's type ──────────
            r = await ac.put(f"/api/co2-types/{tree['id']}",
                             json={"factor": 9999}, headers=ca_b_h)
            assert r.status_code == 403, f"Cross-tenant edit skal 403, got {r.status_code}"
            print(f"✓  8. CA-B blokeret fra at redigere CA-A's type (403)")

            # ──── 8. Knyt CO2-kategorier til materialer på pladsen ────
            # Først: POST /materials med nyt materiale + co2_category_id
            r = await ac.post(f"/api/locations/{location_code}/materials",
                              json={"material": "Murbrokker", "co2_category_id": beton["id"]},
                              headers=ca_a_h)
            assert r.status_code == 200, r.text
            assert r.json().get("co2_category_id") == beton["id"]
            print(f"✓  9. POST /materials med co2_category_id (Murbrokker → Beton)")

            # Sæt CO2-kategorier på de eksisterende materialer via PUT (rename = old=new)
            for mat_name, co2_id in [("Træ-fraktion", tree["id"]),
                                     ("Metal-fraktion", metal["id"]),
                                     ("Beton-fraktion", beton["id"])]:
                r = await ac.put(f"/api/locations/{location_code}/materials",
                                 json={"old_name": mat_name, "new_name": mat_name,
                                       "co2_category_id": co2_id},
                                 headers=ca_a_h)
                assert r.status_code == 200, f"PUT {mat_name}: {r.text}"
                assert r.json().get("co2_category_id") == co2_id
            print(f"✓ 10. PUT /materials sætter co2_category_id på eksisterende materialer")

            # Verificer at GET /materials returnerer mappet
            r = await ac.get(f"/api/locations/{location_code}/materials")
            assert r.status_code == 200
            mco2 = r.json().get("material_co2_categories", {})
            assert mco2.get("Træ-fraktion") == tree["id"]
            assert mco2.get("Metal-fraktion") == metal["id"]
            assert mco2.get("Beton-fraktion") == beton["id"]
            assert mco2.get("Murbrokker") == beton["id"]
            print(f"✓ 11. GET /materials returnerer material_co2_categories korrekt")

            # ──── 9. Submit en ordre UDEN co2_type_id → backend skal hente fra materialet ──
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code,
                "material": "Træ-fraktion",
                "container_number": "TestContainer",
                "priority": "normal",
                "order_date": "2026-06-18",
                "plads_name": f"{PREFIX}AL1",
            })
            assert r.status_code == 200, r.text
            order_tree = r.json().get("order_id")
            # Verificer at backend snapshottede CO2-data fra materialet
            doc = await db.container_orders.find_one({"id": order_tree}, {"_id": 0})
            assert doc["co2_type_id"] == tree["id"]
            assert doc["co2_type_name"] == "Træ"
            assert doc["co2_factor"] == 80.0
            print(f"✓ 12. Ordre uden co2_type_id → backend henter CO2 fra materialets kategori")

            # Opret også Metal- og Beton-ordrer via submit
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code, "material": "Metal-fraktion",
                "container_number": "C2", "priority": "normal",
                "order_date": "2026-06-18", "plads_name": f"{PREFIX}AL1",
            })
            order_metal = r.json()["order_id"]
            r = await ac.post("/api/customer-orders/submit", json={
                "location_code": location_code, "material": "Beton-fraktion",
                "container_number": "C3", "priority": "normal",
                "order_date": "2026-06-18", "plads_name": f"{PREFIX}AL1",
            })
            order_beton = r.json()["order_id"]

            # Træ: 500 kg → forventet 40 kg CO2
            r = await ac.put(f"/api/container-orders/{order_tree}",
                             json={"weight_kg": 500}, headers=ca_a_h)
            assert r.status_code == 200, r.text
            assert r.json()["co2_kg"] == 40.0, f"Træ 500kg @ 80 = 40 kg CO2, got {r.json()['co2_kg']}"
            print(f"✓ 13. Træ (80 kg/ton) × 500 kg = 40.0 kg CO2 ✓ Eksempel matches")

            # Metal: 1200 kg → 26.4
            r = await ac.put(f"/api/container-orders/{order_metal}",
                             json={"weight_kg": 1200}, headers=ca_a_h)
            assert r.status_code == 200
            assert r.json()["co2_kg"] == 26.4, f"Metal 1200kg @ 22 = 26.4, got {r.json()['co2_kg']}"
            print(f"✓ 14. Metal (22 kg/ton) × 1200 kg = 26.4 kg CO2 ✓ Eksempel matches")

            # Beton: 3000 kg → 0.0
            r = await ac.put(f"/api/container-orders/{order_beton}",
                             json={"weight_kg": 3000}, headers=ca_a_h)
            assert r.status_code == 200
            assert r.json()["co2_kg"] == 0.0, f"Beton 3000kg @ 0 = 0, got {r.json()['co2_kg']}"
            assert r.json()["weight_kg"] == 3000.0
            print(f"✓ 15. Beton (0 kg/ton) × 3000 kg = 0.0 kg CO2 ✓ Eksempel matches")

            # ──── 10. Sletning blokeres pga aktiv ordre (Beton-typen er brugt) ────
            r = await ac.delete(f"/api/co2-types/{beton['id']}", headers=ca_a_h)
            assert r.status_code == 409, f"Slet blokeret af aktiv ordre, got {r.status_code}"
            assert "aktive ordre" in r.json()["detail"].lower(), r.json()
            print(f"✓ 16. Sletning blokeres når aktive ordrer bruger typen (409)")

            # ──── 11. PUT med ugyldigt co2_category_id → 400 ────
            r = await ac.put(f"/api/locations/{location_code}/materials",
                             json={"old_name": "Træ-fraktion", "new_name": "Træ-fraktion",
                                   "co2_category_id": "ikke-eksisterende-id"},
                             headers=ca_a_h)
            assert r.status_code == 400, f"Ugyldig CO2-kategori skal 400, got {r.status_code}"
            print(f"✓ 17. Ugyldig co2_category_id afvises (400)")

            # ──── 12. /reports/orders for Location Admin returnerer CO2-felter ────
            r = await ac.get(f"/api/org/reports/orders?location_code={location_code}&period=year",
                             headers=ca_a_h)
            assert r.status_code == 200, r.text
            rep = r.json()
            assert "total_co2_kg" in rep, "LA-rapport skal nu indeholde total_co2_kg"
            assert "by_co2_type" in rep
            assert "co2_over_time" in rep
            # Vores 3 ordrer = 40 + 26.4 + 0 = 66.4 kg CO2
            assert abs(rep["total_co2_kg"] - 66.4) < 0.01, f"Forventede 66.4, got {rep['total_co2_kg']}"
            print(f"✓ 18. /reports/orders returnerer CO2-aggregater for Location Admin (total={rep['total_co2_kg']} kg)")

        print()
        print("═══════════════════════════════════════════════════")
        print(" ✅ Fase 9 refactor — CO2 pr. materiale: 18/18 tests bestået")
        print("    Inkluderet alle 3 eksempel-beregninger fra brugerkrav")
        print("    + ny material-linked CO2 logik + LA-rapport CO2-aggregater")
        print("═══════════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
