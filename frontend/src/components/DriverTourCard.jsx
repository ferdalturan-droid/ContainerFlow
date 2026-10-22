import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../auth/api";
import { createPortal } from "react-dom";
import {
  Navigation, MessageSquare, Flag, Play, CheckCircle2, ChevronRight, X, Phone, Truck,
} from "lucide-react";
import TourChat from "./TourChat";
import { TOUR_TYPE_LABEL, isHaster, openHours, capacityShort, containerNo, daysLate, routeOf, navUrl } from "../lib/tourHelpers";

/**
 * Tur-række til chaufføren (2026-10-20, runde 2: endnu mere kompakt).
 * Hver tur er en lille boks med luft til den næste, så man kan se hvor en tur
 * slutter. Linje 1: Bil/Hænger, haster og indholdet. Linje 2 (grå): tidsrum,
 * på vej, container, størrelse, km. Derunder hent/aflever med en lille "Kør"
 * - men kun de adresser der ikke allerede står i gruppens overskrift
 * (pladsen) eller i hængerkørslens overskrift. Ture med flere end 2 stop
 * viser kun næste stop; hele listen står inde i turen.
 */
export const legsOf = (tour) => {
  const stops = Array.isArray(tour.stops) ? tour.stops : [];
  if (!stops.length) return routeOf(tour).filter(l => (l.address || "").trim());
  const onWay = !!tour.on_way && !tour.completed;
  const next = onWay ? stops.find(x => !x.done_at) : null;
  const s = next || stops[0];
  return s?.address ? [{ label: next ? `Stop ${stops.indexOf(next) + 1}/${stops.length}` : `${stops.length} stop`, name: s.contact_name || "", address: s.address }] : [];
};

export function LegLine({ leg, testid }) {
  return (
    <div className="flex items-center gap-2 min-h-[30px]">
      <span className="w-[46px] shrink-0 text-[10px] font-bold uppercase tracking-wide text-slate-400">{leg.label}</span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-slate-700">{leg.name ? <b className="font-semibold">{leg.name} · </b> : null}{leg.address}</span>
      <a href={navUrl(leg.address)} target="_blank" rel="noreferrer" data-testid={testid} aria-label={`Kør til ${leg.name || leg.address}`}
        className="shrink-0 h-7 px-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-[11px] font-bold inline-flex items-center gap-1 active:bg-slate-50">
        <Navigation className="w-3.5 h-3.5" /> Kør
      </a>
    </div>
  );
}

