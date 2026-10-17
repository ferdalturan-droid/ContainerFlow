"""
Auth module - JWT, bcrypt, multi-tenant context.

Extends the existing system WITHOUT modifying existing endpoints by using:
  - JWT bearer tokens (Authorization header)
  - A request-scoped ContextVar that holds the current company_id
  - A tenant-aware DB wrapper in server.py that auto-injects company_id

Roles: super_admin, customer_admin, location_admin, logistics_admin, driver, order, genbrug_plads

Hierarchy (see HIERARCHY_SPEC.md):
  super_admin    -> system owner (platform). Creates customer & logistics orgs.
  customer_admin -> org-wide admin of a CUSTOMER company (e.g. ARGO / Jørgen).
                    Creates locations, location_admins, links logistics partners.
  location_admin -> admin of ONE location inside a customer company (e.g. KØGE).
                    Creates employees (order users) + containers for that site.
  order          -> site employee that places container-pickup orders.
  logistics_admin-> admin of a LOGISTICS company (e.g. ILK). Creates drivers/trucks.
  driver         -> driver in a logistics company.
"""
from __future__ import annotations
import os
import uuid
import bcrypt
import jwt
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from fastapi import HTTPException, Header, Depends

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
JWT_ALGORITHM = "HS256"
DEFAULT_COMPANY_ID = "default"
SUPER_ADMIN_BYPASS = "*"  # contextvar value used to bypass tenant filter

VALID_ROLES = {
    "super_admin", "customer_admin", "location_admin",
    "logistics_admin", "driver", "order", "genbrug_plads",
}

# Company kinds (Company.company_type)
COMPANY_TYPE_CUSTOMER = "customer"
COMPANY_TYPE_LOGISTICS = "logistics"
VALID_COMPANY_TYPES = {COMPANY_TYPE_CUSTOMER, COMPANY_TYPE_LOGISTICS}

# --------------------------------------------------------------------------- #
# Context variable (per-request)
# --------------------------------------------------------------------------- #
# Holds the company_id used for automatic tenant filtering.
current_company_id: ContextVar[str] = ContextVar("current_company_id", default=DEFAULT_COMPANY_ID)
current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)
current_user_role: ContextVar[Optional[str]] = ContextVar("current_user_role", default=None)
# Extra companies the current user can READ from (in addition to current_company_id).
# Populated for driver / order / genbrug_plads when their primary company has
# Company.serves_company_ids set — they see merged data across those companies.
# WRITES always go to current_company_id (the primary).
current_extra_visible_company_ids: ContextVar[List[str]] = ContextVar(
    "current_extra_visible_company_ids", default=[]
)


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET not set in environment")
    return secret


def get_jwt_expiry_hours() -> int:
    try:
        return int(os.environ.get("JWT_EXPIRY_HOURS", "24"))
    except ValueError:
        return 24


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(
    user_id: str,
    email: str,
    role: str,
    company_id: str,
    managed_company_ids: Optional[List[str]] = None,
) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "company_id": company_id,
        "managed_company_ids": list(managed_company_ids or []),
        "exp": datetime.now(timezone.utc) + timedelta(hours=get_jwt_expiry_hours()),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token udløbet - log venligst ind igen")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Ugyldig token")


