"""Planlæg: tildeling og omfordeling (2026-10-18).
En tur der ikke er startet kan gives til en anden chauffør (også når den er
taget). En startet/afsluttet tur bliver hos chaufføren der kører den - før
kunne masse-tildeling give den til en anden ("tildelt X, kørt af Y")."""
import subprocess
import sys

from _e2e import *  # noqa: F401,F403


def run():
    c = Cleanup()
    la = login(ILK_ADMIN)
    d1_email = free_driver(ILK_DRIVERS)
    d2_email = next(e for e in ILK_DRIVERS if e != d1_email)
    d1, d2 = user_id(d1_email), user_id(d2_email)
    n1, n2 = user_name(d1_email), user_name(d2_email)
    drv1 = login(d1_email)
    try:
        day = today()
        base = {"date": day, "plads": "Arla Ishøj", "fraction": "E2E Planlæg", "tour_type": "normal", "remark": "E2E planlæg"}
        a, b, cc = (x["id"] for x in call("POST", "/tours/bulk", [
            {**base, "address": "E2E Planvej 1, 2635 Ishøj"},
            {**base, "address": "E2E Planvej 2, 2635 Ishøj"},
            {**base, "address": "E2E Planvej 3, 2635 Ishøj"}], t=la))
        c.tours += [a, b, cc]

        r = call("POST", "/tours/bulk-assign", {"tour_ids": [a, b, cc], "driver_id": d1}, t=la)
        ok(r["updated"] == 3 and r["skipped"] == 0, f"1 tre ikke-tildelte ture gives til {n1}")
        call("PUT", f"/tours/{a}", {"on_way": True, "on_way_time": "08:00", "claimed_by": n1, "claimed_by_id": d1}, t=drv1)
        db.tours.update_one({"id": cc}, {"$set": {"claimed_by": n1, "claimed_by_id": d1}})  # taget, ikke startet

        r = call("POST", "/tours/bulk-assign", {"tour_ids": [a, b, cc], "driver_id": d2}, t=la)
        ta, tb, tc = (db.tours.find_one({"id": x}, {"_id": 0}) for x in (a, b, cc))
        ok(r["updated"] == 2 and r["skipped"] == 1, f"2 flyt til {n2}: 2 flyttet, den startede springes over ({r})")
        ok(ta["driver_id"] == d1 and ta["claimed_by_id"] == d1, "3 den startede tur bliver hos chaufføren der kører den")
        ok(tb["driver_id"] == d2, f"4 tildelt (ikke startet) tur flyttes til {n2}")
        ok(tc["driver_id"] == d2 and not tc.get("claimed_by_id"), "5 taget (ikke startet) tur flyttes, og den gamle 'taget' ryddes")

        call("PUT", f"/tours/{a}", {"completed": True, "time": "09:00", "claimed_by": n1, "claimed_by_id": d1}, t=drv1)
        r = call("POST", "/tours/bulk-assign", {"tour_ids": [a], "driver_id": d2}, t=la)
        ok(r["updated"] == 0 and r["skipped"] == 1 and db.tours.find_one({"id": a})["driver_id"] == d1,
           "6 en afsluttet tur kan ikke gives til en anden")

        # Migrering: gammel tur i gang, tildelt en anden end den der kører
        old = new_id()
        db.tours.insert_one({"id": old, "date": day, "plads": "Arla Ishøj", "company_id": db.users.find_one({"id": d1})["company_id"],
                             "fraction": "E2E gammel", "address": "E2E Planvej 4", "on_way": True, "completed": False,
                             "driver_id": d2, "driver_name": n2, "claimed_by_id": d1, "claimed_by": n1})
        c.tours.append(old)
        out = subprocess.run([sys.executable, "-c", (
            "import asyncio, sys; sys.path.insert(0, '/app/backend'); import server;"
            "asyncio.run(server._migrate_driver_matches_claimer())")], capture_output=True, text=True, cwd="/app/backend", timeout=120)
        mo = db.tours.find_one({"id": old}, {"_id": 0})
        ok(mo["driver_id"] == d1 and mo["driver_name"] == n1,
           f"7 migrering: tur i gang står nu på chaufføren der kører den{'' if out.returncode == 0 else ' - ' + out.stderr[-200:]}")
    finally:
        c.run()


if __name__ == "__main__":
    run()