export default function DriverTourCard({ tour, routeInfo, unread = 0, mode = "mine", run = null, hideAddrs = [], hideLegs = false,
  onStart, onTake, onTakeStart, onFinish, onOpen, onChat }) {
  const haster = isHaster(tour);
  const oh = openHours(tour);
  const late = daysLate(tour);
  const done = !!tour.completed;
  const cancelled = !!tour.cancelled && !done;
  const onWay = !!tour.on_way && !done && !cancelled;
  const goods = tour.tour_kind === "goods";
  const lines = Array.isArray(tour.cargo_lines) ? tour.cargo_lines.filter(l => (l.text || "").trim()) : [];
  const what = lines.length > 1 ? lines.map(l => l.text).join(" + ")
    : lines.length === 1 ? `${lines[0].text}${lines[0].qty ? ` · ${lines[0].qty} ${lines[0].unit || ""}` : ""}` : (tour.fraction || "—");
  const typeLabel = tour.tour_type !== "normal" ? (TOUR_TYPE_LABEL[tour.tour_type] || "") : "";
  // 2026-10-22: Containertype kort ("Lukket 30 m³") forrest i den grå linje,
  // containernummeret i titlen ("Restaffald (9999)").
  const cap = tour.tour_type === "loes_afhentning"
    ? (tour.loose_estimated_count ? `${tour.loose_estimated_count} containere` : "")
    : capacityShort(tour);
  const cno = containerNo(tour);
  const meta = done
    ? [tour.time ? `Færdig ${tour.time}` : "Færdig", tour.weight ? `${Number(tour.weight).toLocaleString("da-DK")} kg` : ""]
    : cancelled ? [tour.cancelled_on_way ? "Annulleret undervejs" : "Annulleret", tour.cancel_reason || ""]
      : [oh.from ? `${oh.from}–${oh.to}` : "", onWay && tour.on_way_time ? `På vej ${tour.on_way_time}` : "",
        late > 0 ? `${late} ${late === 1 ? "dag" : "dage"} for sent` : ""];
  const facts = [...(done || cancelled ? [...meta, cap] : [cap, ...meta]), typeLabel,
    Number(tour.trailer_count) > 0 ? `${tour.trailer_count} hænger${Number(tour.trailer_count) === 1 ? "" : "e"}` : "",
    goods && !typeLabel ? "Fragt" : "", routeInfo?.distance_km > 0 && !done ? `${routeInfo.distance_km} km` : ""].filter(Boolean);
  const legs = done || cancelled || hideLegs ? [] : legsOf(tour).filter(l => !hideAddrs.includes(l.address)).slice(0, 2);
  const chip = "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-extrabold uppercase tracking-wide shrink-0";
  const btn = "min-h-[40px] px-3 rounded-xl text-white font-extrabold text-[14px] inline-flex items-center justify-center gap-1.5 shrink-0";
  const border = cancelled ? "border-slate-200" : done ? "border-emerald-200" : onWay ? "border-amber-300" : haster ? "border-rose-300" : "border-slate-200";

  return (
    <div className={`rounded-xl border ${border} ${done || cancelled ? "bg-slate-50" : "bg-white"} shadow-[0_1px_1px_rgba(15,23,42,0.04)]`} data-testid={`mobile-tour-${tour.id}`}>
      <div className="flex items-center gap-2 px-2.5 py-2">
        <button type="button" onClick={() => onOpen(tour)} className="min-w-0 flex-1 text-left" data-testid={`tour-open-${tour.id}`}>
          <div className="flex items-center gap-1 min-w-0">
            {routeInfo?.route_order && !done && <span className="w-5 h-5 shrink-0 rounded-full bg-slate-900 text-white text-[10px] font-bold flex items-center justify-center">{routeInfo.route_order}</span>}
            {run && run.role !== "solo" && (onWay || done) && (
              <span className={`${chip} ${run.role === "truck" ? "bg-slate-900 text-white" : "bg-violet-600 text-white"}`} data-testid={`tour-run-role-${tour.id}`}>
                <Truck className="w-3 h-3" />{run.role === "truck" ? "Bil" : "Hænger"}
              </span>
            )}
            {haster && !done && !cancelled && <span className={`${chip} bg-rose-600 text-white ${!onWay ? "animate-haster-pulse" : ""}`} data-testid={`tour-priority-${tour.id}`}><Flag className="w-3 h-3" />Haster</span>}
            {tour.queued && <span className={`${chip} bg-slate-200 text-slate-600`} data-testid={`tour-queued-${tour.id}`}>Venter på net</span>}
            <span className="min-w-0 truncate text-[15px] font-bold text-slate-900">{what}{cno ? <span className="font-semibold text-slate-600"> ({cno})</span> : null}</span>
            {done && <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />}
          </div>
          <div className={`mt-0.5 text-[12px] truncate ${onWay ? "text-amber-800" : late > 0 && !done ? "text-amber-700" : "text-slate-500"}`}>
            {facts.join(" · ")}{tour.tour_number ? <span className="text-slate-400 font-mono"> · {tour.tour_number}</span> : null}
          </div>
        </button>
        {unread > 0 && (
          <button type="button" onClick={() => onChat(tour)} aria-label={`${unread} nye beskeder`} data-testid={`tour-chat-btn-${tour.id}`}
            className="relative min-h-[40px] min-w-[38px] rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-800 inline-flex items-center justify-center shrink-0">
            <MessageSquare className="w-4 h-4" />
            <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center">{unread}</span>
          </button>
        )}
        {!done && !cancelled && (
          onWay ? (
            <button type="button" onClick={() => onFinish(tour)} data-testid={`tour-action-btn-${tour.id}`} className={`${btn} bg-emerald-600 active:bg-emerald-700`}>
              <CheckCircle2 className="w-4 h-4" /> Afslut
            </button>
          ) : mode === "free" ? (
            <div className="inline-flex rounded-xl overflow-hidden shrink-0">
              <button type="button" onClick={() => onTake(tour)} data-testid={`tour-take-btn-${tour.id}`}
                className="min-h-[40px] px-3 bg-orange-500 active:bg-orange-600 text-white font-extrabold text-[14px]">Tag turen</button>
              <button type="button" onClick={() => onTakeStart(tour)} data-testid={`tour-takestart-btn-${tour.id}`} aria-label="Tag turen og start den nu" title="Tag turen og start den nu"
                className="min-h-[40px] w-10 bg-orange-600 active:bg-orange-700 text-white inline-flex items-center justify-center border-l border-orange-400">
                <Play className="w-4 h-4 fill-current" />
              </button>
            </div>
          ) : (
            <button type="button" onClick={() => onStart(tour)} data-testid={`tour-action-btn-${tour.id}`}
              className={`${btn} ${haster ? "bg-rose-600 active:bg-rose-700" : "bg-orange-500 active:bg-orange-600"}`}>
              <Play className="w-3.5 h-3.5 fill-current" /> Start
            </button>
          )
        )}
        {(done || cancelled) && <ChevronRight className="w-5 h-5 text-slate-300 shrink-0" />}
      </div>
      {legs.length > 0 && (
        <div className="px-2.5 pb-1.5 -mt-1" data-testid={`tour-route-${tour.id}`}>
          {legs.map((l, i) => <LegLine key={i} leg={l} testid={`tour-nav-${tour.id}-${i}`} />)}
        </div>
      )}
    </div>
  );
}

