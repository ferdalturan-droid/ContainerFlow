"""Det testene har brug for ud over seed_local.py (2026-10-19).

Testene kører i deres egen, friske database (./scripts/e2e.sh). Det, som før
kun fandtes fordi nogen havde oprettet det i hånden i den lokale database,
oprettes her: ILK's koordinator, ILK's egen lokation (premium), kunden "Life"
og en partner nr. 2 på Folehaven (City Container, med sit eget materiale)."""
import sys
import uuid
from datetime import datetime, timezone

from _e2e import ILK_ADMIN, PW, db

ILK_COORD = "ferdalturan+ilk.koordinator@gmail.com"


def ensure():
    sys.path.insert(0, "/app/backend")
    from auth import hash_password  # noqa: E402
    now = datetime.now(timezone.utc).isoformat()
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    if not db.users.find_one({"email": ILK_COORD}):
        db.users.insert_one({
            "id": str(uuid.uuid4()), "email": ILK_COORD, "name": "Kim Koordinator", "phone": "", "role": "logistics_admin",
            "is_coordinator": True, "company_id": ilk, "active": True, "invitation_status": "active",
            "password_hash": hash_password(PW), "managed_company_ids": [], "assigned_plads_ids": [], "visible_plads_ids": [],
            "customer_scope": [], "created_at": now,
            "permissions": {"tours_edit": True, "tours_assign": True, "tours_delete": False, "messages": True, "planning": True,
                            "drivers": False, "reports": False, "economy_view": False, "economy_edit": False,
                            "locations": False, "archive": False, "settings": False, "team": False}})
    if not db.plads.find_one({"name": "Arla Ishøj"}):
        db.plads.insert_one({"id": str(uuid.uuid4()), "name": "Arla Ishøj", "address": "Industrivej 22", "city": "Ishøj",
                             "location_code": "1470", "company_id": ilk, "own_location": True, "active": True,
                             "assigned_logistics_company_ids": [ilk], "materials": [], "created_at": now})
    if not db.logistics_customers.find_one({"company_id": ilk, "name": "Life"}):
        db.logistics_customers.insert_one({"id": str(uuid.uuid4()), "company_id": ilk, "name": "Life", "active": True,
                                           "created_at": now})
    city = (db.companies.find_one({"name": "City Container"}, {"_id": 0, "id": 1}) or {}).get("id")
    pl = db.plads.find_one({"location_code": "1121"}, {"_id": 0, "id": 1, "assigned_logistics_company_ids": 1,
                                                       "partner_materials": 1, "materials": 1})
    if city and pl and city not in (pl.get("assigned_logistics_company_ids") or []):
        pm = dict(pl.get("partner_materials") or {})
        pm.setdefault(ilk, list(pl.get("materials") or ["Pap", "Papir", "Glas", "Metal", "Haveaffald", "Restaffald"]))
        pm[city] = ["Beton", "Pap"]
        db.plads.update_one({"id": pl["id"]}, {"$addToSet": {"assigned_logistics_company_ids": city},
                                               "$set": {"partner_materials": pm}})
