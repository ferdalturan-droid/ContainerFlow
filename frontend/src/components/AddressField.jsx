import React, { useMemo, useRef, useState, useEffect } from "react";
import POSTNUMRE from "../data/postnumre.json";

/**
 * Dansk adresse: vej + nr., postnummer og by (2026-10-17).
 * - Postnumre/byer fra Datafordeler (DAR), indlejret i appen (ingen
 *   ekstern afhængighed). Vælg en by -> postnummeret udfyldes; skriv et
 *   postnummer -> byen udfyldes.
 * - "Tilføj manuelt" når byen ikke findes (fx udland eller nyt område):
 *   begge felter skrives frit.
 * value = { street, postal, city }
 */
const BY_POSTAL = new Map(POSTNUMRE.map(([nr, navn]) => [nr, navn]));
const norm = (s) => (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");

export function formatAddress(p) {
  if (!p) return "";
  const tail = [p.postal, p.city].filter(Boolean).join(" ");
  return [p.street, tail].filter(Boolean).join(", ");
}

/** Forsøg at læse "Vej 1, 4600 Køge" tilbage til dele (til redigering). */
export function parseAddress(s) {
  const m = (s || "").match(/^(.*?)(?:,\s*)?(\d{4})\s+(.+)$/);
  if (m) return { street: m[1].trim(), postal: m[2], city: m[3].trim() };
  return { street: (s || "").trim(), postal: "", city: "" };
}

export default function AddressField({ value, onChange, label, placeholder = "Vej og nr.", testid, inputCls }) {
  const v = value || {};
  const [cityQ, setCityQ] = useState(v.city || "");
  const [open, setOpen] = useState(false);
  const [manual, setManual] = useState(() => !!(v.city && v.postal && BY_POSTAL.get(v.postal) !== v.city));
  const wrap = useRef(null);
  useEffect(() => { setCityQ(v.city || ""); }, [v.city]);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("touchstart", close); };
  }, [open]);

  const suggestions = useMemo(() => {
    const q = norm(cityQ).trim();
    if (!q) return [];
    const isNum = /^\d+$/.test(q);
    const hits = POSTNUMRE.filter(([nr, navn]) => (isNum ? nr.startsWith(q) : norm(navn).startsWith(q) || norm(navn).includes(` ${q}`)));
    return hits.slice(0, 8);
  }, [cityQ]);

  const set = (patch) => onChange({ ...v, ...patch });
  const pick = ([nr, navn]) => { set({ postal: nr, city: navn }); setCityQ(navn); setOpen(false); };
  const onPostal = (raw) => {
    const postal = raw.replace(/\D/g, "").slice(0, 4);
    if (!manual && postal.length === 4 && BY_POSTAL.get(postal)) {
      set({ postal, city: BY_POSTAL.get(postal) });
      setCityQ(BY_POSTAL.get(postal));
    } else {
      set({ postal });
    }
  };
  const known = v.postal && BY_POSTAL.get(v.postal) === v.city;
  const ic = inputCls || "w-full px-3 py-2.5 sm:py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";

  return (
    <div className="space-y-2" data-testid={testid}>
      {label && <span className="block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</span>}
      <input className={ic} value={v.street || ""} onChange={(e) => set({ street: e.target.value })} placeholder={placeholder}
        autoComplete="street-address" data-testid={testid ? `${testid}-street` : undefined} />
      <div className="grid grid-cols-[96px_1fr] gap-2" ref={wrap}>
        <input className={ic} value={v.postal || ""} inputMode="numeric" placeholder="Postnr." maxLength={manual ? 10 : 4}
          onChange={(e) => (manual ? set({ postal: e.target.value }) : onPostal(e.target.value))} autoComplete="postal-code"
          data-testid={testid ? `${testid}-postal` : undefined} />
        <div className="relative">
          <input className={ic} value={manual ? (v.city || "") : cityQ} placeholder={manual ? "By" : "By (skriv og vælg)"}
            autoComplete="address-level2"
            onFocus={() => !manual && setOpen(true)}
            onChange={(e) => {
              if (manual) { set({ city: e.target.value }); return; }
              setCityQ(e.target.value); setOpen(true);
              if (v.city && e.target.value !== v.city) set({ city: "", postal: v.postal && BY_POSTAL.get(v.postal) === v.city ? "" : v.postal });
            }}
            onBlur={() => {
              // Skrevet præcist et bynavn? Så vælg det automatisk.
              if (manual) return;
              const exact = POSTNUMRE.filter(([, navn]) => norm(navn) === norm(cityQ).trim());
              if (exact.length === 1 && !v.city) pick(exact[0]);
            }}
            data-testid={testid ? `${testid}-city` : undefined} />
          {open && !manual && suggestions.length > 0 && (
            <ul className="absolute z-30 left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-xl py-1">
              {suggestions.map(s => (
                <li key={s[0]}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(s)}
                    className="w-full text-left px-3 py-2.5 text-sm hover:bg-emerald-50 dark:hover:bg-slate-700 flex gap-3">
                    <span className="font-mono text-slate-500 w-10">{s[0]}</span><span className="text-slate-800 dark:text-slate-100">{s[1]}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between text-[11px]">
        {!manual ? (
          <>
            <span className={known ? "text-emerald-700 dark:text-emerald-400" : "text-slate-400"}>
              {known ? `${v.postal} ${v.city}` : cityQ && !suggestions.length ? "Byen findes ikke på listen" : "Vælg by fra listen - postnummeret udfyldes"}
            </span>
            <button type="button" className="font-semibold text-slate-500 underline" onClick={() => { setManual(true); set({ city: cityQ || v.city || "" }); }}>Tilføj manuelt</button>
          </>
        ) : (
          <>
            <span className="text-amber-700">Manuel by og postnummer</span>
            <button type="button" className="font-semibold text-slate-500 underline" onClick={() => { setManual(false); setCityQ(v.city || ""); }}>Brug listen</button>
          </>
        )}
      </div>
    </div>
  );
}
