import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  BarChart3, Tag, CheckCircle2, CalendarDays, Settings, Plus, X, Loader2, Search,
  Edit2, Copy, Trash2, AlertTriangle, Clock, Lock, Unlock, FileSpreadsheet, ChevronLeft,
  ChevronRight, Truck, Info, Check, Ban, Users, Building2, PowerOff,
} from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Økonomi (logistik admin) - erstatter "Priser & Rapport".
 * Se PRICING_SPEC.md for reglerne. Al beregning sker i backend/pricing.py;
 * siden viser resultatet og lader admin vedligeholde regler, helligdage,
 * indstillinger og godkende chaufførernes rettelser.
 */

const fmtKr = (n) => n == null ? "-" : Number(n).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kr";
const fmtMin = (m) => {
  if (m == null) return "-";
  const h = Math.floor(m / 60);
  return `${h}t ${String(Math.round(m % 60)).padStart(2, "0")}m`;
};
const fmtDate = (s) => {
  if (!s) return "-";
  try { return new Date(s + "T00:00:00").toLocaleDateString("da-DK", { weekday: "short", day: "2-digit", month: "short" }); }
  catch (_) { return s; }
};
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const card = "bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm";
const chipBase = "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors";
const chipOn = "bg-emerald-600 border-emerald-600 text-white";
const chipOff = "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700";
const input = "w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";
const label = "block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1";
const btnPrimary = "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700";

const STATUS_META = {
  ok: null,
  missing_rule: { text: "Mangler pris", cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
  missing_time: { text: "Mangler tid", cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
};

/* 2026-10-17: Hjælpetekster (vises ved ⓘ). Brugerens egen forklaring på en
   regel gemmes i `note` og vises sammen med standardteksten. */
const HELP = {
  base: "Grundpris: hver tur får præcis én grundpris. Passer flere regler, vinder den mest specifikke (kunde > lokation > leveringsadresse > opgavetype > materiale).",
  surcharge: "Tillæg: lægges oveni grundprisen. Højst ét tillæg af hver type pr. tur - igen vinder det mest specifikke. Et kundespecifikt tillæg på 0 kr fritager altså den kunde.",
  model: {
    fixed: "Fast pris: samme beløb pr. tur, uanset hvor lang tid den tager.",
    hourly: "Timepris: tiden fra chaufføren trykker \"På vej\" til turen afsluttes × timeprisen. Startgebyr, minimum og afrunding kan tilføjes, og pauser kan trækkes fra. Kører chaufføren flere ture samtidig, deles tiden mellem dem.",
    per_container: "Pris pr. container: beløbet × antal containere på turen (fx ved løs afhentning, hvor chaufføren vejer flere containere).",
  },
  category: {
    weekend: "Weekend: lægges på ture der køres lørdag eller søndag.",
    holiday: "Helligdag: lægges på ture på helligdage - ud fra dansk kalender eller kundens egen kalender (se fanen Helligdage).",
    haster: "Haster: lægges på ture med prioritet Haster.",
    trailer: "Hænger: lægges på ture hvor chaufføren har kørt med hænger (chaufføren vælger Med/Uden hænger på turen).",
    evening: "Aften/nat: lægges på ture der starter i et bestemt tidsrum, fx 18:00-06:00. Tidsrummet sættes under \"Flere betingelser\".",
    waiting: "Ventetid: betaling for tid chaufføren venter på adressen, fx når containeren er blokeret eller kunden ikke er klar. Afregnes pr. påbegyndt kvarter ud fra de ventetidsminutter der er registreret på turen. Chaufføren beder om ventetid efter turen (godkendes under Godkendelser), eller du skriver den på turen i Rapport. Ture uden ventetid får intet tillæg. Typisk som kr pr. time.",
    other: "Andet: alt det der ikke passer i de andre typer, fx miljøtillæg eller bro/færge. Brug betingelserne til at styre hvilke ture det gælder.",
  },
};
const ruleHelp = (r) => r.kind === "base"
  ? (HELP.model[(r.pricing || {}).model || "fixed"] || HELP.base)
  : (HELP.category[r.category] || HELP.surcharge);

/** ⓘ med forklaring. Klik/tryk åbner (virker også på telefon og iPad). */
function InfoTip({ text, own, className = "" }) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState(null);
  const btn = useRef(null);
  const pop = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!btn.current?.contains(e.target) && !pop.current?.contains(e.target)) setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    window.addEventListener("scroll", onScroll, true);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("touchstart", close); window.removeEventListener("scroll", onScroll, true); };
  }, [open]);
  if (!text && !own) return null;
  const width = Math.min(320, window.innerWidth - 24);
  return (
    <>
      <button ref={btn} type="button" aria-label="Forklaring"
        onClick={(e) => { e.stopPropagation(); setRect(btn.current.getBoundingClientRect()); setOpen(v => !v); }}
        className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 ${own ? "text-emerald-600" : ""} ${className}`}>
        <Info className="w-4 h-4" />
      </button>
      {open && rect && createPortal(
        <div ref={pop} role="tooltip" className="fixed z-[1000] rounded-xl bg-slate-900 text-white text-xs leading-relaxed shadow-2xl p-3 space-y-2"
          style={{ width, top: Math.min(rect.bottom + 6, window.innerHeight - 200), left: Math.max(12, Math.min(rect.left - width / 2 + 12, window.innerWidth - width - 12)) }}>
          {text && <p>{text}</p>}
          {own && <div className="border-t border-white/15 pt-2"><div className="font-bold text-emerald-300 mb-0.5">Jeres forklaring</div><p className="whitespace-pre-wrap">{own}</p></div>}
        </div>,
        document.body
      )}
    </>
  );
}

function Segmented({ value, onChange, options }) {
  return (
    <div className="inline-flex flex-wrap gap-1 p-1 bg-slate-100 dark:bg-slate-900 rounded-lg">
      {options.map(o => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 rounded-md text-xs font-semibold ${value === o.value ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-white" : "text-slate-500 dark:text-slate-400"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Multi-valg med søgning. `items` = [{value, label}] ; tom værdi = "Alle". */
function MultiPick({ title, items, value, onChange, allLabel = "Alle" }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const selected = new Set(value || []);
  const shown = items.filter(i => !q || i.label.toLowerCase().includes(q.toLowerCase()));
  const toggle = (v) => {
    const s = new Set(selected);
    s.has(v) ? s.delete(v) : s.add(v);
    onChange(Array.from(s));
  };
  return (
    <div>
      <span className={label}>{title}</span>
      <div className="flex flex-wrap items-center gap-1.5">
        {selected.size === 0 && <span className="px-2.5 py-1 rounded-full text-xs bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300">{allLabel}</span>}
        {items.filter(i => selected.has(i.value)).map(i => (
          <span key={i.value} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
            {i.label}
            <button type="button" onClick={() => toggle(i.value)} aria-label={`Fjern ${i.label}`}><X className="w-3 h-3" /></button>
          </span>
        ))}
        <button type="button" onClick={() => setOpen(o => !o)} className="px-2.5 py-1 rounded-full text-xs font-semibold text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/30">
          {open ? "Luk" : "+ Vælg"}
        </button>
      </div>
      {open && (
        <div className="mt-2 border border-slate-200 dark:border-slate-600 rounded-lg p-2 bg-slate-50 dark:bg-slate-900">
          {items.length > 6 && (
            <div className="relative mb-2">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input className={`${input} pl-8 py-1.5`} placeholder="Søg..." value={q} onChange={e => setQ(e.target.value)} />
            </div>
          )}
          <div className="max-h-48 overflow-y-auto grid grid-cols-1 sm:grid-cols-2 gap-1">
            {shown.map(i => (
              <label key={i.value} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-white dark:hover:bg-slate-800 text-sm cursor-pointer">
                <input type="checkbox" checked={selected.has(i.value)} onChange={() => toggle(i.value)} className="accent-emerald-600" />
                <span className="truncate">{i.label}</span>
              </label>
            ))}
            {shown.length === 0 && <span className="text-xs text-slate-400 px-2">Ingen valgmuligheder</span>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ======================================================================
   Hovedkomponent
   ====================================================================== */
const fmtTs = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
  return time === "00.00" || time === "00:00" ? date : `${date} kl. ${time}`;
};

export default function EconomyPanel({ canEdit = true }) {
  const [view, setView] = useState("report");
  const [rulesFilter, setRulesFilter] = useState("all");
  const [options, setOptions] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);

  const loadOptions = useCallback(async () => {
    try { setOptions((await axios.get(`${API}/pricing/options`)).data); }
    catch (e) { toast.error(formatApiError(e, "Kunne ikke hente valgmuligheder")); }
  }, []);
  const loadPending = useCallback(async () => {
    try { setPendingCount(((await axios.get(`${API}/pricing/requests`)).data || []).length); }
    catch (_) { /* ignore */ }
  }, []);
  useEffect(() => { loadOptions(); loadPending(); }, [loadOptions, loadPending]);

  const VIEWS = [
    { id: "report", label: "Rapport", icon: BarChart3 },
    { id: "customers", label: "Kunder & priser", icon: Users },
    { id: "rules", label: "Prisregler", icon: Tag },
    canEdit && { id: "approvals", label: "Godkendelser", icon: CheckCircle2, badge: pendingCount },
    { id: "holidays", label: "Helligdage", icon: CalendarDays },
    canEdit && { id: "settings", label: "Indstillinger", icon: Settings },
  ].filter(Boolean);

  return (
    <section className="space-y-4" data-testid="economy-panel">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Økonomi</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Priser beregnes automatisk ud fra dine prisregler. Alle beløb er ekskl. moms.</p>
        </div>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-1 -mx-1 px-1">
        {VIEWS.map(v => {
          const Icon = v.icon;
          return (
            <button key={v.id} onClick={() => setView(v.id)} data-testid={`economy-tab-${v.id}`}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-colors ${view === v.id ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"}`}>
              <Icon className="w-4 h-4" /> {v.label}
              {v.badge > 0 && <span className="min-w-[20px] h-5 px-1.5 inline-flex items-center justify-center rounded-full bg-amber-500 text-white text-[11px] font-bold">{v.badge}</span>}
            </button>
          );
        })}
      </div>
      {!options ? (
        <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : (
        <>
          {view === "report" && <ReportView options={options} onChanged={loadPending} goRules={() => setView("rules")} goApprovals={() => setView("approvals")} />}
          {!canEdit && (
            <div className="flex gap-2 p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm text-amber-900 dark:text-amber-100">
              <Info className="w-4 h-4 mt-0.5 shrink-0" /> Du kan se priser, men ikke ændre dem. Spørg din administrator under Team &amp; rettigheder.
            </div>
          )}
          {view === "customers" && <CustomersView options={options} reloadOptions={loadOptions} canEdit={canEdit} goRules={(f) => { setRulesFilter(f); setView("rules"); }} />}
          {view === "rules" && <RulesView key={rulesFilter} initialFilter={rulesFilter} options={options} reloadOptions={loadOptions} canEdit={canEdit} />}
          {view === "approvals" && <ApprovalsView onChanged={loadPending} />}
          {view === "holidays" && <HolidaysView profile={options.profile} />}
          {view === "settings" && <SettingsView />}
        </>
      )}
    </section>
  );
}

