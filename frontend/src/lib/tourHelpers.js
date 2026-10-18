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
// 2026-10-17: Opgavetyper for "Gods og andet" (premium-firmaers egne ture
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
export const deviationsOf = (t) => {
  const out = [];
  if (!t) return out;
  const lines = Array.isArray(t.cargo_lines) ? t.cargo_lines : [];
  const cap = t.capture || {};
  if (t.completed) {
    if (lines.some(l => l.actual_qty != null && l.qty != null && Number(l.actual_qty) !== Number(l.qty))) out.push("Mængde afviger");
    if (cap.quantity && !lines.some(l => l.actual_qty != null) && !(Number(t.weight) > 0)) out.push("Mangler mængde");
    if (cap.photo && !(Number(t.photo_count) > 0)) out.push("Mangler billede");
    if (stopsOf(t).some(s => !s.done_at)) out.push("Stop ikke krydset af");
  }
  if (t.trailer_count_actual != null && Number(t.trailer_count || 0) !== Number(t.trailer_count_actual)) out.push(`Hængere ${t.trailer_count || 0} → ${t.trailer_count_actual}`);
  if (stopsOf(t).some(s => s.issue?.code)) out.push("Stop ikke gennemført");
  if (stopsOf(t).some(s => s.added_by_driver && !s.approved)) out.push("Ekstra stop fra chaufføren");
  if (t.finish_issue?.code) out.push(t.finish_issue.code);
  return out;
};

