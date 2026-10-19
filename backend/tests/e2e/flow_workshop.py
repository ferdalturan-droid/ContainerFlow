"""2026-10-19: Værksteds-ture fra bestillingssiden og "én partner pr. bestilling".
- Til værksted: turen starter på pladsen (containeren) og slutter på værkstedet.
- Afhent fra værksted: starter på værkstedet og slutter på pladsen.
- Byt container: kun pladsen. Containeradressen har byen med (Google Maps).
- En bestilling går altid til præcis ét logistikfirma - også når pladsen har
  flere, og bestillingen kommer uden partnervalg."""
from _e2e import *  # noqa: F401,F403

ORDER_USER = "ferdalturan+hf.1121.medarbejder1@gmail.com"  # Nordkysten - Folehaven 1 (to partnere)
WS = {"workshop_name": "E2E Værksted", "workshop_address": "Industrivej 12, 3000 Helsingør", "workshop_phone": "49 21 00 10"}


def run():
    c = Cleanup()
    ou = login(ORDER_USER)
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    pl = db.plads.find_one({"location_code": "1121"}, {"_id": 0, "address": 1, "city": 1, "assigned_logistics_company_ids": 1,
                                                       "partner_materials": 1})
    home = f"{pl['address']}, {pl['city']}"
    mat = (call("GET", "/locations/code/1121").get("materials") or ["Pap"])[0]
    base = {"location_code": "1121", "material": mat, "container_number": "Container 1", "priority": "normal",
            "comment": "E2E værksted", "order_date": in_days(3), "partner_id": ilk}

    def order(**kw):
        o = call("POST", "/customer-orders/submit", {**base, **kw}, t=ou)
        c.tours.append(o["tour_id"]); c.orders.append(o["order_id"])
        return o, db.tours.find_one({"id": o["tour_id"]}, {"_id": 0})

    try:
        o1, t1 = order(tour_type="vaerksted", **WS)
        ok(t1["address"] == home and t1["facility"] == WS["workshop_address"] and t1["workshop_name"] == WS["workshop_name"]
           and t1["workshop_phone"] == WS["workshop_phone"],
           f"1 Til værksted: pladsen ({t1['address']}) -> værkstedet ({t1['facility']}), navn + tlf. på turen")
        o2, t2 = order(tour_type="afhent_vaerksted", **WS)
        ok(t2["address"] == WS["workshop_address"] and t2["facility"] == home,
           f"2 Afhent fra værksted: værkstedet -> pladsen ({t2['facility']})")
        o3, t3 = order(tour_type="flyt", container_number="Container 2")
        ok(t3["address"] == home and not t3.get("workshop_address"), "3 Byt container: kun pladsen (med by til Google Maps)")
        ok(set(t1["assigned_logistics_company_ids"]) == {ilk}, "4 valgt partner -> kun den partner")

        # Kunden retter bestillingen fra "Byt container" til "Til værksted" -> turens rute følger med
        call("PUT", f"/customer-orders/{o3['order_id']}", {"tour_type": "vaerksted", **WS}, t=ou)
        t3b = db.tours.find_one({"id": o3["tour_id"]}, {"_id": 0})
        ok(t3b["tour_type"] == "vaerksted" and t3b["facility"] == WS["workshop_address"] and t3b["workshop_name"] == WS["workshop_name"],
           "5 rettet bestilling (byt -> værksted) giver turen værkstedet")

        # Én partner pr. bestilling, også uden partnervalg
        partners = pl.get("assigned_logistics_company_ids") or []
        pm = pl.get("partner_materials") or {}
        ok(len(partners) >= 2, f"6 Folehaven har flere partnere ({len(partners)})")
        st = status_of("POST", "/customer-orders/submit", {**base, "partner_id": "", "tour_type": "normal", "container_number": "Container 3",
                                                           "custom_address": "Folehaven 1", "material": "E2E ukendt materiale"}, t=ou)
        ok(st == 400, "7 uden partnervalg og uden entydigt materiale -> afvist (før: sendt til alle partnere)")
        only = next(((p, m) for p in partners for m in (pm.get(p) or [])
                     if sum(1 for q in partners if m in (pm.get(q) or [])) == 1), None)
        if only:
            o4 = call("POST", "/customer-orders/submit", {**base, "partner_id": "", "tour_type": "flyt", "container_number": "Container 4",
                                                          "material": only[1]}, t=ou)
            c.tours.append(o4["tour_id"]); c.orders.append(o4["order_id"])
            t4 = db.tours.find_one({"id": o4["tour_id"]}, {"_id": 0})
            ok(t4["assigned_logistics_company_ids"] == [only[0]], f"8 materiale kun én partner kører ({only[1]}) -> kun den partner")
        open_multi = db.tours.count_documents({"assigned_logistics_company_ids.1": {"$exists": True}, "completed": {"$ne": True},
                                               "deleted": {"$ne": True}, "order_id": {"$nin": ["", None]}})
        ok(open_multi == 0, f"9 ingen åbne bestillings-ture med flere logistikfirmaer ({open_multi})")
    finally:
        c.run()


if __name__ == "__main__":
    run()
