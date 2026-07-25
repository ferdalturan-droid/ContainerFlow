"""Fase 15.38 — Strikt partner-scope på kundebestillinger.

Den bestilling en medarbejder opretter på bestillingssiden SKAL kun være
synlig for den logistik-partner medarbejderen har valgt i partner-pickeren
— ikke for ALLE partnere knyttet til pladsen.

Tester:
  T1: Ordre med partner_id=A på en multi-partner plads → resulterer i ordre +
      tour med assigned_logistics_company_ids=[A] (ikke [A, B]).
  T2: Ordre uden partner_id (legacy QR-flow) → bevarer den oprindelige
      multi-partner-liste (backwards-compat).
  T3: Ordre med partner_id som IKKE er knyttet til pladsen → faldes tilbage
      til pladsens normale liste (defensiv default — undgår at "skjule" en
      ordre helt hvis pickeren sender forkert ID).
  T4: To ordrer på samme plads med hver sin partner_id → fuldstændig
      adskillelse i `assigned_logistics_company_ids`.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _backend_url() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if val:
        return val.rstrip("/")
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


def _mongo():
    env_path = Path("/app/backend/.env")
    mongo_url = "mongodb://localhost:27017"
    db_name = "test_database"
    for line in env_path.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            mongo_url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("DB_NAME="):
            db_name = line.split("=", 1)[1].strip().strip('"')
    return mongo_url, db_name


API_URL = _backend_url()
MONGO_URL, DB_NAME = _mongo()
_SEED_FLAG_MAT = "__phase15_38_seed_material__"


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def multi_partner_plads(mongo_db):
    """Locate a plads with ≥2 logistics partners and return its details."""
    p = mongo_db.plads.find_one(
        {"assigned_logistics_company_ids.1": {"$exists": True}},
        {"_id": 0, "location_code": 1, "name": 1, "assigned_logistics_company_ids": 1, "company_id": 1},
    )
    assert p, "Test forudsætter mindst én plads med ≥2 logistik-partnere"
    return p


@pytest.fixture
def cleanup_seed_orders(mongo_db):
    """Delete any orders/tours seeded by this test before AND after."""
    mongo_db.container_orders.delete_many({_SEED_FLAG_MAT: True})
    mongo_db.tours.delete_many({_SEED_FLAG_MAT: True})
    yield
    mongo_db.container_orders.delete_many({_SEED_FLAG_MAT: True})
    mongo_db.tours.delete_many({_SEED_FLAG_MAT: True})


def _submit(payload: dict) -> dict:
    r = requests.post(f"{API_URL}/api/customer-orders/submit", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _flag_after_insert(mongo_db, order_id: str, tour_id: str, marker: str):
    """Add the test-seed flag + a unique marker so cleanup_seed_orders can
    target only THIS test's docs."""
    mongo_db.container_orders.update_one({"id": order_id}, {"$set": {_SEED_FLAG_MAT: True, "_seed_marker": marker}})
    mongo_db.tours.update_one({"id": tour_id}, {"$set": {_SEED_FLAG_MAT: True, "_seed_marker": marker}})


# --- tests ------------------------------------------------------------------

def test_T1_partner_id_narrows_to_single(mongo_db, multi_partner_plads, cleanup_seed_orders):
    partner_a = multi_partner_plads["assigned_logistics_company_ids"][0]
    marker = f"T1-{uuid.uuid4().hex[:8]}"
    r = _submit({
        "location_code": multi_partner_plads["location_code"],
        "material": "Pap",
        "container_number": f"TestC-{marker}",
        "custom_address": f"Test {marker}",
        "partner_id": partner_a,
    })
    _flag_after_insert(mongo_db, r["order_id"], r["tour_id"], marker)
    o = mongo_db.container_orders.find_one({"id": r["order_id"]})
    t = mongo_db.tours.find_one({"id": r["tour_id"]})
    assert o["assigned_logistics_company_ids"] == [partner_a], o["assigned_logistics_company_ids"]
    assert t["assigned_logistics_company_ids"] == [partner_a], t["assigned_logistics_company_ids"]
    assert o["partner_id"] == partner_a


