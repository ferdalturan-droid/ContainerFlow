"""Én opgave = én tur, også med flere stop. Kontakt pr. stop, tidsstempel
ved afkrydsning, planlægger retter stop uden at miste chaufførens kryds."""
from _e2e import *  # noqa: F401,F403


def run():
    c = Cleanup()
    ha, drv = login(HANSEN_ADMIN), login(HANSEN_DRIVER)
    nik_id, nik = user_id(HANSEN_DRIVER), user_name(HANSEN_DRIVER)
    disable_company_rules(c, HANSEN_ADMIN)
    try:
        b = call("POST", "/pricing/bundles", {"name": "E2E Stop", "conditions": {"customer_ids": ["firma:e2e stop aps"]},
                                              "base": {"pricing": {"model": "fixed", "amount": "500"}},
                                              "surcharges": [{"category": "stop", "unit": "kr", "value": "100", "included": 2}],
                                              "effective": "all"}, t=ha)
        c.bundles.append(b["bundle_id"])
        stops = [{"kind": "pickup", "street": "Gildbrovej 7", "postal": "2635", "city": "Ishøj",
                  "note": "Port 3", "contact_name": "Hans", "contact_phone": "+45 12 34 56 78"},
                 {"kind": "pickup", "street": "Vej 2", "postal": "4600", "city": "Køge"},
                 {"kind": "delivery", "street": "Industrivej 22", "postal": "4600", "city": "Køge"}]
        res = call("POST", "/tours/bulk", [{"date": today(), "plads": "Hansen Depot Køge", "tour_kind": "goods",
                                            "tour_type": "afhent_lever", "private_company": "E2E Stop ApS", "is_private": True,
                                            "cargo_lines": [{"text": "Paller", "qty": 4, "unit": "paller"}], "stops": stops}], t=ha)
        ok(len(res) == 1, "1 én formular med 3 stop -> én tur")
        tid = res[0]["id"]
        c.tours.append(tid)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        s0 = t["stops"][0]
        ok(t["address"] == "Gildbrovej 7, 2635 Ishøj" and t["facility"] == "Industrivej 22, 4600 Køge",
           "2 adresse = første afhentning, facilitet = sidste aflevering")
        ok(s0["note"] == "Port 3" and s0["contact_name"] == "Hans" and s0["contact_phone"] == "+45 12 34 56 78",
           "3 note og kontakt (navn + telefon) gemmes pr. stop")
        call("PUT", f"/tours/{tid}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        ok(status_of("POST", f"/tours/{tid}/stops/{s0['id']}/done", {"done": True}, t=login(CITY_DRIVER)) == 403,
           "4 chauffør fra et andet firma kan ikke krydse af")
        call("POST", f"/tours/{tid}/stops/{s0['id']}/done", {"done": True}, t=drv)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        done_at = t["stops"][0]["done_at"]
        ok(len(done_at) >= 19 and done_at[:10] == today(), f"5 afkrydsning gemmer fuldt tidsstempel ({done_at})")
        new_stops = [dict(x) for x in t["stops"]] + [{"kind": "delivery", "street": "Ny vej 9", "postal": "4000", "city": "Roskilde"}]
        call("PUT", f"/tours/{tid}", {"stops": new_stops}, t=ha)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(len(t["stops"]) == 4 and t["stops"][0]["done_at"] == done_at and t["facility"].startswith("Ny vej 9"),
           "6 planlæggeren tilføjer et stop: krydset bevares, facilitet = ny sidste aflevering")
        ok(db.tours.count_documents({"private_company": "E2E Stop ApS"}) == 1, "7 stadig kun én tur-record")

        # Kvittering og afvigelse pr. stop, ekstra stop fra chaufføren
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "08:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        s2, s3 = t["stops"][2], t["stops"][3]
        call("POST", f"/tours/{tid}/stops/{s2['id']}/done", {"done": True, "receiver_name": "Bent"}, t=drv)
        call("POST", f"/tours/{tid}/stops/{s3['id']}/done", {"done": True, "issue": {"code": "Lukket", "text": "Port låst"}}, t=drv)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t["stops"][2].get("receiver_name") == "Bent", "8 aflevering kvitteres med modtagerens navn")
        ok(t["stops"][3].get("issue") == {"code": "Lukket", "text": "Port låst"} and t["stops"][3]["done_at"],
           "9 ét stop 'kunne ikke gennemføres' (kode + tekst) - turen kører videre")
        ok(db.tour_messages.count_documents({"tour_id": tid, "text": {"$regex": "Stop ikke gennemført"}}) == 1,
           "10 planlæggeren får afvigelsen som besked på turen")
        added = call("POST", f"/tours/{tid}/stops", {"kind": "delivery", "street": "Ekstra vej 1", "postal": "2600", "city": "Glostrup", "note": "Kunden bad om det"}, t=drv)
        new = added["stops"][-1]
        ok(new.get("added_by_driver") is True and new.get("approved") is False, "11 chaufføren tilføjer et stop (markeret, ikke godkendt)")
        cur = db.tours.find_one({"id": tid}, {"_id": 0})["stops"]
        edited = [{k: v for k, v in x.items() if k not in ("receiver_name", "issue", "added_by_driver", "approved", "done_at", "done_by")} for x in cur]
        edited[0]["note"] = "Port 4"
        call("PUT", f"/tours/{tid}", {"stops": edited}, t=ha)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t["stops"][2].get("receiver_name") == "Bent" and t["stops"][3].get("issue", {}).get("code") == "Lukket"
           and t["stops"][-1].get("added_by_driver") and t["stops"][0]["note"] == "Port 4" and t["stops"][2]["done_at"],
           "12 planlæggeren gemmer stop-listen (som fra formularen): kvittering, afvigelse og ekstra stop bevares")
        ok(price_of(ha, tid)["price"]["total"] == 500 + 2 * 100, "13a ikke-godkendt ekstra stop tæller ikke i stoptillægget (4 stop: 700)")
        call("POST", f"/tours/{tid}/stops/{new['id']}/approve", t=ha)
        ok(price_of(ha, tid)["price"]["total"] == 500 + 3 * 100, "13b efter godkendelse tæller det med (5 stop: 800)")
        ok(db.tours.find_one({"id": tid}, {"_id": 0})["stops"][-1].get("approved") is True, "13 planlæggeren godkender det ekstra stop")
        ok(status_of("POST", f"/tours/{tid}/stops/{new['id']}/approve", t=drv) == 403, "14 chaufføren kan ikke selv godkende")
    finally:
        c.run()


if __name__ == "__main__":
    run()
