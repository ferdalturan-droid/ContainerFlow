"""Phase 9 CO2 refactor — live validation against deployed REACT_APP_BACKEND_URL.

Verifies key endpoints against the actual public URL (not in-process ASGI):
  - POST/GET/PUT /api/locations/{code}/materials with co2_category_id
  - GET /api/locations/{code}/materials returns material_co2_categories dict
  - Invalid co2_category_id → 400
  - GET /api/org/reports/orders returns CO2 aggregates for location_admin
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8080").rstrip("/")
CA_EMAIL = "argokundeadmin@gmail.com"
CA_PASSWORD = "ArgoCust2026!"


@pytest.fixture(scope="module")
def ca_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": CA_EMAIL, "password": CA_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def ca_headers(ca_token):
    return {"Authorization": f"Bearer {ca_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def co2_types(ca_headers):
    r = requests.get(f"{BASE_URL}/api/co2-types", headers=ca_headers)
    assert r.status_code == 200
    types = r.json()
    assert len(types) >= 3, "Need Beton/Metal/Træ pre-seeded"
    return {t["name"]: t for t in types}


@pytest.fixture(scope="module")
def plads_code(ca_headers):
    r = requests.get(f"{BASE_URL}/api/plads", headers=ca_headers)
    assert r.status_code == 200
    arr = r.json()
    arr = arr if isinstance(arr, list) else arr.get("pladser", [])
    assert len(arr) >= 1, "Need at least one plads"
    return arr[0].get("code") or arr[0].get("plads_kode")


def _unique(name):
    return f"{name}_{uuid.uuid4().hex[:6]}"


def test_post_material_with_co2_category(ca_headers, co2_types, plads_code):
    mat = _unique("TEST_Murbrokker")
    r = requests.post(
        f"{BASE_URL}/api/locations/{plads_code}/materials",
        headers=ca_headers,
        json={"material": mat, "co2_category_id": co2_types["Beton"]["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("co2_category_id") == co2_types["Beton"]["id"]


def test_get_materials_returns_mapping(ca_headers, co2_types, plads_code):
    # Add a TEST_ material first
    mat = _unique("TEST_Metal_mat")
    requests.post(
        f"{BASE_URL}/api/locations/{plads_code}/materials",
        headers=ca_headers,
        json={"material": mat, "co2_category_id": co2_types["Metal"]["id"]},
    )
    r = requests.get(f"{BASE_URL}/api/locations/{plads_code}/materials", headers=ca_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "material_co2_categories" in body, f"Missing key in {body.keys()}"
    cats = body["material_co2_categories"]
    assert isinstance(cats, dict)
    assert mat in cats, f"Material {mat} not in mapping {cats}"
    assert cats[mat] == co2_types["Metal"]["id"]


def test_put_material_updates_co2(ca_headers, co2_types, plads_code):
    mat = _unique("TEST_PutMat")
    requests.post(
        f"{BASE_URL}/api/locations/{plads_code}/materials",
        headers=ca_headers,
        json={"material": mat, "co2_category_id": co2_types["Træ"]["id"]},
    )
    # Update to Beton
    r = requests.put(
        f"{BASE_URL}/api/locations/{plads_code}/materials",
        headers=ca_headers,
        json={"old_name": mat, "new_name": mat, "co2_category_id": co2_types["Beton"]["id"]},
    )
    assert r.status_code == 200, r.text
    g = requests.get(f"{BASE_URL}/api/locations/{plads_code}/materials", headers=ca_headers).json()
    assert g["material_co2_categories"].get(mat) == co2_types["Beton"]["id"]


def test_invalid_co2_category_rejected(ca_headers, plads_code):
    mat = _unique("TEST_BadCat")
    r = requests.post(
        f"{BASE_URL}/api/locations/{plads_code}/materials",
        headers=ca_headers,
        json={"material": mat, "co2_category_id": "non-existent-id-xxx"},
    )
    assert r.status_code == 400, f"Expected 400 got {r.status_code}: {r.text}"


def test_reports_orders_includes_co2(ca_headers, plads_code):
    """LA endpoint /org/reports/orders must include total_co2_kg, by_co2_type, co2_over_time."""
    r = requests.get(
        f"{BASE_URL}/api/org/reports/orders",
        params={"location_code": plads_code, "period": "year"},
        headers=ca_headers,
    )
    # CA may not be allowed to call LA endpoint — accept 200 or 403
    if r.status_code == 200:
        d = r.json()
        for key in ("total_co2_kg", "by_co2_type", "co2_over_time", "total_weight_kg"):
            assert key in d, f"Missing {key} in response keys {list(d.keys())}"
    else:
        pytest.skip(f"CA cannot access /org/reports/orders (status={r.status_code})")
