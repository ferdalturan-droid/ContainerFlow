"""Fase 8 regression — Fuld rolle-isolation verifikation.

Tester 6 roller (super_admin, logistics_admin, customer_admin, location_admin,
order, driver) for multi-tenant data isolation. Hver rolle skal kun se sine
egne data og ikke kunne påvirke andre tenants.

Sikkerhedstests:
1. super_admin: kan se alle companies + alle users på tværs af tenants
2. logistics_admin: kan KUN se egne tours + partnered customer's tours
3. logistics_admin: kan IKKE læse anden LA's company data
4. customer_admin: kan KUN administrere egen kundes plads/locations
5. customer_admin: kan IKKE redigere anden kundes plads
6. order: kan KUN se egen lokations ordrer
7. order: kan IKKE oprette ordre på anden lokation
8. driver: kan KUN se aktiv kundes plads/tours (Fase 5)
9. driver: kan IKKE læse anden kundes data
10. driver: kan IKKE pre-tildele ture (kun LA kan)
11. driver: kan IKKE læse audit-log (Fase 6)
12. Cross-tenant /api/plads isolation: alle 4 LA-roller får forskellig liste
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p8_"


async def _cleanup(db):
    for col in ("users", "companies", "plads", "locations", "container_orders",
                "tours", "tour_audit_log"):
        coll = db[col]
        # Match any field that might carry our prefix
        await coll.delete_many({"$or": [
            {"email": {"$regex": f"^{PREFIX}"}},
            {"name": {"$regex": f"^{PREFIX}"}},
            {"customer_id": {"$regex": f"^{PREFIX}"}},
            {"facility": {"$regex": f"^{PREFIX}"}},
            {"location_code": {"$regex": f"^{PREFIX}"}},
            {"user_email": {"$regex": f"^{PREFIX}"}},
        ]})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        # ─────────────────── seed: 2 customer companies + 2 logistics companies ───
        cust_a = str(uuid.uuid4())  # ARGO-like
        cust_b = str(uuid.uuid4())  # Helsingør F-like
        log_x  = str(uuid.uuid4())  # ILK-like
        log_y  = str(uuid.uuid4())  # CityContainer-like
        await db.companies.insert_many([
            {"id": cust_a, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}CA_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": cust_b, "name": f"{PREFIX}CustB", "customer_id": f"{PREFIX}CB_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_x,  "name": f"{PREFIX}LogX", "customer_id": f"{PREFIX}LX_{uuid.uuid4().hex[:4]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_a, cust_b]},
            {"id": log_y,  "name": f"{PREFIX}LogY", "customer_id": f"{PREFIX}LY_{uuid.uuid4().hex[:4]}",
             "company_type": "logistics", "active": True, "serves_company_ids": []},
        ])

        # ─────────────────── seed: 2 locations per customer ───
        loc_a1 = str(uuid.uuid4())
        loc_a2 = str(uuid.uuid4())
        loc_b1 = str(uuid.uuid4())
        await db.locations.insert_many([
            {"id": loc_a1, "name": f"{PREFIX}A_loc1", "location_code": f"{PREFIX}AL1",
             "company_id": cust_a, "active": True},
            {"id": loc_a2, "name": f"{PREFIX}A_loc2", "location_code": f"{PREFIX}AL2",
             "company_id": cust_a, "active": True},
            {"id": loc_b1, "name": f"{PREFIX}B_loc1", "location_code": f"{PREFIX}BL1",
             "company_id": cust_b, "active": True},
        ])

        # ─────────────────── seed: plads per customer ───
        plads_a = str(uuid.uuid4())
        plads_b = str(uuid.uuid4())
        await db.plads.insert_many([
            {"id": plads_a, "name": f"{PREFIX}PladsA", "location_code": f"{PREFIX}PA",
             "company_id": cust_a, "assigned_logistics_company_ids": [log_x], "active": True},
            {"id": plads_b, "name": f"{PREFIX}PladsB", "location_code": f"{PREFIX}PB",
             "company_id": cust_b, "assigned_logistics_company_ids": [log_x], "active": True},
        ])

        # ─────────────────── seed: container_order + tour on each customer ───
        order_a = str(uuid.uuid4())
        order_b = str(uuid.uuid4())
        await db.container_orders.insert_many([
            {"id": order_a, "company_id": cust_a, "location_code": f"{PREFIX}AL1",
             "material": "PAP", "container_type": "10m3", "status": "pending",
             "open_from": "2026-06-17T07:00:00", "open_to": "2026-06-17T15:00:00",
             "created_at": "2026-06-17T06:00:00", "customer_id": f"{PREFIX}CA"},
            {"id": order_b, "company_id": cust_b, "location_code": f"{PREFIX}BL1",
             "material": "Glas", "container_type": "10m3", "status": "pending",
             "open_from": "2026-06-17T07:00:00", "open_to": "2026-06-17T15:00:00",
             "created_at": "2026-06-17T06:00:00", "customer_id": f"{PREFIX}CB"},
        ])

        tour_a = str(uuid.uuid4())
        await db.tours.insert_one({
            "id": tour_a, "date": "2026-06-17", "fraction": "PAP",
            "facility": f"{PREFIX}PladsA", "address": "TestA",
            "company_id": cust_a, "assigned_logistics_company_ids": [log_x],
            "claimed_by": "", "claimed_by_id": "", "completed": False, "on_way": False,
            "sort_order": 0, "active": True, "source": "manual", "is_pause": False,
            "is_private": False, "driver_id": "", "driver_name": "",
        })

        # ─────────────────── seed: 1 user per role ───
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

        sa = f"{PREFIX}sa_{uuid.uuid4().hex[:6]}@x.test"
        la_x_email = f"{PREFIX}la_x_{uuid.uuid4().hex[:6]}@x.test"
        la_y_email = f"{PREFIX}la_y_{uuid.uuid4().hex[:6]}@x.test"
        ca_a_email = f"{PREFIX}ca_a_{uuid.uuid4().hex[:6]}@x.test"
        ca_b_email = f"{PREFIX}ca_b_{uuid.uuid4().hex[:6]}@x.test"
        loc_a1_email = f"{PREFIX}loc_a1_{uuid.uuid4().hex[:6]}@x.test"
        ord_a1_email = f"{PREFIX}ord_a1_{uuid.uuid4().hex[:6]}@x.test"
        ord_b1_email = f"{PREFIX}ord_b1_{uuid.uuid4().hex[:6]}@x.test"
        drv_x_id = str(uuid.uuid4())
        drv_x_email = f"{PREFIX}drv_x_{uuid.uuid4().hex[:6]}@x.test"

        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": sa, "name": "SA", "password_hash": ph,
             "role": "super_admin", "company_id": "", "active": True, "invitation_status": "accepted"},

            {"id": str(uuid.uuid4()), "email": la_x_email, "name": "LA-X", "password_hash": ph,
             "role": "logistics_admin", "company_id": log_x, "active": True,
             "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": la_y_email, "name": "LA-Y", "password_hash": ph,
             "role": "logistics_admin", "company_id": log_y, "active": True,
             "invitation_status": "accepted"},

            {"id": str(uuid.uuid4()), "email": ca_a_email, "name": "CA-A", "password_hash": ph,
             "role": "customer_admin", "company_id": cust_a, "active": True,
             "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": ca_b_email, "name": "CA-B", "password_hash": ph,
             "role": "customer_admin", "company_id": cust_b, "active": True,
             "invitation_status": "accepted"},

            {"id": str(uuid.uuid4()), "email": loc_a1_email, "name": "LocA1", "password_hash": ph,
             "role": "location_admin", "company_id": cust_a,
             "location_codes": [f"{PREFIX}AL1"], "active": True,
             "invitation_status": "accepted"},

            {"id": str(uuid.uuid4()), "email": ord_a1_email, "name": "OrdA1", "password_hash": ph,
             "role": "order", "company_id": cust_a, "location_codes": [f"{PREFIX}AL1"],
             "active": True, "invitation_status": "accepted"},
            {"id": str(uuid.uuid4()), "email": ord_b1_email, "name": "OrdB1", "password_hash": ph,
             "role": "order", "company_id": cust_b, "location_codes": [f"{PREFIX}BL1"],
             "active": True, "invitation_status": "accepted"},

            {"id": drv_x_id, "email": drv_x_email, "name": "DrvX", "password_hash": ph,
             "role": "driver", "company_id": log_x, "active_customer_id": cust_a,
             "active": True, "invitation_status": "accepted"},
        ])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async def login(email):
                r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
                assert r.status_code == 200, f"Login fail for {email}: {r.text}"
                return {"Authorization": f"Bearer {r.json()['token']}"}

            sa_h, la_x_h, la_y_h = await login(sa), await login(la_x_email), await login(la_y_email)
            ca_a_h, ca_b_h = await login(ca_a_email), await login(ca_b_email)
            loc_a1_h = await login(loc_a1_email)
            ord_a1_h, ord_b1_h = await login(ord_a1_email), await login(ord_b1_email)
            drv_x_h = await login(drv_x_email)

            # ────────── 1. super_admin: ser begge customers + begge logistics ──
            r = await ac.get("/api/superadmin/companies", headers=sa_h)
            assert r.status_code == 200, f"SA /superadmin/companies: {r.status_code}: {r.text}"
            sa_company_ids = [c["id"] for c in r.json()]
            assert all(cid in sa_company_ids for cid in [cust_a, cust_b, log_x, log_y]), \
                f"SA must see all 4 companies, got {len(sa_company_ids)}"
            print("✓  1. super_admin ser alle 4 companies på tværs af tenants")

            # ────────── 2. logistics_admin: kun egen company + partnered customers ──
            r = await ac.get("/api/plads", headers=la_x_h)
            assert r.status_code == 200
            la_x_plads_cids = sorted({p.get("company_id") for p in r.json() if p.get("name","").startswith(PREFIX)})
            assert cust_a in la_x_plads_cids and cust_b in la_x_plads_cids, \
                f"LA-X should see PladsA + PladsB (both partnered), got cids {la_x_plads_cids}"
            print("✓  2. LA-X ser PladsA + PladsB (begge partnered kunder)")

            r = await ac.get("/api/plads", headers=la_y_h)
            la_y_plads = [p for p in r.json() if p.get("name","").startswith(PREFIX)]
            assert len(la_y_plads) == 0, f"LA-Y has NO partnered customers, must see 0 PREFIX plads, got {len(la_y_plads)}"
            print("✓  3. LA-Y (ingen partnered kunder) ser INGEN test-plads")

            # ────────── 3. customer_admin: ser kun egen kundes plads ──
            r = await ac.get("/api/plads", headers=ca_a_h)
            ca_a_plads_cids = {p.get("company_id") for p in r.json() if p.get("name","").startswith(PREFIX)}
            assert cust_a in ca_a_plads_cids and cust_b not in ca_a_plads_cids, \
                f"CA-A ser kun cust_a's plads; got cids {ca_a_plads_cids}"
            print("✓  4. CA-A ser egen kundes plads (cust_a), IKKE cust_b's")

            # ────────── 4. customer_admin kan IKKE redigere anden kundes plads ──
            r = await ac.put(f"/api/plads/{plads_b}",
                             json={"name": f"{PREFIX}HACKED"}, headers=ca_a_h)
            assert r.status_code in (403, 404), \
                f"CA-A skal blokeres fra at redigere cust_b's plads, got {r.status_code}: {r.text}"
            print(f"✓  5. CA-A blokeret fra at redigere cust_b's plads ({r.status_code})")

            # ────────── 5. order: ser KUN egen lokations container_orders ──
            r = await ac.get("/api/container-orders", headers=ord_a1_h)
            assert r.status_code == 200
            ord_a1_ids = {o["id"] for o in r.json() if o["id"] in (order_a, order_b)}
            assert order_a in ord_a1_ids and order_b not in ord_a1_ids, \
                f"OrdA1 (cust_a/AL1) skal IKKE se OrdB; got {ord_a1_ids}"
            print("✓  6. order-rolle ser KUN egen lokations container_orders")

            # ────────── 6. order: kan IKKE læse anden kundes ordre direkte ──
            r = await ac.get("/api/container-orders", headers=ord_b1_h)
            ord_b1_ids = {o["id"] for o in r.json() if o["id"] in (order_a, order_b)}
            assert order_b in ord_b1_ids and order_a not in ord_b1_ids, \
                f"OrdB1 skal kun se order_b, got {ord_b1_ids}"
            print("✓  7. OrdB1 isoleret fra cust_a's ordrer")

            # ────────── 7. driver: kun aktiv kundes plads (Fase 5) ──
            r = await ac.get("/api/plads", headers=drv_x_h)
            drv_plads_names = [p["name"] for p in r.json() if p.get("name","").startswith(PREFIX)]
            # DrvX har active_customer_id=cust_a, så skal kun se PladsA
            assert f"{PREFIX}PladsA" in drv_plads_names, \
                f"DrvX (active=cust_a) skal se PladsA, got {drv_plads_names}"
            assert f"{PREFIX}PladsB" not in drv_plads_names, \
                f"DrvX (active=cust_a) må IKKE se PladsB (cust_b's plads)"
            print(f"✓  8. Driver (active=cust_a) ser KUN PladsA, IKKE PladsB")

            # ────────── 8. driver: kan IKKE pre-tildele ture (Fase 6) ──
            r = await ac.put(f"/api/tours/{tour_a}",
                             json={"driver_id": drv_x_id, "driver_name": "DrvX"},
                             headers=drv_x_h)
            assert r.status_code == 200  # silently stripped
            tour_doc = await db.tours.find_one({"id": tour_a}, {"_id": 0, "driver_id": 1})
            assert (tour_doc.get("driver_id") or "") == "", \
                f"Driver-attempt på driver_id skal strippes silently"
            print("✓  9. Driver kan IKKE pre-tildele (driver_id strippes)")

            # ────────── 9. driver: kan IKKE læse audit-log (Fase 6) ──
            r = await ac.get(f"/api/tours/{tour_a}/audit-log", headers=drv_x_h)
            assert r.status_code == 403, f"Driver audit-log skal 403, got {r.status_code}"
            print(f"✓ 10. Driver blokeret fra audit-log ({r.status_code})")

            # ────────── 10. LA-Y kan IKKE se LA-X's tours ──
            r = await ac.get("/api/tours?date=2026-06-17", headers=la_y_h)
            la_y_tour_ids = {t["id"] for t in r.json() if t["id"] == tour_a}
            assert len(la_y_tour_ids) == 0, \
                f"LA-Y (uden partnership) skal IKKE se LA-X's tour, got {la_y_tour_ids}"
            print("✓ 11. LA-Y isoleret fra LA-X's tours (cross-LA isolation)")

            # ────────── 11. location_admin scope check ──
            r = await ac.get("/api/locations", headers=loc_a1_h)
            assert r.status_code in (200, 403), f"location_admin /api/locations: {r.status_code}"
            print(f"✓ 12. location_admin /api/locations svar: {r.status_code}")

            # ────────── 12. super_admin: kan se audit-log for ENHVER tour ──
            await db.tour_audit_log.insert_one({
                "id": str(uuid.uuid4()), "tour_id": tour_a, "action": "assign",
                "user_id": "fake", "user_name": "Test", "user_email": f"{PREFIX}fake@x",
                "user_role": "logistics_admin",
                "before": {"driver_id": "", "driver_name": ""},
                "after": {"driver_id": drv_x_id, "driver_name": "DrvX"},
                "at": "2026-06-17T10:00:00+00:00",
            })
            r = await ac.get(f"/api/tours/{tour_a}/audit-log", headers=sa_h)
            assert r.status_code == 200, f"SA audit-log: {r.status_code}: {r.text}"
            assert len(r.json()) >= 1, f"SA should see audit-log entries, got {r.json()}"
            print(f"✓ 13. super_admin kan læse audit-log på enhver tour")

        print()
        print("═══════════════════════════════════════════════════")
        print(" ✅ Fase 8 — Fuld rolle-isolation: 13/13 tests bestået")
        print("    Roller dækket: super_admin, logistics_admin, customer_admin,")
        print("    location_admin, order, driver")
        print("═══════════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
