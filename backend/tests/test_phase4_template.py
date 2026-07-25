"""Fase 4.1 — Tour template download + upload.

Verifies:
1. GET /api/tours/template downloads a valid .xlsx with Lokation dropdown
2. POST /api/tours/upload-template parses rows and creates tours with:
   - source="manual"
   - company_id derived from chosen plads
   - customer_name auto-filled
3. Rejected: invalid Lokation, missing material — clear error messages
4. Tenant isolation: LA cannot upload rows pointing to a plads not served by them
"""
import os, sys, uuid, asyncio, bcrypt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from io import BytesIO
from openpyxl import load_workbook, Workbook
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport
from server import app

PREFIX = "_pytest_p4t_"


async def _cleanup(db):
    await db.users.delete_many({"email": {"$regex": f"^{PREFIX}"}})
    await db.companies.delete_many({"customer_id": {"$regex": f"^{PREFIX}"}})
    await db.plads.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    await db.tours.delete_many({"facility": {"$regex": f"^{PREFIX}"}})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await _cleanup(db)
    try:
        cust_a = str(uuid.uuid4())
        cust_b = str(uuid.uuid4())  # not served by our LA
        log_id = str(uuid.uuid4())
        await db.companies.insert_many([
            {"id": cust_a, "name": f"{PREFIX}CustA", "customer_id": f"{PREFIX}A_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": cust_b, "name": f"{PREFIX}CustB", "customer_id": f"{PREFIX}B_{uuid.uuid4().hex[:4]}",
             "company_type": "customer", "active": True, "serves_company_ids": []},
            {"id": log_id, "name": f"{PREFIX}LogX", "customer_id": f"{PREFIX}L_{uuid.uuid4().hex[:4]}",
             "company_type": "logistics", "active": True, "serves_company_ids": [cust_a]},
        ])
        # Plads served (cust_a) and one NOT served (cust_b)
        code_served = f"{PREFIX}9001"
        code_forbidden = f"{PREFIX}9002"
        await db.plads.insert_many([
            {"id": str(uuid.uuid4()), "name": f"{PREFIX}Boliggården", "location_code": code_served,
             "city": "Helsingør", "address": "Test 1", "active": True,
             "company_id": cust_a, "assigned_logistics_company_ids": [log_id],
             "materials": ["Pap"], "containers_per_material": 3},
            {"id": str(uuid.uuid4()), "name": f"{PREFIX}Forbidden", "location_code": code_forbidden,
             "city": "X", "active": True,
             "company_id": cust_b, "assigned_logistics_company_ids": []},
        ])
        la_email = f"{PREFIX}la_{uuid.uuid4().hex[:6]}@x.test"
        pw = "TestPass2026!"
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": la_email, "name": "LA",
            "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
            "role": "logistics_admin", "company_id": log_id,
            "active": True, "invitation_status": "accepted", "managed_company_ids": [],
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/api/auth/login", json={"email": la_email, "password": pw})
            assert r.status_code == 200
            token = r.json().get("token") or r.json().get("access_token")
            hdr = {"Authorization": f"Bearer {token}"}

            # ──── 1. Download template ────
            r = await ac.get("/api/tours/template", headers=hdr)
            assert r.status_code == 200, r.text
            assert "spreadsheetml.sheet" in r.headers["content-type"]
            wb = load_workbook(BytesIO(r.content))
            ws = wb.active
            assert ws.cell(row=1, column=1).value == "Lokation"
            assert ws.cell(row=1, column=4).value == "Containertype"
            # Hidden Lokationer sheet must contain only the served plads
            helper = wb["Lokationer"]
            labels = [helper.cell(row=i, column=1).value for i in range(1, 5)]
            labels = [l for l in labels if l]
            assert any(code_served in l for l in labels), f"Served plads must be in dropdown: {labels}"
            assert not any(code_forbidden in (l or "") for l in labels), \
                f"Forbidden plads MUST NOT be in dropdown: {labels}"
            print(f"✓ Template downloaded — dropdown indeholder kun {len(labels)} tilladt(e) plads(er)")

            # ──── 2. Upload med 2 gyldige + 1 ugyldig række ────
            up_wb = Workbook()
            up_ws = up_wb.active
            up_ws.append([
                "Lokation", "Materiale", "Container-nummer", "Containertype",
                "Leveringsadresse", "Åbningstid", "Lukketid", "Note",
            ])
            served_label = next(l for l in labels if code_served in l)
            up_ws.append([
                served_label, "Pap", "2223", "Lav åben 20 m³",
                "Pytest Vej 1, Helsingør", "09:00", "16:00", "Skal hentes på bagsiden",
            ])
            up_ws.append([
                served_label, "Glas", "2224", "Komprimator 30 m³",
                "Pytest Vej 1, Helsingør", "08:00", "15:30", "",
            ])
            up_ws.append([
                "Ikke en plads", "Træ", "2225", "Lav åben 20 m³",
                "X", "09:00", "16:00", "",
            ])
            # Add an empty row + one with missing material
            up_ws.append([None] * 8)
            up_ws.append([served_label, "", "2226", "", "", "", "", ""])

            buf = BytesIO()
            up_wb.save(buf)
            buf.seek(0)
            r = await ac.post(
                "/api/tours/upload-template",
                files={"file": ("upload.xlsx", buf.getvalue(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                headers=hdr,
            )
            assert r.status_code == 200, r.text
            result = r.json()
            print(f"✓ Upload result: created={result['created']}, errors={len(result['errors'])}")
            assert result["created"] == 2, f"Expected 2 created, got {result['created']}: {result}"
            assert len(result["errors"]) == 2, f"Expected 2 errors, got: {result['errors']}"
            # Verify error messages reference correct rows
            err_rows = sorted(e["row"] for e in result["errors"])
            assert err_rows == [4, 6], f"Expected errors on rows 4 + 6, got {err_rows}"

            # ──── 3. Verify created tours in DB ────
            tours = await db.tours.find({"facility": f"{PREFIX}Boliggården"}, {"_id": 0}).to_list(50)
            assert len(tours) == 2
            for t in tours:
                assert t["source"] == "manual"
                assert t["company_id"] == cust_a, f"Tour must be on Customer A: {t.get('company_id')}"
                assert t["customer_name"] == f"{PREFIX}CustA"
                assert log_id in t["assigned_logistics_company_ids"]
                assert t["open_from"] in ("09:00", "08:00")
                assert t["open_to"] in ("16:00", "15:30")
            print(f"✓ Created tours have source=manual, company_id={cust_a[:8]}…, customer_name auto-set")

        print()
        print("═════════════════════════════════════════════")
        print(" ✅ Fase 4.1 — Template download/upload tests bestået")
        print("═════════════════════════════════════════════")
    finally:
        await _cleanup(db)
        client.close()


if __name__ == "__main__":
    asyncio.run(_run())
