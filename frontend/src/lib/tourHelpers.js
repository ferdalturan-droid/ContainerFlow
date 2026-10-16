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
export const TOUR_TYPE_LABEL = Object.fromEntries(TOUR_TYPES.map(t => [t.id, t.label]));

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

export const isHaster = (t) => {
  const p = String(t?.priority || "").toLowerCase();
  return p === "urgent" || p === "haster" || p === "high" || (t?.remark || "").toLowerCase().includes("haster");
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
