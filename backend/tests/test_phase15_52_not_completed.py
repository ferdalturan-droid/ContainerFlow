"""Fase 15.52 — "Kan ikke gennemføres"-flow.

Backend regression-tests for de to nye endpoints:
  POST /api/tours/{id}/not-completed   (chauffør markerer)
  POST /api/tours/{id}/reactivate      (logistik-admin gen-aktiverer)
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
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
    url, db = "mongodb://localhost:27017", "test_database"
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
                return d.get("token") or d.get("access_token") or ""
            last = (r.status_code, r.text)
        except Exception as e:
            last = ("exc", str(e))
        time.sleep(5 + i * 3)
    raise RuntimeError(f"login failed: {last}")


SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASSWORD = "TestSAreset2026!"
DRIVER_EMAIL = "testdriver@default.local"
DRIVER_PASSWORD = "Driver2026!"


@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PASSWORD)


@pytest.fixture(scope="module")
def driver_token():
    # Stagger login to avoid rate-limit
    time.sleep(8)
    return _login(DRIVER_EMAIL, DRIVER_PASSWORD)


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


_SEED_KEY = "__phase15_52_seed__"


@pytest.fixture(autouse=True)
def cleanup(mongo_db):
    mongo_db.tours.delete_many({_SEED_KEY: True})
    mongo_db.container_orders.delete_many({_SEED_KEY: True})
    yield
    mongo_db.tours.delete_many({_SEED_KEY: True})
    mongo_db.container_orders.delete_many({_SEED_KEY: True})


def _seed_tour(mongo_db, *, on_way=True, claimed_by="Test Driver", driver_id_val="dummy", completed=False):
    tid = str(uuid.uuid4())
    today = datetime.now().strftime("%Y-%m-%d")
    mongo_db.tours.insert_one({
        "id": tid,
        "date": today,
        "plads": "Test Plads",
        "address": "Testvej 1",
        "facility": "Test",
        "fraction": "Pap",
        "container": "T-001",
        "tour_type": "normal",
        "claimed_by": claimed_by,
        "claimed_by_id": driver_id_val,
        "driver_id": driver_id_val,
        "on_way": on_way,
        "completed": completed,
        "is_pause": False,
        "not_completed": False,
        "created_at": datetime.now().isoformat(),
        _SEED_KEY: True,
    })
    return tid


def test_T1_mark_not_completed_requires_comment(driver_token, mongo_db):
    tid = _seed_tour(mongo_db)
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/not-completed",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"comment": ""},
        timeout=15,
    )
    assert r.status_code == 400


def test_T2_mark_not_completed_requires_on_way(driver_token, mongo_db):
    tid = _seed_tour(mongo_db, on_way=False)
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/not-completed",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"comment": "Pladsen er lukket"},
        timeout=15,
    )
    assert r.status_code == 409


def test_T3_mark_not_completed_succeeds(driver_token, mongo_db):
    tid = _seed_tour(mongo_db)
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/not-completed",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"comment": "Pladsen lukket pga. snestorm"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    t = mongo_db.tours.find_one({"id": tid})
    assert t.get("not_completed") is True
    assert t.get("on_way") is False
    assert t.get("not_completed_comment") == "Pladsen lukket pga. snestorm"
    assert t.get("not_completed_at")
    assert t.get("not_completed_by_name")


def test_T4_completed_tour_cannot_be_marked_not_completed(driver_token, mongo_db):
    tid = _seed_tour(mongo_db, completed=True, on_way=False)
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/not-completed",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"comment": "Forsøg på at marker afsluttet tur"},
        timeout=15,
    )
    assert r.status_code == 409


def test_T5_reactivate_clears_claim_keeps_comment(sa_token, mongo_db):
    """Gen-aktivering frigør claim men bevarer chauffør-kommentar som historik."""
    tid = _seed_tour(mongo_db)
    # First mark not_completed via direct DB (faster than two roundtrips)
    mongo_db.tours.update_one({"id": tid}, {"$set": {
        "not_completed": True,
        "not_completed_at": "2026-06-22T10:00:00+02:00",
        "not_completed_comment": "Lukket",
        "not_completed_by_name": "Test Driver",
        "on_way": False,
    }})
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/reactivate",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"comment": "Pladsen er nu åben — forsøg igen"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    t = mongo_db.tours.find_one({"id": tid})
    assert t.get("not_completed") is False
    # Claim ryddet
    assert t.get("claimed_by") == ""
    assert t.get("driver_id") == ""
    assert t.get("on_way") is False
    # Historik bevaret
    assert t.get("not_completed_comment") == "Lukket"
    assert t.get("not_completed_by_name") == "Test Driver"
    # Admin-kommentar gemt
    assert t.get("reactivate_comment") == "Pladsen er nu åben — forsøg igen"
    assert t.get("reactivated_at")


def test_T6_reactivate_not_completed_tour_only(sa_token, mongo_db):
    """Kan ikke gen-aktivere en tur der ikke er not_completed."""
    tid = _seed_tour(mongo_db)
    r = requests.post(
        f"{API_URL}/api/tours/{tid}/reactivate",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"comment": ""},
        timeout=15,
    )
    assert r.status_code == 409
