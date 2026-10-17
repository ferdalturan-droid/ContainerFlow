from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Body, Request, Header
from fastapi.responses import Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import os
import logging
import re
import secrets
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
import uuid
import base64
import io
try:
    import fitz  # PyMuPDF for PDF text extraction
except ImportError:
    fitz = None
    print("WARNING: PyMuPDF (fitz) not available - PDF parsing disabled")
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# Danish timezone - all date calculations must use this, NOT UTC
DK_TZ = ZoneInfo("Europe/Copenhagen")

def get_dk_date_str():
    """Get current date string in Danish timezone (YYYY-MM-DD)."""
    return datetime.now(DK_TZ).strftime("%Y-%m-%d")

def get_dk_now_iso():
    """Get current datetime ISO string in Danish timezone."""
    return datetime.now(DK_TZ).isoformat()
import asyncio as async_lib

# Fase 16: OCR service for kvitterings-scanning (Google Cloud Vision EU)
_OCR_IMPORT_ERROR = ""
try:
    from ocr_service import (
        extract_weight_from_image as _ocr_extract,
        is_available as _ocr_is_available,
        get_status_message as _ocr_status_message,
    )
except Exception as _e:
    _OCR_IMPORT_ERROR = str(_e)
    _ocr_extract = None
    _ocr_is_available = lambda: False  # noqa: E731
    _ocr_status_message = lambda: f"OCR import fejlede: {_OCR_IMPORT_ERROR}"  # noqa: E731

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Also try loading from parent directory (deployment fallback)
if not os.environ.get('MONGO_URL'):
    load_dotenv(ROOT_DIR.parent / '.env')
    load_dotenv(ROOT_DIR.parent / 'backend' / '.env')

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
_raw_db = client[os.environ.get('DB_NAME', 'test_database')]

# ============= MULTI-TENANT AUTH IMPORTS =============
from auth import (
    current_company_id, current_user_id, current_user_role,
    current_extra_visible_company_ids,
    DEFAULT_COMPANY_ID, SUPER_ADMIN_BYPASS, VALID_ROLES,
    COMPANY_TYPE_CUSTOMER, COMPANY_TYPE_LOGISTICS, VALID_COMPANY_TYPES,
    hash_password, verify_password, create_access_token, decode_token,
    Company, CompanyCreate, CompanyUpdate,
    User as AuthUser, UserPublic, UserCreate, UserUpdate,
    LoginRequest, LoginResponse,
    get_optional_user_payload, get_current_user_payload,
    require_role, require_super_admin,
)

# Collections that are tenant-scoped (auto-filtered by company_id).
TENANT_COLLECTIONS = {
    "drivers", "tours", "plads", "locations", "customer_addresses",
    "container_orders", "container_overrides", "receipts", "pdf_archives",
    "driver_sessions", "messages", "reports", "schedules", "push_subscriptions",
    "genbrug_orders", "plads_addresses", "co2_types", "vehicles", "trailers",
}

# Paths that are public (no auth, no tenant filter) - used by customer order flow / login.
PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/accept-invitation",
    "/api/auth/verify-token",
    "/api/admin/login",
    "/api/driver/login",
    "/api/driver/verify-code",
    "/api/locations/code/",          # customer order code lookup
    "/api/customer-orders/submit",   # customer submits order
    "/api/customer-orders/check-duplicate",  # public duplicate-check (Fase 15.16)
    "/api/delivery-addresses/resolve",  # QR kiosk needs to resolve schedule per material+date
    "/api/push/vapid-public-key",
)
PUBLIC_PATH_EXACT = {"/api/", "/api"}


class TenantAwareCollection:
    """Motor collection wrapper that auto-injects company_id filter / value."""
    def __init__(self, real_collection, name: str):
        self._coll = real_collection
        self._name = name

    def _inject_filter(self, filter_obj):
        cid = current_company_id.get()
        if cid == SUPER_ADMIN_BYPASS:
            return dict(filter_obj) if filter_obj else {}
        f = dict(filter_obj) if filter_obj else {}
        if "company_id" not in f:
            # Multi-company read: if the user's primary company "serves" other
            # companies, expand the filter so reads (find/find_one/update/delete/
            # count) see merged data. Writes (insert) still use the single
            # primary cid via _inject_doc.
            extra = current_extra_visible_company_ids.get() or []
            if extra:
                visible = [cid] + [c for c in extra if c and c != cid]
                f["company_id"] = {"$in": visible}
            else:
                f["company_id"] = cid
        return f

    def _inject_doc(self, doc):
        if isinstance(doc, dict) and "company_id" not in doc:
            cid = current_company_id.get()
            if cid != SUPER_ADMIN_BYPASS:
                doc["company_id"] = cid
        return doc

    def find(self, filter=None, projection=None, *args, **kwargs):
        return self._coll.find(self._inject_filter(filter), projection, *args, **kwargs)

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._coll.find_one(self._inject_filter(filter), *args, **kwargs)

    async def insert_one(self, doc, *args, **kwargs):
        return await self._coll.insert_one(self._inject_doc(doc), *args, **kwargs)

    async def insert_many(self, docs, *args, **kwargs):
        return await self._coll.insert_many([self._inject_doc(d) for d in docs], *args, **kwargs)

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._coll.update_one(self._inject_filter(filter), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._coll.update_many(self._inject_filter(filter), update, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._coll.delete_one(self._inject_filter(filter), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._coll.delete_many(self._inject_filter(filter), *args, **kwargs)

    async def count_documents(self, filter=None, *args, **kwargs):
        return await self._coll.count_documents(self._inject_filter(filter or {}), *args, **kwargs)

    async def bulk_write(self, ops, *args, **kwargs):
        # Pass through; existing usage operates on unique UUID ids.
        return await self._coll.bulk_write(ops, *args, **kwargs)

    async def create_index(self, *args, **kwargs):
        return await self._coll.create_index(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._coll, name)


class TenantAwareDB:
    """Wraps motor db. Returns TenantAwareCollection for tenant-scoped collections; others pass through."""
    def __init__(self, real_db):
        self._db = real_db
        self._cache = {}

    def __getattr__(self, name):
        if name in TENANT_COLLECTIONS:
            if name not in self._cache:
                self._cache[name] = TenantAwareCollection(getattr(self._db, name), name)
            return self._cache[name]
        return getattr(self._db, name)

    def __getitem__(self, name):
        return self.__getattr__(name)


db = TenantAwareDB(_raw_db)

# Admin/Driver credentials from env (fallback for backward compat)
ADMIN_PASSWORD_DEFAULT = os.environ.get("ADMIN_PASSWORD", "ilk2026")
DRIVER_CODE_DEFAULT = os.environ.get("DRIVER_CODE", "3030")
# These are overridden by DB values at runtime
ADMIN_PASSWORD = ADMIN_PASSWORD_DEFAULT
DRIVER_CODE = DRIVER_CODE_DEFAULT

async def get_system_setting(key: str, default: str) -> str:
    try:
        doc = await _raw_db.system_settings.find_one({"key": key})
        if doc and doc.get("value"):
            return doc["value"]
    except Exception:
        pass
    return default

async def get_admin_password() -> str:
    return await get_system_setting("admin_password", ADMIN_PASSWORD_DEFAULT)

async def get_driver_code_setting() -> str:
    return await get_system_setting("driver_code", DRIVER_CODE_DEFAULT)

# Create the main app without a prefix
app = FastAPI()

# Health check endpoint - directly on app (not behind /api prefix)
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "containerflow"}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============= DATE NORMALIZATION =============
import re as _re

def normalize_date(date_str: str) -> str:
    """Normalize any date string to YYYY-MM-DD format."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    # Already YYYY-MM-DD
    if _re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    # DD-MM-YYYY → YYYY-MM-DD
    m = _re.match(r'^(\d{1,2})-(\d{1,2})-(\d{4})$', date_str)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # DD/MM/YYYY → YYYY-MM-DD
    m = _re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # DD.MM.YYYY → YYYY-MM-DD
    m = _re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', date_str)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return date_str

# Security for admin
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ============= MODELS =============

class Driver(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    plate: str = ""  # Phase 2: optional — drivers may set plate themselves
    area: str = ""
    facility: str = ""
    phone: str = ""
    email: str = ""
    active: bool = True
    # Phase 2: surfaced for admin UI ("Afventer" badge until invite accepted)
    invitation_status: str = "active"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DriverCreate(BaseModel):
    name: str
    plate: str = ""  # Phase 2: plate optional at invitation time
    area: str = ""
    facility: str = ""
    phone: str = ""
    email: str  # Phase 2: REQUIRED — driver receives invitation link here

class DriverUpdate(BaseModel):
    name: Optional[str] = None
    plate: Optional[str] = None
    area: Optional[str] = None
    facility: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    active: Optional[bool] = None

class Tour(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str
    container: str = ""
    fraction: str
    facility: str
    address: str
    weight: Optional[float] = None
    time: str = ""
    completed: bool = False
    on_way: bool = False
    is_pause: bool = False
    is_same_day: bool = False
    is_private: bool = False  # Özel firma turu
    private_company: str = ""  # Özel firma adı
    open_from: str = ""
    open_to: str = ""
    remark: str = ""
    plads: str = ""
    driver_id: str = ""
    driver_name: str = ""
    report_id: str = ""
    sort_order: int = 0  # For drag & drop sorting
    priority: str = "normal"  # low, normal, high, urgent
    claimed_by: str = ""  # Driver name who claimed this tour
    claimed_by_id: str = ""  # Driver ID who claimed this tour
    claimed_at: str = ""  # ISO timestamp when the tour was first claimed/taken
    receipt_image: str = ""  # Base64 encoded receipt image
    lat: Optional[float] = None  # Optional coordinate for route optimization
    lng: Optional[float] = None  # Optional coordinate for route optimization
    route_distance_km: Optional[float] = None  # Distance from starting plads
    route_order: Optional[int] = None  # Optimized route order
    transport_mode: str = ""  # "truck" or "trailer" suggestion
    on_way_time: str = ""  # Time when driver went "på vej"
    tour_type: str = "normal"  # "normal" | "flyt" | "vaerksted" — for special pricing
    # Phase 4.1 (2026-06-16): Free-text container type description (fx "Lav åben 20 m³")
    # — distinct from `container` (the numeric identifier). Filled from the
    # Excel template's "Containertype"-column.
    container_type: str = ""
    order_id: str = ""  # Links back to the originating container_order (Bestil Afhentning)
    # Customer (ARGO / MARTO / …) the tour belongs to. Filled by /api/tours on
    # the way out for driver views so the UI can group/badge by customer.
    customer_name: str = ""
    customer_code: str = ""  # e.g. K001
    # Fase 4 (2026-06-16): Source attribution for clean separation in admin UI.
    # "manual"         = LA created directly in AdminPage
    # "argo"           = imported via Argo PDF/mail parser
    # "customer_order" = auto-created when a customer-side order was submitted
    source: str = "manual"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Fase 13 (2026-06-18): Spejlede felter fra ordren så chaufføren ser ALT
    # på tur-kortet — opgavetype + kapacitet + bestillingsdato + bestilt-af.
    capacity_label: str = ""
    capacity_volume_m3: Optional[float] = None
    order_date: str = ""
    created_by_name: str = ""
    created_by_email: str = ""
    # Fase 15 (2026-06-19): Kort, unik turkode der vises i Planlægning-overblik.
    # Format: "{CUSTOMER_PREFIX}-{nnnn}" (fx "ARG-0142"). Genereres automatisk
    # ved POST /tours / POST /tours/bulk via counters-kollektionen pr. kunde.
    tour_number: str = ""
    # Fase 15 (2026-06-19): Admin-tildelings-spor — sættes når en LA/SA
    # pre-assigner eller claimer en tur på vegne af en chauffør. Bruges på
    # chauffør-siden til at vise "Tildelt af [Navn]" og til at låse turen
    # mod at chaufføren fjerner sig selv. Driver-claimede ture lader disse
    # felter være tomme.
    assigned_by_id: str = ""
    assigned_by_name: str = ""
    assigned_at: str = ""
    # Fase 15.16 (2026-02-21): Estimat-bestillinger gemmer det forventede
    # antal containere her. 0 for almindelige ture (non-estimat).
    estimated_count: int = 0
    # Fase 15.41 (2026-02-22): "Løs afhentning" — chaufføren medbringer egne
    # tomme containere og registrerer vægt per container.
    #   `loose_estimated_count` = kundens estimat ved bestilling (>0).
    #   `container_weights`     = liste af faktisk indvejede vægte (kg).
    # `weight`-feltet auto-beregnes som SUM(container_weights) i update_tour.
    # Eksplicit deklareret her så `response_model=Tour` IKKE stripper dem
    # væk ved PUT /tours/{id} (ConfigDict(extra="ignore") ville ellers fjerne
    # dem — det forårsagede en bug hvor frontend mistede gemte udkast-vægte
    # når listen blev opdateret fra response.data).
    loose_estimated_count: int = 0
    container_weights: List[float] = Field(default_factory=list)
    # Fase 15.52 (2026-02-22): "Kan ikke gennemføres"-flow.
    # Chaufføren markerer turen som ikke-gennemførbar (lukket plads, ingen
    # adgang osv.) MED en obligatorisk kommentar. Turen forsvinder fra
    # chauffør-UI'en men er synlig for logistik-admin der kan gen-aktivere
    # den (sætter not_completed=False, claimed_by="", driver_id="").
    # Tæller IKKE i CO2/vægt/rapport-totaler — den er ikke "kørt".
    not_completed: bool = False
    not_completed_at: str = ""
    not_completed_comment: str = ""
    not_completed_by_name: str = ""
    reactivated_at: str = ""
    reactivated_by_name: str = ""
    reactivate_comment: str = ""
    # 2026-10-16: Prisgrundlag (se PRICING_SPEC.md). None = ikke angivet.
    used_trailer: Optional[bool] = None
    # 2026-10-17: "container" (B2B/containerture) eller "goods" (premium-
    # firmaers egne ture der ikke handler om containere). Strukturerede
    # adresser (vej, postnummer, by) ved siden af de sammensatte strenge
    # `address`/`facility` som resten af systemet bruger. Hængere og
    # indholdslinjer (fx hænger 1: Beton, hænger 2: Træ) - kun premium.
    tour_kind: str = "container"
    address_parts: Dict[str, str] = Field(default_factory=dict)
    facility_parts: Dict[str, str] = Field(default_factory=dict)
    trailer_count: int = 0
    cargo_lines: List[Dict[str, Any]] = Field(default_factory=list)
    # 2026-10-17: Én opgave = én tur, også med flere stop. `stops` er den
    # ordnede liste af afhentninger/afleveringer; `address`/`facility`
    # spejler første afhentning/sidste aflevering, så alt eksisterende
    # (kort, rute, rapporter) virker uændret. Chaufføren krydser stop af.
    stops: List[Dict[str, Any]] = Field(default_factory=list)

class TourCreate(BaseModel):
    date: str = Field(default_factory=get_dk_date_str)
    container: str = ""
    container_type: str = ""
    fraction: str = ""  # 2026-10-17: kan komme fra cargo_lines (se _normalize_tour_doc)
    facility: str = ""
    address: str = ""
    is_same_day: bool = False
    is_private: bool = False
    private_company: str = ""
    open_from: str = ""
    open_to: str = ""
    remark: str = ""
    plads: str = ""
    driver_id: str = ""
    driver_name: str = ""
    report_id: str = ""
    sort_order: int = 0
    priority: str = "normal"
    # Fase 15 (2026-06-19): Tillad kunde-info ind ved create, så
    # _generate_tour_number kan bygge en pænt prefix-baseret kode.
    customer_name: str = ""
    customer_code: str = ""
    tour_type: str = "normal"
    capacity_label: str = ""
    capacity_volume_m3: Optional[float] = None
    order_date: str = ""
    created_by_name: str = ""
    created_by_email: str = ""
    loose_estimated_count: int = 0
    # 2026-10-17: Aftalt fast pris ved oprettelse (manuel tur). Gemmes som
    # price_override og kræver rettigheden "Ændre priser".
    agreed_price: Optional[float] = None
    agreed_add_waiting: bool = True
    tour_kind: str = "container"
    address_parts: Dict[str, str] = Field(default_factory=dict)
    facility_parts: Dict[str, str] = Field(default_factory=dict)
    trailer_count: int = 0
    cargo_lines: List[Dict[str, Any]] = Field(default_factory=list)
    stops: List[Dict[str, Any]] = Field(default_factory=list)

class TourUpdate(BaseModel):
    weight: Optional[float] = None
    # Fase 15.41 (2026-02-22): "Løs afhentning" — chauffør registrerer vægt
    # for hver tom container de fyldte. Lagres som flad liste af tal.
    # `weight`-feltet auto-beregnes som SUM af container_weights i
    # update_tour-handleren — så de aldrig kommer ud af sync.
    container_weights: Optional[List[float]] = None
    time: Optional[str] = None
    completed: Optional[bool] = None
    on_way: Optional[bool] = None
    sort_order: Optional[int] = None
    priority: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    is_private: Optional[bool] = None
    private_company: Optional[str] = None
    claimed_by: Optional[str] = None
    claimed_by_id: Optional[str] = None
    claimed_at: Optional[str] = None
    tour_type: Optional[str] = None
    receipt_image: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    route_distance_km: Optional[float] = None
    route_order: Optional[int] = None
    transport_mode: Optional[str] = None
    on_way_time: Optional[str] = None
    is_same_day: Optional[bool] = None
    container: Optional[str] = None
    container_type: Optional[str] = None
    open_from: Optional[str] = None
    open_to: Optional[str] = None
    remark: Optional[str] = None
    # 2026-10-16: Planlæggeren kan rette grunddata fra Ture-arbejdsfladen
    # (flytte dato, rette adresse/fraktion). Fjernes for chauffører i
    # update_tour.
    date: Optional[str] = None
    fraction: Optional[str] = None
    address: Optional[str] = None
    facility: Optional[str] = None
    plads: Optional[str] = None
    capacity_label: Optional[str] = None
    address_parts: Optional[Dict[str, str]] = None
    facility_parts: Optional[Dict[str, str]] = None
    trailer_count: Optional[int] = None
    cargo_lines: Optional[List[Dict[str, Any]]] = None
    loose_estimated_count: Optional[int] = None
    stops: Optional[List[Dict[str, Any]]] = None

class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str = ""
    driver_name: str = ""
    vehicle_reg: str = ""
    start_time: str = ""
    end_time: str = ""
    report_date: str = ""
    plads: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ReportCreate(BaseModel):
    driver_id: str = ""
    driver_name: str = ""
    vehicle_reg: str = ""
    start_time: str = ""
    end_time: str = ""
    report_date: str = ""
    plads: str = ""
    notes: str = ""

class ReportUpdate(BaseModel):
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_reg: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    report_date: Optional[str] = None
    plads: Optional[str] = None
    notes: Optional[str] = None

class ParsedTour(BaseModel):
    date: str
    container: str
    fraction: str
    facility: str
    address: str
    open_from: str = ""
    open_to: str = ""
    remark: str = ""

class ParseMailRequest(BaseModel):
    text: str
    report_id: str = ""

class ParseMailResponse(BaseModel):
    success: bool
    tours: List[ParsedTour]
    count: int
    debug_info: str = ""
    grouped_by_facility: dict = {}

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_admin: bool = True
    from_driver_id: str = ""  # If message is from driver
    from_driver_name: str = ""
    to_driver_id: str = ""  # If message is to driver
    to_driver_name: str = ""
    to_admin: bool = False  # If message is to admin
    content: str
    read: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MessageCreate(BaseModel):
    to_driver_id: str = ""
    to_driver_name: str = ""  # For driver-to-driver messages
    from_driver_id: str = ""
    from_driver_name: str = ""
    to_admin: bool = False
    content: str

# Driver Session - keeps driver data persistent
class DriverSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_name: str
    vehicle_reg: str = ""
    current_plads: str = ""
    start_time: str = ""
    end_time: str = ""
    report_date: str = ""
    notes: str = ""
    last_active: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DriverSessionCreate(BaseModel):
    driver_name: str
    vehicle_reg: str = ""
    current_plads: str = ""
    start_time: str = ""
    report_date: str = ""

class DriverSessionUpdate(BaseModel):
    vehicle_reg: Optional[str] = None
    current_plads: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    notes: Optional[str] = None

# PDF Archive - stores generated PDFs for 1 week
class PDFArchive(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_name: str
    vehicle_reg: str = ""
    plads: str = ""
    report_date: str
    file_name: str
    file_data: str = ""  # Base64 encoded PDF
    total_tours: int = 0
    completed_tours: int = 0
    total_weight: float = 0
    start_time: str = ""
    end_time: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""  # Auto-delete after 1 week

class DriverStats(BaseModel):
    driver_id: str
    driver_name: str
    plate: str
    total_tours: int = 0
    completed_tours: int = 0
    total_weight: float = 0
    today_tours: int = 0
    today_completed: int = 0
    last_start_time: str = ""
    last_end_time: str = ""
    reports: List[dict] = []

class Plads(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    city: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    active: bool = True
    location_code: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PladsCreate(BaseModel):
    name: str
    city: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_code: Optional[str] = None

class PladsUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_code: Optional[str] = None

class Schedule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str
    driver_name: str
    date: str  # YYYY-MM-DD
    plads: str  # plads name or "FRI"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ScheduleCreate(BaseModel):
    driver_id: str
    driver_name: str
    date: str
    plads: str

class ScheduleBulkCreate(BaseModel):
    schedules: List[ScheduleCreate]

class ReportHistory(BaseModel):
    date: str
    total_tours: int
    completed_tours: int
    total_weight: float
    driver_count: int
    reports: List[dict]

class TourReorderItem(BaseModel):
    id: str
    sort_order: int

class TourReorderRequest(BaseModel):
    tours: List[TourReorderItem]

# ============= CONTAINER ORDER SYSTEM MODELS =============

# Location with unique code for customer access
class Location(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str  # Unique access code (e.g., "3030")
    name: str  # Location name (e.g., "Skipstrup Genbrugsplads")
    address: str = ""  # Physical address
    city: str = ""
    active: bool = True
    materials: List[str] = []  # Available materials at this location
    containers_per_material: int = 3  # Number of containers per material
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class LocationCreate(BaseModel):
    code: str
    name: str
    materials: List[str] = []

class LocationUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    materials: Optional[List[str]] = None
    active: Optional[bool] = None
    containers_per_material: Optional[int] = None

# Customer saved addresses
class CustomerAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    location_code: str  # Which location this address belongs to
    name: str  # Contact name
    address: str  # Full address
    container_number: str  # Container ID
    phone: str = ""
    email: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CustomerAddressCreate(BaseModel):
    location_code: str
    name: str
    address: str
    container_number: str
    phone: str = ""
    email: str = ""

class CustomerAddressUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    container_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

# Container pickup orders
class ContainerOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    location_code: str  # Links to location
    location_name: str = ""  # Denormalized for display
    address_id: str  # Links to saved address
    customer_name: str = ""  # Denormalized
    customer_address: str = ""  # Denormalized
    container_number: str = ""  # Denormalized
    container_id_override: str = ""  # Per-order container number override (does NOT change default)
    material: str  # Selected material type
    # Fase 9 (2026-06-17): CO2-beregning. `co2_type_id` linker til en post i
    # `co2_types` collection (oprettet af Kunde Admin). `co2_kg` beregnes
    # automatisk når vægten lander: faktor * (weight_kg / 1000).
    co2_type_id: str = ""        # FK til CO2Type
    co2_type_name: str = ""      # Denormaliseret label (snapshot ved oprettelse)
    co2_factor: float = 0.0      # Denormaliseret faktor (kg CO2 per ton) — snapshot ved oprettelse
    weight_kg: float = 0.0       # Vægt landet fra chaufførens kvittering
    co2_kg: float = 0.0          # Beregnet: co2_factor * (weight_kg / 1000)
    order_date: str  # "today" or "tomorrow" or specific date
    priority: str = "normal"  # normal, haster, sidst
    comment: str = ""
    status: str = "pending"  # pending, in_progress, completed, cancelled
    driver_id: str = ""
    driver_name: str = ""
    admin_note: str = ""  # Internal admin message
    sort_order: int = 0  # For route ordering
    completed_at: str = ""
    open_from: str = ""  # Opening time (HH:MM)
    open_to: str = ""  # Closing time (HH:MM)
    tour_type: str = "normal"  # "normal" | "flyt" | "vaerksted"
    # Fase 15.16/15.18 (2026-02-21): Estimat-bestillinger gemmer det forventede
    # antal containere her (0 for ikke-estimat-ordrer). Vises i "Mine
    # bestillinger" som separat felt "Antal containere estimeret".
    estimated_count: int = 0
    # Pr. 2026-06-15 brugerkrav (runde 6): Den logistik-partner ordren blev
    # oprettet for (snapshot fra partner-pickeren). Tom = legacy/ingen partner.
    partner_id: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ContainerOrderCreate(BaseModel):
    location_code: str
    address_id: str
    material: str
    # Fase 9: Optional på create — fronend sender det med, men eksisterende
    # integrationer (legacy) skal ikke gå i stykker.
    co2_type_id: str = ""
    order_date: str
    priority: str = "normal"
    comment: str = ""

class ContainerOrderUpdate(BaseModel):
    material: Optional[str] = None
    co2_type_id: Optional[str] = None
    order_date: Optional[str] = None
    priority: Optional[str] = None
    comment: Optional[str] = None
    status: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    admin_note: Optional[str] = None
    sort_order: Optional[int] = None
    tour_type: Optional[str] = None
    # Fase 9: Vægt fra chaufførens kvittering. Når denne sættes >0, beregner
    # backend automatisk co2_kg = co2_factor * (weight_kg / 1000).
    weight_kg: Optional[float] = None
    # Fase 15.16: Estimat-bestillinger har et redigerbart antal.
    estimated_count: Optional[int] = None
    # Fase 15.44 (2026-02-22): Løs afhentning — antal containere som chaufføren
    # skal medbringe. Mirres til den tilhørende tur så multi-vægt-UI'en på
    # chaufførsiden viser korrekt antal rækker.
    loose_estimated_count: Optional[int] = None
    # Custom delivery address — kun relevant for normal / loes_afhentning.
    custom_address: Optional[str] = None
    # Workshop snapshot — kun relevant for vaerksted / afhent_vaerksted.
    workshop_id: Optional[str] = None
    workshop_name: Optional[str] = None
    workshop_address: Optional[str] = None
    workshop_phone: Optional[str] = None


# Fase 9 (2026-06-17): CO2-type/material library — scope: per kunde
# (company_id). Kunde Admin opretter/redigerer/sletter. Faktor = kg CO2 per ton
# (faktor=0 tilladt for jord, beton osv. uden CO2-aftryk).
class CO2Type(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""             # Customer company this type belongs to
    name: str                        # e.g. "PAP", "Træ", "Metal"
    factor: float = 0.0              # kg CO2 per ton
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CO2TypeCreate(BaseModel):
    name: str
    factor: float = 0.0

class CO2TypeUpdate(BaseModel):
    name: Optional[str] = None
    factor: Optional[float] = None
    active: Optional[bool] = None


# Fase 10 (2026-06-17): Vehicle + Trailer flåde-modeller — pr. logistik-virksomhed
# LA opretter alle firmaets vognnumre og hængere ÉN gang. Chaufføren vælger
# ÉN vogn + (valgfri) ÉN hænger pr. login. Hængerens `container_capacity`
# styrer hvor mange samtidige ture chaufføren kan have (max = capacity + 1).
class Vehicle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""    # Logistics company that owns this vehicle
    number: str             # Vognnummer (UPPERCASE)
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class VehicleCreate(BaseModel):
    number: str

class VehicleUpdate(BaseModel):
    number: Optional[str] = None
    active: Optional[bool] = None

class Trailer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""           # Logistics company that owns this trailer
    number: str                    # Hængernummer
    container_capacity: int = 1    # Antal containere pr. hænger — max samtidige ture = capacity + 1
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TrailerCreate(BaseModel):
    number: str
    container_capacity: int = 1

class TrailerUpdate(BaseModel):
    number: Optional[str] = None
    container_capacity: Optional[int] = None
    active: Optional[bool] = None


class Receipt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""  # multi-tenant scope (auto-set by TenantAwareDB)
    driver_name: str = ""
    plads: str = ""
    plads_id: str = ""  # for accurate filtering in archive
    tour_id: str = ""
    customer_company_id: str = ""  # kunde-firma (for retention + location-admin scoping)
    fraction: str = ""
    amount: float = 0.0
    description: str = ""
    image_data: str = ""  # base64 encoded image (kept for backward compatibility)
    # Fase 16 — OCR fields
    ocr_raw_text: str = ""
    ocr_weight_kg: Optional[float] = None
    ocr_confidence: float = 0.0
    ocr_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    ocr_status: str = "none"  # "none" | "success" | "failed" | "manual"
    ocr_error: str = ""
    final_weight_kg: Optional[float] = None  # vægt som blev gemt på turen (efter evt. manuel rettelse)
    audit_log: List[Dict[str, Any]] = Field(default_factory=list)  # [{ts, user, action, before, after, reason}]
    date: str = Field(default_factory=get_dk_date_str)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ReceiptCreate(BaseModel):
    driver_name: str
    plads: str = ""
    tour_id: str = ""
    amount: float = 0.0
    description: str = ""
    image_data: str  # base64 encoded image


class PushSubscription(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_name: str
    endpoint: str
    keys: dict  # {p256dh, auth}
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PushSubscriptionCreate(BaseModel):
    driver_name: str
    subscription: dict  # {endpoint, keys: {p256dh, auth}}

class PushNotificationSend(BaseModel):
    title: str = "ContainerFlow"
    body: str
    driver_names: List[str] = []  # empty = all
    url: str = "/"


# Default materials list - 27 Danish genbrugsplads materials
DEFAULT_MATERIALS = [
    "Trykimprægneret træ",
    "Rest efter sortering til Argo",
    "Stor rest efter sortering til RGS",
    "Beton til RGS",
    "Tegl til RGS",
    "Asfalt til RGS",
    "Pap til HCS",
    "Papir til Stena",
    "Bøger til Stena",
    "Glasuld til Norrecco",
    "Flasker til Krogs flaskegenbrug",
    "Dæk til Toelt",
    "Fjernmøbler til neddeling FSG",
    "Rockwool til RGS",
    "Tekstilaffald til Stena",
    "Hård plast/folie Nyborg",
    "Kølemøbler byt",
    "Hvidevarer byt",
    "Jord",
    "Gipsbaseret byggematerialer",
    "Deponi blandet",
    "Fyldplads/Sanitæt",
    "Eternit fra vejen",
    "Hård plast til kravlegård",
    "Div. interne flytninger",
    "Rest til Argo",
    "Mad til Gemidan",
]

# ============= DRIVER ENDPOINTS =============

# ============= DRIVER ENDPOINTS (Phase 2 — drivers ARE users with role='driver') =============
# Drivers are stored as authenticated users in the `users` collection with
# role="driver". The /api/drivers endpoints below are bagudkompatible adaptere:
# de mapper users-shape til Driver-shape så frontend (AdminPage chauffør-fane,
# tour-tildelinger, etc.) ikke behøver kæmpe-refactor lige nu. Den nye flow:
#  - Logistics admin opretter chauffør → user row med role="driver" oprettes,
#    invitation-email sendes via `_send_invitation_email`.
#  - Chaufføren klikker linket og sætter sit password via /set-password.
#  - Login = standard /api/auth/login (email+password).
#  - Gamle `drivers` collection er slettet i Fase 1 og bruges ikke længere.


def _user_to_driver_shape(u: dict) -> dict:
    """Map a User document to the legacy Driver Pydantic shape."""
    return {
        "id": u.get("id", ""),
        "name": u.get("name", ""),
        "plate": u.get("plate") or "",
        "area": u.get("area") or "",
        "facility": u.get("facility") or "",
        "phone": u.get("phone") or "",
        "email": u.get("email", ""),
        "active": bool(u.get("active", True)),
        "created_at": u.get("created_at", ""),
        # Bonus surfacing: invitation_status so the UI can show pending vs. active
        "invitation_status": u.get("invitation_status", "active"),
    }


async def _require_logistics_admin_or_sa(payload: dict):
    """Helper: only logistics_admin (acting on their tenant) or super_admin may
    manage drivers."""
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må administrere chauffører")


@api_router.get("/drivers", response_model=List[Driver])
async def get_drivers(payload: dict = Depends(get_current_user_payload)):
    """List all drivers in the caller's company (logistics_admin) or all (SA)."""
    role = payload.get("role")
    query = {"role": "driver"}
    if role == "logistics_admin":
        query["company_id"] = payload.get("company_id") or ""
    # super_admin sees all drivers across tenants
    users = await _raw_db.users.find(query, {"_id": 0, "password_hash": 0}).to_list(500)
    return [_user_to_driver_shape(u) for u in users]


@api_router.get("/drivers/{driver_id}", response_model=Driver)
async def get_driver(driver_id: str, payload: dict = Depends(get_current_user_payload)):
    u = await _raw_db.users.find_one({"id": driver_id, "role": "driver"}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Driver not found")
    # Tenant check
    if payload.get("role") == "logistics_admin" and u.get("company_id") != payload.get("company_id"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    return Driver(**_user_to_driver_shape(u))


@api_router.post("/drivers", response_model=Driver)
async def create_driver(
    driver: DriverCreate,
    payload: dict = Depends(get_current_user_payload),
):
    """Create a driver by sending them an invitation email.

    Requires logistics_admin. The driver receives a 72h-valid link to set
    their password. Until they accept, `invitation_status='pending'`.
    """
    await _require_logistics_admin_or_sa(payload)
    company_id = payload.get("company_id") or ""
    if not company_id or company_id == SUPER_ADMIN_BYPASS:
        raise HTTPException(status_code=400, detail="Logistik-firma mangler")

    email = (driver.email or "").strip().lower()
    name = (driver.name or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email er påkrævet")
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")

    # Duplicate guard (per-tenant)
    if await _raw_db.users.find_one({"email": email, "company_id": company_id}):
        raise HTTPException(status_code=409, detail="Email findes allerede i dette firma")

    user_id = str(uuid.uuid4())
    new_user = {
        "id": user_id,
        "email": email,
        "name": name,
        "role": "driver",
        "company_id": company_id,
        "active": True,
        "invitation_status": "pending",
        "password_hash": "",
        "phone": (driver.phone or ""),
        "plate": (driver.plate or ""),
        "area": (driver.area or ""),
        "facility": (driver.facility or ""),
        "managed_company_ids": [],
        "assigned_plads_ids": [],
        "visible_plads_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.users.insert_one(new_user)

    # Build invitation token + email via shared helper
    try:
        await _send_invite_for_user(new_user)
    except Exception as e:
        # Don't block the driver creation if email fails — admin can resend
        logger.warning(f"Driver invitation email failed for {email}: {e}")

    return Driver(**_user_to_driver_shape(new_user))


@api_router.put("/drivers/{driver_id}", response_model=Driver)
async def update_driver(
    driver_id: str,
    update: DriverUpdate,
    payload: dict = Depends(get_current_user_payload),
):
    await _require_logistics_admin_or_sa(payload)
    u = await _raw_db.users.find_one({"id": driver_id, "role": "driver"}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Driver not found")
    if payload.get("role") == "logistics_admin" and u.get("company_id") != payload.get("company_id"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")

    # Email change → enforce uniqueness in same tenant
    if "email" in update_data:
        new_email = update_data["email"].strip().lower()
        if new_email and await _raw_db.users.find_one({
            "email": new_email,
            "company_id": u.get("company_id"),
            "id": {"$ne": driver_id},
        }):
            raise HTTPException(status_code=409, detail="Email findes allerede i dette firma")
        update_data["email"] = new_email

    await _raw_db.users.update_one({"id": driver_id}, {"$set": update_data})
    refreshed = await _raw_db.users.find_one({"id": driver_id}, {"_id": 0, "password_hash": 0})
    return Driver(**_user_to_driver_shape(refreshed))


@api_router.delete("/drivers/{driver_id}")
async def delete_driver(driver_id: str, payload: dict = Depends(get_current_user_payload)):
    await _require_logistics_admin_or_sa(payload)
    u = await _raw_db.users.find_one({"id": driver_id, "role": "driver"}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Driver not found")
    if payload.get("role") == "logistics_admin" and u.get("company_id") != payload.get("company_id"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    await _raw_db.users.delete_one({"id": driver_id})
    # Clean up pending invitation tokens for this user
    await _raw_db.invitation_tokens.delete_many({"user_id": driver_id})
    return {"message": "Driver deleted"}


@api_router.post("/drivers/{driver_id}/resend-invitation")
async def resend_driver_invitation(
    driver_id: str,
    payload: dict = Depends(get_current_user_payload),
):
    """Re-send the invitation email for a pending driver. Existing tokens for
    this user are invalidated; a new 72h token is created."""
    await _require_logistics_admin_or_sa(payload)
    u = await _raw_db.users.find_one({"id": driver_id, "role": "driver"}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Driver not found")
    if payload.get("role") == "logistics_admin" and u.get("company_id") != payload.get("company_id"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    if u.get("invitation_status") != "pending":
        raise HTTPException(status_code=400, detail="Chaufføren har allerede aktiveret kontoen")
    await _send_invite_for_user(u)
    return {"success": True}

# ============= TOUR ENDPOINTS =============

# Fase 6 (2026-06-16): Audit-log helper for tour pre-assignment changes.
# Stored in `tour_audit_log` collection: {id, tour_id, action, before, after,
# user_id, user_name, user_email, user_role, at}. Read via
# GET /api/tours/{tour_id}/audit-log (LA/SA only).
async def _tour_audit(tour_id: str, action: str, payload: dict, before: dict, after: dict):
    entry = {
        "id": str(uuid.uuid4()),
        "tour_id": tour_id,
        "action": action,  # "assign" | "reassign" | "release" | "claim" | "unclaim"
        "user_id": payload.get("sub") or payload.get("user_id") or "",
        "user_name": payload.get("name") or payload.get("email") or "",
        "user_email": payload.get("email") or "",
        "user_role": payload.get("role") or "",
        "before": before,
        "after": after,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.tour_audit_log.insert_one(entry)


# Fase 15 (2026-06-19): Kort, læsbar tur-identifikator.
# Format: "{PREFIX}-{0000}" hvor PREFIX = customer_code (3-4 bogstaver) eller
# første 3 bogstaver af customer_name (uppercase). Counter holdes pr. prefix
# i `tour_counters`-kollektionen (atomisk $inc). "TUR" bruges som fallback
# hvis kunde ikke kan udledes.
async def _generate_tour_number(customer_code: str = "", customer_name: str = "") -> str:
    raw = (customer_code or "").strip().upper()
    if not raw and customer_name:
        # Strip non-letters and take 3 first chars
        letters = "".join(c for c in customer_name.upper() if c.isalpha())
        raw = letters[:3] if letters else ""
    if not raw:
        raw = "TUR"
    # Atomic increment via findOneAndUpdate
    from pymongo import ReturnDocument
    res = await _raw_db.tour_counters.find_one_and_update(
        {"_id": raw},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = (res or {}).get("seq", 1) if res else 1
    if not isinstance(seq, int) or seq < 1:
        seq = 1
    return f"{raw}-{seq:04d}"


@api_router.get("/tours", response_model=List[Tour])
async def get_tours(report_id: Optional[str] = None, plads: Optional[str] = None,
                    driver_id: Optional[str] = None, date: Optional[str] = None,
                    source: Optional[str] = None,
                    tour_type: Optional[str] = None,
                    limit: int = 200,
                    date_from: Optional[str] = None,
                    date_to: Optional[str] = None,
                    pending: bool = False,
                    payload: Optional[dict] = Depends(get_optional_user_payload)):
    query = {}
    # 2026-10-16: Periode + "kun uafsluttede" - bruges af Ture-arbejdsfladen til
    # at finde ture fra tidligere dage der aldrig blev kørt.
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = normalize_date(date_from)
        if date_to:
            rng["$lte"] = normalize_date(date_to)
        query["date"] = rng
    if pending:
        query["completed"] = {"$ne": True}
        query["is_pause"] = {"$ne": True}
    if report_id:
        query["report_id"] = report_id
    if plads:
        query["plads"] = plads
    if driver_id:
        query["driver_id"] = driver_id
    # Fase 15.16 (2026-02-XX): tour_type-filter — bruges af "Planlæg
    # ressourcer"-fanen til kun at hente estimater (tour_type="estimat").
    # Fase 15.19 (2026-02-21): KRITISK ISOLATIONS-REGEL — hvis caller ikke
    # eksplicit beder om estimater (eller "all"), så ekskluderer vi
    # tour_type="estimat" fra resultatet. Estimater må KUN vises i
    # "Planlæg ressourcer" på logistik-admin-siden. Ingen lækage til
    # chauffør-views, "Ikke-tildelte ture", driver-arkiv etc.
    if tour_type:
        if tour_type.lower() != "all":
            query["tour_type"] = tour_type
    else:
        query["tour_type"] = {"$ne": "estimat"}
    if date:
        query["date"] = normalize_date(date)
    # Fase 4: ?source=manual|argo|customer_order — kan også sendes som CSV
    if source:
        srcs = [s.strip() for s in source.split(",") if s.strip()]
        if len(srcs) == 1:
            query["source"] = srcs[0]
        elif len(srcs) > 1:
            query["source"] = {"$in": srcs}

    # Driver visibility: own company tours + tours from partnered locations
    # (assigned_logistics_company_ids contains driver's company). We bypass
    # the default tenant filter (which would only show the driver's own
    # company) and do the union match manually.
    if payload and payload.get("role") in ("driver", "logistics_admin"):
        la_company = payload.get("company_id")
        # Capture driver_uid up front so we can OR with "driver_id == self"
        # in the customer-partnership filter (Fase 15.2 fix).
        _driver_uid_early = (
            payload.get("sub") or payload.get("user_id") or ""
        ) if payload.get("role") == "driver" else ""
        # Fase 5: Driver MUST have picked an active customer. Until they do,
        # /api/tours returns an empty list with a header hint so the UI can
        # route to the customer picker. Logistics admins use X-Acting-Company-Id
        # header for their cross-company switcher (handled elsewhere).
        active_cid = None
        if payload.get("role") == "driver":
            active_cid = await _driver_active_customer_id(payload)
            if not active_cid:
                return []
            # Re-validate the active customer is still served (defense in depth)
            if not await _driver_serves_customer(payload, active_cid):
                await _raw_db.users.update_one(
                    {"id": payload.get("sub")},
                    {"$unset": {"active_customer_id": ""}},
                )
                return []
        if la_company and la_company != SUPER_ADMIN_BYPASS:
            if active_cid:
                # Driver with active customer: STRICT filter to that customer's
                # tours that we serve. Hard cut — no cross-customer leakage.
                #
                # Fase 15.2 (2026-06-19): UNDTAGELSE — ture som er
                # pre-assigned DIREKTE til chaufføren (driver_id == self) skal
                # være synlige UANSET hvilken kunde de tilhører. Ellers kan
                # admin tildele en intern/LA-skabt tur som chaufføren aldrig
                # ser → "På vej"-knappen i bunden af Afventende ture-modal
                # virker ikke fordi turen mangler i tours-state.
                #
                # Fase 15.14 (2026-02-XX): STRIKT MULTI-TENANT ISOLATION —
                # selv driver_id-undtagelsen kræver nu at turen TILHØRER
                # chaufførens eget logistikfirma (la_company in
                # assigned_logistics_company_ids). En tur rettet til et
                # andet logistikfirma må ALDRIG vises, uanset om driver_id
                # tilfældigvis matcher (defensiv mod manuel data-korruption).
                partnership_clause = {
                    "$or": [
                        {"$and": [
                            {"company_id": active_cid},
                            {"assigned_logistics_company_ids": la_company},
                        ]},
                        {"$and": [
                            {"driver_id": _driver_uid_early or "__never_match__"},
                            {"assigned_logistics_company_ids": la_company},
                        ]},
                    ]
                }
                # 2026-10-16: Logistikfirmaets EGNE ture (oprettet af deres
                # admin/chauffører - company_id = firmaet selv). Før blev de
                # aldrig vist for chauffører.
                #   - "Egne ture" valgt (premium): alle egne ture.
                #   - En kunde valgt: egne ture på den kundes pladser (fx en
                #     ekstra/privat tur oprettet på pladsen).
                if active_cid == la_company:
                    partnership_clause["$or"].append({"company_id": la_company})
                else:
                    cust_plads = [p["name"] for p in await _raw_db.plads.find(
                        {"company_id": active_cid}, {"_id": 0, "name": 1}).to_list(2000) if p.get("name")]
                    if cust_plads:
                        partnership_clause["$or"].append(
                            {"company_id": la_company, "plads": {"$in": cust_plads}})
            else:
                # Logistics admin: union of own + served customers
                partnership_clause = {
                    "$or": [
                        {"company_id": la_company},
                        {"assigned_logistics_company_ids": la_company},
                    ]
                }
            if query:
                query = {"$and": [query, partnership_clause]}
            else:
                query = partnership_clause

        # Fase 6 (2026-06-16): Pre-assignment visibility filter.
        # Drivers ONLY see tours that are either unassigned (driver_id empty or
        # missing) OR pre-assigned to themselves. Tours pre-assigned to OTHER
        # drivers are hidden — they belong privately to that driver.
        #
        # Fase 11 (2026-06-18): Når en tur er CLAIMET (en chauffør har trykket
        # "På vej") må andre chauffører ikke se den længere — så to chauffører
        # ikke kan starte samme tur. Færdige ture beholder vi i listen indtil
        # næste dag så historikken er synlig.
        if payload.get("role") == "driver":
            driver_uid = payload.get("sub") or payload.get("user_id") or ""
            driver_name_lookup = ""
            try:
                _u = await _raw_db.users.find_one({"id": driver_uid}, {"_id": 0, "name": 1})
                driver_name_lookup = (_u or {}).get("name", "") or ""
            except Exception:
                pass
            # Tour må vises hvis: (a) pre-assignment matcher; OG (b) ikke
            # claimet af en anden chauffør (men EGEN claim er OK).
            preassign_clause = {
                "$and": [
                    {"$or": [
                        {"driver_id": {"$in": ["", None]}},
                        {"driver_id": {"$exists": False}},
                        {"driver_id": driver_uid},
                    ]},
                    {"$or": [
                        {"claimed_by_id": {"$in": ["", None]}},
                        {"claimed_by_id": {"$exists": False}},
                        {"claimed_by_id": driver_uid},
                        # Bagudkompatibilitet: ældre ture har kun claimed_by (navn).
                        {"$and": [
                            {"claimed_by_id": {"$exists": False}},
                            {"$or": [
                                {"claimed_by": {"$in": ["", None]}},
                                {"claimed_by": {"$exists": False}},
                                {"claimed_by": driver_name_lookup},
                            ]},
                        ]},
                    ]},
                ]
            }
            if query:
                # Merge with existing $and if present, else wrap
                if "$and" in query and isinstance(query["$and"], list):
                    query["$and"].append(preassign_clause)
                else:
                    query = {"$and": [query, preassign_clause]}
            else:
                query = preassign_clause

        tours = await _raw_db.tours.find(query, {"_id": 0, "receipt_image": 0}).to_list(min(limit, 500))
        if payload.get("role") == "logistics_admin":
            _scope = await _la_scope(payload)
            if _scope:
                tours = [t for t in tours if _scope_ok(t, _scope, la_company)]
        # Enrich each tour with its customer (company) name so both driver and
        # logistics_admin UIs can visually separate tours coming from different
        # customers (e.g. ARGO vs MARTO under the same logistics company).
        cust_ids = {t.get("company_id") for t in tours if t.get("company_id") and t.get("company_id") != la_company}
        cust_map = {}
        if cust_ids:
            async for c in _raw_db.companies.find(
                {"id": {"$in": list(cust_ids)}}, {"_id": 0, "id": 1, "name": 1, "customer_id": 1},
            ):
                cust_map[c["id"]] = {"name": c.get("name", ""), "customer_id": c.get("customer_id") or ""}
        for t in tours:
            cid = t.get("company_id")
            if cid and cid != la_company and cid in cust_map:
                t["customer_name"] = cust_map[cid]["name"]
                t["customer_code"] = cust_map[cid]["customer_id"]
            else:
                t["customer_name"] = ""
                t["customer_code"] = ""
        return tours

    # All other roles use the standard tenant-aware filter
    tours = await db.tours.find(query, {"_id": 0, "receipt_image": 0}).to_list(min(limit, 500))
    return tours

def _stamp_logistics_creator(doc: dict, payload: Optional[dict]) -> dict:
    """2026-10-16: Ture som et logistikfirmas admin eller chauffør opretter
    manuelt knyttes til firmaet (assigned_logistics_company_ids), så deres
    chauffører kan se dem. Før manglede feltet, og manuelle ture dukkede
    aldrig op i chauffør-appen."""
    if payload and payload.get("role") in ("logistics_admin", "driver"):
        la = payload.get("company_id") or ""
        if la and la != SUPER_ADMIN_BYPASS:
            ids = list(doc.get("assigned_logistics_company_ids") or [])
            if la not in ids:
                ids.append(la)
            doc["assigned_logistics_company_ids"] = ids
    return doc


CONTAINER_TASK_TYPES = {"normal", "flyt", "vaerksted", "afhent_vaerksted", "loes_afhentning", "estimat"}
GOODS_TASK_TYPES = {"afhentning", "levering", "afhent_lever", "flytning", "andet"}


def _clean_cargo_lines(lines: Any, trailer_count: int) -> List[dict]:
    out = []
    for ln in (lines or [])[:20]:
        if not isinstance(ln, dict):
            continue
        text = str(ln.get("text") or "").strip()[:120]
        if not text:
            continue
        tr = ln.get("trailer")
        try:
            tr = int(tr) if tr not in (None, "") else None
        except (TypeError, ValueError):
            tr = None
        if tr is not None and not (1 <= tr <= max(trailer_count, 1)):
            tr = None
        item = {"text": text, "trailer": tr}
        if ln.get("qty") not in (None, ""):
            try:
                item["qty"] = float(ln["qty"])
            except (TypeError, ValueError):
                pass
        if ln.get("unit"):
            item["unit"] = str(ln["unit"])[:20]
        out.append(item)
    return out


def _fmt_addr(parts: dict) -> str:
    tail = " ".join(x for x in [parts.get("postal") or "", parts.get("city") or ""] if x)
    return ", ".join(x for x in [parts.get("street") or "", tail] if x)


def _clean_stops(stops: Any, previous: Optional[List[dict]] = None) -> List[dict]:
    """Rens stop-listen. Bevarer "udført" for stop der allerede fandtes."""
    prev = {s.get("id"): s for s in (previous or []) if isinstance(s, dict)}
    out = []
    for st in (stops or [])[:20]:
        if not isinstance(st, dict):
            continue
        parts = {k: str(st.get(k) or "").strip()[:120] for k in ("street", "postal", "city")}
        addr = str(st.get("address") or "").strip()[:200] or _fmt_addr(parts)
        if not addr:
            continue
        sid = str(st.get("id") or "") or str(uuid.uuid4())
        old = prev.get(sid) or {}
        out.append({
            "id": sid, "kind": "delivery" if st.get("kind") == "delivery" else "pickup",
            **{k: v for k, v in parts.items() if v}, "address": addr,
            "note": str(st.get("note") or "").strip()[:200],
            "done_at": old.get("done_at") or "", "done_by": old.get("done_by") or "",
        })
    return out


def _apply_stops(td: dict) -> None:
    """address/facility (+ parts) spejler første afhentning og sidste aflevering."""
    stops = td.get("stops") or []
    if not stops:
        return
    picks = [s for s in stops if s["kind"] == "pickup"] or stops[:1]
    dels = [s for s in stops if s["kind"] == "delivery"]
    first = picks[0]
    td["address"] = first["address"]
    td["address_parts"] = {k: first[k] for k in ("street", "postal", "city") if first.get(k)}
    if dels:
        last = dels[-1]
        td["facility"] = last["address"]
        td["facility_parts"] = {k: last[k] for k in ("street", "postal", "city") if last.get(k)}


async def _normalize_tour_doc(td: dict, payload: Optional[dict], profile_cache: dict) -> dict:
    """2026-10-17: Ensretter en ny tur efter hvor den hører til.
    - Tur på en genbrugsplads-kundes plads (B2B) eller hos et partner-firma
      (option 2): altid containertur; hængere/indhold er premium-funktioner.
    - Premium-firmaets egne ture: "container" eller "goods" (gods/andet).
    - Opgavetypen skal passe til typen; fraktion udfyldes fra indholdslinjer."""
    role = (payload or {}).get("role")
    la = (payload or {}).get("company_id") if role in ("logistics_admin", "driver") else None
    premium = False
    if la:
        if la not in profile_cache:
            profile_cache[la] = await _logistics_profile(la)
        premium = bool(profile_cache[la].get("is_premium"))
    customer_site = False
    if td.get("plads"):
        pl = await _raw_db.plads.find_one({"name": td["plads"]}, {"_id": 0, "company_id": 1})
        customer_site = bool(pl and la and pl.get("company_id") != la)
    kind = td.get("tour_kind") if td.get("tour_kind") in ("container", "goods") else "container"
    if not premium or customer_site:
        kind = "container"
    td["tour_kind"] = kind
    if not premium:
        td["trailer_count"] = 0
        td["cargo_lines"] = []
    tc = max(0, min(int(td.get("trailer_count") or 0), 9))
    td["trailer_count"] = tc
    td["cargo_lines"] = _clean_cargo_lines(td.get("cargo_lines"), tc)
    tt = td.get("tour_type") or ""
    if kind == "goods":
        if tt not in GOODS_TASK_TYPES:
            td["tour_type"] = "afhentning"
        td["container"] = ""
        td["container_type"] = ""
        td["loose_estimated_count"] = 0
    elif tt not in CONTAINER_TASK_TYPES:
        td["tour_type"] = "normal"
    if td["cargo_lines"] and not (td.get("fraction") or "").strip():
        td["fraction"] = " + ".join(dict.fromkeys(l["text"] for l in td["cargo_lines"]))
    if not (td.get("fraction") or "").strip():
        raise HTTPException(status_code=400, detail="Skriv materiale eller hvad der skal køres")
    if not (td.get("facility") or "").strip():
        td["facility"] = td.get("plads") or ""
    for key in ("address_parts", "facility_parts"):
        parts = td.get(key) or {}
        td[key] = {k: str(parts.get(k) or "").strip()[:120] for k in ("street", "postal", "city") if parts.get(k)}
    td["stops"] = _clean_stops(td.get("stops"))
    # Én stop er ikke en stop-liste - så er address/facility nok.
    if len(td["stops"]) <= 1:
        td["stops"] = []
    _apply_stops(td)
    return td


@api_router.post("/tours", response_model=Tour)
async def create_tour(tour: TourCreate, payload: dict = Depends(get_current_user_payload)):
    tour_data = tour.model_dump()
    tour_data["date"] = normalize_date(tour_data.get("date", ""))
    tour_data.pop("agreed_price", None)
    tour_data.pop("agreed_add_waiting", None)
    await _normalize_tour_doc(tour_data, payload, {})
    # Fase 15 (2026-06-19): Auto-generér kort tur-nummer hvis ikke sat.
    if not tour_data.get("tour_number"):
        tour_data["tour_number"] = await _generate_tour_number(
            tour_data.get("customer_code") or "",
            tour_data.get("customer_name") or "",
        )
    tour_obj = Tour(**tour_data)
    doc = _stamp_logistics_creator(tour_obj.model_dump(), payload)
    await db.tours.insert_one(doc)
    _push_later(_push_new_haster([dict(doc)]))
    return tour_obj

@api_router.post("/tours/bulk", response_model=List[Tour])
async def create_tours_bulk(tours: List[TourCreate], payload: Optional[dict] = Depends(get_optional_user_payload)):
    """Optimized bulk insert using insert_many"""
    if not tours:
        return []
    try:
        if any(t.agreed_price is not None for t in tours):
            await _require_perm(payload, "economy_edit")
        tour_objs = []
        agreed: Dict[str, tuple] = {}
        prof_cache: dict = {}
        for t in tours:
            td = t.model_dump()
            ap = td.pop("agreed_price", None)
            add_wait = bool(td.pop("agreed_add_waiting", True))
            await _normalize_tour_doc(td, payload, prof_cache)
            td["date"] = normalize_date(td.get("date", ""))
            # Fase 15 (2026-06-19): Auto-generér kort tur-nummer.
            if not td.get("tour_number"):
                td["tour_number"] = await _generate_tour_number(
                    td.get("customer_code") or "",
                    td.get("customer_name") or "",
                )
            tour_objs.append(Tour(**td))
            if ap is not None:
                agreed[tour_objs[-1].id] = (float(ap), add_wait)
        docs = [_stamp_logistics_creator(t.model_dump(), payload) for t in tour_objs]
        if agreed:
            who = (payload or {}).get("email") or ""
            now_iso = datetime.now(timezone.utc).isoformat()
            for d in docs:
                if d["id"] in agreed:
                    amt, add_wait = agreed[d["id"]]
                    po = {"mode": "fixed", "amount": amt, "extra_lines": [], "label": "Aftalt pris",
                          "add_waiting": add_wait}
                    d["price_override"] = po
                    d["price_history"] = [{"at": now_iso, "by": who, "note": "Aftalt pris ved oprettelse",
                                           "kind": "admin", "fact_overrides": {}, "price_override": po}]
        await db.tours.insert_many(docs)
        _push_later(_push_new_haster([dict(d) for d in docs]))
        return tour_objs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk tour create error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create tours")

# Tour reorder - must be before /tours/{tour_id} to avoid route conflict
@api_router.put("/tours/reorder")
async def reorder_tours(request: TourReorderRequest):
    """Update sort_order for multiple tours - optimized with bulk_write"""
    tour_orders = request.tours
    if not tour_orders:
        return {"message": "Nothing to reorder"}
    try:
        from pymongo import UpdateOne
        operations = [
            UpdateOne({"id": item.id}, {"$set": {"sort_order": item.sort_order}})
            for item in tour_orders
        ]
        await db.tours.bulk_write(operations)
        return {"message": f"Updated order for {len(tour_orders)} tours"}
    except Exception as e:
        logger.error(f"Tour reorder error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reorder")


# Fase 15 (2026-06-19): Bulk-tildeling — Logistik Admin kan markere flere
# ikke-tildelte ture og tildele dem til ÉN chauffør i én handling.
# Body: {"tour_ids": [..], "driver_id": "uuid", "driver_name": "..."}
class BulkAssignRequest(BaseModel):
    tour_ids: List[str]
    driver_id: str
    driver_name: str = ""


@api_router.post("/tours/bulk-assign")
async def bulk_assign_tours(
    body: BulkAssignRequest,
    payload: dict = Depends(get_current_user_payload),
):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin kan masse-tildele ture")
    if not body.tour_ids:
        return {"updated": 0}
    # Resolve driver name if not provided
    driver_name = (body.driver_name or "").strip()
    if not driver_name and body.driver_id:
        drv = await _raw_db.users.find_one(
            {"id": body.driver_id}, {"_id": 0, "name": 1, "display_name": 1, "email": 1}
        )
        if drv:
            driver_name = drv.get("display_name") or drv.get("name") or drv.get("email") or ""
    assigner_name = (
        payload.get("name") or payload.get("display_name") or ""
    )
    caller_id = payload.get("sub") or payload.get("user_id") or ""
    # Fase 15.8 (2026-02-XX): Fald aldrig tilbage til email — slå det reelle
    # display-navn op i DB så chaufføren ser "Tildelt af Mike Turan" frem for
    # "Tildelt af mike@firma.dk".
    if not assigner_name and caller_id:
        admin_doc = await _raw_db.users.find_one(
            {"id": caller_id}, {"_id": 0, "display_name": 1, "name": 1, "email": 1}
        )
        if admin_doc:
            assigner_name = (
                (admin_doc.get("display_name") or "").strip()
                or (admin_doc.get("name") or "").strip()
                or (admin_doc.get("email") or "").strip()
            )
    if not assigner_name:
        assigner_name = payload.get("email") or ""
    now_iso = datetime.now(DK_TZ).isoformat()

    # 2026-10-16: En logistik-admin må kun tildele ture firmaet faktisk har
    # adgang til (egne eller tildelt firmaet) - før kunne et vilkårligt tur-id
    # sendes med.
    if role == "logistics_admin":
        la = payload.get("company_id") or ""
        allowed = await _raw_db.tours.find(
            {"id": {"$in": body.tour_ids},
             "$or": [{"company_id": la}, {"assigned_logistics_company_ids": la}]},
            {"_id": 0, "id": 1}).to_list(len(body.tour_ids) + 1)
        body.tour_ids = await _require_tour_scope(payload, [t["id"] for t in allowed])
        if not body.tour_ids:
            return {"updated": 0}
    from pymongo import UpdateOne
    update_set = {
        "driver_id": body.driver_id,
        "driver_name": driver_name,
        "assigned_by_id": caller_id,
        "assigned_by_name": assigner_name,
        "assigned_at": now_iso,
    }
    ops = [UpdateOne({"id": tid}, {"$set": update_set}) for tid in body.tour_ids]
    if not ops:
        return {"updated": 0}
    res = await _raw_db.tours.bulk_write(ops)

    # Audit log per tour (best-effort)
    for tid in body.tour_ids:
        try:
            existing = await _raw_db.tours.find_one(
                {"id": tid}, {"_id": 0, "driver_id": 1, "driver_name": 1}
            )
            await _tour_audit(
                tour_id=tid,
                action="bulk_assign",
                payload=payload,
                before={
                    "driver_id": (existing or {}).get("driver_id", ""),
                    "driver_name": (existing or {}).get("driver_name", ""),
                },
                after={"driver_id": body.driver_id, "driver_name": driver_name},
            )
        except Exception as e:
            logger.error(f"Bulk-assign audit failed for {tid}: {e}")

    if body.driver_id and res.modified_count:
        n = len(body.tour_ids)
        _push_later(_push_driver(
            payload.get("company_id") or "", body.driver_id, driver_name,
            "Ny tur tildelt" if n == 1 else f"{n} nye ture tildelt",
            f"{assigner_name or 'Planlæggeren'} har givet dig {('en tur' if n == 1 else f'{n} ture')}."))
    return {"updated": res.modified_count, "assigned_to": driver_name}


# ============= TUR-BESKEDER (planlægger <-> chauffør pr. tur) =============
# 2026-10-16: Den gamle `messages`-kollektion er navnebaseret og ikke knyttet
# til en tur. Her får hver tur sin egen tråd, så "containeren står bag porten"
# eller "ring til kunden først" står præcis ved den tur det handler om.
# Felter: id, tour_id, logistics_company_id, driver_id (modtager/afsender),
# sender_role ("planner" | "driver"), sender_id, sender_name, text,
# created_at, read_by_driver, read_by_planner.

class TourMessageIn(BaseModel):
    text: str


async def _push_driver(company_id: str, driver_id: str, driver_name: str, title: str, body: str,
                       url: str = "/", tag: str = "") -> int:
    """Web push til én chauffør på alle vedkommendes enheder (best effort).
    Respekterer chaufførens valg (users.push_enabled = False => intet).
    Udløbne abonnementer (404/410) ryddes. Returnerer antal sendte."""
    try:
        from pywebpush import webpush, WebPushException
        import json as _json
        if not _vapid_key():
            return 0
        user = None
        if driver_id:
            user = await _raw_db.users.find_one({"id": driver_id}, {"_id": 0, "id": 1, "name": 1, "push_enabled": 1, "company_id": 1})
        if not user and driver_name:
            q = {"name": driver_name, "role": "driver"}
            if company_id:
                q["company_id"] = company_id
            user = await _raw_db.users.find_one(q, {"_id": 0, "id": 1, "name": 1, "push_enabled": 1, "company_id": 1})
        if not user or user.get("push_enabled") is False:
            return 0
        subs = await _raw_db.push_subscriptions.find({"driver_id": user["id"]}, {"_id": 0}).to_list(20)
        if not subs:  # ældre abonnementer uden driver_id
            subs = await _raw_db.push_subscriptions.find(
                {"driver_name": user.get("name"), "company_id": user.get("company_id")}, {"_id": 0}).to_list(20)
        data = _json.dumps({"title": title, "body": (body or "")[:180], "url": url or "/", "tag": tag or ""})

        def _send(sub):
            try:
                webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                        data=data, vapid_private_key=_vapid_key(),
                        vapid_claims={"sub": VAPID_CLAIMS_EMAIL}, ttl=3600)
                return "ok"
            except WebPushException as e:  # noqa: PERF203
                code = getattr(getattr(e, "response", None), "status_code", None)
                return "gone" if code in (404, 410) else f"err {code}"
            except Exception as e:  # noqa: BLE001
                return f"err {e}"
        sent = 0
        for sub in subs:
            res = await async_lib.to_thread(_send, sub)
            if res == "ok":
                sent += 1
            elif res == "gone":
                await _raw_db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
            else:
                logger.warning(f"push to {user.get('name')} failed: {res}")
        return sent
    except Exception as e:  # noqa: BLE001
        logger.warning(f"push to driver failed: {e}")
        return 0


def _push_later(coro):
    """Send push i baggrunden, så requesten ikke venter på push-tjenesten."""
    try:
        async_lib.get_running_loop().create_task(coro)
    except RuntimeError:
        pass


async def _push_new_haster(tours: List[dict]):
    """Ny HASTER-tur uden chauffør: besked til firmaets chauffører der har
    stemplet ind i dag (ikke dem der har fri)."""
    try:
        for t in tours:
            if not isHaster_tour(t) or t.get("driver_id") or t.get("claimed_by"):
                continue
            firms = list(t.get("assigned_logistics_company_ids") or [])
            if not firms and t.get("company_id"):
                firms = [t["company_id"]]
            today = datetime.now(DK_TZ).strftime("%Y-%m-%d")
            if (t.get("date") or today) > today:
                continue
            for firm in firms:
                drivers = await _raw_db.users.find({"role": "driver", "company_id": firm, "active": {"$ne": False}},
                                                   {"_id": 0, "id": 1, "name": 1}).to_list(500)
                ids = [d["id"] for d in drivers]
                working = set(await _raw_db.driver_time_entries.distinct(
                    "driver_id", {"driver_id": {"$in": ids}, "date": today,
                                  "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}))
                for d in drivers:
                    if d["id"] in working:
                        await _push_driver(firm, d["id"], d.get("name", ""), "HASTER-tur",
                                           f"{t.get('fraction') or 'Tur'} · {t.get('address') or t.get('plads') or ''}",
                                           tag=f"haster-{t.get('id')}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"haster push failed: {e}")


def isHaster_tour(t: dict) -> bool:
    p = str(t.get("priority") or "").lower()
    return p in ("urgent", "haster", "high") or "haster" in (t.get("remark") or "").lower()


def _tour_logistics_company(tour: dict, payload: dict) -> str:
    cid = payload.get("company_id") or ""
    if payload.get("role") == "super_admin":
        ids = tour.get("assigned_logistics_company_ids") or []
        return ids[0] if ids else (tour.get("company_id") or "")
    return cid


async def _tour_for_messages(tour_id: str, payload: dict) -> dict:
    tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "receipt_image": 0})
    if not tour:
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    role = payload.get("role")
    if role == "super_admin":
        return tour
    cid = payload.get("company_id") or ""
    if role not in ("logistics_admin", "driver") or not cid:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    if tour.get("company_id") != cid and cid not in (tour.get("assigned_logistics_company_ids") or []):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    if role == "logistics_admin" and not _scope_ok(tour, await _la_scope(payload), cid):
        raise HTTPException(status_code=403, detail="Turen hører til en kunde du ikke har adgang til")
    if role == "driver":
        uid = payload.get("sub") or ""
        if (tour.get("driver_id") or "") not in ("", uid) or (tour.get("claimed_by_id") or "") not in ("", uid):
            raise HTTPException(status_code=403, detail="Turen er tildelt en anden chauffør")
    return tour


def _tour_driver_id(tour: dict) -> str:
    return tour.get("driver_id") or tour.get("claimed_by_id") or ""


# ============= EGNE KUNDER (logistikfirmaets egne slutkunder) =============
# 2026-10-17: Et logistikfirma kan registrere sine egne kunder (fx byggefirmaer
# på egne ture), så de kan vælges i "Ny tur" og få priser i Økonomi, FØR der
# findes ture. Priser kobles via nøglen "firma:<normaliseret navn>" - samme
# nøgle som egne ture med `private_company` har altid haft, så eksisterende
# regler og ture virker uændret.
class LogiCustomerIn(BaseModel):
    name: str = ""
    cvr: str = ""
    address: str = ""
    contact: str = ""
    phone: str = ""
    email: str = ""
    note: str = ""
    active: Optional[bool] = None


def _firma_key(name: str) -> str:
    return f"firma:{_pricing.norm_label(name)}"


async def _logi_cid(payload: dict) -> str:
    if payload.get("role") != "logistics_admin":
        raise HTTPException(status_code=403, detail="Kun logistik admin")
    return payload.get("company_id") or ""


@api_router.get("/logistics/customers")
async def logi_customers_list(payload: dict = Depends(get_current_user_payload)):
    cid = await _logi_cid(payload)
    docs = await _raw_db.logistics_customers.find({"company_id": cid}, {"_id": 0}).sort("name", 1).to_list(2000)
    for d in docs:
        d["price_key"] = _firma_key(d["name"])
    return docs


@api_router.post("/logistics/customers")
async def logi_customers_create(body: LogiCustomerIn, payload: dict = Depends(get_current_user_payload)):
    cid = await _logi_cid(payload)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skriv kundens navn")
    key = _pricing.norm_label(name)
    for d in await _raw_db.logistics_customers.find({"company_id": cid}, {"_id": 0, "name": 1}).to_list(2000):
        if _pricing.norm_label(d["name"]) == key:
            raise HTTPException(status_code=409, detail="Kunden findes allerede")
    doc = {**body.model_dump(exclude={"active"}), "name": name, "id": str(uuid.uuid4()), "company_id": cid,
           "active": True, "created_at": datetime.now(timezone.utc).isoformat()}
    await _raw_db.logistics_customers.insert_one(dict(doc))
    doc["price_key"] = _firma_key(name)
    return doc


@api_router.put("/logistics/customers/{cust_id}")
async def logi_customers_update(cust_id: str, body: LogiCustomerIn, payload: dict = Depends(get_current_user_payload)):
    cid = await _logi_cid(payload)
    cur = await _raw_db.logistics_customers.find_one({"id": cust_id, "company_id": cid}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Kunde ikke fundet")
    upd = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    new_name = upd.get("name") or cur["name"]
    upd["name"] = new_name
    old_key, new_key = _firma_key(cur["name"]), _firma_key(new_name)
    if new_key != old_key:
        for d in await _raw_db.logistics_customers.find({"company_id": cid, "id": {"$ne": cust_id}}, {"_id": 0, "name": 1}).to_list(2000):
            if _firma_key(d["name"]) == new_key:
                raise HTTPException(status_code=409, detail="Der findes allerede en kunde med det navn")
        # Navnet er nøglen for priser og egne ture - flyt dem med.
        await _raw_db.price_rules.update_many(
            {"company_id": cid, "conditions.customer_ids": old_key},
            {"$set": {"conditions.customer_ids.$": new_key}})
        await _raw_db.tours.update_many({"company_id": cid, "private_company": cur["name"]},
                                        {"$set": {"private_company": new_name}})
    await _raw_db.logistics_customers.update_one({"id": cust_id}, {"$set": upd})
    return {**cur, **upd, "price_key": new_key}


@api_router.delete("/logistics/customers/{cust_id}")
async def logi_customers_delete(cust_id: str, payload: dict = Depends(get_current_user_payload)):
    """Kunden skjules (deaktiveres). Ture og priser bevares."""
    cid = await _logi_cid(payload)
    res = await _raw_db.logistics_customers.update_one({"id": cust_id, "company_id": cid}, {"$set": {"active": False}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Kunde ikke fundet")
    return {"deactivated": True}


# ============= TEAM (logistik admin + koordinatorer) =============
class TeamMemberIn(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    permissions: Dict[str, bool] = Field(default_factory=dict)
    active: Optional[bool] = None
    customer_scope: Optional[List[str]] = None


def _team_public(u: dict) -> dict:
    return {
        "id": u.get("id"), "name": u.get("name") or "", "email": u.get("email") or "",
        "phone": u.get("phone") or "", "is_coordinator": bool(u.get("is_coordinator")),
        "permissions": _effective_perms(u), "active": u.get("active", True),
        "invitation_status": u.get("invitation_status") or "active",
        "created_at": u.get("created_at") or "", "invited_by_name": u.get("invited_by_name") or "",
        "customer_scope": list(u.get("customer_scope") or []),
    }


def _grantable_scope(me: dict, wanted: Optional[List[str]]) -> List[str]:
    """Tom liste = alle kunder. En begrænset koordinator kan kun give
    adgang inden for sin egen begrænsning."""
    w = [str(x) for x in (wanted or []) if str(x).strip()]
    mine = list(me.get("customer_scope") or []) if me.get("is_coordinator") else []
    if mine:
        w = [x for x in w if x in mine] or mine
    return w


async def _team_caller(payload: dict) -> dict:
    if payload.get("role") != "logistics_admin":
        raise HTTPException(status_code=403, detail="Kun logistik admin")
    me = await _raw_db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not me:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    return me


def _grantable(me: dict, wanted: Dict[str, bool]) -> Dict[str, bool]:
    """En koordinator kan kun give rettigheder vedkommende selv har."""
    mine = _effective_perms(me)
    return {k: bool(wanted.get(k)) and mine.get(k, False) for k in COORDINATOR_PERM_KEYS}


@api_router.get("/logistics/team")
async def team_list(payload: dict = Depends(get_current_user_payload)):
    me = await _team_caller(payload)
    users = await _raw_db.users.find(
        {"company_id": me["company_id"], "role": "logistics_admin"},
        {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(200)
    company = await _raw_db.companies.find_one({"id": me["company_id"]}, {"_id": 0, "dispatch_phone": 1, "dispatch_name": 1}) or {}
    prof = await _logistics_profile(me["company_id"])
    scope_options = [{"id": "own", "name": "Egne ture og kunder"}] if prof.get("is_premium") else []
    scope_options += [{"id": c["id"], "name": c["name"]} for c in (prof.get("connected_customers") or [])]
    return {
        "members": [_team_public(u) for u in users],
        "scope_options": scope_options,
        "catalog": [{"key": k, "label": l} for k, l in COORDINATOR_PERMS],
        "me": {"id": me["id"], "is_coordinator": bool(me.get("is_coordinator")), "permissions": _effective_perms(me)},
        "dispatch_phone": company.get("dispatch_phone") or "",
        "dispatch_name": company.get("dispatch_name") or "",
    }


@api_router.post("/logistics/team")
async def team_invite(body: TeamMemberIn, payload: dict = Depends(get_current_user_payload)):
    me = await _team_caller(payload)
    email = (body.email or "").strip().lower()
    name = (body.name or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Skriv en gyldig e-mail")
    if not name:
        raise HTTPException(status_code=400, detail="Skriv et navn")
    if await _raw_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Der findes allerede en bruger med den e-mail")
    doc = {
        "id": str(uuid.uuid4()), "email": email, "name": name, "phone": (body.phone or "").strip(),
        "role": "logistics_admin", "is_coordinator": True, "permissions": _grantable(me, body.permissions),
        "customer_scope": _grantable_scope(me, body.customer_scope),
        "company_id": me["company_id"], "active": True, "invitation_status": "pending", "password_hash": "",
        "managed_company_ids": [], "assigned_plads_ids": [], "visible_plads_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "invited_by_id": me["id"], "invited_by_name": me.get("name") or me.get("email") or "",
    }
    await _raw_db.users.insert_one(dict(doc))
    try:
        await _send_invite_for_user(doc)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Coordinator invitation failed for {email}: {e}")
    return _team_public(doc)


@api_router.put("/logistics/team/{user_id}")
async def team_update(user_id: str, body: TeamMemberIn, payload: dict = Depends(get_current_user_payload)):
    me = await _team_caller(payload)
    u = await _raw_db.users.find_one({"id": user_id, "company_id": me["company_id"], "role": "logistics_admin"}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    upd: Dict[str, Any] = {}
    if body.name.strip():
        upd["name"] = body.name.strip()
    upd["phone"] = (body.phone or "").strip()
    if u.get("is_coordinator"):
        if user_id == me["id"]:
            raise HTTPException(status_code=403, detail="Du kan ikke ændre dine egne rettigheder")
        upd["permissions"] = _grantable(me, body.permissions)
        if body.customer_scope is not None:
            upd["customer_scope"] = _grantable_scope(me, body.customer_scope)
        if body.active is not None:
            upd["active"] = bool(body.active)
    elif user_id != me["id"] and me.get("is_coordinator"):
        raise HTTPException(status_code=403, detail="En koordinator kan ikke ændre en administrator")
    await _raw_db.users.update_one({"id": user_id}, {"$set": upd})
    _perm_cache.pop(user_id, None)
    return _team_public({**u, **upd})


@api_router.delete("/logistics/team/{user_id}")
async def team_remove(user_id: str, payload: dict = Depends(get_current_user_payload)):
    me = await _team_caller(payload)
    u = await _raw_db.users.find_one({"id": user_id, "company_id": me["company_id"], "role": "logistics_admin"}, {"_id": 0})
    if not u or not u.get("is_coordinator"):
        raise HTTPException(status_code=404, detail="Koordinator ikke fundet")
    if user_id == me["id"]:
        raise HTTPException(status_code=400, detail="Du kan ikke fjerne dig selv")
    if u.get("invitation_status") == "pending":
        await _raw_db.users.delete_one({"id": user_id})
        await _raw_db.invitation_tokens.delete_many({"user_id": user_id})
        return {"removed": True}
    await _raw_db.users.update_one({"id": user_id}, {"$set": {"active": False}})
    _perm_cache.pop(user_id, None)
    return {"deactivated": True}


@api_router.post("/logistics/team/{user_id}/resend")
async def team_resend(user_id: str, payload: dict = Depends(get_current_user_payload)):
    me = await _team_caller(payload)
    u = await _raw_db.users.find_one({"id": user_id, "company_id": me["company_id"], "role": "logistics_admin"}, {"_id": 0})
    if not u or u.get("invitation_status") != "pending":
        raise HTTPException(status_code=404, detail="Ingen afventende invitation")
    await _send_invite_for_user(u)
    return {"sent": True}


class DispatchContactIn(BaseModel):
    phone: str = ""
    name: str = ""


@api_router.put("/logistics/team-contact")
async def team_contact(body: DispatchContactIn, payload: dict = Depends(get_current_user_payload)):
    """Disponent-telefon som chaufførerne ringer til (fallback når den der
    tildelte turen ikke har et nummer). Kræver team-rettighed."""
    me = await _team_caller(payload)
    await _require_perm(payload, "team")
    await _raw_db.companies.update_one({"id": me["company_id"]}, {"$set": {
        "dispatch_phone": (body.phone or "").strip(), "dispatch_name": (body.name or "").strip()}})
    return {"dispatch_phone": (body.phone or "").strip(), "dispatch_name": (body.name or "").strip()}


@api_router.get("/driver/dispatch-contact")
async def driver_dispatch_contact(tour_id: str = "", payload: dict = Depends(get_current_user_payload)):
    """Hvem chaufføren ringer til om en tur: den der tildelte turen (hvis
    vedkommende har et nummer), ellers firmaets disponent-telefon."""
    cid = payload.get("company_id") or ""
    if tour_id:
        t = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "assigned_by_id": 1, "company_id": 1,
                                                          "assigned_logistics_company_ids": 1})
        if t and (t.get("company_id") == cid or cid in (t.get("assigned_logistics_company_ids") or [])) and t.get("assigned_by_id"):
            u = await _raw_db.users.find_one({"id": t["assigned_by_id"], "company_id": cid, "active": {"$ne": False}},
                                             {"_id": 0, "name": 1, "phone": 1})
            if u and (u.get("phone") or "").strip():
                return {"phone": u["phone"].strip(), "name": u.get("name") or "Planlægger"}
    c = await _raw_db.companies.find_one({"id": cid}, {"_id": 0, "dispatch_phone": 1, "dispatch_name": 1}) or {}
    return {"phone": (c.get("dispatch_phone") or "").strip(), "name": c.get("dispatch_name") or "Disponent"}


@api_router.get("/tour-messages/unread")
async def tour_messages_unread(payload: dict = Depends(get_current_user_payload)):
    """Ulæste tur-beskeder for den der spørger: {unread: {tour_id: n}, total, latest[]}."""
    role = payload.get("role")
    cid = payload.get("company_id") or ""
    if role == "driver":
        uid = payload.get("sub") or ""
        q = {"logistics_company_id": cid, "sender_role": "planner", "read_by_driver": False,
             "driver_id": {"$in": [uid, ""]}}
    elif role == "logistics_admin":
        q = {"logistics_company_id": cid, "sender_role": "driver", "read_by_planner": False}
    elif role == "super_admin":
        q = {"sender_role": "driver", "read_by_planner": False}
    else:
        return {"unread": {}, "total": 0, "latest": []}
    msgs = await _raw_db.tour_messages.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    if role == "driver" and msgs:
        # Beskeder på ikke-tildelte ture tæller kun hvis turen stadig er fri
        # eller min - ikke hvis en kollega har taget den i mellemtiden.
        uid = payload.get("sub") or ""
        tids = list({m["tour_id"] for m in msgs})
        ok = {t["id"] for t in await _raw_db.tours.find(
            {"id": {"$in": tids}, "completed": {"$ne": True},
             "driver_id": {"$in": ["", None, uid]}, "claimed_by_id": {"$in": ["", None, uid]}},
            {"_id": 0, "id": 1}).to_list(len(tids) + 1)}
        msgs = [m for m in msgs if m["tour_id"] in ok]
    if role == "logistics_admin" and msgs:
        _scope = await _la_scope(payload)
        if _scope:
            tids = list({m["tour_id"] for m in msgs})
            ok = {t["id"] for t in await _raw_db.tours.find({"id": {"$in": tids}}, {"_id": 0, "id": 1, "company_id": 1}).to_list(len(tids) + 1)
                  if _scope_ok(t, _scope, cid)}
            msgs = [m for m in msgs if m["tour_id"] in ok]
    unread = {}
    for m in msgs:
        unread[m["tour_id"]] = unread.get(m["tour_id"], 0) + 1
    return {"unread": unread, "total": len(msgs), "latest": msgs[:10]}


@api_router.get("/tour-messages/{tour_id}")
async def get_tour_messages(tour_id: str, payload: dict = Depends(get_current_user_payload)):
    tour = await _tour_for_messages(tour_id, payload)
    msgs = await _raw_db.tour_messages.find({"tour_id": tour_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    now = datetime.now(timezone.utc).isoformat()
    if payload.get("role") == "driver":
        await _raw_db.tour_messages.update_many(
            {"tour_id": tour_id, "sender_role": "planner", "read_by_driver": False},
            {"$set": {"read_by_driver": True, "read_by_driver_at": now}})
    elif payload.get("role") in ("logistics_admin", "super_admin"):
        await _raw_db.tour_messages.update_many(
            {"tour_id": tour_id, "sender_role": "driver", "read_by_planner": False},
            {"$set": {"read_by_planner": True, "read_by_planner_at": now}})
    return {"tour": {k: tour.get(k) for k in ("id", "tour_number", "fraction", "address", "plads",
                                                  "driver_id", "driver_name", "claimed_by", "date")},
            "messages": msgs}


@api_router.post("/tour-messages/{tour_id}")
async def post_tour_message(tour_id: str, body: TourMessageIn, payload: dict = Depends(get_current_user_payload)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Beskeden er tom")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Beskeden er for lang (max 1000 tegn)")
    tour = await _tour_for_messages(tour_id, payload)
    role = payload.get("role")
    uid = payload.get("sub") or ""
    me = await _raw_db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "display_name": 1, "email": 1}) or {}
    sender_name = (me.get("display_name") or me.get("name") or me.get("email") or payload.get("email") or "").strip()
    is_driver = role == "driver"
    msg = {
        "id": str(uuid.uuid4()),
        "tour_id": tour_id,
        "logistics_company_id": _tour_logistics_company(tour, payload),
        "driver_id": uid if is_driver else _tour_driver_id(tour),
        "sender_role": "driver" if is_driver else "planner",
        "sender_id": uid,
        "sender_name": sender_name,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read_by_driver": is_driver,
        "read_by_planner": not is_driver,
    }
    await _raw_db.tour_messages.insert_one(dict(msg))
    if not is_driver and msg["driver_id"]:
        label = tour.get("tour_number") or tour.get("fraction") or "din tur"
        _push_later(_push_driver(msg["logistics_company_id"], msg["driver_id"],
                                 tour.get("driver_name") or tour.get("claimed_by") or "",
                                 f"Besked om {label}", f"{sender_name}: {text}", tag=f"msg-{tour_id}"))
    return msg


# ============= FASE 5: DRIVER ACTIVE-CUSTOMER (multi-kunde isolation) =============
# Chauffører hos et logistik-firma der betjener FLERE kunder skal eksplicit
# vælge HVILKEN kunde de kører for "lige nu". Backend håndhæver dette ved at
# kræve `active_customer_id` for at returnere tours/plads, og verificerer at
# kunden faktisk er en gyldig partner af driver's firma. Ingen data lækker
# mellem kunder — hverken tours, ordrer, plads eller historik.


async def _driver_serves_customer(driver_payload: dict, customer_id: str) -> bool:
    """Re-validate that the driver's logistics company actually serves this
    customer. Called on EVERY tour/plads request to prevent stale-session
    privilege escalation."""
    drv_company_id = driver_payload.get("company_id")
    if not drv_company_id or not customer_id:
        return False
    if drv_company_id == customer_id:
        return True  # ad-hoc own-company tours
    drv_co = await _raw_db.companies.find_one(
        {"id": drv_company_id},
        {"_id": 0, "serves_company_ids": 1},
    )
    if not drv_co:
        return False
    return customer_id in (drv_co.get("serves_company_ids") or [])


async def _driver_active_customer_id(payload: dict) -> Optional[str]:
    """Read the driver's currently active customer-id from their user doc."""
    if not payload or payload.get("role") != "driver":
        return None
    u = await _raw_db.users.find_one(
        {"id": payload.get("sub")},
        {"_id": 0, "active_customer_id": 1},
    )
    return (u or {}).get("active_customer_id") or None


# 2026-10-16: To slags logistikfirmaer (se LOGISTICS_TIERS.md).
#   premium = oprettet som kunde med kundetype "logistik" (Kunder & Logistik)
#             - bruger systemet selvstændigt: egne lokationer, egne ture.
#   partner = oprettet i logistik-partner-biblioteket (from_library) - får
#             adgang gennem de genbrugsplads-kunder der tilknytter dem.
# Genbrugsplads-funktioner vises kun når firmaet har mindst én tilknyttet
# kunde, og gælder kun for den kunde.
def _logistics_tier(company: Optional[dict]) -> str:
    if not company or company.get("company_type") != COMPANY_TYPE_LOGISTICS:
        return ""
    return "partner" if company.get("from_library") else "premium"


async def _logistics_profile(cid: str) -> dict:
    comp = await _raw_db.companies.find_one(
        {"id": cid}, {"_id": 0, "id": 1, "name": 1, "company_type": 1, "from_library": 1,
                      "serves_company_ids": 1})
    tier = _logistics_tier(comp)
    if not tier:
        return {"is_logistics": False}
    customers = await _raw_db.companies.find(
        {"id": {"$in": [c for c in (comp.get("serves_company_ids") or []) if c]},
         "company_type": COMPANY_TYPE_CUSTOMER, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1},
    ).sort("name", 1).to_list(500)
    return {
        "is_logistics": True,
        "company_id": cid,
        "company_name": comp.get("name") or "",
        "tier": tier,
        "is_premium": tier == "premium",
        "connected_customers": customers,
        "has_connections": bool(customers),
    }


@api_router.get("/logistics/profile")
async def logistics_profile(payload: dict = Depends(require_role("logistics_admin", "driver"))):
    return await _logistics_profile(payload.get("company_id") or "")


@api_router.get("/driver/customers")
async def driver_list_customers(payload: dict = Depends(get_current_user_payload)):
    """List customers this driver's logistics company serves. Premium
    logistikfirmaer har desuden deres egne ture som første valg."""
    if payload.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Kun chauffører")
    drv_company_id = payload.get("company_id")
    if not drv_company_id:
        return []
    drv_co = await _raw_db.companies.find_one(
        {"id": drv_company_id},
        {"_id": 0, "id": 1, "name": 1, "serves_company_ids": 1, "company_type": 1, "from_library": 1},
    )
    own = []
    if _logistics_tier(drv_co) == "premium":
        own = [{"id": drv_company_id, "name": f"Egne ture · {drv_co.get('name', '')}",
                "customer_id": "", "city": "", "own": True}]
    customer_ids = list((drv_co or {}).get("serves_company_ids") or [])
    if not customer_ids:
        return own
    customers = await _raw_db.companies.find(
        {"id": {"$in": customer_ids}, "active": True},
        {"_id": 0, "id": 1, "name": 1, "customer_id": 1, "city": 1},
    ).to_list(100)
    # Sort alphabetically by name
    customers.sort(key=lambda c: (c.get("name") or "").lower())
    return own + customers


@api_router.get("/driver/active-customer")
async def driver_get_active_customer(payload: dict = Depends(get_current_user_payload)):
    """Return currently active customer (or null if none picked yet)."""
    if payload.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Kun chauffører")
    cid = await _driver_active_customer_id(payload)
    if not cid:
        return {"customer_id": None, "customer": None}
    # Re-validate (in case it was revoked)
    if not await _driver_serves_customer(payload, cid):
        # Stale state — clear and surface as none
        await _raw_db.users.update_one(
            {"id": payload.get("sub")},
            {"$unset": {"active_customer_id": ""}},
        )
        return {"customer_id": None, "customer": None}
    c = await _raw_db.companies.find_one(
        {"id": cid, "active": True},
        {"_id": 0, "id": 1, "name": 1, "customer_id": 1, "city": 1},
    )
    if c and cid == payload.get("company_id"):
        c = {**c, "name": f"Egne ture · {c.get('name', '')}", "own": True}
    return {"customer_id": cid, "customer": c}


@api_router.post("/driver/active-customer")
async def driver_set_active_customer(
    body: dict,
    payload: dict = Depends(get_current_user_payload),
):
    """Set the driver's active customer for the session. Server re-validates
    that the driver's logistics company actually serves this customer."""
    if payload.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Kun chauffører")
    customer_id = (body or {}).get("customer_id")
    if not customer_id:
        # Clearing the active customer (e.g. driver logs off duty)
        await _raw_db.users.update_one(
            {"id": payload.get("sub")},
            {"$unset": {"active_customer_id": ""}},
        )
        return {"customer_id": None}
    if not await _driver_serves_customer(payload, customer_id):
        raise HTTPException(status_code=403, detail="Dit logistik-firma servicerer ikke denne kunde")
    await _raw_db.users.update_one(
        {"id": payload.get("sub")},
        {"$set": {"active_customer_id": customer_id}},
    )
    return {"customer_id": customer_id}
# ============= end FASE 5 driver active-customer ============================



# ===== Tour Template — Excel download/upload (Fase 4.1) ====================
# Replaces the manual "Tilføj ture" / "Argo" / "Upload PDF" buttons with a
# single standardized SuccessFactors-style template. The downloaded .xlsx has
# data-validation dropdowns for the Lokation column so LA cannot mistype.
# Upload parses each row, derives customer from the chosen plads, and creates
# tours with source="manual".

TOUR_TEMPLATE_HEADERS = [
    "Lokation",        # Dropdown — drives company_id + customer_name
    "Materiale",       # → fraction
    "Container-nummer",  # → container
    "Containertype",   # → container_type (e.g. "Lav åben 20 m³")
    "Leveringsadresse",  # → address
    "Åbningstid",      # → open_from (e.g. "09:00")
    "Lukketid",        # → open_to (e.g. "16:00")
    "Note",            # → remark
]
TOUR_TEMPLATE_TEMPLATE_ROWS = 50  # how many rows the dropdown pre-populates


def _format_plads_label(p: dict) -> str:
    """Stable identifier shown in the Excel dropdown: '{code} — {name}, {city}'."""
    code = (p.get("location_code") or "").strip()
    name = (p.get("name") or "").strip()
    city = (p.get("city") or "").strip()
    parts = []
    if code:
        parts.append(code)
    if name:
        parts.append(name)
    label = " — ".join(parts) if parts else "?"
    if city:
        label += f", {city}"
    return label


async def _resolve_la_pladser_for_template(payload: dict) -> list:
    """Return the pladser the LA may use as Lokation in the template.
    Same union as GET /api/plads for logistics_admin (own + served customers).
    """
    la_company = payload.get("company_id") or ""
    if not la_company or la_company == SUPER_ADMIN_BYPASS:
        return []
    q = {
        "active": True,
        "$or": [
            {"company_id": la_company},
            {"assigned_logistics_company_ids": la_company},
        ],
    }
    return await _raw_db.plads.find(q, {"_id": 0}).to_list(500)


@api_router.get("/tours/template")
async def download_tours_template(payload: dict = Depends(get_current_user_payload)):
    """Generate an .xlsx template with pre-populated Lokation dropdown."""
    if payload.get("role") not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    from fastapi.responses import StreamingResponse
    from io import BytesIO

    pladser = await _resolve_la_pladser_for_template(payload)
    labels = sorted({_format_plads_label(p) for p in pladser if p.get("location_code")})

    wb = Workbook()
    ws = wb.active
    ws.title = "Manuelle ture"

    # Header row
    header_fill = PatternFill("solid", fgColor="FFEA580C")  # orange
    header_font = Font(bold=True, color="FFFFFFFF", size=11)
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx, header in enumerate(TOUR_TEMPLATE_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center

    # Column widths (rough but readable)
    widths = [40, 16, 18, 22, 36, 12, 12, 36]
    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w

    # Freeze header row + bold border feel
    ws.freeze_panes = "A2"

    # Helper "Lokationer" sheet (hidden) that holds the dropdown source
    helper = wb.create_sheet("Lokationer")
    helper.sheet_state = "hidden"
    for i, label in enumerate(labels, start=1):
        helper.cell(row=i, column=1, value=label)

    if labels:
        last_row = len(labels)
        dv_formula = f"=Lokationer!$A$1:$A${last_row}"
        dv = DataValidation(type="list", formula1=dv_formula, allow_blank=True)
        dv.error = "Vælg en plads fra dropdown-listen"
        dv.errorTitle = "Ugyldig lokation"
        dv.prompt = "Vælg lokationen fra dropdown — kundenavn beregnes automatisk"
        dv.promptTitle = "Lokation"
        dv.showErrorMessage = True
        dv.showInputMessage = True
        # Apply to column A (Lokation), rows 2..N
        dv.add(f"A2:A{TOUR_TEMPLATE_TEMPLATE_ROWS + 1}")
        ws.add_data_validation(dv)

    # Instruction row
    instr_row = TOUR_TEMPLATE_TEMPLATE_ROWS + 3
    ws.cell(row=instr_row, column=1, value="ℹ️ Sådan udfylder du skabelonen").font = Font(bold=True)
    ws.cell(row=instr_row + 1, column=1, value="• Lokation: klik pilen og vælg fra dropdown. Kundenavn sættes automatisk.")
    ws.cell(row=instr_row + 2, column=1, value="• Materiale: f.eks. Pap, Glas, Plast.")
    ws.cell(row=instr_row + 3, column=1, value="• Container-nummer: tal eller intern ID (f.eks. 2223).")
    ws.cell(row=instr_row + 4, column=1, value="• Containertype: f.eks. 'Lav åben 20 m³'.")
    ws.cell(row=instr_row + 5, column=1, value="• Åbningstid/Lukketid: format HH:MM (f.eks. 09:00, 16:00).")
    ws.cell(row=instr_row + 6, column=1, value="• Note: valgfri kommentar til chaufføren.")

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"ture-skabelon-{datetime.now(DK_TZ).strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.post("/tours/upload-template")
async def upload_tours_template(
    file: UploadFile = File(...),
    payload: dict = Depends(get_current_user_payload),
):
    """Parse an LA-filled .xlsx and create manual tours.

    Each row must reference a Lokation that the LA is allowed to use (server
    re-validates against the same union as GET /api/plads). The customer
    (company_id + customer_name) is derived from the chosen plads.
    """
    if payload.get("role") not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")

    from openpyxl import load_workbook
    from io import BytesIO

    contents = await file.read()
    try:
        wb = load_workbook(BytesIO(contents), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Filen kunne ikke åbnes: {e}")
    ws = wb.active

    # Build allowed plads lookup keyed by the same label format we used in the
    # downloaded template — but also accept loose matches on location_code or
    # name so LA can paste data from older systems too.
    pladser = await _resolve_la_pladser_for_template(payload)
    by_label = {_format_plads_label(p): p for p in pladser}
    by_code = {(p.get("location_code") or "").strip(): p for p in pladser if p.get("location_code")}
    by_name = {(p.get("name") or "").strip().lower(): p for p in pladser if p.get("name")}

    def resolve_plads(value: str):
        v = (value or "").strip()
        if not v:
            return None
        if v in by_label:
            return by_label[v]
        # Strip dashes/spaces and try code prefix
        code_guess = v.split("—")[0].strip() if "—" in v else v.split()[0]
        code_guess = code_guess.strip()
        if code_guess in by_code:
            return by_code[code_guess]
        if v.lower() in by_name:
            return by_name[v.lower()]
        return None

    # Cache company names for customer_name on tour docs
    cust_ids = {p.get("company_id") for p in pladser if p.get("company_id")}
    cust_map = {}
    if cust_ids:
        async for c in _raw_db.companies.find(
            {"id": {"$in": list(cust_ids)}}, {"_id": 0, "id": 1, "name": 1, "customer_id": 1},
        ):
            cust_map[c["id"]] = {"name": c.get("name", ""), "customer_id": c.get("customer_id") or ""}

    # Iterate rows. Header on row 1.
    created = 0
    errors = []
    today = get_dk_date_str()
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(cell in (None, "") for cell in row):
            continue  # blank line — skip
        # Defensive: pad to 8 columns
        cells = list(row[:8]) + [""] * (8 - len(row[:8]))
        loc_val, material, container_num, container_type, address, open_from, open_to, note = cells

        # Trim everything to strings
        def _s(x):
            return "" if x is None else (str(x).strip() if not isinstance(x, str) else x.strip())
        loc_val = _s(loc_val)
        material = _s(material)
        container_num = _s(container_num)
        container_type = _s(container_type)
        address = _s(address)
        open_from = _s(open_from)
        open_to = _s(open_to)
        note = _s(note)

        if not loc_val:
            errors.append({"row": row_idx, "reason": "Lokation mangler"})
            continue
        if not material:
            errors.append({"row": row_idx, "reason": "Materiale mangler"})
            continue

        p = resolve_plads(loc_val)
        if not p:
            errors.append({
                "row": row_idx,
                "reason": f"Ukendt lokation: '{loc_val}'. Vælg fra dropdown'en.",
            })
            continue

        plads_company_id = p.get("company_id") or ""
        cust_info = cust_map.get(plads_company_id, {})
        plads_full_name = p.get("name") or ""
        loc_code = p.get("location_code") or ""

        tour_doc = {
            "id": str(uuid.uuid4()),
            "date": today,
            "container": container_num,
            "container_type": container_type,
            "fraction": material,
            "facility": plads_full_name,
            "address": address,
            "plads": plads_full_name,
            "open_from": open_from,
            "open_to": open_to,
            "remark": note,
            "priority": "normal",
            "tour_type": "normal",
            "company_id": plads_company_id,
            "assigned_logistics_company_ids": list(p.get("assigned_logistics_company_ids") or []),
            "source": "manual",
            "customer_name": cust_info.get("name", ""),
            "customer_code": cust_info.get("customer_id", ""),
            "claimed_by": "", "claimed_by_id": "", "claimed_at": "",
            "driver_id": "", "driver_name": "",
            "report_id": "", "sort_order": 0,
            "completed": False, "on_way": False, "is_pause": False,
            "is_same_day": False, "is_private": False, "private_company": "",
            "weight": None, "time": "",
            "lat": p.get("lat"), "lng": p.get("lng"),
            "route_distance_km": None, "route_order": None,
            "transport_mode": "", "on_way_time": "",
            "receipt_image": "", "order_id": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await _raw_db.tours.insert_one(tour_doc)
        # Track which plads-code this row maps to for the UI summary
        tour_doc["_plads_code"] = loc_code
        created += 1

    return {
        "created": created,
        "errors": errors,
        "message": (
            f"{created} tur(e) oprettet" if not errors
            else f"{created} tur(e) oprettet · {len(errors)} fejl"
        ),
    }
# ===== end Tour Template ===================================================


@api_router.put("/tours/{tour_id}", response_model=Tour)
async def update_tour(tour_id: str, update: TourUpdate, payload: dict = Depends(get_current_user_payload)):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
    if "date" in update_data:
        update_data["date"] = normalize_date(update_data["date"])
    if "stops" in update_data:
        _prev_stops = (await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "stops": 1}) or {}).get("stops") or []
        update_data["stops"] = _clean_stops(update_data["stops"], _prev_stops)
        if len(update_data["stops"]) <= 1:
            update_data["stops"] = []
        _apply_stops(update_data)
    if "cargo_lines" in update_data:
        update_data["cargo_lines"] = _clean_cargo_lines(update_data["cargo_lines"], int(update_data.get("trailer_count") or 9))
        if update_data["cargo_lines"] and "fraction" not in update_data:
            update_data["fraction"] = " + ".join(dict.fromkeys(l["text"] for l in update_data["cargo_lines"]))
    if "trailer_count" in update_data:
        update_data["trailer_count"] = max(0, min(int(update_data["trailer_count"] or 0), 9))
    if payload.get("role") == "logistics_admin":
        if not await _require_tour_scope(payload, [tour_id]):
            raise HTTPException(status_code=403, detail="Turen hører til en kunde du ikke har adgang til")
        if {"driver_id", "driver_name"} & set(update_data):
            await _require_perm(payload, "tours_assign")
        if set(update_data) - {"driver_id", "driver_name"}:
            await _require_perm(payload, "tours_edit")

    role = payload.get("role")
    caller_id = payload.get("sub") or payload.get("user_id") or ""

    # Load existing tour (raw — we'll enforce tenant policy manually below
    # so LA/driver can update tours from partnered customer companies).
    existing_tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0})
    if not existing_tour:
        raise HTTPException(status_code=404, detail="Tour not found")

    # Tenant guard: LA/driver may only touch their own company tours OR tours
    # from customer companies that have partnered with their logistics_admin
    # company. super_admin bypasses.
    if role in ("logistics_admin", "driver"):
        la_company = payload.get("company_id") or ""
        tour_cid = existing_tour.get("company_id", "")
        partners = existing_tour.get("assigned_logistics_company_ids") or []
        if not (tour_cid == la_company or la_company in partners):
            raise HTTPException(status_code=403, detail="Tur tilhører anden virksomhed")

    # Fase 6: Pre-assignment guard.
    # Drivers may NEVER set driver_id (only LA can pre-assign). If they try,
    # we strip it silently so the rest of the update still goes through.
    # Drivers may ONLY claim a tour for themselves (claimed_by_id == self).
    if role == "driver":
        # Strip pre-assignment attempts from drivers
        update_data.pop("driver_id", None)
        update_data.pop("driver_name", None)
        for _k in ("date", "fraction", "address", "facility", "plads", "capacity_label",
                   "address_parts", "facility_parts", "trailer_count", "cargo_lines", "loose_estimated_count", "stops"):
            update_data.pop(_k, None)
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")
        # Validate claim attempts
        if "claimed_by_id" in update_data and update_data["claimed_by_id"]:
            if update_data["claimed_by_id"] != caller_id:
                raise HTTPException(status_code=403, detail="Chauffører kan kun tage ture til sig selv")
        # If tour is pre-assigned to a DIFFERENT driver, block any update
        pre_assigned = (existing_tour.get("driver_id") or "").strip()
        if pre_assigned and pre_assigned != caller_id:
            raise HTTPException(status_code=403, detail="Denne tur er tildelt en anden chauffør")

        # Fase 15 (2026-06-19): Hvis turen er ADMIN-tildelt (assigned_by_id
        # er sat), må chaufføren ikke frigøre sig selv via "Fortryd". De
        # kan stadig opdatere weight/on_way/completed, men ikke clear-claim.
        # Fase 15.11 (2026-02-XX): Tilladt nu — chaufføren skal kunne
        # "Fortryd" en igangværende kørsel og gå tilbage til VENTER, så længe
        # de IKKE forsøger at fjerne selve tildelingen (driver_id).
        admin_assigned_id = (existing_tour.get("assigned_by_id") or "").strip()
        existing_driver_id = (existing_tour.get("driver_id") or "").strip()
        wants_unassign_self = (
            "driver_id" in update_data
            and (update_data.get("driver_id") or "") == ""
            and existing_driver_id == caller_id
        )
        if admin_assigned_id and wants_unassign_self:
            raise HTTPException(
                status_code=403,
                detail="Denne tur er tildelt af administrator — kontakt din logistikadmin for at frigøre.",
            )

        # Fase 10 (2026-06-17): Simultaneous-tour limit via trailer-capacity.
        # When a driver claims a NEW tour, count their active claims:
        #   active = claimed_by_id == self AND on_way == true AND completed == false
        # Max samtidige ture = (selected trailer's container_capacity) + 1.
        # If driver has NO trailer selected → max 1 active tour.
        #
        # Fase 14 (2026-06-19): "AKTIV" betyder STRENGT kun "På vej"-ture.
        # Tidligere talte vi alle ikke-afsluttede claims med, hvilket både
        # låste chaufføren ude pga. afsluttede ture (hvis on_way ikke var
        # nulstillet) OG pga. claimede-men-ikke-startede ture. Brugerens
        # regel: kapacitet skal kun matche fysisk samtidige kørsler =
        # on_way:true && completed:false.
        is_new_claim = (
            "claimed_by_id" in update_data
            and update_data["claimed_by_id"] == caller_id
            and not (existing_tour.get("claimed_by_id") or "")
        )
        # Fase 14 (2026-06-19): Kapacitets-tjekket skal kun udløses når
        # chaufføren faktisk PÅBEGYNDER en tur (on_way=true), ikke ved
        # ren claim uden start. Hvis on_way ikke sættes til True i denne
        # update, så er der ikke noget aktivt-load der øges → skip check.
        is_starting_tour = bool(update_data.get("on_way")) and not existing_tour.get("on_way")
        if is_new_claim and is_starting_tour:
            # Find driver's selected trailer (active_trailer_id on user doc)
            user_doc = await _raw_db.users.find_one(
                {"id": caller_id}, {"_id": 0, "active_trailer_id": 1}
            )
            trailer_id = (user_doc or {}).get("active_trailer_id") or ""
            if trailer_id:
                tr = await _raw_db.trailers.find_one(
                    {"id": trailer_id}, {"_id": 0, "container_capacity": 1}
                )
                capacity = int((tr or {}).get("container_capacity") or 1)
            else:
                capacity = 0  # No trailer → only 1 tour at a time
            max_simultaneous = capacity + 1
            # Tæl KUN igangværende kørsler: on_way=true && completed!=true.
            current_active = await _raw_db.tours.count_documents({
                "claimed_by_id": caller_id,
                "on_way": True,
                "$or": [{"completed": False}, {"completed": {"$exists": False}}],
            })
            # Exclude the tour we're about to claim (just in case)
            if existing_tour.get("id") == tour_id and existing_tour.get("claimed_by_id") == caller_id:
                pass  # not a new claim
            if current_active >= max_simultaneous:
                if not trailer_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Du har allerede 1 aktiv tur. Vælg en hænger for at tage flere samtidige ture."
                    )
                raise HTTPException(
                    status_code=409,
                    detail=f"Max {max_simultaneous} samtidige ture med din hænger ({capacity} containere). Afslut en aktiv tur først."
                )

    # Check claim validation
    existing_claimed = existing_tour.get("claimed_by", "")
    incoming_claimed = update_data.get("claimed_by", None)

    if existing_claimed:
        # Tour is claimed by someone
        if incoming_claimed and incoming_claimed != existing_claimed:
            # Different driver trying to claim - block
            raise HTTPException(status_code=409, detail=f"Tur er allerede taget af {existing_claimed}")

        if incoming_claimed is None:
            # No claimed_by in request - check if restricted fields are being modified
            restricted_fields = {"on_way", "completed", "weight"}
            if restricted_fields.intersection(update_data.keys()):
                raise HTTPException(status_code=409, detail=f"Tur er allerede taget af {existing_claimed}")

    # Stamp the claim time when a tour is taken for the first time
    # (transition from unclaimed -> claimed). Gives a full audit trail:
    # claimed_at (taken) -> on_way_time (started) -> time/completed_at (done).
    incoming_claimed = update_data.get("claimed_by")
    if incoming_claimed and not (existing_tour or {}).get("claimed_by"):
        update_data.setdefault("claimed_at", datetime.now(DK_TZ).isoformat())

    # Handle explicit unclaim (claimed_by set to "")
    if update.claimed_by is not None and update.claimed_by == "":
        update_data["claimed_by"] = ""
        update_data["claimed_by_id"] = ""
        update_data["claimed_at"] = ""
        # Fase 15.3 (2026-06-19): Ryd også on_way+on_way_time så vi ikke
        # efterlader en orphan-tur der ser "PÅ VEJ" ud for andre chauffører.
        update_data["on_way"] = False
        update_data["on_way_time"] = ""
        # Fase 15 (2026-06-19): Når admin frigør en tildelt tur, fjern også
        # assigned_by_*-sporet så turen igen kan claimes frit af chauffører.
        # Fase 15.11 (2026-02-XX): MEN — hvis det er chaufføren SELV der
        # "Fortryd" (caller == existing.driver_id), så bevarer vi tildelingen
        # så turen stadig står som "tildelt dig" men i VENTER-status.
        existing_driver_id = (existing_tour.get("driver_id") or "").strip()
        is_driver_self_revert = bool(existing_driver_id) and existing_driver_id == caller_id
        if not is_driver_self_revert:
            update_data["assigned_by_id"] = ""
            update_data["assigned_by_name"] = ""
            update_data["assigned_at"] = ""

    # Fase 15 (2026-06-19): Når admin frigør via Planning UI (driver_id="")
    # skal vi også rydde assigned_by_*-sporet. Dette er den primære "frigør
    # tildeling"-sti fra logistik-admin-overblikket. Uden dette branch
    # forblev "Tildelt af X" på turen efter den var blevet frigivet.
    if update.driver_id is not None and update.driver_id == "":
        update_data["driver_id"] = ""
        update_data["driver_name"] = ""
        update_data["assigned_by_id"] = ""
        update_data["assigned_by_name"] = ""
        update_data["assigned_at"] = ""
        # Fase 15.3 (2026-06-19): Hvis turen var "på vej" af den fjernede
        # chauffør, så ryd også claim + on_way-flag — ellers ser andre
        # chauffører en orphan PÅ VEJ-tur uden ejer.
        existing_claimed_id = (existing_tour.get("claimed_by_id") or "").strip()
        existing_driver_id  = (existing_tour.get("driver_id") or "").strip()
        # Hvis den eksisterende claim hører til den driver vi nu fjerner
        # → ryd alt claim-state.
        if existing_claimed_id and existing_claimed_id == existing_driver_id:
            update_data["claimed_by"] = ""
            update_data["claimed_by_id"] = ""
            update_data["claimed_at"] = ""
        update_data["on_way"] = False
        update_data["on_way_time"] = ""

    # Fase 15 (2026-06-19): Spor admin-tildelinger.
    # Når en LA/SA enten pre-assigner (sætter driver_id) eller claimer på
    # vegne (sætter claimed_by_id til en anden bruger end sig selv), så
    # registrer hvem der tildelte hvornår — chauffør-siden viser "Tildelt af
    # {navn}" og blokerer 'Fortryd' på admin-tildelte ture.
    if role in ("logistics_admin", "super_admin"):
        sets_driver_id = bool((update_data.get("driver_id") or "").strip())
        sets_claim_other = bool(
            update_data.get("claimed_by_id")
            and update_data.get("claimed_by_id") != caller_id
        )
        if sets_driver_id or sets_claim_other:
            assigner_name = (
                payload.get("name")
                or payload.get("display_name")
                or ""
            )
            # Fase 15.8 (2026-02-XX): Fald aldrig tilbage til email — slå
            # display-navn op i DB hvis JWT ikke har det.
            if not assigner_name and caller_id:
                admin_doc = await _raw_db.users.find_one(
                    {"id": caller_id}, {"_id": 0, "display_name": 1, "name": 1, "email": 1}
                )
                if admin_doc:
                    assigner_name = (
                        (admin_doc.get("display_name") or "").strip()
                        or (admin_doc.get("name") or "").strip()
                        or (admin_doc.get("email") or "").strip()
                    )
            if not assigner_name:
                assigner_name = payload.get("email") or ""
            update_data["assigned_by_id"] = caller_id
            update_data["assigned_by_name"] = assigner_name
            update_data["assigned_at"] = datetime.now(DK_TZ).isoformat()

    # Fase 6: Detect pre-assignment change for audit log (only logistics_admin
    # can reach this branch since drivers had driver_id stripped above).
    old_driver_id = (existing_tour.get("driver_id") or "").strip()
    new_driver_id = update_data.get("driver_id")
    assignment_changed = new_driver_id is not None and (new_driver_id or "").strip() != old_driver_id

    # Fase 11 (2026-06-18): Vægt + CO2 må KUN gemmes for opgavetype 'normal'.
    # Hvis chaufføren prøver at sætte weight på andre opgavetyper, ignoreres
    # det og resetes til 0 så DB matcher den nye regel.
    # Fase 15.41 (2026-02-22): Undtagelse — `loes_afhentning` har vægt-data
    # via `container_weights`-liste. Vi auto-beregner `weight` som SUM(list)
    # så de to felter ALDRIG kommer ud af sync. CO2 forbliver 0 (kunden
    # ejer ikke containerne, så vægten er ikke CO2-faktorerbar).
    eff_tour_type = update_data.get("tour_type", existing_tour.get("tour_type") or "normal")
    # 2026-10-17: Flere indholdslinjer (fx hænger 1: Beton, hænger 2: Træ)
    # vejes pr. læs ligesom løs afhentning. Gods-ture har valgfri vægt.
    _cargo_n = len(update_data.get("cargo_lines", existing_tour.get("cargo_lines") or []) or [])
    _goods = (existing_tour.get("tour_kind") or "container") == "goods"
    if _cargo_n > 1 and eff_tour_type != "loes_afhentning":
        incoming_weights = update_data.get("container_weights")
        if incoming_weights is not None:
            cleaned = [float(w) for w in incoming_weights if w is not None and float(w) >= 0]
            update_data["container_weights"] = cleaned
            update_data["weight"] = sum(cleaned)
        if update_data.get("completed") is True and not _goods:
            future_weights = (update_data.get("container_weights") if "container_weights" in update_data
                              else (existing_tour.get("container_weights") or []))
            if not [w for w in (future_weights or []) if float(w) > 0] and not (update_data.get("weight") or 0):
                raise HTTPException(status_code=400, detail="Indtast mindst én vægt før turen afsluttes")
    elif _goods:
        update_data.pop("container_weights", None)
        update_data["co2_kg"] = 0.0
    elif eff_tour_type == "loes_afhentning":
        incoming_weights = update_data.get("container_weights")
        if incoming_weights is not None:
            # Normaliser: floats >= 0, drop None
            cleaned = [float(w) for w in incoming_weights if w is not None and float(w) >= 0]
            update_data["container_weights"] = cleaned
            update_data["weight"] = sum(cleaned)
        # Hvis chaufføren prøver at afslutte uden mindst 1 vægt > 0 → 400.
        if update_data.get("completed") is True:
            future_weights = (
                update_data.get("container_weights")
                if "container_weights" in update_data
                else (existing_tour.get("container_weights") or [])
            )
            positive = [w for w in (future_weights or []) if float(w) > 0]
            if not positive:
                raise HTTPException(
                    status_code=400,
                    detail="Mindst én container-vægt > 0 skal registreres før Løs afhentning kan afsluttes",
                )
        update_data["co2_kg"] = 0.0
    elif eff_tour_type != "normal":
        if "weight" in update_data:
            update_data["weight"] = 0
        if "container_weights" in update_data:
            # Andre opgavetyper må ikke have container_weights overhovedet.
            update_data.pop("container_weights", None)
        update_data["co2_kg"] = 0.0
    else:
        # `normal` opgavetype må ikke have container_weights heller.
        update_data.pop("container_weights", None)

    # Fase 15.50 (2026-02-22): Stamp `completed_at` (lokal DK-tid) når turen
    # transitionerer fra ikke-afsluttet → afsluttet. Bruges på chauffør-UI'en
    # til at vise "Ferdal Turan har afsluttet 22/06 kl. 14:32" så chauffør og
    # admin altid kan se hvornår turen blev lukket.
    if update_data.get("completed") is True and not existing_tour.get("completed"):
        update_data.setdefault("completed_at", datetime.now(DK_TZ).isoformat())

    # 2026-10-16: "Med hænger" er et prisgrundlag pr. tur. Når turen startes
    # (på vej) foreslås værdien ud fra om chaufføren har valgt en hænger ved
    # login; chaufføren kan ændre den på turen bagefter.
    if (update_data.get("on_way") is True and not existing_tour.get("on_way")
            and existing_tour.get("used_trailer") is None):
        starter_id = update_data.get("claimed_by_id") or existing_tour.get("claimed_by_id") or ""
        if starter_id:
            _starter = await _raw_db.users.find_one({"id": starter_id}, {"_id": 0, "active_trailer_id": 1})
            # 2026-10-17: Planlagte hængere på turen betyder "med hænger".
            update_data["used_trailer"] = bool((_starter or {}).get("active_trailer_id")) or int(existing_tour.get("trailer_count") or 0) > 0
    elif update_data.get("completed") is False:
        # Reverter en afsluttet tur → ryd completed_at så stempel ikke
        # forbliver fra forrige afslutning.
        update_data["completed_at"] = ""

    result = await _raw_db.tours.update_one(
        {"id": tour_id},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tour not found")

    tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0})

    # Fase 6: Audit log on assignment change (LA pre-assigns / reassigns / releases)
    if assignment_changed:
        try:
            await _tour_audit(
                tour_id=tour_id,
                action="release" if not new_driver_id else ("reassign" if old_driver_id else "assign"),
                payload=payload,
                before={"driver_id": old_driver_id, "driver_name": existing_tour.get("driver_name", "")},
                after={"driver_id": tour.get("driver_id", ""), "driver_name": tour.get("driver_name", "")},
            )
        except Exception as e:
            logger.error(f"Tour audit failed for {tour_id}: {e}")
        if new_driver_id and payload.get("role") in ("logistics_admin", "super_admin"):
            _push_later(_push_driver(
                payload.get("company_id") or "", new_driver_id, tour.get("driver_name", ""),
                "Ny tur tildelt",
                f"{tour.get('fraction') or 'Tur'} · {tour.get('address') or tour.get('plads') or ''}".strip(" ·"),
                tag=f"tour-{tour_id}"))
    # 2026-10-17: Planlæggeren ændrer en tur en chauffør har -> besked.
    if payload.get("role") in ("logistics_admin", "super_admin") and not assignment_changed:
        _watched = {"date": "dato", "address": "adresse", "facility": "aflevering", "fraction": "indhold",
                    "open_from": "tidsrum", "open_to": "tidsrum", "remark": "note", "priority": "prioritet",
                    "cargo_lines": "indhold", "trailer_count": "hængere", "stops": "stop"}
        changed = sorted({lbl for k, lbl in _watched.items() if k in update_data and update_data[k] != existing_tour.get(k)})
        holder = (tour.get("driver_id") or tour.get("claimed_by_id") or "").strip()
        if changed and holder and not tour.get("completed"):
            _push_later(_push_driver(
                payload.get("company_id") or "", holder, tour.get("driver_name") or tour.get("claimed_by") or "",
                "Tur ændret", f"{tour.get('fraction') or 'Tur'}: ny {', '.join(changed)}", tag=f"tour-{tour_id}"))
        if "priority" in update_data and isHaster_tour(update_data) and not isHaster_tour(existing_tour):
            _push_later(_push_new_haster([dict(tour)]))

    # Mirror driver/status back to the linked customer order so the
    # "Bestil Afhentning / Mine bestillinger" view shows who took the tour,
    # when it was taken (claimed_at), started (on_way_time) and finished (time).
    order_id = tour.get("order_id")
    if order_id:
        mirror = {
            k: tour.get(k)
            for k in ("claimed_by", "claimed_by_id", "claimed_at", "on_way",
                      "on_way_time", "completed", "time", "weight", "driver_name",
                      # Fase 15.41 (2026-02-22): Spejl container_weights over
                      # på ordren så "Mine bestillinger" kan vise per-container-
                      # vægtene og total.
                      "container_weights")
            if k in tour
        }
        if tour.get("completed"):
            mirror["status"] = "completed"
            mirror["completed_at"] = tour.get("completed_at") or datetime.now(DK_TZ).isoformat()
        elif tour.get("on_way") or tour.get("claimed_by"):
            mirror["status"] = "in_progress"
        else:
            mirror["status"] = "pending"

        # Fase 9 (2026-06-17): When chaufføren leverer vægten (kg), mirror den
        # over på ordren som `weight_kg` og genberegn `co2_kg` baseret på det
        # snapshottede faktor på ordren.
        # Fase 11 (2026-06-18): Kun for tour_type='normal' (afhent container).
        # Andre opgavetyper må ikke have vægt/CO2.
        # Fase 15.41 (2026-02-22): `loes_afhentning` har OGSÅ vægt (sum af
        # container_weights).
        # Fase 15.44 (2026-02-22): CO2 BEREGNES NU også for løs afhentning —
        # selvom kunden ikke ejer containerne er materialet stadig deres,
        # og kunden vil se CO2-besparelser i deres rapporter. Bruger samme
        # co2_factor som blev snapshottet ved bestilling (kg CO2 / ton).
        mirror_tour_type = (tour.get("tour_type") or "normal")
        if mirror_tour_type in ("normal", "loes_afhentning") and "weight" in tour and tour.get("weight") is not None:
            kg = float(tour.get("weight") or 0)
            mirror["weight_kg"] = kg
            try:
                order_doc = await _raw_db.container_orders.find_one(
                    {"id": order_id}, {"_id": 0, "co2_factor": 1}
                )
                factor = float((order_doc or {}).get("co2_factor", 0) or 0)
                mirror["co2_kg"] = round(factor * (kg / 1000.0), 3)
            except Exception:
                mirror["co2_kg"] = 0.0
        elif mirror_tour_type != "normal":
            # Tving til 0 for sikkerhed (idempotent oprydning)
            mirror["weight_kg"] = 0.0
            mirror["co2_kg"] = 0.0

        try:
            # Brug raw db for mirror-update — chaufføren tilhører LA-firmaet,
            # men ordren ejes af kunde-firmaet (tenant filter ville blokere).
            await _raw_db.container_orders.update_one({"id": order_id}, {"$set": mirror})
        except Exception as e:
            logger.error(f"Order mirror failed for {order_id}: {e}")

    return Tour(**tour)

@api_router.get("/tours/{tour_id}/audit-log")
async def get_tour_audit_log(tour_id: str, payload: dict = Depends(get_current_user_payload)):
    """Fase 6: Audit log for a tour's pre-assignment changes (LA/SA only)."""
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må se audit-log")
    # Tenant guard: LA can only see audit-log for tours in their company scope
    if role == "logistics_admin":
        la_company = payload.get("company_id") or ""
        tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "company_id": 1, "assigned_logistics_company_ids": 1})
        if not tour:
            raise HTTPException(status_code=404, detail="Tour not found")
        owns = tour.get("company_id") == la_company
        partners = la_company in (tour.get("assigned_logistics_company_ids") or [])
        if not (owns or partners):
            raise HTTPException(status_code=403, detail="Tur tilhører anden virksomhed")
    entries = await _raw_db.tour_audit_log.find(
        {"tour_id": tour_id}, {"_id": 0}
    ).sort("at", -1).to_list(200)
    return entries

@api_router.delete("/tours/{tour_id}")
async def delete_tour(tour_id: str, _auth: dict = Depends(get_current_user_payload)):
    # 2026-10-16: Kræver login (før kunne alle slette en tur med et id).
    if _auth.get("role") == "logistics_admin" and not await _require_tour_scope(_auth, [tour_id]):
        raise HTTPException(status_code=403, detail="Turen hører til en kunde du ikke har adgang til")
    before = await db.tours.find_one({"id": tour_id}, {"_id": 0, "driver_id": 1, "claimed_by_id": 1, "driver_name": 1,
                                                       "claimed_by": 1, "fraction": 1, "address": 1, "completed": 1, "date": 1})
    result = await db.tours.delete_one({"id": tour_id})
    holder = ((before or {}).get("driver_id") or (before or {}).get("claimed_by_id") or "").strip()
    if result.deleted_count and holder and not before.get("completed") and _auth.get("role") in ("logistics_admin", "super_admin"):
        _push_later(_push_driver(_auth.get("company_id") or "", holder, before.get("driver_name") or before.get("claimed_by") or "",
                                 "Tur aflyst", f"{before.get('fraction') or 'Tur'} · {before.get('address') or ''} er fjernet af planlæggeren"))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tour not found")
    return {"message": "Tour deleted"}


@api_router.post("/tours/{tour_id}/not-completed")
async def mark_tour_not_completed(
    tour_id: str,
    body: dict,
    payload: dict = Depends(get_current_user_payload),
):
    """Fase 15.52 (2026-02-22): Chauffør markerer en tur som ikke-gennemførbar.

    Regler:
    - Kaldes KUN af chauffør (eller super_admin for override).
    - Turen skal være on_way OG ikke-afsluttet OG ikke i forvejen not_completed.
    - Body skal indeholde `comment` (obligatorisk, ikke-tom).
    - Sætter `not_completed=True`, `not_completed_at`, `not_completed_comment`,
      `not_completed_by_name` på touren. Bevarer claim/on_way-felter som
      historik (admin ser hvem chaufføren var).
    - Spejler til container_order: `status="not_completed"`.
    """
    role = payload.get("role")
    if role not in ("driver", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun chauffør må markere tur som ikke-gennemført")
    comment = (body.get("comment") or "").strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Kommentar er påkrævet — beskriv hvorfor turen ikke kunne gennemføres")
    tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0})
    if not tour:
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    if tour.get("completed"):
        raise HTTPException(status_code=409, detail="Turen er allerede afsluttet")
    if tour.get("not_completed"):
        raise HTTPException(status_code=409, detail="Turen er allerede markeret som ikke-gennemført")
    if not tour.get("on_way"):
        raise HTTPException(status_code=409, detail="Chaufføren skal være 'På vej' før turen kan markeres ikke-gennemført")
    now_iso = datetime.now(DK_TZ).isoformat()
    by_name = (payload.get("name") or payload.get("email") or "").strip()
    await _raw_db.tours.update_one(
        {"id": tour_id},
        {"$set": {
            "not_completed": True,
            "not_completed_at": now_iso,
            "not_completed_comment": comment,
            "not_completed_by_name": by_name,
            # Ryd on_way så turen visuelt forsvinder fra chauffør-listen
            "on_way": False,
        }},
    )
    # Mirror til ordren (hvis findes)
    await _raw_db.container_orders.update_one(
        {"tour_id": tour_id},
        {"$set": {
            "status": "not_completed",
            "not_completed_at": now_iso,
            "not_completed_comment": comment,
            "not_completed_by_name": by_name,
        }},
    )
    return {"success": True, "not_completed_at": now_iso}


class StopDoneIn(BaseModel):
    done: bool = True


@api_router.post("/tours/{tour_id}/stops/{stop_id}/done")
async def tour_stop_done(tour_id: str, stop_id: str, body: StopDoneIn,
                         payload: dict = Depends(get_current_user_payload)):
    """2026-10-17: Chaufføren krydser et stop af (eller fjerner krydset).
    Kun chaufføren der har turen, eller firmaets planlægger."""
    t = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    role, cid, uid = payload.get("role"), payload.get("company_id") or "", payload.get("sub") or ""
    if role not in ("driver", "logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    if role != "super_admin" and t.get("company_id") != cid and cid not in (t.get("assigned_logistics_company_ids") or []):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    if role == "driver" and uid not in ((t.get("driver_id") or ""), (t.get("claimed_by_id") or "")):
        raise HTTPException(status_code=403, detail="Tag turen først")
    if role == "logistics_admin" and not await _require_tour_scope(payload, [tour_id]):
        raise HTTPException(status_code=403, detail="Turen hører til en kunde du ikke har adgang til")
    stops = list(t.get("stops") or [])
    if not any(s.get("id") == stop_id for s in stops):
        raise HTTPException(status_code=404, detail="Stop ikke fundet")
    me = await _raw_db.users.find_one({"id": uid}, {"_id": 0, "name": 1}) or {}
    now = datetime.now(DK_TZ).strftime("%H:%M")
    for s in stops:
        if s.get("id") == stop_id:
            s["done_at"] = now if body.done else ""
            s["done_by"] = (me.get("name") or "") if body.done else ""
    await _raw_db.tours.update_one({"id": tour_id}, {"$set": {"stops": stops}})
    return {"stops": stops}


@api_router.post("/tours/{tour_id}/reactivate")
async def reactivate_tour(
    tour_id: str,
    body: dict,
    payload: dict = Depends(get_current_user_payload),
):
    """Fase 15.52 (2026-02-22): Logistik-admin gen-aktiverer en ikke-gennemført tur.

    Regler:
    - Kun super_admin og logistics_admin må gen-aktivere.
    - Turen skal være `not_completed=True`.
    - Frigør claim (claimed_by="", driver_id=""), sætter on_way=False,
      completed=False — chaufføren ser turen igen som "Afventer".
    - Bevarer not_completed_comment som HISTORIK — fjernes IKKE.
    - Admin kan valgfrit angive en `comment` der gemmes som `reactivate_comment`.
    - Spejler til container_order: status="pending".
    """
    role = payload.get("role")
    if role not in ("super_admin", "logistics_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må gen-aktivere ture")
    tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0})
    if not tour:
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    if not tour.get("not_completed"):
        raise HTTPException(status_code=409, detail="Turen er ikke markeret som ikke-gennemført")
    now_iso = datetime.now(DK_TZ).isoformat()
    by_name = (payload.get("name") or payload.get("email") or "").strip()
    admin_comment = (body.get("comment") or "").strip()
    set_fields = {
        "not_completed": False,
        "reactivated_at": now_iso,
        "reactivated_by_name": by_name,
        "reactivate_comment": admin_comment,
        # Frigør så enhver chauffør kan tage turen igen
        "claimed_by": "",
        "claimed_by_id": "",
        "claimed_at": "",
        "driver_id": "",
        "driver_name": "",
        "on_way": False,
        "on_way_time": "",
        # Bevarer not_completed_comment som historik
    }
    await _raw_db.tours.update_one({"id": tour_id}, {"$set": set_fields})
    # Mirror til ordren
    order_set = {
        "status": "pending",
        "reactivated_at": now_iso,
        "reactivated_by_name": by_name,
        "reactivate_comment": admin_comment,
    }
    await _raw_db.container_orders.update_one({"tour_id": tour_id}, {"$set": order_set})
    return {"success": True, "reactivated_at": now_iso}


@api_router.get("/tours/{tour_id}/image")
async def get_tour_image(tour_id: str):
    """Get a tour's receipt image (admin only)."""
    tour = await db.tours.find_one({"id": tour_id}, {"_id": 0, "receipt_image": 1, "id": 1, "plads": 1, "fraction": 1})
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    return {"image_data": tour.get("receipt_image", ""), "tour_id": tour_id, "plads": tour.get("plads", ""), "fraction": tour.get("fraction", "")}


@api_router.delete("/tours/report/{report_id}")
async def delete_tours_by_report(report_id: str):
    result = await db.tours.delete_many({"report_id": report_id})
    return {"message": f"Deleted {result.deleted_count} tours"}

# ============= REPORT ENDPOINTS =============

@api_router.get("/reports/history")
async def get_report_history(days: int = 30):
    """Get report history for the last N days - optimized batch query"""
    from datetime import timedelta
    
    try:
        today = datetime.now(DK_TZ).date()
        start_date = today - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")
        
        # Batch fetch: 2 queries instead of 2*N
        all_reports = await db.reports.find(
            {"report_date": {"$gte": start_str, "$lte": end_str}},
            {"_id": 0, "id": 1, "report_date": 1, "driver_id": 1, "driver_name": 1, "start_time": 1, "end_time": 1, "plads": 1}
        ).to_list(500)
        
        all_tours = await db.tours.find(
            {"date": {"$gte": start_str, "$lte": end_str}, "is_pause": False},
            {"_id": 0, "date": 1, "completed": 1, "weight": 1}
        ).to_list(5000)
        
        # Group by date in Python
        reports_by_date = {}
        for r in all_reports:
            d = r.get("report_date", "")
            if d not in reports_by_date:
                reports_by_date[d] = []
            reports_by_date[d].append(r)
        
        tours_by_date = {}
        for t in all_tours:
            d = t.get("date", "")
            if d not in tours_by_date:
                tours_by_date[d] = []
            tours_by_date[d].append(t)
        
        history = []
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            day_reports = reports_by_date.get(date_str, [])
            if not day_reports:
                continue
            
            day_tours = tours_by_date.get(date_str, [])
            total_tours = len(day_tours)
            completed_tours = len([t for t in day_tours if t.get("completed")])
            total_weight = sum(t.get("weight", 0) or 0 for t in day_tours)
            driver_ids = set(r.get("driver_id") for r in day_reports if r.get("driver_id"))
            
            history.append({
                "date": date_str,
                "total_tours": total_tours,
                "completed_tours": completed_tours,
                "total_weight": total_weight,
                "driver_count": len(driver_ids),
                "reports": [{
                    "id": r["id"],
                    "driver_name": r.get("driver_name", ""),
                    "start_time": r.get("start_time", ""),
                    "end_time": r.get("end_time", ""),
                    "plads": r.get("plads", "")
                } for r in day_reports[:10]]
            })
        
        return history
    except Exception as e:
        logger.error(f"Error in report history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

@api_router.get("/reports", response_model=List[Report])
async def get_reports(driver_id: Optional[str] = None, date: Optional[str] = None):
    query = {}
    if driver_id:
        query["driver_id"] = driver_id
    if date:
        query["report_date"] = date
    reports = await db.reports.find(query, {"_id": 0}).to_list(100)
    return reports

@api_router.get("/reports/{report_id}", response_model=Report)
async def get_report(report_id: str):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return Report(**report)

@api_router.post("/reports", response_model=Report)
async def create_report(report: ReportCreate):
    report_obj = Report(**report.model_dump())
    doc = report_obj.model_dump()
    await db.reports.insert_one(doc)
    return report_obj

@api_router.put("/reports/{report_id}", response_model=Report)
async def update_report(report_id: str, update: ReportUpdate):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.reports.update_one(
        {"id": report_id},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    return Report(**report)

@api_router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    await db.tours.delete_many({"report_id": report_id})
    result = await db.reports.delete_one({"id": report_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"message": "Report and associated tours deleted"}

# ============= MAIL PARSING ENDPOINT =============

@api_router.post("/parse-mail", response_model=ParseMailResponse)
async def parse_mail(request: ParseMailRequest):
    text = request.text
    debug_lines = []
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    debug_lines.append(f"Total lines found: {len(lines)}")
    
    parsed_tours = []
    facility_groups = {}
    
    # Detect format: check if lines have tabs (horizontal) or not (vertical)
    tab_lines = [ln for ln in lines if '\t' in ln or len(re.split(r'\s{2,}', ln)) >= 5]
    
    if len(tab_lines) >= 1:
        # ===== HORIZONTAL TAB-SEPARATED FORMAT =====
        debug_lines.append("Detected: TAB-SEPARATED format")
        
        first_line = lines[0].lower() if lines else ""
        start_idx = 0
        if "afhentning" in first_line or "container" in first_line or "fraktion" in first_line:
            start_idx = 1
            debug_lines.append("Header line detected, skipping")
        
        for i, line in enumerate(lines[start_idx:], start=start_idx):
            parts = line.split('\t')
            
            if len(parts) < 5:
                parts = re.split(r'\s{2,}', line)
            
            if len(parts) >= 6:
                try:
                    date = parts[0].strip()
                    container = parts[1].strip()
                    fraction = parts[2].strip()
                    facility = parts[4].strip()
                    address = parts[5].strip()
                    open_from = parts[6].strip() if len(parts) > 6 else ""
                    open_to = parts[7].strip() if len(parts) > 7 else ""
                    remark = parts[8].strip() if len(parts) > 8 else ""
                    
                    date_pattern = re.compile(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$')
                    if not date_pattern.match(date):
                        debug_lines.append(f"Line {i+1}: Invalid date format '{date}'")
                        continue
                    
                    if fraction and facility:
                        tour = ParsedTour(
                            date=date,
                            container=container,
                            fraction=fraction,
                            facility=facility,
                            address=address,
                            open_from=open_from,
                            open_to=open_to,
                            remark=remark
                        )
                        parsed_tours.append(tour)
                        
                        if facility not in facility_groups:
                            facility_groups[facility] = []
                        facility_groups[facility].append({
                            "container": container,
                            "fraction": fraction,
                            "address": address,
                            "remark": remark
                        })
                        
                        debug_lines.append(f"Line {i+1}: OK - {container} | {fraction} -> {facility}")
                    else:
                        debug_lines.append(f"Line {i+1}: Skipped - missing fraction or facility")
                        
                except Exception as e:
                    debug_lines.append(f"Line {i+1}: Error - {str(e)}")
            else:
                date_pattern = re.compile(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$')
                if date_pattern.match(line):
                    debug_lines.append(f"Line {i+1}: Found date, but not enough columns ({len(parts)} parts)")
                else:
                    debug_lines.append(f"Line {i+1}: Skipped - not enough columns ({len(parts)} parts)")
    else:
        # ===== VERTICAL MULTI-LINE FORMAT =====
        # Each tour spans multiple lines:
        # Line 1: Date (dd-mm-yyyy)
        # Line 2: Container number
        # Line 3: Fraction (material)
        # Line 4: Type (Tomning, Ombytning, etc.)
        # Line 5: Facility/Company
        # Line 6: Address
        # Line 7+: Optional (size, remark, etc.)
        debug_lines.append("Detected: VERTICAL multi-line format")
        
        date_pattern = re.compile(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$')
        
        # Find all date line indices to split into tour blocks
        date_indices = []
        for i, line in enumerate(lines):
            if date_pattern.match(line):
                date_indices.append(i)
        
        debug_lines.append(f"Found {len(date_indices)} date lines")
        
        for idx, date_start in enumerate(date_indices):
            # Get lines until next date or end
            next_start = date_indices[idx + 1] if idx + 1 < len(date_indices) else len(lines)
            block = lines[date_start:next_start]
            
            if len(block) < 4:
                debug_lines.append(f"Block at line {date_start+1}: Too few lines ({len(block)})")
                continue
            
            try:
                date = block[0].strip()
                container = block[1].strip() if len(block) > 1 else ""
                fraction = block[2].strip() if len(block) > 2 else ""
                # block[3] is usually "Tømning 7 14" or "Tømning 6 16 some remark"
                tour_type_line = block[3].strip() if len(block) > 3 else ""
                facility = block[4].strip() if len(block) > 4 else ""
                address = block[5].strip() if len(block) > 5 else ""
                # Remaining lines could be container size, remarks etc
                extra_info = " ".join(block[6:]).strip() if len(block) > 6 else ""
                
                # Parse tour_type_line to extract open_from, open_to, remark
                # Format: "Tømning 7 14" or "Tømning 6 16 Skal være tilbage..."
                open_from = ""
                open_to = ""
                remark = ""
                tour_type = ""
                
                if tour_type_line:
                    type_parts = tour_type_line.split()
                    if len(type_parts) >= 1:
                        tour_type = type_parts[0]  # "Tømning" or "Ombytning"
                    if len(type_parts) >= 3 and type_parts[1].isdigit() and type_parts[2].replace(":", "").replace(".", "").isdigit():
                        open_from = type_parts[1]
                        open_to = type_parts[2].split(":")[0] if ":" in type_parts[2] else type_parts[2]
                        # Remaining parts are actual remark (not including type name)
                        remaining = " ".join(type_parts[3:]).strip()
                        remark = remaining if remaining else tour_type
                    elif len(type_parts) >= 2 and type_parts[1].isdigit():
                        open_from = type_parts[1]
                        remaining = " ".join(type_parts[2:]).strip()
                        remark = f"{tour_type} {remaining}".strip() if remaining else tour_type
                    else:
                        remark = tour_type_line
                
                # Append extra_info to remark (skip if just a number - likely container size)
                if extra_info and not extra_info.strip().isdigit():
                    remark = f"{remark} {extra_info}".strip() if remark else extra_info
                
                if fraction and (facility or address):
                    # If no facility but has address, use tour_type or empty
                    if not facility and address:
                        facility = tour_type or ""
                    
                    tour = ParsedTour(
                        date=date,
                        container=container,
                        fraction=fraction,
                        facility=facility,
                        address=address,
                        open_from=open_from,
                        open_to=open_to,
                        remark=remark
                    )
                    parsed_tours.append(tour)
                    
                    if facility not in facility_groups:
                        facility_groups[facility] = []
                    facility_groups[facility].append({
                        "container": container,
                        "fraction": fraction,
                        "address": address,
                        "remark": remark
                    })
                    
                    debug_lines.append(f"Block {idx+1}: OK - {container} | {fraction} -> {facility} @ {address}")
                else:
                    debug_lines.append(f"Block {idx+1}: Skipped - missing fraction or facility/address")
            except Exception as e:
                debug_lines.append(f"Block {idx+1}: Error - {str(e)}")
    
    grouped_summary = {}
    for facility, items in facility_groups.items():
        grouped_summary[facility] = {
            "count": len(items),
            "containers": [item["container"] for item in items]
        }
    
    debug_lines.append("\n=== GROUPED BY FACILITY ===")
    for facility, data in grouped_summary.items():
        debug_lines.append(f"{facility}: {data['count']} ture")
    
    return ParseMailResponse(
        success=len(parsed_tours) > 0,
        tours=parsed_tours,
        count=len(parsed_tours),
        debug_info="\n".join(debug_lines),
        grouped_by_facility=grouped_summary
    )



# ============= ARGO PARSING ENDPOINT =============

class ArgoParseRequest(BaseModel):
    text: str
    date: str  # YYYY-MM-DD

class ArgoParsedTour(BaseModel):
    container: str
    container_type: str
    fra: str
    til: str
    fraktion: str
    plads: str
    tid: str

class ArgoParseResponse(BaseModel):
    tours: List[ArgoParsedTour]
    count: int

@api_router.post("/parse-argo", response_model=ArgoParseResponse)
async def parse_argo(request: ArgoParseRequest):
    """Parse Argo order table text (tab-separated) into tour objects."""
    lines = request.text.strip().split("\n")
    parsed = []
    header_skipped = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Split by tab first, fallback to multiple spaces
        parts = line.split("\t")
        if len(parts) < 3:
            parts = re.split(r'  +', line)
        
        # Skip header lines (contain column titles)
        lower_line = line.lower()
        if not header_skipped and ("type" in lower_line and "størrelse" in lower_line or "fra" in lower_line and "til" in lower_line and "fraktion" in lower_line):
            header_skipped = True
            continue
        # Also skip lines starting with # that look like headers
        if line.startswith("#") and len(parts) > 3:
            header_skipped = True
            continue
        
        if len(parts) < 4:
            continue
        
        container = parts[0].strip() if len(parts) > 0 else ""
        container_type = parts[1].strip() if len(parts) > 1 else ""
        fra = parts[2].strip() if len(parts) > 2 else ""
        til = parts[3].strip() if len(parts) > 3 else ""
        fraktion = parts[4].strip() if len(parts) > 4 else ""
        tid = parts[6].strip() if len(parts) > 6 else ""
        
        # Extract plads from "Fra" field (e.g., "Køge Genbrugsplads" → "Køge")
        plads = fra.replace("Genbrugsplads", "").strip()
        
        if container and fra:
            parsed.append(ArgoParsedTour(
                container=container,
                container_type=container_type,
                fra=fra,
                til=til,
                fraktion=fraktion,
                plads=plads,
                tid=tid
            ))
    
    return ArgoParseResponse(tours=parsed, count=len(parsed))

@api_router.post("/import-argo")
async def import_argo(request: dict = Body(...)):
    """Import parsed Argo tours into the database."""
    tours_data = request.get("tours", [])
    date = request.get("date", "")
    plads = request.get("plads", "")
    if not date or not tours_data:
        raise HTTPException(status_code=400, detail="Date and tours are required")
    
    created = []
    for t in tours_data:
        tour_id = str(uuid.uuid4())
        now = datetime.now(ZoneInfo("Europe/Copenhagen"))
        # Use plads from request if not in tour data
        tour_plads = t.get("plads", "") or plads
        tour_doc = {
            "id": tour_id,
            "date": date,
            "container": t.get("container", ""),
            "fraction": t.get("fraktion", ""),
            "address": t.get("fra", ""),
            "facility": t.get("til", ""),
            "plads": tour_plads,
            "is_pause": False,
            "driver_name": "",
            "weight": 0,
            "completed": False,
            "on_way": False,
            "on_way_time": "",
            "time": "",
            "receipt_image": "",
            "remark": f"Argo | {t.get('container_type', '')}",
            "priority": "normal",
            "is_same_day": False,
            "claimed_by": "",
            "claimed_by_id": "",
            "open_from": "",
            "open_to": "",
            "sort_order": 0,
            "route_distance_km": 0,
            "route_order": 0,
            "transport_mode": "",
            "source": "argo",
            "created_at": now.isoformat()
        }
        await db.tours.insert_one(tour_doc)
        created.append(tour_id)
    
    return {"message": f"{len(created)} ture importeret fra Argo", "count": len(created), "tour_ids": created}



# ============= PDF PARSING ENDPOINT =============

@api_router.post("/parse-pdf", response_model=ParseMailResponse)
async def parse_pdf(file: UploadFile = File(...)):
    """Extract text from uploaded PDF and parse material/quantity lines into tours.
    Each quantity unit = 1 separate job (tour).
    Example: 'Pap = 2' creates 2 separate Pap tours.
    Range values like '3-4' use the minimum (3).
    """
    if fitz is None:
        raise HTTPException(status_code=503, detail="PDF parsing not available - PyMuPDF library missing")
    debug_lines = []
    parsed_tours = []
    
    try:
        contents = await file.read()
        debug_lines.append(f"PDF file received: {file.filename} ({len(contents)} bytes)")
        
        # Extract text from PDF using PyMuPDF
        pdf_doc = fitz.open(stream=contents, filetype="pdf")
        full_text = ""
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_text = page.get_text()
            full_text += page_text + "\n"
            debug_lines.append(f"Page {page_num + 1}: extracted {len(page_text)} chars")
        pdf_doc.close()
        
        if not full_text.strip():
            debug_lines.append("WARNING: No text extracted from PDF")
            return ParseMailResponse(
                success=False,
                tours=[],
                count=0,
                debug_info="\n".join(debug_lines),
                grouped_by_facility={}
            )
        
        debug_lines.append(f"Total extracted text: {len(full_text)} chars")
        
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        debug_lines.append(f"Total non-empty lines: {len(lines)}")
        
        # --- Extract date from PDF ---
        extracted_date = ""
        date_patterns = [
            re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})'),  # DD.MM.YYYY or DD-MM-YYYY
            re.compile(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})'),  # YYYY-MM-DD
            re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2})'),  # DD.MM.YY
        ]
        
        for line in lines:
            for dp_idx, dp in enumerate(date_patterns):
                m = dp.search(line)
                if m:
                    groups = m.groups()
                    if dp_idx == 0:  # DD.MM.YYYY
                        day, month, year = groups
                        extracted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    elif dp_idx == 1:  # YYYY-MM-DD
                        year, month, day = groups
                        extracted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    elif dp_idx == 2:  # DD.MM.YY
                        day, month, year = groups
                        full_year = f"20{year}" if int(year) < 50 else f"19{year}"
                        extracted_date = f"{full_year}-{month.zfill(2)}-{day.zfill(2)}"
                    debug_lines.append(f"Date found: {extracted_date} (from: '{line}')")
                    break
            if extracted_date:
                break
        
        if not extracted_date:
            extracted_date = get_dk_date_str()
            debug_lines.append(f"No date found in PDF, using today: {extracted_date}")
        
        # --- Parse material lines ---
        # Patterns: "Material = N", "Material: N", "Material - N", "Material N stk", "N x Material"
        material_pattern = re.compile(
            r'^(.+?)\s*[=:\-–]\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*$'
        )
        # Also match "N x Material" or "N stk Material"
        reverse_pattern = re.compile(
            r'^(\d+)\s*(?:x|stk\.?|styk)\s+(.+)$', re.IGNORECASE
        )
        
        # Collect notes: lines that don't match material patterns
        current_notes = []
        facility_groups = {}
        
        for i, line in enumerate(lines):
            # Skip date lines, empty, very short lines, headers
            if len(line) < 2:
                continue
            
            # Check for material pattern: "Material = N" or "Material: N"
            m = material_pattern.match(line)
            if m:
                material = m.group(1).strip()
                qty_str = m.group(2)
                qty_max_str = m.group(3)  # For ranges like "3-4"
                
                # Use minimum for ranges
                qty = int(qty_str)
                if qty_max_str:
                    debug_lines.append(f"  Range detected: {qty_str}-{qty_max_str}, using minimum: {qty}")
                
                if qty <= 0:
                    debug_lines.append(f"Line {i+1}: Skipped - zero quantity for '{material}'")
                    continue
                
                # Cap at reasonable max to avoid abuse
                qty = min(qty, 50)
                
                # Attach any pending notes
                note = " | ".join(current_notes) if current_notes else ""
                current_notes = []
                
                debug_lines.append(f"Line {i+1}: '{material}' x {qty}" + (f" [note: {note}]" if note else ""))
                
                # Create 1 tour per quantity unit
                for _ in range(qty):
                    tour = ParsedTour(
                        date=extracted_date,
                        container="",
                        fraction=material,
                        facility="",
                        address="",
                        remark=note
                    )
                    parsed_tours.append(tour)
                
                if material not in facility_groups:
                    facility_groups[material] = {"count": 0, "containers": []}
                facility_groups[material]["count"] += qty
                continue
            
            # Check reverse pattern: "N x Material"
            rm = reverse_pattern.match(line)
            if rm:
                qty = min(int(rm.group(1)), 50)
                material = rm.group(2).strip()
                
                note = " | ".join(current_notes) if current_notes else ""
                current_notes = []
                
                debug_lines.append(f"Line {i+1}: '{material}' x {qty} (reverse format)" + (f" [note: {note}]" if note else ""))
                
                for _ in range(qty):
                    tour = ParsedTour(
                        date=extracted_date,
                        container="",
                        fraction=material,
                        facility="",
                        address="",
                        remark=note
                    )
                    parsed_tours.append(tour)
                
                if material not in facility_groups:
                    facility_groups[material] = {"count": 0, "containers": []}
                facility_groups[material]["count"] += qty
                continue
            
            # Check if line is a potential note (all caps, or known keywords)
            note_keywords = ["rystes", "henvendelse", "obs", "vigtigt", "bemærk", "husk", "note", "nøgle", "aflås", "ring"]
            line_lower = line.lower()
            if any(kw in line_lower for kw in note_keywords) or line.isupper():
                current_notes.append(line)
                debug_lines.append(f"Line {i+1}: Note detected: '{line}'")
            else:
                # Might be a date line or header - skip
                debug_lines.append(f"Line {i+1}: Skipped (no pattern match): '{line[:60]}'")
        
        debug_lines.append(f"\n=== TOTAL: {len(parsed_tours)} tours created ===")
        for mat, data in facility_groups.items():
            debug_lines.append(f"  {mat}: {data['count']} ture")
        
        return ParseMailResponse(
            success=len(parsed_tours) > 0,
            tours=parsed_tours,
            count=len(parsed_tours),
            debug_info="\n".join(debug_lines),
            grouped_by_facility=facility_groups
        )
        
    except Exception as e:
        debug_lines.append(f"ERROR: {str(e)}")
        return ParseMailResponse(
            success=False,
            tours=[],
            count=0,
            debug_info="\n".join(debug_lines),
            grouped_by_facility={}
        )


# ============= PAUSE ENDPOINT =============

@api_router.post("/tours/pause", response_model=Tour)
async def create_pause(report_id: str = "", plads: str = "", driver_id: str = "", driver_name: str = "", date: str = ""):
    pause_date = date if date else get_dk_date_str()
    pause_tour = Tour(
        date=pause_date,
        container="",
        fraction="PAUSE",
        facility="PAUSE",
        address="",
        is_pause=True,
        plads=plads,
        driver_id=driver_id,
        driver_name=driver_name,
        report_id=report_id
    )
    doc = pause_tour.model_dump()
    await db.tours.insert_one(doc)
    return pause_tour

# ============= MESSAGE ENDPOINTS =============

@api_router.get("/messages", response_model=List[Message])
async def get_messages(driver_id: Optional[str] = None, _auth: dict = Depends(get_current_user_payload)):
    query = {}
    if driver_id:
        query["to_driver_id"] = driver_id
    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [Message(**m) for m in messages]

@api_router.post("/messages", response_model=Message)
async def create_message(message: MessageCreate, _auth: dict = Depends(get_current_user_payload)):
    # Handle admin to driver message
    if message.to_driver_id:
        driver = await db.drivers.find_one({"id": message.to_driver_id}, {"_id": 0})
        driver_name = driver["name"] if driver else message.to_driver_id
        
        msg_obj = Message(
            from_admin=True,
            to_driver_id=message.to_driver_id,
            to_driver_name=driver_name,
            content=message.content
        )
    # Handle driver to admin message
    elif message.to_admin:
        msg_obj = Message(
            from_admin=False,
            from_driver_id=message.from_driver_id,
            from_driver_name=message.from_driver_name,
            to_admin=True,
            content=message.content
        )
    # Handle driver to driver message (private)
    elif message.to_driver_name and message.from_driver_name:
        msg_obj = Message(
            from_admin=False,
            from_driver_name=message.from_driver_name,
            to_driver_name=message.to_driver_name,
            to_admin=False,
            content=message.content
        )
    else:
        raise HTTPException(status_code=400, detail="Must specify to_driver_id, to_driver_name, or to_admin")
    
    doc = msg_obj.model_dump()
    await db.messages.insert_one(doc)
    return msg_obj

@api_router.put("/messages/{message_id}/read")
async def mark_message_read(message_id: str, _auth: dict = Depends(get_current_user_payload)):
    result = await db.messages.update_one(
        {"id": message_id},
        {"$set": {"read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Message marked as read"}

@api_router.delete("/messages/{message_id}")
async def delete_message(message_id: str, _auth: dict = Depends(get_current_user_payload)):
    result = await db.messages.delete_one({"id": message_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Message deleted"}

# ============= ADMIN STATS ENDPOINT =============

@api_router.get("/admin/stats", response_model=List[DriverStats])
async def get_admin_stats():
    try:
        drivers = await db.drivers.find({}, {"_id": 0, "id": 1, "name": 1, "plate": 1}).to_list(100)
        today = get_dk_date_str()
        driver_ids = [d["id"] for d in drivers]
        
        # Batch fetch: ALL tours for all drivers at once (2 queries instead of 2N)
        all_tours = await db.tours.find(
            {"driver_id": {"$in": driver_ids}, "is_pause": False},
            {"_id": 0, "driver_id": 1, "date": 1, "completed": 1, "weight": 1}
        ).to_list(5000)
        
        all_reports = await db.reports.find(
            {"driver_id": {"$in": driver_ids}},
            {"_id": 0, "driver_id": 1, "report_date": 1, "start_time": 1, "end_time": 1, "plads": 1}
        ).sort("report_date", -1).to_list(500)
        
        # Index by driver_id in Python
        tours_by_driver = {}
        for t in all_tours:
            did = t.get("driver_id", "")
            if did not in tours_by_driver:
                tours_by_driver[did] = []
            tours_by_driver[did].append(t)
        
        reports_by_driver = {}
        for r in all_reports:
            did = r.get("driver_id", "")
            if did not in reports_by_driver:
                reports_by_driver[did] = []
            reports_by_driver[did].append(r)
        
        stats = []
        for driver in drivers:
            driver_id = driver["id"]
            d_tours = tours_by_driver.get(driver_id, [])
            d_reports = reports_by_driver.get(driver_id, [])
            
            today_tours = [t for t in d_tours if t.get("date") == today]
            
            stats.append(DriverStats(
                driver_id=driver_id,
                driver_name=driver["name"],
                plate=driver["plate"],
                total_tours=len(d_tours),
                completed_tours=len([t for t in d_tours if t.get("completed")]),
                total_weight=sum(t.get("weight", 0) or 0 for t in d_tours),
                today_tours=len(today_tours),
                today_completed=len([t for t in today_tours if t.get("completed")]),
                last_start_time=d_reports[0]["start_time"] if d_reports else "",
                last_end_time=d_reports[0]["end_time"] if d_reports else "",
                reports=[{
                    "date": r["report_date"],
                    "start": r["start_time"],
                    "end": r["end_time"],
                    "plads": r.get("plads", "")
                } for r in d_reports[:10]]
            ))
        
        return stats
    except Exception as e:
        logger.error(f"Error in admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

# ============= ADMIN LOGIN =============

@api_router.post("/admin/login")
async def admin_login(credentials: dict):
    password = credentials.get("password", "")
    admin_pw = await get_admin_password()
    if password == admin_pw:
        return {"success": True, "message": "Login successful"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# ============= DRIVER LOGIN =============

@api_router.post("/driver/login")
async def driver_login(credentials: dict):
    """DEPRECATED (Phase 2): Drivers nu skal logge ind via /api/auth/login med
    email + password. Det fælles 'driver_code' er fjernet — hver chauffør
    opretter sit eget password via invitation-mail fra logistik-admin."""
    raise HTTPException(
        status_code=410,
        detail="Chauffør-login er flyttet. Brug email + adgangskode via /api/auth/login. "
               "Kontakt din logistik-admin for en invitation hvis du ikke har et password endnu.",
    )

@api_router.post("/driver/verify-code")
async def verify_driver_code(credentials: dict):
    """DEPRECATED (Phase 2): Fælles driver-code findes ikke længere."""
    raise HTTPException(
        status_code=410,
        detail="Driver-kode er udfaset. Login via /api/auth/login med email + adgangskode.",
    )

# ============= END OF SHIFT =============

@api_router.post("/driver/end-shift")
async def driver_end_shift(data: dict):
    """Save end-of-shift report with PDF data for admin."""
    driver_name = data.get("driver_name", "")
    if not driver_name:
        raise HTTPException(status_code=400, detail="Driver name required")
    
    archive = PDFArchive(
        driver_name=driver_name,
        vehicle_reg=data.get("vehicle_reg", ""),
        plads=data.get("plads", ""),
        report_date=data.get("report_date", get_dk_date_str()),
        file_name=data.get("file_name", f"dagrapport_{driver_name}.pdf"),
        file_data=data.get("file_data", ""),
        total_tours=data.get("total_tours", 0),
        completed_tours=data.get("completed_tours", 0),
        total_weight=data.get("total_weight", 0),
        start_time=data.get("start_time", ""),
        end_time=data.get("end_time", ""),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    )
    
    await db.pdf_archives.insert_one(archive.model_dump())
    return {"id": archive.id, "message": "Dagrapport gemt"}

@api_router.post("/admin/cleanup")
async def admin_cleanup(credentials: dict):
    """Admin-triggered cleanup of old data."""
    password = credentials.get("password", "")
    admin_pw = await get_admin_password()
    if password != admin_pw:
        raise HTTPException(status_code=401, detail="Unauthorized")
    await cleanup_old_tours()
    return {"message": "Cleanup completed"}


# ============= ADMIN STATISTICS ENDPOINT =============

@api_router.get("/admin/statistics")
async def get_admin_statistics(months: int = 6, payload: Optional[dict] = Depends(get_optional_user_payload)):
    """Comprehensive admin statistics: driver performance, material usage, daily jobs, work hours.

    2026-10-16: Rettet så tallene faktisk viser noget for et logistikfirma:
    chauffører ligger i `users` (role=driver) - den gamle `drivers`-kollektion
    er tom - og ture hentes på samme måde som GET /tours (egne ture + ture
    fra kunder der har tildelt firmaet), ikke kun dem firmaet selv ejer.
    """
    try:
        today = datetime.now(DK_TZ).date()
        # Date ranges
        months_ago = (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        role = (payload or {}).get("role")
        la_company = (payload or {}).get("company_id") if role == "logistics_admin" else None
        scope = ({"$or": [{"company_id": la_company}, {"assigned_logistics_company_ids": la_company}]}
                 if la_company else {})

        drv_q = {"role": "driver"}
        if la_company:
            drv_q["company_id"] = la_company
        users = await _raw_db.users.find(drv_q, {"_id": 0, "id": 1, "name": 1, "plate": 1, "vehicle_reg": 1}).to_list(500)
        drivers = [{"id": u.get("id", ""), "name": u.get("name", ""),
                    "plate": u.get("plate") or u.get("vehicle_reg") or ""} for u in users if u.get("name")]
        legacy = await db.drivers.find({}, {"_id": 0, "id": 1, "name": 1, "plate": 1}).to_list(200)
        known = {d["name"] for d in drivers}
        drivers += [{"id": d.get("id", ""), "name": d["name"], "plate": d.get("plate", "")}
                    for d in legacy if d.get("name") and d["name"] not in known]
        driver_ids = [d["id"] for d in drivers if d["id"]]
        driver_names = {d["id"]: d["name"] for d in drivers}

        # All tours in last N months (excluding pauses, estimates and "kan ikke gennemføres")
        tour_q = {"date": {"$gte": months_ago, "$lte": today_str}, "is_pause": {"$ne": True},
                  "tour_type": {"$ne": "estimat"}, "not_completed": {"$ne": True}}
        if scope:
            tour_q = {"$and": [tour_q, scope]}
        tour_src = _raw_db.tours if scope else db.tours
        all_tours = await tour_src.find(
            tour_q,
            {"_id": 0, "date": 1, "completed": 1, "weight": 1, "fraction": 1, "on_way": 1,
             "driver_name": 1, "driver_id": 1, "claimed_by": 1, "facility": 1, "plads": 1, "time": 1,
             "on_way_time": 1, "priority": 1, "remark": 1}
        ).to_list(20000)
        _scope = await _la_scope(payload)
        if _scope:
            all_tours = [t for t in all_tours if _scope_ok(t, _scope, la_company)]

        # All reports/sessions in last N months
        all_reports = await db.reports.find(
            {"report_date": {"$gte": months_ago, "$lte": today_str}},
            {"_id": 0, "driver_name": 1, "report_date": 1, "start_time": 1, "end_time": 1}
        ).to_list(5000)

        all_sessions = await db.driver_sessions.find(
            {"report_date": {"$gte": months_ago}},
            {"_id": 0, "driver_name": 1, "report_date": 1, "start_time": 1, "end_time": 1}
        ).to_list(5000)

        # Fase 18.1 (2026-02-28): driver_time_entries er nu primær kilde til
        # arbejdstimer. Reports/sessions er kun fallback for dage uden
        # entries. Vi henter ALLE entries for chaufførerne (driver_id) i
        # perioden og grupperer (driver_name, date).
        all_entries = await _raw_db.driver_time_entries.find(
            {"driver_id": {"$in": driver_ids},
             "date": {"$gte": months_ago, "$lte": today_str},
             "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
            {"_id": 0},
        ).to_list(20000)
        entries_by_driver_date = {}
        for e in all_entries:
            did = e.get("driver_id", "")
            d = e.get("date", "")
            if not did or not d:
                continue
            dname = driver_names.get(did, "")
            if not dname:
                continue
            entries_by_driver_date.setdefault((dname, d), []).append(e)

        # Container orders
        order_q = {"created_at": {"$gte": months_ago}}
        if scope:
            order_q = {"$and": [order_q, scope]}
        all_orders = await (_raw_db.container_orders if scope else db.container_orders).find(
            order_q,
            {"_id": 0, "location_name": 1, "material": 1, "status": 1, "created_at": 1, "order_date": 1}
        ).to_list(5000)

        # ---- 1) JOBS PER DAY (last 30 days) ----
        jobs_per_day = {}
        for i in range(30):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            jobs_per_day[d] = {"date": d, "total": 0, "completed": 0, "weight": 0}

        for t in all_tours:
            d = t.get("date", "")
            if d in jobs_per_day:
                jobs_per_day[d]["total"] += 1
                if t.get("completed"):
                    jobs_per_day[d]["completed"] += 1
                    jobs_per_day[d]["weight"] += (t.get("weight") or 0)

        jobs_per_day_list = sorted(jobs_per_day.values(), key=lambda x: x["date"])

        # ---- 2) DRIVER MONTHLY PERFORMANCE ----
        driver_monthly = {}
        for d in drivers:
            driver_monthly[d["name"]] = {
                "name": d["name"],
                "plate": d["plate"],
                "total_tours": 0,
                "completed_tours": 0,
                "total_weight": 0,
                "work_days": set(),
                "total_hours": 0,
                "tour_durations": [],  # list of minutes per completed tour
                "duration_buckets": {"short": 0, "medium": 0, "long": 0},  # <30, 30-60, >60 min
            }

        def parse_hhmm_to_min(s):
            try:
                if not s or ":" not in str(s):
                    return None
                parts = str(s).strip().split(":")
                return int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                return None

        for t in all_tours:
            name = t.get("claimed_by") or t.get("driver_name", "")
            if name in driver_monthly:
                driver_monthly[name]["total_tours"] += 1
                if t.get("completed"):
                    driver_monthly[name]["completed_tours"] += 1
                    driver_monthly[name]["total_weight"] += (t.get("weight") or 0)
                    # Tour duration in minutes
                    s_min = parse_hhmm_to_min(t.get("on_way_time", ""))
                    e_min = parse_hhmm_to_min(t.get("time", ""))
                    if s_min is not None and e_min is not None:
                        dur = e_min - s_min
                        if dur < 0:
                            dur += 24 * 60
                        if 0 < dur <= 600:  # ignore outliers (>10 hours)
                            driver_monthly[name]["tour_durations"].append(dur)
                            if dur < 30:
                                driver_monthly[name]["duration_buckets"]["short"] += 1
                            elif dur <= 60:
                                driver_monthly[name]["duration_buckets"]["medium"] += 1
                            else:
                                driver_monthly[name]["duration_buckets"]["long"] += 1
                d = t.get("date", "")
                if d:
                    driver_monthly[name]["work_days"].add(d)

        # Calculate work hours from reports + sessions
        def calc_hours(start_str, end_str):
            try:
                if not start_str or not end_str:
                    return 0
                s_parts = start_str.replace(".", ":").split(":")
                e_parts = end_str.replace(".", ":").split(":")
                s_min = int(s_parts[0]) * 60 + int(s_parts[1]) if len(s_parts) >= 2 else 0
                e_min = int(e_parts[0]) * 60 + int(e_parts[1]) if len(e_parts) >= 2 else 0
                diff = e_min - s_min
                return max(0, diff / 60)
            except (ValueError, IndexError):
                return 0

        # Fase 18.1 (2026-02-28): Brug driver_time_entries som primær kilde.
        # Per (driver_name, date) summer work_min via fælles helper, så
        # rapport-tallene matcher 1:1 med Driver Archive day-row chips.
        _now_dt2 = datetime.now(DK_TZ)
        _today_str_local = _now_dt2.strftime("%Y-%m-%d")
        _now_hhmm_local = _now_dt2.strftime("%H:%M")
        covered_keys = set()  # (driver_name, date) — entries-dækkede dage
        for (dname, d), entries_for_day in entries_by_driver_date.items():
            if dname not in driver_monthly:
                continue
            summary = _summarize_day_entries(
                entries_for_day,
                today_str=(_today_str_local if d == _today_str_local else ""),
                now_hhmm=(_now_hhmm_local if d == _today_str_local else ""),
            )
            if summary["any"]:
                driver_monthly[dname]["total_hours"] += summary["work_min"] / 60.0
                covered_keys.add((dname, d))

        # Fallback: kun datoer UDEN entries falder tilbage til reports/sessions
        for r in all_reports:
            name = r.get("driver_name", "")
            d = r.get("report_date", "")
            if name in driver_monthly and (name, d) not in covered_keys:
                driver_monthly[name]["total_hours"] += calc_hours(
                    r.get("start_time", ""), r.get("end_time", "")
                )

        for s in all_sessions:
            name = s.get("driver_name", "")
            d = s.get("report_date", "")
            if name in driver_monthly and (name, d) not in covered_keys:
                driver_monthly[name]["total_hours"] += calc_hours(
                    s.get("start_time", ""), s.get("end_time", "")
                )

        # Convert sets to counts
        driver_stats_list = []
        for name, data in driver_monthly.items():
            durs = data["tour_durations"]
            avg_dur = round(sum(durs) / len(durs), 1) if durs else 0
            min_dur = min(durs) if durs else 0
            max_dur = max(durs) if durs else 0
            total_tour_min = sum(durs) if durs else 0
            driver_stats_list.append({
                "name": data["name"],
                "plate": data["plate"],
                "total_tours": data["total_tours"],
                "completed_tours": data["completed_tours"],
                "total_weight": round(data["total_weight"], 1),
                "work_days": len(data["work_days"]),
                "total_hours": round(data["total_hours"], 1),
                "avg_tours_per_day": round(data["total_tours"] / max(len(data["work_days"]), 1), 1),
                "avg_tour_minutes": avg_dur,
                "min_tour_minutes": min_dur,
                "max_tour_minutes": max_dur,
                "total_tour_minutes": total_tour_min,
                "short_tours": data["duration_buckets"]["short"],
                "medium_tours": data["duration_buckets"]["medium"],
                "long_tours": data["duration_buckets"]["long"],
            })
        driver_stats_list.sort(key=lambda x: x["completed_tours"], reverse=True)

        # ---- 3) MATERIAL USAGE ----
        material_usage = {}
        for t in all_tours:
            frac = t.get("fraction", "").strip()
            if frac and frac != "PAUSE":
                if frac not in material_usage:
                    material_usage[frac] = {"name": frac, "count": 0, "weight": 0}
                material_usage[frac]["count"] += 1
                if t.get("completed"):
                    material_usage[frac]["weight"] += (t.get("weight") or 0)

        material_list = sorted(material_usage.values(), key=lambda x: x["count"], reverse=True)

        # ---- 4) GENBRUGSPLADS STATS ----
        plads_stats = {}
        for t in all_tours:
            p = t.get("plads", "").strip()
            if p:
                if p not in plads_stats:
                    plads_stats[p] = {"name": p, "total": 0, "completed": 0, "weight": 0}
                plads_stats[p]["total"] += 1
                if t.get("completed"):
                    plads_stats[p]["completed"] += 1
                    plads_stats[p]["weight"] += (t.get("weight") or 0)

        plads_list = sorted(plads_stats.values(), key=lambda x: x["total"], reverse=True)

        # ---- 5) ORDER STATS ----
        order_stats = {"total": len(all_orders), "pending": 0, "completed": 0}
        for o in all_orders:
            if o.get("status") == "pending":
                order_stats["pending"] += 1
            elif o.get("status") == "completed":
                order_stats["completed"] += 1

        # ---- 6) I DAG (live) ----
        def _is_haster(t):
            return (str(t.get("priority") or "").lower() in ("urgent", "haster")
                    or "haster" in (t.get("remark") or "").lower())
        todays = [t for t in all_tours if t.get("date") == today_str]
        today_block = {
            "date": today_str,
            "total": len(todays),
            "completed": sum(1 for t in todays if t.get("completed")),
            "on_way": sum(1 for t in todays if t.get("on_way") and not t.get("completed")),
            "unassigned": sum(1 for t in todays if not t.get("completed") and not t.get("on_way")
                              and not t.get("driver_id") and not t.get("claimed_by")),
            "haster_open": sum(1 for t in todays if _is_haster(t) and not t.get("completed")),
            "weight": round(sum((t.get("weight") or 0) for t in todays if t.get("completed")), 1),
            "overdue": sum(1 for t in all_tours if (t.get("date") or "") < today_str and not t.get("completed")
                           and (t.get("date") or "") >= (today - timedelta(days=14)).strftime("%Y-%m-%d")),
        }

        return {
            "generated_at": datetime.now(DK_TZ).isoformat(),
            "today": today_block,
            "period_months": months,
            "jobs_per_day": jobs_per_day_list,
            "driver_performance": driver_stats_list,
            "material_usage": material_list[:20],
            "plads_stats": plads_list,
            "order_stats": order_stats,
            "summary": {
                "total_tours": len(all_tours),
                "completed_tours": len([t for t in all_tours if t.get("completed")]),
                "total_weight": round(sum((t.get("weight") or 0) for t in all_tours if t.get("completed")), 1),
                "total_drivers": len(drivers),
                "active_drivers": len([d for d in driver_stats_list if d["work_days"] > 0]),
            }
        }
    except Exception as e:
        logger.error(f"Error in admin statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")

@api_router.get("/materials")
async def get_materials():
    """Get the default materials list."""
    return {"materials": DEFAULT_MATERIALS}

# ============= PLADS MANAGEMENT =============

@api_router.get("/plads")
async def get_plads(payload: Optional[dict] = Depends(get_optional_user_payload)):
    # For driver callers we need to bypass the default tenant filter (which
    # restricts to their own logistics company) and instead match plads where
    # either the company is theirs OR the plads has explicitly assigned their
    # company as a logistics partner. We do this against `_raw_db` and apply the
    # active+company logic by hand.
    if payload and payload.get("role") == "driver":
        user_doc = await _raw_db.users.find_one(
            {"id": payload.get("sub")},
            {"_id": 0, "visible_plads_ids": 1, "company_id": 1, "active_customer_id": 1},
        ) or {}
        drv_company = user_doc.get("company_id")
        active_cid = user_doc.get("active_customer_id")
        # Fase 5: STRICT — driver må kun se pladser fra den aktive kunde.
        # Indtil active customer er sat returneres tom liste.
        if not active_cid:
            return []
        if not await _driver_serves_customer(payload, active_cid):
            await _raw_db.users.update_one(
                {"id": payload.get("sub")},
                {"$unset": {"active_customer_id": ""}},
            )
            return []
        q = {
            "active": True,
            "company_id": active_cid,
            "assigned_logistics_company_ids": drv_company,
        }
        plads_list = await _raw_db.plads.find(q, {"_id": 0}).to_list(500)
        # Optional per-driver whitelist (visible_plads_ids) further restricts
        allowed_ids = set(user_doc.get("visible_plads_ids") or [])
        if allowed_ids:
            plads_list = [p for p in plads_list if p.get("id") in allowed_ids]
    elif payload and payload.get("role") == "logistics_admin":
        # Fase 3 (2026-06-16): Logistics-admins skal AUTOMATISK se pladser
        # som tilhører de kunder de betjener (assigned_logistics_company_ids
        # indeholder deres company_id). De skal IKKE oprette plads manuelt —
        # plads strømmer ind fra customer-admin's /api/org/locations.
        la_company = payload.get("company_id")
        q = {
            "active": True,
            "$or": [
                {"company_id": la_company},
                {"assigned_logistics_company_ids": la_company},
            ],
        }
        plads_list = await _raw_db.plads.find(q, {"_id": 0}).to_list(500)
    else:
        plads_list = await db.plads.find({"active": True}, {"_id": 0}).to_list(500)
        # Brugerkrav 2026-06-15 (runde 9): For `order`-medarbejdere skal listen
        # KUN indeholde pladser de eksplicit er tildelt (assigned_plads_ids +
        # location_code). Det forhindrer at en medarbejder for kunde X kan se
        # andre pladser i samme firma de ikke har adgang til.
        if payload and payload.get("role") == "order":
            user_doc = await _raw_db.users.find_one(
                {"id": payload.get("sub")},
                {"_id": 0, "assigned_plads_ids": 1, "location_code": 1},
            ) or {}
            allowed = set(user_doc.get("assigned_plads_ids") or [])
            primary = user_doc.get("location_code") or ""
            if primary:
                allowed.add(primary)
            if allowed:
                plads_list = [
                    p for p in plads_list
                    if (p.get("location_code") or "") in allowed
                ]
            else:
                plads_list = []
    # Enrich every plads with an effective_location_code:
    #   - the plads' own location_code, if set;
    #   - otherwise the company's first active location code (fallback).
    # This makes ALL plads orderable from the Bestil Afhentning picker.
    # ALSO enrich with `customer_name` + `customer_code` so multi-customer
    # logistics admins and drivers can visually group/filter plads by kunde
    # (e.g. ARGO vs Helsingør Forsyning under the same logistics company).
    company_fallback = {}  # company_id -> first plads location code
    cust_ids = {p.get("company_id") for p in plads_list if p.get("company_id")}
    cust_map = {}
    if cust_ids:
        async for c in _raw_db.companies.find(
            {"id": {"$in": list(cust_ids)}},
            {"_id": 0, "id": 1, "name": 1, "customer_id": 1},
        ):
            cust_map[c["id"]] = {"name": c.get("name", ""), "customer_id": c.get("customer_id") or ""}
    for p in plads_list:
        cid = p.get("company_id") or DEFAULT_COMPANY_ID
        if cid not in company_fallback:
            loc = await _raw_db.plads.find_one(
                {"company_id": cid, "active": True,
                 "location_code": {"$exists": True, "$ne": ""}},
                {"_id": 0, "location_code": 1},
            )
            company_fallback[cid] = loc.get("location_code") if loc else None
        p["effective_location_code"] = p.get("location_code") or company_fallback[cid]
        # Customer attribution
        info = cust_map.get(cid, {})
        p["customer_name"] = info.get("name", "")
        p["customer_code"] = info.get("customer_id", "")
        # how many sub-addresses this plads has — frontend uses this to decide
        # whether to show the address-picker step
        p["address_count"] = await db.plads_addresses.count_documents({"plads_id": p["id"]})
    return plads_list

# ----- Egne lokationer for premium logistikfirmaer (2026-10-16) -------------
async def _location_name_taken(name: str, exclude_id: str = "") -> bool:
    # Ture peger på pladser via NAVN, så navne skal være entydige på tværs af
    # kunder og logistikfirmaer - ellers kan en tur havne på forkert plads.
    q: Dict[str, Any] = {"name": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return bool(await _raw_db.plads.find_one(q, {"_id": 0, "id": 1}))


async def _geocode_dk(query: str) -> dict:
    """2026-10-17: Adresse -> GPS. Google Maps er slået fra, så vi bruger
    OpenStreetMap (Nominatim, gratis, kun Danmark) og falder tilbage til den
    indbyggede postnummer-tabel (groft: byens midte). Resultater caches."""
    q = (query or "").strip()
    if len(q) < 3:
        return {}
    key = q.lower()
    hit = await _raw_db.geocode_cache.find_one({"q": key}, {"_id": 0})
    if hit:
        return {k: hit.get(k) for k in ("lat", "lng", "source", "label")}

    def _osm():
        try:
            r = http_requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "dk"},
                headers={"User-Agent": "ContainerFlow/1.0 (containerflow.dk)"}, timeout=6)
            js = r.json() if r.ok else []
            if js:
                return {"lat": float(js[0]["lat"]), "lng": float(js[0]["lon"]), "source": "osm",
                        "label": js[0].get("display_name", "")[:200]}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"geocode osm failed: {e}")
        return {}
    res = await async_lib.to_thread(_osm)
    if not res:
        lat, lng = geocode_address(q)
        if lat and lng:
            res = {"lat": lat, "lng": lng, "source": "postnr", "label": "Omtrentlig (postnummer/by)"}
    if res:
        await _raw_db.geocode_cache.update_one({"q": key}, {"$set": {"q": key, **res}}, upsert=True)
    return res


@api_router.get("/geocode")
async def api_geocode(q: str, payload: dict = Depends(get_current_user_payload)):
    if payload.get("role") not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    res = await _geocode_dk(q)
    if not res:
        raise HTTPException(status_code=404, detail="Adressen kunne ikke findes - tjek stavning eller skriv postnummer med")
    return res


async def _create_own_location(la: str, plads: "PladsCreate") -> "Plads":
    name = (plads.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    if await _location_name_taken(name):
        raise HTTPException(status_code=409, detail="Navnet bruges allerede af en anden lokation - tilføj fx by eller vejnavn")
    code = ""
    for _ in range(50):
        cand = _gen_location_code_sync()
        if not await _raw_db.plads.find_one({"location_code": cand}, {"_id": 0, "id": 1}):
            code = cand
            break
    lat, lng = plads.lat, plads.lng
    if (lat is None or lng is None) and ((plads.address or "").strip() or (plads.city or "").strip()):
        g = await _geocode_dk(", ".join(x for x in [(plads.address or "").strip(), (plads.city or "").strip()] if x))
        lat, lng = g.get("lat"), g.get("lng")
    obj = Plads(name=name, city=(plads.city or "").strip(), address=(plads.address or "").strip(),
                lat=lat, lng=lng, location_code=code)
    doc = obj.model_dump()
    doc.update({"code": code, "company_id": la, "assigned_logistics_company_ids": [la],
                "own_location": True})
    await _raw_db.plads.insert_one(doc)
    return obj


async def _update_own_location(la: str, plads_id: str, update: "PladsUpdate") -> "Plads":
    cur = await _raw_db.plads.find_one({"id": plads_id, "company_id": la or "__none__"}, {"_id": 0})
    if not cur:
        raise HTTPException(
            status_code=405,
            detail="Plads-felter administreres af kunde-admin via deres lokations-side.",
        )
    data = {k: v for k, v in update.model_dump().items() if v is not None and k != "location_code"}
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise HTTPException(status_code=400, detail="Navn er påkrævet")
        if await _location_name_taken(data["name"], exclude_id=plads_id):
            raise HTTPException(status_code=409, detail="Navnet bruges allerede af en anden lokation")
    if not data:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    if ("address" in data or "city" in data) and ("lat" not in data or "lng" not in data):
        addr = data.get("address", cur.get("address") or "")
        city = data.get("city", cur.get("city") or "")
        if addr != (cur.get("address") or "") or city != (cur.get("city") or "") or not cur.get("lat"):
            g = await _geocode_dk(", ".join(x for x in [addr.strip(), city.strip()] if x))
            if g:
                data["lat"], data["lng"] = g["lat"], g["lng"]
    await _raw_db.plads.update_one({"id": plads_id}, {"$set": data})
    if data.get("name") and data["name"] != cur.get("name"):
        # Egne ture peger på lokationen via navn - flyt dem med.
        await _raw_db.tours.update_many({"company_id": la, "plads": cur.get("name")},
                                        {"$set": {"plads": data["name"]}})
    return Plads(**(await _raw_db.plads.find_one({"id": plads_id}, {"_id": 0})))


@api_router.post("/plads", response_model=Plads)
async def create_plads(plads: PladsCreate, payload: dict = Depends(get_current_user_payload)):
    # Fase 3 (2026-06-16): Logistik-admins må IKKE oprette plads manuelt.
    # Pladser strømmer automatisk ind fra kunde-admin via /api/org/locations.
    # Super_admin er undtaget for migrations-/library-scenarier.
    role = payload.get("role")
    if role == "logistics_admin":
        # 2026-10-16: Premium logistikfirmaer har deres egne lokationer
        # (depoter, faste kunder, byggepladser ...). Partnere får stadig
        # pladserne fra deres genbrugsplads-kunder.
        la = payload.get("company_id") or ""
        if (await _logistics_profile(la)).get("tier") != "premium":
            raise HTTPException(
                status_code=405,
                detail="Pladser oprettes af kunde-admin via deres lokationer. "
                       "Når kunden tildeler dit logistik-firma som partner, vises pladserne automatisk her.",
            )
        return await _create_own_location(la, plads)
    if role not in ("super_admin", "customer_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")

    # Check if plads already exists (in same company)
    existing = await _raw_db.plads.find_one({
        "name": plads.name,
        "company_id": payload.get("company_id"),
    })
    if existing:
        raise HTTPException(status_code=400, detail="Plads findes allerede")

    plads_obj = Plads(**plads.model_dump())
    doc = plads_obj.model_dump()
    doc["company_id"] = payload.get("company_id")
    await _raw_db.plads.insert_one(doc)
    return plads_obj

@api_router.delete("/plads/{plads_id}")
async def delete_plads(plads_id: str, payload: dict = Depends(get_current_user_payload)):
    # Fase 3 (2026-06-16): logistics_admin må ikke slette kunders plads.
    # 2026-10-16: Egne lokationer (premium) må gerne deaktiveres.
    if payload.get("role") == "logistics_admin":
        own = await _raw_db.plads.find_one(
            {"id": plads_id, "company_id": payload.get("company_id") or "__none__"}, {"_id": 0, "id": 1})
        if not own:
            raise HTTPException(
                status_code=405,
                detail="Kun kunde-admin må deaktivere pladser (via deres lokations-side).",
            )
        await _raw_db.plads.update_one({"id": plads_id}, {"$set": {"active": False}})
        return {"message": "Lokation deaktiveret"}
    result = await db.plads.update_one(
        {"id": plads_id},
        {"$set": {"active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plads not found")
    return {"message": "Plads deleted"}

@api_router.put("/plads/{plads_id}", response_model=Plads)
async def update_plads(plads_id: str, update: PladsUpdate, payload: dict = Depends(get_current_user_payload)):
    # Fase 3 (2026-06-16): logistics_admin må ikke ændre kunders plads-felter.
    # 2026-10-16: ... men gerne deres egne lokationer (premium).
    if payload.get("role") == "logistics_admin":
        return await _update_own_location(payload.get("company_id") or "", plads_id, update)
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Check duplicate name
    if "name" in update_data:
        existing = await db.plads.find_one({"name": update_data["name"], "id": {"$ne": plads_id}})
        if existing:
            raise HTTPException(status_code=400, detail="Plads with this name already exists")
    result = await db.plads.update_one({"id": plads_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plads not found")
    updated = await db.plads.find_one({"id": plads_id}, {"_id": 0})
    return Plads(**updated)

# ============= ROUTE OPTIMIZATION =============

import math
import re
import requests as http_requests

# Google Maps API
GOOGLE_MAPS_API_KEY = ""  # DISABLED - Google Maps API removed

# Fallback constants (when Google Maps unavailable)
ROAD_FACTOR = 1.3
CITY_SPEED_MIN_PER_KM = 3.0
HIGHWAY_SPEED_MIN_PER_KM = 1.5

# HÆNGER rules
MAX_HAENGER_SIZE = 2  # Max 2 containers per HÆNGER (trailer limit)
SOLO_MAX_MINUTES = 15  # Tours within ~15 min alone = SOLO

# Danish postal code → approximate center coordinates (fallback geocoding)
DK_POSTNR = {
    "1000": (55.6761, 12.5683), "1050": (55.6761, 12.5683), "1100": (55.6761, 12.5683),
    "1200": (55.6761, 12.5683), "1300": (55.6761, 12.5683), "1400": (55.6761, 12.5683),
    "1500": (55.6761, 12.5683), "1600": (55.6761, 12.5683), "1700": (55.6761, 12.5683),
    "1800": (55.6761, 12.5683), "1900": (55.6761, 12.5683),
    "2000": (55.6333, 12.5167), "2100": (55.7000, 12.5833), "2200": (55.7100, 12.5500),
    "2300": (55.6537, 12.5986), "2400": (55.7300, 12.5000), "2450": (55.7254, 12.4967),
    "2500": (55.6833, 12.4500), "2600": (55.6531, 12.3978), "2605": (55.6450, 12.3600),
    "2610": (55.6833, 12.4500), "2620": (55.6667, 12.5333), "2625": (55.6750, 12.4917),
    "2630": (55.6167, 12.3500), "2635": (55.6250, 12.3700), "2640": (55.6333, 12.3500),
    "2650": (55.6167, 12.4333), "2660": (55.6250, 12.3833), "2665": (55.5833, 12.3167),
    "2670": (55.6333, 12.4833), "2680": (55.5833, 12.3667), "2690": (55.5667, 12.3333),
    "2700": (55.6833, 12.5333), "2720": (55.6833, 12.5167), "2730": (55.7245, 12.4386),
    "2740": (55.6000, 12.5333), "2750": (55.7312, 12.3605), "2760": (55.7333, 12.3667),
    "2765": (55.7500, 12.3500), "2770": (55.7333, 12.4000), "2791": (55.7500, 12.4500),
    "2800": (55.7667, 12.5000), "2820": (55.7833, 12.4500), "2830": (55.8000, 12.4500),
    "2840": (55.7333, 12.5167), "2850": (55.8167, 12.4500), "2860": (55.7500, 12.5167),
    "2870": (55.8000, 12.5333), "2880": (55.8000, 12.5667), "2900": (55.7667, 12.5833),
    "2920": (55.7333, 12.5500), "2930": (55.7833, 12.5667), "2942": (55.6833, 12.3000),
    "2950": (55.7500, 12.5333), "2960": (55.8333, 12.4500), "2970": (55.8167, 12.4833),
    "2980": (55.7500, 12.3333), "2990": (55.7000, 12.2667),
    "3000": (55.8400, 12.4067), "3050": (55.9000, 12.4500), "3060": (55.8500, 12.3500),
    "3070": (55.8500, 12.3000), "3080": (55.9333, 12.3333), "3100": (55.9333, 12.5333),
    "3120": (55.9500, 12.5500), "3140": (56.0742, 12.5641), "3150": (55.8833, 12.5000),
    "3200": (55.8500, 12.3667), "3230": (55.8667, 12.3333), "3250": (55.9667, 12.2000),
    "3300": (55.9500, 12.2000), "3310": (55.9833, 12.3000), "3320": (55.9667, 12.3167),
    "3330": (55.9500, 12.3333), "3360": (55.9333, 12.0333), "3400": (55.9263, 12.3008),
    "3450": (55.9833, 12.1500), "3460": (55.8167, 12.2000), "3480": (55.8500, 12.2000),
    "3500": (55.9000, 12.0667), "3520": (55.8333, 12.0833), "3540": (55.8500, 12.1667),
    "3550": (55.7833, 12.1833), "3600": (55.6333, 11.7333), "3630": (55.5833, 11.9167),
    "3650": (55.5333, 11.8833), "3660": (55.7667, 12.2000), "3670": (55.8333, 12.1333),
    "4000": (55.4667, 11.8000), "4200": (55.4500, 11.7833), "4600": (55.3333, 11.5500),
    "5000": (55.3833, 10.3833), "6000": (55.5000, 9.4667), "7000": (55.8667, 9.8000),
    "8000": (56.1333, 10.2000), "9000": (57.0333, 9.9167),
}

# City-name → (lat, lng) fallback for plads/order addresses that lack a postnr.
# Keys are normalized (lowercase, stripped). Covers the most common locations
# served by ContainerFlow customer companies (Vestforbrænding, FORSYNING etc).
DK_CITIES = {
    "københavn": (55.6761, 12.5683),
    "frederiksberg": (55.6786, 12.5345),
    "valby": (55.6650, 12.5097),
    "rødovre": (55.6800, 12.4533),
    "hvidovre": (55.6531, 12.3978),
    "glostrup": (55.6667, 12.4000),
    "albertslund": (55.6580, 12.3540),
    "brøndby": (55.6450, 12.3600),
    "brondby": (55.6450, 12.3600),
    "vallensbæk": (55.6250, 12.3700),
    "vallensbaek": (55.6250, 12.3700),
    "ishøj": (55.6167, 12.3500),
    "ishoj": (55.6167, 12.3500),
    "greve": (55.5833, 12.3167),
    "solrød": (55.5333, 12.1900),
    "solrod": (55.5333, 12.1900),
    "skovlunde": (55.7245, 12.4386),
    "tåstrup": (55.6500, 12.3000),
    "taastrup": (55.6500, 12.3000),
    "ballerup": (55.7312, 12.3605),
    "herlev": (55.7333, 12.4500),
    "gladsaxe": (55.7333, 12.4833),
    "lyngby": (55.7700, 12.5050),
    "helsingør": (56.0365, 12.6130),
    "helsingor": (56.0365, 12.6130),
    "fredensborg": (55.9667, 12.4167),
    "hillerød": (55.9263, 12.3008),
    "hillerod": (55.9263, 12.3008),
    "hørsholm": (55.8833, 12.5000),
    "horsholm": (55.8833, 12.5000),
    "ålsgårde": (56.0742, 12.5641),
    "alsgarde": (56.0742, 12.5641),
    "humlebæk": (55.9667, 12.5333),
    "espergærde": (56.0333, 12.5500),
    "snekkersten": (56.0167, 12.5833),
    "kvistgård": (56.0333, 12.5167),
    "tikøb": (56.0500, 12.4167),
    "bjæverskov": (55.4700, 12.0500),
    "bjaeverskov": (55.4700, 12.0500),
    "roskilde": (55.6415, 12.0803),
    "køge": (55.4570, 12.1817),
    "koge": (55.4570, 12.1817),
}

def geocode_address(address: str) -> tuple:
    """Geocode address using Google Maps API, fallback to postal code lookup."""
    if not address:
        return None, None
    
    # Try Google Maps Geocoding first
    if GOOGLE_MAPS_API_KEY:
        try:
            resp = http_requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": f"{address}, Denmark", "key": GOOGLE_MAPS_API_KEY},
                timeout=5
            )
            data = resp.json()
            if data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return loc["lat"], loc["lng"]
        except Exception:
            pass
    
    # Fallback 1: postal code lookup
    match = re.search(r'\b(\d{4})\b', address)
    if match:
        postnr = match.group(1)
        if postnr in DK_POSTNR:
            return DK_POSTNR[postnr]

    # Fallback 2: city-name lookup (works when address has only a city, no postnr)
    norm = address.lower().strip()
    if norm in DK_CITIES:
        return DK_CITIES[norm]
    for city, coords in DK_CITIES.items():
        if city in norm:
            return coords
    return None, None

def haversine_km(lat1, lng1, lat2, lng2):
    """Calculate distance in km between two lat/lng points using Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def google_distance_matrix(origins: list, destinations: list) -> dict:
    """Call Google Maps Distance Matrix API. Returns {(i,j): {distance_m, duration_s}}."""
    results = {}
    if not GOOGLE_MAPS_API_KEY or not origins or not destinations:
        return results
    
    try:
        origin_strs = [f"{lat},{lng}" for lat, lng in origins]
        dest_strs = [f"{lat},{lng}" for lat, lng in destinations]
        
        resp = http_requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": "|".join(origin_strs),
                "destinations": "|".join(dest_strs),
                "mode": "driving",
                "key": GOOGLE_MAPS_API_KEY
            },
            timeout=10
        )
        data = resp.json()
        
        if data.get("status") == "OK":
            for i, row in enumerate(data.get("rows", [])):
                for j, el in enumerate(row.get("elements", [])):
                    if el.get("status") == "OK":
                        results[(i, j)] = {
                            "distance_m": el["distance"]["value"],
                            "duration_s": el["duration"]["value"],
                            "distance_km": round(el["distance"]["value"] / 1000, 1),
                            "duration_min": round(el["duration"]["value"] / 60)
                        }
    except Exception as e:
        logger.warning(f"Google Distance Matrix error: {e}")
    
    return results

def road_distance_km(lat1, lng1, lat2, lng2):
    """Estimated road distance = haversine × road factor (fallback)."""
    return round(haversine_km(lat1, lng1, lat2, lng2) * ROAD_FACTOR, 1)

def estimate_travel_minutes(distance_km):
    """Estimate travel time based on distance (fallback when no Google Maps)."""
    if distance_km <= 0:
        return 0
    if distance_km <= 10:
        return round(distance_km * CITY_SPEED_MIN_PER_KM)
    return round(10 * CITY_SPEED_MIN_PER_KM + (distance_km - 10) * HIGHWAY_SPEED_MIN_PER_KM)

def detect_haenger_groups_google(tour_infos, dm_results):
    """Detect HÆNGER groups using real Google Maps driving data.
    Rules:
    - Max 2 containers per HÆNGER group (trailer limit)
    - Tours on the same route (detour < 5 min from direct) = HÆNGER candidates
    - Tours within ~15 min of each other and on the way = HÆNGER
    - Cross/off-route tours = SOLO
    """
    groups = {}
    tour_group_map = {}
    group_counter = 0
    n = len(tour_infos)
    
    # Build inter-tour distance/time matrix
    inter_tour = {}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            key = (i + 1, j)  # offset +1 because origin[0] is plads
            if key in dm_results:
                inter_tour[(i, j)] = dm_results[key]
    
    # Find HÆNGER pairs: tours close to each other on the road
    used = set()
    candidates = []
    
    for i in range(n):
        for j in range(i + 1, n):
            ij_data = inter_tour.get((i, j))
            ji_data = inter_tour.get((j, i))
            
            if not ij_data or not ji_data:
                continue
            
            drive_min = min(ij_data["duration_min"], ji_data["duration_min"])
            drive_km = min(ij_data["distance_km"], ji_data["distance_km"])
            
            # HÆNGER if drive between them is short (within ~15 min)
            if drive_min <= SOLO_MAX_MINUTES:
                # Check if it's "on the way" by comparing:
                # plads→A + A→B vs plads→B directly
                plads_to_a = dm_results.get((0, i))
                plads_to_b = dm_results.get((0, j))
                
                if plads_to_a and plads_to_b:
                    direct_a_min = plads_to_a["duration_min"]
                    direct_b_min = plads_to_b["duration_min"]
                    
                    # Route A then B: plads→A→B
                    via_a_then_b = direct_a_min + ij_data["duration_min"]
                    # Route B then A: plads→B→A 
                    via_b_then_a = direct_b_min + ji_data["duration_min"]
                    
                    # Detour penalty: how much extra time vs going directly
                    best_via = min(via_a_then_b, via_b_then_a)
                    direct_max = max(direct_a_min, direct_b_min)
                    
                    # If detour is reasonable (< 10 min extra), they're on the route
                    detour_min = best_via - direct_max
                    
                    if detour_min <= 10:
                        candidates.append((i, j, drive_min, drive_km, detour_min))
    
    # Sort candidates by detour time (best pairs first)
    candidates.sort(key=lambda x: x[4])
    
    # Assign HÆNGER groups (max 2 per group)
    for i, j, drive_min, drive_km, detour_min in candidates:
        ti_id = tour_infos[i]["tour_id"]
        tj_id = tour_infos[j]["tour_id"]
        
        if ti_id in used or tj_id in used:
            continue
        
        group_counter += 1
        gid = f"G{group_counter}"
        groups[gid] = [ti_id, tj_id]
        tour_group_map[ti_id] = gid
        tour_group_map[tj_id] = gid
        used.add(ti_id)
        used.add(tj_id)
    
    return groups, tour_group_map

def detect_haenger_groups_fallback(tours_with_info):
    """Fallback HÆNGER detection using address matching + Haversine (when Google Maps unavailable).
    Max 2 per group."""
    groups = {}
    tour_group_map = {}
    group_counter = 0
    used = set()
    
    indexed = list(tours_with_info)
    candidates = []
    
    for i, t1 in enumerate(indexed):
        for j, t2 in enumerate(indexed):
            if j <= i:
                continue
            
            # Same address = always HÆNGER (no coordinates needed)
            if (t1.get("address") and t2.get("address") and 
                t1["address"].strip().lower() == t2["address"].strip().lower()):
                candidates.append((i, j, 0))
                continue
            
            # Distance-based matching requires coordinates
            if not t1.get("has_coordinates") or not t2.get("has_coordinates"):
                continue
            
            dist = haversine_km(t1["lat"], t1["lng"], t2["lat"], t2["lng"]) * ROAD_FACTOR
            est_min = estimate_travel_minutes(dist)
            if est_min <= SOLO_MAX_MINUTES:
                candidates.append((i, j, est_min))
    
    candidates.sort(key=lambda x: x[2])
    
    for i, j, _ in candidates:
        ti_id = indexed[i]["tour_id"]
        tj_id = indexed[j]["tour_id"]
        
        if ti_id in used or tj_id in used:
            continue
        
        group_counter += 1
        gid = f"G{group_counter}"
        groups[gid] = [ti_id, tj_id]
        tour_group_map[ti_id] = gid
        tour_group_map[tj_id] = gid
        used.add(ti_id)
        used.add(tj_id)
    
    return groups, tour_group_map

class RouteOptimizeRequest(BaseModel):
    plads_name: str
    tour_ids: List[str] = []

@api_router.post("/optimize-route")
async def optimize_route(request: RouteOptimizeRequest):
    """Smart route optimization with Google Maps Distance Matrix.
    HÆNGER = max 2 containers, on the same route.
    SOLO = alone, cross-route, or far away."""
    try:
        # Try exact match first; if not found, try case-insensitive
        plads = await db.plads.find_one({"name": request.plads_name, "active": True}, {"_id": 0})
        if not plads:
            plads = await db.plads.find_one(
                {"name": {"$regex": f"^{re.escape(request.plads_name)}$", "$options": "i"}, "active": True},
                {"_id": 0},
            )
        if not plads:
            return {"optimized": False, "reason": "Pladsen blev ikke fundet", "tours": []}

        # Auto-geocode the plads if coordinates are missing — many Vestforbrænding
        # pladser were created without GPS data. Use the plads's own address/city
        # (or the name as a fallback) and cache the result back on the doc so the
        # next run is instant.
        if not plads.get("lat") or not plads.get("lng"):
            geo_query = (
                plads.get("address")
                or f"{plads.get('name', '')} {plads.get('city', '')}".strip()
                or plads.get("name", "")
            )
            geo_lat, geo_lng = geocode_address(geo_query) if geo_query else (None, None)
            if geo_lat and geo_lng:
                plads["lat"] = geo_lat
                plads["lng"] = geo_lng
                try:
                    await db.plads.update_one(
                        {"id": plads["id"]},
                        {"$set": {"lat": geo_lat, "lng": geo_lng}},
                    )
                except Exception as e:
                    logger.warning(f"Could not persist geocoded coords for plads {plads.get('name')}: {e}")
            else:
                return {
                    "optimized": False,
                    "reason": "Pladsen mangler GPS-koordinater (auto-geocoding mislykkedes)",
                    "tours": [],
                }

        start_lat = plads["lat"]
        start_lng = plads["lng"]

        if not request.tour_ids:
            return {"optimized": False, "reason": "Ingen ture at optimere", "tours": []}

        tours = []
        for tid in request.tour_ids:
            t = await db.tours.find_one({"id": tid}, {"_id": 0})
            if t and not t.get("is_pause"):
                tours.append(t)

        if not tours:
            return {"optimized": False, "reason": "Ingen ture fundet", "tours": []}
        
        # Geocode all tours
        tours_with_coords = []
        tours_without_coords = []
        geocode_log = []
        
        for t in tours:
            if t.get("lat") and t.get("lng"):
                tours_with_coords.append(t)
                geocode_log.append(f"{t['id'][:8]}: DB coords ({t['lat']}, {t['lng']})")
            else:
                geo_lat, geo_lng = geocode_address(t.get("address", ""))
                if geo_lat and geo_lng:
                    t["lat"] = geo_lat
                    t["lng"] = geo_lng
                    tours_with_coords.append(t)
                    geocode_log.append(f"{t['id'][:8]}: Geocoded '{t.get('address','')}' -> ({geo_lat}, {geo_lng})")
                else:
                    tours_without_coords.append(t)
                    geocode_log.append(f"{t['id'][:8]}: FAILED to geocode '{t.get('address','')}'")
        
        logger.info(f"Route geocoding: {len(tours_with_coords)} OK, {len(tours_without_coords)} failed. Log: {'; '.join(geocode_log)}")
        
        if not tours_with_coords and not tours_without_coords:
            return {"optimized": False, "reason": "No tours found", "tours": []}
        
        if not tours_with_coords:
            # No geocoded tours - still try address-based matching
            pass
        
        # Build tour info list with opening hours
        tour_infos = []
        for t in tours_with_coords:
            open_from = t.get("open_from", "")
            open_to = t.get("open_to", "")
            open_from_min = None
            open_to_min = None
            if open_from:
                try:
                    parts = open_from.replace(".", ":").split(":")
                    open_from_min = int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    pass
            if open_to:
                try:
                    parts = open_to.replace(".", ":").split(":")
                    open_to_min = int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    pass
            
            tour_infos.append({
                "tour_id": t["id"],
                "lat": t["lat"],
                "lng": t["lng"],
                "address": t.get("address", ""),
                "has_coordinates": True,
                "open_from": open_from,
                "open_to": open_to,
                "open_from_min": open_from_min,
                "open_to_min": open_to_min,
                "fraction": t.get("fraction", ""),
            })
        
        # Also include tours WITHOUT coordinates for address-based matching
        for t in tours_without_coords:
            open_from = t.get("open_from", "")
            open_to = t.get("open_to", "")
            open_from_min = None
            open_to_min = None
            if open_from:
                try:
                    parts = open_from.replace(".", ":").split(":")
                    open_from_min = int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    pass
            if open_to:
                try:
                    parts = open_to.replace(".", ":").split(":")
                    open_to_min = int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    pass
            
            tour_infos.append({
                "tour_id": t["id"],
                "lat": None,
                "lng": None,
                "address": t.get("address", ""),
                "has_coordinates": False,
                "open_from": open_from,
                "open_to": open_to,
                "open_from_min": open_from_min,
                "open_to_min": open_to_min,
                "fraction": t.get("fraction", ""),
            })
        
        # Call Google Maps Distance Matrix for all pairs
        use_google = bool(GOOGLE_MAPS_API_KEY)
        dm_results = {}
        
        if use_google:
            # Only include tours WITH coordinates for Google Maps API calls
            coord_infos = [ti for ti in tour_infos if ti.get("has_coordinates")]
            all_origins = [(start_lat, start_lng)] + [(ti["lat"], ti["lng"]) for ti in coord_infos]
            all_dests = [(ti["lat"], ti["lng"]) for ti in coord_infos]
            
            # Distance Matrix API has element limit per request
            # For N tours: (N+1) origins × N destinations
            # Split into chunks if needed
            n = len(tour_infos)
            if (n + 1) * n <= 100:  # Within single API call limit
                dm_results = google_distance_matrix(all_origins, all_dests)
            else:
                # Call in batches: plads to all tours first
                plads_origins = [(start_lat, start_lng)]
                dm_batch1 = google_distance_matrix(plads_origins, all_dests)
                for key, val in dm_batch1.items():
                    dm_results[key] = val
                
                # Then inter-tour pairs in chunks - dynamic chunk size to stay under 100 elements
                chunk_size = max(1, 100 // max(n, 1))
                for ci in range(0, n, chunk_size):
                    chunk_origins = [(tour_infos[k]["lat"], tour_infos[k]["lng"]) for k in range(ci, min(ci + chunk_size, n))]
                    dm_batch = google_distance_matrix(chunk_origins, all_dests)
                    for (oi, di), val in dm_batch.items():
                        dm_results[(ci + oi + 1, di)] = val  # offset +1 for plads
        
        # Detect HÆNGER groups
        if use_google and dm_results:
            groups, tour_group_map = detect_haenger_groups_google(tour_infos, dm_results)
            logger.info(f"Route optimization: Google Maps used, {len(groups)} HÆNGER groups")
        else:
            groups, tour_group_map = detect_haenger_groups_fallback(tour_infos)
            logger.info(f"Route optimization: Haversine fallback, {len(groups)} HÆNGER groups")
        
        # Get distances from plads to each tour
        plads_distances = {}
        for i, ti in enumerate(tour_infos):
            if (0, i) in dm_results:
                plads_distances[ti["tour_id"]] = dm_results[(0, i)]
            elif ti.get("has_coordinates") and ti["lat"] and ti["lng"]:
                dist = road_distance_km(start_lat, start_lng, ti["lat"], ti["lng"])
                plads_distances[ti["tour_id"]] = {
                    "distance_km": dist,
                    "duration_min": estimate_travel_minutes(dist)
                }
            else:
                plads_distances[ti["tour_id"]] = {
                    "distance_km": 0,
                    "duration_min": 0
                }
        
        # Smart sorting: HÆNGER groups first, then by opening hours and nearest-neighbor
        ordered = []
        visited = set()
        current_lat, current_lng = start_lat, start_lng
        
        # Separate HÆNGER groups and SOLO tours
        haenger_tour_ids = set()
        for gid, members in groups.items():
            for mid in members:
                haenger_tour_ids.add(mid)
        
        haenger_tours = [ti for ti in tour_infos if ti["tour_id"] in haenger_tour_ids]
        solo_tours = [ti for ti in tour_infos if ti["tour_id"] not in haenger_tour_ids]
        
        # Sort HÆNGER groups by earliest opening time (or closest if no hours)
        group_order = []
        for gid, members in groups.items():
            group_tours_info = [ti for ti in tour_infos if ti["tour_id"] in members]
            # Get earliest open time in group
            min_open = None
            min_close = None
            for gti in group_tours_info:
                if gti["open_from_min"] is not None:
                    if min_open is None or gti["open_from_min"] < min_open:
                        min_open = gti["open_from_min"]
                if gti["open_to_min"] is not None:
                    if min_close is None or gti["open_to_min"] < min_close:
                        min_close = gti["open_to_min"]
            
            # Get average distance from plads
            avg_dist = 0
            for gti in group_tours_info:
                key = None
                for idx, ti in enumerate(tour_infos):
                    if ti["tour_id"] == gti["tour_id"]:
                        key = (0, idx)
                        break
                if key and key in dm_results:
                    avg_dist += dm_results[key].get("duration_min", 999)
                elif gti.get("has_coordinates") and gti["lat"] and gti["lng"]:
                    avg_dist += haversine_km(start_lat, start_lng, gti["lat"], gti["lng"]) * ROAD_FACTOR * CITY_SPEED_MIN_PER_KM
                else:
                    avg_dist += 0  # No coordinates - can't estimate distance
            avg_dist = avg_dist / max(len(group_tours_info), 1)
            
            group_order.append({
                "gid": gid,
                "tours": group_tours_info,
                "min_open": min_open if min_open is not None else 999,
                "min_close": min_close if min_close is not None else 999,
                "avg_travel": avg_dist
            })
        
        # Sort groups: earliest closing first (urgent), then earliest opening, then nearest
        group_order.sort(key=lambda g: (g["min_close"], g["min_open"], g["avg_travel"]))
        
        # Add HÆNGER groups first (ordered)
        for g in group_order:
            for gt in g["tours"]:
                if gt["tour_id"] not in visited:
                    ordered.append(gt)
                    visited.add(gt["tour_id"])
                    if gt.get("has_coordinates") and gt["lat"] and gt["lng"]:
                        current_lat, current_lng = gt["lat"], gt["lng"]
        
        # Then SOLO tours: by opening hours then nearest-neighbor
        # Sort SOLO by: earliest closing first, then earliest opening, then nearest
        solo_with_priority = []
        for st in solo_tours:
            if st["tour_id"] in visited:
                continue
            travel = 999
            for idx, ti in enumerate(tour_infos):
                if ti["tour_id"] == st["tour_id"]:
                    key = (0, idx)
                    if key in dm_results:
                        travel = dm_results[key].get("duration_min", 999)
                    elif st.get("has_coordinates") and st["lat"] and st["lng"]:
                        travel = haversine_km(start_lat, start_lng, st["lat"], st["lng"]) * ROAD_FACTOR * CITY_SPEED_MIN_PER_KM
                    else:
                        travel = 0
                    break
            solo_with_priority.append({
                **st,
                "close_priority": st["open_to_min"] if st["open_to_min"] is not None else 999,
                "open_priority": st["open_from_min"] if st["open_from_min"] is not None else 999,
                "travel_min": travel
            })
        
        solo_with_priority.sort(key=lambda s: (s["close_priority"], s["open_priority"], s["travel_min"]))
        
        for st in solo_with_priority:
            if st["tour_id"] not in visited:
                ordered.append(st)
                visited.add(st["tour_id"])
        
        # Build result
        result_tours = []
        total_distance = 0
        total_minutes = 0
        haenger_count = 0
        solo_count = 0
        
        prev_lat, prev_lng = start_lat, start_lng
        for i, t in enumerate(ordered):
            # Distance from plads
            pd = plads_distances.get(t["tour_id"], {})
            dist_from_plads = pd.get("distance_km", 0)
            
            # Leg distance from previous stop
            leg_data = None
            if use_google and dm_results:
                for idx, ti in enumerate(tour_infos):
                    if ti["tour_id"] == t["tour_id"]:
                        for prev_idx, pt in enumerate(tour_infos):
                            if abs(pt["lat"] - prev_lat) < 0.001 and abs(pt["lng"] - prev_lng) < 0.001:
                                key = (prev_idx + 1, idx)
                                if key in dm_results:
                                    leg_data = dm_results[key]
                                break
                        if not leg_data and (0, idx) in dm_results and i == 0:
                            leg_data = dm_results[(0, idx)]
                        break
            
            if leg_data:
                leg_dist = leg_data["distance_km"]
                est_min = leg_data["duration_min"]
            elif t.get("has_coordinates") and t["lat"] and t["lng"] and prev_lat and prev_lng:
                leg_dist = road_distance_km(prev_lat, prev_lng, t["lat"], t["lng"])
                est_min = estimate_travel_minutes(leg_dist)
            else:
                leg_dist = 0
                est_min = 0
            
            total_distance += leg_dist
            total_minutes += est_min
            
            gid = tour_group_map.get(t["tour_id"])
            group_size = len(groups[gid]) if gid else 1
            job_type = "HAENGER" if gid else "SOLO"
            
            if job_type == "HAENGER":
                haenger_count += 1
            else:
                solo_count += 1
            
            result_tours.append({
                "tour_id": t["tour_id"],
                "route_order": i + 1,
                "distance_km": dist_from_plads,
                "leg_distance_km": round(leg_dist, 1),
                "estimated_minutes": est_min,
                "job_type": job_type,
                "group_id": gid,
                "group_size": group_size,
                "has_coordinates": t.get("has_coordinates", False),
                "open_from": t.get("open_from", ""),
                "open_to": t.get("open_to", ""),
                "fraction": t.get("fraction", ""),
                "traek_nr": None  # Will be set below for HAENGER groups
            })
            if t.get("has_coordinates") and t["lat"] and t["lng"]:
                prev_lat, prev_lng = t["lat"], t["lng"]
        
        # Append tours that weren't included in tour_infos ordering
        visited_ids = set(t["tour_id"] for t in ordered)
        for t in tours_without_coords:
            if t["id"] in visited_ids:
                continue
            result_tours.append({
                "tour_id": t["id"],
                "route_order": len(result_tours) + 1,
                "distance_km": 0,
                "leg_distance_km": 0,
                "estimated_minutes": 0,
                "job_type": "SOLO",
                "group_id": None,
                "group_size": 1,
                "has_coordinates": False
            })
            solo_count += 1
        
        # Assign Træk numbers within HÆNGER groups
        group_traek_counter = {}
        for rt in result_tours:
            if rt["group_id"]:
                gid = rt["group_id"]
                if gid not in group_traek_counter:
                    group_traek_counter[gid] = 0
                group_traek_counter[gid] += 1
                rt["traek_nr"] = group_traek_counter[gid]
        
        return {
            "optimized": True,
            "start_plads": request.plads_name,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "total_tours": len(result_tours),
            "tours_with_coordinates": len(tours_with_coords),
            "total_distance_km": round(total_distance, 1),
            "total_estimated_minutes": total_minutes,
            "haenger_count": haenger_count,
            "solo_count": solo_count,
            "groups": {gid: members for gid, members in groups.items()},
            "tours": result_tours,
            "google_maps_used": use_google and bool(dm_results),
            "max_haenger_size": MAX_HAENGER_SIZE,
            "geocode_log": geocode_log
        }
    except Exception as e:
        logger.error(f"Route optimization error: {e}")
        return {"optimized": False, "reason": str(e), "tours": []}

# ============= SCHEDULE ENDPOINTS =============

@api_router.get("/schedule")
async def get_schedule(week_start: str):
    """Get schedule for a week starting from week_start date"""
    from datetime import timedelta
    
    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=6)
    
    schedules = await db.schedules.find({
        "date": {
            "$gte": week_start,
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    }, {"_id": 0}).to_list(500)
    
    return schedules

@api_router.post("/schedule")
async def create_schedule(schedule: ScheduleCreate):
    """Create or update a single schedule entry"""
    # Check if schedule already exists for this driver and date
    existing = await db.schedules.find_one({
        "driver_id": schedule.driver_id,
        "date": schedule.date
    }, {"_id": 0})
    
    if existing:
        # Update existing
        await db.schedules.update_one(
            {"id": existing["id"]},
            {"$set": {
                "plads": schedule.plads,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {**existing, "plads": schedule.plads}
    else:
        # Create new
        schedule_obj = Schedule(**schedule.model_dump())
        doc = schedule_obj.model_dump()
        await db.schedules.insert_one(doc)
        return schedule_obj

@api_router.post("/schedule/bulk")
async def create_bulk_schedule(data: ScheduleBulkCreate):
    """Create or update multiple schedule entries"""
    results = []
    for schedule in data.schedules:
        existing = await db.schedules.find_one({
            "driver_id": schedule.driver_id,
            "date": schedule.date
        }, {"_id": 0})
        
        if existing:
            await db.schedules.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "plads": schedule.plads,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            results.append({**existing, "plads": schedule.plads})
        else:
            schedule_obj = Schedule(**schedule.model_dump())
            doc = schedule_obj.model_dump()
            await db.schedules.insert_one(doc)
            results.append({k: v for k, v in doc.items() if k != "_id"})
    
    return {"message": f"Saved {len(results)} schedules", "count": len(results)}

@api_router.delete("/schedule")
async def clear_week_schedule(week_start: str):
    """Clear all schedules for a week"""
    from datetime import timedelta
    
    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=6)
    
    result = await db.schedules.delete_many({
        "date": {
            "$gte": week_start,
            "$lte": end_date.strftime("%Y-%m-%d")
        }
    })
    
    return {"message": f"Deleted {result.deleted_count} schedules"}

# ============= DRIVER SESSION ENDPOINTS =============

@api_router.get("/driver-session/{driver_name}")
async def get_driver_session(driver_name: str):
    session = await db.driver_sessions.find_one({"driver_name": driver_name}, {"_id": 0})
    if not session:
        return None
    return session

@api_router.post("/driver-session")
async def create_or_update_driver_session(session: DriverSessionCreate):
    existing = await db.driver_sessions.find_one({"driver_name": session.driver_name})
    
    if existing:
        # Update existing session
        update_data = {
            "vehicle_reg": session.vehicle_reg or existing.get("vehicle_reg", ""),
            "current_plads": session.current_plads or existing.get("current_plads", ""),
            "start_time": session.start_time or existing.get("start_time", ""),
            "report_date": session.report_date or existing.get("report_date", ""),
            "last_active": datetime.now(timezone.utc).isoformat()
        }
        await db.driver_sessions.update_one(
            {"driver_name": session.driver_name},
            {"$set": update_data}
        )
        updated = await db.driver_sessions.find_one({"driver_name": session.driver_name}, {"_id": 0})
        return updated
    else:
        # Create new session
        session_obj = DriverSession(**session.model_dump())
        await db.driver_sessions.insert_one(session_obj.model_dump())
        return session_obj.model_dump()

@api_router.put("/driver-session/{driver_name}")
async def update_driver_session(driver_name: str, update: DriverSessionUpdate):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["last_active"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.driver_sessions.update_one(
        {"driver_name": driver_name},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"ok": True}


# ─── Fase 12 (2026-06-18): Manuel tidsregistrering ────────────────────────
# Dag-niveau fallback for chauffører der har glemt at stemple ind/ud.
# Én post pr. (driver_id, date). Hvis en post findes for dagen, opdateres
# den; ellers oprettes en ny. Vises kun for ejer + admin.

class ManualTimeEntry(BaseModel):
    date: str
    start_time: str
    end_time: str
    reason: Optional[str] = ""
    # Fase 15.28 (2026-02-22): Admin opretter periode-baseret tidsregistrering
    # på vegne af en chauffør. Driver-only-kald har dette felt tomt; admin-kald
    # angiver chaufførens user-id.
    driver_id: Optional[str] = ""
    # Fase 15.30 (2026-02-22): "work" (arbejde) eller "pause". Default work for
    # bagudkompatibilitet — eksisterende kald uden feltet behandles som arbejde.
    slice_type: Optional[str] = "work"


def _compute_duration_minutes(start_time: str, end_time: str) -> int:
    """Beregn varighed i minutter mellem start og slut (begge "HH:MM").

    Fase 15.35 (2026-02-22): Returnerer -1 hvis slut < start (på samme
    dato). Tidligere wrappede vi til 24t-overnight, men det skjulte
    brugerfejl. Endpoints der bruger denne fkt. SKAL nu tjekke
    `if duration <= 0: raise 400` for at fange forkerte input.
    """
    try:
        sh, sm = [int(x) for x in start_time.split(":")[:2]]
        eh, em = [int(x) for x in end_time.split(":")[:2]]
        mins = (eh * 60 + em) - (sh * 60 + sm)
        if mins < 0:
            return -1  # eksplicit fejl-signal
        return mins
    except Exception:
        return 0


# Fase 18.1 (2026-02-28): Centraliseret summering af én dags
# driver_time_entries. Bruges af /driver-archive, /admin/statistics
# og fremtidig Excel-eksport, så alle steder viser SAMME tal.
#
# Logik (matcher brugerens mentale model):
#   - Første IND (work-slice med tidligste start_time) = dagens start.
#   - Sidste UD (work-slice med seneste end_time, eller "nu" hvis åbent
#     stempel der mangler UD) = dagens slut.
#   - work_min   = sum af work-slice varigheder (open slices tæller frem
#                  til "nu" hvis dagen er i dag, ellers springes over).
#   - pause_min  = sum af pause-slice varigheder.
#   - span_min   = (slut − start) i minutter — den fulde tilstedeværelse.
#   - gap_min    = span_min − work_min − pause_min — ikke-stemplede huller
#                  (chaufføren gik hjem og kom tilbage uden at stemple UD).
#   - work_slices/pause_slices: list af {start,end,duration,manual_type,id}
#     sorteret stigende efter start_time, klar til UI-pills.
#   - open: True hvis mindst én slice ikke har end_time.
def _summarize_day_entries(entries: list, *, today_str: str = "",
                           now_hhmm: str = "") -> dict:
    """Summér én dags driver_time_entries.

    `entries`: liste af raw driver_time_entries-docs for én chauffør & én
    dato. Soft-deleted entries (deleted=True) springes automatisk over.

    `today_str`/`now_hhmm`: kun udfyldes når den dato vi summerer er I
    DAG og åbne slices skal tælle frem til nu. Hvis tomme, betragtes
    åbne slices som varende 0 minutter (vi viser "åben" i UI'et men
    inflater ikke totalerne).
    """
    out = {
        "start": "",
        "end": "",
        "work_min": 0,
        "pause_min": 0,
        "span_min": 0,
        "gap_min": 0,
        "work_slices": [],
        "pause_slices": [],
        "open": False,
        "any": False,
    }
    if not entries:
        return out

    # Filtrér deleted fra og normaliser slice_type
    active = []
    for e in entries:
        if not e:
            continue
        if e.get("deleted"):
            continue
        st = (e.get("slice_type") or "work").lower()
        if st not in ("work", "pause"):
            st = "work"
        active.append({
            "id": e.get("id") or "",
            "start_time": (e.get("start_time") or "").strip(),
            "end_time": (e.get("end_time") or "").strip(),
            "duration_minutes": e.get("duration_minutes") or 0,
            "slice_type": st,
            "manual_type": (e.get("manual_type") or "").strip(),
            "reason": (e.get("reason") or "").strip(),
            "manual": bool(e.get("manual")),
        })
    if not active:
        return out

    out["any"] = True
    today_now = _time_to_min(now_hhmm) if (today_str and now_hhmm) else -1

    # Beregn varighed for hver slice (handle åbne)
    for s in active:
        s_min = _time_to_min(s["start_time"])
        e_min = _time_to_min(s["end_time"]) if s["end_time"] else -1
        if not s["end_time"]:
            out["open"] = True
            # Åbne slices tæller kun frem til "nu" hvis dagen ER i dag
            if today_now >= 0 and s_min >= 0 and today_now > s_min:
                s["_duration"] = today_now - s_min
                s["_effective_end"] = now_hhmm
            else:
                s["_duration"] = 0
                s["_effective_end"] = ""
        else:
            dur = e_min - s_min if (s_min >= 0 and e_min >= 0) else 0
            if dur < 0:
                dur = 0
            # Foretræk forberegnet duration_minutes hvis den findes (kan
            # være sat manuelt af admin), ellers HH:MM-diff.
            s["_duration"] = s["duration_minutes"] if s["duration_minutes"] else dur
            s["_effective_end"] = s["end_time"]

    # Sortér stigende efter start_time
    active.sort(key=lambda x: _time_to_min(x["start_time"]))

    works = [s for s in active if s["slice_type"] == "work"]
    pauses = [s for s in active if s["slice_type"] == "pause"]

    # Første IND = første work-slice start.
    # Hvis ingen work-slices (kun pauser), brug pause som fallback.
    first = works[0] if works else (pauses[0] if pauses else None)
    if first:
        out["start"] = first["start_time"]

    # Sidste UD = seneste effective_end blandt work-slices.
    # Hvis alle åbne og ingen "nu"-fallback, lad end stå tom (=> "åben").
    last_end = ""
    last_end_min = -1
    for s in works:
        ee = s.get("_effective_end") or ""
        em = _time_to_min(ee) if ee else -1
        if em > last_end_min:
            last_end_min = em
            last_end = ee
    out["end"] = last_end

    # Totaler
    out["work_min"] = sum(int(s["_duration"] or 0) for s in works)
    out["pause_min"] = sum(int(s["_duration"] or 0) for s in pauses)

    # Span = sidste UD − første IND
    first_min = _time_to_min(out["start"]) if out["start"] else -1
    if first_min >= 0 and last_end_min >= 0 and last_end_min > first_min:
        out["span_min"] = last_end_min - first_min
    else:
        out["span_min"] = 0

    # Gap = span − work − pause (ikke-stemplede mellemrum)
    gap = out["span_min"] - out["work_min"] - out["pause_min"]
    out["gap_min"] = gap if gap > 0 else 0

    # Strip interne felter inden vi returnerer slice-listerne til API.
    def _clean(s):
        return {
            "id": s["id"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "effective_end": s.get("_effective_end") or "",
            "duration_minutes": int(s.get("_duration") or 0),
            "slice_type": s["slice_type"],
            "manual_type": s["manual_type"],
            "reason": s["reason"],
            "manual": s["manual"],
            "open": not s["end_time"],
        }
    out["work_slices"] = [_clean(s) for s in works]
    out["pause_slices"] = [_clean(s) for s in pauses]
    return out


# Fase 15.35 (2026-02-22): En "missing clock" er en åben entry hvor datoen
# allerede ligger i fortiden (eller end_time mangler og >24t er gået siden
# start_time). Bruges som flag i admin's "alle registreringer"-tabel så
# admin hurtigt kan filtrere på chauffører der har glemt at stemple ud.
def _is_entry_missing_clock(entry: dict) -> bool:
    if not entry or entry.get("end_time"):
        return False
    date_str = entry.get("date", "")
    if not date_str:
        return False
    try:
        today_local = datetime.now(tz=_LOCAL_TZ).strftime("%Y-%m-%d")
        # Hvis datoen er FØR i dag → uoplukket → missing.
        # I dag → ikke missing (driver kan stadig være på arbejde).
        return date_str < today_local
    except Exception:
        return False


# Fase 15.36 (2026-02-22): Søndag aften påmindelse — beregner alle åbne
# (missing_clock) entries fra de seneste `days_back` dage, grupperer dem pr.
# chauffør og returnerer liste klar til at sende email til.
async def _compute_missing_clock_for_drivers(
    *, days_back: int = 7, company_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Returner liste af dicts:
        {driver_id, name, email, company_id, entries: [{date, start_time, slice_type}]}

    Hvis `company_id` er sat: scope til den ene virksomhed (via chaufførens
    user-record, IKKE entry'ens egen `company_id`-felt — mange legacy entries
    har ikke `company_id` udfyldt). Hvis None: alle firmaer.
    Hver entry er "missing": ingen end_time + date < today_local + date >=
    today_local - days_back.
    """
    today_local_dt = datetime.now(tz=_LOCAL_TZ)
    today_str = today_local_dt.strftime("%Y-%m-%d")
    cutoff_str = (today_local_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # 1) Find først hvilke chauffører der hører til scopet (eller alle hvis
    # company_id is None). Vi bruger USER-rækkens company_id som sandheden,
    # da legacy time-entries ofte mangler company_id-feltet helt.
    driver_filter: Dict[str, Any] = {"role": "driver", "active": True}
    if company_id:
        driver_filter["company_id"] = company_id
    drivers_in_scope = await _raw_db.users.find(
        driver_filter,
        {"_id": 0, "id": 1, "name": 1, "display_name": 1, "email": 1, "company_id": 1},
    ).to_list(None)
    if not drivers_in_scope:
        return []
    driver_id_to_user = {d["id"]: d for d in drivers_in_scope if d.get("id")}
    if not driver_id_to_user:
        return []

    # 2) Find åbne entries (no end_time) i datointervallet, kun for disse
    # drivers. Vi bruger driver_id som join-nøgle — NOT entry.company_id.
    entries_filter: Dict[str, Any] = {
        "driver_id": {"$in": list(driver_id_to_user.keys())},
        "date": {"$gte": cutoff_str, "$lt": today_str},
        "$and": [
            {"$or": [{"end_time": {"$exists": False}}, {"end_time": None}, {"end_time": ""}]},
            {"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
        ],
    }
    entries = await _raw_db.driver_time_entries.find(
        entries_filter,
        {"_id": 0, "id": 1, "driver_id": 1, "date": 1, "start_time": 1, "slice_type": 1},
    ).sort([("date", 1), ("start_time", 1)]).to_list(None)

    if not entries:
        return []

    # 3) Gruppér pr. driver_id.
    by_driver: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        did = e.get("driver_id") or ""
        if not did:
            continue
        by_driver.setdefault(did, []).append({
            "date": e.get("date") or "",
            "start_time": e.get("start_time") or "",
            "slice_type": e.get("slice_type") or "work",
        })

    result: List[Dict[str, Any]] = []
    for did, drv_entries in by_driver.items():
        u = driver_id_to_user.get(did)
        if not u:
            continue
        email = (u.get("email") or "").strip()
        if not email:
            continue
        result.append({
            "driver_id": did,
            "name": u.get("display_name") or u.get("name") or email,
            "email": email,
            "company_id": u.get("company_id") or "",
            "entries": drv_entries,
        })
    # Sortér på flest manglende stempler øverst — kun for log-output.
    result.sort(key=lambda r: -len(r.get("entries", [])))
    return result


async def send_weekly_missing_clock_reminders(
    *, days_back: int = 7, company_id: Optional[str] = None
) -> Dict[str, Any]:
    """Send påmindelses-email til hver chauffør med åbne entries i de seneste
    `days_back` dage. Bruges af både cron-job og admin's "Send nu"-knap.

    Returnerer:
        {sent: int, skipped: int, drivers: [{driver_id, name, email,
        entries_count, delivered: bool, error: Optional[str]}]}
    """
    candidates = await _compute_missing_clock_for_drivers(
        days_back=days_back, company_id=company_id
    )
    sent = 0
    skipped = 0
    drivers_report: List[Dict[str, Any]] = []
    for c in candidates:
        entries = c.get("entries") or []
        if not entries:
            skipped += 1
            continue
        try:
            resp = await _send_missing_clock_reminder_email(
                to_email=c["email"],
                name=c.get("name") or "",
                entries=entries,
                days_back=days_back,
            )
            delivered = bool(resp and resp.get("id"))
            drivers_report.append({
                "driver_id": c["driver_id"],
                "name": c.get("name") or "",
                "email": c["email"],
                "entries_count": len(entries),
                "delivered": delivered,
                "error": resp.get("error") if not delivered else None,
            })
            if delivered:
                sent += 1
            else:
                skipped += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("send_weekly_missing_clock_reminders error for %s: %s", c.get("email"), e)
            drivers_report.append({
                "driver_id": c["driver_id"],
                "name": c.get("name") or "",
                "email": c.get("email") or "",
                "entries_count": len(entries),
                "delivered": False,
                "error": str(e),
            })
            skipped += 1
    return {"sent": sent, "skipped": skipped, "drivers": drivers_report}



# Fase 15.31 (2026-02-22): Lokal-tidszone for fremtid-validering. Klienten
# (chauffør eller admin) sender dato + klokkeslæt som lokal tid; vi
# sammenligner mod current local time i Europe/Copenhagen.
_LOCAL_TZ = ZoneInfo("Europe/Copenhagen")


def _is_future_datetime(date_str: str, time_str: str, buffer_minutes: int = 1) -> bool:
    """Return True hvis (date_str, time_str) ligger efter NU lokal tid.

    Bruges af "Manuel stempel" (event) — både chauffør- og admin-side må
    IKKE oprette manuelle events der ligger i fremtiden. "Opret manuel
    tidsregistrering" (periode) er IKKE underlagt denne regel.

    buffer_minutes: tillader op til denne mange minutters fremtid (defensiv
    margin mod klient/server tidsforskel). Default 1 min.
    """
    if not date_str or not time_str:
        return False
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=_LOCAL_TZ)
        now = datetime.now(tz=_LOCAL_TZ) + timedelta(minutes=buffer_minutes)
        return dt > now
    except Exception:
        return False


# Fase 15.31 (2026-02-22): Soft-delete er nu standard for alle
# tidsregistreringer. Slettede docs har deleted=True + audit-felter.
# Standard-GET-endpoints filtrerer disse ud — admin kan toggle
# include_deleted=true for at se "alle registreringer" incl. slettede.
def _not_deleted_filter() -> dict:
    """Mongo-filter til at ekskludere soft-deleted entries."""
    return {"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}


# Fase 15.30 (2026-02-22): Overlap-validering for tidsregistreringer.
# Returns None hvis OK, eller en HTTPException-detail (str) hvis overlap findes.
# Pause-slices tæller ligesom arbejde-slices — en chauffør må ikke have to
# overlappende perioder uanset type.
def _time_to_min(t: str) -> int:
    try:
        h, m = [int(x) for x in t.split(":")[:2]]
        return h * 60 + m
    except Exception:
        return -1


async def _check_time_overlap(driver_id: str, date: str, new_start: str,
                              new_end: str = "", exclude_id: str = "") -> Optional[str]:
    """Tjek om en ny tidsregistrering vil overlappe med en eksisterende.

    Regler:
    - Hvis new_end er tomt (åben IND): bloker hvis new_start falder inden for
      en eksisterende periodes [start, end) — også åbne perioder fra samme dag.
    - Hvis new_end er sat: tjek interval-overlap [new_start, new_end) mod alle
      eksisterende [start, end) perioder.
    - exclude_id: skip denne entry (bruges når en eksisterende entry opdateres).

    Returnerer en fejlbesked-streng hvis overlap fundet, ellers None.
    """
    new_s = _time_to_min(new_start)
    if new_s < 0:
        return None  # kan ikke parse — lad endpoint-validering håndtere
    has_end = bool(new_end)
    new_e = _time_to_min(new_end) if has_end else -1
    if has_end and new_e <= new_s:
        new_e += 24 * 60  # overnight

    existing = [d async for d in _raw_db.driver_time_entries.find(
        {"driver_id": driver_id, "date": date,
         # Fase 15.31 (2026-02-22): Soft-deleted entries tæller ikke i
         # overlap-tjek.
         "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
        {"_id": 0},
    )]
    for e in existing:
        if exclude_id and e.get("id") == exclude_id:
            continue
        ex_s_raw = e.get("start_time") or ""
        ex_e_raw = e.get("end_time") or ""
        ex_s = _time_to_min(ex_s_raw)
        if ex_s < 0:
            continue
        # Åbne perioder behandles som lukkede ved 23:59 så de stadig fanger
        # nye registreringer der ville lande inden i dem.
        if not ex_e_raw:
            ex_e = 23 * 60 + 59
        else:
            ex_e = _time_to_min(ex_e_raw)
            if ex_e <= ex_s:
                ex_e += 24 * 60
        if ex_s < 0 or ex_e < 0:
            continue
        # Punkt-overlap (åben IND uden end): new_s falder inden for [ex_s, ex_e)
        if not has_end:
            if ex_s <= new_s < ex_e:
                stype = "Pause" if (e.get("slice_type") == "pause") else "Arbejde"
                end_label = ex_e_raw or "åben"
                return f"Tidspunktet {new_start} overlapper med eksisterende {stype.lower()}-periode {ex_s_raw}–{end_label}. Vælg et andet tidspunkt."
        else:
            # Interval-overlap [new_s, new_e) ∩ [ex_s, ex_e) != ∅
            if not (new_e <= ex_s or new_s >= ex_e):
                stype = "Pause" if (e.get("slice_type") == "pause") else "Arbejde"
                end_label = ex_e_raw or "åben"
                return f"Periode {new_start}–{new_end} overlapper med eksisterende {stype.lower()}-periode {ex_s_raw}–{end_label}. Vælg et andet tidsrum."
    return None


async def _get_company_punch_reason_settings(company_id: str) -> dict:
    """Hent require_driver_punch_reason og require_admin_punch_reason for
    et logistik-firma. Default False/False hvis ikke sat."""
    if not company_id:
        return {"driver": False, "admin": False}
    doc = await _raw_db.companies.find_one(
        {"id": company_id},
        {"_id": 0, "require_driver_punch_reason": 1, "require_admin_punch_reason": 1},
    )
    if not doc:
        return {"driver": False, "admin": False}
    return {
        "driver": bool(doc.get("require_driver_punch_reason") or False),
        "admin": bool(doc.get("require_admin_punch_reason") or False),
    }


@api_router.post("/driver/time-entries")
async def create_or_update_time_entry(payload: ManualTimeEntry,
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin"))):
    """Periode-baseret manuel tidsregistrering (start + slut).

    Fase 15.28 (2026-02-22): Adgang BEGRÆNSET til logistics_admin/super_admin.
    Chauffører bruger nu "/manual-punch" til enkelt-event-stempler. Admin
    angiver chaufførens `driver_id` i body — endpoint'et opretter perioden
    på chaufførens vegne. Hvis admin-kravet om "Årsag" er slået til på
    firmaet, kræves `reason` udfyldt.
    """
    # Find chaufføren — admin specifier driver_id
    target_driver_id = (payload.driver_id or "").strip()
    if not target_driver_id:
        raise HTTPException(status_code=400, detail="driver_id (chauffør) er påkrævet for admin-oprettelse")
    driver_doc = await _raw_db.users.find_one(
        {"id": target_driver_id, "role": "driver"},
        {"_id": 0, "id": 1, "name": 1, "company_id": 1},
    )
    if not driver_doc:
        raise HTTPException(status_code=404, detail="Chauffør ikke fundet")
    driver_id = driver_doc["id"]
    driver_name = driver_doc.get("name", "") or ""

    # Fase 15.28: Tjek admin-reason-krav på firmaet
    settings = await _get_company_punch_reason_settings(driver_doc.get("company_id") or "")
    reason_clean = (payload.reason or "").strip()
    if settings["admin"] and not reason_clean:
        raise HTTPException(status_code=400, detail="Årsag er påkrævet på dette firma — udfyld feltet før du fortsætter.")

    if not payload.date or not payload.start_time or not payload.end_time:
        raise HTTPException(status_code=400, detail="Dato, starttidspunkt og sluttidspunkt er påkrævet")
    duration_min = _compute_duration_minutes(payload.start_time, payload.end_time)
    if duration_min <= 0:
        raise HTTPException(status_code=400, detail="Sluttidspunkt skal være efter starttidspunkt")
    # Fase 15.30 (2026-02-22): Brug fælles overlap-helper (tjekker også
    # pause-slices). Gælder uanset om perioden er arbejde eller pause —
    # samme chauffør må ikke have to overlappende registreringer.
    overlap_err = await _check_time_overlap(driver_id, payload.date,
                                            payload.start_time, payload.end_time)
    if overlap_err:
        raise HTTPException(status_code=409, detail=overlap_err)
    actor_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    actor_name = ""
    try:
        _a = await _raw_db.users.find_one({"id": actor_id}, {"_id": 0, "name": 1})
        actor_name = (_a or {}).get("name", "") or ""
    except Exception:
        pass
    slice_type = (payload.slice_type or "work").lower()
    if slice_type not in ("work", "pause"):
        slice_type = "work"
    doc = {
        "id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "driver_name": driver_name,
        "date": payload.date,
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "duration_minutes": duration_min,
        "reason": reason_clean,
        "manual": True,
        # Fase 15.28: kilde-tagging — "period" = admin opret manuel
        # tidsregistrering. "punch_ind"/"punch_ud" sættes af /manual-punch.
        "manual_type": "period",
        # Fase 15.30 (2026-02-22): Arbejde eller pause.
        "slice_type": slice_type,
        "created_by_id": actor_id,
        "created_by_name": actor_name,
        "created_by_role": token_payload.get("role") or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.driver_time_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


class ManualPunch(BaseModel):
    """Fase 15.28 (2026-02-22): Enkelt-event manuel stempling.
    Chauffør angiver dato + tidspunkt + type (ind/ud) + valgfri årsag.
    Fase 15.30 (2026-02-22): `slice_type` ("work"|"pause") angiver om
    et IND-stempel åbner et arbejds- eller pause-slice. UD lukker det
    åbne slice uanset type."""
    date: str
    time: str
    type: str  # "ind" | "ud"
    reason: Optional[str] = ""
    driver_id: Optional[str] = ""  # kun brugt af admin-kald
    slice_type: Optional[str] = "work"  # "work" eller "pause"


@api_router.post("/driver/time-entries/manual-punch")
async def create_manual_punch(payload: ManualPunch,
    token_payload: dict = Depends(require_role("driver", "logistics_admin", "super_admin"))):
    """Fase 15.28 (2026-02-22): Manuel stempel.

    - Driver: opretter for sig selv. `driver_id`-felt ignoreres.
    - Admin (logistics_admin/super_admin): kan angive `driver_id` for at
      oprette på vegne af en bestemt chauffør.

    Regler:
    - type='ind': fejl hvis åben IND allerede findes på SAMME dato.
    - type='ud': skal have en åben IND på SAMME dato (ingen cross-date
      parring). Parres med ældste åbne IND (FIFO).
    - reason: påkrævet hvis firmaets indstilling kræver det.
    """
    role = token_payload.get("role") or ""
    actor_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    # Bestem driver_id
    if role == "driver":
        driver_id = actor_id
    else:
        driver_id = (payload.driver_id or "").strip() or actor_id
    if not driver_id:
        raise HTTPException(status_code=400, detail="driver_id påkrævet for admin-kald")

    driver_doc = await _raw_db.users.find_one(
        {"id": driver_id, "role": "driver"},
        {"_id": 0, "id": 1, "name": 1, "company_id": 1},
    )
    if not driver_doc:
        # Tillader logistics_admin også at oprette på sig selv (sjældent men muligt)
        driver_doc = await _raw_db.users.find_one(
            {"id": driver_id},
            {"_id": 0, "id": 1, "name": 1, "company_id": 1},
        )
    if not driver_doc:
        raise HTTPException(status_code=404, detail="Chauffør ikke fundet")
    driver_name = driver_doc.get("name", "") or ""

    if payload.type not in ("ind", "ud"):
        raise HTTPException(status_code=400, detail="type skal være 'ind' eller 'ud'")
    if not payload.date or not payload.time:
        raise HTTPException(status_code=400, detail="dato og tidspunkt er påkrævet")

    # Tjek reason-krav
    settings = await _get_company_punch_reason_settings(driver_doc.get("company_id") or "")
    reason_clean = (payload.reason or "").strip()
    if role == "driver" and settings["driver"] and not reason_clean:
        raise HTTPException(status_code=400, detail="Årsag er påkrævet på dette firma — udfyld feltet før du fortsætter.")
    if role in ("logistics_admin", "super_admin") and settings["admin"] and not reason_clean:
        raise HTTPException(status_code=400, detail="Årsag er påkrævet på dette firma — udfyld feltet før du fortsætter.")

    # Fase 15.31 (2026-02-22): Manuel stempel (event) må IKKE oprettes med
    # tidspunkt i fremtiden. Gælder både chauffør og admin. Periode-funktionen
    # (POST /driver/time-entries) er undtaget.
    if _is_future_datetime(payload.date, payload.time):
        raise HTTPException(status_code=400,
            detail=f"Tidspunktet {payload.date} {payload.time} ligger i fremtiden — manuelle stempler kan kun oprettes for tidspunkter der allerede er passeret.")

    actor_name = ""
    try:
        _a = await _raw_db.users.find_one({"id": actor_id}, {"_id": 0, "name": 1})
        actor_name = (_a or {}).get("name", "") or ""
    except Exception:
        pass
    now_iso = datetime.now(timezone.utc).isoformat()

    if payload.type == "ind":
        # Fase 15.33 (2026-02-22): Manuel IND følger nu SAMME transition-
        # logik som den fysiske /punch endpoint:
        #   - Ingen åben slice + slice_type=work → standard manuel IND
        #   - Ingen åben slice + slice_type=pause → 409 "kan ikke starte pause
        #     uden at være på arbejde"
        #   - Åben work + slice_type=pause → atomisk: luk work + åbn pause
        #   - Åben pause + slice_type=work → atomisk: luk pause + åbn work
        #   - Åben slice af samme type → 409 (allerede i den tilstand)
        slice_type = (payload.slice_type or "work").lower()
        if slice_type not in ("work", "pause"):
            slice_type = "work"
        # Find åben slice (eksl. soft-deleted)
        open_doc = await _raw_db.driver_time_entries.find_one(
            {"driver_id": driver_id, "date": payload.date,
             "$or": [{"end_time": ""}, {"end_time": None}],
             "$and": [{"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}]},
            {"_id": 0, "id": 1, "start_time": 1, "slice_type": 1},
        )

        if open_doc:
            open_slice_type = open_doc.get("slice_type") or "work"
            if open_slice_type == slice_type:
                kind = "pause" if slice_type == "pause" else "arbejde"
                raise HTTPException(status_code=409,
                    detail=f"Du er allerede i {kind} kl. {open_doc.get('start_time')} — afslut den først eller skift type.")
            # Transition — luk den åbne slice ved payload.time + åbn ny slice
            duration_min = _compute_duration_minutes(open_doc.get("start_time", ""), payload.time)
            if duration_min <= 0:
                raise HTTPException(status_code=400,
                    detail=f"Tidspunkt {payload.time} er før den åbne {open_slice_type}-slice's start {open_doc.get('start_time')} — kan ikke lukke den.")
            # Overlap-tjek for det nye lukkede interval
            overlap_err = await _check_time_overlap(
                driver_id, payload.date,
                open_doc.get("start_time", ""), payload.time,
                exclude_id=open_doc.get("id", ""),
            )
            if overlap_err:
                raise HTTPException(status_code=409, detail=overlap_err)
            await _raw_db.driver_time_entries.update_one(
                {"id": open_doc["id"]},
                {"$set": {
                    "end_time": payload.time,
                    "duration_minutes": duration_min,
                    "manual_type": "punch_ud",
                    "ud_reason": reason_clean,
                    "ud_created_by_id": actor_id,
                    "ud_created_by_name": actor_name,
                    "ud_created_by_role": role,
                    "updated_at": now_iso,
                }},
            )
            new_doc = {
                "id": str(uuid.uuid4()),
                "driver_id": driver_id,
                "driver_name": driver_name,
                "date": payload.date,
                "start_time": payload.time,
                "end_time": "",
                "duration_minutes": 0,
                "reason": reason_clean,
                "manual": True,
                "manual_type": "punch_ind",
                "slice_type": slice_type,
                "created_by_id": actor_id,
                "created_by_name": actor_name,
                "created_by_role": role,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            await _raw_db.driver_time_entries.insert_one(new_doc)
            new_doc.pop("_id", None)
            return new_doc

        # Ingen åben slice → almindelig IND
        if slice_type == "pause":
            raise HTTPException(status_code=409,
                detail="Du skal være stemplet ind på arbejde før du kan starte pause.")
        # Overlap-tjek mod eksisterende lukkede perioder
        overlap_err = await _check_time_overlap(driver_id, payload.date, payload.time)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        doc = {
            "id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "driver_name": driver_name,
            "date": payload.date,
            "start_time": payload.time,
            "end_time": "",
            "duration_minutes": 0,
            "reason": reason_clean,
            "manual": True,
            "manual_type": "punch_ind",
            "slice_type": slice_type,
            "created_by_id": actor_id,
            "created_by_name": actor_name,
            "created_by_role": role,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await _raw_db.driver_time_entries.insert_one(doc)
        doc.pop("_id", None)
        return doc

    # type == "ud" — parre med ældste åbne IND samme dato (ingen cross-date),
    # eksl. soft-deleted entries.
    open_doc = await _raw_db.driver_time_entries.find_one(
        {"driver_id": driver_id, "date": payload.date,
         "$or": [{"end_time": ""}, {"end_time": None}],
         "$and": [{"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}]},
        sort=[("start_time", 1)],
    )
    if not open_doc:
        raise HTTPException(status_code=409,
            detail="Ingen åben IND-stempling fundet på den valgte dato. Opret en manuel IND først.")
    duration_min = _compute_duration_minutes(open_doc.get("start_time", ""), payload.time)
    if duration_min <= 0:
        raise HTTPException(status_code=400,
            detail=f"UD-tidspunkt {payload.time} er før IND-tidspunkt {open_doc.get('start_time')}")
    # Fase 15.30 (2026-02-22): Når vi lukker en åben IND, må det resulterende
    # interval ikke overlappe en allerede lukket periode (fx en pause inden i).
    overlap_err = await _check_time_overlap(
        driver_id, payload.date,
        open_doc.get("start_time", ""), payload.time,
        exclude_id=open_doc.get("id", ""),
    )
    if overlap_err:
        raise HTTPException(status_code=409, detail=overlap_err)
    # Bevar evt. eksisterende manual_type på IND'en hvis den var automatisk
    # (punch fra fysisk stempel) — opdatér til "punch_ud" + tag UD-metadata.
    set_doc = {
        "end_time": payload.time,
        "duration_minutes": duration_min,
        "manual": True,  # markér rækken som manuel (mindst én side var manuel)
        "manual_type": "punch_ud",
        "ud_reason": reason_clean,
        "ud_created_by_id": actor_id,
        "ud_created_by_name": actor_name,
        "ud_created_by_role": role,
        "updated_at": now_iso,
    }
    await _raw_db.driver_time_entries.update_one(
        {"id": open_doc["id"]}, {"$set": set_doc},
    )
    return {
        "id": open_doc["id"], "driver_id": driver_id, "date": payload.date,
        "start_time": open_doc.get("start_time"), "end_time": payload.time,
        "duration_minutes": duration_min, "manual": True, "manual_type": "punch_ud",
    }


# ─── Fase 15.28 (2026-02-22): Admin-CRUD på time entries ────────────────────
@api_router.get("/admin/time-entries-list")
async def admin_list_time_entries(
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin")),
    driver_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Liste alle tidsregistreringer for chauffører i admin's firma.
    Multi-tenant scoped via current_company_id."""
    cid = current_company_id.get() or ""
    if not cid or cid == SUPER_ADMIN_BYPASS:
        # super_admin uden valgt company → vis alle
        driver_filter = {}
    else:
        driver_filter = {"company_id": cid}
    if driver_id:
        driver_filter["id"] = driver_id
    driver_ids = [u["id"] async for u in _raw_db.users.find(
        {**driver_filter, "role": "driver"}, {"_id": 0, "id": 1}
    )]
    if not driver_ids:
        return []
    flt = {"driver_id": {"$in": driver_ids}}
    if date_from or date_to:
        flt["date"] = {}
        if date_from:
            flt["date"]["$gte"] = date_from
        if date_to:
            flt["date"]["$lte"] = date_to
    out = []
    async for e in _raw_db.driver_time_entries.find(flt, {"_id": 0}).sort([("date", -1), ("start_time", 1)]).limit(500):
        out.append(e)
    return out


@api_router.delete("/admin/time-entries/{entry_id}")
async def admin_delete_time_entry(
    entry_id: str,
    cascade: bool = False,
    hard: bool = False,
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin")),
):
    """Slet et tidsregistrering-entry.

    Fase 15.31 (2026-02-22): Standard er nu SOFT-delete — entry markeres
    `deleted=True` + audit-felter (deleted_by_id/role/at). Send ?hard=true
    for permanent fjernelse (kun til database-cleanup, bør ikke bruges fra UI).

    cascade (legacy): hvis True og entry er parret, slettes hele rækken.
    Bibeholdes for legacy-kompatibilitet men er nu en no-op i soft-mode.
    """
    cid = current_company_id.get() or ""
    entry = await _raw_db.driver_time_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Tidsregistrering ikke fundet")
    # Verificer at chaufføren tilhører admin's firma
    if cid and cid != SUPER_ADMIN_BYPASS:
        drv = await _raw_db.users.find_one({"id": entry.get("driver_id")}, {"_id": 0, "company_id": 1})
        if not drv or drv.get("company_id") != cid:
            raise HTTPException(status_code=403, detail="Ingen adgang til denne chauffør")
    if hard:
        await _raw_db.driver_time_entries.delete_one({"id": entry_id})
        return {"deleted_count": 1, "mode": "hard"}
    # Soft delete — sæt audit-felter
    actor_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    actor_name = ""
    try:
        _a = await _raw_db.users.find_one({"id": actor_id}, {"_id": 0, "name": 1})
        actor_name = (_a or {}).get("name", "") or ""
    except Exception:
        pass
    await _raw_db.driver_time_entries.update_one(
        {"id": entry_id},
        {"$set": {
            "deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by_id": actor_id,
            "deleted_by_name": actor_name,
            "deleted_by_role": token_payload.get("role") or "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"deleted_count": 1, "mode": "soft"}


# Fase 15.32 (2026-02-22): Admin kan opdatere enhver entry tilhørende
# chaufførerne i sit firma. Felter: start_time/end_time/date/reason/slice_type.
# Overlap-validering anvendes. Fremtid-validering anvendes IKKE (admin må
# oprette/redigere i fremtiden — kun manuel-stempel-event er underlagt
# fremtid-blokering pr. spec).
@api_router.patch("/admin/time-entries/{entry_id}")
async def admin_update_time_entry(
    entry_id: str,
    payload: "DriverOwnEntryUpdate",  # forward-ref — defined below
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin")),
):
    entry = await _raw_db.driver_time_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Tidsregistrering ikke fundet")
    if entry.get("deleted"):
        raise HTTPException(status_code=410, detail="Tidsregistreringen er allerede slettet")
    cid = current_company_id.get() or ""
    if cid and cid != SUPER_ADMIN_BYPASS:
        drv = await _raw_db.users.find_one({"id": entry.get("driver_id")}, {"_id": 0, "company_id": 1})
        if not drv or drv.get("company_id") != cid:
            raise HTTPException(status_code=403, detail="Ingen adgang til denne chauffør")

    new_date = (payload.date or entry.get("date") or "").strip()
    new_start = (payload.start_time or entry.get("start_time") or "").strip()
    new_end_raw = payload.end_time if payload.end_time is not None else entry.get("end_time")
    new_end = (new_end_raw or "").strip()
    new_reason = (payload.reason if payload.reason is not None else (entry.get("reason") or "")).strip()
    new_slice = (payload.slice_type or entry.get("slice_type") or "work").lower()
    if new_slice not in ("work", "pause"):
        new_slice = "work"
    if not new_date or not new_start:
        raise HTTPException(status_code=400, detail="Dato og starttidspunkt er påkrævet")

    if new_end:
        overlap_err = await _check_time_overlap(entry.get("driver_id"), new_date, new_start, new_end, exclude_id=entry_id)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        if _compute_duration_minutes(new_start, new_end) <= 0:
            raise HTTPException(status_code=400, detail="Sluttidspunkt skal være efter starttidspunkt")
        new_duration = _compute_duration_minutes(new_start, new_end)
    else:
        overlap_err = await _check_time_overlap(entry.get("driver_id"), new_date, new_start, exclude_id=entry_id)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        new_duration = 0

    update = {
        "date": new_date,
        "start_time": new_start,
        "end_time": new_end,
        "reason": new_reason,
        "slice_type": new_slice,
        "duration_minutes": new_duration,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.driver_time_entries.update_one({"id": entry_id}, {"$set": update})
    refreshed = await _raw_db.driver_time_entries.find_one({"id": entry_id}, {"_id": 0})
    return refreshed
class DriverOwnEntryUpdate(BaseModel):
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None
    slice_type: Optional[str] = None  # "work" | "pause"


async def _verify_driver_owns_manual(entry_id: str, driver_id: str) -> dict:
    """Henter entry og verificerer at chaufføren MÅ røre det.
    Raises HTTPException ved fejl, ellers returnerer dokumentet.

    Fase 15.32 (2026-02-22): Chauffør må nu også redigere/slette egne
    AUTOMATISKE IND/UD-stemplinger — kun admin-oprettede entries er låste.
    Reglen er nu: driver_id==self AND created_by_role IKKE 'logistics_admin'
    eller 'super_admin'."""
    entry = await _raw_db.driver_time_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Tidsregistrering ikke fundet")
    if entry.get("deleted"):
        raise HTTPException(status_code=410, detail="Tidsregistreringen er allerede slettet")
    if entry.get("driver_id") != driver_id:
        raise HTTPException(status_code=403, detail="Dette er ikke din egen registrering")
    if (entry.get("created_by_role") or "") in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403,
            detail="Denne registrering blev oprettet af en admin og kan kun ændres af en admin.")
    return entry


@api_router.patch("/driver/time-entries/{entry_id}")
async def driver_update_own_manual_entry(
    entry_id: str,
    payload: DriverOwnEntryUpdate,
    token_payload: dict = Depends(require_role("driver")),
):
    driver_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    entry = await _verify_driver_owns_manual(entry_id, driver_id)

    # Beregn nye værdier (falder tilbage til eksisterende ved None)
    new_date = (payload.date or entry.get("date") or "").strip()
    new_start = (payload.start_time or entry.get("start_time") or "").strip()
    new_end_raw = payload.end_time if payload.end_time is not None else entry.get("end_time")
    new_end = (new_end_raw or "").strip()
    new_reason = (payload.reason if payload.reason is not None else (entry.get("reason") or "")).strip()
    new_slice = (payload.slice_type or entry.get("slice_type") or "work").lower()
    if new_slice not in ("work", "pause"):
        new_slice = "work"

    if not new_date or not new_start:
        raise HTTPException(status_code=400, detail="Dato og starttidspunkt er påkrævet")

    # Fremtid-validering (start). Hvis end er sat, valider også den.
    if _is_future_datetime(new_date, new_start):
        raise HTTPException(status_code=400,
            detail=f"Starttidspunkt {new_date} {new_start} ligger i fremtiden — manuelle registreringer må ikke fremtidsdateres.")
    if new_end and _is_future_datetime(new_date, new_end):
        raise HTTPException(status_code=400,
            detail=f"Sluttidspunkt {new_date} {new_end} ligger i fremtiden — manuelle registreringer må ikke fremtidsdateres.")

    # Overlap-tjek (eksklusiv den entry vi opdaterer).
    if new_end:
        # Periode-validering
        overlap_err = await _check_time_overlap(driver_id, new_date, new_start, new_end, exclude_id=entry_id)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        # Tjek at slut > start
        if _compute_duration_minutes(new_start, new_end) <= 0:
            raise HTTPException(status_code=400, detail="Sluttidspunkt skal være efter starttidspunkt")
        new_duration = _compute_duration_minutes(new_start, new_end)
    else:
        # Åben (kun start)
        overlap_err = await _check_time_overlap(driver_id, new_date, new_start, exclude_id=entry_id)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        new_duration = 0

    update = {
        "date": new_date,
        "start_time": new_start,
        "end_time": new_end,
        "reason": new_reason,
        "slice_type": new_slice,
        "duration_minutes": new_duration,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # Fase 15.48 (2026-02-22): Når chaufføren redigerer sin egen time
        # slice (uanset om den oprindeligt var automatisk eller manuel),
        # markeres den nu ALTID som "manuel" så rapporter og audit-log
        # korrekt viser at en bruger har ændret tidspunkterne. `manual_type`
        # afhænger af om der er en sluttid: "period" hvis både start+slut,
        # ellers "punch_ind" (åben registrering — chauffør har kun start).
        "manual": True,
        "manual_type": "period" if new_end else "punch_ind",
        # Audit-spor — gemmer at chaufføren selv har redigeret.
        "edited_by_driver": True,
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.driver_time_entries.update_one({"id": entry_id}, {"$set": update})
    refreshed = await _raw_db.driver_time_entries.find_one({"id": entry_id}, {"_id": 0})
    return refreshed


@api_router.delete("/driver/time-entries/{entry_id}")
async def driver_delete_own_entry(
    entry_id: str,
    token_payload: dict = Depends(require_role("driver")),
):
    """Slet en egen registrering. Fase 15.34 (2026-02-22): Driver-side
    delete er nu HARD-delete — entry fjernes helt fra databasen. Tidligere
    var det soft-delete (deleted=True), men det skabte forvirring fordi
    slettede entries kunne 'sidde fast' i edge-cases (selvom alle backend-
    queries filtrerede dem ud). Hård sletning eliminerer hele kategorien
    af bugs. Admin-siden bevarer soft-delete for audit-trail."""
    driver_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    await _verify_driver_owns_manual(entry_id, driver_id)
    result = await _raw_db.driver_time_entries.delete_one({"id": entry_id})
    return {"deleted_count": int(result.deleted_count or 0), "mode": "hard"}


class TimePunch(BaseModel):
    date: str
    time: str   # "HH:MM"
    type: str   # "ind" eller "ud"
    # Fase 15.30 (2026-02-22): "work" (arbejde) eller "pause". Bruges KUN for
    # type="ind" og kun til at angive hvilken slice-type der åbnes. UD lukker
    # det åbne slice uanset type.
    slice_type: Optional[str] = "work"


@api_router.post("/driver/time-entries/punch")
async def punch_in_out(payload: TimePunch,
    token_payload: dict = Depends(require_role("driver", "logistics_admin", "super_admin"))):
    """Stempl ind eller ud. Hver stempling er en separat operation:
    - "ind": Opretter en ny åben periode (end_time="") for dagen.
             Fejl hvis chaufføren allerede har en åben periode samme dato.
    - "ud":  Lukker den seneste åbne periode for dagen og beregner duration.
             Fejl hvis ingen åben periode findes.

    Fase 13 (2026-06-18): Erstatter den gamle "én post pr. dag"-model med
    en flere-perioder-model. Et typisk dagforløb: Ind 07:00 → Ud 12:00
    (pause) → Ind 13:00 → Ud 17:00 = 9 timer arbejde.

    Fase 15.30 (2026-02-22): Pause er nu en explicit slice-type.
    - type="ind" + slice_type="pause": kræver en åben work-slice → lukker
      den + åbner en ny pause-slice med samme tidspunkt (atomic transition).
    - type="ind" + slice_type="work": hvis en pause er åben → lukker den +
      åbner ny work-slice (atomic). Hvis ingen åben slice → standard ind.
    - type="ud": lukker den ældste åbne slice uanset type.
    """
    driver_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    driver_name = ""
    try:
        _u = await _raw_db.users.find_one({"id": driver_id}, {"_id": 0, "name": 1})
        driver_name = (_u or {}).get("name", "") or ""
    except Exception:
        pass
    if payload.type not in ("ind", "ud"):
        raise HTTPException(status_code=400, detail="type skal være 'ind' eller 'ud'")
    if not payload.date or not payload.time:
        raise HTTPException(status_code=400, detail="dato og tidspunkt er påkrævet")

    requested_slice = (payload.slice_type or "work").lower()
    if requested_slice not in ("work", "pause"):
        requested_slice = "work"
    now_iso = datetime.now(timezone.utc).isoformat()

    if payload.type == "ind":
        # Tjek om der er en åben slice — afgør om dette er en "transition"
        # (start pause / start arbejde igen) eller en helt ny åben slice.
        # Fase 15.31 (2026-02-22): Soft-deleted entries ignoreres.
        open_doc = await _raw_db.driver_time_entries.find_one(
            {"driver_id": driver_id, "date": payload.date,
             "$or": [{"end_time": ""}, {"end_time": None}],
             "$and": [{"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}]},
            {"_id": 0, "id": 1, "start_time": 1, "slice_type": 1},
        )
        open_slice_type = (open_doc or {}).get("slice_type") or ("work" if open_doc else "")
        # Tillad kun specifikke transitions:
        # - open=work + requested=pause → start pause
        # - open=pause + requested=work → start arbejde igen
        # - ingen åben + requested=work → almindelig ind
        # - ingen åben + requested=pause → afvis (kan ikke starte pause uden
        #   at være på arbejde først)
        if open_doc:
            if open_slice_type == requested_slice:
                # Samme type allerede åben → afvis (chaufføren skal stemple
                # ud eller starte den modsatte slice for at gå videre).
                kind = "pause" if requested_slice == "pause" else "arbejde"
                raise HTTPException(status_code=409,
                    detail=f"Du er allerede i {kind} kl. {open_doc.get('start_time')}.")
            # Transition: luk open_doc, beregn duration, og åbn ny slice
            duration_min = _compute_duration_minutes(open_doc.get("start_time", ""), payload.time)
            if duration_min <= 0:
                raise HTTPException(status_code=400,
                    detail=f"Tidspunkt {payload.time} er før {open_doc.get('start_time')} — kan ikke lukke den åbne periode.")
            # Tjek at den lukkede periode ikke overlapper andre lukkede entries
            overlap_err = await _check_time_overlap(
                driver_id, payload.date,
                open_doc.get("start_time", ""), payload.time,
                exclude_id=open_doc.get("id", ""),
            )
            if overlap_err:
                raise HTTPException(status_code=409, detail=overlap_err)
            await _raw_db.driver_time_entries.update_one(
                {"id": open_doc["id"]},
                {"$set": {
                    "end_time": payload.time,
                    "duration_minutes": duration_min,
                    "updated_at": now_iso,
                }},
            )
            # Tjek for overlap inden den nye slice oprettes (overgangs-
            # tidspunktet er allerede taget af den lige-lukkede slice, så
            # vi skipper den fra overlap-tjekket).
            new_doc = {
                "id": str(uuid.uuid4()),
                "driver_id": driver_id,
                "driver_name": driver_name,
                "date": payload.date,
                "start_time": payload.time,
                "end_time": "",
                "duration_minutes": 0,
                "reason": "",
                "manual": False,
                "slice_type": requested_slice,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            await _raw_db.driver_time_entries.insert_one(new_doc)
            new_doc.pop("_id", None)
            return new_doc
        # Ingen åben slice
        if requested_slice == "pause":
            raise HTTPException(status_code=409,
                detail="Du skal være stemplet ind på arbejde før du kan starte pause.")
        # Tjek overlap mod evt. lukkede perioder
        overlap_err = await _check_time_overlap(driver_id, payload.date, payload.time)
        if overlap_err:
            raise HTTPException(status_code=409, detail=overlap_err)
        doc = {
            "id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "driver_name": driver_name,
            "date": payload.date,
            "start_time": payload.time,
            "end_time": "",
            "duration_minutes": 0,
            "reason": "",
            "manual": False,
            "slice_type": "work",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await _raw_db.driver_time_entries.insert_one(doc)
        doc.pop("_id", None)
        return doc

    # type == "ud"
    # Fase 15.1 (2026-06-19): FIFO-parring — find ÆLDSTE åbne ind-stempling
    # for dagen (sort ASC = first in, first out). Tidligere brugte vi DESC
    # som var LIFO — typisk samme resultat fordi backend blokerer multiple
    # opens, men FIFO er den canoniske SuccessFactors-regel.
    # Fase 15.31 (2026-02-22): Soft-deleted entries ignoreres.
    open_doc = await _raw_db.driver_time_entries.find_one(
        {"driver_id": driver_id, "date": payload.date,
         "$or": [{"end_time": ""}, {"end_time": None}],
         "$and": [{"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}]},
        sort=[("start_time", 1)],
    )
    if not open_doc:
        # Fase 15.1 (2026-06-19): Forbedret besked + tjek for at en åben
        # IND-stempling findes på en TIDLIGERE dato. Det betyder chaufføren
        # forsøger at stemple ud efter midnat — afvis og bed om Manuel.
        prior_open = await _raw_db.driver_time_entries.find_one(
            {"driver_id": driver_id, "date": {"$lt": payload.date},
             "$or": [{"end_time": ""}, {"end_time": None}],
             "$and": [{"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]}]},
            sort=[("date", -1), ("start_time", -1)],
        )
        if prior_open:
            raise HTTPException(status_code=409,
                detail="Kan ikke stemple ud efter midnat. Brug Manuel tidsregistrering.")
        raise HTTPException(status_code=409,
            detail="Ingen åben stempling for den dag. Brug Manuel tidsregistrering hvis du glemte at stemple ind.")
    duration_min = _compute_duration_minutes(open_doc.get("start_time", ""), payload.time)
    if duration_min <= 0:
        raise HTTPException(status_code=400,
            detail=f"Sluttidspunkt {payload.time} er før starttidspunkt {open_doc.get('start_time')}")
    # Fase 15.30 (2026-02-22): Tjek at den lukkede periode ikke overlapper
    # andre eksisterende perioder samme dag.
    overlap_err = await _check_time_overlap(
        driver_id, payload.date,
        open_doc.get("start_time", ""), payload.time,
        exclude_id=open_doc.get("id", ""),
    )
    if overlap_err:
        raise HTTPException(status_code=409, detail=overlap_err)
    await _raw_db.driver_time_entries.update_one(
        {"id": open_doc["id"]},
        {"$set": {
            "end_time": payload.time,
            "duration_minutes": duration_min,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "id": open_doc["id"], "driver_id": driver_id, "date": payload.date,
        "start_time": open_doc.get("start_time"), "end_time": payload.time,
        "duration_minutes": duration_min, "manual": False,
        "slice_type": open_doc.get("slice_type") or "work",
    }


@api_router.get("/driver/time-entries")
async def list_my_time_entries(
    token_payload: dict = Depends(require_role("driver", "logistics_admin", "super_admin")),
    date_from: Optional[str] = None, date_to: Optional[str] = None,
):
    driver_id = token_payload.get("sub") or token_payload.get("user_id") or ""
    flt = {"driver_id": driver_id}
    if date_from or date_to:
        flt["date"] = {}
        if date_from:
            flt["date"]["$gte"] = date_from
        if date_to:
            flt["date"]["$lte"] = date_to
    # Fase 15.31 (2026-02-22): Soft-delete — skjul slettede entries fra
    # chaufførens egen liste. Chauffør kan IKKE se sine egne slettede.
    flt.update(_not_deleted_filter())
    cursor = _raw_db.driver_time_entries.find(flt, {"_id": 0}).sort([("date", -1), ("start_time", 1)]).limit(240)
    return [doc async for doc in cursor]


def _tour_duration_min(start_hhmm: str, end_hhmm: str) -> Optional[int]:
    s, e = _time_to_min(start_hhmm or ""), _time_to_min(end_hhmm or "")
    if s < 0 or e < 0:
        return None
    return e - s if e >= s else e - s + 24 * 60  # tur over midnat


# 2026-10-16: Datagrundlag for chaufførens dagrapport-PDF. Før byggede
# PDF'en tiden ud fra ét start/slut-par (sidste IND → UD), så arbejde/pause-
# perioder forsvandt og "Tid i alt" kun dækkede den sidste periode. Ture
# blev desuden kun taget med hvis turens `date` var rapportdagen — en tur
# bestilt til i morgen men kørt i dag manglede. Nu: alle stemplinger
# (samme summering som PDF-arkivet) + alle ture chaufføren AFSLUTTEDE på dagen.
async def _build_day_report(driver_id: str, day: str) -> dict:
    """Datagrundlaget for dagrapport-PDF'en (chaufførens egen + logistik
    admins arkiv). Bygges altid friskt fra stemplinger, ture, godkendte
    rettelser og prisreglernes pause-regel - derfor er PDF'en aldrig et
    forældet øjebliksbillede."""
    user = await _raw_db.users.find_one({"id": driver_id}, {"_id": 0, "name": 1, "company_id": 1}) or {}
    driver_name = user.get("name") or ""
    entries = await _raw_db.driver_time_entries.find(
        {"driver_id": driver_id, "date": day, **_not_deleted_filter()}, {"_id": 0},
    ).to_list(500)
    now = datetime.now(DK_TZ)
    is_today = day == now.strftime("%Y-%m-%d")
    summary = _summarize_day_entries(
        entries,
        today_str=day if is_today else "",
        now_hhmm=now.strftime("%H:%M") if is_today else "",
    )
    mine = [{"claimed_by_id": driver_id}]
    if driver_name:
        mine.append({"claimed_by": driver_name})
    tours = await _raw_db.tours.find(
        {"$and": [
            {"completed": True},
            {"$or": mine},
            {"$or": [
                {"completed_at": {"$regex": f"^{re.escape(day)}"}},
                {"completed_at": {"$in": ["", None]}, "date": day},
                {"completed_at": {"$exists": False}, "date": day},
            ]},
            {"$or": [{"is_pause": {"$exists": False}}, {"is_pause": False}]},
            {"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
            {"tour_type": {"$ne": "estimat"}},
        ]},
        {"_id": 0, "receipt_image": 0},
    ).to_list(1000)
    # Afregnings-tid pr. tur (samme motor som Økonomi): pause-regel,
    # deling ved samtidige ture og afrunding - men ingen beløb.
    logi = user.get("company_id") or ""
    rules = await _active_rules(logi) if logi else []
    ctx = _PricingContext(logi, await _price_settings(logi), rules)
    await ctx.load(tours)
    pauses = [(_time_to_min(p.get("start_time") or ""), _time_to_min(p.get("effective_end") or p.get("end_time") or ""))
              for p in summary.get("pause_slices") or []]
    out_tours = []
    for t in tours:
        start, end = _tour_times(t)
        s_min, e_min = _time_to_min(start), _time_to_min(end)
        pause_min = 0
        if s_min >= 0 and e_min > s_min:
            pause_min = sum(max(0, min(e_min, pe) - max(s_min, ps)) for ps, pe in pauses if ps >= 0 and pe > ps)
        base, _sur = _pricing.select_rules(ctx.rules_for(t), ctx.attrs(t))
        p = (base or {}).get("pricing") or {}
        po = t.get("price_override") or {}
        model = "fixed" if po.get("mode") == "fixed" else (p.get("model") or "")
        deduct = (t.get("fact_overrides") or {}).get("deduct_pause", p.get("deduct_pause", True))
        price = ctx.price(t)
        tm = price.get("time") or {}
        out_tours.append({
            "id": t.get("id", ""),
            "date": t.get("date", ""),
            "plads": t.get("plads", ""),
            "fraction": t.get("fraction", ""),
            "task_type": t.get("tour_type") or "normal",
            "facility": ctx.delivery_label(t) or t.get("facility", ""),
            "container": t.get("container", ""),
            "address": t.get("address", ""),
            "weight": t.get("weight"),
            "is_same_day": bool(t.get("is_same_day")),
            "tour_number": t.get("tour_number", ""),
            "used_trailer": bool(_fact(t, "used_trailer", t.get("used_trailer"))),
            "waiting_min": int(_fact(t, "waiting_min", 0) or 0),
            "start_time": start,
            "end_time": end,
            "duration_min": _tour_duration_min(start, end),
            "pause_min": pause_min,
            "billing": {
                "model": model,
                "deduct_pause": bool(deduct) if model == "hourly" else None,
                "shared_min": tm.get("shared_min") or 0,
                "billable_min": tm.get("billable_min"),
                "rounding": tm.get("rounding") or "",
                "corrected": bool(t.get("fact_overrides")),
            },
            "completed_at": t.get("completed_at", ""),
        })
    out_tours.sort(key=lambda x: (x["start_time"] or "99:99", x["plads"]))
    return {"date": day, "driver_name": driver_name, "time_summary": summary, "tours": out_tours}


@api_router.get("/driver/day-report")
async def driver_day_report(
    date: str,
    token_payload: dict = Depends(require_role("driver")),
):
    return await _build_day_report(token_payload.get("sub") or token_payload.get("user_id") or "", date)


@api_router.get("/admin/day-report/{archive_id}")
async def admin_day_report(archive_id: str,
                           token_payload: dict = Depends(require_role("logistics_admin", "super_admin"))):
    """Logistik admin åbner en dagrapport fra Arkiv: bygges friskt ud fra
    nuværende data (inkl. godkendte rettelser), ikke den gemte fil."""
    a = await _raw_db.pdf_archives.find_one({"id": archive_id}, {"_id": 0, "file_data": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Dagrapport ikke fundet")
    q: Dict[str, Any] = {"role": "driver", "name": a.get("driver_name") or ""}
    if token_payload.get("role") == "logistics_admin":
        me = await _raw_db.users.find_one({"id": token_payload.get("sub")}, {"_id": 0, "company_id": 1}) or {}
        q["company_id"] = me.get("company_id")
    driver = await _raw_db.users.find_one(q, {"_id": 0, "id": 1})
    if not driver:
        raise HTTPException(status_code=404, detail="Chaufføren findes ikke længere")
    rep = await _build_day_report(driver["id"], a.get("report_date") or "")
    rep["vehicle_reg"] = a.get("vehicle_reg") or ""
    rep["notes"] = a.get("notes") or ""
    return rep


@api_router.post("/admin/day-reports")
async def admin_day_reports(body: dict = Body(...),
                            token_payload: dict = Depends(require_role("logistics_admin", "super_admin"))):
    """Samme som /admin/day-report/{id} for mange dagrapporter i ét kald
    (ZIP-download af en hel måned uden at ramme rate-limit)."""
    out = []
    for aid in [str(x) for x in (body.get("ids") or [])][:500]:
        try:
            out.append({"archive_id": aid, **(await admin_day_report(aid, token_payload))})
        except HTTPException as e:
            out.append({"archive_id": aid, "error": e.detail})
    return out


# Fase 15.3 (2026-06-19): Logistik Admin overblik over alle chaufførers
# tidsregistreringer (Ind/Ud + Manuel) for en given dato. Returneres
# grupperet pr. chauffør med pairs (start_time → end_time, duration).
@api_router.get("/admin/time-entries")
async def admin_list_time_entries_for_date(
    date: str,
    include_deleted: bool = False,
    missing_only: bool = False,
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin")),
):
    """Returns: [{driver_id, driver_name, entries: [...], total_minutes, ...}].

    Fase 15.31 (2026-02-22): include_deleted=true viser slettede entries
    også (mærket med deleted=true i hver entry). Default false — slettede
    skjules fra normal Tidsregistrering-overblik.
    Fase 15.35 (2026-02-22): missing_only=true returnerer KUN chauffører
    med mindst én manglende stempel (uoplukket entry fra past date).
    """
    la_company = token_payload.get("company_id")
    # 1) Find alle drivers tilknyttet denne LA's company.
    driver_filter = {"role": "driver"}
    if la_company and la_company != SUPER_ADMIN_BYPASS:
        driver_filter["company_id"] = la_company
    drivers = await _raw_db.users.find(
        driver_filter,
        {"_id": 0, "id": 1, "name": 1, "display_name": 1, "email": 1, "active": 1},
    ).to_list(None)
    # 2) Hent alle time-entries for dagen. Soft-delete filter anvendes
    # by default; toggle include_deleted=true for at se alle.
    entries_filter = {"date": date}
    if not include_deleted:
        entries_filter.update(_not_deleted_filter())
    entries = await _raw_db.driver_time_entries.find(
        entries_filter, {"_id": 0},
    ).sort([("start_time", 1)]).to_list(None)
    by_driver = {}
    for e in entries:
        did = e.get("driver_id") or ""
        by_driver.setdefault(did, []).append(e)

    # Fase 15.31 (2026-02-22): deleted_count regnes ALTID via separat
    # aggregering — så badge'en på admin-UI'et altid kan vise antal slettede
    # uanset om include_deleted-toggle er slået til. Ellers ville
    # deleted_count = 0 i default-visning fordi entries-listen allerede er
    # filtreret. Aggregeringen begrænses til drivers der findes i firmaet.
    deleted_count_by_driver = {}
    try:
        agg = _raw_db.driver_time_entries.aggregate([
            {"$match": {"date": date, "deleted": True}},
            {"$group": {"_id": "$driver_id", "n": {"$sum": 1}}},
        ])
        async for row in agg:
            deleted_count_by_driver[row.get("_id") or ""] = int(row.get("n") or 0)
    except Exception:
        pass
    # 3) Bygg svar. Slettede entries tæller IKKE i sum-aggregeringen.
    def _alive(e):
        return not e.get("deleted", False)
    # Fase 15.35 (2026-02-22): missing_clock-flag pr. entry tilføjes her —
    # sættes på selve entry-dokumentet i listen så frontend kan rendere
    # rød "Mangler stempel"-badge + filtrere på det.
    for entries_list in by_driver.values():
        for e in entries_list:
            e["missing_clock"] = _is_entry_missing_clock(e)
    out = []
    for d in drivers:
        did = d.get("id") or ""
        if not d.get("active", True):
            continue
        de = by_driver.get(did, [])
        # Fase 15.30 (2026-02-22): Skel mellem arbejde- og pause-tid.
        # Fase 15.31: slettede ekskluderes fra totalsummer (men vises i
        # entries-listen når include_deleted=true).
        work_min = sum((e.get("duration_minutes") or 0) for e in de
                       if _alive(e) and (e.get("slice_type") or "work") != "pause")
        pause_min = sum((e.get("duration_minutes") or 0) for e in de
                        if _alive(e) and (e.get("slice_type") or "work") == "pause")
        total = work_min + pause_min
        live = [e for e in de if _alive(e)]
        first_in = live[0].get("start_time") if live else ""
        last_out = ""
        for e in reversed(live):
            if e.get("end_time"):
                last_out = e.get("end_time")
                break
        # Fase 15.35: tæl manglende stempler — uoplukket fra fortidig dato.
        missing_count = sum(1 for e in live if e.get("missing_clock"))
        out.append({
            "driver_id": did,
            "driver_name": d.get("display_name") or d.get("name") or d.get("email") or "Unknown",
            "entries": de,
            "total_minutes": total,
            # Fase 15.30: Tre tal — arbejdstid, pausetid, total tilstede.
            "work_minutes": work_min,
            "pause_minutes": pause_min,
            "first_in": first_in,
            "last_out": last_out,
            "has_open": any(not e.get("end_time") for e in live),
            "entries_count": len(live),
            # Fase 15.31: antal soft-deleted entries for chaufføren (for
            # admin's UI "Vis slettede" badge-tæller). Beregnes via separat
            # aggregering så det altid er korrekt — også når
            # include_deleted=false og entries-listen er filtreret.
            "deleted_count": deleted_count_by_driver.get(did, 0),
            # Fase 15.35: antal manglende stempler (uoplukket fra past date).
            "missing_clock_count": missing_count,
        })
    # Sortér: arbejdere først (har entries), så sorter på navn.
    out.sort(key=lambda x: (-len(x["entries"]), (x["driver_name"] or "").lower()))
    # Fase 15.35: missing_only=true filter — returnér KUN chauffører med
    # mindst én manglende stempel. Bruges af "Vis kun manglende stempel"-
    # filter i admin's Detaljeret liste.
    if missing_only:
        out = [r for r in out if r.get("missing_clock_count", 0) > 0]
    return out


# Fase 15.36 (2026-02-22): Manuel trigger til søndags-påmindelses-mailen.
# Logistics admin og super admin kan trykke "Send påmindelse nu" — bruger samme
# kode-sti som cron-jobbet kører hver søndag kl. 18:00 Europe/Copenhagen.
@api_router.post("/admin/missing-clock/send-reminders")
async def admin_send_missing_clock_reminders(
    days_back: int = 7,
    token_payload: dict = Depends(require_role("logistics_admin", "super_admin")),
):
    """Sender påmindelse til alle chauffører i admin's firma der har åbne
    (missing_clock) entries i de seneste `days_back` dage. Super-admin (uden
    company_id) sender på tværs af alle firmaer.

    Returns: {sent, skipped, drivers: [{driver_id, name, email, entries_count,
    delivered, error}]}
    """
    days_back = max(1, min(int(days_back or 7), 90))
    la_company = token_payload.get("company_id")
    scope_company: Optional[str] = None
    if la_company and la_company != SUPER_ADMIN_BYPASS:
        scope_company = la_company
    try:
        result = await send_weekly_missing_clock_reminders(
            days_back=days_back, company_id=scope_company,
        )
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("admin_send_missing_clock_reminders failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Kunne ikke sende påmindelser: {e}")


# --------------------------------------------------------------------------- #
# Fase 15.40 (2026-02-22): Klient-platformsfunktioner API
# --------------------------------------------------------------------------- #

class FeatureUpdate(BaseModel):
    """Body for PATCH /admin/companies/{company_id}/features/{feature_key}."""
    is_enabled: bool


@api_router.get("/admin/companies/{company_id}/features")
async def admin_list_company_features(
    company_id: str,
    token_payload: dict = Depends(require_super_admin),
):
    """Returnerer fuldt feature-map for én klient (firma). Inkluderer features
    der ALDRIG har været toggle'd — de vises med default-værdien (DISABLED)."""
    feats = await get_company_features(company_id)
    return {"company_id": company_id, "features": list(feats.values())}


@api_router.patch("/admin/companies/{company_id}/features/{feature_key}")
async def admin_set_company_feature(
    company_id: str,
    feature_key: str,
    body: FeatureUpdate,
    token_payload: dict = Depends(require_super_admin),
):
    """Toggler én feature pr. klient. Upsert i `client_features`-kollektionen
    med audit-felter (`updated_at` + `updated_by_email`)."""
    if feature_key not in FEATURE_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Ukendt feature-key: '{feature_key}'. Gyldige nøgler: {sorted(FEATURE_KEYS.keys())}",
        )
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id påkrævet")
    # Verificér at firmaet rent faktisk findes — undgå "spøgelses-features".
    company_exists = await _raw_db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "name": 1})
    if not company_exists:
        raise HTTPException(status_code=404, detail=f"Klient/firma med id '{company_id}' findes ikke")

    now_iso = datetime.now(timezone.utc).isoformat()
    by_email = token_payload.get("email") or ""
    by_user_id = token_payload.get("sub") or ""
    await _raw_db.client_features.update_one(
        {"company_id": company_id, "feature_key": feature_key},
        {"$set": {
            "company_id": company_id,
            "feature_key": feature_key,
            "is_enabled": bool(body.is_enabled),
            "updated_at": now_iso,
            "updated_by_user_id": by_user_id,
            "updated_by_email": by_email,
        }},
        upsert=True,
    )
    # Log til activity_log så super-admin kan spore ændringer.
    await _raw_db.activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": by_user_id,
        "email": by_email,
        "action": "feature_toggle",
        "role": "super_admin",
        "company_id": company_id,
        "company_name": company_exists.get("name") or "",
        "feature_key": feature_key,
        "is_enabled": bool(body.is_enabled),
        "timestamp": now_iso,
    })
    feats = await get_company_features(company_id)
    return {"company_id": company_id, "features": list(feats.values())}


@api_router.get("/clients/me/features")
async def clients_me_features(token_payload: dict = Depends(get_current_user_payload)):
    """Returnerer kompakt {key: bool}-dict for den aktuelle brugers klient.
    Bruges af frontend's central `useFeatures()`-hook for at gate UI."""
    cid = token_payload.get("company_id") or ""
    features = await get_features_dict_for_user(cid)
    return {"company_id": cid, "features": features}


    updated = await db.driver_sessions.find_one({"driver_name": driver_name}, {"_id": 0})
    return updated

@api_router.delete("/driver-session/{driver_name}")
async def end_driver_session(driver_name: str):
    result = await db.driver_sessions.delete_one({"driver_name": driver_name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session ended"}

# ============= PDF ARCHIVE ENDPOINTS =============

@api_router.get("/pdf-archive")
async def get_pdf_archives(driver_name: Optional[str] = None, days: int = 365):
    from datetime import timedelta
    
    # Clean up expired PDFs (older than 1 year)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    await db.pdf_archives.delete_many({"created_at": {"$lt": cutoff}})
    
    query = {}
    if driver_name:
        query["driver_name"] = driver_name
    
    # Return list without file_data for efficiency (up to 1000 entries = ~3 years for one driver)
    archives = await db.pdf_archives.find(query, {"_id": 0, "file_data": 0}).sort("created_at", -1).to_list(1000)
    # Add has_pdf flag (whether file_data is non-empty) without loading the heavy field
    for a in archives:
        a["has_pdf"] = await db.pdf_archives.count_documents({
            "id": a["id"],
            "file_data": {"$exists": True, "$nin": ["", None]}
        }) > 0

    # Fase 18.3 (2026-02-28): Berig hver dagrapport med `time_summary` baseret
    # på driver_time_entries (samme helper som /driver-archive). Det betyder
    # PDF-Arkiv viser nu flere IND/UD-vinduer + pause-totaler i samme format
    # som "Pr. chauffør"-visningen — start/slut/pause er den autoritative kilde.
    if archives:
        # Slå chauffør-id'er op for alle unikke navne i resultatet.
        names = list({a.get("driver_name", "") for a in archives if a.get("driver_name")})
        users = await _raw_db.users.find(
            {"role": "driver",
             "$or": [{"name": {"$in": names}}, {"display_name": {"$in": names}}]},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1},
        ).to_list(500)
        # Map chauffør-navn -> liste af mulige driver_id'er (alias-håndtering)
        name_to_ids: Dict[str, List[str]] = {}
        for u in users:
            for nm in (u.get("name", ""), u.get("display_name", "")):
                if nm:
                    name_to_ids.setdefault(nm, []).append(u["id"])
        all_ids = list({i for ids in name_to_ids.values() for i in ids})
        dates_set = list({a.get("report_date", "") for a in archives if a.get("report_date")})
        entries_by_key: Dict[tuple, list] = {}
        if all_ids and dates_set:
            ents = await _raw_db.driver_time_entries.find(
                {"driver_id": {"$in": all_ids},
                 "date": {"$in": dates_set},
                 "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
                {"_id": 0},
            ).to_list(20000)
            # Map (driver_id, date) -> entries
            for e in ents:
                k = (e.get("driver_id", ""), e.get("date", ""))
                entries_by_key.setdefault(k, []).append(e)

        _now_dt = datetime.now(DK_TZ)
        _today_str = _now_dt.strftime("%Y-%m-%d")
        _now_hhmm = _now_dt.strftime("%H:%M")
        for a in archives:
            ids_for_name = name_to_ids.get(a.get("driver_name", ""), [])
            d = a.get("report_date", "")
            day_entries: list = []
            for did in ids_for_name:
                day_entries.extend(entries_by_key.get((did, d), []))
            if day_entries:
                a["time_summary"] = _summarize_day_entries(
                    day_entries,
                    today_str=(_today_str if d == _today_str else ""),
                    now_hhmm=(_now_hhmm if d == _today_str else ""),
                )
            else:
                a["time_summary"] = None

    return archives

@api_router.get("/pdf-archive/{archive_id}")
async def get_pdf_archive(archive_id: str):
    archive = await db.pdf_archives.find_one({"id": archive_id}, {"_id": 0})
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    
    # If file_data exists, return as downloadable PDF
    file_data = archive.get("file_data", "")
    if file_data:
        import io
        pdf_bytes = base64.b64decode(file_data)
        file_name = archive.get("file_name", "rapport.pdf")
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
        )
    
    # Fallback: return JSON metadata
    return archive

@api_router.post("/pdf-archive/zip")
async def get_pdf_archives_zip(payload: dict = Body(...)):
    """Bulk download multiple PDF archives as a ZIP file. Body: {"ids": [...], "filename": "optional.zip"}"""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    ids = payload.get("ids", []) or []
    if not ids:
        raise HTTPException(status_code=400, detail="No archive IDs provided")

    archives = await db.pdf_archives.find({"id": {"$in": ids}}, {"_id": 0}).to_list(1000)
    if not archives:
        raise HTTPException(status_code=404, detail="No archives found")

    buf = io.BytesIO()
    used_names = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for a in archives:
            file_data = a.get("file_data", "")
            if not file_data:
                continue
            try:
                pdf_bytes = base64.b64decode(file_data)
            except Exception:
                continue
            base_name = a.get("file_name") or f"dagrapport_{a.get('report_date','')}_{a.get('driver_name','rapport')}.pdf"
            # Avoid duplicate file names
            n = used_names.get(base_name, 0) + 1
            used_names[base_name] = n
            if n > 1:
                stem, dot, ext = base_name.rpartition(".")
                base_name = f"{stem}_{n}.{ext}" if dot else f"{base_name}_{n}"
            zf.writestr(base_name, pdf_bytes)

    buf.seek(0)
    zip_name = payload.get("filename") or f"pdf_archive_{datetime.now(DK_TZ).strftime('%Y%m%d_%H%M')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'}
    )

@api_router.post("/pdf-archive")
async def save_pdf_archive(
    driver_name: str,
    vehicle_reg: str = "",
    plads: str = "",
    report_date: str = "",
    file_name: str = "",
    file_data: str = "",
    total_tours: int = 0,
    completed_tours: int = 0,
    total_weight: float = 0,
    start_time: str = "",
    end_time: str = ""
):
    from datetime import timedelta
    
    archive = PDFArchive(
        driver_name=driver_name,
        vehicle_reg=vehicle_reg,
        plads=plads,
        report_date=report_date,
        file_name=file_name,
        file_data=file_data,
        total_tours=total_tours,
        completed_tours=completed_tours,
        total_weight=total_weight,
        start_time=start_time,
        end_time=end_time,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    )
    
    await db.pdf_archives.insert_one(archive.model_dump())
    return {"id": archive.id, "message": "PDF archived successfully"}

@api_router.delete("/pdf-archive/{archive_id}")
async def delete_pdf_archive(archive_id: str):
    result = await db.pdf_archives.delete_one({"id": archive_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Archive not found")
    return {"message": "Archive deleted"}

# ============= ENHANCED MESSAGE ENDPOINTS =============

@api_router.get("/messages/driver/{driver_name}")
async def get_driver_messages(driver_name: str, _auth: dict = Depends(get_current_user_payload)):
    """Get all messages for a specific driver (both to and from)"""
    messages = await db.messages.find({
        "$or": [
            {"to_driver_name": driver_name},
            {"from_driver_name": driver_name}
        ]
    }, {"_id": 0}).sort("created_at", -1).to_list(100)
    return messages

@api_router.get("/messages/admin")
async def get_admin_messages(_auth: dict = Depends(get_current_user_payload)):
    """Get all messages sent to admin"""
    messages = await db.messages.find({"to_admin": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return messages

@api_router.post("/messages/driver")
async def send_message_from_driver(
    from_driver_name: str,
    content: str,
    _auth: dict = Depends(get_current_user_payload),
):
    """Driver sends message to admin"""
    message = Message(
        from_admin=False,
        from_driver_name=from_driver_name,
        to_admin=True,
        content=content
    )
    await db.messages.insert_one(message.model_dump())
    return message.model_dump()

# ============= ADMIN DAILY OVERVIEW =============

@api_router.get("/admin/daily-overview")
async def get_daily_overview(date: Optional[str] = None):
    """Get comprehensive daily overview for admin dashboard"""
    if not date:
        date = get_dk_date_str()
    
    # Filtered by date + only needed fields (no receipt_image)
    all_tours = await db.tours.find(
        {"date": date},
        {"_id": 0, "plads": 1, "is_pause": 1, "completed": 1, "on_way": 1, "weight": 1}
    ).to_list(1000)
    
    all_plads = await db.plads.find({"active": True}, {"_id": 0, "name": 1}).to_list(100)
    plads_names = [p["name"] for p in all_plads]
    
    # Calculate stats per plads
    plads_stats = {}
    for plads_name in plads_names:
        plads_tours = [t for t in all_tours if t.get("plads") == plads_name and not t.get("is_pause")]
        completed = [t for t in plads_tours if t.get("completed")]
        on_way = [t for t in plads_tours if t.get("on_way") and not t.get("completed")]
        waiting = [t for t in plads_tours if not t.get("completed") and not t.get("on_way")]
        
        plads_stats[plads_name] = {
            "total": len(plads_tours),
            "completed": len(completed),
            "on_way": len(on_way),
            "waiting": len(waiting),
            "total_weight": sum(t.get("weight", 0) or 0 for t in completed),
            "progress_percent": round((len(completed) / len(plads_tours) * 100) if plads_tours else 0)
        }
    
    # Overall totals
    total_tours = len([t for t in all_tours if not t.get("is_pause")])
    total_completed = len([t for t in all_tours if t.get("completed") and not t.get("is_pause")])
    total_on_way = len([t for t in all_tours if t.get("on_way") and not t.get("completed")])
    total_waiting = total_tours - total_completed - total_on_way
    total_weight = sum(t.get("weight", 0) or 0 for t in all_tours if t.get("completed"))
    
    # Get active drivers (from sessions)
    active_sessions = await db.driver_sessions.find({}, {"_id": 0}).to_list(100)
    
    # Get unread messages to admin
    unread_messages = await db.messages.count_documents({"to_admin": True, "read": False})
    
    return {
        "date": date,
        "totals": {
            "total_tours": total_tours,
            "completed": total_completed,
            "on_way": total_on_way,
            "waiting": total_waiting,
            "total_weight": total_weight,
            "progress_percent": round((total_completed / total_tours * 100) if total_tours else 0)
        },
        "plads_stats": plads_stats,
        "active_drivers": len(active_sessions),
        "active_sessions": active_sessions,
        "unread_messages": unread_messages
    }


# ============= SEED DATA =============

@api_router.post("/seed")
async def seed_data():
    existing = await db.drivers.count_documents({})
    if existing > 0:
        # Still seed plads if not seeded
        existing_plads = await db.plads.count_documents({})
        if existing_plads == 0:
            default_plads = [
                {"name": "Glostrup", "city": "Glostrup", "address": "Ejby Industrivej 28, 2600 Glostrup", "lat": 55.6787, "lng": 12.3978},
                {"name": "Herlev", "city": "Herlev", "address": "Marielundvej 43, 2730 Herlev", "lat": 55.7245, "lng": 12.4386},
                {"name": "Hillerød", "city": "Hillerød", "address": "Hillerødsholmsalle 70, 3400 Hillerød", "lat": 55.9263, "lng": 12.3008},
                {"name": "Ballerup", "city": "Ballerup", "address": "Energivej 25, 2750 Ballerup", "lat": 55.7312, "lng": 12.3605},
                {"name": "Skipstrup", "city": "Ålsgårde", "address": "Skibstrupvej 1, 3140 Ålsgårde", "lat": 56.0742, "lng": 12.5641},
                {"name": "Helsingør", "city": "Helsingør", "address": "Energivej 1, 3000 Helsingør", "lat": 56.0365, "lng": 12.6130},
                {"name": "Køge", "city": "Køge", "address": "Tangmosevej 100, 4600 Køge", "lat": 55.4561, "lng": 12.1855},
                {"name": "Bjæverskov", "city": "Bjæverskov", "address": "Billesborgvej 40, 4632 Bjæverskov", "lat": 55.3865, "lng": 12.0403},
                {"name": "St. Heddinge", "city": "Store Heddinge", "address": "Hovedgaden 92, 4660 Store Heddinge", "lat": 55.3096, "lng": 12.3882},
                {"name": "Måløv", "city": "Måløv", "address": "Måløv Byvej 229, 2760 Måløv", "lat": 55.7472, "lng": 12.3231},
            ]
            for p in default_plads:
                plads = Plads(**p)
                await db.plads.insert_one(plads.model_dump())
        else:
            # Update existing plads with location data
            seed_data = {
                "Glostrup": {"city": "Glostrup", "address": "Ejby Industrivej 28, 2600 Glostrup", "lat": 55.6787, "lng": 12.3978},
                "Herlev": {"city": "Herlev", "address": "Marielundvej 43, 2730 Herlev", "lat": 55.7245, "lng": 12.4386},
                "Hillerød": {"city": "Hillerød", "address": "Hillerødsholmsalle 70, 3400 Hillerød", "lat": 55.9263, "lng": 12.3008},
                "Ballerup": {"city": "Ballerup", "address": "Energivej 25, 2750 Ballerup", "lat": 55.7312, "lng": 12.3605},
                "Skipstrup": {"city": "Ålsgårde", "address": "Skibstrupvej 1, 3140 Ålsgårde", "lat": 56.0742, "lng": 12.5641},
                "Helsingør": {"city": "Helsingør", "address": "Energivej 1, 3000 Helsingør", "lat": 56.0365, "lng": 12.6130},
                "Køge": {"city": "Køge", "address": "Tangmosevej 100, 4600 Køge", "lat": 55.4561, "lng": 12.1855},
                "Bjæverskov": {"city": "Bjæverskov", "address": "Billesborgvej 40, 4632 Bjæverskov", "lat": 55.3865, "lng": 12.0403},
                "St. Heddinge": {"city": "Store Heddinge", "address": "Hovedgaden 92, 4660 Store Heddinge", "lat": 55.3096, "lng": 12.3882},
                "Måløv": {"city": "Måløv", "address": "Måløv Byvej 229, 2760 Måløv", "lat": 55.7472, "lng": 12.3231},
            }
            for name, data in seed_data.items():
                await db.plads.update_one(
                    {"name": name},
                    {"$set": data},
                    upsert=False
                )
        return {"message": "Data already seeded", "driver_count": existing}
    
    default_drivers = [
        {"name": "Dennis", "plate": "DV 10239", "area": "Glostrup", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Zekiye", "plate": "DY 84184", "area": "Herlev", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Emrer", "plate": "EC 25026", "area": "Hillerød", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Ferdat", "plate": "EN 80295", "area": "Ballerup", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "FRI", "plate": "DM 13404", "area": "Skipstrup", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Rafael", "plate": "DR 30142", "area": "Helsingør", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "John", "plate": "DS 78545", "area": "Køge", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Thomas", "plate": "DY 84177", "area": "Bjæverskov", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Tony", "plate": "EB 64418", "area": "St. Heddinge", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Murat", "plate": "EN 80294", "area": "Hårlev", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Nihat", "plate": "EC 66505", "area": "Gribskov", "facility": "ARGO", "phone": "", "email": ""},
        {"name": "Berrin", "plate": "BN55130", "area": "Glostrup", "facility": "ARGO", "phone": "", "email": ""},
    ]
    
    for driver_data in default_drivers:
        driver = Driver(**driver_data)
        await db.drivers.insert_one(driver.model_dump())
    
    # Seed default plads
    default_plads = [
        {"name": "Glostrup", "city": "Glostrup", "address": "Ejby Industrivej 28, 2600 Glostrup", "lat": 55.6787, "lng": 12.3978},
        {"name": "Herlev", "city": "Herlev", "address": "Marielundvej 43, 2730 Herlev", "lat": 55.7245, "lng": 12.4386},
        {"name": "Hillerød", "city": "Hillerød", "address": "Hillerødsholmsalle 70, 3400 Hillerød", "lat": 55.9263, "lng": 12.3008},
        {"name": "Ballerup", "city": "Ballerup", "address": "Energivej 25, 2750 Ballerup", "lat": 55.7312, "lng": 12.3605},
        {"name": "Skipstrup", "city": "Ålsgårde", "address": "Skibstrupvej 1, 3140 Ålsgårde", "lat": 56.0742, "lng": 12.5641},
        {"name": "Helsingør", "city": "Helsingør", "address": "Energivej 1, 3000 Helsingør", "lat": 56.0365, "lng": 12.6130},
        {"name": "Køge", "city": "Køge", "address": "Tangmosevej 100, 4600 Køge", "lat": 55.4561, "lng": 12.1855},
        {"name": "Bjæverskov", "city": "Bjæverskov", "address": "Billesborgvej 40, 4632 Bjæverskov", "lat": 55.3865, "lng": 12.0403},
        {"name": "St. Heddinge", "city": "Store Heddinge", "address": "Hovedgaden 92, 4660 Store Heddinge", "lat": 55.3096, "lng": 12.3882},
        {"name": "Måløv", "city": "Måløv", "address": "Måløv Byvej 229, 2760 Måløv", "lat": 55.7472, "lng": 12.3231},
    ]
    
    existing_plads = await db.plads.count_documents({})
    if existing_plads == 0:
        for p in default_plads:
            plads = Plads(**p)
            await db.plads.insert_one(plads.model_dump())
    else:
        # Update existing plads with address/coordinates if missing
        for p in default_plads:
            await db.plads.update_one(
                {"name": p["name"], "$or": [{"address": {"$exists": False}}, {"address": ""}, {"lat": None}, {"lat": {"$exists": False}}]},
                {"$set": {"city": p["city"], "address": p["address"], "lat": p["lat"], "lng": p["lng"]}}
            )
    
    return {"message": "Seeded default drivers and plads", "driver_count": len(default_drivers)}

# ============= CONTAINER ORDER SYSTEM ENDPOINTS =============

# Location endpoints

async def _lookup_site_by_code(code: str) -> Optional[dict]:
    """Resolve a 4-digit access code to a "site" (legacy locations OR new plads).

    The legacy `locations` collection has been migrated into `plads` for multi-
    tenant setups (each plads can carry its own `code` / `location_code`). To
    keep the QR-code customer order flow + `order` user login working in both
    worlds this helper checks `plads` first (new path) and falls back to the
    legacy `locations` collection. Returns a location-shaped dict or `None`.
    Uses `_raw_db` because the lookup endpoints are public and must work
    regardless of the current tenant context.
    """
    if not code:
        return None
    # New path: plads carrying a customer-facing code
    plads = await _raw_db.plads.find_one(
        {"$or": [{"location_code": code}, {"code": code}],
         "active": {"$ne": False}},
        {"_id": 0},
    )
    if plads:
        return {
            "id": plads.get("id"),
            "code": plads.get("code") or plads.get("location_code") or code,
            "name": plads.get("name", ""),
            "address": plads.get("address", "") or "",
            "city": plads.get("city", "") or "",
            "active": plads.get("active", True),
            "materials": plads.get("materials") or [],
            "inactive_materials": plads.get("inactive_materials") or [],
            "containers_per_material": plads.get("containers_per_material") or 6,
            "company_id": plads.get("company_id"),
            "partner_materials": plads.get("partner_materials") or {},
            "assigned_logistics_company_ids": plads.get("assigned_logistics_company_ids") or [],
            # Fase 9 refactor (2026-06-18): CO2-kategori-mapping pr. materiale
            "material_co2_categories": plads.get("material_co2_categories") or {},
            "_source": "plads",
            "_plads_id": plads.get("id"),
        }
    # Legacy fallback
    location = await _raw_db.locations.find_one(
        {"code": code, "active": True}, {"_id": 0},
    )
    if location:
        location["_source"] = "locations"
        return location
    return None

@api_router.get("/locations")
async def get_locations():
    locations = await db.locations.find({}, {"_id": 0}).to_list(100)
    return locations

@api_router.get("/locations/code/{code}")
async def get_location_by_code(code: str):
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location

@api_router.get("/locations/{location_id}")
async def get_location(location_id: str):
    location = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location

@api_router.post("/locations")
async def create_location(location: LocationCreate):
    # Check if code already exists
    existing = await db.locations.find_one({"code": location.code})
    if existing:
        raise HTTPException(status_code=400, detail="Location code already exists")
    
    # Use default materials if none provided
    materials = location.materials if location.materials else DEFAULT_MATERIALS
    
    location_obj = Location(
        code=location.code,
        name=location.name,
        materials=materials
    )
    await db.locations.insert_one(location_obj.model_dump())
    return location_obj.model_dump()

@api_router.put("/locations/{location_id}")
async def update_location(location_id: str, update: LocationUpdate):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data")
    
    # If changing code, check it doesn't exist
    if "code" in update_data:
        existing = await db.locations.find_one({"code": update_data["code"], "id": {"$ne": location_id}})
        if existing:
            raise HTTPException(status_code=400, detail="Location code already exists")
    
    result = await db.locations.update_one({"id": location_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Location not found")
    
    location = await db.locations.find_one({"id": location_id}, {"_id": 0})
    return location

@api_router.delete("/locations/{location_id}")
async def delete_location(location_id: str):
    result = await db.locations.delete_one({"id": location_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Location not found")
    return {"message": "Location deleted"}

# Customer address endpoints
@api_router.get("/customer-addresses")
async def get_customer_addresses(location_code: Optional[str] = None):
    query = {}
    if location_code:
        query["location_code"] = location_code
    addresses = await db.customer_addresses.find(query, {"_id": 0}).to_list(500)
    return addresses

@api_router.get("/customer-addresses/{address_id}")
async def get_customer_address(address_id: str):
    address = await db.customer_addresses.find_one({"id": address_id}, {"_id": 0})
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    return address

@api_router.post("/customer-addresses")
async def create_customer_address(address: CustomerAddressCreate):
    address_obj = CustomerAddress(**address.model_dump())
    await db.customer_addresses.insert_one(address_obj.model_dump())
    return address_obj.model_dump()

@api_router.put("/customer-addresses/{address_id}")
async def update_customer_address(address_id: str, update: CustomerAddressUpdate):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data")
    
    result = await db.customer_addresses.update_one({"id": address_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    
    address = await db.customer_addresses.find_one({"id": address_id}, {"_id": 0})
    return address

@api_router.delete("/customer-addresses/{address_id}")
async def delete_customer_address(address_id: str):
    result = await db.customer_addresses.delete_one({"id": address_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"message": "Address deleted"}

# Container order endpoints
@api_router.get("/container-orders")
async def get_container_orders(location_code: Optional[str] = None, status: Optional[str] = None):
    query = {}
    if location_code:
        query["location_code"] = location_code
    if status:
        query["status"] = status
    
    orders = await db.container_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return orders

@api_router.get("/container-orders/{order_id}")
async def get_container_order(order_id: str):
    order = await db.container_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@api_router.post("/container-orders")
async def create_container_order(order: ContainerOrderCreate):
    # Get location info
    location = await _lookup_site_by_code(order.location_code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    # Get address info
    address = await db.customer_addresses.find_one({"id": order.address_id}, {"_id": 0})
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    # Convert order_date
    if order.order_date == "today":
        order_date = get_dk_date_str()
    elif order.order_date == "tomorrow":
        order_date = (datetime.now(DK_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        order_date = order.order_date

    # Fase 9 (2026-06-17): Snapshot the CO2-type (name + factor) so that
    # historical orders keep correct CO2 even if the kunde later renames or
    # changes the factor in their library.
    co2_type_name = ""
    co2_factor = 0.0
    if order.co2_type_id:
        co2_doc = await _raw_db.co2_types.find_one({"id": order.co2_type_id}, {"_id": 0})
        if co2_doc:
            co2_type_name = co2_doc.get("name", "")
            co2_factor = float(co2_doc.get("factor", 0) or 0)

    order_obj = ContainerOrder(
        location_code=order.location_code,
        location_name=location["name"],
        address_id=order.address_id,
        customer_name=address["name"],
        customer_address=address["address"],
        container_number=address["container_number"],
        material=order.material,
        co2_type_id=order.co2_type_id,
        co2_type_name=co2_type_name,
        co2_factor=co2_factor,
        order_date=order_date,
        priority=order.priority,
        comment=order.comment
    )
    
    await db.container_orders.insert_one(order_obj.model_dump())
    return order_obj.model_dump()

# ============= NEW STRUCTURED ORDER SYSTEM =============

class StructuredOrderCreate(BaseModel):
    location_code: str
    material: str
    # Fase 9 (2026-06-17): CO2-type linked to customer's CO2 library
    co2_type_id: str = ""
    container_number: str  # "Container 1", "Container 2", etc.
    priority: str = "normal"  # haster, normal, senere
    comment: str = ""
    custom_address: str = ""  # Customer-edited address
    custom_container_id: str = ""  # Customer-edited container ID
    order_date: str = ""  # Customer-selected date (YYYY-MM-DD), empty = today
    open_from: str = ""  # Opening time at delivery address (HH:MM)
    open_to: str = ""  # Closing time at delivery address (HH:MM)
    # tour_type: "normal" | "flyt" (Byt container) | "vaerksted" (Til værksted)
    # | "afhent_vaerksted" (Afhent fra værksted)
    tour_type: str = "normal"
    plads_name: str = ""  # Optional - overrides the auto-derived plads for the tour
                          # (used by order users who picked a specific plads/city)
    # Leveringsadresse linking — when set, the order is bound to a row in
    # `delivery_addresses` (see Leveringsadresser-tab). When `alternative_*`
    # is set, the primary was closed on the order date and the user picked
    # an alternative — both IDs are persisted for audit/history.
    delivery_address_id: str = ""
    alternative_delivery_address_id: str = ""
    # Fri-tekst alternativ adresse: brugeren har klikket "Vil du udfylde
    # adressen selv?" og indtastet en helt brugerdefineret adresse-streng
    # som ikke matcher noget i biblioteket. Ingen validering, da der ikke
    # er nogen kilde-data at validere imod. Bruges sidestillet med (eller
    # i stedet for) `alternative_delivery_address_id`.
    manual_alternative_address: str = ""
    # ===== WORKSHOP-FELTER (Batch 2) =====
    # For tour_type in ("vaerksted", "afhent_vaerksted") -- kunden vælger et
    # værksted fra CA-biblioteket. workshop_name/address/phone er en snapshot
    # af værkstedet på bestillingstidspunktet (audit + chauffør får dem direkte
    # på touren uden at lookuppe). workshop_override=True betyder brugeren
    # manuelt har overskrevet en eller flere felter med fri tekst.
    workshop_id: str = ""
    workshop_name: str = ""
    workshop_address: str = ""
    workshop_phone: str = ""
    workshop_override: bool = False
    # Pr. 2026-06-15 brugerkrav (runde 6): Den logistik-partner medarbejderen
    # havde valgt i partner-pickeren på bestillingssiden. Persisteres på ordren
    # så "Mine bestillinger" / "Alle bestillinger" kan filtreres strikt per
    # partner — så samme lokation med flere partnere ikke deler ordre-historik.
    partner_id: str = ""
    # Fase 15.16 (2026-02-XX): Tilpasset bestilling kan være "Estimat" — et
    # forventet ressourcebehov uden konkret container-ID. Når tour_type ==
    # "estimat" gemmes også estimated_count (antal containere). Den valideres
    # ikke som en almindelig opgave (ingen leveringsadresse osv.).
    estimated_count: int = 0
    # Fase 15.41 (2026-02-22): "Løs afhentning" — kunden ejer ikke containere;
    # chauffør medbringer egne. Et separat felt fra estimated_count fordi det
    # repræsenterer noget andet (skøn til chauffør om hvor mange tomme
    # containere de skal medbringe). Validation: når tour_type ==
    # "loes_afhentning" skal feltet være > 0.
    loose_estimated_count: int = 0

# Model for container override (customer editable saved data)
class ContainerOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    location_code: str
    material: str
    container_label: str  # "Container 1", "Container 2", etc.
    custom_address: str = ""
    custom_container_id: str = ""
    open_from: str = ""
    open_to: str = ""
    # Lock state — when True, employees can't change the field during an order.
    locked_address: bool = False
    locked_hours: bool = False
    # Optional 3rd lock: make the container-id read-only for employees too.
    locked_container_id: bool = False
    # Reference to a row in `capacity_measures` (LA-bibliotek). Surfaces on the
    # order flow as a read-only chip and is snapshotted on the container_order.
    capacity_measure_id: str = ""
    # Pr. 2026-06-15 brugerkrav: containere kan være knyttet til en bestemt
    # logistik-partner. Tom værdi (""=ingen partner) bevarer bagudkompatibilitet —
    # disse containere er synlige uanset hvilken partner medarbejderen har
    # valgt på bestillingssiden.
    partner_id: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


async def _container_count_for(code: str, material: str, default: int = 0,
                               partner_id: str = "") -> int:
    """How many containers does this plads expose for `material`?
    Stored as a document in `container_counts`. Defaults to 0 — new pladser
    start completely blank and the location_admin uses '+ Tilføj container'
    to add new slots one at a time.

    Pr. 2026-06-15 (runde 3): COPY-ON-WRITE-semantik mellem legacy/per-partner:
      * Hvis der findes en per-partner count for (location, material, partner_id),
        bruges KUN den (legacy ignoreres for denne partner).
      * Ellers falder vi tilbage til legacy/global count (delt skabelon).
      * Tom partner_id matcher KUN legacy/global rækker.
    Dette eliminerer dobbelt-tælling efter LA tilføjer en container under
    en specifik partner.
    """
    if partner_id:
        # Per-partner først — fuldstændig erstatning hvis sat
        doc = await _raw_db.container_counts.find_one(
            {"location_code": code, "material": material, "partner_id": partner_id},
            {"_id": 0, "count": 1},
        )
        if doc and isinstance(doc.get("count"), int) and doc["count"] > 0:
            return doc["count"]
    # Fallback til legacy (også når partner_id er tom)
    doc = await _raw_db.container_counts.find_one(
        {"location_code": code, "material": material,
         "$or": [{"partner_id": {"$exists": False}}, {"partner_id": ""}]},
        {"_id": 0, "count": 1},
    )
    if doc and isinstance(doc.get("count"), int) and doc["count"] > 0:
        return doc["count"]
    return default


async def _can_see_incomplete_containers(code: str, authorization: Optional[str]) -> bool:
    """True if the bearer in the Authorization header is allowed to see
    container slots that haven't had their required fields (address +
    container number) filled in yet. Only super_admin, customer_admin (same
    company as the plads) and location_admin (managing that plads) qualify."""
    if not authorization:
        return False
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            return False
        from auth import decode_token  # local import to avoid cycles
        payload = decode_token(token)
    except Exception:
        return False
    user_id = payload.get("sub") if payload else None
    if not user_id:
        return False
    user = await _raw_db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return False
    role = user.get("role")
    if role == "super_admin":
        return True
    plads = await _raw_db.plads.find_one({"location_code": code}, {"_id": 0, "company_id": 1})
    if not plads or user.get("company_id") != plads.get("company_id"):
        return False
    if role == "customer_admin":
        return True
    if role == "location_admin":
        managed = set(user.get("assigned_plads_ids") or [])
        if user.get("location_code"):
            managed.add(user["location_code"])
        return code in managed
    return False


@api_router.get("/locations/{code}/containers")
async def get_location_containers(code: str, material: str = "",
                                   partner_id: str = "",
                                   authorization: Optional[str] = Header(default=None, alias="Authorization")):
    """Get containers for a material at a location, merged with customer overrides.

    Containers that don't have BOTH a custom_address and a custom_container_id
    are considered "incomplete" (a fresh slot the admin hasn't fully set up
    yet). Incomplete containers are hidden from employees / QR-customers and
    only returned to admin callers (super/customer/location admin).

    `partner_id` (NEW pr. 2026-06-15): scope materials/containers til en
    bestemt logistik-partner. Tom partner_id ⇒ returnér ALLE (LA-overblik) +
    legacy data uden partner_id-felt.
    """
    can_see_incomplete = await _can_see_incomplete_containers(code, authorization)
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Look up the plads doc for this location (incl. partner_materials).
    # Bruger _raw_db så tenant-filter ikke skjuler pladser for offentlige QR-kald.
    plads = await _raw_db.plads.find_one({"location_code": code}, {"_id": 0})

    location_address = location.get("address") or (plads.get("address", "") if plads else "")
    location_city = location.get("city") or (plads.get("city", "") if plads else "")

    # Resolve list of materials for this view.
    # Pr. 2026-06-15 brugerkrav (runde 5): Materialer skal afspejle hvad
    # bestillingssiden VIRKELIG viser — i real-time.
    #
    #   * Med `partner_id` → strict scope = `partner_materials[partner_id]`.
    #   * Uden partner_id, hvis pladsen er "partner-aware" (har MINDST ÉN
    #     non-tom entry i `partner_materials`) → returnér UNIONEN af alle
    #     partneres materialer. Legacy `materials`-listen ignoreres her
    #     (det er den gamle pre-partner-liste der nu ofte indeholder
    #     forældede navne brugeren har slettet på bestillingssiden).
    #   * Uden partner_id og INGEN partner_materials → falder tilbage til
    #     legacy `location.materials` (bagudkompatibilitet for pladser der
    #     aldrig har brugt partner-flowet).
    if partner_id and plads:
        partner_materials_map = plads.get("partner_materials") or {}
        materials = list(partner_materials_map.get(partner_id) or [])
    else:
        partner_materials_map = (plads or {}).get("partner_materials") or {}
        has_any_partner_materials = any(
            (v or []) for v in partner_materials_map.values()
        )
        if has_any_partner_materials:
            union: list = []
            for pid, mats in partner_materials_map.items():
                for m in (mats or []):
                    if m and m not in union:
                        union.append(m)
            materials = union
        else:
            materials = list(location.get("materials") or [])
            if not materials:
                materials = DEFAULT_MATERIALS

    if material:
        containers_per = await _container_count_for(code, material, partner_id=partner_id)
        # Load any customer overrides for this material at this location.
        # We use _raw_db here because the order page is also reachable by
        # anonymous QR customers (no company context), so the tenant filter
        # would erroneously hide every override.
        # Brugerkrav 2026-06-15 (runde 3): COPY-ON-WRITE for overrides.
        # Per-partner overrides erstatter legacy for samme container_label;
        # legacy fungerer som "delt skabelon" indtil partner skriver over.
        ov_query_partner = {"location_code": code, "material": material}
        ov_query_legacy = {"location_code": code, "material": material,
                           "$or": [{"partner_id": {"$exists": False}}, {"partner_id": ""}]}
        if partner_id:
            ov_query_partner["partner_id"] = partner_id
        else:
            ov_query_partner = ov_query_legacy
        partner_overrides = await _raw_db.container_overrides.find(
            ov_query_partner, {"_id": 0}
        ).to_list(50)
        if partner_id:
            # Tilføj legacy overrides KUN for container_label'er der ikke har
            # en per-partner override endnu.
            seen_labels = {o.get("container_label") for o in partner_overrides if o.get("partner_id")}
            legacy = await _raw_db.container_overrides.find(
                ov_query_legacy, {"_id": 0}
            ).to_list(50)
            for o in legacy:
                if o.get("container_label") not in seen_labels:
                    partner_overrides.append(o)
        overrides = partner_overrides
        override_map = {o["container_label"]: o for o in overrides}
        # Pre-resolve capacity measures so the order UI can show label+volume
        # directly on the chip without a 2nd round-trip.
        cm_ids = list({o.get("capacity_measure_id") for o in overrides
                       if (o.get("capacity_measure_id") or "").strip()})
        cm_map = {}
        if cm_ids:
            for cm in await _raw_db.capacity_measures.find(
                {"id": {"$in": cm_ids}}, {"_id": 0, "id": 1, "label": 1, "volume_m3": 1},
            ).to_list(100):
                cm_map[cm["id"]] = cm
        
        containers = []
        for i in range(1, containers_per + 1):
            label = f"Container {i}"
            override = override_map.get(label, {})
            has_id = bool((override.get("custom_container_id") or "").strip())
            # Pr. 2026-06-14 brugerkrav er Leveringsadresse fjernet fra container-
            # definitionen. Kun container-nummer afgør om slotten er færdig.
            is_complete = has_id
            # Hide incomplete slots from non-admin callers — they can't fill
            # those fields in themselves so showing them would lead to a
            # dead-end UX.
            if not is_complete and not can_see_incomplete:
                continue
            containers.append({
                "number": str(i),
                "label": label,
                "material": material,
                # NEW: when there's no override yet (admin just added the slot),
                # the address starts blank — the user explicitly asked for it.
                "address": (override.get("custom_address") or "").strip(),
                "container_id": (override.get("custom_container_id") or "").strip(),
                "open_from": override.get("open_from", ""),
                "open_to": override.get("open_to", ""),
                "locked_address": bool(override.get("locked_address", False)),
                "locked_hours": bool(override.get("locked_hours", False)),
                "locked_container_id": bool(override.get("locked_container_id", False)),
                "capacity_measure_id": (override.get("capacity_measure_id") or "").strip(),
                "capacity_label": (cm_map.get(override.get("capacity_measure_id") or "") or {}).get("label", ""),
                "capacity_volume_m3": (cm_map.get(override.get("capacity_measure_id") or "") or {}).get("volume_m3"),
                "city": location_city,
                "genbrugsplads": location["name"],
                "has_override": bool(override),
                "default_address": location_address,
                "complete": is_complete,
                # Pr. 2026-06-15: hvilken logistik-partner ejer denne container
                "partner_id": (override.get("partner_id") or "").strip(),
            })
        return {
            "material": material,
            "containers": containers,
            "containers_per": containers_per,
            "location": location["name"],
            "address": location_address,
        }

    # Return all materials with their containers (just counts).
    # Brugerkrav 2026-06-15 (runde 4): Materialer er STRIKT per-partner —
    # `partner_materials[partner_id]` hentet ovenfor er nu den eneste kilde
    # når partner_id er valgt. Ingen filtrering på containere-data længere,
    # ingen sammenlæsning med legacy. Hvis listen er tom har partneren
    # ingen materialer endnu og LA skal oprette dem.
    result = []
    for mat in materials:
        containers_per = await _container_count_for(code, mat, partner_id=partner_id)
        containers = []
        for i in range(1, containers_per + 1):
            containers.append({"number": str(i), "label": f"Container {i}"})
        result.append({"material": mat, "containers": containers})
    return {"materials": result, "location": location["name"], "address": location_address}


@api_router.get("/locations/{code}/partners")
async def get_location_partners(code: str):
    """Returnerer de logistik-partnere som er knyttet til en lokation.
    Public endpoint så order-flow + LA-menu kan hente listen uden
    autentificering (QR-kiosken er også offentlig).

    Output: [{id, name, slug}, ...] — sorteret efter navn.
    """
    plads = await _raw_db.plads.find_one(
        {"location_code": code},
        {"_id": 0, "assigned_logistics_company_ids": 1, "name": 1},
    )
    if not plads:
        raise HTTPException(status_code=404, detail="Lokation ikke fundet")
    ids = [p for p in (plads.get("assigned_logistics_company_ids") or []) if p]
    if not ids:
        return {"location_code": code, "location_name": plads.get("name"), "partners": []}
    companies = await _raw_db.companies.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "slug": 1},
    ).to_list(50)
    partners = sorted(
        [{"id": c["id"], "name": c.get("name") or "", "slug": c.get("slug") or ""}
         for c in companies],
        key=lambda p: p["name"].lower(),
    )
    return {"location_code": code, "location_name": plads.get("name"), "partners": partners}



@api_router.post("/locations/{code}/containers/add")
async def add_container_to_material(code: str, data: dict,
                                    payload: dict = Depends(get_current_user_payload)):
    """Add an extra container slot to a material (the "+" button on the order
    page). Increments the persistent count by 1 (or by `delta` if provided).
    Restricted to location/customer admins.

    Pr. 2026-06-15 brugerkrav: Når flere logistik-partnere er knyttet til en
    lokation, SKAL det nye container/materiale-slot tilknyttes en specifik
    partner via `partner_id`. Hvis lokationen kun har én partner, auto-vælges
    den. Hvis lokationen ingen partnere har, accepteres tomt partner_id
    (legacy/global container).
    """
    await _require_admin_for_location(code, payload)
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    material = (data or {}).get("material", "").strip()
    if not material:
        raise HTTPException(status_code=400, detail="material required")
    delta = int((data or {}).get("delta", 1))
    if delta < 1 or delta > 50:
        raise HTTPException(status_code=400, detail="delta must be 1..50")
    partner_id = (data or {}).get("partner_id", "").strip()
    # Auto-resolve partner_id når lokationen kun har én partner (UX-skånsom).
    if not partner_id:
        plads = await _raw_db.plads.find_one({"location_code": code},
                                             {"_id": 0, "assigned_logistics_company_ids": 1})
        partners = [p for p in (plads or {}).get("assigned_logistics_company_ids") or [] if p]
        if len(partners) == 1:
            partner_id = partners[0]
        elif len(partners) > 1:
            raise HTTPException(
                status_code=400,
                detail="Vælg en logistik-partner — der er flere knyttet til denne lokation.",
            )
    # Valider at partneren faktisk er knyttet til lokationen (hvis sat)
    if partner_id:
        plads = await _raw_db.plads.find_one({"location_code": code},
                                             {"_id": 0, "assigned_logistics_company_ids": 1})
        assigned = (plads or {}).get("assigned_logistics_company_ids") or []
        if partner_id not in assigned:
            raise HTTPException(
                status_code=400,
                detail="Den valgte logistik-partner er ikke knyttet til denne lokation.",
            )
    q = {"location_code": code, "material": material}
    if partner_id:
        q["partner_id"] = partner_id
    else:
        q["$or"] = [{"partner_id": {"$exists": False}}, {"partner_id": ""}]
    current = await _container_count_for(code, material, partner_id=partner_id)
    new_count = current + delta
    set_doc = {"count": new_count, "updated_at": datetime.now(timezone.utc).isoformat()}
    if partner_id:
        set_doc["partner_id"] = partner_id
    await db.container_counts.update_one(q, {"$set": set_doc}, upsert=True)
    return {"location_code": code, "material": material, "containers_per": new_count, "partner_id": partner_id}


@api_router.delete("/locations/{code}/containers/slot")
async def delete_container_slot(code: str, material: str = "", container_label: str = "",
                                 payload: dict = Depends(get_current_user_payload)):
    """Remove a single container slot from a material. Decrements the
    container_counts by 1 (min 1) and drops any override for that label.
    Restricted to location/customer admins."""
    await _require_admin_for_location(code, payload)
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    material = (material or "").strip()
    container_label = (container_label or "").strip()
    if not material or not container_label:
        raise HTTPException(status_code=400, detail="material and container_label required")
    current = await _container_count_for(code, material)
    new_count = max(1, current - 1)
    await db.container_counts.update_one(
        {"location_code": code, "material": material},
        {"$set": {"count": new_count, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    # Remove the override doc for that label, if any
    await db.container_overrides.delete_one({
        "location_code": code, "material": material, "container_label": container_label,
    })
    return {"location_code": code, "material": material, "containers_per": new_count}


@api_router.put("/locations/{code}/containers/override")
async def save_container_override(code: str, data: dict,
                                   payload: dict = Depends(get_current_user_payload)):
    """Save customer edits for a specific container at a location. Persists
    per genbrugsplads. Restricted to location/customer admins."""
    await _require_admin_for_location(code, payload)
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    material = data.get("material", "")
    container_label = data.get("container_label", "")
    partner_id_in = (data.get("partner_id") or "").strip()

    if not material or not container_label:
        raise HTTPException(status_code=400, detail="material and container_label required")

    # Only fields explicitly present in the body get touched — this lets the
    # frontend send partial updates (e.g. just the lock state, or just the
    # address) without wiping everything else.
    fields = {}
    for k in ("custom_address", "custom_container_id", "open_from", "open_to",
              "capacity_measure_id"):
        if k in data:
            fields[k] = str(data.get(k) or "").strip()
    for k in ("locked_address", "locked_hours", "locked_container_id"):
        if k in data:
            fields[k] = bool(data.get(k))
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Find existing override.
    # Pr. 2026-06-15 (runde 3) COPY-ON-WRITE-semantik:
    #   * Hvis partner_id er sat: prøv at finde per-partner row først. Hvis
    #     den findes opdateres den. Hvis ikke, OPRETTES en NY per-partner row
    #     (legacy rows mutaeres IKKE — de forbliver synlige for andre partnere).
    #   * Uden partner_id (legacy edit): tag fat i legacy row som før.
    existing = None
    if partner_id_in:
        existing = await db.container_overrides.find_one({
            "location_code": code, "material": material,
            "container_label": container_label, "partner_id": partner_id_in,
        })
    else:
        existing = await db.container_overrides.find_one({
            "location_code": code, "material": material,
            "container_label": container_label,
            "$or": [{"partner_id": {"$exists": False}}, {"partner_id": ""}],
        })

    # Når vi opretter en NY per-partner row, brug evt. legacy som skabelon
    # så fields der ikke sendes med (fx custom_address der ikke er ændret)
    # arver legacy-værdien.
    legacy_template = None
    if not existing and partner_id_in:
        legacy_template = await db.container_overrides.find_one({
            "location_code": code, "material": material,
            "container_label": container_label,
            "$or": [{"partner_id": {"$exists": False}}, {"partner_id": ""}],
        })

    # Required field: container-nummer must be filled. Leveringsadresse blev
    # fjernet pr. brugerkrav 2026-06-14 — den hører til bestillingsflowet,
    # ikke til container-definitionen — så vi accepterer tom adresse her.
    cur = existing or legacy_template or {}
    merged_id = (fields.get("custom_container_id") if "custom_container_id" in fields
                 else cur.get("custom_container_id", "")).strip()
    if not merged_id:
        raise HTTPException(status_code=400, detail="Container-nummer er påkrævet")

    if existing:
        await db.container_overrides.update_one(
            {"id": existing.get("id")} if existing.get("id") else {
                "location_code": code, "material": material, "container_label": container_label,
                "partner_id": existing.get("partner_id", ""),
            },
            {"$set": fields}
        )
    else:
        # Opret en ny override-row. Hvis legacy_template findes (vi opretter
        # en per-partner override for første gang), arv felter derfra så
        # ikke-ændrede værdier ikke "nulstilles" til defaults.
        base = {}
        if legacy_template:
            base = {
                "custom_address": legacy_template.get("custom_address", ""),
                "custom_container_id": legacy_template.get("custom_container_id", ""),
                "open_from": legacy_template.get("open_from", ""),
                "open_to": legacy_template.get("open_to", ""),
                "locked_address": bool(legacy_template.get("locked_address", False)),
                "locked_hours": bool(legacy_template.get("locked_hours", False)),
                "locked_container_id": bool(legacy_template.get("locked_container_id", False)),
                "capacity_measure_id": legacy_template.get("capacity_measure_id", ""),
            }
        # Overskriv med eksplicit ændrede felter
        for k, v in fields.items():
            if k != "updated_at":
                base[k] = v
        override = ContainerOverride(
            location_code=code,
            material=material,
            container_label=container_label,
            custom_address=base.get("custom_address", ""),
            custom_container_id=base.get("custom_container_id", ""),
            open_from=base.get("open_from", ""),
            open_to=base.get("open_to", ""),
            locked_address=base.get("locked_address", False),
            locked_hours=base.get("locked_hours", False),
            locked_container_id=base.get("locked_container_id", False),
            capacity_measure_id=base.get("capacity_measure_id", ""),
            partner_id=partner_id_in,
        )
        await db.container_overrides.insert_one(override.model_dump())

    return {"message": "Container data gemt", "material": material, "container_label": container_label, "partner_id": partner_id_in}

@api_router.get("/customer-orders/check-duplicate")
async def check_duplicate_order(
    location_code: str = "",
    material: str = "",
    container_number: str = "",
    tour_type: str = "normal",
    container_id: str = "",  # legacy alias for custom_container_id
):
    """Fase 15.16 (2026-02-XX): Tjek om der allerede findes en ikke-fuldført
    bestilling for given container + opgavetype. Bruges af frontend til
    at gråne ud containere der allerede har en aktiv bestilling.

    En "container" identificeres som (location_code, material, container_number).
    Forskelligt `tour_type` på samme container er OK; samme `tour_type` blokerer.
    Status: status != 'completed' OG status != 'cancelled'.
    Legacy fallback: hvis kun `container_id` (custom_container_id) sendes,
    falder vi tilbage til match på container_id_override.
    """
    tt = (tour_type or "normal").strip()
    if location_code.strip() and container_number.strip():
        query = {
            "location_code": location_code.strip(),
            "material": material.strip(),
            "container_number": container_number.strip(),
            "tour_type": tt,
            "status": {"$nin": ["completed", "cancelled", "not_completed"]},
        }
        existing = await _raw_db.container_orders.find_one(
            query,
            {"_id": 0, "id": 1, "tour_id": 1, "order_date": 1, "tour_type": 1},
        )
    elif container_id.strip():
        existing = await _raw_db.container_orders.find_one(
            {
                "container_id_override": container_id.strip(),
                "tour_type": tt,
                "status": {"$nin": ["completed", "cancelled", "not_completed"]},
            },
            {"_id": 0, "id": 1, "tour_id": 1, "order_date": 1, "tour_type": 1},
        )
    else:
        return {"blocked": False}
    if not existing:
        return {"blocked": False}
    return {
        "blocked": True,
        "order_id": existing.get("id") or "",
        "tour_id": existing.get("tour_id") or "",
        "order_date": existing.get("order_date") or "",
        "tour_type": existing.get("tour_type") or "normal",
    }


@api_router.post("/customer-orders/submit")
async def submit_customer_order(order: StructuredOrderCreate, request: Request):
    """Submit a structured customer order - creates both container_order and tour for drivers."""
    # Get location info
    location = await _lookup_site_by_code(order.location_code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    # Optional: capture which order-user submitted (so Lokation Admin can see
    # who ordered what in the dashboard). The endpoint stays public for the
    # legacy QR-code flow (`/order` page on a kiosk).
    submitter_user_id = ""
    submitter_user_name = ""
    submitter_user_email = ""
    auth_header = request.headers.get("Authorization", "") if hasattr(request, "headers") else ""
    if auth_header.startswith("Bearer "):
        try:
            tk_payload = decode_token(auth_header.split(" ", 1)[1])
            submitter_user_id = tk_payload.get("sub") or ""
            if submitter_user_id:
                u = await _raw_db.users.find_one({"id": submitter_user_id}, {"_id": 0, "name": 1, "email": 1})
                if u:
                    submitter_user_name = u.get("name") or u.get("email") or ""
                    submitter_user_email = u.get("email") or ""
        except Exception:  # noqa: BLE001 — best-effort; anonymous flow still allowed
            submitter_user_id = ""
    # Enforce: when an authenticated user creates the order, leveringsaddresse
    # (custom_address) is OBLIGATORISK. The public QR-kiosk flow keeps the old
    # behaviour (falls back to the location's default address).
    # EXCEPTION (Batch 2): for "Byt container" (flyt), "Til værksted" (vaerksted)
    # and "Afhent fra værksted" (afhent_vaerksted) the delivery address is hidden
    # from the UI on purpose and replaced by either an in-yard move or the
    # workshop snapshot fields, so we don't require custom_address.
    _tt = (order.tour_type or "normal").strip()
    # Fase 15.16 (2026-02-XX): "Estimat" — tilpasset bestilling uden konkret
    # container. Hopper over leveringsadresse-, værksted- og container-checks
    # fordi det er et fremtidigt ressourcebehov, ikke en konkret opgave.
    # Fase 15.41 (2026-02-22): "Løs afhentning" — samme princip men chaufføren
    # medbringer egne tomme containere. Felt: loose_estimated_count.
    is_estimat = (_tt == "estimat")
    is_loes_afhentning = (_tt == "loes_afhentning")
    if is_estimat:
        if int(order.estimated_count or 0) <= 0:
            raise HTTPException(status_code=400, detail="Estimeret antal containere skal være mindst 1")
        if not (order.material or "").strip():
            raise HTTPException(status_code=400, detail="Materiale er påkrævet for estimat")
    elif is_loes_afhentning:
        if int(order.loose_estimated_count or 0) <= 0:
            raise HTTPException(status_code=400, detail="Estimeret antal containere skal være mindst 1")
        if not (order.material or "").strip():
            raise HTTPException(status_code=400, detail="Materiale er påkrævet for løs afhentning")
        if submitter_user_id and not (order.custom_address or "").strip():
            raise HTTPException(status_code=400, detail="Adresse er påkrævet for løs afhentning")
    else:
        needs_delivery_address = _tt not in ("flyt", "vaerksted", "afhent_vaerksted")
        if submitter_user_id and needs_delivery_address and not (order.custom_address or "").strip():
            raise HTTPException(status_code=400, detail="Leveringsadresse er påkrævet")
        # Workshop tour types must reference a workshop (id+name+address)
        if _tt in ("vaerksted", "afhent_vaerksted"):
            if not (order.workshop_name or "").strip() or not (order.workshop_address or "").strip():
                raise HTTPException(status_code=400, detail="Værksted er påkrævet")
        # Fase 15.16 (2026-02-XX): Bloker dobbeltbestilling — samme
        # container + samme tour_type + status IKKE FULDFØRT.
        # En "container" identificeres entydigt via (location_code, material,
        # container_number). Bestillingsdato har INGEN betydning. Forskelligt
        # tour_type på samme container er OK.
        # Vi forespørger container_orders (kilden) i stedet for tours, fordi
        # tour.container kan blive overskrevet af en låst container_id-override.
        dup_query = {
            "location_code": (order.location_code or "").strip(),
            "material": (order.material or "").strip(),
            "container_number": (order.container_number or "").strip(),
            "tour_type": _tt,
            "status": {"$nin": ["completed", "cancelled"]},
        }
        if dup_query["location_code"] and dup_query["container_number"]:
            existing = await _raw_db.container_orders.find_one(
                dup_query, {"_id": 0, "id": 1, "order_date": 1},
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="Der findes allerede en ikke-fuldført bestilling for denne container og opgavetype.",
                )
    
    # Look up plads address
    plads_name = location["name"].replace(" Genbrugsplads", "")
    plads = await db.plads.find_one({"name": {"$regex": plads_name, "$options": "i"}}, {"_id": 0})
    
    default_address = location.get("address") or (plads.get("address", "") if plads else "")
    plads_full_name = plads.get("name", plads_name) if plads else plads_name

    # If the order user picked a specific plads (city), look it up and use that for the tour.
    # This is how multiple plads (e.g. 50 plads for Vestforbrænding) can share one location_code
    # but each ends up under its own city in the driver/admin view.
    picked_plads = None
    if order.plads_name.strip():
        picked_plads = await db.plads.find_one(
            {"name": order.plads_name.strip()}, {"_id": 0}
        )
        if picked_plads:
            plads_full_name = picked_plads["name"]
    
    # Use customer-edited address if provided, otherwise default
    final_address = order.custom_address.strip() if order.custom_address.strip() else default_address

    # Defense-in-depth: if the container override has a locked address or
    # locked hours, the order MUST honour them. The frontend already enforces
    # this via read-only inputs, but we re-apply the saved values here in case
    # someone tries to bypass the UI. Custom orders (no matching override doc)
    # are not locked.
    ov = await db.container_overrides.find_one(
        {"location_code": order.location_code, "material": order.material,
         "container_label": order.container_number},
        {"_id": 0, "custom_address": 1, "custom_container_id": 1, "open_from": 1, "open_to": 1,
         "locked_address": 1, "locked_hours": 1, "locked_container_id": 1},
    )
    if ov:
        if ov.get("locked_address") and ov.get("custom_address"):
            final_address = ov["custom_address"]
        if ov.get("locked_hours"):
            order.open_from = ov.get("open_from", "")
            order.open_to = ov.get("open_to", "")
        if ov.get("locked_container_id"):
            # Force the default container_id — disallow per-order override
            order.custom_container_id = ""
    
    # If customer edited data, auto-save as override for next time
    # NOTE: Per the new order/edit separation, the order flow does NOT
    # touch container "base definitions" anymore. The container's saved
    # address + container_id are only changed through the explicit
    # "Rediger container" modal on the order page (PUT
    # /api/locations/{code}/containers/override). Anything entered during
    # an order is local to THIS order only and stored on container_orders.
    pass
    
    order_date = order.order_date.strip() if order.order_date.strip() else get_dk_date_str()
    
    # Map priority
    priority_map = {"haster": "urgent", "normal": "normal", "senere": "low"}
    tour_priority = priority_map.get(order.priority, "normal")
    
    # Create container order record
    order_obj = ContainerOrder(
        location_code=order.location_code,
        location_name=location["name"],
        address_id="",
        customer_name=location["name"],
        customer_address=final_address,
        container_number=order.container_number,
        container_id_override=(order.custom_container_id or "").strip(),
        material=order.material,
        order_date=order_date,
        priority=order.priority,
        comment=order.comment,
        open_from=order.open_from.strip() if order.open_from else "",
        open_to=order.open_to.strip() if order.open_to else "",
        tour_type=(order.tour_type or "normal").strip() or "normal",
        partner_id=(order.partner_id or "").strip(),
        status="pending"
    )
    doc = order_obj.model_dump()
    # Track who submitted (when authenticated). Used by the Lokation Admin
    # dashboard to surface "hvem og hvornår" pr. ordre.
    doc["created_by_user_id"] = submitter_user_id
    doc["created_by_name"] = submitter_user_name
    doc["created_by_email"] = submitter_user_email
    # Leveringsadresse audit fields — persist primary + alternative IDs (and
    # the original address line in case the row is later edited / deleted).
    doc["delivery_address_id"] = (order.delivery_address_id or "").strip()
    doc["alternative_delivery_address_id"] = (order.alternative_delivery_address_id or "").strip()
    doc["manual_alternative_address"] = (order.manual_alternative_address or "").strip()
    doc["original_customer_address"] = ""
    # Fase 9 (2026-06-17, refaktoreret 2026-06-18): Snapshot CO2 så historiske
    # ordrer beholder korrekt CO2 selvom kunden senere ændrer biblioteket.
    # Refactor: CO2-kategori knyttes nu til MATERIALET (i plads-doc'ens
    # `material_co2_categories`) i stedet for at brugeren skal vælge typen
    # pr. bestilling.
    #
    # Fase 11 (2026-06-18): CO2 + vægt er KUN relevant for opgavetype
    # 'normal' (afhent container). For 'flyt' (byt container), 'vaerksted'
    # (til værksted) og 'afhent_vaerksted' (afhent fra værksted) gemmes
    # ingen CO2 — kun afhentningsopgaver bidrager til miljøregnskabet.
    # Fase 15.44 (2026-02-22): `loes_afhentning` har OGSÅ CO2 — kunden vil
    # se besparelsen i deres rapport. Snapshot factor ved bestilling så den
    # ikke ændrer sig hvis CO2-biblioteket senere opdateres.
    is_co2_tour = (order.tour_type or "normal") in ("normal", "loes_afhentning")
    explicit_co2 = (order.co2_type_id or "").strip()
    resolved_co2_id = explicit_co2 if is_co2_tour else ""
    if is_co2_tour and not resolved_co2_id:
        # Look up the material's CO2-kategori from the plads doc
        site_doc = picked_plads or plads or {}
        mco2 = (site_doc.get("material_co2_categories") or {})
        resolved_co2_id = (mco2.get(order.material) or "").strip()
    doc["co2_type_id"] = resolved_co2_id
    doc["co2_type_name"] = ""
    doc["co2_factor"] = 0.0
    doc["weight_kg"] = 0.0
    doc["co2_kg"] = 0.0
    if doc["co2_type_id"]:
        _co2_doc = await _raw_db.co2_types.find_one({"id": doc["co2_type_id"]}, {"_id": 0})
        if _co2_doc:
            doc["co2_type_name"] = _co2_doc.get("name", "")
            doc["co2_factor"] = float(_co2_doc.get("factor", 0) or 0)
    # Workshop snapshot (Batch 2) — persisteres pr. ordre så audit / chauffør
    # ikke skal læse fra `workshops`-biblioteket.
    doc["workshop_id"] = (order.workshop_id or "").strip()
    doc["workshop_name"] = (order.workshop_name or "").strip()
    doc["workshop_address"] = (order.workshop_address or "").strip()
    doc["workshop_phone"] = (order.workshop_phone or "").strip()
    doc["workshop_override"] = bool(order.workshop_override)
    # Snapshot kapacitetsmål fra container_overrides så driveren får målet direkte
    # på touren, og ordreopsummeringen kan vise det selv hvis biblioteket senere
    # ændres/slettes. (Batch 2 follow-up — 2026-06-14)
    doc["capacity_label"] = ""
    doc["capacity_volume_m3"] = None
    _ov = await _raw_db.container_overrides.find_one(
        {"location_code": order.location_code, "material": order.material,
         "container_label": order.container_number},
        {"_id": 0, "capacity_measure_id": 1},
    )
    if _ov and _ov.get("capacity_measure_id"):
        _cm = await _raw_db.capacity_measures.find_one(
            {"id": _ov["capacity_measure_id"]}, {"_id": 0, "label": 1, "volume_m3": 1},
        )
        if _cm:
            doc["capacity_label"] = _cm.get("label") or ""
            doc["capacity_volume_m3"] = _cm.get("volume_m3")
    if (doc["alternative_delivery_address_id"] or doc["manual_alternative_address"]) and doc["delivery_address_id"]:
        # Lookup the original (primary) address line so we can render it
        # alongside the alternative on the order details page.
        orig = await _raw_db.delivery_addresses.find_one(
            {"id": doc["delivery_address_id"]}, {"_id": 0},
        )
        if orig:
            orig_line = _da_format_address_line(orig)
            doc["original_customer_address"] = orig_line or orig.get("label", "")
    # Force company_id from the picked plads (or fallback to location's company_id) so
    # the order is correctly tenant-scoped even though /customer-orders/submit is public.
    resolved_company_id = (
        (picked_plads or {}).get("company_id")
        or (plads or {}).get("company_id")
        or location.get("company_id")
        or DEFAULT_COMPANY_ID
    )
    doc["company_id"] = resolved_company_id
    # Propagate the location's assigned logistics partners onto the order so the
    # driver-side `/api/plads` (and any future tour filtering) can route this
    # order to the right partner without re-reading the plads doc each time.
    # Fase 11 (2026-06-18): Inkludér også location.assigned_logistics_company_ids
    # som fallback — den offentlige QR-flow har ingen tenant-context, så
    # `picked_plads`/`plads` kan være None (tenant-aware DB filtrerer dem fra).
    # Fase 15.38 (2026-02-22) — STRIKT PARTNER-SCOPE: hvis medarbejderen har
    # valgt en specifik logistik-partner i partner-pickeren (`order.partner_id`),
    # SKAL bestillingen kun være synlig for DEN partner. Det fikser bugget hvor
    # samme ordre kunne ses af alle partnere knyttet til pladsen. Når
    # partner_id er tomt (legacy QR-anonymflow uden picker), beholdes det
    # gamle adfærdsmønster (alle pladsens partnere kan se ordren).
    _location_partners = list(
        ((picked_plads or {}).get("assigned_logistics_company_ids"))
        or ((plads or {}).get("assigned_logistics_company_ids"))
        or (location.get("assigned_logistics_company_ids") if location else None)
        or []
    )
    _chosen_partner = (order.partner_id or "").strip()
    if _chosen_partner and _chosen_partner in _location_partners:
        doc["assigned_logistics_company_ids"] = [_chosen_partner]
    elif _chosen_partner and not _location_partners:
        # Plads har ingen partner-liste men medarbejderen valgte alligevel en
        # partner — respekter valget.
        doc["assigned_logistics_company_ids"] = [_chosen_partner]
    else:
        doc["assigned_logistics_company_ids"] = _location_partners
    # Fase 15.16/15.18 (2026-02-21): Estimat-felt på container_order
    # (bruges i "Mine bestillinger" → felt "Antal containere estimeret").
    if is_estimat:
        doc["estimated_count"] = int(order.estimated_count or 0)
    # Fase 15.41 (2026-02-22): Løs afhentning — persistér loose_estimated_count
    # OG init en tom container_weights-liste (chaufføren udfylder ved Afslut).
    if is_loes_afhentning:
        doc["loose_estimated_count"] = int(order.loose_estimated_count or 0)
        doc["container_weights"] = []
    await db.container_orders.insert_one(doc)
    
    # The driver tour shows the user-typed container number (when provided)
    # so it carries the per-order override info. If the order user left the
    # override empty, fall back to the default container_id from overrides,
    # else the label.
    custom_id = (order.custom_container_id or "").strip()
    default_id = ""
    if not custom_id:
        ov = await db.container_overrides.find_one(
            {"location_code": order.location_code, "material": order.material,
             "container_label": order.container_number},
            {"_id": 0, "custom_container_id": 1},
        )
        if ov:
            default_id = (ov.get("custom_container_id") or "").strip()
    tour_container_label = custom_id or default_id or order.container_number

    # Also create a TOUR so it appears in driver panel immediately
    tour_obj = Tour(
        date=order_date,
        container=tour_container_label,
        fraction=order.material,
        facility=location["name"],
        address=final_address,
        plads=plads_full_name,
        priority=tour_priority,
        open_from=order.open_from.strip() if order.open_from else "",
        open_to=order.open_to.strip() if order.open_to else "",
        remark=f"Kundeordre: {order.comment}" if order.comment else f"Kundeordre fra {plads_full_name}",
        tour_type=(order.tour_type or "normal").strip() or "normal",
        lat=(picked_plads or plads or {}).get("lat") if (picked_plads or plads) else None,
        lng=(picked_plads or plads or {}).get("lng") if (picked_plads or plads) else None
    )
    tour_doc = tour_obj.model_dump()
    tour_doc["company_id"] = resolved_company_id
    tour_doc["order_id"] = doc["id"]  # link tour -> order for status sync
    tour_doc["assigned_logistics_company_ids"] = doc["assigned_logistics_company_ids"]
    tour_doc["source"] = "customer_order"  # Fase 4: separation manual vs. bestillinger
    # Fase 13 (2026-06-18): Spejl "Bestilt af" på selve turen så chauffør-/
    # admin-UI'et kan vise det via OrderInfoLine uden et ekstra DB-opslag.
    tour_doc["created_by_name"] = doc.get("created_by_name", "")
    tour_doc["created_by_email"] = doc.get("created_by_email", "")
    tour_doc["capacity_label"] = doc.get("capacity_label", "")
    tour_doc["capacity_volume_m3"] = doc.get("capacity_volume_m3")
    tour_doc["order_date"] = doc.get("order_date", "")
    # Fase 15.16/15.18 (2026-02-21): Estimat-bestilling — gem estimeret
    # container-antal på touren (container_orders fik feltet før insert ovenfor).
    if is_estimat:
        tour_doc["estimated_count"] = int(order.estimated_count or 0)
    # Fase 15.41 (2026-02-22): Løs afhentning — spejl loose_estimated_count og
    # initialiser tom container_weights-liste på touren. Chaufføren fylder den
    # ind én vægt ad gangen ved Afslut. `weight`-feltet auto-beregnes som SUM
    # når container_weights opdateres så de aldrig kommer ud af sync.
    if is_loes_afhentning:
        tour_doc["loose_estimated_count"] = int(order.loose_estimated_count or 0)
        tour_doc["container_weights"] = []
    await db.tours.insert_one(tour_doc)
    _push_later(_push_new_haster([dict(tour_doc)]))
    # Link order -> tour as well (handy for lookups)
    await db.container_orders.update_one({"id": doc["id"]}, {"$set": {"tour_id": tour_doc["id"]}})

    return {
        "order_id": doc["id"],
        "tour_id": tour_doc["id"],
        "message": "Bestilling oprettet",
        "material": order.material,
        "container": order.container_number,
        "container_id": doc.get("custom_container_id") or "",
        "capacity_label": doc.get("capacity_label") or "",
        "capacity_volume_m3": doc.get("capacity_volume_m3"),
        "genbrugsplads": location["name"],
        "address": final_address,
        "priority": order.priority,
        "order_date": order_date,
        "tour_type": (order.tour_type or "normal"),
        "workshop_name": (order.workshop_name or ""),
        "workshop_address": (order.workshop_address or ""),
        "workshop_phone": (order.workshop_phone or ""),
    }

@api_router.put("/container-orders/{order_id}")
async def update_container_order(order_id: str, update: ContainerOrderUpdate):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data")

    # If completing, add timestamp
    if update_data.get("status") == "completed":
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Fase 9 (2026-06-17): CO2 auto-recalc.
    # - If a new co2_type_id is supplied → snapshot fresh name + factor
    # - If weight_kg supplied → recalc co2_kg = factor * (kg / 1000)
    existing = await db.container_orders.find_one({"id": order_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found")

    # Fase 11 (2026-06-18): CO2 + vægt kun for opgavetype 'normal' (afhent
    # container). For øvrige opgavetyper må vægt/CO2 ALDRIG sættes.
    # Fase 15.44 (2026-02-22): `loes_afhentning` har også vægt + CO2.
    effective_tour_type = update_data.get("tour_type", existing.get("tour_type") or "normal")
    is_co2_tour = effective_tour_type in ("normal", "loes_afhentning")
    if not is_co2_tour:
        # Tving alle CO2-/vægt-felter til 0 så DB matcher reglen
        update_data["weight_kg"] = 0.0
        update_data["co2_kg"] = 0.0
        update_data["co2_factor"] = 0.0
        update_data["co2_type_id"] = ""
        update_data["co2_type_name"] = ""
    elif "co2_type_id" in update_data:
        new_type_id = update_data["co2_type_id"]
        if new_type_id:
            co2_doc = await _raw_db.co2_types.find_one({"id": new_type_id}, {"_id": 0})
            if co2_doc:
                update_data["co2_type_name"] = co2_doc.get("name", "")
                update_data["co2_factor"] = float(co2_doc.get("factor", 0) or 0)
        else:
            # Clearing CO2 type
            update_data["co2_type_name"] = ""
            update_data["co2_factor"] = 0.0

    # Determine final values for recalc
    final_factor = update_data.get("co2_factor", existing.get("co2_factor", 0.0)) or 0.0
    final_weight = update_data.get("weight_kg", existing.get("weight_kg", 0.0)) or 0.0
    # Fase 11 (2026-06-18): Hvis ikke 'normal' opgavetype skal CO2 forblive 0
    # uanset hvad faktor/vægt måtte være.
    # Fase 15.44 (2026-02-22): Også 'loes_afhentning' beregner CO2.
    if is_co2_tour and ("weight_kg" in update_data or "co2_factor" in update_data):
        update_data["co2_kg"] = round(float(final_factor) * (float(final_weight) / 1000.0), 3)

    result = await db.container_orders.update_one({"id": order_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")

    order = await db.container_orders.find_one({"id": order_id}, {"_id": 0})
    return order

@api_router.delete("/container-orders/{order_id}")
async def delete_container_order(order_id: str):
    result = await db.container_orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order deleted"}

# Reorder container orders
@api_router.put("/container-orders/reorder/bulk")
async def reorder_container_orders(orders: List[dict]):
    for item in orders:
        await db.container_orders.update_one(
            {"id": item["id"]},
            {"$set": {"sort_order": item["sort_order"]}}
        )
    return {"message": f"Reordered {len(orders)} orders"}

# Get orders grouped by location for driver view
@api_router.get("/container-orders/by-location/grouped")
async def get_orders_grouped_by_location():
    orders = await db.container_orders.find({"status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(500)
    
    # Group by location
    grouped = {}
    for order in orders:
        loc_name = order.get("location_name", "Unknown")
        if loc_name not in grouped:
            grouped[loc_name] = {
                "location_code": order.get("location_code"),
                "location_name": loc_name,
                "orders": [],
                "pending_count": 0,
                "completed_count": 0
            }
        grouped[loc_name]["orders"].append(order)
        if order.get("status") == "completed":
            grouped[loc_name]["completed_count"] += 1
        else:
            grouped[loc_name]["pending_count"] += 1
    
    return list(grouped.values())

@api_router.get("/container-orders/by-location/{location_code}")
async def get_orders_by_location(location_code: str, date: str = "",
                                  include_cancelled: bool = False, all: int = 0,
                                  partner_id: str = ""):
    """Get orders for a specific location, optionally filtered by date.

    Query params:
      * date — YYYY-MM-DD; only orders for that day.
      * all=1 — skip date filtering entirely (all dates, past/present/future).
        Has higher precedence than `date`.
      * partner_id (NEW pr. 2026-06-15 runde 6): Strict scope per logistik-
        partner. Når sat returneres KUN ordrer med matchende `partner_id`
        — så samme lokation med flere partnere ikke deler ordre-historik
        i "Mine bestillinger" / "Alle bestillinger". Tom partner_id ⇒
        returnér alle ordrer (legacy + alle partnere).

    For the Lokation Admin dashboard the orders are enriched with the creator's
    name (`created_by_name`) and a derived `status_label` (afventer / accepteret
    / afhentet / annulleret) so the UI doesn't need to duplicate the mapping.
    """
    query = {"location_code": location_code}
    if not include_cancelled:
        query["status"] = {"$ne": "cancelled"}
    if not all and date:
        query["order_date"] = date
    if partner_id:
        query["partner_id"] = partner_id
    orders = await db.container_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # Bulk look-up of creators so we don't issue N queries
    creator_ids = {o.get("created_by_user_id") for o in orders if o.get("created_by_user_id")}
    creator_map = {}
    if creator_ids:
        async for u in _raw_db.users.find(
            {"id": {"$in": list(creator_ids)}}, {"_id": 0, "id": 1, "name": 1, "email": 1},
        ):
            creator_map[u["id"]] = {"name": u.get("name") or u.get("email") or "", "email": u.get("email") or ""}

    # Bulk-resolve container-id defaults so the UI can show the actual
    # container number (e.g. "PAP-001") instead of just the label.
    label_keys = {
        (o.get("location_code"), o.get("material"), o.get("container_number"))
        for o in orders if o.get("location_code") and o.get("material") and o.get("container_number")
    }
    default_id_map: Dict[Any, str] = {}
    if label_keys:
        or_clauses = [
            {"location_code": loc, "material": mat, "container_label": lbl}
            for (loc, mat, lbl) in label_keys
        ]
        async for ov in db.container_overrides.find({"$or": or_clauses}, {"_id": 0, "location_code": 1, "material": 1, "container_label": 1, "custom_container_id": 1}):
            key = (ov.get("location_code"), ov.get("material"), ov.get("container_label"))
            default_id_map[key] = (ov.get("custom_container_id") or "").strip()

    for o in orders:
        uid = o.get("created_by_user_id")
        if uid and uid in creator_map:
            o["created_by_name"] = creator_map[uid]["name"]
            o["created_by_email"] = creator_map[uid]["email"]
        else:
            o.setdefault("created_by_name", o.get("created_by_name", ""))
            o.setdefault("created_by_email", "")
        # Resolved container_id: prefer the per-order override (set when the
        # employee used "Tilføj tilpasset bestilling" or typed something during
        # the order); fall back to the saved default from container_overrides.
        override_id = (o.get("container_id_override") or "").strip()
        default_id = default_id_map.get((o.get("location_code"), o.get("material"), o.get("container_number")), "")
        o["container_id_resolved"] = override_id or default_id
        # Derive a "lifecycle status" the UI can filter on. Original `status`
        # field is preserved untouched.
        # Fase 15.51 (2026-02-22): Estimat-bestillinger har ingen rigtige
        # status — de er kun ressource-planlægning. Map dem til "estimat"
        # så UI kan vise "N/A" i status-kolonnen.
        if (o.get("tour_type") or "") == "estimat":
            o["status_label"] = "estimat"
        elif o.get("status") == "cancelled":
            o["status_label"] = "annulleret"
        elif o.get("status") == "not_completed":
            o["status_label"] = "ikke_gennemfoert"
        elif o.get("completed"):
            o["status_label"] = "afhentet"
        elif o.get("on_way") or o.get("claimed_by"):
            o["status_label"] = "accepteret"
        else:
            o["status_label"] = "afventer"
    return orders


# Get materials list (default)
@api_router.get("/materials")
async def get_materials_list():
    return {"materials": DEFAULT_MATERIALS}


async def _require_admin_for_location(code: str, payload: dict) -> dict:
    """Authorize a write to a per-location resource (containers, materials,
    etc.). The caller must be either:
      * a super_admin (god-mode), or
      * a customer_admin whose company owns the plads, or
      * a location_admin who has `code` in their managed pladser
        (location_code + assigned_plads_ids).
    Returns the resolved caller user document on success, or raises 403."""
    if not payload:
        raise HTTPException(status_code=401, detail="Login krævet")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Login krævet")
    user = await _raw_db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    role = user.get("role")
    if role == "super_admin":
        return user
    # Resolve the plads to make sure we know its owning company.
    plads = await _raw_db.plads.find_one({"location_code": code}, {"_id": 0})
    if not plads:
        # Fall back to legacy locations doc (single-tenant)
        legacy = await _raw_db.locations.find_one({"code": code}, {"_id": 0})
        if not legacy:
            raise HTTPException(status_code=404, detail="Location not found")
        owner_cid = legacy.get("company_id")
    else:
        owner_cid = plads.get("company_id")
    if role == "customer_admin" and user.get("company_id") == owner_cid:
        return user
    if role == "location_admin" and user.get("company_id") == owner_cid:
        managed = set(user.get("assigned_plads_ids") or [])
        if user.get("location_code"):
            managed.add(user["location_code"])
        if code in managed:
            return user
    raise HTTPException(status_code=403, detail="Du må ikke ændre denne lokation")

# ============= PER-LOCATION MATERIAL MANAGEMENT =============

@api_router.get("/locations/{code}/materials")
async def get_location_materials(code: str):
    """Get materials for a specific location. Returns the FULL list (active +
    inactive). Callers that only want active materials should consult the
    `inactive_materials` array returned alongside and filter client-side, or
    use `/locations/{code}/materials/active`.

    Fase 9 refactor (2026-06-18): Returnerer også `material_co2_categories`
    (dict mapping material_name → co2_type_id) så frontend kan vise CO2-
    kategori på materialerne.
    """
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return {
        "materials": location.get("materials", DEFAULT_MATERIALS),
        "inactive_materials": location.get("inactive_materials", []),
        "material_co2_categories": location.get("material_co2_categories", {}),
        "location": location["name"],
    }


@api_router.get("/locations/{code}/materials/active")
async def get_location_active_materials(code: str):
    """Active-only materials. Used by the order page so deactivated
    materials don't appear in the customer-facing dropdown.

    Fase 9 refactor (2026-06-18): Returnerer også `material_co2_categories`
    så bestillingssiden kan vise CO2-kategori-chips på materialerne.
    """
    location = await _lookup_site_by_code(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    inactive = set(location.get("inactive_materials") or [])
    all_mats = location.get("materials", DEFAULT_MATERIALS) or []
    return {
        "materials": [m for m in all_mats if m not in inactive],
        "material_co2_categories": location.get("material_co2_categories", {}),
        "location": location["name"],
    }

async def _materials_write_target(code: str):
    """Pick the right collection + filter for a materials write based on where
    the location currently lives (plads vs legacy locations)."""
    site = await _lookup_site_by_code(code)
    if not site:
        return None, None, None
    if site.get("_source") == "plads":
        return _raw_db.plads, {"id": site["_plads_id"]}, site
    return _raw_db.locations, {"code": code}, site

@api_router.post("/locations/{code}/materials")
async def add_location_material(code: str, data: dict,
                                payload: dict = Depends(get_current_user_payload)):
    """Add a new material to a location's list.

    Pr. 2026-06-15 brugerkrav: Når `partner_id` sendes, tilføjes materialet
    KUN under den partner (gemt i `plads.partner_materials[partner_id]`).
    Uden `partner_id` ender det i den globale (legacy) `materials`-liste.
    Strict separation per partner — partnere deler IKKE længere materialer.
    """
    await _require_admin_for_location(code, payload)
    coll, flt, location = await _materials_write_target(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    material_name = data.get("material", "").strip()
    if not material_name:
        raise HTTPException(status_code=400, detail="Material name required")
    partner_id = (data.get("partner_id") or "").strip()
    # Fase 9 refactor (2026-06-18): CO2-kategori knyttes til materialet,
    # ikke til den enkelte bestilling. Valider at typen findes i kundens
    # CO2-bibliotek hvis den medsendes.
    co2_category_id = (data.get("co2_category_id") or "").strip()
    if co2_category_id:
        owner_cid = location.get("company_id") or ""
        co2_doc = await _raw_db.co2_types.find_one(
            {"id": co2_category_id, "company_id": owner_cid}, {"_id": 0, "id": 1},
        )
        if not co2_doc:
            raise HTTPException(status_code=400, detail="Ukendt CO2-kategori")

    if partner_id:
        partner_materials = dict(location.get("partner_materials") or {})
        current = list(partner_materials.get(partner_id) or [])
        if material_name in current:
            raise HTTPException(status_code=400, detail="Material already exists")
        current.append(material_name)
        partner_materials[partner_id] = current
        update_set = {"partner_materials": partner_materials}
        if co2_category_id:
            mco2 = dict(location.get("material_co2_categories") or {})
            mco2[material_name] = co2_category_id
            update_set["material_co2_categories"] = mco2
        await coll.update_one(flt, {"$set": update_set})
        return {"message": "Materiale tilføjet", "material": material_name,
                "materials": current, "partner_id": partner_id,
                "co2_category_id": co2_category_id}

    materials = list(location.get("materials") or [])
    if material_name in materials:
        raise HTTPException(status_code=400, detail="Material already exists")
    materials.append(material_name)
    update_set = {"materials": materials}
    if co2_category_id:
        mco2 = dict(location.get("material_co2_categories") or {})
        mco2[material_name] = co2_category_id
        update_set["material_co2_categories"] = mco2
    await coll.update_one(flt, {"$set": update_set})
    return {"message": "Materiale tilføjet", "material": material_name,
            "materials": materials, "co2_category_id": co2_category_id}

@api_router.put("/locations/{code}/materials")
async def edit_location_material(code: str, data: dict,
                                 payload: dict = Depends(get_current_user_payload)):
    """Rename a material in a location's list. Location/customer admin only.

    Pr. 2026-06-15 brugerkrav (Krav 5 strict separation): Når `partner_id`
    sendes omdøbes materialet KUN i `plads.partner_materials[partner_id]`.
    Andre partneres lister forbliver urørte. Uden partner_id omdøbes i
    den legacy/globale `materials`-liste (bagudkompatibilitet).
    """
    await _require_admin_for_location(code, payload)
    coll, flt, location = await _materials_write_target(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name required")
    partner_id = (data.get("partner_id") or "").strip()
    # Fase 9 refactor (2026-06-18): Tillad samtidig opdatering af CO2-kategori
    # (None/missing = uændret, "" = ryd, andet = sæt). Valider CO2-id mod kunden.
    co2_category_id = data.get("co2_category_id", None)
    if co2_category_id is not None:
        co2_category_id = (co2_category_id or "").strip()
        if co2_category_id:
            owner_cid = location.get("company_id") or ""
            co2_doc = await _raw_db.co2_types.find_one(
                {"id": co2_category_id, "company_id": owner_cid}, {"_id": 0, "id": 1},
            )
            if not co2_doc:
                raise HTTPException(status_code=400, detail="Ukendt CO2-kategori")

    if partner_id:
        # Strict partner-scoped rename
        partner_materials = dict(location.get("partner_materials") or {})
        current = list(partner_materials.get(partner_id) or [])
        if old_name not in current:
            raise HTTPException(status_code=404, detail="Material not found in partner list")
        # Disallow rename into an existing name within SAME partner list
        if new_name != old_name and new_name in current:
            raise HTTPException(status_code=400, detail="Material already exists in partner list")
        new_list = [new_name if m == old_name else m for m in current]
        partner_materials[partner_id] = new_list
        update_set = {"partner_materials": partner_materials}
        # Flyt evt. CO2-mapping til nyt navn / opdater
        mco2 = dict(location.get("material_co2_categories") or {})
        changed_mco2 = False
        if old_name != new_name and old_name in mco2:
            mco2[new_name] = mco2.pop(old_name)
            changed_mco2 = True
        if co2_category_id is not None:
            if co2_category_id:
                mco2[new_name] = co2_category_id
            else:
                mco2.pop(new_name, None)
            changed_mco2 = True
        if changed_mco2:
            update_set["material_co2_categories"] = mco2
        await coll.update_one(flt, {"$set": update_set})
        # Spejl renamen i partner-scopede container_overrides så historikken
        # holder reference.
        await db.container_overrides.update_many(
            {"location_code": code, "material": old_name, "partner_id": partner_id},
            {"$set": {"material": new_name}},
        )
        return {"message": "Materiale omdøbt", "old_name": old_name,
                "new_name": new_name, "materials": new_list,
                "partner_id": partner_id,
                "co2_category_id": mco2.get(new_name, "")}

    materials = location.get("materials", [])
    if old_name not in materials:
        raise HTTPException(status_code=404, detail="Material not found")

    # Replace in list
    materials = [new_name if m == old_name else m for m in materials]
    update_set = {"materials": materials}
    mco2 = dict(location.get("material_co2_categories") or {})
    changed_mco2 = False
    if old_name != new_name and old_name in mco2:
        mco2[new_name] = mco2.pop(old_name)
        changed_mco2 = True
    if co2_category_id is not None:
        if co2_category_id:
            mco2[new_name] = co2_category_id
        else:
            mco2.pop(new_name, None)
        changed_mco2 = True
    if changed_mco2:
        update_set["material_co2_categories"] = mco2
    await coll.update_one(flt, {"$set": update_set})

    # Also update any container_overrides that reference the old material name
    # (UDEN partner_id — vi rører ikke partner-specifikke overrides her)
    await db.container_overrides.update_many(
        {"location_code": code, "material": old_name,
         "$or": [{"partner_id": {"$exists": False}}, {"partner_id": ""}]},
        {"$set": {"material": new_name}}
    )

    return {"message": "Materiale omdøbt", "old_name": old_name, "new_name": new_name,
            "materials": materials, "co2_category_id": mco2.get(new_name, "")}

@api_router.post("/locations/{code}/materials/toggle-active")
async def toggle_location_material_active(code: str, data: dict,
                                          payload: dict = Depends(get_current_user_payload)):
    """Soft-deactivate a material on a plads. The material stays in
    `materials` so historical orders, calendars and material_calendars
    keep their references — but is moved to/from `inactive_materials` so
    the order page hides it from new bestillinger."""
    await _require_admin_for_location(code, payload)
    coll, flt, location = await _materials_write_target(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    material = (data.get("material") or "").strip()
    if not material:
        raise HTTPException(status_code=400, detail="material er påkrævet")
    materials = location.get("materials") or []
    if material not in materials:
        raise HTTPException(status_code=404, detail="Materiale findes ikke")
    inactive = list(location.get("inactive_materials") or [])
    if "active" in data:
        target_active = bool(data["active"])
    else:
        target_active = material in inactive  # toggle
    if target_active:
        # activate → remove from inactive list
        inactive = [m for m in inactive if m != material]
    else:
        # deactivate → add to inactive list (idempotent)
        if material not in inactive:
            inactive.append(material)
    await coll.update_one(flt, {"$set": {"inactive_materials": inactive}})
    return {
        "material": material, "active": target_active,
        "inactive_materials": inactive,
    }


@api_router.delete("/locations/{code}/materials")
async def delete_location_material(code: str, material: str = "",
                                    partner_id: str = "",
                                    payload: dict = Depends(get_current_user_payload)):
    """Permanent delete — only allowed when the material has NO active
    references (active orders, container_overrides with data, calendar mappings).

    Pr. 2026-06-15: Når `partner_id` sendes fjernes materialet KUN fra den
    partners liste — andre partneres lister forbliver urørte. Tom partner_id
    fjerner fra den legacy/globale liste."""
    await _require_admin_for_location(code, payload)
    coll, flt, location = await _materials_write_target(code)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    if not material:
        raise HTTPException(status_code=400, detail="material query param required")

    # Lokaliser materialet i den rigtige liste (legacy eller partner-specifik)
    if partner_id:
        partner_materials = dict(location.get("partner_materials") or {})
        plist = list(partner_materials.get(partner_id) or [])
        if material not in plist:
            raise HTTPException(status_code=404, detail="Material not found in partner list")
    else:
        materials = location.get("materials", [])
        if material not in materials:
            raise HTTPException(status_code=404, detail="Material not found in list")

    # Brugerkrav 2026-06-15: Tjek KUN aktive referencer (ikke historiske).
    #   * Orders der ikke er slettet/cancelled
    #   * Container-overrides der faktisk har data
    #   * Material-calendar-rækker der faktisk peger på en kalender (holiday eller hours)
    # Tekst "Brug Deaktiver i stedet" er fjernet pr. brugerkrav.
    # Hvis partner_id er sat — scope tjekket til den partners data.
    order_filter = {
        "location_code": code, "material": material,
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
        "status_label": {"$ne": "cancelled"},
    }
    override_filter = {
        "location_code": code, "material": material,
        "$or": [
            {"custom_address": {"$nin": ["", None]}},
            {"custom_container_id": {"$nin": ["", None]}},
        ],
    }
    if partner_id:
        order_filter["partner_id"] = partner_id
        override_filter["partner_id"] = partner_id

    refs_orders = await _raw_db.container_orders.count_documents(order_filter)
    refs_overrides = await _raw_db.container_overrides.count_documents(override_filter)
    # Kalender-mappings er stadig lokationsglobalt (per spec — kalendere er ikke partner-specifikke)
    refs_calendars = await _raw_db.material_calendars.count_documents({
        "location_code": code, "material": material,
        "$or": [
            {"holiday_calendar_id": {"$nin": ["", None]}},
            {"hours_calendar_id": {"$nin": ["", None]}},
        ],
    })
    total = refs_orders + refs_overrides + refs_calendars
    if total > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Kan ikke slettes — materialet har {refs_orders} aktiv bestilling(er), "
                f"{refs_overrides} container-reference(r) og {refs_calendars} kalender-tilknytning(er)."
            ),
        )

    if partner_id:
        new_plist = [m for m in plist if m != material]
        partner_materials[partner_id] = new_plist
        update_set = {"partner_materials": partner_materials}
        mco2 = dict(location.get("material_co2_categories") or {})
        if material in mco2:
            mco2.pop(material, None)
            update_set["material_co2_categories"] = mco2
        await coll.update_one(flt, {"$set": update_set})
        return {"message": "Materiale slettet", "material": material,
                "materials": new_plist, "partner_id": partner_id}

    materials = [m for m in (location.get("materials") or []) if m != material]
    inactive = [m for m in (location.get("inactive_materials") or []) if m != material]
    update_set = {"materials": materials, "inactive_materials": inactive}
    mco2 = dict(location.get("material_co2_categories") or {})
    if material in mco2:
        mco2.pop(material, None)
        update_set["material_co2_categories"] = mco2
    await coll.update_one(flt, {"$set": update_set})
    return {"message": "Materiale slettet", "material": material, "materials": materials}


# ════════════════════════════════════════════════════════════════════════
# CO2-TYPES (Fase 9 — 2026-06-17) — per-customer material library with kg CO2 / ton factor
# Scope: customer_admin (write) + any user in same customer company (read).
# ════════════════════════════════════════════════════════════════════════

def _user_customer_company_id(payload: dict) -> str:
    """Return the customer company_id this user belongs to (for CO2 scoping).
    Falls back to active_customer_id for drivers."""
    cid = payload.get("company_id") or ""
    if payload.get("role") == "driver":
        # Drivers belong to a logistics company; use their selected customer
        return payload.get("active_customer_id", "") or cid
    return cid

@api_router.get("/co2-types", response_model=List[CO2Type])
async def list_co2_types(payload: dict = Depends(get_current_user_payload)):
    """List CO2-types for the caller's customer company. super_admin gets ALL
    for backoffice. logistics_admin reads from their currently-active customer
    (via tenant context middleware sets company_id on payload)."""
    role = payload.get("role")
    if role == "super_admin":
        types = await _raw_db.co2_types.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    else:
        cid = _user_customer_company_id(payload)
        if not cid:
            return []
        types = await _raw_db.co2_types.find(
            {"company_id": cid}, {"_id": 0}
        ).sort("name", 1).to_list(1000)
    return [CO2Type(**t) for t in types]

@api_router.post("/co2-types", response_model=CO2Type)
async def create_co2_type(payload_body: CO2TypeCreate,
                          payload: dict = Depends(get_current_user_payload)):
    """Create a CO2-type. Only customer_admin (for their own kunde) or super_admin."""
    role = payload.get("role")
    if role not in ("customer_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun Kunde Admin må oprette CO2-typer")
    cid = payload.get("company_id") or ""
    if role == "customer_admin" and not cid:
        raise HTTPException(status_code=400, detail="customer_admin mangler company_id")
    name = (payload_body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    if payload_body.factor < 0:
        raise HTTPException(status_code=400, detail="Faktor må ikke være negativ")
    # Prevent duplicate name within same customer
    exists = await _raw_db.co2_types.find_one({"company_id": cid, "name": name, "active": True})
    if exists:
        raise HTTPException(status_code=409, detail=f"CO2-type '{name}' findes allerede")
    obj = CO2Type(company_id=cid, name=name, factor=float(payload_body.factor))
    await _raw_db.co2_types.insert_one(obj.model_dump())
    return obj

@api_router.put("/co2-types/{type_id}", response_model=CO2Type)
async def update_co2_type(type_id: str, payload_body: CO2TypeUpdate,
                          payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("customer_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun Kunde Admin må redigere CO2-typer")
    existing = await _raw_db.co2_types.find_one({"id": type_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="CO2-type ikke fundet")
    if role == "customer_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="CO2-type tilhører anden kunde")
    update_data = {k: v for k, v in payload_body.model_dump().items() if v is not None}
    if "factor" in update_data:
        if float(update_data["factor"]) < 0:
            raise HTTPException(status_code=400, detail="Faktor må ikke være negativ")
        update_data["factor"] = float(update_data["factor"])
    if "name" in update_data:
        update_data["name"] = update_data["name"].strip()
        if not update_data["name"]:
            raise HTTPException(status_code=400, detail="Navn må ikke være tom")
    await _raw_db.co2_types.update_one({"id": type_id}, {"$set": update_data})
    updated = await _raw_db.co2_types.find_one({"id": type_id}, {"_id": 0})
    return CO2Type(**updated)

@api_router.delete("/co2-types/{type_id}")
async def delete_co2_type(type_id: str,
                          payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("customer_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun Kunde Admin må slette CO2-typer")
    existing = await _raw_db.co2_types.find_one({"id": type_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="CO2-type ikke fundet")
    if role == "customer_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="CO2-type tilhører anden kunde")
    # Tjek for aktive ordrer der bruger typen
    in_use = await _raw_db.container_orders.count_documents(
        {"co2_type_id": type_id, "status": {"$nin": ["completed", "cancelled"]}}
    )
    if in_use:
        raise HTTPException(status_code=409,
            detail=f"Kan ikke slette — {in_use} aktive ordre(r) bruger denne CO2-type. Marker den inaktiv i stedet.")
    await _raw_db.co2_types.delete_one({"id": type_id})
    return {"message": "CO2-type slettet", "id": type_id}


# ════════════════════════════════════════════════════════════════════════
# VEHICLES + TRAILERS (Fase 10 — 2026-06-17) — flåde-administration pr. logistik-virksomhed
# LA opretter listerne. Drivers læser dem + vælger ÉN vogn + (valgfri) ÉN hænger.
# ════════════════════════════════════════════════════════════════════════

def _user_logistics_company_id(payload: dict) -> str:
    """Return the logistics company id this user/driver belongs to."""
    return payload.get("company_id") or ""

# ----- VEHICLES -----
@api_router.get("/vehicles", response_model=List[Vehicle])
async def list_vehicles(payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role == "super_admin":
        items = await _raw_db.vehicles.find({}, {"_id": 0}).sort("number", 1).to_list(2000)
    else:
        cid = _user_logistics_company_id(payload)
        if not cid:
            return []
        items = await _raw_db.vehicles.find(
            {"company_id": cid, "active": True}, {"_id": 0}
        ).sort("number", 1).to_list(1000)
    return [Vehicle(**v) for v in items]

@api_router.post("/vehicles", response_model=Vehicle)
async def create_vehicle(body: VehicleCreate,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må oprette vognnumre")
    cid = payload.get("company_id") or ""
    if role == "logistics_admin" and not cid:
        raise HTTPException(status_code=400, detail="logistics_admin mangler company_id")
    number = (body.number or "").strip().upper()
    if not number:
        raise HTTPException(status_code=400, detail="Vognnummer er påkrævet")
    exists = await _raw_db.vehicles.find_one({"company_id": cid, "number": number, "active": True})
    if exists:
        raise HTTPException(status_code=409, detail=f"Vognnummer '{number}' findes allerede")
    obj = Vehicle(company_id=cid, number=number)
    await _raw_db.vehicles.insert_one(obj.model_dump())
    return obj

@api_router.put("/vehicles/{vehicle_id}", response_model=Vehicle)
async def update_vehicle(vehicle_id: str, body: VehicleUpdate,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må redigere vognnumre")
    existing = await _raw_db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vognnummer ikke fundet")
    if role == "logistics_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="Vognnummer tilhører anden virksomhed")
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "number" in update_data:
        update_data["number"] = update_data["number"].strip().upper()
        if not update_data["number"]:
            raise HTTPException(status_code=400, detail="Vognnummer må ikke være tomt")
    await _raw_db.vehicles.update_one({"id": vehicle_id}, {"$set": update_data})
    updated = await _raw_db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    return Vehicle(**updated)

@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må slette vognnumre")
    existing = await _raw_db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vognnummer ikke fundet")
    if role == "logistics_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="Vognnummer tilhører anden virksomhed")
    await _raw_db.vehicles.delete_one({"id": vehicle_id})
    return {"message": "Vognnummer slettet", "id": vehicle_id}

# ----- TRAILERS -----
@api_router.get("/trailers", response_model=List[Trailer])
async def list_trailers(payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role == "super_admin":
        items = await _raw_db.trailers.find({}, {"_id": 0}).sort("number", 1).to_list(2000)
    else:
        cid = _user_logistics_company_id(payload)
        if not cid:
            return []
        items = await _raw_db.trailers.find(
            {"company_id": cid, "active": True}, {"_id": 0}
        ).sort("number", 1).to_list(1000)
    return [Trailer(**t) for t in items]

@api_router.post("/trailers", response_model=Trailer)
async def create_trailer(body: TrailerCreate,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må oprette hængere")
    cid = payload.get("company_id") or ""
    if role == "logistics_admin" and not cid:
        raise HTTPException(status_code=400, detail="logistics_admin mangler company_id")
    number = (body.number or "").strip()
    if not number:
        raise HTTPException(status_code=400, detail="Hængernummer er påkrævet")
    cap = int(body.container_capacity)
    if cap < 1:
        raise HTTPException(status_code=400, detail="Antal containere pr. hænger skal være mindst 1")
    exists = await _raw_db.trailers.find_one({"company_id": cid, "number": number, "active": True})
    if exists:
        raise HTTPException(status_code=409, detail=f"Hængernummer '{number}' findes allerede")
    obj = Trailer(company_id=cid, number=number, container_capacity=cap)
    await _raw_db.trailers.insert_one(obj.model_dump())
    return obj

@api_router.put("/trailers/{trailer_id}", response_model=Trailer)
async def update_trailer(trailer_id: str, body: TrailerUpdate,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må redigere hængere")
    existing = await _raw_db.trailers.find_one({"id": trailer_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Hænger ikke fundet")
    if role == "logistics_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="Hænger tilhører anden virksomhed")
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "number" in update_data:
        update_data["number"] = update_data["number"].strip()
        if not update_data["number"]:
            raise HTTPException(status_code=400, detail="Hængernummer må ikke være tomt")
    if "container_capacity" in update_data:
        cap = int(update_data["container_capacity"])
        if cap < 1:
            raise HTTPException(status_code=400, detail="Antal containere pr. hænger skal være mindst 1")
        update_data["container_capacity"] = cap
    await _raw_db.trailers.update_one({"id": trailer_id}, {"$set": update_data})
    updated = await _raw_db.trailers.find_one({"id": trailer_id}, {"_id": 0})
    return Trailer(**updated)

@api_router.delete("/trailers/{trailer_id}")
async def delete_trailer(trailer_id: str,
                         payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Kun logistik-admin må slette hængere")
    existing = await _raw_db.trailers.find_one({"id": trailer_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Hænger ikke fundet")
    if role == "logistics_admin" and existing.get("company_id") != (payload.get("company_id") or ""):
        raise HTTPException(status_code=403, detail="Hænger tilhører anden virksomhed")
    await _raw_db.trailers.delete_one({"id": trailer_id})
    return {"message": "Hænger slettet", "id": trailer_id}

# Driver-side: gem chaufførens valgte vogn + hænger på user-doc
class DriverSelectionUpdate(BaseModel):
    active_vehicle_id: Optional[str] = None
    active_trailer_id: Optional[str] = None  # "" = ingen hænger

@api_router.post("/driver/active-vehicle-trailer")
async def set_active_vehicle_trailer(body: DriverSelectionUpdate,
                                     payload: dict = Depends(get_current_user_payload)):
    """Driver setter sit valgte vognnummer + (valgfri) hænger pr. login."""
    if payload.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Kun chauffører")
    user_id = payload.get("sub") or payload.get("user_id") or ""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id mangler")
    update = {}
    if body.active_vehicle_id is not None:
        vid = (body.active_vehicle_id or "").strip()
        if vid:
            veh = await _raw_db.vehicles.find_one({"id": vid}, {"_id": 0})
            if not veh:
                raise HTTPException(status_code=404, detail="Vognnummer ikke fundet")
            if veh.get("company_id") != payload.get("company_id"):
                raise HTTPException(status_code=403, detail="Vognnummer tilhører anden virksomhed")
            update["active_vehicle_id"] = vid
            update["plate"] = veh.get("number", "")  # Backwards compat
        else:
            update["active_vehicle_id"] = ""
            update["plate"] = ""
    if body.active_trailer_id is not None:
        tid = (body.active_trailer_id or "").strip()
        if tid:
            tr = await _raw_db.trailers.find_one({"id": tid}, {"_id": 0})
            if not tr:
                raise HTTPException(status_code=404, detail="Hænger ikke fundet")
            if tr.get("company_id") != payload.get("company_id"):
                raise HTTPException(status_code=403, detail="Hænger tilhører anden virksomhed")
            update["active_trailer_id"] = tid
        else:
            update["active_trailer_id"] = ""
    if not update:
        return {"message": "Ingen ændringer"}
    await _raw_db.users.update_one({"id": user_id}, {"$set": update})
    return {"message": "OK", "updates": update}


# Seed default locations
@api_router.post("/seed-locations")
async def seed_locations():
    default_locations = [
        {"code": "3030", "name": "Skipstrup Genbrugsplads", "address": "Skibstrupvej 1, 3140 Ålsgårde", "city": "Ålsgårde"},
        {"code": "3131", "name": "Cireklen Genbrugsplads", "address": "Energivej 1, 3000 Helsingør", "city": "Helsingør"},
    ]
    
    for loc in default_locations:
        existing = await db.locations.find_one({"code": loc["code"]})
        if not existing:
            location_obj = Location(
                code=loc["code"],
                name=loc["name"],
                address=loc.get("address", ""),
                city=loc.get("city", ""),
                materials=DEFAULT_MATERIALS
            )
            await db.locations.insert_one(location_obj.model_dump())
        else:
            # Update existing locations with address and new materials
            await db.locations.update_one(
                {"code": loc["code"]},
                {"$set": {"materials": DEFAULT_MATERIALS, "address": loc.get("address", ""), "city": loc.get("city", "")}}
            )
    
    return {"message": "Seeded default locations"}

@api_router.get("/")
async def root():
    return {"message": "Kørselsrapport API v2.0"}


# ============= RECEIPT ENDPOINTS =============

@api_router.post("/receipts")
async def create_receipt(receipt: ReceiptCreate):
    receipt_doc = Receipt(
        driver_name=receipt.driver_name,
        plads=receipt.plads,
        tour_id=receipt.tour_id,
        amount=receipt.amount,
        description=receipt.description,
        image_data=receipt.image_data
    )
    doc = receipt_doc.model_dump()
    await db.receipts.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/receipts")
async def get_receipts(driver_name: str = "", plads: str = "", date: str = "",
                       tour_id: str = "", limit: int = 100):
    query = {}
    if driver_name:
        query["driver_name"] = driver_name
    if plads:
        query["plads"] = plads
    if date:
        query["date"] = date
    # Fase 18.7 (2026-02-28): Tour-scope så chauffør-UI kan vise eksisterende
    # uploadede kvitteringer for løs afhentning ved siden af vægt-rækkerne.
    if tour_id:
        query["tour_id"] = tour_id
    # Exclude image_data from list queries to reduce payload size
    receipts = await db.receipts.find(query, {"_id": 0, "image_data": 0}).sort("created_at", 1).to_list(min(limit, 500))
    return receipts

@api_router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str):
    receipt = await db.receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt

@api_router.delete("/receipts/{receipt_id}")
async def delete_receipt(receipt_id: str):
    result = await db.receipts.delete_one({"id": receipt_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"deleted": True}


# ============= DRIVER ARCHIVE ENDPOINT =============

@api_router.get("/driver-archive")
async def get_driver_archive():
    """Get all drivers with their daily work data grouped by date.

    Fase 17.11 (2026-02-27): Bruger _raw_db i alle queries. Ture/kvitteringer
    er gemt under KUNDENS company_id (genbrugsplads), men logistik-admins
    skal kunne se ALLE deres chaufførers data uanset hvilken kunde
    de var udsendt til. Driver-archive er admin-only.
    """
    driver_names = set()

    sessions = await _raw_db.driver_sessions.find({}, {"_id": 0, "driver_name": 1}).to_list(2000)
    for s in sessions:
        if s.get("driver_name"):
            driver_names.add(s["driver_name"])

    reports = await _raw_db.reports.find({}, {"_id": 0, "driver_name": 1}).to_list(2000)
    for r in reports:
        if r.get("driver_name"):
            driver_names.add(r["driver_name"])

    tours = await _raw_db.tours.find(
        {"$or": [{"claimed_by": {"$nin": ["", None]}}, {"driver_name": {"$nin": ["", None]}}]},
        {"_id": 0, "claimed_by": 1, "driver_name": 1}
    ).to_list(5000)
    for t in tours:
        for f in ("claimed_by", "driver_name"):
            v = t.get(f)
            if v:
                driver_names.add(v)

    receipts = await _raw_db.receipts.find(
        {"driver_name": {"$nin": ["", None]}},
        {"_id": 0, "driver_name": 1}
    ).to_list(5000)
    for r in receipts:
        if r.get("driver_name"):
            driver_names.add(r["driver_name"])

    # Fase 17.9 (2026-02-27): Dedupér navne-varianter. Hvis "Ferdal Turan"
    # og "ferdal" begge findes, beholder vi det LÆNGSTE navn (mest komplet)
    # og dropper de kortere varianter der er substrings af det.
    sorted_by_len = sorted(driver_names, key=lambda n: (-len(n), n.lower()))
    canonical = []
    for name in sorted_by_len:
        nlow = name.lower()
        is_substring_of_existing = any(
            nlow != c.lower() and nlow in c.lower() for c in canonical
        )
        if not is_substring_of_existing:
            canonical.append(name)

    return {"drivers": sorted(canonical, key=lambda n: n.lower())}

@api_router.get("/driver-archive/{driver_name}")
async def get_driver_archive_detail(driver_name: str):
    """Get a specific driver's daily archive: sessions, tours, receipts grouped by date.

    Fase 17.9 (2026-02-27): Token-baseret matching der merger
    chauffør-aliasser. Et navn som "Ferdal Turan" matcher alt der
    indeholder enten "ferdal" eller "turan" — så records oprettet med
    forskellige navne-varianter ("ferdal" ved login, "Ferdal Turan" på
    sessions, "Ferdal turan" på tours) alle havner under samme mappe.
    """
    import re as _re
    raw = (driver_name or "").strip()
    # Split i tokens > 2 tegn (ignorer "af", "og" osv.)
    tokens = [t.lower() for t in _re.split(r"\s+", raw) if len(t) > 2]
    if not tokens:
        tokens = [raw.lower()]
    # Byg én regex: (token1|token2|...) — match-as-substring, case-insens
    pattern = "(" + "|".join(_re.escape(t) for t in tokens) + ")"
    name_re = {"$regex": pattern, "$options": "i"}
    or_filter = [
        {"driver_name": name_re},
        {"claimed_by": name_re},
    ]

    sessions = await _raw_db.driver_sessions.find(
        {"driver_name": name_re}, {"_id": 0}
    ).to_list(2000)

    reports = await _raw_db.reports.find(
        {"driver_name": name_re}, {"_id": 0}
    ).sort("report_date", -1).to_list(2000)

    # Fase 17.11 (2026-02-27): Brug _raw_db for tours, sessions, reports,
    # receipts. Ellers ville TenantAwareDB filtrere chauffør-data væk:
    # ture er gemt under KUNDENS company_id (genbrugsplads), men
    # logistik-admin'en der ejer chaufføren bruger sin egen company_id.
    # Driver-archive er admin-only og skal vise chaufførens DATA samlet
    # uanset hvilken kunde turen var for.
    tours = await _raw_db.tours.find(
        {"$or": or_filter, "tour_type": {"$ne": "estimat"}},
        {"_id": 0, "receipt_image": 0}
    ).to_list(5000)

    receipts = await _raw_db.receipts.find(
        {"driver_name": name_re},
        {"_id": 0, "image_data": 0}
    ).sort("created_at", -1).to_list(2000)

    # Fase 18.1 (2026-02-28): Hent driver_time_entries (IND/PAUSE/UD-stempler)
    # for ALLE chauffør-aliasser. Disse er nu den autoritative kilde til
    # start/slut/varighed pr. dag — driver_sessions er legacy fallback.
    # Vi slår driver_ids op via users-collection så vi matcher samme tokens
    # som turene/sessions ovenfor.
    user_docs = await _raw_db.users.find(
        {"$or": [{"name": name_re}, {"display_name": name_re}],
         "role": "driver"},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1},
    ).to_list(50)
    driver_ids = [u["id"] for u in user_docs if u.get("id")]
    entries = []
    if driver_ids:
        entries = await _raw_db.driver_time_entries.find(
            {"driver_id": {"$in": driver_ids},
             "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
            {"_id": 0},
        ).sort([("date", -1), ("start_time", 1)]).to_list(5000)

    # Group everything by date
    dates = {}

    def ensure_date(d):
        if d not in dates:
            dates[d] = {"date": d, "sessions": [], "reports": [], "tours": [],
                        "receipts": [], "receipt_ids": [], "entries": [],
                        "time_summary": None}

    for session in sessions:
        d = session.get("report_date", "")
        if not d:
            continue
        ensure_date(d)
        dates[d]["sessions"].append(session)

    for report in reports:
        d = report.get("report_date", "")
        if not d:
            continue
        ensure_date(d)
        dates[d]["reports"].append(report)

    # Fase 18.1 (2026-02-28): Tilføj driver_time_entries til hver dag.
    for entry in entries:
        d = entry.get("date", "")
        if not d:
            continue
        ensure_date(d)
        dates[d]["entries"].append(entry)

    # Get tour IDs that have receipt images (same case-insensitive filter, raw DB)
    tour_ids_with_images = set()
    tours_with_imgs = await _raw_db.tours.find(
        {"$or": or_filter, "receipt_image": {"$ne": ""}},
        {"_id": 0, "id": 1}
    ).to_list(5000)
    for t in tours_with_imgs:
        tour_ids_with_images.add(t.get("id", ""))

    for tour in tours:
        d = tour.get("date", "")
        if not d:
            continue
        ensure_date(d)
        tour["has_receipt_image"] = tour.get("id", "") in tour_ids_with_images
        dates[d]["tours"].append(tour)

    for receipt in receipts:
        d = receipt.get("date", "")
        if not d:
            continue
        ensure_date(d)
        dates[d]["receipts"].append(receipt)
        dates[d]["receipt_ids"].append(receipt.get("id"))

    # Sort by date descending
    sorted_dates = sorted(dates.values(), key=lambda x: x["date"], reverse=True)

    # Fase 18.1 (2026-02-28): Beregn time_summary pr. dag baseret på
    # driver_time_entries. Åbne slices i dag tæller frem til "nu".
    _now_dt = datetime.now(tz=_LOCAL_TZ)
    _today_str = _now_dt.strftime("%Y-%m-%d")
    _now_hhmm = _now_dt.strftime("%H:%M")
    for day in sorted_dates:
        if day.get("entries"):
            day["time_summary"] = _summarize_day_entries(
                day["entries"],
                today_str=(_today_str if day["date"] == _today_str else ""),
                now_hhmm=(_now_hhmm if day["date"] == _today_str else ""),
            )

    return {"driver_name": driver_name, "days": sorted_dates}

@api_router.get("/receipts/{receipt_id}/image")
async def get_receipt_image(receipt_id: str):
    """Get just the image data for a single receipt (for download)"""
    receipt = await db.receipts.find_one({"id": receipt_id}, {"_id": 0, "image_data": 1, "description": 1, "date": 1})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"image_data": receipt.get("image_data", ""), "description": receipt.get("description", ""), "date": receipt.get("date", "")}


@api_router.get("/receipts/{receipt_id}/image-binary")
async def get_receipt_image_binary(receipt_id: str):
    """Stream the receipt image as a raw binary response.

    Fase 17 (2026-02-27): The legacy /image endpoint returns the image as
    base64 inside a JSON envelope which forces the browser to load the
    entire payload before rendering anything. For large iPhone photos
    (10–20 MB base64) the detail-modal appears to freeze. This endpoint
    decodes once and streams a proper image/jpeg response so the <img>
    tag can render progressively.

    Tenant-bypass like /full — locations admins and super-admins may need
    cross-tenant access to images. The id is a UUID so collision risk is
    negligible.
    """
    receipt = await _raw_db.receipts.find_one({"id": receipt_id}, {"_id": 0, "image_data": 1})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    b64 = receipt.get("image_data") or ""
    raw = _b64_to_bytes(b64)
    if not raw:
        raise HTTPException(status_code=404, detail="No image stored on receipt")
    # Image format is typically JPEG (driver uploads from phone camera).
    return Response(content=raw, media_type="image/jpeg")


# ============= FASE 16: KVITTERINGSSCANNING (OCR) + ARKIV =============

def _b64_to_bytes(b64: str) -> bytes:
    """Strip data:URL prefix if present, then decode base64."""
    if not b64:
        return b""
    if "," in b64 and ";base64" in b64.split(",", 1)[0]:
        b64 = b64.split(",", 1)[1]
    try:
        return base64.b64decode(b64)
    except Exception:
        return b""


async def _resolve_customer_company_for_tour(tour: dict) -> str:
    """Best-effort lookup of the customer-company-id a tour belongs to.

    Order of precedence:
      1. tour.order_id  → container_orders.company_id
      2. tour.customer_code → companies.customer_id → company.id
    """
    order_id = tour.get("order_id") or ""
    if order_id:
        order = await _raw_db.container_orders.find_one(
            {"id": order_id}, {"_id": 0, "company_id": 1}
        )
        if order and order.get("company_id"):
            return order["company_id"]

    cust_code = (tour.get("customer_code") or "").strip()
    if cust_code:
        comp = await _raw_db.companies.find_one(
            {"customer_id": cust_code}, {"_id": 0, "id": 1}
        )
        if comp and comp.get("id"):
            return comp["id"]
    return ""


class ReceiptOCRScanRequest(BaseModel):
    image_data: str  # base64-encoded image (with or without data:URL prefix)
    content_type: str = ""


@api_router.get("/ocr/status")
async def ocr_status():
    """Diagnostic — confirms whether OCR is wired up correctly."""
    return {"available": _ocr_is_available(), "message": _ocr_status_message()}


@api_router.post("/receipts/ocr-scan")
async def receipts_ocr_scan(req: ReceiptOCRScanRequest, payload: dict = Depends(get_current_user_payload)):
    """Pure OCR: takes a base64 image, returns parsed net weight + raw text.
    Does NOT persist anything — frontend uses this to preview before saving."""
    image_bytes = _b64_to_bytes(req.image_data)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Tomt eller ugyldigt billede")
    if _ocr_extract is None:
        raise HTTPException(status_code=503, detail=_ocr_status_message())

    # Run blocking call off the event loop.
    result = await async_lib.get_event_loop().run_in_executor(
        None, _ocr_extract, image_bytes, req.content_type
    )
    if result.get("error") and not _ocr_is_available():
        # Vision creds missing → 503 so frontend can fall back to manual entry.
        raise HTTPException(status_code=503, detail=result["error"])
    return result


class ReceiptSaveForTourRequest(BaseModel):
    tour_id: str
    image_data: str  # base64
    content_type: str = ""
    description: str = ""
    # When provided, overrides the OCR-detected weight. When None we use
    # OCR's `weight_kg`. Pass 0 to explicitly save without a weight.
    final_weight_kg: Optional[float] = None
    user_name: str = ""  # for audit log (driver name or logistics admin name)
    # If True (or if the tour is a "løs afhentning"), the weight is appended
    # to tour.container_weights instead of replacing tour.weight.
    append_for_loose: bool = False
    # When True, the receipt is created but the tour itself is NOT touched —
    # used for late uploads / when the tour weight was already set client-side.
    skip_tour_update: bool = False


@api_router.post("/receipts/save-for-tour")
async def receipts_save_for_tour(req: ReceiptSaveForTourRequest, payload: dict = Depends(get_current_user_payload)):
    """Combined OCR + persist flow.

    - Runs OCR if Vision is available (best-effort; failures don't block saving).
    - Stores image + OCR metadata + audit log in `receipts` collection.
    - Updates the linked tour:
        * Normal tour: sets `weight` and stamps `completed=True` if requested.
        * Løs afhentning: appends to `container_weights` (sum becomes new weight).
    """
    tour = await db.tours.find_one({"id": req.tour_id}, {"_id": 0})
    if not tour:
        raise HTTPException(status_code=404, detail="Tour ikke fundet")

    image_bytes = _b64_to_bytes(req.image_data)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Tomt eller ugyldigt billede")

    # Run OCR (graceful — failure just leaves ocr fields empty).
    ocr_result = {}
    if _ocr_extract is not None:
        ocr_result = await async_lib.get_event_loop().run_in_executor(
            None, _ocr_extract, image_bytes, req.content_type
        )

    # Determine which weight ends up on the tour.
    is_loose = bool(
        req.append_for_loose
        or (tour.get("loose_estimated_count") or 0) > 0
    )
    proposed_weight = (
        req.final_weight_kg
        if req.final_weight_kg is not None
        else ocr_result.get("weight_kg")
    )

    # Always save the original image as base64 (back-compat with /receipts list).
    # For larger images this could be moved to GridFS; for now we keep it inline.
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    customer_company_id = await _resolve_customer_company_for_tour(tour)

    now_iso = datetime.now(timezone.utc).isoformat()
    audit_entry = {
        "ts": now_iso,
        "user": req.user_name or "",
        "action": "create",
        "before": None,
        "after": proposed_weight,
        "ocr_weight": ocr_result.get("weight_kg"),
        "ocr_confidence": ocr_result.get("confidence", 0.0),
    }

    ocr_status_str = "none"
    if ocr_result:
        if ocr_result.get("error"):
            ocr_status_str = "failed"
        elif ocr_result.get("weight_kg") is not None:
            ocr_status_str = "success"
        else:
            ocr_status_str = "failed"
    if req.final_weight_kg is not None and (
        ocr_result.get("weight_kg") is None
        or float(req.final_weight_kg or 0) != float(ocr_result.get("weight_kg") or 0)
    ):
        ocr_status_str = "manual"

    receipt = Receipt(
        driver_name=tour.get("claimed_by") or tour.get("driver_name") or "",
        plads=tour.get("plads") or "",
        tour_id=req.tour_id,
        customer_company_id=customer_company_id,
        fraction=tour.get("fraction") or "",
        description=req.description,
        image_data=image_b64,
        ocr_raw_text=ocr_result.get("raw_text", ""),
        ocr_weight_kg=ocr_result.get("weight_kg"),
        ocr_confidence=ocr_result.get("confidence", 0.0),
        ocr_candidates=ocr_result.get("candidates", []),
        ocr_status=ocr_status_str,
        ocr_error=ocr_result.get("error", "") or "",
        final_weight_kg=proposed_weight,
        audit_log=[audit_entry],
    )
    # CRITICAL: drop the default-empty `company_id` so the TenantAwareDB
    # wrapper can inject the current user's company_id. Without this fix
    # the receipt would be saved with company_id="" and become invisible
    # in the multi-tenant archive view.
    receipt_doc = receipt.model_dump()
    if not receipt_doc.get("company_id"):
        receipt_doc.pop("company_id", None)
    await db.receipts.insert_one(receipt_doc)

    # Update the tour's weight.
    new_tour_weight = None
    update_payload: Dict[str, Any] = {}
    if req.skip_tour_update:
        pass  # explicit no-op — receipt is saved without touching the tour
    elif is_loose:
        existing_weights = list(tour.get("container_weights") or [])
        if proposed_weight is not None:
            existing_weights.append(float(proposed_weight))
        new_tour_weight = sum(existing_weights) if existing_weights else None
        update_payload["container_weights"] = existing_weights
        if new_tour_weight is not None:
            update_payload["weight"] = new_tour_weight
    else:
        if proposed_weight is not None:
            update_payload["weight"] = float(proposed_weight)
            new_tour_weight = float(proposed_weight)

    if update_payload:
        await db.tours.update_one({"id": req.tour_id}, {"$set": update_payload})

    return {
        "receipt_id": receipt.id,
        "ocr": ocr_result,
        "tour_weight": new_tour_weight,
        "is_loose": is_loose,
        "ocr_status": ocr_status_str,
    }


class ReceiptWeightOverrideRequest(BaseModel):
    new_weight_kg: float
    user_name: str = ""
    reason: str = ""


@api_router.put("/receipts/{receipt_id}/weight-override")
async def receipts_weight_override(receipt_id: str, req: ReceiptWeightOverrideRequest):
    """Admin / driver manually overrides a receipt's final weight.

    Logs the change (before/after/user/timestamp/reason). If the receipt is
    attached to a non-loose tour, also re-syncs `tours.weight`. For loose
    tours we leave the tour weight untouched since multiple receipts feed it
    — admins should use the tour edit dialog for that.
    """
    receipt = await db.receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    before = receipt.get("final_weight_kg")
    after = float(req.new_weight_kg or 0)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": req.user_name or "",
        "action": "weight_override",
        "before": before,
        "after": after,
        "reason": req.reason or "",
    }
    audit = list(receipt.get("audit_log") or [])
    audit.append(entry)
    await db.receipts.update_one(
        {"id": receipt_id},
        {"$set": {
            "final_weight_kg": after,
            "ocr_status": "manual",
            "audit_log": audit,
        }},
    )

    # Sync tour weight for non-loose tours.
    tour_id = receipt.get("tour_id") or ""
    if tour_id:
        tour = await db.tours.find_one({"id": tour_id}, {"_id": 0})
        if tour and (tour.get("loose_estimated_count") or 0) == 0:
            await db.tours.update_one(
                {"id": tour_id}, {"$set": {"weight": after}}
            )

    return {"updated": True, "audit_log": audit}


@api_router.get("/receipts-archive")
async def receipts_archive(
    date_from: str = "",
    date_to: str = "",
    driver_name: str = "",
    plads: str = "",
    fraction: str = "",
    customer_company_id: str = "",
    search: str = "",
    limit: int = 200,
    offset: int = 0,
):
    """Logistics-admin archive — tenant-scoped via TenantAwareDB. Filters:
    date range, driver, plads, fraction, customer-company, free-text in OCR text.

    Fase 18.3 (2026-02-28): Tekst-filtrene (`driver_name`, `plads`, `fraction`)
    bruger nu case-insensitive REGEX partial match — så "ferd" matcher
    "Ferdal Turan" osv. Tidligere krævede de eksakt match og returnerede
    altid 0 resultater når man begyndte at skrive. Hver række beriges
    desuden med `tour_started_at` + `tour_completed_at` fra den linkede
    tur, så Tabel-visningen kan vise tur-start og tur-slut.
    """
    def _ci_partial(val: str):
        # Escape regex meta-tegn og returner case-insensitive partial.
        return {"$regex": re.escape(val.strip()), "$options": "i"}

    query: Dict[str, Any] = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})
        query["date"]["$lte"] = date_to
    if driver_name:
        query["driver_name"] = _ci_partial(driver_name)
    if plads:
        query["plads"] = _ci_partial(plads)
    if fraction:
        query["fraction"] = _ci_partial(fraction)
    if customer_company_id:
        query["customer_company_id"] = customer_company_id
    if search:
        # Fase 18.5 (2026-02-28): Søgningen var tidligere kun mod
        # `ocr_raw_text` + `description`. Da OCR blev fjernet, er
        # ocr_raw_text tomt for nye kvitteringer og description er
        # sjældent udfyldt — søgningen returnerede derfor 0 træf.
        # Søger nu også i driver_name, plads, fraction, og id (alle
        # case-insensitive partial). Tour-id'et bruges ved support.
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"ocr_raw_text": {"$regex": pattern, "$options": "i"}},
            {"description": {"$regex": pattern, "$options": "i"}},
            {"driver_name": {"$regex": pattern, "$options": "i"}},
            {"plads": {"$regex": pattern, "$options": "i"}},
            {"fraction": {"$regex": pattern, "$options": "i"}},
            {"id": {"$regex": pattern, "$options": "i"}},
            {"tour_id": {"$regex": pattern, "$options": "i"}},
        ]
    total = await db.receipts.count_documents(query)
    items = await db.receipts.find(
        query,
        {"_id": 0, "image_data": 0, "ocr_raw_text": 0, "ocr_candidates": 0},
    ).sort("created_at", -1).skip(max(0, offset)).limit(min(limit, 500)).to_list(min(limit, 500))

    # Fase 18.3: Berig hver kvittering med tur-start (on_way_time) +
    # tur-slut (completed_at). Bruger _raw_db da turene kan ligge under
    # kunde-tenant og ellers filtreres væk af TenantAwareDB.
    tour_ids = [it.get("tour_id") for it in items if it.get("tour_id")]
    tour_times: Dict[str, Dict[str, str]] = {}
    if tour_ids:
        tour_docs = await _raw_db.tours.find(
            {"id": {"$in": list(set(tour_ids))}},
            {"_id": 0, "id": 1, "on_way_time": 1, "completed_at": 1,
             "claimed_at": 1, "time": 1},
        ).to_list(2000)
        for t in tour_docs:
            tour_times[t["id"]] = {
                "started": t.get("on_way_time") or "",
                "completed": t.get("completed_at") or t.get("time") or "",
                "claimed": t.get("claimed_at") or "",
            }
    for it in items:
        tt = tour_times.get(it.get("tour_id") or "", {})
        it["tour_started_at"] = tt.get("started", "")
        it["tour_completed_at"] = tt.get("completed", "")
        it["tour_claimed_at"] = tt.get("claimed", "")

    return {"total": total, "items": items, "offset": offset, "limit": limit}


@api_router.get("/receipts-location-documents")
async def receipts_location_documents(
    company_id: str = "",
    date_from: str = "",
    date_to: str = "",
    plads: str = "",
    fraction: str = "",
    search: str = "",
    limit: int = 200,
    offset: int = 0,
):
    """Location-admin / customer-admin view — only shows receipts whose
    `customer_company_id` matches the caller's company (or sub-companies they
    administer). `company_id` query-param can be used by super-admin to view
    any specific customer.
    """
    target_ids: List[str] = []
    if company_id:
        target_ids = [company_id]
    else:
        # Default: current acting company (the location admin's own company).
        cid = current_company_id.get() or ""
        if cid:
            target_ids = [cid]
    if not target_ids:
        return {"total": 0, "items": [], "offset": offset, "limit": limit}

    # Important: bypass the per-company tenant filter for *this* lookup —
    # logistics-side receipts are tenant-scoped to the LOGISTICS company, but
    # location admins on the CUSTOMER side need to see receipts tagged with
    # their own customer_company_id regardless of which logistics partner
    # created them.
    query: Dict[str, Any] = {"customer_company_id": {"$in": target_ids}}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})
        query["date"]["$lte"] = date_to
    if plads:
        query["plads"] = plads
    if fraction:
        query["fraction"] = fraction
    if search:
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"ocr_raw_text": {"$regex": pattern, "$options": "i"}},
            {"description": {"$regex": pattern, "$options": "i"}},
        ]
    total = await _raw_db.receipts.count_documents(query)
    items = await _raw_db.receipts.find(
        query,
        {"_id": 0, "image_data": 0, "ocr_raw_text": 0, "ocr_candidates": 0},
    ).sort("created_at", -1).skip(max(0, offset)).limit(min(limit, 500)).to_list(min(limit, 500))
    return {"total": total, "items": items, "offset": offset, "limit": limit}


@api_router.get("/receipts/{receipt_id}/full")
async def receipts_full(receipt_id: str):
    """Single receipt metadata for the archive's detail modal.

    Fase 17 (2026-02-27): `image_data` and `ocr_raw_text` are EXCLUDED
    from this response — they can be 10–20 MB on iPhone photos and made
    the modal feel frozen. The frontend now loads the image via the
    dedicated /receipts/{id}/image-binary endpoint which streams a raw
    image/jpeg the <img> tag can render progressively.

    Tenant-bypass: looks up by raw id since locations admins (customer
    side) may need to access receipts created by the logistics company.
    """
    receipt = await _raw_db.receipts.find_one(
        {"id": receipt_id},
        {"_id": 0, "image_data": 0, "ocr_raw_text": 0, "ocr_candidates": 0},
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    # Hint flag so the UI knows there IS an image — fetch it via /image-binary.
    receipt["has_image"] = True  # there's always at least an empty image field; image-binary will 404 if empty
    return receipt


# ============= FASE 16: PER-CUSTOMER RETENTION POLICY =============

class RetentionPolicyUpdate(BaseModel):
    receipt_retention_days: int


@api_router.get("/superadmin/retention-policies")
async def superadmin_retention_policies(
    payload: dict = Depends(require_super_admin),
):
    """List all customer companies + their current retention configuration."""
    companies = await _raw_db.companies.find(
        {"company_type": COMPANY_TYPE_CUSTOMER},
        {"_id": 0, "id": 1, "name": 1, "customer_id": 1, "receipt_retention_days": 1, "active": 1},
    ).sort("name", 1).to_list(2000)
    for c in companies:
        c.setdefault("receipt_retention_days", 1095)
    return {"companies": companies}


@api_router.put("/superadmin/companies/{company_id}/retention-policy")
async def superadmin_update_retention_policy(
    company_id: str,
    req: RetentionPolicyUpdate,
    payload: dict = Depends(require_super_admin),
):
    if req.receipt_retention_days < 30 or req.receipt_retention_days > 36500:
        raise HTTPException(
            status_code=400,
            detail="receipt_retention_days skal være mellem 30 og 36500 (100 år)",
        )
    result = await _raw_db.companies.update_one(
        {"id": company_id},
        {"$set": {"receipt_retention_days": int(req.receipt_retention_days)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"updated": True, "receipt_retention_days": req.receipt_retention_days}


# ============= PUSH NOTIFICATION ENDPOINTS =============

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").replace("\\n", "\n")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@containerflow.com")
_VAPID_OBJ: Any = None


def _vapid_key():
    """VAPID-nøglen som Vapid-objekt. Accepterer både PEM (fra
    scripts/gen-vapid.py, med \\n i env) og rå base64url-nøgle."""
    global _VAPID_OBJ
    if _VAPID_OBJ is None:
        _VAPID_OBJ = False
        k = (VAPID_PRIVATE_KEY or "").strip()
        if k:
            try:
                from py_vapid import Vapid
                _VAPID_OBJ = Vapid.from_pem(k.encode()) if "BEGIN" in k else Vapid.from_string(k)
            except Exception as e:  # noqa: BLE001
                logger.error(f"VAPID-nøglen kunne ikke læses: {e}")
    return _VAPID_OBJ or None

@api_router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    return {"public_key": VAPID_PUBLIC_KEY}

@api_router.post("/push/subscribe")
async def push_subscribe(data: PushSubscriptionCreate, payload: dict = Depends(get_current_user_payload)):
    """2026-10-17: Push til chauffører er slået TIL igen (standard). Ét
    abonnement pr. enhed (endpoint), så telefon og iPad begge får besked.
    Gemmes med driver_id + firma, så beskeder aldrig går til en forkert
    chauffør med samme navn i et andet firma."""
    sub = data.subscription or {}
    if not sub.get("endpoint") or not (sub.get("keys") or {}).get("p256dh"):
        raise HTTPException(status_code=400, detail="Ugyldigt abonnement")
    uid = payload.get("sub") or ""
    me = await _raw_db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "company_id": 1}) or {}
    await _raw_db.push_subscriptions.delete_many({"endpoint": sub["endpoint"]})
    doc = PushSubscription(driver_name=me.get("name") or data.driver_name, endpoint=sub["endpoint"], keys=sub["keys"]).model_dump()
    doc.update({"driver_id": uid, "company_id": me.get("company_id") or payload.get("company_id") or "",
                "role": payload.get("role") or ""})
    await _raw_db.push_subscriptions.insert_one(doc)
    if payload.get("role") == "driver":
        await _raw_db.users.update_one({"id": uid}, {"$set": {"push_enabled": True}})
    return {"subscribed": True}


@api_router.delete("/push/unsubscribe")
async def push_unsubscribe(endpoint: str = "", payload: dict = Depends(get_current_user_payload)):
    q = {"driver_id": payload.get("sub") or "__none__"}
    if endpoint:
        q["endpoint"] = endpoint
    res = await _raw_db.push_subscriptions.delete_many(q)
    return {"unsubscribed": res.deleted_count}


class PushSettingsIn(BaseModel):
    enabled: bool


@api_router.put("/driver/push-settings")
async def driver_push_settings(body: PushSettingsIn, payload: dict = Depends(get_current_user_payload)):
    """Chaufføren slår notifikationer til/fra (Profil). Fra = alle enheders
    abonnementer slettes, og der sendes intet før de slås til igen."""
    uid = payload.get("sub") or ""
    await _raw_db.users.update_one({"id": uid}, {"$set": {"push_enabled": bool(body.enabled)}})
    if not body.enabled:
        await _raw_db.push_subscriptions.delete_many({"driver_id": uid})
    return {"push_enabled": bool(body.enabled)}


@api_router.post("/push/send")
async def send_push_notification(data: PushNotificationSend, payload: dict = Depends(get_current_user_payload)):
    """Manuel push fra logistik admin til egne chauffører (før: uden login)."""
    if payload.get("role") not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    cid = payload.get("company_id") or ""
    q: Dict[str, Any] = {"role": "driver", "company_id": cid}
    if data.driver_names:
        q["name"] = {"$in": data.driver_names}
    drivers = await _raw_db.users.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    sent = 0
    for d in drivers:
        sent += await _push_driver(cid, d["id"], d.get("name", ""), data.title, data.body, url=data.url)
    return {"sent": sent}


# ============= MULTI-TENANT AUTH / SUPER ADMIN / GENBRUG PLADS =============

# ----- Middleware that sets the company_id contextvar from the JWT (if any) -----
# Simple in-memory cache for company active-status (refreshed every 30s) so we
# don't hit Mongo on every request.
_company_active_cache: dict = {}
_company_cache_ts: dict = {}
_COMPANY_CACHE_TTL = 30  # seconds


async def _is_company_active(company_id: str) -> bool:
    """Returns True if the company can perform operations.

    Pr. brugerkrav 2026-06-15 (runde 8): Når en LOGISTIK-partner deaktiveres
    skal det IKKE blokere login eller eksisterende workflows for de brugere
    der historisk har refereret til den partner. Deaktivering af logistik-
    partner betyder kun at den ikke længere kan VÆLGES på bestillingssiden
    eller af kunde-admins fremadrettet. KUN deaktivering af et KUNDE-firma
    skal blokere login (det er den ægte "suspender"-funktion).
    """
    if not company_id or company_id in (SUPER_ADMIN_BYPASS, DEFAULT_COMPANY_ID):
        return True
    import time as _t
    now = _t.time()
    if company_id in _company_active_cache and now - _company_cache_ts.get(company_id, 0) < _COMPANY_CACHE_TTL:
        return _company_active_cache[company_id]
    doc = await _raw_db.companies.find_one(
        {"id": company_id}, {"_id": 0, "active": 1, "company_type": 1},
    )
    if doc is None:
        active = True
    else:
        is_active_flag = bool(doc.get("active", True))
        company_type = (doc.get("company_type") or "customer").strip().lower()
        # Logistik-firmaer "deaktiveres" kun for UI-listing-formål — login og
        # eksisterende drift skal stadig fungere uændret.
        if company_type == "logistics":
            active = True
        else:
            active = is_active_flag
    _company_active_cache[company_id] = active
    _company_cache_ts[company_id] = now
    return active


def invalidate_company_cache(company_id: Optional[str] = None) -> None:
    if company_id is None:
        _company_active_cache.clear()
        _company_cache_ts.clear()
    else:
        _company_active_cache.pop(company_id, None)
        _company_cache_ts.pop(company_id, None)


# Paths that are always allowed even when the user's company is suspended
# (so they can still log in/out and see a clear error message).
SUSPENDED_ALLOW_PATHS = {"/api/auth/me", "/api/auth/logout", "/api/auth/login", "/api/health"}


# ============= KOORDINATORER + RETTIGHEDER (2026-10-17) =============
# En koordinator er en bruger med role=logistics_admin + is_coordinator=True og
# et sæt rettigheder. Firmaets administrator(er) (is_coordinator falsk) har
# altid alle rettigheder. Kontrollen sker centralt i TenantContextMiddleware
# (rute -> rettighed), så ingen endpoint kan glemmes; PUT /tours/{id} tjekkes i
# update_tour, fordi rettigheden afhænger af hvilke felter der ændres.
COORDINATOR_PERMS = [
    ("tours_edit", "Opret og ret ture"),
    ("tours_assign", "Tildel chauffører"),
    ("tours_delete", "Slet ture"),
    ("messages", "Skriv med chauffører"),
    ("planning", "Planlægning og tidsregistrering"),
    ("drivers", "Chauffører og flåde"),
    ("reports", "Rapportering"),
    ("economy_view", "Se priser og økonomi"),
    ("economy_edit", "Ændre priser, rette og godkende"),
    ("locations", "Lokationer"),
    ("archive", "Arkiv (dagrapporter og kvitteringer)"),
    ("settings", "Indstillinger"),
    ("team", "Team og rettigheder"),
]
COORDINATOR_PERM_KEYS = [k for k, _ in COORDINATOR_PERMS]
COORDINATOR_PERM_LABEL = dict(COORDINATOR_PERMS)

_PERM_ROUTES = [
    # (metoder, regex, rettighed). GET på /pricing kræver kun "se".
    ({"GET"}, re.compile(r"^/api/pricing/"), "economy_view"),
    ({"POST", "PUT", "DELETE", "PATCH"}, re.compile(r"^/api/pricing/"), "economy_edit"),
    ({"GET"}, re.compile(r"^/api/admin/statistics"), "reports"),
    ({"POST", "PUT", "DELETE"}, re.compile(r"^/api/(drivers|vehicles|trailers)(/|$)"), "drivers"),
    ({"POST", "PUT", "DELETE"}, re.compile(r"^/api/plads(/|$)"), "locations"),
    ({"POST"}, re.compile(r"^/api/tours(/bulk)?/?$"), "tours_edit"),
    ({"POST"}, re.compile(r"^/api/tours/upload-template$"), "tours_edit"),
    ({"POST"}, re.compile(r"^/api/tours/[^/]+/reactivate$"), "tours_edit"),
    ({"POST"}, re.compile(r"^/api/parse-mail"), "tours_edit"),
    ({"POST"}, re.compile(r"^/api/tours/bulk-assign$"), "tours_assign"),
    ({"DELETE"}, re.compile(r"^/api/tours/[^/]+$"), "tours_delete"),
    ({"POST"}, re.compile(r"^/api/tour-messages/"), "messages"),
    ({"GET", "POST", "PUT", "DELETE"}, re.compile(r"^/api/logistics/team"), "team"),
    ({"POST", "PUT", "DELETE"}, re.compile(r"^/api/logistics/customers"), "tours_edit"),
    ({"GET", "POST"}, re.compile(r"^/api/admin/day-report"), "archive"),
]
_perm_cache: Dict[str, tuple] = {}


async def _coordinator_perms(uid: str) -> Optional[dict]:
    """None = fuld adgang (administrator). Ellers dict med rettigheder."""
    hit = _perm_cache.get(uid)
    if hit and _time.time() - hit[0] < 15:
        return hit[1]
    u = await _raw_db.users.find_one({"id": uid}, {"_id": 0, "is_coordinator": 1, "permissions": 1, "active": 1,
                                                  "customer_scope": 1})
    perms = None
    if u and u.get("is_coordinator"):
        perms = {k: bool((u.get("permissions") or {}).get(k)) for k in COORDINATOR_PERM_KEYS}
        perms["__scope"] = list(u.get("customer_scope") or [])
        # Deaktiveret koordinator: ingen adgang, heller ikke med et gammelt token.
        perms["__active"] = u.get("active", True) is not False
    _perm_cache[uid] = (_time.time(), perms)
    return perms


def _effective_perms(user_doc: dict) -> dict:
    if user_doc.get("role") == "logistics_admin" and user_doc.get("is_coordinator"):
        return {k: bool((user_doc.get("permissions") or {}).get(k)) for k in COORDINATOR_PERM_KEYS}
    return {k: True for k in COORDINATOR_PERM_KEYS}


async def _la_scope(payload: Optional[dict]) -> Optional[set]:
    """2026-10-17: En koordinator kan begrænses til bestemte kunder
    (genbrugsplads-kunders company_id og/eller "own" = firmaets egne ture).
    None = ingen begrænsning."""
    if (payload or {}).get("role") != "logistics_admin":
        return None
    perms = await _coordinator_perms(payload.get("sub") or "")
    scope = (perms or {}).get("__scope") or []
    return set(scope) if scope else None


def _scope_ok(t: dict, scope: Optional[set], la: str) -> bool:
    if not scope:
        return True
    cid = t.get("company_id") or ""
    return ("own" in scope) if cid == la else (cid in scope)


async def _require_tour_scope(payload: dict, tour_ids: List[str]) -> List[str]:
    """Filtrerer tur-id'er til dem koordinatoren må røre."""
    scope = await _la_scope(payload)
    if not scope:
        return tour_ids
    la = payload.get("company_id") or ""
    docs = await _raw_db.tours.find({"id": {"$in": tour_ids}}, {"_id": 0, "id": 1, "company_id": 1}).to_list(len(tour_ids) + 1)
    return [d["id"] for d in docs if _scope_ok(d, scope, la)]


async def _require_perm(payload: dict, key: str):
    if (payload or {}).get("role") != "logistics_admin":
        return
    perms = await _coordinator_perms(payload.get("sub") or "")
    if perms is not None and not perms.get(key):
        raise HTTPException(status_code=403, detail=f"Du har ikke rettighed til: {COORDINATOR_PERM_LABEL.get(key, key)}")


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        is_public = (
            path in PUBLIC_PATH_EXACT
            or any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES)
        )

        cid = DEFAULT_COMPANY_ID
        uid = None
        role = None
        user_company_id = None
        managed_company_ids: list = []

        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = decode_token(token)
                uid = payload.get("sub")
                role = payload.get("role")
                user_company_id = payload.get("company_id", DEFAULT_COMPANY_ID)
                managed_company_ids = list(payload.get("managed_company_ids") or [])
                if role == "super_admin":
                    cid = SUPER_ADMIN_BYPASS
                else:
                    cid = user_company_id
            except HTTPException:
                pass

        # Acting-Company override: a logistics_admin (or super_admin) may pass
        # an X-Acting-Company-Id header to operate on a different company's
        # data (e.g. tours/pladser for a managed client company).
        acting = request.headers.get("x-acting-company-id") or request.headers.get("X-Acting-Company-Id")
        if acting and role in ("logistics_admin", "super_admin"):
            acting = acting.strip()
            if role == "super_admin":
                cid = acting  # super admin may act as any company
            elif acting == user_company_id or acting in managed_company_ids:
                cid = acting  # found in JWT — fast path
            else:
                # Fall back to a fresh DB lookup so newly-assigned companies
                # take effect on next page reload without requiring re-login.
                doc = await _raw_db.users.find_one(
                    {"id": uid}, {"_id": 0, "managed_company_ids": 1},
                )
                fresh_managed = (doc or {}).get("managed_company_ids") or []
                if acting in fresh_managed:
                    cid = acting
                else:
                    from starlette.responses import JSONResponse
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Du har ikke adgang til denne virksomhed"},
                    )

        # 2026-10-17: Koordinator-rettigheder (se COORDINATOR_PERMS).
        if role == "logistics_admin" and uid and path.startswith("/api/") and not is_public:
            _cp = await _coordinator_perms(uid)
            if _cp is not None and not _cp.get("__active", True):
                from starlette.responses import JSONResponse
                return JSONResponse(status_code=401, content={"detail": "Din adgang er deaktiveret"})
            needed = next((perm for methods, rx, perm in _PERM_ROUTES
                           if request.method in methods and rx.match(path)), None)
            if needed:
                perms = await _coordinator_perms(uid)
                if perms is not None and not perms.get(needed):
                    from starlette.responses import JSONResponse
                    return JSONResponse(status_code=403, content={
                        "detail": f"Du har ikke rettighed til: {COORDINATOR_PERM_LABEL.get(needed, needed)}",
                        "missing_permission": needed})

        # Company suspension check: block any non-super-admin user whose company is inactive.
        # We allow auth endpoints (login/logout/me) so users can still authenticate / log out
        # and see a friendly error message in the UI.
        if (
            user_company_id
            and role != "super_admin"
            and path not in SUSPENDED_ALLOW_PATHS
            and not is_public
        ):
            active = await _is_company_active(user_company_id)
            if not active:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Din virksomheds adgang er suspenderet. Kontakt din administrator.",
                        "company_suspended": True,
                    },
                )

        if is_public:
            cid = SUPER_ADMIN_BYPASS

        # Multi-company READ visibility: for non-admin roles (driver, order,
        # genbrug_plads) whose company "serves" other companies, expand the
        # read view so they see merged data. Writes still go to the primary
        # cid via _inject_doc.
        extra_visible: list = []
        if (
            role in ("driver", "order", "genbrug_plads")
            and cid not in (SUPER_ADMIN_BYPASS, "", None)
        ):
            comp = await _raw_db.companies.find_one(
                {"id": cid}, {"_id": 0, "serves_company_ids": 1}
            )
            if comp:
                extra_visible = [c for c in (comp.get("serves_company_ids") or []) if c]

        # NOTE: per-location logistics partnership (drivers seeing customer
        # locations explicitly assigned to their logistics company) is enforced
        # below the tenant filter, directly inside the relevant endpoints
        # (`/api/plads`, `/api/tours`) via a `assigned_logistics_company_ids`
        # match. We deliberately do NOT widen `extra_visible` here so that a
        # partnered customer's *unrelated* records (e.g. a different location)
        # stay hidden from this driver.

        t1 = current_company_id.set(cid)
        t2 = current_user_id.set(uid)
        t3 = current_user_role.set(role)
        t4 = current_extra_visible_company_ids.set(extra_visible)
        try:
            response = await call_next(request)
        finally:
            current_company_id.reset(t1)
            current_user_id.reset(t2)
            current_user_role.reset(t3)
            current_extra_visible_company_ids.reset(t4)
        return response


# ----- Helpers -----
async def _get_company_name(company_id: str) -> Optional[str]:
    if not company_id or company_id == SUPER_ADMIN_BYPASS:
        return None
    doc = await _raw_db.companies.find_one({"id": company_id}, {"_id": 0})
    return doc.get("name") if doc else None


# --------------------------------------------------------------------------- #
# Fase 15.40 (2026-02-22): Klient-platformsfunktioner (feature flags pr. klient)
# --------------------------------------------------------------------------- #
# Master-liste over alle feature-keys super-admin kan toggle pr. klient. Vi
# bruger en konstant dict så det er typesikkert og let at udvide. Brugerens
# valg: DISABLED er default for ALLE klienter — super-admin må aktivt slå til.
FEATURE_KEYS: Dict[str, str] = {
    "estimate": "Aktiverer estimatfunktionen på bestillingsside og i logistik-planlægning",
    "loes_afhentning": "Aktiverer 'Løs afhentning' — kunden ejer ikke containere; chauffør medbringer egne og registrerer vægt pr. container",
}
DEFAULT_FEATURE_ENABLED: bool = False


async def get_company_features(company_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Returner det fulde feature-map for én klient (firma). Manglende rækker
    = DISABLED (per Fase 15.40-default).

    Output-form pr. feature:
        {key, enabled, description, updated_at, updated_by}
    """
    if not company_id or company_id == SUPER_ADMIN_BYPASS:
        return {
            k: {
                "key": k, "enabled": DEFAULT_FEATURE_ENABLED,
                "description": desc, "updated_at": None, "updated_by": None,
            } for k, desc in FEATURE_KEYS.items()
        }
    docs = await _raw_db.client_features.find(
        {"company_id": company_id}, {"_id": 0},
    ).to_list(None)
    by_key = {d.get("feature_key"): d for d in docs if d.get("feature_key")}
    out: Dict[str, Dict[str, Any]] = {}
    for k, desc in FEATURE_KEYS.items():
        d = by_key.get(k)
        out[k] = {
            "key": k,
            "enabled": bool(d.get("is_enabled")) if d else DEFAULT_FEATURE_ENABLED,
            "description": desc,
            "updated_at": (d.get("updated_at") if d else None),
            "updated_by": (d.get("updated_by_email") if d else None),
        }
    return out


async def is_feature_enabled(company_id: Optional[str], key: str) -> bool:
    """Single-feature lookup. Brug fra ENHVER backend-handler der vil gate
    en feature."""
    if key not in FEATURE_KEYS:
        return False
    feats = await get_company_features(company_id)
    return bool(feats.get(key, {}).get("enabled"))


async def get_features_dict_for_user(company_id: Optional[str]) -> Dict[str, bool]:
    """Kompakt {key: bool}-dict beregnet til frontend-cache (sendes med
    /auth/me og /clients/me/features).

    Fase 15.40 designvalg: Toggle ligger PR. KUNDE-ORGANISATION. Men LA-
    brugere har deres EGET company_id — så de ville ALDRIG se en feature
    aktiveret med naiv lookup. Derfor:

      - For en kunde-bruger (order/customer_admin/location_admin) → returner
        deres eget firmas features.
      - For en LA-bruger (logistics_admin/driver) → aggreger OR-logik på
        tværs af de kunder LA betjener (`serves_company_ids` på LA-firmaet).
        Hvis nogen kunde har feature ON, så ser LA også feature ON.

    Det betyder: SA toggler "estimate=ON" på ARGO → ARGO's order-medarbejdere
    ser feature → OG enhver LA der betjener ARGO ser også feature aktiveret
    i deres planlægnings-UI (så de kan håndtere ARGO's estimat-bestillinger).
    """
    if not company_id or company_id == SUPER_ADMIN_BYPASS:
        return {k: DEFAULT_FEATURE_ENABLED for k in FEATURE_KEYS}

    # 1) Læs firmaets egne features (uanset rolle).
    own = await get_company_features(company_id)
    aggregated: Dict[str, bool] = {k: bool(v.get("enabled")) for k, v in own.items()}

    # 2) Hvis firmaet betjener kunder (LA-pattern), aggreger OR-logik på tværs.
    comp = await _raw_db.companies.find_one(
        {"id": company_id}, {"_id": 0, "serves_company_ids": 1},
    )
    served = list((comp or {}).get("serves_company_ids") or [])
    served = [c for c in served if c and c != company_id]
    if served:
        # Læs alle feature-rows for de betjente kunder i én forespørgsel.
        rows = await _raw_db.client_features.find(
            {"company_id": {"$in": served}}, {"_id": 0, "feature_key": 1, "is_enabled": 1},
        ).to_list(None)
        for r in rows:
            k = r.get("feature_key")
            if k in aggregated and bool(r.get("is_enabled")):
                aggregated[k] = True  # OR-aggregering — én ON er nok
    return aggregated


def _user_to_public(user_doc: dict, company_name: Optional[str] = None) -> dict:
    return {
        "id": user_doc.get("id"),
        "email": user_doc.get("email"),
        "name": user_doc.get("name"),
        "role": user_doc.get("role"),
        "company_id": user_doc.get("company_id"),
        "company_name": company_name,
        "active": user_doc.get("active", True),
        "invitation_status": user_doc.get("invitation_status", "active"),
        "driver_name": user_doc.get("driver_name"),
        "phone": user_doc.get("phone"),
        "employment_date": user_doc.get("employment_date"),
        "location_code": user_doc.get("location_code"),
        "managed_company_ids": list(user_doc.get("managed_company_ids") or []),
        "is_hq_admin": bool(user_doc.get("is_hq_admin") or False),
        "assigned_plads_ids": list(user_doc.get("assigned_plads_ids") or []),
        "visible_plads_ids": list(user_doc.get("visible_plads_ids") or []),
        # Fase 10/11: Aktivt vognnummer + hænger så chauffør-frontend kan
        # vise den valgte hænger og lade chaufføren skifte den.
        "active_vehicle_id": user_doc.get("active_vehicle_id") or "",
        "active_trailer_id": user_doc.get("active_trailer_id") or "",
        "plate": user_doc.get("plate") or "",
        "created_at": user_doc.get("created_at"),
        "is_coordinator": bool(user_doc.get("is_coordinator")),
        "permissions": _effective_perms(user_doc),
        "customer_scope": list(user_doc.get("customer_scope") or []),
        "push_enabled": user_doc.get("push_enabled") is not False,
    }


# --------------------------------------------------------------------------- #
# Invitation / password-reset tokens
# --------------------------------------------------------------------------- #
import secrets as _secrets  # standard-library secure-random
from email_service import (  # local module
    send_invitation_email as _send_invitation_email,
    send_password_reset_email as _send_password_reset_email,
    send_missing_clock_reminder_email as _send_missing_clock_reminder_email,
)

INVITATION_TTL_HOURS = int(os.environ.get("INVITATION_TOKEN_TTL_HOURS", "72") or 72)
RESET_TTL_HOURS = int(os.environ.get("RESET_TOKEN_TTL_HOURS", "72") or 72)


def _new_token() -> str:
    """URL-safe ~32-byte token (resistant to brute-force/guessing)."""
    return _secrets.token_urlsafe(32)


async def _create_token(*, user_id: str, token_type: str, ttl_hours: int) -> dict:
    """Insert a fresh single-use token and invalidate any prior unused tokens
    of the same type for this user."""
    # Invalidate any earlier pending tokens of the same type so only ONE link
    # is ever valid at a time.
    await _raw_db.invitation_tokens.update_many(
        {"user_id": user_id, "token_type": token_type, "used": False},
        {"$set": {"used": True, "invalidated_at": datetime.now(timezone.utc).isoformat(), "invalidated_reason": "replaced"}},
    )
    doc = {
        "id": str(uuid.uuid4()),
        "token": _new_token(),
        "user_id": user_id,
        "token_type": token_type,  # "invitation" | "reset"
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
        "used": False,
    }
    await _raw_db.invitation_tokens.insert_one(doc)
    return doc


async def _consume_token(token: str, token_type: str) -> dict:
    """Look up + validate + mark-used in a single atomic-ish step. Returns the
    *user* doc that owned the token. Raises 400/410 on bad/expired tokens."""
    if not token:
        raise HTTPException(status_code=400, detail="Token mangler")
    tk = await _raw_db.invitation_tokens.find_one({"token": token, "token_type": token_type}, {"_id": 0})
    if not tk:
        raise HTTPException(status_code=400, detail="Ugyldigt link")
    if tk.get("used"):
        raise HTTPException(status_code=410, detail="Linket er allerede brugt")
    try:
        expires = datetime.fromisoformat(tk["expires_at"])
    except Exception:
        expires = datetime.now(timezone.utc) - timedelta(hours=1)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Linket er udløbet")
    user = await _raw_db.users.find_one({"id": tk["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Bruger findes ikke længere")
    # Mark used here — if anything goes wrong upstream it's still correct to
    # invalidate the token (security > convenience).
    await _raw_db.invitation_tokens.update_one(
        {"id": tk["id"]}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return user


async def _send_invite_for_user(user_doc: dict) -> Optional[dict]:
    """Generate an invitation token for the given user and email them the link."""
    tk = await _create_token(user_id=user_doc["id"], token_type="invitation", ttl_hours=INVITATION_TTL_HOURS)
    company = await _raw_db.companies.find_one({"id": user_doc.get("company_id")}, {"_id": 0, "name": 1, "company_type": 1})
    company_name = company.get("name") if company else "ContainerFlow"
    company_type = company.get("company_type") if company else "customer"
    try:
        return await _send_invitation_email(
            to_email=user_doc["email"],
            name=user_doc.get("name") or "",
            token=tk["token"],
            company_name=company_name,
            role=user_doc.get("role", ""),
            company_type=company_type,
            ttl_hours=INVITATION_TTL_HOURS,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("send invitation failed for %s: %s", user_doc.get("email"), e)
        return None


# ----- /api/auth router -----
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/login", response_model=LoginResponse)
async def auth_login(req: LoginRequest, request: Request):
    # Preserve the email exactly as typed, BUT match case-insensitively. We
    # deliberately do not strip non-ASCII (å, æ, ø) — those are valid email
    # local-parts in Danish setups.
    email_raw = (req.email or "").strip()
    email = email_raw.lower()
    ip = request.client.host if request.client else "unknown"
    if not email or not req.password:
        raise HTTPException(status_code=400, detail="Email og password er påkrævet")

    # --- Rate limit ---
    _rate_limit_check(request)
    # --- Brute-force check ---
    _bf_check(email)

    # Multi-tenant: the same email may exist multiple times across customers
    # (e.g. an ILK admin invited by both ARGO and MARTO with their own
    # per-customer password). Fetch every match and try them all — only the
    # row whose password verifies wins.
    candidates = await _raw_db.users.find(
        {"email": email}, {"_id": 0},
    ).to_list(100)
    if not candidates:
        # Fallback: try the raw-cased email (legacy/inadvertent caps stored)
        candidates = await _raw_db.users.find(
            {"email": email_raw}, {"_id": 0},
        ).to_list(100) if email_raw != email else []

    if not candidates:
        _bf_fail(email)
        await _raw_db.activity_log.insert_one({
            "id": str(uuid.uuid4()), "email": email, "action": "login_failed",
            "reason": "user_not_found", "ip": ip,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        raise HTTPException(status_code=401, detail="Forkert email eller password")

    user = None
    for cand in candidates:
        if not cand.get("active", True):
            continue
        # "pending" users have an empty password hash — they MUST go through
        # the invitation flow to set one before they can log in.
        if cand.get("invitation_status") == "pending" or not cand.get("password_hash"):
            continue
        if verify_password(req.password, cand.get("password_hash", "")):
            user = cand
            break

    if not user:
        # Differentiate the error: any active candidate with wrong password
        # vs all candidates inactive → 403 instead of 401 if all inactive.
        all_inactive = all(not c.get("active", True) for c in candidates)
        all_pending = candidates and all(
            (c.get("invitation_status") == "pending" or not c.get("password_hash"))
            for c in candidates if c.get("active", True)
        )
        _bf_fail(email)
        await _raw_db.activity_log.insert_one({
            "id": str(uuid.uuid4()), "email": email, "action": "login_failed",
            "reason": "all_inactive" if all_inactive else ("pending_invitation" if all_pending else "wrong_password"),
            "ip": ip, "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if all_inactive:
            raise HTTPException(status_code=403, detail="Brugeren er deaktiveret")
        if all_pending:
            raise HTTPException(
                status_code=403,
                detail="Du har ikke aktiveret din konto endnu — tjek din e-mail for invitations-linket.",
            )
        raise HTTPException(status_code=401, detail="Forkert email eller password")
    # Block login if the user's company is suspended (super_admin bypasses)
    if user.get("role") != "super_admin":
        _cid = user.get("company_id") or DEFAULT_COMPANY_ID
        if not await _is_company_active(_cid):
            await _raw_db.activity_log.insert_one({
                "id": str(uuid.uuid4()), "email": email, "action": "login_blocked_suspended",
                "company_id": _cid, "role": user.get("role", ""), "ip": ip,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            raise HTTPException(
                status_code=403,
                detail="Din virksomheds adgang er suspenderet. Kontakt din administrator.",
            )
    token = create_access_token(
        user_id=user["id"], email=user["email"], role=user["role"], company_id=user["company_id"],
        managed_company_ids=user.get("managed_company_ids") or [],
    )
    # Clear brute-force counter
    _bf_success(email)
    # Log successful login
    await _raw_db.activity_log.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "email": email,
        "action": "login_success", "role": user.get("role", ""),
        "company_id": user.get("company_id", ""), "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    company_name = await _get_company_name(user["company_id"])
    public = _user_to_public(user, company_name)
    # Fase 15.40: Inkludér features ved login så frontend cacher dem fra start.
    public["features"] = await get_features_dict_for_user(user.get("company_id"))
    return {"token": token, "user": public}


@auth_router.get("/me", response_model=UserPublic)
async def auth_me(payload: dict = Depends(get_current_user_payload)):
    user = await _raw_db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    company_name = await _get_company_name(user["company_id"])
    public = _user_to_public(user, company_name)
    # Fase 15.40: Inkludér aktive features for brugerens klient så frontend
    # kan gate UI uden ekstra rundtur ved page-load.
    public["features"] = await get_features_dict_for_user(user.get("company_id"))
    return public


@auth_router.get("/managed-companies")
async def auth_managed_companies(payload: dict = Depends(get_current_user_payload)):
    """Return the list of companies the current user may act on behalf of.

    - For `super_admin`: every active company.
    - For `logistics_admin`: own company + every company in `managed_company_ids`
      (only the ones still existing & active).
    - For other roles: just their own company.

    Each entry: {id, name, active, is_own}
    """
    role = payload.get("role")
    own_cid = payload.get("company_id")
    if role == "super_admin":
        docs = await _raw_db.companies.find({}, {"_id": 0}).to_list(1000)
        out = [
            {"id": d["id"], "name": d.get("name", d["id"]),
             "active": d.get("active", True), "is_own": False}
            for d in docs
        ]
        return out

    # Read fresh from DB so an admin's managed list takes effect on next page
    # reload (no need to re-login after Super Admin updates it).
    user = await _raw_db.users.find_one(
        {"id": payload.get("sub")},
        {"_id": 0, "company_id": 1, "managed_company_ids": 1, "role": 1},
    )
    if not user:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    ids = [user.get("company_id")]
    if role == "logistics_admin":
        for mid in (user.get("managed_company_ids") or []):
            if mid and mid not in ids:
                ids.append(mid)
    docs = await _raw_db.companies.find(
        {"id": {"$in": ids}}, {"_id": 0}
    ).to_list(1000)
    by_id = {d["id"]: d for d in docs}
    out = []
    for cid in ids:
        d = by_id.get(cid)
        if not d:
            continue
        out.append({
            "id": d["id"], "name": d.get("name", d["id"]),
            "active": d.get("active", True), "is_own": (cid == own_cid),
        })
    return out


@auth_router.post("/logout")
async def auth_logout():
    # Stateless JWT - client just discards the token. Endpoint exists for symmetry.
    return {"success": True}


@auth_router.post("/change-password")
async def auth_change_password(body: dict, payload: dict = Depends(get_current_user_payload)):
    old_pw = body.get("old_password", "")
    new_pw = body.get("new_password", "")
    if not new_pw or len(new_pw) < 4:
        raise HTTPException(status_code=400, detail="Nyt password skal være mindst 4 tegn")
    user = await _raw_db.users.find_one({"id": payload.get("sub")})
    if not user:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    if not verify_password(old_pw, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Forkert nuværende password")
    await _raw_db.users.update_one(
        {"id": user["id"]}, {"$set": {"password_hash": hash_password(new_pw)}}
    )
    return {"success": True}


# --------------------------------------------------------------------------- #
# Forgot / reset password + accept-invitation
# --------------------------------------------------------------------------- #
class ForgotPasswordRequest(BaseModel):
    email: str


class TokenSubmitRequest(BaseModel):
    token: str
    new_password: str


@auth_router.post("/forgot-password")
async def auth_forgot_password(body: ForgotPasswordRequest, request: Request):
    """Step 1 of Glemt adgangskode. Always returns 200 to avoid leaking which
    emails exist — but only actually emails when we find an active user.
    """
    # Reuse the login rate-limit window so this can't be abused for enumeration.
    _rate_limit_check(request)
    email = (body.email or "").strip().lower()
    if not email:
        return {"success": True}

    # Pick the most-recently-active user with this email — there may be more
    # than one across tenants. We don't ask which company they want; the reset
    # token is per-user-id so the link is unambiguous.
    candidates = await _raw_db.users.find(
        {"email": email, "active": True}, {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    for user in candidates:
        if not user.get("password_hash"):
            # User hasn't accepted their invitation yet — resend the invite
            # rather than a reset link, the UX is the same to the recipient.
            await _send_invite_for_user(user)
            break  # we only ever email ONE user per request
        tk = await _create_token(user_id=user["id"], token_type="reset", ttl_hours=RESET_TTL_HOURS)
        try:
            await _send_password_reset_email(
                to_email=user["email"],
                name=user.get("name") or "",
                token=tk["token"],
                ttl_hours=RESET_TTL_HOURS,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Reset email failed for %s: %s", email, e)
        break

    await _raw_db.activity_log.insert_one({
        "id": str(uuid.uuid4()), "email": email, "action": "forgot_password_requested",
        "matched": bool(candidates),
        "ip": request.client.host if request.client else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True}


@auth_router.post("/reset-password")
async def auth_reset_password(body: TokenSubmitRequest):
    if not body.new_password or len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="Nyt password skal være mindst 4 tegn")
    user = await _consume_token(body.token, token_type="reset")
    await _raw_db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.new_password), "active": True}},
    )
    return {"success": True, "email": user["email"]}


@auth_router.post("/accept-invitation")
async def auth_accept_invitation(body: TokenSubmitRequest):
    if not body.new_password or len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="Adgangskoden skal være mindst 4 tegn")
    user = await _consume_token(body.token, token_type="invitation")
    await _raw_db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password_hash": hash_password(body.new_password),
            "active": True,
            "invitation_status": "active",
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"success": True, "email": user["email"]}


@auth_router.get("/verify-token")
async def auth_verify_token(token: str = "", type: str = "invitation"):
    """Frontend pre-validation. Does NOT consume the token — only previews."""
    if not token:
        raise HTTPException(status_code=400, detail="Token mangler")
    if type not in ("invitation", "reset"):
        raise HTTPException(status_code=400, detail="Ukendt token-type")
    tk = await _raw_db.invitation_tokens.find_one({"token": token, "token_type": type}, {"_id": 0})
    if not tk:
        raise HTTPException(status_code=400, detail="Ugyldigt link")
    if tk.get("used"):
        raise HTTPException(status_code=410, detail="Linket er allerede brugt")
    try:
        if datetime.fromisoformat(tk["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Linket er udløbet")
    except (KeyError, ValueError):
        raise HTTPException(status_code=410, detail="Linket er udløbet")
    user = await _raw_db.users.find_one({"id": tk["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Bruger findes ikke længere")
    company = await _raw_db.companies.find_one(
        {"id": user.get("company_id")}, {"_id": 0, "name": 1, "company_type": 1},
    )
    return {
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role"),
        "company_name": company.get("name") if company else "",
        "company_type": company.get("company_type") if company else "",
        "expires_at": tk["expires_at"],
    }


# ----- /api/superadmin router (super_admin only) -----
sa_router = APIRouter(prefix="/api/superadmin", tags=["superadmin"], dependencies=[Depends(require_super_admin)])


# Fase 15.14 (2026-02-XX): Lønperiode-indstillinger pr. logistik-firma.
# Fase 15.15 (2026-02-XX): Udvidet til at understøtte 3 cyklus-typer.
# Logistics-admin redigerer for deres eget firma; super_admin kan acte på
# tværs via X-Acting-Company-Id-headeren (samme switcher som /api/tours).
PAYROLL_CYCLE_TYPES = {"monthly", "biweekly", "weekly"}


def _normalize_payroll_settings(doc: dict) -> dict:
    """Returner gyldige payroll-felter med defaults — så Arkiv altid kan
    regne en cyklus selv om firmaet aldrig har konfigureret noget."""
    return {
        "payroll_cycle_type": (doc.get("payroll_cycle_type") or "monthly").lower(),
        "payroll_start_day": int(doc.get("payroll_start_day") or 20),
        "payroll_anchor_date": (doc.get("payroll_anchor_date") or "").strip(),
    }


@api_router.get("/company/punch-reason-settings")
async def get_punch_reason_settings(payload: dict = Depends(get_current_user_payload)):
    """Fase 15.28 (2026-02-22): Lightweight read-only endpoint som ALLE
    autentificerede brugere kan kalde (incl. chauffører) for at finde ud
    af om "Årsag" skal udfyldes ved manuel stempel."""
    cid = payload.get("company_id")
    if not cid or cid == SUPER_ADMIN_BYPASS:
        return {"require_driver_punch_reason": False, "require_admin_punch_reason": False}
    doc = await _raw_db.companies.find_one(
        {"id": cid},
        {"_id": 0, "require_driver_punch_reason": 1, "require_admin_punch_reason": 1},
    )
    return {
        "require_driver_punch_reason": bool((doc or {}).get("require_driver_punch_reason") or False),
        "require_admin_punch_reason": bool((doc or {}).get("require_admin_punch_reason") or False),
    }


@api_router.get("/company/payroll-settings")
async def get_payroll_settings(payload: dict = Depends(get_current_user_payload)):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    cid = payload.get("company_id")
    if not cid or cid == SUPER_ADMIN_BYPASS:
        raise HTTPException(status_code=400, detail="Vælg et logistik-firma først (X-Acting-Company-Id-header)")
    doc = await _raw_db.companies.find_one(
        {"id": cid},
        {"_id": 0, "id": 1, "name": 1, "payroll_cycle_type": 1, "payroll_start_day": 1,
         "payroll_anchor_date": 1, "require_driver_punch_reason": 1, "require_admin_punch_reason": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Firma ikke fundet")
    settings = _normalize_payroll_settings(doc)
    settings["require_driver_punch_reason"] = bool(doc.get("require_driver_punch_reason") or False)
    settings["require_admin_punch_reason"] = bool(doc.get("require_admin_punch_reason") or False)
    return {"company_id": doc["id"], "company_name": doc.get("name", ""), **settings}


class PayrollSettingsUpdate(BaseModel):
    # Fase 15.15: alle 3 felter er valgfri — partial update er tilladt.
    payroll_cycle_type: Optional[str] = None  # "monthly" | "biweekly" | "weekly"
    payroll_start_day: Optional[int] = None
    payroll_anchor_date: Optional[str] = None
    # Fase 15.28 (2026-02-22): Krav om "Årsag" på manuel stempel.
    require_driver_punch_reason: Optional[bool] = None
    require_admin_punch_reason: Optional[bool] = None


@api_router.patch("/company/payroll-settings")
async def patch_payroll_settings(
    body: PayrollSettingsUpdate, payload: dict = Depends(get_current_user_payload)
):
    role = payload.get("role")
    if role not in ("logistics_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    cid = payload.get("company_id")
    if not cid or cid == SUPER_ADMIN_BYPASS:
        raise HTTPException(status_code=400, detail="Vælg et logistik-firma først")
    target = await _raw_db.companies.find_one(
        {"id": cid},
        {"_id": 0, "id": 1, "name": 1, "payroll_cycle_type": 1, "payroll_start_day": 1, "payroll_anchor_date": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Firma ikke fundet")

    update_doc = {}
    # Validér cyklus-type
    if body.payroll_cycle_type is not None:
        ct = body.payroll_cycle_type.strip().lower()
        if ct not in PAYROLL_CYCLE_TYPES:
            raise HTTPException(status_code=400, detail="Ugyldig cyklus-type. Brug monthly/biweekly/weekly.")
        update_doc["payroll_cycle_type"] = ct

    # Validér startdag (kun relevant for monthly)
    if body.payroll_start_day is not None:
        day = int(body.payroll_start_day)
        if day < 1 or day > 28:
            raise HTTPException(status_code=400, detail="Lønperiode-startdag skal være mellem 1 og 28")
        update_doc["payroll_start_day"] = day

    # Validér anchor-dato (kun relevant for weekly/biweekly)
    if body.payroll_anchor_date is not None:
        ad = (body.payroll_anchor_date or "").strip()
        if ad:
            try:
                datetime.strptime(ad, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Ugyldigt ankerdato-format (forventet YYYY-MM-DD)")
        update_doc["payroll_anchor_date"] = ad

    # Fase 15.28 (2026-02-22): Krav om Årsag på manuel stempel.
    if body.require_driver_punch_reason is not None:
        update_doc["require_driver_punch_reason"] = bool(body.require_driver_punch_reason)
    if body.require_admin_punch_reason is not None:
        update_doc["require_admin_punch_reason"] = bool(body.require_admin_punch_reason)

    if not update_doc:
        raise HTTPException(status_code=400, detail="Intet at opdatere")

    await _raw_db.companies.update_one({"id": cid}, {"$set": update_doc})
    # Returner det nye komplette billede
    refreshed = await _raw_db.companies.find_one(
        {"id": cid},
        {"_id": 0, "id": 1, "name": 1, "payroll_cycle_type": 1, "payroll_start_day": 1,
         "payroll_anchor_date": 1, "require_driver_punch_reason": 1, "require_admin_punch_reason": 1},
    )
    settings = _normalize_payroll_settings(refreshed or {})
    settings["require_driver_punch_reason"] = bool((refreshed or {}).get("require_driver_punch_reason") or False)
    settings["require_admin_punch_reason"] = bool((refreshed or {}).get("require_admin_punch_reason") or False)
    return {"company_id": cid, "company_name": (refreshed or {}).get("name", ""), **settings}


@sa_router.get("/companies")
async def sa_list_companies(include_library: bool = False):
    """List companies. By default the partner-library entries (created via
    the 'Tilføj logistik partner' tab) are EXCLUDED — the customers-and-logistics
    panel shows kunder + logistik that were manually onboarded with full
    admin/contact info. Pass `include_library=true` to get the partner library
    instead (used by LogisticsPartnersPanel)."""
    q: Dict[str, Any] = {}
    if not include_library:
        # Treat missing field as False (existing data has no `from_library`).
        q["$or"] = [{"from_library": {"$exists": False}}, {"from_library": False}]
    items = await _raw_db.companies.find(q, {"_id": 0}).to_list(1000)
    # Add admin info, user count, and default missing fields for each company
    for c in items:
        c["user_count"] = await _raw_db.users.count_documents({"company_id": c["id"]})
        # Active employee count (for license overview): only "order" users with active=true
        c["active_employee_count"] = await _raw_db.users.count_documents({
            "company_id": c["id"],
            "role": {"$in": ["order", "location_admin"]},
            "active": True,
        })
        # iteration 18 — Kundeoverblik additions
        #   locations_count: how many plads docs belong to this customer
        #   partners_count: how many logistic companies serve this customer
        #   active_users_incl_partners: this company's active users PLUS active
        #     users belonging to partner companies that serve this customer
        c["locations_count"] = await _raw_db.plads.count_documents({"company_id": c["id"]})
        partner_ids: list[str] = []
        partners_cursor = _raw_db.companies.find(
            {"serves_company_ids": c["id"], "company_type": {"$ne": COMPANY_TYPE_CUSTOMER}},
            {"_id": 0, "id": 1},
        )
        async for p in partners_cursor:
            partner_ids.append(p["id"])
        c["partners_count"] = len(partner_ids)
        c["active_users_incl_partners"] = await _raw_db.users.count_documents({
            "company_id": {"$in": [c["id"], *partner_ids]},
            "active": True,
        })
        c.setdefault("serves_company_ids", [])
        c.setdefault("active", True)
        c.setdefault("customer_id", None)
        c.setdefault("company_type", COMPANY_TYPE_CUSTOMER)
        c.setdefault("admin_phone", "")
        # Surface the first admin (customer_admin/logistics_admin) so the
        # SuperAdmin Edit form can show admin email/name without an extra call.
        admin_role = "customer_admin" if c.get("company_type") == COMPANY_TYPE_CUSTOMER else "logistics_admin"
        first_admin = await _raw_db.users.find_one(
            {"company_id": c["id"], "role": admin_role},
            {"_id": 0, "id": 1, "email": 1, "name": 1, "active": 1,
             "phone": 1, "invitation_status": 1, "created_at": 1},
            sort=[("created_at", 1)],
        )
        if first_admin:
            first_admin.setdefault("invitation_status", "active")
            first_admin.setdefault("phone", "")
        c["first_admin"] = first_admin or None
    return items


@sa_router.post("/companies")
async def sa_create_company(body: CompanyCreate, payload: dict = Depends(require_super_admin)):
    """Create a customer/logistics company.

    Kunde-ID (customer_id) is OBLIGATORISK. If admin_email is supplied the
    system creates the first admin with `invitation_status=pending` (no
    password) and emails them a 72h set-password link.
    """
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    customer_id = (body.customer_id or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="Kunde-ID er påkrævet")
    ctype = (body.company_type or COMPANY_TYPE_CUSTOMER).strip()
    if ctype not in VALID_COMPANY_TYPES:
        raise HTTPException(status_code=400, detail="Ugyldig firmatype")
    existing = await _raw_db.companies.find_one({"name": name})
    if existing:
        raise HTTPException(status_code=409, detail="En gruppe med dette navn findes allerede")
    if await _raw_db.companies.find_one({"customer_id": customer_id}):
        raise HTTPException(status_code=409, detail=f"Kunde-ID '{customer_id}' er allerede i brug")

    company = Company(
        name=name,
        slug=(body.slug or "").strip(),
        company_type=ctype,
        customer_id=customer_id,
        active=bool(body.active) if body.active is not None else True,
        admin_phone=(body.admin_phone or "").strip(),
        from_library=bool(getattr(body, "from_library", False)),
        holiday_group_id=getattr(body, "holiday_group_id", None) or None,
    )
    await _raw_db.companies.insert_one(company.model_dump())

    created_admin = None
    admin_email = (body.admin_email or "").strip().lower()
    if admin_email:
        admin_role = "customer_admin" if ctype == COMPANY_TYPE_CUSTOMER else "logistics_admin"
        admin_name = (body.admin_name or "").strip() or admin_email
        user = AuthUser(
            email=admin_email,
            name=admin_name,
            role=admin_role,
            company_id=company.id,
            phone=(body.admin_phone or "").strip() or None,
            invitation_status="pending",
        )
        doc = user.model_dump()
        doc["password_hash"] = ""  # set when invitation accepted
        try:
            await _raw_db.users.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Admin-email findes allerede")
        await _send_invite_for_user(doc)
        created_admin = {"id": user.id, "email": admin_email, "name": admin_name, "role": admin_role}
        await _audit("company_admin_invited", payload, {
            "company_id": company.id, "user_email": admin_email, "role": admin_role,
        })

    return {"company": company.model_dump(), "created_admin": created_admin}


# ----- Hurtig firma-opsætning (wizard) -------------------------------------
class QuickAdmin(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""


class QuickCompanySetup(BaseModel):
    company_name: str
    # "customer" (ARGO-type, has locations) or "logistics" (ILK-type, has drivers)
    company_type: str = COMPANY_TYPE_CUSTOMER
    # Optional fields available to the system owner only.
    customer_id: Optional[str] = None  # external/CRM identifier, free text
    active: Optional[bool] = True       # contract status — inactive customers hidden from operations
    # The org's first admin (customer_admin or logistics_admin) is OPTIONAL.
    # If you don't supply credentials at creation time, the system owner can
    # add one later via the regular "Brugere" flow.
    admin: Optional[QuickAdmin] = None


@sa_router.post("/companies/quick-setup")
async def sa_quick_company_setup(body: QuickCompanySetup,
                                 payload: dict = Depends(require_super_admin)):
    """System owner: create a CUSTOMER or LOGISTICS org. Admin is optional.

    - customer  -> if an admin is supplied they get role `customer_admin` and
                   are auto-assigned to every location that exists today for
                   this customer (none by default — locations are added later).
    - logistics -> if an admin is supplied they get role `logistics_admin`.
    No default location is auto-created any more; the environment stays clean
    so stats reflect real activity. The customer admin adds locations on demand.
    """
    name = (body.company_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Firmanavn er påkrævet")

    ctype = (body.company_type or COMPANY_TYPE_CUSTOMER).strip()
    if ctype not in VALID_COMPANY_TYPES:
        raise HTTPException(status_code=400, detail="Ugyldig firmatype")

    has_admin = body.admin and (body.admin.email or "").strip()
    admin_email = ""
    if has_admin:
        admin_email = (body.admin.email or "").strip().lower()
        if not body.admin.password or len(body.admin.password) < 4:
            raise HTTPException(status_code=400, detail="Password skal være mindst 4 tegn")

    # Pre-validate before creating anything (avoid half-finished setup).
    # NOTE: emails are NOT globally unique any more — multi-tenant by design.
    # We only block duplicate (email, company_name) which we can't yet check
    # because the company doesn't exist. So: rely on per-create scope below.
    if await _raw_db.companies.find_one({"name": name}):
        raise HTTPException(status_code=409, detail="En virksomhed med dette navn findes allerede")

    admin_role = "customer_admin" if ctype == COMPANY_TYPE_CUSTOMER else "logistics_admin"

    # 1) Create the company with the new optional fields
    company = Company(
        name=name,
        company_type=ctype,
        customer_id=(body.customer_id or "").strip() or None,
        active=bool(body.active) if body.active is not None else True,
    )
    await _raw_db.companies.insert_one(company.model_dump())

    # 2) NOTE: we deliberately do NOT auto-create a default location any more.
    # The user wanted a fully clean environment that reflects only real data.

    created_users = []
    if has_admin:
        # 3) Create the org's first admin (optional path)
        user = AuthUser(
            email=admin_email,
            name=(body.admin.name or "").strip() or admin_email,
            role=admin_role,
            company_id=company.id,
            phone=None,
            location_code=None,
            managed_company_ids=[],
            is_hq_admin=False,
            assigned_plads_ids=[],
            visible_plads_ids=[],
        )
        doc = user.model_dump()
        doc["password_hash"] = hash_password(body.admin.password)
        await _raw_db.users.insert_one(doc)
        created_users.append({
            "email": user.email, "name": user.name, "role": user.role, "id": user.id,
        })
        await _audit("quick_setup_admin_created", payload, {
            "company_id": company.id, "user_email": user.email, "role": user.role,
        })

    return {
        "company": company.model_dump(),
        "created_users": created_users,
        "message": (
            f"{'Kunde' if ctype == COMPANY_TYPE_CUSTOMER else 'Logistik'}-firma "
            f"'{name}' oprettet" + (f" med admin {admin_email}" if has_admin else " (ingen admin)")
        ),
    }


@sa_router.put("/companies/{company_id}", response_model=Company)
async def sa_update_company(company_id: str, body: CompanyUpdate):
    # exclude_unset lets us distinguish between "field not provided" and
    # "field provided as null". Critical for holiday_group_id where null
    # legitimately means "clear the assignment".
    raw = body.model_dump(exclude_unset=True)
    # Pull the admin-level fields out — they live on the user document, not
    # the company document. We persist them in a separate atomic step so we
    # don't get half-applied state when only one set is invalid.
    admin_name = raw.pop("admin_name", None)
    admin_email = raw.pop("admin_email", None)
    # Fields that are allowed to be explicitly null (to clear/unset them).
    # Other fields that come through as None are treated as "no change".
    nullable_fields = {"holiday_group_id"}
    update = {
        k: v for k, v in raw.items()
        if v is not None or k in nullable_fields
    }
    if not update and admin_name is None and admin_email is None:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    if company_id == DEFAULT_COMPANY_ID and update.get("active") is False:
        raise HTTPException(status_code=400, detail="Standard-gruppen kan ikke suspenderes")
    if "customer_id" in update:
        cid = (update["customer_id"] or "").strip()
        if not cid:
            raise HTTPException(status_code=400, detail="Kunde-ID må ikke være tomt")
        clash = await _raw_db.companies.find_one(
            {"customer_id": cid, "id": {"$ne": company_id}}, {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409, detail=f"Kunde-ID '{cid}' bruges af et andet firma")
        update["customer_id"] = cid
    # serves_company_ids is a legacy field kept for back-compat — we still
    # accept it on the API but customer admins manage per-location partnership
    # instead (see /api/org/locations/{id}/logistics-partners).
    if "serves_company_ids" in update:
        ids = list({c for c in update["serves_company_ids"] if c and c != company_id})
        if ids:
            existing = await _raw_db.companies.find(
                {"id": {"$in": ids}}, {"_id": 0, "id": 1}
            ).to_list(1000)
            existing_ids = {d["id"] for d in existing}
            invalid = [c for c in ids if c not in existing_ids]
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ukendt(e) virksomheds-ID: {', '.join(invalid)}",
                )
        update["serves_company_ids"] = ids
    if update:
        result = await _raw_db.companies.find_one_and_update(
            {"id": company_id}, {"$set": update}, return_document=True
        )
    else:
        result = await _raw_db.companies.find_one({"id": company_id})
    if not result:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    result.pop("_id", None)
    invalidate_company_cache(company_id)

    # If admin name/email changed, mutate the company's first_admin record.
    # Brugerkrav 2026-06-15 (runde 9): Hvis ingen admin endnu findes (firmaet
    # blev oprettet uden email) OG admin_email er udfyldt, så opret en ny
    # admin-bruger PLUS send invitations-email. Det dækker partner-flowet hvor
    # SA først opretter logistik-firmaet uden kontaktoplysninger, og senere
    # tilføjer email + navn ved at redigere firmaet.
    if admin_name is not None or admin_email is not None:
        admin_role = "customer_admin" if result.get("company_type") == COMPANY_TYPE_CUSTOMER else "logistics_admin"
        first_admin = await _raw_db.users.find_one(
            {"company_id": company_id, "role": admin_role},
            {"_id": 0},
            sort=[("created_at", 1)],
        )
        if first_admin:
            admin_update: Dict[str, Any] = {}
            if admin_name is not None:
                admin_update["name"] = admin_name.strip() or first_admin.get("name") or ""
            if admin_email is not None:
                new_email = (admin_email or "").strip().lower()
                if not new_email:
                    raise HTTPException(status_code=400, detail="Admin-email må ikke være tom")
                if new_email != (first_admin.get("email") or "").lower():
                    # Multi-tenant: only blocked if SAME company has same email
                    clash = await _raw_db.users.find_one({
                        "email": new_email, "company_id": company_id, "id": {"$ne": first_admin["id"]},
                    })
                    if clash:
                        raise HTTPException(status_code=409, detail="Email findes allerede i dette firma")
                    admin_update["email"] = new_email
            if admin_update:
                await _raw_db.users.update_one({"id": first_admin["id"]}, {"$set": admin_update})
                # Hvis email blev sat (eller ændret), invalidate password og send invitation.
                if "email" in admin_update or (first_admin.get("invitation_status") == "pending"
                                                and not first_admin.get("password_hash")):
                    await _raw_db.users.update_one(
                        {"id": first_admin["id"]},
                        {"$set": {"invitation_status": "pending", "password_hash": ""}},
                    )
                    refreshed = await _raw_db.users.find_one({"id": first_admin["id"]}, {"_id": 0})
                    if refreshed:
                        try:
                            await _send_invite_for_user(refreshed)
                        except Exception as _e:
                            pass  # mail-fejl bør ikke blokere selve gemningen
        else:
            # INGEN admin findes endnu — opret en ny hvis email er udfyldt
            new_email = (admin_email or "").strip().lower()
            new_name = (admin_name or "").strip()
            if not new_email:
                # Kun navn givet → kan ikke oprette user uden email; ignorér stille
                pass
            else:
                # Tjek for clash inden for SAMME firma
                clash = await _raw_db.users.find_one({
                    "email": new_email, "company_id": company_id,
                })
                if clash:
                    raise HTTPException(status_code=409, detail="Email findes allerede i dette firma")
                new_user_id = str(uuid.uuid4())
                new_user = {
                    "id": new_user_id,
                    "email": new_email,
                    "name": new_name or new_email.split("@")[0],
                    "password_hash": "",  # afventer invitations-flow
                    "role": admin_role,
                    "company_id": company_id,
                    "active": True,
                    "invitation_status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "managed_company_ids": [],
                    "assigned_plads_ids": [],
                    "location_code": "",
                }
                await _raw_db.users.insert_one(new_user)
                # Send invitations-email
                try:
                    await _send_invite_for_user(new_user)
                except Exception as _e:
                    pass  # mail-fejl må ikke rulle ændring tilbage
    return result


@sa_router.post("/companies/{company_id}/resend-invitation")
async def sa_resend_invitation(company_id: str, payload: dict = Depends(require_super_admin)):
    """Generate a fresh invitation link for the company's first admin and
    email it again. Useful when the original 72h link has expired."""
    company = await _raw_db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Firma ikke fundet")
    admin_role = "customer_admin" if company.get("company_type") == COMPANY_TYPE_CUSTOMER else "logistics_admin"
    # Prefer a still-pending admin; fall back to the oldest one.
    admin = await _raw_db.users.find_one(
        {"company_id": company_id, "role": admin_role, "invitation_status": "pending"},
        {"_id": 0},
    ) or await _raw_db.users.find_one(
        {"company_id": company_id, "role": admin_role},
        {"_id": 0},
        sort=[("created_at", 1)],
    )
    if not admin:
        raise HTTPException(status_code=404, detail="Ingen admin tilknyttet dette firma")
    # Reset to pending so the activation status flag stays accurate even after a resend.
    await _raw_db.users.update_one(
        {"id": admin["id"]},
        {"$set": {"invitation_status": "pending", "password_hash": ""}},
    )
    admin["invitation_status"] = "pending"
    admin["password_hash"] = ""
    result = await _send_invite_for_user(admin)
    await _audit("company_admin_invitation_resent", payload, {
        "company_id": company_id, "user_email": admin.get("email"),
    })
    return {"success": True, "delivered": bool(result and result.get("id")), "admin_email": admin.get("email")}


@sa_router.delete("/companies/{company_id}")
async def sa_delete_company(company_id: str, payload: dict = Depends(require_super_admin)):
    await _audit("company_deleted", payload, {"company_id": company_id})
    if company_id == DEFAULT_COMPANY_ID:
        raise HTTPException(status_code=400, detail="Standard-gruppen kan ikke slettes")
    user_count = await _raw_db.users.count_documents({"company_id": company_id})
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Gruppe har {user_count} brugere. Slet eller flyt brugerne først.",
        )
    res = await _raw_db.companies.delete_one({"id": company_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    return {"success": True}


@sa_router.get("/users")
async def sa_list_users(company_id: Optional[str] = None):
    q = {}
    if company_id:
        q["company_id"] = company_id
    users = await _raw_db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(2000)
    # attach company name
    companies = await _raw_db.companies.find({}, {"_id": 0}).to_list(1000)
    cmap = {c["id"]: c["name"] for c in companies}
    for u in users:
        u["company_name"] = cmap.get(u.get("company_id"))
    return users


@sa_router.post("/users", response_model=UserPublic)
async def sa_create_user(body: UserCreate):
    """System owner -> "Ny Bruger" form. Per the 5-level hierarchy rules this
    endpoint ONLY creates *super_admin* users (other roles are managed by
    the relevant customer/logistics admin via the org-router endpoints)."""
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email er påkrævet")
    if body.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Kun super_admin-brugere kan oprettes her. Brug de respektive admin-sider for andre roller.",
        )
    if not body.password or len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password skal være mindst 4 tegn")
    existing = await _raw_db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Email findes allerede")
    user = AuthUser(
        email=email,
        name=body.name.strip() or email,
        role="super_admin",
        company_id=SUPER_ADMIN_BYPASS,
        phone=body.phone,
        invitation_status="active",
    )
    doc = user.model_dump()
    doc["password_hash"] = hash_password(body.password)
    try:
        await _raw_db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email findes allerede")
    return _user_to_public(doc, None)


@sa_router.put("/users/{user_id}", response_model=UserPublic)
async def sa_update_user(user_id: str, body: UserUpdate):
    update = {}
    raw = body.model_dump(exclude_unset=True)
    for k, v in raw.items():
        if v is None:
            continue
        if k == "password":
            update["password_hash"] = hash_password(v)
        elif k == "email":
            update["email"] = v.strip().lower()
        elif k == "role":
            if v not in VALID_ROLES:
                raise HTTPException(status_code=400, detail="Ugyldig rolle")
            update["role"] = v
        elif k == "managed_company_ids":
            # de-dup, remove own company (it's implicit)
            update["managed_company_ids"] = [c for c in (v or []) if c]
        elif k == "assigned_plads_ids":
            update["assigned_plads_ids"] = [p for p in (v or []) if p]
        elif k == "visible_plads_ids":
            update["visible_plads_ids"] = [p for p in (v or []) if p]
        elif k == "is_hq_admin":
            update["is_hq_admin"] = bool(v)
        else:
            update[k] = v
    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")

    # Data hygiene: if role is being changed to a non-logistics_admin role,
    # clear any stale managed_company_ids on the user doc.
    if "role" in update and update["role"] != "logistics_admin":
        update["managed_company_ids"] = []
    # Data hygiene: if role is being changed away from genbrug_plads, clear
    # genbrug-specific flags so they don't leak into other roles.
    if "role" in update and update["role"] != "genbrug_plads":
        update["is_hq_admin"] = False
        update["assigned_plads_ids"] = []
    # Data hygiene: visible_plads_ids only makes sense for drivers.
    if "role" in update and update["role"] != "driver":
        update["visible_plads_ids"] = []

    # Also guard against setting is_hq_admin / assigned_plads_ids on a user
    # whose existing role is NOT genbrug_plads (and the role isn't being changed
    # in this same call). Look up the doc once and refuse.
    if ("is_hq_admin" in update or "assigned_plads_ids" in update or "visible_plads_ids" in update) and "role" not in update:
        existing = await _raw_db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
        if existing:
            existing_role = existing.get("role")
            if existing_role != "genbrug_plads":
                update.pop("is_hq_admin", None)
                update.pop("assigned_plads_ids", None)
            if existing_role != "driver":
                update.pop("visible_plads_ids", None)
            if not update:
                raise HTTPException(
                    status_code=400,
                    detail="Disse felter gælder kun for den relevante rolle",
                )

    # If email is being changed, ensure it's unique (skip the current user itself)
    if "email" in update:
        clash = await _raw_db.users.find_one({"email": update["email"], "id": {"$ne": user_id}})
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"Email '{update['email']}' bruges allerede af en anden bruger",
            )

    try:
        result = await _raw_db.users.find_one_and_update(
            {"id": user_id}, {"$set": update}, return_document=True
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email bruges allerede")
    if not result:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    result.pop("_id", None)
    result.pop("password_hash", None)
    company_name = await _get_company_name(result.get("company_id"))
    return _user_to_public(result, company_name)


@sa_router.delete("/users/{user_id}")
async def sa_delete_user(user_id: str):
    # Permanent safeguard: the bootstrap super admin (`is_system_super_admin`
    # flag set during the iteration_18 reset) can never be deleted via the
    # API. Any attempt returns 409 instead of silently wiping the only login.
    target = await _raw_db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    if target.get("is_system_super_admin"):
        raise HTTPException(
            status_code=409,
            detail="System Super Admin kan ikke slettes — denne konto er permanent forankret.",
        )
    res = await _raw_db.users.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    return {"success": True}


# ----- Super Admin: cross-company Plads management -----
# Lets the super admin add/edit/delete Genbrug Plads facilities for any company.

class SAPladsCreate(BaseModel):
    company_id: str
    name: str
    city: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_code: Optional[str] = None


class SAPladsUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    company_id: Optional[str] = None  # allow moving a plads to another company
    location_code: Optional[str] = None


@sa_router.get("/plads")
async def sa_list_plads(company_id: Optional[str] = None):
    q = {}
    if company_id:
        q["company_id"] = company_id
    items = await _raw_db.plads.find(q, {"_id": 0}).sort("name", 1).to_list(5000)
    # attach company name
    companies = await _raw_db.companies.find({}, {"_id": 0}).to_list(1000)
    cmap = {c["id"]: c["name"] for c in companies}
    for p in items:
        p["company_name"] = cmap.get(p.get("company_id"))
    return items


@sa_router.post("/plads")
async def sa_create_plads(body: SAPladsCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    # validate company
    comp = await _raw_db.companies.find_one({"id": body.company_id})
    if not comp:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": body.company_id,
        "name": body.name.strip(),
        "city": (body.city or "").strip(),
        "address": (body.address or "").strip(),
        "lat": body.lat,
        "lng": body.lng,
        "location_code": (body.location_code or "").strip() or None,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.plads.insert_one(doc)
    doc.pop("_id", None)
    doc["company_name"] = comp.get("name")
    return doc


@sa_router.put("/plads/{plads_id}")
async def sa_update_plads(plads_id: str, body: SAPladsUpdate):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    if "company_id" in update:
        comp = await _raw_db.companies.find_one({"id": update["company_id"]})
        if not comp:
            raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    res = await _raw_db.plads.find_one_and_update(
        {"id": plads_id}, {"$set": update}, return_document=True
    )
    if not res:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    res.pop("_id", None)
    comp = await _raw_db.companies.find_one({"id": res.get("company_id")}, {"_id": 0})
    res["company_name"] = comp.get("name") if comp else None
    return res


@sa_router.delete("/plads/{plads_id}")
async def sa_delete_plads(plads_id: str):
    res = await _raw_db.plads.delete_one({"id": plads_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    return {"success": True}


# Bulk import: add many plads at once for one company (used for fx Vestforbrænding 50 plads).
class SAPladsBulkItem(BaseModel):
    name: str
    city: str = ""
    address: str = ""
    location_code: Optional[str] = None


class SAPladsBulkRequest(BaseModel):
    company_id: str
    items: List[SAPladsBulkItem]


@sa_router.post("/plads/bulk")
async def sa_bulk_create_plads(body: SAPladsBulkRequest):
    comp = await _raw_db.companies.find_one({"id": body.company_id})
    if not comp:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    if not body.items:
        raise HTTPException(status_code=400, detail="Ingen plads at oprette")
    docs = []
    now = datetime.now(timezone.utc).isoformat()
    for it in body.items:
        if not it.name.strip():
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "company_id": body.company_id,
            "name": it.name.strip(),
            "city": (it.city or "").strip(),
            "address": (it.address or "").strip(),
            "lat": None,
            "lng": None,
            "location_code": (it.location_code or "").strip() or None,
            "active": True,
            "created_at": now,
        })
    if not docs:
        raise HTTPException(status_code=400, detail="Ingen gyldige plads-navne")
    await _raw_db.plads.insert_many(docs)
    return {"created": len(docs), "company_id": body.company_id}


# ----- Merge two plads (move tours / addresses / assignments, then delete source) -----
class SAPladsMergeRequest(BaseModel):
    source_id: str
    target_id: str


@sa_router.post("/plads/merge")
async def sa_merge_plads(body: SAPladsMergeRequest):
    if not body.source_id or not body.target_id:
        raise HTTPException(status_code=400, detail="Både kilde og mål er påkrævet")
    if body.source_id == body.target_id:
        raise HTTPException(status_code=400, detail="Kilde og mål må ikke være den samme plads")

    source = await _raw_db.plads.find_one({"id": body.source_id}, {"_id": 0})
    target = await _raw_db.plads.find_one({"id": body.target_id}, {"_id": 0})
    if not source or not target:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")

    src_name = source.get("name") or ""
    tgt_name = target.get("name") or ""

    moved = {
        "tours": 0,
        "container_orders": 0,
        "genbrug_orders": 0,
        "tour_prices": 0,
        "addresses": 0,
        "user_assignments": 0,
    }

    # 1) Re-point tours that reference source by NAME → target name
    if src_name and tgt_name and src_name != tgt_name:
        r = await _raw_db.tours.update_many(
            {"plads": src_name}, {"$set": {"plads": tgt_name}}
        )
        moved["tours"] = r.modified_count
        r = await _raw_db.container_orders.update_many(
            {"plads": src_name}, {"$set": {"plads": tgt_name}}
        )
        moved["container_orders"] = r.modified_count
        r = await _raw_db.genbrug_orders.update_many(
            {"plads": src_name}, {"$set": {"plads": tgt_name}}
        )
        moved["genbrug_orders"] = r.modified_count
        r = await _raw_db.tour_prices.update_many(
            {"plads": src_name}, {"$set": {"plads": tgt_name}}
        )
        moved["tour_prices"] = r.modified_count

    # 2) Re-point sub-addresses to the target plads
    r = await _raw_db.plads_addresses.update_many(
        {"plads_id": body.source_id},
        {"$set": {"plads_id": body.target_id, "company_id": target.get("company_id")}}
    )
    moved["addresses"] = r.modified_count

    # 3) Re-point genbrug_plads site users that had the source plads assigned →
    #    swap to the target id (de-dup by pulling first, then $addToSet target).
    users_with_src = await _raw_db.users.find(
        {"assigned_plads_ids": body.source_id},
        {"_id": 0, "id": 1},
    ).to_list(2000)
    if users_with_src:
        ids = [u["id"] for u in users_with_src]
        await _raw_db.users.update_many(
            {"id": {"$in": ids}},
            {"$pull": {"assigned_plads_ids": body.source_id}}
        )
        await _raw_db.users.update_many(
            {"id": {"$in": ids}},
            {"$addToSet": {"assigned_plads_ids": body.target_id}}
        )
        moved["user_assignments"] = len(ids)

    # 4) Finally delete the source plads
    await _raw_db.plads.delete_one({"id": body.source_id})

    return {
        "success": True,
        "source_id": body.source_id,
        "target_id": body.target_id,
        "moved": moved,
    }


# ===== Plads Sub-Addresses =====
# A plads (e.g., "FORSYNING HELSINGØR") can have many specific addresses underneath
# grouped by a "sub_area" (e.g., "Nordkysten", "Boliggården"). The order user picks
# a plads, then a specific sub-address, and the tour is created with plads = parent
# plads name (so the driver sees everything grouped) and address = the specific street.

class PladsAddressBase(BaseModel):
    sub_area: str = ""
    postcode: str = ""
    city: str = ""
    street: str = ""


class PladsAddressBulkRequest(BaseModel):
    items: List[PladsAddressBase] = []


@sa_router.get("/plads/{plads_id}/addresses")
async def sa_list_plads_addresses(plads_id: str):
    items = await _raw_db.plads_addresses.find(
        {"plads_id": plads_id}, {"_id": 0}
    ).sort([("sub_area", 1), ("street", 1)]).to_list(5000)
    return items


@sa_router.post("/plads/{plads_id}/addresses")
async def sa_create_plads_address(plads_id: str, body: PladsAddressBase):
    plads = await _raw_db.plads.find_one({"id": plads_id})
    if not plads:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    if not body.street.strip():
        raise HTTPException(status_code=400, detail="Adresse er påkrævet")
    doc = {
        "id": str(uuid.uuid4()),
        "plads_id": plads_id,
        "company_id": plads.get("company_id") or DEFAULT_COMPANY_ID,
        "sub_area": body.sub_area.strip(),
        "postcode": body.postcode.strip(),
        "city": body.city.strip(),
        "street": body.street.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.plads_addresses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@sa_router.post("/plads/{plads_id}/addresses/bulk")
async def sa_bulk_create_plads_addresses(plads_id: str, body: PladsAddressBulkRequest):
    plads = await _raw_db.plads.find_one({"id": plads_id})
    if not plads:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    if not body.items:
        raise HTTPException(status_code=400, detail="Ingen adresser at oprette")
    docs = []
    now = datetime.now(timezone.utc).isoformat()
    cid = plads.get("company_id") or DEFAULT_COMPANY_ID
    for it in body.items:
        if not it.street.strip():
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "plads_id": plads_id,
            "company_id": cid,
            "sub_area": (it.sub_area or "").strip(),
            "postcode": (it.postcode or "").strip(),
            "city": (it.city or "").strip(),
            "street": it.street.strip(),
            "created_at": now,
        })
    if not docs:
        raise HTTPException(status_code=400, detail="Ingen gyldige adresser")
    await _raw_db.plads_addresses.insert_many(docs)
    return {"created": len(docs), "plads_id": plads_id}


@sa_router.put("/plads/addresses/{address_id}")
async def sa_update_plads_address(address_id: str, body: PladsAddressBase):
    update = {}
    raw = body.model_dump(exclude_unset=True)
    for k, v in raw.items():
        if v is not None:
            update[k] = (v.strip() if isinstance(v, str) else v)
    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    res = await _raw_db.plads_addresses.find_one_and_update(
        {"id": address_id}, {"$set": update}, return_document=True
    )
    if not res:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    res.pop("_id", None)
    return res


@sa_router.delete("/plads/addresses/{address_id}")
async def sa_delete_plads_address(address_id: str):
    res = await _raw_db.plads_addresses.delete_one({"id": address_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    return {"success": True}


# Public-ish endpoint: any authenticated user gets addresses for a plads they can see
# (tenant filter is automatic via the wrapper since plads_addresses is in TENANT_COLLECTIONS).
@api_router.get("/plads/{plads_id}/addresses")
async def list_plads_addresses(plads_id: str):
    items = await db.plads_addresses.find(
        {"plads_id": plads_id}, {"_id": 0}
    ).sort([("sub_area", 1), ("street", 1)]).to_list(5000)
    return items


# Logistics-admin and super-admin endpoints for managing plads addresses (tenant-scoped).
# These let the company's own admin manage addresses without going through super-admin.
PLADS_ADDR_ROLES = ("logistics_admin", "super_admin")


@api_router.post("/plads/{plads_id}/addresses")
async def admin_create_plads_address(
    plads_id: str,
    body: PladsAddressBase,
    payload: dict = Depends(require_role(*PLADS_ADDR_ROLES)),
):
    plads = await db.plads.find_one({"id": plads_id})
    if not plads:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    if not body.street.strip():
        raise HTTPException(status_code=400, detail="Adresse er påkrævet")
    doc = {
        "id": str(uuid.uuid4()),
        "plads_id": plads_id,
        "company_id": plads.get("company_id") or DEFAULT_COMPANY_ID,
        "sub_area": body.sub_area.strip(),
        "postcode": body.postcode.strip(),
        "city": body.city.strip(),
        "street": body.street.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.plads_addresses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/plads/{plads_id}/addresses/bulk")
async def admin_bulk_create_plads_addresses(
    plads_id: str,
    body: PladsAddressBulkRequest,
    payload: dict = Depends(require_role(*PLADS_ADDR_ROLES)),
):
    plads = await db.plads.find_one({"id": plads_id})
    if not plads:
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    if not body.items:
        raise HTTPException(status_code=400, detail="Ingen adresser at oprette")
    docs = []
    now = datetime.now(timezone.utc).isoformat()
    cid = plads.get("company_id") or DEFAULT_COMPANY_ID
    for it in body.items:
        if not it.street.strip():
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "plads_id": plads_id,
            "company_id": cid,
            "sub_area": (it.sub_area or "").strip(),
            "postcode": (it.postcode or "").strip(),
            "city": (it.city or "").strip(),
            "street": it.street.strip(),
            "created_at": now,
        })
    if not docs:
        raise HTTPException(status_code=400, detail="Ingen gyldige adresser")
    await db.plads_addresses.insert_many(docs)
    return {"created": len(docs), "plads_id": plads_id}


@api_router.delete("/plads/addresses/{address_id}")
async def admin_delete_plads_address(
    address_id: str,
    payload: dict = Depends(require_role(*PLADS_ADDR_ROLES)),
):
    res = await db.plads_addresses.delete_one({"id": address_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    return {"success": True}


# ----- /api/genbrug router -----
genbrug_router = APIRouter(prefix="/api/genbrug", tags=["genbrug"])


class GenbrugOrderBase(BaseModel):
    customer_name: str = ""
    address: str = ""
    phone: str = ""
    material: str = ""
    container_type: str = ""
    quantity: int = 1
    pickup_date: str = ""
    notes: str = ""
    status: str = "pending"  # pending | received | completed | cancelled
    photo: Optional[str] = None  # base64 image


class GenbrugOrder(GenbrugOrderBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GenbrugOrderCreate(GenbrugOrderBase):
    pass


class GenbrugOrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    material: Optional[str] = None
    container_type: Optional[str] = None
    quantity: Optional[int] = None
    pickup_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    photo: Optional[str] = None  # base64 image


GENBRUG_ALLOWED_ROLES = ("genbrug_plads", "logistics_admin", "super_admin")


@genbrug_router.get("/orders")
async def genbrug_list(payload: dict = Depends(require_role(*GENBRUG_ALLOWED_ROLES))):
    items = await db.genbrug_orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@genbrug_router.post("/orders", response_model=GenbrugOrder)
async def genbrug_create(
    body: GenbrugOrderCreate,
    payload: dict = Depends(require_role(*GENBRUG_ALLOWED_ROLES)),
):
    company_id = payload.get("company_id") or current_company_id.get()
    if company_id == SUPER_ADMIN_BYPASS:
        raise HTTPException(
            status_code=400,
            detail="Super admin kan ikke oprette genbrugsordrer direkte. Log ind som en bruger med en gruppe-tilknytning.",
        )
    order = GenbrugOrder(
        **body.model_dump(),
        company_id=company_id,
        created_by=payload.get("email", ""),
    )
    await db.genbrug_orders.insert_one(order.model_dump())
    return order


@genbrug_router.put("/orders/{order_id}", response_model=GenbrugOrder)
async def genbrug_update(
    order_id: str,
    body: GenbrugOrderUpdate,
    payload: dict = Depends(require_role(*GENBRUG_ALLOWED_ROLES)),
):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.genbrug_orders.update_one({"id": order_id}, {"$set": update})
    result = await db.genbrug_orders.find_one({"id": order_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Ordre ikke fundet")
    return result


@genbrug_router.delete("/orders/{order_id}")
async def genbrug_delete(order_id: str, payload: dict = Depends(require_role(*GENBRUG_ALLOWED_ROLES))):
    res = await db.genbrug_orders.delete_one({"id": order_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ordre ikke fundet")
    return {"success": True}


# ============= END MULTI-TENANT AUTH =============


# Include the router in the main app



@sa_router.post("/users/csv-import")
async def sa_csv_import(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    payload: dict = Depends(require_super_admin)
):
    """Bulk import users from CSV. Format: email,name,role,password"""
    import csv, io
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    created = []
    errors = []
    for i, row in enumerate(reader, 1):
        email = (row.get("email") or "").strip().lower()
        name = (row.get("name") or row.get("navn") or "").strip()
        role = (row.get("role") or row.get("rolle") or "driver").strip().lower()
        password = (row.get("password") or row.get("kode") or "Temp1234").strip()
        if not email or not name:
            errors.append({"row": i, "error": "Email og navn er påkrævet", "data": dict(row)})
            continue
        if role not in {"super_admin", "logistics_admin", "driver", "order", "genbrug_plads"}:
            role = "driver"
        existing = await _raw_db.users.find_one({"email": email})
        if existing:
            errors.append({"row": i, "error": f"Email {email} findes allerede"})
            continue
        doc = {
            "id": str(uuid.uuid4()), "email": email, "name": name,
            "role": role, "company_id": company_id, "active": True,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await _raw_db.users.insert_one(doc)
        created.append(email)
    return {"created": len(created), "errors": errors, "created_emails": created}


@sa_router.get("/company-stats/{company_id}")
async def sa_company_stats(company_id: str, payload: dict = Depends(require_super_admin)):
    """Get tour/order statistics for a specific company."""
    # Tours stats (from tenant-scoped tours collection)
    tours = await _raw_db.tours.find({"company_id": company_id, "is_pause": {"$ne": True}}, {"_id": 0, "completed": 1, "weight": 1, "date": 1, "fraction": 1, "plads": 1}).to_list(5000)
    completed = [t for t in tours if t.get("completed")]
    total_weight = sum(t.get("weight") or 0 for t in completed)

    # Genbrug orders
    orders = await _raw_db.genbrug_orders.find({"company_id": company_id}, {"_id": 0, "status": 1, "material": 1, "created_at": 1}).to_list(2000)

    # Material breakdown from tours
    materials = {}
    for t in tours:
        m = t.get("fraction") or "Ukendt"
        materials[m] = materials.get(m, 0) + 1

    # Plads breakdown
    plads_stats = {}
    for t in tours:
        p = t.get("plads") or "Ukendt"
        if p not in plads_stats:
            plads_stats[p] = {"total": 0, "completed": 0}
        plads_stats[p]["total"] += 1
        if t.get("completed"):
            plads_stats[p]["completed"] += 1

    return {
        "company_id": company_id,
        "tours": {
            "total": len(tours),
            "completed": len(completed),
            "total_weight_kg": total_weight,
            "completion_rate": round(len(completed) / max(len(tours), 1) * 100, 1),
        },
        "genbrug_orders": {
            "total": len(orders),
            "by_status": {s: sum(1 for o in orders if o.get("status") == s) for s in ["pending", "received", "completed", "cancelled"]},
        },
        "materials": sorted(materials.items(), key=lambda x: -x[1])[:10],
        "plads_stats": sorted(plads_stats.items(), key=lambda x: -x[1]["total"])[:10],
    }

# ============= ACTIVITY LOG =============
@sa_router.get("/activity-log")
async def sa_activity_log(
    limit: int = 100,
    action: str = "",
    payload: dict = Depends(require_super_admin)
):
    query = {}
    if action:
        query["action"] = action
    logs = await _raw_db.activity_log.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs



# ============= RATE LIMITING =============
_rate_store: dict = {}  # ip -> {"count": int, "window_start": float}
_RATE_LIMIT_REQ  = 60   # max requests
_RATE_LIMIT_WIN  = 60   # per 60 seconds

def _rate_limit_check(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = _time.time()
    rec = _rate_store.get(ip)
    if not rec or now - rec["window_start"] > _RATE_LIMIT_WIN:
        _rate_store[ip] = {"count": 1, "window_start": now}
        return
    rec["count"] += 1
    if rec["count"] > _RATE_LIMIT_REQ:
        raise HTTPException(status_code=429, detail="For mange anmodninger. Vent venligst.")

# Cleanup old entries periodically
async def _cleanup_rate_store():
    now = _time.time()
    stale = [ip for ip, rec in _rate_store.items() if now - rec["window_start"] > _RATE_LIMIT_WIN * 2]
    for ip in stale:
        _rate_store.pop(ip, None)


async def _audit(action: str, payload: dict, details: dict = None):
    """Log admin actions to activity_log."""
    try:
        await _raw_db.activity_log.insert_one({
            "id": str(uuid.uuid4()),
            "email": payload.get("email", "unknown"),
            "user_id": payload.get("sub", ""),
            "action": action,
            "role": payload.get("role", ""),
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass  # Never crash on audit failure

# ============= BRUTE-FORCE KORUMASI =============
import time as _time
_failed_attempts: dict = {}   # email -> {"count": int, "first_fail": float, "locked_until": float}
_BF_MAX_ATTEMPTS = 5          # kaç denemede kilitlenir
_BF_WINDOW_SEC   = 300        # 5 dakika içinde
_BF_LOCKOUT_SEC  = 900        # 15 dakika kilit

def _bf_check(email: str):
    """Raises HTTPException if account is locked."""
    now = _time.time()
    rec = _failed_attempts.get(email)
    if not rec:
        return
    if rec.get("locked_until", 0) > now:
        remaining = int(rec["locked_until"] - now)
        raise HTTPException(
            status_code=429,
            detail=f"For mange fejl. Prøv igen om {remaining // 60}m {remaining % 60}s."
        )
    # Window expired — reset
    if now - rec.get("first_fail", 0) > _BF_WINDOW_SEC:
        _failed_attempts.pop(email, None)

def _bf_fail(email: str):
    """Record a failed attempt."""
    now = _time.time()
    rec = _failed_attempts.setdefault(email, {"count": 0, "first_fail": now})
    if now - rec.get("first_fail", now) > _BF_WINDOW_SEC:
        rec.update({"count": 0, "first_fail": now})
    rec["count"] += 1
    if rec["count"] >= _BF_MAX_ATTEMPTS:
        rec["locked_until"] = now + _BF_LOCKOUT_SEC

def _bf_success(email: str):
    """Clear failed attempts on successful login."""
    _failed_attempts.pop(email, None)

# ============= SUPERADMIN SETTINGS =============
@sa_router.get("/settings")
async def sa_get_settings(payload: dict = Depends(require_super_admin)):
    admin_pw = await get_admin_password()
    return {
        "admin_password": admin_pw,
        # Phase 2: driver_code er udfaset — feltet vises ikke længere, men
        # behold tom værdi til bagudkompatibilitet med ældre UI-snapshots.
        "driver_code": "",
        "super_admin_email": os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@platform.com"),
    }

@sa_router.post("/settings")
async def sa_update_settings(body: dict, payload: dict = Depends(require_super_admin)):
    updated = []
    if body.get("admin_password"):
        await _raw_db.system_settings.update_one(
            {"key": "admin_password"},
            {"$set": {"key": "admin_password", "value": body["admin_password"]}},
            upsert=True
        )
        updated.append("admin_password")
    # Phase 2: driver_code endpoint accepterer stadig requests (idempotent
    # ignoreret) for bagudkompatibilitet; nye drivers bruger invitation-flow.
    return {"success": True, "updated": updated}




# ============= GENBRUG PLADS RAPPORT (Sadece okuma) =============
@genbrug_router.get("/plads-rapport")
async def genbrug_plads_rapport(
    period: str = "today",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    payload: dict = Depends(require_role("genbrug_plads", "logistics_admin", "super_admin", "customer_admin"))
):
    from datetime import timedelta
    # Use Danish local date so day boundaries match real operations
    # (a tour completed at 23:30 stays on the correct local day, not next-day UTC).
    today = datetime.now(DK_TZ)

    if period == "today":
        date_filter = today.strftime("%Y-%m-%d")
        query = {"date": date_filter}
    elif period == "week":
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        query = {"date": {"$gte": week_start}}
    elif period == "month":
        month_start = today.strftime("%Y-%m-01")
        query = {"date": {"$gte": month_start}}
    elif period == "custom" and (date_from or date_to):
        query = {"date": {}}
        if date_from: query["date"]["$gte"] = date_from
        if date_to:   query["date"]["$lte"] = date_to
    else:
        query = {"date": today.strftime("%Y-%m-%d")}

    # Multi-tenant: filter by company
    company_id = payload.get("company_id")
    if company_id:
        query["company_id"] = company_id

    # Genbrug HQ vs Site filter: if the caller is a genbrug_plads SITE user
    # (is_hq_admin=False) with assigned_plads_ids, restrict by those plads names.
    if payload.get("role") == "genbrug_plads":
        user_doc = await _raw_db.users.find_one(
            {"id": payload.get("sub")},
            {"_id": 0, "is_hq_admin": 1, "assigned_plads_ids": 1, "company_id": 1},
        )
        if user_doc and not user_doc.get("is_hq_admin"):
            assigned_ids = list(user_doc.get("assigned_plads_ids") or [])
            if assigned_ids:
                plads_docs = await _raw_db.plads.find(
                    {"id": {"$in": assigned_ids}}, {"_id": 0, "name": 1}
                ).to_list(500)
                assigned_names = [p["name"] for p in plads_docs if p.get("name")]
                if assigned_names:
                    query["plads"] = {"$in": assigned_names}
                else:
                    # User has IDs that no longer match any plads → return nothing
                    return []
            else:
                # Site user without any assigned plads → see nothing
                return []

    query["completed"] = True
    query["is_pause"]  = {"$ne": True}

    tours = await _raw_db.tours.find(query, {"_id": 0,
        "id": 1, "date": 1, "time": 1, "driver_name": 1, "claimed_by": 1,
        "fraction": 1, "address": 1, "weight": 1, "container": 1,
        "plads": 1, "remark": 1, "priority": 1, "reg_nr": 1
    }).sort("date", -1).to_list(5000)

    return tours

# ============= TOUR PRICES (Fiyatlandırma Sistemi) =============
class TourPriceCreate(BaseModel):
    plads: str
    fraction: str = ""
    price: float
    kind: str = "material"  # "material" | "flyt" | "vaerksted"

class TourPriceUpdate(BaseModel):
    plads: Optional[str] = None
    fraction: Optional[str] = None
    price: Optional[float] = None
    kind: Optional[str] = None


async def _company_haster_fee() -> float:
    """Per-company haster surcharge (falls back to the legacy global setting)."""
    cid = current_company_id.get()
    if cid and cid != SUPER_ADMIN_BYPASS:
        comp = await _raw_db.companies.find_one({"id": cid}, {"_id": 0, "haster_fee": 1})
        if comp and comp.get("haster_fee") is not None:
            return float(comp["haster_fee"])
    doc = await _raw_db.system_settings.find_one({"key": "haster_fee"})
    return float(doc["value"]) if doc else 200.0


@sa_router.get("/tour-prices")
@api_router.get("/tour-prices")
async def list_tour_prices():
    # Tenant-aware: each company sees ONLY its own prices (super_admin sees all).
    prices = await db.tour_prices.find({}, {"_id": 0}).sort("plads", 1).to_list(1000)
    for p in prices:
        p.setdefault("kind", "material")
    return {
        "prices": prices,
        "haster_fee": await _company_haster_fee(),
    }

@sa_router.post("/tour-prices")
@api_router.post("/tour-prices")
async def create_tour_price(body: TourPriceCreate):
    doc = {
        "id": str(uuid.uuid4()),
        "plads": body.plads.strip(),
        "fraction": body.fraction.strip(),
        "price": body.price,
        "kind": (body.kind or "material").strip() or "material",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    # db wrapper auto-injects company_id so the price is locked to this company.
    await db.tour_prices.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}

@sa_router.put("/tour-prices/{price_id}")
@api_router.put("/tour-prices/{price_id}")
async def update_tour_price(price_id: str, body: TourPriceUpdate):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.tour_prices.update_one({"id": price_id}, {"$set": update})
    result = await db.tour_prices.find_one({"id": price_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Pris ikke fundet")
    return result

@sa_router.delete("/tour-prices/{price_id}")
@api_router.delete("/tour-prices/{price_id}")
async def delete_tour_price(price_id: str):
    await db.tour_prices.delete_one({"id": price_id})
    return {"success": True}

@sa_router.post("/tour-prices/haster-fee")
@api_router.post("/tour-prices/haster-fee")
async def set_haster_fee(body: dict):
    fee = float(body.get("fee", 200))
    cid = current_company_id.get()
    if cid and cid != SUPER_ADMIN_BYPASS:
        # Per-company: store on the caller's company document
        await _raw_db.companies.update_one({"id": cid}, {"$set": {"haster_fee": fee}})
        invalidate_company_cache(cid)
    else:
        # super_admin (no single company) -> legacy global default
        await _raw_db.system_settings.update_one(
            {"key": "haster_fee"},
            {"$set": {"key": "haster_fee", "value": str(fee)}},
            upsert=True,
        )
    return {"success": True, "fee": fee}

@sa_router.get("/tour-prices/rapport")
@api_router.get("/tour-prices/rapport")
async def tour_prices_rapport(
    period: str = "weekly",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_id: Optional[str] = None,
    plads: Optional[str] = None
):
    # Build date filter (Danish local dates so day boundaries are correct)
    query = {}
    if company_id:
        query["company_id"] = company_id
    if date_from or date_to:
        query["date"] = {}
        if date_from: query["date"]["$gte"] = date_from
        if date_to:   query["date"]["$lte"] = date_to
    elif period == "daily":
        today = datetime.now(DK_TZ).strftime("%Y-%m-%d")
        query["date"] = today
    elif period == "weekly":
        from datetime import timedelta
        today = datetime.now(DK_TZ)
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        query["date"] = {"$gte": week_start}
    elif period == "monthly":
        month_start = datetime.now(DK_TZ).strftime("%Y-%m-01")
        query["date"] = {"$gte": month_start}

    # Add plads filter
    if plads:
        query["plads"] = plads

    # Get completed tours — tenant-aware (each company only its own tours).
    tours = await db.tours.find(
        {**query, "completed": True, "is_pause": {"$ne": True}},
        {"_id": 0, "date": 1, "driver_name": 1, "plads": 1, "fraction": 1,
         "priority": 1, "remark": 1, "claimed_by": 1, "price": 1, "tour_type": 1}
    ).to_list(5000)

    # Get price table — tenant-aware. Split into material prices and special
    # per-plads task prices (flyt / værksted).
    prices = await db.tour_prices.find({}, {"_id": 0}).to_list(1000)
    material_map = {}
    special_map = {}  # (plads_lower, kind) -> price
    for p in prices:
        kind = (p.get("kind") or "material")
        if kind in ("flyt", "vaerksted"):
            special_map[(p["plads"].lower(), kind)] = p["price"]
        else:
            material_map[(p["plads"].lower(), (p.get("fraction") or "").lower())] = p["price"]

    haster_fee = await _company_haster_fee()

    type_labels = {"flyt": "Flyt container", "vaerksted": "Til værksted", "normal": ""}

    # Calculate prices
    rows = []
    for t in tours:
        plads    = (t.get("plads") or "").strip()
        fraction = (t.get("fraction") or "").strip()
        ttype    = (t.get("tour_type") or "normal").strip() or "normal"
        if ttype == "værksted":
            ttype = "vaerksted"
        is_haster = (
            t.get("priority") in ("urgent", "haster") or
            "haster" in (t.get("remark") or "").lower()
        )
        if ttype in ("flyt", "vaerksted"):
            base_price = special_map.get((plads.lower(), ttype), 0)
        else:
            base_price = (material_map.get((plads.lower(), fraction.lower()))
                          or material_map.get((plads.lower(), "")) or 0)
        total_price = base_price + (haster_fee if is_haster else 0)
        rows.append({
            "date":      t.get("date", ""),
            "driver":    t.get("driver_name") or t.get("claimed_by") or "Ukendt",
            "plads":     plads,
            "fraction":  type_labels.get(ttype) or fraction,
            "tour_type": ttype,
            "is_haster": is_haster,
            "price":     total_price,
            "base_price": base_price,
        })

    rows.sort(key=lambda r: r["date"], reverse=True)

    # Driver summary
    driver_map = {}
    for r in rows:
        d = r["driver"]
        if d not in driver_map:
            driver_map[d] = {"driver": d, "tours": 0, "haster": 0, "amount": 0.0}
        driver_map[d]["tours"]  += 1
        driver_map[d]["amount"] += r["price"]
        if r["is_haster"]: driver_map[d]["haster"] += 1

    by_driver = sorted(driver_map.values(), key=lambda x: -x["amount"])
    total_amount  = sum(r["price"] for r in rows)
    haster_amount = sum(haster_fee for r in rows if r["is_haster"])

    return {
        "summary": {
            "total_tours":   len(rows),
            "total_amount":  round(total_amount, 2),
            "haster_amount": round(haster_amount, 2),
            "total_haster":  sum(1 for r in rows if r["is_haster"]),
            "driver_count":  len(driver_map),
        },
        "by_driver": by_driver,
        "rows": rows,
    }

# ============= GLOBAL RATE LIMIT MIDDLEWARE =============
# Fase 15.40b: Polling-friendly endpoints (small responses, called every ~30s
# by EACH active session) skal IKKE indgå i den globale rate limit — ellers
# vil de spise hele kvoten på en travl admin-konto. Tilføj nye polling-paths
# her hvis vi bygger flere.
_RATE_LIMIT_EXEMPT_PATHS = {
    "/api/clients/me/features",
}

# 2026-10-17: Egen tæller (før delte den `_rate_store` med login-grænsen, så
# almindelig brug kunne blokere login fra samme netværk) og pr. bruger når
# der er et gyldigt token - flere koordinatorer og chauffører bag samme
# kontor-IP deler ellers én kvote.
_global_rate_store: dict = {}


def _rate_key(request: Request) -> tuple:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:
            sub = decode_token(auth.split(" ", 1)[1].strip()).get("sub")
            if sub:
                return f"u:{sub}", 300
        except HTTPException:
            pass
    return f"ip:{request.client.host if request.client else 'unknown'}", 120


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only rate-limit API endpoints, not static files
    if request.url.path.startswith("/api/") and request.url.path not in _RATE_LIMIT_EXEMPT_PATHS:
        key, limit = _rate_key(request)
        now = _time.time()
        rec = _global_rate_store.get(key)
        if not rec or now - rec.get("window_start", 0) > _RATE_LIMIT_WIN:
            _global_rate_store[key] = {"count": 1, "window_start": now}
            if len(_global_rate_store) > 20000:
                for k in [k for k, v in _global_rate_store.items() if now - v["window_start"] > _RATE_LIMIT_WIN]:
                    _global_rate_store.pop(k, None)
        else:
            rec["count"] += 1
            if rec["count"] > limit:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=429, content={"detail": "For mange anmodninger. Vent venligst."})
    response = await call_next(request)
    return response

# ===========================================================================
# ORG ROUTER — delegated, scoped administration (the 5-level hierarchy)
# See HIERARCHY_SPEC.md. Every write is permission-checked server-side against
# the caller's role + company + location. The UI is never trusted.
# ===========================================================================
org_router = APIRouter(prefix="/api/org", tags=["org"])


async def _org_caller(payload: dict) -> dict:
    """Load the authenticated caller's full user record (no password)."""
    uid = payload.get("sub")
    doc = await _raw_db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    return doc


async def _company_of(caller: dict) -> dict:
    comp = await _raw_db.companies.find_one({"id": caller.get("company_id")}, {"_id": 0})
    if not comp:
        raise HTTPException(status_code=404, detail="Virksomhed ikke fundet")
    return comp


def _gen_location_code_sync():
    import random as _rnd
    return str(_rnd.randint(1000, 9999))


class OrgLocationCreate(BaseModel):
    name: str
    address: str = ""
    city: str = ""
    code: Optional[str] = None
    location_group_id: Optional[str] = None  # Optional grouping (e.g. "Sjælland")


class OrgLocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    active: Optional[bool] = None
    location_group_id: Optional[str] = None  # Use empty string "" to clear grouping


class OrgUserCreate(BaseModel):
    name: str = ""
    email: str
    password: Optional[str] = None      # OPTIONAL — when omitted, send invitation
    role: str                            # location_admin | order | driver (depends on caller)
    phone: Optional[str] = None
    employment_date: Optional[str] = None  # YYYY-MM-DD — ansættelsesdato
    send_invitation: Optional[bool] = None  # explicit "use invitation flow"
    location_code: Optional[str] = None
    # Optional: customer_admin can create a brand new location inline when
    # adding a location_admin so the flow is "Lokation + Admin in one step".
    location_name: Optional[str] = None
    # Multi-location support for location_admin: a customer_admin can grant
    # a single location_admin access to several pladser at once. The primary
    # `location_code` is still set (first entry), but every code in this list
    # is added to assigned_plads_ids so the admin sees all of them.
    location_codes: Optional[List[str]] = None


class OrgUserUpdate(BaseModel):
    """Lokation Admin -> medarbejder/redigering. Subset of fields the
    location_admin (and customer_admin) is allowed to change."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    employment_date: Optional[str] = None
    active: Optional[bool] = None        # active / inactive toggle
    # The list of pladser this user may access. Used by customer_admin when
    # re-assigning a location_admin to a different / extra plads, and by
    # location_admin when changing which plads an order-user belongs to.
    location_codes: Optional[List[str]] = None
    # Single primary plads (also moves the order user to that plads).
    location_code: Optional[str] = None


class LogisticsPartnerLink(BaseModel):
    logistics_company_id: str
    # Legacy field – customer_admins can no longer create the logistics admin
    # via this endpoint (per the new architecture only the system-ejer creates
    # logistics_admin users). Accept-and-ignore for backwards compat.
    admin: Optional[QuickAdmin] = None


# ----- LOCATIONS (customer_admin manages sites inside their own company) -----
@org_router.get("/locations")
async def org_list_locations(payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    role = caller.get("role")
    cid = caller.get("company_id")
    if role not in ("customer_admin", "location_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    # NOTE: locations and plads are the same thing in this product (driver +
    # employee + order + price + report flows ALL read from `plads`). The
    # /api/org/locations API stays for naming clarity but the storage is
    # the unified `plads` collection so adding a location here is visible
    # everywhere downstream.
    q = {"company_id": cid}
    # A location_admin only sees their own location(s)
    if role == "location_admin":
        codes = caller.get("assigned_plads_ids") or []
        own = caller.get("location_code")
        codes = [c for c in (codes + ([own] if own else [])) if c]
        if not codes:
            return []
        q["location_code"] = {"$in": codes}
    items = await _raw_db.plads.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    # Resolve assigned_logistics_company_ids -> [{id,name}] so admins can see
    # the names of the logistics partners that serve each of their pladser.
    all_ids = {lid for it in items for lid in (it.get("assigned_logistics_company_ids") or [])}
    name_map = {}
    if all_ids:
        async for c in _raw_db.companies.find(
            {"id": {"$in": list(all_ids)}, "company_type": COMPANY_TYPE_LOGISTICS},
            {"_id": 0, "id": 1, "name": 1},
        ):
            name_map[c["id"]] = c["name"]
    # Normalize so the frontend can keep using `.code`
    for it in items:
        it.setdefault("code", it.get("location_code") or "")
        partner_ids = it.get("assigned_logistics_company_ids") or []
        it["assigned_logistics_company_ids"] = list(partner_ids)
        it["logistics_partners"] = [
            {"id": pid, "name": name_map.get(pid, pid)} for pid in partner_ids
        ]
    return items


@org_router.post("/locations")
async def org_create_location(body: OrgLocationCreate,
                              payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    comp = await _company_of(caller)
    if comp.get("company_type", COMPANY_TYPE_CUSTOMER) != COMPANY_TYPE_CUSTOMER:
        raise HTTPException(status_code=403, detail="Kun kunde-firmaer har lokationer")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Lokationsnavn er påkrævet")
    # Unique 4-digit code across the whole platform (using location_code field
    # which is what plads/driver/order code reads)
    code = (body.code or "").strip()
    if code:
        if await _raw_db.plads.find_one({"location_code": code}):
            raise HTTPException(status_code=409, detail="Lokationskode er allerede i brug")
    else:
        for _ in range(50):
            cand = _gen_location_code_sync()
            if not await _raw_db.plads.find_one({"location_code": cand}):
                code = cand
                break
        if not code:
            raise HTTPException(status_code=500, detail="Kunne ikke generere kode")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "location_code": code,
        "code": code,  # alias for convenience
        "address": (body.address or "").strip(),
        "city": (body.city or "").strip(),
        "active": True,
        "company_id": caller["company_id"],
        "location_group_id": (body.location_group_id or None),
        "materials": ["Pap til HCS", "Papir til HCS", "Glas til HCS",
                      "Metal til HCS", "Træ til HCS", "Restaffald"],
        "containers_per_material": 3,
        "assigned_logistics_company_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.plads.insert_one(doc)
    await _audit("org_location_created", payload,
                 {"company_id": caller["company_id"], "location_code": code, "name": name})
    return {k: v for k, v in doc.items() if k != "_id"}


@org_router.put("/locations/{location_id}")
async def org_update_location(location_id: str, body: OrgLocationUpdate,
                              payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    loc = await _raw_db.plads.find_one({"id": location_id}, {"_id": 0})
    if not loc or loc.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Lokation ikke fundet")
    raw = body.model_dump()
    update = {k: v for k, v in raw.items() if v is not None}
    # Allow clearing the group by sending empty string
    if "location_group_id" in raw and raw["location_group_id"] is not None:
        update["location_group_id"] = raw["location_group_id"].strip() or None
    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")
    await _raw_db.plads.update_one({"id": location_id}, {"$set": update})
    res = await _raw_db.plads.find_one({"id": location_id}, {"_id": 0})
    res.setdefault("code", res.get("location_code") or "")
    return res


@org_router.delete("/locations/{location_id}")
async def org_delete_location(location_id: str,
                              payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    loc = await _raw_db.plads.find_one({"id": location_id}, {"_id": 0})
    if not loc or loc.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Lokation ikke fundet")
    await _raw_db.plads.delete_one({"id": location_id})
    return {"success": True}


# ----- PER-LOCATION LOGISTICS PARTNER ASSIGNMENT -----------------------------
class LocationLogisticsAssign(BaseModel):
    logistics_company_ids: List[str] = Field(default_factory=list)


@org_router.put("/locations/{location_id}/logistics-partners")
async def org_set_location_logistics(location_id: str,
                                     body: LocationLogisticsAssign,
                                     payload: dict = Depends(require_role("customer_admin"))):
    """Assign one or more logistics companies to a specific location.
    Only the customer_admin that owns the location may set this. The list is
    the source of truth: drivers from those logistics companies (and only
    those) will see this location in their app."""
    caller = await _org_caller(payload)
    loc = await _raw_db.plads.find_one({"id": location_id}, {"_id": 0})
    if not loc or loc.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Lokation ikke fundet")
    # Validate every id refers to an actual logistics company
    ids = [x for x in (body.logistics_company_ids or []) if x]
    if ids:
        valid = await _raw_db.companies.find(
            {"id": {"$in": ids}, "company_type": COMPANY_TYPE_LOGISTICS},
            {"_id": 0, "id": 1},
        ).to_list(1000)
        valid_ids = {c["id"] for c in valid}
        unknown = [x for x in ids if x not in valid_ids]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Ukendt(e) logistik-firma(er): {', '.join(unknown)}",
            )
        ids = [x for x in ids if x in valid_ids]
    await _raw_db.plads.update_one(
        {"id": location_id},
        {"$set": {"assigned_logistics_company_ids": ids}},
    )
    await _audit("org_location_logistics_set", payload,
                 {"location_id": location_id, "logistics_company_ids": ids})
    res = await _raw_db.plads.find_one({"id": location_id}, {"_id": 0})
    res.setdefault("code", res.get("location_code") or "")
    return res


# ----- USERS (delegated creation, gated by what the caller may create) -------
def _allowed_child_roles(caller_role: str) -> set:
    return {
        "customer_admin": {"location_admin", "order"},
        "location_admin": {"order"},
        "logistics_admin": {"driver"},
    }.get(caller_role, set())


@org_router.get("/users")
async def org_list_users(payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    role = caller.get("role")
    if role not in ("customer_admin", "location_admin", "logistics_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    q = {"company_id": caller["company_id"]}
    if role == "location_admin":
        # employees of ALL pladser this admin manages
        managed = list(caller.get("assigned_plads_ids") or [])
        own = caller.get("location_code")
        codes = sorted({c for c in (managed + ([own] if own else [])) if c})
        if not codes:
            return []
        q["location_code"] = {"$in": codes}
        q["role"] = "order"
    else:
        # only the child roles this caller manages
        q["role"] = {"$in": list(_allowed_child_roles(role))}
    users = await _raw_db.users.find(q, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(2000)
    return users


@org_router.post("/users")
async def org_create_user(body: OrgUserCreate,
                          payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    caller_role = caller.get("role")
    allowed = _allowed_child_roles(caller_role)
    if not allowed:
        raise HTTPException(status_code=403, detail="Du må ikke oprette brugere")
    role = (body.role or "").strip()
    if role not in allowed:
        raise HTTPException(status_code=403,
                            detail=f"Du må kun oprette: {', '.join(sorted(allowed))}")

    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email er påkrævet")

    # New rule (Phase 2): location_admin, order AND driver users go through
    # the invitation flow. No more shared driver_code. Each driver gets their
    # own email + password via /set-password.
    invite_only_roles = {"location_admin", "order", "driver"}
    use_invitation = role in invite_only_roles or bool(body.send_invitation) or not body.password

    if not use_invitation:
        if not body.password or len(body.password) < 4:
            raise HTTPException(status_code=400, detail="Password skal være mindst 4 tegn")
    # Multi-tenant: the SAME email may exist across different companies (e.g.
    # an ILK admin invited separately by ARGO and MARTO). We only block
    # duplicate (email, company_id) within the SAME tenant.
    if await _raw_db.users.find_one({"email": email, "company_id": caller["company_id"]}):
        raise HTTPException(
            status_code=409,
            detail="Email findes allerede i dette firma",
        )

    cid = caller["company_id"]
    location_code = (body.location_code or "").strip()
    location_name = (getattr(body, "location_name", "") or "").strip()
    # Multi-location: customer_admin may grant access to several pladser at
    # once when inviting a location_admin. The first non-empty entry becomes
    # the primary `location_code`; every entry is also stored in
    # assigned_plads_ids so the admin sees all of them.
    location_codes_raw = list(getattr(body, "location_codes", None) or [])
    location_codes = [c.strip() for c in location_codes_raw if c and str(c).strip()]

    # Location binding rules. When a customer_admin invites a location_admin
    # we let them either pick an existing location_code OR supply a NEW
    # `location_name` (and optionally `location_code`) which we'll create on
    # the fly so they don't have to switch between two screens.
    if role in ("location_admin", "order"):
        if caller_role == "location_admin":
            # employees are forced to ONE of the admin's managed locations.
            # If the caller passed an explicit location_code, validate it is
            # inside their managed set; otherwise fall back to their primary.
            managed = list(caller.get("assigned_plads_ids") or [])
            primary = caller.get("location_code") or ""
            if primary and primary not in managed:
                managed.append(primary)
            if location_code:
                if location_code not in managed:
                    raise HTTPException(
                        status_code=403,
                        detail="Du administrerer ikke denne lokation",
                    )
            else:
                location_code = primary or (managed[0] if managed else "")
        loc = None
        # Prefer explicit location_codes[0] over location_code for location_admin
        if role == "location_admin" and location_codes and not location_code:
            location_code = location_codes[0]
        if location_code:
            loc = await _raw_db.plads.find_one(
                {"location_code": location_code, "company_id": cid}, {"_id": 0},
            )
        # Inline-create when the customer_admin supplies just a name and the
        # code either doesn't exist or wasn't provided. Only customer_admin
        # can create new locations; the location_admin → order path always
        # reuses the admin's own location.
        if not loc and caller_role == "customer_admin" and location_name:
            import random as _rnd
            if not location_code:
                for _ in range(50):
                    cand = str(_rnd.randint(1000, 9999))
                    if not await _raw_db.plads.find_one({"location_code": cand}):
                        location_code = cand
                        break
                if not location_code:
                    raise HTTPException(status_code=500, detail="Kunne ikke generere lokationskode")
            else:
                if await _raw_db.plads.find_one({"location_code": location_code}):
                    raise HTTPException(status_code=409, detail="Lokationskode er allerede i brug")
            loc_doc = {
                "id": str(uuid.uuid4()),
                "name": location_name,
                "location_code": location_code,
                "code": location_code,
                "address": "", "city": "",
                "active": True, "company_id": cid,
                "materials": ["Pap til HCS", "Papir til HCS", "Glas til HCS",
                              "Metal til HCS", "Træ til HCS", "Restaffald"],
                "containers_per_material": 3,
                "assigned_logistics_company_ids": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await _raw_db.plads.insert_one(loc_doc)
            loc = loc_doc
            await _audit("org_location_created_inline", payload, {
                "company_id": cid, "location_code": location_code, "name": location_name,
            })
        if not loc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Lokation er påkrævet for denne rolle. "
                    "Vælg en eksisterende lokation, eller angiv et nyt lokationsnavn."
                ) if role == "location_admin" else "Ukendt lokation for din virksomhed",
            )

    # Compute the full set of pladser this user is allowed to access. For
    # location_admin: every code passed in `location_codes` (after validating
    # each one belongs to the caller's company) plus the primary code.
    # Pr. brugerkrav 2026-06-15 (runde 9): `order`-medarbejdere kan nu også
    # tildeles FLERE lokationer i én session så de selv kan vælge hvilken
    # plads de logger ind på (samme adfærd som LA, men kun for ordrer).
    assigned_plads_ids: List[str] = []
    if role in ("location_admin", "order"):
        candidate = list({c for c in (location_codes + [location_code]) if c})
        if candidate:
            valid = await _raw_db.plads.find(
                {"location_code": {"$in": candidate}, "company_id": cid},
                {"_id": 0, "location_code": 1},
            ).to_list(1000)
            assigned_plads_ids = sorted({v["location_code"] for v in valid})
            # primary location_code MUST be in the validated set
            if location_code and location_code not in assigned_plads_ids:
                raise HTTPException(status_code=404, detail="Lokation ikke fundet")
            # Hvis ingen primary blev angivet (men location_codes var), brug første
            if not location_code and assigned_plads_ids:
                location_code = assigned_plads_ids[0]

    user = AuthUser(
        email=email,
        name=(body.name or "").strip() or email,
        role=role,
        company_id=cid,
        phone=(body.phone or "").strip() or None,
        employment_date=(body.employment_date or "").strip() or None,
        location_code=location_code or None,
        # location_admin sees only its own pladser in report screens
        assigned_plads_ids=assigned_plads_ids,
        invitation_status="pending" if use_invitation else "active",
    )
    doc = user.model_dump()
    doc["password_hash"] = "" if use_invitation else hash_password(body.password)
    try:
        await _raw_db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email findes allerede")

    if use_invitation:
        await _send_invite_for_user(doc)
    await _audit("org_user_created", payload,
                 {"company_id": cid, "email": email, "role": role,
                  "location_code": location_code or None, "by_role": caller_role,
                  "invitation": use_invitation})
    return {"id": user.id, "email": email, "role": role, "name": user.name,
            "location_code": location_code or None,
            "invitation_status": user.invitation_status,
            "phone": user.phone, "employment_date": user.employment_date}


@org_router.put("/users/{user_id}")
async def org_update_user(user_id: str, body: OrgUserUpdate,
                          payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    allowed = _allowed_child_roles(caller.get("role"))
    target = await _raw_db.users.find_one({"id": user_id}, {"_id": 0})
    if not target or target.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    if target.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Du må ikke redigere denne bruger")
    # Lokation Admin må kun røre brugere knyttet til en af sine pladser
    if caller.get("role") == "location_admin":
        managed = set(caller.get("assigned_plads_ids") or [])
        if caller.get("location_code"):
            managed.add(caller["location_code"])
        if target.get("location_code") not in managed:
            raise HTTPException(status_code=403, detail="Bruger tilhører en anden lokation")

    update: Dict[str, Any] = {}
    raw = body.model_dump(exclude_unset=True)
    if "name" in raw and raw["name"] is not None:
        update["name"] = raw["name"].strip()
    if "email" in raw and raw["email"] is not None:
        new_email = raw["email"].strip().lower()
        if not new_email:
            raise HTTPException(status_code=400, detail="Email må ikke være tom")
        clash = await _raw_db.users.find_one({
            "email": new_email, "company_id": caller["company_id"], "id": {"$ne": user_id},
        })
        if clash:
            raise HTTPException(status_code=409, detail="Email findes allerede i dette firma")
        update["email"] = new_email
    if "phone" in raw:
        update["phone"] = (raw["phone"] or "").strip() or None
    if "employment_date" in raw:
        update["employment_date"] = (raw["employment_date"] or "").strip() or None
    if "active" in raw and raw["active"] is not None:
        update["active"] = bool(raw["active"])
    # Multi-location reassignment.
    # Pr. brugerkrav 2026-06-15 (runde 9): location_admin må også sætte flere
    # lokationer for `order`-medarbejdere — men kun blandt LA's egne pladser.
    if "location_codes" in raw and raw["location_codes"] is not None:
        caller_role = caller.get("role")
        target_role = target.get("role")
        if caller_role == "customer_admin":
            allowed_codes = None  # any plads in firma
        elif caller_role == "location_admin" and target_role == "order":
            la_codes = set([
                *(caller.get("assigned_plads_ids") or []),
                caller.get("location_code") or "",
            ])
            la_codes.discard("")
            allowed_codes = la_codes
        else:
            raise HTTPException(status_code=403, detail="Du må ikke ændre lokations-tildeling for denne bruger")
        codes = [c for c in raw["location_codes"] if c]
        if codes:
            # Begræns til LA's egne pladser når det er LA der opdaterer
            if allowed_codes is not None:
                codes = [c for c in codes if c in allowed_codes]
                if not codes:
                    raise HTTPException(status_code=403, detail="Ingen af lokationerne er under din administration")
            valid = await _raw_db.plads.find(
                {"location_code": {"$in": codes}, "company_id": caller["company_id"]},
                {"_id": 0, "location_code": 1},
            ).to_list(1000)
            valid_codes = sorted({v["location_code"] for v in valid})
            if not valid_codes:
                raise HTTPException(status_code=404, detail="Ingen af lokationerne tilhører dit firma")
            update["assigned_plads_ids"] = valid_codes
            # Keep `location_code` valid: if the current primary is no longer
            # in the set, snap to the first new code.
            current_primary = target.get("location_code") or ""
            if current_primary not in valid_codes:
                update["location_code"] = valid_codes[0]
        else:
            # Brugerkrav 2026-06-15 (Krav 1): Når alle lokationer afkobles,
            # skal LA'en være helt løsrevet — ryd også den primære location_code,
            # så `adminsForLoc` i UI'et ikke længere viser brugeren som
            # tilknyttet en lokation.
            update["assigned_plads_ids"] = []
            update["location_code"] = ""
    if "location_code" in raw and raw["location_code"] is not None:
        new_primary = (raw["location_code"] or "").strip()
        if not new_primary:
            raise HTTPException(status_code=400, detail="location_code må ikke være tom")
        plads = await _raw_db.plads.find_one(
            {"location_code": new_primary, "company_id": caller["company_id"]},
            {"_id": 0},
        )
        if not plads:
            raise HTTPException(status_code=404, detail="Ukendt lokation for dit firma")
        # location_admin reassigning an employee must control the destination
        if caller.get("role") == "location_admin":
            managed = set(caller.get("assigned_plads_ids") or [])
            if caller.get("location_code"):
                managed.add(caller["location_code"])
            if new_primary not in managed:
                raise HTTPException(status_code=403, detail="Du administrerer ikke denne lokation")
        update["location_code"] = new_primary
        # Order users get assigned_plads_ids re-synced to their primary
        if target.get("role") == "order":
            update["assigned_plads_ids"] = [new_primary]

    if not update:
        raise HTTPException(status_code=400, detail="Intet at opdatere")

    await _raw_db.users.update_one({"id": user_id}, {"$set": update})
    await _audit("org_user_updated", payload, {
        "company_id": caller["company_id"], "user_id": user_id,
        "fields": list(update.keys()),
    })
    refreshed = await _raw_db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return refreshed


@org_router.post("/users/{user_id}/resend-invitation")
async def org_resend_invitation(user_id: str,
                                payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    allowed = _allowed_child_roles(caller.get("role"))
    target = await _raw_db.users.find_one({"id": user_id}, {"_id": 0})
    if not target or target.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    if target.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Du må ikke gensende til denne bruger")
    if caller.get("role") == "location_admin":
        managed = set(caller.get("assigned_plads_ids") or [])
        if caller.get("location_code"):
            managed.add(caller["location_code"])
        if target.get("location_code") not in managed:
            raise HTTPException(status_code=403, detail="Bruger tilhører en anden lokation")
    await _raw_db.users.update_one(
        {"id": user_id},
        {"$set": {"invitation_status": "pending", "password_hash": ""}},
    )
    target["invitation_status"] = "pending"
    target["password_hash"] = ""
    result = await _send_invite_for_user(target)
    await _audit("org_user_invitation_resent", payload, {
        "company_id": caller["company_id"], "user_id": user_id, "email": target.get("email"),
    })
    return {"success": True, "delivered": bool(result and result.get("id"))}


@org_router.delete("/users/{user_id}")
async def org_delete_user(user_id: str, payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    allowed = _allowed_child_roles(caller.get("role"))
    target = await _raw_db.users.find_one({"id": user_id}, {"_id": 0})
    if not target or target.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Bruger ikke fundet")
    if target.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Du må ikke slette denne bruger")
    if caller.get("role") == "location_admin" and target.get("location_code") != caller.get("location_code"):
        # location_admin may also delete employees in any of their managed
        # locations (assigned_plads_ids). Allow if the target's location is
        # in the caller's full managed set.
        managed = set(caller.get("assigned_plads_ids") or [])
        if caller.get("location_code"):
            managed.add(caller["location_code"])
        if target.get("location_code") not in managed:
            raise HTTPException(status_code=403, detail="Bruger tilhører en anden lokation")
    # Full delete: hard-remove the user document regardless of active flag.
    # This is the explicit "fuld sletning" path requested by customers.
    await _raw_db.users.delete_one({"id": user_id})
    # Clean up any outstanding invitation/reset tokens
    await _raw_db.invitation_tokens.delete_many({"user_id": user_id})
    await _audit("org_user_purged", payload, {
        "company_id": caller["company_id"], "user_id": user_id,
        "email": target.get("email"),
        "was_active": bool(target.get("active", True)),
    })
    return {"success": True}


# ----- LOGISTICS PARTNER LINKING (customer_admin links an ILK-type company) --
@org_router.get("/logistics-companies")
async def org_list_logistics_companies(payload: dict = Depends(require_role("customer_admin"))):
    """List logistics-type companies the customer can partner with."""
    comps = await _raw_db.companies.find(
        {"company_type": COMPANY_TYPE_LOGISTICS},
        {"_id": 0, "id": 1, "name": 1, "serves_company_ids": 1},
    ).sort("name", 1).to_list(1000)
    caller = await _org_caller(payload)
    cid = caller["company_id"]
    for c in comps:
        c["linked"] = cid in (c.get("serves_company_ids") or [])
    return comps


@org_router.get("/my-partners")
async def org_my_partners(payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    cid = caller["company_id"]
    comps = await _raw_db.companies.find(
        {"company_type": COMPANY_TYPE_LOGISTICS, "serves_company_ids": cid},
        {"_id": 0, "id": 1, "name": 1},
    ).sort("name", 1).to_list(1000)
    return comps


@org_router.post("/logistics-partners")
async def org_link_logistics_partner(body: LogisticsPartnerLink,
                                     payload: dict = Depends(require_role("customer_admin"))):
    """Link a logistics company so it serves my customer org. Optionally create
    that logistics org's first logistics_admin in the same step."""
    caller = await _org_caller(payload)
    cid = caller["company_id"]
    logi = await _raw_db.companies.find_one({"id": body.logistics_company_id}, {"_id": 0})
    if not logi or logi.get("company_type") != COMPANY_TYPE_LOGISTICS:
        raise HTTPException(status_code=404, detail="Logistik-firma ikke fundet")

    serves = list(logi.get("serves_company_ids") or [])
    if cid not in serves:
        serves.append(cid)
        await _raw_db.companies.update_one(
            {"id": logi["id"]}, {"$set": {"serves_company_ids": serves}}
        )
        invalidate_company_cache(logi["id"])

    created_admin = None
    if body.admin and (body.admin.email or "").strip():
        # Multi-tenant rule: EVERY customer that links a logistics partner
        # may seed their OWN admin user for that partner — possibly with the
        # same email and a customer-specific password. The system records
        # them as separate users (different passwords), so when Bo logs in
        # with ARGO's password he gets ARGO context, with MARTO's password
        # MARTO context. We just ensure (email, customer_link) is unique to
        # avoid double-creating the same admin from the same customer.
        email = body.admin.email.strip().lower()
        if not body.admin.password or len(body.admin.password) < 4:
            raise HTTPException(status_code=400, detail="Admin password skal være mindst 4 tegn")
        # Block: same email already exists under THIS logistics company with the
        # SAME linked_customer_id (i.e. this same customer already invited them).
        dup = await _raw_db.users.find_one({
            "email": email,
            "company_id": logi["id"],
            "linked_customer_id": cid,
        })
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Du har allerede tilføjet en admin med email {email} for dette logistik-firma",
            )
        admin_user = AuthUser(
            email=email,
            name=(body.admin.name or "").strip() or email,
            role="logistics_admin",
            company_id=logi["id"],
        )
        adoc = admin_user.model_dump()
        adoc["password_hash"] = hash_password(body.admin.password)
        # Track which customer invited this admin (for audit + per-customer disambiguation)
        adoc["linked_customer_id"] = cid
        await _raw_db.users.insert_one(adoc)
        created_admin = {"email": email, "role": "logistics_admin"}

    await _audit("org_logistics_linked", payload,
                 {"customer_company_id": cid, "logistics_company_id": logi["id"],
                  "logistics_name": logi["name"], "created_admin": bool(created_admin)})
    return {"success": True, "logistics": {"id": logi["id"], "name": logi["name"]},
            "created_admin": created_admin}


@org_router.delete("/logistics-partners/{logistics_company_id}")
async def org_unlink_logistics_partner(logistics_company_id: str,
                                       payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    cid = caller["company_id"]
    logi = await _raw_db.companies.find_one({"id": logistics_company_id}, {"_id": 0})
    if not logi:
        raise HTTPException(status_code=404, detail="Logistik-firma ikke fundet")
    serves = [c for c in (logi.get("serves_company_ids") or []) if c != cid]
    await _raw_db.companies.update_one(
        {"id": logistics_company_id}, {"$set": {"serves_company_ids": serves}}
    )
    invalidate_company_cache(logistics_company_id)
    await _audit("org_logistics_unlinked", payload,
                 {"customer_company_id": cid, "logistics_company_id": logistics_company_id})
    return {"success": True}


app.include_router(auth_router)
# ===================================================================
#                  HELLIGDAGE  /  ÅBNINGSTIDER
#  Datamodel:
#   - holiday_groups   : Super Admin maintained library (name + list of holidays).
#                        Companies refer to a group via Company.holiday_group_id.
#   - holiday_calendars: Location Admin's per-plads calendar. Pre-filled at
#                        creation from the customer's assigned group. Each
#                        holiday has its own open_from/open_to or `closed=True`.
#   - hours_calendars  : Location Admin's per-plads weekday calendar
#                        (mon..sun open/close/closed).
#   - material_calendars: Mapping table per (location_code, material) → (holiday_calendar_id, hours_calendar_id).
# ===================================================================
import re as _re_holiday  # noqa: E402


def _holiday_strip_holidays(arr) -> List[Dict[str, Any]]:
    """Validate + sanitize a list of holiday entries. Each entry must have
    `name` (non-empty) and `date` (YYYY-MM-DD)."""
    out: List[Dict[str, Any]] = []
    if not isinstance(arr, list):
        return out
    date_re = _re_holiday.compile(r"^\d{4}-\d{2}-\d{2}$")
    for it in arr:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        date = str(it.get("date", "")).strip()
        if not name or not date_re.match(date):
            continue
        out.append({"name": name, "date": date})
    return out


def _holiday_day_entry(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    date = str(raw.get("date", "")).strip()
    if not name or not date:
        return None
    closed = bool(raw.get("closed", False))
    open_from = str(raw.get("open_from", "")).strip()
    open_to = str(raw.get("open_to", "")).strip()
    # delivery_address_id: optional reference into the address library
    # (added iteration 18). Null when the LA doesn't override the default
    # — in that case the resolve endpoint falls back to the weekday entry.
    delivery_address_id = raw.get("delivery_address_id") or None
    if closed:
        open_from = ""
        open_to = ""
    return {
        "name": name, "date": date, "closed": closed,
        "open_from": open_from, "open_to": open_to,
        "delivery_address_id": delivery_address_id,
    }


def _weekday_entry(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    closed = bool(raw.get("closed", False))
    open_from = str(raw.get("open_from", "")).strip()
    open_to = str(raw.get("open_to", "")).strip()
    # delivery_address_id is REQUIRED on weekday entries (validated when the
    # caller saves the calendar — we don't bail here so the LA can still
    # iterate on a partially-filled calendar in draft).
    delivery_address_id = raw.get("delivery_address_id") or None
    if closed:
        open_from = ""
        open_to = ""
    return {
        "closed": closed, "open_from": open_from, "open_to": open_to,
        "delivery_address_id": delivery_address_id,
    }


WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# -------------------------- SUPER ADMIN: holiday-groups --------------------------

@sa_router.get("/holiday-groups")
async def sa_list_holiday_groups():
    items = await _raw_db.holiday_groups.find({}, {"_id": 0}).sort("year", -1).to_list(500)
    # Attach assigned_count per group so the UI can render badges + block deletion
    if items:
        # Aggregate counts in a single query
        pipeline = [
            {"$match": {"holiday_group_id": {"$in": [g["id"] for g in items]}}},
            {"$group": {"_id": "$holiday_group_id", "count": {"$sum": 1}}},
        ]
        counts = {d["_id"]: d["count"] async for d in _raw_db.companies.aggregate(pipeline)}
        for g in items:
            g["assigned_count"] = counts.get(g["id"], 0)
            # default active=true for legacy docs that don't have the field
            g.setdefault("active", True)
    return items


@sa_router.post("/holiday-groups")
async def sa_create_holiday_group(body: dict, payload: dict = Depends(get_current_user_payload)):
    name = str((body or {}).get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    raw = body or {}
    year = raw.get("year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="year skal være et heltal")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "year": year,
        "active": True,
        "holidays": _holiday_strip_holidays(raw.get("holidays", [])),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.holiday_groups.insert_one(doc)
    await _audit("sa_holiday_group_created", payload, {"id": doc["id"], "name": name, "year": year})
    doc.pop("_id", None)
    return doc


@sa_router.put("/holiday-groups/{group_id}")
async def sa_update_holiday_group(group_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Helligdagsgruppe ikke fundet")
    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    raw = body or {}
    if "name" in raw:
        new_name = str(raw["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Navn må ikke være tomt")
        update["name"] = new_name
    if "year" in raw:
        y = raw["year"]
        if y is None or y == "":
            update["year"] = None
        else:
            try:
                update["year"] = int(y)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="year skal være et heltal")
    if "active" in raw:
        update["active"] = bool(raw["active"])
    if "holidays" in raw:
        update["holidays"] = _holiday_strip_holidays(raw["holidays"])
    await _raw_db.holiday_groups.update_one({"id": group_id}, {"$set": update})
    await _audit("sa_holiday_group_updated", payload, {"id": group_id})
    return await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})


@sa_router.post("/holiday-groups/{group_id}/copy")
async def sa_copy_holiday_group(group_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    """Duplicate a holiday group to a target year. All holiday names + dates
    are copied verbatim — the Super Admin adjusts dates manually afterwards
    (most Danish holidays shift each year, so the copy is a starting point)."""
    src = await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Helligdagsgruppe ikke fundet")
    raw = body or {}
    target_year = raw.get("target_year") or raw.get("year")
    try:
        target_year_int = int(target_year) if target_year is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="target_year skal være et heltal")
    base_name = str(raw.get("name") or src.get("name") or "").strip()
    # If the source already had a year, strip the trailing "– <year>" before re-suffixing.
    src_year = src.get("year")
    if src_year and base_name.endswith(f"– {src_year}"):
        base_name = base_name[: -len(f"– {src_year}")].strip()
    elif src_year and base_name.endswith(f"- {src_year}"):
        base_name = base_name[: -len(f"- {src_year}")].strip()
    new_name = f"{base_name} – {target_year_int}" if target_year_int else f"{base_name} (kopi)"
    new_doc = {
        "id": str(uuid.uuid4()),
        "name": new_name,
        "year": target_year_int,
        "active": True,
        "holidays": list(src.get("holidays", [])),  # shallow copy — items are plain dicts
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.holiday_groups.insert_one(new_doc)
    await _audit("sa_holiday_group_copied", payload, {"id": new_doc["id"], "src": group_id, "target_year": target_year_int})
    new_doc.pop("_id", None)
    return new_doc


@sa_router.post("/holiday-groups/{group_id}/toggle-active")
async def sa_toggle_holiday_group_active(group_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Helligdagsgruppe ikke fundet")
    raw = body or {}
    if "active" in raw:
        new_active = bool(raw["active"])
    else:
        new_active = not bool(existing.get("active", True))
    await _raw_db.holiday_groups.update_one(
        {"id": group_id},
        {"$set": {"active": new_active, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await _audit(
        "sa_holiday_group_activated" if new_active else "sa_holiday_group_deactivated",
        payload, {"id": group_id},
    )
    return {"id": group_id, "active": new_active}


@sa_router.delete("/holiday-groups/{group_id}")
async def sa_delete_holiday_group(group_id: str, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Helligdagsgruppe ikke fundet")
    # BLOCK permanent deletion when any customer references the group.
    # The UI is expected to surface the count and prompt the SA to
    # deactivate (soft delete) instead.
    assigned = await _raw_db.companies.count_documents({"holiday_group_id": group_id})
    if assigned > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Kan ikke slettes — gruppen er tildelt {assigned} kunde(r). Deaktiver gruppen i stedet.",
        )
    await _raw_db.holiday_groups.delete_one({"id": group_id})
    await _audit("sa_holiday_group_deleted", payload, {"id": group_id})
    return {"success": True}


# ===================================================================
#                  HELLIGDAGS-DELTA (Super Admin → Location Admins)
#  A delta is a set of operations (ADD/MODIFY/DELETE) on holiday names.
#  When SA "publishes" a delta, every Location Admin in the system gets
#  a pending notification that surfaces as a popup on next login.
#
#  Schema (collection `holiday_deltas`):
#    {id, name, year?, status: "draft"|"published", operations: [
#       {op: "add"|"modify"|"delete", match_name, new_name?, new_date?},
#    ], created_at, published_at?}
#
#  Notifications (collection `delta_notifications`):
#    {id, delta_id, user_id, status: "pending"|"accepted"|"rejected",
#     acted_at?, created_at}
#  When LA dismisses (reject) or imports (accept) → status flips and the
#  popup stops appearing.
# ===================================================================


def _delta_normalize_ops(raw_ops: Any) -> List[Dict[str, Any]]:
    """Strip + validate the operations list."""
    if not isinstance(raw_ops, list):
        raise HTTPException(status_code=400, detail="operations skal være en liste")
    out: List[Dict[str, Any]] = []
    valid_ops = {"add", "modify", "delete"}
    for o in raw_ops:
        if not isinstance(o, dict):
            continue
        op = str(o.get("op", "")).strip().lower()
        if op not in valid_ops:
            raise HTTPException(status_code=400, detail=f"Ukendt op: {op}")
        match_name = str(o.get("match_name") or o.get("name") or "").strip()
        if not match_name:
            raise HTTPException(status_code=400, detail="match_name (navn) er påkrævet pr. operation")
        entry: Dict[str, Any] = {"op": op, "match_name": match_name}
        if op != "delete":
            entry["new_name"] = str(o.get("new_name") or match_name).strip()
            entry["new_date"] = str(o.get("new_date") or "").strip()
            if not entry["new_date"]:
                raise HTTPException(status_code=400, detail="new_date er påkrævet ved add/modify")
        out.append(entry)
    return out


@sa_router.get("/holiday-deltas")
async def sa_list_holiday_deltas(payload: dict = Depends(get_current_user_payload)):
    items = await _raw_db.holiday_deltas.find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(200)
    return items


@sa_router.post("/holiday-deltas")
async def sa_create_holiday_delta(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    name = str(raw.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "year": _coerce_year(raw.get("year")),
        "status": "draft",
        "operations": _delta_normalize_ops(raw.get("operations") or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "published_at": None,
    }
    await _raw_db.holiday_deltas.insert_one(doc)
    doc.pop("_id", None)
    await _audit("sa_delta_created", payload, {"id": doc["id"]})
    return doc


@sa_router.put("/holiday-deltas/{delta_id}")
async def sa_update_holiday_delta(delta_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.holiday_deltas.find_one({"id": delta_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Delta ikke fundet")
    if existing.get("status") == "published":
        raise HTTPException(status_code=409, detail="Publiceret delta kan ikke redigeres")
    update: Dict[str, Any] = {}
    raw = body or {}
    if "name" in raw:
        nm = str(raw["name"] or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Navn må ikke være tomt")
        update["name"] = nm
    if "year" in raw:
        update["year"] = _coerce_year(raw["year"])
    if "operations" in raw:
        update["operations"] = _delta_normalize_ops(raw["operations"])
    if update:
        await _raw_db.holiday_deltas.update_one({"id": delta_id}, {"$set": update})
    return await _raw_db.holiday_deltas.find_one({"id": delta_id}, {"_id": 0})


@sa_router.post("/holiday-deltas/{delta_id}/publish")
async def sa_publish_holiday_delta(delta_id: str, body: dict | None = None,
                                   payload: dict = Depends(get_current_user_payload)):
    """Mark the delta as published and fan out a pending notification.

    Body (valgfri):
      - company_ids: List[str]  → kun publicér til LA'er på disse kunder.
        Hvis tom eller mangler, sendes til ALLE aktive kunde-LA'er
        (bevarer bagudkompatibilitet).
    Idempotent: eksisterende notifikationer for samme delta/user genbruges.
    """
    existing = await _raw_db.holiday_deltas.find_one({"id": delta_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Delta ikke fundet")
    if not existing.get("operations"):
        raise HTTPException(status_code=400, detail="Delta uden operationer kan ikke publiceres")
    now = datetime.now(timezone.utc).isoformat()
    await _raw_db.holiday_deltas.update_one(
        {"id": delta_id},
        {"$set": {"status": "published", "published_at": now}},
    )
    company_ids = []
    if body:
        raw = body.get("company_ids") or []
        company_ids = [str(c) for c in raw if str(c).strip()]
    user_q: Dict[str, Any] = {"role": "location_admin", "active": True}
    if company_ids:
        user_q["company_id"] = {"$in": company_ids}
    la_ids = [u["id"] async for u in _raw_db.users.find(user_q, {"_id": 0, "id": 1})]
    notifications_created = 0
    for uid in la_ids:
        existing_notif = await _raw_db.delta_notifications.find_one(
            {"delta_id": delta_id, "user_id": uid},
        )
        if not existing_notif:
            await _raw_db.delta_notifications.insert_one({
                "id": str(uuid.uuid4()),
                "delta_id": delta_id,
                "user_id": uid,
                "status": "pending",
                "created_at": now,
                "acted_at": None,
            })
            notifications_created += 1
    await _audit("sa_delta_published", payload,
                 {"id": delta_id, "notifications": notifications_created,
                  "company_ids": company_ids})
    return {"published_at": now, "notifications_created": notifications_created,
            "total_recipients": len(la_ids), "scope_company_ids": company_ids}


@sa_router.delete("/holiday-deltas/{delta_id}")
async def sa_delete_holiday_delta(delta_id: str, payload: dict = Depends(get_current_user_payload)):
    """Slet en helligdags-delta uanset status. Hvis den er publiceret, ryddes
    også alle relaterede notifikationer hos LA'erne (dem der ikke har handlet)
    og evt. spor i import-historikken. LA'er der allerede har importeret deltaet
    beholder deres data — vi rører kun selve delta-dokumentet og pending
    notifikationer."""
    existing = await _raw_db.holiday_deltas.find_one({"id": delta_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Delta ikke fundet")
    # Ryd notifikationer (alle statusser) så LA'er ikke ser dem længere
    deleted_notifs = await _raw_db.delta_notifications.delete_many({"delta_id": delta_id})
    await _raw_db.holiday_deltas.delete_one({"id": delta_id})
    return {
        "success": True,
        "deleted_notifications": deleted_notifs.deleted_count,
    }


# ----- LA-side: pending notifications + accept/reject ---------------

@org_router.get("/holiday-deltas/pending")
async def org_list_pending_deltas(payload: dict = Depends(get_current_user_payload)):
    """Returns deltas that the caller (LA) has NOT yet accepted or rejected.
    Each delta is paired with its notification id so the LA can act on it."""
    caller = await _org_caller(payload)
    if caller.get("role") != "location_admin":
        return []
    notifs = await _raw_db.delta_notifications.find(
        {"user_id": caller["id"], "status": "pending"},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)
    out = []
    for n in notifs:
        delta = await _raw_db.holiday_deltas.find_one({"id": n["delta_id"]}, {"_id": 0})
        if not delta:
            continue
        out.append({**n, "delta": delta})
    return out


@org_router.get("/holiday-deltas/received")
async def org_list_received_deltas(days: int = 30,
                                    payload: dict = Depends(get_current_user_payload)):
    """Brugerkrav 2026-06-15 (Krav 2): Returnerer ALLE delta'er som LA har
    modtaget de seneste ``days`` dage — uanset om de er pending, accepted eller
    rejected. Tillader LA at gen-publicere et delta til andre kalendere senere.

    Beriger hvert delta med:
      * `applied_calendar_ids`: liste over kalendere LA allerede har publiceret til
      * `available_calendar_ids`: liste over LA's kalendere som ENDNU IKKE har modtaget
        dette delta (= multi-publish-targets)
    """
    caller = await _org_caller(payload)
    if caller.get("role") != "location_admin":
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))).isoformat()
    notifs = await _raw_db.delta_notifications.find(
        {"user_id": caller["id"], "created_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)

    # Find LA's egne kalendere én gang (samme firma)
    own_cals = await _raw_db.holiday_calendars.find(
        {"company_id": caller["company_id"]},
        {"_id": 0, "id": 1, "name": 1, "is_active": 1, "year": 1},
    ).to_list(500)
    active_cal_ids = [c["id"] for c in own_cals if c.get("is_active", True)]

    out = []
    for n in notifs:
        delta = await _raw_db.holiday_deltas.find_one({"id": n["delta_id"]}, {"_id": 0})
        if not delta:
            continue
        applied = list(n.get("applied_calendar_ids") or [])
        # Available targets = active calendars that haven't received this delta yet
        available = [cid for cid in active_cal_ids if cid not in applied]
        out.append({
            **n,
            "delta": delta,
            "applied_calendar_ids": applied,
            "available_calendar_ids": available,
            "calendars": own_cals,
        })
    return out


@org_router.post("/holiday-deltas/{notification_id}/reject")
async def org_reject_delta(notification_id: str, payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    n = await _raw_db.delta_notifications.find_one({"id": notification_id}, {"_id": 0})
    if not n or n.get("user_id") != caller["id"]:
        raise HTTPException(status_code=404, detail="Notifikation ikke fundet")
    await _raw_db.delta_notifications.update_one(
        {"id": notification_id},
        {"$set": {"status": "rejected", "acted_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}


@org_router.post("/holiday-deltas/{notification_id}/import")
async def org_import_delta(notification_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    """Apply the (possibly LA-edited) delta operations to one or MORE of the
    LA's holiday_calendars. Body shape:

        {
          "calendar_id": "<id>",       # legacy single-target
          "calendar_ids": ["<id>", ...],  # NEW: multi-publish (Krav 2)
          "operations": [
            {"op": "add"|"modify"|"delete", "match_name": "<name>",
             "new_name": "<name>", "new_date": "YYYY-MM-DD"},
            ...
          ]
        }

    Brugerkrav 2026-06-15 (Krav 2): Når flere kalender-id'er er angivet
    publiceres delta til hver enkelt. Notifikationen bliver KUN markeret
    'accepted' (frigør popup), men forbliver synlig i den nye 30-dages tab
    så LA kan publicere det igen til andre kalendere senere.
    """
    caller = await _org_caller(payload)
    n = await _raw_db.delta_notifications.find_one({"id": notification_id}, {"_id": 0})
    if not n or n.get("user_id") != caller["id"]:
        raise HTTPException(status_code=404, detail="Notifikation ikke fundet")
    raw = body or {}

    # Accept either calendar_id (single) or calendar_ids (array, multi-publish)
    cal_ids_raw = raw.get("calendar_ids")
    if isinstance(cal_ids_raw, list) and cal_ids_raw:
        cal_ids = [str(c).strip() for c in cal_ids_raw if c and str(c).strip()]
    else:
        single = str(raw.get("calendar_id") or "").strip()
        cal_ids = [single] if single else []
    if not cal_ids:
        raise HTTPException(status_code=400, detail="calendar_id eller calendar_ids er påkrævet")

    # Validate ALL calendars before mutating any of them
    cals = []
    for cid in cal_ids:
        cal = await _raw_db.holiday_calendars.find_one({"id": cid}, {"_id": 0})
        if not cal or cal.get("company_id") != caller["company_id"]:
            raise HTTPException(status_code=403, detail=f"Kalender {cid} ikke fundet eller adgang nægtet")
        cals.append(cal)

    ops = raw.get("operations")
    if not ops:
        delta = await _raw_db.holiday_deltas.find_one({"id": n["delta_id"]}, {"_id": 0})
        ops = (delta or {}).get("operations", [])

    summary = {"added": 0, "modified": 0, "deleted": 0, "calendars": []}
    for cal in cals:
        days = list(cal.get("days") or [])
        name_idx = {d["name"].strip().lower(): i for i, d in enumerate(days)}
        # Brugerkrav 2026-06-15 (runde 11 bugfix): `add`-ops skal matche på
        # NAVN + DATO så samme helligdag for et andet år/dato kan tilføjes.
        # Tidligere blev fx "Juledag 2027-12-24" tavst skippet hvis "Juledag
        # 2026-12-24" allerede fandtes — så LA så "0 tilføjet" på trods af
        # success-toast.
        name_date_idx = {
            (d["name"].strip().lower(), str(d.get("date") or "").strip()): i
            for i, d in enumerate(days)
        }
        per_cal = {"added": 0, "modified": 0, "deleted": 0}
        for o in ops:
            op = str(o.get("op", "")).lower()
            match = str(o.get("match_name") or "").strip().lower()
            if not match:
                continue
            idx = name_idx.get(match)
            if op == "delete":
                if idx is not None:
                    days.pop(idx)
                    name_idx = {d["name"].strip().lower(): i for i, d in enumerate(days)}
                    name_date_idx = {
                        (d["name"].strip().lower(), str(d.get("date") or "").strip()): i
                        for i, d in enumerate(days)
                    }
                    per_cal["deleted"] += 1
            elif op == "modify":
                if idx is not None:
                    days[idx] = {
                        "name": str(o.get("new_name") or days[idx]["name"]).strip(),
                        "date": str(o.get("new_date") or days[idx]["date"]).strip(),
                        "closed": days[idx].get("closed", False),
                        "open_from": days[idx].get("open_from", ""),
                        "open_to": days[idx].get("open_to", ""),
                        "delivery_address_id": days[idx].get("delivery_address_id"),
                    }
                    per_cal["modified"] += 1
            elif op == "add":
                new_name = str(o.get("new_name") or o.get("match_name")).strip()
                new_date = str(o.get("new_date") or "").strip()
                key = (new_name.lower(), new_date)
                # Skip kun hvis EXACT (navn + dato) duplikat findes
                if key not in name_date_idx:
                    days.append({
                        "name": new_name,
                        "date": new_date,
                        "closed": False, "open_from": "", "open_to": "",
                        "delivery_address_id": None,
                    })
                    name_idx[new_name.lower()] = len(days) - 1
                    name_date_idx[key] = len(days) - 1
                    per_cal["added"] += 1
        await _raw_db.holiday_calendars.update_one(
            {"id": cal["id"]},
            {"$set": {"days": days, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        summary["added"] += per_cal["added"]
        summary["modified"] += per_cal["modified"]
        summary["deleted"] += per_cal["deleted"]
        summary["calendars"].append({"id": cal["id"], "name": cal.get("name", ""), **per_cal})

    # Mark notification as accepted (closes popup) + record applied calendars.
    # Notification stays VISIBLE in the 30-day "Modtagne" tab so LA can later
    # publish this delta to additional calendars via the same endpoint.
    await _raw_db.delta_notifications.update_one(
        {"id": notification_id},
        {
            "$set": {"status": "accepted", "acted_at": datetime.now(timezone.utc).isoformat()},
            "$addToSet": {"applied_calendar_ids": {"$each": [c["id"] for c in cals]}},
        },
    )
    return {"success": True, **summary}


# -------------------------- ORG: helligdags-kalender + åbningstid-kalender --------------------------

async def _resolve_plads_for_org(code: str, payload: dict) -> dict:
    """Find the plads doc & ensure the caller can manage it. Returns the plads."""
    caller = await _org_caller(payload)
    role = caller.get("role")
    if role not in ("customer_admin", "location_admin"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    plads = await _raw_db.plads.find_one({"location_code": code}, {"_id": 0})
    if not plads or plads.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Lokation ikke fundet")
    if role == "location_admin":
        managed = set(caller.get("assigned_plads_ids") or [])
        if caller.get("location_code"):
            managed.add(caller["location_code"])
        if code not in managed:
            raise HTTPException(status_code=403, detail="Du administrerer ikke denne lokation")
    return {"plads": plads, "caller": caller}


# ------------------- Kopiér konfiguration fra én lokation til en anden -------------------

@org_router.post("/schedule/copy-config")
async def org_copy_schedule_config(payload_body: dict, payload: dict = Depends(get_current_user_payload)):
    """Kopier ALT konfiguration fra source_code → target_code.

    Body: {
      "source_code": "1967",
      "target_code": "6164",
      "sections": [...]   # OPTIONAL — hvis mangler eller tom, kopieres ALT
    }

    Følgende data-collections/felter kopieres og er lokationsafhængige:
      1. holiday_calendars            (helligdagskalendere)
      2. hours_calendars              (åbningstidskalendere)
      3. material_calendars           (assignments: hvilken kalender pr. materiale)
      4. delivery_addresses           (leveringsadresser)
      5. capacity_measures            (kapacitetsmål-bibliotek)
      6. container_overrides          (per-container adresse/tid/ID/lås/kapacitetsref)
      7. container_counts             (antal containere pr. materiale/partner)
      8. plads/locations dokumentet:
           - materials, inactive_materials
           - partner_materials
           - material_co2_categories
           - containers_per_material

    Target'ens eksisterende data i alle disse sektioner slettes altid først —
    ingen preudfyldning, ingen "default materialer". Target starter helt tomt
    og modtager KUN en 1:1 kopi af source.

    `sections` (valgfrit) accepterer alle keys ovenfor + "all". Mangler feltet
    eller er tomt → alt kopieres. UI kan bevares som den var.
    """
    source_code = (payload_body.get("source_code") or "").strip()
    target_code = (payload_body.get("target_code") or "").strip()
    sections_in = payload_body.get("sections") or []
    if not source_code or not target_code:
        raise HTTPException(status_code=400, detail="source_code og target_code er påkrævet")
    if source_code == target_code:
        raise HTTPException(status_code=400, detail="Source og target kan ikke være den samme lokation")

    # Normaliser sections. Tom liste eller "all" → alt kopieres.
    ALL_SECTIONS = {
        "holidays", "hours", "material_calendars", "delivery_addresses",
        "capacity_measures", "container_overrides", "container_counts",
        "materials",
    }
    if not sections_in or "all" in sections_in:
        sections = ALL_SECTIONS
    else:
        sections = set(sections_in) & ALL_SECTIONS
        # Legacy: hvis brugeren har valgt "holidays" eller "hours" antag
        # material_calendars også skal kopieres (for at referencerne virker).
        if "holidays" in sections or "hours" in sections:
            sections.add("material_calendars")
        # "materials" implicit hvis kalendere kopieres, ellers går refs på tværs.
        if "material_calendars" in sections or "container_overrides" in sections:
            sections.add("materials")

    src_ctx = await _resolve_plads_for_org(source_code, payload)
    tgt_ctx = await _resolve_plads_for_org(target_code, payload)
    company_id = src_ctx["caller"]["company_id"]
    src_plads = src_ctx["plads"]
    tgt_plads = tgt_ctx["plads"]

    now_iso = datetime.now(timezone.utc).isoformat()
    result = {
        "holidays": 0, "hours": 0, "material_calendars": 0,
        "delivery_addresses": 0, "capacity_measures": 0,
        "container_overrides": 0, "container_counts": 0,
        "materials": 0, "inactive_materials": 0,
        "partner_materials": 0, "material_co2_categories": 0,
    }

    # ID-remap-tabeller: source_id → new_target_id
    holiday_id_map: dict[str, str] = {}
    hours_id_map: dict[str, str] = {}
    capmeasure_id_map: dict[str, str] = {}

    # 1) Holiday calendars
    if "holidays" in sections:
        await _raw_db.holiday_calendars.delete_many(
            {"company_id": company_id, "location_code": target_code}
        )
        src_holidays = await _raw_db.holiday_calendars.find(
            {"company_id": company_id, "location_code": source_code}, {"_id": 0}
        ).to_list(1000)
        for cal in src_holidays:
            new_id = str(uuid.uuid4())
            holiday_id_map[cal["id"]] = new_id
            new_doc = {**cal, "id": new_id, "location_code": target_code,
                       "created_at": now_iso, "updated_at": now_iso}
            await _raw_db.holiday_calendars.insert_one(new_doc)
            result["holidays"] += 1

    # 2) Hours calendars
    if "hours" in sections:
        await _raw_db.hours_calendars.delete_many(
            {"company_id": company_id, "location_code": target_code}
        )
        src_hours = await _raw_db.hours_calendars.find(
            {"company_id": company_id, "location_code": source_code}, {"_id": 0}
        ).to_list(1000)
        for cal in src_hours:
            new_id = str(uuid.uuid4())
            hours_id_map[cal["id"]] = new_id
            new_doc = {**cal, "id": new_id, "location_code": target_code,
                       "created_at": now_iso, "updated_at": now_iso}
            await _raw_db.hours_calendars.insert_one(new_doc)
            result["hours"] += 1

    # 3) Capacity measures (LA-bibliotek) — SKAL kopieres FØR container_overrides
    #    fordi overrides referer til capacity_measure_id.
    if "capacity_measures" in sections:
        await _raw_db.capacity_measures.delete_many(
            {"company_id": company_id, "location_code": target_code}
        )
        src_caps = await _raw_db.capacity_measures.find(
            {"company_id": company_id, "location_code": source_code}, {"_id": 0}
        ).to_list(1000)
        for cap in src_caps:
            new_id = str(uuid.uuid4())
            capmeasure_id_map[cap["id"]] = new_id
            new_doc = {**cap, "id": new_id, "location_code": target_code,
                       "created_at": now_iso, "updated_at": now_iso}
            await _raw_db.capacity_measures.insert_one(new_doc)
            result["capacity_measures"] += 1

    # 4) Material_calendars (assignments)
    if "material_calendars" in sections:
        await _raw_db.material_calendars.delete_many(
            {"company_id": company_id, "location_code": target_code}
        )
        src_assignments = await _raw_db.material_calendars.find(
            {"company_id": company_id, "location_code": source_code}, {"_id": 0}
        ).to_list(2000)
        for a in src_assignments:
            new_doc = {**a, "id": str(uuid.uuid4()), "location_code": target_code,
                       "created_at": now_iso, "updated_at": now_iso}
            # Remap kalender-IDs. Hvis kalender-section IKKE var valgt, bevar
            # ID'et tomt (kunne ellers pege på en source-kalender som target
            # ikke har).
            if "holidays" in sections:
                new_doc["holiday_calendar_id"] = holiday_id_map.get(a.get("holiday_calendar_id", ""), "")
            else:
                new_doc["holiday_calendar_id"] = ""
            if "hours" in sections:
                new_doc["hours_calendar_id"] = hours_id_map.get(a.get("hours_calendar_id", ""), "")
            else:
                new_doc["hours_calendar_id"] = ""
            await _raw_db.material_calendars.insert_one(new_doc)
            result["material_calendars"] += 1

    # 5) Delivery addresses
    if "delivery_addresses" in sections:
        await _raw_db.delivery_addresses.delete_many(
            {"company_id": company_id, "location_code": target_code}
        )
        src_addrs = await _raw_db.delivery_addresses.find(
            {"company_id": company_id, "location_code": source_code}, {"_id": 0}
        ).to_list(1000)
        for a in src_addrs:
            new_doc = {**a, "id": str(uuid.uuid4()), "location_code": target_code,
                       "created_at": now_iso, "updated_at": now_iso}
            await _raw_db.delivery_addresses.insert_one(new_doc)
            result["delivery_addresses"] += 1

    # 6) Container overrides (per-container adresse/tid/ID/lås/kapacitetsref)
    if "container_overrides" in sections:
        await _raw_db.container_overrides.delete_many({"location_code": target_code})
        src_overrides = await _raw_db.container_overrides.find(
            {"location_code": source_code}, {"_id": 0}
        ).to_list(5000)
        for ov in src_overrides:
            new_doc = {**ov, "id": str(uuid.uuid4()), "location_code": target_code,
                       "updated_at": now_iso}
            # Remap capacity_measure_id hvis capacity_measures blev kopieret
            cm_id = (ov.get("capacity_measure_id") or "").strip()
            if cm_id:
                if "capacity_measures" in sections:
                    new_doc["capacity_measure_id"] = capmeasure_id_map.get(cm_id, "")
                else:
                    new_doc["capacity_measure_id"] = ""
            await _raw_db.container_overrides.insert_one(new_doc)
            result["container_overrides"] += 1

    # 7) Container counts
    if "container_counts" in sections:
        await _raw_db.container_counts.delete_many({"location_code": target_code})
        src_counts = await _raw_db.container_counts.find(
            {"location_code": source_code}, {"_id": 0}
        ).to_list(5000)
        for cc in src_counts:
            new_doc = {**cc, "location_code": target_code}
            # container_counts har typisk ikke et 'id' felt (identificeret ved
            # location_code+material+partner_id). Fjern det for at undgå
            # duplikat-key-fejl hvis feltet skulle findes.
            new_doc.pop("id", None)
            await _raw_db.container_counts.insert_one(new_doc)
            result["container_counts"] += 1

    # 8) Plads/locations doc-felter (materialer + relaterede felter)
    if "materials" in sections:
        # Find den korrekte target-collection (plads eller legacy locations)
        tgt_coll, tgt_flt, _ = await _materials_write_target(target_code)
        if tgt_coll is not None:
            src_materials = list(src_plads.get("materials") or [])
            src_inactive = list(src_plads.get("inactive_materials") or [])
            src_partner_mats = dict(src_plads.get("partner_materials") or {})
            src_mat_co2 = dict(src_plads.get("material_co2_categories") or {})
            src_cpm = src_plads.get("containers_per_material")

            update_set = {
                "materials": src_materials,
                "inactive_materials": src_inactive,
                "partner_materials": src_partner_mats,
                "material_co2_categories": src_mat_co2,
            }
            if src_cpm is not None:
                update_set["containers_per_material"] = src_cpm
            await tgt_coll.update_one(tgt_flt, {"$set": update_set})
            result["materials"] = len(src_materials)
            result["inactive_materials"] = len(src_inactive)
            result["partner_materials"] = sum(len(v or []) for v in src_partner_mats.values())
            result["material_co2_categories"] = len(src_mat_co2)

    await _audit("org_schedule_config_copied", payload, {
        "source_code": source_code,
        "target_code": target_code,
        "sections": sorted(sections),
        **result,
    })
    return {"success": True, "sections": sorted(sections), **result}



@org_router.get("/holiday-calendars")
async def org_list_holiday_calendars(location_code: str, payload: dict = Depends(get_current_user_payload)):
    ctx = await _resolve_plads_for_org(location_code, payload)
    items = await _raw_db.holiday_calendars.find(
        {"company_id": ctx["caller"]["company_id"], "location_code": location_code},
        {"_id": 0},
    ).sort([("year", -1), ("name", 1)]).to_list(500)
    # Attach assigned_count per calendar = how many material_calendars
    # rows still reference it. Used by the UI to (a) show a badge,
    # (b) block permanent delete when > 0.
    if items:
        ids = [c["id"] for c in items]
        pipeline = [
            {"$match": {"company_id": ctx["caller"]["company_id"], "location_code": location_code,
                        "holiday_calendar_id": {"$in": ids}}},
            {"$group": {"_id": "$holiday_calendar_id", "count": {"$sum": 1}}},
        ]
        counts = {d["_id"]: d["count"] async for d in _raw_db.material_calendars.aggregate(pipeline)}
        for c in items:
            c["assigned_count"] = counts.get(c["id"], 0)
            c.setdefault("is_active", True)
    return items


@org_router.post("/holiday-calendars")
async def org_create_holiday_calendar(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    code = str(raw.get("location_code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="location_code er påkrævet")
    ctx = await _resolve_plads_for_org(code, payload)
    name = str(raw.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    # Pre-fill days from the customer's assigned holiday_group, unless the
    # caller explicitly provided their own `days` array.
    days: List[Dict[str, Any]] = []
    if "days" in raw and isinstance(raw["days"], list):
        for d in raw["days"]:
            entry = _holiday_day_entry(d)
            if entry:
                days.append(entry)
    else:
        # Lookup company → holiday_group → holidays
        company = await _raw_db.companies.find_one(
            {"id": ctx["caller"]["company_id"]}, {"_id": 0, "holiday_group_id": 1},
        )
        if company and company.get("holiday_group_id"):
            group = await _raw_db.holiday_groups.find_one(
                {"id": company["holiday_group_id"]}, {"_id": 0, "holidays": 1},
            )
            if group:
                for h in group.get("holidays", []):
                    days.append({
                        "name": h["name"],
                        "date": h["date"],
                        "closed": False,
                        "open_from": "",
                        "open_to": "",
                    })
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": ctx["caller"]["company_id"],
        "location_code": code,
        "name": name,
        "year": _coerce_year(raw.get("year")),
        "is_active": True,
        "days": days,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.holiday_calendars.insert_one(doc)
    await _audit("org_holiday_calendar_created", payload,
                 {"id": doc["id"], "location_code": code, "name": name})
    doc.pop("_id", None)
    return doc


@org_router.get("/holiday-groups")
async def org_list_holiday_groups(payload: dict = Depends(get_current_user_payload)):
    """Read-only list of Super Admin helligdagsgrupper that the calling
    Location/Customer Admin can use as a copy-source when creating a new
    holiday calendar. Only ACTIVE groups are returned (deactivated groups
    must not show up as a new-assignment option per spec). No company
    gating — SA groups are platform-wide templates."""
    items = await _raw_db.holiday_groups.find(
        {"$or": [{"active": True}, {"active": {"$exists": False}}]},
        {"_id": 0},
    ).sort([("year", -1), ("name", 1)]).to_list(500)
    return items


@org_router.post("/holiday-calendars/copy-from-group")
async def org_copy_holiday_calendar_from_group(body: dict, payload: dict = Depends(get_current_user_payload)):
    """Create a NEW holiday calendar pre-populated from a Super Admin
    helligdagsgruppe. The group must be one that the caller's company has
    access to: either the company's currently-assigned group, OR any active
    group (LA may choose any active group to base on).
    Body: {location_code, group_id, name?, year?}
    """
    raw = body or {}
    code = str(raw.get("location_code", "")).strip()
    group_id = str(raw.get("group_id", "")).strip()
    if not code or not group_id:
        raise HTTPException(status_code=400, detail="location_code og group_id er påkrævede")
    ctx = await _resolve_plads_for_org(code, payload)
    group = await _raw_db.holiday_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Helligdagsgruppe ikke fundet")
    if not group.get("active", True):
        raise HTTPException(status_code=400, detail="Gruppen er deaktiveret")
    year = _coerce_year(raw.get("year")) or group.get("year")
    name = (str(raw.get("name") or "").strip()
            or (f"{group['name']}" if group.get("year") else f"{group['name']} (kopi)"))
    days = []
    for h in group.get("holidays", []):
        days.append({
            "name": h.get("name", ""),
            "date": h.get("date", ""),
            "closed": False,
            "open_from": "",
            "open_to": "",
        })
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": ctx["caller"]["company_id"],
        "location_code": code,
        "name": name,
        "year": year,
        "is_active": True,
        "days": days,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.holiday_calendars.insert_one(doc)
    doc.pop("_id", None)
    return doc


@org_router.put("/holiday-calendars/{cal_id}")
async def org_update_holiday_calendar(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    raw = body or {}
    if "name" in raw:
        nm = str(raw["name"] or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Navn må ikke være tomt")
        update["name"] = nm
    if "year" in raw:
        update["year"] = _coerce_year(raw["year"])
    if "is_active" in raw:
        update["is_active"] = bool(raw["is_active"])
    if "days" in raw and isinstance(raw["days"], list):
        cleaned = []
        for d in raw["days"]:
            entry = _holiday_day_entry(d)
            if entry:
                cleaned.append(entry)
        update["days"] = cleaned
    await _raw_db.holiday_calendars.update_one({"id": cal_id}, {"$set": update})
    return await _raw_db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})


@org_router.post("/holiday-calendars/{cal_id}/toggle-active")
async def org_toggle_holiday_calendar_active(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    """Activate/deactivate a holiday calendar. When activating, the
    caller may pass `material_id` to ALSO point that material's
    material_calendars row at this calendar (the typical "switch over
    to the new year" action). Inactive calendars are filtered from the
    UI dropdowns when assigning to materials, but existing
    material_calendars mappings + historical orders are NOT affected."""
    cal = await _raw_db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    raw = body or {}
    new_active = bool(raw["active"]) if "active" in raw else (not bool(cal.get("is_active", True)))
    await _raw_db.holiday_calendars.update_one(
        {"id": cal_id},
        {"$set": {"is_active": new_active, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"id": cal_id, "is_active": new_active}


@org_router.post("/holiday-calendars/{cal_id}/copy")
async def org_copy_holiday_calendar(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    """Duplicate a calendar (typically to start next year's calendar)."""
    cal = await _raw_db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    new_name = str((body or {}).get("name", "")).strip() or f"{cal['name']} (kopi)"
    new_doc = {
        "id": str(uuid.uuid4()),
        "company_id": cal["company_id"],
        "location_code": cal["location_code"],
        "name": new_name,
        "days": list(cal.get("days", [])),  # shallow copy is fine — items are plain dicts
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.holiday_calendars.insert_one(new_doc)
    new_doc.pop("_id", None)
    return new_doc


@org_router.delete("/holiday-calendars/{cal_id}")
async def org_delete_holiday_calendar(cal_id: str, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.holiday_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    # Permanent delete is only allowed when NO material_calendars row still
    # references this calendar. UI should prompt to deactivate instead.
    refs = await _raw_db.material_calendars.count_documents(
        {"company_id": cal["company_id"], "location_code": cal["location_code"],
         "holiday_calendar_id": cal_id},
    )
    if refs > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Kan ikke slettes — kalenderen er tilknyttet {refs} materiale(r). Deaktivér kalenderen i stedet.",
        )
    await _raw_db.holiday_calendars.delete_one({"id": cal_id})
    return {"success": True}


@org_router.get("/hours-calendars")
async def org_list_hours_calendars(location_code: str, payload: dict = Depends(get_current_user_payload)):
    ctx = await _resolve_plads_for_org(location_code, payload)
    items = await _raw_db.hours_calendars.find(
        {"company_id": ctx["caller"]["company_id"], "location_code": location_code},
        {"_id": 0},
    ).sort("name", 1).to_list(500)
    if items:
        ids = [c["id"] for c in items]
        pipeline = [
            {"$match": {"company_id": ctx["caller"]["company_id"], "location_code": location_code,
                        "hours_calendar_id": {"$in": ids}}},
            {"$group": {"_id": "$hours_calendar_id", "count": {"$sum": 1}}},
        ]
        counts = {d["_id"]: d["count"] async for d in _raw_db.material_calendars.aggregate(pipeline)}
        for c in items:
            c["assigned_count"] = counts.get(c["id"], 0)
            c.setdefault("is_active", True)
    return items


@org_router.post("/hours-calendars")
async def org_create_hours_calendar(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    code = str(raw.get("location_code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="location_code er påkrævet")
    ctx = await _resolve_plads_for_org(code, payload)
    name = str(raw.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    weekdays_in = raw.get("weekdays") or {}
    weekdays: Dict[str, Any] = {}
    for key in WEEKDAY_KEYS:
        weekdays[key] = _weekday_entry(weekdays_in.get(key))
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": ctx["caller"]["company_id"],
        "location_code": code,
        "name": name,
        "is_active": True,
        "weekdays": weekdays,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.hours_calendars.insert_one(doc)
    doc.pop("_id", None)
    return doc


@org_router.put("/hours-calendars/{cal_id}")
async def org_update_hours_calendar(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.hours_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    raw = body or {}
    if "name" in raw:
        nm = str(raw["name"] or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Navn må ikke være tomt")
        update["name"] = nm
    if "is_active" in raw:
        update["is_active"] = bool(raw["is_active"])
    if "weekdays" in raw and isinstance(raw["weekdays"], dict):
        merged = {}
        for key in WEEKDAY_KEYS:
            merged[key] = _weekday_entry(raw["weekdays"].get(key, cal.get("weekdays", {}).get(key)))
        update["weekdays"] = merged
    await _raw_db.hours_calendars.update_one({"id": cal_id}, {"$set": update})
    return await _raw_db.hours_calendars.find_one({"id": cal_id}, {"_id": 0})


@org_router.post("/hours-calendars/{cal_id}/copy")
async def org_copy_hours_calendar(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.hours_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    new_name = str((body or {}).get("name", "")).strip() or f"{cal['name']} (kopi)"
    new_doc = {
        "id": str(uuid.uuid4()),
        "company_id": cal["company_id"],
        "location_code": cal["location_code"],
        "name": new_name,
        "is_active": True,
        "weekdays": {k: dict(v) for k, v in (cal.get("weekdays") or {}).items()},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.hours_calendars.insert_one(new_doc)
    new_doc.pop("_id", None)
    return new_doc


@org_router.post("/hours-calendars/{cal_id}/toggle-active")
async def org_toggle_hours_calendar_active(cal_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.hours_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    raw = body or {}
    new_active = bool(raw["active"]) if "active" in raw else (not bool(cal.get("is_active", True)))
    await _raw_db.hours_calendars.update_one(
        {"id": cal_id},
        {"$set": {"is_active": new_active, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"id": cal_id, "is_active": new_active}


@org_router.delete("/hours-calendars/{cal_id}")
async def org_delete_hours_calendar(cal_id: str, payload: dict = Depends(get_current_user_payload)):
    cal = await _raw_db.hours_calendars.find_one({"id": cal_id}, {"_id": 0})
    if not cal:
        raise HTTPException(status_code=404, detail="Kalender ikke fundet")
    ctx = await _resolve_plads_for_org(cal["location_code"], payload)
    if cal.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    refs = await _raw_db.material_calendars.count_documents(
        {"company_id": cal["company_id"], "location_code": cal["location_code"],
         "hours_calendar_id": cal_id},
    )
    if refs > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Kan ikke slettes — kalenderen er tilknyttet {refs} materiale(r). Deaktivér kalenderen i stedet.",
        )
    await _raw_db.hours_calendars.delete_one({"id": cal_id})
    return {"success": True}


@org_router.get("/material-calendars")
async def org_list_material_calendars(location_code: str, payload: dict = Depends(get_current_user_payload)):
    ctx = await _resolve_plads_for_org(location_code, payload)
    items = await _raw_db.material_calendars.find(
        {"company_id": ctx["caller"]["company_id"], "location_code": location_code},
        {"_id": 0},
    ).to_list(500)
    return items


@org_router.put("/material-calendars")
async def org_upsert_material_calendar(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    code = str(raw.get("location_code", "")).strip()
    material = str(raw.get("material", "")).strip()
    if not code or not material:
        raise HTTPException(status_code=400, detail="location_code og material er påkrævede")
    ctx = await _resolve_plads_for_org(code, payload)
    # holiday_calendar_id may be null (= "ingen helligdagskalender")
    holiday_id = raw.get("holiday_calendar_id")
    hours_id = raw.get("hours_calendar_id")
    if holiday_id is not None and holiday_id != "":
        h = await _raw_db.holiday_calendars.find_one(
            {"id": holiday_id, "company_id": ctx["caller"]["company_id"], "location_code": code},
            {"_id": 0, "id": 1},
        )
        if not h:
            raise HTTPException(status_code=404, detail="Helligdagskalender ikke fundet")
    else:
        holiday_id = None
    if hours_id is not None and hours_id != "":
        h = await _raw_db.hours_calendars.find_one(
            {"id": hours_id, "company_id": ctx["caller"]["company_id"], "location_code": code},
            {"_id": 0, "id": 1},
        )
        if not h:
            raise HTTPException(status_code=404, detail="Åbningstidskalender ikke fundet")
    else:
        hours_id = None
    flt = {"company_id": ctx["caller"]["company_id"], "location_code": code, "material": material}
    update = {
        "holiday_calendar_id": holiday_id,
        "hours_calendar_id": hours_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.material_calendars.update_one(
        flt,
        {"$set": update, "$setOnInsert": {**flt, "id": str(uuid.uuid4()),
                                            "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return await _raw_db.material_calendars.find_one(flt, {"_id": 0})


# ===================================================================
#                  LEVERINGSADRESSER (Delivery Addresses)
#  Datamodel:
#   - delivery_addresses: Location Admin maintained list of delivery
#     addresses per plads. Each address can be linked to one or more
#     materials. For each (location_code, material) tuple exactly ONE
#     address may be marked "primary" — that's the default used when a
#     container of that material is created and when an order is placed.
#     Non-primary addresses for the same material show up as
#     "alternativ leveringsadresse" in the order flow.
#
#     {id, company_id, location_code, label, street, postcode, city,
#      materials: [str], primary_for: [str],
#      holiday_calendar_id: Optional[str], hours_calendar_id: Optional[str],
#      created_at, updated_at}
#
#     Calendars on delivery_addresses are OPTIONAL — when null we fall
#     back to material_calendars[(location_code, material)]. This lets an
#     "alternativ" address override the schedule if needed.
# ===================================================================

WEEKDAY_KEY_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def _coerce_year(v) -> Optional[int]:
    """Best-effort int coercion for the `year` field used on holiday
    groups + LA calendars. Returns None for blank/invalid input rather
    than raising — keeps the column optional for legacy docs."""
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _da_normalize_address_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate & normalize delivery-address payload (shared by POST/PUT)."""
    out: Dict[str, Any] = {}
    if "label" in raw:
        lbl = str(raw.get("label") or "").strip()
        if not lbl:
            raise HTTPException(status_code=400, detail="Navn (label) er påkrævet")
        out["label"] = lbl
    if "street" in raw:
        out["street"] = str(raw.get("street") or "").strip()
    if "postcode" in raw:
        out["postcode"] = str(raw.get("postcode") or "").strip()
    if "city" in raw:
        out["city"] = str(raw.get("city") or "").strip()
    # iteration 18: materials/primary_for fields are deprecated. The
    # delivery-address library is now a pure {label, street, postcode, city}
    # bibliothek — links to calendars happen on the calendar entries instead.
    # We still ACCEPT the legacy keys (silently ignored) to avoid breaking
    # any in-flight UI deployments.
    return out


async def _da_unset_primary_for(company_id: str, location_code: str, materials: List[str], except_id: Optional[str] = None):
    """Remove the supplied material(s) from `primary_for` on every OTHER
    delivery_address at the same plads. Keeps the "one primary per material"
    invariant."""
    if not materials:
        return
    flt: Dict[str, Any] = {
        "company_id": company_id,
        "location_code": location_code,
        "primary_for": {"$in": materials},
    }
    if except_id:
        flt["id"] = {"$ne": except_id}
    await _raw_db.delivery_addresses.update_many(
        flt, {"$pull": {"primary_for": {"$in": materials}}}
    )


@org_router.get("/delivery-addresses")
async def org_list_delivery_addresses(location_code: str, payload: dict = Depends(get_current_user_payload)):
    ctx = await _resolve_plads_for_org(location_code, payload)
    items = await _raw_db.delivery_addresses.find(
        {"company_id": ctx["caller"]["company_id"], "location_code": location_code},
        {"_id": 0},
    ).sort("label", 1).to_list(500)
    return items


@org_router.post("/delivery-addresses")
async def org_create_delivery_address(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    code = str(raw.get("location_code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="location_code er påkrævet")
    ctx = await _resolve_plads_for_org(code, payload)
    norm = _da_normalize_address_payload(raw)
    if not norm.get("label"):
        raise HTTPException(status_code=400, detail="Navn (label) er påkrævet")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": ctx["caller"]["company_id"],
        "location_code": code,
        "label": norm["label"],
        "street": norm.get("street", ""),
        "postcode": norm.get("postcode", ""),
        "city": norm.get("city", ""),
        "created_at": now,
        "updated_at": now,
    }
    await _raw_db.delivery_addresses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@org_router.put("/delivery-addresses/{address_id}")
async def org_update_delivery_address(address_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.delivery_addresses.find_one({"id": address_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    ctx = await _resolve_plads_for_org(existing["location_code"], payload)
    if existing.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    norm = _da_normalize_address_payload(body or {})
    norm["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _raw_db.delivery_addresses.update_one({"id": address_id}, {"$set": norm})
    return await _raw_db.delivery_addresses.find_one({"id": address_id}, {"_id": 0})


@org_router.delete("/delivery-addresses/{address_id}")
async def org_delete_delivery_address(address_id: str, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.delivery_addresses.find_one({"id": address_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Adresse ikke fundet")
    ctx = await _resolve_plads_for_org(existing["location_code"], payload)
    if existing.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    # Block delete when this address is still referenced by ANY calendar entry
    # (holiday or hours). We check the bibliotek's primary purpose: links from
    # calendars. UI surfaces the count + offers an inline jump-to-reference.
    refs_holiday = await _raw_db.holiday_calendars.count_documents(
        {"company_id": existing["company_id"],
         "location_code": existing["location_code"],
         "days.delivery_address_id": address_id},
    )
    pipeline_w = [
        {"$match": {"company_id": existing["company_id"],
                    "location_code": existing["location_code"]}},
        {"$project": {"ids": [
            "$weekdays.mon.delivery_address_id", "$weekdays.tue.delivery_address_id",
            "$weekdays.wed.delivery_address_id", "$weekdays.thu.delivery_address_id",
            "$weekdays.fri.delivery_address_id", "$weekdays.sat.delivery_address_id",
            "$weekdays.sun.delivery_address_id",
        ]}},
        {"$match": {"ids": address_id}},
        {"$count": "n"},
    ]
    cur = await _raw_db.hours_calendars.aggregate(pipeline_w).to_list(1)
    refs_hours = (cur[0]["n"] if cur else 0)
    total = refs_holiday + refs_hours
    if total > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Kan ikke slettes — adressen er brugt i "
                f"{refs_holiday} helligdagskalender-rækker og {refs_hours} "
                "åbningstidskalender-dage. Fjern referencerne først."
            ),
        )
    await _raw_db.delivery_addresses.delete_one({"id": address_id})
    return {"success": True}


def _da_format_address_line(a: Dict[str, Any]) -> str:
    """Render a delivery_address doc as a single human-readable line."""
    if not a:
        return ""
    parts = [a.get("street") or "", " ".join([p for p in [a.get("postcode") or "", a.get("city") or ""] if p]).strip()]
    return ", ".join([p for p in parts if p])


async def _da_resolve_schedule_for_address(
    company_id: str, location_code: str, material: str, date_str: str,
    address: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve open_from / open_to / is_closed / resolved_delivery_address_id
    for a given (material, date).

    Priority (iteration 18):
      1. Holiday calendar: any entry matching `date_str` wins. If the helligdag
         entry has its own delivery_address_id we use it; otherwise we
         fall back to the weekday entry's delivery_address_id for that
         weekday — this is the new rule.
      2. Weekday calendar: entry matching the weekday of `date_str`
         (delivery_address_id is REQUIRED on weekday entries).
      3. Fallback when nothing is configured → not closed, blank hours,
         no resolved address.
    """
    mc = await _raw_db.material_calendars.find_one(
        {"company_id": company_id, "location_code": location_code, "material": material},
        {"_id": 0},
    ) or {}
    h_id = mc.get("holiday_calendar_id")
    w_id = mc.get("hours_calendar_id")
    result: Dict[str, Any] = {
        "is_holiday": False,
        "holiday_name": None,
        "is_closed": False,
        "open_from": "",
        "open_to": "",
        "resolved_delivery_address_id": None,
        "source": None,
    }

    # 1. Holiday lookup
    holiday_entry: Optional[Dict[str, Any]] = None
    if h_id:
        h_cal = await _raw_db.holiday_calendars.find_one({"id": h_id}, {"_id": 0})
        if h_cal:
            for d in (h_cal.get("days") or []):
                if str(d.get("date")) == date_str:
                    holiday_entry = d
                    break

    # 2. Weekday lookup (always done — needed for fallback even on holidays)
    weekday_entry: Optional[Dict[str, Any]] = None
    if w_id:
        w_cal = await _raw_db.hours_calendars.find_one({"id": w_id}, {"_id": 0})
        if w_cal:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                wd_key = WEEKDAY_KEY_MAP.get(dt.weekday())
            except ValueError:
                wd_key = None
            if wd_key:
                weekday_entry = (w_cal.get("weekdays") or {}).get(wd_key) or {}

    if holiday_entry:
        # Holiday takes precedence for hours/closed; delivery_address_id
        # falls back to weekday when helligdag's own field is empty.
        result.update({
            "is_holiday": True,
            "holiday_name": holiday_entry.get("name"),
            "is_closed": bool(holiday_entry.get("closed")),
            "open_from": holiday_entry.get("open_from") or "",
            "open_to": holiday_entry.get("open_to") or "",
            "resolved_delivery_address_id": (
                holiday_entry.get("delivery_address_id")
                or (weekday_entry.get("delivery_address_id") if weekday_entry else None)
            ),
            "source": "holiday",
        })
    elif weekday_entry:
        result.update({
            "is_closed": bool(weekday_entry.get("closed")),
            "open_from": weekday_entry.get("open_from") or "",
            "open_to": weekday_entry.get("open_to") or "",
            "resolved_delivery_address_id": weekday_entry.get("delivery_address_id"),
            "source": "weekday",
        })
    return result


@app.get("/api/delivery-addresses/resolve")
async def resolve_delivery_address(
    location_code: str, material: str, date: str,
    address_id: Optional[str] = None,
):
    """PUBLIC endpoint — used by the order flow (both kiosk QR users and
    authenticated order users). Returns:

      - primary: the primary delivery address for (location_code, material)
        (or null if none configured)
      - alternatives: the other addresses linked to the same material
      - selected: the resolved schedule for `address_id` if supplied, else
        the schedule for `primary`
      - is_closed / is_holiday / holiday_name / open_from / open_to: the
        effective schedule for the selected address on the supplied `date`

    Date is YYYY-MM-DD. The location_code's company_id is used as the
    multi-tenant scope. No auth required (QR kiosk flow needs it)."""
    code = (location_code or "").strip()
    mat = (material or "").strip()
    if not code or not mat or not date:
        raise HTTPException(status_code=400, detail="location_code, material og date er påkrævede")
    plads = await _raw_db.plads.find_one({"location_code": code}, {"_id": 0, "company_id": 1})
    if not plads:
        # Fall back to lookup by name suffix etc — but we strictly need company_id, so 404 if missing.
        raise HTTPException(status_code=404, detail="Plads ikke fundet")
    company_id = plads.get("company_id")
    addresses = await _raw_db.delivery_addresses.find(
        {"company_id": company_id, "location_code": code},
        {"_id": 0},
    ).sort("label", 1).to_list(500)
    # iteration 18: delivery addresses are a pure bibliotek — no per-material
    # primary/alternatives anymore. The resolved address comes from the
    # holiday/weekday calendar's own delivery_address_id reference.
    primary = None
    alternatives = addresses
    selected = next((a for a in addresses if a.get("id") == address_id), None) if address_id else None
    schedule = await _da_resolve_schedule_for_address(
        company_id=company_id, location_code=code, material=mat,
        date_str=date, address=selected,
    )
    # Hydrate resolved_delivery_address (the address doc the order page should
    # auto-populate) from the holiday→weekday fallback chain.
    resolved_id = schedule.get("resolved_delivery_address_id")
    resolved_address = None
    if resolved_id:
        # Look in the addresses already loaded; otherwise hit DB
        resolved_address = next((a for a in addresses if a.get("id") == resolved_id), None)
        if not resolved_address:
            resolved_address = await _raw_db.delivery_addresses.find_one(
                {"id": resolved_id}, {"_id": 0},
            )
    return {
        "location_code": code,
        "material": mat,
        "date": date,
        "primary": primary,
        "alternatives": alternatives,
        "selected": selected,
        "resolved_delivery_address": resolved_address,
        **schedule,
    }


# ===================================================================
#                  CAPACITY MEASURES (Kapacitetsmål-bibliotek)
#  Per (company_id, location_code) collection of {label, volume_m3}.
#  Used as a dropdown when the LA creates/edits containers — and the
#  composite display string ("{label} – {volume_m3} m³") follows the
#  container everywhere it's referenced in the order flow.
# ===================================================================

def _cap_normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "label" in raw:
        lbl = str(raw.get("label") or "").strip()
        if not lbl:
            raise HTTPException(status_code=400, detail="Label er påkrævet")
        out["label"] = lbl
    if "volume_m3" in raw:
        v = raw.get("volume_m3")
        if v is None or v == "":
            out["volume_m3"] = None
        else:
            try:
                out["volume_m3"] = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="volume_m3 skal være et tal")
    return out


@org_router.get("/capacity-measures")
async def org_list_capacity_measures(location_code: str, payload: dict = Depends(get_current_user_payload)):
    ctx = await _resolve_plads_for_org(location_code, payload)
    items = await _raw_db.capacity_measures.find(
        {"company_id": ctx["caller"]["company_id"], "location_code": location_code},
        {"_id": 0},
    ).sort("volume_m3", 1).to_list(500)
    return items


@org_router.post("/capacity-measures")
async def org_create_capacity_measure(body: dict, payload: dict = Depends(get_current_user_payload)):
    raw = body or {}
    code = str(raw.get("location_code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="location_code er påkrævet")
    ctx = await _resolve_plads_for_org(code, payload)
    norm = _cap_normalize(raw)
    if not norm.get("label"):
        raise HTTPException(status_code=400, detail="Label er påkrævet")
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": ctx["caller"]["company_id"],
        "location_code": code,
        "label": norm["label"],
        "volume_m3": norm.get("volume_m3"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.capacity_measures.insert_one(doc)
    doc.pop("_id", None)
    return doc


@org_router.put("/capacity-measures/{cm_id}")
async def org_update_capacity_measure(cm_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.capacity_measures.find_one({"id": cm_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kapacitetsmål ikke fundet")
    ctx = await _resolve_plads_for_org(existing["location_code"], payload)
    if existing.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    norm = _cap_normalize(body or {})
    norm["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _raw_db.capacity_measures.update_one({"id": cm_id}, {"$set": norm})
    return await _raw_db.capacity_measures.find_one({"id": cm_id}, {"_id": 0})


@org_router.delete("/capacity-measures/{cm_id}")
async def org_delete_capacity_measure(cm_id: str, payload: dict = Depends(get_current_user_payload)):
    existing = await _raw_db.capacity_measures.find_one({"id": cm_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kapacitetsmål ikke fundet")
    ctx = await _resolve_plads_for_org(existing["location_code"], payload)
    if existing.get("company_id") != ctx["caller"]["company_id"]:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    # Block delete when containers still reference it
    refs = await _raw_db.container_overrides.count_documents({"capacity_measure_id": cm_id})
    if refs > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Kan ikke slettes — {refs} container(e) bruger dette kapacitetsmål.",
        )
    await _raw_db.capacity_measures.delete_one({"id": cm_id})
    return {"success": True}


# ===================================================================
#                  REPORTS / STATISTICS (Location Admin)
#  Aggregate orders by various dimensions for the new Rapporter tab.
#  Returns pre-aggregated JSON so the frontend just renders charts.
# ===================================================================

@org_router.get("/reports/orders")
async def org_report_orders(
    location_code: str,
    period: str = "month",  # day | week | month | 3months | 6months | year | custom
    start: Optional[str] = None,  # YYYY-MM-DD (custom)
    end: Optional[str] = None,    # YYYY-MM-DD (custom)
    payload: dict = Depends(get_current_user_payload),
):
    """Return an aggregated report covering: total orders, by-material,
    by-employee, by-time-bucket (peak hours / days), pending count,
    workshop count, by-hour for a day, etc. The frontend then renders the
    charts. Period semantics:
      day      → today (1 calendar day, hour granularity)
      week     → last 7 days (24-hour fold)
      month    → current calendar month (day granularity)
      3months  → last 3 calendar months (week granularity)
      6months  → last 6 calendar months (week granularity)
      year     → current calendar year (month granularity)
      custom   → explicit start/end window with auto-picked granularity
    """
    ctx = await _resolve_plads_for_org(location_code, payload)
    today = datetime.now(timezone.utc).date()
    if period == "day":
        s, e = today, today
        granularity = "hour"
    elif period == "week":
        s, e = today - timedelta(days=6), today
        granularity = "hour"  # 24h fold
    elif period == "month":
        s = today.replace(day=1)
        # last day of current month
        next_month = (s + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1)
        granularity = "day"
    elif period == "3months":
        s = (today.replace(day=1) - timedelta(days=62)).replace(day=1)
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1)
        granularity = "week"
    elif period == "6months":
        s = (today.replace(day=1) - timedelta(days=160)).replace(day=1)
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1)
        granularity = "week"
    elif period == "year":
        s = today.replace(month=1, day=1)
        e = today.replace(month=12, day=31)
        granularity = "month"
    elif period == "custom":
        if not start or not end:
            raise HTTPException(status_code=400, detail="custom kræver start og end")
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        # Pick granularity based on span
        span = (e - s).days
        granularity = "hour" if span <= 1 else ("day" if span <= 90 else "week" if span <= 365 else "month")
    else:
        raise HTTPException(status_code=400, detail="Ukendt period")

    # All orders within range. We filter on order_date (kundens afhentnings-
    # dato) since that's the LA's operational lens. Soft-deleted orders are
    # excluded.
    cur = _raw_db.container_orders.find({
        "company_id": ctx["caller"]["company_id"],
        "location_code": location_code,
        "order_date": {"$gte": s.isoformat(), "$lte": e.isoformat()},
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    }, {"_id": 0})
    orders = await cur.to_list(20000)

    # ----- Aggregations -----
    by_material: Dict[str, int] = {}
    by_employee: Dict[str, int] = {}
    by_material_weight: Dict[str, float] = {}
    pattern: Dict[str, int] = {}  # bucket-key → count
    workshop_count = 0
    pending_count = 0
    urgent_count = 0
    # Fase 9 refactor (2026-06-18): CO2-rapportering også for Location Admin
    by_co2_type: Dict[str, dict] = {}    # name -> {count, weight_kg, co2_kg, factor}
    co2_over_time: Dict[str, float] = {} # date -> total co2_kg
    for o in orders:
        mat = o.get("material") or "(ukendt)"
        by_material[mat] = by_material.get(mat, 0) + 1
        emp = o.get("created_by_name") or o.get("created_by_email") or "(ukendt)"
        by_employee[emp] = by_employee.get(emp, 0) + 1
        # Brugerkrav 2026-06-15 (runde 13): "Værksteder"-KPI tæller KUN
        # `vaerksted` (til værksted) — `afhent_vaerksted` (afhent fra
        # værksted) er den returnerende del af samme besøg og må ikke
        # tælle dobbelt.
        if o.get("tour_type") == "vaerksted":
            workshop_count += 1
        if (o.get("status_label") or "afventer") == "afventer":
            pending_count += 1
        # Brugerkrav 2026-06-15 (runde 12): Haste bestillinger (priority='haster')
        # erstatter den tidligere lidet meningsfulde "Afventer (i alt)" KPI.
        if str(o.get("priority") or "").lower() == "haster":
            urgent_count += 1
        try:
            w = float(o.get("weight") or 0)
        except (TypeError, ValueError):
            w = 0.0
        by_material_weight[mat] = by_material_weight.get(mat, 0) + w
        # CO2 aggregation (Fase 9 refactor 2026-06-18)
        co2_name = (o.get("co2_type_name") or "").strip() or "(ingen CO2-kategori)"
        try:
            kg = float(o.get("weight_kg") or 0)
        except (TypeError, ValueError):
            kg = 0.0
        try:
            co2 = float(o.get("co2_kg") or 0)
        except (TypeError, ValueError):
            co2 = 0.0
        if co2_name not in by_co2_type:
            by_co2_type[co2_name] = {"count": 0, "weight_kg": 0.0, "co2_kg": 0.0,
                                     "factor": float(o.get("co2_factor") or 0)}
        by_co2_type[co2_name]["count"] += 1
        by_co2_type[co2_name]["weight_kg"] += kg
        by_co2_type[co2_name]["co2_kg"] += co2
        d_key = (o.get("order_date") or "")[:10]
        if d_key:
            co2_over_time[d_key] = co2_over_time.get(d_key, 0) + co2
        # Pattern bucket
        # Brugerkrav 2026-06-15 (runde 14): "Bestillinger pr. time"-diagrammet
        # skal afspejle FAKTISK oprettelsestidspunkt (`created_at`), ikke det
        # tidligere brugte `open_from` (leveringsvindue — typisk tomt → alt
        # endte i 00:00-bucket).
        # Strategi: floor-to-hour i lokal dansk tid (samme som Google
        # Analytics, Mixpanel, Tableau, Power BI). Sikrer max 24 buckets
        # uanset datavolumen. Konvertering fra UTC til Europe/Copenhagen
        # håndterer både CET/CEST (sommertid).
        d = o.get("order_date") or ""
        if granularity == "hour":
            ts = o.get("created_at") or ""
            hr = "00"
            if ts:
                try:
                    iso = ts.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt_local = dt.astimezone(DK_TZ)
                    hr = f"{dt_local.hour:02d}"
                except (ValueError, TypeError):
                    import re as _re
                    m = _re.search(r"T(\d{2}):", ts)
                    if m:
                        hr = m.group(1)
            key = f"{hr}:00"
        elif granularity == "day":
            key = d
        elif granularity == "week":
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                iso = dt.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
            except ValueError:
                key = d
        elif granularity == "month":
            key = d[:7]
        else:
            key = d
        pattern[key] = pattern.get(key, 0) + 1

    # All-time pending count (for the "Afventende bestillinger" panel)
    all_pending = await _raw_db.container_orders.count_documents({
        "company_id": ctx["caller"]["company_id"],
        "location_code": location_code,
        "status_label": "afventer",
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    })

    # Pending orders (most recent 50) for the side-panel
    pending_orders = await _raw_db.container_orders.find({
        "company_id": ctx["caller"]["company_id"],
        "location_code": location_code,
        "status_label": "afventer",
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    }, {"_id": 0}).sort([("order_date", -1)]).limit(50).to_list(50)

    # Fase 9 refactor (2026-06-18): CO2 aggregater til Location Admin rapport
    by_co2_type_list = [
        {"name": name, "count": d["count"],
         "weight_kg": round(d["weight_kg"], 1),
         "co2_kg": round(d["co2_kg"], 3),
         "factor": d.get("factor", 0)}
        for name, d in sorted(by_co2_type.items(), key=lambda x: -x[1]["co2_kg"])
    ]
    co2_over_time_list = [
        {"date": d, "co2_kg": round(v, 3)}
        for d, v in sorted(co2_over_time.items())
    ]
    total_co2_kg = round(sum(co2_over_time.values()), 3)
    total_weight_kg = round(sum(by_co2_type[n]["weight_kg"] for n in by_co2_type), 1)

    return {
        "period": period, "start": s.isoformat(), "end": e.isoformat(),
        "granularity": granularity,
        "total_orders": len(orders),
        "by_material": [{"name": k, "count": v, "weight": by_material_weight.get(k, 0)}
                        for k, v in sorted(by_material.items(), key=lambda x: -x[1])],
        "by_employee": [{"name": k, "count": v}
                        for k, v in sorted(by_employee.items(), key=lambda x: -x[1])],
        "pattern": [{"bucket": k, "count": v}
                    for k, v in sorted(pattern.items())],
        "workshop_count": workshop_count,
        "pending_in_period": pending_count,
        "pending_all_time": all_pending,
        "urgent_count": urgent_count,
        "pending_orders": pending_orders,
        # Fase 9 refactor (2026-06-18): CO2-rapport — også synlig for Location Admin
        "by_co2_type": by_co2_type_list,
        "co2_over_time": co2_over_time_list,
        "total_co2_kg": total_co2_kg,
        "total_weight_kg": total_weight_kg,
    }


# ===================================================================
#   Customer Admin Reports — aggregeret på TVÆRS af alle lokationer
#   med per-lokation breakdown (brugerkrav 2026-06-15).
#   Reuses period-logikken fra /reports/orders ovenfor.
# ===================================================================

def _resolve_period_window(period: str, start: Optional[str], end: Optional[str]) -> Tuple[datetime, datetime, str]:
    """Returnerer (start_date, end_date, granularity) — fælles helper for
    både LA per-lokation og CA cross-lokation rapporter."""
    today = datetime.now(timezone.utc).date()
    if period == "day":
        s, e = today, today; granularity = "hour"
    elif period == "week":
        s, e = today - timedelta(days=6), today; granularity = "hour"
    elif period == "month":
        s = today.replace(day=1)
        next_month = (s + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1); granularity = "day"
    elif period == "3months":
        s = (today.replace(day=1) - timedelta(days=62)).replace(day=1)
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1); granularity = "week"
    elif period == "6months":
        s = (today.replace(day=1) - timedelta(days=160)).replace(day=1)
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        e = next_month - timedelta(days=1); granularity = "week"
    elif period == "year":
        s = today.replace(month=1, day=1); e = today.replace(month=12, day=31); granularity = "month"
    elif period == "custom":
        if not start or not end:
            raise HTTPException(status_code=400, detail="custom kræver start og end")
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        span = (e - s).days
        granularity = "hour" if span <= 1 else ("day" if span <= 90 else "week" if span <= 365 else "month")
    else:
        raise HTTPException(status_code=400, detail="Ukendt period")
    return s, e, granularity


@org_router.get("/reports/orders-multi")
async def org_report_orders_multi(
    period: str = "month",
    start: Optional[str] = None,
    end: Optional[str] = None,
    location_codes: Optional[str] = None,  # CSV; tom/None = ALLE lokationer i kundens selskab
    payload: dict = Depends(require_role("customer_admin")),
):
    """Customer Admin Reports: aggregeret på TVÆRS af alle (eller en delmængde
    af) lokationer i kundens selskab. Returnerer:
      * Samme top-level felter som /reports/orders (total_orders, by_material,
        by_employee, pattern, workshop_count, pending_*)
      * Et nyt felt `by_location` med per-lokation breakdown.
    Filteret er KUN tilladt for customer_admin pr. requirement.
    """
    caller = await _org_caller(payload)
    s, e, granularity = _resolve_period_window(period, start, end)

    # Resolve hvilke lokationer der må slås op
    plads_cursor = _raw_db.plads.find(
        {"company_id": caller["company_id"]},
        {"_id": 0, "location_code": 1, "name": 1},
    )
    pladser = await plads_cursor.to_list(2000)
    code_to_name = {p["location_code"]: p.get("name") or p["location_code"] for p in pladser if p.get("location_code")}

    if location_codes:
        wanted = [c.strip() for c in location_codes.split(",") if c.strip()]
        # Strict filter — sikrer kunden ikke kan tilgå pladser udenfor egen org
        wanted = [c for c in wanted if c in code_to_name]
    else:
        wanted = list(code_to_name.keys())
    if not wanted:
        return {
            "period": period, "start": s.isoformat(), "end": e.isoformat(),
            "granularity": granularity, "total_orders": 0,
            "by_material": [], "by_employee": [], "pattern": [],
            "by_location": [], "workshop_count": 0,
            "pending_in_period": 0, "pending_all_time": 0,
            "urgent_count": 0,
            "pending_orders": [], "location_count": 0,
        }

    cur = _raw_db.container_orders.find({
        "company_id": caller["company_id"],
        "location_code": {"$in": wanted},
        "order_date": {"$gte": s.isoformat(), "$lte": e.isoformat()},
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    }, {"_id": 0})
    orders = await cur.to_list(50000)

    by_material: Dict[str, int] = {}
    by_employee: Dict[str, int] = {}
    by_material_weight: Dict[str, float] = {}
    by_location_count: Dict[str, int] = {}
    by_location_pending: Dict[str, int] = {}
    by_location_weight: Dict[str, float] = {}
    # Fase 9 (2026-06-17): CO2-rapportering
    by_co2_type: Dict[str, dict] = {}    # name -> {count, weight_kg, co2_kg}
    by_location_co2: Dict[str, float] = {}
    co2_over_time: Dict[str, float] = {} # date -> total co2_kg
    pattern: Dict[str, int] = {}
    workshop_count = 0
    pending_count = 0
    urgent_count = 0
    for o in orders:
        mat = o.get("material") or "(ukendt)"
        by_material[mat] = by_material.get(mat, 0) + 1
        emp = o.get("created_by_name") or o.get("created_by_email") or "(ukendt)"
        by_employee[emp] = by_employee.get(emp, 0) + 1
        loc = o.get("location_code") or "(ukendt)"
        by_location_count[loc] = by_location_count.get(loc, 0) + 1
        if (o.get("status_label") or "afventer") == "afventer":
            pending_count += 1
            by_location_pending[loc] = by_location_pending.get(loc, 0) + 1
        if o.get("tour_type") == "vaerksted":
            workshop_count += 1
        if str(o.get("priority") or "").lower() == "haster":
            urgent_count += 1
        try:
            w = float(o.get("weight") or 0)
        except (TypeError, ValueError):
            w = 0.0
        by_material_weight[mat] = by_material_weight.get(mat, 0) + w
        by_location_weight[loc] = by_location_weight.get(loc, 0) + w

        # CO2 aggregation
        co2_name = (o.get("co2_type_name") or "").strip() or "(ingen CO2-type)"
        try:
            kg = float(o.get("weight_kg") or 0)
        except (TypeError, ValueError):
            kg = 0.0
        try:
            co2 = float(o.get("co2_kg") or 0)
        except (TypeError, ValueError):
            co2 = 0.0
        if co2_name not in by_co2_type:
            by_co2_type[co2_name] = {"count": 0, "weight_kg": 0.0, "co2_kg": 0.0,
                                     "factor": float(o.get("co2_factor") or 0)}
        by_co2_type[co2_name]["count"] += 1
        by_co2_type[co2_name]["weight_kg"] += kg
        by_co2_type[co2_name]["co2_kg"] += co2
        by_location_co2[loc] = by_location_co2.get(loc, 0) + co2
        date_key = (o.get("order_date") or "")[:10]
        if date_key:
            co2_over_time[date_key] = co2_over_time.get(date_key, 0) + co2
        d = o.get("order_date") or ""
        if granularity == "hour":
            # Floor-to-hour fra created_at i dansk tid (industri-standard)
            ts = o.get("created_at") or ""
            hr = "00"
            if ts:
                try:
                    iso = ts.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt_local = dt.astimezone(DK_TZ)
                    hr = f"{dt_local.hour:02d}"
                except (ValueError, TypeError):
                    import re as _re
                    m = _re.search(r"T(\d{2}):", ts)
                    if m:
                        hr = m.group(1)
            key = f"{hr}:00"
        elif granularity == "day":
            key = d
        elif granularity == "week":
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                iso = dt.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
            except ValueError:
                key = d
        elif granularity == "month":
            key = d[:7]
        else:
            key = d
        pattern[key] = pattern.get(key, 0) + 1

    # All-time pending count på tværs af de valgte lokationer
    all_pending = await _raw_db.container_orders.count_documents({
        "company_id": caller["company_id"],
        "location_code": {"$in": wanted},
        "status_label": "afventer",
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    })

    # Pending-listen begrænses til de 100 mest aktuelle på tværs.
    pending_orders = await _raw_db.container_orders.find({
        "company_id": caller["company_id"],
        "location_code": {"$in": wanted},
        "status_label": "afventer",
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
    }, {"_id": 0}).sort([("order_date", -1)]).limit(100).to_list(100)

    by_location = [
        {
            "location_code": code,
            "location_name": code_to_name.get(code, code),
            "count": cnt,
            "pending": by_location_pending.get(code, 0),
            "weight": round(by_location_weight.get(code, 0.0), 1),
            "co2_kg": round(by_location_co2.get(code, 0.0), 3),
        }
        for code, cnt in sorted(by_location_count.items(), key=lambda x: -x[1])
    ]

    # Fase 9: CO2 aggregates
    by_co2_type_list = [
        {"name": name, "count": d["count"],
         "weight_kg": round(d["weight_kg"], 1),
         "co2_kg": round(d["co2_kg"], 3),
         "factor": d.get("factor", 0)}
        for name, d in sorted(by_co2_type.items(), key=lambda x: -x[1]["co2_kg"])
    ]
    co2_over_time_list = [
        {"date": d, "co2_kg": round(v, 3)}
        for d, v in sorted(co2_over_time.items())
    ]
    total_co2_kg = round(sum(co2_over_time.values()), 3)
    total_weight_kg = round(sum(by_co2_type[n]["weight_kg"] for n in by_co2_type), 1)

    return {
        "period": period, "start": s.isoformat(), "end": e.isoformat(),
        "granularity": granularity,
        "total_orders": len(orders),
        "location_count": len(wanted),
        "by_material": [{"name": k, "count": v, "weight": round(by_material_weight.get(k, 0), 1)}
                        for k, v in sorted(by_material.items(), key=lambda x: -x[1])],
        "by_employee": [{"name": k, "count": v}
                        for k, v in sorted(by_employee.items(), key=lambda x: -x[1])],
        "by_location": by_location,
        "pattern": [{"bucket": k, "count": v}
                    for k, v in sorted(pattern.items())],
        "workshop_count": workshop_count,
        "pending_in_period": pending_count,
        "pending_all_time": all_pending,
        "urgent_count": urgent_count,
        "pending_orders": pending_orders,
        # Fase 9 (2026-06-17): CO2-rapport
        "by_co2_type": by_co2_type_list,
        "co2_over_time": co2_over_time_list,
        "total_co2_kg": total_co2_kg,
        "total_weight_kg": total_weight_kg,
    }


# ===================================================================
#  Fase 18.5 (2026-02-28) — TUR-ARKIV til Location Admin
#  Returnerer turhistorik for en eller flere lokationer som
#  Location Admin har adgang til (assigned_plads_ids). Hver tur
#  beriges med kundens ContainerOrder (for order_date), driverens
#  navn, tur start/slut, container_weights og linkede receipts
#  (for løs afhentning breakdown).
#  Tilladt for: location_admin, customer_admin, super_admin.
# ===================================================================
@org_router.get("/tour-archive")
async def org_tour_archive(
    location_codes: Optional[str] = None,    # CSV; tom = alle adgangsberettigede
    date_from: Optional[str] = None,         # YYYY-MM-DD
    date_to: Optional[str] = None,           # YYYY-MM-DD
    limit: int = 1000,
    payload: dict = Depends(require_role("location_admin", "customer_admin", "logistics_admin", "super_admin")),
):
    caller = await _org_caller(payload)
    role = caller.get("role")

    # Resolve hvilke location_codes brugeren MÅ se.
    if role == "logistics_admin":
        # 2026-10-16: Logistik admin ser ture på de pladser firmaet betjener
        # (på tværs af kunder). Kun egne ture — se partner-filter nederst.
        plads_list = await _raw_db.plads.find(
            {"assigned_logistics_company_ids": caller.get("company_id")},
            {"_id": 0, "location_code": 1},
        ).to_list(2000)
        allowed = {p["location_code"] for p in plads_list if p.get("location_code")}
        if location_codes:
            req_codes = [c.strip() for c in location_codes.split(",") if c.strip()]
            wanted = [c for c in req_codes if c in allowed]
        else:
            wanted = sorted(allowed)
    elif role == "super_admin":
        # Super_admin må se alt — men skal angive specifikke codes.
        wanted = [c.strip() for c in (location_codes or "").split(",") if c.strip()]
        if not wanted:
            raise HTTPException(status_code=400, detail="location_codes er påkrævet for super_admin")
    elif role == "customer_admin":
        # Customer_admin må se alle lokationer i eget selskab.
        plads_list = await _raw_db.plads.find(
            {"company_id": caller.get("company_id")},
            {"_id": 0, "location_code": 1},
        ).to_list(2000)
        allowed = {p["location_code"] for p in plads_list if p.get("location_code")}
        if location_codes:
            req_codes = [c.strip() for c in location_codes.split(",") if c.strip()]
            wanted = [c for c in req_codes if c in allowed]
        else:
            wanted = sorted(allowed)
    else:  # location_admin
        managed = set(caller.get("assigned_plads_ids") or [])
        if caller.get("location_code"):
            managed.add(caller["location_code"])
        if location_codes:
            req_codes = [c.strip() for c in location_codes.split(",") if c.strip()]
            wanted = [c for c in req_codes if c in managed]
        else:
            wanted = sorted(managed)

    if not wanted:
        return {"tours": [], "total": 0, "location_codes": []}

    # Map location_code -> plads-navn (tour.plads holder navnet, ikke koden).
    plads_docs = await _raw_db.plads.find(
        {"location_code": {"$in": wanted}},
        {"_id": 0, "location_code": 1, "name": 1, "company_id": 1},
    ).to_list(2000)
    code_to_name = {p["location_code"]: (p.get("name") or "") for p in plads_docs}
    plads_names = [n for n in code_to_name.values() if n]
    if not plads_names:
        return {"tours": [], "total": 0, "location_codes": wanted}

    # Byg query mod tours.
    # Fase 18.10 (2026-02-28): Estimat-ture er ikke rigtige ture (kun en
    # placeholder mens kunden planlægger) — de udelukkes fra arkiv-visning.
    tour_q: Dict[str, Any] = {
        "plads": {"$in": plads_names},
        "$or": [{"deleted": {"$exists": False}}, {"deleted": False}],
        "tour_type": {"$ne": "estimat"},
    }
    if date_from or date_to:
        df = date_from or "1970-01-01"
        dt_ = date_to or "9999-12-31"
        tour_q["date"] = {"$gte": df, "$lte": dt_}

    tours = await _raw_db.tours.find(
        tour_q,
        {"_id": 0, "receipt_image": 0},
    ).sort([("date", -1), ("completed_at", -1)]).limit(min(limit, 5000)).to_list(min(limit, 5000))

    # Berig med order_date fra container_orders (hvis tour stammer fra en
    # bestilling) og receipts (multi-vægt-breakdown for løse).
    order_ids = [t["order_id"] for t in tours if t.get("order_id")]
    orders_by_id: Dict[str, dict] = {}
    if order_ids:
        ods = await _raw_db.container_orders.find(
            {"id": {"$in": list(set(order_ids))}},
            {"_id": 0, "id": 1, "order_date": 1, "priority": 1,
             "comment": 1, "created_by_name": 1, "created_by_email": 1,
             "created_at": 1, "customer_address": 1, "co2_kg": 1,
             "co2_factor": 1, "co2_type_name": 1, "partner_id": 1,
             "weight_kg": 1},
        ).to_list(5000)
        orders_by_id = {o["id"]: o for o in ods}

    # Fase 18.6 (2026-02-28): Slå logistik-partner-firmaer op for at vise
    # menneskeligt læsbart navn (fx "ILK" eller "Marius Pedersen").
    # Partner-id kan komme fra: order.partner_id (når ordren blev oprettet)
    # eller tour.assigned_logistics_company_ids (ved manuelle ture).
    partner_ids = set()
    for t in tours:
        for pid in (t.get("assigned_logistics_company_ids") or []):
            if pid:
                partner_ids.add(pid)
    for o in orders_by_id.values():
        pid = o.get("partner_id")
        if pid:
            partner_ids.add(pid)
    partner_names: Dict[str, str] = {}
    if partner_ids:
        comps = await _raw_db.companies.find(
            {"id": {"$in": list(partner_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        partner_names = {c["id"]: c.get("name", "") for c in comps}

    tour_ids = [t["id"] for t in tours]
    receipts_by_tour: Dict[str, list] = {}
    if tour_ids:
        # Henter receipts (uden image_data — frontend trækker dem on-demand
        # via /receipts/{id}/image-binary). Inkluderer created_at + weight
        # + driver_name så hover-breakdown kan vise tidspunkter pr. kvit.
        recs = await _raw_db.receipts.find(
            {"tour_id": {"$in": tour_ids}},
            {"_id": 0, "id": 1, "tour_id": 1, "driver_name": 1,
             "final_weight_kg": 1, "created_at": 1, "date": 1,
             "fraction": 1, "image_filename": 1, "description": 1},
        ).sort("created_at", 1).to_list(20000)
        for r in recs:
            receipts_by_tour.setdefault(r["tour_id"], []).append(r)

    # Saml output med felter Location Admin har brug for. Beholder den
    # rå location_code så frontend kan filtrere visuelt på tværs af
    # valgte pladser.
    name_to_code = {v: k for k, v in code_to_name.items()}
    out = []
    for t in tours:
        order = orders_by_id.get(t.get("order_id") or "", {})
        # Resolve partner — order.partner_id har forrang, fallback til turens
        # assigned_logistics_company_ids[0].
        partner_id = order.get("partner_id") or (
            (t.get("assigned_logistics_company_ids") or [None])[0] or ""
        )
        partner_name = partner_names.get(partner_id, "") if partner_id else ""
        # CO2 — Bestilling-tab beregner som `co2_factor * weight_kg / 1000`.
        # For NORMAL ture: order.co2_kg er allerede sat når ordrens weight_kg
        # blev opdateret. For LØS afhentning ligger vægten på TUREN (sum af
        # container_weights), ikke ordren — så vi skal genberegne klientside.
        # Strategi (Fase 18.8): Foretræk altid backend-beregningen
        # `factor * tour.weight / 1000` når både factor og tour.weight er
        # > 0. Det giver 100% parity med Bestilling og sikrer at løs-tur
        # CO2 er korrekt selv om order.co2_kg er stale.
        co2_factor = float(order.get("co2_factor") or 0)
        tour_w = float(t.get("weight") or 0)
        if co2_factor > 0 and tour_w > 0:
            co2_kg = round(co2_factor * (tour_w / 1000.0), 2)
        else:
            co2_kg = order.get("co2_kg") or 0
        out.append({
            "id": t.get("id", ""),
            "date": t.get("date", ""),
            "order_date": (order.get("order_date") or t.get("order_date") or t.get("date") or ""),
            "ordered_at": order.get("created_at", ""),
            "completed_at": t.get("completed_at", ""),
            "completed": bool(t.get("completed")),
            "not_completed": bool(t.get("not_completed")),
            "not_completed_comment": t.get("not_completed_comment", ""),
            "tour_type": t.get("tour_type") or "normal",
            "loose_estimated_count": int(t.get("loose_estimated_count") or 0),
            "container_weights": list(t.get("container_weights") or []),
            "weight": t.get("weight"),
            "fraction": t.get("fraction", ""),
            "container": t.get("container", ""),
            "container_type": t.get("container_type", ""),
            "address": t.get("address", ""),
            "remark": t.get("remark", ""),
            "plads": t.get("plads", ""),
            "location_code": name_to_code.get(t.get("plads", ""), ""),
            "driver_name": t.get("claimed_by") or t.get("driver_name", ""),
            "on_way_time": t.get("on_way_time", ""),
            "on_way": bool(t.get("on_way")),
            "time": t.get("time", ""),
            "priority": t.get("priority") or order.get("priority") or "normal",
            "comment": order.get("comment", "") or t.get("remark", ""),
            "ordered_by": order.get("created_by_name", ""),
            "ordered_by_email": order.get("created_by_email", ""),
            "customer_address": order.get("customer_address", ""),
            "tour_number": t.get("tour_number", ""),
            "receipts": receipts_by_tour.get(t["id"], []),
            "co2_kg": co2_kg,
            "co2_factor": co2_factor,
            "co2_type_name": order.get("co2_type_name", ""),
            "partner_id": partner_id,
            "partner_name": partner_name,
        })

    if role == "logistics_admin":
        # Strict partner-isolation: på pladser med flere partnere må ILK ikke
        # se City Containers ture. Ture uden partner (legacy) vises kun hvis
        # pladsen udelukkende betjenes af dette firma.
        my_cid = caller.get("company_id")
        sole = {p["location_code"] for p in await _raw_db.plads.find(
            {"location_code": {"$in": wanted}, "assigned_logistics_company_ids": [my_cid]},
            {"_id": 0, "location_code": 1},
        ).to_list(2000)}
        out = [t for t in out
               if t["partner_id"] == my_cid or (not t["partner_id"] and t["location_code"] in sole)]

    return {
        "tours": out,
        "total": len(out),
        "location_codes": wanted,
        "location_names": code_to_name,
    }


# ===================================================================
#                  WORKSHOPS (Værksteder) — Batch 2
#  Library of workshop sites maintained by Customer Admin. Used in the
#  order flow when tour_type is "vaerksted" or "afhent_vaerksted":
#  the customer picks a workshop and name/address/phone are snapshotted
#  onto the order so the driver gets them directly on the tour.
# ===================================================================

def _ws_normalize(raw: dict) -> dict:
    return {
        "name": (raw.get("name") or "").strip(),
        "address": (raw.get("address") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "comment": (raw.get("comment") or "").strip(),
    }


@org_router.get("/workshops")
async def org_list_workshops(payload: dict = Depends(get_current_user_payload)):
    """Læses af alle org-roller (CA, LA, order-bruger) i deres egen kunde.
    Bruges i bestillingsflowet og i CA-biblioteket."""
    caller = await _org_caller(payload)
    if caller.get("role") not in ("customer_admin", "location_admin", "order", "driver"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    items = await _raw_db.workshops.find(
        {"company_id": caller["company_id"]},
        {"_id": 0},
    ).sort("name", 1).to_list(500)
    return items


@org_router.post("/workshops")
async def org_create_workshop(body: dict, payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    norm = _ws_normalize(body or {})
    if not norm["name"]:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    if not norm["address"]:
        raise HTTPException(status_code=400, detail="Adresse er påkrævet")
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": caller["company_id"],
        **norm,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.workshops.insert_one(doc)
    doc.pop("_id", None)
    return doc


@org_router.put("/workshops/{ws_id}")
async def org_update_workshop(ws_id: str, body: dict,
                              payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    existing = await _raw_db.workshops.find_one({"id": ws_id}, {"_id": 0})
    if not existing or existing.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Værksted ikke fundet")
    norm = _ws_normalize(body or {})
    if not norm["name"]:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    if not norm["address"]:
        raise HTTPException(status_code=400, detail="Adresse er påkrævet")
    norm["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _raw_db.workshops.update_one({"id": ws_id}, {"$set": norm})
    return await _raw_db.workshops.find_one({"id": ws_id}, {"_id": 0})


@org_router.delete("/workshops/{ws_id}")
async def org_delete_workshop(ws_id: str,
                              payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    existing = await _raw_db.workshops.find_one({"id": ws_id}, {"_id": 0})
    if not existing or existing.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Værksted ikke fundet")
    await _raw_db.workshops.delete_one({"id": ws_id})
    return {"success": True}


# ===================================================================
#                  LOCATION GROUPS (Lokationsgrupper) — Batch 2
#  Lightweight grouping of locations within ONE customer company.
#  Used as a filter/aggregator (e.g. "Sjælland" = Roskilde + Køge + Greve).
#  Each location may reference at most ONE group (optional).
# ===================================================================

@org_router.get("/location-groups")
async def org_list_location_groups(payload: dict = Depends(get_current_user_payload)):
    caller = await _org_caller(payload)
    if caller.get("role") not in ("customer_admin", "location_admin", "order", "driver"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    items = await _raw_db.location_groups.find(
        {"company_id": caller["company_id"]},
        {"_id": 0},
    ).sort("name", 1).to_list(200)
    # Add `locations_count` for each group
    if items:
        ids = [g["id"] for g in items]
        agg = await _raw_db.plads.aggregate([
            {"$match": {"company_id": caller["company_id"],
                        "location_group_id": {"$in": ids}}},
            {"$group": {"_id": "$location_group_id", "n": {"$sum": 1}}},
        ]).to_list(500)
        cmap = {a["_id"]: a["n"] for a in agg}
        for g in items:
            g["locations_count"] = cmap.get(g["id"], 0)
    return items


@org_router.post("/location-groups")
async def org_create_location_group(body: dict,
                                    payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    name = (body.get("name") or "").strip() if body else ""
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    clash = await _raw_db.location_groups.find_one(
        {"company_id": caller["company_id"], "name": name},
        {"_id": 0, "id": 1},
    )
    if clash:
        raise HTTPException(status_code=409, detail="En gruppe med dette navn findes allerede")
    doc = {
        "id": str(uuid.uuid4()),
        "company_id": caller["company_id"],
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.location_groups.insert_one(doc)
    doc.pop("_id", None)
    doc["locations_count"] = 0
    return doc


@org_router.put("/location-groups/{group_id}")
async def org_update_location_group(group_id: str, body: dict,
                                    payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    existing = await _raw_db.location_groups.find_one({"id": group_id}, {"_id": 0})
    if not existing or existing.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    name = (body.get("name") or "").strip() if body else ""
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    clash = await _raw_db.location_groups.find_one({
        "company_id": caller["company_id"], "name": name,
        "id": {"$ne": group_id},
    }, {"_id": 0, "id": 1})
    if clash:
        raise HTTPException(status_code=409, detail="En anden gruppe har allerede dette navn")
    await _raw_db.location_groups.update_one(
        {"id": group_id}, {"$set": {"name": name,
                                     "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return await _raw_db.location_groups.find_one({"id": group_id}, {"_id": 0})


@org_router.delete("/location-groups/{group_id}")
async def org_delete_location_group(group_id: str,
                                    payload: dict = Depends(require_role("customer_admin"))):
    caller = await _org_caller(payload)
    existing = await _raw_db.location_groups.find_one({"id": group_id}, {"_id": 0})
    if not existing or existing.get("company_id") != caller["company_id"]:
        raise HTTPException(status_code=404, detail="Gruppe ikke fundet")
    # Detach group from any pladser before deleting
    await _raw_db.plads.update_many(
        {"company_id": caller["company_id"], "location_group_id": group_id},
        {"$unset": {"location_group_id": ""}},
    )
    await _raw_db.location_groups.delete_one({"id": group_id})
    return {"success": True}


# ===================================================================
#                  CUSTOMER ORDER — EDIT + HARD DELETE + HISTORY
#  Batch 2: any authenticated user belonging to the same company may
#  edit/delete a pending order; every change writes an audit entry to
#  `customer_orders_history`. Delete is hard delete on the document
#  itself (after a soft-confirm in the frontend) — but the audit log
#  is preserved so it's traceable.
# ===================================================================

EDITABLE_ORDER_FIELDS = {
    "priority", "comment", "order_date", "open_from", "open_to",
    "tour_type", "custom_address", "custom_container_id",
    "workshop_id", "workshop_name", "workshop_address",
    "workshop_phone", "workshop_override",
    # Fase 9 (2026-06-17): CO2-type kan ændres efterfølgende (snapshot + recalc)
    "co2_type_id",
    # Fase 15.20 (2026-02-21): Estimat-redigering — materiale + antal
    # containere estimeret er redigerbare felter på estimat-ordrer.
    "material", "estimated_count",
    # Fase 15.44 (2026-02-22): Løs afhentning — antal containere chaufføren
    # skal medbringe. Spejles til den tilhørende tur så multi-vægt-UI'en
    # har korrekt antal felter.
    "loose_estimated_count",
}


async def _co_audit(order_id: str, action: str, payload: dict, before: dict, after: dict):
    user_id = payload.get("user_id") or ""
    name = payload.get("name") or payload.get("email") or ""
    entry = {
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "action": action,  # "edit" | "delete"
        "user_id": user_id,
        "user_name": name,
        "user_email": payload.get("email") or "",
        "before": before,
        "after": after,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.customer_orders_history.insert_one(entry)


def _diff_fields(before: dict, after: dict) -> tuple:
    cb, ca = {}, {}
    for k, v in after.items():
        if before.get(k) != v:
            cb[k] = before.get(k)
            ca[k] = v
    return cb, ca


@api_router.put("/customer-orders/{order_id}")
async def edit_customer_order(order_id: str, body: dict,
                              payload: dict = Depends(get_current_user_payload)):
    caller_role = payload.get("role")
    caller_cid = payload.get("company_id")
    if caller_role in ("driver", "genbrug_plads"):
        raise HTTPException(status_code=403, detail="Denne rolle må ikke redigere bestillinger")
    if caller_role not in ("super_admin", "customer_admin", "location_admin", "order"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    order = await _raw_db.container_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Bestilling ikke fundet")
    if caller_role != "super_admin" and order.get("company_id") != caller_cid:
        raise HTTPException(status_code=403, detail="Bestilling tilhører et andet firma")
    if order.get("status_label") in ("paa_vej", "fuldfoert"):
        raise HTTPException(
            status_code=409,
            detail="Bestillingen er allerede påbegyndt og kan ikke længere redigeres",
        )

    raw = body or {}
    proposed = {k: v for k, v in raw.items() if k in EDITABLE_ORDER_FIELDS}
    if not proposed:
        raise HTTPException(status_code=400, detail="Intet at opdatere")

    before_diff, after_diff = _diff_fields(order, proposed)
    if not after_diff:
        return {"success": True, "no_change": True}

    # Fase 9 (2026-06-17): Hvis CO2-type ændres, snapshot navn+faktor og
    # genberegn co2_kg ud fra eksisterende weight_kg.
    if "co2_type_id" in after_diff:
        new_id = proposed.get("co2_type_id") or ""
        if new_id:
            co2_doc = await _raw_db.co2_types.find_one({"id": new_id}, {"_id": 0})
            if co2_doc:
                proposed["co2_type_name"] = co2_doc.get("name", "")
                proposed["co2_factor"] = float(co2_doc.get("factor", 0) or 0)
            else:
                proposed["co2_type_name"] = ""
                proposed["co2_factor"] = 0.0
        else:
            proposed["co2_type_name"] = ""
            proposed["co2_factor"] = 0.0
        kg = float(order.get("weight_kg") or 0)
        proposed["co2_kg"] = round(float(proposed["co2_factor"]) * (kg / 1000.0), 3)

    proposed["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _raw_db.container_orders.update_one({"id": order_id}, {"$set": proposed})
    # Sync the linked driver tour where relevant
    tour_update = {}
    if "priority" in after_diff:
        tour_update["priority"] = proposed["priority"]
    if "order_date" in after_diff:
        # Spejle BÅDE date (driver date-filter) OG order_date (vises på
        # tour-kortet som "Bestillingsdato"). Tidligere blev kun `date`
        # opdateret, så chauffør-kortet viste stadig den gamle dato.
        tour_update["date"] = proposed["order_date"]
        tour_update["order_date"] = proposed["order_date"]
    if "tour_type" in after_diff:
        tour_update["tour_type"] = proposed["tour_type"]
    if "comment" in after_diff:
        tour_update["remark"] = (f"Kundeordre: {proposed['comment']}"
                                  if proposed["comment"] else "Kundeordre")
    if "custom_container_id" in after_diff and proposed.get("custom_container_id"):
        tour_update["container"] = proposed["custom_container_id"]
    # Fase 15.20 (2026-02-21): Estimat-specifikke felter spejles til touren
    # (bruges af "Planlæg ressourcer"-fanen for at vise opdaterede værdier).
    if "material" in after_diff:
        tour_update["fraction"] = proposed["material"]
    if "estimated_count" in after_diff:
        try:
            tour_update["estimated_count"] = int(proposed["estimated_count"] or 0)
        except (TypeError, ValueError):
            tour_update["estimated_count"] = 0
    # Fase 15.44 (2026-02-22): Spejle loose_estimated_count til touren så
    # chaufførens multi-vægt-UI viser korrekt antal rækker når antallet
    # ændres efter bestillingen er oprettet.
    if "loose_estimated_count" in after_diff:
        try:
            tour_update["loose_estimated_count"] = int(proposed["loose_estimated_count"] or 0)
        except (TypeError, ValueError):
            tour_update["loose_estimated_count"] = 0
    if tour_update and order.get("tour_id"):
        await _raw_db.tours.update_one({"id": order["tour_id"]}, {"$set": tour_update})

    await _co_audit(order_id, "edit", payload, before_diff, after_diff)
    return {"success": True, "changed_fields": list(after_diff.keys())}


@api_router.delete("/customer-orders/{order_id}")
async def delete_customer_order(order_id: str,
                                payload: dict = Depends(get_current_user_payload)):
    # Fase 15.51 (2026-02-22): "Slet" er erstattet med "Annuller" for customer/
    # order-roller. Endepunktet beholdes for super_admin (audit/cleanup) men
    # blokerer alle andre roller — de skal nu bruge POST /cancel.
    caller_role = payload.get("role")
    if caller_role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Brug 'Annuller'-knappen i stedet for at slette bestillinger",
        )
    order = await _raw_db.container_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Bestilling ikke fundet")
    await _co_audit(order_id, "delete", payload, order, {})
    if order.get("tour_id"):
        await _raw_db.tours.delete_one({"id": order["tour_id"]})
    await _raw_db.container_orders.delete_one({"id": order_id})
    return {"success": True}


@api_router.post("/customer-orders/{order_id}/cancel")
async def cancel_customer_order(order_id: str,
                                payload: dict = Depends(get_current_user_payload)):
    """Fase 15.51 (2026-02-22): Annuller en bestilling (soft-cancel).
    Erstatter den tidligere "slet"-flow på Mine bestillinger.

    Regler:
    - Kun customer_admin/location_admin/order/super_admin må annullere.
    - Multi-tenant: bestillingen skal tilhøre callerens firma (super_admin
      bypass'er).
    - En bestilling KAN IKKE annulleres hvis:
        * status er allerede 'completed' eller 'cancelled', ELLER
        * den tilhørende tour er markeret `on_way=True` eller `completed=True`.
      Frontend skal allerede skjule knappen i disse tilfælde, men backend er
      defense-in-depth.
    - Annullering er ENDELIG — der findes ingen revert-endpoint. Hvis kunden
      fortryder, skal de oprette en ny bestilling.

    Sideeffekter:
    - Ordre: status='cancelled', cancelled_at=now (ISO).
    - Tour (hvis findes): cancelled=True, cancelled_at=now. Vi sletter IKKE
      turen så driver-UI'en kan vise den grået ud nederst i listen og admin/
      rapport kan vise den i statistik.
    - Overlap-check (POST /api/order/check-overlap) ekskluderer allerede
      'cancelled'-ordrer så en ny bestilling kan oprettes uden konflikt.
    """
    caller_role = payload.get("role")
    caller_cid = payload.get("company_id")
    if caller_role in ("driver", "genbrug_plads"):
        raise HTTPException(status_code=403, detail="Denne rolle må ikke annullere bestillinger")
    if caller_role not in ("super_admin", "customer_admin", "location_admin", "order"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    order = await _raw_db.container_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Bestilling ikke fundet")
    if caller_role != "super_admin" and order.get("company_id") != caller_cid:
        raise HTTPException(status_code=403, detail="Bestilling tilhører et andet firma")
    current_status = (order.get("status") or "").lower()
    if current_status == "completed":
        raise HTTPException(status_code=409, detail="Bestillingen er allerede afsluttet — kan ikke annulleres")
    if current_status == "cancelled":
        raise HTTPException(status_code=409, detail="Bestillingen er allerede annulleret")
    tour_id = order.get("tour_id")
    if tour_id:
        tour = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "on_way": 1, "completed": 1, "claimed_by": 1})
        if tour:
            if tour.get("completed"):
                raise HTTPException(status_code=409, detail="Turen er allerede afsluttet — kan ikke annulleres")
            if tour.get("on_way"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Chaufføren ({tour.get('claimed_by') or 'ukendt'}) er allerede på vej — kan ikke annulleres",
                )
    now_iso = datetime.now(DK_TZ).isoformat()
    cancelled_by_name = (payload.get("name") or payload.get("email") or "").strip()
    # Update order
    await _raw_db.container_orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": now_iso,
            "cancelled_by_id": payload.get("user_id") or payload.get("sub") or "",
            "cancelled_by_name": cancelled_by_name,
            "cancelled_by_role": caller_role,
        }},
    )
    # Mirror to tour (so driver UI viser den som annulleret nederst)
    if tour_id:
        await _raw_db.tours.update_one(
            {"id": tour_id},
            {"$set": {
                "cancelled": True,
                "cancelled_at": now_iso,
                "cancelled_by_name": cancelled_by_name,
                "cancelled_by_role": caller_role,
            }},
        )
    # Audit log
    await _co_audit(
        order_id, "cancel", payload, order,
        {"status": "cancelled", "cancelled_at": now_iso},
    )
    return {"success": True, "cancelled_at": now_iso, "cancelled_by": cancelled_by_name}



async def get_customer_order_history(order_id: str,
                                     payload: dict = Depends(get_current_user_payload)):
    caller_role = payload.get("role")
    caller_cid = payload.get("company_id")
    if caller_role in ("driver", "genbrug_plads"):
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    order = await _raw_db.container_orders.find_one({"id": order_id}, {"_id": 0, "company_id": 1})
    if order and caller_role != "super_admin" and order.get("company_id") != caller_cid:
        raise HTTPException(status_code=403, detail="Adgang nægtet")
    entries = await _raw_db.customer_orders_history.find(
        {"order_id": order_id},
        {"_id": 0},
    ).sort("at", -1).to_list(200)
    if not order and entries and caller_role != "super_admin":
        first_before = entries[-1].get("before") or {}
        if first_before.get("company_id") and first_before["company_id"] != caller_cid:
            raise HTTPException(status_code=403, detail="Adgang nægtet")
    return entries


# =====================================================================
#   ØKONOMI — prisregler, rapport og godkendelser (PRICING_SPEC.md)
#   Logistik admin vedligeholder prisregler; prisen pr. tur beregnes af
#   backend/pricing.py ud fra turens fakta, kalendere og stemplinger.
# =====================================================================
import pricing as _pricing
from datetime import date as _date

pricing_router = APIRouter(prefix="/api/pricing", tags=["pricing"])

_PRICE_SETTINGS_DEFAULT = {
    "holiday_source": "customer_first",   # customer_first | own
    "concurrent_mode": "split",           # split | full
    "vat_percent": 25.0,
    "holiday_optional": list(_pricing.DEFAULT_OPTIONAL),
    "holiday_extra": [],
    "holiday_excluded": [],
}
_PRIORITY_TO_PRICE = {"urgent": "haster", "haster": "haster", "low": "lav", "senere": "lav", "sidst": "lav"}


async def _pricing_caller(payload: dict) -> dict:
    """Logistik admin + hans firma. (Prisregler er logistikfirmaets egne.)"""
    if payload.get("role") != "logistics_admin":
        raise HTTPException(status_code=403, detail="Kun logistik admin har adgang til økonomi")
    user = await _raw_db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("company_id"):
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    return user


async def _price_settings(cid: str) -> dict:
    doc = await _raw_db.price_settings.find_one({"company_id": cid}, {"_id": 0}) or {}
    return {**_PRICE_SETTINGS_DEFAULT, **{k: v for k, v in doc.items() if k in _PRICE_SETTINGS_DEFAULT}}


def _to_dk_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo:
            dt = dt.astimezone(DK_TZ)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso[:10]


def _service_date(t: dict) -> str:
    """Den dag turen køres: afslutningsdato, forgæves-dato eller planlagt dato."""
    if t.get("completed") and t.get("completed_at"):
        return _to_dk_date(t["completed_at"])
    if t.get("not_completed") and t.get("not_completed_at"):
        return _to_dk_date(t["not_completed_at"])
    return t.get("date") or ""


async def _my_drivers(cid: str) -> list:
    return await _raw_db.users.find(
        {"company_id": cid, "role": "driver"}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(2000)


def _fact(t: dict, key: str, fallback=None):
    fo = t.get("fact_overrides") or {}
    return fo[key] if fo.get(key) not in (None, "") else fallback


def _tour_times(t: dict) -> tuple:
    start = _fact(t, "start_time", t.get("on_way_time") or "")
    end = _fact(t, "end_time", t.get("time") if t.get("completed") else "")
    return start, end


async def _billable_tours(cid: str, date_from: str, date_to: str, extra: Optional[dict] = None) -> list:
    """Ture logistikfirmaet kan fakturere: gennemført eller forgæves, kørt af
    firmaets egne chauffører, med køre-dato i perioden."""
    drivers = await _my_drivers(cid)
    ids = [d["id"] for d in drivers]
    names = [d["name"] for d in drivers if d.get("name")]
    if not ids:
        return []
    # Bred forespørgsel (±1 dag pga. tidszoner), præcis filtrering bagefter.
    lo = (_date.fromisoformat(date_from) - timedelta(days=1)).isoformat()
    hi = (_date.fromisoformat(date_to) + timedelta(days=2)).isoformat()
    q: Dict[str, Any] = {"$and": [
        {"$or": [{"claimed_by_id": {"$in": ids}}, {"claimed_by": {"$in": names}},
                 {"not_completed_by_name": {"$in": names}}]},
        {"$or": [{"completed": True}, {"not_completed": True}]},
        {"$or": [{"completed_at": {"$gte": lo, "$lt": hi}},
                 {"not_completed_at": {"$gte": lo, "$lt": hi}},
                 {"date": {"$gte": lo, "$lt": hi}}]},
        {"$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
        {"$or": [{"is_pause": {"$exists": False}}, {"is_pause": False}]},
        {"tour_type": {"$ne": "estimat"}},
    ]}
    if extra:
        q["$and"].append(extra)
    tours = await _raw_db.tours.find(q, {"_id": 0, "receipt_image": 0}).to_list(20000)
    return [t for t in tours if date_from <= _service_date(t) <= date_to]


class _PricingContext:
    """Samler alt der skal til for at prissætte en mængde ture på én gang."""

    def __init__(self, cid: str, settings: dict, rules: list):
        self.cid, self.settings, self.rules = cid, settings, rules
        self.orders: Dict[str, dict] = {}
        self.addr_labels: Dict[str, str] = {}
        self.addr_line_labels: Dict[tuple, str] = {}
        self.plads_by_name: Dict[str, dict] = {}
        self.customers: Dict[str, dict] = {}
        self.mat_cal: Dict[tuple, str] = {}
        self.cal_days: Dict[str, Dict[str, Any]] = {}
        self.loc_active_cals: Dict[str, List[str]] = {}
        self.groups: Dict[str, dict] = {}
        self.time_by_tour: Dict[str, dict] = {}
        self.holiday_cache: Dict[tuple, tuple] = {}

    async def load(self, tours: list):
        order_ids = list({t["order_id"] for t in tours if t.get("order_id")})
        if order_ids:
            for o in await _raw_db.container_orders.find(
                {"id": {"$in": order_ids}},
                {"_id": 0, "id": 1, "location_code": 1, "delivery_address_id": 1,
                 "alternative_delivery_address_id": 1, "manual_alternative_address": 1},
            ).to_list(20000):
                self.orders[o["id"]] = o
        addr_ids = {a for o in self.orders.values()
                    for a in (o.get("delivery_address_id"), o.get("alternative_delivery_address_id")) if a}
        if addr_ids:
            for a in await _raw_db.delivery_addresses.find(
                {"id": {"$in": list(addr_ids)}}, {"_id": 0, "id": 1, "label": 1},
            ).to_list(20000):
                self.addr_labels[a["id"]] = a.get("label") or ""
        # Bestillingssiden gemmer leveringsadressen som tekst ("Energivej 10,
        # 3000 Helsingør") uden id. Genkend modtageren ved at matche teksten
        # mod lokationens leveringsadresser.
        order_codes = list({o.get("location_code") for o in self.orders.values() if o.get("location_code")})
        if order_codes:
            for a in await _raw_db.delivery_addresses.find(
                {"location_code": {"$in": order_codes}}, {"_id": 0},
            ).to_list(20000):
                line = _pricing.norm_label(_da_format_address_line(a))
                if line and a.get("label"):
                    self.addr_line_labels[(a.get("location_code"), line)] = a["label"]
                    self.addr_line_labels.setdefault(("", line), a["label"])
        names = list({t.get("plads") for t in tours if t.get("plads")})
        for p in await _raw_db.plads.find(
            {"name": {"$in": names}}, {"_id": 0, "name": 1, "location_code": 1, "company_id": 1},
        ).to_list(5000):
            self.plads_by_name[p["name"]] = p
        cust_ids = list({t.get("company_id") for t in tours if t.get("company_id")})
        for c in await _raw_db.companies.find(
            {"id": {"$in": cust_ids}}, {"_id": 0, "id": 1, "name": 1, "holiday_group_id": 1},
        ).to_list(1000):
            self.customers[c["id"]] = c
        codes = list({self.location_code(t) for t in tours} - {""})
        if codes:
            for mc in await _raw_db.material_calendars.find(
                {"location_code": {"$in": codes}}, {"_id": 0, "location_code": 1, "material": 1,
                                                    "holiday_calendar_id": 1},
            ).to_list(20000):
                if mc.get("holiday_calendar_id"):
                    self.mat_cal[(mc["location_code"], mc["material"])] = mc["holiday_calendar_id"]
            for hc in await _raw_db.holiday_calendars.find(
                {"location_code": {"$in": codes}}, {"_id": 0, "id": 1, "location_code": 1,
                                                    "is_active": 1, "days": 1},
            ).to_list(5000):
                self.cal_days[hc["id"]] = {d.get("date"): d.get("name") for d in (hc.get("days") or [])
                                           if d.get("date")}
                if hc.get("is_active", True):
                    self.loc_active_cals.setdefault(hc["location_code"], []).append(hc["id"])
        gids = list({c.get("holiday_group_id") for c in self.customers.values() if c.get("holiday_group_id")})
        if gids:
            for g in await _raw_db.holiday_groups.find({"id": {"$in": gids}}, {"_id": 0}).to_list(500):
                self.groups[g["id"]] = {h.get("date"): h.get("name") for h in (g.get("holidays") or [])}
        await self._load_times(tours)

    def customer_key(self, t: dict) -> str:
        """Kunden i økonomi-forstand. Logistikfirmaets EGNE ture (premium,
        manuelle) har ingen genbrugsplads-kunde - der er kunden det firma der
        står på turen ("firma tur"), så priser og fakturagrundlag kan laves
        pr. slutkunde."""
        cid_t = t.get("company_id") or ""
        if cid_t and cid_t == self.cid:
            nm = (t.get("private_company") or t.get("customer_name") or "").strip()
            return f"firma:{_pricing.norm_label(nm)}" if nm else self.cid
        return cid_t

    def customer_name(self, t: dict) -> str:
        cid_t = t.get("company_id") or ""
        if cid_t and cid_t == self.cid:
            return (t.get("private_company") or t.get("customer_name") or "").strip() or "Egne ture"
        return (self.customers.get(cid_t) or {}).get("name") or t.get("customer_name") or ""

    def location_code(self, t: dict) -> str:
        order = self.orders.get(t.get("order_id") or "")
        if order and order.get("location_code"):
            # Ordrens location_code er QR-koden; plads-navnet er den præcise plads.
            p = self.plads_by_name.get(t.get("plads") or "")
            return (p or {}).get("location_code") or order["location_code"]
        return (self.plads_by_name.get(t.get("plads") or "") or {}).get("location_code") or ""

    def delivery_label(self, t: dict) -> str:
        o = self.orders.get(t.get("order_id") or "")
        if o:
            if o.get("alternative_delivery_address_id") in self.addr_labels:
                return self.addr_labels[o["alternative_delivery_address_id"]]
            if o.get("manual_alternative_address"):
                return o["manual_alternative_address"]
            if o.get("delivery_address_id") in self.addr_labels:
                return self.addr_labels[o["delivery_address_id"]]
            line = _pricing.norm_label(o.get("customer_address") or t.get("address") or "")
            hit = (self.addr_line_labels.get((o.get("location_code"), line))
                   or self.addr_line_labels.get(("", line)))
            if hit:
                return hit
            return o.get("customer_address") or t.get("address") or ""
        return t.get("facility") or ""

    def holidays_for(self, t: dict, service_date: str) -> tuple:
        """(set af helligdage, kilde) — kundens kalender først hvis valgt."""
        year = service_date[:4]
        code, material = self.location_code(t), t.get("fraction") or ""
        key = (t.get("company_id"), code, material, year)
        if key in self.holiday_cache:
            return self.holiday_cache[key]
        result = None
        if self.settings.get("holiday_source") == "customer_first":
            cal_ids = ([self.mat_cal[(code, material)]] if (code, material) in self.mat_cal
                       else self.loc_active_cals.get(code, []))
            days = {d for cid_ in cal_ids for d in self.cal_days.get(cid_, {}) if d.startswith(year)}
            if days:
                result = (days, "Lokationens helligdagskalender")
            else:
                gid = (self.customers.get(t.get("company_id")) or {}).get("holiday_group_id")
                gdays = {d for d in self.groups.get(gid, {}) if d.startswith(year)} if gid else set()
                if gdays:
                    result = (gdays, "Kundens helligdagsgruppe")
        if not result:
            try:
                own = _pricing.own_holidays(int(year), self.settings)
            except ValueError:
                own = {}
            result = (set(own), "Egen helligdagskalender")
        self.holiday_cache[key] = result
        return result

    async def _load_times(self, tours: list):
        """Tid pr. tur inkl. pause-overlap og fordeling ved samtidige ture."""
        keys = {(t.get("claimed_by_id"), _service_date(t)) for t in tours
                if t.get("claimed_by_id") and t.get("completed")}
        if not keys:
            return
        driver_ids = list({k[0] for k in keys})
        dates = sorted({k[1] for k in keys})
        lo = (_date.fromisoformat(dates[0]) - timedelta(days=1)).isoformat()
        hi = (_date.fromisoformat(dates[-1]) + timedelta(days=2)).isoformat()
        companions = await _raw_db.tours.find(
            {"claimed_by_id": {"$in": driver_ids}, "completed": True,
             "completed_at": {"$gte": lo, "$lt": hi},
             "$or": [{"deleted": {"$exists": False}}, {"deleted": False}]},
            {"_id": 0, "id": 1, "claimed_by_id": 1, "on_way_time": 1, "time": 1, "completed": 1,
             "completed_at": 1, "fact_overrides": 1, "date": 1},
        ).to_list(20000)
        pauses = await _raw_db.driver_time_entries.find(
            {"driver_id": {"$in": driver_ids}, "date": {"$in": dates}, "slice_type": "pause",
             **_not_deleted_filter()},
            {"_id": 0, "driver_id": 1, "date": 1, "start_time": 1, "end_time": 1},
        ).to_list(20000)
        pause_by_key: Dict[tuple, list] = {}
        for p in pauses:
            s, e = _pricing.hhmm_to_min(p.get("start_time")), _pricing.hhmm_to_min(p.get("end_time"))
            if s >= 0 and e > s:
                pause_by_key.setdefault((p["driver_id"], p["date"]), []).append((s, e))
        by_key: Dict[tuple, Dict[str, tuple]] = {}
        gross: Dict[str, int] = {}
        for t in {c["id"]: c for c in companions + tours}.values():
            key = (t.get("claimed_by_id"), _service_date(t))
            if key not in keys or not t.get("completed"):
                continue
            st, en = _tour_times(t)
            s, e = _pricing.hhmm_to_min(st), _pricing.hhmm_to_min(en)
            if s < 0 or e < 0:
                continue
            if e <= s:
                e += 1440  # over midnat
            by_key.setdefault(key, {})[t["id"]] = (s, e)
            gross[t["id"]] = e - s
        mode = self.settings.get("concurrent_mode") or "split"
        for key, intervals in by_key.items():
            split = _pricing.split_driver_day(intervals, pause_by_key.get(key, []), mode)
            for tid, v in split.items():
                self.time_by_tour[tid] = {"gross": gross[tid], "total": v["total"], "pause": v["pause"]}

    def attrs(self, t: dict) -> dict:
        sd = _service_date(t)
        holidays, _src = self.holidays_for(t, sd)
        start, _end = _tour_times(t)
        trailer = _fact(t, "used_trailer", t.get("used_trailer"))
        trailer_count = int(t.get("trailer_count") or 0) or (1 if trailer else 0)
        containers = len(t.get("container_weights") or []) or int(t.get("loose_estimated_count") or 0) or 1
        return {
            "customer_id": self.customer_key(t),
            "location_code": self.location_code(t),
            "material": t.get("fraction") or "",
            "task_type": (t.get("tour_type") or "normal").replace("værksted", "vaerksted"),
            "priority": _PRIORITY_TO_PRICE.get(t.get("priority") or "", "normal"),
            "day_type": _pricing.day_type(sd, holidays),
            "trailer": bool(trailer) or trailer_count > 0,
            "trailer_count": trailer_count,
            "container_label": t.get("capacity_label") or "",
            "delivery_label": self.delivery_label(t),
            "start_min": _pricing.hhmm_to_min(start),
            "outcome": "not_completed" if t.get("not_completed") and not t.get("completed") else "completed",
            "service_date": sd,
            "containers": containers,
            "waiting_min": int(_fact(t, "waiting_min", 0) or 0),
            "deduct_pause_override": (t.get("fact_overrides") or {}).get("deduct_pause"),
        }

    def rules_for(self, t: dict) -> list:
        """2026-10-17: Prisregler har versioner (version_from/version_to). En tur
        prisberegnes med de regler der gjaldt da turen blev oprettet/bestilt,
        så en prisændring i dag ikke ændrer eksisterende ture i rapporter/PDF."""
        ref = _rule_ref_time(t)
        return [r for r in self.rules if _rule_active_at(r, ref)]

    def price(self, t: dict) -> dict:
        locked = t.get("price_locked")
        if locked:
            return {**locked, "flags": list(locked.get("flags") or []) + ["Faktureret"], "locked": True}
        res = _pricing.price_tour(self.attrs(t), self.rules_for(t), self.time_by_tour.get(t["id"]),
                                  t.get("price_override"))
        res["locked"] = False
        return res


async def _active_rules(cid: str) -> list:
    """Alle versioner (også udløbne) - filtreres pr. tur i _PricingContext.rules_for."""
    return await _raw_db.price_rules.find({"company_id": cid}, {"_id": 0}).to_list(5000)


def _parse_ts(v: str) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(str(v)[:10] + "T00:00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DK_TZ)
    return dt


def _rule_ref_time(t: dict) -> Optional[datetime]:
    """Tidspunktet der afgør hvilken prisversion en tur bruger: hvornår turen
    blev oprettet/bestilt. Mangler det, bruges kørselsdatoen."""
    return _parse_ts(t.get("created_at") or "") or _parse_ts(t.get("date") or "")


def _rule_active_at(r: dict, ref: Optional[datetime]) -> bool:
    vf, vt = _parse_ts(r.get("version_from") or ""), _parse_ts(r.get("version_to") or "")
    if ref is None:
        return not vt  # ukendt tidspunkt: brug den gældende version
    if vf and ref < vf:
        return False
    if vt and ref >= vt:
        return False
    return True


def _effective_ts(effective: Any) -> Optional[str]:
    """"all" = gælder også eksisterende ture (None). "now"/tomt = fra nu.
    "YYYY-MM-DD" = fra den dato kl. 00:00 dansk tid."""
    e = str(effective or "now").strip()
    if e == "all":
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", e):
        return datetime.fromisoformat(e + "T00:00:00").replace(tzinfo=DK_TZ).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _rule_is_current(r: dict) -> bool:
    vt = _parse_ts(r.get("version_to") or "")
    return not vt or vt > datetime.now(timezone.utc)


def _report_row(ctx: _PricingContext, t: dict, pending: Dict[str, int]) -> dict:
    a = ctx.attrs(t)
    start, end = _tour_times(t)
    _hol, hol_src = ctx.holidays_for(t, a["service_date"])
    return {
        "tour_id": t["id"],
        "tour_number": t.get("tour_number") or "",
        "service_date": a["service_date"],
        "customer_id": a["customer_id"],
        "customer_name": ctx.customer_name(t),
        "location_code": a["location_code"],
        "location_name": t.get("plads") or "",
        "material": a["material"],
        "task_type": a["task_type"],
        "priority": a["priority"],
        "day_type": a["day_type"],
        "holiday_source": hol_src,
        "trailer": a["trailer"],
        "delivery_label": a["delivery_label"],
        "container_label": a["container_label"],
        "driver_name": t.get("claimed_by") or t.get("not_completed_by_name") or "",
        "start_time": start, "end_time": end,
        "waiting_min": a["waiting_min"],
        "outcome": a["outcome"],
        "weight": t.get("weight"),
        "has_override": bool((t.get("price_override") or {}).get("mode") == "fixed"
                             or (t.get("price_override") or {}).get("extra_lines")
                             or t.get("fact_overrides")),
        "pending_requests": pending.get(t["id"], 0),
        "price": ctx.price(t),
    }


# ----- Indstillinger + helligdage ------------------------------------------
@pricing_router.get("/settings")
async def pricing_get_settings(payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    return await _price_settings(me["company_id"])


@pricing_router.put("/settings")
async def pricing_put_settings(body: dict, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    cur = await _price_settings(me["company_id"])
    upd = {}
    if body.get("holiday_source") in ("customer_first", "own"):
        upd["holiday_source"] = body["holiday_source"]
    if body.get("concurrent_mode") in ("split", "full"):
        upd["concurrent_mode"] = body["concurrent_mode"]
    if "vat_percent" in body:
        upd["vat_percent"] = max(0.0, min(100.0, float(body.get("vat_percent") or 0)))
    if isinstance(body.get("holiday_optional"), list):
        upd["holiday_optional"] = [k for k in body["holiday_optional"] if k in _pricing.OPTIONAL_HOLIDAYS]
    if isinstance(body.get("holiday_extra"), list):
        extra = []
        for x in body["holiday_extra"]:
            d = str((x or {}).get("date") or "")
            if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                extra.append({"date": d, "name": str(x.get("name") or "Ekstra fridag").strip()[:60]})
        upd["holiday_extra"] = sorted(extra, key=lambda x: x["date"])
    if isinstance(body.get("holiday_excluded"), list):
        upd["holiday_excluded"] = sorted({d for d in body["holiday_excluded"]
                                          if re.match(r"^\d{4}-\d{2}-\d{2}$", str(d))})
    new = {**cur, **upd}
    await _raw_db.price_settings.update_one(
        {"company_id": me["company_id"]},
        {"$set": {**new, "company_id": me["company_id"],
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return new


@pricing_router.get("/holidays")
async def pricing_holidays(year: int, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    s = await _price_settings(me["company_id"])
    official = _pricing.danish_holidays(year)
    optional_all = _pricing.danish_holidays(year, list(_pricing.OPTIONAL_HOLIDAYS))
    own = _pricing.own_holidays(year, s)
    extra_dates = {x["date"] for x in s.get("holiday_extra") or []}
    rows = []
    for d, name in sorted({**optional_all, **own}.items()):
        kind = "official" if d in official else "extra" if d in extra_dates else "optional"
        rows.append({"date": d, "name": own.get(d) or name, "kind": kind,
                     "active": d in own, "excluded": d in (s.get("holiday_excluded") or [])})
    return {"year": year, "days": rows, "settings": s,
            "optional_keys": _pricing.OPTIONAL_HOLIDAYS}


# ----- Valgmuligheder til regel-editoren -----------------------------------
@pricing_router.get("/options")
async def pricing_options(payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    cid = me["company_id"]
    plads = await _raw_db.plads.find(
        {"assigned_logistics_company_ids": cid},
        {"_id": 0, "name": 1, "location_code": 1, "company_id": 1, "materials": 1, "partner_materials": 1},
    ).to_list(5000)
    comp = await _raw_db.companies.find_one({"id": cid}, {"_id": 0, "serves_company_ids": 1}) or {}
    cust_ids = set(comp.get("serves_company_ids") or []) | {p.get("company_id") for p in plads}
    customers = await _raw_db.companies.find(
        {"id": {"$in": [c for c in cust_ids if c]}, "company_type": COMPANY_TYPE_CUSTOMER},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(1000)
    codes = [p["location_code"] for p in plads if p.get("location_code")]
    labels = sorted({(a.get("label") or "").strip() for a in await _raw_db.delivery_addresses.find(
        {"location_code": {"$in": codes}}, {"_id": 0, "label": 1}).to_list(20000)} - {""})
    caps = sorted({(c.get("label") or "").strip() for c in await _raw_db.capacity_measures.find(
        {"location_code": {"$in": codes}}, {"_id": 0, "label": 1}).to_list(20000)} - {""})
    materials = set()
    for p in plads:
        pm = (p.get("partner_materials") or {}).get(cid)
        materials.update(pm if pm else (p.get("materials") or []))
    legacy = await _raw_db.tour_prices.count_documents({"company_id": cid})
    profile = await _logistics_profile(cid)
    customers = sorted(customers, key=lambda c: c["name"])
    # Egne ture (premium / manuelle): kunden er firmaet på turen.
    own_names: Dict[str, str] = {}
    for field in ("private_company", "customer_name"):
        for nm in await _raw_db.tours.distinct(field, {"company_id": cid}):
            if isinstance(nm, str) and nm.strip():
                own_names.setdefault(_pricing.norm_label(nm), nm.strip())
    # 2026-10-17: Registrerede egne kunder (Økonomi › Kunder) - også før de har ture.
    registered = await _raw_db.logistics_customers.find({"company_id": cid}, {"_id": 0}).to_list(2000)
    reg_keys = {}
    for d in registered:
        k = _pricing.norm_label(d["name"])
        reg_keys[k] = d
        if d.get("active", True) or k in own_names:
            own_names[k] = d["name"]
    if own_names or profile.get("is_premium"):
        customers.append({"id": cid, "name": "Egne ture uden kunde", "own": True})
        customers += [{"id": f"firma:{k}", "name": v, "own": True,
                       "registered_id": (reg_keys.get(k) or {}).get("id"),
                       "inactive": (reg_keys.get(k) or {}).get("active") is False}
                      for k, v in sorted(own_names.items(), key=lambda kv: kv[1].lower())]
    return {
        "profile": profile,
        "customers": customers,
        "locations": sorted([{"code": p["location_code"], "name": p["name"], "customer_id": p.get("company_id")}
                             for p in plads if p.get("location_code")], key=lambda x: x["name"]),
        "delivery_labels": labels,
        "container_labels": caps,
        "materials": sorted(materials),
        "task_types": _pricing.TASK_TYPES,
        "priorities": _pricing.PRIORITIES,
        "day_types": _pricing.DAY_TYPES,
        "categories": _pricing.SURCHARGE_CATEGORIES,
        "models": _pricing.BASE_MODELS,
        "legacy_prices": legacy,
    }


# ----- Prisregler ----------------------------------------------------------
_COND_LISTS = ("customer_ids", "location_codes", "delivery_labels", "materials", "task_types",
               "priorities", "day_types", "container_labels")


def _clean_rule(body: dict) -> dict:
    kind = body.get("kind")
    if kind not in ("base", "surcharge"):
        raise HTTPException(status_code=400, detail="Vælg grundpris eller tillæg")
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Navn er påkrævet")
    c = body.get("conditions") or {}
    cond = {k: [str(x) for x in (c.get(k) or []) if str(x).strip()] for k in _COND_LISTS}
    cond["trailer"] = c.get("trailer") if c.get("trailer") in ("with", "without") else ""
    cond["trailer_counts"] = sorted({int(x) for x in (c.get("trailer_counts") or []) if str(x).isdigit() and 1 <= int(x) <= 3})
    cond["outcome"] = c.get("outcome") if c.get("outcome") in ("completed", "not_completed", "any") else "completed"
    tf, tt = str(c.get("time_from") or ""), str(c.get("time_to") or "")
    if tf or tt:
        if _pricing.hhmm_to_min(tf) < 0 or _pricing.hhmm_to_min(tt) < 0 or tf == tt:
            raise HTTPException(status_code=400, detail="Tidsrum skal være to forskellige klokkeslæt (TT:MM)")
    cond["time_from"], cond["time_to"] = tf, tt

    def num(x, label, allow_none=False):
        if x in (None, ""):
            if allow_none:
                return None
            raise HTTPException(status_code=400, detail=f"{label} mangler")
        try:
            v = float(x)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{label} skal være et tal")
        if v < 0:
            raise HTTPException(status_code=400, detail=f"{label} må ikke være negativ")
        return v

    doc = {"kind": kind, "name": name[:80], "conditions": cond,
           "active": bool(body.get("active", True)), "note": str(body.get("note") or "")[:1000],
           "valid_from": str(body.get("valid_from") or ""), "valid_to": str(body.get("valid_to") or ""),
           "category": "", "pricing": {}, "surcharge": {}}
    if doc["valid_from"] and doc["valid_to"] and doc["valid_from"] > doc["valid_to"]:
        raise HTTPException(status_code=400, detail="Gyldig fra skal være før gyldig til")
    if kind == "base":
        p = body.get("pricing") or {}
        model = p.get("model")
        if model not in _pricing.BASE_MODELS:
            raise HTTPException(status_code=400, detail="Vælg prismodel")
        if model in ("fixed", "per_container"):
            doc["pricing"] = {"model": model, "amount": num(p.get("amount"), "Beløb")}
        else:
            rmode = p.get("rounding_mode") if p.get("rounding_mode") in ("none", "up", "nearest", "down") else "none"
            rmin = int(num(p.get("rounding_minutes"), "Afrunding", True) or 0)
            if rmode != "none" and not (1 <= rmin <= 240):
                raise HTTPException(status_code=400, detail="Afrunding skal være 1–240 minutter")
            doc["pricing"] = {
                "model": "hourly",
                "hourly_rate": num(p.get("hourly_rate"), "Timepris"),
                "start_fee": num(p.get("start_fee"), "Startgebyr", True) or 0,
                "min_minutes": int(num(p.get("min_minutes"), "Minimum minutter", True) or 0),
                "min_amount": num(p.get("min_amount"), "Minimumsbeløb", True) or 0,
                "rounding_mode": rmode, "rounding_minutes": rmin if rmode != "none" else 0,
                "deduct_pause": bool(p.get("deduct_pause", True)),
            }
    else:
        cat = body.get("category")
        if cat not in _pricing.SURCHARGE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Vælg tillægstype")
        s = body.get("surcharge") or {}
        unit = s.get("unit") if s.get("unit") in ("kr", "percent", "per_hour") else "kr"
        doc["category"] = cat
        doc["surcharge"] = {"unit": unit, "value": num(s.get("value"), "Tillæg")}
    return doc


@pricing_router.get("/rules")
async def pricing_list_rules(payload: dict = Depends(get_current_user_payload)):
    """Gældende (og planlagte) versioner. Udløbne versioner ses via /history."""
    me = await _pricing_caller(payload)
    all_rules = await _active_rules(me["company_id"])
    counts: Dict[str, int] = {}
    for r in all_rules:
        g = r.get("version_group") or r["id"]
        counts[g] = counts.get(g, 0) + 1
    rules = [r for r in all_rules if _rule_is_current(r)]
    for r in rules:
        r["specificity"] = _pricing.specificity(r)
        r["versions"] = counts.get(r.get("version_group") or r["id"], 1)
    return sorted(rules, key=lambda r: (r["kind"] != "base", r.get("category") or "", -r["specificity"], r["name"],
                                        r.get("version_from") or ""))


@pricing_router.get("/rules/{rule_id}/history")
async def pricing_rule_history(rule_id: str, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    r = await _raw_db.price_rules.find_one({"id": rule_id, "company_id": me["company_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Regel ikke fundet")
    g = r.get("version_group") or r["id"]
    vs = await _raw_db.price_rules.find(
        {"company_id": me["company_id"], "$or": [{"version_group": g}, {"id": g}]}, {"_id": 0}).to_list(500)
    return sorted(vs, key=lambda v: v.get("version_from") or "", reverse=True)


@pricing_router.post("/rules")
async def pricing_create_rule(body: dict, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    doc = {**_clean_rule(body), "id": rid, "version_group": rid, "company_id": me["company_id"],
           "created_at": now, "updated_at": now, "updated_by": me.get("name") or me.get("email"),
           "version_from": _effective_ts(body.get("effective"))}
    await _raw_db.price_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@pricing_router.put("/rules/{rule_id}")
async def pricing_update_rule(rule_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    """2026-10-17: En ændring laver en NY version fra et valgt tidspunkt
    (standard: nu). Den gamle version lukkes, så eksisterende ture beholder
    deres pris. effective="all" retter versionen direkte (også bagudrettet)."""
    me = await _pricing_caller(payload)
    old = await _raw_db.price_rules.find_one({"id": rule_id, "company_id": me["company_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(status_code=404, detail="Regel ikke fundet")
    now = datetime.now(timezone.utc).isoformat()
    who = me.get("name") or me.get("email")
    clean = _clean_rule(body)
    eff = _effective_ts(body.get("effective"))
    old_vf = _parse_ts(old.get("version_from") or "")
    if eff is None or (old_vf and old_vf >= _parse_ts(eff)):
        # Bagudrettet rettelse - eller versionen er ikke trådt i kraft endnu.
        upd = {**clean, "updated_at": now, "updated_by": who}
        if eff is not None:
            # Flyt versionens start tilbage til den valgte dato, og luk den
            # forrige version samme tidspunkt.
            upd["version_from"] = eff
            if old.get("previous_id"):
                await _raw_db.price_rules.update_one({"id": old["previous_id"]}, {"$set": {"version_to": eff}})
        await _raw_db.price_rules.update_one({"id": rule_id}, {"$set": upd})
        return await _raw_db.price_rules.find_one({"id": rule_id}, {"_id": 0})
    new_id = str(uuid.uuid4())
    doc = {**old, **clean, "id": new_id, "version_group": old.get("version_group") or old["id"],
           "previous_id": old["id"], "version_from": eff, "version_to": old.get("version_to"),
           "created_at": now, "updated_at": now, "updated_by": who}
    if not doc.get("version_to"):
        doc.pop("version_to", None)
    await _raw_db.price_rules.update_one({"id": rule_id}, {"$set": {
        "version_to": eff, "version_group": doc["version_group"], "replaced_by": new_id}})
    await _raw_db.price_rules.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@pricing_router.delete("/rules/{rule_id}")
async def pricing_delete_rule(rule_id: str, effective: str = "now", payload: dict = Depends(get_current_user_payload)):
    """Standard: reglen ophører fra nu (eksisterende ture beholder prisen).
    effective=all: slettes helt (også for eksisterende ture)."""
    me = await _pricing_caller(payload)
    r = await _raw_db.price_rules.find_one({"id": rule_id, "company_id": me["company_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Regel ikke fundet")
    eff = _effective_ts(effective)
    vf = _parse_ts(r.get("version_from") or "")
    if eff is None or (vf and vf >= _parse_ts(eff)):
        await _raw_db.price_rules.delete_one({"id": rule_id})
        return {"success": True, "deleted": True}
    await _raw_db.price_rules.update_one({"id": rule_id}, {"$set": {"version_to": eff, "retired": True}})
    return {"success": True, "retired_from": eff}


@pricing_router.post("/import-legacy")
async def pricing_import_legacy(payload: dict = Depends(get_current_user_payload)):
    """Konverterer den gamle prisliste (plads + fraktion + haster-gebyr)."""
    me = await _pricing_caller(payload)
    cid = me["company_id"]
    old = await _raw_db.tour_prices.find({"company_id": cid}, {"_id": 0}).to_list(5000)
    if not old:
        raise HTTPException(status_code=404, detail="Ingen gamle priser at importere")
    plads = {p["name"].lower(): p.get("location_code") for p in await _raw_db.plads.find(
        {}, {"_id": 0, "name": 1, "location_code": 1}).to_list(10000) if p.get("name")}
    now = datetime.now(timezone.utc).isoformat()
    made = 0
    for p in old:
        code = plads.get((p.get("plads") or "").lower())
        kind = p.get("kind") or "material"
        cond = {k: [] for k in _COND_LISTS}
        cond.update({"location_codes": [code] if code else [], "trailer": "", "outcome": "completed",
                     "time_from": "", "time_to": ""})
        if kind in ("flyt", "vaerksted"):
            cond["task_types"] = [kind]
        elif p.get("fraction"):
            cond["materials"] = [p["fraction"]]
        name = f"{p.get('plads')} · {p.get('fraction') or _pricing.TASK_TYPES.get(kind, kind)}"
        await _raw_db.price_rules.insert_one({
            "id": str(uuid.uuid4()), "company_id": cid, "kind": "base", "name": name[:80],
            "conditions": cond, "pricing": {"model": "fixed", "amount": float(p.get("price") or 0)},
            "surcharge": {}, "category": "", "active": True, "note": "Importeret fra gammel prisliste",
            "valid_from": "", "valid_to": "", "created_at": now, "updated_at": now,
            "updated_by": me.get("name") or "",
        })
        made += 1
    comp = await _raw_db.companies.find_one({"id": cid}, {"_id": 0, "haster_fee": 1}) or {}
    fee = comp.get("haster_fee")
    if fee:
        cond = {k: [] for k in _COND_LISTS}
        cond.update({"priorities": ["haster"], "trailer": "", "outcome": "completed",
                     "time_from": "", "time_to": ""})
        await _raw_db.price_rules.insert_one({
            "id": str(uuid.uuid4()), "company_id": cid, "kind": "surcharge", "category": "haster",
            "name": "Haster-tillæg", "conditions": cond, "pricing": {},
            "surcharge": {"unit": "kr", "value": float(fee)}, "active": True,
            "note": "Importeret fra gammel prisliste", "valid_from": "", "valid_to": "",
            "created_at": now, "updated_at": now, "updated_by": me.get("name") or "",
        })
        made += 1
    return {"created": made}


# ----- Rapport + tur-detaljer ----------------------------------------------
async def _pending_counts(tour_ids: list) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if tour_ids:
        for r in await _raw_db.tour_change_requests.find(
            {"tour_id": {"$in": tour_ids}, "status": "pending"}, {"_id": 0, "tour_id": 1},
        ).to_list(20000):
            out[r["tour_id"]] = out.get(r["tour_id"], 0) + 1
    return out


@pricing_router.get("/report")
async def pricing_report(date_from: str, date_to: str, customer_id: str = "", location_code: str = "",
                         payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    cid = me["company_id"]
    try:
        _date.fromisoformat(date_from); _date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ugyldig periode")
    tours = await _billable_tours(cid, date_from, date_to)
    settings = await _price_settings(cid)
    ctx = _PricingContext(cid, settings, await _active_rules(cid))
    await ctx.load(tours)
    if customer_id:
        tours = [t for t in tours if ctx.customer_key(t) == customer_id]
    if location_code:
        tours = [t for t in tours if ctx.location_code(t) == location_code]
    pending = await _pending_counts([t["id"] for t in tours])
    rows = sorted((_report_row(ctx, t, pending) for t in tours),
                  key=lambda r: (r["service_date"], r["start_time"] or ""), reverse=True)
    priced = [r for r in rows if r["price"].get("total") is not None]
    net = round(sum(r["price"]["total"] for r in priced), 2)
    vat = round(net * float(settings.get("vat_percent") or 0) / 100, 2)
    by_customer: Dict[str, dict] = {}
    for r in rows:
        b = by_customer.setdefault(r["customer_id"], {"customer_id": r["customer_id"],
                                                      "customer_name": r["customer_name"],
                                                      "tours": 0, "net": 0.0, "missing": 0})
        b["tours"] += 1
        if r["price"].get("total") is None:
            b["missing"] += 1
        else:
            b["net"] = round(b["net"] + r["price"]["total"], 2)
    billable_min = sum((r["price"].get("time") or {}).get("billable_min") or 0 for r in priced)
    return {
        "rows": rows,
        "totals": {
            "tours": len(rows), "net": net, "vat": vat, "gross": round(net + vat, 2),
            "vat_percent": settings.get("vat_percent"),
            "billable_hours": round(billable_min / 60, 2),
            "missing_rule": sum(1 for r in rows if r["price"]["status"] == "missing_rule"),
            "missing_time": sum(1 for r in rows if r["price"]["status"] == "missing_time"),
            "pending_requests": sum(r["pending_requests"] for r in rows),
            "invoiced": sum(1 for r in rows if r["price"].get("locked")),
            "not_completed": sum(1 for r in rows if r["outcome"] == "not_completed"),
        },
        "by_customer": sorted(by_customer.values(), key=lambda b: -b["net"]),
    }


async def _owned_tour(cid: str, tour_id: str) -> dict:
    t = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "receipt_image": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    drivers = await _my_drivers(cid)
    if not ({d["id"] for d in drivers} & {t.get("claimed_by_id")}
            or {d["name"] for d in drivers} & {t.get("claimed_by"), t.get("not_completed_by_name")}):
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    return t


@pricing_router.get("/tours/{tour_id}")
async def pricing_tour_detail(tour_id: str, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    t = await _owned_tour(me["company_id"], tour_id)
    ctx = _PricingContext(me["company_id"], await _price_settings(me["company_id"]),
                          await _active_rules(me["company_id"]))
    await ctx.load([t])
    row = _report_row(ctx, t, await _pending_counts([tour_id]))
    requests = await _raw_db.tour_change_requests.find(
        {"tour_id": tour_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {**row, "original": {"start_time": t.get("on_way_time") or "",
                                "end_time": t.get("time") if t.get("completed") else "",
                                "used_trailer": t.get("used_trailer")},
            "fact_overrides": t.get("fact_overrides") or {},
            "price_override": t.get("price_override") or {},
            "history": t.get("price_history") or [], "requests": requests}


@pricing_router.put("/tours/{tour_id}/adjust")
async def pricing_adjust_tour(tour_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    t = await _owned_tour(me["company_id"], tour_id)
    if t.get("price_locked"):
        raise HTTPException(status_code=409, detail="Turen er faktureret. Fjern markeringen før du ændrer.")
    note = str(body.get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Skriv en kort begrundelse")
    fo_in = body.get("fact_overrides") or {}
    fo: Dict[str, Any] = {}
    for k in ("start_time", "end_time"):
        v = str(fo_in.get(k) or "").strip()
        if v:
            if _pricing.hhmm_to_min(v) < 0:
                raise HTTPException(status_code=400, detail="Tid skal være TT:MM")
            fo[k] = v
    if fo_in.get("used_trailer") in (True, False):
        fo["used_trailer"] = fo_in["used_trailer"]
    if fo_in.get("deduct_pause") in (True, False):
        fo["deduct_pause"] = fo_in["deduct_pause"]
    if fo_in.get("waiting_min") not in (None, ""):
        fo["waiting_min"] = max(0, int(float(fo_in["waiting_min"])))
    po_in = body.get("price_override") or {}
    po: Dict[str, Any] = {"mode": "fixed" if po_in.get("mode") == "fixed" else "rules"}
    if po["mode"] == "fixed":
        try:
            po["amount"] = float(po_in.get("amount"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Angiv det faste beløb")
        # 2026-10-17: Bevar "Aftalt pris" og valget om ventetid oveni når en
        # aftalt pris rettes (før blev den til en almindelig "Manuel pris").
        prev = t.get("price_override") or {}
        po["label"] = str(po_in.get("label") or prev.get("label") or "Manuel pris")[:40]
        aw = po_in.get("add_waiting", prev.get("add_waiting"))
        if aw is not None:
            po["add_waiting"] = bool(aw)
    po["extra_lines"] = [{"label": str(x.get("label") or "Ekstra").strip()[:60],
                          "amount": float(x.get("amount") or 0)}
                         for x in (po_in.get("extra_lines") or []) if str(x.get("label") or "").strip()]
    hist = {"at": datetime.now(timezone.utc).isoformat(), "by": me.get("name") or me.get("email"),
            "note": note[:300], "kind": "admin", "fact_overrides": fo, "price_override": po}
    await _raw_db.tours.update_one({"id": tour_id}, {
        "$set": {"fact_overrides": fo, "price_override": po}, "$push": {"price_history": hist}})
    return await pricing_tour_detail(tour_id, payload)


@pricing_router.post("/invoice")
async def pricing_mark_invoiced(body: dict, payload: dict = Depends(get_current_user_payload)):
    """Markér ture som faktureret (prisen fryses) — eller fjern markeringen."""
    me = await _pricing_caller(payload)
    cid = me["company_id"]
    ids = [str(x) for x in (body.get("tour_ids") or [])][:5000]
    if not ids:
        raise HTTPException(status_code=400, detail="Ingen ture valgt")
    tours = []
    for tid in ids:
        tours.append(await _owned_tour(cid, tid))
    if not body.get("invoiced", True):
        await _raw_db.tours.update_many({"id": {"$in": ids}}, {"$unset": {"price_locked": ""}})
        return {"updated": len(ids)}
    ctx = _PricingContext(cid, await _price_settings(cid), await _active_rules(cid))
    await ctx.load(tours)
    now, by = datetime.now(timezone.utc).isoformat(), me.get("name") or me.get("email")
    done, skipped = 0, 0
    for t in tours:
        if t.get("price_locked"):
            continue
        p = ctx.price(t)
        if p.get("total") is None:
            skipped += 1
            continue
        snap = {k: p.get(k) for k in ("status", "model", "base_rule", "lines", "time", "total", "flags")}
        snap.update({"invoiced_at": now, "invoiced_by": by})
        await _raw_db.tours.update_one({"id": t["id"]}, {"$set": {"price_locked": snap}})
        done += 1
    return {"updated": done, "skipped_without_price": skipped}


# ----- Godkendelser (chaufførens rettelser) --------------------------------
@pricing_router.get("/requests")
async def pricing_list_requests(status: str = "pending", payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    q: Dict[str, Any] = {"company_id": me["company_id"]}
    if status != "all":
        q["status"] = status
    return await _raw_db.tour_change_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@pricing_router.post("/requests/{req_id}/decide")
async def pricing_decide_request(req_id: str, body: dict, payload: dict = Depends(get_current_user_payload)):
    me = await _pricing_caller(payload)
    r = await _raw_db.tour_change_requests.find_one({"id": req_id, "company_id": me["company_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Anmodning ikke fundet")
    if r.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Anmodningen er allerede behandlet")
    approve = bool(body.get("approve"))
    note = str(body.get("note") or "").strip()[:300]
    if not approve and not note:
        raise HTTPException(status_code=400, detail="Skriv hvorfor anmodningen afvises")
    now, by = datetime.now(timezone.utc).isoformat(), me.get("name") or me.get("email")
    if approve:
        t = await _owned_tour(me["company_id"], r["tour_id"])
        if t.get("price_locked"):
            raise HTTPException(status_code=409, detail="Turen er faktureret. Fjern markeringen før du godkender.")
        fo = {**(t.get("fact_overrides") or {}), **(r.get("changes") or {})}
        await _raw_db.tours.update_one({"id": r["tour_id"]}, {
            "$set": {"fact_overrides": fo},
            "$push": {"price_history": {"at": now, "by": by, "kind": "driver_request",
                                        "note": f"Godkendt rettelse fra {r.get('driver_name')}: {r.get('comment')}",
                                        "fact_overrides": r.get("changes")}}})
    await _raw_db.tour_change_requests.update_one({"id": req_id}, {"$set": {
        "status": "approved" if approve else "rejected", "decided_at": now, "decided_by": by,
        "decision_note": note}})
    return await _raw_db.tour_change_requests.find_one({"id": req_id}, {"_id": 0})


app.include_router(pricing_router)


# ----- Chaufføren: prisinfo (uden beløb), hænger pr. tur, rettelser ---------
async def _driver_doc(payload: dict) -> dict:
    u = await _raw_db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "id": 1, "name": 1, "company_id": 1})
    if not u:
        raise HTTPException(status_code=401, detail="Bruger ikke fundet")
    return u


async def _driver_own_tour(me: dict, tour_id: str) -> dict:
    t = await _raw_db.tours.find_one({"id": tour_id}, {"_id": 0, "receipt_image": 0})
    if not t or not (t.get("claimed_by_id") == me["id"] or (me.get("name") and t.get("claimed_by") == me["name"])):
        raise HTTPException(status_code=404, detail="Tur ikke fundet")
    return t


@api_router.get("/driver/tour-pricing")
async def driver_tour_pricing(ids: str, payload: dict = Depends(require_role("driver"))):
    """Hvordan turen afregnes — prismodel, timepris og pause-regel. Chaufføren
    ser aldrig faste priser, tillæg eller totaler."""
    me = await _driver_doc(payload)
    tour_ids = [x for x in ids.split(",") if x][:200]
    tours = await _raw_db.tours.find({"id": {"$in": tour_ids}}, {"_id": 0, "receipt_image": 0}).to_list(200)
    rules = await _active_rules(me["company_id"])
    ctx = _PricingContext(me["company_id"], await _price_settings(me["company_id"]), rules)
    await ctx.load(tours)
    pending = await _pending_counts(tour_ids)
    reqs = await _raw_db.tour_change_requests.find(
        {"tour_id": {"$in": tour_ids}}, {"_id": 0, "tour_id": 1, "status": 1, "created_at": 1,
                                         "decision_note": 1}).sort("created_at", -1).to_list(1000)
    latest: Dict[str, dict] = {}
    for r in reqs:
        latest.setdefault(r["tour_id"], r)
    out = {}
    for t in tours:
        base, _s = _pricing.select_rules(ctx.rules_for(t), ctx.attrs(t))
        po = t.get("price_override") or {}
        info: Dict[str, Any] = {"model": None}
        if po.get("mode") == "fixed":
            info = {"model": "fixed"}
        elif base:
            p = base.get("pricing") or {}
            info = {"model": p.get("model")}
            if p.get("model") == "hourly":
                info.update({"hourly_rate": p.get("hourly_rate"),
                             "deduct_pause": (t.get("fact_overrides") or {}).get("deduct_pause",
                                                                                 p.get("deduct_pause", True)),
                             "rounding": _pricing.rounding_label(p),
                             "min_minutes": p.get("min_minutes") or 0})
        info["used_trailer"] = _fact(t, "used_trailer", t.get("used_trailer"))
        info["pending_requests"] = pending.get(t["id"], 0)
        info["last_request"] = latest.get(t["id"])
        info["invoiced"] = bool(t.get("price_locked"))
        out[t["id"]] = info
    return out


@api_router.put("/driver/tours/{tour_id}/trailer")
async def driver_set_trailer(tour_id: str, body: dict, payload: dict = Depends(require_role("driver"))):
    me = await _driver_doc(payload)
    t = await _driver_own_tour(me, tour_id)
    if t.get("completed"):
        raise HTTPException(status_code=409, detail="Turen er afsluttet - brug 'Ret tur' for at anmode om ændring")
    await _raw_db.tours.update_one({"id": tour_id}, {"$set": {"used_trailer": bool(body.get("used_trailer"))}})
    return {"used_trailer": bool(body.get("used_trailer"))}


@api_router.post("/driver/tours/{tour_id}/change-request")
async def driver_change_request(tour_id: str, body: dict, payload: dict = Depends(require_role("driver"))):
    me = await _driver_doc(payload)
    t = await _driver_own_tour(me, tour_id)
    if not t.get("completed"):
        raise HTTPException(status_code=409, detail="Rettelser kan kun anmodes om på afsluttede ture")
    if t.get("price_locked"):
        raise HTTPException(status_code=409, detail="Turen er allerede faktureret - kontakt din logistik admin")
    if await _raw_db.tour_change_requests.find_one({"tour_id": tour_id, "status": "pending"}):
        raise HTTPException(status_code=409, detail="Der er allerede en rettelse til godkendelse på denne tur")
    comment = str(body.get("comment") or "").strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Skriv hvad der skal rettes og hvorfor")
    changes: Dict[str, Any] = {}
    cur_start, cur_end = _tour_times(t)
    for k, cur in (("start_time", cur_start), ("end_time", cur_end)):
        v = str(body.get(k) or "").strip()
        if v and v != cur:
            if _pricing.hhmm_to_min(v) < 0:
                raise HTTPException(status_code=400, detail="Tid skal være TT:MM")
            changes[k] = v
    if body.get("used_trailer") in (True, False) and body["used_trailer"] != bool(
            _fact(t, "used_trailer", t.get("used_trailer"))):
        changes["used_trailer"] = body["used_trailer"]
    if body.get("waiting_min") not in (None, ""):
        w = max(0, int(float(body["waiting_min"])))
        if w != int(_fact(t, "waiting_min", 0) or 0):
            changes["waiting_min"] = w
    if not changes:
        raise HTTPException(status_code=400, detail="Du har ikke ændret noget")
    logi = me["company_id"]
    doc = {
        "id": str(uuid.uuid4()), "tour_id": tour_id, "company_id": logi,
        "tour_number": t.get("tour_number") or "", "tour_label": f"{t.get('fraction', '')} · {t.get('plads', '')}",
        "service_date": _service_date(t), "driver_id": me["id"], "driver_name": me.get("name") or "",
        "before": {"start_time": cur_start, "end_time": cur_end,
                   "used_trailer": bool(_fact(t, "used_trailer", t.get("used_trailer"))),
                   "waiting_min": int(_fact(t, "waiting_min", 0) or 0)},
        "changes": changes, "comment": comment[:500], "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _raw_db.tour_change_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc




app.include_router(api_router)
app.include_router(sa_router)
app.include_router(genbrug_router)
app.include_router(org_router)

# Tenant middleware MUST be added before CORS so it runs after CORS in the request flow.
app.add_middleware(TenantContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Production SPA serving ──────────────────────────────────────────────
# When the React build is baked into the container (see Dockerfile), serve it
# from the same origin. API routes above always take precedence; any other
# path falls back to index.html so client-side routing works.
_FRONTEND_BUILD = os.environ.get(
    "FRONTEND_BUILD_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend_build"),
)
if os.path.isdir(_FRONTEND_BUILD):
    from fastapi.responses import FileResponse

    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(_FRONTEND_BUILD, "static")),
        name="spa-static",
    )

    # 2026-10-16: index.html, service-worker.js og manifest skal altid
    # revalideres, ellers kører browsere (chaufførernes telefoner) videre på
    # den gamle version efter et deploy. /static/* har hash i filnavnet og
    # må gerne caches.
    _NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = os.path.join(_FRONTEND_BUILD, full_path)
        if full_path and os.path.isfile(candidate):
            if full_path.endswith((".html", "service-worker.js", "manifest.json")):
                return FileResponse(candidate, headers=_NO_CACHE)
            return FileResponse(candidate)
        return FileResponse(os.path.join(_FRONTEND_BUILD, "index.html"), headers=_NO_CACHE)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    logger.info("Shutting down ContainerFlow backend...")
    client.close()

# Auto-cleanup: delete tours older than 60 days, receipts based on per-company retention
async def cleanup_old_tours():
    """Delete old tours + receipts using per-customer retention (Fase 16)."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        result = await db.tours.delete_many({"created_at": {"$lt": cutoff}})
        if result.deleted_count > 0:
            logger.info(f"Auto-cleanup: deleted {result.deleted_count} tours older than 60 days")

        # Per-customer receipt retention. Receipt.customer_company_id points to
        # the customer (kunde) company; we look up that company's
        # `receipt_retention_days` and delete receipts older than that.
        # Falls back to default 1095 days (3 years) when missing.
        deleted_receipts = 0
        try:
            companies = await _raw_db.companies.find(
                {}, {"_id": 0, "id": 1, "receipt_retention_days": 1}
            ).to_list(2000)
            company_retention = {
                c["id"]: int(c.get("receipt_retention_days") or 1095)
                for c in companies
                if c.get("id")
            }
            # Group deletes per retention horizon to minimise DB calls.
            now = datetime.now(timezone.utc)
            for company_id, days in company_retention.items():
                horizon = (now - timedelta(days=days)).isoformat()
                r = await _raw_db.receipts.delete_many({
                    "customer_company_id": company_id,
                    "created_at": {"$lt": horizon},
                })
                deleted_receipts += r.deleted_count
            # Receipts without customer_company_id (legacy) — apply default 1095d.
            default_horizon = (now - timedelta(days=1095)).isoformat()
            r2 = await _raw_db.receipts.delete_many({
                "$or": [
                    {"customer_company_id": {"$exists": False}},
                    {"customer_company_id": ""},
                ],
                "created_at": {"$lt": default_horizon},
            })
            deleted_receipts += r2.deleted_count
        except Exception as e:
            logger.error(f"Receipt retention cleanup error: {e}")

        if deleted_receipts > 0:
            logger.info(
                f"Auto-cleanup: deleted {deleted_receipts} receipts (per-company retention)"
            )
    except Exception as e:
        logger.error(f"Auto-cleanup error: {e}")

async def periodic_cleanup():
    """Run cleanup every 24 hours."""
    while True:
        await cleanup_old_tours()
        await async_lib.sleep(86400)  # 24 hours


# Fase 15.36 (2026-02-22): Automatisk søndags-aften påmindelse til chauffører
# der har åbne (missing_clock) tidsregistreringer i de seneste 7 dage. Sendes
# hver søndag kl. 18:00 Europe/Copenhagen.
def _seconds_until_next_sunday_1800() -> float:
    tz = ZoneInfo("Europe/Copenhagen")
    now = datetime.now(tz)
    # weekday(): Mon=0 … Sun=6
    days_ahead = (6 - now.weekday()) % 7
    target = now.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    if target <= now:
        target = target + timedelta(days=7)
    return max(1.0, (target - now).total_seconds())


async def sunday_evening_reminder_task():
    """Background loop: sov indtil næste søndag 18:00 Europe/Copenhagen, send
    påmindelser til alle chauffører på tværs af firmaer, gentag.

    Implementeret uden APScheduler — én simpel async loop er nok.
    """
    while True:
        try:
            wait_s = _seconds_until_next_sunday_1800()
            logger.info(
                "sunday_reminder: sleeping %.0fs (%.1fh) until next Sunday 18:00 Europe/Copenhagen",
                wait_s, wait_s / 3600.0,
            )
            await async_lib.sleep(wait_s)
            try:
                result = await send_weekly_missing_clock_reminders(days_back=7)
                logger.info(
                    "sunday_reminder: sent=%d skipped=%d",
                    result.get("sent", 0), result.get("skipped", 0),
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("sunday_reminder: send failed: %s", e)
            # Sov 90 sekunder før vi beregner næste søndag, så vi undgår at
            # ramme samme minut to gange.
            await async_lib.sleep(90)
        except async_lib.CancelledError:
            logger.info("sunday_reminder: cancelled")
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("sunday_reminder: loop error: %s — retrying in 10 min", e)
            await async_lib.sleep(600)


# Startup: create DB indexes
@app.on_event("startup")
async def startup_db_client():
    logger.info("Starting ContainerFlow backend...")
    logger.info(f"MONGO_URL: {mongo_url[:30]}...")
    logger.info(f"Python version: {os.sys.version}")
    try:
        # Test MongoDB connection first with timeout
        await async_lib.wait_for(db.command("ping"), timeout=10)
        logger.info("MongoDB connection successful")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        return  # Server starts but DB operations will fail gracefully
    try:
        await db.tours.create_index("date")
        await db.tours.create_index("plads")
        await db.tours.create_index("driver_id")
        await db.tours.create_index("driver_name")
        await db.tours.create_index("claimed_by")
        await db.reports.create_index("report_date")
        await db.reports.create_index("driver_id")
        await db.driver_sessions.create_index("driver_name")
        await db.driver_sessions.create_index("report_date")
        await db.receipts.create_index("driver_name")
        await db.messages.create_index("to_driver_id")
        await db.push_subscriptions.create_index("driver_name")
        await _raw_db.tour_messages.create_index("tour_id")
        await _raw_db.tour_messages.create_index([("logistics_company_id", 1), ("sender_role", 1)])
        logger.info("Database indexes created/verified")
        # Multi-tenant: seed default company, super admin, and migrate existing docs.
        await seed_multitenant_auth()
        # Run initial cleanup and start periodic background task
        await cleanup_old_tours()
        async_lib.create_task(periodic_cleanup())
        logger.info("Auto-cleanup background task started (60-day retention)")
        # Fase 15.36 (2026-02-22): Start ugentlig søndags-påmindelses-task.
        async_lib.create_task(sunday_evening_reminder_task())
        logger.info("Sunday reminder background task started (every Sunday 18:00 Europe/Copenhagen)")
        # Legacy: seed_locations() used to insert 2 demo single-tenant pladser
        # with no company_id. In the multi-tenant world they're orphans and
        # would clutter the dashboard, so we no longer auto-seed locations.
        # Customers create their own pladser via the customer-admin UI.
        # Migrate dates to YYYY-MM-DD format
        await migrate_dates()
    except Exception as e:
        logger.warning(f"Startup tasks warning: {e}")


async def seed_multitenant_auth():
    """Create default company, super admin user, and migrate existing data to default company."""
    try:
        # Indexes for auth collections.
        # NOTE: email is intentionally NOT unique anymore — this is a multi-tenant
        # platform and the same person (e.g. a logistics admin) may be invited
        # by multiple customers with their own per-customer password. Login
        # disambiguates by trying every user with that email and matching the
        # password.
        try:
            await _raw_db.users.drop_index("email_1")
        except Exception:
            pass  # index didn't exist
        await _raw_db.users.create_index("email")  # non-unique, just for lookup speed
        await _raw_db.users.create_index("company_id")
        await _raw_db.companies.create_index("name", unique=True)
        await _raw_db.companies.create_index("id", unique=True)

        # Default company seeding is INTENTIONALLY DISABLED.
        # The platform is now strictly multi-tenant — the system owner explicitly
        # creates each customer/logistics firm through the SuperAdmin UI. Seeding
        # a synthetic "Default Company" pollutes the empty dashboard the owner
        # wants to start from.
        # (Legacy data migration has been completed; nothing references the
        # default id any more for fresh data flows.)

        # Seed super admin (only if it doesn't exist AND no other super_admin
        # exists either — the platform owner asked us to keep ONLY their own
        # super-admin account on a clean install, so we don't recreate the
        # platform-default account on every startup).
        sa_email = (os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@platform.com") or "").strip().lower()
        sa_password = os.environ.get("SUPER_ADMIN_PASSWORD", "SuperAdmin2026!")
        any_super = await _raw_db.users.find_one({"role": "super_admin"})
        if not any_super:
            await _raw_db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": sa_email,
                "name": "Super Admin",
                "role": "super_admin",
                "company_id": SUPER_ADMIN_BYPASS,
                "active": True,
                "password_hash": hash_password(sa_password),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"Super admin seeded: {sa_email}")

        # NOTE: legacy admin@default.local / driver@default.local / etc are NO
        # LONGER auto-seeded. Users explicitly opt-in by creating new customers
        # + admins through the SuperAdmin UI. This keeps the environment clean
        # so statistics reflect REAL data, not seeded samples.
    except Exception as e:
        logger.error(f"seed_multitenant_auth error: {e}")

async def migrate_dates():
    """One-time migration: convert all DD-MM-YYYY dates to YYYY-MM-DD."""
    cursor = db.tours.find({"date": {"$regex": r"^\d{1,2}-\d{1,2}-\d{4}$"}}, {"_id": 1, "date": 1})
    count = 0
    async for doc in cursor:
        old_date = doc["date"]
        new_date = normalize_date(old_date)
        if new_date != old_date:
            await db.tours.update_one({"_id": doc["_id"]}, {"$set": {"date": new_date}})
            count += 1
    if count > 0:
        logger.info(f"Migrated {count} tour dates from DD-MM-YYYY to YYYY-MM-DD")
