"""Fase 15.8 — assigned_by_name skal vise display-navn fra DB,
ikke email fra JWT-payload (fallback).

Tester at når en logistik-admin tildeler en tur til en chauffør, gemmes det
menneskelæsbare display-navn (fx "ILK Dist Admin") i tour.assigned_by_name —
IKKE admin'ens email ("ilkdistadmin@gmail.com").
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL skal være sat"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "ilkdistadmin@gmail.com"
ADMIN_PASSWORD = "TestPass2026!"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def test_assigned_by_name_is_display_name_not_email():
    """Når en admin tildeler en tur, skal assigned_by_name være display-navn."""
    token = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    h = {"Authorization": f"Bearer {token}"}

    # Hent alle ture, find én med assigned_by_name sat
    r = requests.get(f"{API}/tours?limit=500", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    tours = r.json() if isinstance(r.json(), list) else r.json().get("tours", [])
    assigned = [t for t in tours if (t.get("assigned_by_name") or "").strip()]
    assert assigned, "Forventede mindst én tur med assigned_by_name"

    # Ingen af de assigned ture må have @ i navnet (= email)
    for t in assigned:
        name = (t.get("assigned_by_name") or "").strip()
        assert "@" not in name, f"Tour {t.get('tour_number')} har email som assigned_by_name: {name!r}"
        assert len(name) >= 3, f"Tour {t.get('tour_number')} har for kort navn: {name!r}"
