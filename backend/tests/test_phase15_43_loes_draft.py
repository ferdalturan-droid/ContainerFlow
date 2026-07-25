"""Fase 15.43 — Løs afhentning DRAFT save.

Tester:
  T1: PATCH tour med container_weights=[100,200] OG ingen `completed`-felt
      gemmer som DRAFT — turen forbliver IKKE completed, weight = sum.
  T2: Gentaget DRAFT-PATCH med flere vægte opdaterer både weight og array
      (kunden kan følge med på Mine bestillinger i realtid).
  T3: container_orders får DRAFT-vægte spejlet uden at status flippes
      til 'completed'.
  T4: Efter draft-saves, en endelig PATCH med completed=True afslutter
      turen og spejler endelig weight/status til ordren.
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
        except Exception as e:
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
    assert p, "Mindst én plads med en logistik-partner skal findes"
    return p


_SEED_KEY = "__phase15_43_seed__"


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
    assert r.status_code == 200, r.text
    body = r.json()
    mongo_db.container_orders.update_one({"id": body["order_id"]}, {"$set": {_SEED_KEY: True}})
    mongo_db.tours.update_one({"id": body["tour_id"]}, {"$set": {_SEED_KEY: True}})
    return body


def test_T1_draft_save_does_not_complete(sa_token, mongo_db, multi_partner_plads):
    """Draft-save (container_weights uden completed) opdaterer kun array+sum,
    holder turen åben."""
    body = _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    upd = requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [100, 200]},
        timeout=15,
    )
    assert upd.status_code == 200, upd.text
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert t["container_weights"] == [100.0, 200.0]
    assert abs(t["weight"] - 300.0) < 0.01
    # Turen er IKKE afsluttet
    assert t.get("completed") is not True


def test_T2_repeated_drafts_update_progressively(sa_token, mongo_db, multi_partner_plads):
    """Chaufføren kan gemme udkast flere gange undervejs."""
    body = _submit_loes(mongo_db, multi_partner_plads, 5, uuid.uuid4().hex[:8])
    # 1. udkast: 2 vægte
    requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [50, 75]},
        timeout=15,
    ).raise_for_status()
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert t["container_weights"] == [50.0, 75.0]
    assert abs(t["weight"] - 125.0) < 0.01
    assert not t.get("completed")
    # 2. udkast: 4 vægte (chauffør har vejet flere)
    requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [50, 75, 100, 125]},
        timeout=15,
    ).raise_for_status()
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert t["container_weights"] == [50.0, 75.0, 100.0, 125.0]
    assert abs(t["weight"] - 350.0) < 0.01
    assert not t.get("completed")


def test_T3_draft_mirrors_to_order_without_completing(sa_token, mongo_db, multi_partner_plads):
    """Drafts spejles til container_orders så Mine bestillinger viser dem."""
    body = _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [200, 250, 300]},
        timeout=15,
    ).raise_for_status()
    o = mongo_db.container_orders.find_one({"id": body["order_id"]})
    # Spejling: container_weights + weight_kg på ordren
    assert o.get("container_weights") == [200.0, 250.0, 300.0]
    assert abs(float(o.get("weight_kg") or 0) - 750.0) < 0.01
    # Status er IKKE "completed" — driver er ikke færdig
    assert o.get("status") != "completed"
    assert o.get("completed") is not True


def test_T4_final_completion_after_drafts(sa_token, mongo_db, multi_partner_plads):
    """Efter draft-saves kan endelig PATCH med completed=True afslutte turen
    og spejle status="completed" til ordren."""
    body = _submit_loes(mongo_db, multi_partner_plads, 2, uuid.uuid4().hex[:8])
    # Draft først
    requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [400]},
        timeout=15,
    ).raise_for_status()
    # Endelig completion
    final = requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": True, "container_weights": [400, 500]},
        timeout=15,
    )
    assert final.status_code == 200, final.text
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert t.get("completed") is True
    assert t["container_weights"] == [400.0, 500.0]
    assert abs(t["weight"] - 900.0) < 0.01
    o = mongo_db.container_orders.find_one({"id": body["order_id"]})
    assert o.get("status") == "completed"
    assert abs(float(o.get("weight_kg") or 0) - 900.0) < 0.01


def test_T5_put_response_includes_container_weights(sa_token, mongo_db, multi_partner_plads):
    """Regression: PUT /tours/{id} skal returnere `container_weights` og
    `loose_estimated_count` i response så frontend kan opdatere lokalt state
    uden at miste data. Tidligere bug: response_model=Tour strippede dem væk
    fordi de manglede i Tour-modellen."""
    body = _submit_loes(mongo_db, multi_partner_plads, 4, uuid.uuid4().hex[:8])
    r = requests.put(
        f"{API_URL}/api/tours/{body['tour_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"container_weights": [120, 240, 360]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # KRITISK: Disse felter SKAL være i response (regression-vagt)
    assert data.get("container_weights") == [120.0, 240.0, 360.0], f"container_weights mangler i response: {data}"
    assert data.get("loose_estimated_count") == 4
    assert abs(float(data.get("weight") or 0) - 720.0) < 0.01


def test_T6_edit_order_date_mirrors_to_tour(sa_token, mongo_db, multi_partner_plads):
    """Fase 15.47: Når en bruger redigerer `order_date` på en ordre via
    PUT /customer-orders/{id}, skal BÅDE `tour.date` (driver-filter) OG
    `tour.order_date` (vises på tur-kortet som 'Bestillingsdato')
    opdateres. Tidligere blev kun `date` opdateret, så chauffør-kortet
    viste stadig den gamle bestillingsdato."""
    body = _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    # Endpoint kræver authenticated user med customer_admin/order role.
    # super_admin token bypass'er ejerskab-check.
    r = requests.put(
        f"{API_URL}/api/customer-orders/{body['order_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"order_date": "2026-12-15", "priority": "normal", "comment": ""},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert t["date"] == "2026-12-15", f"tour.date IKKE opdateret: {t}"
    assert t.get("order_date") == "2026-12-15", f"tour.order_date IKKE opdateret: {t}"


def test_T7_edit_loose_count_mirrors_to_tour(sa_token, mongo_db, multi_partner_plads):
    """Fase 15.46: Når kunden redigerer `loose_estimated_count`, skal
    feltet både gemmes på ordren OG spejles til den tilhørende tur
    så chaufførens multi-vægt-UI viser det nye antal rækker."""
    body = _submit_loes(mongo_db, multi_partner_plads, 3, uuid.uuid4().hex[:8])
    r = requests.put(
        f"{API_URL}/api/customer-orders/{body['order_id']}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"loose_estimated_count": 8, "priority": "normal", "comment": ""},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    o = mongo_db.container_orders.find_one({"id": body["order_id"]})
    t = mongo_db.tours.find_one({"id": body["tour_id"]})
    assert o.get("loose_estimated_count") == 8
    assert t.get("loose_estimated_count") == 8
