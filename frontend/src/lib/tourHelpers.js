// Fælles hjælpere til tur-visning (2026-10-16). Bruges af den nye
// Ture-arbejdsflade (logistik admin) og de nye chauffør-kort, så status,
// prioritet og tidsvindue læses ens begge steder.

export const TOUR_TYPES = [
  { id: "normal", label: "Afhent container" },
  { id: "flyt", label: "Byt container" },
  { id: "loes_afhentning", label: "Løs afhentning" },
  { id: "vaerksted", label: "Til værksted" },
  { id: "afhent_vaerksted", label: "Afhent fra værksted" },
];
// 2026-10-17: Opgavetyper for "Fragt" (tidl. "Gods og andet"; premium-firmaers egne ture
// der ikke handler om containere).
export const GOODS_TYPES = [
  { id: "afhentning", label: "Afhentning" },
  { id: "levering", label: "Levering" },
  { id: "afhent_lever", label: "Afhentning + levering" },
  { id: "flytning", label: "Flytning" },
  { id: "andet", label: "Andet" },
];
export const TOUR_TYPE_LABEL = Object.fromEntries([...TOUR_TYPES, ...GOODS_TYPES].map(t => [t.id, t.label]));
export const isGoods = (t) => t?.tour_kind === "goods";

/** "2 hængere: 1) Beton  2) Træ" - kort tekst til kort og lister. */
export const cargoSummary = (t) => {
  const lines = Array.isArray(t?.cargo_lines) ? t.cargo_lines : [];
  const n = Number(t?.trailer_count || 0);
  if (!lines.length && !n) return "";
  const parts = lines.map(l => `${l.trailer ? `H${l.trailer}: ` : ""}${l.text}${l.qty ? ` ×${l.qty}${l.unit ? " " + l.unit : ""}` : ""}`);
  const head = n ? `${n} hænger${n === 1 ? "" : "e"}` : "";
  return [head, parts.join(" · ")].filter(Boolean).join(" — ");
};
/** Flere læs der vejes hver for sig (løs afhentning eller flere indholdslinjer). */
export const isMultiLoad = (t) => t?.tour_type === "loes_afhentning" || (Array.isArray(t?.cargo_lines) && t.cargo_lines.length > 1);

export const SOURCE_LABEL = {
  manual: "Manuel",
  customer_order: "Bestilling",
  argo: "ARGO",
};

export const todayStr = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

