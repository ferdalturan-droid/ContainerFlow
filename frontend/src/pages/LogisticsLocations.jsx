import React, { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MapPin, Plus, Edit2, X, Check, Loader2, Building2, CheckCircle2, PowerOff, Info, LocateFixed, ExternalLink } from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Lokationer for logistik admin (2026-10-16, se LOGISTICS_TIERS.md).
 *  - Premium logistikfirmaer: egne lokationer (depoter, faste kunders
 *    adresser, byggepladser ...) som de selv opretter og vedligeholder.
 *  - Genbrugsplads-kunders pladser vises read-only, og kun når firmaet er
 *    tilknyttet mindst én kunde.
 */

const card = "bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm";
const input = "w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";
const label = "block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1";
const btnPrimary = "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-50";
const btnGhost = "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700";

const EMPTY = { name: "", address: "", city: "", lat: "", lng: "" };

function LocationForm({ initial, onCancel, onSaved }) {
  const [f, setF] = useState({ ...EMPTY, ...initial, lat: initial?.lat ?? "", lng: initial?.lng ?? "" });
  const [saving, setSaving] = useState(false);
  const [gpsTouched, setGpsTouched] = useState(false);
  const [finding, setFinding] = useState(false);
  const [gpsNote, setGpsNote] = useState("");
  const addrChanged = (f.address || "") !== (initial?.address || "") || (f.city || "") !== (initial?.city || "");
  const findGps = async () => {
    const q = [f.address, f.city].map(x => (x || "").trim()).filter(Boolean).join(", ");
    if (!q) { toast.error("Skriv adresse og by først"); return; }
    setFinding(true);
    try {
      const { data } = await axios.get(`${API}/geocode`, { params: { q } });
      setF(x => ({ ...x, lat: Number(data.lat).toFixed(6), lng: Number(data.lng).toFixed(6) }));
      setGpsTouched(true);
      setGpsNote(data.source === "postnr" ? "Omtrentlig placering (byens midte) - ret gerne præcist" : (data.label || "Fundet"));
    } catch (e) { toast.error(formatApiError(e)); }
    setFinding(false);
  };
  const save = async () => {
    if (!f.name.trim()) { toast.error("Skriv et navn"); return; }
    setSaving(true);
    // Ændres adressen uden at GPS er rettet, sendes GPS tomt, så serveren
    // finder den nye placering automatisk.
    const resetGps = addrChanged && !gpsTouched;
    const body = {
      name: f.name.trim(), address: f.address.trim(), city: f.city.trim(),
      lat: resetGps || f.lat === "" ? null : Number(String(f.lat).replace(",", ".")),
      lng: resetGps || f.lng === "" ? null : Number(String(f.lng).replace(",", ".")),
    };
    try {
      if (initial?.id) await axios.put(`${API}/plads/${initial.id}`, body);
      else await axios.post(`${API}/plads`, body);
      toast.success(initial?.id ? "Lokationen er opdateret" : "Lokationen er oprettet");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };
  return (
    <div className="p-4 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/20 space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="md:col-span-1"><span className={label}>Navn</span>
          <input className={input} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Fx Depot Køge" autoFocus /></div>
        <div className="md:col-span-1"><span className={label}>Adresse</span>
          <input className={input} value={f.address} onChange={e => setF({ ...f, address: e.target.value })} placeholder="Vej og nr." /></div>
        <div><span className={label}>By</span>
          <input className={input} value={f.city} onChange={e => setF({ ...f, city: e.target.value })} /></div>
      </div>
      <div className="rounded-lg bg-white/70 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 p-3 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold flex items-center gap-1.5"><LocateFixed className="w-4 h-4 text-slate-400" /> GPS-placering</div>
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={findGps} disabled={finding}>{finding ? <Loader2 className="w-4 h-4 animate-spin" /> : <LocateFixed className="w-4 h-4" />} Find fra adressen</button>
            {f.lat !== "" && f.lng !== "" && (
              <a className={btnGhost} href={`https://www.google.com/maps/search/?api=1&query=${String(f.lat).replace(",", ".")},${String(f.lng).replace(",", ".")}`} target="_blank" rel="noreferrer"><ExternalLink className="w-4 h-4" /> Vis på kort</a>
            )}
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Bruges som startpunkt, når chaufføren trykker "Optimer rute": turene sorteres efter afstand fra lokationen, og der vises km pr. tur.
          Lader du felterne stå tomme, finder systemet placeringen automatisk ud fra adressen, når du gemmer.
          Skriv kun tal selv, hvis stedet ikke har en rigtig adresse (fx en byggeplads) - kopiér dem fra Google Maps (højreklik på stedet).
        </p>
        <div className="grid grid-cols-2 gap-3 max-w-md">
          <div><span className={label}>Breddegrad</span>
            <input className={input} inputMode="decimal" value={f.lat} onChange={e => { setGpsTouched(true); setF({ ...f, lat: e.target.value }); }} placeholder="Fx 55.4565" /></div>
          <div><span className={label}>Længdegrad</span>
            <input className={input} inputMode="decimal" value={f.lng} onChange={e => { setGpsTouched(true); setF({ ...f, lng: e.target.value }); }} placeholder="Fx 12.1820" /></div>
        </div>
        {gpsNote && <p className="text-[11px] text-emerald-700 dark:text-emerald-400">{gpsNote}</p>}
        {addrChanged && !gpsTouched && initial?.id && f.lat !== "" && <p className="text-[11px] text-amber-700">Adressen er ændret - GPS findes igen automatisk, når du gemmer.</p>}
      </div>
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onCancel}><X className="w-4 h-4" /> Annuller</button>
        <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem</button>
      </div>
    </div>
  );
}

