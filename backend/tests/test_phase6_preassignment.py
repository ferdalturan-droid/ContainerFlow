"""Fase 6 regression test — Tur-delegering: pre-assignment + self-claim (SIKKERHED).

Critical security cases:
1. LA can pre-assign a tour to driver A via driver_id.
2. Pre-assigned tour is visible to A but HIDDEN from driver B (same company, same customer).
3. Open tour (no driver_id) is visible to BOTH A and B.
4. Driver A cannot set driver_id (strip silently); cannot set claimed_by_id to B's id.
5. Driver A can self-claim an open tour (claimed_by_id = A.id).
6. LA can reassign / release driver_id.
7. Each LA assignment creates an audit-log entry retrievable via GET /api/tours/{id}/audit-log.

Uses ephemeral `_pytest_p6_` prefix.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p6_"


async def _cleanup(db):
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    await db.tours.delete_many({"facility": {"$regex": f"^{PREFIX}"}})
    await db.tour_audit_log.delete_many({"user_email": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        cust_id = str(uuid.uuid4())
        log_id = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust_id, "name": f"{PREFIX}Cust", "customer_id": f"{PREFIX}C_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_id, "name": f"{PREFIX}Log", "customer_id": f"{PREFIX}L_{uuid.uuid4().hex[:4]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_id]},
        ])

        plads_id = str(uuid.uuid4())
        await db.plads.insert_one({
            "id": plads_id, "name": f"{PREFIX}Plads", "location_code": f"{PREFIX}P1",
            "active": True, "company_id": cust_id, "assigned_logistics_company_ids": [log_id],
        })

        common_tour = {
            "claimed_by": "", "claimed_by_id": "", "active": True,
            "completed": False, "on_way": False, "sort_order": 0,
            "source": "manual", "is_pause": False, "is_private": False,
            "driver_id": "", "driver_name": "",
        }
        tour_open_id = str(uuid.uuid4())     # open — visible to both A and B
        tour_assigned_id = str(uuid.uuid4()) # to be pre-assigned to A
        await db.tours.insert_many([
            {"id": tour_open_id, "date": "2026-06-17", "fraction": "Pap",
             "facility": f"{PREFIX}Plads", "address": "Open Test",
             "company_id": cust_id, "assigned_logistics_company_ids": [log_id], **common_tour},
            {"id": tour_assigned_id, "date": "2026-06-17", "fraction": "Glas",
             "facility": f"{PREFIX}Plads", "address": "Assigned Test",
             "company_id": cust_id, "assigned_logistics_company_ids": [log_id], **common_tour},
        ])

        # LA + 2 drivers
        la_email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@x.test"
        drv_a_email = f"{PREFIX}drvA_{uuid.uuid4().hex[:6]}@x.test"
        drv_b_email = f"{PREFIX}drvB_{uuid.uuid4().hex[:6]}@x.test"
        pw = "TestPass2026!"
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        drv_a_id = str(uuid.uuid4())
        drv_b_id = str(uuid.uuid4())
        await db.users.insert_many([
            {"id": str(uuid.uuid4()), "email": la_email, "name": "Test LA",
             "password_hash": ph, "role": "logistics_admin", "company_id": log_id,
             "active": True, "invitation_status": "accepted"},
            {"id": drv_a_id, "email": drv_a_email, "name": "Driver A",
             "password_hash": ph, "role": "driver", "company_id": log_id,
             "active": True, "invitation_status": "accepted",
             "active_customer_id": cust_id},
            {"id": drv_b_id, "email": drv_b_email, "name": "Driver B",
             "password_hash": ph, "role": "driver", "company_id": log_id,
             "active": True, "invitation_status": "accepted",
             "active_customer_id": cust_id},
        ])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Login as LA + A + B
            r = await ac.post("/api/auth/login", json={"email": la_email, "password": pw})
            la_tok = r.json().get("token")
            la_hdr = {"Authorization": f"Bearer {la_tok}"}
            r = await ac.post("/api/auth/login", json={"email": drv_a_email, "password": pw})
            a_tok = r.json().get("token")
            a_hdr = {"Authorization": f"Bearer {a_tok}"}
            r = await ac.post("/api/auth/login", json={"email": drv_b_email, "password": pw})
            b_tok = r.json().get("token")
            b_hdr = {"Authorization": f"Bearer {b_tok}"}

            # ──── 1. Both drivers see open tour ────
            r = await ac.get("/api/tours?date=2026-06-17", headers=a_hdr)
            assert r.status_code == 200
            a_tour_ids = sorted(t["id"] for t in r.json())
            assert tour_open_id in a_tour_ids and tour_assigned_id in a_tour_ids
            r = await ac.get("/api/tours?date=2026-06-17", headers=b_hdr)
            b_tour_ids = sorted(t["id"] for t in r.json())
            assert tour_open_id in b_tour_ids and tour_assigned_id in b_tour_ids
            print("✓ 1. Open tour visible to both drivers")

            # ──── 2. LA pre-assigns tour_assigned to Driver A ────
            r = await ac.put(f"/api/tours/{tour_assigned_id}",
                             json={"driver_id": drv_a_id, "driver_name": "Driver A"},
                             headers=la_hdr)
            assert r.status_code == 200, r.text
            assert r.json()["driver_id"] == drv_a_id
            print("✓ 2. LA pre-assigns tour to Driver A")

            # ──── 3. Pre-assigned tour hidden from Driver B ────
            r = await ac.get("/api/tours?date=2026-06-17", headers=b_hdr)
            b_tour_ids = sorted(t["id"] for t in r.json())
            assert tour_assigned_id not in b_tour_ids, "Pre-assigned tour MUST be hidden from B"
            assert tour_open_id in b_tour_ids, "Open tour must remain visible"
            print("✓ 3. Pre-assigned tour HIDDEN from Driver B; open tour still visible")

            # ──── 4. Pre-assigned tour STILL visible to Driver A ────
            r = await ac.get("/api/tours?date=2026-06-17", headers=a_hdr)
            a_tour_ids = sorted(t["id"] for t in r.json())
            assert tour_assigned_id in a_tour_ids
            print("✓ 4. Pre-assigned tour visible to assigned Driver A")

            # ──── 5. Driver A cannot set driver_id (silently stripped) ────
            r = await ac.put(f"/api/tours/{tour_open_id}",
                             json={"driver_id": drv_b_id, "driver_name": "Driver B"},
                             headers=a_hdr)
            assert r.status_code == 200, r.text
            # Verify driver_id was NOT updated (still empty)
            tour_doc = await db.tours.find_one({"id": tour_open_id}, {"_id": 0, "driver_id": 1})
            assert (tour_doc.get("driver_id") or "") == "", \
                f"Driver A's attempt to set driver_id should be silently stripped, got {tour_doc.get('driver_id')}"
            print("✓ 5. Driver A cannot set driver_id (silently stripped)")

            # ──── 6. Driver A cannot self-claim with B's id (403) ────
            r = await ac.put(f"/api/tours/{tour_open_id}",
                             json={"claimed_by": "Driver B", "claimed_by_id": drv_b_id},
                             headers=a_hdr)
            assert r.status_code == 403, f"Driver A claiming as B must 403, got {r.status_code}"
            print("✓ 6. Driver A cannot self-claim with B's id (403)")

            # ──── 7. Driver A self-claims open tour ────
            r = await ac.put(f"/api/tours/{tour_open_id}",
                             json={"claimed_by": "Driver A", "claimed_by_id": drv_a_id},
                             headers=a_hdr)
            assert r.status_code == 200, r.text
            tour_doc = await db.tours.find_one({"id": tour_open_id}, {"_id": 0})
            assert tour_doc["claimed_by_id"] == drv_a_id
            print("✓ 7. Driver A self-claims open tour")

            # ──── 8. Driver B cannot update tour pre-assigned to A (403) ────
            r = await ac.put(f"/api/tours/{tour_assigned_id}",
                             json={"on_way": True},
                             headers=b_hdr)
            assert r.status_code == 403, f"B updating A's pre-assigned tour must 403, got {r.status_code}"
            print("✓ 8. Driver B blocked from updating Driver A's pre-assigned tour (403)")

            # ──── 9. LA releases pre-assignment ────
            r = await ac.put(f"/api/tours/{tour_assigned_id}",
                             json={"driver_id": "", "driver_name": ""},
                             headers=la_hdr)
            assert r.status_code == 200, r.text
            # Now B should see it again
            r = await ac.get("/api/tours?date=2026-06-17", headers=b_hdr)
            b_tour_ids = sorted(t["id"] for t in r.json())
            assert tour_assigned_id in b_tour_ids, "After release, B should see the tour again"
            print("✓ 9. LA releases pre-assignment → tour open for all again")

            # ──── 10. Audit log has assign + release entries ────
            r = await ac.get(f"/api/tours/{tour_assigned_id}/audit-log", headers=la_hdr)
            assert r.status_code == 200, r.text
            entries = r.json()
            actions = [e["action"] for e in entries]
            assert "assign" in actions, f"Expected 'assign' in audit-log, got {actions}"
            assert "release" in actions, f"Expected 'release' in audit-log, got {actions}"
            print(f"✓ 10. Audit log has {len(entries)} entries: {actions}")

            # ──── 11. Driver cannot read audit log (403) ────
            r = await ac.get(f"/api/tours/{tour_assigned_id}/audit-log", headers=a_hdr)
            assert r.status_code == 403, f"Driver reading audit log must 403, got {r.status_code}"
            print("✓ 11. Driver blocked from audit-log (403)")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 6 — Pre-assignment + self-claim: 11/11 sikkerhedstests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
