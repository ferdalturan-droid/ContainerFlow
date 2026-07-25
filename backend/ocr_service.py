"""
ocr_service.py — Google Cloud Vision OCR integration for ContainerFlow.

GDPR-compliant: Uses EU regional endpoint (eu-vision.googleapis.com) so all
image processing happens inside the European Union.

Public API:
    is_available()              -> bool   (creds + import status)
    get_status_message()        -> str    (human-readable status, Danish)
    extract_weight_from_image(image_bytes, content_type) ->
        {weight_kg, raw_text, confidence, candidates, error}

Designed to fail gracefully — if the Vision client cannot be instantiated
(missing creds, import error, network), the manual weight-entry flow in the
UI remains the fallback path.
"""

from __future__ import annotations

import io
import logging
import os
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — pillow-heif + google-cloud-vision are optional at startup so
# the rest of the backend keeps booting even if the libs aren't yet installed
# (e.g. during environment rebuilds).
# ---------------------------------------------------------------------------

try:
    from PIL import Image  # noqa: F401
    import pillow_heif

    pillow_heif.register_heif_opener()
    _PIL_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning(f"PIL/pillow-heif not available: {exc}")
    _PIL_AVAILABLE = False

try:
    from google.cloud import vision as gcv  # type: ignore
    _VISION_IMPORTED = True
except Exception as exc:  # pragma: no cover
    logger.warning(f"google-cloud-vision not importable: {exc}")
    gcv = None  # type: ignore
    _VISION_IMPORTED = False


VISION_ENDPOINT = os.environ.get("GCP_VISION_ENDPOINT", "eu-vision.googleapis.com")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/app/secrets/google_drive_sa.json",
)

_VISION_CLIENT = None
_VISION_INIT_ERROR: Optional[str] = None


def _ensure_credentials_env() -> None:
    """Set GOOGLE_APPLICATION_CREDENTIALS for the Google SDK when missing."""
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS


def _get_client():
    """Lazy singleton — only construct on first use."""
    global _VISION_CLIENT, _VISION_INIT_ERROR
    if _VISION_CLIENT is not None:
        return _VISION_CLIENT
    if not _VISION_IMPORTED:
        _VISION_INIT_ERROR = "google-cloud-vision er ikke installeret"
        return None

    _ensure_credentials_env()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path or not os.path.exists(creds_path):
        _VISION_INIT_ERROR = (
            "Service account JSON ikke fundet. Læg filen på "
            f"{creds_path or '/app/secrets/google_drive_sa.json'} og genstart backend."
        )
        return None

    try:
        _VISION_CLIENT = gcv.ImageAnnotatorClient(
            client_options={"api_endpoint": VISION_ENDPOINT}
        )
        logger.info(f"Vision client initialiseret med endpoint {VISION_ENDPOINT}")
        return _VISION_CLIENT
    except Exception as exc:
        _VISION_INIT_ERROR = f"Vision client init fejlede: {exc}"
        logger.exception("Vision client init failed")
        return None


def is_available() -> bool:
    """True if OCR can run end-to-end right now."""
    return _get_client() is not None and _PIL_AVAILABLE


def get_status_message() -> str:
    if not _VISION_IMPORTED:
        return "OCR utilgængelig: google-cloud-vision ikke installeret"
    if not _PIL_AVAILABLE:
        return "OCR utilgængelig: PIL/pillow-heif ikke installeret"
    if _get_client() is None:
        return _VISION_INIT_ERROR or "OCR utilgængelig: ukendt fejl"
    return f"OCR aktiv (endpoint: {VISION_ENDPOINT})"


# ---------------------------------------------------------------------------
# Image normalization — accept JPG/PNG/HEIC + compress before sending
# ---------------------------------------------------------------------------

# Accepted MIME types for incoming uploads.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/heic",
    "image/heif",
    "image/webp",
    "application/octet-stream",  # some mobile browsers send this for HEIC
}

