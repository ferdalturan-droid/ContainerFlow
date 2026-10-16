import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Navigation, MessageSquare, Clock, Package2, Flag, Play, CheckCircle2, ChevronRight, X, UserCheck, Building2, AlertTriangle,
} from "lucide-react";
import TourChat from "./TourChat";
import { TOUR_TYPE_LABEL, isHaster, openHours, capacityText, daysLate, mapsUrl } from "../lib/tourHelpers";

/**
 * Lyst tur-kort til chaufførens TURE-fane (2026-10-16). Erstatter det mørke
 * MobileTourCard i listen.
 *  - Én tydelig hovedhandling pr. tilstand: "Start tur" → "Afslut tur".
 *    Afslut åbner tur-panelet når der skal vejes (normal / løs afhentning),
 *    så knappen aldrig "fejler" med en toast om manglende vægt.
 *  - Sekundært: Kort og Besked (med ulæst-tæller).
 *  - Store tryk-flader (min. 44 px) og ingen hover-afhængigheder.
 */
export default function DriverTourCard({ tour, index, routeInfo, unread = 0, onStart, onFinish, onOpen, onChat }) {
  const haster = isHaster(tour);
  const oh = openHours(tour);
  const late = daysLate(tour);
  const cap = tour.tour_type === "loes_afhentning"
    ? (tour.loose_estimated_count ? `${tour.loose_estimated_count} containere` : "")
    : capacityText(tour);
  const done = !!tour.completed;
  const onWay = !!tour.on_way && !done;
  const accent = done ? "#10b981" : onWay ? "#f59e0b" : haster ? "#e11d48" : "#cbd5e1";
  const typeLabel = tour.tour_type && tour.tour_type !== "normal" ? (TOUR_TYPE_LABEL[tour.tour_type] || tour.tour_type) : "";

  return (
    <article
      className={`relative bg-white rounded-2xl border border-slate-200 shadow-[0_1px_2px_rgba(15,23,42,0.04)] overflow-hidden ${done ? "opacity-70" : ""}`}
      style={{ borderLeft: `4px solid ${accent}` }}
      data-testid={`mobile-tour-${tour.id}`}
    >
      <button type="button" onClick={() => onOpen(tour)} className="w-full text-left px-3.5 pt-3 pb-2.5 flex gap-3 active:bg-slate-50">
        <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-extrabold ${
          done ? "bg-emerald-100 text-emerald-700" : onWay ? "bg-amber-100 text-amber-800" : haster ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>
          {routeInfo?.route_order || index + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 flex-wrap">
            {haster && !done && (
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-rose-600 text-white text-[10px] font-extrabold uppercase tracking-wide ${!onWay ? "animate-haster-pulse" : ""}`} data-testid={`tour-priority-${tour.id}`}>
                <Flag className="w-2.5 h-2.5" /> Haster
              </span>
            )}
            <span className="font-bold text-[15px] leading-tight text-slate-900">{tour.fraction || "Ingen fraktion"}</span>
            {typeLabel && <span className="text-[11px] font-semibold text-violet-700 bg-violet-50 px-1.5 py-0.5 rounded-md">{typeLabel}</span>}
          </span>
          <span className="block text-[13px] text-slate-600 mt-0.5 truncate">{tour.address || tour.facility || "Ingen adresse"}</span>
          <span className="flex items-center gap-x-3 gap-y-1 flex-wrap mt-1.5 text-[11px] text-slate-500">
            {oh.from && <span className="inline-flex items-center gap-1 font-semibold text-slate-700"><Clock className="w-3 h-3" />{oh.from}–{oh.to}</span>}
            {cap && <span className="inline-flex items-center gap-1"><Package2 className="w-3 h-3" />{cap}</span>}
            {tour.container && tour.tour_type !== "loes_afhentning" && <span>#{tour.container}</span>}
            {routeInfo?.distance_km > 0 && <span>{routeInfo.distance_km} km</span>}
            {routeInfo?.job_type === "HAENGER" && <span className="font-semibold text-blue-700">Hænger</span>}
            {tour.customer_name && <span className="inline-flex items-center gap-1 max-w-[160px] truncate"><Building2 className="w-3 h-3 shrink-0" />{tour.customer_name}</span>}
            {tour.tour_number && <span className="font-mono text-slate-400">{tour.tour_number}</span>}
          </span>
          {(tour.driver_id && !done) || late > 0 ? (
            <span className="flex items-center gap-1.5 flex-wrap mt-1.5">
              {tour.driver_id && !done && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[10px] font-bold" data-testid={`preassigned-badge-${tour.id}`}>
                  <UserCheck className="w-3 h-3" /> Tildelt dig{tour.assigned_by_name ? ` af ${tour.assigned_by_name}` : ""}
                </span>
              )}
              {late > 0 && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-800 text-[10px] font-bold" data-testid={`tour-delay-${tour.id}`}>
                  <AlertTriangle className="w-3 h-3" /> {late} {late === 1 ? "dag" : "dage"} forsinket
                </span>
              )}
            </span>
          ) : null}
          {oh.note && !done && (
            <span className="block mt-1.5 text-[12px] leading-snug text-amber-900 bg-amber-50 rounded-lg px-2 py-1.5 line-clamp-2">{oh.note}</span>
          )}
          {done && (
            <span className="block mt-1.5 text-[12px] font-semibold text-emerald-700">
              Færdig{tour.time ? ` kl. ${tour.time}` : ""}{tour.weight && (tour.tour_type || "normal") !== "flyt" ? ` · ${tour.weight} kg` : ""}
            </span>
          )}
          {onWay && tour.on_way_time && <span className="block mt-1.5 text-[12px] font-semibold text-amber-700">På vej siden {tour.on_way_time}</span>}
        </span>
        <ChevronRight className="w-4 h-4 text-slate-300 shrink-0 self-center" />
      </button>

      <div className="flex items-stretch gap-2 px-3.5 pb-3">
        {!done && (
          onWay ? (
            <button type="button" onClick={() => onFinish(tour)} data-testid={`tour-action-btn-${tour.id}`}
              className="flex-1 min-h-[46px] rounded-xl bg-emerald-600 active:bg-emerald-700 text-white font-bold text-[14px] inline-flex items-center justify-center gap-2">
              <CheckCircle2 className="w-4 h-4" /> Afslut tur
            </button>
          ) : (
            <button type="button" onClick={() => onStart(tour)} data-testid={`tour-action-btn-${tour.id}`}
              className={`flex-1 min-h-[46px] rounded-xl text-white font-bold text-[14px] inline-flex items-center justify-center gap-2 ${haster ? "bg-rose-600 active:bg-rose-700" : "bg-orange-500 active:bg-orange-600"}`}>
              <Play className="w-4 h-4 fill-current" /> Start tur
            </button>
          )
        )}
        {!done && (tour.address || tour.facility) && (
          <a href={mapsUrl(tour.address || tour.facility)} target="_blank" rel="noreferrer" data-testid={`maps-btn-${tour.id}`}
            className="min-h-[46px] min-w-[46px] px-3 rounded-xl border border-slate-200 text-slate-700 font-semibold text-[13px] inline-flex items-center justify-center gap-1.5 active:bg-slate-50">
            <Navigation className="w-4 h-4" /><span className="hidden min-[380px]:inline">Kort</span>
          </a>
        )}
        <button type="button" onClick={() => onChat(tour)} data-testid={`tour-chat-btn-${tour.id}`}
          className={`relative min-h-[46px] min-w-[46px] px-3 rounded-xl border font-semibold text-[13px] inline-flex items-center justify-center gap-1.5 ${done ? "flex-1" : ""} ${
            unread ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-slate-200 text-slate-700 active:bg-slate-50"}`}
          aria-label="Beskeder">
          <MessageSquare className="w-4 h-4" /><span className={done ? "" : "hidden min-[380px]:inline"}>Besked</span>
          {unread > 0 && <span className="absolute -top-1.5 -right-1.5 min-w-[20px] h-5 px-1 rounded-full bg-rose-600 text-white text-[11px] font-bold flex items-center justify-center">{unread}</span>}
        </button>
      </div>
    </article>
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
        <div className="px-4 pt-3">
          <TourChat tourId={tour.id} side="driver" onChanged={onChanged} maxHeight={"45vh"} />
        </div>
      </div>
    </div>,
    document.body
  );
}
