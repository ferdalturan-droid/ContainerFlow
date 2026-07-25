"""Regression: /api/locations/code/{code} must resolve codes that live on the
new `plads` collection (post legacy-locations migration), so that the `order`
role can log in and load its site without a 404 "Location not found".
"""
import os
import asyncio
import uuid
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import requests

API = os.environ.get("BACKEND_URL", "http://localhost:8001")


@pytest.fixture(scope="module")
def db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name]


def _await(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def plads_with_code(db):
    """Seed a plads document with a customer-facing code, then clean it up."""
    code = "TEST" + str(uuid.uuid4().int)[:4]
    plads_id = str(uuid.uuid4())
    doc = {
        "id": plads_id,
        "name": "PYTEST PLADS " + code,
        "city": "Køge",
        "address": "Test 1",
        "code": code,
        "location_code": code,
        "active": True,
        "company_id": "test-company-lookup",
        "materials": ["Pap til HCS"],
    }
    _await(db.plads.insert_one(doc))
    yield {"code": code, "plads_id": plads_id, "name": doc["name"]}
    _await(db.plads.delete_one({"id": plads_id}))


class TestLocationCodeLookupFallback:
    def test_plads_code_resolves_via_locations_endpoint(self, plads_with_code):
        r = requests.get(f"{API}/api/locations/code/{plads_with_code['code']}", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == plads_with_code["code"]
        assert body["name"] == plads_with_code["name"]
        assert body.get("_source") == "plads"
        # materials list is preserved
        assert "Pap til HCS" in (body.get("materials") or [])

    def test_unknown_code_still_404(self):
        r = requests.get(f"{API}/api/locations/code/ZZZZ-NOPE-{uuid.uuid4().hex[:8]}", timeout=10)
        assert r.status_code == 404

    def test_materials_endpoint_resolves_via_plads(self, plads_with_code):
        r = requests.get(
            f"{API}/api/locations/{plads_with_code['code']}/materials", timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["location"] == plads_with_code["name"]
        assert "Pap til HCS" in body["materials"]
