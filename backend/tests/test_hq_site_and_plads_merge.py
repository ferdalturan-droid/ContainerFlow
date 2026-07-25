"""
Tests for:
(a) Genbrug HQ vs Site user separation
    - User model fields is_hq_admin / assigned_plads_ids persisted via POST/PUT
    - _user_to_public returns the fields in /auth/login and /auth/me
    - /api/genbrug/plads-rapport site filter behaviour
    - Data hygiene when role changes away from genbrug_plads

(b) Plads Merge feature
    - POST /api/superadmin/plads/merge moves tours/addresses/orders/prices/user_assignments
    - Rejects same source/target (400) and missing IDs (404)
    - Endpoint is super-admin protected
"""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SUPER = {"email": "superadmin@platform.com", "password": "SuperAdmin2026!"}
GENBRUG = {"email": "genbrug@default.local", "password": "genbrug2026"}


# ---------- helpers ----------

def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def sa_headers():
    return {"Authorization": f"Bearer {_login(SUPER)}"}


@pytest.fixture(scope="module")
def gen_headers():
    return {"Authorization": f"Bearer {_login(GENBRUG)}"}


@pytest.fixture(scope="module")
def default_company_id(sa_headers):
    r = requests.get(f"{API}/superadmin/companies", headers=sa_headers, timeout=10)
    assert r.status_code == 200
    cos = r.json()
    default = next((c for c in cos if c.get("id") == "default" or c.get("slug") == "default"), None)
    assert default, f"default company not found in {cos}"
    return default["id"]


@pytest.fixture(scope="module")
def created_users():
    """tracks user IDs to clean up at end of module"""
    ids = []
    yield ids
    # cleanup
    token = _login(SUPER)
    h = {"Authorization": f"Bearer {token}"}
    for uid in ids:
        try:
            requests.delete(f"{API}/superadmin/users/{uid}", headers=h, timeout=10)
        except Exception:
            pass


@pytest.fixture(scope="module")
def created_plads():
    ids = []
    yield ids
    token = _login(SUPER)
    h = {"Authorization": f"Bearer {token}"}
    for pid in ids:
        try:
            requests.delete(f"{API}/superadmin/plads/{pid}", headers=h, timeout=10)
        except Exception:
            pass


@pytest.fixture(scope="module")
def created_tours():
    ids = []
    yield ids
    # cleanup test tours from raw db via API not available; tours created directly via mongo
    # Will be best-effort cleaned in the test itself via delete endpoint if accessible.


# ---------- (a) HQ vs Site user fields ----------

