"""Fase 2 regression test — chauffør oprettes via invitation-flow.

Verifies:
1. Old endpoints `/api/driver/login` and `/api/driver/verify-code` return 410 Gone.
2. Logistics admin can POST /api/drivers → creates a user (role=driver,
   invitation_status=pending, empty password_hash) and creates an invitation
   token.
3. The driver can accept the invitation, set a password, and log in via
   /api/auth/login with email + password.
4. Tenant isolation: logistics_admin A cannot see/modify driver from
   logistics company B.

Uses ephemeral `_pytest_drv_` prefix; cleans up after.
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_drv_"


async def _cleanup(db):
    # Capture user IDs for token cleanup
    user_ids = [u["id"] async for u in db.users.find(
        {"email": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    if user_ids:
        await db.invitation_tokens.delete_many({"user_id": {"$in": user_ids}})
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)

    try:
        # Two logistics companies (for tenant-isolation test)
        log_co_a = str(uuid.uuid4())
        log_co_b = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": log_co_a, "name": f"{PREFIX}LogA", "company_type": "logistics",
             "customer_id": f"{PREFIX}{uuid.uuid4().hex[:6]}", "active": True,
             "serves_company_ids": []},
            {"id": log_co_b, "name": f"{PREFIX}LogB", "company_type": "logistics",
             "customer_id": f"{PREFIX}{uuid.uuid4().hex[:6]}", "active": True,
             "serves_company_ids": []},
        ])

        # Logistics admin in company A
        la_id = str(uuid.uuid4())
        la_email = f"{PREFIX}la_a_{uuid.uuid4().hex[:6]}@x.test"
        la_pw = "TestPass2026!"
        await db.users.insert_one({
            "id": la_id, "email": la_email, "name": "LA A",
            "password_hash": bcrypt.hashpw(la_pw.encode(), bcrypt.gensalt()).decode(),
            "role": "logistics_admin", "company_id": log_co_a,
            "active": True, "invitation_status": "accepted",
            "managed_company_ids": [],
        })
        # Logistics admin in company B (for tenant isolation)
        lb_id = str(uuid.uuid4())
        lb_email = f"{PREFIX}la_b_{uuid.uuid4().hex[:6]}@x.test"
        await db.users.insert_one({
            "id": lb_id, "email": lb_email, "name": "LA B",
            "password_hash": bcrypt.hashpw(la_pw.encode(), bcrypt.gensalt()).decode(),
            "role": "logistics_admin", "company_id": log_co_b,
            "active": True, "invitation_status": "accepted",
            "managed_company_ids": [],
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # ──── 1. Gamle endpoints returnerer 410 Gone ────
            r = await ac.post("/api/driver/login", json={"name": "Whoever", "code": "anything"})
            assert r.status_code == 410, f"Old driver/login should be 410, got {r.status_code}"
            r = await ac.post("/api/driver/verify-code", json={"code": "1234"})
            assert r.status_code == 410, f"Old driver/verify-code should be 410, got {r.status_code}"
            print("✓ Old driver endpoints return 410 Gone")

            # ──── 2. LA opretter chauffør via invitation ────
            r = await ac.post("/api/auth/login", json={"email": la_email, "password": la_pw})
            assert r.status_code == 200
            la_token = r.json().get("token") or r.json().get("access_token")
            la_hdr = {"Authorization": f"Bearer {la_token}"}

            drv_email = f"{PREFIX}driver_{uuid.uuid4().hex[:6]}@x.test"
            r = await ac.post("/api/drivers", json={
                "name": "Pytest Driver",
                "email": drv_email,
                "plate": "AB12345",
                "phone": "12345678",
                "area": "Helsingør",
            }, headers=la_hdr)
            assert r.status_code == 200, f"Create driver failed: {r.text}"
            drv = r.json()
            assert drv["email"] == drv_email
            assert drv["name"] == "Pytest Driver"
            assert drv["plate"] == "AB12345"
            assert drv["invitation_status"] == "pending"
            driver_user_id = drv["id"]
            print(f"✓ Driver created via invitation: id={driver_user_id}, status=pending")

            # Verify user row + invitation token in DB
            u = await db.users.find_one({"id": driver_user_id}, {"_id": 0})
            assert u["role"] == "driver"
            assert u["company_id"] == log_co_a
            assert u.get("password_hash", "") == "", "Driver should have empty password until set"
            tk = await db.invitation_tokens.find_one({"user_id": driver_user_id, "token_type": "invitation"}, {"_id": 0})
            assert tk is not None and not tk.get("used"), "Invitation token should exist and be unused"
            print(f"✓ Invitation token created (token={tk['token'][:8]}…), unused")

            # ──── 3. Driver accepts invitation + sets password ────
            new_pw = "DriverPass2026!"
            r = await ac.post("/api/auth/accept-invitation", json={
                "token": tk["token"], "new_password": new_pw, "type": "invitation",
            })
            assert r.status_code == 200, f"Accept invitation failed: {r.text}"
            print("✓ Driver accepted invitation and set password")

            # ──── 4. Driver logs in with new credentials ────
            r = await ac.post("/api/auth/login", json={"email": drv_email, "password": new_pw})
            assert r.status_code == 200, f"Driver login failed: {r.text}"
            payload = r.json()
            drv_token = payload.get("token") or payload.get("access_token")
            assert drv_token, "Driver login should return token"
            # Some endpoints embed user info under "user", others top-level
            user_blob = payload.get("user", payload)
            assert user_blob.get("role") == "driver"
            print("✓ Driver logged in successfully with email + password")

            # ──── 5. Tenant isolation: LA B cannot see/modify driver from LA A ────
            r = await ac.post("/api/auth/login", json={"email": lb_email, "password": la_pw})
            assert r.status_code == 200
            lb_token = r.json().get("token") or r.json().get("access_token")
            lb_hdr = {"Authorization": f"Bearer {lb_token}"}

            r = await ac.get("/api/drivers", headers=lb_hdr)
            assert r.status_code == 200
            lb_drivers = r.json()
            assert all(d["id"] != driver_user_id for d in lb_drivers), \
                f"LA B should not see LA A's driver! Got: {lb_drivers}"
            r = await ac.get(f"/api/drivers/{driver_user_id}", headers=lb_hdr)
            assert r.status_code == 403, f"LA B accessing LA A's driver should be 403, got {r.status_code}"
            r = await ac.delete(f"/api/drivers/{driver_user_id}", headers=lb_hdr)
            assert r.status_code == 403, f"LA B deleting LA A's driver should be 403, got {r.status_code}"
            print("✓ Tenant isolation: LA B cannot see/modify LA A's drivers")

            # ──── 6. LA A can still see + manage their driver ────
            r = await ac.get("/api/drivers", headers=la_hdr)
            assert r.status_code == 200
            la_drivers = r.json()
            assert any(d["id"] == driver_user_id for d in la_drivers)
            print(f"✓ LA A sees their driver in /api/drivers (count={len(la_drivers)})")

            # ──── 7. LA can update driver fields (e.g. plate) ────
            r = await ac.put(f"/api/drivers/{driver_user_id}",
                             json={"plate": "CD98765"}, headers=la_hdr)
            assert r.status_code == 200, f"Update driver failed: {r.text}"
            assert r.json()["plate"] == "CD98765"
            print("✓ LA updated driver's plate successfully")

            # ──── 8. Resend invitation requires status=pending (should fail now since driver accepted) ────
            r = await ac.post(f"/api/drivers/{driver_user_id}/resend-invitation", headers=la_hdr)
            assert r.status_code == 400, f"Resend should fail for non-pending driver, got {r.status_code}"
            print("✓ Resend invitation correctly blocked for already-active driver")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 2 — Alle driver-invitation tests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
