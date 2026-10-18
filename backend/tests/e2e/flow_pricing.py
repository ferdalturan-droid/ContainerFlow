"""Prisaftaler (premium-firma): "Opret pris" gælder også ture uden pris,
"ture kørt fra en dato", pris pr. enhed + minimum, stoptillæg, forgæves
kørsel, materiale som liste, forklaring på manglende pris, haster fra noten,
konflikt og simulator (2026-10-18)."""
from _e2e import *  # noqa: F401,F403

X, Y, Z, W = "E2E Prisaftale ApS", "E2E Gods ApS", "E2E Materiale ApS", "E2E Legacy ApS"


def key(name):
    return "firma:" + " ".join(name.lower().split())


def tour(t, c, customer, task="levering", date_=None, lines=None, **extra):
    body = {"date": date_ or next_weekday(), "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": task,
            "private_company": customer, "is_private": True, "address": "Industrivej 22, 4600 Køge",
            "facility": "Nordhavn Etape 2", "cargo_lines": lines or [{"text": "Gods", "qty": 1, "unit": "stk"}], **extra}
    tid = call("POST", "/tours/bulk", [body], t=t)[0]["id"]
    c.tours.append(tid)
    return tid


def bundle(t, c, name, conditions, base=None, surcharges=None, failed=None, effective="now", **extra):
    res = call("POST", "/pricing/bundles", {"name": name, "conditions": conditions, "base": base,
                                            "surcharges": surcharges or [], "failed": failed,
                                            "effective": effective, "active": True, **extra}, t=t)
    c.bundles.append(res["bundle_id"])
    return res


def total(t, tid):
    return price_of(t, tid)["price"].get("total")