class TestUserHQSiteFields:
    def test_create_genbrug_site_user_persists_new_fields(self, sa_headers, default_company_id, created_users):
        email = f"TEST_site_{uuid.uuid4().hex[:8]}@default.local"
        body = {
            "email": email,
            "name": "TEST Site User",
            "password": "Test2026!",
            "role": "genbrug_plads",
            "company_id": default_company_id,
            "is_hq_admin": False,
            "assigned_plads_ids": ["plads-aaa", "plads-bbb"],
        }
        r = requests.post(f"{API}/superadmin/users", json=body, headers=sa_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "genbrug_plads"
        assert data["is_hq_admin"] is False
        assert data["assigned_plads_ids"] == ["plads-aaa", "plads-bbb"]
        assert "id" in data
        created_users.append(data["id"])

        # Verify via GET list
        r2 = requests.get(f"{API}/superadmin/users", headers=sa_headers, timeout=10)
        assert r2.status_code == 200
        u = next((x for x in r2.json() if x.get("id") == data["id"]), None)
        assert u is not None
        assert u["is_hq_admin"] is False
        assert u["assigned_plads_ids"] == ["plads-aaa", "plads-bbb"]

    def test_create_genbrug_hq_user_persists_is_hq_admin_true(self, sa_headers, default_company_id, created_users):
        email = f"TEST_hq_{uuid.uuid4().hex[:8]}@default.local"
        body = {
            "email": email,
            "name": "TEST HQ User",
            "password": "Test2026!",
            "role": "genbrug_plads",
            "company_id": default_company_id,
            "is_hq_admin": True,
            "assigned_plads_ids": [],
        }
        r = requests.post(f"{API}/superadmin/users", json=body, headers=sa_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_hq_admin"] is True
        assert data["assigned_plads_ids"] == []
        created_users.append(data["id"])

    def test_put_user_updates_assigned_plads(self, sa_headers, default_company_id, created_users):
        # create
        email = f"TEST_upd_{uuid.uuid4().hex[:8]}@default.local"
        cr = requests.post(f"{API}/superadmin/users", json={
            "email": email, "name": "X", "password": "Test2026!",
            "role": "genbrug_plads", "company_id": default_company_id,
            "is_hq_admin": False, "assigned_plads_ids": []
        }, headers=sa_headers, timeout=15)
        assert cr.status_code == 200
        uid = cr.json()["id"]
        created_users.append(uid)

        # update
        up = requests.put(f"{API}/superadmin/users/{uid}", json={
            "is_hq_admin": True, "assigned_plads_ids": ["x1", "x2"]
        }, headers=sa_headers, timeout=15)
        assert up.status_code == 200, up.text
        d = up.json()
        assert d["is_hq_admin"] is True
        assert d["assigned_plads_ids"] == ["x1", "x2"]

    def test_data_hygiene_role_change_clears_genbrug_fields(self, sa_headers, default_company_id, created_users):
        email = f"TEST_hyg_{uuid.uuid4().hex[:8]}@default.local"
        cr = requests.post(f"{API}/superadmin/users", json={
            "email": email, "name": "Hyg", "password": "Test2026!",
            "role": "genbrug_plads", "company_id": default_company_id,
            "is_hq_admin": True, "assigned_plads_ids": ["a", "b"]
        }, headers=sa_headers, timeout=15)
        assert cr.status_code == 200
        uid = cr.json()["id"]
        created_users.append(uid)

        # change role to logistics_admin
        up = requests.put(f"{API}/superadmin/users/{uid}",
                          json={"role": "logistics_admin"},
                          headers=sa_headers, timeout=15)
        assert up.status_code == 200, up.text
        d = up.json()
        assert d["role"] == "logistics_admin"
        assert d["is_hq_admin"] is False, "is_hq_admin should be cleared on role change"
        assert d["assigned_plads_ids"] == [], "assigned_plads_ids should be cleared on role change"


# ---------- (a) login / me public payload ----------

class TestUserPublicPayload:
    def test_login_response_contains_new_fields(self):
        r = requests.post(f"{API}/auth/login", json=GENBRUG, timeout=10)
        assert r.status_code == 200
        body = r.json()
        user = body.get("user", body)
        assert "is_hq_admin" in user
        assert "assigned_plads_ids" in user
        assert isinstance(user["assigned_plads_ids"], list)

    def test_me_returns_new_fields(self, gen_headers):
        r = requests.get(f"{API}/auth/me", headers=gen_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "is_hq_admin" in d
        assert "assigned_plads_ids" in d


# ---------- (a) genbrug_plads_rapport filter ----------

class TestPladsRapportSiteFilter:
    """Sets up the default genbrug user as HQ / Site and verifies filtering."""

    @pytest.fixture(scope="class")
    def genbrug_user_id(self, sa_headers):
        r = requests.get(f"{API}/superadmin/users", headers=sa_headers, timeout=10)
        assert r.status_code == 200
        u = next((x for x in r.json() if x.get("email") == GENBRUG["email"]), None)
        assert u, "default genbrug user not found"
        return u["id"]

    @pytest.fixture(scope="class")
    def default_plads_list(self, sa_headers, default_company_id):
        r = requests.get(f"{API}/superadmin/plads",
                         headers=sa_headers, timeout=10,
                         params={"company_id": default_company_id})
        assert r.status_code == 200
        items = r.json()
        # filter only items of default company
        items = [p for p in items if p.get("company_id") == default_company_id]
        assert len(items) >= 1, "default company must have at least one plads"
        return items

    def test_hq_admin_sees_unfiltered(self, sa_headers, genbrug_user_id):
        # Mark default genbrug user as HQ
        up = requests.put(f"{API}/superadmin/users/{genbrug_user_id}",
                          json={"is_hq_admin": True, "assigned_plads_ids": []},
                          headers=sa_headers, timeout=15)
        assert up.status_code == 200, up.text
        # Login as genbrug to get fresh token (claims may not embed new fields)
        token = _login(GENBRUG)
        gh = {"Authorization": f"Bearer {token}"}
        # Just verify endpoint returns 200 (no plads filter applied)
        r = requests.get(f"{API}/genbrug/plads-rapport?period=month", headers=gh, timeout=15)
        assert r.status_code == 200, r.text
        # Could be empty in test env – that's fine; just must be a list
        assert isinstance(r.json(), list)

    def test_site_user_empty_assignments_returns_empty(self, sa_headers, genbrug_user_id):
        up = requests.put(f"{API}/superadmin/users/{genbrug_user_id}",
                          json={"is_hq_admin": False, "assigned_plads_ids": []},
                          headers=sa_headers, timeout=15)
        assert up.status_code == 200, up.text
        token = _login(GENBRUG)
        gh = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API}/genbrug/plads-rapport?period=month", headers=gh, timeout=15)
        assert r.status_code == 200
        assert r.json() == [], "Site user with no assignments must see []"

    def test_site_user_assigned_filters_by_plads_name(self, sa_headers, genbrug_user_id, default_plads_list, default_company_id):
        # Pick one plads
        chosen = default_plads_list[0]
        # Create a TEST tour referencing that plads
        # We don't have a public tour-create endpoint that lets us drop arbitrary plads;
        # use the raw DB indirectly via a dummy approach: skip if endpoint not available.
        # Instead, validate filter by ensuring the response only contains tours whose
        # plads name equals the chosen plads name (or empty if none in db).
        up = requests.put(f"{API}/superadmin/users/{genbrug_user_id}",
                          json={"is_hq_admin": False, "assigned_plads_ids": [chosen["id"]]},
                          headers=sa_headers, timeout=15)
        assert up.status_code == 200, up.text
        token = _login(GENBRUG)
        gh = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API}/genbrug/plads-rapport?period=month", headers=gh, timeout=15)
        assert r.status_code == 200, r.text
        tours = r.json()
        for t in tours:
            assert t.get("plads") == chosen["name"], (
                f"Site filter leak: tour.plads={t.get('plads')} != assigned {chosen['name']}"
            )

    def test_restore_default_genbrug_user(self, sa_headers, genbrug_user_id):
        """Reset default user to clean state after tests (is_hq_admin=False, empty assignments)."""
        up = requests.put(f"{API}/superadmin/users/{genbrug_user_id}",
                          json={"is_hq_admin": False, "assigned_plads_ids": []},
                          headers=sa_headers, timeout=15)
        assert up.status_code == 200


# ---------- (b) Plads Merge ----------

class TestPladsMerge:
    def test_merge_same_source_and_target_returns_400(self, sa_headers, default_company_id, created_plads):
        r = requests.post(f"{API}/superadmin/plads",
                          json={"company_id": default_company_id, "name": f"TEST_merge_same_{uuid.uuid4().hex[:6]}"},
                          headers=sa_headers, timeout=10)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        created_plads.append(pid)
        rr = requests.post(f"{API}/superadmin/plads/merge",
                           json={"source_id": pid, "target_id": pid},
                           headers=sa_headers, timeout=10)
        assert rr.status_code == 400, rr.text

    def test_merge_missing_ids_returns_404(self, sa_headers):
        rr = requests.post(f"{API}/superadmin/plads/merge",
                           json={"source_id": "nonexist-xxx", "target_id": "nonexist-yyy"},
                           headers=sa_headers, timeout=10)
        assert rr.status_code == 404

    def test_merge_endpoint_requires_super_admin(self, gen_headers):
        rr = requests.post(f"{API}/superadmin/plads/merge",
                           json={"source_id": "a", "target_id": "b"},
                           headers=gen_headers, timeout=10)
        assert rr.status_code in (401, 403), f"Expected unauthorized; got {rr.status_code} {rr.text}"

    def test_full_merge_flow(self, sa_headers, default_company_id, created_plads, created_users):
        # 1) Create 2 plads
        src_name = f"TEST_merge_src_{uuid.uuid4().hex[:6]}"
        tgt_name = f"TEST_merge_tgt_{uuid.uuid4().hex[:6]}"
        rs = requests.post(f"{API}/superadmin/plads",
                           json={"company_id": default_company_id, "name": src_name, "city": "TestCity"},
                           headers=sa_headers, timeout=10)
        assert rs.status_code == 200, rs.text
        src = rs.json()
        rt = requests.post(f"{API}/superadmin/plads",
                           json={"company_id": default_company_id, "name": tgt_name, "city": "TestCity"},
                           headers=sa_headers, timeout=10)
        assert rt.status_code == 200, rt.text
        tgt = rt.json()
        created_plads.append(tgt["id"])  # source will be deleted by merge, only track tgt

        # 2) Create a sub-address under src
        ar = requests.post(f"{API}/superadmin/plads/{src['id']}/addresses",
                           json={"sub_area": "Test", "street": "Testvej 1", "city": "TestCity"},
                           headers=sa_headers, timeout=10)
        assert ar.status_code == 200, ar.text

        # 3) Create a genbrug_plads site user that has src assigned
        email = f"TEST_mergeuser_{uuid.uuid4().hex[:6]}@default.local"
        ur = requests.post(f"{API}/superadmin/users", json={
            "email": email, "name": "MergeUser", "password": "Test2026!",
            "role": "genbrug_plads", "company_id": default_company_id,
            "is_hq_admin": False, "assigned_plads_ids": [src["id"]]
        }, headers=sa_headers, timeout=15)
        assert ur.status_code == 200, ur.text
        uid = ur.json()["id"]
        created_users.append(uid)

        # 4) Insert a tour into DB referencing src.name directly via Mongo
        #    (no public tour-create with arbitrary plads). Use a helper endpoint.
        #    We'll use a python mongo connection to the same DB.
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]
        tour_id = f"TEST_tour_{uuid.uuid4().hex[:8]}"

        async def insert_tour():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            await db.tours.insert_one({
                "id": tour_id,
                "plads": src_name,
                "company_id": default_company_id,
                "date": "2026-01-15",
                "completed": True,
                "is_pause": False,
                "fraction": "Træ",
                "address": "Testvej 1",
                "weight": 100,
            })
            client.close()
        asyncio.get_event_loop().run_until_complete(insert_tour())

        try:
            # 5) Perform merge
            mr = requests.post(f"{API}/superadmin/plads/merge",
                               json={"source_id": src["id"], "target_id": tgt["id"]},
                               headers=sa_headers, timeout=20)
            assert mr.status_code == 200, mr.text
            body = mr.json()
            assert body["success"] is True
            assert body["source_id"] == src["id"]
            assert body["target_id"] == tgt["id"]
            moved = body["moved"]
            assert moved["tours"] >= 1, f"expected >=1 tour moved, got {moved}"
            assert moved["addresses"] >= 1, f"expected >=1 address moved, got {moved}"
            assert moved["user_assignments"] >= 1, f"expected >=1 user reassignment, got {moved}"

            # 6) Verify tour was repointed
            async def fetch_tour():
                client = AsyncIOMotorClient(mongo_url)
                db = client[db_name]
                t = await db.tours.find_one({"id": tour_id}, {"_id": 0})
                client.close()
                return t
            t = asyncio.get_event_loop().run_until_complete(fetch_tour())
            assert t is not None
            assert t["plads"] == tgt_name, f"tour.plads not updated: {t}"

            # 7) Source plads deleted
            chk = requests.get(f"{API}/superadmin/plads", headers=sa_headers, timeout=10,
                               params={"company_id": default_company_id})
            ids = [p["id"] for p in chk.json()]
            assert src["id"] not in ids, "source plads should be deleted after merge"
            assert tgt["id"] in ids

            # 8) User assigned_plads_ids swap
            ulist = requests.get(f"{API}/superadmin/users", headers=sa_headers, timeout=10).json()
            u = next((x for x in ulist if x["id"] == uid), None)
            assert u is not None
            assert src["id"] not in (u.get("assigned_plads_ids") or [])
            assert tgt["id"] in (u.get("assigned_plads_ids") or [])
        finally:
            async def cleanup_tour():
                client = AsyncIOMotorClient(mongo_url)
                db = client[db_name]
                await db.tours.delete_one({"id": tour_id})
                client.close()
            try:
                asyncio.get_event_loop().run_until_complete(cleanup_tour())
            except Exception:
                pass
