import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../auth/api";
import { createPortal } from "react-dom";
import {
  Navigation, MessageSquare, Clock, Package2, Flag, Play, CheckCircle2, ChevronRight, X, UserCheck, Building2, AlertTriangle, Phone,
} from "lucide-react";
import TourChat from "./TourChat";
import { TOUR_TYPE_LABEL, isHaster, openHours, capacityText, daysLate, routeOf, navUrl } from "../lib/tourHelpers";

/**
 * Tur-kort til chaufføren (2026-10-17, nyt design).
 * Rækkefølge efter hvad chaufføren skal bruge først: HVORNÅR (tidsrum,
 * haster) -> HVOR (adresse stort) -> HVAD (materiale/indhold, container)
 * -> EN tydelig hovedknap. Store trykflader (min. 48 px), ingen hover.
 */
/**
 * 2026-10-19: Kort-knappen. Har turen to steder (fx hent på pladsen og aflever
 * på HCS, eller værkstedet og pladsen), vælger chaufføren her i køreorden -
 * så knappen aldrig sender ham til det forkerte sted. Ét sted (Byt container)
 * eller næste stop på en stop-tur åbner Google Maps direkte.
 */
export function NavChooser({ legs, onClose }) {
  if (!legs) return null;
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center" data-testid="nav-chooser">
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white rounded-t-2xl shadow-2xl p-4 space-y-2" style={{ paddingBottom: "max(16px, env(safe-area-inset-bottom))" }}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">Hvor skal du hen?</h3>
          <button type="button" onClick={onClose} className="p-2 -mr-2 rounded-lg text-slate-500" aria-label="Luk"><X className="w-5 h-5" /></button>
        </div>
        {legs.map((l, i) => (
          <a key={i} href={navUrl(l.address)} target="_blank" rel="noreferrer" onClick={onClose} data-testid={`nav-leg-${i}`}
            className="flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-3 active:bg-slate-50 min-h-[60px]">
            <span className="w-8 h-8 shrink-0 rounded-full bg-slate-900 text-white text-sm font-bold flex items-center justify-center">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] font-bold uppercase tracking-wide text-slate-500">{l.label}{l.name ? ` · ${l.name}` : ""}</span>
              <span className="block text-[15px] font-bold text-slate-900 break-words">{l.address}</span>
            </span>
            <Navigation className="w-5 h-5 text-slate-500 shrink-0" />
          </a>
        ))}
      </div>
    </div>,
    document.body
  );
}

