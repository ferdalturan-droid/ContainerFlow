import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import { X, Camera, Loader2, CheckCircle2, Trash2, AlertTriangle, Minus, Plus } from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * "Afslut tur" for ture hvor planlæggeren har valgt hvad der skal
 * registreres (tour.capture, sat i Ny tur). 2026-10-17.
 *
 * Ét samlet trin i stedet for spredte felter:
 *  1. Mængde pr. linje i linjens enhed (paller, stk, kg ...) - kun hvis valgt.
 *  2. Billede - kun hvis valgt. Uploades straks (ingen tab ved iOS-reload).
 *  3. Hængere: hvor mange der faktisk blev brugt (bruges til afregning).
 *  4. Ventetid (sendes til godkendelse hos planlæggeren).
 *  5. Afvigelse / besked til planlæggeren (lander i turens beskedtråd).
 * Mangler noget af det valgte, får chaufføren en blød påmindelse - aldrig en
 * blokering, for chaufføren kender virkeligheden bedst.
 */
const QUICK_NOTES = ["Mere end planlagt", "Mindre end planlagt", "Kunden var ikke til stede", "Skade/mangler", "Ekstra stop"];

const compress = (file) => new Promise((resolve) => {
  const img = new window.Image();
  const url = URL.createObjectURL(file);
  img.onload = () => {
    URL.revokeObjectURL(url);
    const max = 1280;
    const k = Math.min(1, max / Math.max(img.width, img.height));
    const c = document.createElement("canvas");
    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    resolve(c.toDataURL("image/jpeg", 0.72));
  };
  img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
  img.src = url;
});

const num = (v) => {
  if (v === "" || v == null) return null;
  let s = String(v).replace(/\s/g, "");
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? n : null;
};

