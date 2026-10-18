import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Plus, ChevronLeft, ChevronRight, Search, X, Loader2, MessageSquare, AlertTriangle,
  Clock, MapPin, Truck, User, Flag, MoreHorizontal, Upload, Download, Copy, Trash2,
  RotateCcw, Edit2, Check, ChevronDown, History, CalendarDays, Package2, Building2, Navigation,
} from "lucide-react";
import { API, formatApiError } from "../auth/api";
import { ArchiveTab } from "./LocationAdminPage";
import TourChat from "../components/TourChat";
import AddressField, { formatAddress, parseAddress } from "../components/AddressField";
import {
  TOUR_TYPES, GOODS_TYPES, TOUR_TYPE_LABEL, SOURCE_LABEL, cargoSummary, isGoods, stopsOf, stopsDone, parseDk, todayStr, addDays, fmtDayLong, fmtClock, deviationsOf,
  isHaster, openHours, capacityText, assigneeName, tourStatus, daysLate, mapsUrl,
} from "../lib/tourHelpers";

/**
 * Ture - logistik admins daglige arbejdsflade (2026-10-16).
 * Erstatter "Manuelle ture" (plads-først, Excel-først, skrivebeskyttet
 * tildeling) og Arkiv > Ture. Alt for én dag samles ét sted:
 *   - alle kilder (manuelle, bestillinger, ARGO) grupperet pr. lokation
 *   - opmærksomhedslinje: haster uden chauffør, ture fra tidligere dage,
 *     "kan ikke gennemføres", ulæste beskeder
 *   - tildeling direkte i listen og som masse-handling
 *   - tur-panel med tidslinje og beskedtråd til chaufføren
 *   - ny tur: én formular med flere stop og gentagelse
 *   - Historik (tidligere Arkiv > Ture) og Excel-import som sekundære valg
 */

const card = "bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm";
const inputCls = "w-full px-3 py-2.5 sm:py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";
const labelCls = "block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1";
const btnPrimary = "inline-flex items-center justify-center gap-1.5 px-4 py-2.5 sm:py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-50";
const btnGhost = "inline-flex items-center justify-center gap-1.5 px-3 py-2.5 sm:py-2 rounded-lg border border-slate-200 dark:border-slate-600 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50";
const btnDanger = "inline-flex items-center justify-center gap-1.5 px-3 py-2.5 sm:py-2 rounded-lg border border-rose-200 dark:border-rose-900 text-sm font-semibold text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 disabled:opacity-50";

const STATUS_FILTERS = [
  { id: "all", label: "Alle" },
  { id: "open", label: "Ikke tildelt" },
  { id: "assigned", label: "Tildelt" },
  { id: "onway", label: "På vej" },
  { id: "done", label: "Færdig" },
  { id: "blocked", label: "Kan ikke gennemføres" },
];

const customerOf = (t, ownName) =>
  t.customer_name || (t.is_private && t.private_company ? t.private_company : "") || ownName || "Egne ture";

// ─────────────────────────── små byggesten ───────────────────────────

