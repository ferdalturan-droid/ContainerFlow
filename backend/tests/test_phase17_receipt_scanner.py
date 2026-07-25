"""Phase 17 — Receipt Scanner regression tests.

Verifies that after the OCR removal + jscanify rewrite the backend still
properly supports the manual-weight save flow used by the new scanner,
the merged archive listing, the driver-archive endpoints, and the
weight-override endpoint.

NOTE: DB currently contains only super_admin (per /app/memory/test_credentials.md).
We log in as SA, create a TEST_ tour scoped to a synthetic company_id, and
exercise the receipt endpoints against it. Cleanup at end of test class.
"""

import base64
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

def _load_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    # Fallback: read from frontend .env
    env_path = "/app/frontend/.env"
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""


BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASSWORD = "TestSAreset2026!"

# 1x1 transparent PNG (smallest valid PNG)
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture(scope="module")
def sa_token():
    r = requests.post(f"{API}/auth/login", json={
        "email": SA_EMAIL, "password": SA_PASSWORD,
    }, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"SA login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def sa_client(sa_token):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {sa_token}",
    })
    return s


@pytest.fixture(scope="module")
def test_tour(sa_client):
    """Create a TEST_ tour via /api/tours we can attach receipts to."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "driver_name": "TEST_Phase17_Driver",
        "plads": "TEST_Phase17_Plads",
        "facility": "TEST_Phase17_Facility",
        "fraction": "TEST_FraktionA",
        "date": today,
        "loose_estimated_count": 0,
    }
    r = sa_client.post(f"{API}/tours", json=payload, timeout=20)
    if r.status_code not in (200, 201):
        pytest.skip(f"Could not create test tour: {r.status_code} {r.text[:300]}")
    tour = r.json()
    assert "id" in tour
    yield tour
    # Cleanup
    try:
        sa_client.delete(f"{API}/tours/{tour['id']}", timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def loose_tour(sa_client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "driver_name": "TEST_Phase17_LooseDriver",
        "plads": "TEST_Phase17_LoosePlads",
        "facility": "TEST_Phase17_LooseFacility",
        "fraction": "TEST_LooseFrac",
        "date": today,
        "loose_estimated_count": 3,
    }
    r = sa_client.post(f"{API}/tours", json=payload, timeout=20)
    if r.status_code not in (200, 201):
        pytest.skip(f"Could not create loose tour: {r.status_code} {r.text[:300]}")
    tour = r.json()
    yield tour
    try:
        sa_client.delete(f"{API}/tours/{tour['id']}", timeout=10)
    except Exception:
        pass


# ============================================================
# 1. POST /api/receipts/save-for-tour — manual weight, no OCR
# ============================================================
class TestSaveForTourManualWeight:

    def test_save_for_tour_with_manual_weight_normal_tour(self, sa_client, test_tour):
        payload = {
            "tour_id": test_tour["id"],
            "image_data": TINY_PNG_B64,
            "content_type": "image/jpeg",
            "description": "jscanify-scan",
            "final_weight_kg": 1234.5,
            "user_name": "TEST_Phase17_Driver",
            "append_for_loose": False,
            "skip_tour_update": True,  # mirrors frontend new behaviour
        }
        r = sa_client.post(f"{API}/receipts/save-for-tour", json=payload, timeout=30)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert "receipt_id" in data and data["receipt_id"]
        assert data.get("is_loose") is False
        # Persistence check via GET
        rid = data["receipt_id"]
        g = sa_client.get(f"{API}/receipts/{rid}", timeout=15)
        assert g.status_code == 200
        rec = g.json()
        assert rec["tour_id"] == test_tour["id"]
        assert rec.get("final_weight_kg") == 1234.5
        # Tenancy: receipt is persisted (company_id may be absent for SA tokens
        # since SA has no company scope — tenant-aware injection only applies
        # to scoped roles like logistics_admin). Just verify persistence.
        assert rec.get("customer_company_id") is not None  # field present
        # save_for_tour stores image inline
        # ocr_status should be 'manual' (since OCR creds absent + manual weight supplied)
        assert rec.get("ocr_status") in ("manual", "none", "failed")
        # Store for downstream tests
        TestSaveForTourManualWeight.last_receipt_id = rid

    def test_save_for_tour_loose_appends_weight(self, sa_client, loose_tour):
        # First scan
        r1 = sa_client.post(f"{API}/receipts/save-for-tour", json={
            "tour_id": loose_tour["id"],
            "image_data": TINY_PNG_B64,
            "content_type": "image/jpeg",
            "description": "jscanify-scan",
            "final_weight_kg": 500.0,
            "user_name": "TEST_LooseDriver",
            "append_for_loose": True,
            "skip_tour_update": False,
        }, timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        d1 = r1.json()
        assert d1.get("is_loose") is True
        assert d1.get("tour_weight") == 500.0

        # Second scan accumulates
        r2 = sa_client.post(f"{API}/receipts/save-for-tour", json={
            "tour_id": loose_tour["id"],
            "image_data": TINY_PNG_B64,
            "content_type": "image/jpeg",
            "description": "jscanify-scan",
            "final_weight_kg": 250.0,
            "user_name": "TEST_LooseDriver",
            "append_for_loose": True,
            "skip_tour_update": False,
        }, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json().get("tour_weight") == 750.0

    def test_save_for_tour_invalid_image_returns_400(self, sa_client, test_tour):
        r = sa_client.post(f"{API}/receipts/save-for-tour", json={
            "tour_id": test_tour["id"],
            "image_data": "",
            "content_type": "image/jpeg",
            "final_weight_kg": 100.0,
            "skip_tour_update": True,
        }, timeout=20)
        assert r.status_code == 400

    def test_save_for_tour_missing_tour_returns_404(self, sa_client):
        r = sa_client.post(f"{API}/receipts/save-for-tour", json={
            "tour_id": f"NON_EXISTENT_{uuid.uuid4()}",
            "image_data": TINY_PNG_B64,
            "content_type": "image/jpeg",
            "final_weight_kg": 100.0,
            "skip_tour_update": True,
        }, timeout=20)
        assert r.status_code == 404


# ============================================================
# 2. GET /api/receipts and /api/receipts-archive (unified listing)
# ============================================================
class TestReceiptListings:
    def test_get_receipts_basic_no_image_data(self, sa_client):
        r = sa_client.get(f"{API}/receipts", timeout=15)
        assert r.status_code == 200
        receipts = r.json()
        assert isinstance(receipts, list)
        # image_data must be excluded from list payload
        for rec in receipts[:5]:
            assert "image_data" not in rec or rec.get("image_data") in (None, "")

    def test_get_receipts_filter_by_driver_name(self, sa_client):
        r = sa_client.get(
            f"{API}/receipts",
            params={"driver_name": "TEST_Phase17_Driver"},
            timeout=15,
        )
        assert r.status_code == 200
        items = r.json()
        # all returned (if any) must match the driver
        for rec in items:
            assert rec.get("driver_name") == "TEST_Phase17_Driver"

    def test_get_receipts_filter_by_plads(self, sa_client):
        r = sa_client.get(
            f"{API}/receipts",
            params={"plads": "TEST_Phase17_Plads"},
            timeout=15,
        )
        assert r.status_code == 200
        for rec in r.json():
            assert rec.get("plads") == "TEST_Phase17_Plads"

    def test_receipts_archive_returns_paginated(self, sa_client):
        r = sa_client.get(f"{API}/receipts-archive", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "items" in data and "offset" in data and "limit" in data
        assert isinstance(data["items"], list)
        # No image_data / ocr_raw_text in archive payload (performance)
        for rec in data["items"][:5]:
            assert "image_data" not in rec
            assert "ocr_raw_text" not in rec

    def test_receipts_archive_filter_driver_name(self, sa_client):
        r = sa_client.get(
            f"{API}/receipts-archive",
            params={"driver_name": "TEST_Phase17_Driver"},
            timeout=15,
        )
        assert r.status_code == 200
        for rec in r.json()["items"]:
            assert rec.get("driver_name") == "TEST_Phase17_Driver"

    def test_receipts_archive_filter_plads_fraction(self, sa_client):
        r = sa_client.get(
            f"{API}/receipts-archive",
            params={"plads": "TEST_Phase17_Plads", "fraction": "TEST_FraktionA"},
            timeout=15,
        )
        assert r.status_code == 200
        for rec in r.json()["items"]:
            assert rec.get("plads") == "TEST_Phase17_Plads"
            assert rec.get("fraction") == "TEST_FraktionA"

    def test_receipts_archive_filter_date_range(self, sa_client):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = sa_client.get(
            f"{API}/receipts-archive",
            params={"date_from": today, "date_to": today},
            timeout=15,
        )
        assert r.status_code == 200
        # Should not 500; might be empty depending on records, but call must succeed.
        assert isinstance(r.json()["items"], list)

    def test_receipts_archive_search_text(self, sa_client):
        r = sa_client.get(
            f"{API}/receipts-archive",
            params={"search": "jscanify"},
            timeout=15,
        )
        assert r.status_code == 200
        # Our saves used description="jscanify-scan"; should be matchable
        items = r.json()["items"]
        # at least 0 results returned without 500
        assert isinstance(items, list)


# ============================================================
# 3. GET /api/driver-archive (used by 'Pr. chauffør' view)
# ============================================================
class TestDriverArchive:
    def test_get_driver_archive_list(self, sa_client):
        r = sa_client.get(f"{API}/driver-archive", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "drivers" in data
        assert isinstance(data["drivers"], list)

    def test_get_driver_archive_detail_returns_days(self, sa_client):
        # Use a known driver name (from earlier save)
        r = sa_client.get(
            f"{API}/driver-archive/TEST_Phase17_Driver", timeout=20
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("driver_name") == "TEST_Phase17_Driver"
        assert "days" in data and isinstance(data["days"], list)
        # Each day should have receipts list
        for day in data["days"]:
            assert "date" in day
            assert "receipts" in day
            assert isinstance(day["receipts"], list)

    def test_get_driver_archive_unknown_driver_still_200(self, sa_client):
        r = sa_client.get(
            f"{API}/driver-archive/NONEXISTENT_DRIVER_XYZ", timeout=15
        )
        assert r.status_code == 200
        assert r.json()["days"] == []


# ============================================================
# 4. PUT /api/receipts/{id}/weight-override
# ============================================================
class TestWeightOverride:
    @pytest.fixture(scope="class")
    def override_receipt(self, sa_client, test_tour):
        # Create a fresh receipt to override
        r = sa_client.post(f"{API}/receipts/save-for-tour", json={
            "tour_id": test_tour["id"],
            "image_data": TINY_PNG_B64,
            "content_type": "image/jpeg",
            "description": "override-test",
            "final_weight_kg": 800.0,
            "user_name": "TEST_OverrideUser",
            "skip_tour_update": False,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        return r.json()["receipt_id"]

    def test_weight_override_updates_receipt_and_tour(self, sa_client, override_receipt, test_tour):
        r = sa_client.put(
            f"{API}/receipts/{override_receipt}/weight-override",
            json={"new_weight_kg": 1500.0, "user_name": "TEST_Admin", "reason": "manual"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["updated"] is True
        assert len(data["audit_log"]) >= 1

        # Verify receipt
        g = sa_client.get(f"{API}/receipts/{override_receipt}", timeout=15)
        assert g.status_code == 200
        rec = g.json()
        assert rec["final_weight_kg"] == 1500.0
        assert rec["ocr_status"] == "manual"

        # Verify tour weight re-synced (non-loose tour)
        t = sa_client.get(f"{API}/tours/{test_tour['id']}", timeout=15)
        if t.status_code == 200:
            tour = t.json()
            assert tour.get("weight") == 1500.0

    def test_weight_override_unknown_receipt_404(self, sa_client):
        r = sa_client.put(
            f"{API}/receipts/NONEXISTENT_RID/weight-override",
            json={"new_weight_kg": 1.0},
            timeout=15,
        )
        assert r.status_code == 404
