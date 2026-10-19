"""Premium (option 1) og partner (option 2), 2026-10-18. Se LOGISTICS_TIERS.md.
Kernen (begge): alt der gavner genbrugsplads-kunden - bestillinger, planlægning,
chauffører, tidsregistrering og Økonomi for kundernes ture. Premium: egne
lokationer, egne ture og kunder, Fragt, hængere med indhold, stop, Gentag og
krav ved afslutning. Serveren håndhæver det - ikke kun skærmbilledet."""
import subprocess
import sys

from _e2e import *  # noqa: F401,F403

# Et midlertidigt partnerfirma (option 2) tilknyttet Helsingør Forsyning, med
# egen admin og chauffør - så testen ikke afhænger af lokale testbrugere.
CITY_ADMIN = "e2e-partner-admin@example.com"
CITY_DRIVER = "e2e-partner-driver@example.com"


def _partner_setup(hf: str):
    sys.path.insert(0, "/app/backend")
    from auth import hash_password  # noqa: E402
    city = new_id()
    db.companies.insert_one({"id": city, "name": "E2E Partner Transport", "company_type": "logistics", "from_library": True,
                             "active": True, "serves_company_ids": [hf], "created_at": "2026-10-18"})
    for email, role, name in ((CITY_ADMIN, "logistics_admin", "E2E Partner Admin"), (CITY_DRIVER, "driver", "E2E Partner Chauffør")):
        db.users.insert_one({"id": new_id(), "email": email, "name": name, "role": role, "company_id": city, "active": True,
                             "invitation_status": "active", "password_hash": hash_password(PW), "managed_company_ids": [],
                             "assigned_plads_ids": [], "visible_plads_ids": [], "created_at": "2026-10-18"})
    return city


