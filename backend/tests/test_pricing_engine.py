"""Unit tests for backend/pricing.py (no server or database needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pricing as P  # noqa: E402


def attrs(**kw):
    base = {"customer_id": "c1", "location_code": "1101", "material": "Træ",
            "task_type": "normal", "priority": "normal", "day_type": "weekday",
            "trailer": False, "container_label": "", "delivery_label": "HCS A/S",
            "start_min": 8 * 60, "outcome": "completed", "service_date": "2026-10-14",
            "containers": 1, "waiting_min": 0, "deduct_pause_override": None}
    base.update(kw)
    return base


def base_rule(rid, model="fixed", conditions=None, **pricing):
    return {"id": rid, "name": rid, "kind": "base", "active": True,
            "conditions": conditions or {}, "pricing": {"model": model, **pricing},
            "updated_at": "2026-01-01"}


def surcharge(rid, category, unit, value, conditions=None, updated="2026-01-01"):
    return {"id": rid, "name": rid, "kind": "surcharge", "category": category, "active": True,
            "conditions": conditions or {}, "surcharge": {"unit": unit, "value": value},
            "updated_at": updated}


def test_easter_and_holidays():
    assert P.easter_sunday(2026).isoformat() == "2026-04-05"
    assert P.easter_sunday(2027).isoformat() == "2027-03-28"
    h = P.danish_holidays(2026, ["grundlovsdag"])
    assert h["2026-05-14"] == "Kristi himmelfartsdag"
    assert h["2026-06-05"] == "Grundlovsdag"
    assert "2026-12-24" not in h  # optional day not chosen


def test_own_holidays_extra_and_excluded():
    s = {"holiday_optional": [], "holiday_extra": [{"date": "2026-08-01", "name": "Firmafest"}],
         "holiday_excluded": ["2026-04-02"]}
    h = P.own_holidays(2026, s)
    assert "2026-04-02" not in h and h["2026-08-01"] == "Firmafest"


def test_day_type_holiday_beats_weekend():
    assert P.day_type("2026-12-26", {"2026-12-26"}) == "holiday"   # Saturday + holiday
    assert P.day_type("2026-10-17", set()) == "saturday"
    assert P.day_type("2026-10-18", set()) == "sunday"
    assert P.day_type("2026-10-16", set()) == "weekday"


def test_rounding():
    assert P.round_minutes(31, "up", 15) == 45
    assert P.round_minutes(37, "nearest", 15) == 30
    assert P.round_minutes(38, "nearest", 15) == 45
    assert P.round_minutes(44, "down", 15) == 30
    assert P.round_minutes(31.4, "none", 0) == 31


def test_most_specific_base_rule_wins():
    rules = [base_rule("general", amount=1000),
             base_rule("customer", amount=900, conditions={"customer_ids": ["c1"]}),
             base_rule("customer+location", amount=800,
                       conditions={"customer_ids": ["c1"], "location_codes": ["1101"]})]
    r = P.price_tour(attrs(), rules, None)
    assert r["total"] == 800 and r["base_rule"]["id"] == "customer+location"
    r2 = P.price_tour(attrs(location_code="9999"), rules, None)
    assert r2["total"] == 900


def test_surcharge_one_per_category_and_exemption():
    rules = [base_rule("b", amount=1000),
             surcharge("weekend-all", "weekend", "kr", 500, {"day_types": ["saturday", "sunday"]}),
             surcharge("weekend-c1", "weekend", "kr", 0,
                       {"customer_ids": ["c1"], "day_types": ["saturday", "sunday"]}),
             surcharge("haster", "haster", "percent", 20, {"priorities": ["haster"]})]
    sat = P.price_tour(attrs(day_type="saturday", priority="haster"), rules, None)
    # c1 is exempt from the weekend surcharge (0 kr), haster +20% of base
    assert sat["total"] == 1000 + 0 + 200
    other = P.price_tour(attrs(day_type="saturday", customer_id="c2"), rules, None)
    assert other["total"] == 1500


def test_delivery_label_matching_is_case_and_space_insensitive():
    rules = [base_rule("b", amount=100),
             base_rule("hcs", amount=150, conditions={"delivery_labels": ["hcs  a/s"]})]
    assert P.price_tour(attrs(delivery_label="HCS A/S"), rules, None)["total"] == 150


def test_hourly_with_pause_rounding_minimum_and_start_fee():
    rule = base_rule("time", model="hourly", hourly_rate=600, start_fee=250,
                     min_minutes=60, rounding_mode="up", rounding_minutes=15, deduct_pause=True)
    # 70 min tour, 10 min pause inside -> 60 billable -> exactly 1 hour
    r = P.price_tour(attrs(), [rule], {"gross": 70, "total": 70, "pause": 10})
    assert r["time"]["billable_min"] == 60
    assert r["total"] == 250 + 600
    # pause counted -> 70 -> rounded up to 75 min
    r2 = P.price_tour(attrs(deduct_pause_override=False), [rule], {"gross": 70, "total": 70, "pause": 10})
    assert r2["time"]["billable_min"] == 75 and r2["total"] == 250 + 750
    # short tour -> minimum 60 min
    r3 = P.price_tour(attrs(), [rule], {"gross": 20, "total": 20, "pause": 0})
    assert r3["time"]["billable_min"] == 60


def test_hourly_missing_time():
    rule = base_rule("time", model="hourly", hourly_rate=600)
    r = P.price_tour(attrs(), [rule], None)
    assert r["status"] == "missing_time" and r["total"] is None


def test_per_container_and_per_hour_surcharge():
    rules = [base_rule("loes", model="per_container", amount=400, conditions={"task_types": ["loes_afhentning"]}),
             surcharge("trailer", "trailer", "per_hour", 120, {"trailer": "with"})]
    r = P.price_tour(attrs(task_type="loes_afhentning", containers=3, trailer=True), rules,
                     {"gross": 90, "total": 90, "pause": 0})
    assert r["total"] == 1200 + 180


def test_waiting_time_surcharge_rounds_up_to_quarter():
    rules = [base_rule("b", amount=1000), surcharge("vent", "waiting", "per_hour", 400)]
    assert P.price_tour(attrs(waiting_min=0), rules, None)["total"] == 1000
    assert P.price_tour(attrs(waiting_min=20), rules, None)["total"] == 1000 + 200  # 30 min


def test_time_window_crossing_midnight():
    rules = [base_rule("b", amount=1000),
             surcharge("aften", "evening", "kr", 300, {"time_from": "18:00", "time_to": "06:00"})]
    assert P.price_tour(attrs(start_min=19 * 60), rules, None)["total"] == 1300
    assert P.price_tour(attrs(start_min=5 * 60), rules, None)["total"] == 1300
    assert P.price_tour(attrs(start_min=12 * 60), rules, None)["total"] == 1000


def test_outcome_not_completed_needs_its_own_rule():
    rules = [base_rule("b", amount=1000),
             base_rule("forgaeves", amount=450, conditions={"outcome": "not_completed"})]
    assert P.price_tour(attrs(outcome="not_completed"), rules, None)["total"] == 450
    assert P.price_tour(attrs(outcome="not_completed"), rules[:1], None)["status"] == "missing_rule"


def test_validity_dates():
    rules = [base_rule("old", amount=900), base_rule("new", amount=1000)]
    rules[0]["valid_to"] = "2026-12-31"
    rules[1]["valid_from"] = "2027-01-01"
    assert P.price_tour(attrs(service_date="2026-06-01"), rules, None)["total"] == 900
    assert P.price_tour(attrs(service_date="2027-02-01"), rules, None)["total"] == 1000


def test_concurrent_tours_split_and_pause():
    # Tour A 08:00-10:00, tour B 09:00-11:00, pause 09:30-09:40
    res = P.split_driver_day({"A": (480, 600), "B": (540, 660)}, [(570, 580)], "split")
    assert round(res["A"]["total"]) == 90 and round(res["B"]["total"]) == 90  # 60 overlap shared
    assert res["A"]["pause"] == 5 and res["B"]["pause"] == 5
    full = P.split_driver_day({"A": (480, 600), "B": (540, 660)}, [], "full")
    assert full["A"]["total"] == 120


def test_manual_override_and_extra_lines():
    rules = [base_rule("b", amount=1000)]
    r = P.price_tour(attrs(), rules, None, {"mode": "fixed", "amount": 750,
                                            "extra_lines": [{"label": "Rengøring", "amount": 300}]})
    assert r["total"] == 1050
    r2 = P.price_tour(attrs(), [], None, {"mode": "fixed", "amount": 500})
    assert r2["total"] == 500 and r2["status"] == "ok"