# Max upload size before normalization (bytes). 12 MB to leave headroom for HEIC.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Max dimension for the normalized JPEG (Vision handles up to 75 MP but
# downscaling speeds OCR and reduces cost).
MAX_DIM = 2200


def normalize_to_jpeg(image_bytes: bytes, content_type: str = "") -> bytes:
    """Convert any supported image format to a compressed JPEG (max ~MAX_DIM px).

    Raises:
        ValueError: if the input is invalid / unsupported.
    """
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow not available")

    from PIL import Image, ImageOps

    if not image_bytes:
        raise ValueError("Tomt billede")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)  # respect EXIF orientation
            img = img.convert("RGB")

            # Downscale if huge
            w, h = img.size
            scale = min(MAX_DIM / max(w, h), 1.0)
            if scale < 1.0:
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88, optimize=True)
            return buf.getvalue()
    except Exception as exc:
        raise ValueError(f"Kunne ikke læse billede: {exc}") from exc


# ---------------------------------------------------------------------------
# Weight parsing — Danish receipts
# ---------------------------------------------------------------------------

# Keywords (lowercased) that boost confidence that a number is the NET weight.
NETTO_KEYWORDS = (
    "nettovægt",
    "netto vægt",
    "vægt netto",
    "netto:",
    "total netto",
    "i alt netto",
    "samlet netto",
    "vægt:",  # often the receipt only lists "Vægt"
    "nettovaegt",  # without æ
    "net weight",
    "total net",
    "netto-vægt",
    "nettomængde",
    "nettomaengde",
)

# Keywords that DECREASE confidence (we don't want brutto/tara).
BRUTTO_KEYWORDS = ("bruttovægt", "brutto", "bruttovaegt")
TARA_KEYWORDS = ("taravægt", "tara", "taravaegt", "egenvægt", "egenvaegt")

# Lines containing these usually mean "summary" lines — bump them slightly.
TOTAL_KEYWORDS = ("total", "i alt", "sum", "samlet")

