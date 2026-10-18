"""P8 (2026-10-18): Tid på timeprisede ture. Kørselsdatoen er startdagen
(en lørdagstur afsluttet søndag er en lørdagstur), start-tidsstempel ved
start, rettet starttid fra afslutningsarket går til godkendelse, og Ture-siden
får at vide hvilke ture der er på timepris."""
from _e2e import *  # noqa: F401,F403

CUST = "E2E Tid ApS"


def run():
    c = Cleanup()
    ha, drv = login(HANSEN_ADMIN), login(free_driver([HANSEN_DRIVER, "ferdalturan+hansen.chauffoer2@gmail.com"]))
    d_email = next(e for e in (HANSEN_DRIVER, "ferdalturan+hansen.chauffoer2@gmail.com") if login(e) == drv)
    nik_id, nik = user_id(d_email), user_name(d_email)
    hansen = disable_company_rules(c, HANSEN_ADMIN)
    c.customers.append(CUST)
    try:
        db.logistics_customers.delete_many({"name": CUST})
        call("POST", "/logistics/customers", {"name": CUST}, t=ha)
        b = call("POST", "/pricing/bundles", {"name": "E2E timepris", "conditions": {"customer_ids": ["firma:e2e tid aps"]},
                                              "base": {"pricing": {"model": "hourly", "hourly_rate": "600", "rounding_mode": "none",
                                                                   "rounding_minutes": 0, "deduct_pause": False}},
                                              "surcharges": [{"category": "weekend", "unit": "kr", "value": "1000"}],
                                              "effective": "all"}, t=ha)
        c.bundles.append(b["bundle_id"])
        body = {"date": today(), "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "levering",
                "private_company": CUST, "is_private": True, "cargo_lines": [{"text": "Kasser", "qty": 2, "unit": "stk"}]}
        tid = call("POST", "/tours/bulk", [body], t=ha)[0]["id"]
        c.tours.append(tid)
        call("PUT", f"/tours/{tid}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "10:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t.get("on_way_at", "")[:10] == today(), "1 start gemmer fuldt tidsstempel (on_way_at)")
        ok(call("GET", "/pricing/status", t=ha, params={"ids": tid}).get(tid, {}).get("hourly") is True,
           "2 prisstatus fortæller Ture-siden at turen er på timepris")
        r = call("POST", f"/tours/{tid}/finish", {"op_id": new_id(), "start_time": "09:40", "time": "10:01"}, t=drv)
        req = db.tour_change_requests.find_one({"tour_id": tid}, {"_id": 0})
        ok(r["ok"] and req and req["changes"].get("start_time") == "09:40" and req["status"] == "pending",
           "3 rettet starttid fra afslutningsarket sendes som rettelse til godkendelse")

        # Over midnat: startet lørdag 23:30, afsluttet søndag 00:20 -> lørdag
        sat = "2026-10-17"
        for i, with_ts in enumerate((True, False)):
            oid = new_id()
            doc = {"id": oid, "company_id": hansen, "date": sat, "plads": "Hansen Depot Køge", "tour_kind": "goods",
                   "tour_type": "levering", "private_company": CUST, "is_private": True, "fraction": "E2E midnat",
                   "address": "E2E Midnatsvej 1", "claimed_by": nik, "claimed_by_id": nik_id, "on_way": False,
                   "on_way_time": "23:30", "time": "00:20", "completed": True, "completed_at": "2026-10-18T00:20:00+02:00",
                   "created_at": "2026-10-17T08:00:00+00:00", "assigned_logistics_company_ids": [hansen]}
            if with_ts:
                doc["on_way_at"] = "2026-10-17T23:30:00+02:00"
            db.tours.insert_one(doc)
            c.tours.append(oid)
            p = price_of(ha, oid)
            ok(p["service_date"] == sat and p["day_type"] == "saturday" and p["price"].get("total") == 500 + 1000,
               f"{4 + i} tur over midnat ({'med' if with_ts else 'uden'} start-tidsstempel) er lørdagens tur: 50 min + weekend ({p['service_date']}, {p['price'].get('total')})")
            db.tours.delete_one({"id": oid})  # ellers deler de to testture tiden (samme chauffør, samme tidsrum)
    finally:
        c.run()


if __name__ == "__main__":
    run()
