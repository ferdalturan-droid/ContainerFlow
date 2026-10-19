"""2026-10-19: Faste tømninger.

Lokationsadmin sætter en fast tømning op pr. container. Serveren laver hver
tømning om til en almindelig bestilling 7 dage før (med dagens
leveringsadresse fra kundens kalender), aldrig to gange for samme dag.
Medarbejderen kan springe en over og bestille ekstra. Ret, pause og stop
rydder de allerede bestilte tømninger, der ikke længere skal køres."""
from datetime import date, timedelta

from _e2e import *  # noqa: F401,F403

LA_NORD = "ferdalturan+hf.la.nordkysten@gmail.com"     # lokationsadmin for 1121
ORDER_USER = "ferdalturan+hf.1121.medarbejder1@gmail.com"
ARGO_LA = "ferdalturan+argo.la.roskilde@gmail.com"


def run():
    c = Cleanup()
    la, ou, ilk_t = login(LA_NORD), login(ORDER_USER), login(ILK_ADMIN)
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    mats = call("GET", "/locations/1121/containers", params={"partner_id": ilk})["materials"]
    mat = mats[0]["material"]
    today = date.fromisoformat(globals()["today"]())
    window = [today + timedelta(days=i) for i in range(8)]
    expected = [d.isoformat() for d in window if d.weekday() < 5]
    sid = None

    def orders_of(s):
        return list(db.container_orders.find({"fixed_schedule_id": s}, {"_id": 0}))

    try:
        st = status_of("POST", "/org/fixed-schedules", {"location_code": "1121", "material": mat, "container_number": "E2E Fast 1",
                                                        "weekdays": [0, 1, 2, 3, 4], "partner_id": ilk}, t=ou)
        ok(st == 403, "1 en medarbejder kan ikke oprette faste tømninger (det gør lokations-/kundeadmin)")

        r = call("POST", "/org/fixed-schedules", {"location_code": "1121", "material": mat, "container_number": "E2E Fast 1",
                                                  "weekdays": [0, 1, 2, 3, 4], "interval_weeks": 1, "start_date": today.isoformat(),
                                                  "partner_id": ilk, "comment": "E2E fast"}, t=la)
        sid = r["id"]
        gen = r["generated"]
        ok(sorted(g["date"] for g in gen) == expected and all(g["status"] in ("created", "skipped_closed") for g in gen),
           f"2 hverdage de næste 7 dage bliver til bestillinger ({len([g for g in gen if g['status'] == 'created'])} oprettet, "
           f"{len([g for g in gen if g['status'] == 'skipped_closed'])} lukket)")
        os_ = orders_of(sid)
        c.orders += [o["id"] for o in os_]; c.tours += [o["tour_id"] for o in os_ if o.get("tour_id")]
        t0 = db.tours.find_one({"id": os_[0]["tour_id"]}, {"_id": 0}) if os_ else {}
        ok(os_ and all(o["assigned_logistics_company_ids"] == [ilk] and o["created_by_name"] == "Fast tømning" for o in os_)
           and t0.get("fixed_schedule_id") == sid and t0.get("fixed_label") and t0.get("address"),
           "3 almindelige bestillinger + ture med leveringsadresse, kun ILK, mærket 'Fast tømning'")
        r2 = call("POST", f"/org/fixed-schedules/{sid}/resume", {}, t=la)
        ok(r2["generated"] == [] and len(orders_of(sid)) == len(os_), "4 kører jobbet igen, oprettes ingen dubletter")
        mine = call("GET", "/container-orders/by-location/1121", t=ou, params={"all": 1, "include_cancelled": "true"})
        ok(sum(1 for o in mine if o.get("fixed_schedule_id") == sid) == len(os_), "5 medarbejderen ser de faste tømninger i Mine bestillinger")
        lt = [x for x in call("GET", "/tours", t=ilk_t, params={"date": os_[0]["order_date"]}) if x["id"] == os_[0]["tour_id"]] if os_ else []
        ok(lt and lt[0].get("fixed_label"), "6 logistikfirmaet ser turen som fast tømning")

        # Ekstra bestilling: en anden dag er tilladt, samme dag er en dobbeltbestilling
        extra_day = (today + timedelta(days=10)).isoformat()
        base = {"location_code": "1121", "material": mat, "container_number": "E2E Fast 1", "priority": "normal", "tour_type": "normal",
                "custom_address": "Energivej 10, 3000 Helsingør", "partner_id": ilk, "comment": "E2E ekstra"}
        ex = call("POST", "/customer-orders/submit", {**base, "order_date": extra_day}, t=ou)
        c.orders.append(ex["order_id"]); c.tours.append(ex["tour_id"])
        ok(bool(ex["order_id"]), "7 containeren blev fuld før tid: ekstra bestilling en anden dag er tilladt")
        if os_:
            ok(status_of("POST", "/customer-orders/submit", {**base, "order_date": os_[0]["order_date"]}, t=ou) == 409,
               "8 men samme dag som en fast tømning er en dobbeltbestilling")

        # Spring én over - den kommer ikke igen
        if len(os_) >= 2:
            skip = os_[-1]
            call("POST", f"/customer-orders/{skip['id']}/cancel", {"reason": "Sprunget over - ikke fuld"}, t=ou)
            call("POST", f"/org/fixed-schedules/{sid}/resume", {}, t=la)
            again = [o for o in orders_of(sid) if o["order_date"] == skip["order_date"] and o["status"] != "cancelled"]
            ok(not again, "9 en tømning der er sprunget over, oprettes ikke igen")

        # Ret: fjern en ugedag -> den dags bestilling annulleres, resten får ny prioritet
        drop = next((d for d in [today + timedelta(days=i) for i in range(1, 6)] if d.weekday() < 5), None)
        keep_wd = [w for w in [0, 1, 2, 3, 4] if w != drop.weekday()]
        call("PUT", f"/org/fixed-schedules/{sid}", {"location_code": "1121", "weekdays": keep_wd, "interval_weeks": 1,
                                                    "start_date": today.isoformat(), "partner_id": ilk, "priority": "haster",
                                                    "comment": "E2E rettet"}, t=la)
        now = orders_of(sid)
        dropped = [o for o in now if o["order_date"] == drop.isoformat()]
        live = [o for o in now if o["status"] == "pending"]
        ok(dropped and all(o["status"] == "cancelled" for o in dropped) and live and all(o["priority"] == "haster" for o in live),
           "10 rettelse: fjernet ugedag annulleres, de øvrige får den nye prioritet")

        # Pause -> kommende annulleres; genoptag -> de kommer igen (ikke den der blev sprunget over)
        p = call("POST", f"/org/fixed-schedules/{sid}/pause", {}, t=la)
        ok(p["cancelled"] == len(live) and not [o for o in orders_of(sid) if o["status"] == "pending"],
           f"11 pause annullerer de {len(live)} bestilte tømninger der ikke er startet")
        r3 = call("POST", f"/org/fixed-schedules/{sid}/resume", {}, t=la)
        ok(len([g for g in r3["generated"] if g["status"] == "created"]) >= 1, "12 genoptag opretter dem igen")
        for o in orders_of(sid):
            if o["id"] not in c.orders:
                c.orders.append(o["id"]); c.tours.append(o.get("tour_id"))

        ok(status_of("GET", "/org/fixed-schedules", t=login(ARGO_LA), params={"location_code": "1121"}) in (403, 404),
           "13 en anden kundes lokationsadmin kan ikke se pladsens faste tømninger")
        lst = call("GET", "/org/fixed-schedules", t=la, params={"location_code": "1121"})
        ok(any(x["id"] == sid and x["next_dates"] and x["text"] for x in lst), "14 listen viser hvornår og de næste datoer")

        stp = call("DELETE", f"/org/fixed-schedules/{sid}", t=la)
        ok(stp["cancelled"] >= 1 and not [o for o in orders_of(sid) if o["status"] == "pending"]
           and not any(x["id"] == sid for x in call("GET", "/org/fixed-schedules", t=la, params={"location_code": "1121"})),
           "15 stop annullerer de kommende og fjerner den faste tømning")
    finally:
        if sid:
            for o in orders_of(sid):
                c.orders.append(o["id"]); c.tours.append(o.get("tour_id"))
            db.fixed_schedules.delete_many({"id": sid})
            db.fixed_schedule_runs.delete_many({"schedule_id": sid})
        c.tours = [t for t in c.tours if t]
        c.run()


if __name__ == "__main__":
    run()
