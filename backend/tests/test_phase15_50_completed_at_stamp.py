"""Fase 15.50 — Chauffør-side færdiggjorte ture + completed_at stempel.

Tester:
  T1: Når en tour markeres `completed=True` første gang, sættes `completed_at`
      til nuværende DK-tid (ISO-format).
  T2: Når en allerede afsluttet tour PATCHes igen, ændres `completed_at`
      IKKE — det er kun den FØRSTE completion-transition der stamper.
  T3: Når en tour reverteres til `completed=False`, ryddes `completed_at`.
  T4: GET /api/tours inkluderer `completed_at` på den returnerede tour så
      driver-UI kan vise stemplet.

Bemærk: Fysisk "Vis færdiggjorte ture"-knappen virker via frontend-toggle
(showCompletedDriver). Filterlogikken på linje 16030-16033 i App.js er ren
client-side på allerede-fetchede ture. Bagsiden af knappens functionality
afhænger af at GET /api/tours returnerer completed-ture som matcher driver's
reportDate. Det dækker T4.
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
                return d.get("token") or d.get("access_token") or ""
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


_SEED_KEY = "__phase15_50_seed__"


@pytest.fixture(autouse=True)
def cleanup(mongo_db):
    mongo_db.tours.delete_many({_SEED_KEY: True})
    yield
    mongo_db.tours.delete_many({_SEED_KEY: True})


def _seed_tour(mongo_db, *, completed=False, weight=0):
    """Seed en simpel 'normal' tur på i dag."""
    tid = str(uuid.uuid4())
    today = datetime.now().strftime("%Y-%m-%d")
    mongo_db.tours.insert_one({
        "id": tid,
        "date": today,
        "order_date": today,
        "plads": "Test Plads",
        "address": "Testvej 1",
        "facility": "Test Facility",
        "fraction": "Pap",
        "container": "T-001",
        "container_id_override": "",
        "tour_type": "normal",
        "claimed_by": "Test Chauffør",
        "claimed_by_id": "test-driver-id",
        "completed": completed,
        "weight": weight,
        "on_way": False,
        "is_pause": False,
        "created_at": datetime.now().isoformat(),
        _SEED_KEY: True,
    })
    return tid


def test_T1_first_completion_stamps_completed_at(sa_token, mongo_db):
    """Første gang completed flippes til True, sættes completed_at."""
    tid = _seed_tour(mongo_db)
    before = mongo_db.tours.find_one({"id": tid})
    assert not before.get("completed_at")
    r = requests.put(
        f"{API_URL}/api/tours/{tid}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": True, "weight": 100, "claimed_by": "Test Chauffør"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    after = mongo_db.tours.find_one({"id": tid})
    assert after.get("completed") is True
    assert after.get("completed_at"), f"completed_at IKKE sat efter completion: {after}"
    # Skal være ISO-format, parsebar
    parsed = datetime.fromisoformat(after["completed_at"])
    assert parsed.year == datetime.now().year


def test_T2_re_patching_completed_tour_keeps_completed_at(sa_token, mongo_db):
    """Allerede completed → senere PATCH må IKKE overskrive completed_at."""
    tid = _seed_tour(mongo_db, completed=True, weight=100)
    # Manually stamp it
    fixed_stamp = "2026-06-22T12:00:00+02:00"
    mongo_db.tours.update_one({"id": tid}, {"$set": {"completed_at": fixed_stamp}})
    # PATCH a noop / unrelated field
    r = requests.put(
        f"{API_URL}/api/tours/{tid}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"weight": 150, "claimed_by": "Test Chauffør"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    after = mongo_db.tours.find_one({"id": tid})
    assert after.get("completed_at") == fixed_stamp, \
        f"completed_at blev overskrevet: {after.get('completed_at')}"


def test_T3_uncomplete_clears_completed_at(sa_token, mongo_db):
    """Revert til completed=False rydder completed_at."""
    tid = _seed_tour(mongo_db, completed=True, weight=100)
    mongo_db.tours.update_one({"id": tid}, {"$set": {"completed_at": "2026-06-22T12:00:00+02:00"}})
    r = requests.put(
        f"{API_URL}/api/tours/{tid}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": False, "claimed_by": "Test Chauffør"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    after = mongo_db.tours.find_one({"id": tid})
    assert after.get("completed") is False
    assert after.get("completed_at") == "", \
        f"completed_at IKKE ryddet ved revert: {after.get('completed_at')}"


def test_T4_get_tours_returns_completed_at(sa_token, mongo_db):
    """GET /api/tours returnerer completed_at på completed-ture så chauffør-
    UI'en kan vise 'har afsluttet kl. 14:32'."""
    tid = _seed_tour(mongo_db)
    # Mark completed via PUT
    requests.put(
        f"{API_URL}/api/tours/{tid}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"completed": True, "weight": 200, "claimed_by": "Test Chauffør"},
        timeout=15,
    ).raise_for_status()
    # GET /tours (filtered to today by default)
    r = requests.get(f"{API_URL}/api/tours?limit=500",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     timeout=20)
    assert r.status_code == 200
    body = r.json()
    arr = body if isinstance(body, list) else body.get("tours", [])
    match = [t for t in arr if t.get("id") == tid]
    assert match, "Seeded tour fundes ikke i GET /tours response"
    t = match[0]
    assert t.get("completed") is True
    assert t.get("completed_at"), f"completed_at mangler i GET /tours response: {t}"