# --------------------------------------------------------------------------- #
# Pydantic Models
# --------------------------------------------------------------------------- #
class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str = ""  # short identifier
    # System owner can attach an external/CRM identifier visible only at the
    # super_admin level. Free text, optional.
    customer_id: Optional[str] = None
    # "customer" (buys the service, has locations) or "logistics" (provides trucks/drivers)
    company_type: str = COMPANY_TYPE_CUSTOMER
    active: bool = True
    haster_fee: float = 200.0  # per-company surcharge added to urgent (haster) tours
    # List of OTHER company IDs that THIS company performs work on behalf of.
    # All non-admin members of this company (driver / order / genbrug_plads)
    # will see data merged from their own company AND every company in this
    # list. Example: FORSYNING.serves_company_ids = [VestforbraendingId] means
    # FORSYNING's drivers/order users see tours+pladser from both.
    serves_company_ids: List[str] = Field(default_factory=list)
    # Phone number of the customer's first admin (captured at creation, surfaced
    # in the SuperAdmin overview panel — for support / license-renewal calls).
    admin_phone: str = ""
    # `from_library` marks logistics partners created via the dedicated
    # "Tilføj logistik partner" library tab on the SuperAdmin page. Library
    # entries are hidden from the regular "Kunder & Logistik" listing so the
    # two collections stay independent — but they're still surfaced in the
    # customer-admin partner-picker so they can be linked to a customer.
    from_library: bool = False
    # Holiday group that location admins inherit when creating new holiday
    # calendars. Optional — when null/empty the calendar starts empty.
    holiday_group_id: Optional[str] = None
    # Fase 15.14 (2026-02-XX): Konfigurerbar lønperiode pr. logistik-firma.
    # Fase 15.15 (2026-02-XX): Udvidet med cyklus-type (monthly/biweekly/weekly).
    # - "monthly": brug payroll_start_day (1-28). Periode = start-dag i M → (start-1) i M+1.
    # - "weekly":  brug payroll_anchor_date (ISO YYYY-MM-DD). 7-dages cyklus fra ankerdagen.
    # - "biweekly": som weekly, men 14-dages cyklus.
    # Default = monthly start 20 (matcher tidligere hardkodet adfærd).
    payroll_cycle_type: str = "monthly"
    payroll_start_day: int = 20
    payroll_anchor_date: str = ""
    # Fase 15.28 (2026-02-22): Manuel tidsregistrering — konfigurerbart krav
    # om "Årsag" pr. logistik-firma. Default = False (valgfrit) så
    # eksisterende setups ikke ændres.
    # - `require_driver_punch_reason`: gælder chaufførens "Manuel stempel"
    # - `require_admin_punch_reason`:  gælder admin's "Manuel stempel" + "Manuel tidsregistrering"
    require_driver_punch_reason: bool = False
    require_admin_punch_reason: bool = False
    # Fase 16 (2026-02-XX): Konfigurerbar opbevaringsperiode for kvitterings-
    # billeder (i dage). Default = 1095 (3 år, dansk regnskabsstandard).
    # Konfigureres pr. kunde-firma af super_admin via "Administrer dataopbevaring".
    receipt_retention_days: int = 1095
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompanyCreate(BaseModel):
    name: str
    slug: str = ""
    company_type: str = COMPANY_TYPE_CUSTOMER
    customer_id: str  # OBLIGATORISK – external/CRM identifier (Kunde-ID)
    active: Optional[bool] = True
    admin_phone: Optional[str] = None
    # When True the company is stored in the logistics-partner library and is
    # excluded from `/api/superadmin/companies?include_library=false` lists.
    from_library: Optional[bool] = False
    # Holiday group assigned at creation time (super_admin only).
    holiday_group_id: Optional[str] = None
    # Optional first-admin payload — when provided the system creates the
    # admin user with a pending invitation and emails them a 72h set-password
    # link. password is intentionally NOT accepted here.
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    customer_id: Optional[str] = None
    company_type: Optional[str] = None
    active: Optional[bool] = None
    serves_company_ids: Optional[List[str]] = None
    haster_fee: Optional[float] = None
    admin_phone: Optional[str] = None
    # The two below mutate the company's first_admin USER record (not the
    # company itself). Surfaced here so super_admins can fix typos directly
    # from the "Rediger" modal without having to dig into the users table.
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    # Holiday group assignment (super_admin only — surfaced on the company
    # create/edit modal).
    holiday_group_id: Optional[str] = None
    # Fase 15.14/15.15 (2026-02-XX): Lønperiode-felter.
    payroll_cycle_type: Optional[str] = None  # "monthly" | "biweekly" | "weekly"
    payroll_start_day: Optional[int] = None
    payroll_anchor_date: Optional[str] = None
    # Fase 15.28 (2026-02-22): Manuel tidsregistrering — krav om "Årsag".
    require_driver_punch_reason: Optional[bool] = None
    require_admin_punch_reason: Optional[bool] = None
    # Fase 16 (2026-02-XX): Per-kunde opbevaringsperiode for kvittering-billeder.
    receipt_retention_days: Optional[int] = None


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: str  # one of VALID_ROLES
    company_id: str  # which company - "*" for super_admin (cross-company)
    active: bool = True
    # Invitation lifecycle: "pending" = user invited, has not chosen a password
    # yet; "active" = password has been set (via direct create OR invitation
    # accept). Surfaced in UI as Afventer / Aktiv. password_hash is empty while
    # status is "pending".
    invitation_status: str = "active"  # "pending" | "active"
    # driver-specific binding (optional - links auth user to a Driver record)
    driver_name: Optional[str] = None
    phone: Optional[str] = None
    # driver-specific identification (added in Phase 2 — driver-as-user
    # migration). `plate` is the vehicle reg shown in the driver picker; it
    # can be empty at invitation time and filled in during first login.
    plate: Optional[str] = None
    area: Optional[str] = None
    facility: Optional[str] = None
    # order/location-admin specific: medarbejder ansættelsesdato (employee
    # start date). ISO-date string ("YYYY-MM-DD") or empty. Captured at
    # invitation/creation time by Lokation Admin.
    employment_date: Optional[str] = None
    # order-specific binding (optional - links auth user to a Location code)
    location_code: Optional[str] = None
    # logistics_admin: extra company IDs this admin is allowed to manage on
    # behalf of (cross-company). Empty for all other roles. The admin's own
    # company is implicitly always allowed.
    managed_company_ids: List[str] = Field(default_factory=list)
    # genbrug_plads-specific: HQ admin sees ALL pladser + price management.
    # Site user (is_hq_admin=False) sees ONLY pladser in assigned_plads_ids.
    is_hq_admin: bool = False
    assigned_plads_ids: List[str] = Field(default_factory=list)
    # driver-specific: when set, the driver only sees these pladser in the
    # plads picker / tour list. Empty list = see all pladser in their company
    # (the previous default behavior).
    visible_plads_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str
    company_id: str
    company_name: Optional[str] = None
    active: bool = True
    invitation_status: str = "active"  # "pending" | "active"
    driver_name: Optional[str] = None
    phone: Optional[str] = None
    plate: Optional[str] = None
    area: Optional[str] = None
    facility: Optional[str] = None
    employment_date: Optional[str] = None
    location_code: Optional[str] = None
    managed_company_ids: List[str] = Field(default_factory=list)
    is_hq_admin: bool = False
    assigned_plads_ids: List[str] = Field(default_factory=list)
    visible_plads_ids: List[str] = Field(default_factory=list)
    # Fase 10/11: Driver's active vehicle + trailer
    active_vehicle_id: Optional[str] = ""
    active_trailer_id: Optional[str] = ""
    created_at: Optional[str] = None
    # 2026-10-17: Koordinator-rettigheder (logistik). Administratorer har alle.
    is_coordinator: bool = False
    permissions: Dict[str, bool] = Field(default_factory=dict)
    customer_scope: List[str] = Field(default_factory=list)
    push_enabled: bool = True
    # Fase 15.40 (2026-02-22): Klient-platformsfunktioner — cached features
    # for brugerens klient/firma så frontend kan gate UI uden ekstra rundtur.
    features: Dict[str, bool] = Field(default_factory=dict)


