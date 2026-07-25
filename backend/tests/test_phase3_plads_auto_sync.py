"""Fase 3 regression test — Pladser auto-synkroniseres til logistik-side.

Verifies:
1. Når en kunde-admin opretter en lokation via /api/org/locations OG knytter
   et logistik-firma til den, så ser logistik-admin'en for det firma
   pladsen i sit /api/plads-svar.
2. logistics_admin må IKKE oprette/slette/opdatere plads:
   - POST /api/plads → 405 Method Not Allowed
   - DELETE /api/plads/{id} → 405
   - PUT /api/plads/{id} → 405
3. Tenant isolation: logistics_admin A ser IKKE pladser fra kunder der ikke
   har tildelt A's firma.

Uses ephemeral `_pytest_p3_` prefix; cleans up after.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p3_"


async def _cleanup(db):
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)

    try:
        # Create: customer C, two logistics firms (X, Y).
        # Customer C creates a location and assigns X as partner — only X should see it.
        cust_id = str(uuid.uuid4())
        log_x_id = str(uuid.uuid4())
        log_y_id = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust_id, "name": f"{PREFIX}Customer C", "customer_id": f"{PREFIX}cc_{uuid.uuid4().hex[:6]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_x_id, "name": f"{PREFIX}Logistics X", "customer_id": f"{PREFIX}lx_{uuid.uuid4().hex[:6]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_id]},
            {"id": log_y_id, "name": f"{PREFIX}Logistics Y", "customer_id": f"{PREFIX}ly_{uuid.uuid4().hex[:6]}",
             "company_type": "logistics", "active": True, "serves_company_ids": []},
        ])

        ca_email = f"{PREFIX}ca_{uuid.uuid4().hex[:6]}@x.test"
        la_x_email = f"{PREFIX}la_x_{uuid.uuid4().hex[:6]}@x.test"
        la_y_email = f"{PREFIX}la_y_{uuid.uuid4().hex[:6]}@x.test"
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        for email, role, cid, name in [
            (ca_email, "customer_admin", cust_id, "CA"),
            (la_x_email, "logistics_admin", log_x_id, "LA X"),
            (la_y_email, "logistics_admin", log_y_id, "LA Y"),
        ]:
            await db.users.insert_one({
                "id": str(uuid.uuid4()), "email": email, "name": name,
                "password_hash": ph, "role": role, "company_id": cid,
                "active": True, "invitation_status": "accepted", "managed_company_ids": [],
            })

        async def login(ac, email):
            r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            return r.json().get("token") or r.json().get("access_token")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            ca_t = await login(ac, ca_email)
            la_x_t = await login(ac, la_x_email)
            la_y_t = await login(ac, la_y_email)

            # ──── 1. Customer admin creates location ────
            r = await ac.post("/api/org/locations", json={
                "name": f"{PREFIX}Boliggården",
                "city": "Helsingør",
                "address": "Hovedgaden 1",
            }, headers={"Authorization": f"Bearer {ca_t}"})
            assert r.status_code == 200, r.text
            loc = r.json()
            loc_id = loc["id"]
            loc_code = loc["location_code"]
            print(f"✓ Customer admin oprettede lokation (id={loc_id[:8]}…, code={loc_code})")

            # ──── 2. Customer admin assigns Logistics X as partner ────
            r = await ac.put(f"/api/org/locations/{loc_id}/logistics-partners",
                             json={"logistics_company_ids": [log_x_id]},
                             headers={"Authorization": f"Bearer {ca_t}"})
            assert r.status_code == 200, r.text
            print(f"✓ Customer admin tildelte Logistics X som partner")

            # ──── 3. LA X (assigned) ser pladsen ────
            r = await ac.get("/api/plads", headers={"Authorization": f"Bearer {la_x_t}"})
            assert r.status_code == 200, r.text
            x_plads = r.json()
            assert any(p["id"] == loc_id for p in x_plads), \
                f"LA X skal se den nytildelte plads, fik: {[p.get('name') for p in x_plads]}"
            print(f"✓ LA X ser pladsen automatisk (count={len(x_plads)})")

            # ──── 4. LA Y (NOT assigned) ser IKKE pladsen ────
            r = await ac.get("/api/plads", headers={"Authorization": f"Bearer {la_y_t}"})
            assert r.status_code == 200, r.text
            y_plads = r.json()
            assert all(p["id"] != loc_id for p in y_plads), \
                f"LA Y må IKKE se Customer C's plads! Fik: {[p.get('name') for p in y_plads]}"
            print(f"✓ LA Y ser IKKE pladsen (tenant-isolation respekteret)")

            # ──── 5. LA X må IKKE oprette plads via /api/plads ────
            r = await ac.post("/api/plads",
                              json={"name": f"{PREFIX}AdHoc", "city": "X", "address": "Y"},
                              headers={"Authorization": f"Bearer {la_x_t}"})
            assert r.status_code == 405, f"POST /api/plads for LA skal være 405, fik {r.status_code}: {r.text}"
            print("✓ POST /api/plads blokeret for LA (405)")

            # ──── 6. LA X må IKKE slette plads ────
            r = await ac.delete(f"/api/plads/{loc_id}", headers={"Authorization": f"Bearer {la_x_t}"})
            assert r.status_code == 405, f"DELETE /api/plads/{{id}} for LA skal være 405, fik {r.status_code}"
            print("✓ DELETE /api/plads/{id} blokeret for LA (405)")

            # ──── 7. LA X må IKKE opdatere plads-felter ────
            r = await ac.put(f"/api/plads/{loc_id}",
                             json={"name": f"{PREFIX}Hacked"},
                             headers={"Authorization": f"Bearer {la_x_t}"})
            assert r.status_code == 405, f"PUT /api/plads/{{id}} for LA skal være 405, fik {r.status_code}"
            print("✓ PUT /api/plads/{id} blokeret for LA (405)")

            # ──── 8. Customer admin kan stadig opdatere lokationen ────
            r = await ac.put(f"/api/org/locations/{loc_id}",
                             json={"city": "Hillerød"},
                             headers={"Authorization": f"Bearer {ca_t}"})
            assert r.status_code == 200, f"CA update skal stadig virke: {r.text}"
            # And LA X sees the updated city
            r = await ac.get("/api/plads", headers={"Authorization": f"Bearer {la_x_t}"})
            updated = [p for p in r.json() if p["id"] == loc_id]
            assert updated and updated[0]["city"] == "Hillerød"
            print("✓ Customer admin kan stadig opdatere; ændringer synlige hos LA X")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 3 — Alle plads-auto-sync tests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