export default function DriverTourCard({ tour, index, routeInfo, unread = 0, mine = true, onStart, onFinish, onOpen, onChat }) {
  const haster = isHaster(tour);
  const oh = openHours(tour);
  const [navLegs, setNavLegs] = useState(null);
  const late = daysLate(tour);
  const done = !!tour.completed;
  const onWay = !!tour.on_way && !done;
  const goods = tour.tour_kind === "goods";
  const ap = tour.address_parts || {};
  const street = ap.street || (tour.address || "").split(",")[0] || tour.facility || "Ingen adresse";
  const town = ap.street ? [ap.postal, ap.city].filter(Boolean).join(" ") : (tour.address || "").split(",").slice(1).join(",").trim();
  // Ingen "A → A" når afleveringen er samme adresse som afhentningen.
  const delivery = tour.facility && tour.facility !== tour.plads && tour.facility !== tour.address ? tour.facility : "";
  const stops = Array.isArray(tour.stops) ? tour.stops : [];
  const stopsDoneN = stops.filter(x => x.done_at).length;
  // 2026-10-18 (P6): Når turen kører, er det næste åbne stop det chaufføren
  // skal bruge i førerhuset - adresse, note og telefon.
  const nextStop = onWay ? stops.find(x => !x.done_at) : null;
  // 2026-10-19: Værksted. Til værksted: pladsen -> værkstedet. Afhent fra
  // værksted: værkstedet -> pladsen. Kortets store adresse er første stop.
  const workshop = (tour.tour_type === "vaerksted" || tour.tour_type === "afhent_vaerksted") && tour.workshop_address
    ? { name: tour.workshop_name || "Værksted", phone: tour.workshop_phone || "", pickup: tour.tour_type === "afhent_vaerksted" } : null;
  // 2026-10-19: Kortet følger turens rute (se routeOf): næste stop på en
  // stop-tur, ellers ét sted direkte eller et valg mellem stederne.
  const legs = routeOf(tour);
  const navTarget = nextStop?.address || (legs.length === 1 ? legs[0].address : "") || (!legs.length ? (tour.address || tour.facility) : "");
  const cancelled = !!tour.cancelled && !tour.completed;
  const deliveryName = tour.order_id && tour.delivery_name && (tour.tour_type === "normal" || tour.tour_type === "loes_afhentning") ? tour.delivery_name : "";
  const cap = tour.tour_type === "loes_afhentning"
    ? (tour.loose_estimated_count ? `${tour.loose_estimated_count} containere` : "")
    : capacityText(tour);
  const lines = Array.isArray(tour.cargo_lines) ? tour.cargo_lines : [];
  const typeLabel = TOUR_TYPE_LABEL[tour.tour_type] || "";
  const accent = done ? "border-l-emerald-500" : onWay ? "border-l-amber-400" : haster ? "border-l-rose-500" : "border-l-slate-200";

  return (
    <article className={`bg-white rounded-2xl border border-slate-200 border-l-4 ${tour.cancelled && !done ? "border-l-slate-300" : accent} shadow-[0_1px_2px_rgba(15,23,42,0.05)] overflow-hidden ${done || (tour.cancelled && !done) ? "opacity-80" : ""}`}
      data-testid={`mobile-tour-${tour.id}`}>
      <button type="button" onClick={() => onOpen(tour)} className="w-full text-left px-4 pt-3.5 pb-3 active:bg-slate-50">
        <div className="flex items-center gap-1.5 flex-wrap min-h-[22px]">
          {routeInfo?.route_order && !done && <span className="w-6 h-6 rounded-full bg-slate-900 text-white text-[11px] font-bold flex items-center justify-center">{routeInfo.route_order}</span>}
          {haster && !done && (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-600 text-white text-[11px] font-extrabold uppercase tracking-wide ${!onWay ? "animate-haster-pulse" : ""}`} data-testid={`tour-priority-${tour.id}`}>
              <Flag className="w-3 h-3" /> Haster
            </span>
          )}
          {oh.from && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[12px] font-bold"><Clock className="w-3.5 h-3.5" />{oh.from}–{oh.to}</span>}
          {onWay && tour.on_way_time && <span className="px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 text-[12px] font-bold">På vej siden {tour.on_way_time}</span>}
          {late > 0 && !done && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 text-[11px] font-bold" data-testid={`tour-delay-${tour.id}`}>
              <AlertTriangle className="w-3 h-3" /> {late} {late === 1 ? "dag" : "dage"} for sent
            </span>
          )}
          {tour.driver_id && !done && !onWay && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[11px] font-bold" data-testid={`preassigned-badge-${tour.id}`}>
              <UserCheck className="w-3 h-3" /> Tildelt dig
            </span>
          )}
          {tour.queued && <span className="px-2 py-0.5 rounded-md bg-slate-200 text-slate-600 text-[11px] font-bold" data-testid={`tour-queued-${tour.id}`}>Venter på net</span>}
          {tour.tour_number && <span className="ml-auto text-[11px] font-mono text-slate-400">{tour.tour_number}</span>}
        </div>

        <div className="mt-2 flex items-start gap-2">
          <div className="min-w-0 flex-1">
            {workshop && <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{workshop.pickup ? `Hent på ${workshop.name}` : "Hent på pladsen"}</p>}
            {!workshop && deliveryName && <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500" data-testid={`tour-delivery-name-${tour.id}`}>Aflever · {deliveryName}</p>}
            <p className="text-[17px] leading-snug font-extrabold text-slate-900 break-words">{street}</p>
            {town && <p className="text-[13px] text-slate-500">{town}</p>}
            {stops.length > 0 ? (
              <p className="text-[13px] font-semibold text-slate-600 mt-1">{stops.length} stop{onWay || done ? ` · ${stopsDoneN} udført` : ""} · slut: {stops[stops.length - 1]?.address}</p>
            ) : delivery && <p className="text-[13px] text-slate-600 mt-1" data-testid={`tour-delivery-${tour.id}`}>→ {workshop ? (workshop.pickup ? "Pladsen: " : `${workshop.name}: `) : ""}{delivery}</p>}
          </div>
          <ChevronRight className="w-5 h-5 text-slate-300 shrink-0 mt-1" />
        </div>

        <div className="mt-2.5 flex items-center gap-x-3 gap-y-1 flex-wrap text-[13px]">
          {lines.length > 1 || (lines.length === 1 && Number(tour.trailer_count) > 0) ? (
            <span className="w-full space-y-0.5">
              {lines.map((l, i) => (
                <span key={i} className="flex items-center gap-2 font-semibold text-slate-800">
                  {l.trailer ? <span className="text-[11px] font-bold text-slate-500 bg-slate-100 rounded px-1.5">H{l.trailer}</span> : <Package2 className="w-3.5 h-3.5 text-slate-400" />}
                  {l.text}{l.qty ? <span className="text-slate-500 font-normal"> · {l.qty} {l.unit || ""}</span> : null}
                </span>
              ))}
            </span>
          ) : (
            <span className="font-semibold text-slate-800">{tour.fraction || "—"}</span>
          )}
          {typeLabel && tour.tour_type !== "normal" && <span className={`text-[12px] font-semibold px-1.5 py-0.5 rounded-md ${goods ? "bg-sky-50 text-sky-700" : "bg-violet-50 text-violet-700"}`}>{typeLabel}</span>}
          {cap && <span className="text-slate-500 inline-flex items-center gap-1"><Package2 className="w-3.5 h-3.5" />{cap}</span>}
          {tour.container && tour.tour_type !== "loes_afhentning" && <span className="text-slate-500">#{tour.container}</span>}
          {Number(tour.trailer_count) > 0 && <span className="text-slate-500">{tour.trailer_count} hænger{Number(tour.trailer_count) === 1 ? "" : "e"}</span>}
          {routeInfo?.distance_km > 0 && <span className="text-slate-500">{routeInfo.distance_km} km</span>}
        </div>
        {(tour.customer_name || tour.private_company) && (
          <p className="mt-1 text-[12px] text-slate-500 inline-flex items-center gap-1 max-w-full"><Building2 className="w-3.5 h-3.5 shrink-0" /><span className="truncate">{tour.customer_name || tour.private_company}</span></p>
        )}
        {oh.note && !done && <p className="mt-2 text-[13px] leading-snug text-amber-900 bg-amber-50 rounded-lg px-2.5 py-2">{oh.note}</p>}
        {done && (
          <p className="mt-2 text-[13px] font-bold text-emerald-700 inline-flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" /> Færdig{tour.time ? ` kl. ${tour.time}` : ""}{tour.weight ? ` · ${Number(tour.weight).toLocaleString("da-DK")} kg` : ""}
            {lines.filter(l => l.actual_qty != null && !["kg", "ton"].includes((l.unit || "").toLowerCase())).map((l, i) => <span key={i}>{` · ${Number(l.actual_qty).toLocaleString("da-DK")} ${l.unit}`}</span>)}
            <span className="text-slate-400 font-semibold">· tryk for at rette</span>
          </p>
        )}
      </button>

      {workshop && workshop.phone && !done && (
        <div className="mx-4 mb-3 flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2" data-testid={`tour-workshop-${tour.id}`}>
          <span className="text-[13px] text-slate-700 min-w-0 truncate"><b>{workshop.name}</b> · {tour.workshop_address}</span>
          <a href={`tel:${workshop.phone.replace(/\s/g, "")}`} aria-label={`Ring til ${workshop.name}`}
            className="min-h-[40px] min-w-[40px] rounded-xl border border-emerald-200 bg-white text-emerald-700 inline-flex items-center justify-center"><Phone className="w-4 h-4" /></a>
        </div>
      )}
      {nextStop && (
        <div className="mx-4 mb-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 flex items-start gap-2" data-testid={`tour-next-stop-${tour.id}`}>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Næste stop · {nextStop.kind === "delivery" ? "aflevering" : "afhentning"} ({stops.indexOf(nextStop) + 1}/{stops.length})</div>
            <div className="text-[15px] font-bold text-slate-900 break-words">{nextStop.address}</div>
            {nextStop.note && <div className="mt-1 text-[13px] text-amber-900 bg-amber-50 rounded-lg px-2 py-1.5">{nextStop.note}</div>}
            {nextStop.contact_name && <div className="text-[12px] text-slate-500 mt-0.5">{nextStop.contact_name}</div>}
          </div>
          {nextStop.contact_phone && (
            <a href={`tel:${nextStop.contact_phone.replace(/\s/g, "")}`} aria-label={`Ring til ${nextStop.contact_name || "kontakt"}`}
              className="min-h-[44px] min-w-[44px] rounded-xl border border-emerald-200 bg-white text-emerald-700 inline-flex items-center justify-center"><Phone className="w-5 h-5" /></a>
          )}
        </div>
      )}

      {cancelled && (
        <div className="mx-4 mb-3 rounded-xl bg-slate-100 border border-slate-300 px-3 py-2.5" data-testid={`tour-cancelled-${tour.id}`}>
          <div className="text-[14px] font-extrabold text-slate-800">{tour.cancelled_on_way ? "Annulleret mens du var på vej" : "Turen er annulleret"}</div>
          <div className="text-[13px] text-slate-600">{tour.cancelled_by_name ? `Af ${tour.cancelled_by_name}` : "Af kunden"}{tour.cancel_reason ? `: ${tour.cancel_reason}` : ""}</div>
          <div className="text-[12px] text-slate-500 mt-0.5">Kør ikke turen. Har du allerede kørt den, så skriv til planlæggeren.</div>
        </div>
      )}
      <div className="flex items-stretch gap-2 px-4 pb-3.5">
        {!done && !cancelled && (
          onWay ? (
            <button type="button" onClick={() => onFinish(tour)} data-testid={`tour-action-btn-${tour.id}`}
              className="flex-1 min-h-[50px] rounded-xl bg-emerald-600 active:bg-emerald-700 text-white font-extrabold text-[15px] inline-flex items-center justify-center gap-2">
              <CheckCircle2 className="w-5 h-5" /> Afslut tur
            </button>
          ) : (
            <button type="button" onClick={() => onStart(tour)} data-testid={`tour-action-btn-${tour.id}`}
              className={`flex-1 min-h-[50px] rounded-xl text-white font-extrabold text-[15px] inline-flex items-center justify-center gap-2 ${haster ? "bg-rose-600 active:bg-rose-700" : "bg-orange-500 active:bg-orange-600"}`}>
              <Play className="w-4 h-4 fill-current" /> {mine ? "Start tur" : "Tag og start"}
            </button>
          )
        )}
        {!done && !cancelled && navTarget && (
          <a href={navUrl(navTarget)} target="_blank" rel="noreferrer" data-testid={`maps-btn-${tour.id}`} aria-label={nextStop ? "Navigér til næste stop" : "Åbn kort"}
            className="min-h-[50px] min-w-[50px] rounded-xl border border-slate-200 text-slate-700 inline-flex items-center justify-center active:bg-slate-50">
            <Navigation className="w-5 h-5" />
          </a>
        )}
        {!done && !cancelled && !navTarget && legs.length > 1 && (
          <button type="button" onClick={() => setNavLegs(legs)} data-testid={`maps-btn-${tour.id}`} aria-label="Vælg hvor du skal hen"
            className="min-h-[50px] min-w-[50px] rounded-xl border border-slate-200 text-slate-700 inline-flex items-center justify-center active:bg-slate-50">
            <Navigation className="w-5 h-5" />
          </button>
        )}
        <NavChooser legs={navLegs} onClose={() => setNavLegs(null)} />
        <button type="button" onClick={() => onChat(tour)} data-testid={`tour-chat-btn-${tour.id}`} aria-label="Beskeder"
          className={`relative min-h-[50px] min-w-[50px] rounded-xl border inline-flex items-center justify-center gap-2 font-semibold text-sm ${done ? "flex-1" : ""} ${
            unread ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-slate-200 text-slate-700 active:bg-slate-50"}`}>
          <MessageSquare className="w-5 h-5" />{done && "Besked"}
          {unread > 0 && <span className="absolute -top-1.5 -right-1.5 min-w-[20px] h-5 px-1 rounded-full bg-rose-600 text-white text-[11px] font-bold flex items-center justify-center">{unread}</span>}
        </button>
      </div>
    </article>
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
