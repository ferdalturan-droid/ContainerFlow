"""B2B containerflow: bestilling på en genbrugsplads -> tur -> chauffør ->
vægt -> spejling til bestillingen -> økonomi. Plus hænger-bekræftelse,
rettelser og spærring når turen er faktureret (2026-10-18)."""
from _e2e import *  # noqa: F401,F403


def run():
    c = Cleanup()
    d_email = free_driver(ILK_DRIVERS)
    la, drv = login(ILK_ADMIN), login(d_email)
    lars_id, lars = user_id(d_email), user_name(d_email)
    lars_doc = db.users.find_one({"id": lars_id}, {"_id": 0, "active_trailer_id": 1}) or {}
    c.restore.append(("users", {"id": lars_id}, {"active_trailer_id": lars_doc.get("active_trailer_id") or ""}))
    try:
        loc = call("GET", "/locations/code/1101")
        material = (loc.get("materials") or ["Pap"])[0]
        o = call("POST", "/customer-orders/submit", {"partner_id": db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"],
            "location_code": "1101", "material": material, "container_number": "Container 1",
            "priority": "normal", "comment": "E2E-test B2B haster", "order_date": today(), "tour_type": "normal",
            "custom_address": "Energivej 6, 3000 Helsingør", "open_from": "07:00", "open_to": "15:00",
            "delivery_address_id": (db.delivery_addresses.find_one({"location_code": "1101"}, {"_id": 0, "id": 1}) or {}).get("id", ""),
        }, t=login(HF_ORDER_USER))
        tid = o["tour_id"]
        c.tours.append(tid); c.orders.append(o["order_id"])
        tour = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(tour and tour.get("source") == "customer_order", "1 bestilling opretter én tur (source=customer_order)")
        ok(tour.get("priority") == "normal", "2 B2B: 'haster' i kundens kommentar ændrer ikke kundens valgte prioritet")
        ok(not tour.get("capture"), "3 B2B-tur har ingen capture (gammelt afslutningsflow uændret)")
        ok(any(x["id"] == tid for x in call("GET", "/tours", t=la, params={"limit": 500})), "4 ILK ser turen")

        call("PUT", f"/tours/{tid}", {"driver_id": lars_id, "driver_name": lars}, t=la)
        # Chaufføren har valgt en hænger i profilen, men kører turen alene.
        # 2026-10-20: "Med hænger" på en containertur = hængerkørsel, ikke login-hængeren.
        db.users.update_one({"id": lars_id}, {"$set": {"active_trailer_id": "e2e-trailer"}})
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "08:00", "claimed_by": lars, "claimed_by_id": lars_id}, t=drv)
        tour = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(tour.get("run_role") == "solo" and tour.get("used_trailer") is False and tour.get("trailer_confirmed") is True,
           "5 start alene med hænger valgt ved login: solo, ikke 'med hænger'")
        p = price_of(la, tid)["price"]
        ok("Hænger: automatisk, ikke bekræftet" not in (p.get("flags") or []), "6 ingen 'automatisk, ikke bekræftet' på containerture")
        r = call("PUT", f"/driver/tours/{tid}/trailer", {"used_trailer": True}, t=drv)
        p = price_of(la, tid)
        ok(r.get("ignored") and p["trailer_confirmed"] is True and p["trailer"] is False, "7 'Med hænger' ændrer ikke en containertur (kørslen afgør)")

        ok(status_of("POST", f"/tours/{tid}/stops", {"kind": "delivery", "street": "Ekstra 1", "postal": "3000", "city": "Helsingør"}, t=drv) == 400,
           "7a chaufføren kan ikke tilføje stop på en kundebestilling (B2B uændret)")
        call("PUT", f"/tours/{tid}", {"completed": True, "weight": 1850, "time": "09:10", "claimed_by": lars, "claimed_by_id": lars_id}, t=drv)
        order = db.container_orders.find_one({"id": o["order_id"]}, {"_id": 0})
        ok(order and order.get("status") == "completed" and float(order.get("weight_kg") or 0) == 1850,
           "8 bestillingen spejles: status=completed, 1850 kg")
        row = report_row(la, tid)
        ok(row is not None and not row["trailer"] and row["trailer_confirmed"] and row["run_role"] == "solo",
           f"9 rapport-række: solo, ingen hænger ({row and row['price'].get('total')})")

        # Rettelser bagefter: hænger rettes ikke af chaufføren på en containertur
        ok(status_of("POST", f"/driver/tours/{tid}/change-request", {"trailer_count": 1, "comment": "E2E havde hænger"}, t=drv) == 400,
           "10 chaufføren kan ikke rette hænger på en containertur (kørslen afgør, admin retter)")
        req = call("POST", f"/driver/tours/{tid}/change-request", {"start_time": "07:55", "comment": "E2E startede før"}, t=drv)
        req2 = call("POST", f"/driver/tours/{tid}/change-request", {"waiting_min": 20, "comment": "E2E ventede"}, t=drv)
        ok(req2["status"] in ("pending", "approved"), "11 to rettelser af forskellige ting på samme tur er tilladt")
        dup = status_of("POST", f"/driver/tours/{tid}/change-request", {"start_time": "07:50", "comment": "E2E igen"}, t=drv)
        ok(dup == 409, "12 rettelse af det samme (starttid) mens den første venter -> 409")
        call("POST", f"/pricing/requests/{req['id']}/decide", {"approve": True}, t=la)
        call("PUT", f"/pricing/tours/{tid}/adjust", {"note": "E2E kørte på hængeren", "fact_overrides": {"run_role": "trailer", "start_time": "07:55"}}, t=la)
        row = report_row(la, tid)
        ok(row and row["trailer"] is True and row["run_role"] == "trailer" and row["start_time"] == "07:55",
           "13 admin retter kørslen til 'på hængeren' -> med hænger i prisen")

        # Faktureret = frosset registrering
        if row["price"].get("total") is not None:
            call("POST", "/pricing/invoice", {"tour_ids": [tid], "invoiced": True}, t=la)
            def locked_msg(tok):
                try:
                    call("PUT", f"/tours/{tid}", {"weight": 999, "claimed_by": lars}, t=tok)
                    return ""
                except ApiError as e:
                    return detail(e)
            m1, m2 = locked_msg(drv), locked_msg(la)
            ok("faktureret" in m1, f"14 faktureret: chauffør kan ikke rette vægt ({m1})")
            ok("faktureret" in m2, f"15 faktureret: planlægger kan ikke rette vægt ({m2})")
            ok(status_of("PUT", f"/tours/{tid}", {"remark": "E2E note efter fakturering"}, t=la) == 200,
               "16 faktureret: note (ikke registrering) kan stadig rettes")
            ok(status_of("POST", f"/tours/{tid}/photos", {"image": "aGVq"}, t=drv) == 409, "17 faktureret: billeder spærret")
            call("POST", "/pricing/invoice", {"tour_ids": [tid], "invoiced": False}, t=la)
            ok(status_of("PUT", f"/tours/{tid}", {"weight": 1900, "claimed_by": lars}, t=la) == 200, "18 faktureringen fjernet -> kan rettes igen")
        else:
            ok(False, f"14 B2B-turen har ingen pris ({row['price'].get('why')}) - kan ikke teste fakturering")
    finally:
        c.run()


if __name__ == "__main__":
    run()
