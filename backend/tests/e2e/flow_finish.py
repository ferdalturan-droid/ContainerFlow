"""Ét afslutningskald (POST /tours/{id}/finish): sikkert at gentage (op_id),
afvigelseskode + besked, ventetid, hængere - og serier af gentagne ture,
prisstatus til Ture-siden og firmaets afslutnings-indstillinger (2026-10-18)."""
from _e2e import *  # noqa: F401,F403


def run():
    c = Cleanup()
    ha, drv = login(HANSEN_ADMIN), login(HANSEN_DRIVER)
    nik_id, nik = user_id(HANSEN_DRIVER), user_name(HANSEN_DRIVER)
    hansen = disable_company_rules(c, HANSEN_ADMIN)
    st0 = db.price_settings.find_one({"company_id": hansen}, {"_id": 0}) or {}
    c.restore.append(("price_settings", {"company_id": hansen}, {
        "deviation_codes": st0.get("deviation_codes") or [], "unified_finish": bool(st0.get("unified_finish")),
        "auto_approve_waiting_min": st0.get("auto_approve_waiting_min", 0)}))
    try:
        call("PUT", "/pricing/settings", {"deviation_codes": ["Lukket", "E2E Container blokeret"], "unified_finish": True,
                                          "auto_approve_waiting_min": 0}, t=ha)
        fs = call("GET", "/driver/finish-settings", t=drv)
        ok("E2E Container blokeret" in fs["codes"] and fs["unified_finish"] is True, "1 chaufføren får firmaets koder og 'ét afslutningsark'")

        body = {"date": today(), "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "levering",
                "private_company": "E2E Finish ApS", "is_private": True, "trailer_count": 1,
                "cargo_lines": [{"text": "Paller", "qty": 8, "unit": "paller"}], "capture": {"quantity": True}}
        tid = call("POST", "/tours/bulk", [body], t=ha)[0]["id"]
        c.tours.append(tid)
        call("PUT", f"/tours/{tid}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("PUT", f"/tours/{tid}", {"on_way": True, "on_way_time": "08:00", "claimed_by": nik, "claimed_by_id": nik_id}, t=drv)
        op = new_id()
        fb = {"op_id": op, "cargo_actuals": [7], "trailer_count": 0, "time": "09:00", "issue_code": "Lukket",
              "message": "1 palle manglede", "waiting_min": 25}
        r1 = call("POST", f"/tours/{tid}/finish", fb, t=drv)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(r1["ok"] and t["completed"] and t["cargo_lines"][0]["actual_qty"] == 7, "2 ét kald afslutter turen med 7 paller")
        ok(t.get("trailer_count_actual") == 0 and t.get("trailer_confirmed") is True, "3 hængere (0 af 1 planlagt) gemt i samme kald")
        ok((t.get("finish_issue") or {}).get("code") == "Lukket", "4 afvigelseskode gemt på turen")
        msgs = db.tour_messages.count_documents({"tour_id": tid})
        reqs = db.tour_change_requests.count_documents({"tour_id": tid})
        ok(msgs == 1 and reqs == 1 and r1["waiting"] == "pending", "5 besked i tråden + ventetid sendt til godkendelse")
        r2 = call("POST", f"/tours/{tid}/finish", fb, t=drv)
        ok(r2.get("repeated") and db.tour_messages.count_documents({"tour_id": tid}) == msgs
           and db.tour_change_requests.count_documents({"tour_id": tid}) == reqs,
           "6 samme afslutning sendt igen (fx fra offline-køen) gør intet to gange")
        ok(status_of("POST", f"/tours/{tid}/finish", {"op_id": new_id()}, t=ha) == 403, "7 kun chaufføren kan bruge afslutnings-kaldet")

        # Tildelt men ikke "taget": afslutningen tager turen og gemmer hængere
        t2 = call("POST", "/tours/bulk", [{**body, "trailer_count": 2}], t=ha)[0]["id"]
        c.tours.append(t2)
        call("PUT", f"/tours/{t2}", {"driver_id": nik_id, "driver_name": nik}, t=ha)
        call("POST", f"/tours/{t2}/finish", {"op_id": new_id(), "cargo_actuals": [8], "trailer_count": 1}, t=drv)
        tt = db.tours.find_one({"id": t2}, {"_id": 0})
        ok(tt["completed"] and tt.get("claimed_by_id") == nik_id and tt.get("trailer_count_actual") == 1,
           "7a tildelt tur (ikke startet) kan afsluttes - hængere gemmes også")

        ps = call("GET", "/pricing/status", t=ha, params={"ids": tid})
        ok(ps.get(tid, {}).get("status") == "missing" and ps[tid].get("pending") == 1,
           f"8 prisstatus til Ture-siden: {ps.get(tid, {}).get('label')} + 'rettelse venter' (ingen beløb)")
        ok("total" not in str(ps), "9 prisstatus indeholder ingen beløb")

        # Serie: 3 hverdage
        sid = new_id()
        days = [next_weekday(3), next_weekday(4), next_weekday(5)]
        days = sorted(set(days))
        bodies = [{"date": d, "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "levering",
                   "private_company": "E2E Serie ApS", "is_private": True, "series_id": sid, "remark": "gammel note",
                   "cargo_lines": [{"text": "Kasser", "qty": 3, "unit": "stk"}]} for d in days]
        ids = [x["id"] for x in call("POST", "/tours/bulk", bodies, t=ha)]
        c.tours += ids
        info = call("GET", f"/tours/series/{sid}", t=ha, params={"from_date": days[1]})
        ok(info["count"] == len(days) - 1, f"10 serien kender de kommende ture ({info['count']})")
        up = call("PUT", f"/tours/series/{sid}", {"from_date": days[1], "fields": {"remark": "ny note", "date": "2030-01-01"}}, t=ha)
        notes = [db.tours.find_one({"id": i}, {"_id": 0, "remark": 1, "date": 1}) for i in ids]
        ok(up["updated"] == len(days) - 1 and notes[0]["remark"] == "gammel note" and all(n["remark"] == "ny note" for n in notes[1:])
           and all(n["date"] != "2030-01-01" for n in notes), "11 'ret resten af serien' retter kun kommende ture - og aldrig datoen")
        de = call("DELETE", f"/tours/series/{sid}", t=ha, params={"from_date": days[1]})
        ok(de["deleted"] == len(days) - 1 and db.tours.count_documents({"series_id": sid}) == 1, "12 'slet resten af serien' beholder turen før datoen")
    finally:
        c.run()


if __name__ == "__main__":
    run()
