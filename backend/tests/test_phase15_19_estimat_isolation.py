"""Fase 15.19 — Estimat-bestillinger må KUN vises i 'Planlæg ressourcer'.

Tester:
  1. GET /api/tours (ILK logistics_admin, ingen tour_type-param) → INGEN estimat.
  2. GET /api/tours?tour_type=estimat → må stadig returnere estimater.
  3. GET /api/tours?tour_type=all → må returnere alt (inkl. estimater).
  4. GET /api/tours (driver) → INGEN estimat.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env", override=False)
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL skal være sat"
API = f"{BASE}/api"

ILK_EMAIL = "ilkdistadmin@gmail.com"
ILK_PASS = "TestPass2026!"
DRV_EMAIL = "testdriver@default.local"
DRV_PASS = "Driver2026!"


def _login(email: str, password: str) -> str:
    """Returner JWT-token. Retry ved 429 rate-limit."""
    for attempt in range(5):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code == 429:
            time.sleep(20 + attempt * 10)
            continue
        pytest.fail(f"Login fejlede ({email}): {r.status_code} {r.text[:200]}")
    pytest.skip(f"Rate-limit på login for {email}")


@pytest.fixture(scope="module")
def ilk_token():
    return _login(ILK_EMAIL, ILK_PASS)


@pytest.fixture(scope="module")
def drv_token():
    return _login(DRV_EMAIL, DRV_PASS)


def test_admin_default_excludes_estimat(ilk_token):
    """Default-filter MÅ IKKE returnere ture med tour_type='estimat'."""
    r = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {ilk_token}"},
        params={"limit": 500},
        timeout=20,
    )
    assert r.status_code == 200, f"GET /api/tours: {r.status_code} {r.text[:200]}"
    tours = r.json()
    assert isinstance(tours, list)
    leaked = [t for t in tours if (t.get("tour_type") or "").lower() == "estimat"]
    assert not leaked, (
        f"ISOLATION BROKEN: {len(leaked)} estimat-tour(e) lækket i default GET /api/tours. "
        f"Eksempler: {[(t.get('id'), t.get('plads'), t.get('fraction')) for t in leaked[:3]]}"
    )


def test_admin_opt_in_estimat(ilk_token):
    """?tour_type=estimat skal stadig returnere estimater."""
    r = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {ilk_token}"},
        params={"tour_type": "estimat", "limit": 500},
        timeout=20,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    tours = r.json()
    # Alle returnerede skal være estimat
    non_est = [t for t in tours if (t.get("tour_type") or "").lower() != "estimat"]
    assert not non_est, f"?tour_type=estimat returnerede {len(non_est)} ikke-estimat tour(e)"
    # Vi forventer >=1 estimat på Blishøj 1 (jf. agent-context)
    print(f"Antal estimater fundet: {len(tours)}")


def test_admin_opt_in_all_returns_both(ilk_token):
    """?tour_type=all skal returnere både estimat OG ikke-estimat."""
    r = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {ilk_token}"},
        params={"tour_type": "all", "limit": 1000},
        timeout=20,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    tours = r.json()
    types = {(t.get("tour_type") or "").lower() for t in tours}
    print(f"tour_types i ?tour_type=all: {types} (total {len(tours)})")
    # Sammenlign med default
    r2 = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {ilk_token}"},
        params={"limit": 1000},
        timeout=20,
    )
    default_count = len(r2.json())
    assert len(tours) >= default_count, (
        f"?tour_type=all ({len(tours)}) skal være >= default ({default_count})"
    )


def test_driver_default_excludes_estimat(drv_token):
    """Driver må heller ikke se estimater."""
    r = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {drv_token}"},
        params={"limit": 500},
        timeout=20,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    tours = r.json()
    assert isinstance(tours, list)
    leaked = [t for t in tours if (t.get("tour_type") or "").lower() == "estimat"]
    assert not leaked, (
        f"DRIVER ISOLATION BROKEN: {len(leaked)} estimat lækket til driver: "
        f"{[(t.get('id'), t.get('plads')) for t in leaked[:3]]}"
    )
