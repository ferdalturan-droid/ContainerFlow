"""Phase 16: end-to-end integration tests against the live preview backend.

Covers:
  - /api/ocr/status (available=false expected when creds missing)
  - /api/receipts/ocr-scan (400 empty / 503 missing creds)
  - /api/receipts/save-for-tour (normal tour weight + loose append + skip_tour_update)
  - /api/receipts-archive (filters + pagination)
  - /api/receipts-location-documents (customer-side bypass)
  - /api/receipts/{id}/full
  - /api/receipts/{id}/weight-override (audit log + tour sync)
  - /api/superadmin/retention-policies + PUT update validation
  - /api/receipts CRUD regression smoke
"""
import os
import base64
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# Fallback to read the same file as backend tests rely on
if not BASE_URL:
    try:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
    except Exception:
        pass

SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASSWORD = "TestSAreset2026!"
LA_EMAIL = "ilkdistadmin@gmail.com"
LA_PASSWORD = "TestPass2026!"

# 1x1 PNG (valid, smallest possible)
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    body = r.json()
    return body.get("token") or body.get("access_token")


@pytest.fixture(scope="module")
def la_token():
    tok = _login(LA_EMAIL, LA_PASSWORD)
    if not tok:
        # DB wiped — only super admin exists. Fall back to SA token so the
        # endpoints can still be exercised (SA has cross-tenant access).
        tok = _login(SA_EMAIL, SA_PASSWORD)
    if not tok:
        pytest.skip("No usable login (LA and SA both failed)")
    return tok


@pytest.fixture(scope="module")
def sa_token():
    tok = _login(SA_EMAIL, SA_PASSWORD)
    if not tok:
        pytest.skip("Super admin login failed")
    return tok


@pytest.fixture(scope="module")
def la_headers(la_token):
    return {"Authorization": f"Bearer {la_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}", "Content-Type": "application/json"}


# ---------------- OCR status / scan ----------------

