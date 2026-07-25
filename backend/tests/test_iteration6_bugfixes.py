"""Iteration 6 backend tests:
- Bug fix: order user `erik@erik.dk` can log in & resolve location 2076 (plads-only)
- Regression: /api/locations/code/{code} for legacy codes 3030 & 3131; 404 on miss
- Regression: /api/locations/{code}/materials & /api/customer-orders/submit for code 2076
- Backend: /api/tours driver response enriched with customer_name & customer_code
"""
import os
import requests
import pytest

API = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")


def _login(email, password):
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    return r


class TestOrderLoginPladsFallback:
    """Bug fix: order user with location_code in `plads`-only collection."""

    def test_erik_can_login(self):
        r = _login("erik@erik.dk", "erik2026")
        assert r.status_code == 200, r.text
        body = r.json()
        # accept both 'token' and 'access_token' shape
        assert body.get("token") or body.get("access_token"), body
        user = body.get("user") or {}
        assert user.get("role") == "order", user
        assert user.get("location_code") == "2076", user

    def test_locations_code_2076_resolves_via_plads(self):
        r = requests.get(f"{API}/api/locations/code/2076", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("code") == "2076"
        # Source must be the plads collection (the whole point of the fix)
        assert body.get("_source") == "plads", body
        # Must mention Køge (per problem statement)
        name_or_city = (body.get("name") or "") + " " + (body.get("city") or "")
        assert "Køge" in name_or_city or "koge" in name_or_city.lower(), body


class TestLegacyLocationCodeLookup:
    """Regression: legacy 3030 + 3131 still resolve, missing returns 404."""

    def test_legacy_3030(self):
        r = requests.get(f"{API}/api/locations/code/3030", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("code") == "3030"
        assert body.get("name")  # has name
        assert isinstance(body.get("materials", []), list)

    def test_legacy_3131(self):
        r = requests.get(f"{API}/api/locations/code/3131", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("code") == "3131"
        assert body.get("name")

    def test_missing_code_404(self):
        r = requests.get(f"{API}/api/locations/code/ZZZ-NOPE-00000", timeout=15)
        assert r.status_code == 404


class TestMaterialsAndOrderSubmitForPladsCode:
    """Regression: /api/locations/{code}/materials and customer-orders/submit accept plads-only code 2076."""

    def test_materials_endpoint_2076(self):
        r = requests.get(f"{API}/api/locations/2076/materials", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("location"), body
        assert isinstance(body.get("materials", []), list)

    def test_customer_order_submit_2076(self):
        payload = {
            "location_code": "2076",
            "name": "PYTEST iteration6",
            "phone": "+4500000000",
            "material": (
                requests.get(f"{API}/api/locations/2076/materials", timeout=10).json().get("materials") or ["Pap til HCS"]
            )[0],
            "weight": 12,
            "notes": "iteration6 regression",
            "container_number": "PYTEST-CT-6",
        }
        r = requests.post(f"{API}/api/customer-orders/submit", json=payload, timeout=15)
        # Some impls demand additional fields; accept 200/201 or detail-rich 400
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text}"
        body = r.json()
        # response should reference our location somehow
        assert body.get("order_id"), body
        assert "K" in (body.get("genbrugsplads") or "") or "Køge" in (body.get("genbrugsplads") or ""), body


class TestDriverToursEnrichment:
    """Drivers see customer_name & customer_code populated for cross-company tours."""

    def _get_logistics_token(self):
        # bo@ilk.dk with ARGO password is a logistics_admin
        r = _login("bo@ilk.dk", "argopass123")
        if r.status_code != 200:
            pytest.skip(f"logistics admin login failed: {r.status_code} {r.text}")
        return r.json().get("token") or r.json().get("access_token")

    def test_tours_have_customer_name_and_code_fields(self):
        token = self._get_logistics_token()
        r = requests.get(f"{API}/api/tours", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200, r.text
        tours = r.json()
        if not isinstance(tours, list):
            tours = tours.get("tours", []) if isinstance(tours, dict) else []
        if not tours:
            pytest.skip("no tours present in env, cannot assert enrichment shape")
        for t in tours:
            # Fields must be present in payload (may be empty strings)
            assert "customer_name" in t, f"missing customer_name: {t}"
            assert "customer_code" in t, f"missing customer_code: {t}"
            assert isinstance(t["customer_name"], str)
            assert isinstance(t["customer_code"], str)
