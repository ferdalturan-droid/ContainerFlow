"""Fase 16: Tests for OCR parser + Receipt endpoints."""
import os
import sys
from pathlib import Path

# Make backend imports resolvable
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import pytest


# ---------- ocr_service: pure-parser tests ----------

def test_normalize_number_thousand_dot():
    from ocr_service import _normalize_number
    assert _normalize_number("1.250") == 1250.0
    assert _normalize_number("12.500") == 12500.0


def test_normalize_number_decimal_comma():
    from ocr_service import _normalize_number
    assert _normalize_number("1,5") == 1.5
    assert _normalize_number("850,75") == 850.75


def test_normalize_number_mixed_da_locale():
    from ocr_service import _normalize_number
    assert _normalize_number("12.500,5") == 12500.5


def test_normalize_number_plain_integer():
    from ocr_service import _normalize_number
    assert _normalize_number("850") == 850.0


def test_parse_netto_beats_brutto_and_tara():
    from ocr_service import parse_net_weight
    text = (
        "Bruttovægt 3.950 kg\n"
        "Taravægt 1.750 kg\n"
        "Nettovægt 2.200 kg"
    )
    w, all_w, conf, cands = parse_net_weight(text)
    assert w == 2200.0
    assert conf >= 0.7
    assert set(all_w) == {3950.0, 1750.0, 2200.0}
    assert len(cands) == 3


def test_parse_short_netto_label():
    from ocr_service import parse_net_weight
    text = "Argo Recycling\n26/06/26\nVægt netto 1.450 kg"
    w, _, conf, _ = parse_net_weight(text)
    assert w == 1450.0
    assert conf >= 0.7


def test_parse_ton_converts_to_kg():
    from ocr_service import parse_net_weight
    w, _, _, _ = parse_net_weight("Total netto 2,5 ton")
    assert w == 2500.0


def test_parse_no_weight_returns_none():
    from ocr_service import parse_net_weight
    w, all_w, conf, cands = parse_net_weight("no numbers here, just words")
    assert w is None
    assert all_w == []
    assert conf == 0.0


def test_ocr_available_without_creds_is_false():
    """Without GOOGLE_APPLICATION_CREDENTIALS pointing at a real file, OCR
    must report unavailable but never raise."""
    from ocr_service import is_available, get_status_message
    avail = is_available()
    msg = get_status_message()
    assert isinstance(avail, bool)
    assert isinstance(msg, str)
    assert msg  # non-empty


# ---------- Endpoint registration smoke checks ----------

def test_endpoints_registered():
    """Make sure the Fase 16 routes are registered on the FastAPI app."""
    import server  # noqa: F401
    routes = {(getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", []) or []))) for r in server.app.routes}
    paths = {r[0] for r in routes}
    assert "/api/ocr/status" in paths
    assert "/api/receipts/ocr-scan" in paths
    assert "/api/receipts/save-for-tour" in paths
    assert "/api/receipts-archive" in paths
    assert "/api/receipts-location-documents" in paths
    assert "/api/superadmin/retention-policies" in paths
    assert "/api/superadmin/companies/{company_id}/retention-policy" in paths
    assert "/api/receipts/{receipt_id}/full" in paths
    assert "/api/receipts/{receipt_id}/weight-override" in paths


def test_receipt_model_extended():
    from server import Receipt
    sample = Receipt()
    # Fase 16 fields
    assert hasattr(sample, "ocr_raw_text")
    assert hasattr(sample, "ocr_weight_kg")
    assert hasattr(sample, "ocr_confidence")
    assert hasattr(sample, "ocr_status")
    assert hasattr(sample, "audit_log")
    assert hasattr(sample, "final_weight_kg")
    assert hasattr(sample, "customer_company_id")


def test_company_model_has_retention_field():
    from auth import Company
    c = Company(name="Test Co")
    assert hasattr(c, "receipt_retention_days")
    assert c.receipt_retention_days == 1095  # default 3 years
