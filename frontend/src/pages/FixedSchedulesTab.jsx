import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CalendarClock, Plus, Edit2, Pause, Play, Square, Loader2, X, Check, AlertTriangle } from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Faste tømninger (2026-10-19).
 * Lokationsadmin / kundeadmin sætter en fast tømning op pr. container, fx
 * "Container 1 · Pap: hver mandag, uge 14-43". Serveren laver hver tømning om
 * til en almindelig bestilling 7 dage før - med leveringsadressen for netop
 * den dag fra kundens kalender. Medarbejderne ser dem under Mine bestillinger,
 * kan springe en over og bestille ekstra.
 */
const WD = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];
const EVERY = [[1, "Hver uge"], [2, "Hver 2. uge"], [3, "Hver 3. uge"], [4, "Hver 4. uge"]];
const NTH = [[1, "Første"], [2, "Anden"], [3, "Tredje"], [4, "Fjerde"], [5, "Sidste"]];
const TYPES = [["normal", "Afhent container"], ["flyt", "Byt container"]];
const PRIO = [["normal", "Normal"], ["haster", "Haster"], ["senere", "Lav"]];
const input = "w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40 disabled:opacity-60";
const label = "block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1";
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const todayYmd = () => ymd(new Date());
const fmtDay = (s) => {
  try { return new Date(`${s}T12:00:00`).toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "numeric" }); } catch (_) { return s; }
};

/** Samme regel som serveren (_fixed_dates): ugedage + hver N. uge fra startugen. */
function nextDates(f, n = 6) {
  if (!f.weekdays.length || !f.start_date) return [];
  const start = new Date(`${f.start_date}T12:00:00`);
  const anchor = new Date(start); anchor.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const end = f.end_date ? new Date(`${f.end_date}T12:00:00`) : null;
  const from = new Date(`${todayYmd()}T12:00:00`);
  const out = [];
  for (let d = new Date(Math.max(from, start)), i = 0; i < 400 && out.length < n; i++, d.setDate(d.getDate() + 1)) {
    if (end && d > end) break;
    const wd = (d.getDay() + 6) % 7;
    if (!f.weekdays.includes(wd)) continue;
    const nth = Number(f.monthly_nth || 0);
    if (nth) {
      const next = new Date(d); next.setDate(d.getDate() + 7);
      const last = next.getMonth() !== d.getMonth();
      if ((nth === 5 && last) || (nth < 5 && Math.floor((d.getDate() - 1) / 7) + 1 === nth)) out.push(ymd(d));
    } else {
      const weeks = Math.floor(Math.round((d - anchor) / 86400000) / 7);
      if (weeks % Number(f.interval_weeks || 1) === 0) out.push(ymd(d));
    }
  }
  return out;
}