# Match "1.250 kg", "850 kg", "2,5 ton", "1250kg" etc.
WEIGHT_REGEX = re.compile(
    r"""
    (?P<num>
        \d{1,3}(?:[.\s]\d{3})+(?:[.,]\d+)?   # 1.250 / 12.500,5
        | \d+(?:[.,]\d+)?                     # 850 / 1,5
    )
    \s*
    (?P<unit>kg|kilo|kilogram|ton|tons|tonnes|t\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalize_number(num_str: str) -> Optional[float]:
    """Turn '1.250', '2,100', '12.500,5', '1,5' into a float.

    Heuristic (Danish locale):
      - dot followed by 3 digits = thousands separator
      - comma = decimal separator
      - if BOTH present, dot is thousands, comma is decimal
    """
    s = num_str.strip().replace(" ", "")
    if not s:
        return None
    try:
        if "." in s and "," in s:
            return float(s.replace(".", "").replace(",", "."))
        if "," in s:
            return float(s.replace(",", "."))
        if "." in s:
            # "1.250" → thousands separator (3 trailing digits)
            integer, decimal = s.rsplit(".", 1)
            if len(decimal) == 3 and integer.replace(".", "").isdigit():
                return float(integer.replace(".", "") + decimal)
            return float(s)
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_net_weight(raw_text: str) -> Tuple[Optional[float], List[float], float, List[dict]]:
    """Extract the net weight from OCR text.

    Returns:
        (primary_weight_kg, all_candidates_kg, confidence_0_1, raw_candidates)

    raw_candidates includes per-candidate diagnostic info for the audit log.
    """
    if not raw_text:
        return None, [], 0.0, []

    lines = raw_text.splitlines()
    candidates: List[dict] = []
    all_weights: List[float] = []

    for idx, line in enumerate(lines):
        lower = line.lower()
        for m in WEIGHT_REGEX.finditer(line):
            num_str = m.group("num")
            unit = (m.group("unit") or "").lower()
            value = _normalize_number(num_str)
            if value is None:
                continue
            if unit.startswith("t"):
                value *= 1000.0  # tons → kg

            all_weights.append(round(value, 1))

            conf = 0.40  # base
            if any(k in lower for k in NETTO_KEYWORDS):
                conf += 0.40
            if any(k in lower for k in BRUTTO_KEYWORDS):
                conf -= 0.35
            if any(k in lower for k in TARA_KEYWORDS):
                conf -= 0.35
            if any(k in lower for k in TOTAL_KEYWORDS):
                conf += 0.10
            # Reasonable mass range for a recycling drop (50 kg – 30 t)
            if 50 <= value <= 30000:
                conf += 0.10
            elif value < 5:  # noise (e.g. "1 kg" notes)
                conf -= 0.30

            conf = max(0.0, min(1.0, conf))
            candidates.append({
                "weight_kg": round(value, 1),
                "confidence": round(conf, 2),
                "line": line.strip()[:200],
                "line_idx": idx,
                "raw_match": num_str,
                "unit": unit,
            })

    if not candidates:
        return None, all_weights, 0.0, []

    # Best = highest confidence; on tie, prefer largest weight (totals).
    candidates.sort(key=lambda c: (c["confidence"], c["weight_kg"]), reverse=True)
    best = candidates[0]
    return best["weight_kg"], all_weights, best["confidence"], candidates


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def extract_weight_from_image(image_bytes: bytes, content_type: str = "") -> dict:
    """Run OCR + parse net weight. Synchronous (call via thread executor in async)."""
    if not _PIL_AVAILABLE:
        return {
            "weight_kg": None,
            "raw_text": "",
            "confidence": 0.0,
            "candidates": [],
            "all_candidate_weights": [],
            "error": "PIL/pillow-heif ikke installeret",
        }

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        return {
            "weight_kg": None,
            "raw_text": "",
            "confidence": 0.0,
            "candidates": [],
            "all_candidate_weights": [],
            "error": f"Billede er for stort (>{MAX_UPLOAD_BYTES // (1024*1024)} MB)",
        }

    client = _get_client()
    if client is None:
        return {
            "weight_kg": None,
            "raw_text": "",
            "confidence": 0.0,
            "candidates": [],
            "all_candidate_weights": [],
            "error": _VISION_INIT_ERROR or "OCR utilgængelig",
        }

    try:
        jpeg_bytes = normalize_to_jpeg(image_bytes, content_type)
    except ValueError as exc:
        return {
            "weight_kg": None,
            "raw_text": "",
            "confidence": 0.0,
            "candidates": [],
            "all_candidate_weights": [],
            "error": str(exc),
        }

    try:
        image = gcv.Image(content=jpeg_bytes)
        ctx = gcv.ImageContext(language_hints=["da"])
        response = client.document_text_detection(image=image, image_context=ctx)
        if response.error.message:
            return {
                "weight_kg": None,
                "raw_text": "",
                "confidence": 0.0,
                "candidates": [],
                "all_candidate_weights": [],
                "error": f"Vision API: {response.error.message}",
            }
        raw_text = (
            response.full_text_annotation.text if response.full_text_annotation else ""
        )
        weight_kg, all_weights, conf, candidates = parse_net_weight(raw_text)
        return {
            "weight_kg": weight_kg,
            "raw_text": raw_text,
            "confidence": conf,
            "candidates": candidates,
            "all_candidate_weights": all_weights,
            "error": None,
        }
    except Exception as exc:
        logger.exception("Vision OCR call failed")
        return {
            "weight_kg": None,
            "raw_text": "",
            "confidence": 0.0,
            "candidates": [],
            "all_candidate_weights": [],
            "error": f"Vision OCR fejlede: {exc}",
        }
