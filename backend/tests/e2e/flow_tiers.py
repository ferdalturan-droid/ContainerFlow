"""Premium (option 1) og partner (option 2), 2026-10-18. Se LOGISTICS_TIERS.md.
Kernen (begge): alt der gavner genbrugsplads-kunden - bestillinger, planlægning,
chauffører, tidsregistrering og Økonomi for kundernes ture. Premium: egne
lokationer, egne ture og kunder, Fragt, hængere med indhold, stop, Gentag og
krav ved afslutning. Serveren håndhæver det - ikke kun skærmbilledet."""
import os
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
        # --- 2026-10-20: Logistikfirmaets egen drift er Premium -------------------------
        connected = {x["id"] for x in prof["connected_customers"]}
        ok(call("GET", "/pricing/options", t=ca) == [], "11 basic: Økonomi er Premium (prisaftaler svarer tom)")
        r = _session.post(f"{BASE}/pricing/bundles", json={"name": "E2E HF partnerpris", "conditions": {"customer_ids": [hf]},
                                                         "base": {"pricing": {"model": "fixed", "amount": "555"}}, "surcharges": []},
                          headers={"Authorization": f"Bearer {ca}"}, timeout=20)
        ok(r.status_code == 403 and r.json().get("premium_required") == "economy", "12 ...og kan ikke oprettes (Kræver Premium)")
        cd = login(CITY_DRIVER)
        r = _session.post(f"{BASE}/driver/time-entries/punch", json={"date": today(), "time": "07:00", "type": "ind"},
                          headers={"Authorization": f"Bearer {cd}"}, timeout=20)
        ok(r.status_code == 403 and r.json().get("premium_required") == "time", "12a basic: stempling (Tid & ressourcer) er Premium")
        ok(call("GET", "/admin/statistics", t=ca) == [], "12b basic: Rapportering er Premium")
        inv = call("POST", "/logistics/team", {"name": "E2E Kollega", "email": "e2e-kollega@example.com", "permissions": {"tours_edit": True},
                                               "customer_scope": [hf]}, t=ca)
        kol = db.users.find_one({"email": "e2e-kollega@example.com"}, {"_id": 0, "permissions": 1, "customer_scope": 1})
        ok(inv and kol and all(kol["permissions"].values()) and kol["customer_scope"] == [] and call("GET", "/logistics/team", t=ca)["roles"] is False,
           "12c basic: en inviteret kollega får fuld adgang - roller pr. person er Premium")

        # Ventetid: står på turen (fakturagrundlag) - ingen godkendelse uden Økonomi
        call("POST", "/driver/active-customer", {"customer_id": hf}, t=cd)
        cd_id = db.users.find_one({"email": CITY_DRIVER}, {"_id": 0, "id": 1})["id"]
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "08:00", "claimed_by": "E2E Partner Chauffør", "claimed_by_id": cd_id}, t=cd)
        fin = call("POST", f"/tours/{tid}/finish", {"op_id": new_id(), "weight": 900, "waiting_min": 15}, t=cd)
        tt = db.tours.find_one({"id": tid}, {"_id": 0, "waiting_reported_min": 1, "completed": 1})
        ok(fin.get("waiting") == "noted" and tt["completed"] and tt["waiting_reported_min"] == 15
           and not db.tour_change_requests.find_one({"tour_id": tid}),
           "12d basic: chaufførens ventetid står på turen (til fakturagrundlaget) - ingen godkendelse uden Økonomi")
        r = _session.post(f"{BASE}/driver/tours/{tid}/change-request", json={"waiting_min": 30, "comment": "E2E ventede"},
                          headers={"Authorization": f"Bearer {cd}"}, timeout=20)
        ok(r.status_code == 403 and r.json().get("premium_required") == "economy",
           "12e basic: rettelser til godkendelse kræver Økonomi (ingen Godkendelser at sende dem til)")

        # Super admin giver Økonomi enkeltvis (overgang / prøve)
        sa = login(os.environ["SUPER_ADMIN_EMAIL"])
        call("PUT", f"/superadmin/companies/{city}/premium-modules", {"modules": ["economy"]}, t=sa)
        prof2 = call("GET", "/logistics/profile", t=ca)
        ok(prof2["capabilities"]["economy"] and not prof2["capabilities"]["time"] and prof2["premium_modules"] == ["economy"],
           "13 super admin kan give et basic-firma Økonomi enkeltvis")
        opts = call("GET", "/pricing/options", t=ca)
        ok(opts["customers"] and {x["id"] for x in opts["customers"]} <= connected and not any(x.get("own") for x in opts["customers"]),
           "13a ...så har det Økonomi for sine genbrugsplads-kunder - ingen egne kunder")
        st = status_of("POST", "/pricing/bundles", {"name": "E2E egen", "conditions": {"customer_ids": ["firma:e2e"]},
                                                     "base": {"pricing": {"model": "fixed", "amount": "100"}}, "surcharges": []}, t=ca)
        ok(st == 403, "13b ...men kan ikke lave priser for egne kunder")
        b = call("POST", "/pricing/bundles", {"name": "E2E HF partnerpris", "conditions": {"customer_ids": [hf]},
                                             "base": {"pricing": {"model": "fixed", "amount": "555"}}, "surcharges": [], "effective": "all"}, t=ca)
        c.bundles.append(b["bundle_id"])
        ok(price_of(ca, tid)["price"].get("total") == 555, "13c ...og prisaftalen for genbrugsplads-kunden gælder turen")
        ok("stop" not in opts["categories"] and "per_unit" not in opts["models"] and "levering" not in opts["task_types"]
           and "normal" in opts["task_types"], "13d basic: ingen prisvalg der aldrig kan ramme en partnertur (stop, pr. enhed, gods)")

        # --- 2026-10-20: Pakkeskift slår igennem med det samme (begge veje) ---------------
        def gate(method, path, tok, body=None):
            """premium_required-nøglen hvis serveren afviser (ugyldig body = ingen sideeffekt)."""
            r = _session.request(method, f"{BASE}{path}", json=body if body is not None else {},
                                 headers={"Authorization": f"Bearer {tok}"}, timeout=20)
            try:
                j = r.json()
            except ValueError:
                j = {}
            return j.get("premium_required") if r.status_code == 403 and isinstance(j, dict) else None

        flips = []
        for _ in range(3):
            call("PUT", f"/superadmin/companies/{city}/logistics-tier", {"tier": "premium"}, t=sa)
            up_ok = (call("GET", "/logistics/profile", t=ca)["tier"] == "premium"
                     and call("GET", "/logistics/profile", t=cd)["capabilities"]["time"]
                     and gate("POST", "/driver/time-entries/punch", cd) is None
                     and gate("POST", "/logistics/customers", ca) is None)
            call("PUT", f"/superadmin/companies/{city}/logistics-tier", {"tier": "partner"}, t=sa)
            down_ok = (call("GET", "/logistics/profile", t=ca)["tier"] == "partner"
                       and not call("GET", "/logistics/profile", t=cd)["capabilities"]["time"]
                       and gate("POST", "/driver/time-entries/punch", cd) == "time"
                       and gate("POST", "/logistics/customers", ca) == "own_customers")
            flips.append(f"{'op' if up_ok else 'OP-FEJL'}/{'ned' if down_ok else 'NED-FEJL'}")
        ok(all(f == "op/ned" for f in flips),
           f"13e premium <-> basic slår igennem med det samme hos admin og chauffør, 3 gange i træk ({', '.join(flips)})")
        call("PUT", f"/superadmin/companies/{city}/premium-modules", {"modules": ["economy", "time"]}, t=sa)
        m_on = gate("POST", "/driver/time-entries/punch", cd) is None and call("GET", "/logistics/profile", t=cd)["capabilities"]["time"]
        call("PUT", f"/superadmin/companies/{city}/premium-modules", {"modules": ["economy"]}, t=sa)
        m_off = gate("POST", "/driver/time-entries/punch", cd) == "time" and not call("GET", "/logistics/profile", t=cd)["capabilities"]["time"]
        ok(m_on and m_off, "13f et enkelt modul (Tid) til og fra slår også igennem med det samme")

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
        db.users.delete_many({"email": {"$in": [CITY_ADMIN, CITY_DRIVER, "e2e-kollega@example.com"]}})
        db.companies.delete_one({"id": city})
        c.run()


if __name__ == "__main__":
    run()
