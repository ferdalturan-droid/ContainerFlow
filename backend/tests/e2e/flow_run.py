"""2026-10-20: Hængerkørsel. En chauffør med hænger kører 2-3 containerture
sammen: én på bilen og resten på hængeren. "Tag turen" lægger en ledig tur i
Mine ture; start kan ske fra Mine eller med det samme. Prisen kan afhænge af
kørslen (solo / på bilen / på hængeren), og "med hænger" på en containertur
betyder nu at den kørte i en hængerkørsel - ikke at chaufføren valgte en
hænger ved login. Ældre ture og varekørsel er uændrede."""
from _e2e import *  # noqa: F401,F403

MAT = "Pap"


def run():
    c = Cleanup()
    la = login(ILK_ADMIN)
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    hf = db.companies.find_one({"name": "Helsingør Forsyning"}, {"_id": 0, "id": 1})["id"]
    free = [e for e in ILK_DRIVERS if user_id(e) and not db.tours.count_documents(
        {"claimed_by_id": user_id(e), "on_way": True, "completed": {"$ne": True}})]
    if len(free) < 3:
        ok(False, "0 tre ledige ILK-chauffører findes")
        return
    da, db_, dc = free[:3]
    ta, tb, tc = login(da), login(db_), login(dc)
    ida, idb, idc = user_id(da), user_id(db_), user_id(dc)
    h1 = db.trailers.find_one({"company_id": ilk, "number": "ILK-H1"}, {"_id": 0, "id": 1})["id"]   # 1 container -> 2 ture
    h2 = db.trailers.find_one({"company_id": ilk, "number": "ILK-H2"}, {"_id": 0, "id": 1})["id"]   # 2 containere -> 3 ture
    for uid in (ida, idb, idc):
        u = db.users.find_one({"id": uid}, {"_id": 0, "active_trailer_id": 1}) or {}
        c.restore.append(("users", {"id": uid}, {"active_trailer_id": u.get("active_trailer_id") or ""}))
    disable_company_rules(c, ILK_ADMIN)

    def trailer(tok, tid):
        call("POST", "/driver/active-vehicle-trailer", {"active_trailer_id": tid}, t=tok)

    ou = login(HF_ORDER_USER)
    delivery = (db.delivery_addresses.find_one({"location_code": "1101"}, {"_id": 0, "id": 1}) or {}).get("id", "")

    def order(n, material=MAT, code="1101"):
        o = call("POST", "/customer-orders/submit", {
            "partner_id": ilk, "location_code": code, "material": material, "container_number": f"E2E Run {n}",
            "priority": "normal", "comment": "E2E hængerkørsel", "order_date": today(), "tour_type": "normal",
            "custom_address": "Energivej 6, 3000 Helsingør", "delivery_address_id": delivery}, t=ou)
        c.tours.append(o["tour_id"]); c.orders.append(o["order_id"])
        return o["tour_id"], o["order_id"]

    def T(tid):
        return db.tours.find_one({"id": tid}, {"_id": 0})

    def start(tok, ids, op=None):
        return call("POST", "/driver/tours/start", {"tour_ids": ids, "op_id": op or new_id()}, t=tok)

    def roles(*ids):
        return [T(i).get("run_role") for i in ids]

    mats = [m for m in (call("GET", "/locations/code/1101").get("materials") or [MAT])]
    other_mat = next((m for m in mats if m != MAT), MAT)
    try:
        t1, o1 = order(1)
        t2, _ = order(2)
        t3, _ = order(3)
        t4, _ = order(4)
        t5, _ = order(5, material=other_mat)
        t6, _ = order(6)
        t7, _ = order(7)

        # --- Tag turen (ledig -> Mine ture, ikke startet) ---------------------------
        trailer(ta, "")
        call("POST", f"/driver/tours/{t1}/take", t=ta)
        x = T(t1)
        ok(x["claimed_by_id"] == ida and not x.get("on_way") and x.get("claimed_at"),
           "1 'Tag turen' lægger turen i chaufførens Mine ture uden at starte den")
        ok(status_of("POST", f"/driver/tours/{t1}/take", t=tb) == 409, "2 en anden chauffør kan ikke tage den samme tur")

        # --- Uden hænger: én tur ad gangen, solo ---------------------------------------
        start(ta, [t1])
        x = T(t1)
        ok(x["on_way"] and x["run_role"] == "solo" and x.get("used_trailer") is False and x.get("trailer_source") == "run",
           "3 uden hænger: turen starter som solo (ikke 'med hænger')")
        ok(status_of("POST", "/driver/tours/start", {"tour_ids": [t2]}, t=ta) == 409, "4 uden hænger kan der kun køres én tur ad gangen")

        # --- Hænger med plads til 1 container: 2 ture -----------------------------------
        trailer(ta, h1)
        start(ta, [t2])
        ok(roles(t1, t2) == ["truck", "trailer"] and T(t1)["run_id"] == T(t2)["run_id"] and T(t2)["run_size"] == 2,
           "5 en ny tur mens den første kører kommer med på hængeren (første = på bilen)")
        ok(T(t1).get("used_trailer") is True and T(t2).get("used_trailer") is True, "6 begge ture er 'med hænger' i prisgrundlaget")
        ok(status_of("POST", "/driver/tours/start", {"tour_ids": [t3]}, t=ta) == 409, "7 hængeren er fuld (2 ture) - en tredje afvises")

        # --- Tag en tur af hængeren igen, og læg den på igen ----------------------------
        call("PUT", f"/tours/{t2}", {"on_way": False, "on_way_time": "", "claimed_by": user_name(da), "claimed_by_id": ida}, t=ta)
        x2 = T(t2)
        ok(T(t1)["run_role"] == "solo" and not T(t1).get("run_id") and not x2.get("on_way") and x2["claimed_by_id"] == ida
           and x2.get("run_role") == "", "8 en tur taget af hængeren: tilbage i Mine (ikke startet), den anden er solo igen")
        r = start(ta, [t1, t2])
        ok(r["started"] == [t1, t2] and roles(t1, t2) == ["truck", "trailer"], "9 'Tilføj tur på hængeren' fra en tur der kører")

        # --- Hænger med plads til 2 containere: 3 ture, start sammen --------------------
        trailer(tb, h2)
        start(tb, [t3, t4])
        ok(roles(t3, t4) == ["truck", "trailer"], "10 to ture startet sammen fra listen: den valgte på bilen, den anden på hængeren")
        start(tb, [t5])
        ok(roles(t3, t4, t5) == ["truck", "trailer", "trailer"] and T(t5)["run_size"] == 3, "11 et andet materiale kan også komme med (3 ture)")
        ok(status_of("POST", "/driver/tours/start", {"tour_ids": [t6]}, t=tb) == 409, "12 hængeren med plads til 2 er fuld ved 3 ture")
        ok(status_of("POST", "/driver/tours/start", {"tour_ids": [t4]}, t=tc) in (403, 409), "13 en tur en anden chauffør kører kan ikke startes")

        # --- Samme op_id to gange (telefonens kø uden net) ------------------------------
        trailer(tc, h1)
        op = new_id()
        r1 = start(tc, [t6], op)
        r2 = start(tc, [t6], op)
        ok(r1 == r2 and T(t6)["run_role"] == "solo", "14 start er sikker at gentage (samme op_id) og en ledig tur kan startes med det samme")

        # --- Pris: solo 1.000, på hængeren 700, hængertillæg 150 ------------------------
        b = call("POST", "/pricing/bundles", {"name": "E2E HF hænger", "conditions": {"customer_ids": [hf]}, "effective": "all",
                                              "base": {"pricing": {"model": "fixed", "amount": "1.000"}},
                                              "run_trailer": {"mode": "amount", "value": "700"},
                                              "surcharges": [{"category": "trailer", "unit": "kr", "value": "150"}]}, t=la)
        c.bundles.append(b["bundle_id"])
        rule_t = next((x for x in b["rules"] if (x.get("conditions") or {}).get("run_roles") == ["trailer"]), None)
        ok(rule_t and rule_t["pricing"]["amount"] == 700 and rule_t.get("run_spec") == {"mode": "amount", "value": 700.0},
           "15 prisaftalen gemmer 'container på hængeren' som en regel med betingelsen Kørsel")
        for tid, tok, w in ((t1, ta, 1200), (t2, ta, 900)):
            call("PUT", f"/tours/{tid}", {"completed": True, "weight": w, "time": "10:00", "claimed_by": user_name(da), "claimed_by_id": ida}, t=tok)
        ok(roles(t1, t2) == ["truck", "trailer"], "16 kørslen bevares når turene afsluttes")
        p1, p2 = price_of(la, t1)["price"], price_of(la, t2)["price"]
        ok(p1["total"] == 1150 and p2["total"] == 850,
           f"17 på bilen: grundpris 1.000 + hænger 150; på hængeren: 700 + 150 ({p1['total']}, {p2['total']})")
        row = report_row(la, t2)
        ok(row and row["run_role"] == "trailer" and [x["tour_id"] for x in row["run_partners"]] == [t1],
           "18 rapporten viser kørslen og hvilken tur den kørte sammen med")
        call("PUT", f"/tours/{t6}", {"completed": True, "weight": 800, "time": "10:30", "claimed_by": user_name(dc), "claimed_by_id": idc}, t=tc)
        p6 = price_of(la, t6)["price"]
        ok(p6["total"] == 1000 and not any("Hænger" in l["label"] for l in p6["lines"]),
           f"19 solo med hænger valgt ved login: ingen hængertillæg ({p6['total']})")

        # --- Admin retter kørslen -------------------------------------------------------
        call("PUT", f"/pricing/tours/{t6}/adjust", {"note": "E2E kørte på hængeren", "fact_overrides": {"run_role": "trailer"}}, t=la)
        ok(price_of(la, t6)["price"]["total"] == 850, "20 admin retter kørslen til 'på hængeren' -> 700 + 150")
        call("PUT", f"/pricing/tours/{t6}/adjust", {"note": "E2E solo igen", "fact_overrides": {}}, t=la)
        ok(price_of(la, t6)["price"]["total"] == 1000, "21 rettelsen fjernet -> solo igen")

        # --- Prøv prisen + procent ------------------------------------------------------
        sim = lambda role: call("POST", "/pricing/simulate", {"scenario": {"customer_id": hf, "run_role": role}}, t=la)["total"]  # noqa: E731
        ok((sim("solo"), sim("truck"), sim("trailer")) == (1000, 1150, 850), "22 'Prøv prisen' kan vælge kørsel")
        rules = [x for x in call("GET", "/pricing/rules", t=la) if x.get("bundle_id") == b["bundle_id"]]
        base_id = next(x["id"] for x in rules if not (x.get("conditions") or {}).get("run_roles") and x["kind"] == "base")
        call("POST", "/pricing/bundles", {"bundle_id": b["bundle_id"], "name": "E2E HF hænger", "conditions": {"customer_ids": [hf]},
                                          "effective": "all", "force": True,
                                          "base": {"id": base_id, "pricing": {"model": "fixed", "amount": "1.000"}},
                                          "run_trailer": {"id": rule_t["id"], "mode": "percent", "value": "75"},
                                          "surcharges": []}, t=la)
        ok(price_of(la, t2)["price"]["total"] == 750, "23 'container på hængeren' som 75 % af grundprisen = 750")
        ok(status_of("POST", "/pricing/bundles", {"name": "E2E pct uden grund", "conditions": {"customer_ids": [hf], "materials": ["E2E x"]},
                                                  "run_trailer": {"mode": "percent", "value": "70"}, "surcharges": []}, t=la) == 400,
           "24 procent uden grundpris i aftalen afvises")

        # --- Chaufføren kan ikke længere skifte hænger på en containertur ---------------
        tog = call("PUT", f"/driver/tours/{t5}/trailer", {"used_trailer": False}, t=tb)
        ok(tog.get("ignored") and T(t5).get("used_trailer") is True, "25 'Uden/Med hænger' på en containertur ændrer ikke kørslen")
        ok(status_of("POST", f"/driver/tours/{t1}/change-request", {"trailer_count": 0, "comment": "E2E"}, t=ta) == 400,
           "26 en rettelse af hænger på en containertur afvises (kørslen rettes af admin)")

        # --- Planlæggeren nulstiller en tur i kørslen; kunden annullerer en anden -------
        call("PUT", f"/tours/{t4}", {"on_way": False, "claimed_by": "", "claimed_by_id": "", "on_way_time": ""}, t=la)
        ok(roles(t3, t5) == ["truck", "trailer"] and T(t4).get("run_role") == "" and T(t5)["run_size"] == 2,
           "27 planlæggeren tager en tur ud: resten af kørslen tilpasses")
        o5 = db.container_orders.find_one({"tour_id": t5}, {"_id": 0, "id": 1})["id"]
        call("POST", f"/customer-orders/{o5}/cancel", {"reason": "E2E ikke fuld", "confirm_on_way": True}, t=ou)
        ok(T(t5).get("not_completed") and T(t5)["run_role"] == "trailer", "28 annulleret undervejs: turen bliver i kørslen (forgæves)")
        own = db.plads.find_one({"company_id": ilk, "active": True}, {"_id": 0, "name": 1})["name"]
        m1, m2 = [x["id"] for x in call("POST", "/tours/bulk?force=true", [
            {"date": today(), "plads": own, "tour_kind": "container", "fraction": "E2E run egen", "address": "E2E Vej 1, 3000 Helsingør"},
            {"date": today(), "plads": own, "tour_kind": "container", "fraction": "E2E run egen", "address": "E2E Vej 2, 3000 Helsingør"}], t=la)]
        c.tours += [m1, m2]
        start(tc, [m1, m2])
        ok(roles(m1, m2) == ["truck", "trailer"], "29 egne containerture (logistikfirmaets lokation) kan også køres sammen")
        call("DELETE", f"/tours/{m1}", t=la)
        ok(T(m2)["run_role"] == "solo" and not T(m2).get("run_id"), "30 en tur i kørslen slettes: den sidste bliver solo")
        call("PUT", f"/tours/{m2}", {"on_way": False, "claimed_by": "", "claimed_by_id": "", "on_way_time": ""}, t=la)

        # --- 2026-10-22: containertype slås op når turen mangler den -----------------
        cm = db.capacity_measures.find_one({"location_code": "1101"}, {"_id": 0, "id": 1, "label": 1})
        if cm:
            t9, _ = order(9)
            db.container_overrides.insert_one({"location_code": "1101", "material": MAT, "container_label": "Container 99",
                                               "custom_container_id": "E2E Run 9", "capacity_measure_id": cm["id"], "partner_id": ""})
            try:
                row9 = next((x for x in call("GET", "/tours", t=la, params={"date": today(), "limit": 500}) if x["id"] == t9), {})
                ok(not T(t9).get("capacity_label") and row9.get("capacity_label") == cm["label"],
                   f"30a containertype ({cm['label']}) vises fra pladsens container, også når turen ikke har fået den med")
            finally:
                db.container_overrides.delete_many({"custom_container_id": "E2E Run 9"})
        else:
            ok(False, "30a testdata mangler et kapacitetsmål på 1101")

        # --- Ældre ture (før hængerkørsel) prissættes som før ---------------------------
        db.tours.update_one({"id": t7}, {"$set": {"on_way": True, "on_way_time": "08:00", "completed": True, "time": "09:00",
                                                  "completed_at": datetime.now(DK).isoformat(), "claimed_by": user_name(dc),
                                                  "claimed_by_id": idc, "used_trailer": True, "trailer_source": "auto",
                                                  "trailer_confirmed": False, "run_role": ""}})
        p7 = price_of(la, t7)["price"]
        ok("Hænger: automatisk, ikke bekræftet" in (p7.get("flags") or []), "31 en ældre tur med automatisk hænger vises som før")

        # --- Varekørsel er uændret (hængere hører til turen) ----------------------------
        ha, hd = login(HANSEN_ADMIN), login(HANSEN_DRIVER)
        g = call("POST", "/tours/bulk", [{"date": today(), "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "levering",
                                          "private_company": "E2E Run Gods", "is_private": True, "trailer_count": 2,
                                          "cargo_lines": [{"text": "Paller", "qty": 4, "unit": "paller"}]}], t=ha)[0]["id"]
        c.tours.append(g)
        r = start(hd, [g])
        gt = T(g)
        ok(r["started"] == [g] and gt.get("run_role") == "" and gt.get("used_trailer") is True and gt.get("trailer_source") == "planned",
           "32 varekørsel: ingen hængerkørsel - de planlagte hængere gælder som før")
        ok(status_of("POST", "/driver/tours/start", {"tour_ids": [g, t6]}, t=hd) == 400, "33 varekørsel kan ikke kobles med containerture")
        call("PUT", f"/tours/{g}", {"on_way": False, "claimed_by": "", "claimed_by_id": "", "on_way_time": ""}, t=ha)
    finally:
        c.run()


if __name__ == "__main__":
    run()