def test_T2_no_partner_id_keeps_legacy_multi(mongo_db, multi_partner_plads, cleanup_seed_orders):
    partners = multi_partner_plads["assigned_logistics_company_ids"]
    marker = f"T2-{uuid.uuid4().hex[:8]}"
    r = _submit({
        "location_code": multi_partner_plads["location_code"],
        "material": "Pap",
        "container_number": f"TestC-{marker}",
        "custom_address": f"Test {marker}",
        # NO partner_id → legacy QR-flow
    })
    _flag_after_insert(mongo_db, r["order_id"], r["tour_id"], marker)
    o = mongo_db.container_orders.find_one({"id": r["order_id"]})
    t = mongo_db.tours.find_one({"id": r["tour_id"]})
    assert set(o["assigned_logistics_company_ids"]) == set(partners), o["assigned_logistics_company_ids"]
    assert set(t["assigned_logistics_company_ids"]) == set(partners)


def test_T3_invalid_partner_id_falls_back(mongo_db, multi_partner_plads, cleanup_seed_orders):
    """Defensive: hvis pickeren sender et partner_id som IKKE er knyttet til
    pladsen, må vi ikke skjule ordren helt — vi falder tilbage til pladsens
    normale liste."""
    partners = multi_partner_plads["assigned_logistics_company_ids"]
    bogus = str(uuid.uuid4())
    assert bogus not in partners
    marker = f"T3-{uuid.uuid4().hex[:8]}"
    r = _submit({
        "location_code": multi_partner_plads["location_code"],
        "material": "Pap",
        "container_number": f"TestC-{marker}",
        "custom_address": f"Test {marker}",
        "partner_id": bogus,
    })
    _flag_after_insert(mongo_db, r["order_id"], r["tour_id"], marker)
    o = mongo_db.container_orders.find_one({"id": r["order_id"]})
    t = mongo_db.tours.find_one({"id": r["tour_id"]})
    assert set(o["assigned_logistics_company_ids"]) == set(partners)
    assert set(t["assigned_logistics_company_ids"]) == set(partners)


def test_T4_two_orders_strictly_separated(mongo_db, multi_partner_plads, cleanup_seed_orders):
    partners = multi_partner_plads["assigned_logistics_company_ids"]
    partner_a, partner_b = partners[0], partners[1]

    m1 = f"T4A-{uuid.uuid4().hex[:8]}"
    r1 = _submit({
        "location_code": multi_partner_plads["location_code"],
        "material": "Pap",
        "container_number": f"TestC-{m1}",
        "custom_address": f"Test {m1}",
        "partner_id": partner_a,
    })
    _flag_after_insert(mongo_db, r1["order_id"], r1["tour_id"], m1)

    m2 = f"T4B-{uuid.uuid4().hex[:8]}"
    r2 = _submit({
        "location_code": multi_partner_plads["location_code"],
        "material": "Plast",
        "container_number": f"TestC-{m2}",
        "custom_address": f"Test {m2}",
        "partner_id": partner_b,
    })
    _flag_after_insert(mongo_db, r2["order_id"], r2["tour_id"], m2)

    o1 = mongo_db.container_orders.find_one({"id": r1["order_id"]})
    o2 = mongo_db.container_orders.find_one({"id": r2["order_id"]})
    assert o1["assigned_logistics_company_ids"] == [partner_a]
    assert o2["assigned_logistics_company_ids"] == [partner_b]
    # KRYDS-SCOPE-CHECK: ingen af de 2 ordrer må indeholde den andens partner.
    assert partner_b not in o1["assigned_logistics_company_ids"]
    assert partner_a not in o2["assigned_logistics_company_ids"]