export default function FinishSheet({ tour, onClose, onDone, driverName, myId }) {
  const cap = tour?.capture || {};
  const lines = Array.isArray(tour?.cargo_lines) ? tour.cargo_lines : [];
  const editMode = !!tour?.completed;
  const plannedTrailers = Number(tour?.trailer_count || 0);
  const [qty, setQty] = useState(() => lines.map(l => (l.actual_qty != null ? String(l.actual_qty) : "")));
  const [weight, setWeight] = useState(() => (tour?.weight ? String(tour.weight) : ""));
  const [photos, setPhotos] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [trailers, setTrailers] = useState(() => (tour?.trailer_count_actual != null ? tour.trailer_count_actual : (plannedTrailers || (tour?.used_trailer ? 1 : 0))));
  const [waiting, setWaiting] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const stops = Array.isArray(tour?.stops) ? tour.stops : [];
  const openStops = stops.filter(s => !s.done_at).length;

  useEffect(() => {
    if (!tour?.id || !(tour.photo_count > 0)) return;
    axios.get(`${API}/tours/${tour.id}/photos`).then(r => setPhotos(r.data || [])).catch(() => {});
  }, [tour?.id, tour?.photo_count]);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);
  if (!tour) return null;

  const addPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const dataUrl = await compress(file);
      if (!dataUrl) throw new Error("Billedet kunne ikke læses");
      const { data } = await axios.post(`${API}/tours/${tour.id}/photos`, { image: dataUrl });
      setPhotos(p => [...p, { id: data.id, url: dataUrl }]);
    } catch (err) { toast.error(formatApiError(err)); }
    setUploading(false);
  };
  const delPhoto = async (pid) => {
    try { await axios.delete(`${API}/tours/${tour.id}/photos/${pid}`); setPhotos(p => p.filter(x => x.id !== pid)); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const missing = [];
  if (cap.quantity) {
    if (lines.length) lines.forEach((l, i) => { if (num(qty[i]) == null) missing.push(`mængde for ${l.text}`); });
    else if (num(weight) == null) missing.push("vægt");
  }
  if (cap.photo && photos.length === 0) missing.push("billede");
  if (openStops && !editMode) missing.push(`${openStops} stop er ikke krydset af`);

  const submit = async () => {
    if (missing.length) {
      let go = true;
      try { go = window.confirm(`Du mangler: ${missing.join(", ")}.\n\n${editMode ? "Gem alligevel?" : "Afslut turen alligevel?"}`); } catch (_) { /* ok */ }
      if (!go) return;
    }
    setBusy(true);
    try {
      const me = { claimed_by: tour.claimed_by || driverName, claimed_by_id: tour.claimed_by_id || myId };
      const regs = {};
      if (cap.quantity || lines.some(l => l.actual_qty != null)) {
        if (lines.length) regs.cargo_actuals = qty.map(num);
        else if (num(weight) != null) regs.weight = num(weight);
      }
      if (!editMode) {
        // Hænger-oplysningen gemmes altid eksplicit (den styrer afregningen).
        await axios.put(`${API}/driver/tours/${tour.id}/trailer`, { used_trailer: trailers > 0, trailer_count: trailers });
        await axios.put(`${API}/tours/${tour.id}`, {
          completed: true, on_way: false, time: new Date().toTimeString().slice(0, 5), ...regs, ...me,
        });
        if (note.trim()) await axios.post(`${API}/tour-messages/${tour.id}`, { text: note.trim() }).catch(() => {});
        const w = parseInt(waiting, 10);
        if (w > 0) {
          await axios.post(`${API}/driver/tours/${tour.id}/change-request`, { waiting_min: w, comment: `Ventetid oplyst ved afslutning${note.trim() ? `: ${note.trim()}` : ""}` })
            .then(() => toast.message("Ventetid sendt til godkendelse"))
            .catch((err) => toast.error(formatApiError(err)));
        }
        toast.success("Turen er afsluttet");
      } else {
        await axios.put(`${API}/tours/${tour.id}`, { ...regs, ...me });
        toast.success("Registreringen er rettet");
      }
      onDone?.();
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    setBusy(false);
  };

  const ic = "w-full px-3 py-3 rounded-xl border border-slate-200 bg-white text-base focus:outline-none focus:ring-2 focus:ring-emerald-500/40";
  const sectionTitle = "text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2";

  return createPortal(
    <div className="fixed inset-0 z-[95] flex items-end sm:items-center justify-center" data-testid="finish-sheet">
      <div className="absolute inset-0 bg-slate-900/50" onClick={() => !busy && onClose()} />
      <div className="relative w-full sm:max-w-lg bg-slate-50 rounded-t-3xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[92vh]">
        <div className="px-5 pt-3 pb-3 bg-white rounded-t-3xl sm:rounded-t-2xl border-b border-slate-100">
          <div className="mx-auto mb-2 w-10 h-1.5 rounded-full bg-slate-200 sm:hidden" />
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <h3 className="text-lg font-extrabold text-slate-900">{editMode ? "Ret registrering" : "Afslut tur"}</h3>
              <p className="text-sm text-slate-500 truncate">{tour.fraction} · {tour.address}</p>
            </div>
            <button onClick={onClose} className="p-2 -mr-2 text-slate-500" aria-label="Luk"><X className="w-5 h-5" /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {openStops > 0 && !editMode && (
            <div className="flex gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5 text-sm text-amber-900">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {openStops} af {stops.length} stop er ikke krydset af. Kryds dem af i turen, eller skriv hvorfor nedenfor.
            </div>
          )}

          {cap.quantity && (
            <section data-testid="finish-quantity">
              <div className={sectionTitle}>Registrér mængde</div>
              {lines.length ? (
                <div className="space-y-2.5">
                  {lines.map((l, i) => (
                    <div key={i} className="rounded-xl bg-white border border-slate-200 p-3">
                      <div className="flex items-baseline justify-between gap-2 mb-1.5">
                        <span className="font-semibold text-slate-800">{l.trailer ? `H${l.trailer} · ` : ""}{l.text}</span>
                        {l.qty != null && <span className="text-xs text-slate-500">Planlagt {Number(l.qty).toLocaleString("da-DK")} {l.unit}</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <input className={ic} inputMode="decimal" value={qty[i]} placeholder={l.unit === "kg" ? "Vægt" : "Antal"}
                          onChange={(e) => setQty(qty.map((x, j) => (j === i ? e.target.value : x)))} data-testid={`finish-qty-${i}`} />
                        <span className="w-14 text-sm font-semibold text-slate-600">{l.unit || "stk"}</span>
                      </div>
                      {l.qty != null && qty[i] === "" && (
                        <button type="button" className="mt-1.5 text-xs font-semibold text-emerald-700" onClick={() => setQty(qty.map((x, j) => (j === i ? String(l.qty).replace(".", ",") : x)))}>Som planlagt ({Number(l.qty).toLocaleString("da-DK")} {l.unit})</button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <input className={ic} inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="Vægt" data-testid="finish-weight" />
                  <span className="w-14 text-sm font-semibold text-slate-600">kg</span>
                </div>
              )}
            </section>
          )}

          {(cap.photo || photos.length > 0) && (
            <section data-testid="finish-photo">
              <div className={sectionTitle}>Billede{cap.photo ? "" : " (valgfrit)"}</div>
              <div className="flex flex-wrap gap-2">
                {photos.map(p => (
                  <div key={p.id} className="relative w-20 h-20 rounded-xl overflow-hidden border border-slate-200">
                    <img src={p.url} alt="" className="w-full h-full object-cover" />
                    {!editMode && <button type="button" onClick={() => delPhoto(p.id)} className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white flex items-center justify-center" aria-label="Slet billede"><Trash2 className="w-3.5 h-3.5" /></button>}
                  </div>
                ))}
                <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}
                  className="w-20 h-20 rounded-xl border-2 border-dashed border-slate-300 text-slate-500 flex flex-col items-center justify-center gap-1 text-[11px] font-semibold" data-testid="finish-photo-add">
                  {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Camera className="w-5 h-5" />} {uploading ? "Gemmer" : "Tag billede"}
                </button>
                <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={addPhoto} />
              </div>
            </section>
          )}

          {!editMode && (
            <section>
              <div className={sectionTitle}>Hængere</div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-slate-700">
                    {plannedTrailers ? `Hvor mange hængere brugte du? (planlagt ${plannedTrailers})` : "Kørte du med hænger på turen?"}
                    <div className="text-[11px] text-slate-500">Bruges til afregningen af turen.</div>
                  </div>
                  {plannedTrailers ? (
                    <div className="flex items-center gap-2">
                      <button type="button" className="w-10 h-10 rounded-xl border border-slate-200 flex items-center justify-center" onClick={() => setTrailers(Math.max(0, trailers - 1))} aria-label="Færre"><Minus className="w-4 h-4" /></button>
                      <span className="w-6 text-center text-lg font-extrabold" data-testid="finish-trailers">{trailers}</span>
                      <button type="button" className="w-10 h-10 rounded-xl border border-slate-200 flex items-center justify-center" onClick={() => setTrailers(Math.min(9, trailers + 1))} aria-label="Flere"><Plus className="w-4 h-4" /></button>
                    </div>
                  ) : (
                    <div className="inline-flex p-0.5 rounded-lg bg-slate-100">
                      {[[0, "Nej"], [1, "Ja"]].map(([v, l]) => (
                        <button key={l} type="button" onClick={() => setTrailers(v)} className={`px-4 py-2 rounded-md text-sm font-bold ${(trailers > 0 ? 1 : 0) === v ? "bg-white shadow-sm text-slate-900" : "text-slate-500"}`}>{l}</button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {!editMode && (
            <section>
              <div className={sectionTitle}>Ventetid (valgfri)</div>
              <div className="flex items-center gap-2">
                <input className={ic} inputMode="numeric" value={waiting} onChange={(e) => setWaiting(e.target.value.replace(/\D/g, ""))} placeholder="Minutter du ventede på stedet" data-testid="finish-waiting" />
                <span className="w-14 text-sm font-semibold text-slate-600">min</span>
              </div>
              <p className="text-[11px] text-slate-500 mt-1">Sendes til godkendelse hos planlæggeren.</p>
            </section>
          )}

          {!editMode && (
            <section>
              <div className={sectionTitle}>Afvigelse eller besked til planlæggeren (valgfri)</div>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {QUICK_NOTES.map(q => (
                  <button key={q} type="button" onClick={() => setNote(n => (n ? `${n}. ${q}` : q))} className="px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs font-semibold text-slate-600">{q}</button>
                ))}
              </div>
              <textarea rows={2} className={ic} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Fx kun 10 paller klar - resten hentes i morgen" data-testid="finish-note" />
            </section>
          )}
        </div>

        <div className="px-5 py-3 bg-white border-t border-slate-100" style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom))" }}>
          {missing.length > 0 && <p className="text-xs text-amber-700 mb-2">Mangler: {missing.join(", ")}</p>}
          <button type="button" onClick={submit} disabled={busy} data-testid="finish-submit"
            className="w-full min-h-[52px] rounded-xl bg-emerald-600 active:bg-emerald-700 text-white font-extrabold text-base inline-flex items-center justify-center gap-2 disabled:opacity-60">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle2 className="w-5 h-5" />} {editMode ? "Gem rettelse" : "Afslut tur"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
