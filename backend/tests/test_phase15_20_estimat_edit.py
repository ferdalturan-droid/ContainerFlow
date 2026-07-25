"""Fase 15.20 — Estimat-redigering via PUT /api/customer-orders/{id}.

Tester:
  1. ILK admin kan opdatere material + estimated_count + order_date + comment på et estimat.
  2. Den linkede tour (tours-collection) får 'fraction' = nyt material og 'estimated_count' = nyt antal.
  3. container_orders-dokumentet får ligeledes opdaterede felter.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env", override=False)
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

ILK_EMAIL = "ilkdistadmin@gmail.com"
ILK_PASS = "TestPass2026!"
# Super admin har globale rettigheder og kan redigere customer-orders.
# logistics_admin må IKKE redigere customer-orders ifølge server.py L12405.
SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "TestSAreset2026!"


def _login(email: str, password: str) -> str:
    for attempt in range(5):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        if r.status_code == 200:
            j = r.json()
            return j.get("token") or j.get("access_token")
        if r.status_code == 429:
            time.sleep(25 + attempt * 10)
            continue
        pytest.fail(f"Login fejlede ({email}): {r.status_code} {r.text[:200]}")
    pytest.skip(f"Rate-limit på login for {email}")


@pytest.fixture(scope="module")
def ilk_token():
    """ILK token er ikke længere brugt aktivt — logistics_admin må ikke
    redigere customer-orders (server.py L12405). Returnerer None hvis login
    fejler (creds drift)."""
    try:
        r = requests.post(f"{API}/auth/login",
                          json={"email": ILK_EMAIL, "password": ILK_PASS},
                          timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get("token") or j.get("access_token")
    except Exception:
        pass
    return None


@pytest.fixture(scope="module")
def sa_token():
    return _login(SA_EMAIL, SA_PASS)


def _find_estimat_order(token: str) -> dict | None:
    """Find første tour_type='estimat' tour og returnér tilknyttet customer-order via order_id."""
    r = requests.get(
        f"{API}/tours",
        headers={"Authorization": f"Bearer {token}"},
        params={"tour_type": "estimat", "limit": 50},
        timeout=20,
    )
    assert r.status_code == 200, f"GET tours estimat fejlede: {r.status_code}"
    tours = r.json() if isinstance(r.json(), list) else r.json().get("tours", [])
    for t in tours:
        oid = t.get("order_id") or t.get("customer_order_id")
        if oid:
            return {"tour": t, "order_id": oid}
    return None


def test_estimat_edit_updates_order_and_tour(ilk_token, sa_token):
    target = _find_estimat_order(sa_token)
    if not target:
        pytest.skip("Ingen estimat-tour fundet i miljøet")

    order_id = target["order_id"]
    tour = target["tour"]
    tour_id = tour.get("id")

    # Hent original order via tours endpoint snapshot — gem original værdier.
    original_count = int(tour.get("estimated_count") or 0)
    original_material = tour.get("fraction") or ""

    # Generér nye værdier som er forskellige fra originalen.
    new_count = original_count + 3 if original_count else 7
    new_material = "Beton" if original_material != "Beton" else "Tegl"
    new_date = "2026-07-15"
    new_comment = "Phase 15.20 test edit"

    r = requests.put(
        f"{API}/customer-orders/{order_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={
            "material": new_material,
            "estimated_count": new_count,
            "order_date": new_date,
            "comment": new_comment,
        },
        timeout=20,
    )
    assert r.status_code == 200, f"PUT fejlede: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("success") is True
    changed = set(body.get("changed_fields", []))
    # mindst material og estimated_count skal være changed (kan inkludere date/comment hvis forskellig)
    assert "material" in changed
    assert "estimated_count" in changed

    # Verificér via direkte DB-opslag (GET /api/tours kan filtrere på dato-range
    # og vi har lige ændret tour.date til en ny dato).
    from pymongo import MongoClient
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    updated_tour = db.tours.find_one({"id": tour_id}, {"_id": 0})
    assert updated_tour, f"Tour {tour_id} ikke længere fundet efter edit"
    assert updated_tour.get("fraction") == new_material, (
        f"Tour fraction blev ikke spejlet — forventede '{new_material}', fik '{updated_tour.get('fraction')}'"
    )
    assert int(updated_tour.get("estimated_count") or 0) == new_count, (
        f"Tour estimated_count blev ikke spejlet — forventede {new_count}, fik {updated_tour.get('estimated_count')}"
    )
    assert updated_tour.get("date") == new_date, (
        f"Tour date blev ikke spejlet — forventede '{new_date}', fik '{updated_tour.get('date')}'"
    )
    # container_orders skal også reflektere ændringen
    co = db.container_orders.find_one({"id": order_id}, {"_id": 0})
    assert co is not None
    assert co.get("material") == new_material
    assert int(co.get("estimated_count") or 0) == new_count
    assert co.get("order_date") == new_date
    assert co.get("comment") == new_comment


def test_estimat_edit_no_change_returns_no_change(ilk_token, sa_token):
    """PUT med samme værdier som allerede er sat skal returnere no_change=True."""
    target = _find_estimat_order(sa_token)
    if not target:
        pytest.skip("Ingen estimat-tour fundet")
    order_id = target["order_id"]

    # Send identisk material (Beton) som det tidligere test sandsynligvis efterlod.
    # Kør edit én gang, så vi kender state.
    requests.put(
        f"{API}/customer-orders/{order_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"comment": "no-change-baseline"},
        timeout=15,
    )
    # Anden gang med samme comment → no_change
    r = requests.put(
        f"{API}/customer-orders/{order_id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"comment": "no-change-baseline"},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    assert body.get("no_change") is True