/* ======================================================================
   Rapport
   ====================================================================== */
function periodRange(p) {
  const now = new Date();
  if (p === "this_month") return { from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), to: ymd(new Date(now.getFullYear(), now.getMonth() + 1, 0)) };
  if (p === "last_month") return { from: ymd(new Date(now.getFullYear(), now.getMonth() - 1, 1)), to: ymd(new Date(now.getFullYear(), now.getMonth(), 0)) };
  if (p === "this_week") {
    const d = new Date(now); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd);
    const e = new Date(d); e.setDate(d.getDate() + 6);
    return { from: ymd(d), to: ymd(e) };
  }
  return null;
}

function ReportView({ options, onChanged, goRules, goApprovals }) {
  const [period, setPeriod] = useState("this_month");
  const [range, setRange] = useState(periodRange("this_month"));
  const [customer, setCustomer] = useState("");
  const [location, setLocation] = useState("");
  const [attention, setAttention] = useState("");
  const [search, setSearch] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [openTour, setOpenTour] = useState(null);

  useEffect(() => { const r = periodRange(period); if (r) setRange(r); }, [period]);

  const load = useCallback(async () => {
    if (!range.from || !range.to) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ date_from: range.from, date_to: range.to });
      if (customer) params.set("customer_id", customer);
      if (location) params.set("location_code", location);
      setData((await axios.get(`${API}/pricing/report?${params}`)).data);
      setSelected(new Set());
    } catch (e) { toast.error(formatApiError(e, "Kunne ikke hente rapporten")); }
    finally { setLoading(false); }
  }, [range.from, range.to, customer, location]);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    let arr = data?.rows || [];
    if (attention === "missing") arr = arr.filter(r => r.price.status !== "ok");
    if (attention === "pending") arr = arr.filter(r => r.pending_requests > 0);
    if (attention === "invoiced") arr = arr.filter(r => r.price.locked);
    if (attention === "open") arr = arr.filter(r => !r.price.locked);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      arr = arr.filter(r => [r.tour_number, r.customer_name, r.location_name, r.material, r.driver_name, r.delivery_label]
        .some(v => (v || "").toLowerCase().includes(q)));
    }
    return arr;
  }, [data, attention, search]);

  const locationsForCustomer = options.locations.filter(l => !customer || l.customer_id === customer);
  const t = data?.totals;
  const taskLabel = (k) => options.task_types[k] || k;

  const toggleAll = () => setSelected(s => s.size === rows.length ? new Set() : new Set(rows.map(r => r.tour_id)));
  // "Faktureret" fryser prisen. Markeringen kan kun fjernes fra ture der ER
  // faktureret - og kun ture med en pris kan markeres.
  const selectedRows = rows.filter(r => selected.has(r.tour_id));
  const toInvoice = selectedRows.filter(r => !r.price.locked && r.price.total != null);
  const toUninvoice = selectedRows.filter(r => r.price.locked);
  const markInvoiced = async (invoiced) => {
    const ids = (invoiced ? toInvoice : toUninvoice).map(r => r.tour_id);
    if (!ids.length) return;
    try {
      const { data: res } = await axios.post(`${API}/pricing/invoice`, { tour_ids: ids, invoiced });
      toast.success(invoiced
        ? `${res.updated} ture markeret som faktureret${res.skipped_without_price ? ` · ${res.skipped_without_price} sprunget over (mangler pris)` : ""}`
        : `Faktureret-markering fjernet fra ${res.updated} ture`);
      load();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const exportCsv = () => {
    const list = selected.size ? rows.filter(r => selected.has(r.tour_id)) : rows;
    if (!list.length) { toast.error("Ingen ture at eksportere"); return; }
    const num = (n) => n == null ? "" : String(n).replace(".", ",");
    const head = ["Kunde", "Dato", "Tur nr.", "Lokation", "Materiale", "Opgavetype", "Leveringsadresse", "Chauffør",
      "Start", "Slut", "Hænger", "Ventetid (min)", "Prismodel", "Faktureret tid (min)", "Linjer", "Pris ekskl. moms", "Status"];
    const sorted = [...list].sort((a, b) => (a.customer_name || "").localeCompare(b.customer_name || "") || a.service_date.localeCompare(b.service_date));
    const lines = sorted.map(r => [
      r.customer_name, r.service_date, r.tour_number, r.location_name, r.material, taskLabel(r.task_type), r.delivery_label,
      r.driver_name, r.start_time, r.end_time, r.trailer ? "Ja" : "Nej", r.waiting_min || 0,
      options.models[r.price.model] || "", r.price.time?.billable_min ?? "",
      (r.price.lines || []).map(l => `${l.label}: ${num(l.amount)}`).join(" | "),
      num(r.price.total), r.outcome === "not_completed" ? "Forgæves" : r.price.locked ? "Faktureret" : (STATUS_META[r.price.status]?.text || "OK"),
    ]);
    const csv = [head, ...lines].map(row => row.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fakturagrundlag_${range.from}_${range.to}.csv`;
    a.click();
  };

  return (
    <div className="space-y-4">
      <div className={`${card} p-4 space-y-3`}>
        <div className="flex flex-wrap gap-2">
          {[["this_month", "Denne måned"], ["last_month", "Sidste måned"], ["this_week", "Denne uge"], ["custom", "Brugerdef."]].map(([v, l]) => (
            <button key={v} onClick={() => setPeriod(v)} className={`${chipBase} ${period === v ? chipOn : chipOff}`}>{l}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <div><span className={label}>Fra</span><input type="date" className={input} value={range.from} onChange={e => { setPeriod("custom"); setRange(r => ({ ...r, from: e.target.value })); }} /></div>
          <div><span className={label}>Til</span><input type="date" className={input} value={range.to} onChange={e => { setPeriod("custom"); setRange(r => ({ ...r, to: e.target.value })); }} /></div>
          <div><span className={label}>Kunde</span>
            <select className={input} value={customer} onChange={e => { setCustomer(e.target.value); setLocation(""); }}>
              <option value="">Alle kunder</option>
              {options.customers.some(c => c.own) && (
                <optgroup label="Egne kunder">
                  {options.customers.filter(c => c.own).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </optgroup>
              )}
              {options.customers.some(c => !c.own) && (
                <optgroup label="Genbrugsplads-kunder">
                  {options.customers.filter(c => !c.own).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </optgroup>
              )}
            </select></div>
          <div><span className={label}>Lokation</span>
            <select className={input} value={location} onChange={e => setLocation(e.target.value)}>
              <option value="">Alle lokationer</option>
              {locationsForCustomer.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select></div>
          <div className="col-span-2 md:col-span-1"><span className={label}>Søg</span>
            <input className={input} placeholder="Tur, materiale, chauffør..." value={search} onChange={e => setSearch(e.target.value)} /></div>
        </div>
      </div>

      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi tone="emerald" title="Omsætning ekskl. moms" value={fmtKr(t.net)} sub={`Inkl. ${t.vat_percent}% moms: ${fmtKr(t.gross)}`} />
          <Kpi tone="blue" title="Ture" value={t.tours} sub={`${t.not_completed} forgæves · ${t.invoiced} faktureret`} />
          <Kpi tone="amber" title="Fakt. timer" value={`${String(t.billable_hours).replace(".", ",")} t`} sub="Timeprisede ture" />
          <Kpi tone="sky" title="Gns. pr. tur" value={fmtKr(t.tours - t.missing_rule - t.missing_time > 0 ? t.net / (t.tours - t.missing_rule - t.missing_time) : 0)} sub="Ture med pris" />
        </div>
      )}

      {t && (t.missing_rule > 0 || t.missing_time > 0 || t.pending_requests > 0) && (
        <div className="flex flex-wrap gap-2">
          {t.missing_rule > 0 && (
            <button onClick={() => setAttention(attention === "missing" ? "" : "missing")} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-sm text-red-700 dark:text-red-300">
              <AlertTriangle className="w-4 h-4" /> {t.missing_rule} ture mangler en prisregel
              <span className="underline" onClick={(e) => { e.stopPropagation(); goRules(); }}>Opret regel</span>
            </button>
          )}
          {t.missing_time > 0 && (
            <button onClick={() => setAttention(attention === "missing" ? "" : "missing")} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm text-amber-800 dark:text-amber-200">
              <Clock className="w-4 h-4" /> {t.missing_time} timeprisede ture mangler start/slut
            </button>
          )}
          {t.pending_requests > 0 && (
            <button onClick={goApprovals} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm text-amber-800 dark:text-amber-200">
              <CheckCircle2 className="w-4 h-4" /> {t.pending_requests} rettelser venter på godkendelse
            </button>
          )}
        </div>
      )}

      {data?.by_customer?.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {data.by_customer.map(b => (
            <button key={b.customer_id} onClick={() => setCustomer(customer === b.customer_id ? "" : b.customer_id)}
              className={`${card} px-4 py-2.5 text-left min-w-[180px] ${customer === b.customer_id ? "ring-2 ring-emerald-500" : ""}`}>
              <div className="text-xs font-semibold text-slate-500 truncate">{b.customer_name}</div>
              <div className="font-bold">{fmtKr(b.net)}</div>
              <div className="text-[11px] text-slate-500">{b.tours} ture{b.missing ? ` · ${b.missing} uden pris` : ""}</div>
            </button>
          ))}
        </div>
      )}

      <div className={`${card} overflow-hidden`}>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-slate-100 dark:border-slate-700">
          <div className="flex flex-wrap gap-1.5">
            {[["", "Alle"], ["open", "Ikke faktureret"], ["invoiced", "Faktureret"], ["missing", "Mangler pris/tid"], ["pending", "Afventer godkendelse"]].map(([v, l]) => (
              <button key={v} onClick={() => setAttention(v)} className={`${chipBase} ${attention === v ? chipOn : chipOff}`}>{l}</button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {toInvoice.length > 0 && (
              <button className={btnGhost} onClick={() => markInvoiced(true)} title="Prisen fryses, så senere regelændringer ikke ændrer den">
                <Lock className="w-4 h-4" /> Markér som faktureret ({toInvoice.length})
              </button>
            )}
            {toUninvoice.length > 0 && (
              <button className={btnGhost} onClick={() => markInvoiced(false)} title="Prisen beregnes igen ud fra de nuværende regler">
                <Unlock className="w-4 h-4" /> Fjern faktureret-markering ({toUninvoice.length})
              </button>
            )}
            <button className={btnPrimary} onClick={exportCsv}><FileSpreadsheet className="w-4 h-4" /> {selected.size ? `Eksportér valgte (${selected.size})` : "Eksportér fakturagrundlag"}</button>
          </div>
        </div>
        {loading ? (
          <div className="p-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">Ingen afsluttede ture i perioden.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/40 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="p-3 w-8"><input type="checkbox" className="accent-emerald-600" checked={selected.size === rows.length} onChange={toggleAll} /></th>
                  <th className="p-3 text-left">Dato</th>
                  <th className="p-3 text-left">Kunde · Lokation</th>
                  <th className="p-3 text-left">Opgave</th>
                  <th className="p-3 text-left">Chauffør</th>
                  <th className="p-3 text-left">Tid</th>
                  <th className="p-3 text-left">Model</th>
                  <th className="p-3 text-right">Pris</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => {
                  const st = STATUS_META[r.price.status];
                  return (
                    <tr key={r.tour_id} onClick={() => setOpenTour(r.tour_id)} className="border-t border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/40 cursor-pointer">
                      <td className="p-3" onClick={e => e.stopPropagation()}>
                        <input type="checkbox" className="accent-emerald-600" checked={selected.has(r.tour_id)}
                          onChange={() => setSelected(s => { const n = new Set(s); n.has(r.tour_id) ? n.delete(r.tour_id) : n.add(r.tour_id); return n; })} />
                      </td>
                      <td className="p-3 whitespace-nowrap">
                        <div className="font-semibold">{fmtDate(r.service_date)}</div>
                        <div className="text-[11px] text-slate-500">{r.tour_number || ""} {r.day_type !== "weekday" && <span className="text-amber-600">· {options.day_types[r.day_type]}</span>}</div>
                      </td>
                      <td className="p-3"><div className="font-semibold">{r.customer_name}</div><div className="text-xs text-slate-500">{r.location_name}</div></td>
                      <td className="p-3">
                        <div>{r.material}</div>
                        <div className="text-xs text-slate-500">{taskLabel(r.task_type)}{r.priority === "haster" ? " · Haster" : ""}{r.trailer ? " · Hænger" : ""}</div>
                      </td>
                      <td className="p-3 whitespace-nowrap">{r.driver_name}</td>
                      <td className="p-3 whitespace-nowrap font-mono text-xs">{r.start_time || "-"}–{r.end_time || "-"}</td>
                      <td className="p-3 text-xs">
                        {r.outcome === "not_completed" ? <span className="text-red-600 font-semibold">Forgæves</span> : (options.models[r.price.model] || "-")}
                        {r.price.time && <div className="text-slate-500">{fmtMin(r.price.time.billable_min)}</div>}
                      </td>
                      <td className="p-3 text-right whitespace-nowrap">
                        <div className="font-bold">{fmtKr(r.price.total)}</div>
                        <div className="flex justify-end gap-1 mt-0.5">
                          {st && <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${st.cls}`}>{st.text}</span>}
                          {r.price.locked && <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200">Faktureret</span>}
                          {r.has_override && <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">Tilpasset</span>}
                          {r.pending_requests > 0 && <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700">Afventer</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {openTour && <TourPriceDrawer tourId={openTour} options={options} onClose={() => setOpenTour(null)} onChanged={() => { load(); onChanged(); }} />}
    </div>
  );
}

function Kpi({ tone, title, value, sub }) {
  const tones = {
    emerald: "bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-900",
    blue: "bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-900",
    amber: "bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-900",
    sky: "bg-sky-50 border-sky-200 dark:bg-sky-950/30 dark:border-sky-900",
  };
  return (
    <div className={`rounded-2xl border p-4 ${tones[tone]}`}>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</div>
      <div className="text-2xl font-black mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

/* ======================================================================
   Tur-detaljer: prisopbygning + tilpasning
   ====================================================================== */
function TourPriceDrawer({ tourId, options, onClose, onChanged }) {
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setD((await axios.get(`${API}/pricing/tours/${tourId}`)).data); }
    catch (e) { toast.error(formatApiError(e)); onClose(); }
  }, [tourId, onClose]);
  useEffect(() => { load(); }, [load]);

  const startEdit = () => {
    const fo = d.fact_overrides || {}, po = d.price_override || {};
    setEdit({
      start_time: fo.start_time || "", end_time: fo.end_time || "",
      used_trailer: fo.used_trailer === undefined ? "" : String(fo.used_trailer),
      waiting_min: fo.waiting_min ?? "", deduct_pause: fo.deduct_pause === undefined ? "" : String(fo.deduct_pause),
      mode: po.mode === "fixed" ? "fixed" : "rules", amount: po.amount ?? "",
      extra_lines: po.extra_lines || [], note: "",
    });
  };
  const save = async () => {
    if (!edit.note.trim()) { toast.error("Skriv en kort begrundelse"); return; }
    const fact = {};
    if (edit.start_time) fact.start_time = edit.start_time;
    if (edit.end_time) fact.end_time = edit.end_time;
    if (edit.used_trailer !== "") fact.used_trailer = edit.used_trailer === "true";
    if (edit.deduct_pause !== "") fact.deduct_pause = edit.deduct_pause === "true";
    if (edit.waiting_min !== "") fact.waiting_min = Number(edit.waiting_min);
    setSaving(true);
    try {
      const { data } = await axios.put(`${API}/pricing/tours/${tourId}/adjust`, {
        note: edit.note, fact_overrides: fact,
        price_override: { mode: edit.mode, amount: edit.mode === "fixed" ? Number(edit.amount) : undefined, extra_lines: edit.extra_lines.filter(x => x.label) },
      });
      setD(data); setEdit(null); toast.success("Turen er opdateret"); onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };
  const unlock = async () => {
    try { await axios.post(`${API}/pricing/invoice`, { tour_ids: [tourId], invoiced: false }); await load(); onChanged(); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="w-full max-w-lg h-full overflow-y-auto bg-slate-50 dark:bg-slate-900 shadow-2xl" onClick={e => e.stopPropagation()} data-testid="tour-price-drawer">
        <div className="sticky top-0 z-10 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-5 py-4 flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-500">{d?.tour_number} · {d ? fmtDate(d.service_date) : ""}</div>
            <div className="font-bold">{d ? `${d.material} · ${d.location_name}` : "Henter..."}</div>
            <div className="text-xs text-slate-500">{d?.customer_name} · {d?.driver_name}</div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"><X className="w-5 h-5" /></button>
        </div>
        {!d ? <div className="p-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin" /></div> : (
          <div className="p-5 space-y-4">
            {d.price.locked && (
              <div className="flex items-center justify-between gap-2 p-3 rounded-xl bg-slate-200/70 dark:bg-slate-700 text-sm">
                <span className="flex items-center gap-2"><Lock className="w-4 h-4" /> Faktureret - prisen er låst</span>
                <button className="underline font-semibold" onClick={unlock} title="Prisen beregnes igen ud fra de nuværende regler">Fjern faktureret-markering</button>
              </div>
            )}
            <div className={`${card} p-4`}>
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Prisopbygning</div>
              {(d.price.lines || []).map((l, i) => (
                <div key={i} className="flex justify-between gap-3 py-1.5 text-sm border-b border-slate-100 dark:border-slate-700 last:border-0">
                  <span className={l.type === "surcharge" ? "text-amber-700 dark:text-amber-300" : l.type === "extra" || l.type === "override" ? "text-blue-700 dark:text-blue-300" : ""}>{l.label}</span>
                  <span className="font-mono">{fmtKr(l.amount)}</span>
                </div>
              ))}
              <div className="flex justify-between pt-2 mt-1 font-bold"><span>I alt ekskl. moms</span><span>{fmtKr(d.price.total)}</span></div>
              {(d.price.flags || []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">{d.price.flags.map(f => <span key={f} className="px-2 py-0.5 rounded-full text-[11px] bg-slate-100 dark:bg-slate-700">{f}</span>)}</div>
              )}
              {d.price.base_rule && <div className="text-xs text-slate-500 mt-2">Grundpris fra reglen "{d.price.base_rule.name}"</div>}
            </div>

            {d.price.time && (
              <div className={`${card} p-4 text-sm`}>
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Tid</div>
                <Row k="På vej → afsluttet" v={fmtMin(d.price.time.gross_min)} />
                {d.price.time.shared_min > 0 && <Row k="Delt med samtidige ture" v={`− ${fmtMin(d.price.time.shared_min)}`} />}
                <Row k={`Pause under turen ${d.price.time.deduct_pause ? "(trækkes fra)" : "(tæller med)"}`} v={d.price.time.pause_min ? `${d.price.time.deduct_pause ? "− " : ""}${fmtMin(d.price.time.pause_min)}` : "-"} />
                <Row k={`Faktureret tid · ${d.price.time.rounding}`} v={<b>{fmtMin(d.price.time.billable_min)}</b>} />
              </div>
            )}

            <div className={`${card} p-4 text-sm`}>
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Fakta</div>
              <Row k="Start – slut" v={`${d.start_time || "-"} – ${d.end_time || "-"}`} />
              <Row k="Dagtype" v={`${options.day_types[d.day_type]} · ${d.holiday_source}`} />
              <Row k="Opgavetype" v={options.task_types[d.task_type] || d.task_type} />
              <Row k="Prioritet" v={options.priorities[d.priority] || d.priority} />
              <Row k="Hænger" v={d.trailer ? "Med hænger" : "Uden hænger"} />
              <Row k="Ventetid" v={d.waiting_min ? `${d.waiting_min} min` : "-"} />
              <Row k="Leveringsadresse" v={d.delivery_label || "-"} />
              {d.container_label && <Row k="Containerstørrelse" v={d.container_label} />}
              {d.outcome === "not_completed" && <Row k="Udfald" v={<span className="text-red-600 font-semibold">Forgæves</span>} />}
            </div>

            {!d.price.locked && !edit && (
              <button className={`${btnGhost} w-full justify-center`} onClick={startEdit}><Edit2 className="w-4 h-4" /> Tilpas tur eller pris</button>
            )}
            {edit && (
              <div className={`${card} p-4 space-y-3`}>
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Tilpas</div>
                <div className="grid grid-cols-2 gap-2">
                  <div><span className={label}>Start</span><input type="time" className={input} value={edit.start_time} placeholder={d.original.start_time} onChange={e => setEdit({ ...edit, start_time: e.target.value })} /></div>
                  <div><span className={label}>Slut</span><input type="time" className={input} value={edit.end_time} onChange={e => setEdit({ ...edit, end_time: e.target.value })} /></div>
                  <div><span className={label}>Hænger</span>
                    <select className={input} value={edit.used_trailer} onChange={e => setEdit({ ...edit, used_trailer: e.target.value })}>
                      <option value="">Som registreret</option><option value="true">Med hænger</option><option value="false">Uden hænger</option>
                    </select></div>
                  <div><span className={label}>Ventetid (min)</span><input type="number" min="0" className={input} value={edit.waiting_min} onChange={e => setEdit({ ...edit, waiting_min: e.target.value })} /></div>
                  <div className="col-span-2"><span className={label}>Pause under turen</span>
                    <select className={input} value={edit.deduct_pause} onChange={e => setEdit({ ...edit, deduct_pause: e.target.value })}>
                      <option value="">Som prisreglen siger</option><option value="true">Træk pause fra</option><option value="false">Pause tæller med</option>
                    </select></div>
                </div>
                <div>
                  <span className={label}>Pris</span>
                  <Segmented value={edit.mode} onChange={v => setEdit({ ...edit, mode: v })} options={[{ value: "rules", label: "Beregn efter regler" }, { value: "fixed", label: "Fast beløb" }]} />
                  {edit.mode === "fixed" && <input type="number" min="0" className={`${input} mt-2`} placeholder="Beløb ekskl. moms" value={edit.amount} onChange={e => setEdit({ ...edit, amount: e.target.value })} />}
                </div>
                <div>
                  <span className={label}>Ekstra linjer</span>
                  {edit.extra_lines.map((x, i) => (
                    <div key={i} className="flex gap-2 mb-2">
                      <input className={input} placeholder="Fx Ekstra rengøring" value={x.label} onChange={e => { const l = [...edit.extra_lines]; l[i] = { ...x, label: e.target.value }; setEdit({ ...edit, extra_lines: l }); }} />
                      <input type="number" className={`${input} w-32`} placeholder="kr" value={x.amount} onChange={e => { const l = [...edit.extra_lines]; l[i] = { ...x, amount: e.target.value }; setEdit({ ...edit, extra_lines: l }); }} />
                      <button className="p-2 text-slate-400 hover:text-red-600" onClick={() => setEdit({ ...edit, extra_lines: edit.extra_lines.filter((_, j) => j !== i) })}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  ))}
                  <button className="text-xs font-semibold text-emerald-700 dark:text-emerald-300" onClick={() => setEdit({ ...edit, extra_lines: [...edit.extra_lines, { label: "", amount: "" }] })}>+ Tilføj linje</button>
                </div>
                <div><span className={label}>Begrundelse (påkrævet)</span><input className={input} value={edit.note} onChange={e => setEdit({ ...edit, note: e.target.value })} placeholder="Fx aftalt med kunden pr. telefon" /></div>
                <div className="flex gap-2 justify-end">
                  <button className={btnGhost} onClick={() => setEdit(null)}>Annuller</button>
                  <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem</button>
                </div>
              </div>
            )}

            {(d.requests?.length > 0 || d.history?.length > 0) && (
              <div className={`${card} p-4 text-sm space-y-2`}>
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Historik</div>
                {d.requests.map(r => (
                  <div key={r.id} className="text-xs border-l-2 border-amber-400 pl-2">
                    <b>{r.driver_name}</b> anmodede om rettelse · {new Date(r.created_at).toLocaleString("da-DK")} · <b>{{ pending: "Afventer", approved: "Godkendt", rejected: "Afvist" }[r.status]}</b>
                    <div className="text-slate-500">"{r.comment}"</div>
                  </div>
                ))}
                {[...d.history].reverse().map((h, i) => (
                  <div key={i} className="text-xs border-l-2 border-blue-400 pl-2">
                    <b>{h.by}</b> · {new Date(h.at).toLocaleString("da-DK")}<div className="text-slate-500">{h.note}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const Row = ({ k, v }) => (
  <div className="flex justify-between gap-3 py-1 border-b border-slate-100 dark:border-slate-700 last:border-0">
    <span className="text-slate-500">{k}</span><span className="text-right">{v}</span>
  </div>
);

/* ======================================================================
   Prisregler
   ====================================================================== */
const EMPTY_COND = { customer_ids: [], location_codes: [], delivery_labels: [], materials: [], task_types: [], priorities: [], day_types: [], container_labels: [], trailer: "", time_from: "", time_to: "", outcome: "completed" };

function ruleSummary(rule, options) {
  if (rule.kind === "base") {
    const p = rule.pricing || {};
    if (p.model === "fixed") return `Fast pris ${fmtKr(p.amount)}`;
    if (p.model === "per_container") return `${fmtKr(p.amount)} pr. container`;
    const parts = [`${fmtKr(p.hourly_rate)}/t`];
    if (p.start_fee) parts.push(`start ${fmtKr(p.start_fee)}`);
    if (p.min_minutes) parts.push(`min. ${p.min_minutes} min`);
    if (p.min_amount) parts.push(`min. ${fmtKr(p.min_amount)}`);
    if (p.rounding_mode !== "none") parts.push(`${{ up: "op", down: "ned", nearest: "nærmeste" }[p.rounding_mode]} til ${p.rounding_minutes} min`);
    parts.push(p.deduct_pause ? "pause trækkes fra" : "pause tæller med");
    return `Timepris ${parts.join(" · ")}`;
  }
  const s = rule.surcharge || {};
  const v = s.unit === "percent" ? `+${s.value}%` : s.unit === "per_hour" ? `+${fmtKr(s.value)}/t` : `+${fmtKr(s.value)}`;
  return `${options.categories[rule.category] || "Tillæg"} ${v}`;
}

function conditionChips(c, options) {
  const out = [];
  const nameOf = (list, key = "id", nameKey = "name") => (v) => (list.find(x => x[key] === v) || {})[nameKey] || v;
  if (c.customer_ids?.length) out.push(c.customer_ids.map(nameOf(options.customers)).join(", "));
  if (c.location_codes?.length) out.push(c.location_codes.map(nameOf(options.locations, "code")).join(", "));
  if (c.delivery_labels?.length) out.push("→ " + c.delivery_labels.join(", "));
  if (c.materials?.length) out.push(c.materials.join(", "));
  if (c.task_types?.length) out.push(c.task_types.map(t => options.task_types[t] || t).join(", "));
  if (c.priorities?.length) out.push(c.priorities.map(p => options.priorities[p]).join(", "));
  if (c.day_types?.length) out.push(c.day_types.map(d => options.day_types[d]).join(", "));
  if (c.trailer) out.push(c.trailer === "with" ? "Med hænger" : "Uden hænger");
  if (c.container_labels?.length) out.push(c.container_labels.join(", "));
  if (c.time_from && c.time_to) out.push(`Start ${c.time_from}–${c.time_to}`);
  if (c.outcome === "not_completed") out.push("Forgæves ture");
  if (c.outcome === "any") out.push("Gennemført + forgæves");
  return out;
}

function RulesView({ options, reloadOptions, canEdit = true, initialFilter = "all" }) {
  const [rules, setRules] = useState(null);
  const [history, setHistory] = useState({});
  const [filter, setFilter] = useState(initialFilter);
  const [editing, setEditing] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);

  const load = useCallback(async () => {
    try { setRules((await axios.get(`${API}/pricing/rules`)).data); }
    catch (e) { toast.error(formatApiError(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const importLegacy = async () => {
    try {
      const { data } = await axios.post(`${API}/pricing/import-legacy`);
      toast.success(`${data.created} regler importeret fra den gamle prisliste`);
      load(); reloadOptions();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  // 2026-10-17: Standard er at reglen ophører fra nu - eksisterende ture
  // beholder deres pris. "Slet helt" fjerner den også bagudrettet.
  const remove = async (id, effective = "now") => {
    try {
      await axios.delete(`${API}/pricing/rules/${id}`, { params: { effective } });
      toast.success(effective === "all" ? "Regel slettet helt" : "Reglen gælder ikke for nye ture");
      setConfirmDel(null); load();
    }
    catch (e) { toast.error(formatApiError(e)); }
  };
  const toggleHistory = async (r) => {
    if (history[r.id]) { setHistory(h => ({ ...h, [r.id]: null })); return; }
    try { const { data } = await axios.get(`${API}/pricing/rules/${r.id}/history`); setHistory(h => ({ ...h, [r.id]: data })); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  const toggleActive = async (r) => {
    try { await axios.put(`${API}/pricing/rules/${r.id}`, { ...r, active: !r.active }); load(); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  if (!rules) return <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  const visible = rules.filter(r => {
    if (filter === "all") return true;
    if (filter === "general") return !(r.conditions?.customer_ids || []).length;
    if (filter === "own") {
      const ownIds = new Set(options.customers.filter(c => c.own).map(c => c.id));
      return (r.conditions?.customer_ids || []).some(id => ownIds.has(id));
    }
    return (r.conditions?.customer_ids || []).includes(filter);
  });
  const base = visible.filter(r => r.kind === "base");
  const sur = visible.filter(r => r.kind === "surcharge");

  const RuleCard = ({ r }) => (
    <div className={`${card} p-4 flex flex-col sm:flex-row sm:items-start gap-3 ${r.active ? "" : "opacity-60"}`}>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold">{r.name}</span>
          <InfoTip text={ruleHelp(r)} own={r.note} />
          {!r.active && <span className="px-2 py-0.5 rounded-full text-[11px] bg-slate-200 dark:bg-slate-700">Inaktiv</span>}
          {(r.valid_from || r.valid_to) && <span className="px-2 py-0.5 rounded-full text-[11px] bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200" title="Kørselsdato">Kørt {r.valid_from || "…"} → {r.valid_to || "…"}</span>}
          {r.version_from && new Date(r.version_from) > new Date() && <span className="px-2 py-0.5 rounded-full text-[11px] bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200">Træder i kraft {fmtTs(r.version_from)}</span>}
          {r.version_to && <span className="px-2 py-0.5 rounded-full text-[11px] bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">Ophører {fmtTs(r.version_to)}</span>}
        </div>
        {(r.version_from || r.versions > 1) && (
          <div className="text-[11px] text-slate-500 mt-0.5">
            {r.version_from ? `Gælder for ture oprettet fra ${fmtTs(r.version_from)}` : "Gælder for alle ture"}
            {r.versions > 1 && <> · <button className="underline" onClick={() => toggleHistory(r)}>{history[r.id] ? "Skjul" : "Vis"} {r.versions - 1} tidligere version{r.versions - 1 === 1 ? "" : "er"}</button></>}
          </div>
        )}
        {history[r.id] && (
          <ul className="mt-2 space-y-1 border-l-2 border-slate-200 dark:border-slate-700 pl-3">
            {history[r.id].filter(v => v.id !== r.id).map(v => (
              <li key={v.id} className="text-xs text-slate-600 dark:text-slate-300">
                <span className="font-semibold">{ruleSummary(v, options)}</span>
                <span className="text-slate-400"> · ture oprettet {v.version_from ? `fra ${fmtTs(v.version_from)}` : "før"} {v.version_to ? `til ${fmtTs(v.version_to)}` : ""}{v.updated_by ? ` · ${v.updated_by}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="text-sm text-emerald-700 dark:text-emerald-300 font-semibold mt-0.5">{ruleSummary(r, options)}</div>
        <div className="flex flex-wrap gap-1 mt-2">
          {conditionChips(r.conditions || {}, options).map((c, i) => <span key={i} className="px-2 py-0.5 rounded-full text-[11px] bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">{c}</span>)}
          {conditionChips(r.conditions || {}, options).length === 0 && <span className="px-2 py-0.5 rounded-full text-[11px] bg-slate-100 dark:bg-slate-700 text-slate-500">Gælder alle ture</span>}
        </div>
      </div>
      {canEdit && <div className="flex items-center gap-1 shrink-0">
        <button title={r.active ? "Deaktivér" : "Aktivér"} onClick={() => toggleActive(r)} className={`w-10 h-6 rounded-full relative transition-colors ${r.active ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}`}>
          <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${r.active ? "left-[18px]" : "left-0.5"}`} />
        </button>
        <button title="Rediger" className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" onClick={() => setEditing(r)}><Edit2 className="w-4 h-4" /></button>
        <button title="Kopiér" className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" onClick={() => setEditing({ ...r, id: undefined, name: `${r.name} (kopi)` })}><Copy className="w-4 h-4" /></button>
        {confirmDel === r.id ? (
          <div className="flex flex-col sm:flex-row gap-1">
            <button className="px-2 py-1 rounded-lg bg-amber-600 text-white text-xs font-bold" title="Eksisterende ture beholder prisen" onClick={() => remove(r.id, "now")}>Stop fra nu</button>
            <button className="px-2 py-1 rounded-lg bg-red-600 text-white text-xs font-bold" title="Fjernes også fra eksisterende ture der ikke er faktureret" onClick={() => remove(r.id, "all")}>Slet helt</button>
            <button className="px-2 py-1 rounded-lg text-xs" onClick={() => setConfirmDel(null)}>Annuller</button>
          </div>
        ) : <button title="Slet" className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600" onClick={() => setConfirmDel(r.id)}><Trash2 className="w-4 h-4" /></button>}
      </div>}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className={`${card} p-4 flex flex-wrap items-center justify-between gap-3`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">Vis regler for</span>
          <select className={`${input} w-auto min-w-[220px]`} value={filter} onChange={e => setFilter(e.target.value)} data-testid="rules-filter">
            <option value="all">Alle regler</option>
            <option value="general">Generelle (gælder alle kunder)</option>
            {options.customers.some(c => c.own) && <option value="own">Alle egne kunder</option>}
            {options.customers.some(c => !c.own) && (
              <optgroup label="Genbrugsplads-kunder">
                {options.customers.filter(c => !c.own).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </optgroup>
            )}
            {options.customers.some(c => c.own) && (
              <optgroup label="Egne kunder">
                {options.customers.filter(c => c.own).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </optgroup>
            )}
          </select>
        </div>
        {canEdit && <button className={btnPrimary} onClick={() => setEditing({ kind: "base", name: "", conditions: { ...EMPTY_COND, customer_ids: !["all", "general", "own"].includes(filter) ? [filter] : [] }, pricing: { model: "fixed", amount: "" }, active: true })}>
          <Plus className="w-4 h-4" /> Ny regel
        </button>}
      </div>

      <div className="flex gap-2 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-900 text-sm text-sky-900 dark:text-sky-100">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          <b>Sådan virker det:</b> Hver tur får én <b>grundpris</b> - den mest specifikke regel der passer vinder (kunde &gt; lokation &gt; leveringsadresse &gt; opgavetype &gt; materiale).
          Derefter lægges <b>tillæg</b> oveni - højst ét pr. type (fx ét weekendtillæg), igen det mest specifikke. Et kundespecifikt tillæg på 0 kr fritager altså kunden.
        </div>
      </div>

      {rules.length === 0 && options.legacy_prices > 0 && (
        <div className={`${card} p-4 flex flex-wrap items-center justify-between gap-3`}>
          <span className="text-sm">Du har {options.legacy_prices} priser fra den gamle prisliste. Vil du importere dem som regler?</span>
          <button className={btnGhost} onClick={importLegacy}>Importér gamle priser</button>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Grundpriser ({base.length})</h3>
        {base.length === 0 && <div className={`${card} p-6 text-sm text-slate-500 text-center`}>Ingen grundpriser endnu. Start med en generel regel uden betingelser - så har alle ture en pris.</div>}
        {base.map(r => <RuleCard key={r.id} r={r} />)}
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Tillæg ({sur.length})</h3>
        {sur.length === 0 && <div className={`${card} p-6 text-sm text-slate-500 text-center`}>Ingen tillæg endnu (fx weekend, helligdag, haster, hænger, aften eller ventetid).</div>}
        {sur.map(r => <RuleCard key={r.id} r={r} />)}
      </div>
      {editing && <RuleEditor rule={editing} options={options} firstRule={rules.length === 0} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}

/* ======================================================================
   Kunder & priser (2026-10-17): ét sted at se alle kunder - genbrugsplads-
   kunder og logistikfirmaets egne kunder - og hvilke priser de har.
   ====================================================================== */
const EMPTY_CUST = { name: "", cvr: "", address: "", contact: "", phone: "", email: "", note: "" };

function CustomerForm({ initial, onCancel, onSaved }) {
  const [f, setF] = useState({ ...EMPTY_CUST, ...(initial || {}) });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.name.trim()) { toast.error("Skriv kundens navn"); return; }
    setBusy(true);
    try {
      if (initial?.id) await axios.put(`${API}/logistics/customers/${initial.id}`, f);
      else await axios.post(`${API}/logistics/customers`, f);
      toast.success(initial?.id ? "Kunden er opdateret" : "Kunden er oprettet");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    setBusy(false);
  };
  const fld = (k, l, ph, extra = {}) => (
    <div><span className={label}>{l}</span><input className={input} value={f[k] || ""} placeholder={ph} onChange={e => setF({ ...f, [k]: e.target.value })} {...extra} /></div>
  );
  return (
    <div className="p-4 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/20 space-y-3" data-testid="customer-form">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {fld("name", "Navn", "Fx Carlsberg Byen A/S", { autoFocus: true })}
        {fld("cvr", "CVR (valgfri)", "12345678", { inputMode: "numeric" })}
        {fld("address", "Adresse (valgfri)", "Vej, postnr. by")}
        {fld("contact", "Kontaktperson", "Valgfri")}
        {fld("phone", "Telefon", "Valgfri", { inputMode: "tel" })}
        {fld("email", "E-mail", "Valgfri", { type: "email" })}
      </div>
      <div><span className={label}>Note (valgfri)</span><input className={input} value={f.note || ""} onChange={e => setF({ ...f, note: e.target.value })} placeholder="Fx faktureres månedligt" /></div>
      {initial?.id && f.name.trim() !== initial.name && <p className="text-xs text-amber-700">Navnet ændres også på kundens ture og prisregler.</p>}
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onCancel}>Annuller</button>
        <button className={btnPrimary} disabled={busy} onClick={save}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem</button>
      </div>
    </div>
  );
}

function CustomersView({ options, reloadOptions, canEdit, goRules }) {
  const [rules, setRules] = useState(null);
  const [registered, setRegistered] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editingCust, setEditingCust] = useState(null);
  const [newRuleFor, setNewRuleFor] = useState(null);

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([axios.get(`${API}/pricing/rules`), axios.get(`${API}/logistics/customers`)]);
      setRules(r.data); setRegistered(c.data || []);
    } catch (e) { toast.error(formatApiError(e)); setRules([]); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const reloadAll = () => { load(); reloadOptions(); };

  if (!rules) return <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  const countFor = (id) => rules.filter(r => (r.conditions?.customer_ids || []).includes(id));
  const general = rules.filter(r => !(r.conditions?.customer_ids || []).length);
  const regById = Object.fromEntries(registered.map(c => [c.id, c]));
  const recycling = options.customers.filter(c => !c.own);
  const own = options.customers.filter(c => c.own && c.id.startsWith("firma:"));
  const noCustomer = options.customers.find(c => c.own && !c.id.startsWith("firma:"));

  const Row = ({ c, kind }) => {
    const list = countFor(c.id);
    const base = list.filter(r => r.kind === "base").length;
    const sur = list.length - base;
    const reg = c.registered_id ? regById[c.registered_id] : null;
    return (
      <li className={`px-4 py-3 ${c.inactive ? "opacity-60" : ""}`} data-testid={`customer-row-${c.name}`}>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-slate-900 dark:text-white">{c.name}</span>
              {kind === "own" && !reg && <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500" title="Fundet på egne ture - ikke oprettet i kunderegistret">Fra ture</span>}
              {c.inactive && <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">Skjult</span>}
            </div>
            <div className="text-xs mt-0.5">
              {list.length === 0
                ? <span className="text-slate-500">Følger de generelle priser ({general.length} regler)</span>
                : <span className="text-emerald-700 dark:text-emerald-300 font-semibold">Egen prisaftale: {base} grundpris{base === 1 ? "" : "er"}{sur ? `, ${sur} tillæg` : ""} - resten følger de generelle</span>}
              {reg && (reg.cvr || reg.contact || reg.phone) && <span className="text-slate-400"> · {[reg.cvr && `CVR ${reg.cvr}`, reg.contact, reg.phone].filter(Boolean).join(" · ")}</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            {list.length > 0 && <button className={btnGhost} onClick={() => goRules(c.id)}><Tag className="w-4 h-4" /> Se priser</button>}
            {canEdit && <button className={btnPrimary} onClick={() => setNewRuleFor(c)} data-testid={`customer-price-${c.name}`}><Plus className="w-4 h-4" /> {list.length ? "Tilføj pris" : "Sæt egen pris"}</button>}
            {reg && <button className={btnGhost} onClick={() => setEditingCust(reg)} title="Ret kundeoplysninger"><Edit2 className="w-4 h-4" /></button>}
            {reg && reg.active !== false && (
              <button className={btnGhost} title="Skjul kunden (ture og priser bevares)" onClick={async () => {
                if (!window.confirm(`Skjul ${reg.name}? Ture og priser bevares.`)) return;
                try { await axios.delete(`${API}/logistics/customers/${reg.id}`); reloadAll(); } catch (e) { toast.error(formatApiError(e)); }
              }}><PowerOff className="w-4 h-4" /></button>
            )}
          </div>
        </div>
        {editingCust && reg && editingCust.id === reg.id && (
          <div className="mt-3"><CustomerForm initial={reg} onCancel={() => setEditingCust(null)} onSaved={() => { setEditingCust(null); reloadAll(); }} /></div>
        )}
      </li>
    );
  };

  return (
    <div className="space-y-4" data-testid="customers-view">
      <div className="flex gap-2 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-900 text-sm text-sky-900 dark:text-sky-100">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          <b>Sådan sætter du priser pr. kunde:</b> De <b>generelle regler</b> gælder alle kunder. Tryk <b>"Sæt egen pris"</b> ud for en kunde for at lave en regel, der kun gælder den kunde -
          den vinder altid over den generelle. Du kan lave én enkelt afvigelse (fx kun timeprisen) eller en hel prismodel for kunden (grundpris + tillæg).
          Alle betingelser (lokation, materiale, opgavetype, dag, tid, hænger …) kan kombineres med kunden.
        </div>
      </div>

      <section className={`${card} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between gap-2">
          <h3 className="font-bold flex items-center gap-2"><Tag className="w-4 h-4 text-slate-400" /> Generelle priser</h3>
          <button className={btnGhost} onClick={() => goRules("general")}>Se {general.length} regler</button>
        </div>
        <p className="px-4 py-3 text-sm text-slate-500">Gælder alle kunder, der ikke har en egen regel for den samme slags tur.</p>
      </section>

      {recycling.length > 0 && (
        <section className={`${card} overflow-hidden`}>
          <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700">
            <h3 className="font-bold flex items-center gap-2"><Building2 className="w-4 h-4 text-slate-400" /> Genbrugsplads-kunder</h3>
            <p className="text-xs text-slate-500">Kunder der har købt systemet og bruger jer som logistikpartner. Ture kommer fra deres bestillinger.</p>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">{recycling.map(c => <Row key={c.id} c={c} kind="recycling" />)}</ul>
        </section>
      )}

      <section className={`${card} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-bold flex items-center gap-2"><Users className="w-4 h-4 text-slate-400" /> Egne kunder</h3>
            <p className="text-xs text-slate-500">Jeres egne slutkunder på egne ture (fx byggefirmaer). Opret dem her, så kan de vælges under "Ny tur" og få egne priser - også før den første tur.</p>
          </div>
          {canEdit && !adding && <button className={btnPrimary} onClick={() => setAdding(true)} data-testid="customer-add"><Plus className="w-4 h-4" /> Ny kunde</button>}
        </div>
        {adding && <div className="p-4 border-b border-slate-100 dark:border-slate-700"><CustomerForm onCancel={() => setAdding(false)} onSaved={() => { setAdding(false); reloadAll(); }} /></div>}
        {own.length === 0 && !adding && <p className="px-4 py-6 text-sm text-slate-500 text-center">Ingen egne kunder endnu.</p>}
        <ul className="divide-y divide-slate-100 dark:divide-slate-700">
          {own.map(c => <Row key={c.id} c={c} kind="own" />)}
          {noCustomer && <Row c={{ ...noCustomer, name: "Egne ture uden kunde" }} kind="none" />}
        </ul>
      </section>

      {newRuleFor && (
        <RuleEditor
          rule={{ kind: "base", name: `${newRuleFor.name} - pris`, conditions: { ...EMPTY_COND, customer_ids: [newRuleFor.id] }, pricing: { model: "fixed", amount: "" }, active: true }}
          options={options} firstRule={rules.length === 0}
          onClose={() => setNewRuleFor(null)} onSaved={() => { setNewRuleFor(null); load(); }} />
      )}
    </div>
  );
}

function RuleEditor({ rule, options, onClose, onSaved, firstRule = false }) {
  // 2026-10-17: Hvornår ændringen gælder. "now" = kun ture oprettet fra nu
  // (eksisterende ture beholder prisen), "all" = også eksisterende ture der
  // ikke er faktureret, eller en dato.
  const [effective, setEffective] = useState(firstRule ? "all" : "now");
  const [effDate, setEffDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [r, setR] = useState(() => ({
    kind: rule.kind || "base", name: rule.name || "", category: rule.category || "weekend",
    conditions: { ...EMPTY_COND, ...(rule.conditions || {}) },
    pricing: { model: "fixed", amount: "", hourly_rate: "", start_fee: "", min_minutes: "", min_amount: "", rounding_mode: "up", rounding_minutes: 15, deduct_pause: true, ...(rule.pricing || {}) },
    surcharge: { unit: "kr", value: "", ...(rule.surcharge || {}) },
    valid_from: rule.valid_from || "", valid_to: rule.valid_to || "", active: rule.active !== false, note: rule.note || "",
  }));
  const [more, setMore] = useState(() => {
    const c = rule.conditions || {};
    return !!(c.delivery_labels?.length || c.priorities?.length || c.trailer || c.container_labels?.length || c.time_from || (c.outcome && c.outcome !== "completed") || rule.valid_from || rule.valid_to);
  });
  const [saving, setSaving] = useState(false);
  const setC = (k, v) => setR(x => ({ ...x, conditions: { ...x.conditions, [k]: v } }));
  const setP = (k, v) => setR(x => ({ ...x, pricing: { ...x.pricing, [k]: v } }));
  const c = r.conditions;

  const locs = options.locations.filter(l => !c.customer_ids.length || c.customer_ids.includes(l.customer_id));
  const customRounding = ![15, 30, 60].includes(Number(r.pricing.rounding_minutes));

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...r, effective: effective === "date" ? effDate : effective };
      if (rule.id) await axios.put(`${API}/pricing/rules/${rule.id}`, body);
      else await axios.post(`${API}/pricing/rules`, body);
      toast.success("Regel gemt");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const preview = (() => {
    const chips = conditionChips(c, options);
    const what = r.kind === "base" ? ruleSummary({ kind: "base", pricing: r.pricing }, options) : ruleSummary({ kind: "surcharge", category: r.category, surcharge: r.surcharge }, options);
    return `${chips.length ? chips.join(" · ") : "Alle ture"}: ${what}`;
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/40 p-0 sm:p-4" onClick={onClose}>
      <div className="w-full sm:max-w-2xl max-h-[100dvh] sm:max-h-[92vh] overflow-y-auto bg-white dark:bg-slate-800 sm:rounded-2xl shadow-2xl" onClick={e => e.stopPropagation()} data-testid="rule-editor">
        <div className="sticky top-0 z-10 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-5 py-4 flex items-center justify-between">
          <h3 className="font-bold text-lg">{rule.id ? "Rediger regel" : "Ny prisregel"}</h3>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-5">
          <div className="space-y-3">
            <Segmented value={r.kind} onChange={v => setR({ ...r, kind: v })} options={[{ value: "base", label: "Grundpris" }, { value: "surcharge", label: "Tillæg" }]} />
            <p className="text-xs text-slate-500">{r.kind === "base" ? HELP.base : HELP.surcharge}</p>
            {r.kind === "surcharge" && (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(options.categories).map(([k, v]) => (
                    <button key={k} type="button" className={`${chipBase} ${r.category === k ? chipOn : chipOff}`} onClick={() => setR({ ...r, category: k })}>{v}</button>
                  ))}
                </div>
                {HELP.category[r.category] && <p className="text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-900 rounded-lg px-3 py-2">{HELP.category[r.category]}</p>}
              </>
            )}
            <div><span className={label}>Navn</span><input className={input} value={r.name} onChange={e => setR({ ...r, name: e.target.value })} placeholder={r.kind === "base" ? "Fx ARGO Roskilde - afhentning" : "Fx Weekendtillæg"} /></div>
          </div>

          <div className="space-y-3">
            <h4 className="text-sm font-bold">Gælder for <span className="font-normal text-slate-500">(tomt = alle)</span></h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MultiPick title="Kunder" items={options.customers.map(x => ({ value: x.id, label: x.own ? `${x.name} · egen kunde` : x.name }))} value={c.customer_ids} onChange={v => setC("customer_ids", v)} allLabel="Alle kunder" />
              <MultiPick title="Lokationer" items={locs.map(x => ({ value: x.code, label: x.name }))} value={c.location_codes} onChange={v => setC("location_codes", v)} allLabel="Alle lokationer" />
              <MultiPick title="Opgavetype" items={Object.entries(options.task_types).map(([k, v]) => ({ value: k, label: v }))} value={c.task_types} onChange={v => setC("task_types", v)} />
              <MultiPick title="Materiale" items={options.materials.map(m => ({ value: m, label: m }))} value={c.materials} onChange={v => setC("materials", v)} allLabel="Alle materialer" />
              <MultiPick title="Dagtype" items={Object.entries(options.day_types).map(([k, v]) => ({ value: k, label: v }))} value={c.day_types} onChange={v => setC("day_types", v)} allLabel="Alle dage" />
            </div>
            <button type="button" className="text-sm font-semibold text-emerald-700 dark:text-emerald-300" onClick={() => setMore(m => !m)}>{more ? "− Færre betingelser" : "+ Flere betingelser (leveringsadresse, prioritet, hænger, tidsrum, ...)"}</button>
            {more && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <MultiPick title="Leveringsadresse" items={options.delivery_labels.map(m => ({ value: m, label: m }))} value={c.delivery_labels} onChange={v => setC("delivery_labels", v)} />
                <MultiPick title="Prioritet" items={Object.entries(options.priorities).map(([k, v]) => ({ value: k, label: v }))} value={c.priorities} onChange={v => setC("priorities", v)} />
                <MultiPick title="Containerstørrelse" items={options.container_labels.map(m => ({ value: m, label: m }))} value={c.container_labels} onChange={v => setC("container_labels", v)} />
                <div><span className={label}>Hænger</span>
                  <Segmented value={c.trailer} onChange={v => setC("trailer", v)} options={[{ value: "", label: "Ligegyldigt" }, { value: "with", label: "Med" }, { value: "without", label: "Uden" }]} /></div>
                <div><span className={label}>Turen starter i tidsrummet</span>
                  <div className="flex items-center gap-2">
                    <input type="time" className={input} value={c.time_from} onChange={e => setC("time_from", e.target.value)} />
                    <span>–</span>
                    <input type="time" className={input} value={c.time_to} onChange={e => setC("time_to", e.target.value)} />
                  </div>
                  <span className="text-[11px] text-slate-500">Fx 18:00–06:00 for aften/nat</span></div>
                <div><span className={label}>Udfald</span>
                  <Segmented value={c.outcome} onChange={v => setC("outcome", v)} options={[{ value: "completed", label: "Gennemført" }, { value: "not_completed", label: "Forgæves" }, { value: "any", label: "Begge" }]} /></div>
                <div><span className={label}>Kørselsdato fra</span><input type="date" className={input} value={r.valid_from} onChange={e => setR({ ...r, valid_from: e.target.value })} /></div>
                <div><span className={label}>Kørselsdato til</span><input type="date" className={input} value={r.valid_to} onChange={e => setR({ ...r, valid_to: e.target.value })} /></div>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <h4 className="text-sm font-bold">Pris</h4>
            {r.kind === "base" ? (
              <>
                <Segmented value={r.pricing.model} onChange={v => setP("model", v)} options={Object.entries(options.models).map(([k, v]) => ({ value: k, label: v }))} />
                {HELP.model[r.pricing.model] && <p className="text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-900 rounded-lg px-3 py-2">{HELP.model[r.pricing.model]}</p>}
                {r.pricing.model !== "hourly" ? (
                  <div className="max-w-xs"><span className={label}>{r.pricing.model === "per_container" ? "Pris pr. container (kr)" : "Pris pr. tur (kr)"}</span>
                    <input type="number" min="0" className={input} value={r.pricing.amount} onChange={e => setP("amount", e.target.value)} /></div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div><span className={label}>Timepris (kr)</span><input type="number" min="0" className={input} value={r.pricing.hourly_rate} onChange={e => setP("hourly_rate", e.target.value)} /></div>
                    <div><span className={label}>Startgebyr</span><input type="number" min="0" className={input} placeholder="Valgfri" value={r.pricing.start_fee || ""} onChange={e => setP("start_fee", e.target.value)} /></div>
                    <div><span className={label}>Min. minutter</span><input type="number" min="0" className={input} placeholder="Valgfri" value={r.pricing.min_minutes || ""} onChange={e => setP("min_minutes", e.target.value)} /></div>
                    <div><span className={label}>Min. beløb</span><input type="number" min="0" className={input} placeholder="Valgfri" value={r.pricing.min_amount || ""} onChange={e => setP("min_amount", e.target.value)} /></div>
                    <div className="col-span-2 md:col-span-4">
                      <span className={label}>Afrunding af tiden</span>
                      <div className="flex flex-wrap items-center gap-2">
                        <Segmented value={r.pricing.rounding_mode} onChange={v => setP("rounding_mode", v)} options={[{ value: "none", label: "Ingen" }, { value: "up", label: "Op" }, { value: "nearest", label: "Nærmeste" }, { value: "down", label: "Ned" }]} />
                        {r.pricing.rounding_mode !== "none" && (
                          <>
                            {[15, 30, 60].map(m => <button key={m} type="button" className={`${chipBase} ${Number(r.pricing.rounding_minutes) === m ? chipOn : chipOff}`} onClick={() => setP("rounding_minutes", m)}>{m} min</button>)}
                            <input type="number" min="1" max="240" className={`${input} w-24 ${customRounding ? "ring-2 ring-emerald-500/40" : ""}`} value={r.pricing.rounding_minutes} onChange={e => setP("rounding_minutes", e.target.value)} />
                            <span className="text-xs text-slate-500">min</span>
                          </>
                        )}
                      </div>
                    </div>
                    <label className="col-span-2 md:col-span-4 flex items-center gap-2 text-sm">
                      <input type="checkbox" className="accent-emerald-600 w-4 h-4" checked={!!r.pricing.deduct_pause} onChange={e => setP("deduct_pause", e.target.checked)} />
                      Træk pauser fra (pauser chaufføren starter under "Tid" mens turen kører)
                    </label>
                  </div>
                )}
              </>
            ) : (
              <div className="flex flex-wrap items-end gap-3">
                <Segmented value={r.surcharge.unit} onChange={v => setR({ ...r, surcharge: { ...r.surcharge, unit: v } })} options={[{ value: "kr", label: "kr pr. tur" }, { value: "percent", label: "% af grundpris" }, { value: "per_hour", label: "kr pr. time" }]} />
                <div className="w-36"><span className={label}>Værdi</span><input type="number" min="0" className={input} value={r.surcharge.value} onChange={e => setR({ ...r, surcharge: { ...r.surcharge, value: e.target.value } })} /></div>
                {r.category === "waiting" && <span className="text-xs text-slate-500">Ventetid afregnes pr. påbegyndt kvarter ud fra minutter registreret på turen.</span>}
              </div>
            )}
          </div>

          <div>
            <span className={label}>Jeres forklaring (valgfri - vises ved ⓘ på reglen)</span>
            <textarea rows={2} maxLength={1000} className={input} value={r.note} onChange={e => setR({ ...r, note: e.target.value })}
              placeholder="Fx: Aftalt med ARGO i rammeaftale 2026. Gælder kun containere over 20 m³." data-testid="rule-note" />
          </div>
          <div className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="accent-emerald-600 w-4 h-4" checked={r.active} onChange={e => setR({ ...r, active: e.target.checked })} id="rule-active" />
            <label htmlFor="rule-active">Aktiv</label>
          </div>
          <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900 text-sm"><b>Opsummering:</b> {preview}</div>
          <div className="space-y-2" data-testid="rule-effective">
            <h4 className="text-sm font-bold">Hvornår gælder {rule.id ? "ændringen" : "reglen"}?</h4>
            <Segmented value={effective} onChange={setEffective} options={[
              { value: "now", label: "Nye ture fra nu" },
              { value: "date", label: "Fra en dato" },
              { value: "all", label: "Også eksisterende ture" },
            ]} />
            {effective === "date" && (
              <div className="max-w-xs"><span className={label}>Ture oprettet fra</span><input type="date" className={input} value={effDate} onChange={e => setEffDate(e.target.value)} /></div>
            )}
            <p className="text-xs text-slate-500">
              {effective === "now" && "Ture og bestillinger der allerede er oprettet beholder deres pris i rapporter og PDF. Den gamle pris gemmes som en tidligere version."}
              {effective === "date" && "Gælder for ture oprettet fra den valgte dato. Ture fra før beholder den gamle pris."}
              {effective === "all" && "Ændrer også prisen på eksisterende ture der ikke er markeret som faktureret. Fakturerede ture ændres aldrig."}
            </p>
          </div>
        </div>
        <div className="sticky bottom-0 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 px-5 py-3 flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Annuller</button>
          <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem regel</button>
        </div>
      </div>
    </div>
  );
}

/* ======================================================================
   Godkendelser
   ====================================================================== */
function ApprovalsView({ onChanged }) {
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState(null);
  const [rejecting, setRejecting] = useState(null);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try { setItems((await axios.get(`${API}/pricing/requests?status=${status}`)).data); }
    catch (e) { toast.error(formatApiError(e)); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const decide = async (id, approve) => {
    try {
      await axios.post(`${API}/pricing/requests/${id}/decide`, { approve, note });
      toast.success(approve ? "Rettelsen er godkendt" : "Rettelsen er afvist");
      setRejecting(null); setNote(""); load(); onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const diff = (r) => {
    const b = r.before || {}, c = r.changes || {};
    const out = [];
    if ("start_time" in c) out.push(["Start", b.start_time || "-", c.start_time]);
    if ("end_time" in c) out.push(["Slut", b.end_time || "-", c.end_time]);
    if ("used_trailer" in c) out.push(["Hænger", b.used_trailer ? "Med" : "Uden", c.used_trailer ? "Med" : "Uden"]);
    if ("waiting_min" in c) out.push(["Ventetid", `${b.waiting_min || 0} min`, `${c.waiting_min} min`]);
    return out;
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5">
        {[["pending", "Afventer"], ["approved", "Godkendt"], ["rejected", "Afvist"]].map(([v, l]) => (
          <button key={v} className={`${chipBase} ${status === v ? chipOn : chipOff}`} onClick={() => setStatus(v)}>{l}</button>
        ))}
      </div>
      {!items ? <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
        : items.length === 0 ? <div className={`${card} p-10 text-center text-sm text-slate-500`}>{status === "pending" ? "Ingen rettelser venter. Chauffører kan anmode om rettelser på afsluttede ture." : "Ingen her endnu."}</div>
          : items.map(r => (
            <div key={r.id} className={`${card} p-4 space-y-3`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-bold">{r.driver_name} <span className="font-normal text-slate-500">· {fmtDate(r.service_date)} · {r.tour_number}</span></div>
                  <div className="text-sm text-slate-500">{r.tour_label}</div>
                </div>
                <span className="text-xs text-slate-500">{new Date(r.created_at).toLocaleString("da-DK")}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {diff(r).map(([k, from, to]) => (
                  <div key={k} className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900 text-sm">
                    <div className="text-[11px] font-bold uppercase text-slate-500">{k}</div>
                    <span className="line-through text-slate-400">{from}</span> → <b>{to}</b>
                  </div>
                ))}
              </div>
              <div className="text-sm italic text-slate-600 dark:text-slate-300">"{r.comment}"</div>
              {r.status === "pending" ? (
                rejecting === r.id ? (
                  <div className="flex flex-wrap gap-2">
                    <input className={`${input} flex-1 min-w-[200px]`} placeholder="Hvorfor afvises den?" value={note} onChange={e => setNote(e.target.value)} />
                    <button className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold" onClick={() => decide(r.id, false)}><Ban className="w-4 h-4" /> Afvis</button>
                    <button className={btnGhost} onClick={() => { setRejecting(null); setNote(""); }}>Annuller</button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button className={btnPrimary} onClick={() => decide(r.id, true)}><Check className="w-4 h-4" /> Godkend</button>
                    <button className={btnGhost} onClick={() => setRejecting(r.id)}><Ban className="w-4 h-4" /> Afvis</button>
                  </div>
                )
              ) : (
                <div className="text-xs text-slate-500">{r.status === "approved" ? "Godkendt" : "Afvist"} af {r.decided_by} · {new Date(r.decided_at).toLocaleString("da-DK")}{r.decision_note ? ` · "${r.decision_note}"` : ""}</div>
              )}
            </div>
          ))}
    </div>
  );
}

/* ======================================================================
   Helligdage
   ====================================================================== */
function HolidaysView({ profile }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [newDay, setNewDay] = useState({ date: "", name: "" });

  const load = useCallback(async () => {
    try { setData((await axios.get(`${API}/pricing/holidays?year=${year}`)).data); }
    catch (e) { toast.error(formatApiError(e)); }
  }, [year]);
  useEffect(() => { load(); }, [load]);

  const save = async (patch) => {
    try { await axios.put(`${API}/pricing/settings`, patch); load(); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  if (!data) return <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  const s = data.settings;
  const keyByName = Object.fromEntries(Object.entries(data.optional_keys).map(([k, v]) => [v, k]));

  const toggleDay = (d) => {
    if (d.kind === "optional") {
      const key = keyByName[d.name];
      const cur = new Set(s.holiday_optional || []);
      cur.has(key) ? cur.delete(key) : cur.add(key);
      save({ holiday_optional: Array.from(cur) });
    } else if (d.kind === "official") {
      const cur = new Set(s.holiday_excluded || []);
      cur.has(d.date) ? cur.delete(d.date) : cur.add(d.date);
      save({ holiday_excluded: Array.from(cur) });
    }
  };
  const addExtra = () => {
    if (!newDay.date) { toast.error("Vælg en dato"); return; }
    save({ holiday_extra: [...(s.holiday_extra || []), { date: newDay.date, name: newDay.name || "Ekstra fridag" }] });
    setNewDay({ date: "", name: "" });
  };
  const removeExtra = (date) => save({ holiday_extra: (s.holiday_extra || []).filter(x => x.date !== date) });
  const KIND = { official: ["Officiel", "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200"], optional: ["Valgfri", "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200"], extra: ["Egen dag", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"] };

  return (
    <div className="space-y-4">
      {!profile?.has_connections ? (
        <div className={`${card} p-4 text-sm text-slate-600 dark:text-slate-300`}>
          <b>Din helligdagskalender herunder bruges til alle ture.</b> Bliver I tilknyttet en genbrugsplads-kunde,
          kan I her vælge at bruge kundens egen kalender for netop den kundes ture.
        </div>
      ) : (
      <div className={`${card} p-4 space-y-3`}>
        <h3 className="font-bold">Hvilken kalender bestemmer om en dag er helligdag?</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {[["customer_first", "Kundens kalender først", "Lokationens helligdagskalender (den samme som bestillingssiden bruger) → kundens helligdagsgruppe → din egen kalender herunder, hvis kunden ikke har nogen."],
            ["own", "Altid min egen kalender", "Kun kalenderen herunder bruges, uanset hvad kunderne har sat op."]].map(([v, t, desc]) => (
            <button key={v} onClick={() => save({ holiday_source: v })} className={`text-left p-3 rounded-xl border-2 ${s.holiday_source === v ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30" : "border-slate-200 dark:border-slate-700"}`}>
              <div className="font-semibold text-sm">{t}</div><div className="text-xs text-slate-500 mt-1">{desc}</div>
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500">Kundens kalender gælder kun for den kundes ture - dine egne ture bruger altid din egen kalender. Om et tillæg gælder på helligdage styres i prisreglerne (dagtype "Helligdag"), så et helligdagstillæg kan gælde for ét materiale eller én kunde og ikke for andre.</p>
      </div>
      )}

      <div className={`${card} overflow-hidden`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
          <h3 className="font-bold">Min helligdagskalender</h3>
          <div className="flex items-center gap-2">
            <button className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" onClick={() => setYear(y => y - 1)}><ChevronLeft className="w-4 h-4" /></button>
            <span className="font-bold w-12 text-center">{year}</span>
            <button className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" onClick={() => setYear(y => y + 1)}><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
        <div className="px-4 py-2 text-xs text-slate-500 bg-slate-50 dark:bg-slate-900/40">Danske helligdage beregnes automatisk for hvert år (også påske og pinse). Slå dage til/fra, eller tilføj jeres egne.</div>
        {data.days.map(d => (
          <div key={d.date} className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-slate-100 dark:border-slate-700">
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-mono text-sm w-32 shrink-0 whitespace-nowrap">{fmtDate(d.date)}</span>
              <span className={`text-sm ${d.active ? "" : "text-slate-400 line-through"}`}>{d.name}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${KIND[d.kind][1]}`}>{KIND[d.kind][0]}</span>
            </div>
            {d.kind === "extra" ? (
              <button className="p-1.5 rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30" onClick={() => removeExtra(d.date)}><Trash2 className="w-4 h-4" /></button>
            ) : (
              <button onClick={() => toggleDay(d)} className={`w-10 h-6 rounded-full relative transition-colors shrink-0 ${d.active ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}`}>
                <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${d.active ? "left-[18px]" : "left-0.5"}`} />
              </button>
            )}
          </div>
        ))}
        <div className="flex flex-wrap gap-2 px-4 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40">
          <input type="date" className={`${input} w-44`} value={newDay.date} onChange={e => setNewDay({ ...newDay, date: e.target.value })} />
          <input className={`${input} flex-1 min-w-[160px]`} placeholder="Navn, fx Firmafest" value={newDay.name} onChange={e => setNewDay({ ...newDay, name: e.target.value })} />
          <button className={btnPrimary} onClick={addExtra}><Plus className="w-4 h-4" /> Tilføj dag</button>
        </div>
      </div>
    </div>
  );
}

/* ======================================================================
   Indstillinger
   ====================================================================== */
function SettingsView() {
  const [s, setS] = useState(null);
  useEffect(() => { axios.get(`${API}/pricing/settings`).then(r => setS(r.data)).catch(e => toast.error(formatApiError(e))); }, []);
  const save = async (patch) => {
    try { setS((await axios.put(`${API}/pricing/settings`, patch)).data); toast.success("Gemt"); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  if (!s) return <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  return (
    <div className="space-y-4">
      <div className={`${card} p-4 space-y-3`}>
        <h3 className="font-bold flex items-center gap-2"><Truck className="w-4 h-4" /> Samtidige ture (timepris)</h3>
        <p className="text-sm text-slate-500">Med hænger kan en chauffør have flere ture i gang på samme tid. Hvordan skal den fælles tid afregnes?</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {[["split", "Fordel tiden ligeligt", "1 time med 2 ture i gang = 30 min på hver tur. Ingen kunde betaler for den samme time to gange."],
            ["full", "Fuld tid på hver tur", "1 time med 2 ture i gang = 1 time på hver tur."]].map(([v, t, desc]) => (
            <button key={v} onClick={() => save({ concurrent_mode: v })} className={`text-left p-3 rounded-xl border-2 ${s.concurrent_mode === v ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30" : "border-slate-200 dark:border-slate-700"}`}>
              <div className="font-semibold text-sm">{t}</div><div className="text-xs text-slate-500 mt-1">{desc}</div>
            </button>
          ))}
        </div>
      </div>
      <div className={`${card} p-4 space-y-2`}>
        <h3 className="font-bold">Moms</h3>
        <p className="text-sm text-slate-500">Priser i reglerne er ekskl. moms. Rapporten viser moms separat.</p>
        <div className="flex items-center gap-2">
          <input type="number" min="0" max="100" className={`${input} w-28`} defaultValue={s.vat_percent} onBlur={e => Number(e.target.value) !== s.vat_percent && save({ vat_percent: Number(e.target.value) })} />
          <span className="text-sm">%</span>
        </div>
      </div>
    </div>
  );
}
