"""Eksemplerne i PRISBEREGNING.md - regnet af den rigtige prismotor.

Hvert eksempel har et håndregnet facit. Scriptet kører eksemplet gennem
backend/pricing.py (og serverens hjælpefunktioner i backend/server.py) og
stopper med en fejl, hvis motoren giver et andet resultat. Derefter skrives
eksempel-afsnittet som markdown på stdout.

Kør i app-containeren (server.py skal kunne importeres):

    docker exec -i cf-app-e2e python - < scripts/prisberegning_eksempler.py > /tmp/eksempler.md

Kun læsning: databasen bruges kun af ét eksempel (turens tid), og der skrives intet.
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import pricing as P  # noqa: E402
import server as S  # noqa: E402

CUST = {"HF": "Helsingør Forsyning", "ARGO": "ARGO", "firma:byg aps": "Byg ApS (egen kunde)"}
SECTIONS = {}      # afsnitstitel -> markdown-linjer (udskrives i B-nummerorden)
CUR = [None]
COUNT = [0]
FAILS = []


class _Out:
    def append(self, text):
        SECTIONS[CUR[0]].append(text)


OUT = _Out()


# ----------------------------------------------------------------------------- formatering
def kr(x) -> str:
    if x is None:
        return "-"
    s = f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} kr"


def tal(x) -> str:
    x = float(x)
    return f"{x:g}".replace(".", ",")


def cond_text(c: dict) -> str:
    c = c or {}
    p = []
    if c.get("customer_ids"):
        p.append("kunde = " + " eller ".join(CUST.get(x, x) for x in c["customer_ids"]))
    if c.get("location_codes"):
        p.append("lokation = " + " eller ".join(c["location_codes"]))
    if c.get("delivery_labels"):
        p.append("leveringsadresse = " + " eller ".join(f'"{x}"' for x in c["delivery_labels"]))
    if c.get("task_types"):
        p.append("opgavetype = " + " eller ".join(P.TASK_TYPES.get(x, x) for x in c["task_types"]))
    if c.get("materials"):
        p.append("materiale = " + " eller ".join(c["materials"]))
    if c.get("container_labels"):
        p.append("containerstørrelse = " + " eller ".join(f'"{x}"' for x in c["container_labels"]))
    if c.get("priorities"):
        p.append("prioritet = " + " eller ".join(P.PRIORITIES.get(x, x) for x in c["priorities"]))
    if c.get("day_types"):
        p.append("dagtype = " + " eller ".join(P.DAY_TYPES.get(x, x) for x in c["day_types"]))
    if c.get("trailer") == "with":
        p.append("med hænger")
    if c.get("trailer") == "without":
        p.append("uden hænger")
    if c.get("trailer_counts"):
        p.append("antal hængere = " + " eller ".join("3+" if int(k) >= 3 else str(k) for k in c["trailer_counts"]))
    if c.get("time_from") and c.get("time_to"):
        p.append(f"start kl. {c['time_from']}-{c['time_to']}")
    if (c.get("outcome") or "completed") == "not_completed":
        p.append("udfald = forgæves")
    if c.get("outcome") == "any":
        p.append("udfald = alle (gennemført og forgæves)")
    return ", ".join(p) or "ingen betingelser (gælder alle ture)"


def price_text(r: dict) -> str:
    if r["kind"] == "base":
        p = r.get("pricing") or {}
        m = p.get("model")
        if m == "fixed":
            return f"fast pris {kr(p['amount'])}"
        if m == "per_container":
            return f"{kr(p['amount'])} pr. container"
        if m == "per_unit":
            t = f"{kr(p['amount'])} pr. {p['unit']}"
            return t + (f", minimum {kr(p['min_amount'])}" if p.get("min_amount") else "")
        bits = [f"timepris {tal(p['hourly_rate'])} kr/t"]
        if p.get("start_fee"):
            bits.append(f"startgebyr {kr(p['start_fee'])}")
        if p.get("min_minutes"):
            bits.append(f"minimum {p['min_minutes']} min")
        if p.get("min_amount"):
            bits.append(f"minimumsbeløb {kr(p['min_amount'])}")
        bits.append(P.rounding_label(p).lower())
        bits.append("pause trækkes fra" if p.get("deduct_pause", True) else "pause trækkes ikke fra")
        return ", ".join(bits)
    s = r.get("surcharge") or {}
    cat = P.SURCHARGE_CATEGORIES.get(r.get("category"), r.get("category"))
    if r.get("category") == "stop":
        inc = s.get("included") if s.get("included") is not None else 2
        return f"tillæg ({cat}): {kr(s['value'])} pr. stop ud over {inc}"
    if s.get("unit") == "percent":
        return f"tillæg ({cat}): {tal(s['value'])} % af grundprisen"
    if s.get("unit") == "per_hour":
        return f"tillæg ({cat}): {tal(s['value'])} kr/t"
    return f"tillæg ({cat}): {kr(s['value'])}"


def rule_line(r: dict) -> str:
    extra = []
    if r.get("active") is False:
        extra.append("SLÅET FRA")
    if r.get("valid_from") or r.get("valid_to"):
        extra.append(f"kørselsdato {r.get('valid_from') or '…'} til {r.get('valid_to') or '…'}")
    if r.get("version_from") or r.get("version_to"):
        extra.append(f"version for ture oprettet {r.get('version_from') or '…'} til {r.get('version_to') or '…'}")
    if r.get("backfill_unpriced"):
        extra.append("gælder også ældre ture uden pris")
    if r.get("updated_at") and r.get("_show_updated"):
        extra.append(f"senest rettet {r['updated_at'][:10]}")
    ex = f" [{'; '.join(extra)}]" if extra else ""
    return (f"- **{r['name']}** - {price_text(r)}. Gælder: {cond_text(r.get('conditions'))}. "
            f"Specificitet {P.specificity(r)}.{ex}")


DEFAULT_ATTRS = {
    "customer_id": "HF", "location_code": "1101", "material": "Pap", "materials": ["Pap"], "task_type": "normal",
    "priority": "normal", "day_type": "weekday", "trailer": False, "trailer_count": 0, "trailer_confirmed": True,
    "container_label": "", "delivery_label": "", "start_min": 8 * 60, "outcome": "completed",
    "service_date": "2026-10-20", "containers": 1, "waiting_min": 0, "deduct_pause_override": None,
    "units": {}, "units_source": {}, "stops": 2,
}


def tour_text(a: dict, time_info, override) -> str:
    p = [f"kunde {CUST.get(a['customer_id'], a['customer_id'])}", f"lokation {a['location_code'] or '(ingen)'}"]
    mats = P.tour_materials(a)
    p.append("materiale " + (" + ".join(mats) if mats else "(intet)"))
    if a["task_type"] != "normal":
        p.append(f"opgavetype {P.TASK_TYPES.get(a['task_type'], a['task_type'])}")
    if a["priority"] != "normal":
        p.append(f"prioritet {P.PRIORITIES.get(a['priority'])}")
    p.append(f"dagtype {P.DAY_TYPES.get(a['day_type'])}")
    if a["trailer"] or a["trailer_count"]:
        p.append(f"{a['trailer_count'] or 1} hænger(e)")
    if a.get("container_label"):
        p.append(f"containerstørrelse \"{a['container_label']}\"")
    if a.get("delivery_label"):
        p.append(f"leveringsadresse \"{a['delivery_label']}\"")
    st = a["start_min"]
    p.append(f"start kl. {st // 60:02d}:{st % 60:02d}" if st >= 0 else "ingen starttid")
    if a["outcome"] == "not_completed":
        p.append("FORGÆVES")
    if a["containers"] != 1:
        p.append(f"{a['containers']} containere")
    if a["waiting_min"]:
        p.append(f"ventetid {a['waiting_min']} min")
    if a["stops"] != 2:
        p.append(f"{a['stops']} stop")
    if a.get("units"):
        p.append("antal: " + ", ".join(f"{tal(v)} {k} ({(a.get('units_source') or {}).get(k, 'planlagt')})"
                                        for k, v in a["units"].items()))
    if a.get("deduct_pause_override") is not None:
        p.append("admin: pause " + ("trækkes fra" if a["deduct_pause_override"] else "trækkes ikke fra"))
    if time_info:
        t = f"tid {tal(time_info['total'])} min"
        if time_info.get("gross") not in (None, time_info["total"]):
            t += f" (af {tal(time_info['gross'])} min før deling med samtidige ture)"
        if time_info.get("pause"):
            t += f", heraf {tal(time_info['pause'])} min pause"
        p.append(t)
    if override:
        if override.get("mode") == "fixed":
            p.append(f"{override.get('label') or 'Manuel pris'} {kr(override['amount'])}"
                     + (" + ventetid oveni" if override.get("add_waiting") else ""))
        for x in override.get("extra_lines") or []:
            p.append(f"ekstra linje \"{x['label']}\" {kr(x['amount'])}")
    return "; ".join(p)


def result_text(res: dict) -> str:
    out = []
    for l in res.get("lines") or []:
        out.append(f"  - {l['label']}: {kr(l['amount'])}")
    if res.get("total") is not None:
        out.append(f"  - **I alt {kr(res['total'])}** (ekskl. moms)")
    else:
        st = {"missing_rule": "Mangler pris", "missing_time": "Mangler tid", "missing_qty": "Mangler antal"}.get(res["status"], res["status"])
        out.append(f"  - **Ingen pris: {st}** (turen tæller ikke med i summen)")
    if res.get("flags"):
        out.append("  - Markeringer: " + "; ".join(res["flags"]))
    why = (res.get("why") or {}).get("text") if isinstance(res.get("why"), dict) else None
    if why:
        out.append(f"  - Forklaring i Rapport: \"{why}\"")
    return "\n".join(out)


# ----------------------------------------------------------------------------- byggeklodser
_rid = [0]


def _rule(name, kind, cond=None, upd="2026-01-01T08:00:00", **kw):
    _rid[0] += 1
    c = {k: v for k, v in (cond or {}).items()}
    r = {"id": f"r{_rid[0]}", "name": name, "kind": kind, "conditions": c, "active": kw.pop("active", True),
         "valid_from": kw.pop("valid_from", ""), "valid_to": kw.pop("valid_to", ""), "updated_at": upd}
    for k in ("version_from", "version_to", "backfill_unpriced", "_show_updated"):
        if k in kw:
            r[k] = kw.pop(k)
    if kind == "base":
        r["pricing"] = kw
    else:
        r["category"] = kw.pop("cat")
        r["surcharge"] = kw
    return r


def FIX(name, amount, cond=None, **kw):
    return _rule(name, "base", cond, model="fixed", amount=amount, **kw)


def PERC(name, amount, cond=None, **kw):
    return _rule(name, "base", cond, model="per_container", amount=amount, **kw)


def UNIT(name, amount, unit, cond=None, min_amount=0, **kw):
    return _rule(name, "base", cond, model="per_unit", amount=amount, unit=unit, min_amount=min_amount, **kw)


def HOUR(name, rate, cond=None, start_fee=0, min_minutes=0, min_amount=0, rounding_mode="none", rounding_minutes=0,
         deduct_pause=True, **kw):
    return _rule(name, "base", cond, model="hourly", hourly_rate=rate, start_fee=start_fee, min_minutes=min_minutes,
                 min_amount=min_amount, rounding_mode=rounding_mode, rounding_minutes=rounding_minutes,
                 deduct_pause=deduct_pause, **kw)


def SUR(name, cat, value, cond=None, unit="kr", **kw):
    return _rule(name, "surcharge", cond, cat=cat, unit=unit, value=value, **kw)


WEEKEND = {"day_types": ["saturday", "sunday"]}


def T(minutes, pause=0, gross=None):
    return {"gross": gross if gross is not None else minutes, "total": minutes, "pause": pause}


def A(**kw):
    a = dict(DEFAULT_ATTRS)
    if "material" in kw and "materials" not in kw:
        kw["materials"] = [kw["material"]] if kw["material"] else []
    if "start" in kw:
        s = kw.pop("start")
        kw["start_min"] = P.hhmm_to_min(s) if s else -1
    a.update(kw)
    return a


def section(title, intro=""):
    CUR[0] = title
    SECTIONS[title] = [f"\n### {title}\n"] + ([intro + "\n"] if intro else [])


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def ex(title, rules, attrs, why, expect, time=None, override=None, status="ok", extra_check=None):
    """Et priseksempel: regler + tur -> pris. `expect` = forventet total (None = ingen pris)."""
    COUNT[0] += 1
    n = COUNT[0]
    res = P.price_tour(attrs, rules, time, override)
    got = res.get("total")
    check(got == (None if expect is None else round(expect, 2)), f"E{n} {title}: forventet {expect}, motoren gav {got}")
    check(res["status"] == status or (override or {}).get("mode") == "fixed",
          f"E{n} {title}: forventet status {status}, motoren gav {res['status']}")
    if res["status"] == "missing_rule":
        res["why"] = P.explain_missing(rules, attrs)
    if extra_check:
        try:
            ok, msg = extra_check(res)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, repr(e)
        check(ok, f"E{n} {title}: {msg}")
    OUT.append(f"#### E§. {title}\n")
    OUT.append("**Regler:**\n" + ("\n".join(rule_line(r) for r in rules) if rules else "- (ingen regler)") + "\n")
    OUT.append(f"**Turen:** {tour_text(attrs, time, override)}\n")
    OUT.append("**Resultat:**\n" + result_text(res) + "\n")
    OUT.append(f"**Hvorfor:** {why}\n")
    return res


def note(title, body, ok=True, msg=""):
    """Et eksempel der ikke er en hel prisberegning (fx en tabel)."""
    COUNT[0] += 1
    n = COUNT[0]
    check(ok, f"E{n} {title}: {msg}")
    OUT.append(f"#### E§. {title}\n")
    OUT.append(body.strip() + "\n")


def has_flag(text):
    return lambda res: (any(text in f for f in res.get("flags") or []), f"mangler markeringen '{text}' ({res.get('flags')})")


def line_has(text):
    return lambda res: (any(text in l["label"] for l in res.get("lines") or []),
                        f"ingen linje med '{text}' ({[l['label'] for l in res.get('lines') or []]})")


# ----------------------------------------------------------------------------- eksempler
def run_engine_examples():
    G = FIX("Standardpris", 1000)

    section("B1. Grundlæggende", "Én tur, få regler. Standardturen er en almindelig afhentning (opgavetype "
            "Afhentning) for Helsingør Forsyning (HF) på lokation 1101, materiale Pap, en hverdag "
            "(tirsdag 20.10.2026) med start kl. 08:00, gennemført, uden hænger, ventetid og ekstra stop.")
    ex("Én generel fast pris", [FIX("Standardpris", 950)], A(),
       "Reglen har ingen betingelser, så den passer på alle gennemførte ture. Fast pris = beløbet.", 950)
    ex("Ingen regler", [], A(),
       "Uden en grundpris kan turen ikke prissættes. Den står som \"Mangler pris\" og tæller ikke med i "
       "rapportens sum.", None, status="missing_rule")
    ex("Reglen er slået fra", [FIX("Gammel pris", 950, active=False)], A(),
       "En regel der er slået fra, deltager slet ikke - heller ikke i forklaringen. Derfor siger forklaringen "
       "\"ikke oprettet nogen grundpris\", selvom reglen findes.", None, status="missing_rule",
       extra_check=lambda r: ("ikke oprettet nogen grundpris" in r["why"]["text"], r["why"]["text"]))
    ex("Kun et tillæg, ingen grundpris", [SUR("Weekendtillæg", "weekend", 500, WEEKEND)], A(day_type="saturday"),
       "Tillæg lægges kun oven på en grundpris. Uden grundpris beregnes intet - heller ikke tillægget.",
       None, status="missing_rule", extra_check=lambda r: (r["lines"] == [], "der burde ikke være linjer"))

    section("B2. Overlappende grundpriser (specificitet)",
            "Passer flere grundpriser på samme tur, vinder den mest specifikke. Point: kunde 64, lokation 32, "
            "leveringsadresse 16, opgavetype 8, materiale 4, containerstørrelse 2, prioritet 1, dagtype 1, "
            "hænger med/uden 1, antal hængere 2, tidsrum 1, udfald (andet end gennemført) 1. Point lægges "
            "sammen. Står det lige, vinder den senest rettede regel.")
    ex("Kundepris slår generel pris", [G, FIX("HF-pris", 1200, {"customer_ids": ["HF"]})], A(),
       "Begge passer. HF-prisen har 64 point mod 0, så den vinder.", 1200)
    ex("Kunde slår lokation", [FIX("HF-pris", 1200, {"customer_ids": ["HF"]}), FIX("Lokation 1101", 1100, {"location_codes": ["1101"]})], A(),
       "Kunde (64) > lokation (32).", 1200)
    ex("Kunde slår lokation + materiale", [FIX("1101 Pap", 1050, {"location_codes": ["1101"], "materials": ["Pap"]}),
                                            FIX("HF-pris", 1200, {"customer_ids": ["HF"]})], A(),
       "Lokation + materiale = 32 + 4 = 36, kunde = 64. En kundepris slår altid alt, der ikke nævner kunden.", 1200)
    ex("Kunde + lokation slår kunde", [FIX("HF-pris", 1200, {"customer_ids": ["HF"]}),
                                        FIX("HF på 1101", 1150, {"customer_ids": ["HF"], "location_codes": ["1101"]})], A(),
       "64 + 32 = 96 mod 64. Den mere præcise aftale vinder, også selvom den er billigere.", 1150)
    ex("Opgavetype slår materiale", [FIX("Byt container", 800, {"task_types": ["flyt"]}), FIX("Pap", 700, {"materials": ["Pap"]})],
       A(task_type="flyt"), "Opgavetype (8) > materiale (4).", 800)
    ex("Leveringsadresse slår opgavetype + materiale + størrelse",
       [FIX("HCS", 1300, {"delivery_labels": ["HCS A/S Helsingør"]}),
        FIX("Afhentning Pap 20 m³", 900, {"task_types": ["normal"], "materials": ["Pap"], "container_labels": ["Åben container 20 m³"]})],
       A(container_label="Åben container 20 m³", delivery_label="HCS A/S Helsingør"),
       "16 > 8 + 4 + 2 = 14. Vægtene er valgt, så en højere betingelse altid slår alle lavere tilsammen.", 1300)
    ex("Lige specifikke: den senest rettede vinder",
       [FIX("Pris A", 900, upd="2026-03-01T08:00:00", _show_updated=True), FIX("Pris B", 950, upd="2026-05-01T08:00:00", _show_updated=True)], A(),
       "Begge har 0 point. Så vinder den, der senest er rettet (updated_at). Det er en faldgrube: to "
       "generelle priser bør ikke findes samtidig. Editoren advarer, når betingelserne er helt ens.", 950)
    ex("Lige specifikke på hver sin led", [FIX("Haster-pris", 1100, {"priorities": ["haster"]}, upd="2026-02-01T08:00:00", _show_updated=True),
                                          FIX("Hverdagspris", 1000, {"day_types": ["weekday"]}, upd="2026-04-01T08:00:00", _show_updated=True)],
       A(priority="haster"),
       "Prioritet og dagtype giver 1 point hver. En haster-tur på en hverdag passer på begge, og så vinder den "
       "senest rettede - her hverdagsprisen. Vil man have et haster-pristrin, er et haster-TILLÆG det rigtige.", 1000)
    ex("Kundepris for en anden kunde gælder ikke", [G, FIX("ARGO-pris", 1500, {"customer_ids": ["ARGO"]})], A(),
       "ARGO-reglen passer ikke på en HF-tur. Den generelle pris bruges.", 1000)
    ex("Lokationspris for en anden lokation", [G, FIX("Lokation 1102", 1250, {"location_codes": ["1102"]})], A(),
       "Turen er på 1101.", 1000)
    ex("Flere kunder i samme betingelse", [G, FIX("HF og ARGO", 1150, {"customer_ids": ["HF", "ARGO"]})], A(),
       "En liste betyder \"en af disse\". Specificiteten er stadig 64 - antallet af værdier tæller ikke.", 1150)
    ex("Kunde + hverdag slår kunde (hverdag)", [FIX("HF", 1200, {"customer_ids": ["HF"]}),
                                               FIX("HF hverdag", 1100, {"customer_ids": ["HF"], "day_types": ["weekday"]})], A(),
       "65 > 64 på en hverdag.", 1100)
    ex("Kunde + hverdag passer ikke en lørdag", [FIX("HF", 1200, {"customer_ids": ["HF"]}),
                                                 FIX("HF hverdag", 1100, {"customer_ids": ["HF"], "day_types": ["weekday"]})],
       A(day_type="saturday"), "Lørdag passer kun den brede HF-regel.", 1200)
    ex("Kørselsdato uden for reglens periode", [FIX("HF 2026", 1200, {"customer_ids": ["HF"]}, valid_to="2026-09-30"), G], A(),
       "Reglen gælder ture KØRT til og med 30.09.2026. Turen er kørt 20.10.2026, så den generelle pris bruges.", 1000)
    ex("Periode udløbet og ingen anden pris", [FIX("HF 2026", 1200, {"customer_ids": ["HF"]}, valid_to="2026-09-30")], A(),
       "Rapporten forklarer, hvad der mangler.", None, status="missing_rule",
       extra_check=lambda r: ("periode" in r["why"]["text"], r["why"]["text"]))
    ex("Containerstørrelse matches uden hensyn til store/små bogstaver og mellemrum",
       [FIX("20 m³", 900, {"container_labels": ["Åben container 20 m³"]})], A(container_label="åben  container 20 M³"),
       "Tekst-betingelser (containerstørrelse, leveringsadresse, materiale) sammenlignes med små bogstaver og enkelte mellemrum.", 900)
    ex("Leveringsadresse matches på navnet", [FIX("HCS", 1300, {"delivery_labels": ["HCS A/S Helsingør"]})],
       A(delivery_label="hcs a/s  helsingør"),
       "Leveringsadressen matches på modtagerens navn, ikke på gade og nummer. Samme modtager på flere pladser "
       "prissættes derfor kun én gang.", 1300)

    section("B3. Tillæg - og når flere tillæg overlapper",
            "Tillæg har en kategori (Weekend, Helligdag, Haster, Hænger, Aften/nat, Ventetid, Ekstra stop, Andet). "
            "Pr. kategori bruges kun den mest specifikke regel, der passer (samme pointsystem). Forskellige "
            "kategorier lægges sammen.")
    W = SUR("Weekendtillæg", "weekend", 500, WEEKEND)
    ex("Weekendtillæg en lørdag", [G, W], A(day_type="saturday"), "1.000 + 500.", 1500)
    ex("Weekendtillæg en hverdag", [G, W], A(), "Tillægget passer ikke en hverdag.", 1000)
    WHF = SUR("Weekend HF", "weekend", 300, {"customer_ids": ["HF"], **WEEKEND})
    ex("Kundens eget weekendtillæg erstatter det generelle", [G, W, WHF], A(day_type="saturday"),
       "Begge weekendtillæg passer. HF-tillægget har 65 point mod 1 og vinder. Det generelle bruges IKKE "
       "også - ingen dobbeltopkrævning.", 1300)
    ex("En anden kunde får det generelle", [G, W, WHF], A(day_type="saturday", customer_id="ARGO"),
       "HF-tillægget passer ikke på ARGO.", 1500)
    ex("Kunde fritaget for weekendtillæg", [G, W, SUR("Weekend HF fritaget", "weekend", 0, {"customer_ids": ["HF"], **WEEKEND})],
       A(day_type="saturday"), "Et kundespecifikt tillæg på 0 kr vinder over det generelle og fritager kunden. "
       "Linjen vises med 0 kr, så man kan se hvorfor.", 1000)
    ex("Forskellige kategorier lægges sammen", [G, W, SUR("Haster", "haster", 250, {"priorities": ["haster"]})],
       A(day_type="saturday", priority="haster"), "1.000 + 500 (weekend) + 250 (haster).", 1750)
    ex("Helligdag på en lørdag: kun helligdagstillæg", [G, W, SUR("Helligdag", "holiday", 800, {"day_types": ["holiday"]})],
       A(day_type="holiday", service_date="2026-12-26"),
       "Dagtyperne udelukker hinanden. 26.12.2026 er en lørdag og 2. juledag, så dagtypen er \"Helligdag\" - "
       "ikke \"Lørdag\". Weekendtillægget passer derfor ikke.", 1800)
    ex("Lørdagstillæg gælder ikke søndag", [G, SUR("Lørdag", "weekend", 400, {"day_types": ["saturday"]})], A(day_type="sunday"),
       "Tillægget nævner kun lørdag.", 1000)
    ex("Tillæg uden betingelser gælder altid", [G, SUR("Miljøgebyr", "other", 75)], A(), "Et tillæg uden betingelser lægges på alle ture.", 1075)
    ex("To tillæg i samme kategori: kun ét bruges", [G, SUR("Miljøgebyr", "other", 75), SUR("Brobizz", "other", 120, {"location_codes": ["1101"]})],
       A(), "Begge er kategori \"Andet\". Brobizz (32 point) vinder, og miljøgebyret bortfalder. Skal begge "
       "opkræves, skal de have hver sin kategori.", 1120)
    ex("To lige tillæg i samme kategori", [G, SUR("Gebyr A", "other", 50, upd="2026-03-01T08:00:00", _show_updated=True),
                                          SUR("Gebyr B", "other", 60, upd="2026-06-01T08:00:00", _show_updated=True)], A(),
       "Lige specifikke: den senest rettede vinder.", 1060)
    ex("Specifikt haster-tillæg for materialet", [G, SUR("Haster", "haster", 200, {"priorities": ["haster"]}),
                                                 SUR("Haster Pap", "haster", 300, {"priorities": ["haster"], "materials": ["Pap"]})],
       A(priority="haster"), "Haster Pap har 1 + 4 = 5 point mod 1.", 1300)
    ex("Kundetillæg for en anden kunde", [G, W, SUR("Weekend ARGO", "weekend", 250, {"customer_ids": ["ARGO"], **WEEKEND})],
       A(day_type="saturday"), "ARGO-tillægget passer ikke på HF; det generelle gælder.", 1500)
    ex("Procent og kroner i forskellige kategorier", [G, SUR("Weekend 25 %", "weekend", 25, WEEKEND, unit="percent"),
                                                     SUR("Haster", "haster", 200, {"priorities": ["haster"]})],
       A(day_type="saturday", priority="haster"), "25 % af 1.000 = 250, plus 200.", 1450)

    section("B4. Procenttillæg", "Et %-tillæg regnes ALTID af grundprisen (inkl. startgebyr og evt. op til "
            "minimumsbeløb) - aldrig af andre tillæg. Flere %-tillæg lægges sammen, de ganges ikke.")
    ex("Haster 15 %", [G, SUR("Haster 15 %", "haster", 15, {"priorities": ["haster"]}, unit="percent")], A(priority="haster"), "15 % af 1.000.", 1150)
    ex("Procent af timepris med startgebyr", [HOUR("Timepris", 600, start_fee=200), SUR("Weekend 20 %", "weekend", 20, WEEKEND, unit="percent")],
       A(day_type="saturday"), "Grundpris = 200 + 600 × 90/60 = 1.100. 20 % af 1.100 = 220.", 1320, time=T(90))
    ex("Procent af minimumsbeløb", [HOUR("Timepris", 600, min_amount=500), SUR("Haster 10 %", "haster", 10, {"priorities": ["haster"]}, unit="percent")],
       A(priority="haster"), "30 min = 300 kr, løftes til minimum 500. 10 % af 500 = 50.", 550, time=T(30))
    ex("To procenttillæg ganges ikke", [G, SUR("Weekend 20 %", "weekend", 20, WEEKEND, unit="percent"),
                                       SUR("Haster 10 %", "haster", 10, {"priorities": ["haster"]}, unit="percent")],
       A(day_type="saturday", priority="haster"), "200 + 100 = 300 (ikke 1.000 × 1,2 × 1,1).", 1300)
    ex("Procent af pris pr. container", [PERC("Pr. container", 400), SUR("Weekend 10 %", "weekend", 10, WEEKEND, unit="percent")],
       A(day_type="saturday", containers=3), "3 × 400 = 1.200. 10 % = 120.", 1320)
    ex("Procent på en aftalt pris er indregnet", [G, SUR("Weekend 25 %", "weekend", 25, WEEKEND, unit="percent")],
       A(day_type="saturday"), "Med aftalt pris beregnes tillæggene (500), men de vises som \"indregnet i aftalt pris\" "
       "med 0 kr. Kun ventetid kan lægges oveni (se B9).", 2000,
       override={"mode": "fixed", "amount": 2000, "label": "Aftalt pris"}, extra_check=line_has("indregnet i aftalt pris"))

    section("B5. Timepris", "Fakturerbar tid = turens tid (efter deling med samtidige ture) minus pause (hvis "
            "reglen siger det) -> afrunding -> minimum minutter. Beløb = startgebyr + timepris × minutter/60, "
            "løftet til evt. minimumsbeløb.")
    H = lambda **kw: HOUR("Timepris", 600, **kw)  # noqa: E731
    ex("Uden afrunding", [H()], A(), "95 min × 600/60 = 950.", 950, time=T(95))
    ex("Op til nærmeste 15 min", [H(rounding_mode="up", rounding_minutes=15)], A(), "95 -> 105 min. 105 × 10 = 1.050.", 1050, time=T(95))
    ex("Nærmeste 15 min (ned)", [H(rounding_mode="nearest", rounding_minutes=15)], A(), "95/15 = 6,33 -> 6 kvarterer = 90 min.", 900, time=T(95))
    ex("Nærmeste 15 min, præcis på halvdelen", [H(rounding_mode="nearest", rounding_minutes=15)], A(),
       "97,5/15 = 6,5. Halve rundes op -> 7 kvarterer = 105 min. (Halve minutter opstår, når tid deles mellem samtidige ture.)",
       1050, time=T(97.5))
    ex("Ned til 30 min", [H(rounding_mode="down", rounding_minutes=30)], A(), "95 -> 90 min.", 900, time=T(95))
    ex("Ingen afrunding, halvt minut (22,5)", [H()], A(),
       "Uden afrunding rundes til hele minutter med Pythons round(), der runder halve til nærmeste LIGE tal: "
       "22,5 -> 22. Det sker kun ved delt tid.", 220, time=T(22.5))
    ex("Ingen afrunding, halvt minut (23,5)", [H()], A(), "23,5 -> 24 (lige tal).", 240, time=T(23.5))
    ex("Op til hele minutter", [H(rounding_mode="up", rounding_minutes=1)], A(), "\"Op til 1 min\": 22,5 -> 23.", 230, time=T(22.5))
    ex("Minimum 60 minutter", [H(min_minutes=60)], A(), "35 min løftes til 60.", 600, time=T(35),
       extra_check=has_flag("Minimum 60 min anvendt"))
    ex("Afrunding før minimum (ingen markering)", [H(rounding_mode="up", rounding_minutes=15, min_minutes=60)], A(),
       "50 -> 60 ved afrundingen. Minimum er dermed nået, så der kommer ingen markering.", 600, time=T(50),
       extra_check=lambda r: (not r["flags"], f"uventet markering {r['flags']}"))
    ex("Afrunding, så minimum", [H(rounding_mode="up", rounding_minutes=15, min_minutes=60)], A(),
       "40 -> 45 (afrunding) -> 60 (minimum).", 600, time=T(40), extra_check=has_flag("Minimum 60 min anvendt"))
    ex("Startgebyr", [H(start_fee=200)], A(), "200 + 60 min × 10 kr = 800. To linjer.", 800, time=T(60))
    ex("Minimumsbeløb", [H(start_fee=100, min_amount=500)], A(), "100 + 20 min (200) = 300. Løftes med 200 til 500.", 500, time=T(20),
       extra_check=line_has("Op til minimumsbeløb"))
    ex("Pause trækkes fra", [H()], A(), "120 min, heraf 30 min pause -> 90 min.", 900, time=T(120, pause=30))
    ex("Pause trækkes ikke fra", [H(deduct_pause=False)], A(), "Reglen siger at pausen ikke trækkes fra -> 120 min.", 1200, time=T(120, pause=30))
    ex("Admin: pausen skal trækkes fra på denne tur", [H(deduct_pause=False)], A(deduct_pause_override=True),
       "Turens rettelse (\"pause tæller/tæller ikke\") vinder over reglen.", 900, time=T(120, pause=30))
    ex("Admin: pausen skal ikke trækkes fra", [H()], A(deduct_pause_override=False), "Omvendt.", 1200, time=T(120, pause=30))
    ex("Mangler tid", [H(), W], A(day_type="saturday"),
       "Timepris kræver start og slut. Uden tid ingen grundpris - og derfor heller ingen tillæg.", None, status="missing_time",
       extra_check=lambda r: (r["lines"] == [] and "Mangler start- eller sluttid" in r["flags"], str(r)))
    over = P.split_driver_day({"A": (22 * 60 + 30, 1 * 60 + 15 + 1440)}, [])["A"]
    ex("Over midnat", [H()], A(start="22:30"),
       "Start 22:30, slut 01:15. Slut før start = næste dag: 165 min.", 1650, time=T(over["total"]))
    ex("Minimum efter pause", [H(min_minutes=60)], A(), "75 - 30 pause = 45 -> minimum 60.", 600, time=T(75, pause=30),
       extra_check=has_flag("Minimum 60 min anvendt"))

    section("B6. Samtidige ture og pauser",
            "Kører samme chauffør flere ture samtidig (fx flere containere på én hænger), deles de overlappende "
            "minutter ligeligt mellem turene (indstillingen \"split\", standard). Med \"full\" får hver tur hele tiden. "
            "Pauser fra chaufførens Tid-registrering deles på samme måde. Kun samme chauffør og samme kørselsdato tæller.")

    def split(intervals, pauses=(), mode="split"):
        iv = {k: (P.hhmm_to_min(a), P.hhmm_to_min(b)) for k, (a, b) in intervals.items()}
        ps = [(P.hhmm_to_min(a), P.hhmm_to_min(b)) for a, b in pauses]
        out = P.split_driver_day(iv, ps, mode)
        return {k: T(v["total"], v["pause"], gross=iv[k][1] - iv[k][0]) for k, v in out.items()}

    def multi(title, intervals, rules, why, expects, pauses=(), mode="split"):
        tm = split(intervals, pauses, mode)
        COUNT[0] += 1
        n = COUNT[0]
        rows = []
        for k, exp in expects.items():
            res = P.price_tour(A(start=intervals[k][0]), rules, tm[k], None)
            check(res.get("total") == exp, f"E{n} {title} tur {k}: forventet {exp}, motoren gav {res.get('total')}")
            rows.append(f"| {k} | {intervals[k][0]}-{intervals[k][1]} | {tal(tm[k]['gross'])} | {tal(tm[k]['total'])} | "
                        f"{tal(tm[k]['pause'])} | {kr(res.get('total'))} |")
        OUT.append(f"#### E§. {title}\n")
        OUT.append("**Regler:**\n" + "\n".join(rule_line(r) for r in rules) + "\n")
        OUT.append(f"**Pauser:** {', '.join(f'{a}-{b}' for a, b in pauses) or 'ingen'}. **Tilstand:** {mode}\n")
        OUT.append("| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |\n|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
        OUT.append(f"**Hvorfor:** {why}\n")

    HR = [HOUR("Timepris", 600)]
    multi("To ture helt samtidig", {"A": ("08:00", "10:00"), "B": ("08:00", "10:00")}, HR,
          "120 minutter med to ture -> 60 til hver. Kunderne betaler tilsammen for de 2 timer, chaufføren brugte.", {"A": 600, "B": 600})
    multi("Delvist overlap", {"A": ("08:00", "10:00"), "B": ("09:00", "11:00")}, HR,
          "A: 60 alene + halvdelen af 60 fælles = 90. B ligeså.", {"A": 900, "B": 900})
    multi("Delvist overlap, tilstand \"full\"", {"A": ("08:00", "10:00"), "B": ("09:00", "11:00")}, HR,
          "Hver tur får hele sin tid. Den fælles time betales to gange.", {"A": 1200, "B": 1200}, mode="full")
    multi("Tre ture", {"A": ("08:00", "11:00"), "B": ("09:00", "10:00"), "C": ("09:30", "10:30")}, HR,
          "08-09 A alene (60). 09-09:30 A+B (15 hver). 09:30-10 A+B+C (10 hver). 10-10:30 A+C (15 hver). "
          "10:30-11 A alene (30). A = 130, B = 25, C = 25. I alt 180 = de 3 timer chaufføren var i gang.",
          {"A": 1300, "B": 250, "C": 250})
    multi("Pause mens to ture kører", {"A": ("08:00", "10:00"), "B": ("08:00", "10:00")}, HR,
          "Hver tur får 60 min, heraf 15 min af pausen (30 min delt på to). 60 - 15 = 45 min.", {"A": 450, "B": 450},
          pauses=[("09:00", "09:30")])
    multi("Pause uden for turen", {"A": ("08:00", "10:00")}, HR, "Pausen 12:00-12:30 ligger ikke i turen og påvirker den ikke.",
          {"A": 1200}, pauses=[("12:00", "12:30")])
    tm = split({"A": ("08:00", "09:00"), "B": ("08:30", "09:00")})
    ex("Tillæg pr. time på en tur med fast pris", [FIX("Fast pris", 800), SUR("Kran", "other", 120, unit="per_hour")], A(),
       "Fast pris har ingen fakturerbar tid. Et kr/t-tillæg (ikke ventetid) bruger så turens tid efter deling "
       "- UDEN afrunding og UDEN pausefradrag: 45 min × 120/60 = 90. (Teksten viser \"45.0 min\".)", 890, time=tm["A"],
       extra_check=line_has("45.0 min"))

    section("B7. Pris pr. container og pr. enhed")
    ex("Pr. container, 3 containere", [PERC("Pr. container", 350)], A(containers=3), "3 × 350.", 1050)
    ex("Pr. container, ingen antal", [PERC("Pr. container", 350)], A(containers=0), "Mindst 1 container.", 350)
    U = lambda **kw: UNIT("Palletakst", 45, "paller", **kw)  # noqa: E731
    ex("Pr. enhed, planlagt antal", [U()], A(task_type="levering", units={"paller": 12}, units_source={"paller": "planlagt"}),
       "12 paller × 45. Uden registreret antal bruges det planlagte.", 540)
    ex("Pr. enhed, registreret antal", [U()], A(task_type="levering", units={"paller": 11}, units_source={"paller": "registreret"}),
       "Chaufføren registrerede 11 - det registrerede antal vinder over det planlagte.", 495)
    ex("Pr. enhed med minimumsbeløb", [U(min_amount=600)], A(task_type="levering", units={"paller": 12}, units_source={"paller": "planlagt"}),
       "540 løftes til 600.", 600, extra_check=line_has("Op til minimumsbeløb"))
    ex("Pr. enhed, turen har ikke enheden", [U(), W], A(task_type="levering", day_type="saturday", units={"kolli": 5}),
       "Reglen tæller paller, turen har kun kolli. \"Mangler antal\" - og så heller ingen tillæg.", None, status="missing_qty",
       extra_check=has_flag("Turen har intet antal i paller"))
    ex("Pr. enhed, enhedens navn skrevet anderledes", [UNIT("Palletakst", 45, "Paller ")], A(task_type="levering", units={"paller": 4}),
       "Enheden sammenlignes med små bogstaver og uden ekstra mellemrum.", 180)

    section("B8. Hængere")
    ex("Hængertillæg", [G, SUR("Hænger", "trailer", 300, {"trailer": "with"})], A(trailer=True, trailer_count=1), "1.000 + 300.", 1300)
    TR = [FIX("Uden hænger", 500, {"trailer": "without"}), FIX("1 hænger", 700, {"trailer_counts": [1]}),
          FIX("2 hængere", 1100, {"trailer_counts": [2]}), FIX("3+ hængere", 1500, {"trailer_counts": [3]})]
    ex("Pris efter antal hængere: 2", TR, A(trailer=True, trailer_count=2), "Kun \"2 hængere\" passer. 2 hængere koster ikke nødvendigvis det dobbelte.", 1100)
    ex("Pris efter antal hængere: 4", TR, A(trailer=True, trailer_count=4), "\"3+\" dækker 3 og derover.", 1500)
    ex("Pris efter antal hængere: 0", TR, A(), "Kun \"Uden hænger\" passer.", 500)
    ex("Antal hængere slår \"med hænger\"", [G, SUR("Hænger", "trailer", 300, {"trailer": "with"}),
                                            SUR("2 hængere", "trailer", 450, {"trailer_counts": [2]})], A(trailer=True, trailer_count=2),
       "Samme kategori. Antal (2 point) > med/uden (1 point).", 1450)

    section("B9. Ventetid", "Ventetid kommer fra turens godkendte rettelser (chaufførens anmodning, automatisk "
            "godkendelse eller admin). Uden ventetid ingen linje. Kr/t-ventetid afregnes pr. PÅBEGYNDT kvarter.")
    WT = lambda v=400, unit="per_hour": SUR("Ventetid", "waiting", v, unit=unit)  # noqa: E731
    ex("20 min ventetid", [G, WT()], A(waiting_min=20), "20 -> 30 min (påbegyndt kvarter). 400 × 30/60 = 200.", 1200)
    ex("15 min ventetid", [G, WT()], A(waiting_min=15), "Præcis ét kvarter.", 1100)
    ex("Ingen ventetid", [G, WT()], A(), "Ingen linje.", 1000)
    ex("Ventetid som fast beløb", [G, WT(150, "kr")], A(waiting_min=40), "Fast 150 kr når der er ventetid - uanset hvor lang.", 1150)
    ex("Ventetid i procent", [G, WT(10, "percent")], A(waiting_min=40), "10 % af grundprisen når der er ventetid.", 1100)
    ex("Aftalt pris + ventetid oveni", [G, WT()], A(waiting_min=25), "Aftalt 2.000. Ventetid 25 -> 30 min = 200 lægges oveni (valgt ved aftalen).",
       2200, override={"mode": "fixed", "amount": 2000, "label": "Aftalt pris", "add_waiting": True})
    ex("Aftalt pris uden ventetid oveni", [G, WT()], A(waiting_min=25), "Ventetiden er indregnet (0 kr).", 2000,
       override={"mode": "fixed", "amount": 2000, "label": "Aftalt pris", "add_waiting": False}, extra_check=line_has("indregnet"))
    ex("61 min ventetid", [G, WT()], A(waiting_min=61), "61 -> 75 min (5 påbegyndte kvarterer). 400 × 75/60 = 500.", 1500)

    section("B10. Ekstra stop", "En tur har som udgangspunkt 2 stop (afhentning + aflevering). Tillægget betales "
            "pr. stop ud over de inkluderede (standard 2).")
    ST = lambda inc=2: SUR("Ekstra stop", "stop", 150, included=inc)  # noqa: E731
    ex("4 stop, 2 inkluderet", [G, ST()], A(stops=4), "2 ekstra × 150.", 1300)
    ex("2 stop", [G, ST()], A(), "Ingen ekstra stop - ingen linje.", 1000)
    ex("3 stop, 1 inkluderet", [G, ST(1)], A(stops=3), "2 ekstra × 150.", 1300)

    section("B11. Aften/nat (tidsrum)", "Tidsrummet gælder turens STARTtidspunkt. Fra-tid er med, til-tid er ikke. "
            "Et tidsrum over midnat (18:00-06:00) er tilladt.")
    EV = SUR("Aftentillæg", "evening", 250, {"time_from": "18:00", "time_to": "06:00"})
    ex("Start 19:30", [G, EV], A(start="19:30"), "I tidsrummet.", 1250)
    ex("Start 06:00", [G, EV], A(start="06:00"), "06:00 er sluttiden og er ikke med.", 1000)
    ex("Start 05:59", [G, EV], A(start="05:59"), "Før 06:00 = med.", 1250)
    ex("Start 17:59", [G, EV], A(start="17:59"), "Før 18:00.", 1000)
    ex("Ingen starttid", [G, EV], A(start=""), "Uden starttid kan et tidsrum aldrig passe.", 1000)
    ex("Dagtidsrum 06-18, start 18:00", [G, SUR("Dagtillæg", "other", 100, {"time_from": "06:00", "time_to": "18:00"})], A(start="18:00"),
       "18:00 er sluttiden.", 1000)
    ex("Aftentillæg pr. time på timepris", [HOUR("Timepris", 600), SUR("Aften kr/t", "evening", 100, {"time_from": "18:00", "time_to": "06:00"}, unit="per_hour")],
       A(start="19:00"), "120 fakturerbare min: 1.200 + 100 × 2 = 1.400. Et kr/t-tillæg bruger de fakturerbare minutter.", 1400, time=T(120))

    section("B13. Materialer", "En GRUNDPRIS med materialer gælder kun, når ALLE turens materialer er nævnt. "
            "Et TILLÆG med materialer gælder, når ét af dem er på turen.")
    BET = FIX("Beton", 900, {"materials": ["Beton"]})
    ex("Blandet tur matcher ikke betonprisen", [BET], A(materials=["Beton", "Træ"], material="Beton + Træ"),
       "Turen har Beton + Træ. Betonprisen gælder kun rene betonture.", None, status="missing_rule",
       extra_check=lambda r: ("turen har Beton + Træ" in r["why"]["text"], r["why"]["text"]))
    ex("Blandet tur får den generelle pris", [BET, G], A(materials=["Beton", "Træ"], material="Beton + Træ"), "", 1000)
    ex("Regel for begge materialer", [FIX("Beton/Træ", 950, {"materials": ["Beton", "Træ"]})], A(materials=["Beton", "Træ"]),
       "Alle turens materialer er nævnt.", 950)
    ex("Regel for begge, tur med ét", [FIX("Beton/Træ", 950, {"materials": ["Beton", "Træ"]})], A(material="Beton"),
       "Beton er nævnt - det er nok.", 950)
    ex("Tillæg for ét af materialerne", [G, SUR("Betontillæg", "other", 200, {"materials": ["Beton"]})], A(materials=["Beton", "Træ"]),
       "Tillæg: ét materiale er nok.", 1200)
    ex("Store og små bogstaver", [FIX("pap", 800, {"materials": ["pap"]})], A(), "\"pap\" = \"Pap\".", 800)
    ex("Tur uden materiale", [FIX("Pap", 800, {"materials": ["Pap"]}), G], A(material=""), "En materialeregel kræver et materiale.", 1000)

    section("B14. Forgæves kørsel", "Almindelige regler gælder kun gennemførte ture. En forgæves tur skal have "
            "en regel med udfald \"forgæves\" (eller \"alle\").")
    ex("Forgæves uden forgæves-pris", [G], A(outcome="not_completed"), "", None, status="missing_rule",
       extra_check=lambda r: ("forgæves kørsel" in r["why"]["text"], r["why"]["text"]))
    ex("Forgæves-pris", [G, FIX("Forgæves kørsel", 400, {"outcome": "not_completed"})], A(outcome="not_completed"), "", 400)
    ex("Timepris for alle udfald", [HOUR("Timepris alle", 600, {"outcome": "any"})], A(outcome="not_completed"),
       "Tiden for en forgæves tur er fra \"På vej\" til den blev markeret forgæves.", 450, time=T(45))
    ex("Kundens forgæves-pris slår \"alle udfald\"", [FIX("Alle udfald", 700, {"outcome": "any"}),
                                                    FIX("HF forgæves", 450, {"customer_ids": ["HF"], "outcome": "not_completed"})],
       A(outcome="not_completed"), "65 > 1.", 450)
    ex("Prisaftalens tillæg gælder ikke forgæves ture", [FIX("HF forgæves", 400, {"customer_ids": ["HF"], "outcome": "not_completed"}),
                                                        SUR("Weekend HF", "weekend", 300, {"customer_ids": ["HF"], **WEEKEND})],
       A(outcome="not_completed", day_type="saturday"),
       "Tillæg i en prisaftale har udfald \"gennemført\". En forgæves lørdagstur får kun forgæves-prisen.", 400)
    ex("Tillæg der også gælder forgæves", [FIX("Forgæves", 450, {"outcome": "not_completed"}),
                                           SUR("Helligdag (alle udfald)", "holiday", 800, {"day_types": ["holiday"], "outcome": "any"})],
       A(outcome="not_completed", day_type="holiday"), "Vil man have tillæg på forgæves ture, skal tillægget have udfald \"alle\".", 1250)

    section("B15. Aftalt pris, manuel pris og ekstra linjer")
    AG = {"mode": "fixed", "amount": 2400, "label": "Aftalt pris"}
    ex("Aftalt pris erstatter reglerne", [G, W], A(day_type="saturday"), "Weekend vises som indregnet (0 kr).", 2400, override=AG,
       extra_check=line_has("indregnet"))
    ex("Aftalt pris uden regler", [], A(), "En aftalt pris virker også uden prisregler.", 2400, override=AG, status="missing_rule")
    ex("Manuel pris + ekstra linje", [G], A(), "1.500 + 300.", 1800,
       override={"mode": "fixed", "amount": 1500, "extra_lines": [{"label": "Ekstra rengøring", "amount": 300}]})
    ex("Reglernes pris + ekstra linje", [G], A(), "1.000 + 300. Ekstra linjer kan bruges uden at overstyre prisen.", 1300,
       override={"mode": "rules", "extra_lines": [{"label": "Ekstra rengøring", "amount": 300}]})
    ex("Ekstra linje redder ikke en manglende pris", [], A(), "Mangler grundprisen, er der stadig ingen total.", None, status="missing_rule",
       override={"mode": "rules", "extra_lines": [{"label": "Ekstra rengøring", "amount": 300}]})
    ex("Manuel pris på en timepris-tur uden tid", [HOUR("Timepris", 600)], A(), "Den manuelle pris gælder; \"Mangler tid\" forsvinder.",
       1500, override={"mode": "fixed", "amount": 1500}, status="missing_time",
       extra_check=lambda r: (r["flags"] == ["Manuel pris"], str(r["flags"])))
    ex("Aftalt pris + ventetid + ekstra linje", [G, WT()], A(waiting_min=25), "2.000 + 200 (ventetid 30 min) + 350.", 2550,
       override={"mode": "fixed", "amount": 2000, "label": "Aftalt pris", "add_waiting": True,
                 "extra_lines": [{"label": "Færge", "amount": 350}]})

    section("B19. Samlede eksempler (mange regler på én gang)")
    ex("HF lørdag, haster, 2 hængere, ventetid, timepris",
       [HOUR("HF timepris", 650, {"customer_ids": ["HF"]}, start_fee=250, rounding_mode="up", rounding_minutes=15),
        SUR("Weekend HF 20 %", "weekend", 20, {"customer_ids": ["HF"], **WEEKEND}, unit="percent"),
        SUR("Haster", "haster", 300, {"priorities": ["haster"]}), SUR("2 hængere", "trailer", 400, {"trailer_counts": [2]}),
        SUR("Ventetid", "waiting", 450, unit="per_hour")],
       A(day_type="saturday", priority="haster", trailer=True, trailer_count=2, waiting_min=25, start="07:00"),
       "128 -> 135 min. 650 × 135/60 = 1.462,50 + startgebyr 250 = 1.712,50. Weekend 20 % = 342,50. Haster 300. "
       "Hænger 400. Ventetid 25 -> 30 min × 450/60 = 225. I alt 2.980.", 2980, time=T(128))
    ex("Varelevering pr. palle med stop, aften og ventetid",
       [UNIT("Palletakst", 45, "paller", min_amount=600), SUR("Ekstra stop", "stop", 175, included=2),
        SUR("Aften 15 %", "evening", 15, {"time_from": "18:00", "time_to": "06:00"}, unit="percent"), SUR("Ventetid", "waiting", 400, unit="per_hour")],
       A(task_type="levering", units={"paller": 18}, units_source={"paller": "registreret"}, stops=4, start="18:30", waiting_min=10),
       "18 × 45 = 810 (over minimum). 2 ekstra stop = 350. Aften 15 % af 810 = 121,50. Ventetid 10 -> 15 min = 100. I alt 1.381,50.", 1381.5)
    ex("Forgæves på en helligdag", [G, FIX("Forgæves", 450, {"outcome": "not_completed"}), SUR("Helligdag", "holiday", 800, {"day_types": ["holiday"]})],
       A(outcome="not_completed", day_type="holiday"), "Helligdagstillægget har udfald \"gennemført\" og gælder ikke.", 450)
    ex("Nærmeste regel i forklaringen", [FIX("HF Pap", 900, {"customer_ids": ["HF"], "materials": ["Pap"]}),
                                         FIX("ARGO 1101 Plast", 950, {"customer_ids": ["ARGO"], "location_codes": ["1101"], "materials": ["Plast"]})],
       A(customer_id="ARGO", location_code="1102"),
       "\"HF Pap\" fejler kun på kunde (1 betingelse), \"ARGO 1101 Plast\" på lokation og materiale (2). "
       "Forklaringen viser reglen med færrest fejl.", None, status="missing_rule",
       extra_check=lambda r: (r["why"]["rule"] == "HF Pap", r["why"]["text"]))
    ex("Lige mange fejl: den mest specifikke vises", [FIX("Lokation 1102", 900, {"location_codes": ["1102"]}), FIX("ARGO", 950, {"customer_ids": ["ARGO"]})],
       A(), "Begge fejler på én betingelse; ARGO (64) foretrækkes frem for lokation (32).", None, status="missing_rule",
       extra_check=lambda r: (r["why"]["rule"] == "ARGO", r["why"]["text"]))


# ----------------------------------------------------------------------------- serverens dele
def run_server_examples():
    section("B12. Dagtyper og helligdage")
    h = P.danish_holidays(2026, P.DEFAULT_OPTIONAL)
    rows = "\n".join(f"| {d} | {n} |" for d, n in h.items())
    note("Helligdage 2026 i logistikfirmaets egen kalender (standard)",
         "Officielle danske helligdage beregnes for ethvert år (påskeformlen). Standard-tilvalg: Grundlovsdag, "
         "Juleaften, Nytårsaftensdag. 1. maj kan vælges til. Store bededag findes ikke (afskaffet fra 2024).\n\n"
         "| Dato | Navn |\n|---|---|\n" + rows,
         ok=len(h) == 13 and "2026-04-05" in h and "2026-05-01" not in h, msg=str(h))
    hs = set(h)
    cases = [("2026-10-20", "weekday"), ("2026-10-24", "saturday"), ("2026-10-25", "sunday"), ("2026-12-26", "holiday"),
             ("2026-06-05", "holiday"), ("2026-05-01", "weekday"), ("2026-12-24", "holiday")]
    got = [(d, P.day_type(d, hs)) for d, _t in cases]
    note("Dagtype for udvalgte datoer",
         "| Dato | Dagtype |\n|---|---|\n" + "\n".join(f"| {d} | {P.DAY_TYPES[t]} |" for d, t in got) +
         "\n\nEn helligdag er altid \"Helligdag\", også på en lørdag eller søndag (26.12.2026 er en lørdag).",
         ok=got == cases, msg=str(got))
    own = P.own_holidays(2026, {"holiday_optional": P.DEFAULT_OPTIONAL, "holiday_excluded": ["2026-12-24"],
                                "holiday_extra": [{"date": "2026-08-14", "name": "Firmafest"}]})
    note("Egen kalender: fravalgt juleaften, tilføjet firmafest",
         "Indstillinger: fravalg 24.12.2026, ekstra fridag 14.08.2026 \"Firmafest\". Resultat: 24.12 er en "
         "almindelig torsdag, 14.08 er en helligdag (helligdagstillæg gælder).",
         ok="2026-12-24" not in own and own.get("2026-08-14") == "Firmafest", msg=str(own))

    settings = {**S._PRICE_SETTINGS_DEFAULT}

    def ctx_for(settings_=None, rules=()):
        ctx = S._PricingContext("LOGI", settings_ or settings, list(rules))
        ctx.plads_by_name = {"Genbrugsplads Nord": {"name": "Genbrugsplads Nord", "location_code": "1101", "company_id": "HF"}}
        ctx.customers = {"HF": {"id": "HF", "name": "Helsingør Forsyning", "holiday_group_id": ""}}
        return ctx

    base_tour = {"id": "t1", "company_id": "HF", "plads": "Genbrugsplads Nord", "fraction": "Pap", "tour_type": "normal",
                 "priority": "normal", "date": "2026-06-05", "created_at": "2026-06-01T08:00:00+00:00"}
    c1 = ctx_for()
    c1.cal_days = {"cal1": {"2026-12-25": "1. juledag", "2026-12-26": "2. juledag"}}
    c1.loc_active_cals = {"1101": ["cal1"]}
    hol, src = c1.holidays_for(base_tour, "2026-06-05")
    dt = P.day_type("2026-06-05", hol)
    note("Lokationens kalender bruges i stedet for den egne",
         "Indstilling \"Brug kundens helligdage først\" (standard). Lokation 1101 har en aktiv helligdagskalender "
         "for 2026 med kun juledagene. Tur 05.06.2026 (Grundlovsdag): kalenderen kommer fra "
         f"\"{src}\", og dagtypen er **{P.DAY_TYPES[dt]}**. Den egne kalender (som har Grundlovsdag) bruges IKKE "
         "- den er kun reserve, når kunden ingen kalender har. Helligdagstillæg gælder derfor ikke.",
         ok=src == "Lokationens helligdagskalender" and dt == "weekday", msg=f"{src} {dt}")
    c2 = ctx_for()
    c2.cal_days = {"cal1": {"2026-12-25": "1. juledag"}, "calPap": {"2026-06-05": "Grundlovsdag"}}
    c2.loc_active_cals = {"1101": ["cal1"]}
    c2.mat_cal = {("1101", "Pap"): "calPap"}
    d_pap = P.day_type("2026-06-05", c2.holidays_for(base_tour, "2026-06-05")[0])
    d_pl = P.day_type("2026-06-05", c2.holidays_for({**base_tour, "fraction": "Plast"}, "2026-06-05")[0])
    note("Materialets kalender går forud for lokationens",
         "Pap på lokation 1101 har sin egen helligdagskalender (samme som bestillingssiden bruger), hvor 05.06 er "
         f"fridag. Plast bruger lokationens aktive kalender. 05.06.2026: Pap = **{P.DAY_TYPES[d_pap]}**, Plast = **{P.DAY_TYPES[d_pl]}**.",
         ok=d_pap == "holiday" and d_pl == "weekday", msg=f"{d_pap} {d_pl}")
    c3 = ctx_for()
    c3.customers = {"HF": {"id": "HF", "name": "Helsingør Forsyning", "holiday_group_id": "g1"}}
    c3.groups = {"g1": {"2026-06-05": "Grundlovsdag"}}
    hol3, src3 = c3.holidays_for(base_tour, "2026-06-05")
    note("Kundens helligdagsgruppe når lokationen ingen kalender har",
         f"Ingen kalender på lokationen. HF er i en helligdagsgruppe med 05.06. Kilde: \"{src3}\", dagtype **{P.DAY_TYPES[P.day_type('2026-06-05', hol3)]}**.",
         ok=src3 == "Kundens helligdagsgruppe" and "2026-06-05" in hol3, msg=src3)
    c4 = ctx_for({**settings, "holiday_source": "own"})
    c4.cal_days, c4.loc_active_cals = c1.cal_days, c1.loc_active_cals
    hol4, src4 = c4.holidays_for(base_tour, "2026-06-05")
    rules = [FIX("Standardpris", 1000), SUR("Helligdag", "holiday", 800, {"day_types": ["holiday"]})]
    p1 = P.price_tour({**A(), "day_type": P.day_type("2026-06-05", hol)}, rules, None)["total"]
    p4 = P.price_tour({**A(), "day_type": P.day_type("2026-06-05", hol4)}, rules, None)["total"]
    note("Indstillingen \"Brug egen kalender\"",
         f"Med indstillingen \"own\" bruges altid logistikfirmaets egen kalender (kilde: \"{src4}\"). Samme tur "
         f"05.06.2026 med reglerne Standardpris 1.000 + Helligdag 800: med kundens kalender {kr(p1)}, med egen kalender {kr(p4)}.",
         ok=src4 == "Egen helligdagskalender" and p1 == 1000 and p4 == 1800, msg=f"{src4} {p1} {p4}")

    section("B7b. Hvad turen tæller som (containere, enheder, stop)")
    c5 = ctx_for()
    t5 = {**base_tour, "date": "2026-10-20", "tour_kind": "container",
          "cargo_lines": [{"text": "Pap", "qty": 1, "unit": ""}, {"text": "Plast", "qty": 3, "unit": "stk"}]}
    a5 = c5.attrs(t5)
    r5 = P.price_tour(a5, [PERC("Pr. container", 350)], None)
    note("Containertur med to indholdslinjer",
         "Linjer: \"Pap\" (ingen enhed) og \"Plast\" 3 stk. En linje tæller som 1 container, men en linje i "
         f"stk/containere tæller sit antal: 1 + 3 = **{a5['containers']}** containere. Med 350 kr pr. container: {kr(r5['total'])}. "
         f"Materialerne er {' + '.join(a5['materials'])}.",
         ok=a5["containers"] == 4 and r5["total"] == 1400 and a5["materials"] == ["Pap", "Plast"], msg=str(a5["containers"]))
    t6 = {**base_tour, "date": "2026-10-20", "tour_kind": "goods", "company_id": "LOGI", "private_company": "Byg ApS", "plads": "",
          "cargo_lines": [{"text": "Køkken", "qty": 5, "unit": "paller", "actual_qty": 6}, {"text": "Bad", "qty": 7, "unit": "Paller"}]}
    a6 = c5.attrs(t6)
    r6 = P.price_tour(a6, [UNIT("Palletakst", 45, "paller")], None)
    note("Varetur: samme enhed på to linjer, kun den ene registreret",
         f"Køkken: planlagt 5, registreret 6. Bad: planlagt 7 (enheden stavet \"Paller\"). Antal paller = 6 + 7 = "
         f"**{tal(a6['units']['paller'])}**, kilde \"{a6['units_source']['paller']}\". 45 kr pr. palle: {kr(r6['total'])}.",
         ok=a6["units"]["paller"] == 13 and a6["units_source"]["paller"] == "delvist registreret" and r6["total"] == 585,
         msg=str(a6["units"]))
    a7 = c5.attrs({**base_tour, "date": "2026-10-20"})
    stops = [{"kind": "pickup"}, {"kind": "delivery"}, {"kind": "delivery", "added_by_driver": True}]
    a8 = c5.attrs({**base_tour, "date": "2026-10-20", "stops": stops})
    a9 = c5.attrs({**base_tour, "date": "2026-10-20", "stops": [*stops[:2], {**stops[2], "approved": True}]})
    note("Antal stop",
         f"Tur uden stop-liste = **{a7['stops']}** stop (afhentning + aflevering). Tre stop, hvor chaufføren selv har "
         f"tilføjet det tredje og planlæggeren ikke har godkendt det = **{a8['stops']}**. Når det er godkendt = **{a9['stops']}**.",
         ok=(a7["stops"], a8["stops"], a9["stops"]) == (2, 2, 3), msg=str((a7["stops"], a8["stops"], a9["stops"])))

    section("B8b. Hvor antallet af hængere kommer fra")
    cases = [
        ("Godkendt rettelse \"0 hængere\", chaufføren sagde 2, planlagt 2", {"fact_overrides": {"trailer_count": 0}, "trailer_count_actual": 2, "trailer_count": 2}, 0, "approved"),
        ("Ældre godkendt \"med hænger\", intet antal, intet planlagt", {"fact_overrides": {"used_trailer": True}}, 1, "approved"),
        ("Chaufføren oplyste 1, planlagt 2", {"trailer_count_actual": 1, "trailer_count": 2}, 1, "driver"),
        ("Kun planlagt 2", {"trailer_count": 2}, 2, "planned"),
        ("Automatisk forslag fra chaufførens profil", {"used_trailer": True, "trailer_source": "auto", "trailer_confirmed": False}, 1, "auto"),
        ("Intet", {}, 0, ""),
    ]
    rows, ok = [], True
    for label, t, n, src in cases:
        ti = S._trailer_info(t)
        ok = ok and ti["count"] == n and ti["source"] == src
        src_da = {"approved": "godkendt/rettet", "driver": "chaufføren", "planned": "planlagt", "auto": "automatisk"}.get(ti["source"], "-")
        rows.append(f"| {label} | {ti['count']} | {src_da} | {'ja' if ti['confirmed'] else 'NEJ'} |")
    note("Rækkefølgen for hængere",
         "Godkendt/admin-rettet antal > ældre godkendt ja/nej > chaufførens oplyste antal > planlagt antal > ja/nej på turen.\n\n"
         "| Situation | Antal i prisen | Kilde | Bekræftet |\n|---|---|---|---|\n" + "\n".join(rows) +
         "\n\nEt automatisk forslag prissættes med hænger, men turen får markeringen \"Hænger: automatisk, ikke bekræftet\".",
         ok=ok, msg="\n".join(rows))
    c6 = ctx_for(rules=[FIX("Standardpris", 1000), SUR("Hænger", "trailer", 300, {"trailer": "with"})])
    r6 = c6.price({**base_tour, "date": "2026-10-20", "used_trailer": True, "trailer_source": "auto", "trailer_confirmed": False})
    note("Automatisk hænger i prisen", f"Standardpris 1.000 + hængertillæg 300 = {kr(r6['total'])}. Markeringer: {'; '.join(r6['flags'])}.",
         ok=r6["total"] == 1300 and "Hænger: automatisk, ikke bekræftet" in r6["flags"], msg=str(r6))

    section("B16. Versioner, gyldighed og fakturering",
            "To forskellige ting: VERSION afgøres af hvornår turen blev OPRETTET/bestilt (`created_at`). "
            "GYLDIGHED (kørselsdato fra/til) afgøres af hvornår turen blev KØRT.")
    vt = "2026-10-01T10:00:00+02:00"
    pts = [("2026-09-30T12:00:00+02:00", False), ("2026-10-01T10:00:00+02:00", True), ("2026-11-01T08:00:00+01:00", True)]
    r_new = {"version_from": vt}
    r_old = {"version_to": vt}
    rows, ok = [], True
    for ref, exp in pts:
        a_new = S._rule_active_at(r_new, S._parse_ts(ref))
        a_old = S._rule_active_at(r_old, S._parse_ts(ref))
        ok = ok and a_new == exp and a_old == (not exp)
        rows.append(f"| {ref} | {'ja' if a_old else 'nej'} | {'ja' if a_new else 'nej'} |")
    note("Hvilken version gælder for en tur",
         f"Prisen blev rettet {vt} (\"Nye ture fra nu\"). Den gamle version lukkes på tidspunktet, den nye starter "
         "samme tidspunkt. Fra-tidspunktet er med, til-tidspunktet er ikke.\n\n"
         "| Turen oprettet | Gammel version gælder | Ny version gælder |\n|---|---|---|\n" + "\n".join(rows),
         ok=ok, msg="\n".join(rows))
    v1 = FIX("HF-pris", 900, version_to=vt)
    v2 = FIX("HF-pris", 1000, version_from=vt)
    c7 = ctx_for(rules=[v1, v2])
    tA = {**base_tour, "id": "tA", "date": "2026-10-20", "created_at": "2026-09-28T09:00:00+00:00"}
    tB = {**base_tour, "id": "tB", "date": "2026-10-20", "created_at": "2026-10-02T09:00:00+00:00"}
    pA, pB = c7.price(tA)["total"], c7.price(tB)["total"]
    note("Prisstigning \"Nye ture fra nu\"",
         "v1 900 kr gælder ture oprettet før 01.10.2026 kl. 10, v2 1.000 kr ture oprettet derefter. Begge ture "
         f"køres 20.10.2026. Tur oprettet 28.09: **{kr(pA)}**. Tur oprettet 02.10: **{kr(pB)}**. En prisændring "
         "ændrer altså ikke prisen på ture, der allerede var bestilt.", ok=(pA, pB) == (900, 1000), msg=f"{pA} {pB}")
    jan = S._effective_ts("2027-01-01")
    c8 = ctx_for(rules=[FIX("HF-pris", 900, version_to=jan), FIX("HF-pris", 1000, version_from=jan)])
    pC = c8.price({**base_tour, "id": "tC", "date": "2027-01-05", "created_at": "2026-12-30T09:00:00+00:00"})["total"]
    note("\"Fra en dato\" følger oprettelsen, ikke kørslen",
         f"Ny pris \"fra 01.01.2027\" (versionen starter {jan}). En tur oprettet 30.12.2026 og kørt 05.01.2027 "
         f"får **{kr(pC)}** - den gamle pris, fordi den blev oprettet før. Skal prisen følge KØRSELSDATOEN, bruges "
         "\"Ture kørt fra en dato\" (næste eksempel).", ok=pC == 900, msg=str(pC))
    c9 = ctx_for(rules=[FIX("HF 2026", 900, valid_to="2026-12-31"), FIX("HF 2027", 1000, valid_from="2027-01-01")])
    pD = c9.price({**base_tour, "id": "tD", "date": "2027-01-05", "created_at": "2026-12-30T09:00:00+00:00"})["total"]
    pE = c9.price({**base_tour, "id": "tE", "date": "2026-12-30", "created_at": "2026-12-01T09:00:00+00:00"})["total"]
    note("\"Ture kørt fra en dato\"",
         "Den gamle aftale får kørselsdato til 31.12.2026, en ny aftale gælder ture kørt fra 01.01.2027 - også ture der "
         f"allerede er oprettet (fx en serie). Tur oprettet 30.12, kørt 05.01.2027: **{kr(pD)}**. Tur kørt 30.12.2026: **{kr(pE)}**.",
         ok=(pD, pE) == (1000, 900), msg=f"{pD} {pE}")
    late = FIX("Ny aftale", 800, version_from="2026-10-15T10:00:00+02:00", backfill_unpriced=True)
    c10 = ctx_for(rules=[late])
    tF = {**base_tour, "id": "tF", "date": "2026-09-10", "created_at": "2026-09-01T09:00:00+00:00"}
    rF = c10.price(tF)
    c11 = ctx_for(rules=[late, FIX("Standardpris", 1000)])
    rG = c11.price(tF)
    note("\"Nye + ture uden pris\" (standard for nye prisaftaler)",
         f"En aftale oprettet 15.10 med dette valg gælder ture oprettet senere OG ældre ture, der ellers ingen pris har. "
         f"Ældre tur uden pris: **{kr(rF['total'])}** med markeringen \"{rF['flags'][-1] if rF['flags'] else ''}\". "
         f"Samme tur, når den allerede havde en standardpris: **{kr(rG['total'])}** - en tur med pris ændres aldrig.",
         ok=rF["total"] == 800 and rG["total"] == 1000 and any("oprettet efter turen" in f for f in rF["flags"]), msg=f"{rF} {rG}")
    locked = {"status": "ok", "model": "fixed", "total": 950.0, "lines": [{"type": "base", "label": "HF-pris", "amount": 950.0}], "flags": []}
    rH = ctx_for(rules=[FIX("HF-pris", 1200)]).price({**base_tour, "id": "tH", "price_locked": locked})
    note("Faktureret tur er frosset",
         f"Turen blev faktureret til 950 kr. Reglen er siden sat op til 1.200. Turen viser stadig **{kr(rH['total'])}** "
         f"med markeringen \"{rH['flags'][-1]}\". Skal den ændres, fjernes markeringen \"faktureret\" først.",
         ok=rH["total"] == 950 and rH["flags"][-1] == "Faktureret", msg=str(rH))
    rI = ctx_for(rules=[v1, v2]).price({**base_tour, "id": "tI", "date": "2026-10-20", "created_at": ""})
    note("Tur uden oprettelsestidspunkt",
         f"Mangler `created_at` (meget gamle ture), bruges kørselsdatoen som oprettelse: 20.10.2026 -> ny version, **{kr(rI['total'])}**.",
         ok=rI["total"] == 1000, msg=str(rI["total"]))
    nums = ["1.000", "1.000,50", "1000,5", "1100.5", "12.500", "1.5", "2 500 kr", "15%"]
    vals = [S._parse_dk_number(x) for x in nums]
    note("Danske tal i beløbsfelterne",
         "| Indtastet | Læses som |\n|---|---|\n" + "\n".join(f"| `{a}` | {tal(b)} |" for a, b in zip(nums, vals)) +
         "\n\n\"1.000\" er tusind (dansk tusindtalsseparator), mens \"1.5\" er halvanden.",
         ok=vals == [1000, 1000.5, 1000.5, 1100.5, 12500, 1.5, 2500, 15], msg=str(vals))

    section("B17. Kørselsdato (hvilken dag tæller)", "Kørselsdatoen styrer dagtype (weekend/helligdag), "
            "kørselsdato-gyldighed og hvilken periode turen står i i Rapport.")
    sd_cases = [
        ("Startet lørdag 23:00 (på vej-tidsstempel), afsluttet søndag", {"completed": True, "on_way_at": "2026-10-24T21:00:00+00:00", "completed_at": "2026-10-25T00:30:00+00:00"}, "2026-10-24"),
        ("Ældre tur uden på vej-tidsstempel: start 23:00, slut 02:15 søndag", {"completed": True, "completed_at": "2026-10-25T00:15:00+00:00", "on_way_time": "23:00", "time": "02:15"}, "2026-10-24"),
        ("Afsluttet 00:30 dansk tid (22:30 UTC dagen før), startet 23:30", {"completed": True, "completed_at": "2026-10-20T22:30:00+00:00", "on_way_time": "23:30", "time": "00:30"}, "2026-10-20"),
        ("Forgæves", {"not_completed": True, "not_completed_at": "2026-10-20T08:00:00+00:00", "date": "2026-10-19"}, "2026-10-20"),
        ("Ikke kørt endnu", {"date": "2026-11-02"}, "2026-11-02"),
    ]
    rows, ok = [], True
    for label, t, exp in sd_cases:
        got = S._service_date(t)
        ok = ok and got == exp
        rows.append(f"| {label} | {got} |")
    note("Kørselsdato i forskellige situationer",
         "Kørselsdatoen er den dag turen blev STARTET (dansk tid). Uden starttidsstempel regnes den ud fra "
         "afslutningen; er sluttiden før starttiden, startede turen dagen før.\n\n"
         "| Situation | Kørselsdato |\n|---|---|\n" + "\n".join(rows), ok=ok, msg="\n".join(rows))
    c12 = ctx_for(rules=[FIX("Standardpris", 1000), SUR("Søndagstillæg", "weekend", 600, {"day_types": ["sunday"]})])
    rS = c12.price({**base_tour, "id": "tS", "date": "2026-10-24", "completed": True, "on_way_at": "2026-10-24T21:00:00+00:00",
                    "completed_at": "2026-10-25T00:30:00+00:00", "on_way_time": "23:00", "time": "01:30"})
    note("Lørdagstur der først blev afsluttet søndag",
         f"Reglerne: Standardpris 1.000 + søndagstillæg 600. Turen startede lørdag 23:00 og sluttede søndag 01:30. "
         f"Pris: **{kr(rS['total'])}** - lørdag, intet søndagstillæg.", ok=rS["total"] == 1000, msg=str(rS))
    st, en = S._tour_times({"on_way_time": "09:10", "not_completed": True, "not_completed_at": "2026-10-20T07:55:00+00:00"})
    note("Tid på en forgæves tur", f"På vej kl. 09:10, markeret forgæves 07:55 UTC = 09:55 dansk tid. Tid: {st}-{en} = 45 min.",
         ok=(st, en) == ("09:10", "09:55"), msg=f"{st} {en}")

    section("B18. Hvem er kunden (prisnøglen)")
    c13 = ctx_for()
    c13.registry = {"c1": "Byg A/S"}
    keys = [("Tur på HF's genbrugsplads (B2B)", {"company_id": "HF"}, "HF"),
            ("Egen tur med firmanavn \"Byg ApS\"", {"company_id": "LOGI", "private_company": "Byg  ApS"}, "firma:byg aps"),
            ("Egen tur valgt fra kunderegistret (navn \"Byg A/S\")", {"company_id": "LOGI", "private_company": "Byg", "customer_ref_id": "c1"}, "firma:byg a/s"),
            ("Egen tur uden kunde", {"company_id": "LOGI"}, "LOGI")]
    rows, ok = [], True
    for label, t, exp in keys:
        got = c13.customer_key(t)
        ok = ok and got == exp
        rows.append(f"| {label} | `{got}` |")
    note("Prisnøglen for kunden",
         "Logistikfirmaet hedder her `LOGI`. En kunde-betingelse i en prisregel matcher denne nøgle.\n\n"
         "| Tur | Kundenøgle |\n|---|---|\n" + "\n".join(rows) +
         "\n\nNavne gøres til små bogstaver med enkelte mellemrum, så \"Byg  ApS\" og \"byg aps\" er samme kunde. "
         "Et navn fra kunderegistret vinder over teksten på turen.", ok=ok, msg="\n".join(rows))

    section("B20. Prisaftaler (sådan gemmes en aftale)")
    body = {"name": "HF aftale", "conditions": {"customer_ids": ["HF"]}, "base": {"pricing": {"model": "fixed", "amount": "1.200"}},
            "failed": {"amount": "400"},
            "surcharges": [{"category": "weekend", "unit": "kr", "value": "300"}, {"category": "evening", "unit": "kr", "value": "250"},
                           {"category": "trailer", "unit": "kr", "value": "350", "trailer_counts": [2]},
                           {"category": "stop", "value": "150", "included": 2}]}
    cleaned = [S._clean_rule(r) for r in S._bundle_rule_bodies(body)]
    rows = "\n".join(f"| {c['name']} | {'grundpris' if c['kind'] == 'base' else 'tillæg'} | {cond_text(c['conditions'])} | {P.specificity(c)} |" for c in cleaned)
    specs = [P.specificity(c) for c in cleaned]
    dup_err = ""
    try:
        S._bundle_rule_bodies({**body, "surcharges": [{"category": "weekend", "value": 1}, {"category": "weekend", "value": 2}]})
    except Exception as e:  # noqa: BLE001
        dup_err = getattr(e, "detail", str(e))
    note("En prisaftale bliver til flere regler",
         "Aftalen \"HF aftale\" (kunde HF): grundpris 1.200, forgæves 400, weekend 300, aften 250, 2 hængere 350, "
         "ekstra stop 150. Hvert tillæg får aftalens betingelser + sin egen situation automatisk:\n\n"
         "| Regel | Type | Gælder | Specificitet |\n|---|---|---|---|\n" + rows +
         f"\n\nSamme tillægstype to gange i én aftale afvises (\"{dup_err}\").",
         ok=specs == [64, 65, 65, 65, 66, 64] and "to gange" in dup_err, msg=f"{specs} {dup_err}")


async def run_db_examples():
    """Kører serverens egen tidsberegning (læser kun - chaufføren findes ikke i databasen)."""
    section("B5b. Serverens tidsberegning")
    settings = {**S._PRICE_SETTINGS_DEFAULT}
    rules = [HOUR("Timepris", 600)]
    ctx = S._PricingContext("LOGI", settings, rules)
    ctx.plads_by_name = {"Genbrugsplads Nord": {"name": "Genbrugsplads Nord", "location_code": "1101", "company_id": "HF"}}
    base = {"company_id": "HF", "plads": "Genbrugsplads Nord", "fraction": "Pap", "claimed_by_id": "eksempel-chauffoer",
            "completed": True, "date": "2026-10-20", "created_at": "2026-10-19T08:00:00+00:00"}
    t1 = {**base, "id": "x1", "on_way_at": "2026-10-20T20:30:00+00:00", "completed_at": "2026-10-20T23:15:00+00:00",
          "on_way_time": "22:30", "time": "01:15"}
    t2 = {**base, "id": "x2", "on_way_at": "2026-10-20T08:00:00+00:00", "completed_at": "2026-10-20T08:00:30+00:00",
          "on_way_time": "10:00", "time": "10:00"}
    await ctx._load_times([t1, t2])
    r1, r2 = ctx.price(t1), ctx.price(t2)
    note("Over midnat i serveren", f"På vej 22:30, afsluttet 01:15: {tal(ctx.time_by_tour.get('x1', {}).get('total') or 0)} min -> {kr(r1['total'])}.",
         ok=r1["total"] == 1650, msg=str(r1))
    note("Start og slut i samme minut (rettet 20.10.2026)",
         f"Start 10:00, slut 10:00. Før blev det regnet som et helt døgn (24 timer × 600 = 14.400 kr). Nu: "
         f"\"{'Mangler tid' if r2['total'] is None else kr(r2['total'])}\" med markeringen \"{'; '.join(r2['flags'])}\", "
         "så tiden rettes før fakturering.",
         ok=r2["total"] is None and r2["flags"] == ["Start og slut er samme minut - ret tiden"], msg=str(r2))


def main():
    run_engine_examples()
    run_server_examples()
    asyncio.run(run_db_examples())
    vat_net = 10000.0
    section("B21. Moms")
    note("Moms i Rapport", f"Alle priser er ekskl. moms. Rapporten lægger moms på summen: netto {kr(vat_net)} + "
         f"25 % moms {kr(vat_net * 0.25)} = {kr(vat_net * 1.25)}. Momssatsen kan ændres under Indstillinger.",
         ok=round(vat_net * 0.25, 2) == 2500, msg="moms")
    if FAILS:
        sys.stderr.write("FEJL:\n" + "\n".join(FAILS) + "\n")
        sys.exit(1)
    import re as _re

    def order(title):
        m = _re.match(r"B(\d+)([a-z]?)", title)
        return (int(m.group(1)), m.group(2)) if m else (999, title)
    n = [0]

    def num(_m):
        n[0] += 1
        return f"E{n[0]}."
    text = "\n".join("\n".join(SECTIONS[t]) for t in sorted(SECTIONS, key=order))
    text = _re.sub(r"E§\.", num, text)
    print(f"<!-- Genereret af scripts/prisberegning_eksempler.py - {COUNT[0]} eksempler, alle kontrolleret mod prismotoren -->")
    print(text)
    sys.stderr.write(f"{COUNT[0]} eksempler OK\n")


main()
