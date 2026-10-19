"""Sikkerhed (2026-10-18): login-krav som standard, kunde-admin kan ikke oprette
logistik-admins, ture kun på pladser man har adgang til, frakobling af en
partner fjerner adgangen, chauffør-arkivet er pr. firma og koordinatorens
rettigheder håndhæves på serveren."""
import time

from _e2e import *  # noqa: F401,F403

HF_ADMIN = "ferdalturan+hf.admin@gmail.com"
ILK_COORD = "ferdalturan+ilk.koordinator@gmail.com"
CITY_DRIVER = "ferdalturan+city.chauffoer1@gmail.com"


def anon(method: str, path: str, body=None) -> int:
    r = _session.request(method, f"{BASE}{path}", json=body, timeout=20)
    return r.status_code


def run():
    c = Cleanup()
    e2e_logi = new_id()
    hf = db.companies.find_one({"name": "Helsingør Forsyning"}, {"_id": 0, "id": 1})["id"]
    try:
        # --- 1. Uden login -------------------------------------------------------
        ok(all(anon(m, p, b) == 401 for m, p, b in [
            ("GET", "/tours", None), ("GET", "/plads", None), ("GET", "/driver-archive", None),
            ("GET", "/reports", None), ("GET", "/admin/statistics", None),
            ("POST", "/tours/bulk", [{"date": today(), "plads": "", "fraction": "x", "facility": "", "address": "x"}]),
            ("POST", "/seed", None)]), "1 uden login: ture, pladser, chauffør-arkiv, rapporter og oprettelse afvises (401)")
        ok(db.tours.count_documents({"fraction": "x", "address": "x", "date": today()}) == 0, "2 ...og der blev ikke oprettet nogen tur")
        ok(all(anon("GET", p) == 200 for p in ["/locations/code/1101", "/locations/1101/partners", "/locations/1101/materials",
                                                 "/locations/1101/containers", "/container-orders/by-location/1101"]),
           "3 QR-bestillingen (uden login) virker stadig")

        # --- 2. Kunde-admin og logistikfirmaer --------------------------------------
        db.companies.insert_one({"id": e2e_logi, "name": "E2E Vognmand", "company_type": "logistics", "from_library": True,
                                 "active": True, "serves_company_ids": [], "created_at": "2026-10-18"})
        ha = login(HF_ADMIN)
        lst = call("GET", "/org/logistics-companies", t=ha)
        ok(lst and all(set(x) == {"id", "name", "linked"} for x in lst),
           "4 kunde-adminens liste viser ikke længere hvilke andre kunder et logistikfirma kører for")
        call("POST", "/org/logistics-partners", {"logistics_company_id": e2e_logi,
                                                 "admin": {"email": "e2e-overtag@example.com", "password": "1234", "name": "X"}}, t=ha)
        ok(db.users.count_documents({"email": "e2e-overtag@example.com"}) == 0,
           "5 kunde-admin kan ikke oprette en logistik-admin med egen adgangskode (feltet ignoreres)")
        ok(hf in db.companies.find_one({"id": e2e_logi})["serves_company_ids"], "6 ...men tilknytningen virker")

        # En HF-plads får E2E-firmaet som partner + en åben tur
        pl = db.plads.find_one({"company_id": hf, "active": True, "location_code": {"$exists": True}}, {"_id": 0})
        c.restore.append(("plads", {"id": pl["id"]}, {"assigned_logistics_company_ids": pl.get("assigned_logistics_company_ids") or []}))
        call("PUT", f"/org/locations/{pl['id']}/logistics-partners",
             {"logistics_company_ids": (pl.get("assigned_logistics_company_ids") or []) + [e2e_logi]}, t=ha)
        open_t, done_t = new_id(), new_id()
        db.tours.insert_many([
            {"id": open_t, "date": today(), "plads": pl["name"], "company_id": hf, "fraction": "E2E åben",
             "address": "E2E Vej 1", "assigned_logistics_company_ids": [e2e_logi], "completed": False},
            {"id": done_t, "date": today(), "plads": pl["name"], "company_id": hf, "fraction": "E2E kørt",
             "address": "E2E Vej 2", "assigned_logistics_company_ids": [e2e_logi], "completed": True}])
        c.tours += [open_t, done_t]
        r = call("DELETE", f"/org/logistics-partners/{e2e_logi}", t=ha)
        ok(e2e_logi not in (db.plads.find_one({"id": pl["id"]})["assigned_logistics_company_ids"] or []),
           "7 frakobling fjerner partneren fra kundens pladser (før så den dem fortsat)")
        ok(r.get("open_tours_released") == 1 and e2e_logi not in db.tours.find_one({"id": open_t})["assigned_logistics_company_ids"]
           and e2e_logi in db.tours.find_one({"id": done_t})["assigned_logistics_company_ids"],
           "8 ...tager åbne ture fra den, men kørte ture kan den stadig se")
        st = status_of("PUT", f"/org/locations/{pl['id']}/logistics-partners",
                       {"logistics_company_ids": (pl.get("assigned_logistics_company_ids") or []) + [e2e_logi]}, t=ha)
        ok(st == 400, "9 en plads kan ikke tildeles et logistikfirma, kunden ikke har tilknyttet")
        if pl.get("assigned_logistics_company_ids"):
            call("PUT", f"/org/locations/{pl['id']}/logistics-partners", {"logistics_company_ids": pl["assigned_logistics_company_ids"]}, t=ha)
            ok(set(db.tours.find_one({"id": open_t})["assigned_logistics_company_ids"]) == set(pl["assigned_logistics_company_ids"]),
               "10 den åbne tur går til pladsens nuværende partnere")

        # --- 3. Ture kun på pladser man har adgang til -------------------------------
        la = login(ILK_ADMIN)
        ilk = db.users.find_one({"email": ILK_ADMIN})["company_id"]
        foreign = db.plads.find_one({"company_id": {"$ne": ilk}, "assigned_logistics_company_ids": {"$ne": ilk}, "active": True}, {"_id": 0, "name": 1})
        st = status_of("POST", "/tours/bulk", [{"date": today(), "plads": foreign["name"], "fraction": "E2E fremmed", "address": "E2E Vej 3"}], t=la)
        ok(st == 403, f"11 en tur kan ikke lægges på en fremmed plads ({foreign['name']}) - den ville havne i en andens arkiv")

        # --- 4. Chauffør-arkiv pr. firma -------------------------------------------------
        names = call("GET", "/driver-archive", t=la)["drivers"]
        hansen = user_name(HANSEN_DRIVER)
        ok(user_name(ILK_DRIVER) in names and hansen not in names, "12 chauffør-arkivet viser kun firmaets egne chauffører")
        ok(status_of("GET", f"/driver-archive/{hansen}", t=la) == 404, "13 ...og et andet firmas chauffør kan ikke slås op")

        # --- 5. Partner-chauffør kan ikke vælge "Egne ture" -------------------------------
        cd = login(CITY_DRIVER)
        city = db.users.find_one({"email": CITY_DRIVER})["company_id"]
        prev = (db.users.find_one({"email": CITY_DRIVER}, {"active_customer_id": 1}) or {}).get("active_customer_id") or ""
        c.restore.append(("users", {"email": CITY_DRIVER}, {"active_customer_id": prev}))
        ok(status_of("POST", "/driver/active-customer", {"customer_id": city}, t=cd) == 403,
           "14 partner-chauffør kan ikke få 'Egne ture' frem med sit eget firma-id")

        # --- 6. Koordinator-rettigheder på serveren ----------------------------------------
        coord = db.users.find_one({"email": ILK_COORD}, {"_id": 0, "id": 1, "permissions": 1, "is_coordinator": 1})
        if coord and coord.get("is_coordinator"):
            c.restore.append(("users", {"id": coord["id"]}, {"permissions": coord.get("permissions") or {}}))
            db.users.update_one({"id": coord["id"]}, {"$set": {"permissions": {**(coord.get("permissions") or {}), "planning": False}}})
            time.sleep(16)  # rettighedscache
            ok(status_of("GET", "/admin/time-entries", t=login(ILK_COORD), params={"date": today()}) == 403,
               "15 koordinator uden 'Planlægning og tidsregistrering' afvises også på serveren")

        # --- 4. Rette/slette ture (2026-10-19) --------------------------------------
        hans, cu, la = login(HANSEN_ADMIN), login(HF_ORDER_USER), login(ILK_ADMIN)
        own = call("POST", "/tours/bulk?force=true", [{"date": in_days(5), "plads": "Hansen Depot Køge", "fraction": "E2E sikkerhed",
                                                        "address": "Vej 1, 4600 Køge", "facility": "Vej 2, 4600 Køge"}], t=hans)[0]["id"]
        c.tours.append(own)
        ok(status_of("PUT", f"/tours/{own}", {"remark": "E2E rettet af fremmed"}, t=cu) == 403
           and db.tours.find_one({"id": own}, {"_id": 0, "remark": 1}).get("remark") != "E2E rettet af fremmed",
           "16 en kunde-bruger kan ikke rette et andet firmas tur (før: 200 og turen blev ændret)")
        # En ældre tur på kundens plads uden bestilling (fra før "Bestil for kunden"),
        # ejet af kunden - logistikfirmaet skal stadig kunne finde og slette den.
        pl = db.plads.find_one({"location_code": "1101"}, {"_id": 0, "name": 1, "company_id": 1})
        ilk_id = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
        sid = "e2e-serie-" + new_id()
        cust = [new_id(), new_id()]
        for i, d in zip(cust, (4, 5)):
            db.tours.insert_one({"id": i, "date": in_days(d), "plads": pl["name"], "fraction": "E2E sikkerhed", "series_id": sid,
                                 "company_id": pl["company_id"], "assigned_logistics_company_ids": [ilk_id], "completed": False,
                                 "on_way": False, "source": "manual", "order_id": ""})
        c.tours += cust
        ok(call("GET", f"/tours/series/{sid}", t=la, params={"from_date": in_days(1)})["count"] == 2,
           "17 serien findes også når turene ligger på en kundes plads (før: 0)")
        ok(status_of("DELETE", f"/tours/{cust[0]}", t=la) == 200 and not db.tours.find_one({"id": cust[0]}),
           "18 logistikfirmaet kan slette en tur på kundens plads (før: 404)")
        ou = login("ferdalturan+hf.1121.medarbejder1@gmail.com")
        ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
        mat = (call("GET", "/locations/code/1121").get("materials") or ["Pap"])[0]
        o = call("POST", "/customer-orders/submit", {"location_code": "1121", "material": mat, "container_number": "Container 9",
                                                     "priority": "normal", "tour_type": "flyt", "order_date": in_days(3),
                                                     "partner_id": ilk, "comment": "E2E sikkerhed"}, t=ou)
        c.tours.append(o["tour_id"]); c.orders.append(o["order_id"])
        ok(status_of("DELETE", f"/tours/{o['tour_id']}", t=la) == 409 and db.tours.find_one({"id": o["tour_id"]}),
           "19 en kundebestillings tur kan ikke slettes af logistikfirmaet (kunden annullerer den)")
    finally:
        db.companies.delete_one({"id": e2e_logi})
        db.users.delete_many({"email": "e2e-overtag@example.com"})
        c.run()


if __name__ == "__main__":
    run()