function LocationRow({ p, badge, actions }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 py-3 border-t border-slate-100 dark:border-slate-700 first:border-t-0">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <MapPin className="w-4 h-4 text-emerald-600 shrink-0" />
          <span className="font-semibold">{p.name}</span>
          {p.location_code && <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-[10px] font-mono">{p.location_code}</span>}
          {p.lat && p.lng
            ? <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">GPS</span>
            : <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">Ingen GPS</span>}
          {badge}
        </div>
        {(p.address || p.city) && <div className="text-xs text-slate-500 ml-6 mt-0.5">{[p.address, p.city].filter(Boolean).join(", ")}</div>}
      </div>
      {actions}
    </div>
  );
}

export default function LogisticsLocations({ profile, pladsList = [], onChanged }) {
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirmOff, setConfirmOff] = useState(null);
  const ownId = profile?.company_id;
  const isPremium = !!profile?.is_premium;
  const own = pladsList.filter(p => ownId && p.company_id === ownId);
  const customerSites = pladsList.filter(p => !ownId || p.company_id !== ownId);
  const customerName = (cid) => (profile?.connected_customers || []).find(c => c.id === cid)?.name;

  const deactivate = async (p) => {
    try { await axios.delete(`${API}/plads/${p.id}`); toast.success(`${p.name} er deaktiveret`); setConfirmOff(null); onChanged(); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-5" data-testid="logistics-locations">
      {isPremium && (
        <section className={card}>
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-700">
            <div>
              <h2 className="font-bold text-lg flex items-center gap-2"><MapPin className="w-5 h-5 text-emerald-600" /> Mine lokationer</h2>
              <p className="text-xs text-slate-500">Depoter, faste kunders adresser, byggepladser m.m. Bruges når du opretter ture - chaufførerne finder dem under "Egne ture".</p>
            </div>
            {!creating && <button className={btnPrimary} onClick={() => { setCreating(true); setEditing(null); }}><Plus className="w-4 h-4" /> Ny lokation</button>}
          </div>
          {creating && <div className="p-4"><LocationForm onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); onChanged(); }} /></div>}
          {own.length === 0 && !creating && (
            <div className="p-8 text-center text-sm text-slate-500">Ingen lokationer endnu. Opret din første lokation for at kunne oprette egne ture.</div>
          )}
          {own.map(p => editing === p.id ? (
            <div key={p.id} className="p-4 border-t border-slate-100 dark:border-slate-700">
              <LocationForm initial={p} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />
            </div>
          ) : (
            <LocationRow key={p.id} p={p} actions={
              <div className="flex items-center gap-1 shrink-0">
                <button className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" title="Rediger" onClick={() => { setEditing(p.id); setCreating(false); }}><Edit2 className="w-4 h-4" /></button>
                {confirmOff === p.id ? (
                  <>
                    <button className="px-2 py-1 rounded-lg bg-red-600 text-white text-xs font-bold" onClick={() => deactivate(p)}>Deaktivér</button>
                    <button className="px-2 py-1 rounded-lg text-xs" onClick={() => setConfirmOff(null)}>Nej</button>
                  </>
                ) : (
                  <button className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600" title="Deaktivér (ture og historik bevares)" onClick={() => setConfirmOff(p.id)}><PowerOff className="w-4 h-4" /></button>
                )}
              </div>
            } />
          ))}
        </section>
      )}

      {(!isPremium || profile?.has_connections || customerSites.length > 0) && (
        <section className={card}>
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-700">
            <h2 className="font-bold text-lg flex items-center gap-2"><Building2 className="w-5 h-5 text-blue-600" /> {isPremium ? "Kunders genbrugspladser" : "Genbrugspladser"}</h2>
            <span className="text-xs text-slate-500 inline-flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Auto-synkroniseret fra kunder</span>
          </div>
          <div className="mx-4 my-3 flex gap-2 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-900 text-xs text-sky-900 dark:text-sky-100">
            <Info className="w-4 h-4 shrink-0" />
            Når en kunde tildeler jer som logistik-partner på en lokation, vises pladsen her automatisk. Kunden vedligeholder pladserne.
          </div>
          {customerSites.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">Ingen pladser endnu.</div>
          ) : customerSites.map(p => (
            <LocationRow key={p.id} p={p} badge={
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                Kunde: {customerName(p.company_id) || "Anden kunde"}
              </span>
            } />
          ))}
        </section>
      )}
    </div>
  );
}
