"""2026-10-19: "Bestil for kunden" og annullering hele vejen rundt.

På en genbrugsplads-kundes plads opretter logistikfirmaet en rigtig bestilling
på kundens vegne (ikke en fri tur): kunden ser den under Mine bestillinger, den
tæller i rapporter/CO2, og kunden kan annullere den. Annulleres en bestilling,
ser planlæggeren og chaufføren det, og turen kan ikke køres - også når
chaufføren er på vej (så bliver den en forgæves kørsel efter aftalen).
Premium-firmaets egne ture (egne lokationer, stop, Gentag) er uændrede."""
from io import BytesIO

from _e2e import *  # noqa: F401,F403

ORDER_USER = "ferdalturan+hf.1121.medarbejder1@gmail.com"  # Nordkysten - Folehaven 1
DRIVERS = [ILK_DRIVER, "ferdalturan+ilk.chauffoer2@gmail.com", "ferdalturan+ilk.chauffoer3@gmail.com"]


def run():
    c = Cleanup()
    la, ou, hans = login(ILK_ADMIN), login(ORDER_USER), login(HANSEN_ADMIN)
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    pl = db.plads.find_one({"location_code": "1121"}, {"_id": 0})
    hf = pl["company_id"]
    drv_email = free_driver(DRIVERS)
    drv, drv_id = login(drv_email), user_id(drv_email)
    call("POST", "/driver/active-customer", {"customer_id": hf}, t=drv)
    d0 = next_weekday(3)

    def behalf(**kw):
        body = {"location_code": "1121", "plads_name": pl["name"], "material": mat, "container_number": "Container 7",
                "tour_type": "normal", "order_date": d0, "priority": "normal", "comment": "E2E bestil for kunden",
                "custom_address": "Energivej 10, 3000 Helsingør", "requested_by": "Jens, telefon", **kw}
        r = call("POST", "/logistics/customer-orders", body, t=la)
        c.tours.append(r["tour_id"]); c.orders.append(r["order_id"])
        return r

    def tour(tid):
        return db.tours.find_one({"id": tid}, {"_id": 0})

    def order(oid):
        return db.container_orders.find_one({"id": oid}, {"_id": 0})

    try:
        # --- Det kunden selv kan vælge --------------------------------------------
        opts = call("GET", "/logistics/order-options", t=la, params={"location_code": "1121", "plads_name": pl["name"]})
        mat = (opts["materials"] or [{"material": "Pap"}])[0]["material"]
        ok(opts["customer_name"] and opts["materials"] and opts["plads_address"].startswith(pl["address"]),
           f"1 kundens materialer og pladsens adresse ({opts['plads_address']}) til formularen")
        dfl = call("GET", "/logistics/order-defaults", t=la, params={"location_code": "1121", "material": mat, "date": d0,
                                                                    "container": "Container 7", "plads_name": pl["name"]})
        ok({"address", "open_from", "open_orders", "is_closed"} <= set(dfl), "2 leveringsadresse/åbningstid for dagen fra kundens kalender")
        ok(status_of("POST", "/logistics/customer-orders", {"location_code": "1121", "material": mat, "container_number": "Container 7",
                                                            "custom_address": "Energivej 10, 3000 Helsingør", "order_date": d0}, t=la) == 400,
           "3 'Hvem bad om det?' er påkrævet")

        # --- Bestil for kunden -----------------------------------------------------
        r = behalf(driver_id=drv_id, trailer_count=1)
        o, t = order(r["order_id"]), tour(r["tour_id"])
        ok(o["company_id"] == hf and o["on_behalf_company_id"] == ilk and o["requested_by"] == "Jens, telefon"
           and o["assigned_logistics_company_ids"] == [ilk], "4 bestillingen er kundens, mærket 'bestilt af ILK for jer' + hvem der bad om det")
        ok(t["order_id"] == o["id"] and t["source"] == "customer_order" and t["company_id"] == hf and t["driver_id"] == drv_id
           and t["trailer_count"] == 1 and t["plads_address"].startswith(pl["address"]) and t["requested_by"] == "Jens, telefon",
           "5 turen hænger på bestillingen, er tildelt chaufføren, har pladsens adresse og hvem der bad om det")
        mine = call("GET", "/container-orders/by-location/1121", t=ou, params={"all": 1, "include_cancelled": "true"})
        ok(any(x["id"] == o["id"] and x.get("on_behalf_company_name") for x in mine), "6 kunden ser den under Mine bestillinger")
        e = status_of("POST", "/logistics/customer-orders", {"location_code": "1121", "plads_name": pl["name"], "material": mat,
                                                             "container_number": "Container 7", "order_date": d0,
                                                             "custom_address": "Energivej 10, 3000 Helsingør",
                                                             "requested_by": "Jens igen"}, t=la)
        ok(e == 409, "7 samme container to gange -> afvist (dobbeltbestilling)")
        st = status_of("POST", "/tours/bulk", [{"date": d0, "plads": pl["name"], "fraction": mat, "address": "Energivej 10",
                                               "facility": pl["name"]}], t=la)
        ok(st == 409, "8 fri 'Ny tur' på kundens plads afvises - det skal være en bestilling")
        hist = call("GET", f"/customer-orders/{o['id']}/history", t=ou)
        ok(any(h["action"] == "create_on_behalf" for h in hist), "9 Historik på bestillingen virker (før: intet endpoint) og viser 'bestilt for jer'")

        # --- Premium-firmaets egen logistik er uændret --------------------------------
        sid = "e2e-egen-" + new_id()
        own = call("POST", "/tours/bulk?force=true", [{"date": d0, "plads": "Hansen Depot Køge", "tour_kind": "goods", "tour_type": "levering",
                                                        "fraction": "Paller", "series_id": sid, "private_company": "E2E Egen Kunde",
                                                        "is_private": True, "stops": [
                                                            {"kind": "pickup", "street": "Vej 1", "postal": "4600", "city": "Køge"},
                                                            {"kind": "delivery", "street": "Vej 2", "postal": "4000", "city": "Roskilde"},
                                                            {"kind": "delivery", "street": "Vej 3", "postal": "3000", "city": "Helsingør"}]}], t=hans)
        c.tours.append(own[0]["id"])
        ot = tour(own[0]["id"])
        ok(ot["tour_kind"] == "goods" and len(ot["stops"]) == 3 and ot["series_id"] == sid and not ot.get("order_id"),
           "10 premium: egen tur med Fragt, stop og Gentag virker som før (ingen bestilling)")

        # --- Planlæggeren og bestillingen siger det samme ---------------------------
        d1 = next_weekday(5)
        call("PUT", f"/tours/{t['id']}", {"date": d1, "priority": "urgent"}, t=la)
        o2 = order(o["id"])
        ok(o2["order_date"] == d1 and o2["priority"] == "haster", "11 planlæggeren flytter dato/haster -> kundens bestilling følger med")
        ok(status_of("PUT", f"/tours/{t['id']}", {"fraction": "Noget andet"}, t=la) == 409,
           "12 materialet på en bestillings-tur rettes i bestillingen, ikke på turen")
        call("PUT", f"/logistics/customer-orders/{o['id']}", {"comment": "E2E rettet af planlæggeren"}, t=la)
        ok("E2E rettet af planlæggeren" in tour(t["id"])["remark"], "13 logistikfirmaet retter sin egen bestilling for kunden -> turen følger med")
        own_order = call("POST", "/customer-orders/submit", {"location_code": "1121", "material": mat, "container_number": "Container 8",
                                                             "priority": "normal", "tour_type": "flyt", "order_date": d0,
                                                             "partner_id": ilk, "comment": "E2E kundens egen"}, t=ou)
        c.tours.append(own_order["tour_id"]); c.orders.append(own_order["order_id"])
        ok(status_of("PUT", f"/logistics/customer-orders/{own_order['order_id']}", {"comment": "x"}, t=la) == 403,
           "14 kundens egen bestilling retter kunden - ikke logistikfirmaet")

        # --- Kunden annullerer før start: chaufføren ser det, kan ikke køre ----------
        call("POST", f"/customer-orders/{o['id']}/cancel", {}, t=ou)
        ok(order(o["id"])["status"] == "cancelled" and tour(t["id"])["cancelled"], "15 kunden annullerer -> bestilling og tur annulleret")
        dt = [x for x in call("GET", "/tours", t=drv, params={"date": d1}) if x["id"] == t["id"]]
        ok(dt and dt[0]["cancelled"] and dt[0]["cancelled_by_name"], "16 chaufføren (tildelt) ser turen som annulleret med hvem (før: almindelig tur)")
        ok(status_of("PUT", f"/tours/{t['id']}", {"on_way": True, "claimed_by_id": drv_id, "claimed_by": user_name(drv_email)}, t=drv) == 409,
           "17 en annulleret tur kan ikke startes")
        lt = [x for x in call("GET", "/tours", t=la, params={"date": d1}) if x["id"] == t["id"]]
        ok(lt and lt[0]["cancelled"], "18 planlæggeren ser den som annulleret")

        # --- Genoptag (kunden fortrød i telefonen) ----------------------------------
        ok(status_of("POST", f"/logistics/customer-orders/{o['id']}/restore", {}, t=la) == 400, "19 genoptag kræver en begrundelse")
        call("POST", f"/logistics/customer-orders/{o['id']}/restore", {"reason": "Jens fortrød"}, t=la)
        ok(order(o["id"])["status"] == "pending" and not tour(t["id"])["cancelled"], "20 genoptaget -> bestillingen er aktiv igen")

        # --- Annullering mens chaufføren er på vej -----------------------------------
        call("PUT", f"/tours/{t['id']}", {"on_way": True, "on_way_time": "08:00", "claimed_by": user_name(drv_email),
                                          "claimed_by_id": drv_id}, t=drv)
        ok(status_of("POST", f"/logistics/customer-orders/{o['id']}/cancel", {"reason": "Jens ringede"}, t=la) == 409,
           "21 logistikfirmaet annullerer ikke en tur der er i gang (chaufføren melder den)")
        try:
            call("POST", f"/customer-orders/{o['id']}/cancel", {}, t=ou)
            ok(False, "22 annullering på vej kræver bekræftelse")
        except ApiError as ex:
            ok(ex.status == 409 and isinstance(ex.body.get("detail"), dict) and ex.body["detail"].get("code") == "on_way",
               "22 på vej: kunden skal bekræfte (det kan koste en forgæves kørsel)")
        call("POST", f"/customer-orders/{o['id']}/cancel", {"confirm_on_way": True, "reason": "Containeren er tømt"}, t=ou)
        t3 = tour(t["id"])
        ok(t3["cancelled"] and t3["cancelled_on_way"] and t3["not_completed"] and t3["not_completed_code"] == "Annulleret af kunden",
           "23 annulleret på vej -> forgæves kørsel med koden 'Annulleret af kunden'")
        ok(status_of("POST", f"/tours/{t['id']}/finish", {"op_id": new_id()}, t=drv) == 409,
           "24 chaufføren kan ikke afslutte den (fx fra offline-køen)")
        rep = call("GET", "/pricing/report", t=la, params={"date_from": today(), "date_to": in_days(14)})
        ok(any(row["tour_id"] == t["id"] for row in rep.get("rows") or []), "25 forgæves kørslen står i Økonomi til vurdering")
        ok(order(o["id"])["status"] == "cancelled", "26 bestillingen forbliver annulleret (spejlingen overskriver den ikke)")

        # --- Kørt alligevel: genoptag, så chaufføren kan afslutte ---------------------
        call("POST", f"/logistics/customer-orders/{o['id']}/restore", {"reason": "Turen var allerede kørt"}, t=la)
        t4 = tour(t["id"])
        ok(not t4["cancelled"] and not t4["not_completed"] and t4["on_way"] and order(o["id"])["status"] == "in_progress",
           "27 genoptaget mens han er på vej -> chaufføren beholder turen")
        call("POST", f"/tours/{t['id']}/finish", {"op_id": new_id(), "weight": 1200}, t=drv)
        ok(order(o["id"])["status"] == "completed", "28 ...og kan afslutte den - bestillingen er afhentet")
        ok(status_of("POST", f"/customer-orders/{o['id']}/cancel", {"confirm_on_way": True}, t=ou) == 409,
           "29 en afhentet bestilling kan ikke annulleres")

        # --- Logistikfirmaet annullerer på kundens anmodning ------------------------
        r5 = behalf(container_number="Container 9")
        ok(status_of("POST", f"/logistics/customer-orders/{r5['order_id']}/cancel", {}, t=la) == 400, "30 annullering kræver en begrundelse")
        call("POST", f"/logistics/customer-orders/{r5['order_id']}/cancel", {"reason": "Jens ringede - ikke fuld"}, t=la)
        o5 = order(r5["order_id"])
        ok(o5["status"] == "cancelled" and o5["cancelled_by_logistics"] and o5["cancel_reason"].startswith("Jens"),
           "31 annulleret af logistikfirmaet med begrundelse, som kunden ser")

        # --- Containerlisten: pladsens containere for netop dette firma ----------------
        city = db.companies.find_one({"name": "City Container"}, {"_id": 0, "id": 1})["id"]
        cmat = "E2E Containermateriale"
        db.plads.update_one({"location_code": "1121"}, {"$addToSet": {f"partner_materials.{ilk}": cmat, f"partner_materials.{city}": cmat}})
        db.container_counts.insert_many([{"location_code": "1121", "material": cmat, "partner_id": ilk, "count": 2},
                                         {"location_code": "1121", "material": cmat, "partner_id": city, "count": 1}])
        db.container_overrides.insert_one({"location_code": "1121", "material": cmat, "container_label": "Container 1", "partner_id": "",
                                           "custom_container_id": "E2E-12345", "locked_container_id": True})
        try:
            op = call("GET", "/logistics/order-options", t=la, params={"location_code": "1121", "plads_name": pl["name"]})
            cl = next((m["containers"] for m in op["materials"] if m["material"] == cmat), [])
            ok([c["label"] for c in cl] == ["Container 1", "Container 2"] and cl[0]["container_id"] == "E2E-12345"
               and cl[0]["locked_container_id"] and cl[1]["container_id"] == "",
               "33 containerlisten = pladsens containere for ILK (2, også den uden nummer) - ikke City Containers")
            ov = behalf(material=cmat, container_number="Container 2", custom_container_id="E2E-7777", custom_address="Energivej 10, 3000 Helsingør")
            ok(tour(ov["tour_id"])["container"] == "E2E-7777" and order(ov["order_id"])["container_id_override"] == "E2E-7777",
               "34 'Overskriv' på en container uden låst nummer: chaufføren ser det indtastede nummer")
            lk = behalf(material=cmat, container_number="Container 1", custom_container_id="E2E-8888", custom_address="Energivej 10, 3000 Helsingør")
            ok(tour(lk["tour_id"])["container"] == "E2E-12345", "35 kundens låste containernummer kan ikke overskrives på den container")
            mn = behalf(material=cmat, container_number="E2E-9999", custom_container_id="E2E-9999", custom_address="Energivej 10, 3000 Helsingør")
            ok(tour(mn["tour_id"])["container"] == "E2E-9999", "36 et manuelt nummer uden for listen bestilles som en anden container")
        finally:
            db.container_counts.delete_many({"location_code": "1121", "material": cmat})
            db.container_overrides.delete_many({"location_code": "1121", "material": cmat})
            db.plads.update_one({"location_code": "1121"}, {"$pull": {f"partner_materials.{ilk}": cmat, f"partner_materials.{city}": cmat}})

        # --- Excel på kundens plads bliver bestillinger -----------------------------
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Lokation", "Materiale", "Container-nummer", "Containertype", "Leveringsadresse", "Åbningstid", "Lukketid", "Note", "Dato"])
        ws.append([pl["name"], mat, "Container 11", "", "Energivej 10, 3000 Helsingør", "", "", "E2E excel", d0])
        ws.append(["ℹ️ Sådan udfylder du skabelonen"])
        buf = BytesIO()
        wb.save(buf)
        rx = _session.post(f"{BASE}/tours/upload-template", headers={"Authorization": f"Bearer {la}"},
                           files={"file": ("e2e.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                           timeout=30).json()
        xo = db.container_orders.find_one({"location_code": "1121", "container_number": "Container 11", "comment": "E2E excel"}, {"_id": 0})
        if xo:
            c.orders.append(xo["id"]); c.tours.append(xo.get("tour_id"))
        ok(rx.get("created") == 1 and not rx.get("errors") and xo and xo["requested_by"].startswith("Excel-import")
           and xo["order_date"] == d0, f"32 Excel-række på kundens plads -> bestilling for kunden med datoen; vejledningen er ikke en fejl ({rx.get('message')})")
    finally:
        call("POST", "/driver/active-customer", {"customer_id": hf}, t=drv)
        c.run()


if __name__ == "__main__":
    run()
