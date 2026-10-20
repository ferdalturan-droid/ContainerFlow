import React, { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { X, Truck, Check, Clock, Flag, Loader2 } from "lucide-react";
import { isHaster, openHours, todayStr } from "../lib/tourHelpers";

/**
 * Hængerkørsel (2026-10-20). Vises når en chauffør med hænger starter en
 * containertur: flere containere fra samme plads kan komme med (ikke
 * obligatorisk). Samme materiale står øverst, derefter andre materialer og
 * ture fra tidligere dage. Både chaufførens egne og ledige ture vises.
 * addMode: turen kører allerede - vælg den næste til hængeren.
 */
export default function DriverRunSheet({ anchor, active = [], candidates = [], slots = 0, trailerName = "", addMode = false, onConfirm, onClose }) {
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  const today = todayStr();
  const groups = useMemo(() => {
    const mat = (anchor?.fraction || "").trim().toLowerCase();
    const order = (a, b) => (a._mine === b._mine ? 0 : a._mine ? -1 : 1) || (isHaster(a) === isHaster(b) ? 0 : isHaster(a) ? -1 : 1)
      || String(openHours(a).to || "99").padStart(5, "0").localeCompare(String(openHours(b).to || "99").padStart(5, "0"));
    const past = (t) => (t.date || "").slice(0, 10) < today;
    const same = candidates.filter(t => !past(t) && (t.fraction || "").trim().toLowerCase() === mat).sort(order);
    const other = candidates.filter(t => !past(t) && (t.fraction || "").trim().toLowerCase() !== mat).sort(order);
    const old = candidates.filter(past).sort(order);
    return [
      { key: "same", title: `Samme materiale${anchor?.fraction ? ` (${anchor.fraction})` : ""}`, list: same },
      { key: "other", title: "Andre materialer", list: other },
      { key: "past", title: "Fra tidligere dage", list: old },
    ].filter(g => g.list.length);
  }, [anchor, candidates, today]);
  if (!anchor) return null;
  const toggle = (id) => setSel(s => (s.includes(id) ? s.filter(x => x !== id) : s.length >= slots ? s : [...s, id]));
  const confirm = async () => {
    setBusy(true);
    try { await onConfirm(sel); } finally { setBusy(false); }
  };
  const others = active.filter(t => t.id !== anchor.id);
  const label = addMode
    ? (sel.length ? `Læg ${sel.length === 1 ? "turen" : `${sel.length} ture`} på hængeren` : "Vælg en tur")
    : (sel.length ? `Start ${sel.length + 1} ture` : others.length ? "Start på hængeren" : "Start kun denne tur");
  const name = (t) => `${t.fraction || "Tur"}${t.container ? ` · #${t.container}` : ""}`;

  return createPortal(
    <div className="fixed inset-0 z-[85] flex items-end sm:items-center justify-center" data-testid="run-sheet">
      <div className="absolute inset-0 bg-slate-900/50" onClick={() => !busy && onClose()} />
      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl max-h-[88vh] flex flex-col"
        style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom))" }}>
        <div className="mx-auto mt-2 w-10 h-1.5 rounded-full bg-slate-200 sm:hidden" />
        <div className="px-5 pt-3 pb-2 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-extrabold text-slate-900">{addMode ? "Tilføj tur på hængeren" : "Kører du flere containere?"}</h3>
            <p className="text-[13px] text-slate-500">
              {anchor.plads || "Pladsen"}{trailerName ? ` · hænger ${trailerName}` : ""} · {slots > 0 ? `plads til ${slots} mere` : "hængeren er fuld"}
            </p>
          </div>
          <button onClick={() => !busy && onClose()} className="p-2 -mr-2 text-slate-500" aria-label="Luk"><X className="w-5 h-5" /></button>
        </div>
        <div className="px-4 overflow-y-auto space-y-3">
          <div className="rounded-xl bg-slate-50 border border-slate-200 px-3 py-2 text-[13px]" data-testid="run-sheet-current">
            {(addMode ? active : [...others, anchor]).map((t, i) => (
              <div key={t.id} className="flex items-center gap-2 py-0.5">
                <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold ${i === 0 ? "bg-slate-900 text-white" : "bg-violet-600 text-white"}`}>{i === 0 ? "Bil" : "Hænger"}</span>
                <span className="font-semibold text-slate-800 truncate">{name(t)}</span>
                {t.id === anchor.id && !addMode && <span className="text-[11px] text-slate-500 shrink-0">starter nu</span>}
              </div>
            ))}
            {!addMode && others.length > 0 && (
              <p className="mt-1 text-[12px] text-slate-500">Du kører allerede {others.length === 1 ? "en tur" : `${others.length} ture`}. Er den færdig, så afslut den først.</p>
            )}
          </div>
          {slots > 0 && groups.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 px-3 py-3 text-sm text-slate-600" data-testid="run-sheet-empty">
              Ingen andre ture på {anchor.plads || "pladsen"} lige nu.
              <span className="block text-[12px] text-slate-500 mt-0.5">Bliver en container mere klar, kan du lægge den på hængeren inde i turen ("Tilføj tur på hængeren").</span>
            </div>
          )}
          {slots > 0 && groups.map(g => (
            <section key={g.key} className="space-y-1.5">
              <div className="flex items-center gap-1.5 px-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">
                {g.key === "past" && <Clock className="w-3.5 h-3.5 text-amber-600" />}{g.title}
              </div>
              <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden">
                {g.list.map(t => {
                  const on = sel.includes(t.id);
                  const full = !on && sel.length >= slots;
                  const oh = openHours(t);
                  return (
                    <button key={t.id} type="button" onClick={() => toggle(t.id)} disabled={full} data-testid={`run-candidate-${t.id}`}
                      className={`w-full text-left px-3 py-2.5 flex items-center gap-3 ${on ? "bg-violet-50" : "bg-white"} ${full ? "opacity-40" : "active:bg-slate-50"}`}>
                      <span className={`w-6 h-6 shrink-0 rounded-md border-2 flex items-center justify-center ${on ? "bg-violet-600 border-violet-600 text-white" : "border-slate-300"}`}>
                        {on && <Check className="w-4 h-4" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-bold text-[14px] text-slate-900 truncate">{name(t)}</span>
                        <span className="flex items-center gap-1.5 text-[12px] text-slate-500 flex-wrap">
                          {isHaster(t) && <span className="inline-flex items-center gap-0.5 font-bold text-rose-600"><Flag className="w-3 h-3" />Haster</span>}
                          {oh.from && <span>{oh.from}–{oh.to}</span>}
                          {g.key === "past" && <span>{t.date}</span>}
                          <span className={`px-1.5 rounded ${t._mine ? "bg-indigo-50 text-indigo-700" : "bg-orange-50 text-orange-700"} font-bold`}>{t._mine ? "Din tur" : "Ledig"}</span>
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
        <div className="px-4 pt-3 flex gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="h-12 px-4 rounded-xl border border-slate-200 text-slate-700 font-bold">Annuller</button>
          <button type="button" onClick={confirm} disabled={busy || (addMode && !sel.length)} data-testid="run-sheet-confirm"
            className="flex-1 h-12 rounded-xl bg-orange-500 active:bg-orange-600 disabled:opacity-50 text-white font-extrabold inline-flex items-center justify-center gap-2">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Truck className="w-4 h-4" />} {label}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