function Sheet({ open, onClose, title, subtitle, children, footer, wide = false, testid }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-[70]" data-testid={testid}>
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]" onClick={onClose} />
      <div className={`absolute right-0 top-0 bottom-0 w-full ${wide ? "sm:max-w-2xl" : "sm:max-w-xl"} bg-slate-50 dark:bg-slate-900 shadow-2xl flex flex-col`}
        style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className="px-4 sm:px-6 py-3 sm:py-4 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white truncate">{title}</h2>
            {subtitle && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="p-2 -mr-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500" aria-label="Luk" data-testid="sheet-close">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">{children}</div>
        {footer && <div className="px-4 sm:px-6 py-3 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

function Confirm({ state, onClose }) {
  const [busy, setBusy] = useState(false);
  if (!state) return null;
  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-slate-900/50" onClick={() => !busy && onClose()} />
      <div className="relative w-full sm:max-w-md bg-white dark:bg-slate-800 rounded-t-2xl sm:rounded-2xl shadow-2xl p-5" style={{ paddingBottom: "max(20px, env(safe-area-inset-bottom))" }}>
        <h3 className="text-base font-bold text-slate-900 dark:text-white">{state.title}</h3>
        <p className="text-sm text-slate-600 dark:text-slate-300 mt-1.5">{state.text}</p>
        <div className="mt-5 flex gap-2 justify-end">
          <button className={btnGhost} disabled={busy} onClick={onClose}>Annuller</button>
          <button
            className={state.danger ? "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold disabled:opacity-50" : btnPrimary}
            disabled={busy}
            data-testid="confirm-ok"
            onClick={async () => { setBusy(true); try { await state.onOk(); } finally { setBusy(false); onClose(); } }}>
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} {state.okLabel || "OK"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function Menu({ items, label = "Flere handlinger", testid }) {
  const [open, setOpen] = useState(false);
  const btn = useRef(null);
  const menu = useRef(null);
  const [rect, setRect] = useState(null);
  useEffect(() => {
    if (!open) return;
    const up = () => btn.current && setRect(btn.current.getBoundingClientRect());
    up();
    const close = (e) => {
      if (btn.current?.contains(e.target) || menu.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    window.addEventListener("resize", up);
    window.addEventListener("scroll", up, true);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      window.removeEventListener("resize", up);
      window.removeEventListener("scroll", up, true);
    };
  }, [open]);
  return (
    <>
      <button ref={btn} onClick={() => setOpen(v => !v)} className={btnGhost} aria-label={label} title={label} data-testid={testid}>
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {open && rect && createPortal(
        <div ref={menu} role="menu"
          className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl py-1.5"
          style={{ position: "fixed", top: rect.bottom + 6, right: Math.max(8, window.innerWidth - rect.right), minWidth: 250, zIndex: 1000 }}>
          {items.filter(Boolean).map(it => (
            <button key={it.label} role="menuitem" disabled={it.disabled}
              onClick={() => { setOpen(false); it.onClick(); }}
              className={`w-full text-left flex items-center gap-3 px-4 py-3 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700/50 disabled:opacity-40 ${it.danger ? "text-rose-600" : "text-slate-700 dark:text-slate-200"}`}>
              <it.icon className={`w-4 h-4 ${it.danger ? "text-rose-500" : "text-slate-400"}`} /> {it.label}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}

function DriverSelect({ value, drivers, load, onChange, disabled, compact = false, testid }) {
  return (
    <select
      value={value || ""}
      disabled={disabled}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      className={`${compact ? "py-1.5 text-sm" : "py-2.5 sm:py-2 text-base sm:text-sm"} w-full px-2 rounded-lg border bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 disabled:opacity-60 ${
        value ? "border-indigo-200 dark:border-indigo-900 text-indigo-700 dark:text-indigo-300 font-semibold" : "border-dashed border-slate-300 dark:border-slate-600 text-slate-500"
      }`}
    >
      <option value="">Ikke tildelt</option>
      {drivers.map(d => (
        <option key={d.id} value={d.id}>{d.name}{load && load[d.id] ? ` (${load[d.id]})` : ""}</option>
      ))}
    </select>
  );
}

// ─────────────────────────── Ny / ret tur ───────────────────────────

const WEEKDAYS = [["1", "Man"], ["2", "Tir"], ["3", "Ons"], ["4", "Tor"], ["5", "Fre"], ["6", "Lør"], ["0", "Søn"]];
const UNITS = ["stk", "paller", "kolli", "m³", "ton", "kg"];
const KIND_KEY = "cf_tour_kind_default";
const readKind = () => { try { return localStorage.getItem(KIND_KEY) === "goods" ? "goods" : "container"; } catch (_) { return "container"; } };

const blankForm = (date, plads) => ({
  date, plads: plads || "", firma: "", kind: readKind(), tour_type: readKind() === "goods" ? "afhentning" : "normal",
  lines: [{ text: "", trailer: "", qty: "", unit: "stk" }], container: "", capacity_label: "", loose_count: "",
  stops: [{ street: "", postal: "", city: "" }], deliveries: [{ street: "", postal: "", city: "" }], separate: false,
  open_from: "", open_to: "", priority: "normal", driver_id: "", remark: "", trailer_count: 0,
  agreed_price: "", agreed_add_waiting: true, agreed_split: false, capture_qty: null, capture_photo: false, create_customer: true,
  repeat: "none", repeat_days: ["1", "2", "3", "4", "5"], repeat_until: addDays(date, 28),
});

function repeatDates(f) {
  if (f.repeat === "none") return [f.date];
  const out = [];
  let d = f.date;
  const until = f.repeat_until || f.date;
  for (let i = 0; i < 120 && d <= until; i++) {
    const wd = String(new Date(`${d}T12:00:00`).getDay());
    if (f.repeat === "daily" ? (wd !== "0" && wd !== "6") : f.repeat_days.includes(wd)) out.push(d);
    d = addDays(d, 1);
  }
  return out;
}

const addrFilled = (a) => !!((a?.street || "").trim() || (a?.city || "").trim());
// Et stop med note/kontakt tæller også (fx aflevering på lokationen med "port 3").
const stopFilled = (a) => addrFilled(a) || !!((a?.note || "").trim() || (a?.contact_name || "").trim() || (a?.contact_phone || "").trim());
const addrOnly = (a) => ({ street: a?.street || "", postal: a?.postal || "", city: a?.city || "" });

/** 2026-10-18: Kunde-navne der ligner hinanden ("Carlsberg Byen" ~ "Carlsberg byen A/S"). */
const normCust = (s) => (s || "").toLowerCase().replace(/\b(a\/s|aps|i\/s|as|ivs|k\/s)\b/g, "").replace(/[^a-z0-9æøå]+/g, " ").trim();
const lev = (a, b) => {
  if (Math.abs(a.length - b.length) > 3) return 9;
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
};
const similarCustomers = (name, list) => {
  const n = normCust(name);
  if (n.length < 3) return [];
  return list.filter(c => {
    const m = normCust(c.name);
    return m === n || (m.length >= 4 && (m.includes(n) || n.includes(m))) || (n.length > 4 && lev(m, n) <= 2);
  }).slice(0, 3);
};

/** Note og kontakt på et stop (valgfrit, foldet sammen). */
function StopExtras({ value, onChange }) {
  const v = value || {};
  const [open, setOpen] = useState(!!(v.note || v.contact_name || v.contact_phone));
  if (!open) return <button type="button" className="mt-2 text-xs font-semibold text-slate-500 underline" onClick={() => setOpen(true)} data-testid="stop-extras-open">+ Note / kontakt på stoppet</button>;
  return (
    <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
      <input className={`${inputCls} sm:col-span-3`} value={v.note || ""} onChange={(e) => onChange({ ...v, note: e.target.value })} placeholder="Note til stoppet, fx port 3" maxLength={200} data-testid="stop-note" />
      <input className={`${inputCls} sm:col-span-2`} value={v.contact_name || ""} onChange={(e) => onChange({ ...v, contact_name: e.target.value })} placeholder="Kontaktperson" maxLength={80} />
      <input className={inputCls} type="tel" inputMode="tel" value={v.contact_phone || ""} onChange={(e) => onChange({ ...v, contact_phone: e.target.value })} placeholder="Telefon" maxLength={20} data-testid="stop-phone" />
    </div>
  );
}

/**
 * Ny tur (2026-10-17). Det man altid skal bruge står fremme; resten ligger
 * under "Flere detaljer". Feltsættet følger turens type:
 *  - Container: genbrugsplads-kundens plads (B2B) eller premium-firmaets
 *    egne containerture - materiale, container nr., kapacitet.
 *  - Gods og andet (kun premium, egne lokationer): "hvad skal køres" med
 *    antal/enhed, ingen containerfelter.
 * Hængere og indhold pr. hænger er premium-funktioner.
 */
function TourForm({ open, onClose, initialDate, pladsList, drivers, materials, defaultPlads, onCreated, siteWord, canPrice = false, customers = [], isPremium = false }) {
  const [f, setF] = useState(() => blankForm(initialDate, defaultPlads));
  const [saving, setSaving] = useState(false);
  const [more, setMore] = useState(false);
  useEffect(() => { if (open) { setF(blankForm(initialDate, defaultPlads)); setMore(false); } }, [open, initialDate, defaultPlads]);
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }));
  const plads = pladsList.find(p => p.name === f.plads);
  // Egen lokation hos et premium-firma = frit valg af type. Kundens plads = container (B2B).
  const canChooseKind = isPremium && (!plads || !!plads.own_location);
  const kind = canChooseKind ? f.kind : "container";
  const goods = kind === "goods";
  const types = goods ? GOODS_TYPES : TOUR_TYPES;
  const tc = isPremium ? Number(f.trailer_count || 0) : 0;
  const multiLines = goods || tc >= 2;
  const dates = repeatDates(f);
  const stops = f.stops.filter(addrFilled);
  const deliveries = f.deliveries.filter(stopFilled);
  // Én opgave = én tur. Kun hvis brugeren beder om det, laves én tur pr. afhentningsadresse.
  const separate = f.separate && stops.length > 1;
  const total = dates.length * (separate ? stops.length : 1);
  const lines = f.lines.filter(l => (l.text || "").trim());
  // Ved afslutning: standard = mængde ved containerafhentning (vægt) og på
  // gods når en linje har et antal (fx 12 paller skal afstemmes).
  const qtyDefault = goods ? lines.some(l => parseDk(l.qty) > 0) : (f.tour_type === "normal" || f.tour_type === "loes_afhentning");
  const captureQty = f.capture_qty === null ? qtyDefault : f.capture_qty;
  const unitsInUse = Array.from(new Set(lines.map(l => (goods ? (l.unit || "stk") : "kg"))));

  const setKind = (k) => {
    try { localStorage.setItem(KIND_KEY, k); } catch (_) { /* ignore */ }
    setF(prev => ({ ...prev, kind: k, tour_type: k === "goods" ? "afhentning" : "normal" }));
  };
  const setLine = (i, patch) => set("lines", f.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const firmaTrim = f.firma.trim();
  const regMatch = customers.find(c => c.name.toLowerCase() === firmaTrim.toLowerCase());
  const lookAlikes = firmaTrim && !regMatch ? similarCustomers(firmaTrim, customers) : [];
  const agreedN = canPrice && f.agreed_price !== "" && !isNaN(parseDk(f.agreed_price)) ? parseDk(f.agreed_price) : null;

  const submit = async () => {
    if (!f.plads) { toast.error(`Vælg ${siteWord.toLowerCase()}`); return; }
    if (!lines.length) { toast.error(goods ? "Skriv hvad der skal køres" : "Skriv materiale/fraktion"); return; }
    if (!stops.length) { toast.error("Skriv afhentningsadressen"); return; }
    if (f.tour_type === "loes_afhentning" && !(parseInt(f.loose_count, 10) > 0)) { toast.error("Skriv antal containere"); return; }
    if (dates.length === 0) { toast.error("Gentagelsen giver ingen datoer"); return; }
    if (total > 200) { toast.error("Højst 200 ture ad gangen"); return; }
    const firma = f.firma.trim();
    // 2026-10-18: Kunden kobles til kunderegistret, så en stavefejl ikke giver
    // en "ny" kunde uden pris. Nye navne oprettes i registret (valgfrit).
    let customerRef = regMatch ? regMatch.id : "";
    if (firma && !regMatch && (!plads || plads.own_location) && f.create_customer) {
      try {
        const { data } = await axios.post(`${API}/logistics/customers`, { name: firma });
        customerRef = data.id;
      } catch (e) {
        if (e?.response?.status !== 409) toast.message?.("Kunden blev ikke oprettet i registret - turen gemmes alligevel");
      }
    }
    const lastDel = [...deliveries].reverse().find(addrFilled);
    const facility = lastDel ? formatAddress(lastDel) : f.plads;
    const stopList = (pickups) => [
      ...pickups.map(a => ({ kind: "pickup", ...a })),
      // Aflevering uden adresse = lokationen (som før), men note/kontakt bevares.
      ...deliveries.map(a => ({ kind: "delivery", ...a, ...(addrFilled(a) ? {} : { address: f.plads }) })),
    ];
    // Aftalt pris ved flere ture: pr. tur (standard) eller samlet beløb delt ligeligt.
    const nTours = dates.length * (separate ? stops.length : 1);
    const perTour = agreedN == null ? null : (f.agreed_split && nTours > 1 ? Math.floor((agreedN / nTours) * 100) / 100 : agreedN);
    const split = !!f.agreed_split && nTours > 1;
    // Ved deling får den sidste tur resten, så summen passer præcist.
    const prices = Array.from({ length: nTours }, (_, k) => (perTour == null ? null
      : split && k === nTours - 1 ? Math.round((agreedN - perTour * (nTours - 1)) * 100) / 100 : perTour));
    const seriesId = dates.length > 1 ? (window.crypto?.randomUUID?.() || `s-${Date.now()}`) : "";
    let idx = 0;
    const cargo = (multiLines || tc >= 1) ? lines.map(l => ({
      text: l.text.trim(), trailer: tc >= 2 && l.trailer ? Number(l.trailer) : (tc === 1 ? 1 : null),
      ...(goods ? { unit: l.unit || "stk" } : { unit: "kg" }),
      ...(goods && l.qty && !isNaN(parseDk(l.qty)) ? { qty: parseDk(l.qty) } : {}),
    })) : [];
    const body = [];
    const groups = separate ? stops.map(st => [st]) : [stops];
    dates.forEach(date => groups.forEach((pickups, i) => body.push({
      date, plads: f.plads, tour_kind: kind, tour_type: f.tour_type,
      fraction: cargo.length ? "" : lines[0].text.trim(), cargo_lines: cargo, trailer_count: tc,
      address: formatAddress(pickups[0]), address_parts: addrOnly(pickups[0]),
      facility, facility_parts: lastDel ? addrOnly(lastDel) : {},
      customer_ref_id: customerRef, series_id: seriesId,
      stops: stopList(pickups),
      container: goods ? "" : f.container.trim(), capacity_label: goods ? "" : f.capacity_label.trim(),
      open_from: f.open_from, open_to: f.open_to, priority: f.priority, remark: f.remark.trim(),
      is_private: !!firma, private_company: firma, sort_order: i,
      loose_estimated_count: f.tour_type === "loes_afhentning" ? (parseInt(f.loose_count, 10) || 0) : 0,
      capture: { quantity: captureQty, photo: !!f.capture_photo },
      ...(perTour != null ? { agreed_price: prices[idx++], agreed_add_waiting: !!f.agreed_add_waiting } : {}),
    })));
    setSaving(true);
    try {
      const r = await axios.post(`${API}/tours/bulk`, body);
      const ids = (r.data || []).map(t => t.id);
      if (f.driver_id && ids.length) {
        await axios.post(`${API}/tours/bulk-assign`, { tour_ids: ids, driver_id: f.driver_id });
      }
      toast.success(ids.length === 1 ? "Turen er oprettet" : `${ids.length} ture er oprettet`);
      onCreated(dates[0]);
      onClose();
    } catch (e) {
      toast.error(formatApiError(e));
    }
    setSaving(false);
  };

  const grouped = useMemo(() => ({
    own: pladsList.filter(p => p.own_location),
    cust: pladsList.filter(p => !p.own_location),
  }), [pladsList]);

  const moreSummary = [
    f.open_from && f.open_to ? `${f.open_from}–${f.open_to}` : "",
    tc ? `${tc} hænger${tc === 1 ? "" : "e"}` : "",
    f.agreed_price ? `${f.agreed_price} kr` : "",
    f.repeat !== "none" ? `Gentages ${dates.length} dage` : "",
  ].filter(Boolean);

  const chip = (on, extra = "") => `px-3 py-2 rounded-lg text-sm font-semibold border ${on ? "bg-emerald-600 border-emerald-600 text-white" : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300"} ${extra}`;

  return (
    <Sheet open={open} onClose={onClose} title="Ny tur" subtitle="Én opgave er én tur - også med flere stop. Gentagelse giver én tur pr. dag." testid="tour-form"
      footer={
        <div className="flex items-center gap-2">
          <div className="text-xs text-slate-500 flex-1">{total > 0 ? `${total} tur${total === 1 ? "" : "e"} oprettes` : ""}</div>
          <button className={btnGhost} onClick={onClose}>Annuller</button>
          <button className={btnPrimary} onClick={submit} disabled={saving} data-testid="tour-form-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Opret
          </button>
        </div>
      }>
      <section className={`${card} p-4 space-y-3`}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>{siteWord}</label>
            <select className={inputCls} value={f.plads} onChange={(e) => set("plads", e.target.value)} data-testid="tf-plads">
              <option value="">Vælg…</option>
              {grouped.own.length > 0 && <optgroup label="Egne lokationer">{grouped.own.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}</optgroup>}
              {grouped.cust.length > 0 && <optgroup label="Kunders pladser">{grouped.cust.map(p => <option key={p.id} value={p.name}>{p.name}{p.customer_name ? ` · ${p.customer_name}` : ""}</option>)}</optgroup>}
            </select>
          </div>
          <div>
            <label className={labelCls}>Dato</label>
            <input type="date" className={inputCls} value={f.date} onChange={(e) => set("date", e.target.value)} data-testid="tf-date" />
          </div>
        </div>
        {(!plads || plads.own_location) && (
          <div>
            <label className={labelCls}>Kunde <span className="normal-case font-normal">(valgfri - bruges til priser i Økonomi)</span></label>
            <input className={inputCls} list="tf-customers" value={f.firma} onChange={(e) => set("firma", e.target.value)} placeholder={customers.length ? "Vælg eller skriv en kunde" : "Fx Carlsberg Byen A/S"} data-testid="tf-firma" />
            <datalist id="tf-customers">{customers.map(c => <option key={c.id} value={c.name} />)}</datalist>
            {regMatch && <p className="text-[11px] text-emerald-700 mt-1">Kunde fra kunderegistret</p>}
            {firmaTrim && !regMatch && (
              <div className="mt-1.5 space-y-1.5" data-testid="tf-firma-new">
                {lookAlikes.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-amber-800 dark:text-amber-200">
                    <span>Mente du:</span>
                    {lookAlikes.map(c => <button key={c.id} type="button" className="px-2 py-1 rounded-full bg-amber-100 dark:bg-amber-900/40 font-semibold" onClick={() => set("firma", c.name)} data-testid="tf-firma-suggest">{c.name}</button>)}
                  </div>
                )}
                <label className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-300">
                  <input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={!!f.create_customer} onChange={(e) => set("create_customer", e.target.checked)} />
                  Opret "{firmaTrim}" som ny kunde i kunderegistret (så den kan få egne priser)
                </label>
              </div>
            )}
          </div>
        )}
        {plads && !plads.own_location && (
          <p className="text-xs text-slate-500 bg-slate-50 dark:bg-slate-900 rounded-lg px-3 py-2" data-testid="tf-owner-note">Turen bliver {plads.customer_name ? `${plads.customer_name}${/[sxz]$/i.test(plads.customer_name) ? "'" : "s"}` : "kundens"} tur: deres priser gælder, og de kan se den i deres arkiv.</p>
        )}
      </section>

      <section className={`${card} p-4 space-y-3`}>
        {canChooseKind && (
          <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-slate-900" data-testid="tf-kind">
            {[["container", "Container"], ["goods", "Gods og andet"]].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setKind(k)}
                className={`py-2 rounded-lg text-sm font-semibold ${kind === k ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-white" : "text-slate-500"}`}>{l}</button>
            ))}
          </div>
        )}
        <div>
          <label className={labelCls}>Opgave</label>
          <div className="flex flex-wrap gap-1.5">
            {types.map(t => (
              <button key={t.id} type="button" onClick={() => set("tour_type", t.id)} className={chip(f.tour_type === t.id)}>{t.label}</button>
            ))}
            <span className="w-px bg-slate-200 dark:bg-slate-700 mx-1" aria-hidden />
            <button type="button" onClick={() => set("priority", f.priority === "urgent" ? "normal" : "urgent")} data-testid="tf-haster"
              className={`px-3 py-2 rounded-lg text-sm font-bold border ${f.priority === "urgent" ? "bg-rose-600 border-rose-600 text-white" : "border-rose-200 text-rose-700 dark:border-rose-900 dark:text-rose-300"}`}>
              {f.priority === "urgent" ? "✓ Haster" : "Haster"}</button>
          </div>
        </div>
        <div>
          <label className={labelCls}>{goods ? "Hvad skal køres" : (multiLines ? "Materiale pr. hænger" : "Materiale / fraktion")}</label>
          <div className="space-y-2">
            {(multiLines ? f.lines : f.lines.slice(0, 1)).map((l, i) => (
              <div key={i} className="flex flex-wrap sm:flex-nowrap gap-2 items-center">
                <input className={`${inputCls} flex-1 min-w-[140px]`} list={goods ? undefined : "tf-materials"} value={l.text}
                  onChange={(e) => setLine(i, { text: e.target.value })} placeholder={goods ? "Fx Køkkenelementer" : "Fx Træ"} data-testid={`tf-line-${i}`} />
                {goods && (
                  <>
                    <input className={`${inputCls.replace("w-full ", "")} w-24 flex-none`} inputMode="decimal" value={l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} placeholder="Antal" />
                    <select className={`${inputCls.replace("w-full ", "")} w-28 flex-none`} value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })}>
                      {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                    </select>
                  </>
                )}
                {tc >= 2 && (
                  <select className={`${inputCls.replace("w-full ", "")} w-32 flex-none`} value={l.trailer} onChange={(e) => setLine(i, { trailer: e.target.value })} aria-label="Hænger">
                    <option value="">Hænger…</option>
                    {Array.from({ length: tc }, (_, k) => <option key={k} value={k + 1}>Hænger {k + 1}</option>)}
                  </select>
                )}
                {multiLines && f.lines.length > 1 && (
                  <button type="button" className="p-2 text-slate-400 hover:text-rose-500" aria-label="Fjern linje" onClick={() => set("lines", f.lines.filter((_, j) => j !== i))}><X className="w-4 h-4" /></button>
                )}
              </div>
            ))}
            {multiLines && (
              <button type="button" className="text-sm font-semibold text-emerald-700 dark:text-emerald-400 inline-flex items-center gap-1"
                onClick={() => set("lines", [...f.lines, { text: "", trailer: tc >= 2 ? String(Math.min(f.lines.length + 1, tc)) : "", qty: "", unit: "stk" }])}>
                <Plus className="w-4 h-4" /> {goods ? "Tilføj linje" : "Tilføj materiale"}
              </button>
            )}
            <datalist id="tf-materials">{(plads?.materials?.length ? plads.materials : materials).map(m => <option key={m} value={m} />)}</datalist>
          </div>
        </div>
        {f.tour_type === "loes_afhentning" && (
          <div className="max-w-[200px]">
            <label className={labelCls}>Antal containere</label>
            <input type="number" min="1" inputMode="numeric" className={inputCls} value={f.loose_count} onChange={(e) => set("loose_count", e.target.value)} />
          </div>
        )}
        {!goods && (
          <div className="grid grid-cols-2 gap-3">
            {f.tour_type !== "loes_afhentning" && <div><label className={labelCls}>Container nr.</label><input className={inputCls} value={f.container} onChange={(e) => set("container", e.target.value)} placeholder="Valgfri" data-testid="tf-container" /></div>}
            <div><label className={labelCls}>Kapacitet</label><input className={inputCls} value={f.capacity_label} onChange={(e) => set("capacity_label", e.target.value)} placeholder="Fx 20 m³" /></div>
          </div>
        )}
        <div className="rounded-xl bg-slate-50 dark:bg-slate-900 p-3 space-y-3" data-testid="tf-capture">
          <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Ved afslutning</div>
          {[
            ["capture_qty", "Skal chaufføren registrere mængde?", captureQty,
              goods ? `I linjens enhed${unitsInUse.length ? ` (${unitsInUse.join(", ")})` : ""} - fx hvor mange paller der faktisk blev kørt.` : "Vægt i kg (fx fra vejesedlen)."],
            ["capture_photo", "Skal chaufføren tage billede?", !!f.capture_photo, "Fx af læsset, containeren eller afleveringen."],
          ].map(([key, q, val, hint]) => (
            <div key={key} className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">{q}</div>
                <div className="text-[11px] text-slate-500">{hint}</div>
              </div>
              <div className="inline-flex p-0.5 rounded-lg bg-slate-200 dark:bg-slate-800" role="radiogroup" aria-label={q}>
                {[[true, "Ja"], [false, "Nej"]].map(([v, l]) => (
                  <button key={l} type="button" role="radio" aria-checked={val === v} onClick={() => set(key, v)} data-testid={`${key}-${v ? "yes" : "no"}`}
                    className={`px-4 py-1.5 rounded-md text-sm font-bold ${val === v ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500"}`}>{l}</button>
                ))}
              </div>
            </div>
          ))}
          <p className="text-[11px] text-slate-400">Chaufføren får en påmindelse hvis det mangler, men kan altid afslutte.</p>
        </div>
      </section>

      <section className={`${card} p-4 space-y-4`}>
        {[["stops", "Afhentning", "Tilføj afhentning"], ["deliveries", "Aflevering", "Tilføj aflevering"]].map(([key, title, addLabel]) => (
          <div key={key} className="space-y-3">
            <span className={labelCls}>{title}{f[key].length > 1 ? ` (${f[key].length} stop)` : ""}</span>
            {f[key].map((st, i) => (
              <div key={i} className="relative rounded-xl border border-slate-100 dark:border-slate-700 p-3">
                {f[key].length > 1 && (
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-500">{title} {i + 1}</span>
                    <button type="button" className="p-1 text-slate-400 hover:text-rose-500" aria-label="Fjern" onClick={() => set(key, f[key].filter((_, j) => j !== i))}><X className="w-4 h-4" /></button>
                  </div>
                )}
                <AddressField value={st} onChange={(v) => set(key, f[key].map((x, j) => (j === i ? { ...x, ...v } : x)))}
                  placeholder={key === "deliveries" && f.plads ? `Tom = ${f.plads}` : "Vej og nr."}
                  testid={key === "stops" ? `tf-stop-${i}` : `tf-delivery-${i}`} inputCls={inputCls} />
                <StopExtras value={st} onChange={(v) => set(key, f[key].map((x, j) => (j === i ? v : x)))} />
              </div>
            ))}
            <button type="button" className="text-sm font-semibold text-emerald-700 dark:text-emerald-400 inline-flex items-center gap-1"
              onClick={() => set(key, [...f[key], { street: "", postal: "", city: "" }])}><Plus className="w-4 h-4" /> {addLabel}</button>
          </div>
        ))}
        {stops.length > 1 && (
          <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-900 rounded-lg px-3 py-2.5">
            <input type="checkbox" className="w-4 h-4 mt-0.5 accent-emerald-600" checked={!!f.separate} onChange={(e) => set("separate", e.target.checked)} data-testid="tf-separate" />
            <span><b>Opret som separate ture</b> - én tur pr. afhentningsadresse (fx flere containere hos forskellige kunder, der kan køres af forskellige chauffører). Ellers er det <b>én tur med {stops.length + deliveries.length} stop</b>, som chaufføren krydser af undervejs.</span>
          </label>
        )}
      </section>

      <section className={`${card} p-4 space-y-3`}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Chauffør</label>
            <DriverSelect value={f.driver_id} drivers={drivers} onChange={(v) => set("driver_id", v)} testid="tf-driver" />
          </div>
          <div>
            <label className={labelCls}>Note til chaufføren</label>
            <input className={inputCls} value={f.remark} onChange={(e) => set("remark", e.target.value)} placeholder="Fx nøgle hos portvagten" />
          </div>
        </div>
      </section>

      <section className={`${card} overflow-hidden`}>
        <button type="button" onClick={() => setMore(v => !v)} className="w-full flex items-center gap-3 px-4 py-3 text-left" data-testid="tf-more">
          <span className="font-semibold text-slate-800 dark:text-slate-100">Flere detaljer</span>
          <span className="flex-1 text-xs text-slate-500 truncate">{moreSummary.join(" · ") || "Tidsrum, hængere, pris, gentagelse"}</span>
          <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${more ? "rotate-180" : ""}`} />
        </button>
        {more && (
          <div className="px-4 pb-4 space-y-4 border-t border-slate-100 dark:border-slate-700 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Tidligst</label><input type="time" className={inputCls} value={f.open_from} onChange={(e) => set("open_from", e.target.value)} /></div>
              <div><label className={labelCls}>Senest</label><input type="time" className={inputCls} value={f.open_to} onChange={(e) => set("open_to", e.target.value)} /></div>
            </div>
            {isPremium && (
              <div>
                <label className={labelCls}>Hængere</label>
                <div className="flex flex-wrap gap-1.5" data-testid="tf-trailers">
                  {[0, 1, 2, 3, 4].map(n => (
                    <button key={n} type="button" onClick={() => setF(prev => ({ ...prev, trailer_count: n,
                      lines: n >= 2 && prev.lines.length < n ? [...prev.lines, ...Array.from({ length: n - prev.lines.length }, (_, k) => ({ text: "", trailer: String(prev.lines.length + k + 1), qty: "", unit: "stk" }))].map((l, k) => ({ ...l, trailer: l.trailer || String(Math.min(k + 1, n)) })) : prev.lines }))}
                      className={chip(tc === n, "min-w-[52px]")}>{n === 0 ? "Ingen" : n}</button>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500 mt-1">{tc >= 2 ? "Skriv hvad der skal på hver hænger ovenfor. Prisen kan sættes samlet (aftalt pris) eller via prisregler for antal hængere." : "Planlagt antal hængere på turen."}</p>
              </div>
            )}

            {canPrice && (
              <div className="space-y-2">
                <label className={labelCls}>Aftalt pris pr. tur (kr, ekskl. moms)</label>
                <input type="text" inputMode="decimal" className={`${inputCls} max-w-[220px]`} value={f.agreed_price} onChange={(e) => set("agreed_price", e.target.value)} placeholder="Tom = prisreglerne" data-testid="tf-price" />
                {f.agreed_price !== "" && (isNaN(parseDk(f.agreed_price))
                  ? <p className="text-[11px] text-red-600">Ugyldigt beløb - skriv fx 1.100 eller 1100,50</p>
                  : <p className="text-[11px] text-emerald-700">= {parseDk(f.agreed_price).toLocaleString("da-DK", { minimumFractionDigits: 2 })} kr</p>)}
                {agreedN != null && total > 1 && (
                  <div className="rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 px-3 py-2 space-y-1.5" data-testid="tf-price-total">
                    <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">
                      {f.agreed_split
                        ? `${agreedN.toLocaleString("da-DK")} kr i alt · deles på ${total} ture = ca. ${(agreedN / total).toLocaleString("da-DK", { maximumFractionDigits: 2 })} kr pr. tur`
                        : `${agreedN.toLocaleString("da-DK")} kr pr. tur · ${total} ture = ${(agreedN * total).toLocaleString("da-DK")} kr i alt`}
                    </div>
                    <label className="flex items-center gap-2 text-xs text-amber-900 dark:text-amber-100">
                      <input type="checkbox" className="w-4 h-4 accent-amber-600" checked={!!f.agreed_split} onChange={(e) => set("agreed_split", e.target.checked)} data-testid="tf-price-split" />
                      Beløbet er samlet for alle {total} ture (deles ligeligt)
                    </label>
                  </div>
                )}
                <p className="text-[11px] text-slate-500">
                  Erstatter prisreglerne for {total > 1 ? (f.agreed_split ? "de oprettede ture (delt)" : "hver af de oprettede ture") : "hele turen"}{tc >= 2 ? ` (samlet for alle ${tc} hængere)` : ""}{!separate && stops.length + deliveries.length > 2 ? " inkl. alle stop" : ""}.
                  Tillæg som weekend og haster er indregnet. Senere ændringer af prisreglerne påvirker den ikke.
                </p>
                {f.agreed_price !== "" && (
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={!!f.agreed_add_waiting} onChange={(e) => set("agreed_add_waiting", e.target.checked)} />
                    Læg ventetid oveni, hvis chaufføren må vente (efter jeres ventetidsregel)
                  </label>
                )}
              </div>
            )}
            <div className="space-y-2">
              <label className={labelCls}>Gentag</label>
              <div className="grid grid-cols-3 gap-1.5 max-w-sm">
                {[["none", "Ingen"], ["daily", "Hverdage"], ["weekly", "Valgte dage"]].map(([id, l]) => (
                  <button key={id} type="button" onClick={() => set("repeat", id)} className={chip(f.repeat === id)}>{l}</button>
                ))}
              </div>
              {f.repeat === "weekly" && (
                <div className="flex flex-wrap gap-1.5">
                  {WEEKDAYS.map(([id, l]) => {
                    const on = f.repeat_days.includes(id);
                    return (
                      <button key={id} type="button" onClick={() => set("repeat_days", on ? f.repeat_days.filter(x => x !== id) : [...f.repeat_days, id])}
                        className={`w-12 py-2 rounded-lg text-sm font-semibold border ${on ? "bg-slate-800 text-white border-slate-800 dark:bg-slate-200 dark:text-slate-900" : "border-slate-200 dark:border-slate-600 text-slate-500"}`}>{l}</button>
                    );
                  })}
                </div>
              )}
              {f.repeat !== "none" && (
                <div className="grid grid-cols-2 gap-3 items-end max-w-sm">
                  <div><label className={labelCls}>Til og med</label><input type="date" className={inputCls} value={f.repeat_until} min={f.date} onChange={(e) => set("repeat_until", e.target.value)} /></div>
                  <div className="text-xs text-slate-500 pb-2">{dates.length} dag{dates.length === 1 ? "" : "e"}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </Sheet>
  );
}

// ─────────────────────────── Tur-panel ───────────────────────────

function Timeline({ tour, audit }) {
  const items = [];
  if (tour.created_at) items.push({ at: tour.created_at, label: `Oprettet${tour.created_by_name ? ` af ${tour.created_by_name}` : ""}`, tone: "slate" });
  (audit || []).forEach(a => {
    const name = a.after?.driver_name || "";
    const lbl = a.action === "release" ? "Frigivet - åben for alle" : a.action === "claim" ? `Taget af ${name}` : a.action === "unclaim" ? "Chaufføren slap turen" : `Tildelt ${name}`;
    items.push({ at: a.at, label: `${lbl}${a.user_name ? ` · ${a.user_name}` : ""}`, tone: "indigo" });
  });
  if (!audit?.length && tour.assigned_at) items.push({ at: tour.assigned_at, label: `Tildelt ${tour.driver_name || ""} af ${tour.assigned_by_name || ""}`, tone: "indigo" });
  if (tour.claimed_at) items.push({ at: tour.claimed_at, label: `Taget af ${tour.claimed_by || ""}`, tone: "indigo" });
  if (tour.on_way_time) items.push({ at: `${tour.date}T${tour.on_way_time.padStart(5, "0")}:00`, label: "På vej", tone: "amber", clock: tour.on_way_time });
  if (tour.completed && tour.time) items.push({ at: `${tour.date}T${tour.time.padStart(5, "0")}:00`, label: `Færdig${tour.weight ? ` · ${tour.weight} kg` : ""}`, tone: "emerald", clock: tour.time });
  if (tour.not_completed) items.push({ at: tour.not_completed_at, label: `Kan ikke gennemføres: ${tour.not_completed_comment || ""}`, tone: "rose" });
  if (tour.reactivated_at) items.push({ at: tour.reactivated_at, label: `Genaktiveret af ${tour.reactivated_by_name || ""}`, tone: "indigo" });
  items.sort((a, b) => String(a.at).localeCompare(String(b.at)));
  const dot = { slate: "bg-slate-400", indigo: "bg-indigo-500", amber: "bg-amber-500", emerald: "bg-emerald-500", rose: "bg-rose-500" };
  return (
    <ol className="relative border-l border-slate-200 dark:border-slate-700 ml-1.5 space-y-3">
      {items.map((it, i) => (
        <li key={i} className="ml-4">
          <span className={`absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full ${dot[it.tone]}`} />
          <div className="text-sm text-slate-800 dark:text-slate-100">{it.label}</div>
          <div className="text-[11px] text-slate-400">{it.clock || fmtClock(it.at)}</div>
        </li>
      ))}
    </ol>
  );
}

/** Hvad chaufføren skulle registrere og hvad der blev registreret (2026-10-17). */
function Registration({ tour }) {
  const [photos, setPhotos] = useState(null);
  const [big, setBig] = useState(null);
  const cap = tour.capture || {};
  const lines = Array.isArray(tour.cargo_lines) ? tour.cargo_lines : [];
  const planned = Number(tour.trailer_count || 0);
  const actual = tour.trailer_count_actual;
  useEffect(() => {
    setPhotos(null);
    if (!(tour.photo_count > 0)) return;
    axios.get(`${API}/tours/${tour.id}/photos`).then(r => setPhotos(r.data || [])).catch(() => setPhotos([]));
  }, [tour.id, tour.photo_count]);
  const anyActual = lines.some(l => l.actual_qty != null);
  if (!cap.quantity && !cap.photo && !anyActual && !(tour.photo_count > 0) && actual == null) return null;
  return (
    <div className="mt-4 rounded-xl bg-slate-50 dark:bg-slate-900 p-3 space-y-2" data-testid="panel-registration">
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">Registrering</div>
      {(cap.quantity || cap.photo) && (
        <div className="text-xs text-slate-500">Chaufføren skal registrere: {[cap.quantity && "mængde", cap.photo && "billede"].filter(Boolean).join(" og ")}</div>
      )}
      {lines.length > 0 && (cap.quantity || anyActual) && (
        <table className="w-full text-sm">
          <thead><tr className="text-[11px] text-slate-400"><th className="text-left font-semibold">Linje</th><th className="text-right font-semibold">Planlagt</th><th className="text-right font-semibold">Registreret</th></tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td className="py-0.5">{l.trailer ? `H${l.trailer} · ` : ""}{l.text}</td>
                <td className="text-right text-slate-500">{l.qty != null ? `${Number(l.qty).toLocaleString("da-DK")} ${l.unit || ""}` : "-"}</td>
                <td className={`text-right font-semibold ${l.actual_qty == null ? "text-slate-400" : (l.qty != null && Number(l.actual_qty) !== Number(l.qty) ? "text-amber-700" : "text-emerald-700")}`}>
                  {l.actual_qty == null ? (tour.completed ? "Ikke registreret" : "-") : `${Number(l.actual_qty).toLocaleString("da-DK")} ${l.unit || ""}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!lines.length && cap.quantity && <div className="text-sm">Vægt: <b>{tour.weight ? `${tour.weight} kg` : (tour.completed ? "ikke registreret" : "-")}</b></div>}
      {actual != null && <div className="text-sm">Hængere: planlagt {planned} · <b className={actual !== planned ? "text-amber-700" : ""}>kørt {actual}</b></div>}
      {cap.photo && !(tour.photo_count > 0) && tour.completed && <div className="text-sm text-amber-700">Intet billede taget</div>}
      {photos && photos.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {photos.map(p => (
            <button key={p.id} type="button" onClick={() => setBig(p.url)} className="w-20 h-20 rounded-lg overflow-hidden border border-slate-200">
              <img src={p.url} alt="Billede fra chaufføren" className="w-full h-full object-cover" />
            </button>
          ))}
        </div>
      )}
      {big && createPortal(
        <div className="fixed inset-0 z-[90] bg-black/80 flex items-center justify-center p-4" onClick={() => setBig(null)}>
          <img src={big} alt="Billede fra chaufføren" className="max-w-full max-h-full rounded-lg" />
        </div>, document.body)}
    </div>
  );
}

