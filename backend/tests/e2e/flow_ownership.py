"""P0 (2026-10-18): Ejerskab af en tur følger lokationen.
En tur på en genbrugsplads-kundes plads er kundens tur (priser, arkiv,
koordinator-scope) - også når logistikfirmaet opretter den via "Ny tur" eller
Kopiér. En tur på firmaets egen lokation er firmaets egen tur."""
import subprocess
import sys
import time

from _e2e import *  # noqa: F401,F403

ILK_COORD = "ferdalturan+ilk.koordinator@gmail.com"
HF_ADMIN = "ferdalturan+hf.admin@gmail.com"


def run():
    c = Cleanup()
    la = login(ILK_ADMIN)
    ilk = db.users.find_one({"email": ILK_ADMIN}, {"_id": 0, "company_id": 1})["company_id"]
    hf = db.plads.find_one({"name": "Cirklen"}, {"_id": 0, "company_id": 1})["company_id"]
    disable_company_rules(c, ILK_ADMIN)
    coord = db.users.find_one({"email": ILK_COORD}, {"_id": 0, "id": 1, "customer_scope": 1})
    c.restore.append(("users", {"id": coord["id"]}, {"customer_scope": coord.get("customer_scope") or []}))
    try:
        day = today()
        base = {"date": day, "plads": "Cirklen", "fraction": "Pap til HCS", "tour_type": "normal",
                "address": "E2E Ejer Vej 1, 3000 Helsingør", "remark": "E2E ejerskab"}
        tid = call("POST", "/tours/bulk", [base], t=la)[0]["id"]
        c.tours.append(tid)
        t = db.tours.find_one({"id": tid}, {"_id": 0})
        ok(t["company_id"] == hf and t.get("customer_name") == "Helsingør Forsyning" and ilk in (t.get("assigned_logistics_company_ids") or []),
           "1 'Ny tur' på Cirklen ejes af Helsingør Forsyning (ILK står som tildelt)")
        ok(not t.get("customer_ref_id") and not t.get("private_company"), "2 ingen registerkunde/fritekst-kunde på kundens plads")
        row = next((x for x in call("GET", "/tours", t=la, params={"date": day, "limit": 500}) if x["id"] == tid), None)
        ok(row is not None and row.get("customer_name") == "Helsingør Forsyning", "3 ILK ser turen under Cirklen med kunden Helsingør Forsyning")

        b = call("POST", "/pricing/bundles", {"name": "E2E HF kundepris", "conditions": {"customer_ids": [hf]},
                                              "base": {"pricing": {"model": "fixed", "amount": "777"}}, "surcharges": [],
                                              "effective": "all"}, t=la)
        c.bundles.append(b["bundle_id"])
        p = price_of(la, tid)
        ok(p["customer_id"] == hf and p["price"].get("total") == 777, f"4 kundens grundpris vinder på turen ({p['price'].get('total')})")
        ok(call("GET", "/pricing/status", t=la, params={"ids": tid}).get(tid, {}).get("status") == "ok", "5 prisstatus OK på Ture-siden")

        # Koordinator begrænset til kunden ser turen - begrænset til "egne" gør ikke
        db.users.update_one({"id": coord["id"]}, {"$set": {"customer_scope": [hf]}})
        time.sleep(16)  # rettighedscache (15 s)
        ct = login(ILK_COORD)
        ok(any(x["id"] == tid for x in call("GET", "/tours", t=ct, params={"date": day, "limit": 500})),
           "6 koordinator med scope = Helsingør Forsyning ser turen")
        db.users.update_one({"id": coord["id"]}, {"$set": {"customer_scope": ["own"]}})
        time.sleep(16)
        ok(not any(x["id"] == tid for x in call("GET", "/tours", t=ct, params={"date": day, "limit": 500})),
           "7 koordinator med scope = egne ture ser den ikke")

        arch = call("GET", "/org/tour-archive", t=login(HF_ADMIN), params={"date_from": day, "date_to": day})
        ok(any(x.get("id") == tid for x in arch.get("tours") or []), "8 Helsingørs kunde-admin ser turen i sit arkiv")

        # Kontrol: egen lokation + registerkunde forbliver firmaets egen tur
        life = (db.logistics_customers.find_one({"company_id": ilk, "name": "Life"}, {"_id": 0, "id": 1}) or {}).get("id", "")
        own = call("POST", "/tours/bulk", [{**base, "plads": "Arla Ishøj", "private_company": "Life", "is_private": True,
                                             "customer_ref_id": life}], t=la)[0]["id"]
        c.tours.append(own)
        ot = db.tours.find_one({"id": own}, {"_id": 0})
        ok(ot["company_id"] == ilk and price_of(la, own)["customer_id"] == "firma:life", "9 Arla Ishøj + Life er stadig ILK's egen tur (firma:life)")

        # Kopiér en Helsingør-bestilling til i morgen (som Ture-siden gør, uden kundenavn)
        o = call("POST", "/customer-orders/submit", {
            "location_code": "1102", "material": "Pap til HCS", "container_number": "Container 1", "priority": "normal",
            "comment": "E2E ejer kopi", "order_date": day, "tour_type": "normal", "custom_address": "Energivej 6, 3000 Helsingør",
            "delivery_address_id": (db.delivery_addresses.find_one({"location_code": "1102"}, {"_id": 0, "id": 1}) or {}).get("id", ""),
        }, t=login("ferdalturan+hf.1102.medarbejder1@gmail.com"))
        c.tours.append(o["tour_id"]); c.orders.append(o["order_id"])
        src = db.tours.find_one({"id": o["tour_id"]}, {"_id": 0})
        copy = {k: src.get(k) for k in ("plads", "fraction", "facility", "address", "tour_type", "container", "capacity_label",
                                        "open_from", "open_to", "priority", "remark")}
        cp = call("POST", "/tours/bulk", [{**copy, "date": in_days(1)}], t=la)[0]["id"]
        c.tours.append(cp)
        ct2 = db.tours.find_one({"id": cp}, {"_id": 0})
        ok(ct2["company_id"] == hf and ct2.get("customer_name") == "Helsingør Forsyning" and not ct2.get("order_id"),
           "10 kopi af en Helsingør-bestilling er Helsingørs tur")

        # Migrering: en gammel tur gemt med ILK's id på Cirklen bliver kundens
        old = new_id()
        db.tours.insert_one({"id": old, "date": day, "plads": "Cirklen", "company_id": ilk, "fraction": "E2E gammel",
                             "address": "E2E Ejer Vej 2", "private_company": "Helsingør Forsyning", "is_private": True,
                             "assigned_logistics_company_ids": [], "completed": False})
        locked = new_id()
        db.tours.insert_one({"id": locked, "date": day, "plads": "Cirklen", "company_id": ilk, "fraction": "E2E faktureret",
                             "address": "E2E Ejer Vej 3", "price_locked": {"total": 1}, "completed": True})
        c.tours += [old, locked]
        print("  (kører migreringen i en separat proces)")
        out = subprocess.run([sys.executable, "-c", (
            "import asyncio, sys; sys.path.insert(0, '/app/backend'); import server;"
            "asyncio.run(server._migrate_tour_owner_from_plads())")], capture_output=True, text=True, cwd="/app/backend", timeout=120)
        mo = db.tours.find_one({"id": old}, {"_id": 0})
        ml = db.tours.find_one({"id": locked}, {"_id": 0})
        ok(mo["company_id"] == hf and ilk in mo.get("assigned_logistics_company_ids", []) and not mo.get("private_company"),
           f"11 migrering: gammel tur på Cirklen bliver Helsingørs (ILK beholdt som tildelt){'' if out.returncode == 0 else ' - ' + out.stderr[-200:]}")
        ok(ml["company_id"] == ilk, "12 migrering rører ikke en faktureret tur")
    finally:
        c.run()


if __name__ == "__main__":
    run()