class TestOcrStatus:
    def test_ocr_status_unavailable(self, la_headers):
        r = requests.get(f"{BASE_URL}/api/ocr/status", headers=la_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("available") is False, f"Expected available=false, got {body}"
        assert isinstance(body.get("message"), str) and body["message"], "Danish message must be non-empty"

    def test_ocr_scan_empty_image_400(self, la_headers):
        r = requests.post(
            f"{BASE_URL}/api/receipts/ocr-scan",
            json={"image_data": "", "content_type": "image/png"},
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_ocr_scan_valid_b64_returns_503(self, la_headers):
        r = requests.post(
            f"{BASE_URL}/api/receipts/ocr-scan",
            json={"image_data": TINY_PNG_B64, "content_type": "image/png"},
            headers=la_headers,
            timeout=20,
        )
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"


# ---------------- Tour creation + save-for-tour ----------------

def _create_tour(la_headers, tour_type="normal", loose_count=0):
    payload = {
        "fraction": "TEST_Fraction_OCR",
        "facility": "Argo Recycling",
        "container": "TEST_OCR_BOX",
        "plads": "TEST_PLADS_OCR",
        "tour_type": tour_type,
    }
    r = requests.post(f"{BASE_URL}/api/tours", json=payload, headers=la_headers, timeout=15)
    assert r.status_code == 200, r.text
    tour = r.json()
    # For loose, we need to set loose_estimated_count manually via direct DB-style update via PUT /tours/{id}
    if loose_count > 0:
        # Try to set via PUT /tours/{id}
        r2 = requests.put(
            f"{BASE_URL}/api/tours/{tour['id']}",
            json={"tour_type": "loes_afhentning"},
            headers=la_headers,
            timeout=10,
        )
        # We may not be able to set loose_estimated_count via TourUpdate; that's ok — append_for_loose=True triggers the same branch.
    return tour


@pytest.fixture(scope="module")
def normal_tour(la_headers):
    return _create_tour(la_headers, tour_type="normal")


@pytest.fixture(scope="module")
def loose_tour(la_headers):
    return _create_tour(la_headers, tour_type="loes_afhentning")


class TestSaveForTour:
    def test_save_normal_tour_updates_weight(self, la_headers, normal_tour):
        r = requests.post(
            f"{BASE_URL}/api/receipts/save-for-tour",
            json={
                "tour_id": normal_tour["id"],
                "image_data": TINY_PNG_B64,
                "content_type": "image/png",
                "final_weight_kg": 1234.0,
                "user_name": "TEST_pytest_phase16",
            },
            headers=la_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "receipt_id" in body
        assert body["tour_weight"] == 1234.0
        # Verify tour was actually updated
        tr = requests.get(f"{BASE_URL}/api/tours", headers=la_headers, timeout=10)
        assert tr.status_code == 200
        match = [t for t in tr.json() if t["id"] == normal_tour["id"]]
        assert len(match) == 1
        assert match[0].get("weight") == 1234.0
        # Save id for later tests
        TestSaveForTour.receipt_id_normal = body["receipt_id"]

    def test_save_loose_appends_to_container_weights(self, la_headers, loose_tour):
        # First receipt
        r1 = requests.post(
            f"{BASE_URL}/api/receipts/save-for-tour",
            json={
                "tour_id": loose_tour["id"],
                "image_data": TINY_PNG_B64,
                "content_type": "image/png",
                "final_weight_kg": 100.0,
                "append_for_loose": True,
                "user_name": "TEST_pytest_phase16",
            },
            headers=la_headers,
            timeout=30,
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["is_loose"] is True
        assert body1["tour_weight"] == 100.0

        # Second receipt -> should append
        r2 = requests.post(
            f"{BASE_URL}/api/receipts/save-for-tour",
            json={
                "tour_id": loose_tour["id"],
                "image_data": TINY_PNG_B64,
                "content_type": "image/png",
                "final_weight_kg": 250.0,
                "append_for_loose": True,
                "user_name": "TEST_pytest_phase16",
            },
            headers=la_headers,
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["tour_weight"] == 350.0, f"Expected 350, got {body2['tour_weight']}"

    def test_save_with_skip_tour_update_does_not_change_weight(self, la_headers):
        # Create fresh tour
        tour = _create_tour(la_headers, tour_type="normal")
        r = requests.post(
            f"{BASE_URL}/api/receipts/save-for-tour",
            json={
                "tour_id": tour["id"],
                "image_data": TINY_PNG_B64,
                "content_type": "image/png",
                "final_weight_kg": 999.0,
                "skip_tour_update": True,
                "user_name": "TEST_pytest_phase16",
            },
            headers=la_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        # Verify tour weight is NOT 999
        tr = requests.get(f"{BASE_URL}/api/tours", headers=la_headers, timeout=10)
        match = [t for t in tr.json() if t["id"] == tour["id"]]
        assert len(match) == 1
        assert match[0].get("weight") in (None, 0, 0.0), f"Tour weight should be untouched, got {match[0].get('weight')}"

    def test_save_for_nonexistent_tour_404(self, la_headers):
        r = requests.post(
            f"{BASE_URL}/api/receipts/save-for-tour",
            json={
                "tour_id": "nonexistent-" + str(uuid.uuid4()),
                "image_data": TINY_PNG_B64,
                "content_type": "image/png",
            },
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 404, r.text


# ---------------- Archive endpoints ----------------

class TestArchive:
    def test_archive_listing_basic(self, la_headers):
        r = requests.get(f"{BASE_URL}/api/receipts-archive", headers=la_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "total" in body and "items" in body
        assert isinstance(body["items"], list)
        # We just created at least 3 receipts
        assert body["total"] >= 3
        # Image data should be excluded from list payload (perf)
        for it in body["items"]:
            assert "image_data" not in it or not it.get("image_data")

    def test_archive_pagination(self, la_headers):
        r = requests.get(
            f"{BASE_URL}/api/receipts-archive?limit=1&offset=0",
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 1
        assert len(body["items"]) <= 1

    def test_archive_filter_fraction(self, la_headers):
        r = requests.get(
            f"{BASE_URL}/api/receipts-archive?fraction=TEST_Fraction_OCR",
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        for it in body["items"]:
            assert it.get("fraction") == "TEST_Fraction_OCR"

    def test_location_documents_endpoint_accessible(self, la_headers):
        r = requests.get(
            f"{BASE_URL}/api/receipts-location-documents",
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "total" in body and "items" in body


# ---------------- Receipt detail + weight-override ----------------

class TestReceiptDetailOverride:
    def test_get_full_receipt(self, la_headers):
        # Get a receipt id from archive
        ar = requests.get(f"{BASE_URL}/api/receipts-archive?limit=5", headers=la_headers, timeout=10)
        items = ar.json().get("items", [])
        assert items, "Need at least one receipt in archive"
        rid = items[0]["id"]
        r = requests.get(f"{BASE_URL}/api/receipts/{rid}/full", headers=la_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Full payload must include the heavy fields
        assert "image_data" in body
        assert "ocr_raw_text" in body
        assert "audit_log" in body
        assert isinstance(body["audit_log"], list)
        assert len(body["audit_log"]) >= 1

    def test_weight_override_appends_audit_and_syncs_tour(self, la_headers, normal_tour):
        # Find a receipt linked to normal_tour
        ar = requests.get(f"{BASE_URL}/api/receipts-archive?limit=50", headers=la_headers, timeout=10)
        items = ar.json().get("items", [])
        target = next((it for it in items if it.get("tour_id") == normal_tour["id"]), None)
        assert target, "Need a receipt linked to normal tour"
        rid = target["id"]

        new_weight = 5555.0
        r = requests.put(
            f"{BASE_URL}/api/receipts/{rid}/weight-override",
            json={"new_weight_kg": new_weight, "user_name": "TEST_override", "reason": "pytest"},
            headers=la_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("updated") is True
        assert any(e.get("action") == "weight_override" for e in body.get("audit_log", []))

        # Verify ocr_status set to manual on the receipt
        full = requests.get(f"{BASE_URL}/api/receipts/{rid}/full", headers=la_headers, timeout=10).json()
        assert full.get("ocr_status") == "manual"
        assert full.get("final_weight_kg") == new_weight

        # Verify tour weight re-synced
        tr = requests.get(f"{BASE_URL}/api/tours", headers=la_headers, timeout=10)
        match = [t for t in tr.json() if t["id"] == normal_tour["id"]]
        assert match[0].get("weight") == new_weight


# ---------------- Super-admin retention ----------------

class TestRetention:
    def test_list_retention_policies_super_admin(self, sa_headers):
        r = requests.get(f"{BASE_URL}/api/superadmin/retention-policies", headers=sa_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "companies" in body
        for c in body["companies"]:
            assert "id" in c and "name" in c
            assert "receipt_retention_days" in c
            assert isinstance(c["receipt_retention_days"], int)

    def test_list_retention_forbidden_for_logistics(self):
        la_tok = _login(LA_EMAIL, LA_PASSWORD)
        if not la_tok:
            pytest.skip("No separate LA user in DB (DB wiped to super_admin only)")
        r = requests.get(
            f"{BASE_URL}/api/superadmin/retention-policies",
            headers={"Authorization": f"Bearer {la_tok}"},
            timeout=10,
        )
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_update_retention_validation(self, sa_headers):
        # Get one company
        r = requests.get(f"{BASE_URL}/api/superadmin/retention-policies", headers=sa_headers, timeout=10)
        companies = r.json().get("companies", [])
        if not companies:
            pytest.skip("No customer companies to test retention update")
        cid = companies[0]["id"]
        original = companies[0]["receipt_retention_days"]

        # Out of range — too low
        r_low = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{cid}/retention-policy",
            json={"receipt_retention_days": 10},
            headers=sa_headers,
            timeout=10,
        )
        assert r_low.status_code == 400, r_low.text

        # Out of range — too high
        r_high = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{cid}/retention-policy",
            json={"receipt_retention_days": 99999},
            headers=sa_headers,
            timeout=10,
        )
        assert r_high.status_code == 400, r_high.text

        # Valid — set 365
        r_ok = requests.put(
            f"{BASE_URL}/api/superadmin/companies/{cid}/retention-policy",
            json={"receipt_retention_days": 365},
            headers=sa_headers,
            timeout=10,
        )
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["receipt_retention_days"] == 365

        # Verify persisted
        r_v = requests.get(f"{BASE_URL}/api/superadmin/retention-policies", headers=sa_headers, timeout=10)
        new_c = [c for c in r_v.json()["companies"] if c["id"] == cid][0]
        assert new_c["receipt_retention_days"] == 365

        # Restore original (best-effort cleanup)
        requests.put(
            f"{BASE_URL}/api/superadmin/companies/{cid}/retention-policy",
            json={"receipt_retention_days": original},
            headers=sa_headers,
            timeout=10,
        )

    def test_update_retention_nonexistent_404(self, sa_headers):
        r = requests.put(
            f"{BASE_URL}/api/superadmin/companies/no-such-id-xyz/retention-policy",
            json={"receipt_retention_days": 1000},
            headers=sa_headers,
            timeout=10,
        )
        assert r.status_code == 404, r.text


# ---------------- Existing /api/receipts CRUD regression ----------------

class TestReceiptsRegression:
    def test_list_receipts_still_works(self, la_headers):
        r = requests.get(f"{BASE_URL}/api/receipts", headers=la_headers, timeout=15)
        assert r.status_code == 200, r.text
        # Could be list or {items: ...}
        body = r.json()
        assert isinstance(body, (list, dict))