class UserCreate(BaseModel):
    email: str
    name: str
    password: Optional[str] = None  # optional - if omitted, send invitation
    role: str
    company_id: str
    send_invitation: Optional[bool] = None  # explicit flag from UI
    driver_name: Optional[str] = None
    phone: Optional[str] = None
    plate: Optional[str] = None
    area: Optional[str] = None
    facility: Optional[str] = None
    employment_date: Optional[str] = None
    location_code: Optional[str] = None
    managed_company_ids: Optional[List[str]] = None
    is_hq_admin: Optional[bool] = None
    assigned_plads_ids: Optional[List[str]] = None
    visible_plads_ids: Optional[List[str]] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # plain text; will be hashed
    role: Optional[str] = None
    company_id: Optional[str] = None
    active: Optional[bool] = None
    invitation_status: Optional[str] = None
    driver_name: Optional[str] = None
    phone: Optional[str] = None
    plate: Optional[str] = None
    area: Optional[str] = None
    facility: Optional[str] = None
    employment_date: Optional[str] = None
    location_code: Optional[str] = None
    managed_company_ids: Optional[List[str]] = None
    is_hq_admin: Optional[bool] = None
    assigned_plads_ids: Optional[List[str]] = None
    visible_plads_ids: Optional[List[str]] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserPublic


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
async def get_optional_user_payload(
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    """Decode JWT if present, otherwise return None (does not raise)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


async def get_current_user_payload(
    authorization: Optional[str] = Header(None),
) -> dict:
    """Require a valid JWT. Returns the decoded payload."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Ikke logget ind")
    token = authorization.split(" ", 1)[1].strip()
    return decode_token(token)


def require_role(*allowed_roles: str):
    """Dependency factory: ensures the current user has one of the allowed roles."""
    async def _checker(payload: dict = Depends(get_current_user_payload)) -> dict:
        role = payload.get("role")
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Adgang nægtet for denne rolle")
        return payload
    return _checker


async def require_super_admin(payload: dict = Depends(get_current_user_payload)) -> dict:
    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Kun super admin har adgang")
    return payload