def run():
    c = Cleanup()
    hf = db.companies.find_one({"name": "Helsingør Forsyning"}, {"_id": 0, "id": 1})["id"]
    city = _partner_setup(hf)
    site = db.plads.find_one({"company_id": hf, "active": True, "location_code": {"$exists": True}}, {"_id": 0})
    c.restore.append(("plads", {"id": site["id"]}, {"assigned_logistics_company_ids": site.get("assigned_logistics_company_ids") or []}))
    db.plads.update_one({"id": site["id"]}, {"$addToSet": {"assigned_logistics_company_ids": city}})
    ca, la = login(CITY_ADMIN), login(ILK_ADMIN)
    try:
        prof = call("GET", "/logistics/profile", t=ca)
        ok(prof["tier"] == "partner" and not any(prof["capabilities"].values()), "1 et partnerfirma har ingen premium-evner")
        ok(all(call("GET", "/logistics/profile", t=la)["capabilities"].values()), "2 ILK Logistics (premium) har alle evner")

        # --- Ny tur som partner: premium-felter fjernes, turen bliver kundens ---------
        body = {"date": next_weekday(), "plads": site["name"], "tour_kind": "goods", "fraction": "E2E Pap",
                "address": "E2E Partnervej 1, 3000 Helsingør", "trailer_count": 2, "series_id": "e2e-serie",
                "capture": {"quantity": True, "photo": True},
                "cargo_lines": [{"text": "Pap", "trailer": 1}, {"text": "Træ", "trailer": 2}],
                "stops": [{"kind": "pickup", "street": "E2E Vej 1", "postal": "3000", "city": "Helsingør"},
                          {"kind": "pickup", "street": "E2E Vej 2", "postal": "3000", "city": "Helsingør"},
                          {"kind": "delivery", "street": "E2E Vej 3", "postal": "3000", "city": "Helsingør"}]}
        # 2026-10-19: På kundens plads er det en bestilling for kunden - ingen fri tur.
        try:
            call("POST", "/tours/bulk?force=true", [body], t=ca)
            ok(False, "3 partner: fri tur på kundens plads afvises")
        except ApiError as ex:
            ok(ex.status == 409 and ex.body["detail"].get("code") == "use_customer_order",
               "3 partner: fri tur på kundens plads afvises - det skal være 'Bestil for kunden'")
        r = call("POST", "/logistics/customer-orders", {"location_code": site["location_code"], "plads_name": site["name"],
                                                        "material": "E2E Pap", "container_number": "E2E Container P",
                                                        "order_date": next_weekday(), "custom_address": "E2E Partnervej 1, 3000 Helsingør",
                                                        "requested_by": "E2E telefon", "trailer_count": 2}, t=ca)
        tid = r["tour_id"]
        c.tours.append(tid); c.orders.append(r["order_id"])
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t["company_id"] == hf and t["assigned_logistics_company_ids"] == [city] and t["tour_kind"] == "container"
           and t["trailer_count"] == 2 and t.get("order_id"),
           "4 partner bestiller for kunden: kundens bestilling, kun partneren tildelt, antal hængere er kerne")
        ok(status_of("POST", "/tours/bulk", [{**body, "plads": ""}], t=ca) == 403, "5 partner kan ikke oprette egne ture uden plads")

        # --- Ret tur / stop / serier ----------------------------------------------------
        ok(status_of("PUT", f"/tours/{tid}", {"stops": body["stops"]}, t=ca) == 403,
           "6 partner kan ikke sætte stop på en eksisterende tur")
        call("PUT", f"/tours/{tid}", {"remark": "E2E note", "trailer_count": 3, "cargo_lines": body["cargo_lines"]}, t=ca)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t["remark"] == "E2E note" and t["trailer_count"] == 3 and not t.get("cargo_lines"),
           "7 ...en almindelig rettelse virker; antal hængere gemmes, indhold pr. hænger (premium) ignoreres")
        ok(status_of("POST", f"/tours/{tid}/stops", {"kind": "delivery", "street": "E2E Vej 9", "postal": "3000", "city": "Helsingør"},
                     t=login(CITY_DRIVER)) == 403, "8 partner-chauffør kan ikke tilføje stop")

        # --- Egne kunder og Økonomi -------------------------------------------------------
        ok(call("GET", "/logistics/customers", t=ca) == [], "9 partner: egne kunder svarer tom liste")
        r = _session.post(f"{BASE}/logistics/customers", json={"name": "E2E Ejen kunde"}, headers={"Authorization": f"Bearer {ca}"}, timeout=20)
        ok(r.status_code == 403 and r.json().get("premium_required") == "own_customers", "10 ...og kan ikke oprettes (Kræver Premium)")
        opts = call("GET", "/pricing/options", t=ca)
        connected = {x["id"] for x in prof["connected_customers"]}
        ok(opts["customers"] and {x["id"] for x in opts["customers"]} <= connected and not any(x.get("own") for x in opts["customers"]),
           "11 partner har Økonomi for sine tilknyttede genbrugsplads-kunder - ingen egne kunder")
        st = status_of("POST", "/pricing/bundles", {"name": "E2E egen", "conditions": {"customer_ids": ["firma:e2e"]},
                                                     "base": {"pricing": {"model": "fixed", "amount": "100"}}, "surcharges": []}, t=ca)
        ok(st == 403, "12 partner kan ikke lave priser for egne kunder")
        b = call("POST", "/pricing/bundles", {"name": "E2E HF partnerpris", "conditions": {"customer_ids": [hf]},
                                             "base": {"pricing": {"model": "fixed", "amount": "555"}}, "surcharges": [], "effective": "all"}, t=ca)
        c.bundles.append(b["bundle_id"])
        ok(price_of(ca, tid)["price"].get("total") == 555, "13 ...men kan lave en prisaftale for sin genbrugsplads-kunde, og den gælder turen")

        ok("stop" not in opts["categories"] and "per_unit" not in opts["models"] and "levering" not in opts["task_types"]
           and "normal" in opts["task_types"], "13a partner: ingen prisvalg der aldrig kan ramme en partnertur (stop, pr. enhed, gods)")

        # --- Pladser og indstillinger -------------------------------------------------------
        ok(not any(p.get("company_id") == city for p in call("GET", "/plads", t=ca)), "14 partner ser ingen egne lokationer")
        fs = call("GET", "/company/finish-settings", t=ca)
        call("PUT", "/company/finish-settings", {"deviation_codes": fs["deviation_codes"] + ["E2E kode"]}, t=ca)
        ok("E2E kode" in call("GET", "/driver/finish-settings", t=login(CITY_DRIVER))["codes"],
           "15 afvigelseskoder ligger under Indstillinger (også for partnere) og når chaufføren")

        # --- Premium er uændret --------------------------------------------------------------
        own = db.plads.find_one({"company_id": db.users.find_one({"email": ILK_ADMIN})["company_id"], "active": True}, {"_id": 0, "name": 1})
        pid = call("POST", "/tours/bulk?force=true", [{**body, "plads": own["name"], "tour_kind": "container", "fraction": "E2E premium"}], t=la)[0]["id"]
        c.tours.append(pid)
        pt = db.tours.find_one({"id": pid}, {"_id": 0})
        ok(len(pt.get("stops") or []) == 3 and pt.get("series_id") == "e2e-serie" and pt.get("trailer_count") == 2,
           "16 premium beholder stop, Gentag og hængere")

        # --- Super admin: skift type (samme id - intet slettes) ------------------------------
        ok(status_of("PUT", f"/superadmin/companies/{city}/logistics-tier", {"tier": "premium"}, t=ca) == 403,
           "17 kun super admin kan skifte et firmas type")
        out = subprocess.run([sys.executable, "-c", (
            "import asyncio, sys; sys.path.insert(0, '/app/backend'); import server;"
            f"print(asyncio.run(server.sa_set_logistics_tier('{city}', {{'tier': 'premium'}}, {{'sub': 'e2e', 'email': 'e2e'}})))")],
            capture_output=True, text=True, cwd="/app/backend", timeout=120)
        up = db.companies.find_one({"id": city}, {"_id": 0, "from_library": 1, "serves_company_ids": 1})
        ok(up["from_library"] is False and set(up["serves_company_ids"]) >= connected,
           f"18 opgradering til premium beholder tilknytningerne{'' if out.returncode == 0 else ' - ' + out.stderr[-200:]}")
    finally:
        db.price_rules.delete_many({"company_id": city})
        db.price_settings.delete_many({"company_id": city})
        db.users.delete_many({"email": {"$in": [CITY_ADMIN, CITY_DRIVER]}})
        db.companies.delete_one({"id": city})
        c.run()


if __name__ == "__main__":
    run()
