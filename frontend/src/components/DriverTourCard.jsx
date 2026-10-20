import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../auth/api";
import { createPortal } from "react-dom";
import {
  Navigation, MessageSquare, Clock, Flag, Play, CheckCircle2, ChevronRight, X, AlertTriangle, Phone, Truck,
} from "lucide-react";
import TourChat from "./TourChat";
import { TOUR_TYPE_LABEL, isHaster, openHours, capacityText, daysLate, routeOf, navUrl } from "../lib/tourHelpers";

/**
 * Tur-række til chaufføren (2026-10-20: kompakt liste i stedet for store kort).
 * Linje 1: hvornår (haster, tidsrum, på vej) + kørsel (bil/hænger).
 * Linje 2: hvad (indhold, opgave, container).
 * Adresser: hent og/eller aflever på hver sin linje med en lille "Kør"-knap.
 * Én knap til højre: Start / Afslut / Tag turen (+ start med det samme).
 * Kunde, kundens note, telefon og beskeder står inde i turen (tryk på rækken).
 */
export default function DriverTourCard({ tour, routeInfo, unread = 0, mode = "mine", run = null, sameRoute = false,
  onStart, onTake, onTakeStart, onFinish, onOpen, onChat }) {
  const haster = isHaster(tour);
  const oh = openHours(tour);
  const late = daysLate(tour);
  const done = !!tour.completed;
  const cancelled = !!tour.cancelled && !done;
  const onWay = !!tour.on_way && !done && !cancelled;
  const goods = tour.tour_kind === "goods";
  const stops = Array.isArray(tour.stops) ? tour.stops : [];
  const nextStop = onWay ? stops.find(x => !x.done_at) : null;
  const lines = Array.isArray(tour.cargo_lines) ? tour.cargo_lines.filter(l => (l.text || "").trim()) : [];
  const what = lines.length > 1 ? lines.map(l => l.text).join(" + ")
    : lines.length === 1 ? `${lines[0].text}${lines[0].qty ? ` · ${lines[0].qty} ${lines[0].unit || ""}` : ""}` : (tour.fraction || "—");
  const typeLabel = tour.tour_type !== "normal" ? (TOUR_TYPE_LABEL[tour.tour_type] || "") : "";
  const cap = tour.tour_type === "loes_afhentning"
    ? (tour.loose_estimated_count ? `${tour.loose_estimated_count} containere` : "")
    : capacityText(tour);
  const facts = [typeLabel, cap, tour.container && tour.tour_type !== "loes_afhentning" ? `#${tour.container}` : "",
    Number(tour.trailer_count) > 0 ? `${tour.trailer_count} hænger${Number(tour.trailer_count) === 1 ? "" : "e"}` : "",
    routeInfo?.distance_km > 0 ? `${routeInfo.distance_km} km` : ""].filter(Boolean);
  // Adresser: på en tur med stop vises næste stop (eller første + antal);
  // ellers hent og aflever. En færdig tur viser kun hvor den endte.
  const legs = stops.length
    ? [nextStop
      ? { label: `Stop ${stops.indexOf(nextStop) + 1}/${stops.length}`, name: nextStop.contact_name || "", address: nextStop.address }
      : { label: `${stops.length} stop`, name: "", address: stops[0]?.address }]
    : routeOf(tour);
  const shownLegs = sameRoute ? [] : (done || cancelled ? legs.slice(-1) : legs.slice(0, 2)).filter(l => (l.address || "").trim());
  const accent = cancelled ? "border-l-slate-300" : done ? "border-l-emerald-500" : onWay ? "border-l-amber-400" : haster ? "border-l-rose-500" : "border-l-transparent";
  const chip = "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[11px] font-bold";
  const btn = "min-h-[44px] px-3.5 rounded-xl text-white font-extrabold text-[14px] inline-flex items-center justify-center gap-1.5";

  return (
    <div className={`border-l-4 ${accent} ${done || cancelled ? "bg-slate-50/60" : "bg-white"}`} data-testid={`mobile-tour-${tour.id}`}>
      <div className="flex items-center gap-2 pl-3 pr-2.5 pt-2.5 pb-1.5">
        <button type="button" onClick={() => onOpen(tour)} className="min-w-0 flex-1 text-left" data-testid={`tour-open-${tour.id}`}>
          <div className="flex items-center gap-1 flex-wrap min-h-[20px]">
            {routeInfo?.route_order && !done && <span className="w-5 h-5 rounded-full bg-slate-900 text-white text-[10px] font-bold flex items-center justify-center">{routeInfo.route_order}</span>}
            {haster && !done && !cancelled && <span className={`${chip} bg-rose-600 text-white uppercase ${!onWay ? "animate-haster-pulse" : ""}`} data-testid={`tour-priority-${tour.id}`}><Flag className="w-3 h-3" /> Haster</span>}
            {oh.from && !done && <span className={`${chip} bg-slate-100 text-slate-700`}><Clock className="w-3 h-3" />{oh.from}–{oh.to}</span>}
            {onWay && tour.on_way_time && <span className={`${chip} bg-amber-100 text-amber-800`}>På vej {tour.on_way_time}</span>}
            {run && run.role !== "solo" && (onWay || done) && (
              <span className={`${chip} ${run.role === "truck" ? "bg-slate-900 text-white" : "bg-violet-600 text-white"}`} data-testid={`tour-run-role-${tour.id}`}>
                <Truck className="w-3 h-3" /> {run.role === "truck" ? "Bil" : "Hænger"}
              </span>
            )}
            {late > 0 && !done && !cancelled && <span className={`${chip} bg-amber-100 text-amber-800`} data-testid={`tour-delay-${tour.id}`}><AlertTriangle className="w-3 h-3" />{late} {late === 1 ? "dag" : "dage"} for sent</span>}
            {done && <span className={`${chip} bg-emerald-50 text-emerald-700`}><CheckCircle2 className="w-3 h-3" />{tour.time ? `Færdig ${tour.time}` : "Færdig"}{tour.weight ? ` · ${Number(tour.weight).toLocaleString("da-DK")} kg` : ""}</span>}
            {cancelled && <span className={`${chip} bg-slate-200 text-slate-700`} data-testid={`tour-cancelled-${tour.id}`}>{tour.cancelled_on_way ? "Annulleret undervejs" : "Annulleret"}</span>}
            {tour.queued && <span className={`${chip} bg-slate-200 text-slate-600`} data-testid={`tour-queued-${tour.id}`}>Venter på net</span>}
            {tour.tour_number && <span className="ml-auto pl-1 text-[10px] font-mono text-slate-400">{tour.tour_number}</span>}
          </div>
          <div className="mt-0.5 text-[15px] font-bold text-slate-900 leading-snug line-clamp-2 break-words">
            {what}
            {facts.length > 0 && <span className="text-[12px] font-semibold text-slate-500"> · {facts.join(" · ")}</span>}
            {goods && !typeLabel && <span className="text-[12px] font-semibold text-sky-700"> · Fragt</span>}
          </div>
        </button>
        {unread > 0 && (
          <button type="button" onClick={() => onChat(tour)} aria-label={`${unread} nye beskeder`} data-testid={`tour-chat-btn-${tour.id}`}
            className="relative min-h-[44px] min-w-[40px] rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-800 inline-flex items-center justify-center">
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
                className="min-h-[44px] px-3 bg-orange-500 active:bg-orange-600 text-white font-extrabold text-[14px]">Tag turen</button>
              <button type="button" onClick={() => onTakeStart(tour)} data-testid={`tour-takestart-btn-${tour.id}`} aria-label="Tag turen og start den nu" title="Tag turen og start den nu"
                className="min-h-[44px] w-11 bg-orange-600 active:bg-orange-700 text-white inline-flex items-center justify-center border-l border-orange-400">
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
      {sameRoute && <p className="pl-3 pb-2 -mt-0.5 text-[12px] text-slate-500" data-testid={`tour-same-route-${tour.id}`}>Samme hent og aflever som ovenfor</p>}
      {shownLegs.length > 0 && (
        <div className="pl-3 pr-2.5 pb-2 space-y-1" data-testid={`tour-route-${tour.id}`}>
          {shownLegs.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <button type="button" onClick={() => onOpen(tour)} className="min-w-0 flex-1 text-left flex items-baseline gap-2">
                <span className="w-[50px] shrink-0 text-[10px] font-bold uppercase tracking-wide text-slate-400">{l.label}</span>
                <span className={`line-clamp-2 break-words text-[13px] leading-snug ${i === 0 && !done ? "font-semibold text-slate-800" : "text-slate-600"}`}>{l.name ? `${l.name} · ` : ""}{l.address}</span>
              </button>
              {!done && !cancelled && (
                <a href={navUrl(l.address)} target="_blank" rel="noreferrer" data-testid={`tour-nav-${tour.id}-${i}`} aria-label={`Kør til ${l.name || l.address}`}
                  className="shrink-0 h-8 px-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-[11px] font-bold inline-flex items-center gap-1 active:bg-slate-50">
                  <Navigation className="w-3.5 h-3.5" /> Kør
                </a>
              )}
            </div>
          ))}
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
