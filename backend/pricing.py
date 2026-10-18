"""ContainerFlow price engine (pure functions, no database).

See PRICING_SPEC.md for the business rules. server.py loads tours, rules,
calendars and time entries, builds the per-tour attributes and calls
`price_tour`. Everything here is deterministic so it can be unit tested.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

TASK_TYPES = {
    "normal": "Afhentning",
    "flyt": "Byt container",
    "vaerksted": "Til værksted",
    "afhent_vaerksted": "Hent fra værksted",
    "loes_afhentning": "Løs afhentning (egne containere)",
    # 2026-10-17: Gods/andet (premium-firmaers egne ture, ikke containere)
    "afhentning": "Afhentning (gods)",
    "levering": "Levering",
    "afhent_lever": "Afhentning + levering",
    "flytning": "Flytning",
    "andet": "Andet",
}
PRIORITIES = {"haster": "Haster", "normal": "Normal", "lav": "Lav"}
DAY_TYPES = {"weekday": "Hverdag", "saturday": "Lørdag", "sunday": "Søndag", "holiday": "Helligdag"}
SURCHARGE_CATEGORIES = {
    "weekend": "Weekend",
    "holiday": "Helligdag",
    "haster": "Haster",
    "trailer": "Hænger",
    "evening": "Aften/nat",
    "waiting": "Ventetid",
    # 2026-10-18: pr. stop ud over de inkluderede (standard 2 = én afhentning
    # + én aflevering). Stop der ikke kunne gennemføres tæller med - chaufføren
    # kørte derhen.
    "stop": "Ekstra stop",
    "other": "Andet",
}
BASE_MODELS = {"fixed": "Fast pris", "hourly": "Timepris", "per_container": "Pris pr. container",
               # 2026-10-18: pr. palle/kolli/m³/ton ... ud fra linjernes antal
               # (registreret, ellers planlagt), med valgfrit minimumsbeløb.
               "per_unit": "Pris pr. enhed"}

# Specificity weights: a rule naming a customer beats one naming a location,
# which beats a delivery address, and so on. Sums never collide upwards
# (64 > 32+16+8+4+2+1*5).
_WEIGHTS = {
    "customer_ids": 64, "location_codes": 32, "delivery_labels": 16,
    "task_types": 8, "materials": 4, "container_labels": 2,
    "priorities": 1, "day_types": 1,
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def hhmm_to_min(t: str) -> int:
    try:
        h, m = [int(x) for x in (t or "").split(":")[:2]]
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    return -1


def norm_label(s: str) -> str:
    return " ".join((s or "").lower().split())


def money(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def round_minutes(minutes: float, mode: str, step: int) -> int:
    """mode: none | up | nearest | down; step in minutes."""
    if minutes <= 0:
        return 0
    if mode in ("", None, "none") or not step or step <= 1:
        return int(math.ceil(minutes - 1e-9)) if mode == "up" else int(round(minutes))
    q = minutes / step
    if mode == "up":
        return int(math.ceil(q - 1e-9) * step)
    if mode == "down":
        return int(math.floor(q + 1e-9) * step)
    return int(math.floor(q + 0.5) * step)  # nearest, halves round up


# ---------------------------------------------------------------------------
# Danish holidays (computed for any year)
# ---------------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


OPTIONAL_HOLIDAYS = {
    "grundlovsdag": "Grundlovsdag",
    "juleaften": "Juleaften",
    "nytaarsaften": "Nytårsaftensdag",
    "1maj": "1. maj",
}
DEFAULT_OPTIONAL = ["grundlovsdag", "juleaften", "nytaarsaften"]


def danish_holidays(year: int, optional: Iterable[str] = ()) -> Dict[str, str]:
    """Official Danish public holidays (+ selected optional days) as
    {YYYY-MM-DD: name}. Store bededag is not included (abolished from 2024)."""
    es = easter_sunday(year)
    days = {
        date(year, 1, 1): "Nytårsdag",
        es - timedelta(days=3): "Skærtorsdag",
        es - timedelta(days=2): "Langfredag",
        es: "Påskedag",
        es + timedelta(days=1): "2. påskedag",
        es + timedelta(days=39): "Kristi himmelfartsdag",
        es + timedelta(days=49): "Pinsedag",
        es + timedelta(days=50): "2. pinsedag",
        date(year, 12, 25): "1. juledag",
        date(year, 12, 26): "2. juledag",
    }
    opt = set(optional or ())
    if "grundlovsdag" in opt:
        days[date(year, 6, 5)] = "Grundlovsdag"
    if "juleaften" in opt:
        days[date(year, 12, 24)] = "Juleaften"
    if "nytaarsaften" in opt:
        days[date(year, 12, 31)] = "Nytårsaftensdag"
    if "1maj" in opt:
        days[date(year, 5, 1)] = "1. maj"
    return {d.isoformat(): n for d, n in sorted(days.items())}


def own_holidays(year: int, settings: dict) -> Dict[str, str]:
    """The logistics company's own calendar: Danish defaults + optional days
    + extra days − excluded dates."""
    days = danish_holidays(year, settings.get("holiday_optional", DEFAULT_OPTIONAL))
    for d in settings.get("holiday_excluded") or []:
        days.pop(d, None)
    for x in settings.get("holiday_extra") or []:
        if (x.get("date") or "").startswith(str(year)):
            days[x["date"]] = x.get("name") or "Ekstra fridag"
    return dict(sorted(days.items()))


def day_type(service_date: str, holidays: Set[str]) -> str:
    if service_date in holidays:
        return "holiday"
    try:
        wd = date.fromisoformat(service_date).weekday()
    except ValueError:
        return "weekday"
    return "saturday" if wd == 5 else "sunday" if wd == 6 else "weekday"


# ---------------------------------------------------------------------------
# Time: concurrent tours + pauses
# ---------------------------------------------------------------------------

def split_driver_day(intervals: Dict[str, Tuple[int, int]],
                     pauses: List[Tuple[int, int]],
                     mode: str = "split") -> Dict[str, Dict[str, float]]:
    """For one driver on one day.

    intervals: tour_id -> (start_min, end_min) with end > start (callers add
               1440 for tours crossing midnight).
    pauses:    pause periods (start_min, end_min) from the "Tid" section.
    mode:      "split" shares overlapping minutes equally between tours that
               run at the same time; "full" gives each tour the full minutes.

    Returns tour_id -> {"total": minutes attributed, "pause": of which in pause}.
    """
    out = {tid: {"total": 0.0, "pause": 0.0} for tid in intervals}
    points = sorted({p for s, e in intervals.values() for p in (s, e)} |
                    {p for s, e in pauses for p in (s, e)})
    for a, b in zip(points, points[1:]):
        if b <= a:
            continue
        active = [tid for tid, (s, e) in intervals.items() if s <= a and e >= b]
        if not active:
            continue
        length = b - a
        share = length / len(active) if mode == "split" else length
        in_pause = any(ps <= a and pe >= b for ps, pe in pauses)
        for tid in active:
            out[tid]["total"] += share
            if in_pause:
                out[tid]["pause"] += share
    return out


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _in_window(start_min: int, frm: str, to: str) -> bool:
    f, t = hhmm_to_min(frm), hhmm_to_min(to)
    if f < 0 or t < 0 or start_min < 0:
        return False
    return f <= start_min < t if f <= t else (start_min >= f or start_min < t)


def tour_materials(attrs: dict) -> List[str]:
    """2026-10-18: Turens materialer som liste (én pr. indholdslinje). Ældre
    attrs har kun `material` (én streng)."""
    mats = [m for m in (attrs.get("materials") or []) if (m or "").strip()]
    if mats:
        return mats
    m = (attrs.get("material") or "").strip()
    return [m] if m else []


CONDITION_LABELS = {
    "active": "reglen er slået fra", "valid": "kørselsdatoen er uden for reglens periode",
    "outcome": "udfald (gennemført/forgæves)", "customer_ids": "kunde", "location_codes": "lokation",
    "materials": "materiale", "task_types": "opgavetype", "priorities": "prioritet",
    "day_types": "dagtype", "container_labels": "containerstørrelse", "delivery_labels": "leveringsadresse",
    "trailer_counts": "antal hængere", "trailer": "hænger", "time": "tidsrum",
}


def failing_conditions(rule: dict, attrs: dict) -> List[str]:
    """Hvilke betingelser i reglen turen IKKE opfylder (tom liste = match)."""
    c = rule.get("conditions") or {}
    out: List[str] = []
    if not rule.get("active", True):
        out.append("active")
    sd = attrs.get("service_date") or ""
    if (rule.get("valid_from") and sd and sd < rule["valid_from"]) or (rule.get("valid_to") and sd and sd > rule["valid_to"]):
        out.append("valid")
    outcome = c.get("outcome") or "completed"
    if outcome != "any" and outcome != attrs.get("outcome"):
        out.append("outcome")
    checks = {
        "customer_ids": attrs.get("customer_id"),
        "location_codes": attrs.get("location_code"),
        "task_types": attrs.get("task_type"),
        "priorities": attrs.get("priority"),
        "day_types": attrs.get("day_type"),
        "container_labels": norm_label(attrs.get("container_label") or ""),
        "delivery_labels": norm_label(attrs.get("delivery_label") or ""),
    }
    for key, value in checks.items():
        wanted = c.get(key) or []
        if not wanted:
            continue
        if key in ("container_labels", "delivery_labels"):
            if value not in {norm_label(w) for w in wanted}:
                out.append(key)
        elif value not in wanted:
            out.append(key)
    # 2026-10-18: Materiale som liste. Grundpris: ALLE turens materialer skal
    # være i reglen (en betonpris gælder kun rene betonture). Tillæg: ét er nok.
    wanted_m = {norm_label(w) for w in (c.get("materials") or []) if str(w).strip()}
    if wanted_m:
        mats = {norm_label(m) for m in tour_materials(attrs)}
        ok = bool(mats) and (mats <= wanted_m if rule.get("kind") == "base" else bool(mats & wanted_m))
        if not ok:
            out.append("materials")
    # 2026-10-17: Antal hængere (fx 1 hænger = 700, 2 hængere = 1100).
    counts = [int(x) for x in (c.get("trailer_counts") or []) if str(x).isdigit()]
    if counts:
        n = int(attrs.get("trailer_count") or 0)
        if not any(n == k or (k >= 3 and n >= 3) for k in counts):
            out.append("trailer_counts")
    trailer = c.get("trailer") or ""
    if (trailer == "with" and not attrs.get("trailer")) or (trailer == "without" and attrs.get("trailer")):
        out.append("trailer")
    if c.get("time_from") and c.get("time_to"):
        if not _in_window(attrs.get("start_min", -1), c["time_from"], c["time_to"]):
            out.append("time")
    return out


def rule_matches(rule: dict, attrs: dict) -> bool:
    return not failing_conditions(rule, attrs)


def explain_missing(rules: List[dict], attrs: dict) -> Optional[dict]:
    """Hvorfor fandt turen ingen grundpris? Den nærmeste grundpris-regel (færrest
    betingelser der ikke passer) og hvilke betingelser der ikke passer."""
    best = None
    for r in rules:
        if r.get("kind") != "base" or not r.get("active", True):
            continue
        fails = failing_conditions(r, attrs)
        if not fails:
            return None
        key = (len(fails), -specificity(r))
        if best is None or key < best[0]:
            best = (key, r, fails)
    if not best:
        return {"rule": None, "failing": [], "text": "Der er ikke oprettet nogen grundpris endnu"}
    _k, r, fails = best
    parts = [CONDITION_LABELS.get(f, f) for f in fails]
    if "materials" in fails and len(tour_materials(attrs)) > 1:
        parts[fails.index("materials")] = (f"materiale (turen har {' + '.join(tour_materials(attrs))}, "
                                           f"reglen gælder {', '.join((r.get('conditions') or {}).get('materials') or [])})")
    if "outcome" in fails and attrs.get("outcome") == "not_completed":
        parts[fails.index("outcome")] = "forgæves kørsel (ingen pris for forgæves kørsel)"
    return {"rule": r.get("name"), "failing": fails,
            "text": f"Nærmeste regel \"{r.get('name')}\" passer ikke på: {', '.join(parts)}"}


def specificity(rule: dict) -> int:
    c = rule.get("conditions") or {}
    score = sum(w for k, w in _WEIGHTS.items() if c.get(k))
    score += 1 if c.get("trailer") else 0
    score += 2 if c.get("trailer_counts") else 0
    score += 1 if (c.get("time_from") and c.get("time_to")) else 0
    score += 1 if (c.get("outcome") or "completed") != "completed" else 0
    return score


def _pick(rules: List[dict]) -> Optional[dict]:
    if not rules:
        return None
    return max(rules, key=lambda r: (specificity(r), r.get("updated_at") or ""))


def select_rules(rules: List[dict], attrs: dict) -> Tuple[Optional[dict], List[dict]]:
    """(winning base rule, one winning surcharge rule per category)."""
    matching = [r for r in rules if rule_matches(r, attrs)]
    base = _pick([r for r in matching if r.get("kind") == "base"])
    by_cat: Dict[str, List[dict]] = {}
    for r in matching:
        if r.get("kind") == "surcharge":
            by_cat.setdefault(r.get("category") or "other", []).append(r)
    surcharges = [_pick(v) for _, v in sorted(by_cat.items())]
    return base, [s for s in surcharges if s]


def rounding_label(p: dict) -> str:
    mode, step = p.get("rounding_mode") or "none", int(p.get("rounding_minutes") or 0)
    if mode == "none" or not step:
        return "Ingen afrunding"
    word = {"up": "Op", "down": "Ned", "nearest": "Nærmeste"}.get(mode, mode)
    return f"{word} til {step} min"


# ---------------------------------------------------------------------------
# Price one tour
# ---------------------------------------------------------------------------

def price_tour(attrs: dict, rules: List[dict], time_info: Optional[dict],
               override: Optional[dict] = None) -> dict:
    """attrs: tour attributes (see rule_matches) + `containers`,
    `waiting_min`, `deduct_pause_override` (None|bool).
    time_info: {"gross": raw minutes, "total": minutes after concurrency
    split, "pause": of which during pause} or None when start/end missing.
    override: tour.price_override ({"mode": "rules"|"fixed", "amount",
    "extra_lines": [{"label","amount"}], "note"}).
    """
    result = {
        "status": "ok", "model": None, "base_rule": None, "lines": [],
        "time": None, "total": None, "flags": [],
    }
    override = override or {}
    base, surcharges = select_rules(rules, attrs)
    base_amount = None
    billable_min = None

    if base:
        p = base.get("pricing") or {}
        model = p.get("model") or "fixed"
        result["model"] = model
        result["base_rule"] = {"id": base.get("id"), "name": base.get("name")}
        if model == "fixed":
            base_amount = float(p.get("amount") or 0)
            result["lines"].append({"type": "base", "label": base.get("name") or "Fast pris",
                                    "amount": money(base_amount), "rule_id": base.get("id")})
        elif model == "per_container":
            qty = max(1, int(attrs.get("containers") or 1))
            base_amount = float(p.get("amount") or 0) * qty
            result["lines"].append({"type": "base",
                                    "label": f"{base.get('name') or 'Pris pr. container'} ({qty} stk.)",
                                    "amount": money(base_amount), "rule_id": base.get("id")})
        elif model == "per_unit":
            unit = norm_label(p.get("unit") or "")
            units = {norm_label(k): v for k, v in (attrs.get("units") or {}).items()}
            qty = float(units.get(unit) or 0)
            if qty <= 0:
                result["status"] = "missing_qty"
                result["flags"].append(f"Turen har intet antal i {p.get('unit') or 'enheden'}")
            else:
                rate = float(p.get("amount") or 0)
                base_amount = rate * qty
                src = (attrs.get("units_source") or {}).get(unit) or ""
                result["lines"].append({"type": "base",
                                        "label": f"{base.get('name') or 'Pris pr. enhed'} ({qty:g} {p.get('unit')} × {rate:g} kr{', ' + src if src else ''})",
                                        "amount": money(base_amount), "rule_id": base.get("id")})
                min_amount = float(p.get("min_amount") or 0)
                if min_amount and base_amount < min_amount:
                    result["lines"].append({"type": "base", "label": "Op til minimumsbeløb",
                                            "amount": money(min_amount - base_amount), "rule_id": base.get("id")})
                    base_amount = min_amount
        else:  # hourly
            deduct = p.get("deduct_pause", True)
            if attrs.get("deduct_pause_override") is not None:
                deduct = bool(attrs["deduct_pause_override"])
            if not time_info:
                result["status"] = "missing_time"
                result["flags"].append("Mangler start- eller sluttid")
            else:
                raw = time_info["total"] - (time_info["pause"] if deduct else 0)
                billable_min = round_minutes(max(raw, 0), p.get("rounding_mode") or "none",
                                             int(p.get("rounding_minutes") or 0))
                min_minutes = int(p.get("min_minutes") or 0)
                if min_minutes and billable_min < min_minutes:
                    billable_min = min_minutes
                    result["flags"].append(f"Minimum {min_minutes} min anvendt")
                rate = float(p.get("hourly_rate") or 0)
                start_fee = float(p.get("start_fee") or 0)
                time_amount = rate * billable_min / 60
                if start_fee:
                    result["lines"].append({"type": "base", "label": "Startgebyr",
                                            "amount": money(start_fee), "rule_id": base.get("id")})
                h, m = divmod(billable_min, 60)
                result["lines"].append({"type": "base",
                                        "label": f"{base.get('name') or 'Timepris'} ({h}t {m:02d}m × {rate:g} kr/t)",
                                        "amount": money(time_amount), "rule_id": base.get("id")})
                base_amount = start_fee + time_amount
                min_amount = float(p.get("min_amount") or 0)
                if min_amount and base_amount < min_amount:
                    result["lines"].append({"type": "base", "label": "Op til minimumsbeløb",
                                            "amount": money(min_amount - base_amount),
                                            "rule_id": base.get("id")})
                    base_amount = min_amount
                result["time"] = {
                    "gross_min": int(round(time_info["gross"])),
                    "shared_min": int(round(time_info["gross"] - time_info["total"])),
                    "pause_min": int(round(time_info["pause"])),
                    "deduct_pause": deduct,
                    "billable_min": billable_min,
                    "rounding": rounding_label(p),
                }
    else:
        result["status"] = "missing_rule"
        result["flags"].append("Ingen grundpris-regel matcher turen")

    # Fast/aftalt pris: tillæg beregnes ud fra det faste beløb (fx % ved
    # weekend), men kun ventetid beholdes - og kun hvis det er valgt.
    fixed = override.get("mode") == "fixed"
    surcharge_base = float(override.get("amount") or 0) if fixed else base_amount
    if surcharge_base is not None:
        base_amount = surcharge_base
        for s in surcharges:
            sp = s.get("surcharge") or {}
            unit, value = sp.get("unit") or "kr", float(sp.get("value") or 0)
            if s.get("category") == "stop":
                included = int(sp.get("included") if sp.get("included") is not None else 2)
                extra = max(0, int(attrs.get("stops") or 0) - included)
                if not extra:
                    continue
                amt = value * extra if unit != "percent" else base_amount * value / 100 * extra
                detail = f"{extra} ekstra stop × {value:g}{'%' if unit == 'percent' else ' kr'}"
            elif unit == "percent":
                amt, detail = base_amount * value / 100, f"{value:g}%"
            elif unit == "per_hour":
                if s.get("category") == "waiting":
                    mins = round_minutes(float(attrs.get("waiting_min") or 0), "up", 15)
                else:
                    mins = billable_min if billable_min is not None else (
                        time_info["total"] if time_info else None)
                if not mins:
                    continue
                amt, detail = value * mins / 60, f"{mins} min × {value:g} kr/t"
            else:
                amt, detail = value, ""
            if s.get("category") == "waiting" and not attrs.get("waiting_min"):
                continue
            label = s.get("name") or SURCHARGE_CATEGORIES.get(s.get("category"), "Tillæg")
            result["lines"].append({"type": "surcharge",
                                    "label": f"{label} ({detail})" if detail else label,
                                    "amount": money(amt), "rule_id": s.get("id"),
                                    "category": s.get("category")})

    if fixed:
        keep = [l for l in result["lines"] if l.get("category") == "waiting"] if override.get("add_waiting") else []
        # 2026-10-18: Vis de tillæg der er indregnet i den aftalte pris (0 kr),
        # så "hvorfor er der ingen weekend på denne tur?" besvarer sig selv.
        included = [{"type": "included", "label": f"{l['label']} - indregnet i aftalt pris", "amount": 0.0,
                     "category": l.get("category")}
                    for l in result["lines"] if l.get("type") == "surcharge" and l not in keep]
        result["lines"] = [{"type": "override", "label": override.get("label") or "Manuel pris",
                            "amount": money(float(override.get("amount") or 0))}] + keep + included
        result["status"] = "ok"
        result["flags"] = [f for f in result["flags"] if f.startswith("Minimum")]
        result["flags"].append("Manuel pris")
    for x in override.get("extra_lines") or []:
        result["lines"].append({"type": "extra", "label": x.get("label") or "Ekstra",
                                "amount": money(float(x.get("amount") or 0))})

    if result["status"] == "ok" or override.get("mode") == "fixed":
        result["total"] = money(sum(l["amount"] for l in result["lines"]))
    return result
