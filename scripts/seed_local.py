"""Clean, realistic test data for a LOCAL ContainerFlow.

Run it through `./scripts/local-test.sh --seed`, which wipes the local database
first. It runs inside the cf-app container and creates everything through the
app's own API (the same calls the admin screens make), so all links between
customers, locations, partners, materials and calendars are real.

Every user gets the same local password (LOCAL_TEST_PASSWORD in .env.local) and
a Gmail "+" alias of SEED_EMAIL_BASE, so any email the app sends lands in that
one inbox. No orders/tours are created.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from pymongo import MongoClient

API = "http://localhost:8080/api"
PASSWORD = os.environ["SEED_PASSWORD"]
EMAIL_BASE = os.environ.get("SEED_EMAIL_BASE", "ferdalturan@gmail.com")
SA_EMAIL = os.environ["SUPER_ADMIN_EMAIL"]
MONGO_URL = os.environ["MONGO_URL"]

if "cf-mongo" not in MONGO_URL and "localhost" not in MONGO_URL:
    sys.exit("Refusing to seed: MONGO_URL is not the local test database.")
db = MongoClient(MONGO_URL)[os.environ.get("DB_NAME", "containerflow")]

LOGINS = []  # (role, name, email, scope) for the summary


def email(slug):
    local, domain = EMAIL_BASE.split("@")
    return f"{local}+{slug}@{domain}"


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(40):
        req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429:  # the app allows 60 requests/minute per IP; wait for the window
                time.sleep(5)
                continue
            sys.exit(f"{method} {path} failed ({e.code}): {e.read().decode()[:400]}")
    sys.exit(f"{method} {path} kept hitting the rate limit")


def login(addr):
    return call("POST", "/auth/login", {"email": addr, "password": PASSWORD})["token"]


def activate(user_id):
    """Accept the invitation the app just created, like clicking the email link."""
    tk = db.invitation_tokens.find_one(
        {"user_id": user_id, "token_type": "invitation", "used": False})
    call("POST", "/auth/accept-invitation", {"token": tk["token"], "new_password": PASSWORD})


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
HOLIDAYS_2026 = [
    ("Nytårsdag", "2026-01-01"), ("Skærtorsdag", "2026-04-02"), ("Langfredag", "2026-04-03"),
    ("Påskedag", "2026-04-05"), ("2. påskedag", "2026-04-06"),
    ("Kristi himmelfartsdag", "2026-05-14"), ("Pinsedag", "2026-05-24"),
    ("2. pinsedag", "2026-05-25"), ("Grundlovsdag", "2026-06-05"),
    ("Juleaften", "2026-12-24"), ("1. juledag", "2026-12-25"), ("2. juledag", "2026-12-26"),
    ("Nytårsaftensdag", "2026-12-31"),
]
HALF_DAYS = {"Juleaften", "Nytårsaftensdag", "Grundlovsdag"}

# name -> estimated kg CO2 saved per ton (not exact, good enough for reports)
MATERIALS = {
    "Træ": 80, "Imprægneret træ": 40, "Hård plast": 1200, "Blød plast": 900,
    "Metal": 1500, "Pap": 700, "Papir": 650, "Glas": 300, "Beton": 15, "Tegl": 20,
    "Asfalt": 25, "Gips": 60, "Jord": 5, "Haveaffald": 50, "Dæk": 600,
    "Elektronik": 1800, "Hvidevarer": 1300, "Tekstiler": 2500, "Restaffald": 0,
    "Farligt affald": 0,
}
# Who handles what when two partners share a site
HEAVY = ["Beton", "Tegl", "Asfalt", "Jord", "Gips", "Træ", "Imprægneret træ",
         "Dæk", "Metal", "Hvidevarer"]
SIZE_MATERIALS = {
    "stor": ["Træ", "Imprægneret træ", "Hård plast", "Blød plast", "Metal", "Pap", "Papir",
             "Glas", "Beton", "Tegl", "Asfalt", "Gips", "Jord", "Haveaffald", "Dæk",
             "Elektronik", "Hvidevarer", "Tekstiler", "Restaffald", "Farligt affald"],
    "mellem": ["Træ", "Hård plast", "Metal", "Pap", "Papir", "Glas", "Beton",
               "Haveaffald", "Elektronik", "Restaffald"],
    "lille": ["Pap", "Papir", "Glas", "Metal", "Haveaffald", "Restaffald"],
}
SIZE_CONTAINERS = {
    "stor": [("Vippecontainer 10 m³", 10), ("Åben container 20 m³", 20),
             ("Lukket container 30 m³", 30)],
    "mellem": [("Vippecontainer 10 m³", 10), ("Åben container 20 m³", 20)],
    "lille": [("Minicontainer 6 m³", 6), ("Vippecontainer 10 m³", 10)],
}
SIZE_HOURS = {
    "stor": {"mon": ("07:00", "17:00"), "tue": ("07:00", "17:00"), "wed": ("07:00", "17:00"),
             "thu": ("07:00", "17:00"), "fri": ("07:00", "15:00"), "sat": ("09:00", "14:00")},
    "mellem": {d: ("07:00", "16:00") for d in ("mon", "tue", "wed", "thu")} | {"fri": ("07:00", "14:00")},
    "lille": {d: ("08:00", "15:00") for d in ("mon", "tue", "wed", "thu", "fri")},
}

LOGISTICS = [
    {"key": "ilk", "name": "ILK Logistics", "customer_id": "ILK-9001", "tier": "premium",
     "admin": ("ILK Distribution Admin", "ilk.admin"),
     "vehicles": ["CF 21 401", "CF 21 402", "CF 21 403"],
     "trailers": [("ILK-H1", 1), ("ILK-H2", 2)],
     "drivers": [("Lars Jensen", "ilk.chauffoer1", "40 11 20 01", "Nordsjælland"),
                 ("Mads Nielsen", "ilk.chauffoer2", "40 11 20 02", "Roskilde/Køge"),
                 ("Peter Hansen", "ilk.chauffoer3", "40 11 20 03", "Storkøbenhavn")]},
    {"key": "city", "name": "City Container", "customer_id": "CC-9002", "tier": "partner",
     "admin": ("City Container Admin", "city.admin"),
     "vehicles": ["CC 33 101", "CC 33 102"],
     "trailers": [("CC-H1", 1)],
     "drivers": [("Jonas Pedersen", "city.chauffoer1", "40 22 30 01", "Helsingør"),
                 ("Kasper Andersen", "city.chauffoer2", "40 22 30 02", "Storkøbenhavn")]},
    # Premium uden genbrugsplads-kunder: bruger systemet helt selvstændigt.
    {"key": "hansen", "name": "Hansen Transport", "customer_id": "HT-9003", "tier": "premium",
     "admin": ("Hansen Transport Admin", "hansen.admin"),
     "vehicles": ["HT 44 201", "HT 44 202"],
     "trailers": [("HT-H1", 1)],
     "drivers": [("Nikolaj Holm", "hansen.chauffoer1", "40 33 40 01", "Sjælland"),
                 ("Sara Kjeldsen", "hansen.chauffoer2", "40 33 40 02", "Storkøbenhavn")],
     "own_locations": [("Hansen Depot Køge", "Industrivej 22", "Køge", 55.4565, 12.1820),
                       ("Byggeplads Ørestad Syd", "Arne Jacobsens Allé 20", "København S", 55.6260, 12.5770),
                       ("Nordhavn Etape 2", "Kattegatvej 8", "København Ø", 55.7140, 12.5980)]},
]

CUSTOMERS = [
    {"key": "hf", "name": "Helsingør Forsyning", "customer_id": "HF-1001",
     "admin": ("Jens Thomsen", "hf.admin"), "partners": ["ilk", "city"],
     "groups": ["Boliggården", "Nordkysten"],
     "addresses": [("HCS A/S Helsingør", "Energivej 10", "3000", "Helsingør"),
                   ("Stena Recycling Kokkedal", "Kokkedal Industripark 104", "2980", "Kokkedal"),
                   ("RGS Nordic Avedøre", "Avedøreholmen 96", "2650", "Hvidovre")],
     "workshops": [("Værksted Helsingør", "Industrivej 12, 3000 Helsingør", "49 21 00 10",
                    "Indkørsel via port 2 - ring på ved ankomst"),
                   ("Værksted Hornbæk", "Havnevej 4, 3100 Hornbæk", "49 21 00 11", "")],
     "locations": [
         ("1101", "SAC (Skibstrup Affaldscenter)", "Skibstrupvej 39", "Ålsgårde", "stor", None, ["ilk", "city"]),
         ("1102", "Cirklen", "Energivej 6", "Helsingør", "stor", None, ["ilk"]),
         ("1111", "Boliggården - Blishøj 1", "Blishøj 1", "Helsingør", "lille", "Boliggården", ["city"]),
         ("1112", "Boliggården - Blishøj 49", "Blishøj 49", "Helsingør", "lille", "Boliggården", ["city"]),
         ("1113", "Boliggården - Olaf Rudes Vej 1", "Olaf Rudes Vej 1", "Helsingør", "lille", "Boliggården", ["city"]),
         ("1121", "Nordkysten - Folehaven 1", "Folehaven 1", "Hornbæk", "lille", "Nordkysten", ["ilk"]),
         ("1122", "Nordkysten - Gylfesvej 3", "Gylfesvej 3", "Hornbæk", "lille", "Nordkysten", ["ilk"]),
     ],
     "location_admins": [("Brian Holm", "hf.la.sac", ["1101"]),
                         ("Frank Madsen", "hf.la.cirklen", ["1102"]),
                         ("Morten Kjær", "hf.la.boliggaarden", ["1111", "1112", "1113"]),
                         ("Jørgen Lund", "hf.la.nordkysten", ["1121", "1122"])]},
    {"key": "argo", "name": "ARGO", "customer_id": "ARGO-2001",
     "admin": ("Mette Rasmussen", "argo.admin"), "partners": ["ilk"],
     "groups": ["ARGO Syd"],
     "addresses": [("ARGO Roskilde", "Håndværkervej 70B", "4000", "Roskilde"),
                   ("Stena Recycling Køge", "Værftsvej 22", "4600", "Køge"),
                   ("Norrecco Kalundborg", "Ellehammervej 2", "4400", "Kalundborg")],
     "workshops": [("ARGO Værksted Roskilde", "Håndværkervej 68, 4000 Roskilde", "46 34 10 20",
                    "Containere afleveres ved hal B")],
     "locations": [
         ("2101", "Genbrugsplads Roskilde", "Kornerupvej 17", "Roskilde", "stor", None, ["ilk"]),
         ("2102", "Genbrugsplads Køge", "Asgårdsvej 31", "Køge", "mellem", "ARGO Syd", ["ilk"]),
         ("2103", "Genbrugsplads Hvalsø", "Industrivej 9", "Hvalsø", "lille", "ARGO Syd", ["ilk"]),
     ],
     "location_admins": [("Camilla Berg", "argo.la.roskilde", ["2101"]),
                         ("Henrik Dahl", "argo.la.syd", ["2102", "2103"])]},
    {"key": "vf", "name": "Vestforbrænding", "customer_id": "VF-3001",
     "admin": ("Anders Kristensen", "vf.admin"), "partners": ["ilk", "city"],
     "groups": ["VF Nord"],
     "addresses": [("Vestforbrænding Glostrup", "Ejby Mosevej 219", "2600", "Glostrup"),
                   ("Stena Recycling Avedøre", "Avedøreholmen 70", "2650", "Hvidovre")],
     "workshops": [("VF Værksted Glostrup", "Ejby Mosevej 221, 2600 Glostrup", "43 23 18 00",
                    "Kun hverdage 07-15"),
                   ("VF Værksted Farum", "Ny Hammersholtvej 53, 3520 Farum", "43 23 18 01", "")],
     "locations": [
         ("3101", "Genbrugsplads Gladsaxe", "Kildebakkegårds Allé 99", "Søborg", "stor", None, ["ilk", "city"]),
         ("3102", "Genbrugsplads Ballerup", "Toldbuen 1", "Ballerup", "mellem", "VF Nord", ["city"]),
         ("3103", "Genbrugsplads Farum", "Ny Hammersholtvej 51", "Farum", "mellem", "VF Nord", ["ilk"]),
     ],
     "location_admins": [("Sofie Lauridsen", "vf.la.gladsaxe", ["3101"]),
                         ("Thomas Brandt", "vf.la.nord", ["3102", "3103"])]},
]

WORKER_NAMES = iter([
    "Anne Mortensen", "Bo Christiansen", "Christina Holt", "Dennis Bach", "Emil Friis",
    "Freja Nørgaard", "Gustav Lind", "Hanne Krogh", "Ida Svendsen", "Jakob Skov",
    "Karina Vestergaard", "Lasse Møller", "Maria Juhl", "Nikolaj Bang", "Oliver Dam",
    "Pernille Kock", "Rasmus Lykke", "Signe Winther", "Tobias Kofoed", "Ulla Poulsen",
])


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
sa = login(SA_EMAIL)
LOGINS.append(("Super admin", "Super Admin", SA_EMAIL, "Hele platformen"))

group = call("POST", "/superadmin/holiday-groups", {
    "name": "Danske helligdage 2026", "year": 2026,
    "holidays": [{"name": n, "date": d} for n, d in HOLIDAYS_2026]}, sa)
print("Helligdagsgruppe oprettet")

partner_ids = {}
for lg in LOGISTICS:
    admin_name, admin_slug = lg["admin"]
    if lg["tier"] == "partner":
        # Option 2: logistik-partner fra biblioteket (Super Admin > Tilføj
        # logistik partner) - får adgang gennem genbrugsplads-kunderne.
        res = call("POST", "/superadmin/companies", {
            "name": lg["name"], "company_type": "logistics", "customer_id": lg["customer_id"],
            "admin_name": admin_name, "admin_email": email(admin_slug), "from_library": True}, sa)
        activate(res["created_admin"]["id"])
    else:
        # Option 1: premium - oprettet som kunde med kundetype logistik.
        res = call("POST", "/superadmin/companies/quick-setup", {
            "company_name": lg["name"], "company_type": "logistics", "customer_id": lg["customer_id"],
            "admin": {"name": admin_name, "email": email(admin_slug), "password": PASSWORD}}, sa)
    partner_ids[lg["key"]] = res["company"]["id"]
    LOGINS.append(("Logistik admin", admin_name, email(admin_slug), f"{lg['name']} ({lg['tier']})"))
    tok = login(email(admin_slug))
    for name, street, city, lat, lng in lg.get("own_locations", []):
        call("POST", "/plads", {"name": name, "address": street, "city": city, "lat": lat, "lng": lng}, tok)
    for number in lg["vehicles"]:
        call("POST", "/vehicles", {"number": number}, tok)
    for number, cap in lg["trailers"]:
        call("POST", "/trailers", {"number": number, "container_capacity": cap}, tok)
    for name, slug, phone, area in lg["drivers"]:
        d = call("POST", "/drivers", {"name": name, "email": email(slug), "phone": phone,
                                      "area": area}, tok)
        activate(d["id"])
        LOGINS.append(("Chauffør", name, email(slug), lg["name"]))
    print(f"{lg['name']}: {len(lg['drivers'])} chauffører, {len(lg['vehicles'])} biler, "
          f"{len(lg['trailers'])} hængere")

for cu in CUSTOMERS:
    admin_name, admin_slug = cu["admin"]
    res = call("POST", "/superadmin/companies/quick-setup", {
        "company_name": cu["name"], "company_type": "customer", "customer_id": cu["customer_id"],
        "admin": {"name": admin_name, "email": email(admin_slug), "password": PASSWORD}}, sa)
    cid = res["company"]["id"]
    call("PUT", f"/superadmin/companies/{cid}", {"holiday_group_id": group["id"]}, sa)
    LOGINS.append(("Kunde admin", admin_name, email(admin_slug), cu["name"]))
    tok = login(email(admin_slug))

    for key in cu["partners"]:
        call("POST", "/org/logistics-partners", {"logistics_company_id": partner_ids[key]}, tok)
    co2 = {}
    for name, factor in MATERIALS.items():
        co2[name] = call("POST", "/co2-types", {"name": name, "factor": factor}, tok)["id"]
    group_ids = {g: call("POST", "/org/location-groups", {"name": g}, tok)["id"]
                 for g in cu["groups"]}
    for name, address, phone, comment in cu["workshops"]:
        call("POST", "/org/workshops", {"name": name, "address": address, "phone": phone,
                                        "comment": comment}, tok)

    for code, name, street, city, size, grp, partners in cu["locations"]:
        loc = call("POST", "/org/locations", {
            "name": name, "code": code, "address": street, "city": city,
            "location_group_id": group_ids.get(grp)}, tok)
        call("PUT", f"/org/locations/{loc['id']}/logistics-partners",
             {"logistics_company_ids": [partner_ids[p] for p in partners]}, tok)

        addrs = cu["addresses"][:2] if size == "lille" else cu["addresses"]
        addr_ids = [call("POST", "/org/delivery-addresses", {
            "location_code": code, "label": lbl, "street": st, "postcode": pc, "city": cy}, tok)["id"]
            for lbl, st, pc, cy in addrs]
        for label, m3 in SIZE_CONTAINERS[size]:
            call("POST", "/org/capacity-measures",
                 {"location_code": code, "label": label, "volume_m3": m3}, tok)

        weekdays = {}
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            hours = SIZE_HOURS[size].get(day)
            weekdays[day] = ({"closed": False, "open_from": hours[0], "open_to": hours[1],
                              "delivery_address_id": addr_ids[0]} if hours else {"closed": True})
        hours_cal = call("POST", "/org/hours-calendars", {
            "location_code": code, "name": "Standard åbningstid", "weekdays": weekdays}, tok)
        holiday_cal = call("POST", "/org/holiday-calendars", {
            "location_code": code, "name": "Helligdage 2026", "year": 2026,
            "days": [{"name": n, "date": d, "closed": n not in HALF_DAYS,
                      "open_from": "07:00" if n in HALF_DAYS else "",
                      "open_to": "12:00" if n in HALF_DAYS else ""}
                     for n, d in HOLIDAYS_2026]}, tok)

        for i, material in enumerate(SIZE_MATERIALS[size]):
            if len(partners) == 1:
                partner = partners[0]
            else:
                partner = partners[0] if material in HEAVY else partners[1]
            call("POST", f"/locations/{code}/materials", {
                "material": material, "partner_id": partner_ids[partner],
                "co2_category_id": co2[material]}, tok)
            # More containers for the busiest fractions on the bigger sites
            extra = {"stor": 2, "mellem": 1}.get(size, 0) if i % 3 == 0 else 0
            if extra:
                call("POST", f"/locations/{code}/containers/add", {
                    "material": material, "partner_id": partner_ids[partner], "delta": extra}, tok)
            call("PUT", "/org/material-calendars", {
                "location_code": code, "material": material,
                "hours_calendar_id": hours_cal["id"], "holiday_calendar_id": holiday_cal["id"]}, tok)

        for n in range(2 if size == "stor" else 1):
            worker = next(WORKER_NAMES)
            slug = f"{cu['key']}.{code}.medarbejder{n + 1}"
            u = call("POST", "/org/users", {"name": worker, "email": email(slug), "role": "order",
                                             "location_code": code}, tok)
            activate(u["id"])
            LOGINS.append(("Medarbejder", worker, email(slug), f"{name} ({code})"))

    for la_name, slug, codes in cu["location_admins"]:
        u = call("POST", "/org/users", {"name": la_name, "email": email(slug),
                                         "role": "location_admin", "location_codes": codes}, tok)
        activate(u["id"])
        LOGINS.append(("Lokation admin", la_name, email(slug), ", ".join(codes)))
    print(f"{cu['name']}: {len(cu['locations'])} lokationer, {len(cu['location_admins'])} "
          f"lokation admins, partnere: {', '.join(cu['partners'])}")

# Example price rules (Økonomi) so the report has numbers from day one
customer_ids = {c["id"]: c["name"] for c in db.companies.find({"company_type": "customer"}, {"_id": 0, "id": 1, "name": 1})}
by_name = {v: k for k, v in customer_ids.items()}


def rule(kind, name, cond=None, **kw):
    body = {"kind": kind, "name": name, "conditions": cond or {}}
    body.update(kw)
    return body


ILK_RULES = [
    rule("base", "Standard afhentning", pricing={"model": "fixed", "amount": 950}),
    rule("base", "ARGO timepris", {"customer_ids": [by_name["ARGO"]]},
         pricing={"model": "hourly", "hourly_rate": 650, "start_fee": 200, "min_minutes": 60,
                  "rounding_mode": "up", "rounding_minutes": 15, "deduct_pause": True}),
    rule("base", "Løs afhentning pr. container", {"task_types": ["loes_afhentning"]},
         pricing={"model": "per_container", "amount": 450}),
    rule("base", "Byt container / værksted", {"task_types": ["flyt", "vaerksted", "afhent_vaerksted"]},
         pricing={"model": "fixed", "amount": 1150}),
    rule("base", "Forgæves kørsel", {"outcome": "not_completed"}, pricing={"model": "fixed", "amount": 450}),
    rule("surcharge", "Weekendtillæg", {"day_types": ["saturday", "sunday"]}, category="weekend",
         surcharge={"unit": "kr", "value": 500}),
    rule("surcharge", "Weekend - Helsingør Forsyning aftale", {"customer_ids": [by_name["Helsingør Forsyning"]],
                                                             "day_types": ["saturday", "sunday"]},
         category="weekend", surcharge={"unit": "kr", "value": 300}),
    rule("surcharge", "Helligdagstillæg", {"day_types": ["holiday"]}, category="holiday",
         surcharge={"unit": "percent", "value": 50}),
    rule("surcharge", "Haster", {"priorities": ["haster"]}, category="haster", surcharge={"unit": "kr", "value": 300}),
    rule("surcharge", "Hænger", {"trailer": "with"}, category="trailer", surcharge={"unit": "per_hour", "value": 150}),
    rule("surcharge", "Aften/nat", {"time_from": "18:00", "time_to": "06:00"}, category="evening",
         surcharge={"unit": "kr", "value": 350}),
    rule("surcharge", "Ventetid", category="waiting", surcharge={"unit": "per_hour", "value": 600}),
]
CITY_RULES = [
    rule("base", "Timepris", pricing={"model": "hourly", "hourly_rate": 590, "rounding_mode": "up",
                                      "rounding_minutes": 30, "deduct_pause": True}),
    rule("base", "Gladsaxe pap/papir fast pris", {"location_codes": ["3101"], "materials": ["Pap", "Papir"]},
         pricing={"model": "fixed", "amount": 1100}),
    rule("surcharge", "Weekendtillæg", {"day_types": ["saturday", "sunday"]}, category="weekend",
         surcharge={"unit": "percent", "value": 25}),
]
HANSEN_RULES = [
    rule("base", "Timepris", pricing={"model": "hourly", "hourly_rate": 625, "start_fee": 150,
                                      "rounding_mode": "up", "rounding_minutes": 15, "deduct_pause": True}),
    rule("base", "Containerbyt fast pris", {"task_types": ["flyt"]}, pricing={"model": "fixed", "amount": 1050}),
    rule("surcharge", "Weekendtillæg", {"day_types": ["saturday", "sunday"]}, category="weekend",
         surcharge={"unit": "percent", "value": 30}),
    rule("surcharge", "Ventetid", category="waiting", surcharge={"unit": "per_hour", "value": 625}),
]
for admin_slug, rules in (("ilk.admin", ILK_RULES), ("city.admin", CITY_RULES), ("hansen.admin", HANSEN_RULES)):
    tok = login(email(admin_slug))
    for r in rules:
        call("POST", "/pricing/rules", r, tok)
print(f"Prisregler: {len(ILK_RULES)} for ILK, {len(CITY_RULES)} for City Container, {len(HANSEN_RULES)} for Hansen Transport")

# Summary for the person testing
lines = ["# Lokale test-logins (kun din lokale ContainerFlow)",
         "", "Adgangskode for alle: LOCAL_TEST_PASSWORD i .env.local", "",
         f"{'Rolle':<16}{'Navn':<26}{'Email':<52}Omfang"]
lines += [f"{r:<16}{n:<26}{e:<52}{s}" for r, n, e, s in LOGINS]
print("\n" + "\n".join(lines[4:]))
print("@@LOGINS@@\n" + "\n".join(lines))
