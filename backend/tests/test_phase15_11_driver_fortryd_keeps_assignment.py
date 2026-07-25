"""Fase 15.11 — Chauffør kan fortryde PÅ VEJ på admin-tildelte ture,
men tildelingen (driver_id + assigned_by_*) skal forblive intakt.

Tester at sekvensen:
  1. Admin tildeler tur til driver
  2. Driver markerer PÅ VEJ
  3. Driver klikker Fortryd
  -> tour.on_way=False, claimed_by="", men driver_id og assigned_by_* bevares.
"""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL skal være sat"
API = f"{BASE_URL}/api"

ADMIN = ("ilkdistadmin@gmail.com", "TestPass2026!")
DRIVER = ("testx", "TestC2026!")
DRIVER_ID = "b8a3dddc-25c3-48e2-b775-ae1967b3a024"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _find_assigned_venter_tour(token: str) -> str | None:
    r = requests.get(f"{API}/tours?limit=500", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    tours = r.json() if isinstance(r.json(), list) else r.json().get("tours", [])
    for t in tours:
        if (t.get("driver_id") == DRIVER_ID
            and (t.get("assigned_by_name") or "").strip()
            and not t.get("on_way")
            and not t.get("completed")):
            return t["id"]
    return None


def test_driver_can_fortryd_on_assigned_tour_keeps_assignment():
    """Driver klikker PÅ VEJ → Fortryd. Tildeling bevares."""
    drv_tok = _login(*DRIVER)
    h = {"Authorization": f"Bearer {drv_tok}"}

    tour_id = _find_assigned_venter_tour(drv_tok)
    assert tour_id, "Skal være en tildelt VENTER-tur til testx for testen"

    # 1. PÅ VEJ
    r = requests.put(
        f"{API}/tours/{tour_id}",
        headers=h,
        json={
            "on_way": True,
            "on_way_time": "10:00",
            "claimed_by": "testx",
            "claimed_by_id": DRIVER_ID,
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["on_way"] is True
    assert t["claimed_by"] == "testx"

    # 2. Fortryd
    r = requests.put(
        f"{API}/tours/{tour_id}",
        headers=h,
        json={
            "claimed_by": "",
            "claimed_by_id": "",
            "on_way": False,
            "completed": False,
            "time": "",
            "on_way_time": "",
            "weight": 0,
        },
        timeout=15,
    )
    assert r.status_code == 200, f"Fortryd skal være tilladt: {r.text}"
    t = r.json()
    # 3. Verificer: tildeling bevaret, status = VENTER
    assert t["on_way"] is False, "Skal være VENTER efter Fortryd"
    assert (t.get("claimed_by") or "") == "", "claimed_by skal være tom"
    assert t.get("driver_id") == DRIVER_ID, "driver_id skal bevares"
    assert (t.get("assigned_by_name") or "").strip(), "assigned_by_name skal bevares"
    assert (t.get("assigned_by_id") or "").strip(), "assigned_by_id skal bevares"
