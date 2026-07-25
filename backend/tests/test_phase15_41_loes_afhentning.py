"""Fase 15.41 — Løs afhentning (tour_type=loes_afhentning).

Tester:
  T1: Bestilling med tour_type='loes_afhentning' + loose_estimated_count=5
      opretter et order + tour med korrekte felter.
  T2: Bestilling uden loose_estimated_count → 400.
  T3: PATCH tour med container_weights=[150,220,180] auto-beregner
      weight=550. Tour vises hos chauffør.
  T4: PATCH tour med container_weights=[] OG completed=True → 400
      ("Mindst én container-vægt > 0...").
  T5: PATCH tour med container_weights=[100,200] OG completed=True →
      success. weight=300, completed=True. co2_kg=0.
  T6: container_weights gemt på selve ordren også (så Mine bestillinger
      kan vise dem).
  T7: GET /tours med tour_type=estimat returnerer IKKE loes_afhentning og
      omvendt.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _backend_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if val:
        return val.rstrip("/")
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


def _mongo():
    env = Path("/app/backend/.env")
    url = "mongodb://localhost:27017"
    db = "test_database"
    for line in env.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("DB_NAME="):
            db = line.split("=", 1)[1].strip().strip('"')
    return url, db


API_URL = _backend_url()
MONGO_URL, DB_NAME = _mongo()


def _login(email, password, attempts=4):
    last = None
    for i in range(attempts):
        try:
            r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
            if r.status_code == 200:
                d = r.json()
                return d.get("access_token") or d.get("token") or ""
            last = (r.status_code, r.text)
        except Exception as e:  # noqa: BLE001
            last = ("exc", str(e))
        time.sleep(5 + i * 3)
    raise RuntimeError(f"login failed: {last}")


SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASSWORD = "TestSAreset2026!"


@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PASSWORD)


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def multi_partner_plads(mongo_db):
    p = mongo_db.plads.find_one(
        {"assigned_logistics_company_ids.0": {"$exists": True}},
        {"_id": 0, "location_code": 1, "name": 1, "assigned_logistics_company_ids": 1, "company_id": 1},
    )
    assert p, "Mindst én plads med en logistik-partner skal findes for at køre testen"
    return p


_SEED_KEY = "__phase15_41_seed__"


@pytest.fixture(autouse=True)
def cleanup(mongo_db):
    mongo_db.container_orders.delete_many({_SEED_KEY: True})
    mongo_db.tours.delete_many({_SEED_KEY: True})
    yield
    mongo_db.container_orders.delete_many({_SEED_KEY: True})
    mongo_db.tours.delete_many({_SEED_KEY: True})


def _submit_loes(mongo_db, multi_partner_plads, count, marker):
    partner = multi_partner_plads["assigned_logistics_company_ids"][0]
    r = requests.post(
        f"{API_URL}/api/customer-orders/submit",
        json={
            "location_code": multi_partner_plads["location_code"],
            "material": "Pap",
            "container_number": "Løs afhentning",
            "priority": "normal",
            "tour_type": "loes_afhentning",
            "custom_address": f"Testvej 1, 4000 Test — {marker}",
            "loose_estimated_count": count,
            "partner_id": partner,
        },
        timeout=15,
    )
    if r.status_code == 200:
        body = r.json()
        mongo_db.container_orders.update_one({"id": body["order_id"]}, {"$set": {_SEED_KEY: True, "_marker": marker}})
        mongo_db.tours.update_one({"id": body["tour_id"]}, {"$set": {_SEED_KEY: True, "_marker": marker}})
    return r


# --- tests ------------------------------------------------------------------

def test_T1_creates_order_and_tour_with_correct_fields(mongo_db, multi_partner_plads):
    marker = uuid.uuid4().hex[:8]
    r = _submit_loes(mongo_db, multi_partner_plads, 5, marker)
    assert r.status_code == 200, r.text
    body = r.json()
    o = mongo_db.container_orders.find_one({"id": body["order_id"]})
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert o["tour_type"] == "loes_afhentning"
    assert o["loose_estimated_count"] == 5
    assert o.get("container_weights") == []
    assert t["tour_type"] == "loes_afhentning"
    assert t["loose_estimated_count"] == 5
    assert t.get("container_weights") == []


def test_T2_zero_count_rejected(multi_partner_plads):
    partner = multi_partner_plads["assigned_logistics_company_ids"][0]
    r = requests.post(
        f"{API_URL}/api/customer-orders/submit",
        json={
            "location_code": multi_partner_plads["location_code"],
            "material": "Pap",
            "container_number": "Løs",
            "priority": "normal",
            "tour_type": "loes_afhentning",
            "custom_address": "Testvej 1",
            "loose_estimated_count": 0,
            "partner_id": partner,
        },
        timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "antal" in (r.json().get("detail") or "").lower() or "estim" in (r.json().get("detail") or "").lower()


def test_T3_patch_container_weights_autocomputes_sum(sa_token, mongo_db, multi_partner_plads):
    r = _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    tour_id = r.json()["tour_id"]
    upd = requests.put(
        f"{API_URL}/api/tours/{tour_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [150, 220, 180]},
        timeout=15,
    )
    assert upd.status_code == 200, upd.text
    t = mongo_db.tours.find_one({"id": tour_id})
    assert t["container_weights"] == [150.0, 220.0, 180.0]
    assert abs(t["weight"] - 550.0) < 0.01
    # CO2 must remain 0 — customer owns no containers, no factor.
    assert (t.get("co2_kg") or 0) == 0.0


def test_T4_completion_without_weights_rejected(sa_token, mongo_db, multi_partner_plads):
    r = _submit_loes(mongo_db, multi_partner_plads, 2, uuid.uuid4().hex[:8])
    tour_id = r.json()["tour_id"]
    upd = requests.put(
        f"{API_URL}/api/tours/{tour_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": True, "container_weights": []},
        timeout=15,
    )
    assert upd.status_code == 400, upd.text
    assert "vægt" in (upd.json().get("detail") or "").lower() or "weight" in (upd.json().get("detail") or "").lower()


def test_T5_completion_with_weights_succeeds(sa_token, mongo_db, multi_partner_plads):
    r = _submit_loes(mongo_db, multi_partner_plads, 2, uuid.uuid4().hex[:8])
    tour_id = r.json()["tour_id"]
    order_id = r.json()["order_id"]
    upd = requests.put(
        f"{API_URL}/api/tours/{tour_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": True, "container_weights": [100, 200]},
        timeout=15,
    )
    assert upd.status_code == 200, upd.text
    t = mongo_db.tours.find_one({"id": tour_id})
    assert t["completed"] is True
    assert abs(t["weight"] - 300.0) < 0.01
    assert t["container_weights"] == [100.0, 200.0]
    assert (t.get("co2_kg") or 0) == 0.0
    # T6: mirror på ordren
    o = mongo_db.container_orders.find_one({"id": order_id})
    assert o.get("container_weights") == [100.0, 200.0]
    assert abs((o.get("weight") or 0) - 300.0) < 0.01


def test_T7_resource_planning_only_returns_correct_tour_type(sa_token, mongo_db, multi_partner_plads):
    """GET /api/tours?tour_type=loes_afhentning skal kun returnere
    loes_afhentning-ture, ikke estimat eller normal."""
    _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    r = requests.get(
        f"{API_URL}/api/tours?tour_type=loes_afhentning&limit=500",
        headers={"Authorization": f"Bearer {sa_token}"},
        timeout=15,
    )
    assert r.status_code == 200
    tours = r.json() if isinstance(r.json(), list) else r.json().get("tours", [])
    assert len(tours) >= 1
    assert all(t.get("tour_type") == "loes_afhentning" for t in tours)
