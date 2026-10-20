import React, { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  ChevronLeft, ChevronRight, MessageCircle, Search, X, Navigation, ChevronDown, Check, Building2, Truck, Loader2, MapPin,
  CheckCircle2, Inbox, Clock,
} from "lucide-react";
import DriverTourCard, { legsOf, LegLine } from "./DriverTourCard";
import { isHaster, openHours, todayStr } from "../lib/tourHelpers";

/**
 * Chaufførens TURE-fane (2026-10-17, ny opbygning).
 *
 * Før: hero med ring + 3 statistikkort + fremskridtskort (samme tal tre
 * gange), "Mine ture / Lokation"-vælger, en skjult "Afventende"-knap og en
 * liste der kun viste ledige ture når man havde valgt en plads.
 *
 * Nu - tre spørgsmål chaufføren stiller sig:
 *   Mine     - hvad skal JEG køre? (tildelt mig / taget af mig)
 *   Ledige   - hvad kan jeg tage? (grupperet pr. lokation, inkl. ture fra
 *              tidligere dage der aldrig blev kørt)
 *   Færdige  - hvad har jeg kørt i dag? (ret vægt herfra)
 * En tur der er i gang ligger altid øverst med en stor "Afslut"-knap.
 *
 * 2026-10-20: Kompakte rækker i stedet for store kort, grupperet pr. plads.
 * En hængerkørsel (flere containere på én gang) står samlet med Bil/Hænger.
 */
const fmtKg = (kg) => (kg >= 1000 ? `${(kg / 1000).toLocaleString("da-DK", { maximumFractionDigits: 1 })} t` : `${Math.round(kg)} kg`);
const fmtDate = (d) => {
  try {
    const t = todayStr();
    if (d === t) return "I dag";
    return new Date(`${d}T12:00:00`).toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" });
  } catch (_) { return d; }
};

function sortOpen(a, b, routeInfo) {
  const ra = routeInfo(a.id)?.route_order, rb = routeInfo(b.id)?.route_order;
  if ((a.on_way ? 1 : 0) !== (b.on_way ? 1 : 0)) return a.on_way ? -1 : 1;
  if (isHaster(a) !== isHaster(b)) return isHaster(a) ? -1 : 1;
  if (ra != null && rb != null && ra !== rb) return ra - rb;
  const oa = openHours(a).to || "99", ob = openHours(b).to || "99";
  if (oa !== ob) return String(oa).padStart(5, "0").localeCompare(String(ob).padStart(5, "0"));
  return (a.sort_order || 0) - (b.sort_order || 0);
}

function Sheet({ title, onClose, children }) {
  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl max-h-[80vh] overflow-y-auto" style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom))" }}>
        <div className="mx-auto mt-2 w-10 h-1.5 rounded-full bg-slate-200 sm:hidden" />
        <div className="flex items-center justify-between px-5 pt-3 pb-2">
          <h3 className="text-base font-bold text-slate-900">{title}</h3>
          <button onClick={onClose} className="p-2 -mr-2 text-slate-500" aria-label="Luk"><X className="w-5 h-5" /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}