function TourPanel({ tour, onClose, drivers, load, onAssign, onChanged, onUnreadChanged, ownName, siteWord, askConfirm, can = () => true, isPremium = false, priceStatus = null }) {
  const [audit, setAudit] = useState(null);
  const [edit, setEdit] = useState(null);
  const [saving, setSaving] = useState(false);
  const [copyDate, setCopyDate] = useState("");
  // 2026-10-18 (D-serie): ture oprettet med "Gentag" deler series_id.
  const [seriesLeft, setSeriesLeft] = useState(0);
  const [applySeries, setApplySeries] = useState(false);
  useEffect(() => {
    setSeriesLeft(0); setApplySeries(false);
    if (!tour?.series_id) return;
    axios.get(`${API}/tours/series/${tour.series_id}`, { params: { from_date: addDays(tour.date, 1) } })
      .then(r => setSeriesLeft(r.data?.count || 0)).catch(() => {});
  }, [tour?.id, tour?.series_id, tour?.date]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!tour) return;
    setEdit(null);
    setAudit(null);
    setCopyDate(addDays(tour.date || todayStr(), 1));
  }, [tour?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!tour) return;
    axios.get(`${API}/tours/${tour.id}/audit-log`).then(r => setAudit(r.data || [])).catch(() => setAudit([]));
  }, [tour?.id, tour?.driver_id, tour?.claimed_by, tour?.on_way, tour?.completed]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!tour) return null;
  const st = tourStatus(tour);
  const oh = openHours(tour);
  const locked = tour.completed || tour.on_way;

  const saveEdit = async () => {
    setSaving(true);
    try {
      const { addr, deliv, lines, stops, ...rest } = edit;
      const delivFilled = (deliv?.street || deliv?.city || "").trim();
      const body = stops
        ? { ...rest, stops: stops.map(x => ({ ...x, address: x.address || formatAddress(x) })).filter(x => (x.address || "").trim()) }
        : {
          ...rest,
          address: formatAddress(addr), address_parts: addr,
          facility: delivFilled ? formatAddress(deliv) : (tour.plads || ""), facility_parts: delivFilled ? deliv : {},
        };
      // Ældre ture/bestillinger uden "Ved afslutning"-valg beholder deres
      // oprindelige regler (fx vægt påkrævet), medmindre der vælges noget.
      if (!Object.keys(tour.capture || {}).length && !body.capture?.quantity && !body.capture?.photo) delete body.capture;
      if (lines) {
        body.cargo_lines = lines.filter(l => (l.text || "").trim());
        body.fraction = body.cargo_lines.map(l => l.text.trim()).join(" + ");
      }
      await axios.put(`${API}/tours/${tour.id}`, body);
      if (applySeries && tour.series_id && seriesLeft > 0) {
        const { date: _d, ...fields } = body;
        const { data } = await axios.put(`${API}/tours/series/${tour.series_id}`, { from_date: addDays(tour.date, 1), fields });
        toast.success(`Turen og ${data.updated} kommende ture i serien er gemt${data.failed?.length ? ` · ${data.failed.length} kunne ikke rettes` : ""}`);
      } else toast.success("Turen er gemt");
      setEdit(null);
      onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
    setSaving(false);
  };
  const duplicate = async (date) => {
    try {
      await axios.post(`${API}/tours/bulk`, [copyBody(tour, date)]);
      toast.success(`Kopieret til ${fmtDayLong(date)}`);
      onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const approveStop = async (st) => {
    try { await axios.post(`${API}/tours/${tour.id}/stops/${st.id}/approve`); toast.success("Stoppet er godkendt og tæller med i prisen"); onChanged(); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  const deleteRestOfSeries = () => askConfirm({
    title: "Slet resten af serien?", text: `${seriesLeft} kommende ture efter ${fmtDayLong(tour.date)} slettes (ture der er startet eller afsluttet røres ikke).`,
    danger: true, okLabel: "Slet resten",
    onOk: async () => {
      try {
        const { data } = await axios.delete(`${API}/tours/series/${tour.series_id}`, { params: { from_date: addDays(tour.date, 1) } });
        toast.success(`${data.deleted} ture slettet`); setSeriesLeft(0); onChanged();
      } catch (e) { toast.error(formatApiError(e)); }
    },
  });
  const reactivate = async () => {
    try {
      await axios.post(`${API}/tours/${tour.id}/reactivate`, { comment: "Genaktiveret fra Ture" });
      toast.success("Turen er åben igen");
      onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const fact = (k, v) => v ? (
    <div className="min-w-0"><div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">{k}</div><div className="text-sm text-slate-800 dark:text-slate-100 break-words">{v}</div></div>
  ) : null;

  return (
    <Sheet open={!!tour} onClose={onClose} wide testid="tour-panel"
      title={<span className="flex items-center gap-2"><span className="truncate">{tour.fraction || "Tur"}</span>{tour.tour_number && <span className="text-xs font-mono font-semibold text-slate-400">{tour.tour_number}</span>}</span>}
      subtitle={<span className="inline-flex items-center gap-1.5"><span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${st.chip}`}>{st.label}</span>{isHaster(tour) && <span className="px-2 py-0.5 rounded-full bg-rose-600 text-white text-[11px] font-bold">Haster</span>}<span>{fmtDayLong(tour.date)}</span></span>}>
      <section className={`${card} p-4`}>
        <div className="flex items-start gap-3">
          <MapPin className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-slate-900 dark:text-white break-words">{tour.address || "Ingen adresse"}</div>
            {tour.facility && tour.facility !== tour.address && <div className="text-sm text-slate-500 mt-0.5">→ {tour.facility}</div>}
          </div>
          {tour.address && <a href={mapsUrl(tour.address)} target="_blank" rel="noreferrer" className={btnGhost}><Navigation className="w-4 h-4" /> Kort</a>}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
          {fact(siteWord, tour.plads)}
          {fact("Kunde", customerOf(tour, ownName))}
          {fact("Opgave", `${TOUR_TYPE_LABEL[tour.tour_type] || tour.tour_type}${isGoods(tour) ? " (gods)" : ""}`)}
          {fact("Indhold", cargoSummary(tour))}
          {fact("Container", tour.tour_type === "loes_afhentning" ? (tour.loose_estimated_count ? `${tour.loose_estimated_count} stk. (løs)` : "") : tour.container)}
          {fact("Kapacitet", capacityText(tour))}
          {fact("Tidsvindue", oh.from ? `${oh.from}–${oh.to}` : "")}
          {fact("Kilde", SOURCE_LABEL[tour.source] || tour.source)}
          {fact("Bestilt af", tour.created_by_name)}
          {fact("Vægt", tour.weight ? `${tour.weight} kg` : "")}
        </div>
        <Registration tour={tour} />
        {(priceStatus?.status === "missing" || deviationsOf(tour).length > 0) && (
          <div className="mt-3 flex flex-col gap-1.5" data-testid="panel-attention">
            {priceStatus?.status === "missing" && <div className="text-xs rounded-lg bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200 px-3 py-2"><b>{priceStatus.label}:</b> {priceStatus.why || "ingen prisregel passer"} - opret prisen under Økonomi › Rapport.</div>}
            {deviationsOf(tour).length > 0 && <div className="text-xs rounded-lg bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-100 px-3 py-2"><b>Afvigelse:</b> {deviationsOf(tour).join(" · ")}</div>}
          </div>
        )}
        {stopsOf(tour).length > 0 && (
          <div className="mt-4" data-testid="panel-stops">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400 mb-1.5">Stop ({stopsDone(tour)}/{stopsOf(tour).length} udført)</div>
            <ol className="space-y-1.5">
              {stopsOf(tour).map((st, i) => (
                <li key={st.id || i} className="flex items-start gap-2 text-sm">
                  <span className={`mt-0.5 w-5 h-5 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0 ${st.done_at ? "bg-emerald-500 text-white" : "bg-slate-100 text-slate-600"}`}>{st.done_at ? <Check className="w-3 h-3" /> : i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="text-[11px] font-semibold text-slate-500 mr-1">{st.kind === "delivery" ? "Aflevering" : "Afhentning"}</span>
                    <span className="text-slate-800 dark:text-slate-100 break-words">{st.address}</span>
                    {(st.note || st.contact_name || st.contact_phone) && <span className="block text-[11px] text-slate-500">{[st.note, [st.contact_name, st.contact_phone].filter(Boolean).join(" ")].filter(Boolean).join(" · ")}</span>}
                    {st.done_at && <span className="block text-[11px] text-emerald-700">Udført kl. {fmtClock(st.done_at)}{st.done_by ? ` · ${st.done_by}` : ""}{st.receiver_name ? ` · modtaget af ${st.receiver_name}` : ""}</span>}
                    {st.issue?.code && <span className="block text-[11px] font-semibold text-rose-700">Kunne ikke gennemføres: {st.issue.code}{st.issue.text ? ` - ${st.issue.text}` : ""}</span>}
                    {st.added_by_driver && <span className="block text-[11px] font-semibold text-amber-700">Tilføjet af chaufføren{st.approved ? " · godkendt" : ""}</span>}
                  </span>
                  {st.added_by_driver && !st.approved && can("tours_edit") && (
                    <button type="button" className="shrink-0 px-2 py-1 rounded-lg bg-amber-500 text-white text-[11px] font-bold" onClick={() => approveStop(st)} data-testid={`approve-stop-${i}`}>Godkend</button>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
        {oh.note && <div className="mt-3 text-sm bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 rounded-lg px-3 py-2">{oh.note}</div>}
        {tour.not_completed && (
          <div className="mt-3 text-sm bg-rose-50 dark:bg-rose-950/30 text-rose-800 dark:text-rose-200 rounded-lg px-3 py-2">
            <b>{tour.not_completed_by_name || "Chaufføren"}:</b> {tour.not_completed_comment}
          </div>
        )}
      </section>

      <section className={`${card} p-4`}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2"><User className="w-4 h-4 text-slate-400" /> Chauffør</h3>
          {tour.assigned_by_name && <span className="text-[11px] text-slate-400">Tildelt af {tour.assigned_by_name}</span>}
        </div>
        {tour.claimed_by && tour.claimed_by_id !== tour.driver_id ? (
          <div className="text-sm text-slate-700 dark:text-slate-200">Taget af <b>{tour.claimed_by}</b>{locked ? "" : " (ikke startet)"}</div>
        ) : (
          <DriverSelect value={tour.driver_id} drivers={drivers} load={load} disabled={locked || tour.not_completed || !can("tours_assign")}
            onChange={(v) => onAssign([tour.id], v)} testid="panel-driver" />
        )}
        {locked && <p className="text-[11px] text-slate-400 mt-1.5">Turen er {tour.completed ? "afsluttet" : "i gang"} og kan ikke flyttes til en anden chauffør.</p>}
      </section>

      <section className={`${card} p-4`}>
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2 mb-3"><MessageSquare className="w-4 h-4 text-slate-400" /> Beskeder med chaufføren</h3>
        {!assigneeName(tour) && <p className="text-[11px] text-slate-400 -mt-1 mb-2">Turen har ingen chauffør endnu - beskeden ses af den der tager turen.</p>}
        <TourChat tourId={tour.id} side="planner" onChanged={onUnreadChanged} maxHeight={260} readOnly={!can("messages")} />
      </section>

      <section className={`${card} p-4`}>
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2 mb-3"><Clock className="w-4 h-4 text-slate-400" /> Tidslinje</h3>
        {audit === null ? <Loader2 className="w-4 h-4 animate-spin text-slate-400" /> : <Timeline tour={tour} audit={audit} />}
      </section>

      <section className={`${card} p-4 space-y-3`}>
        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Handlinger</h3>
        {edit ? (
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div><label className={labelCls}>Dato</label><input type="date" className={inputCls} value={edit.date} onChange={(e) => setEdit({ ...edit, date: e.target.value })} /></div>
              <div>
                <label className={labelCls}>Opgave</label>
                <select className={inputCls} value={edit.tour_type} onChange={(e) => setEdit({ ...edit, tour_type: e.target.value })}>
                  {(isGoods(tour) ? GOODS_TYPES : TOUR_TYPES).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
              </div>
              {edit.lines ? (
                <div className="sm:col-span-2 space-y-2">
                  <label className={labelCls}>Indhold</label>
                  {edit.lines.map((l, i) => (
                    <div key={i} className="flex gap-2">
                      <input className={inputCls} value={l.text} onChange={(e) => setEdit({ ...edit, lines: edit.lines.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
                      {edit.trailer_count >= 2 && (
                        <select className={`${inputCls.replace("w-full ", "")} w-28`} value={l.trailer || ""} onChange={(e) => setEdit({ ...edit, lines: edit.lines.map((x, j) => (j === i ? { ...x, trailer: e.target.value ? Number(e.target.value) : null } : x)) })}>
                          <option value="">Hænger…</option>
                          {Array.from({ length: edit.trailer_count }, (_, k) => <option key={k} value={k + 1}>Hænger {k + 1}</option>)}
                        </select>
                      )}
                      {edit.lines.length > 1 && <button type="button" className="p-2 text-slate-400" onClick={() => setEdit({ ...edit, lines: edit.lines.filter((_, j) => j !== i) })}><X className="w-4 h-4" /></button>}
                    </div>
                  ))}
                  <button type="button" className="text-sm font-semibold text-emerald-700 inline-flex items-center gap-1" onClick={() => setEdit({ ...edit, lines: [...edit.lines, { text: "", trailer: null }] })}><Plus className="w-4 h-4" /> Tilføj linje</button>
                </div>
              ) : (
                <div><label className={labelCls}>Materiale</label><input className={inputCls} value={edit.fraction} onChange={(e) => setEdit({ ...edit, fraction: e.target.value })} /></div>
              )}
              {isPremium && (
                <div>
                  <label className={labelCls}>Hængere</label>
                  <select className={inputCls} value={edit.trailer_count} onChange={(e) => {
                    const n = Number(e.target.value);
                    setEdit({ ...edit, trailer_count: n, lines: edit.lines || (n >= 2 ? [{ text: edit.fraction, trailer: 1 }] : null) });
                  }}>
                    {[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n === 0 ? "Ingen" : n}</option>)}
                  </select>
                </div>
              )}
              {edit.stops ? (
                <div className="sm:col-span-2 space-y-3">
                  <label className={labelCls}>Stop</label>
                  {edit.stops.map((st, i) => (
                    <div key={st.id || i} className="rounded-xl border border-slate-100 dark:border-slate-700 p-3">
                      <div className="flex items-center justify-between mb-2">
                        <select className="text-xs font-bold bg-transparent" value={st.kind} onChange={(e) => setEdit({ ...edit, stops: edit.stops.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)) })}>
                          <option value="pickup">Afhentning</option><option value="delivery">Aflevering</option>
                        </select>
                        {edit.stops.length > 1 && <button type="button" className="p-1 text-slate-400" onClick={() => setEdit({ ...edit, stops: edit.stops.filter((_, j) => j !== i) })}><X className="w-4 h-4" /></button>}
                      </div>
                      <AddressField value={st.street || st.city ? st : parseAddress(st.address)} onChange={(v) => setEdit({ ...edit, stops: edit.stops.map((x, j) => (j === i ? { ...x, ...v, address: formatAddress(v) } : x)) })} inputCls={inputCls} />
                      <StopExtras value={st} onChange={(v) => setEdit({ ...edit, stops: edit.stops.map((x, j) => (j === i ? v : x)) })} />
                    </div>
                  ))}
                  <div className="flex gap-3">
                    <button type="button" className="text-sm font-semibold text-emerald-700 inline-flex items-center gap-1" onClick={() => setEdit({ ...edit, stops: [...edit.stops, { kind: "pickup", street: "", postal: "", city: "" }] })}><Plus className="w-4 h-4" /> Afhentning</button>
                    <button type="button" className="text-sm font-semibold text-emerald-700 inline-flex items-center gap-1" onClick={() => setEdit({ ...edit, stops: [...edit.stops, { kind: "delivery", street: "", postal: "", city: "" }] })}><Plus className="w-4 h-4" /> Aflevering</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="sm:col-span-2"><AddressField label="Afhentning" value={edit.addr} onChange={(v) => setEdit({ ...edit, addr: v })} inputCls={inputCls} /></div>
                  <div className="sm:col-span-2"><AddressField label="Aflevering" value={edit.deliv} onChange={(v) => setEdit({ ...edit, deliv: v })} inputCls={inputCls} /></div>
                  <button type="button" className="sm:col-span-2 text-left text-sm font-semibold text-emerald-700 inline-flex items-center gap-1"
                    onClick={() => setEdit({ ...edit, stops: [{ kind: "pickup", ...edit.addr }, ...((edit.deliv?.street || edit.deliv?.city) ? [{ kind: "delivery", ...edit.deliv }] : []), { kind: "pickup", street: "", postal: "", city: "" }] })}>
                    <Plus className="w-4 h-4" /> Tilføj et stop mere på turen</button>
                </>
              )}
              {!isGoods(tour) && <div><label className={labelCls}>Container nr.</label><input className={inputCls} value={edit.container} onChange={(e) => setEdit({ ...edit, container: e.target.value })} /></div>}
              {!isGoods(tour) && <div><label className={labelCls}>Kapacitet</label><input className={inputCls} value={edit.capacity_label} onChange={(e) => setEdit({ ...edit, capacity_label: e.target.value })} /></div>}
              <div><label className={labelCls}>Tidligst</label><input type="time" className={inputCls} value={edit.open_from} onChange={(e) => setEdit({ ...edit, open_from: e.target.value })} /></div>
              <div><label className={labelCls}>Senest</label><input type="time" className={inputCls} value={edit.open_to} onChange={(e) => setEdit({ ...edit, open_to: e.target.value })} /></div>
              <div>
                <label className={labelCls}>Prioritet</label>
                <select className={inputCls} value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value })}>
                  <option value="low">Lav</option><option value="normal">Normal</option><option value="urgent">Haster</option>
                </select>
              </div>
              <div className="sm:col-span-2"><label className={labelCls}>Note til chaufføren</label><textarea rows={2} className={inputCls} value={edit.remark} onChange={(e) => setEdit({ ...edit, remark: e.target.value })} /></div>
              <div className="sm:col-span-2 flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={!!edit.capture?.quantity} onChange={(e) => setEdit({ ...edit, capture: { ...edit.capture, quantity: e.target.checked } })} /> Chaufføren registrerer mængde</label>
                <label className="flex items-center gap-2"><input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={!!edit.capture?.photo} onChange={(e) => setEdit({ ...edit, capture: { ...edit.capture, photo: e.target.checked } })} /> Chaufføren tager billede</label>
              </div>
            </div>
            {tour.series_id && seriesLeft > 0 && (
              <label className="flex items-center gap-2 text-sm bg-slate-50 dark:bg-slate-900 rounded-lg px-3 py-2" data-testid="panel-series-apply">
                <input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={applySeries} onChange={(e) => setApplySeries(e.target.checked)} />
                Gem også for de {seriesLeft} kommende ture i serien (ikke datoen)
              </label>
            )}
            <div className="flex gap-2 justify-end">
              <button className={btnGhost} onClick={() => setEdit(null)}>Annuller</button>
              <button className={btnPrimary} disabled={saving} onClick={saveEdit} data-testid="panel-save">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem</button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {can("tours_edit") && <button className={btnGhost} disabled={tour.completed} data-testid="panel-edit" onClick={() => setEdit({
              date: tour.date || "", fraction: tour.fraction || "",
              addr: Object.keys(tour.address_parts || {}).length ? tour.address_parts : parseAddress(tour.address),
              deliv: Object.keys(tour.facility_parts || {}).length ? tour.facility_parts : parseAddress(tour.facility === tour.plads ? "" : tour.facility),
              lines: (tour.cargo_lines || []).length ? tour.cargo_lines.map(l => ({ text: l.text, trailer: l.trailer })) : null,
              stops: stopsOf(tour).length ? stopsOf(tour).map(x => ({ ...x })) : null,
              capture: { quantity: !!(tour.capture || {}).quantity, photo: !!(tour.capture || {}).photo },
              trailer_count: Number(tour.trailer_count || 0),
              container: tour.container || "", capacity_label: tour.capacity_label || "", open_from: oh.from || "", open_to: oh.to || "",
              tour_type: tour.tour_type || "normal", priority: isHaster(tour) ? "urgent" : (tour.priority || "normal"), remark: tour.remark || "",
            })}><Edit2 className="w-4 h-4" /> Ret</button>}
            {tour.not_completed && can("tours_edit") && <button className={btnGhost} onClick={reactivate}><RotateCcw className="w-4 h-4" /> Genaktivér</button>}
            {tour.series_id && seriesLeft > 0 && can("tours_delete") && <button className={btnGhost} onClick={deleteRestOfSeries} data-testid="panel-series-delete"><Trash2 className="w-4 h-4" /> Slet resten af serien ({seriesLeft})</button>}
            {can("tours_edit") && <div className="inline-flex items-stretch rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden">
              <input type="date" value={copyDate} onChange={(e) => setCopyDate(e.target.value)} className="px-2 text-base sm:text-sm bg-white dark:bg-slate-900 border-0 focus:outline-none" aria-label="Kopiér til dato" />
              <button className="px-3 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 inline-flex items-center gap-1.5 border-l border-slate-200 dark:border-slate-600"
                onClick={() => copyDate && duplicate(copyDate)} data-testid="panel-copy"><Copy className="w-4 h-4" /> Kopiér</button>
            </div>}
            {can("tours_delete") && <button className={btnDanger} disabled={tour.on_way || tour.source === "customer_order"}
              title={tour.source === "customer_order" ? "Kundebestillinger annulleres af kunden" : undefined} onClick={() => askConfirm({
              title: "Slet tur?", text: `${tour.fraction || "Turen"} · ${tour.address || ""} slettes permanent.`, danger: true, okLabel: "Slet",
              onOk: async () => {
                try { await axios.delete(`${API}/tours/${tour.id}`); toast.success("Turen er slettet"); onClose(); onChanged(); }
                catch (e) { toast.error(formatApiError(e)); }
              },
            })} data-testid="panel-delete"><Trash2 className="w-4 h-4" /> Slet</button>}
          </div>
        )}
      </section>
    </Sheet>
  );
}

const copyBody = (t, date) => ({
  date, plads: t.plads || "", fraction: t.fraction || "", facility: t.facility || "", address: t.address || "",
  tour_type: t.tour_type || "normal", container: t.container || "", container_type: t.container_type || "",
  capacity_label: t.capacity_label || "", capacity_volume_m3: t.capacity_volume_m3 ?? null,
  open_from: t.open_from || "", open_to: t.open_to || "", priority: t.priority || "normal", remark: t.remark || "",
  // Ejer (kunde) sendes ikke med: backend afgør den ud fra lokationen (P0).
  is_private: !!t.is_private, private_company: t.private_company || "", loose_estimated_count: t.loose_estimated_count || 0,
  tour_kind: t.tour_kind || "container", address_parts: t.address_parts || {}, facility_parts: t.facility_parts || {},
  trailer_count: t.trailer_count || 0, cargo_lines: t.cargo_lines || [],
  stops: (t.stops || []).map(({ id, done_at, done_by, receiver_name, issue, added_by_driver, approved, ...rest }) => rest),
  capture: t.capture || {}, customer_ref_id: t.customer_ref_id || "",
});

// ─────────────────────────── Arbejdsfladen ───────────────────────────

export default function ToursWorkspace({ drivers = [], pladsList = [], siteWord = "Lokation", perms = {}, profile = null }) {
  // 2026-10-17: Koordinator-rettigheder - mangler en nøgle, er den tilladt.
  const can = useCallback((k) => perms[k] !== false, [perms]);
  const canSelect = can("tours_assign") || can("tours_edit") || can("tours_delete");
  const [view, setView] = useState("day"); // day | history
  const [date, setDate] = useState(todayStr());
  const [tours, setTours] = useState(null);
  const [overdue, setOverdue] = useState([]);
  const [unread, setUnread] = useState({});
  const [updatedAt, setUpdatedAt] = useState(null);
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [fPlads, setFPlads] = useState("");
  const [fCustomer, setFCustomer] = useState("");
  const [fDriver, setFDriver] = useState("");
  const [fSource, setFSource] = useState("");
  const [onlyHaster, setOnlyHaster] = useState(false);
  // 2026-10-18 (E1/E3): prisstatus pr. tur (uden beløb) og afvigelser.
  const [priceStatus, setPriceStatus] = useState({});
  const [attnFilter, setAttnFilter] = useState(""); // "" | "price" | "deviation"
  const [showOverdue, setShowOverdue] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [collapsed, setCollapsed] = useState({});
  const [openId, setOpenId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [registry, setRegistry] = useState([]);
  const [bulkDate, setBulkDate] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef(null);
  const lastUnreadTotal = useRef(null);

  const isToday = date === todayStr();
  // Står siden åben over midnat, følger "i dag" med.
  const lastToday = useRef(todayStr());
  useEffect(() => {
    const iv = setInterval(() => {
      const t = todayStr();
      if (t !== lastToday.current) {
        setDate(d => (d === lastToday.current ? t : d));
        lastToday.current = t;
      }
    }, 60000);
    return () => clearInterval(iv);
  }, []);

  const fetchTours = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/tours`, { params: { date, limit: 500 } });
      setTours((r.data || []).filter(t => !t.is_pause));
      setUpdatedAt(new Date());
    } catch (e) {
      setTours(prev => prev || []);
    }
  }, [date]);

  const fetchOverdue = useCallback(async () => {
    try {
      const today = todayStr();
      const r = await axios.get(`${API}/tours`, { params: { date_from: addDays(today, -14), date_to: addDays(today, -1), pending: true, limit: 500 } });
      setOverdue((r.data || []).filter(t => !t.is_pause && !t.not_completed));
    } catch (e) { /* ikke kritisk */ }
  }, []);

  const fetchUnread = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/tour-messages/unread`);
      setUnread(r.data.unread || {});
      const total = r.data.total || 0;
      if (lastUnreadTotal.current !== null && total > lastUnreadTotal.current) {
        const m = (r.data.latest || [])[0];
        if (m) toast.message(`Ny besked fra ${m.sender_name || "chauffør"}`, { description: m.text });
      }
      lastUnreadTotal.current = total;
    } catch (e) { /* ikke kritisk */ }
  }, []);

  useEffect(() => { setTours(null); setSelected(new Set()); fetchTours(); }, [fetchTours]);
  useEffect(() => { fetchOverdue(); fetchUnread(); }, [fetchOverdue, fetchUnread]);
  useEffect(() => {
    axios.get(`${API}/logistics/customers`).then(r => setRegistry((r.data || []).filter(c => c.active !== false))).catch(() => {});
  }, [formOpen]);
  useEffect(() => {
    axios.get(`${API}/materials`).then(r => setMaterials((r.data?.materials || []).map(m => (typeof m === "string" ? m : m.name)).filter(Boolean))).catch(() => {});
  }, []);
  // Live: opdatér hvert 10. sekund mens fanen er synlig + straks når man vender tilbage.
  useEffect(() => {
    if (view !== "day") return;
    const tick = () => { if (!document.hidden) { fetchTours(); fetchUnread(); } };
    const iv = setInterval(tick, 10000);
    const iv2 = setInterval(() => { if (!document.hidden) fetchOverdue(); }, 60000);
    const onVis = () => { if (!document.hidden) { fetchTours(); fetchUnread(); fetchOverdue(); } };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onVis);
    return () => { clearInterval(iv); clearInterval(iv2); document.removeEventListener("visibilitychange", onVis); window.removeEventListener("focus", onVis); };
  }, [view, fetchTours, fetchUnread, fetchOverdue]);

  const refresh = useCallback(() => { fetchTours(); fetchOverdue(); fetchUnread(); }, [fetchTours, fetchOverdue, fetchUnread]);

  // Prisstatus kræver økonomi-adgang - koordinatorer uden den ser ingen chip.
  const priceIdsKey = (tours || []).map(t => `${t.id}:${t.completed ? 1 : 0}:${t.not_completed ? 1 : 0}`).join(",");
  useEffect(() => {
    if (!can("economy_view") || !tours || !tours.length) { setPriceStatus({}); return; }
    const ids = tours.map(t => t.id).slice(0, 500).join(",");
    axios.get(`${API}/pricing/status`, { params: { ids } }).then(r => setPriceStatus(r.data || {})).catch(() => setPriceStatus({}));
  }, [priceIdsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const source = useMemo(() => (showOverdue ? overdue : (tours || [])), [showOverdue, overdue, tours]);
  const ownName = "Egne ture";

  const load = useMemo(() => {
    const m = {};
    (tours || []).forEach(t => { const id = t.driver_id || t.claimed_by_id; if (id && !t.completed) m[id] = (m[id] || 0) + 1; });
    return m;
  }, [tours]);

  const counts = useMemo(() => {
    const c = { all: 0, open: 0, assigned: 0, onway: 0, done: 0, blocked: 0, haster: 0 };
    source.forEach(t => { c.all++; c[tourStatus(t).id]++; if (isHaster(t) && !t.completed) c.haster++; });
    return c;
  }, [source]);

  const customers = useMemo(() => Array.from(new Set(source.map(t => customerOf(t, ownName)))).sort(), [source, ownName]);
  const pladsNames = useMemo(() => Array.from(new Set(source.map(t => t.plads || "Uden lokation"))).sort(), [source]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return source.filter(t => {
      if (status !== "all" && tourStatus(t).id !== status) return false;
      if (onlyHaster && !isHaster(t)) return false;
      if (fPlads && (t.plads || "Uden lokation") !== fPlads) return false;
      if (fCustomer && customerOf(t, ownName) !== fCustomer) return false;
      if (fDriver === "__none" && assigneeName(t)) return false;
      if (fDriver && fDriver !== "__none" && t.driver_id !== fDriver && t.claimed_by_id !== fDriver) return false;
      if (fSource && (t.source || "manual") !== fSource) return false;
      if (attnFilter === "price" && priceStatus[t.id]?.status !== "missing") return false;
      if (attnFilter === "deviation" && !deviationsOf(t).length) return false;
      if (needle) {
        const hay = [t.fraction, t.address, t.facility, t.plads, t.tour_number, t.container, t.private_company, t.customer_name, assigneeName(t), t.remark].join(" ").toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [source, status, onlyHaster, fPlads, fCustomer, fDriver, fSource, q, ownName, attnFilter, priceStatus]);

  const groups = useMemo(() => {
    const rank = (t) => (t.not_completed ? 0 : t.completed ? 4 : t.on_way ? 2 : assigneeName(t) ? 3 : 1);
    const m = new Map();
    filtered.forEach(t => {
      const k = t.plads || "Uden lokation";
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(t);
    });
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0], "da")).map(([name, list]) => ({
      name,
      customer: customerOf(list[0], ownName),
      list: list.sort((a, b) => (isHaster(b) - isHaster(a)) || (rank(a) - rank(b)) || String(a.open_from || "99").localeCompare(String(b.open_from || "99")) || ((a.sort_order || 0) - (b.sort_order || 0))),
    }));
  }, [filtered, ownName]);

  const unreadTotal = Object.values(unread).reduce((s, n) => s + n, 0);
  const hasterOpen = (tours || []).filter(t => isHaster(t) && !t.completed && !assigneeName(t) && !t.not_completed);
  const blocked = (tours || []).filter(t => t.not_completed);
  const missingPrice = (tours || []).filter(t => priceStatus[t.id]?.status === "missing");
  const withDeviation = (tours || []).filter(t => deviationsOf(t).length > 0);
  const openTour = source.find(t => t.id === openId) || (tours || []).find(t => t.id === openId) || overdue.find(t => t.id === openId) || null;
  const activeFilters = !!(q || fPlads || fCustomer || fDriver || fSource || onlyHaster || attnFilter || status !== "all");

  const assign = async (ids, driverId) => {
    try {
      if (driverId) {
        await axios.post(`${API}/tours/bulk-assign`, { tour_ids: ids, driver_id: driverId });
        const d = drivers.find(x => x.id === driverId);
        toast.success(`${ids.length === 1 ? "Tildelt" : `${ids.length} ture tildelt`} ${d?.name || ""} - vises hos chaufføren med det samme`);
      } else {
        await Promise.all(ids.map(id => axios.put(`${API}/tours/${id}`, { driver_id: "", driver_name: "" })));
        toast.success("Frigivet - åben for alle chauffører");
      }
      refresh();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const selectedTours = source.filter(t => selected.has(t.id));
  const toggleSel = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSel = () => setSelected(new Set());

  const bulkPriority = async (p) => {
    try {
      await Promise.all(selectedTours.map(t => axios.put(`${API}/tours/${t.id}`, { priority: p })));
      toast.success("Prioritet opdateret"); clearSel(); refresh();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const bulkMove = async (d) => {
    const movable = selectedTours.filter(t => !t.completed && !t.on_way);
    if (!movable.length) { toast.error("Kun ture der ikke er startet kan flyttes"); return; }
    try {
      await Promise.all(movable.map(t => axios.put(`${API}/tours/${t.id}`, { date: d })));
      toast.success(`${movable.length} tur${movable.length === 1 ? "" : "e"} flyttet til ${fmtDayLong(d)}`); clearSel(); refresh();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const bulkCopy = async (d) => {
    try {
      await axios.post(`${API}/tours/bulk`, selectedTours.map(t => copyBody(t, d)));
      toast.success(`${selectedTours.length} tur${selectedTours.length === 1 ? "" : "e"} kopieret til ${fmtDayLong(d)}`); clearSel(); refresh();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const bulkDelete = () => {
    const deletable = selectedTours.filter(t => !t.on_way && !t.completed && t.source !== "customer_order");
    setConfirm({
      title: `Slet ${deletable.length} tur${deletable.length === 1 ? "" : "e"}?`,
      text: deletable.length < selectedTours.length
        ? `${selectedTours.length - deletable.length} er startet, færdige eller kundebestillinger (annulleres af kunden) og bliver ikke slettet. Kan ikke fortrydes.`
        : "Turene slettes permanent. Kan ikke fortrydes.",
      danger: true, okLabel: "Slet",
      onOk: async () => {
        try {
          await Promise.all(deletable.map(t => axios.delete(`${API}/tours/${t.id}`)));
          toast.success("Slettet"); clearSel(); refresh();
        } catch (e) { toast.error(formatApiError(e)); }
      },
    });
  };

  const downloadTemplate = async () => {
    try {
      const res = await axios.get(`${API}/tours/template`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = `ture-skabelon-${todayStr().replace(/-/g, "")}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const uploadTemplate = async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    setImporting(true); setImportResult(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await axios.post(`${API}/tours/upload-template`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setImportResult(r.data);
      if (r.data.created > 0) toast.success(`${r.data.created} tur(e) importeret`);
      refresh();
    } catch (e) {
      setImportResult({ created: 0, errors: [{ row: "?", reason: formatApiError(e) }] });
    }
    setImporting(false);
    ev.target.value = "";
  };

  const resetFilters = () => { setQ(""); setFPlads(""); setFCustomer(""); setFDriver(""); setFSource(""); setOnlyHaster(false); setAttnFilter(""); setStatus("all"); };

  // ───────── render ─────────
  return (
    <div className="space-y-4" data-testid="tours-workspace">
      {/* Topbar */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <div className="inline-flex rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-1">
          {[["day", "Dagsplan", CalendarDays], ["history", "Historik", History]].map(([id, l, Icon]) => (
            <button key={id} onClick={() => setView(id)} data-testid={`tours-view-${id}`}
              className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-sm font-semibold inline-flex items-center gap-1.5 ${view === id ? "bg-emerald-600 text-white" : "text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"}`}>
              <Icon className="w-4 h-4 hidden sm:block" /> {l}
            </button>
          ))}
        </div>
        {view === "day" && (
          <>
            <div className="order-last sm:order-none w-full sm:w-auto flex sm:inline-flex items-center rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
              <button onClick={() => { setShowOverdue(false); setDate(addDays(date, -1)); }} className="p-2 hover:bg-slate-50 dark:hover:bg-slate-700 rounded-l-xl" aria-label="Forrige dag"><ChevronLeft className="w-4 h-4" /></button>
              <label className="relative flex-1 sm:flex-none px-2 text-sm font-semibold text-slate-800 dark:text-slate-100 capitalize cursor-pointer min-w-[150px] text-center">
                {showOverdue ? "Tidligere dage" : (isToday ? `I dag · ${fmtDayLong(date).split(" ").slice(1).join(" ")}` : fmtDayLong(date))}
                <input type="date" value={date} onChange={(e) => { setShowOverdue(false); e.target.value && setDate(e.target.value); }} className="absolute inset-0 opacity-0 cursor-pointer" aria-label="Vælg dato" data-testid="tours-date" />
              </label>
              <button onClick={() => { setShowOverdue(false); setDate(addDays(date, 1)); }} className="p-2 hover:bg-slate-50 dark:hover:bg-slate-700 rounded-r-xl" aria-label="Næste dag"><ChevronRight className="w-4 h-4" /></button>
            </div>
            {(!isToday || showOverdue) && <button className={`${btnGhost} order-last sm:order-none`} onClick={() => { setShowOverdue(false); setDate(todayStr()); }} title="Gå tilbage til dagens ture">Til i dag</button>}
          </>
        )}
        <div className="flex-1" />
        {view === "day" && updatedAt && (
          <span className="hidden md:inline-flex items-center gap-1.5 text-[11px] text-slate-400" title="Opdateres automatisk hvert 10. sekund">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live · {updatedAt.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
        )}
        {can("tours_edit") && <button className={btnPrimary} onClick={() => setFormOpen(true)} data-testid="tours-new"><Plus className="w-4 h-4" /> Ny tur</button>}
        {can("tours_edit") && <Menu testid="tours-more" items={[
          { label: "Importér fra Excel-skabelon", icon: Upload, onClick: () => fileRef.current?.click() },
          { label: "Hent tom Excel-skabelon", icon: Download, onClick: downloadTemplate },
        ]} />}
        <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={uploadTemplate} />
      </div>

      {importing && <div className={`${card} p-3 text-sm flex items-center gap-2`}><Loader2 className="w-4 h-4 animate-spin" /> Importerer…</div>}
      {importResult && (
        <div className={`${card} p-3 text-sm`}>
          <div className="flex items-center justify-between">
            <b>{importResult.created} tur(e) importeret{importResult.errors?.length ? ` · ${importResult.errors.length} række(r) sprunget over` : ""}</b>
            <button onClick={() => setImportResult(null)} className="p-1 text-slate-400"><X className="w-4 h-4" /></button>
          </div>
          {importResult.errors?.length > 0 && (
            <ul className="mt-2 text-xs text-rose-600 space-y-0.5 max-h-32 overflow-y-auto">
              {importResult.errors.map((e, i) => <li key={i}>Række {e.row}: {e.reason}</li>)}
            </ul>
          )}
        </div>
      )}

      {view === "history" ? (
        <ArchiveTab locations={(pladsList || []).filter(p => p.location_code || p.code).map(p => ({ code: p.location_code || p.code, name: p.name }))} />
      ) : (
        <>
          {/* Opmærksomhed */}
          {(hasterOpen.length > 0 || overdue.length > 0 || blocked.length > 0 || unreadTotal > 0 || missingPrice.length > 0 || withDeviation.length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2" data-testid="tours-attention">
              {hasterOpen.length > 0 && (
                <button onClick={() => { setShowOverdue(false); setStatus("open"); setOnlyHaster(true); }} className="text-left rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 px-3 py-2.5 flex items-center gap-2.5">
                  <Flag className="w-4 h-4 text-rose-600 shrink-0" /><span className="text-sm text-rose-800 dark:text-rose-200"><b>{hasterOpen.length}</b> haster uden chauffør</span>
                </button>
              )}
              {overdue.length > 0 && (
                <button onClick={() => { setShowOverdue(true); setStatus("all"); }} className="text-left rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 px-3 py-2.5 flex items-center gap-2.5" data-testid="tours-overdue-btn">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" /><span className="text-sm text-amber-900 dark:text-amber-200"><b>{overdue.length}</b> fra tidligere dage ikke kørt</span>
                </button>
              )}
              {blocked.length > 0 && (
                <button onClick={() => { setShowOverdue(false); setStatus("blocked"); }} className="text-left rounded-xl border border-rose-200 dark:border-rose-900 bg-white dark:bg-slate-800 px-3 py-2.5 flex items-center gap-2.5">
                  <X className="w-4 h-4 text-rose-600 shrink-0" /><span className="text-sm text-slate-800 dark:text-slate-200"><b>{blocked.length}</b> kan ikke gennemføres</span>
                </button>
              )}
              {missingPrice.length > 0 && (
                <button onClick={() => { setShowOverdue(false); setStatus("all"); setAttnFilter(attnFilter === "price" ? "" : "price"); }} data-testid="tours-missing-price"
                  className={`text-left rounded-xl border px-3 py-2.5 flex items-center gap-2.5 ${attnFilter === "price" ? "border-red-500 bg-red-100 dark:bg-red-950/50" : "border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30"}`}>
                  <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" /><span className="text-sm text-red-800 dark:text-red-200"><b>{missingPrice.length}</b> tur{missingPrice.length === 1 ? "" : "e"} mangler pris</span>
                </button>
              )}
              {withDeviation.length > 0 && (
                <button onClick={() => { setShowOverdue(false); setStatus("all"); setAttnFilter(attnFilter === "deviation" ? "" : "deviation"); }} data-testid="tours-deviations"
                  className={`text-left rounded-xl border px-3 py-2.5 flex items-center gap-2.5 ${attnFilter === "deviation" ? "border-amber-500 bg-amber-100 dark:bg-amber-950/50" : "border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30"}`}>
                  <Flag className="w-4 h-4 text-amber-600 shrink-0" /><span className="text-sm text-amber-900 dark:text-amber-200"><b>{withDeviation.length}</b> med afvigelse at se på</span>
                </button>
              )}
              {unreadTotal > 0 && (
                <button onClick={() => { const id = Object.keys(unread)[0]; if (id) setOpenId(id); }} className="text-left rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 px-3 py-2.5 flex items-center gap-2.5">
                  <MessageSquare className="w-4 h-4 text-emerald-700 shrink-0" /><span className="text-sm text-emerald-900 dark:text-emerald-200"><b>{unreadTotal}</b> ulæst{unreadTotal === 1 ? "" : "e"} besked{unreadTotal === 1 ? "" : "er"} fra chauffører</span>
                </button>
              )}
            </div>
          )}

          {/* Status-faner */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none">
            {STATUS_FILTERS.filter(s => s.id !== "blocked" || counts.blocked > 0).map(s => (
              <button key={s.id} onClick={() => setStatus(s.id)} data-testid={`tours-status-${s.id}`}
                className={`shrink-0 px-3 py-2 rounded-xl text-sm font-semibold border inline-flex items-center gap-2 ${status === s.id
                  ? "bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white"
                  : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300"}`}>
                {s.label}
                <span className={`text-xs tabular-nums px-1.5 rounded-md ${status === s.id ? "bg-white/20" : "bg-slate-100 dark:bg-slate-700"}`}>{counts[s.id]}</span>
              </button>
            ))}
            <button onClick={() => setOnlyHaster(v => !v)}
              className={`shrink-0 px-3 py-2 rounded-xl text-sm font-semibold border inline-flex items-center gap-2 ${onlyHaster ? "bg-rose-600 text-white border-rose-600" : "bg-white dark:bg-slate-800 text-rose-600 border-rose-200 dark:border-rose-900"}`}>
              <Flag className="w-3.5 h-3.5" /> Haster <span className="text-xs tabular-nums">{counts.haster}</span>
            </button>
          </div>

          {/* Filtre */}
          <div className={`${card} p-2.5 sm:p-3 flex flex-col lg:flex-row gap-2`}>
            <div className="flex gap-2 flex-1 min-w-0">
              <div className="relative flex-1 min-w-0">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Søg adresse, materiale, tur-nr., firma…" className={`${inputCls} pl-9`} data-testid="tours-search" />
              </div>
              <button className={`${btnGhost} sm:hidden shrink-0`} onClick={() => setShowFilters(v => !v)} aria-expanded={showFilters}>
                Filtre{(fPlads || fCustomer || fDriver || fSource) ? ` (${[fPlads, fCustomer, fDriver, fSource].filter(Boolean).length})` : ""}
              </button>
            </div>
            <div className={`${showFilters ? "grid" : "hidden"} sm:grid grid-cols-2 sm:grid-cols-4 gap-2 lg:w-[640px]`}>
              <select className={inputCls} value={fPlads} onChange={(e) => setFPlads(e.target.value)} aria-label={siteWord}>
                <option value="">Alle {siteWord.toLowerCase()}er</option>
                {pladsNames.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <select className={inputCls} value={fCustomer} onChange={(e) => setFCustomer(e.target.value)} aria-label="Kunde">
                <option value="">Alle kunder</option>
                {customers.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <select className={inputCls} value={fDriver} onChange={(e) => setFDriver(e.target.value)} aria-label="Chauffør">
                <option value="">Alle chauffører</option>
                <option value="__none">Uden chauffør</option>
                {drivers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <select className={inputCls} value={fSource} onChange={(e) => setFSource(e.target.value)} aria-label="Kilde">
                <option value="">Alle kilder</option>
                {Object.entries(SOURCE_LABEL).map(([id, l]) => <option key={id} value={id}>{l}</option>)}
              </select>
            </div>
            {activeFilters && <button className={btnGhost} onClick={resetFilters}>Nulstil</button>}
          </div>

          {/* Masse-handlinger */}
          {selected.size > 0 && (
            <div className="sticky top-2 z-20 rounded-2xl bg-slate-900 text-white shadow-xl p-2.5 flex flex-wrap items-center gap-2" data-testid="tours-bulkbar">
              <span className="text-sm font-semibold px-2">{selected.size} valgt</span>
              {can("tours_assign") && <div className="w-44"><DriverSelect value="" drivers={drivers} load={load} compact onChange={(v) => { if (v) { assign([...selected], v); clearSel(); } }} testid="bulk-driver" /></div>}
              {can("tours_edit") && <>
              <button onClick={() => bulkPriority("urgent")} className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-sm font-semibold">Haster</button>
              <button onClick={() => bulkPriority("normal")} className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm font-semibold">Normal</button>
              <div className="inline-flex items-center rounded-lg bg-white/10 overflow-hidden">
                <input type="date" value={bulkDate} onChange={(e) => setBulkDate(e.target.value)} className="bg-transparent px-2 py-1.5 text-sm text-white [color-scheme:dark]" aria-label="Dato" />
                <button disabled={!bulkDate} onClick={() => bulkMove(bulkDate)} className="px-2.5 py-1.5 text-sm font-semibold hover:bg-white/10 disabled:opacity-40 border-l border-white/10">Flyt</button>
                <button disabled={!bulkDate} onClick={() => bulkCopy(bulkDate)} className="px-2.5 py-1.5 text-sm font-semibold hover:bg-white/10 disabled:opacity-40 border-l border-white/10">Kopiér</button>
              </div>
              </>}
              {can("tours_delete") && <button onClick={bulkDelete} className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-rose-600 text-sm font-semibold inline-flex items-center gap-1.5"><Trash2 className="w-4 h-4" /> Slet</button>}
              <div className="flex-1" />
              <button onClick={clearSel} className="p-1.5 rounded-lg hover:bg-white/10" aria-label="Fravælg"><X className="w-4 h-4" /></button>
            </div>
          )}

          {/* Listen */}
          {tours === null ? (
            <div className={`${card} p-10 flex items-center justify-center text-slate-400`}><Loader2 className="w-5 h-5 animate-spin" /></div>
          ) : groups.length === 0 ? (
            <div className={`${card} p-10 text-center`}>
              <Truck className="w-10 h-10 text-slate-300 mx-auto" />
              <div className="mt-3 font-semibold text-slate-700 dark:text-slate-200">{activeFilters ? "Ingen ture matcher filtrene" : showOverdue ? "Ingen uafsluttede ture fra de sidste 14 dage" : "Ingen ture denne dag"}</div>
              <div className="mt-1 text-sm text-slate-500">{activeFilters ? <button className="underline" onClick={resetFilters}>Nulstil filtre</button> : "Opret en tur, eller importér fra Excel via ⋯-menuen."}</div>
            </div>
          ) : (
            <div className="space-y-3">
              {groups.map(g => {
                const isCol = !!collapsed[g.name];
                const done = g.list.filter(t => t.completed).length;
                const allSel = g.list.every(t => selected.has(t.id));
                return (
                  <section key={g.name} className={`${card} overflow-hidden`} data-testid={`tours-group-${g.name}`}>
                    <div className="flex items-center gap-2 px-3 sm:px-4 py-2.5 bg-slate-50/80 dark:bg-slate-800/80 border-b border-slate-100 dark:border-slate-700">
                      {canSelect && <input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={allSel} aria-label="Vælg alle i gruppen"
                        onChange={() => setSelected(prev => { const n = new Set(prev); g.list.forEach(t => allSel ? n.delete(t.id) : n.add(t.id)); return n; })} />}
                      <button onClick={() => setCollapsed(c => ({ ...c, [g.name]: !isCol }))} className="flex-1 min-w-0 flex items-center gap-2 text-left">
                        <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                        <span className="font-semibold text-slate-900 dark:text-white truncate">{g.name}</span>
                        <span className="text-xs text-slate-400 truncate hidden sm:inline">· {g.customer}</span>
                        <span className="ml-auto text-xs text-slate-500 tabular-nums shrink-0">{done}/{g.list.length} færdig</span>
                        <ChevronDown className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${isCol ? "-rotate-90" : ""}`} />
                      </button>
                    </div>
                    {!isCol && (
                      <ul className="divide-y divide-slate-100 dark:divide-slate-700/70">
                        {g.list.map(t => {
                          const st = tourStatus(t);
                          const oh = openHours(t);
                          const late = daysLate(t);
                          const un = unread[t.id] || 0;
                          const cap = t.tour_type === "loes_afhentning" ? (t.loose_estimated_count ? `${t.loose_estimated_count} stk.` : "") : capacityText(t);
                          const lockedRow = t.completed || t.on_way || t.not_completed || (t.claimed_by && t.claimed_by_id !== t.driver_id);
                          return (
                            <li key={t.id} onClick={() => setOpenId(t.id)} data-testid={`tours-row-${t.id}`}
                              className={`group grid grid-cols-[auto_1fr_auto] md:grid-cols-[auto_minmax(0,2.2fr)_minmax(0,1fr)_200px_auto] items-center gap-x-3 gap-y-2 px-3 sm:px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/30 ${t.completed ? "opacity-60" : ""} ${selected.has(t.id) ? "bg-emerald-50/60 dark:bg-emerald-950/20" : ""}`}>
                              <div className="flex items-center gap-2.5 self-start pt-0.5" onClick={(e) => e.stopPropagation()}>
                                {canSelect && <input type="checkbox" className="w-4 h-4 accent-emerald-600" checked={selected.has(t.id)} onChange={() => toggleSel(t.id)} aria-label="Vælg tur" />}
                                <span className={`w-2.5 h-2.5 rounded-full ${st.dot}`} title={st.label} />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {isHaster(t) && !t.completed && <span className="px-1.5 py-0.5 rounded bg-rose-600 text-white text-[10px] font-bold uppercase">Haster</span>}
                                  <span className="font-semibold text-slate-900 dark:text-white">{t.fraction || "—"}</span>
                                  {isGoods(t) && <span className="text-[11px] font-semibold text-sky-700 bg-sky-50 dark:bg-sky-950/40 dark:text-sky-300 px-1.5 py-0.5 rounded">Gods</span>}
                                  {Number(t.trailer_count) > 0 && <span className="text-[11px] text-slate-500">{t.trailer_count} hænger{Number(t.trailer_count) === 1 ? "" : "e"}</span>}
                                  {t.tour_type && t.tour_type !== "normal" && <span className="text-[11px] font-semibold text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/40 px-1.5 py-0.5 rounded">{TOUR_TYPE_LABEL[t.tour_type] || t.tour_type}</span>}
                                  {cap && <span className="text-[11px] text-slate-500 inline-flex items-center gap-0.5"><Package2 className="w-3 h-3" />{cap}</span>}
                                  {t.container && t.tour_type !== "loes_afhentning" && <span className="text-[11px] text-slate-400">#{t.container}</span>}
                                  {showOverdue && <span className="text-[11px] font-semibold text-amber-700">{fmtDayLong(t.date)}</span>}
                                  {!showOverdue && late > 0 && <span className="text-[11px] font-semibold text-amber-700">{late} d. forsinket</span>}
                                  {priceStatus[t.id]?.status === "missing" && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" title={priceStatus[t.id].why || ""} data-testid={`row-price-${t.id}`}>{priceStatus[t.id].label}</span>}
                                  {priceStatus[t.id]?.status === "invoiced" && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300">Faktureret</span>}
                                  {priceStatus[t.id]?.pending > 0 && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">Rettelse venter</span>}
                                  {deviationsOf(t).length > 0 && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200" title={deviationsOf(t).join(" · ")} data-testid={`row-deviation-${t.id}`}>Afvigelse</span>}
                                </div>
                                <div className="text-sm text-slate-600 dark:text-slate-300 truncate">{t.address || "Ingen adresse"}{t.facility && t.facility !== t.plads ? <span className="text-slate-400"> → {t.facility}</span> : null}</div>
                                {stopsOf(t).length > 0 && <div className="text-[11px] font-semibold text-slate-500">{stopsOf(t).length} stop · {stopsDone(t)} udført</div>}
                                <div className="md:hidden mt-1 flex items-center gap-3 text-[11px] text-slate-500">
                                  {oh.from && <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />{oh.from}–{oh.to}</span>}
                                  <span className={`px-1.5 py-0.5 rounded border ${st.chip}`}>{st.label}{t.on_way_time && !t.completed ? ` ${t.on_way_time}` : ""}{t.completed && t.time ? ` ${t.time}` : ""}</span>
                                  {t.source && t.source !== "manual" && <span>{SOURCE_LABEL[t.source] || t.source}</span>}
                                </div>
                              </div>
                              <div className="hidden md:block min-w-0 text-xs text-slate-500 space-y-0.5">
                                {oh.from ? <div className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />{oh.from}–{oh.to}</div> : <div className="text-slate-300 dark:text-slate-600">Hele dagen</div>}
                                <div className="flex items-center gap-1.5">
                                  <span className={`px-1.5 py-0.5 rounded border ${st.chip}`}>{st.label}{t.on_way_time && !t.completed ? ` ${t.on_way_time}` : ""}{t.completed && t.time ? ` ${t.time}` : ""}</span>
                                  {t.source && t.source !== "manual" && <span className="text-slate-400">{SOURCE_LABEL[t.source] || t.source}</span>}
                                </div>
                              </div>
                              <div className="col-span-2 col-start-2 md:col-span-1 md:col-start-auto" onClick={(e) => e.stopPropagation()}>
                                {lockedRow || !can("tours_assign") ? (
                                  <div className="text-sm text-slate-700 dark:text-slate-200 truncate px-1 inline-flex items-center gap-1.5"><User className="w-3.5 h-3.5 text-slate-400" />{assigneeName(t) || "—"}</div>
                                ) : (
                                  <DriverSelect value={t.driver_id} drivers={drivers} load={load} compact onChange={(v) => assign([t.id], v)} testid={`row-driver-${t.id}`} />
                                )}
                              </div>
                              <div className="row-start-1 col-start-3 md:row-start-auto md:col-start-auto flex items-center gap-1 self-start md:self-center">
                                <button onClick={(e) => { e.stopPropagation(); setOpenId(t.id); }} title="Beskeder"
                                  className={`relative p-2 rounded-lg ${un ? "text-emerald-700 bg-emerald-50 dark:bg-emerald-950/40" : "text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"}`}>
                                  <MessageSquare className="w-4 h-4" />
                                  {un > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center">{un}</span>}
                                </button>
                                <ChevronRight className="w-4 h-4 text-slate-300 hidden sm:block" />
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}

      <TourForm open={formOpen} canPrice={can("economy_edit")} customers={registry} isPremium={!!profile?.is_premium} onClose={() => setFormOpen(false)} initialDate={showOverdue ? todayStr() : date} pladsList={pladsList}
        drivers={drivers} materials={materials} defaultPlads={fPlads || (pladsList.length === 1 ? pladsList[0].name : "")}
        siteWord={siteWord}
        onCreated={(d) => { setShowOverdue(false); if (d && d !== date) setDate(d); else refresh(); }} />
      <TourPanel tour={openTour} onClose={() => setOpenId(null)} drivers={drivers} load={load} onAssign={assign}
        onChanged={refresh} onUnreadChanged={fetchUnread} ownName={ownName} siteWord={siteWord} askConfirm={setConfirm} can={can} isPremium={!!profile?.is_premium}
        priceStatus={openTour ? priceStatus[openTour.id] : null} />
      <Confirm state={confirm} onClose={() => setConfirm(null)} />
    </div>
  );
}