/**
 * "Ring til planlæggeren" (2026-10-17). Research: chauffører ringer stadig
 * oftest til disponenten - et opkald med ét tryk skal ligge lige ved siden af
 * beskederne. Ringer til den der tildelte turen (hvis telefonnummer), ellers
 * firmaets disponent-telefon (Team & rettigheder). Skjules hvis intet nummer.
 */
export function CallPlannerButton({ tourId, className = "" }) {
  const [c, setC] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/driver/dispatch-contact`, { params: { tour_id: tourId || "" } })
      .then(r => alive && setC(r.data)).catch(() => alive && setC({}));
    return () => { alive = false; };
  }, [tourId]);
  if (!c?.phone) return null;
  return (
    <a href={`tel:${c.phone.replace(/[^\d+]/g, "")}`} data-testid="call-planner"
      className={`min-h-[46px] rounded-xl bg-slate-900 active:bg-slate-700 text-white font-semibold text-sm inline-flex items-center justify-center gap-2 px-4 ${className}`}>
      <Phone className="w-4 h-4" /> Ring til {c.name || "planlæggeren"}
    </a>
  );
}

/** Bundark med beskedtråden for én tur (chauffør-siden). */
export function DriverChatSheet({ tour, onClose, onChanged }) {
  useEffect(() => {
    if (!tour) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [tour]);
  if (!tour) return null;
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center" data-testid="driver-chat-sheet">
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div className="relative w-full sm:max-w-lg bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[88vh]"
        style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom))" }}>
        <div className="mx-auto mt-2 w-10 h-1.5 rounded-full bg-slate-200 sm:hidden" />
        <div className="px-4 pt-3 pb-2 flex items-start gap-3 border-b border-slate-100">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">Besked til planlægger</div>
            <div className="font-bold text-slate-900 truncate">{tour.fraction || "Tur"} · {tour.address || tour.facility || ""}</div>
          </div>
          <button onClick={onClose} className="p-2 -mr-1 rounded-lg text-slate-500 active:bg-slate-100" aria-label="Luk"><X className="w-5 h-5" /></button>
        </div>
        <div className="px-4 pt-3 space-y-3">
          <CallPlannerButton tourId={tour.id} className="w-full" />
          <TourChat tourId={tour.id} side="driver" onChanged={onChanged} maxHeight={"40vh"} />
        </div>
      </div>
    </div>,
    document.body
  );
}