export default function DriverTodayView({
  tours = [], myId = "", myName = "", reportDate, setReportDate, onPrevDay, onNextDay,
  customers = [], activeCustomer, onSwitchCustomer, unread = {}, messagesUnread = 0, onMessages,
  onStart, onTake, onTakeStart, onFinish, onOpen, onChat, getRouteInfo = () => null, onOptimize, optimizing = false, workedMin = 0, loading = false, showWorked = true,
}) {
  const [tab, setTab] = useState("mine");
  const [q, setQ] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [custOpen, setCustOpen] = useState(false);
  const [collapsed, setCollapsed] = useState({});

  const isMine = (t) => (myId && (t.claimed_by_id === myId || (t.driver_id || "") === myId)) || (!t.claimed_by_id && myName && t.claimed_by === myName);
  const match = (t) => {
    const n = q.trim().toLowerCase();
    if (!n) return true;
    return [t.fraction, t.address, t.facility, t.plads, t.customer_name, t.private_company, t.tour_number, t.container].join(" ").toLowerCase().includes(n);
  };

  const { active, mine, free, done, cancelled } = useMemo(() => {
    // 2026-10-19: En annulleret tur (også annulleret mens han var på vej, som
    // er forgæves) vises nederst under "Annulleret" og tæller ikke med.
    const all = tours.filter(t => !t.is_pause && (t.tour_type || "") !== "estimat" && (!t.not_completed || t.cancelled));
    const list = all.filter(t => !t.cancelled && !t.not_completed);
    const mineAll = list.filter(isMine);
    const act = mineAll.filter(t => t.on_way && !t.completed).sort((a, b) => sortOpen(a, b, getRouteInfo));
    return {
      active: act,
      cancelled: all.filter(t => t.cancelled && !t.completed && isMine(t)),
      mine: mineAll.filter(t => !t.completed && !t.on_way).sort((a, b) => sortOpen(a, b, getRouteInfo)),
      free: list.filter(t => !isMine(t) && !t._is_other_driver && !t.completed && !t.on_way && !t.claimed_by && !(t.driver_id || "").trim()),
      done: mineAll.filter(t => t.completed && (t.date || "").slice(0, 10) === reportDate)
        .sort((a, b) => String(b.time || "").localeCompare(String(a.time || ""))),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tours, myId, myName, reportDate, getRouteInfo]);

  const freeGroups = useMemo(() => {
    const m = new Map();
    free.filter(match).forEach(t => {
      const past = (t.date || "").slice(0, 10) < reportDate;
      const key = past ? "__past" : (t.plads || "Uden lokation");
      if (!m.has(key)) m.set(key, []);
      m.get(key).push(t);
    });
    return Array.from(m.entries())
      .sort((a, b) => (a[0] === "__past" ? -1 : b[0] === "__past" ? 1 : a[0].localeCompare(b[0], "da")))
      .map(([k, list]) => ({ key: k, title: k === "__past" ? "Fra tidligere dage" : k, list: list.sort((a, b) => sortOpen(a, b, getRouteInfo)) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [free, q, reportDate, getRouteInfo]);

  const totalMine = active.length + mine.length + done.length;
  const pct = totalMine ? Math.round((done.length / totalMine) * 100) : 0;
  const kg = done.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  const worked = `${Math.floor(workedMin / 60)}:${String(workedMin % 60).padStart(2, "0")}`;
  const mineOpen = [...active, ...mine];
  const optimizePlads = (() => {
    const c = {};
    mineOpen.forEach(t => { if (t.plads) c[t.plads] = (c[t.plads] || 0) + 1; });
    return Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  })();
  const freeCount = free.length;
  const multiCustomer = customers.length > 1;

  const row = (t, mode, opts = {}) => (
    <DriverTourCard key={t.id} tour={t} routeInfo={getRouteInfo(t.id)} unread={unread[t.id] || 0} mode={mode}
      hideAddrs={opts.hideAddrs || []} hideLegs={!!opts.hideLegs}
      run={t.run_role ? { role: t.run_role, size: t.run_size } : null}
      onStart={onStart} onTake={onTake} onTakeStart={onTakeStart} onFinish={onFinish} onOpen={onOpen} onChat={onChat} />
  );
  // 2026-10-20 (runde 2): Hver tur er sin egen lille boks med luft imellem.
  const list = (children, testid) => <div className="space-y-1.5" data-testid={testid}>{children}</div>;
  // Pladsens adresse står én gang i gruppens overskrift (med "Kør"), når
  // alle turene i gruppen kører til/fra pladsen - så viser hver tur kun den
  // anden adresse (typisk afleveringen).
  const sharedPlads = (ts) => {
    const a = ts[0]?.plads_address;
    return a && ts.every(t => t.plads_address === a && legsOf(t).some(l => l.address === a)) ? a : "";
  };
  // I gang: en hængerkørsel står samlet (bil først), solo-ture hver for sig.
  const activeBlocks = useMemo(() => {
    const runs = new Map();
    const out = [];
    active.filter(match).forEach(t => {
      if (t.run_id && t.run_role && t.run_role !== "solo") {
        if (!runs.has(t.run_id)) { runs.set(t.run_id, []); out.push({ key: t.run_id, run: runs.get(t.run_id) }); }
        runs.get(t.run_id).push(t);
      } else out.push({ key: t.id, list: [t] });
    });
    out.forEach(b => b.run && b.run.sort((a, c) => (a.run_role === "truck" ? -1 : c.run_role === "truck" ? 1 : (a.run_seq || 0) - (c.run_seq || 0))));
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, q]);
  // Næste (mine, ikke startet): grupperet pr. plads i den rækkefølge turene skal køres.
  const mineGroups = useMemo(() => {
    const m = new Map();
    mine.filter(match).forEach(t => {
      const k = t.plads || "Uden lokation";
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(t);
    });
    return Array.from(m.entries()).map(([k, list]) => ({ key: k, title: k, list }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mine, q]);
  const groupHead = (title, n, addr = "", icon = <MapPin className="w-4 h-4 text-slate-400" />) => (
    <div className="px-1 pt-1">
      <div className="flex items-center gap-2">
        {icon}<span className="font-bold text-sm text-slate-800 truncate">{title}</span>
        <span className="text-xs font-bold text-slate-500 bg-white border border-slate-200 rounded-full px-2 py-0.5">{n}</span>
      </div>
      {addr && <LegLine leg={{ label: "Plads", name: "", address: addr }} testid={`ture-group-nav-${title}`} />}
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-100" data-testid="ture-tab-hero" style={{ paddingBottom: 96 }}>
      {/* Top: hvem/hvornår */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="max-w-2xl mx-auto px-4 pt-3 pb-2">
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 truncate">{myName || "Chauffør"}</p>
              {multiCustomer ? (
                <button onClick={() => setCustOpen(true)} className="flex items-center gap-1 max-w-full text-left" data-testid="ture-customer-switch">
                  <span className="text-[17px] font-extrabold text-slate-900 truncate">{activeCustomer?.name || "Vælg kunde"}</span>
                  <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                </button>
              ) : (
                <p className="text-[17px] font-extrabold text-slate-900 truncate">{activeCustomer?.name || "Dagens ture"}</p>
              )}
            </div>
            <button onClick={() => setSearchOpen(v => !v)} className={`w-11 h-11 rounded-xl flex items-center justify-center ${searchOpen || q ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`} aria-label="Søg" data-testid="ture-search-toggle">
              <Search className="w-5 h-5" />
            </button>
            <button onClick={onMessages} className="relative w-11 h-11 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center" aria-label="Beskeder" data-testid="ture-bell-btn">
              <MessageCircle className="w-5 h-5" />
              {messagesUnread > 0 && <span className="absolute top-2 right-2 w-2.5 h-2.5 rounded-full bg-orange-500" />}
            </button>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <button onClick={onPrevDay} className="w-11 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600" aria-label="Forrige dag" data-testid="ture-date-prev"><ChevronLeft className="w-5 h-5" /></button>
            <label className="relative flex-1 h-10 rounded-xl bg-slate-100 flex items-center justify-center gap-2 text-sm font-bold text-slate-800 capitalize">
              <Clock className="w-4 h-4 text-slate-400" /> {fmtDate(reportDate)}
              <input type="date" value={reportDate} onChange={(e) => e.target.value && setReportDate(e.target.value)} className="absolute inset-0 opacity-0" aria-label="Vælg dato" data-testid="ture-date-input" />
            </label>
            <button onClick={onNextDay} className="w-11 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600" aria-label="Næste dag" data-testid="ture-date-next"><ChevronRight className="w-5 h-5" /></button>
          </div>
          {(searchOpen || q) && (
            <div className="mt-2 flex items-center gap-2 h-11 rounded-xl border border-slate-200 bg-white px-3">
              <Search className="w-4 h-4 text-slate-400" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Søg adresse, materiale, kunde…" className="flex-1 bg-transparent outline-none text-base" data-testid="ture-search-input" />
              {q && <button onClick={() => setQ("")} className="p-1 text-slate-400" aria-label="Ryd"><X className="w-4 h-4" /></button>}
            </div>
          )}
          {/* Faner */}
          <div className="mt-3 grid grid-cols-3 gap-1 p-1 rounded-2xl bg-slate-100" role="tablist">
            {[["mine", "Mine", mineOpen.length], ["free", "Ledige", freeCount], ["done", "Færdige", done.length]].map(([id, l, n]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} data-testid={`ture-tab-${id}`}
                className={`h-10 rounded-xl text-sm font-bold flex items-center justify-center gap-1.5 ${tab === id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
                {l}
                <span className={`min-w-[22px] h-[22px] px-1.5 rounded-full text-xs flex items-center justify-center ${tab === id ? (id === "free" && n ? "bg-orange-500 text-white" : "bg-slate-900 text-white") : "bg-slate-200 text-slate-600"}`}>{n}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 pt-4 space-y-3">
        {/* Dagen på én linje */}
        <div className="rounded-2xl bg-white border border-slate-200 px-4 py-3" data-testid="ture-day-summary">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-extrabold text-slate-900">{done.length}/{totalMine} kørt</span>
            <span className="text-slate-300">·</span>
            <span className="font-semibold text-emerald-700">{fmtKg(kg)}</span>
            {showWorked && <span className="text-slate-300">·</span>}
            {showWorked && <span className="font-semibold text-slate-600">{worked} t</span>}
            {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400 ml-auto" />}
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden"><div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} /></div>
        </div>

        {/* I gang - altid øverst */}
        {active.length > 0 && tab === "mine" && (
          <div className="space-y-2" data-testid="ture-active">
            <p className="text-[11px] font-bold uppercase tracking-wide text-amber-700 px-1">I gang</p>
            {activeBlocks.map(b => {
              if (!b.run) return <React.Fragment key={b.key}>{row(b.list[0], "mine")}</React.Fragment>;
              // Hængerkørsel: lilla ramme, hvide bokse. Kører alle containerne
              // samme vej, står adresserne én gang øverst.
              const k = (t) => legsOf(t).map(l => l.address).join("|");
              const same = b.run.every(t => k(t) === k(b.run[0]));
              return (
                <div key={b.key} className="rounded-2xl bg-violet-100/70 border-2 border-violet-300 p-1.5 space-y-1.5" data-testid="ture-run-block">
                  <div className="px-1.5 pt-0.5 text-[12px] font-extrabold text-violet-900 flex items-center gap-1.5">
                    <Truck className="w-3.5 h-3.5" /> Hængerkørsel · {b.run.length} containere
                  </div>
                  {same && legsOf(b.run[0]).length > 0 && (
                    <div className="px-1.5" data-testid="ture-run-route">
                      {legsOf(b.run[0]).slice(0, 2).map((l, i) => <LegLine key={i} leg={l} testid={`ture-run-nav-${i}`} />)}
                    </div>
                  )}
                  {b.run.map(t => row(t, "mine", { hideLegs: same }))}
                </div>
              );
            })}
          </div>
        )}
        {active.length > 0 && tab !== "mine" && (
          <button onClick={() => setTab("mine")} className="w-full h-11 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm font-bold flex items-center justify-center gap-2">
            {active.length} {active.length === 1 ? "tur" : "ture"} i gang <ChevronRight className="w-4 h-4" />
          </button>
        )}

        {tab === "mine" && mine.length > 0 && active.length > 0 && <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 px-1 pt-1">Næste</p>}
        {tab === "mine" && (
          <div className="space-y-2" data-testid="ture-list-cards">
            {mine.length > 1 && onOptimize && optimizePlads && (
              <button onClick={() => onOptimize(optimizePlads, mineOpen.map(t => t.id))} disabled={optimizing}
                className="w-full h-11 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-700 flex items-center justify-center gap-2 disabled:opacity-60" data-testid="ture-optimize-btn">
                {optimizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Navigation className="w-4 h-4 text-orange-500" />} Optimer rækkefølge fra {optimizePlads}
              </button>
            )}
            {mineGroups.map(g => {
              const addr = sharedPlads(g.list);
              return (
                <section key={g.key} className="space-y-1.5">
                  {groupHead(g.title, g.list.length, addr)}
                  {list(g.list.map(t => row(t, "mine", { hideAddrs: addr ? [addr] : [] })), `ture-mine-${g.key}`)}
                </section>
              );
            })}
            {mine.length === 0 && active.length === 0 && (
              <div className="rounded-2xl bg-white border border-slate-200 p-8 text-center" data-testid="ture-empty">
                {done.length ? <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto" /> : <Inbox className="w-8 h-8 text-slate-300 mx-auto" />}
                <p className="mt-2 font-bold text-slate-700">{done.length ? "Alle dine ture er kørt" : "Ingen ture til dig endnu"}</p>
                <p className="text-sm text-slate-500 mt-1">{freeCount ? "Der er ledige ture du kan tage." : done.length ? "Godt arbejde. Nye ture dukker op her." : "Planlæggeren har ikke tildelt dig noget for denne dag."}</p>
                {freeCount > 0 && <button onClick={() => setTab("free")} className="mt-4 h-11 px-5 rounded-xl bg-orange-500 text-white font-bold">Se {freeCount} ledige ture</button>}
              </div>
            )}
          </div>
        )}

        {tab === "mine" && cancelled.length > 0 && (
          <div className="space-y-2" data-testid="ture-cancelled">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 px-1 pt-1">Annulleret</p>
            {list(cancelled.filter(match).map(t => row(t, "mine")))}
          </div>
        )}

        {tab === "free" && (
          <div className="space-y-3" data-testid="ture-free">
            {freeGroups.length === 0 && (
              <div className="rounded-2xl bg-white border border-slate-200 p-8 text-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                <p className="mt-2 font-bold text-slate-700">Ingen ledige ture</p>
                <p className="text-sm text-slate-500 mt-1">Alle ture er taget eller tildelt.</p>
              </div>
            )}
            {freeGroups.map(g => {
              const isCol = collapsed[g.key] ?? (freeGroups.length > 3 && g.key !== "__past");
              return (
                <section key={g.key} className="space-y-2">
                  <button onClick={() => setCollapsed(c => ({ ...c, [g.key]: !isCol }))} className="w-full flex items-center gap-2 px-1 py-1 text-left">
                    {g.key === "__past" ? <Clock className="w-4 h-4 text-amber-600" /> : <MapPin className="w-4 h-4 text-slate-400" />}
                    <span className={`font-bold text-sm truncate ${g.key === "__past" ? "text-amber-800" : "text-slate-800"}`}>{g.title}</span>
                    <span className="text-xs font-bold text-slate-500 bg-white border border-slate-200 rounded-full px-2 py-0.5">{g.list.length}</span>
                    <ChevronDown className={`w-4 h-4 text-slate-400 ml-auto transition-transform ${isCol ? "-rotate-90" : ""}`} />
                  </button>
                  {!isCol && g.key !== "__past" && sharedPlads(g.list) && <div className="px-1"><LegLine leg={{ label: "Plads", name: "", address: sharedPlads(g.list) }} testid={`ture-free-nav-${g.key}`} /></div>}
                  {!isCol && list(g.list.map(t => row(t, "free", { hideAddrs: g.key !== "__past" && sharedPlads(g.list) ? [sharedPlads(g.list)] : [] })))}
                </section>
              );
            })}
          </div>
        )}

        {tab === "done" && (
          <div className="space-y-2" data-testid="ture-done">
            {done.length === 0 && (
              <div className="rounded-2xl bg-white border border-slate-200 p-8 text-center text-sm text-slate-500">Ingen færdige ture endnu.</div>
            )}
            {done.length > 0 && list(done.filter(match).map(t => row(t, "done")))}
          </div>
        )}
      </div>

      {custOpen && (
        <Sheet title="Hvem kører du for?" onClose={() => setCustOpen(false)}>
          <div className="px-3 pb-2">
            {customers.map(c => {
              const on = activeCustomer?.id === c.id;
              return (
                <button key={c.id} onClick={() => { setCustOpen(false); if (!on) onSwitchCustomer(c); }}
                  className={`w-full flex items-center gap-3 px-3 py-3.5 rounded-xl text-left ${on ? "bg-orange-50" : "active:bg-slate-50"}`}>
                  {c.own ? <Truck className="w-5 h-5 text-slate-400" /> : <Building2 className="w-5 h-5 text-slate-400" />}
                  <span className={`flex-1 font-semibold ${on ? "text-orange-700" : "text-slate-800"}`}>{c.name}</span>
                  {on && <Check className="w-5 h-5 text-orange-600" />}
                </button>
              );
            })}
          </div>
        </Sheet>
      )}
    </div>
  );
}