export const addDays = (dateStr, n) => {
  const d = new Date(`${dateStr}T12:00:00`);
  d.setDate(d.getDate() + n);
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

export const fmtDayLong = (dateStr) => {
  try {
    return new Date(`${dateStr}T12:00:00`).toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" });
  } catch (_) { return dateStr; }
};

export const fmtClock = (iso) => {
  if (!iso) return "";
  if (/^\d{1,2}:\d{2}$/.test(iso)) return iso;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
};

/** 2026-10-18: Kun prioritetsfeltet - samme kilde som prisen og push.
 *  "haster" i noten sættes som prioritet af backend ved oprettelse. */
export const isHaster = (t) => {
  const p = String(t?.priority || "").toLowerCase();
  return p === "urgent" || p === "haster" || p === "high";
};

/** Åbningstider - felter først, ellers "Tømning 7 14 ..." i bemærkningen. */
export const openHours = (t) => {
  if (t?.open_from && t?.open_to) return { from: t.open_from, to: t.open_to, note: t.remark || "" };
  const remark = t?.remark || "";
  const m = remark.match(/^([A-Za-zÆØÅæøå]+)\s+(\d{1,2}(?::\d{2})?)\s+(\d{1,2}(?::\d{2})?)(.*)$/);
  if (m) return { from: m[2], to: m[3], note: m[4].trim() };
  return { from: "", to: "", note: remark };
};

export const capacityText = (t) => {
  const label = (t?.capacity_label || "").trim();
  const m3 = t?.capacity_volume_m3;
  if (label && m3 != null && m3 !== "") return `${label} (${m3} m³)`;
  if (label) return label;
  if (m3 != null && m3 !== "") return `${m3} m³`;
  return "";
};

export const assigneeName = (t) => t?.claimed_by || t?.driver_name || "";

/** Én status pr. tur - samme ord hos planlægger og chauffør. */
export const tourStatus = (t) => {
  // 2026-10-19: Annulleret (af kunden, eller af logistikfirmaet på kundens anmodning).
  if (t?.cancelled) return { id: "cancelled", label: t.cancelled_on_way ? "Annulleret undervejs" : "Annulleret", dot: "bg-slate-300", chip: "bg-slate-100 text-slate-500 border-slate-300 line-through decoration-slate-400 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-600" };
  if (t?.not_completed) return { id: "blocked", label: "Kan ikke gennemføres", dot: "bg-rose-500", chip: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900" };
  if (t?.completed) return { id: "done", label: "Færdig", dot: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900" };
  if (t?.on_way) return { id: "onway", label: "På vej", dot: "bg-amber-500", chip: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900" };
  if (assigneeName(t)) return { id: "assigned", label: "Tildelt", dot: "bg-indigo-500", chip: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-900" };
  return { id: "open", label: "Ikke tildelt", dot: "bg-slate-400", chip: "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700" };
};

/** Dage turen er forsinket (dato før i dag og ikke færdig). */
export const daysLate = (t) => {
  if (!t || t.completed || !t.date) return 0;
  const today = todayStr();
  if (t.date >= today) return 0;
  return Math.round((new Date(`${today}T12:00:00`) - new Date(`${t.date.slice(0, 10)}T12:00:00`)) / 86400000);
};

export const mapsUrl = (address) =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${address}, Denmark`)}`;

/** 2026-10-19: Google Maps-vejvisning til én adresse (Danmark, så "Folehaven 1" ikke lander i udlandet). */
export const navUrl = (address) => {
  const a = String(address || "").trim();
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(/danmark|denmark/i.test(a) ? a : `${a}, Danmark`)}&travelmode=driving`;
};
/** Hele ruten (fra første til sidste sted) - til planlæggerens "Kort". */
export const routeUrl = (legs) => {
  const ls = (legs || []).filter(l => (l.address || "").trim());
  if (ls.length < 2) return navUrl(ls[0]?.address || "");
  const dk = (a) => (/danmark|denmark/i.test(a) ? a : `${a}, Danmark`);
  const mid = ls.slice(1, -1).map(l => dk(l.address)).join("|");
  return `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(dk(ls[0].address))}&destination=${encodeURIComponent(dk(ls[ls.length - 1].address))}${mid ? `&waypoints=${encodeURIComponent(mid)}` : ""}&travelmode=driving`;
};

/**
 * 2026-10-19: Turens steder i køreorden: [{ role: "pickup"|"delivery", label, name, address }].
 * Felterne betyder noget forskelligt på en bestilling og en manuel tur, så
 * kort, chauffør og planlægger bruger alle denne ene funktion:
 *  - Bestilling, afhent container: Hent på pladsen (plads_address) -> aflever
 *    på leveringsadressen (address, navn i delivery_name).
 *  - Byt container: kun pladsen.
 *  - Til værksted: pladsen -> værkstedet. Afhent fra værksted: værkstedet -> pladsen.
 *  - Manuel tur: afhentning (address) -> aflevering (facility; pladsen når tom).
 *  - Ture med stop: stoppene.
 */
export const routeOf = (t) => {
  if (!t) return [];
  const st = Array.isArray(t.stops) ? t.stops : [];
  if (st.length) return st.map(s => ({ role: s.kind === "delivery" ? "delivery" : "pickup", label: s.kind === "delivery" ? "Aflevering" : "Afhentning", name: s.contact_name || "", address: s.address || "" }));
  const pladsName = t.plads || "Pladsen";
  if ((t.tour_type === "vaerksted" || t.tour_type === "afhent_vaerksted") && t.workshop_address) {
    const w = { name: t.workshop_name || "Værksted", address: t.workshop_address };
    const home = { name: pladsName, address: (t.tour_type === "vaerksted" ? t.address : t.facility) || t.plads_address || "" };
    return t.tour_type === "vaerksted"
      ? [{ role: "pickup", label: "Hent", ...home }, { role: "delivery", label: "Aflever", ...w }]
      : [{ role: "pickup", label: "Hent", ...w }, { role: "delivery", label: "Aflever", ...home }];
  }
  if (t.tour_type === "flyt") return [{ role: "pickup", label: "Pladsen", name: pladsName, address: t.address || t.plads_address || "" }].filter(l => l.address);
  const facIsPlads = !t.facility || t.facility === t.plads;
  if (t.order_id && facIsPlads) {
    const legs = [];
    if (t.plads_address && t.plads_address !== t.address) legs.push({ role: "pickup", label: "Hent", name: pladsName, address: t.plads_address });
    if (t.address) legs.push({ role: "delivery", label: "Aflever", name: t.delivery_name || "", address: t.address });
    return legs;
  }
  const legs = [];
  if (t.address) legs.push({ role: "pickup", label: "Hent", name: "", address: t.address });
  if (facIsPlads ? t.plads_address : (t.facility && t.facility !== t.address)) {
    legs.push({ role: "delivery", label: "Aflever", name: facIsPlads ? pladsName : "", address: facIsPlads ? t.plads_address : t.facility });
  }
  return legs;
};

/** Stop på turen (2026-10-17). Tom liste = almindelig tur med én adresse. */
export const stopsOf = (t) => (Array.isArray(t?.stops) ? t.stops : []);
export const stopsDone = (t) => stopsOf(t).filter(s => s.done_at).length;

/** Dansk talformat: "1.100", "1.100,50", "1100,5" og "1100.5" -> tal. NaN hvis tomt/ugyldigt. */
export const parseDk = (v) => {
  if (v === "" || v == null) return NaN;
  let s = String(v).replace(/\s|kr|%/g, "");
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  return Number(s);
};

/** 2026-10-18 (E2/E3): Hvad planlæggeren bør kigge på efter turen -
 *  registreret ≠ planlagt, manglende registrering, stop der ikke blev
 *  gennemført, ekstra stop fra chaufføren og afvigelser ved afslutning. */
const hhmm = (v) => { const m = /^(\d{1,2}):(\d{2})/.exec(v || ""); return m ? Number(m[1]) * 60 + Number(m[2]) : -1; };
const dkDay = (iso) => { try { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" }); } catch (_) { return ""; } };

/** 2026-10-18 (P8): Tidsfejl der giver forkert pris på timepris - fx Start
 *  ved ankomst og Afslut et minut senere, eller glemt Afslut til næste dag.
 *  opts.hourly = turen afregnes på timepris (fra prisstatus). */
export const timeDeviations = (t, opts = {}) => {
  const out = [];
  if (!t?.completed || !t.on_way_time || !t.time) return out;
  const st = hhmm(t.on_way_time), en = hhmm(t.time);
  if (st < 0 || en < 0) return out;
  const startDay = t.on_way_at ? dkDay(t.on_way_at) : "";
  const endDay = t.completed_at ? dkDay(t.completed_at) : "";
  const otherDay = (startDay && endDay && startDay !== endDay) || (!startDay && en < st);
  if (otherDay) { out.push("Afsluttet en anden dag end startet"); return out; }
  const dur = en - st;
  if (dur < 2) out.push("Startet under 2 min før afsluttet");
  else if (dur < 5 && opts.hourly) out.push("Varighed under 5 min (timepris)");
  return out;
};

export const deviationsOf = (t, opts = {}) => {
  const out = [...timeDeviations(t, opts)];
  if (!t) return out;
  const lines = Array.isArray(t.cargo_lines) ? t.cargo_lines : [];
  const cap = t.capture || {};
  if (t.completed) {
    if (lines.some(l => l.actual_qty != null && l.qty != null && Number(l.actual_qty) !== Number(l.qty))) out.push("Mængde afviger");
    if (cap.quantity && !lines.some(l => l.actual_qty != null) && !(Number(t.weight) > 0)) out.push("Mangler mængde");
    if (cap.photo && !(Number(t.photo_count) > 0)) out.push("Mangler billede");
    if (stopsOf(t).some(s => !s.done_at)) out.push("Stop ikke krydset af");
  }
  // 2026-10-19: Kun når planlæggeren faktisk har planlagt hængere. Uden planlagt
  // antal er chaufførens svar en oplysning, ikke en afvigelse (før fik alle
  // partner- og bestillings-ture "Hængere 0 → 1").
  if (t.trailer_count_actual != null && Number(t.trailer_count || 0) > 0 && Number(t.trailer_count) !== Number(t.trailer_count_actual)) out.push(`Hængere ${t.trailer_count} → ${t.trailer_count_actual}`);
  if (stopsOf(t).some(s => s.issue?.code)) out.push("Stop ikke gennemført");
  if (stopsOf(t).some(s => s.added_by_driver && !s.approved)) out.push("Ekstra stop fra chaufføren");
  if (t.finish_issue?.code) out.push(t.finish_issue.code);
  return out;
};