function ScheduleForm({ code, initial, onClose, onSaved }) {
  const edit = !!initial?.id;
  const [f, setF] = useState(() => ({
    partner_id: initial?.partner_id || "", material: initial?.material || "", container_number: initial?.container_number || "",
    tour_type: initial?.tour_type || "normal", weekdays: initial?.weekdays || [0], interval_weeks: initial?.interval_weeks || 1,
    monthly_nth: initial?.monthly_nth || 0,
    start_date: initial?.start_date || todayYmd(), end_date: initial?.end_date || "", priority: initial?.priority || "normal",
    comment: initial?.comment || "", other: false,
  }));
  const [partners, setPartners] = useState([]);
  const [mats, setMats] = useState(null);
  const [containers, setContainers] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));

  useEffect(() => {
    axios.get(`${API}/locations/${code}/partners`).then(r => {
      const ps = r.data?.partners || [];
      setPartners(ps);
      if (!edit && ps.length === 1) set("partner_id", ps[0].id);
    }).catch(() => setPartners([]));
  }, [code]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!f.partner_id) { setMats([]); return; }
    axios.get(`${API}/locations/${code}/containers`, { params: { partner_id: f.partner_id } })
      .then(r => setMats((r.data?.materials || []).map(m => m.material))).catch(() => setMats([]));
  }, [code, f.partner_id]);
  useEffect(() => {
    if (!f.material || !f.partner_id) { setContainers([]); return; }
    axios.get(`${API}/locations/${code}/containers`, { params: { partner_id: f.partner_id, material: f.material } })
      .then(r => setContainers(r.data?.containers || [])).catch(() => setContainers([]));
  }, [code, f.partner_id, f.material]);

  const preview = useMemo(() => nextDates(f), [f]);
  const save = async () => {
    if (!f.partner_id) { toast.error("Vælg logistikpartner"); return; }
    if (!f.material || !f.container_number.trim()) { toast.error("Vælg materiale og container"); return; }
    if (!f.weekdays.length) { toast.error("Vælg mindst én ugedag"); return; }
    setSaving(true);
    try {
      const body = { location_code: code, ...f, container_number: f.container_number.trim() };
      const { data } = edit ? await axios.put(`${API}/org/fixed-schedules/${initial.id}`, body) : await axios.post(`${API}/org/fixed-schedules`, body);
      const made = (data.generated || []).filter(g => g.status === "created").length;
      toast.success(`${edit ? "Den faste tømning er rettet" : "Den faste tømning er oprettet"}${made ? ` - ${made} tømning${made === 1 ? "" : "er"} er bestilt de næste 7 dage` : ""}${data.cancelled ? ` · ${data.cancelled} annulleret` : ""}`);
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    setSaving(false);
  };
  const chip = (on) => `px-3 py-1.5 rounded-lg text-xs font-bold border ${on ? "bg-emerald-600 border-emerald-600 text-white" : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`;

  return (
    <div className="bg-white dark:bg-slate-800 border border-emerald-200 dark:border-emerald-900 rounded-xl p-4 space-y-4" data-testid="fixed-form">
      <div className="flex items-center justify-between">
        <p className="font-bold text-slate-900 dark:text-white">{edit ? "Ret fast tømning" : "Ny fast tømning"}</p>
        <button onClick={onClose} className="p-1.5 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700" aria-label="Luk"><X className="w-4 h-4" /></button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <span className={label}>Logistikpartner</span>
          <select className={input} value={f.partner_id} disabled={edit} onChange={(e) => setF(p => ({ ...p, partner_id: e.target.value, material: "", container_number: "" }))} data-testid="fixed-partner">
            <option value="">Vælg…</option>
            {partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <span className={label}>Materiale</span>
          <select className={input} value={f.material} disabled={edit || !f.partner_id} onChange={(e) => setF(p => ({ ...p, material: e.target.value, container_number: "", other: false }))} data-testid="fixed-material">
            <option value="">{mats === null ? "Henter…" : "Vælg…"}</option>
            {(mats || []).map(m => <option key={m} value={m}>{m}</option>)}
            {edit && f.material && !(mats || []).includes(f.material) && <option value={f.material}>{f.material}</option>}
          </select>
        </div>
        <div>
          <span className={label}>Container</span>
          {containers.length > 0 && !f.other && !edit ? (
            <select className={input} value={f.container_number} onChange={(e) => (e.target.value === "__other" ? setF(p => ({ ...p, other: true, container_number: "" })) : set("container_number", e.target.value))} data-testid="fixed-container">
              <option value="">Vælg…</option>
              {containers.map(c => <option key={c.label} value={c.label}>{c.label}{c.container_id ? ` · ${c.container_id}` : ""}{c.capacity_label ? ` · ${c.capacity_label}` : ""}</option>)}
              <option value="__other">Anden container…</option>
            </select>
          ) : (
            <input className={input} value={f.container_number} disabled={edit} onChange={(e) => set("container_number", e.target.value)} placeholder="Fx Container 2" data-testid="fixed-container-text" />
          )}
        </div>
        <div>
          <span className={label}>Opgave</span>
          <div className="flex gap-1.5">
            {TYPES.map(([k, l]) => <button key={k} type="button" disabled={edit} className={chip(f.tour_type === k)} onClick={() => set("tour_type", k)}>{l}</button>)}
          </div>
        </div>
      </div>
      {edit && <p className="text-[11px] text-slate-500">Partner, materiale, container og opgave er selve tømningen. Skal de ændres, så stop den og opret en ny.</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <span className={label}>Hvornår</span>
          <div className="flex flex-wrap gap-1.5" data-testid="fixed-weekdays">
            {WD.map((l, i) => {
              const on = f.weekdays.includes(i);
              return <button key={l} type="button" className={`${chip(on)} w-12`} onClick={() => set("weekdays", on ? f.weekdays.filter(x => x !== i) : [...f.weekdays, i].sort())}>{l}</button>;
            })}
          </div>
          <div className="inline-flex p-0.5 rounded-lg bg-slate-100 dark:bg-slate-900" data-testid="fixed-mode">
            {[[false, "Ugentligt"], [true, "Månedligt"]].map(([m, l]) => (
              <button key={l} type="button" onClick={() => set("monthly_nth", m ? (Number(f.monthly_nth) || 1) : 0)}
                className={`px-3 py-1 rounded-md text-xs font-bold ${!!Number(f.monthly_nth) === m ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-white" : "text-slate-500"}`}>{l}</button>
            ))}
          </div>
          {Number(f.monthly_nth) ? (
            <div className="flex flex-wrap gap-1.5" data-testid="fixed-nth">
              {NTH.map(([n, l]) => <button key={n} type="button" className={chip(Number(f.monthly_nth) === n)} onClick={() => set("monthly_nth", n)}>{l}</button>)}
              <span className="text-xs text-slate-500 self-center">valgte ugedag i måneden</span>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {EVERY.map(([n, l]) => <button key={n} type="button" className={chip(Number(f.interval_weeks) === n)} onClick={() => set("interval_weeks", n)}>{l}</button>)}
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><span className={label}>Fra</span><input type="date" className={input} value={f.start_date} onChange={(e) => set("start_date", e.target.value)} data-testid="fixed-start" /></div>
          <div><span className={label}>Til <span className="normal-case font-normal">(valgfri, fx sæsonens slut)</span></span><input type="date" className={input} value={f.end_date} min={f.start_date} onChange={(e) => set("end_date", e.target.value)} /></div>
          <div>
            <span className={label}>Prioritet</span>
            <div className="flex gap-1.5">{PRIO.map(([k, l]) => <button key={k} type="button" className={chip(f.priority === k)} onClick={() => set("priority", k)}>{l}</button>)}</div>
          </div>
          <div><span className={label}>Kommentar</span><input className={input} value={f.comment} onChange={(e) => set("comment", e.target.value)} placeholder="Fx adgang via port 2" /></div>
        </div>
      </div>
      <div className="rounded-lg bg-slate-50 dark:bg-slate-900 px-3 py-2 text-sm text-slate-700 dark:text-slate-200" data-testid="fixed-preview">
        <b>Næste tømninger:</b> {preview.length ? preview.map(fmtDay).join(", ") : "ingen - vælg ugedage"}
        <p className="text-[11px] text-slate-500 mt-0.5">Hver tømning bliver en almindelig bestilling 7 dage før, med leveringsadressen fra jeres kalender for dagen. Lukkede dage og helligdage springes over.</p>
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-sm font-semibold text-slate-700 dark:text-slate-200">Annuller</button>
        <button onClick={save} disabled={saving} data-testid="fixed-save"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} {edit ? "Gem" : "Opret"}
        </button>
      </div>
    </div>
  );
}

export default function FixedSchedulesTab({ locations: locProp = null }) {
  const [locations, setLocations] = useState(locProp || []);
  useEffect(() => {
    if (locProp) { setLocations(locProp); return; }
    axios.get(`${API}/org/locations`).then(r => setLocations(r.data || [])).catch(() => setLocations([]));
  }, [locProp]);
  const codes = locations.map(l => l.code || l.location_code).filter(Boolean);
  const [code, setCode] = useState("");
  useEffect(() => { if (!code && codes.length) setCode(codes[0]); }, [codes.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const loc = locations.find(l => (l.code || l.location_code) === code);
  const [items, setItems] = useState(null);
  const [form, setForm] = useState(null);
  const load = useCallback(() => {
    if (!code) return;
    axios.get(`${API}/org/fixed-schedules`, { params: { location_code: code } })
      .then(r => setItems(r.data || [])).catch(e => { setItems([]); toast.error(formatApiError(e)); });
  }, [code]);
  useEffect(() => { setItems(null); setForm(null); load(); }, [load]);

  const act = async (s, what) => {
    const msg = { pause: "Sæt på pause? De bestilte tømninger, der ikke er startet, annulleres.", stop: "Stop den faste tømning? De bestilte tømninger, der ikke er startet, annulleres." }[what];
    if (msg && !window.confirm(msg)) return;
    try {
      const { data } = what === "stop" ? await axios.delete(`${API}/org/fixed-schedules/${s.id}`)
        : await axios.post(`${API}/org/fixed-schedules/${s.id}/${what}`, {});
      toast.success(what === "resume" ? "Genoptaget" : `${what === "pause" ? "Sat på pause" : "Stoppet"}${data.cancelled ? ` - ${data.cancelled} tømning${data.cancelled === 1 ? "" : "er"} annulleret` : ""}`);
      load();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-6" data-testid="fixed-schedules-tab">
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lokation:</p>
          {locations.map(l => {
            const c = l.code || l.location_code; const on = c === code;
            return <button key={c} onClick={() => setCode(c)} className={`px-3 py-1.5 rounded-lg text-xs font-bold ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`}>{l.name}</button>;
          })}
        </div>
      )}
      <div>
        <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">Faste tømninger{loc && <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {loc.name}</span>}</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">Containere der tømmes på faste dage, fx pap hver mandag i sæsonen. Hver tømning bliver en almindelig bestilling 7 dage før - medarbejderne kan springe en over, hvis containeren ikke er fuld, og bestille ekstra, hvis den bliver fuld før tid.</p>
      </div>
      {form ? (
        <ScheduleForm code={code} initial={form === "new" ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />
      ) : (
        <div className="flex justify-end">
          <button onClick={() => setForm("new")} disabled={!code} data-testid="fixed-new"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold disabled:opacity-50">
            <Plus className="w-3.5 h-3.5" /> Ny fast tømning
          </button>
        </div>
      )}
      {items === null ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Indlæser…</div>
      ) : items.length === 0 ? (
        <div className="bg-slate-50 dark:bg-slate-800/50 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-6 text-center text-sm text-slate-500 dark:text-slate-400">
          Ingen faste tømninger på pladsen endnu.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {items.map(s => {
            const booked = (s.upcoming_orders || []).filter(o => o.status !== "cancelled");
            return (
              <div key={s.id} className={`bg-white dark:bg-slate-800 border rounded-xl p-4 ${s.paused ? "border-amber-200 dark:border-amber-900" : "border-slate-200 dark:border-slate-700"}`} data-testid={`fixed-row-${s.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-900 dark:text-white inline-flex items-center gap-1.5"><CalendarClock className="w-4 h-4 text-emerald-600" /> {s.material} · {s.container_number}</p>
                    <p className="text-sm text-slate-700 dark:text-slate-200 mt-0.5">{TYPES.find(t => t[0] === s.tour_type)?.[1]} · {s.text}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{s.partner_name}{s.priority !== "normal" ? ` · ${PRIO.find(p => p[0] === s.priority)?.[1]}` : ""}{s.comment ? ` · ${s.comment}` : ""}</p>
                  </div>
                  {s.paused && <span className="shrink-0 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[11px] font-bold">På pause</span>}
                </div>
                {!s.paused && (
                  <p className="text-xs text-slate-600 dark:text-slate-300 mt-2"><b>Næste:</b> {(s.next_dates || []).map(fmtDay).join(", ") || "ingen (perioden er slut)"}</p>
                )}
                {booked.length > 0 && <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">{booked.length} bestilt: {booked.map(o => fmtDay(o.order_date)).join(", ")}</p>}
                {(s.problems || []).map((p, i) => (
                  <p key={i} className="text-xs text-amber-800 dark:text-amber-300 mt-1 inline-flex items-start gap-1"><AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {fmtDay(p.date)}: {p.note || "ikke oprettet"}</p>
                ))}
                <div className="flex gap-1.5 mt-3">
                  <button onClick={() => setForm(s)} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200" data-testid={`fixed-edit-${s.id}`}><Edit2 className="w-3.5 h-3.5" /> Ret</button>
                  {s.paused
                    ? <button onClick={() => act(s, "resume")} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200"><Play className="w-3.5 h-3.5" /> Genoptag</button>
                    : <button onClick={() => act(s, "pause")} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200"><Pause className="w-3.5 h-3.5" /> Pause</button>}
                  <button onClick={() => act(s, "stop")} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-rose-200 dark:border-rose-900 text-xs font-semibold text-rose-600" data-testid={`fixed-stop-${s.id}`}><Square className="w-3.5 h-3.5" /> Stop</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