def run():
    c = Cleanup()
    ha, drv = login(HANSEN_ADMIN), login(HANSEN_DRIVER)
    nik_id, nik = user_id(HANSEN_DRIVER), user_name(HANSEN_DRIVER)
    c.customers += [X, Y, Z, W]
    # Firmaets egne (generelle) regler slås fra under testen, så resultatet
    # ikke afhænger af lokale data eller ugedagen - og slås til igen bagefter.
    disable_company_rules(c, HANSEN_ADMIN)
    try:
        for n in (X, Y, Z, W):
            db.logistics_customers.delete_many({"name": n})
            call("POST", "/logistics/customers", {"name": n}, t=ha)

        # --- "Opret pris" fra Rapport (effective=unpriced) ---------------------
        a = tour(ha, c, X, task="flytning")
        p = price_of(ha, a)["price"]
        ok(p["status"] == "missing_rule" and p.get("why"), f"1 tur uden regel: Mangler pris + forklaring ({(p.get('why') or {}).get('text')})")
        b1 = bundle(ha, c, "E2E X generel", {"customer_ids": [key(X)]}, base={"pricing": {"model": "fixed", "amount": "1.000"}})
        ok(total(ha, a) is None, "2 ny aftale 'kun ture oprettet fra nu' giver IKKE den gamle tur pris (det var fejlen)")
        cc = tour(ha, c, X, task="flytning")
        ok(total(ha, cc) == 1000, "3 tur oprettet efter aftalen: 1.000 kr")
        bundle(ha, c, "E2E X flytning", {"customer_ids": [key(X)], "task_types": ["flytning"]},
               base={"pricing": {"model": "fixed", "amount": "700"}}, effective="unpriced")
        pa = price_of(ha, a)["price"]
        ok(pa.get("total") == 700 and any("uden pris" in f for f in pa.get("flags") or []),
           "4 'Opret pris' (nye + ture uden pris): den gamle tur får nu 700 kr")
        ok(total(ha, cc) == 1000, "5 ...men en tur der allerede havde en pris (1.000) ændres ikke")

        # --- Prisstigning: "ture kørt fra en dato" ------------------------------
        d = next_weekday(10)
        before_d = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
        after_d = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        e_after = tour(ha, c, X, task="levering", date_=after_d)
        e_before = tour(ha, c, X, task="levering", date_=before_d)
        ok(total(ha, e_after) == 1000 and total(ha, e_before) == 1000, "6 to ture (før/efter datoen) koster 1.000 inden prisstigningen")
        res = call("POST", "/pricing/bundles", {"bundle_id": b1["bundle_id"], "name": "E2E X generel",
                                                "conditions": {"customer_ids": [key(X)]},
                                                "base": {"id": b1["rules"][0]["id"], "pricing": {"model": "fixed", "amount": "1.200"}},
                                                "surcharges": [], "effective": "all", "driven_from": d, "active": True}, t=ha)
        c.bundles.append(res["bundle_id"])
        ok(total(ha, e_after) == 1200, f"7 'kørt fra {d}': tur kørt efter datoen (oprettet før) får 1.200")
        ok(total(ha, e_before) == 1000, "8 tur kørt dagen før beholder 1.000")
        old = db.price_rules.find_one({"id": b1["rules"][0]["id"]}, {"_id": 0})
        ok(old and old.get("valid_to") == before_d, "9 den gamle aftale gælder til og med dagen før")

        # Prisstigning på en gammel enkeltregel (uden aftale): "kørt fra" lukker den
        legacy = call("POST", "/pricing/rules", {"kind": "base", "name": "E2E legacy W", "conditions": {"customer_ids": [key(W)]},
                                                 "pricing": {"model": "fixed", "amount": 600}, "effective": "all"}, t=ha)
        c.rules.append(legacy["id"])
        w_after = tour(ha, c, W, task="levering", date_=after_d)
        res = call("POST", "/pricing/bundles", {"adopt_ids": [legacy["id"]], "name": "E2E W ny", "conditions": {"customer_ids": [key(W)]},
                                                "base": {"id": legacy["id"], "pricing": {"model": "fixed", "amount": "650"}},
                                                "surcharges": [], "effective": "all", "driven_from": d, "active": True}, t=ha)
        c.bundles.append(res["bundle_id"])
        ok(total(ha, w_after) == 650 and db.price_rules.find_one({"id": legacy["id"]}, {"_id": 0})["valid_to"] == before_d,
           "9a 'kørt fra' virker også på en gammel enkeltregel (ingen konflikt-dialog)")

        # --- Pris pr. enhed + minimum, stoptillæg, forgæves ---------------------
        bundle(ha, c, "E2E Gods palle", {"customer_ids": [key(Y)]},
               base={"pricing": {"model": "per_unit", "unit": "paller", "amount": "150", "min_amount": "1.000"}},
               surcharges=[{"category": "stop", "unit": "kr", "value": "200", "included": 2}],
               failed={"amount": "450"})
        stops = [{"kind": "pickup", "street": "Vej 1", "postal": "4600", "city": "Køge"},
                 {"kind": "pickup", "street": "Vej 2", "postal": "4600", "city": "Køge"},
                 {"kind": "delivery", "street": "Vej 3", "postal": "3000", "city": "Helsingør"},
                 {"kind": "delivery", "street": "Vej 4", "postal": "3400", "city": "Hillerød"},
                 {"kind": "delivery", "street": "Vej 5", "postal": "4000", "city": "Roskilde"}]
        g = tour(ha, c, Y, lines=[{"text": "Køkkenelementer", "qty": 12, "unit": "paller"}], stops=stops,
                 capture={"quantity": True}, remark="HASTER inden kl. 10", date_=today())
        gt = db.tours.find_one({"id": g}, {"_id": 0})
        ok(gt.get("priority") == "urgent", "10 'HASTER' i planlæggerens note -> prioritet haster (samme kilde som prisen)")
        ok(total(ha, g) == 12 * 150 + 3 * 200, "11 planlagt: 12 paller × 150 + 3 ekstra stop × 200 = 2.400")
        call("PUT", f"/tours/{g}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{g}", {"on_way": True, "on_way_time": "08:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        call("PUT", f"/tours/{g}", {"completed": True, "time": "10:00", "cargo_actuals": [6], "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        pg = price_of(ha, g)["price"]
        ok(pg.get("total") == 1000 + 600 and "registreret" in pg["lines"][0]["label"],
           f"12 kørt 6 paller: 900 løftet til minimum 1.000 + stop 600 = {pg.get('total')} ('registreret')")
        h = tour(ha, c, Y, lines=[{"text": "Køkkenelementer", "qty": 4, "unit": "paller"}], date_=today())
        call("PUT", f"/tours/{h}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{h}", {"on_way": True, "on_way_time": "11:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        call("POST", f"/tours/{h}/not-completed", {"code": "Lukket"}, t=drv)
        ht = db.tours.find_one({"id": h}, {"_id": 0})
        ok(ht.get("not_completed_code") == "Lukket" and ht.get("not_completed_comment") == "Lukket", "13 forgæves med årsagskode (koden er nok)")
        ok(total(ha, h) == 450, "14 forgæves kørsel prissættes af aftalens forgæves-pris (450)")

        # --- Materiale som liste ---------------------------------------------
        bundle(ha, c, "E2E Beton", {"customer_ids": [key(Z)], "materials": ["Beton"]},
               base={"pricing": {"model": "fixed", "amount": "900"}})
        i = tour(ha, c, Z, lines=[{"text": "Beton", "qty": 1, "unit": "stk"}, {"text": "Træ", "qty": 1, "unit": "stk"}])
        j = tour(ha, c, Z, lines=[{"text": "Beton", "qty": 2, "unit": "stk"}])
        pi = price_of(ha, i)["price"]
        ok(pi["status"] == "missing_rule" and "Beton + Træ" in (pi.get("why") or {}).get("text", ""),
           f"15 Beton + Træ: ingen stille fejlpris, men forklaring ({(pi.get('why') or {}).get('text')})")
        ok(total(ha, j) == 900, "16 ren betontur: 900")

        # --- Konflikt + simulator --------------------------------------------
        st = status_of("POST", "/pricing/bundles", {"name": "E2E dublet", "conditions": {"customer_ids": [key(Z)], "materials": ["Beton"]},
                                                    "base": {"pricing": {"model": "fixed", "amount": "1"}}, "surcharges": []}, t=ha)
        ok(st == 409, "17 samme betingelser som en eksisterende aftale -> 409 konflikt")
        draft = {"name": "E2E sim", "conditions": {"customer_ids": [key(Z)]}, "base": {"pricing": {"model": "fixed", "amount": "1.000"}},
                 "surcharges": [{"category": "weekend", "unit": "kr", "value": "500"}]}
        sat = call("POST", "/pricing/simulate", {"scenario": {"customer_id": key(Z), "day_type": "saturday", "task_type": "levering"}, "draft": draft}, t=ha)
        wd = call("POST", "/pricing/simulate", {"scenario": {"customer_id": key(Z), "day_type": "weekday", "task_type": "levering"}, "draft": draft}, t=ha)
        ok(sat["total"] == 1500 and wd["total"] == 1000, "18 weekendtillæg gælder kun lør/søn (auto-betingelse)")
        simu = call("POST", "/pricing/simulate", {"scenario": {"customer_id": key(Y), "task_type": "levering", "units": {"paller": 10}, "stops": 4}}, t=ha)
        ok(simu["total"] == 1500 + 400, "19 simulator: 10 paller + 4 stop = 1.900")
        n = tour(ha, c, X, remark="ikke haster")
        ok(db.tours.find_one({"id": n}, {"_id": 0, "priority": 1})["priority"] == "normal", "20 'ikke haster' i noten forbliver normal")
    finally:
        c.run()


if __name__ == "__main__":
    run()
