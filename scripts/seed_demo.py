"""Demo-data til ContainerFlow - lokalt og på serveren (2026-10-22).

Opretter et realistisk, lille datasæt til at vise og teste systemet:
  - Kunder: Helsingør Forsyning (3 pladser) og ARGO (1 plads) med materialer,
    CO2-faktorer, containere med nummer og type, leveringsadresser, værksteder,
    åbningstider og helligdage.
  - ILK Logistics (basic) og ILK Logistics Premium (premium) med admins,
    chauffører, biler og hængere. Premium har også eget depot, egne kunder,
    en koordinator og prisaftaler (Økonomi).
  - Ture: 6 ugers historik (afsluttet, med vægt, CO2, hængerkørsler, haster,
    ventetid, varekørsel og stemplinger) + dagens ture (tildelte og ledige,
    en forsinket, værksted, varekørsel og en fast tømning).

Alt oprettes gennem appens egen API (samme kald som skærmene), så alle
forbindelser er ægte. Kun historikken dateres tilbage og afsluttes direkte i
databasen (det kan API'et ikke gøre bagud i tid).

Miljø:
  SEED_API          appens API (standard http://localhost:8080/api)
  MONGO_URL/DB_NAME databasen (til invitationer og historik)
  SA_EMAIL/SA_PASSWORD  super admin (bruges kun til at logge ind)
  SEED_PASSWORD     koden til ALLE oprettede brugere (standard 123456)
  SEED_EMAIL_BASE   mails bliver +aliaser af denne adresse
  SEED_WIPE=ja-slet-alt  slet først al forretningsdata (super admin og
                    systemindstillinger bevares; en JSON-backup lægges i
                    SEED_BACKUP_DIR). Lokalt sletter local-test.sh --demo
                    hele databasen i stedet.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo import MongoClient

API = os.environ.get("SEED_API", "http://localhost:8080/api").rstrip("/")
PASSWORD = os.environ.get("SEED_PASSWORD", "123456")
EMAIL_BASE = os.environ.get("SEED_EMAIL_BASE", "ferdalturan@gmail.com")
SA_EMAIL = os.environ["SA_EMAIL"]
SA_PASSWORD = os.environ["SA_PASSWORD"]
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "containerflow")]
DK = ZoneInfo("Europe/Copenhagen")
random.seed(20261022)

LOGINS = []  # (rolle, navn, email, omfang)


def email(slug):
    local, domain = EMAIL_BASE.split("@")
    return f"{local}+{slug}@{domain}"


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(60):
        req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429:  # 60 kald/minut pr. IP - vent på vinduet
                time.sleep(5)
                continue
            sys.exit(f"{method} {path} fejlede ({e.code}): {e.read().decode()[:500]}")
    sys.exit(f"{method} {path} ramte hele tiden kaldgrænsen")


def login(addr, pw=PASSWORD):
    return call("POST", "/auth/login", {"email": addr, "password": pw})["token"]


def activate(user_id):
    """Acceptér invitationen appen lige har lavet (som at klikke på mailen)."""
    tk = db.invitation_tokens.find_one({"user_id": user_id, "token_type": "invitation", "used": False})
    call("POST", "/auth/accept-invitation", {"token": tk["token"], "new_password": PASSWORD})


# ---------------------------------------------------------------------------
# Sletning (kun med SEED_WIPE=ja-slet-alt)
# ---------------------------------------------------------------------------
KEEP_COLLECTIONS = {"system_flags", "system_settings", "geocode_cache"}


def wipe():
    from bson import json_util
    backup_dir = os.environ.get("SEED_BACKUP_DIR", "/backup")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(backup_dir, f"containerflow-backup-{stamp}")
    os.makedirs(folder, exist_ok=True)
    keep_users = list(db.users.find({"role": "super_admin"}, {"_id": 0, "id": 1, "company_id": 1}))
    keep_companies = {u.get("company_id") for u in keep_users if u.get("company_id")}
    for name in sorted(db.list_collection_names()):
        docs = list(db[name].find({}))
        with open(os.path.join(folder, f"{name}.json"), "w") as f:
            f.write(json_util.dumps(docs))
        if name in KEEP_COLLECTIONS:
            continue
        if name == "users":
            db.users.delete_many({"role": {"$ne": "super_admin"}})
        elif name == "companies":
            db.companies.delete_many({"id": {"$nin": list(keep_companies)}})
        else:
            db[name].delete_many({})
    print(f"Slettet. Backup af alle samlinger: {folder}")


# Tjek alt før noget slettes: database, super admin-login og at serveren kører
# en version med hængerkørsel (ellers står man med en tom server).
try:
    db.command("ping")
except Exception as e:
    sys.exit(f"Kan ikke nå databasen ({type(e).__name__}). Tjek MONGO_URL - på Scaleway også at din IP må forbinde.")
sa = login(SA_EMAIL, SA_PASSWORD)
try:
    urllib.request.urlopen(urllib.request.Request(API + "/driver/tours/start", data=b"{}", method="POST",
                                                  headers={"Content-Type": "application/json"}), timeout=60)
except urllib.error.HTTPError as e:
    if e.code in (404, 405):
        sys.exit(f"{API} kører en ældre version. Deploy den nyeste først (intet er slettet).")

if os.environ.get("SEED_WIPE") == "ja-slet-alt":
    wipe()
elif db.companies.count_documents({"name": {"$in": ["Helsingør Forsyning", "ILK Logistics", "ILK Logistics Premium"]}}):
    sys.exit("Der findes allerede data med de navne. Slet først (lokalt: ./scripts/local-test.sh --demo).")

# ---------------------------------------------------------------------------
# Stamdata
# ---------------------------------------------------------------------------
HOLIDAYS_2026 = [
    ("Nytårsdag", "2026-01-01"), ("Skærtorsdag", "2026-04-02"), ("Langfredag", "2026-04-03"),
    ("Påskedag", "2026-04-05"), ("2. påskedag", "2026-04-06"), ("Kristi himmelfartsdag", "2026-05-14"),
    ("Pinsedag", "2026-05-24"), ("2. pinsedag", "2026-05-25"), ("Grundlovsdag", "2026-06-05"),
    ("Juleaften", "2026-12-24"), ("1. juledag", "2026-12-25"), ("2. juledag", "2026-12-26"),
    ("Nytårsaftensdag", "2026-12-31"),
]
HALF_DAYS = {"Juleaften", "Nytårsaftensdag", "Grundlovsdag"}
# kg CO2 sparet pr. ton genanvendt (omtrentligt - godt nok til rapporterne)
CO2 = {"Træ": 80, "Imprægneret træ": 40, "Hård plast": 1200, "Blød plast": 900, "Metal": 1500, "Pap": 700,
       "Papir": 650, "Glas": 300, "Beton": 15, "Tegl": 20, "Gips": 60, "Haveaffald": 50, "Elektronik": 1800,
       "Restaffald": 0}
# Typisk vægt pr. container (kg)
WEIGHT = {"Træ": (1800, 3200), "Imprægneret træ": (1500, 2600), "Hård plast": (400, 900), "Blød plast": (200, 500),
          "Metal": (1500, 3500), "Pap": (600, 1400), "Papir": (900, 1800), "Glas": (1500, 3000),
          "Beton": (4000, 8500), "Tegl": (3500, 7000), "Gips": (1500, 3500), "Haveaffald": (1200, 2500),
          "Elektronik": (600, 1500), "Restaffald": (1500, 3000)}
# Containertype pr. materiale (stor/lille plads)
CONTAINER_TYPE = {"Beton": "Vippecontainer 10 m³", "Tegl": "Vippecontainer 10 m³", "Gips": "Vippecontainer 10 m³",
                  "Glas": "Vippecontainer 10 m³", "Metal": "Åben container 20 m³", "Træ": "Åben container 30 m³",
                  "Imprægneret træ": "Åben container 30 m³", "Haveaffald": "Åben container 30 m³",
                  "Restaffald": "Lukket container 30 m³", "Pap": "Lukket container 30 m³",
                  "Papir": "Lukket container 30 m³", "Hård plast": "Lukket container 20 m³",
                  "Blød plast": "Lukket container 20 m³", "Elektronik": "Lukket container 20 m³"}
SMALL_TYPE = {"Pap": "Lukket container 20 m³", "Papir": "Lukket container 20 m³", "Glas": "Minicontainer 6 m³",
              "Haveaffald": "Vippecontainer 10 m³", "Restaffald": "Lukket container 20 m³"}
SIZES = {"stor": [("Vippecontainer 10 m³", 10), ("Åben container 20 m³", 20), ("Åben container 30 m³", 30),
                  ("Lukket container 20 m³", 20), ("Lukket container 30 m³", 30)],
         "lille": [("Minicontainer 6 m³", 6), ("Vippecontainer 10 m³", 10), ("Lukket container 20 m³", 20)]}
HOURS = {"stor": {"mon": ("07:00", "17:00"), "tue": ("07:00", "17:00"), "wed": ("07:00", "17:00"),
                  "thu": ("07:00", "17:00"), "fri": ("07:00", "15:00"), "sat": ("09:00", "14:00")},
         "lille": {d: ("08:00", "15:00") for d in ("mon", "tue", "wed", "thu", "fri")}}

LOGISTICS = [
    {"key": "ilk", "name": "ILK Logistics", "customer_id": "ILK-9001", "tier": "partner",
     "admin": ("Kim Larsen", "ilk.admin"), "vehicles": ["CF 21 401", "CF 21 402"], "trailers": [("ILK-H1", 1)],
     "drivers": [("Lars Jensen", "ilk.chauffoer1", "40 11 20 01", "Nordsjælland"),
                 ("Mads Nielsen", "ilk.chauffoer2", "40 11 20 02", "Helsingør")]},
    {"key": "ilkp", "name": "ILK Logistics Premium", "customer_id": "ILKP-9002", "tier": "premium",
     "admin": ("Anne Holm", "ilkp.admin"), "coordinator": ("Sofie Dahl", "ilkp.planlaegger"),
     "vehicles": ["CF 31 501", "CF 31 502", "CF 31 503"], "trailers": [("ILKP-H1", 1), ("ILKP-H2", 2)],
     "drivers": [("Peter Hansen", "ilkp.chauffoer1", "40 22 30 01", "Nordsjælland"),
                 ("Jonas Pedersen", "ilkp.chauffoer2", "40 22 30 02", "Helsingør"),
                 ("Nikolaj Holm", "ilkp.chauffoer3", "40 22 30 03", "Roskilde")],
     "depot": ("ILK Depot Helsingør", "Industrivej 14", "Helsingør", 56.0270, 12.5900),
     "own_customers": [("Byg & Anlæg ApS", "31415926", "Kongevejen 120, 3000 Helsingør", "Morten Byg", "22 33 44 55"),
                       ("Nordkystens Tømrer", "27182818", "Strandvejen 8, 3100 Hornbæk", "Lene Træ", "23 45 67 89")]},
]
# (kode, navn, gade, by, størrelse, {materiale: partner}, flere containere for)
CUSTOMERS = [
    {"key": "hf", "name": "Helsingør Forsyning", "customer_id": "HF-1001", "admin": ("Jens Thomsen", "hf.admin"),
     "addresses": [("HCS A/S Helsingør", "Energivej 10", "3000", "Helsingør"),
                   ("Stena Recycling Kokkedal", "Kokkedal Industripark 104", "2980", "Kokkedal")],
     "workshops": [("Værksted Helsingør", "Industrivej 12, 3000 Helsingør", "49 21 00 10", "Indkørsel via port 2")],
     "locations": [
         ("1101", "SAC (Skibstrup Affaldscenter)", "Skibstrupvej 39", "Ålsgårde", "stor",
          {"Træ": "ilkp", "Beton": "ilkp", "Metal": "ilkp", "Gips": "ilkp",
           "Pap": "ilk", "Papir": "ilk", "Glas": "ilk", "Hård plast": "ilk", "Haveaffald": "ilk"}, ["Træ", "Pap", "Beton"]),
         ("1102", "Cirklen", "Energivej 6", "Helsingør", "stor",
          {"Pap": "ilkp", "Papir": "ilkp", "Træ": "ilkp", "Metal": "ilkp", "Restaffald": "ilkp", "Tegl": "ilkp",
           "Elektronik": "ilkp"}, ["Pap", "Træ"]),
         ("1121", "Nordkysten - Folehaven", "Folehaven 1", "Hornbæk", "lille",
          {"Pap": "ilk", "Papir": "ilk", "Glas": "ilk", "Haveaffald": "ilk", "Restaffald": "ilk"}, []),
     ],
     "location_admins": [("Brian Holm", "hf.la.sac", ["1101"]), ("Frank Madsen", "hf.la.cirklen", ["1102"]),
                         ("Jørgen Lund", "hf.la.nordkysten", ["1121"])],
     "employees": {"1101": ("Anne Mortensen", "hf.sac.medarbejder"), "1102": ("Bo Christiansen", "hf.cirklen.medarbejder"),
                   "1121": ("Christina Holt", "hf.nordkysten.medarbejder")}},
    {"key": "argo", "name": "ARGO", "customer_id": "ARGO-2001", "admin": ("Mette Rasmussen", "argo.admin"),
     "addresses": [("ARGO Roskilde", "Håndværkervej 70B", "4000", "Roskilde"),
                   ("Stena Recycling Køge", "Værftsvej 22", "4600", "Køge")],
     "workshops": [("ARGO Værksted Roskilde", "Håndværkervej 68, 4000 Roskilde", "46 34 10 20", "")],
     "locations": [
         ("2101", "Genbrugsplads Roskilde", "Kornerupvej 17", "Roskilde", "stor",
          {"Træ": "ilkp", "Metal": "ilkp", "Beton": "ilkp", "Pap": "ilkp", "Restaffald": "ilkp", "Haveaffald": "ilkp"},
          ["Træ"]),
     ],
     "location_admins": [("Camilla Berg", "argo.la.roskilde", ["2101"])],
     "employees": {"2101": ("Dennis Bach", "argo.roskilde.medarbejder")}},
]

LOGINS.append(("Super admin", "Super Admin", SA_EMAIL, "Hele platformen (uændret kode)"))
group = call("POST", "/superadmin/holiday-groups", {
    "name": "Danske helligdage 2026", "year": 2026, "holidays": [{"name": n, "date": d} for n, d in HOLIDAYS_2026]}, sa)

P = {}        # logistik: key -> {"id", "token", "drivers": [(id, name)], "name"}
for lg in LOGISTICS:
    admin_name, admin_slug = lg["admin"]
    if lg["tier"] == "partner":
        res = call("POST", "/superadmin/companies", {
            "name": lg["name"], "company_type": "logistics", "customer_id": lg["customer_id"],
            "admin_name": admin_name, "admin_email": email(admin_slug), "from_library": True}, sa)
        activate(res["created_admin"]["id"])
    else:
        res = call("POST", "/superadmin/companies/quick-setup", {
            "company_name": lg["name"], "company_type": "logistics", "customer_id": lg["customer_id"],
            "admin": {"name": admin_name, "email": email(admin_slug), "password": PASSWORD}}, sa)
    tok = login(email(admin_slug))
    P[lg["key"]] = {"id": res["company"]["id"], "token": tok, "drivers": [], "name": lg["name"]}
    LOGINS.append(("Logistik admin", admin_name, email(admin_slug), f"{lg['name']} ({'premium' if lg['tier'] == 'premium' else 'basic'})"))
    for number in lg["vehicles"]:
        call("POST", "/vehicles", {"number": number}, tok)
    for number, cap in lg["trailers"]:
        call("POST", "/trailers", {"number": number, "container_capacity": cap}, tok)
    for name, slug, phone, area in lg["drivers"]:
        d = call("POST", "/drivers", {"name": name, "email": email(slug), "phone": phone, "area": area}, tok)
        activate(d["id"])
        P[lg["key"]]["drivers"].append((d["id"], name))
        LOGINS.append(("Chauffør", name, email(slug), lg["name"]))
    if lg.get("depot"):
        n, st, cy, la_, ln = lg["depot"]
        call("POST", "/plads", {"name": n, "address": st, "city": cy, "lat": la_, "lng": ln}, tok)
        P[lg["key"]]["depot"] = n
    if lg.get("coordinator"):
        c_name, c_slug = lg["coordinator"]
        call("POST", "/logistics/team", {"name": c_name, "email": email(c_slug), "customer_scope": [],
                                         "permissions": {"tours_edit": True, "tours_assign": True, "planning": True,
                                                         "drivers": True, "archive": True, "messages": True,
                                                         "reports": True, "economy_view": True, "economy_edit": False}}, tok)
        activate(db.users.find_one({"email": email(c_slug)}, {"_id": 0, "id": 1})["id"])
        LOGINS.append(("Koordinator", c_name, email(c_slug), f"{lg['name']} (planlægning, ser priser)"))
    P[lg["key"]]["registry"] = {}
    for name, cvr, addr, contact, phone in lg.get("own_customers", []):
        r = call("POST", "/logistics/customers", {"name": name, "cvr": cvr, "address": addr, "contact": contact,
                                                   "phone": phone}, tok)
        P[lg["key"]]["registry"][name] = r["id"]
    print(f"{lg['name']}: {len(lg['drivers'])} chauffører, {len(lg['vehicles'])} biler, {len(lg['trailers'])} hængere")

C = {}        # kunde: key -> {"id", "token", "co2": {mat: id}, "locations": {...}}
for cu in CUSTOMERS:
    admin_name, admin_slug = cu["admin"]
    res = call("POST", "/superadmin/companies/quick-setup", {
        "company_name": cu["name"], "company_type": "customer", "customer_id": cu["customer_id"],
        "admin": {"name": admin_name, "email": email(admin_slug), "password": PASSWORD}}, sa)
    cid = res["company"]["id"]
    call("PUT", f"/superadmin/companies/{cid}", {"holiday_group_id": group["id"]}, sa)
    LOGINS.append(("Kunde admin", admin_name, email(admin_slug), cu["name"]))
    tok = login(email(admin_slug))
    partners = sorted({p for loc in cu["locations"] for p in loc[5].values()})
    for key in partners:
        call("POST", "/org/logistics-partners", {"logistics_company_id": P[key]["id"]}, tok)
    mats_used = sorted({m for loc in cu["locations"] for m in loc[5]})
    co2 = {m: call("POST", "/co2-types", {"name": m, "factor": CO2[m]}, tok)["id"] for m in mats_used}
    workshops = []
    for name, address, phone, comment in cu["workshops"]:
        w = call("POST", "/org/workshops", {"name": name, "address": address, "phone": phone, "comment": comment}, tok)
        workshops.append({"id": (w or {}).get("id", ""), "name": name, "address": address, "phone": phone})
    C[cu["key"]] = {"id": cid, "token": tok, "co2": co2, "locations": {}, "workshops": workshops, "name": cu["name"]}

    serial = 4100 if cu["key"] == "hf" else 7100
    for code, name, street, city, size, mats, busy in cu["locations"]:
        loc = call("POST", "/org/locations", {"name": name, "code": code, "address": street, "city": city}, tok)
        loc_partners = sorted(set(mats.values()))
        call("PUT", f"/org/locations/{loc['id']}/logistics-partners",
             {"logistics_company_ids": [P[p]["id"] for p in loc_partners]}, tok)
        addr_ids = [call("POST", "/org/delivery-addresses", {"location_code": code, "label": lbl, "street": st,
                                                             "postcode": pc, "city": cy}, tok)["id"]
                    for lbl, st, pc, cy in cu["addresses"]]
        cm_ids = {}
        for label, m3 in SIZES[size]:
            cm = call("POST", "/org/capacity-measures", {"location_code": code, "label": label, "volume_m3": m3}, tok)
            cm_ids[label] = (cm or {}).get("id") or db.capacity_measures.find_one(
                {"location_code": code, "label": label}, {"_id": 0, "id": 1})["id"]
        weekdays = {}
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            h = HOURS[size].get(day)
            weekdays[day] = ({"closed": False, "open_from": h[0], "open_to": h[1], "delivery_address_id": addr_ids[0]}
                             if h else {"closed": True})
        hours_cal = call("POST", "/org/hours-calendars", {"location_code": code, "name": "Standard åbningstid",
                                                          "weekdays": weekdays}, tok)
        holiday_cal = call("POST", "/org/holiday-calendars", {
            "location_code": code, "name": "Helligdage 2026", "year": 2026,
            "days": [{"name": n, "date": d, "closed": n not in HALF_DAYS, "open_from": "07:00" if n in HALF_DAYS else "",
                      "open_to": "12:00" if n in HALF_DAYS else ""} for n, d in HOLIDAYS_2026]}, tok)
        containers = {}  # materiale -> [(label, nummer, type)]
        for material, pkey in mats.items():
            call("POST", f"/locations/{code}/materials", {"material": material, "partner_id": P[pkey]["id"],
                                                          "co2_category_id": co2[material]}, tok)
            n = 2 if material in busy else 1
            if n > 1:
                call("POST", f"/locations/{code}/containers/add", {"material": material, "partner_id": P[pkey]["id"],
                                                                   "delta": n - 1}, tok)
            call("PUT", "/org/material-calendars", {"location_code": code, "material": material,
                                                    "hours_calendar_id": hours_cal["id"],
                                                    "holiday_calendar_id": holiday_cal["id"]}, tok)
            ctype = (SMALL_TYPE.get(material) if size == "lille" else None) or CONTAINER_TYPE[material]
            if ctype not in cm_ids:
                ctype = SIZES[size][-1][0]
            containers[material] = []
            for i in range(1, n + 1):
                serial += 1
                call("PUT", f"/locations/{code}/containers/override", {
                    "material": material, "container_label": f"Container {i}", "partner_id": P[pkey]["id"],
                    "custom_container_id": str(serial), "capacity_measure_id": cm_ids[ctype]}, tok)
                containers[material].append((f"Container {i}", str(serial), ctype))
        emp_name, emp_slug = cu["employees"][code]
        u = call("POST", "/org/users", {"name": emp_name, "email": email(emp_slug), "role": "order", "location_code": code}, tok)
        activate(u["id"])
        LOGINS.append(("Medarbejder", emp_name, email(emp_slug), f"{name} ({code}) - bestiller containere"))
        lbl0, st0, pc0, cy0 = cu["addresses"][0]
        C[cu["key"]]["locations"][code] = {"name": name, "mats": mats, "containers": containers, "addr": addr_ids[0],
                                           "addr_text": f"{st0}, {pc0} {cy0}",
                                           "employee": login(email(emp_slug)), "size": size}
    for la_name, slug, codes in cu["location_admins"]:
        u = call("POST", "/org/users", {"name": la_name, "email": email(slug), "role": "location_admin",
                                        "location_codes": codes}, tok)
        activate(u["id"])
        LOGINS.append(("Lokation admin", la_name, email(slug), ", ".join(codes)))
        for code in codes:
            C[cu["key"]]["locations"][code]["la"] = email(slug)
    print(f"{cu['name']}: {len(cu['locations'])} pladser, partnere: {', '.join(P[p]['name'] for p in partners)}")

# ---------------------------------------------------------------------------
# Priser (Økonomi) - kun premium. Basic har ikke Økonomi.
# ---------------------------------------------------------------------------
pt = P["ilkp"]["token"]
hf_id, argo_id = C["hf"]["id"], C["argo"]["id"]
BUNDLES = [
    {"name": "Helsingør Forsyning - containerafhentning", "conditions": {"customer_ids": [hf_id]},
     "base": {"pricing": {"model": "fixed", "amount": "1050"}}, "failed": {"amount": "450"},
     "run_trailer": {"mode": "amount", "value": "750"},
     "surcharges": [{"category": "weekend", "unit": "kr", "value": "300"},
                    {"category": "holiday", "unit": "percent", "value": "50"},
                    {"category": "haster", "unit": "kr", "value": "350"},
                    {"category": "waiting", "unit": "per_hour", "value": "600"},
                    {"category": "evening", "unit": "kr", "value": "350", "time_from": "18:00", "time_to": "06:00"}]},
    {"name": "ARGO - timepris", "conditions": {"customer_ids": [argo_id]},
     "base": {"pricing": {"model": "hourly", "hourly_rate": "650", "start_fee": "200", "min_minutes": "60",
                          "rounding_mode": "up", "rounding_minutes": 15, "deduct_pause": True}},
     "run_trailer": {"mode": "percent", "value": "75"}, "failed": {"amount": "450"},
     "surcharges": [{"category": "weekend", "unit": "percent", "value": "25"},
                    {"category": "waiting", "unit": "per_hour", "value": "600"}]},
    {"name": "Byt container og værksted", "conditions": {"task_types": ["flyt", "vaerksted", "afhent_vaerksted"]},
     "base": {"pricing": {"model": "fixed", "amount": "1250"}}, "surcharges": []},
    {"name": "Fragt - timepris", "conditions": {"task_types": ["afhentning", "levering", "afhent_lever", "flytning", "andet"]},
     "base": {"pricing": {"model": "hourly", "hourly_rate": "695", "start_fee": "250", "rounding_mode": "up",
                          "rounding_minutes": 15, "deduct_pause": True}},
     "surcharges": [{"category": "weekend", "unit": "percent", "value": "30"},
                    {"category": "waiting", "unit": "per_hour", "value": "600"}]},
    {"name": "Byg & Anlæg ApS - pr. palle", "conditions": {"customer_ids": ["firma:byg & anlæg aps"]},
     "base": {"pricing": {"model": "per_unit", "unit": "paller", "amount": "85", "min_amount": "900"}},
     "surcharges": [{"category": "stop", "value": "175", "included": 2},
                    {"category": "waiting", "unit": "per_hour", "value": "600"}]},
]
for b in BUNDLES:
    call("POST", "/pricing/bundles", {**b, "effective": "all", "active": True, "force": True}, pt)
call("PUT", "/pricing/settings", {"auto_approve_waiting_min": 15}, pt)
print(f"Prisaftaler: {len(BUNDLES)} for ILK Logistics Premium (basic har ikke Økonomi)")

# ---------------------------------------------------------------------------
# Ture
# ---------------------------------------------------------------------------
TODAY = datetime.now(DK).date()
ORDER_DAY = TODAY if TODAY.weekday() < 5 else TODAY + timedelta(days=7 - TODAY.weekday())


def dk_iso(d, hhmm):
    h, m = [int(x) for x in hhmm.split(":")]
    return datetime(d.year, d.month, d.day, h, m, tzinfo=DK).isoformat()


def hhmm(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def order(cust, code, material, idx=0, priority="normal", tour_type="normal", comment="", day=None, workshop=None):
    """Bestilling som pladsens medarbejder gør det på bestillingssiden."""
    loc = C[cust]["locations"][code]
    label, number, _type = loc["containers"][material][idx % len(loc["containers"][material])]
    body = {"location_code": code, "material": material, "co2_type_id": C[cust]["co2"][material],
            "container_number": label, "custom_container_id": number, "priority": priority, "comment": comment,
            "order_date": (day or ORDER_DAY).isoformat(), "tour_type": tour_type, "delivery_address_id": loc["addr"],
            "custom_address": loc["addr_text"],
            "partner_id": P[loc["mats"][material]]["id"]}
    if workshop:
        body.update({"workshop_id": workshop["id"], "workshop_name": workshop["name"],
                     "workshop_address": workshop["address"], "workshop_phone": workshop["phone"]})
    r = call("POST", "/customer-orders/submit", body, loc["employee"])
    return r["order_id"], r["tour_id"], loc["mats"][material]


def finish(order_id, tour_id, day, driver, start_min, minutes, material, run=None, waiting=0):
    """Dater en bestilling tilbage og afslutter den, som chaufføren ville have gjort."""
    did, dname = driver
    kg = random.randrange(*WEIGHT[material], 10)
    o = db.container_orders.find_one({"id": order_id}, {"_id": 0, "co2_factor": 1})
    factor = float((o or {}).get("co2_factor") or CO2.get(material, 0))
    start, end = hhmm(start_min), hhmm(start_min + minutes)
    created = (datetime(day.year, day.month, day.day, 9, 0, tzinfo=DK) - timedelta(days=random.choice([1, 2, 3]))).astimezone(timezone.utc).isoformat()
    common = {"date": day.isoformat(), "order_date": day.isoformat(), "created_at": created, "claimed_by": dname,
              "claimed_by_id": did, "claimed_at": dk_iso(day, start), "driver_name": dname, "on_way": False,
              "on_way_time": start, "time": end, "completed": True, "completed_at": dk_iso(day, end), "weight": kg}
    tour_set = {**common, "driver_id": did, "on_way_at": dk_iso(day, start), "trailer_confirmed": True,
                "trailer_source": "run", "used_trailer": bool(run), "run_role": run["role"] if run else "solo",
                "run_id": run["id"] if run else "", "run_seq": run["seq"] if run else 1, "run_size": run["size"] if run else 1}
    if waiting:
        tour_set["fact_overrides"] = {"waiting_min": waiting}
    db.tours.update_one({"id": tour_id}, {"$set": tour_set})
    db.container_orders.update_one({"id": order_id}, {"$set": {
        **common, "status": "completed", "weight_kg": kg, "co2_kg": round(factor * kg / 1000, 3)}})
    return tour_id


HIST = []      # (dag, chauffør-id) for stempling
PREMIUM_TOURS = []
hf_sites = {"1101": "hf", "1102": "hf", "1121": "hf", "2101": "argo"}
days = [TODAY - timedelta(days=i) for i in range(42, 0, -1)]
for day in days:
    if day.weekday() == 6 or (day.weekday() == 5 and random.random() < 0.6):
        continue
    plan = []
    # Premium: 2-3 ture (SAC tungt, Cirklen, ARGO) - nogle som hængerkørsel
    for code in random.sample(["1101", "1102", "2101"], 2 if random.random() < 0.6 else 3):
        mats = [m for m, p in C[hf_sites[code]]["locations"][code]["mats"].items() if p == "ilkp"]
        plan.append((code, random.choice(mats)))
    # Basic: 1-2 ture (SAC let, Folehaven)
    for code in random.sample(["1101", "1121"], 1 if random.random() < 0.5 else 2):
        mats = [m for m, p in C["hf"]["locations"][code]["mats"].items() if p == "ilk"]
        plan.append((code, random.choice(mats)))
    used = {}
    for code, material in plan:
        cust = hf_sites[code]
        idx = used.get((code, material), 0)
        used[(code, material)] = idx + 1
        prio = "haster" if random.random() < 0.12 else "normal"
        oid, tid, pkey = order(cust, code, material, idx=idx, priority=prio)
        driver = random.choice(P[pkey]["drivers"])
        start = random.randrange(7 * 60, 13 * 60, 5)
        finish(oid, tid, day, driver, start, random.randrange(35, 95, 5), material,
               waiting=random.choice([0, 0, 0, 0, 10, 20, 35]) if pkey == "ilkp" else 0)
        HIST.append((day, driver[0], pkey))
        if pkey == "ilkp":
            PREMIUM_TOURS.append((day, tid))
    # Hængerkørsel ca. hver 4. dag (premium, samme plads, to containere)
    if random.random() < 0.25:
        code = random.choice(["1101", "1102"])
        mats = [m for m, p in C["hf"]["locations"][code]["mats"].items() if p == "ilkp"]
        m1, m2 = random.sample(mats, 2)
        driver = random.choice(P["ilkp"]["drivers"])
        run_id, start = str(uuid.uuid4()), random.randrange(7 * 60, 12 * 60, 5)
        for seq, (mat, role) in enumerate(((m1, "truck"), (m2, "trailer")), 1):
            oid, tid, _ = order("hf", code, mat, idx=used.get((code, mat), 0))
            finish(oid, tid, day, driver, start, 80 + seq * 5, mat, run={"id": run_id, "role": role, "seq": seq, "size": 2})
            PREMIUM_TOURS.append((day, tid))
        HIST.append((day, driver[0], "ilkp"))
print(f"Historik: {db.container_orders.count_documents({'status': 'completed'})} afsluttede bestillinger over 6 uger")

# Varekørsel (premium, egne kunder) i historikken
depot = P["ilkp"]["depot"]
GOODS = [("Byg & Anlæg ApS", "levering", [{"text": "Byggematerialer", "qty": 12, "unit": "paller"}], 2),
         ("Nordkystens Tømrer", "afhent_lever", [{"text": "Træplader", "qty": 40, "unit": "stk"},
                                                {"text": "Isolering", "qty": 6, "unit": "paller"}], 2)]
goods_hist = 0
for day in days[::5]:
    if day.weekday() >= 5:
        continue
    cust_name, task, lines, n_stops = random.choice(GOODS)
    t = call("POST", "/tours/bulk?force=true", [{
        "date": day.isoformat(), "plads": depot, "tour_kind": "goods", "tour_type": task, "private_company": cust_name,
        "customer_ref_id": P["ilkp"]["registry"][cust_name], "is_private": True,
        "address_parts": {"street": "Kongevejen 120", "postal": "3000", "city": "Helsingør"},
        "facility": "Strandvejen 8, 3100 Hornbæk", "cargo_lines": lines, "capture": {"quantity": True}}], pt)[0]["id"]
    driver = random.choice(P["ilkp"]["drivers"])
    start = random.randrange(7 * 60, 11 * 60, 5)
    end = start + random.randrange(90, 200, 5)
    actual = [dict(l, actual_qty=max(1, l["qty"] - random.choice([0, 0, 1, 2]))) for l in lines]
    db.tours.update_one({"id": t}, {"$set": {
        "claimed_by": driver[1], "claimed_by_id": driver[0], "driver_id": driver[0], "driver_name": driver[1],
        "on_way_time": hhmm(start), "on_way_at": dk_iso(day, hhmm(start)), "time": hhmm(end),
        "completed": True, "completed_at": dk_iso(day, hhmm(end)), "on_way": False, "cargo_lines": actual,
        "trailer_count_actual": 0, "trailer_confirmed": True, "trailer_source": "driver",
        "created_at": (datetime(day.year, day.month, day.day, 8, 0, tzinfo=DK) - timedelta(days=2)).astimezone(timezone.utc).isoformat()}})
    PREMIUM_TOURS.append((day, t))
    HIST.append((day, driver[0], "ilkp"))
    goods_hist += 1
print(f"Varekørsel i historikken: {goods_hist} ture")

# Stempling (Tid & ressourcer) for premium-chaufførerne de dage de kørte
names = {d[0]: d[1] for d in P["ilkp"]["drivers"]}
stamped = set()
for day, did, pkey in HIST:
    if pkey != "ilkp" or (day, did) in stamped:
        continue
    stamped.add((day, did))
    for st, en, kind in (("06:45", "11:30", "work"), ("11:30", "12:00", "pause"), ("12:00", "15:15", "work")):
        mins = (int(en[:2]) * 60 + int(en[3:])) - (int(st[:2]) * 60 + int(st[3:]))
        db.driver_time_entries.insert_one({
            "id": str(uuid.uuid4()), "driver_id": did, "driver_name": names[did], "date": day.isoformat(),
            "start_time": st, "end_time": en, "duration_minutes": mins, "reason": "", "manual": False,
            "slice_type": kind, "created_by_id": did, "created_by_name": names[did], "created_by_role": "driver",
            "created_at": dk_iso(day, st), "updated_at": dk_iso(day, en)})
print(f"Stemplinger: {len(stamped)} arbejdsdage for premium-chaufførerne")

# Ture over 30 dage gamle er faktureret (prisen er frosset)
old = [tid for d, tid in PREMIUM_TOURS if (TODAY - d).days > 30]
if old:
    r = call("POST", "/pricing/invoice", {"tour_ids": old, "invoiced": True}, pt)
    print(f"Faktureret: {r.get('updated')} ture (over 30 dage gamle)")

# Dagens ture: nogle tildelt, nogle ledige
assign = []
oid, tid, _ = order("hf", "1101", "Træ", 0); assign.append(("ilkp", tid, 0))
order("hf", "1101", "Træ", 1)                                      # ledig - kan komme med på hængeren
order("hf", "1101", "Beton", 0)                                    # ledig
oid, tid, _ = order("hf", "1102", "Pap", 0, priority="haster", comment="Containeren står bag porten - ring på"); assign.append(("ilkp", tid, 1))
order("hf", "1102", "Tegl", 0, tour_type="vaerksted", workshop=C["hf"]["workshops"][0])
oid, tid, _ = order("argo", "2101", "Metal", 0); assign.append(("ilkp", tid, 2))
order("argo", "2101", "Træ", 0)
oid, tid, _ = order("hf", "1121", "Pap", 0); assign.append(("ilk", tid, 0))
order("hf", "1121", "Glas", 0)
order("hf", "1101", "Papir", 0)
# Forsinket: bestilt til i går, ikke kørt
oid, tid, _ = order("hf", "1102", "Papir", 0)
yday = (ORDER_DAY - timedelta(days=1)).isoformat()
db.tours.update_one({"id": tid}, {"$set": {"date": yday, "order_date": yday}})
db.container_orders.update_one({"id": oid}, {"$set": {"date": yday, "order_date": yday}})
assign.append(("ilkp", tid, 0))
for pkey, tid, di in assign:
    did, dname = P[pkey]["drivers"][di]
    call("PUT", f"/tours/{tid}", {"driver_id": did, "driver_name": dname}, P[pkey]["token"])

# Varekørsel i dag (premium): med stop og med planlagte hængere
g1 = call("POST", "/tours/bulk?force=true", [{
    "date": ORDER_DAY.isoformat(), "plads": depot, "tour_kind": "goods", "tour_type": "levering",
    "private_company": "Byg & Anlæg ApS", "customer_ref_id": P["ilkp"]["registry"]["Byg & Anlæg ApS"], "is_private": True,
    "open_from": "08:00", "open_to": "14:00", "cargo_lines": [{"text": "Byggematerialer", "qty": 14, "unit": "paller"}],
    "capture": {"quantity": True, "photo": True},
    "stops": [{"kind": "pickup", "street": "Industrivej 14", "postal": "3000", "city": "Helsingør"},
              {"kind": "delivery", "street": "Kongevejen 120", "postal": "3000", "city": "Helsingør", "contact_name": "Morten Byg", "contact_phone": "22 33 44 55"},
              {"kind": "delivery", "street": "Strandvejen 8", "postal": "3100", "city": "Hornbæk", "note": "Aflæs ved bagindgangen"}]}], pt)[0]["id"]
g2 = call("POST", "/tours/bulk?force=true", [{
    "date": ORDER_DAY.isoformat(), "plads": depot, "tour_kind": "goods", "tour_type": "afhent_lever",
    "private_company": "Nordkystens Tømrer", "customer_ref_id": P["ilkp"]["registry"]["Nordkystens Tømrer"], "is_private": True,
    "address_parts": {"street": "Strandvejen 8", "postal": "3100", "city": "Hornbæk"},
    "facility": "Industrivej 14, 3000 Helsingør", "trailer_count": 2,
    "cargo_lines": [{"text": "Træplader", "trailer": 1, "qty": 40, "unit": "stk"},
                    {"text": "Isolering", "trailer": 2, "qty": 6, "unit": "paller"}],
    "capture": {"quantity": True}}], pt)[0]["id"]
for tid, di in ((g1, 1), (g2, 2)):
    did, dname = P["ilkp"]["drivers"][di]
    call("PUT", f"/tours/{tid}", {"driver_id": did, "driver_name": dname}, pt)

# Fast tømning: Cirklen, Pap, mandag/onsdag/fredag (bestilles automatisk 7 dage frem)
la_cirklen = login(C["hf"]["locations"]["1102"]["la"])
call("POST", "/org/fixed-schedules", {"location_code": "1102", "material": "Restaffald", "container_number": "Container 1",
                                      "weekdays": [0, 2, 4], "interval_weeks": 1, "start_date": ORDER_DAY.isoformat(),
                                      "partner_id": P["ilkp"]["id"], "comment": ""}, la_cirklen)
print("Dagens ture: tildelte og ledige hos begge firmaer, en forsinket, værksted, varekørsel og en fast tømning")

# ---------------------------------------------------------------------------
# Logins
# ---------------------------------------------------------------------------
lines = [f"Adgangskode for alle oprettede brugere: {PASSWORD}", "",
         f"{'Rolle':<16}{'Navn':<18}{'Email':<52}Omfang"]
lines += [f"{r:<16}{n:<18}{e:<52}{s}" for r, n, e, s in LOGINS]
print("@@LOGINS@@\n" + "\n".join(lines))
