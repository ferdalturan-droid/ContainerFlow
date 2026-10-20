"""Gods-tur hos et premium-firma: "Ved afslutning" (capture), mængde i linjens
enhed, billeder, hængere planlagt mod kørt, aftalt pris + ventetid,
automatisk godkendelse af kort ventetid (2026-10-18)."""
from _e2e import *  # noqa: F401,F403

CUST = "E2E Byg ApS"


def run():
    c = Cleanup()
    ha, drv = login(HANSEN_ADMIN), login(HANSEN_DRIVER)
    nik_id, nik = user_id(HANSEN_DRIVER), user_name(HANSEN_DRIVER)
    hansen = db.users.find_one({"email": HANSEN_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    settings = db.price_settings.find_one({"company_id": hansen}, {"_id": 0, "auto_approve_waiting_min": 1}) or {}
    c.restore.append(("price_settings", {"company_id": hansen}, {"auto_approve_waiting_min": settings.get("auto_approve_waiting_min", 0)}))
    c.customers.append(CUST)
    disable_company_rules(c, HANSEN_ADMIN)
    try:
        db.logistics_customers.delete_many({"name": CUST})
        cu = call("POST", "/logistics/customers", {"name": CUST, "cvr": "11223344"}, t=ha)
        ok(cu.get("price_key") == "firma:e2e byg aps", "1 kunde i registret får en fast prisnøgle")
        body = {"date": today(), "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "afhent_lever",
                "private_company": CUST, "is_private": True, "trailer_count": 2,
                "address_parts": {"street": "Industrivej 22", "postal": "4600", "city": "Køge"},
                "facility": "Nordhavn Etape 2",
                "cargo_lines": [{"text": "Køkkenelementer", "trailer": 1, "qty": 12, "unit": "paller"},
                                {"text": "Beton", "trailer": 2, "qty": 2, "unit": "ton"}],
                "capture": {"quantity": True, "photo": True}, "agreed_price": 1100, "agreed_add_waiting": True}
        tid = call("POST", "/tours/bulk", [body], t=ha)[0]["id"]
        c.tours.append(tid)
        t0 = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t0["capture"] == {"quantity": True, "photo": True} and t0["fraction"] == "Køkkenelementer + Beton",
           "2 tur gemt med 'Ved afslutning' og to indholdslinjer")
        call("PUT", f"/tours/{tid}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "08:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        t1 = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t1.get("trailer_source") == "planned" and t1.get("trailer_confirmed") is True, "3 planlagte hængere tæller som bekræftet")
        call("PUT", f"/driver/tours/{tid}/trailer", {"used_trailer": True, "trailer_count": 1}, t=drv)
        img = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
        ph = call("POST", f"/tours/{tid}/photos", {"image": img}, t=drv)
        ok(ph.get("photo_count") == 1, "4 chaufføren uploader et billede")
        ok(status_of("POST", f"/tours/{tid}/photos", {"image": img}, t=login(CITY_DRIVER)) == 403, "5 chauffør fra et andet firma kan ikke uploade")
        call("PUT", f"/tours/{tid}", {"completed": True, "time": "10:30", "cargo_actuals": [11, 1.8],
                                     "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        t2 = db.tours.find_one({"id": tid}, {"_id": 0})
        ok([l.get("actual_qty") for l in t2["cargo_lines"]] == [11.0, 1.8] and float(t2.get("weight") or 0) == 1800,
           "6 registreret 11 paller + 1,8 ton -> vægt 1.800 kg (kun kg/ton tæller som vægt)")
        ok(len(call("GET", f"/tours/{tid}/photos", t=ha)) == 1, "7 planlæggeren ser billedet")
        # 2026-10-20: Vedhæftninger i arkivet - også på en tur uden container
        arc = call("GET", "/attachments-archive", t=ha, params={"search": tid})["items"]
        prow = next((a for a in arc if a["kind"] == "photo" and a["tour_id"] == tid), None)
        ok(prow and prow["tour_kind"] == "goods" and prow["driver_name"] == nik and "data" not in prow,
           "7a billedet står i Arkiv > Vedhæftninger (type Billede, varekørsel, uden selve billeddata i listen)")
        full = call("GET", f"/tour-photos/{ph['id'] if 'id' in ph else prow['id']}", t=ha)
        ok(full["url"].startswith("data:image/jpeg;base64,") and full["tour"]["id"] == tid and full["siblings"] == [prow["id"]],
           "7b billedet kan åbnes fra arkivet med turens oplysninger")
        ilk_a = login(ILK_ADMIN)
        ok(not [a for a in call("GET", "/attachments-archive", t=ilk_a, params={"search": tid})["items"] if a["tour_id"] == tid]
           and status_of("GET", f"/tour-photos/{prow['id']}", t=ilk_a) == 403,
           "7c et andet logistikfirma ser hverken billedet i arkivet eller kan åbne det")
        rc = call("POST", "/receipts/save-for-tour", {"tour_id": tid, "image_data": img, "content_type": "image/jpeg",
                                                       "description": "Vedhæftet ved afslutning", "final_weight_kg": None,
                                                       "user_name": nik, "skip_tour_update": True}, t=drv)
        arc = call("GET", "/attachments-archive", t=ha, params={"search": tid})["items"]
        kinds = sorted(a["kind"] for a in arc if a["tour_id"] == tid)
        only_ph = call("GET", "/attachments-archive", t=ha, params={"search": tid, "kind": "photo"})["items"]
        ok(rc.get("receipt_id") and kinds == ["photo", "receipt"] and all(a["kind"] == "photo" for a in only_ph)
           and float(db.tours.find_one({"id": tid}, {"_id": 0, "weight": 1}).get("weight") or 0) == 1800,
           "7d en seddel uden vægt gemmes også (rører ikke turens vægt) - begge typer står samlet, filter virker")
        row = report_row(ha, tid)
        ok(row and row["price"]["total"] == 1100 and row["trailer_count"] == 1,
           f"8 aftalt pris 1.100, hængere kørt 1 (planlagt 2) ({row and row['price']['total']})")
        # Kort ventetid godkendes automatisk når indstillingen er sat
        call("PUT", "/pricing/settings", {"auto_approve_waiting_min": 15}, t=ha)
        req = call("POST", f"/driver/tours/{tid}/change-request", {"waiting_min": 10, "comment": "E2E ventede 10 min"}, t=drv)
        ok(req["status"] == "approved" and req.get("auto_approved"), "9 ventetid ≤ 15 min godkendes automatisk")
        req2 = call("POST", f"/driver/tours/{tid}/change-request", {"waiting_min": 40, "comment": "E2E ventede 40 min"}, t=drv)
        ok(req2["status"] == "pending", "10 længere ventetid (40 min) venter på godkendelse")
        reqs = call("GET", "/pricing/requests", t=ha)
        mine = next((r for r in reqs if r["id"] == req2["id"]), {})
        ok(any("ventetidstillæg" in w for w in (mine.get("warnings") or [])),
           f"11 godkendelser advarer: intet ventetidstillæg = 0 kr ({(mine.get('warnings') or ['-'])[0][:70]})")

        # Tur uden "registrér mængde" kan afsluttes uden vægt
        b2 = {**body, "capture": {"quantity": False, "photo": False}, "agreed_price": None, "trailer_count": 0,
              "cargo_lines": [{"text": "Flyttekasser", "qty": 30, "unit": "stk"}]}
        t3 = call("POST", "/tours/bulk", [b2], t=ha)[0]["id"]
        c.tours.append(t3)
        call("PUT", f"/tours/{t3}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{t3}", {"on_way": True, "on_way_time": "11:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        ok(status_of("PUT", f"/tours/{t3}", {"completed": True, "time": "11:30", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv) == 200,
           "12 tur uden 'registrér mængde' afsluttes uden vægt")
    finally:
        c.run()


if __name__ == "__main__":
    run()
