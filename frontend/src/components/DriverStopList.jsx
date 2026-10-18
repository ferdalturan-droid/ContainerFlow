import React, { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Check, Navigation, Phone, Plus, X, AlertTriangle, Loader2 } from "lucide-react";
import { API, formatApiError } from "../auth/api";
import { fmtClock } from "../lib/tourHelpers";
import { enqueueOp, isNetworkError } from "../lib/tourOpQueue";

/**
 * Chaufførens stop på en tur (2026-10-18).
 *  - Note og kontakt pr. stop (ring direkte til modtageren).
 *  - Kryds af - ved aflevering kan modtagerens navn skrives (kvittering).
 *  - "Kunne ikke gennemføres" for ÉT stop med årsagskode; turen kører videre.
 *  - "Tilføj stop" når kunden beder om et stop mere (planlæggeren godkender
 *    det før det tæller i prisen).
 *  - Uden net: krydset gemmes på telefonen og sendes når der er forbindelse.
 */
export default function DriverStopList({ tour, stops, canTick, onChanged, codes = [], canAdd = true }) {
  const [receiver, setReceiver] = useState({});
  const [issueFor, setIssueFor] = useState(null);
  const [issueText, setIssueText] = useState("");
  const [adding, setAdding] = useState(null);
  const [busy, setBusy] = useState(false);

  const post = async (st, body, optimistic) => {
    try {
      const { data } = await axios.post(`${API}/tours/${tour.id}/stops/${st.id}/done`, body);
      onChanged(data.stops || []);
    } catch (e) {
      if (isNetworkError(e)) {
        enqueueOp({ kind: "stop", tour_id: tour.id, stop_id: st.id, body });
        onChanged(stops.map(x => (x.id === st.id ? { ...x, ...optimistic, queued: true } : x)), true);
        toast.message("Ingen forbindelse - stoppet sendes når der er net");
      } else toast.error(formatApiError(e, "Kunne ikke opdatere stoppet"));
    }
  };
  const tick = (st) => {
    const done = !st.done_at;
    const name = (receiver[st.id] || "").trim();
    post(st, { done, ...(done && st.kind === "delivery" && name ? { receiver_name: name } : {}) },
      { done_at: done ? new Date().toISOString() : "", receiver_name: done ? name : st.receiver_name });
  };
  const reportIssue = (st, code) => {
    post(st, { done: true, issue: { code, text: issueText.trim() } }, { done_at: new Date().toISOString(), issue: { code, text: issueText.trim() } });
    setIssueFor(null); setIssueText("");
  };
  const addStop = async () => {
    if (!(adding.street || "").trim()) { toast.error("Skriv adressen"); return; }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/tours/${tour.id}/stops`, adding);
      onChanged(data.stops || []);
      setAdding(null);
      toast.success("Stoppet er tilføjet - planlæggeren kan se det");
    } catch (e) { toast.error(formatApiError(e)); }
    setBusy(false);
  };
  const ic = "w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-base focus:outline-none focus:ring-2 focus:ring-emerald-500/40";

  return (
    <div data-testid="mobile-tour-panel-stops">
      {stops.length > 0 && (
        <>
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-1.5">Stop ({stops.filter(x => x.done_at).length}/{stops.length} udført)</div>
          <div className="space-y-2">
            {stops.map((st, i) => {
              const failed = !!st.issue?.code;
              return (
                <div key={st.id || i} className={`rounded-xl border px-3 py-2.5 ${failed ? "border-rose-200 bg-rose-50" : st.done_at ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}>
                  <div className="flex items-center gap-2">
                    <button type="button" disabled={!canTick} onClick={() => tick(st)} data-testid={`stop-toggle-${i}`}
                      aria-label={st.done_at ? "Fortryd stop" : "Marker stop som udført"}
                      className={`w-9 h-9 shrink-0 rounded-full border-2 flex items-center justify-center ${failed ? "bg-rose-500 border-rose-500 text-white" : st.done_at ? "bg-emerald-500 border-emerald-500 text-white" : "border-slate-300 text-slate-400"} disabled:opacity-40`}>
                      {failed ? <X className="w-5 h-5" /> : st.done_at ? <Check className="w-5 h-5" /> : <span className="text-xs font-bold">{i + 1}</span>}
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-semibold text-slate-500">
                        {st.kind === "delivery" ? "Aflevering" : "Afhentning"}
                        {st.done_at ? ` · ${failed ? "ikke gennemført" : "udført"} ${fmtClock(st.done_at)}` : ""}
                        {st.queued ? " · venter på net" : ""}
                        {st.added_by_driver ? " · tilføjet af dig" : ""}
                      </div>
                      <div className="text-sm font-semibold text-slate-800 break-words">{st.address}</div>
                      {st.note && <div className="text-xs text-amber-800 mt-0.5">{st.note}</div>}
                      {st.contact_name && <div className="text-xs text-slate-500">{st.contact_name}</div>}
                      {failed && <div className="text-xs font-semibold text-rose-700">{st.issue.code}{st.issue.text ? ` - ${st.issue.text}` : ""}</div>}
                      {st.receiver_name && !failed && <div className="text-xs text-emerald-700">Modtaget af {st.receiver_name}</div>}
                    </div>
                    {st.contact_phone && (
                      <a href={`tel:${st.contact_phone.replace(/\s/g, "")}`} className="w-9 h-9 shrink-0 rounded-lg border border-slate-200 flex items-center justify-center text-emerald-700" aria-label={`Ring til ${st.contact_name || "kontakt"}`}><Phone className="w-4 h-4" /></a>
                    )}
                    <a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(st.address)}&travelmode=driving`} target="_blank" rel="noopener noreferrer"
                      className="w-9 h-9 shrink-0 rounded-lg border border-slate-200 flex items-center justify-center text-slate-600" aria-label="Navigér"><Navigation className="w-4 h-4" /></a>
                  </div>
                  {canTick && !st.done_at && (
                    <div className="mt-2 flex items-center gap-2 pl-11">
                      {st.kind === "delivery" && (
                        <input className={`${ic} py-1.5 text-sm`} value={receiver[st.id] || ""} onChange={(e) => setReceiver(r => ({ ...r, [st.id]: e.target.value }))}
                          placeholder="Modtager (valgfri)" data-testid={`stop-receiver-${i}`} />
                      )}
                      <button type="button" onClick={() => { setIssueFor(issueFor === st.id ? null : st.id); setIssueText(""); }} data-testid={`stop-issue-${i}`}
                        className="shrink-0 px-2.5 py-1.5 rounded-lg border border-rose-200 text-rose-700 text-xs font-semibold inline-flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Kunne ikke</button>
                    </div>
                  )}
                  {issueFor === st.id && (
                    <div className="mt-2 pl-11 space-y-2" data-testid={`stop-issue-form-${i}`}>
                      <input className={`${ic} py-1.5 text-sm`} value={issueText} onChange={(e) => setIssueText(e.target.value)} placeholder="Kort forklaring (valgfri)" />
                      <div className="flex flex-wrap gap-1.5">
                        {codes.map(c => <button key={c} type="button" onClick={() => reportIssue(st, c)} className="px-2.5 py-1.5 rounded-full bg-rose-600 text-white text-xs font-semibold">{c}</button>)}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
      {canAdd && canTick && !tour.completed && tour.source !== "customer_order" && (
        adding ? (
          <div className="mt-2 rounded-xl border border-slate-200 bg-white p-3 space-y-2" data-testid="stop-add-form">
            <div className="inline-flex p-0.5 rounded-lg bg-slate-100">
              {[["delivery", "Aflevering"], ["pickup", "Afhentning"]].map(([k, l]) => (
                <button key={k} type="button" onClick={() => setAdding({ ...adding, kind: k })} className={`px-3 py-1.5 rounded-md text-xs font-bold ${adding.kind === k ? "bg-white shadow-sm" : "text-slate-500"}`}>{l}</button>
              ))}
            </div>
            <input className={ic} value={adding.street} onChange={(e) => setAdding({ ...adding, street: e.target.value })} placeholder="Vej og nr." data-testid="stop-add-street" />
            <div className="grid grid-cols-[96px_1fr] gap-2">
              <input className={ic} inputMode="numeric" value={adding.postal} onChange={(e) => setAdding({ ...adding, postal: e.target.value.replace(/\D/g, "").slice(0, 4) })} placeholder="Postnr." />
              <input className={ic} value={adding.city} onChange={(e) => setAdding({ ...adding, city: e.target.value })} placeholder="By" />
            </div>
            <input className={ic} value={adding.note} onChange={(e) => setAdding({ ...adding, note: e.target.value })} placeholder="Hvorfor? (fx kunden bad om det)" />
            <div className="flex gap-2">
              <button type="button" className="flex-1 py-2 rounded-lg bg-slate-100 text-sm font-semibold" onClick={() => setAdding(null)}>Annuller</button>
              <button type="button" disabled={busy} className="flex-1 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold inline-flex items-center justify-center gap-1" onClick={addStop} data-testid="stop-add-save">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Tilføj stop</button>
            </div>
          </div>
        ) : (
          <button type="button" className="mt-2 text-sm font-semibold text-emerald-700 inline-flex items-center gap-1" data-testid="stop-add"
            onClick={() => setAdding({ kind: "delivery", street: "", postal: "", city: "", note: "" })}><Plus className="w-4 h-4" /> Tilføj et stop</button>
        )
      )}
      {stops.length > 0 && !tour.on_way && !tour.completed && <p className="text-[11px] text-slate-400 mt-1.5">Start turen for at krydse stop af.</p>}
    </div>
  );
}
