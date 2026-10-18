import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import "@/App.css";
import axios from "axios";
import { toast } from "sonner";
import jsPDF from "jspdf";
import * as XLSX from "xlsx";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts";
import { 
  Truck, Users, Mail, FileText, CheckCircle2, MapPin,
  Wand2, Plus, Trash2, Clock, Weight, X, 
  Pause, RotateCcw, Download, Settings, ChevronDown, Calendar,
  Shield, Send, Eye, Phone, Bell, Car, BarChart3, Navigation, Edit2, LogOut,
  History, Building2, ChevronLeft, ChevronRight, MessageCircle, MessageSquare, GripVertical,
  AlertTriangle, AlertCircle, Circle, WifiOff, Wifi, Archive,
  Camera, Image, ZoomIn, RotateCw, Crop, ScanLine, FolderOpen, FileUp, Megaphone,
  Sun, Moon, MoreVertical, ExternalLink, DollarSign, Loader2, Search, Wrench, Ruler, Upload, Leaf, Package2, UserCheck, Check, ListFilter, ChevronsDown, ChevronsUp, Flag, Filter, Save, XCircle, RefreshCw
} from "lucide-react";
import { useAuth, useFeatureFlag } from "@/auth/AuthContext";
import { formatApiError } from "@/auth/api";
import LoginPage from "@/pages/LoginPage";
import SetPasswordPage from "@/pages/SetPasswordPage";
import PrijsPage from "@/pages/PrijsPage";
import SuperAdminPage from "@/pages/SuperAdminPage";
import CustomerAdminPage from "@/pages/CustomerAdminPage";
import LocationAdminPage from "@/pages/LocationAdminPage";
import ToursWorkspace from "@/pages/ToursWorkspace";
import AdminTabNav from "@/components/AdminTabNav";
import TeamPanel from "@/pages/TeamPanel";
import DriversPanel from "@/pages/DriversPanel";
import { DriverChatSheet, CallPlannerButton } from "@/components/DriverTourCard";
import DriverTodayView from "@/components/DriverTodayView";
import FinishSheet, { effectiveCapture } from "@/components/FinishSheet";
import DriverStopList from "@/components/DriverStopList";
import { initTourOpQueue, enqueueOp, isNetworkError, subscribeOps } from "@/lib/tourOpQueue";
import { enablePush, disablePush, syncPush, pushSupported, isIOS, isStandalone, permission as pushPermission } from "@/lib/push";
import EconomyPanel from "@/pages/EconomyPanel";
import LogisticsLocations from "@/pages/LogisticsLocations";
import { buildDayReportPdf, dayReportFileName } from "@/lib/dayReportPdf";
import { saveAs } from "file-saver";
import GenbrugPladsPage from "@/pages/GenbrugPladsPage";
import PladsPickerPage from "@/pages/PladsPickerPage";
import AdminPladsAddressesModal from "@/components/AdminPladsAddressesModal";
import OCRReceiptScanner from "@/components/ReceiptScanner";
import ReceiptOCRArchive from "@/components/ReceiptOCRArchive";
import { enqueueReceiptUpload, initReceiptUploadQueue, subscribeQueue } from "@/lib/receiptUploadQueue";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

// Wrapper that lets a genbrug_plads HQ admin toggle between the Rapport view
// (GenbrugPladsPage) and the Priser view (PrijsPage). Site users (is_hq_admin=false)
// only see the report.
function GenbrugPladsRouter() {
  const { user } = useAuth();
  const [view, setView] = React.useState("rapport");
  const isHq = !!user?.is_hq_admin;
  if (isHq && view === "priser") {
    return <PrijsPage onBack={() => setView("rapport")} />;
  }
  return (
    <GenbrugPladsPage
      onOpenPrices={isHq ? () => setView("priser") : null}
    />
  );
}

// ============= CONFIRMATION MODAL =============
const ConfirmModal = ({ open, title, message, confirmText = "Ja", cancelText = "Annuller", onConfirm, onCancel, variant = "danger" }) => {
  if (!open) return null;
  const colors = {
    danger: { btn: "bg-red-600 hover:bg-red-700", icon: "text-red-500", ring: "ring-red-100" },
    warning: { btn: "bg-amber-500 hover:bg-amber-600", icon: "text-amber-500", ring: "ring-amber-100" },
    info: { btn: "bg-blue-600 hover:bg-blue-700", icon: "text-blue-500", ring: "ring-blue-100" },
  }[variant] || { btn: "bg-red-600 hover:bg-red-700", icon: "text-red-500", ring: "ring-red-100" };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="confirm-modal">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden animate-[scaleIn_0.2s_ease-out]">
        <div className="p-6 text-center">
          <div className={`w-14 h-14 mx-auto mb-4 rounded-full ${colors.ring} ring-8 flex items-center justify-center`}>
            <AlertTriangle className={`w-7 h-7 ${colors.icon}`} />
          </div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{title}</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">{message}</p>
        </div>
        <div className="flex gap-3 p-4 bg-slate-50 dark:bg-slate-900/50">
          <button onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors"
            data-testid="confirm-cancel-btn">{cancelText}</button>
          <button onClick={onConfirm}
            className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white ${colors.btn} transition-colors`}
            data-testid="confirm-ok-btn">{confirmText}</button>
        </div>
      </div>
    </div>
  );
};

// Priority colors
// Helper: Extract opening hours from remark if open_from/open_to are empty
const extractOpenHours = (tour) => {
  if (tour.open_from && tour.open_to) {
    return { openFrom: tour.open_from, openTo: tour.open_to, cleanRemark: tour.remark || "" };
  }
  // Try to extract from remark: "Tømning 7 14" or "Tømning 6 16 some text"
  const remark = tour.remark || "";
  const match = remark.match(/^([A-Za-zÆØÅæøå]+)\s+(\d{1,2}(?::\d{2})?)\s+(\d{1,2}(?::\d{2})?)(.*)$/);
  if (match) {
    const remaining = match[4].trim();
    return { openFrom: match[2], openTo: match[3], cleanRemark: remaining || "" };
  }
  return { openFrom: "", openTo: "", cleanRemark: remark };
};

const PRIORITY_COLORS = {
  urgent: { bg: "bg-red-500", text: "text-white", border: "border-red-500", label: "HASTER" },
  high: { bg: "bg-orange-500", text: "text-white", border: "border-orange-500", label: "HØJ" },
  normal: { bg: "bg-blue-500", text: "text-white", border: "border-blue-500", label: "NORMAL" },
  low: { bg: "bg-slate-400", text: "text-white", border: "border-slate-400", label: "LAV" }
};

// Driver color system - consistent color per driver name
const DRIVER_COLORS = [
  { bg: "bg-blue-600", text: "text-white", light: "bg-blue-100 text-blue-800" },
  { bg: "bg-purple-600", text: "text-white", light: "bg-purple-100 text-purple-800" },
  { bg: "bg-teal-600", text: "text-white", light: "bg-teal-100 text-teal-800" },
  { bg: "bg-rose-600", text: "text-white", light: "bg-rose-100 text-rose-800" },
  { bg: "bg-amber-600", text: "text-white", light: "bg-amber-100 text-amber-800" },
  { bg: "bg-cyan-600", text: "text-white", light: "bg-cyan-100 text-cyan-800" },
  { bg: "bg-indigo-600", text: "text-white", light: "bg-indigo-100 text-indigo-800" },
  { bg: "bg-emerald-700", text: "text-white", light: "bg-emerald-100 text-emerald-800" },
];
const getDriverColor = (name) => {
  if (!name) return DRIVER_COLORS[0];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return DRIVER_COLORS[Math.abs(hash) % DRIVER_COLORS.length];
};

// Get current time in HH:MM format
const getCurrentTime = () => {
  const now = new Date();
  return now.toTimeString().slice(0, 5);
};

// Open address in maps
const openInMaps = (address) => {
  if (!address) return;
  const encodedAddress = encodeURIComponent(address + ", Denmark");
  window.open(`https://www.google.com/maps/search/?api=1&query=${encodedAddress}`, '_blank');
};

// ─── Fase 11 (2026-06-18): Kompakt info-blok pr. bestilling/tur ────────────
// Brugerkrav: vis bestillingsdato + bestillingstid (created_at), planlagt
// afhentningsdato (order_date), kapacitetsmål (capacity_label / m³) og
// opgavetype som én kompakt linje med ikoner. Bruges på admin-, chauffør-
// og kundeside.
const TOUR_TYPE_LABELS = {
  normal: "Afhent container",
  flyt: "Byt container",
  vaerksted: "Til værksted",
  afhent_vaerksted: "Afhent fra værksted",
  // Fase 15.16 (2026-02-21): Estimat = forventet ressourcebehov (vises kun
  // i logistik-admin's Planlæg ressourcer, ikke som chauffør-tur).
  estimat: "Estimat",
  // Fase 15.41 (2026-02-22): Løs afhentning - kunden ejer ikke containere;
  // chauffør medbringer egne. Lander hos chauffør som almindelig tur.
  loes_afhentning: "Løs afhentning",
  // 2026-10-18: Gods/andet (premium) - før vistes rå koder som "afhent_lever".
  afhentning: "Afhentning",
  levering: "Levering",
  afhent_lever: "Afhentning + levering",
  flytning: "Flytning",
  andet: "Andet",
};
const _fmtDateDM = (s) => {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit" });
  } catch (_) { return s; }
};
const _fmtTimeHM = (s) => {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
  } catch (_) { return s; }
};
// Fase 15.50 (2026-02-22): "Afsluttet"-tidsstempel - viser kun klokkeslæt
// hvis afslutningen skete i dag, ellers DD/MM + klokkeslæt. Fx
//   - Samme dag : "kl. 14:32"
//   - I går     : "21/06 kl. 14:32"
const formatCompletedAt = (s) => {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const today = new Date();
    const sameDay = d.getFullYear() === today.getFullYear()
      && d.getMonth() === today.getMonth()
      && d.getDate() === today.getDate();
    const time = d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
    if (sameDay) return `kl. ${time}`;
    const dm = d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit" });
    return `${dm} kl. ${time}`;
  } catch (_) { return s; }
};
// Henter capacity label fra en ordre eller tur i prioriteret rækkefølge.
const _getCapacityLabel = (obj) => {
  if (!obj) return "";
  return (
    obj.capacity_label ||
    (obj.capacity_volume_m3 != null ? `${obj.capacity_volume_m3} m³` : "") ||
    obj.container_capacity ||
    ""
  );
};
// Fase 15 (2026-06-19): Konsistent format overalt: "{Label} ({volume} m³)".
// Brug på Driver-kort, Mine/Alle Bestillinger, Location Admin, Logistik Admin,
// rapporter etc. Hvis kun ét felt findes, vises det alene (uden parentes).
const formatCapacity = (obj) => {
  if (!obj) return "";
  const label = (obj.capacity_label || "").trim();
  const m3 = obj.capacity_volume_m3;
  if (label && m3 != null && m3 !== "") return `${label} (${m3} m³)`;
  if (label) return label;
  if (m3 != null && m3 !== "") return `${m3} m³`;
  return (obj.container_capacity || "").toString();
};
// Fase 15.13 (2026-02-XX): Prioritets-chip - vises på ALLE tur-kort som
// generel info. "Haster" overruler stadig sorteringen (HASTER-sektion).
// Mapping: urgent/haster → "Haster" (rød), low/senere → "Lav" (slate),
// alt andet → "Normal" (blå).
const PRIORITY_CHIP_MAP = {
  urgent: { label: "Haster",  cls: "bg-red-500/20 text-red-200 border-red-500/40" },
  haster: { label: "Haster",  cls: "bg-red-500/20 text-red-200 border-red-500/40" },
  high:   { label: "Haster",  cls: "bg-red-500/20 text-red-200 border-red-500/40" },
  normal: { label: "Normal",  cls: "bg-blue-500/15 text-blue-200 border-blue-500/40" },
  low:    { label: "Lav",     cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
  senere: { label: "Lav",     cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
};
const getPriorityChip = (tour) => {
  const p = (tour?.priority || "normal").toString().toLowerCase();
  if (PRIORITY_CHIP_MAP[p]) return PRIORITY_CHIP_MAP[p];
  // 2026-10-18: Kun prioritetsfeltet (samme kilde som prisen). "haster" i
  // noten sættes til prioritet ved oprettelse i backend.
  return PRIORITY_CHIP_MAP.normal;
};
const OrderInfoLine = ({ order, dark = false, compact = false, testid = "" }) => {
  if (!order) return null;
  // Fase 15.20 (2026-02-21): "Bestilt"-feltet (created_at) fjernet fra denne
  // linje for at undgå duplikat med "Oprettet"-stamp som vises andetsteds
  // på samme kort. "Afhentes" omdøbt til "Bestillingsdato" - samme datakilde
  // (order_date), bare nyt navn. Gælder ALLE bestillingstyper inkl. Estimat.
  const orderDate = order.order_date || "";
  // Fase 15 (2026-06-19): Vis konsistent "{label} ({volume} m³)" overalt.
  const cap = formatCapacity(order);
  const tt = order.tour_type || "normal";
  const ttLabel = TOUR_TYPE_LABELS[tt] || tt;
  // Fase 15.41 (2026-02-22): For "løs afhentning" SKAL container-info (id +
  // kapacitetsmål) IKKE vises - kunden ejer ikke containerne. Vi viser i
  // stedet "Estimeret antal containere" + evt. total vægt når chaufføren
  // har registreret den.
  const isLoes = tt === "loes_afhentning";
  const showCap = !!cap && !isLoes;
  const looseCount = isLoes ? (order.loose_estimated_count || 0) : 0;
  const looseTotalKg = isLoes && Array.isArray(order.container_weights)
    ? order.container_weights.reduce((s, w) => s + (parseFloat(w) || 0), 0)
    : 0;
  const looseRegistered = isLoes && Array.isArray(order.container_weights) ? order.container_weights.length : 0;
  const dotCls = dark ? "text-slate-500" : "text-slate-400";
  const lblCls = dark ? "text-slate-400" : "text-slate-500";
  const valCls = dark ? "text-slate-200" : "text-slate-700";
  const sep = <span className={`mx-1.5 ${dotCls}`}>·</span>;
  const sizeCls = compact ? "text-[10px]" : "text-[11px]";
  return (
    <div
      className={`flex flex-wrap items-center gap-y-1 ${sizeCls} ${valCls}`}
      data-testid={testid || "order-info-line"}
    >
      {/* Fase 15.42 (2026-02-22): Tydelig LØS AFHENTNING-badge i toppen af
          info-linjen så det er umiddelbart synligt i Mine/Alle Bestillinger.
          Amber baggrund + Truck-ikon - matcher chauffør-side. */}
      {isLoes && (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 mr-2 rounded-md bg-amber-500 text-white font-black text-[10px] uppercase tracking-wider shadow-sm"
          data-testid={`order-loes-badge-${order.id || order.tour_id || "x"}`}
          title="Løs afhentning - chauffør medbringer egne tomme containere"
        >
          <Truck className="w-3 h-3" />
          Løs afhentning
        </span>
      )}
      {orderDate && (
        <span className="inline-flex items-center gap-1" title="Bestillingsdato (planlagt udførelse)">
          <Calendar className="w-3 h-3 text-blue-500" />
          <span className={lblCls}>Bestillingsdato</span>
          <span className="font-semibold">{_fmtDateDM(orderDate)}</span>
        </span>
      )}
      {showCap && (<>
        {orderDate && sep}
        <span className="inline-flex items-center gap-1" title="Kapacitetsmål">
          <Package2 className="w-3 h-3 text-amber-500" />
          <span className="font-semibold">{cap}</span>
        </span>
      </>)}
      {/* Fase 15.41 (2026-02-22): Løs afhentning - vises "Estimeret antal
          containere" + evt. registrerede vægte i stedet for kapacitetsmål. */}
      {isLoes && looseCount > 0 && (<>
        {orderDate && sep}
        <span className="inline-flex items-center gap-1" title="Estimeret antal containere" data-testid={`order-loose-count-${order.id || order.tour_id || "x"}`}>
          <Package2 className="w-3 h-3 text-amber-500" />
          <span className={lblCls}>Estimat</span>
          <span className="font-semibold">{looseCount} container{looseCount === 1 ? "" : "e"}</span>
        </span>
      </>)}
      {isLoes && looseRegistered > 0 && (<>
        {sep}
        <span className="inline-flex items-center gap-1" title={order.completed ? "Endelig registreret vægt fra chauffør" : "Foreløbig vægt - chaufføren har endnu ikke afsluttet turen"} data-testid={`order-loose-weight-${order.id || order.tour_id || "x"}`}>
          <Truck className="w-3 h-3 text-emerald-500" />
          <span className={lblCls}>Vægt</span>
          <span className="font-semibold">{looseTotalKg.toLocaleString("da-DK", { maximumFractionDigits: 1 })} kg / {looseRegistered} container{looseRegistered === 1 ? "" : "e"}</span>
          {/* Fase 15.43 (2026-02-22): Når turen ikke er afsluttet vises et
              tydeligt "Udkast"-badge så order-user ved at chaufføren stadig
              er i gang. */}
          {!order.completed && (
            <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider bg-blue-500 text-white animate-pulse" data-testid={`order-loose-weight-draft-${order.id || order.tour_id || "x"}`} title="Udkast - chaufføren tilføjer stadig vægte">
              Udkast
            </span>
          )}
        </span>
      </>)}
      {tt && !isLoes && (<>
        {(orderDate || showCap) && sep}
        <span className="inline-flex items-center gap-1" title="Opgavetype">
          <Wrench className="w-3 h-3 text-purple-500" />
          <span className="font-semibold">{ttLabel}</span>
        </span>
      </>)}
      {/* Fase 13 (2026-06-18): "Bestilt af" - vises både på chauffør-tur-kort
          og i Logistik Admin Planlægning split-view. Backend lægger
          `created_by_name` (eller `created_by_email` som fallback) på selve
          turen via mirror-update fra ordren. */}
      {(order.created_by_name || order.created_by_email) && (<>
        {(orderDate || showCap || isLoes || tt) && sep}
        <span className="inline-flex items-center gap-1" title="Bestilt af">
          <Users className="w-3 h-3 text-blue-500" />
          <span className={lblCls}>Bestilt af</span>
          <span className="font-semibold">{order.created_by_name || order.created_by_email}</span>
        </span>
      </>)}
    </div>
  );
};

// ─── Fase 12 (2026-06-18): Manuel tidsregistrering modal ──────────────────
// Dag-niveau fallback: én post pr. dag pr. chauffør med dato + start + slut
// + valgfri årsag. Bruges af logistik-admin (Fase 15.28 flyttet hertil).
const ManualTimeEntryModal = ({ open, onClose, onSave, defaultDate, mode = "driver", drivers = [], requireReason = false }) => {
  const [date, setDate] = useState(defaultDate || new Date().toISOString().slice(0, 10));
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [reason, setReason] = useState("");
  const [driverId, setDriverId] = useState("");
  // Fase 15.30 (2026-02-22): "work" eller "pause" - admin kan oprette en
  // pause-periode på vegne af chaufføren.
  const [sliceType, setSliceType] = useState("work");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDate(defaultDate || new Date().toISOString().slice(0, 10));
      setStartTime("");
      setEndTime("");
      setReason("");
      setDriverId("");
      setSliceType("work");
    }
  }, [open, defaultDate]);

  if (!open) return null;

  const computedDuration = (() => {
    if (!startTime || !endTime) return null;
    const [sh, sm] = startTime.split(":").map(Number);
    const [eh, em] = endTime.split(":").map(Number);
    if ([sh, sm, eh, em].some(n => isNaN(n))) return null;
    // Fase 15.35 (2026-02-22): Strikt regel - start > end er en fejl på
    // samme dato (ingen overnight-wrap). Returnerer negativ → UI viser
    // fejl + save disabled.
    const mins = (eh * 60 + em) - (sh * 60 + sm);
    if (mins <= 0) return { mins: -1, label: "Ugyldig - slut skal være efter start", invalid: true };
    const hh = Math.floor(mins / 60);
    const mm = mins % 60;
    return { mins, label: `${hh}t ${String(mm).padStart(2, "0")}m`, invalid: false };
  })();

  const reasonInvalid = requireReason && !reason.trim();
  const valid = date && startTime && endTime && computedDuration && !computedDuration.invalid && computedDuration.mins > 0 && (mode === "driver" || driverId) && !reasonInvalid;

  const handleSubmit = async () => {
    if (!valid) {
      if (mode === "admin" && !driverId) { toast.error("Vælg chauffør"); return; }
      if (reasonInvalid) { toast.error("Årsag er påkrævet"); return; }
      toast.error("Udfyld dato, starttidspunkt og sluttidspunkt");
      return;
    }
    setSaving(true);
    try {
      const payload = { date, start_time: startTime, end_time: endTime, reason: reason || "", slice_type: sliceType };
      if (mode === "admin") payload.driver_id = driverId;
      await onSave(payload);
      const lbl = sliceType === "pause" ? "Manuel pause-periode gemt" : "Manuel arbejdsperiode gemt";
      toast.success(`${lbl} - ${computedDuration.label}`);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke gemme tidsregistrering");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-4" onClick={onClose} data-testid="manual-time-modal">
      <div
        className="bg-white dark:bg-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-orange-500/15 flex items-center justify-center">
              <Clock className="w-5 h-5 text-orange-500" />
            </div>
            <div>
              <h2 className="font-bold text-slate-800 dark:text-slate-100">Manuel tidsregistrering</h2>
              <p className="text-[11px] text-slate-500">Glemt at stemple ind eller ud?</p>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center justify-center" data-testid="manual-time-close-btn">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {mode === "admin" && (
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Chauffør <span className="text-red-500">*</span></label>
              <select
                value={driverId}
                onChange={(e) => setDriverId(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm focus:outline-none focus:border-orange-400"
                data-testid="manual-time-driver"
              >
                <option value="">- Vælg chauffør -</option>
                {drivers.map(d => (
                  <option key={d.id} value={d.id}>{d.name || d.email}</option>
                ))}
              </select>
            </div>
          )}
          {/* Fase 15.30 (2026-02-22): Vælg type - arbejde eller pause */}
          <div data-testid="manual-time-slice-type-row">
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Hvilken slags periode?</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setSliceType("work")}
                className={`h-11 rounded-lg font-bold text-sm flex items-center justify-center gap-1.5 ${sliceType === "work" ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="manual-time-slice-work"
              >
                <Clock className="w-3.5 h-3.5" /> Arbejde
              </button>
              <button
                type="button"
                onClick={() => setSliceType("pause")}
                className={`h-11 rounded-lg font-bold text-sm flex items-center justify-center gap-1.5 ${sliceType === "pause" ? "bg-blue-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="manual-time-slice-pause"
              >
                <Pause className="w-3.5 h-3.5" /> Pause
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Dato</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm focus:outline-none focus:border-orange-400"
              data-testid="manual-time-date-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Start</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm font-mono focus:outline-none focus:border-orange-400"
                data-testid="manual-time-start-input"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Slut</label>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm font-mono focus:outline-none focus:border-orange-400"
                data-testid="manual-time-end-input"
              />
            </div>
          </div>
          {computedDuration && (
            <div className={`px-3 py-2 rounded-lg text-xs font-semibold ${
              computedDuration.invalid
                ? "bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700"
                : sliceType === "pause"
                  ? "bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300"
                  : "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300"
            }`} data-testid="manual-time-duration">
              {computedDuration.invalid ? (
                <span className="flex items-center gap-1.5"><X className="w-3.5 h-3.5" /> {computedDuration.label}</span>
              ) : (
                <>
                  Beregnet varighed: <span className="font-mono">{computedDuration.label}</span>
                  {sliceType === "pause" && <span className="ml-2 italic">(pause - tæller ikke som arbejdstid)</span>}
                </>
              )}
            </div>
          )}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Årsag {requireReason
              ? <span className="text-red-500">*</span>
              : <span className="font-normal lowercase text-slate-400">(valgfri)</span>}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Fx 'Glemte at stemple ind kl. 7:00 da jeg startede med det samme på en akut tur.'"
              rows={2}
              className={`w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700 border text-sm focus:outline-none resize-none ${reasonInvalid ? "border-red-400 focus:border-red-500" : "border-slate-200 dark:border-slate-600 focus:border-orange-400"}`}
              data-testid="manual-time-reason-input"
            />
            {reasonInvalid && (
              <p className="text-[11px] text-red-500 mt-1">Årsag er obligatorisk på dette firma.</p>
            )}
          </div>
        </div>

        <div className="p-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-2">
          <button
            onClick={onClose}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="manual-time-cancel-btn"
          >
            Annuller
          </button>
          <button
            onClick={handleSubmit}
            disabled={!valid || saving}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            data-testid="manual-time-save-btn"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Gem
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Fase 15.28 (2026-02-22): Manuel stempel modal (event-baseret) ─────────
// ÉT enkelt stempel ad gangen (IND eller UD) med dato + tidspunkt + valgfri
// årsag. Erstatter den tidligere periode-baserede modal på chaufførsiden.
// Periode-modal'en findes stadig som ManualTimeEntryModal og bruges af admin.
const ManualPunchModal = ({ open, onClose, onSave, defaultDate, mode = "driver", drivers = [], requireReason = false }) => {
  const [date, setDate] = useState(defaultDate || new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState("");
  const [type, setType] = useState("ind");
  // Fase 15.30 (2026-02-22): "work" (arbejde) eller "pause". Kun relevant
  // når type="ind". UD lukker det åbne slice uanset type.
  const [sliceType, setSliceType] = useState("work");
  const [reason, setReason] = useState("");
  const [driverId, setDriverId] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDate(defaultDate || new Date().toISOString().slice(0, 10));
      setTime("");
      setType("ind");
      setSliceType("work");
      setReason("");
      setDriverId("");
    }
  }, [open, defaultDate]);

  if (!open) return null;

  // Fase 15.31 (2026-02-22): Manuel stempel må IKKE oprettes med tidspunkt
  // i fremtiden. UI'et viser fejl-feedback med det samme - backend laver
  // det autoritative tjek.
  const isFutureDateTime = (() => {
    if (!date || !time) return false;
    try {
      const dt = new Date(`${date}T${time}`);
      return dt.getTime() > Date.now() + 60 * 1000;
    } catch { return false; }
  })();

  const reasonInvalid = requireReason && !reason.trim();
  const valid = date && time && type && (mode === "driver" || driverId) && !reasonInvalid && !isFutureDateTime;

  const handleSubmit = async () => {
    if (!valid) {
      if (mode === "admin" && !driverId) { toast.error("Vælg chauffør"); return; }
      if (reasonInvalid) { toast.error("Årsag er påkrævet"); return; }
      if (isFutureDateTime) { toast.error("Tidspunktet ligger i fremtiden - manuelle stempler kan kun oprettes for tidspunkter der allerede er passeret."); return; }
      toast.error("Udfyld dato, tidspunkt og type");
      return;
    }
    setSaving(true);
    try {
      const payload = { date, time, type, reason: (reason || "").trim() };
      if (mode === "admin") payload.driver_id = driverId;
      // Fase 15.30 (2026-02-22): slice_type sendes kun for IND. UD lukker
      // det åbne slice uanset arbejde/pause.
      if (type === "ind") payload.slice_type = sliceType;
      await onSave(payload);
      const label = type === "ind"
        ? `Manuel ${sliceType === "pause" ? "pause" : "arbejde"} startet`
        : `Manuel UD gemt`;
      toast.success(label);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke gemme manuel stempel");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-4" onClick={onClose} data-testid="manual-punch-modal">
      <div className="bg-white dark:bg-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-amber-500/15 flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-500" />
            </div>
            <div>
              <h2 className="font-bold text-slate-800 dark:text-slate-100">Manuel stempel</h2>
              <p className="text-[11px] text-slate-500">Ét stempel ad gangen - IND eller UD</p>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center justify-center" data-testid="manual-punch-close-btn">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {mode === "admin" && (
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Chauffør <span className="text-red-500">*</span></label>
              <select
                value={driverId}
                onChange={(e) => setDriverId(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm focus:outline-none focus:border-amber-400"
                data-testid="manual-punch-driver"
              >
                <option value="">- Vælg chauffør -</option>
                {drivers.map(d => (
                  <option key={d.id} value={d.id}>{d.name || d.email}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Stempel-type</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setType("ind")}
                className={`h-11 rounded-lg font-bold text-sm ${type === "ind" ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="manual-punch-type-ind"
              >Start (IND)</button>
              <button
                type="button"
                onClick={() => setType("ud")}
                className={`h-11 rounded-lg font-bold text-sm ${type === "ud" ? "bg-orange-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="manual-punch-type-ud"
              >Slut (UD)</button>
            </div>
          </div>
          {/* Fase 15.30 (2026-02-22): Slice-type vælger - kun synlig ved IND.
              Arbejde åbner et arbejds-slice; Pause åbner et pause-slice. */}
          {type === "ind" && (
            <div data-testid="manual-punch-slice-type-row">
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Hvilken slags slice?</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSliceType("work")}
                  className={`h-11 rounded-lg font-bold text-sm flex items-center justify-center gap-1.5 ${sliceType === "work" ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                  data-testid="manual-punch-slice-work"
                >
                  <Clock className="w-3.5 h-3.5" /> Arbejde
                </button>
                <button
                  type="button"
                  onClick={() => setSliceType("pause")}
                  className={`h-11 rounded-lg font-bold text-sm flex items-center justify-center gap-1.5 ${sliceType === "pause" ? "bg-blue-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                  data-testid="manual-punch-slice-pause"
                >
                  <Pause className="w-3.5 h-3.5" /> Pause
                </button>
              </div>
              <p className="mt-1 text-[10px] text-slate-500 italic">
                {sliceType === "pause"
                  ? "Pause-slices tæller separat fra arbejdstid."
                  : "Arbejde tæller i den daglige arbejdstid."}
              </p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Dato</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm focus:outline-none focus:border-amber-400"
                data-testid="manual-punch-date"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Tidspunkt</label>
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm font-mono focus:outline-none focus:border-amber-400"
                data-testid="manual-punch-time"
              />
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Årsag {requireReason
                ? <span className="text-red-500">*</span>
                : <span className="font-normal lowercase text-slate-400">(valgfri)</span>}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Fx 'Glemte at klokke ud kl. 17:00'"
              rows={2}
              className={`w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700 border text-sm focus:outline-none resize-none ${reasonInvalid ? "border-red-400 focus:border-red-500" : "border-slate-200 dark:border-slate-600 focus:border-amber-400"}`}
              data-testid="manual-punch-reason"
            />
            {reasonInvalid && (
              <p className="text-[11px] text-red-500 mt-1">Årsag er obligatorisk på dette firma.</p>
            )}
          </div>
          {/* Fase 15.31 (2026-02-22): Inline fejl hvis tidspunkt er i fremtiden */}
          {isFutureDateTime && (
            <p className="text-[11px] text-red-600 dark:text-red-400 font-semibold flex items-center gap-1" data-testid="manual-punch-future-error">
              <X className="w-3 h-3" /> Tidspunktet ligger i fremtiden - kan ikke registreres.
            </p>
          )}
        </div>

        <div className="p-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-2">
          <button
            onClick={onClose}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="manual-punch-cancel"
          >Annuller</button>
          <button
            onClick={handleSubmit}
            disabled={!valid || saving}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            data-testid="manual-punch-save"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Gem stempel
          </button>
        </div>
      </div>
    </div>
  );
};


// Fase 15.31 (2026-02-22): Driver-egen edit-modal til at rette en
// manuelt-oprettet entry. Felter: dato, start, slut, slice_type, årsag.
// Fremtid- og overlap-validering håndteres af backend, men frontend
// laver UX-feedback før submit.
const EditOwnEntryModal = ({ open, entry, onClose, onSaved }) => {
  const [date, setDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [sliceType, setSliceType] = useState("work");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (open && entry) {
      setDate(entry.date || "");
      setStartTime(entry.start_time || "");
      setEndTime(entry.end_time || "");
      setSliceType((entry.slice_type || "work").toLowerCase());
      setReason(entry.reason || "");
      setErr("");
    }
  }, [open, entry]);

  if (!open || !entry) return null;

  // Lokal fremtid-tjek for UX. Backend laver autoritativt tjek.
  const isFuture = (d, t) => {
    if (!d || !t) return false;
    try {
      const dt = new Date(`${d}T${t}`);
      return dt.getTime() > Date.now() + 60 * 1000;
    } catch { return false; }
  };
  const startFuture = isFuture(date, startTime);
  const endFuture = endTime ? isFuture(date, endTime) : false;
  // Fase 15.35 (2026-02-22): Strikt regel - slut skal være efter start
  // (samme dato, ingen overnight-wrap).
  const startEndInvalid = (() => {
    if (!startTime || !endTime) return false;
    const [sh, sm] = startTime.split(":").map(Number);
    const [eh, em] = endTime.split(":").map(Number);
    if ([sh, sm, eh, em].some(n => isNaN(n))) return false;
    return (eh * 60 + em) <= (sh * 60 + sm);
  })();
  const valid = date && startTime && !startFuture && !endFuture && !startEndInvalid;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const payload = {
        date,
        start_time: startTime,
        end_time: endTime || "",
        slice_type: sliceType,
        reason: reason || "",
      };
      const r = await axios.patch(`${API}/driver/time-entries/${entry.id}`, payload);
      toast.success("Manuel registrering opdateret");
      onSaved?.(r.data);
      onClose();
    } catch (e) {
      const msg = e?.response?.data?.detail || "Kunne ikke gemme ændringer";
      setErr(msg); toast.error(msg);
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" data-testid="edit-own-entry-modal">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Edit2 className="w-4 h-4 text-blue-500" />
            <h3 className="font-bold text-sm">Rediger manuel registrering</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700" data-testid="edit-own-entry-cancel">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Dato</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm"
              data-testid="edit-own-entry-date" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Start</label>
              <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)}
                className={`w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border text-sm font-mono ${startFuture ? "border-red-400" : "border-slate-200 dark:border-slate-600"}`}
                data-testid="edit-own-entry-start" />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Slut (valgfri)</label>
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)}
                className={`w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border text-sm font-mono ${endFuture ? "border-red-400" : "border-slate-200 dark:border-slate-600"}`}
                data-testid="edit-own-entry-end" />
            </div>
          </div>
          {(startFuture || endFuture) && (
            <p className="text-[11px] text-red-500" data-testid="edit-own-entry-future-error">
              Tidspunkt må ikke ligge i fremtiden.
            </p>
          )}
          {/* Fase 15.35 (2026-02-22): Strikt regel - slut > start */}
          {startEndInvalid && (
            <p className="text-[11px] text-red-600 dark:text-red-400 font-semibold flex items-center gap-1" data-testid="edit-own-entry-startend-error">
              <X className="w-3 h-3" /> Sluttidspunkt skal være efter starttidspunkt.
            </p>
          )}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Type</label>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => setSliceType("work")}
                className={`h-10 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 ${sliceType === "work" ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="edit-own-entry-slice-work">
                <Clock className="w-3.5 h-3.5" /> Arbejde
              </button>
              <button type="button" onClick={() => setSliceType("pause")}
                className={`h-10 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 ${sliceType === "pause" ? "bg-blue-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="edit-own-entry-slice-pause">
                <Pause className="w-3.5 h-3.5" /> Pause
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Årsag (valgfri)</label>
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Fx 'Glemt at stemple ind'"
              className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm"
              data-testid="edit-own-entry-reason" />
          </div>
          {err && (
            <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-300 text-xs" data-testid="edit-own-entry-err">{err}</div>
          )}
        </div>
        <div className="p-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-2">
          <button onClick={onClose} className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={submit} disabled={!valid || saving}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            data-testid="edit-own-entry-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Gem ændringer
          </button>
        </div>
      </div>
    </div>
  );
};
const useOnlineStatus = () => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  
  useEffect(() => {
    const handleOnline = () => { setIsOnline(true); toast.success("Online igen!"); };
    const handleOffline = () => { setIsOnline(false); toast.warning("Offline - data gemmes lokalt"); };
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  
  return isOnline;
};

// PWA Install hook
const usePWAInstall = () => {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    // Check if already installed
    if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) {
      setIsInstalled(true);
      return;
    }

    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };

    const installedHandler = () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', installedHandler);

    return () => {
      window.removeEventListener('beforeinstallprompt', handler);
      window.removeEventListener('appinstalled', installedHandler);
    };
  }, []);

  const install = async () => {
    if (!deferredPrompt) return false;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    setDeferredPrompt(null);
    return outcome === 'accepted';
  };

  return { canInstall: !!deferredPrompt && !isInstalled, isInstalled, install };
};

// Service Worker Registration
const registerServiceWorker = () => {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js')
        .then((registration) => {
          console.log('SW registered:', registration.scope);
          
          // Listen for SW messages (offline queue)
          navigator.serviceWorker.addEventListener('message', (event) => {
            if (event.data.type === 'OFFLINE_QUEUE_ADD') {
              const queue = JSON.parse(localStorage.getItem('ilk-offline-queue') || '[]');
              queue.push(event.data.data);
              localStorage.setItem('ilk-offline-queue', JSON.stringify(queue));
            }
            if (event.data.type === 'SYNC_OFFLINE_QUEUE') {
              syncOfflineQueue();
            }
          });
        })
        .catch((err) => console.log('SW registration failed:', err));
    });
  }
};

// Process offline queue when back online
const syncOfflineQueue = async () => {
  const queue = JSON.parse(localStorage.getItem('ilk-offline-queue') || '[]');
  if (queue.length === 0) return;
  
  const remaining = [];
  let synced = 0;
  for (const item of queue) {
    try {
      const res = await fetch(item.url, {
        method: item.method,
        headers: item.headers,
        body: item.body
      });
      if (res.ok) { synced++; }
      else { remaining.push(item); }
    } catch (e) {
      remaining.push(item);
    }
  }
  localStorage.setItem('ilk-offline-queue', JSON.stringify(remaining));
  if (synced > 0) {
    toast.success(`✅ ${synced} offline ændringer synkroniseret!`);
  }
  if (remaining.length > 0) {
    toast.error(`⚠️ ${remaining.length} handlinger kunne ikke synkroniseres - prøv igen`);
  }
};

// Queue an action for offline retry
const queueOfflineAction = (url, method, body, headers = {}) => {
  try {
    const queue = JSON.parse(localStorage.getItem('ilk-offline-queue') || '[]');
    queue.push({
      url, method, headers: { 'Content-Type': 'application/json', ...headers },
      body: typeof body === 'string' ? body : JSON.stringify(body),
      queued_at: new Date().toISOString()
    });
    localStorage.setItem('ilk-offline-queue', JSON.stringify(queue));
    toast.warning('📴 Offline - handlingen gemmes og sendes når du er online igen');
  } catch(e) { console.error('Queue error:', e); }
};

// Register on load
registerServiceWorker();

// Fase 17.13 (2026-02-27): Aktivér receipt-upload-køen ved app-start så
// pending kvitteringer fra forrige session bliver retried automatisk
// (overlever browser-luk, dårlig dækning, iOS Safari reloads).
initReceiptUploadQueue();
// 2026-10-18: Offline-kø for start/stop-kryds/billeder/afslutning.
initTourOpQueue();

// ============= ORDER PRIORITIES =============
const ORDER_PRIORITIES = {
  normal: { bg: "bg-blue-500", text: "text-white", label: "Normal" },
  haster: { bg: "bg-red-500", text: "text-white", label: "Haster" },
  sidst: { bg: "bg-slate-400", text: "text-white", label: "Sidst" }
};

// ============= CUSTOMER ORDER PAGE =============
const CustomerOrderPage = ({ locationCode, pladsName = "", prefillAddress = "", onBack, onLogout = null, userName = "", adminMode = false, onSwitchLocation = null }) => {
  // onBack  -> "Tilbage til start": for an order-user with a pinned
  //            location_code we re-render the picker (in practice this means
  //            resetting the order form). NEVER logs out anymore.
  // onLogout -> explicit "Log ud" action (header + success-screen).
  //            Falls back to onBack when not supplied (kiosk/QR flow).
  // adminMode -> true when a location_admin opens this page from their admin
  //            dashboard. Adds container-edit + lock controls.
  // onSwitchLocation -> (code, name) callback to swap to a different plads
  //            without logging out. Enables in-page "Lokation"-switcher.
  // Local date helper (timezone-safe)
  const localDateStr = (d = new Date()) => {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  };
  const [location, setLocation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [materials, setMaterials] = useState([]);
  // Fase 15.40 (2026-02-22): Klient-platformsfunktioner - bestillings-siden
  // gater estimat-mode + estimat-form bag `estimate`-feature-flaget. Default
  // er DISABLED, så super-admin skal aktivt slå feature til pr. klient.
  const isFeatureEnabled = useFeatureFlag();
  const estimateEnabled = isFeatureEnabled("estimate");
  // Fase 15.41 (2026-02-22): "Løs afhentning"-feature - kunden ejer ikke
  // containere; chauffør medbringer egne. Skjuler container-vælger og viser
  // et "Estimeret antal containere"-felt i stedet. Default OFF - super-admin
  // skal aktivere pr. klient.
  const loesAfhentningEnabled = isFeatureEnabled("loes_afhentning");
  // Fase 9 refactor (2026-06-18): Per-material CO2-kategori mapping
  // (material_name → co2_type_id) hentet fra `plads.material_co2_categories`.
  const [materialCo2Map, setMaterialCo2Map] = useState({});

  // Per-partner container setup (brugerkrav 2026-06-15):
  // Når lokationen har 2+ logistik-partnere, skal medarbejderen først vælge
  // hvilken partner de bestiller til. Materialer + container-data filtreres
  // server-side på `partner_id`. Hvis kun én partner er knyttet auto-vælges
  // den. Toppen af bestillingssiden viser en dropdown til at skifte.
  const [partners, setPartners] = useState([]);
  const [partnerId, setPartnerId] = useState("");
  const [partnersLoaded, setPartnersLoaded] = useState(false);

  // Lokation-switcher (brugerkrav 2026-06-15 runde 15):
  // Når brugeren har adgang til 2+ pladser skal de kunne skifte uden at logge
  // ud. Vi henter `/api/plads` (server-side filtreret efter tenant +
  // assigned_plads_ids) og viser et dropdown-felt ved siden af partner-vælgeren.
  const [availablePladser, setAvailablePladser] = useState([]);
  // Fase 18.37 (mobil): location-switcher konverteret til ikon-only med popover
  // i top-højre hjørne. Denne state styrer om popoveren er åben.
  const [mobileLocMenuOpen, setMobileLocMenuOpen] = useState(false);
  // Fase 18.38 (mobil): partner-switcher konverteret til ikon-only med popover.
  const [mobilePartnerMenuOpen, setMobilePartnerMenuOpen] = useState(false);

  // Stepper state
  const [step, setStep] = useState(1); // 1=material, 2=container, 3=confirm, 4=priority, 5=submit
  const [selectedMaterial, setSelectedMaterial] = useState("");
  const [containers, setContainers] = useState([]);
  const [selectedContainer, setSelectedContainer] = useState(null);
  // Fase 15.16 (2026-02-XX): Aktive (ikke-fuldførte) bestillinger per
  // (container_number, tour_type) → vises som "grå/lås"-overlay på
  // container-grid så medarbejder kan se at en container allerede har en
  // bestilling, og hvilken opgavetype den er bundet til. Forskelligt
  // tour_type på samme container er OK.
  const [blockedByContainer, setBlockedByContainer] = useState({});
  const refreshBlockedByContainer = useCallback(async (containerNumbers, materialName) => {
    const nums = (containerNumbers || []).filter(Boolean);
    if (nums.length === 0 || !locationCode || !materialName) { setBlockedByContainer({}); return; }
    try {
      // Hent alle bestillinger for denne lokation der ikke er fuldført/cancelled,
      // og gruppér efter container_number → liste af tour_types.
      const r = await axios.get(`${API}/container-orders/by-location/${encodeURIComponent(locationCode)}`);
      const arr = Array.isArray(r.data) ? r.data : (r.data?.orders || []);
      const map = {};
      for (const o of arr) {
        const status = (o.status || "").toLowerCase();
        if (status === "completed" || status === "cancelled") continue;
        const cnum = (o.container_number || "").trim();
        const mat = (o.material || "").trim();
        if (!cnum || mat !== materialName) continue;
        if (!nums.includes(cnum)) continue;
        if (!map[cnum]) map[cnum] = [];
        map[cnum].push({ tour_type: o.tour_type || "normal", order_date: o.order_date || "" });
      }
      setBlockedByContainer(map);
    } catch (_) { /* ignore - duplicate check sker også backend-side */ }
  }, [locationCode]);
  const [autoFillData, setAutoFillData] = useState(null);
  const [priority, setPriority] = useState("normal");
  // Fase 9 (2026-06-17): CO2-type valgt af brugeren (linker til kunde's bibliotek)
  const [co2Types, setCo2Types] = useState([]);
  const [selectedCo2TypeId, setSelectedCo2TypeId] = useState("");
  const [tourType, setTourType] = useState("normal"); // normal | flyt (Byt container) | vaerksted | afhent_vaerksted
  // Workshop snapshot for tourType in (vaerksted, afhent_vaerksted). Vælges
  // fra biblioteket (CA-administreret) og kan overskrives med fri tekst.
  const [workshops, setWorkshops] = useState([]);
  const [workshopId, setWorkshopId] = useState("");
  const [workshopName, setWorkshopName] = useState("");
  const [workshopAddress, setWorkshopAddress] = useState("");
  const [workshopPhone, setWorkshopPhone] = useState("");
  const [workshopOverride, setWorkshopOverride] = useState(false);
  const [comment, setComment] = useState("");
  const [openFrom, setOpenFrom] = useState("");
  const [openTo, setOpenTo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [orderSuccess, setOrderSuccess] = useState(null);
  const [materialSearch, setMaterialSearch] = useState("");
  const [showCustomMaterial, setShowCustomMaterial] = useState(false);
  const [customMaterial, setCustomMaterial] = useState("");
  const [editingMaterial, setEditingMaterial] = useState(null);
  const [editMaterialName, setEditMaterialName] = useState("");
  // Fase 9 refactor (2026-06-18): CO2-kategori-state til material-formularerne
  const [newMaterialCo2Id, setNewMaterialCo2Id] = useState("");
  const [editMaterialCo2Id, setEditMaterialCo2Id] = useState("");
  
  // Date selection for order
  const [orderDate, setOrderDate] = useState(() => localDateStr());

  // Leveringsadresse / schedule auto-resolution. The order form auto-
  // populates the delivery address from the PRIMARY address registered
  // for the (location_code, material) tuple, and auto-fills open_from /
  // open_to from the resolved schedule (helligdagskalender takes
  // precedence over the weekday schedule). If the primary address is
  // closed on the chosen date, the user can pick an alternative - see
  // `scheduleInfo.alternatives`. Both IDs are persisted on the order
  // for audit / history.
  const [scheduleInfo, setScheduleInfo] = useState(null); // {primary, alternatives, selected, is_closed, ...}
  // 2026-06-15 brugerkrav: "Alternativ leveringsadresse" og "Vil du udfylde adressen
  // selv?" er PERMANENT FJERNET. Medarbejderen får ALENE "Leveringsadresse
  // (forudfyldt)" som auto-udfyldes fra kalenderen; hvis adressen er lukket på
  // den valgte dato, klikker man "Ændre til anden adresse" og skriver i feltet.
  const [addressEditable, setAddressEditable] = useState(false); // toggled via "Ændre til anden adresse"
  
  // Order history view
  const [view, setView] = useState("order"); // "order" or "history"
  const [orderHistory, setOrderHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyDate, setHistoryDate] = useState(() => localDateStr());
  // Per-order edit / delete / audit-history modals (Batch 2)
  const [editingOrder, setEditingOrder] = useState(null);   // order doc
  const [confirmDeleteOrder, setConfirmDeleteOrder] = useState(null);
  const [auditOrder, setAuditOrder] = useState(null);       // {order, entries}
  // Container "Rediger" base-definition modal (locks for admin, address etc.)
  const [editingContainer, setEditingContainer] = useState(null);
  // Soft-confirm dialogs for create/delete container actions (admin only)
  const [confirmAddContainer, setConfirmAddContainer] = useState(false);
  const [confirmDeleteContainer, setConfirmDeleteContainer] = useState(null);
  // "Tilføj tilpasset bestilling" flag - true when the user clicked the
  // custom-request button on step 2. Step 3 then becomes a fully editable
  // form with NO defaults and ALL three fields required.
  const [isCustomRequest, setIsCustomRequest] = useState(false);
  // Fase 15.16 (2026-02-XX): "Tilpasset bestilling" understøtter to typer:
  //  - "opgave" (default, eksisterende fuld bestillings-flow)
  //  - "estimat" (forventet ressourcebehov: materiale + antal + dato)
  //  - "loes_afhentning" (Fase 15.41 - chauffør medbringer egne tomme containere)
  const [customRequestMode, setCustomRequestMode] = useState("opgave");
  // Fase 15.16 (2026-02-21): brugerinput skal være helt frit - tom-streng
  // som default, brugeren skal indtaste tallet selv. Vi validerer på submit.
  const [estimatedCount, setEstimatedCount] = useState("");
  // Fase 15.41 (2026-02-22): Separat felt fra estimatedCount - skøn over
  // hvor mange tomme containere chaufføren skal medbringe til løs afhentning.
  const [looseEstimatedCount, setLooseEstimatedCount] = useState("");
  // Effective admin mode = prop adminMode (set by LocationAdminPage) for the
  // current order session. Order-users always have it disabled.
  const isAdmin = !!adminMode;

  // Fetch location data + tilknyttede logistik-partnere (per-partner setup
  // brugerkrav 2026-06-15). Materialer filtreres SENERE på `partnerId` for
  // at undgå at vise andre partneres containere til medarbejderen.
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const locRes = await axios.get(`${API}/locations/code/${locationCode}`);
        setLocation(locRes.data);
        // Hent partnere PARALLELT med location-data
        try {
          const pRes = await axios.get(`${API}/locations/${locationCode}/partners`);
          const parts = pRes.data?.partners || [];
          setPartners(parts);
          // Auto-vælg når kun ÉN partner (skjul vælgeren helt for medarbejderen).
          // Brugerkrav 2026-06-15 (runde 2): VED 2+ partnere SKAL der vælges
          // hver gang - ingen sessionStorage-genskabelse længere, så
          // medarbejderen kan bevidst skifte view ved hver navigation.
          if (parts.length === 1) setPartnerId(parts[0].id);
        } catch (_) { setPartners([]); }
        setPartnersLoaded(true);
        // Materialer hentes senere når partnerId er sat (se separat effect nedenfor)
        // Workshops bibliotek (kun synligt for autentificerede bestiller-brugere).
        // 401/403 ignoreres så det offentlige QR-kiosk-flow ikke fejler.
        try {
          const wsRes = await axios.get(`${API}/org/workshops`);
          setWorkshops(wsRes.data || []);
        } catch (_) { /* ikke autoriseret eller endnu ikke konfigureret */ }
        // Fase 9 (2026-06-17): Hent kundens CO2-bibliotek så det kan vises som
        // dropdown i bestillings-flowet. Stille fejl-håndtering - hvis kunde
        // ikke har oprettet typer endnu, viser vi blot ingen dropdown.
        try {
          const co2Res = await axios.get(`${API}/co2-types`);
          setCo2Types((co2Res.data || []).filter(t => t.active !== false));
        } catch (_) { /* CA har ikke oprettet typer eller bruger er ikke logged in */ }
      } catch (e) {
        setError("Kunne ikke finde lokationen. Tjek din kode.");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [locationCode]);

  // Hent listen af pladser brugeren har adgang til.
  // - Order-medarbejder: `/api/plads` (server filtrerer på assigned_plads_ids).
  // - Location admin (adminMode): `/api/org/locations` (deres managed pladser).
  // Bruges til "Lokation"-switcheren ved siden af partner-vælgeren.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const url = adminMode ? `${API}/org/locations` : `${API}/plads`;
        const { data } = await axios.get(url);
        if (cancelled) return;
        const list = Array.isArray(data) ? data : [];
        const normalized = list
          .map(p => ({
            code: p.effective_location_code || p.location_code,
            name: p.name || "",
            city: p.city || "",
            address: p.address || "",
          }))
          .filter(p => p.code)
          .sort((a, b) => (a.city || a.name).localeCompare(b.city || b.name, "da"));
        setAvailablePladser(normalized);
      } catch (_) {
        if (!cancelled) setAvailablePladser([]);
      }
    })();
    return () => { cancelled = true; };
  }, [locationCode, adminMode]);

  // Når partner skifter (eller første gang sat), hent materialer filtreret
  // på partner_id. Når ingen partnere findes overhovedet (legacy plads), vis
  // standard-materialerne fra location-objektet.
  //
  // Brugerkrav 2026-06-15 (Krav 5 strict separation, fix runde 2):
  //   Når partner_id er sat hentes materialer KUN fra
  //   `plads.partner_materials[partner_id]`. Vi falder IKKE længere tilbage
  //   til legacy `location.materials` - det fik tidligere materialer fra én
  //   partner til at lække ind til en anden partners view. En partner uden
  //   materialer skal vise en TOM liste så LA kan tilføje fra bunden.
  useEffect(() => {
    if (!partnersLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        if (partners.length === 0) {
          // Legacy: ingen partnere knyttet → standard-materialer fra plads
          const mats = location?.materials?.length > 0 ? location.materials : [];
          if (mats.length === 0) {
            const matRes = await axios.get(`${API}/materials`);
            if (!cancelled) setMaterials(matRes.data?.materials || []);
          } else if (!cancelled) {
            setMaterials(mats);
          }
          return;
        }
        if (!partnerId) {
          // Vi er på partner-picker-skærmen; ryd materialer indtil et valg er foretaget
          if (!cancelled) setMaterials([]);
          return;
        }
        // Strict per-partner kilde: containers-endpointet returnerer netop
        // `partner_materials[partner_id]` når partner_id er sat (jf.
        // server.py get_location_containers). Hvis listen er tom, ER den
        // tom for denne partner - vi falder IKKE tilbage til legacy.
        const r = await axios.get(
          `${API}/locations/${locationCode}/containers?partner_id=${encodeURIComponent(partnerId)}`
        );
        if (cancelled) return;
        const partnerMats = (r.data?.materials || []).map(m => m.material);
        setMaterials(partnerMats);
      } catch (e) {
        if (!cancelled) setMaterials([]);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partnerId, partnersLoaded, locationCode, partners.length]);

  // Fase 9 refactor (2026-06-18): Hent CO2-kategori-mapping fra pladsen så
  // vi kan vise chips på materialerne og pre-udfylde "Rediger materiale".
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/locations/${locationCode}/materials`);
        if (!cancelled) setMaterialCo2Map(r.data?.material_co2_categories || {});
      } catch (_) { if (!cancelled) setMaterialCo2Map({}); }
    })();
    return () => { cancelled = true; };
  }, [locationCode, materials]);

  // Pr. 2026-06-15 (runde 2): Vi PERSISTERER IKKE partner-valg længere.
  // Brugeren skal aktivt vælge partner hver gang siden indlæses, så de bevidst
  // kan skifte view ved hver navigation. (Tidligere sessionStorage-cache er
  // fjernet - partneren leve kun i komponent-state.)

  // -------- Schedule resolution --------
  // Public endpoint that returns: {primary, alternatives, selected,
  // is_closed, is_holiday, holiday_name, open_from, open_to, source}.
  // We call it whenever the (material, date) tuple changes so the order
  // form stays in sync. Alternativ-adresse-vælgeren er FJERNET pr.
  // 2026-06-15 - vi bruger udelukkende primær-adressen og lader brugeren
  // skrive frit i adresse-feltet hvis det er lukket.
  const resolveSchedule = useCallback(async (material, date) => {
    if (!material || !date) return null;
    try {
      const params = new URLSearchParams({ location_code: locationCode, material, date });
      const r = await axios.get(`${API}/delivery-addresses/resolve?${params.toString()}`);
      return r.data;
    } catch (e) {
      // Endpoint can 404 when plads has no company_id mapping - silently ignore;
      // the order form keeps its manual inputs in that case.
      return null;
    }
  }, [locationCode]);

  // Re-resolve whenever material or date changes
  useEffect(() => {
    if (!selectedMaterial || !orderDate || step < 3) return;
    let cancelled = false;
    (async () => {
      const data = await resolveSchedule(selectedMaterial, orderDate);
      if (cancelled || !data) return;
      setScheduleInfo(data);
      // Auto-populate åbner/lukker UANSET om feltet er read-only (brugerkrav 2026-06-15).
      // Hvis containeren har sine egne låste timer (gemt i autoFillData), beholdes de;
      // ellers udfyldes fra kalenderen så feltet aldrig står tomt.
      const containerFrom = (autoFillData?.containerOpenFrom || "").trim();
      const containerTo   = (autoFillData?.containerOpenTo   || "").trim();
      setOpenFrom(containerFrom || data.open_from || "");
      setOpenTo(containerTo || data.open_to || "");
      // Auto-populate adresse: hvis brugeren IKKE selv har slået redigering til
      // og containeren ikke har sin egen låste adresse, brug kalenderens
      // resolved adresse (`resolved_delivery_address` = den adresse som kalender-
      // fallback-kæden valgte for denne dato). Hvis ingen resolved adresse,
      // falder vi tilbage til `data.selected` (hvis sat), og som sidste udvej
      // bruger vi første adresse fra biblioteket (alternatives[0]) eller
      // den default-adresse container havde.
      if (!addressEditable) {
        const containerAddr = (autoFillData?.containerAddress || "").trim();
        if (containerAddr) {
          setAutoFillData(prev => prev ? { ...prev, address: containerAddr } : prev);
        } else {
          const addrSource = data.resolved_delivery_address
            || data.selected
            || (Array.isArray(data.alternatives) && data.alternatives.length > 0 ? data.alternatives[0] : null);
          if (addrSource) {
            const line = [addrSource.street, [addrSource.postcode, addrSource.city].filter(Boolean).join(" ")]
              .filter(Boolean).join(", ");
            if (line) {
              setAutoFillData(prev => prev ? { ...prev, address: line } : prev);
            }
          }
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMaterial, orderDate, step]);

  // Fetch containers when material is selected
  const handleMaterialSelect = async (material) => {
    setSelectedMaterial(material);
    try {
      const partnerQuery = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
      const res = await axios.get(`${API}/locations/${locationCode}/containers?material=${encodeURIComponent(material)}${partnerQuery}`);
      const items = res.data.containers || [];
      setContainers(items);
      setStep(2);
      // Fase 15.16: Pre-fetch hvilke containere allerede har aktive bestillinger
      // (matchet på container_number + material - kilden er container_orders).
      refreshBlockedByContainer(items.map(c => (c.label || c.number || "").trim()), material);
    } catch (e) {
      toast.error("Kunne ikke hente containere");
    }
  };

  // Select container → auto-fill
  const handleContainerSelect = (container) => {
    setIsCustomRequest(false);
    setCustomRequestMode("opgave");
    setEstimatedCount("");
    setSelectedContainer(container);
    setAddressEditable(false);
    setAutoFillData({
      address: prefillAddress || (container.has_override ? (container.address || "") : (container.address || "")),
      city: container.city,
      genbrugsplads: container.genbrugsplads,
      material: container.material,
      container: container.label,
      // Pre-fill order-time container_id with default so the read-only
      // field shows the saved number (employees don't edit it). For custom
      // orders we override this in the dedicated branch.
      containerId: container.container_id || "",
      defaultContainerId: container.container_id || "",
      hasOverride: container.has_override || false,
      defaultAddress: container.default_address || "",
      lockedAddress: !!container.locked_address,
      lockedHours: !!container.locked_hours,
      lockedContainerId: !!container.locked_container_id,
      // Gem containerens egne åbnings-/lukketider + låste adresse separat så
      // auto-populate fra kalenderen kan falde tilbage hertil hvis sat,
      // og bruge kalenderen som backup når container har låst men tomt felt.
      containerOpenFrom: container.open_from || "",
      containerOpenTo: container.open_to || "",
      containerAddress: (container.locked_address && container.address) ? container.address : "",
      // Kapacitetsmål - auto-popuates ind på "Bekræft og rediger" og videre i
      // ordreopsummeringen + success popup (Batch 2 follow-up).
      capacityMeasureId: container.capacity_measure_id || "",
      capacityLabel: container.capacity_label || "",
      capacityVolumeM3: container.capacity_volume_m3 ?? null,
    });
    if (container.open_from) setOpenFrom(container.open_from);
    if (container.open_to) setOpenTo(container.open_to);
    setStep(3);
  };

  // Submit order
  const handleSubmitOrder = async () => {
    // For "Byt container" / "Til værksted" / "Afhent fra værksted" er leverings-
    // adressen helt fjernet fra UI'et - vi springer derfor adresse-validering
    // over for disse flows.
    const isWorkshopFlow = tourType === "vaerksted" || tourType === "afhent_vaerksted";
    const isMoveFlow = tourType === "flyt";
    const isAddressFlow = !isWorkshopFlow && !isMoveFlow;
    // Leveringsadresse er OBLIGATORISK når en medarbejder opretter en
    // almindelig afhentnings-bestilling. Pr. 2026-06-15 har vi kun ÉN
    // adresse-input (forudfyldt fra kalenderen, redigerbar via "Ændre til
    // anden adresse"). Ingen alternativ-vælger længere.
    const delivery = (autoFillData?.address || "").trim();
    if (isAddressFlow) {
      if (!delivery) {
        toast.error("Leveringsadresse er påkrævet - udfyld den i trin 3");
        setStep(3);
        return;
      }
    }
    if (isWorkshopFlow) {
      if (!workshopName.trim() || !workshopAddress.trim()) {
        toast.error("Værksted er påkrævet (navn + adresse)");
        setStep(3);
        return;
      }
    }
    setSubmitting(true);
    try {
      const primaryId = isAddressFlow ? (scheduleInfo?.primary?.id || "") : "";
      const res = await axios.post(`${API}/customer-orders/submit`, {
        location_code: locationCode,
        material: selectedMaterial,
        co2_type_id: "",
        container_number: selectedContainer.label,
        priority: priority,
        tour_type: tourType,
        comment: comment,
        custom_address: isAddressFlow ? delivery : "",
        custom_container_id: autoFillData.containerId || "",
        order_date: orderDate,
        open_from: isAddressFlow ? (openFrom || "") : "",
        open_to: isAddressFlow ? (openTo || "") : "",
        plads_name: pladsName || "",
        delivery_address_id: primaryId,
        // Workshop snapshot (Batch 2) - kun relevant for vaerksted/afhent_vaerksted
        workshop_id: isWorkshopFlow ? workshopId : "",
        workshop_name: isWorkshopFlow ? workshopName.trim() : "",
        workshop_address: isWorkshopFlow ? workshopAddress.trim() : "",
        workshop_phone: isWorkshopFlow ? workshopPhone.trim() : "",
        workshop_override: isWorkshopFlow ? workshopOverride : false,
        // Pr. 2026-06-15 brugerkrav: snapshot af valgt logistik-partner.
        // Bagudkompatibel: hvis lokationen ikke har partnere er feltet "".
        partner_id: partnerId || "",
      });
      setOrderSuccess(res.data);
      setStep(5);
      toast.success("Bestilling oprettet!");
    } catch (e) {
      const msg = e?.response?.data?.detail || "Kunne ikke oprette bestilling";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Reset flow
  const resetOrder = () => {
    setStep(1);
    setSelectedMaterial("");
    setSelectedCo2TypeId("");
    setContainers([]);
    setSelectedContainer(null);
    setAutoFillData(null);
    setPriority("normal");
    setTourType("normal");
    setComment("");
    setOpenFrom("");
    setOpenTo("");
    setOrderSuccess(null);
    setShowCustomMaterial(false);
    setCustomMaterial("");
    setEditingMaterial(null);
    setEditMaterialName("");
    setScheduleInfo(null);
    setWorkshopId("");
    setWorkshopName("");
    setWorkshopAddress("");
    setWorkshopPhone("");
    setWorkshopOverride(false);
    setAddressEditable(false);
  };

  // Add material to this location's list permanently.
  // Brugerkrav 2026-06-15 (Krav 5 strict separation): Når en partner er valgt,
  // sendes `partner_id` med så materialet KUN registreres under den partners
  // liste (`plads.partner_materials[partner_id]`). Ellers ender det i
  // legacy/globale `materials`-liste - som tidligere.
  const handleAddMaterial = async (name) => {
    try {
      const body = { material: name };
      if (partnerId) body.partner_id = partnerId;
      if (newMaterialCo2Id) body.co2_category_id = newMaterialCo2Id;
      const res = await axios.post(`${API}/locations/${locationCode}/materials`, body);
      setMaterials(res.data.materials);
      // Opdater CO2-mapping lokalt så chips opdateres med det samme
      if (newMaterialCo2Id) {
        setMaterialCo2Map(prev => ({ ...prev, [name]: newMaterialCo2Id }));
      }
      setShowCustomMaterial(false);
      setCustomMaterial("");
      setNewMaterialCo2Id("");
      toast.success(`"${name}" tilføjet til materialer`);
    } catch (e) {
      if (e.response?.status === 400) toast.error(e.response?.data?.detail || "Materialet findes allerede");
      else toast.error("Kunne ikke tilføje materiale");
    }
  };

  // Edit material name + CO2-kategori - partner-scoped når en partner er valgt.
  const handleEditMaterial = async (oldName, newName) => {
    const trimmed = (newName || "").trim();
    const renameWanted = trimmed && trimmed !== oldName;
    const currentCo2 = materialCo2Map[oldName] || "";
    const co2Changed = editMaterialCo2Id !== currentCo2;
    if (!renameWanted && !co2Changed) {
      setEditingMaterial(null);
      return;
    }
    try {
      const body = {
        old_name: oldName,
        new_name: renameWanted ? trimmed : oldName,
        co2_category_id: editMaterialCo2Id,
      };
      if (partnerId) body.partner_id = partnerId;
      const res = await axios.put(`${API}/locations/${locationCode}/materials`, body);
      setMaterials(res.data.materials);
      // Opdater lokal CO2-mapping
      setMaterialCo2Map(prev => {
        const next = { ...prev };
        if (renameWanted) delete next[oldName];
        const newKey = renameWanted ? trimmed : oldName;
        if (editMaterialCo2Id) next[newKey] = editMaterialCo2Id;
        else delete next[newKey];
        return next;
      });
      setEditingMaterial(null);
      setEditMaterialName("");
      setEditMaterialCo2Id("");
      toast.success(renameWanted ? `Omdøbt til "${trimmed}"` : "Materiale opdateret");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kunne ikke opdatere materiale");
    }
  };

  // Delete material - uses local state-based confirm modal (no more
  // missing window/global showConfirm). Triggered through SoftConfirmModal.
  // Brugerkrav 2026-06-15 (Krav 5): Send `partner_id` med så slet er strengt
  // begrænset til den valgte partners liste - andre partnere er urørte.
  const [confirmDeleteMaterialName, setConfirmDeleteMaterialName] = useState(null);
  const handleDeleteMaterial = (materialName) => {
    setConfirmDeleteMaterialName(materialName);
  };
  const performDeleteMaterial = async () => {
    const materialName = confirmDeleteMaterialName;
    setConfirmDeleteMaterialName(null);
    if (!materialName) return;
    try {
      const partnerQ = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
      const res = await axios.delete(
        `${API}/locations/${locationCode}/materials?material=${encodeURIComponent(materialName)}${partnerQ}`
      );
      setMaterials(res.data.materials);
      setMaterialCo2Map(prev => {
        const next = { ...prev };
        delete next[materialName];
        return next;
      });
      toast.success(`"${materialName}" slettet`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kunne ikke slette materiale");
    }
  };

  // Order-history scope (Mine bestillinger vs Alle bestillinger på denne lokation).
  // Default = mine, the user can opt-in to see colleagues' orders.
  const [historyScope] = useState("all"); // Fase 18.33: scope toggle fjernet - viser altid alle bestillinger på lokationen.
  // Fase 18.24 (2026-02-28): List-view med inline-expand for bestillingshistorik.
  // Klik på en række toggler udvidet visning med alle detaljer + actions.
  const [expandedHistoryId, setExpandedHistoryId] = useState(null);
  // Fase 15.20 (2026-02-21): Estimater er skjult som default på "Mine
  // bestillinger" og "Alle bestillinger (denne lokation)". Slås toggle TIL
  // vises estimater nederst i listen (efter alle almindelige bestillinger),
  // uafhængigt af resten af sorteringsorden.
  const [includeEstimates, setIncludeEstimates] = useState(false);
  // Date range mode (brugerkrav 2026-06-14/15):
  //   "day"     - viser kun bestillinger for den valgte dato (default)
  //   "all"     - viser ALLE bestillinger uafhængigt af dato
  // BEMÆRK (2026-06-15): "Pr. dato" viser ALLE statuser. "Alle bestillinger"
  // skjuler som standard fuldførte. "Skjul afhentede stillinger"-toggle
  // virker uafhængigt i begge modes og persisteres i localStorage.
  // "Filtrér på afventende" virker også uafhængigt af mode og inkluderer
  // både "afventer" og "på vej" som "afventende".
  const [historyMode, setHistoryMode] = useState("day"); // "day" | "all"
  const [pendingOnly, setPendingOnly] = useState(false);
  // Fase 18.28: Pull-to-refresh state (kun mobil) - tracker hvor langt brugeren
  // har trukket ned fra toppen så vi kan vise spinner + trigger genindlæsning.
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const pullStartY = useRef(0);
  const PULL_THRESHOLD = 70; // px før refresh trigger
  const [hideCompleted, setHideCompleted] = useState(() => {
    try { return localStorage.getItem("cf:hideCompletedOrders") === "1"; }
    catch (_) { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("cf:hideCompletedOrders", hideCompleted ? "1" : "0"); }
    catch (_) { /* ignore quota / private mode */ }
  }, [hideCompleted]);
  const { user: authUserCtx } = useAuth();

  // Fetch order history for this location
  // Brugerkrav 2026-06-15 (runde 6): Strict per-partner isolation - sender
  // `partner_id` med så samme lokation med flere partnere ikke deler historik.
  const fetchOrderHistory = async (date, mode = historyMode) => {
    setHistoryLoading(true);
    try {
      // Backend supports `?all=1` to skip the date filter entirely.
      // `include_cancelled=true` ensures the server doesn't pre-filter
      // completed/cancelled orders away - UI does the final filtering.
      const partnerQ = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
      const url = mode === "all"
        ? `${API}/container-orders/by-location/${locationCode}?all=1&include_cancelled=true${partnerQ}`
        : `${API}/container-orders/by-location/${locationCode}?date=${date}&include_cancelled=true${partnerQ}`;
      const res = await axios.get(url);
      setOrderHistory(res.data || []);
    } catch (e) {
      console.error("Error fetching order history:", e);
      setOrderHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Load history when switching to history view or changing date/mode/partner
  useEffect(() => {
    if (view === "history") fetchOrderHistory(historyDate, historyMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, historyDate, historyMode, partnerId]);

  // Filtered + SORTED history. Filters virker uafhængigt og kombineres frit.
  // Sortering (brugerkrav 2026-06-15):
  //   1) Afventer (intet claim, ikke på vej, ikke fuldført)
  //   2) På vej / Taget (claimed_by ELLER on_way)
  //   3) Fuldført - altid nederst
  // "Filtrér på afventende" reducerer til (!completed) - dvs. både afventer
  // og på vej. "Skjul afhentede stillinger" fjerner fuldførte. I "Alle
  // bestillinger"-mode skjules fuldførte ALTID som standard (uafhængigt af
  // togglen). Multi-tenant isolation håndteres server-side.
  const visibleHistory = useMemo(() => {
    let list = orderHistory;
    if (historyScope !== "all") {
      const me = authUserCtx?.id;
      const myEmail = (authUserCtx?.email || "").toLowerCase();
      list = list.filter(o =>
        (me && o.created_by_user_id === me) ||
        (myEmail && (o.created_by_email || "").toLowerCase() === myEmail) ||
        (!o.created_by_user_id && !o.created_by_email)
      );
    }
    // "Afventende" = ikke fuldført (dvs. afventer + på vej + taget).
    if (pendingOnly) {
      list = list.filter(o => !o.completed);
    }
    // Skjul fuldførte: enten via eksplicit toggle ELLER fordi vi er i
    // "Alle bestillinger"-mode (mode-default ifølge brugerkrav).
    const effectiveHide = hideCompleted || historyMode === "all";
    if (effectiveHide) {
      list = list.filter(o => !o.completed);
    }
    // Fase 15.20 (2026-02-21): Estimater filtreres fra som default; når
    // toggle er ON inkluderes de men placeres nederst i listen (efter
    // sortering af de almindelige bestillinger).
    const estimates = list.filter(o => (o.tour_type || "") === "estimat");
    let nonEstimates = list.filter(o => (o.tour_type || "") !== "estimat");
    // Sortér de almindelige: afventer → på vej → fuldført; nyeste først indenfor gruppen.
    const rank = (o) => o.completed ? 3 : ((o.on_way || o.claimed_by) ? 2 : 1);
    nonEstimates = [...nonEstimates].sort((a, b) => {
      const r = rank(a) - rank(b);
      if (r !== 0) return r;
      return (b.created_at || "").localeCompare(a.created_at || "");
    });
    if (!includeEstimates) return nonEstimates;
    // Estimater sorteres internt på order_date (nyeste først).
    const sortedEstimates = [...estimates].sort((a, b) =>
      (b.order_date || "").localeCompare(a.order_date || "")
    );
    return [...nonEstimates, ...sortedEstimates];
  }, [orderHistory, historyScope, historyMode, pendingOnly, hideCompleted, authUserCtx, includeEstimates]);

  // Navigate history dates
  const changeHistoryDate = (days) => {
    const d = new Date(historyDate);
    d.setDate(d.getDate() + days);
    setHistoryDate(localDateStr(d));
  };

  const filteredMaterials = materialSearch
    ? materials.filter(m => m.toLowerCase().includes(materialSearch.toLowerCase()))
    : materials;

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-lg text-slate-300">Indlæser...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 mx-auto mb-4 text-red-500" />
          <h2 className="text-xl font-bold text-slate-800 mb-2">Fejl</h2>
          <p className="text-slate-600 mb-6">{error}</p>
          <button onClick={onBack} className="px-6 py-3 bg-orange-500 text-white rounded-xl font-bold hover:bg-orange-600" data-testid="error-back-btn">
            Prøv igen
          </button>
        </div>
      </div>
    );
  }

  // Per-partner picker (brugerkrav 2026-06-15): Når lokationen har 2+
  // logistik-partnere SKAL medarbejderen vælge én før bestillingen kan starte.
  // Når kun én partner findes (eller ingen - legacy plads), springes skærmen
  // over og partnerId er allerede sat. Skærmen viser også et fald-tilbage-link
  // hvis medarbejderen er i tvivl.
  if (partnersLoaded && partners.length >= 2 && !partnerId) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" data-testid="partner-picker-screen">
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 max-w-md w-full">
          <div className="w-14 h-14 bg-orange-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <Truck className="w-7 h-7 text-orange-400" />
          </div>
          <h2 className="text-xl font-black text-white text-center mb-1">Vælg logistik-partner</h2>
          <p className="text-slate-400 text-center text-sm mb-6">Hvem skal udføre afhentningen?</p>
          <div className="space-y-2">
            {partners.map(p => (
              <button key={p.id} onClick={() => setPartnerId(p.id)}
                className="w-full px-4 py-3 bg-slate-900 hover:bg-slate-700 border border-slate-600 hover:border-orange-500 rounded-xl text-left transition-colors flex items-center justify-between"
                data-testid={`partner-pick-${p.id}`}>
                <span className="text-white font-bold">{p.name}</span>
                <ChevronRight className="w-4 h-4 text-slate-400" />
              </button>
            ))}
          </div>
          {onBack && (
            <button onClick={onBack}
              className="mt-6 w-full text-center text-sm text-slate-400 hover:text-white"
              data-testid="partner-picker-back">
              ← Tilbage
            </button>
          )}
        </div>
      </div>
    );
  }

  // SUCCESS SCREEN
  if (step === 5 && orderSuccess) {
    const tt = orderSuccess.tour_type || "normal";
    const isWorkshop = tt === "vaerksted" || tt === "afhent_vaerksted";
    const isMove = tt === "flyt";
    const tourLabel = tt === "flyt" ? "Byt container"
      : tt === "vaerksted" ? "Til værksted"
      : tt === "afhent_vaerksted" ? "Afhent fra værksted"
      : "Afhentning";
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-lg w-full text-center" data-testid="order-success">
          <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="w-12 h-12 text-emerald-600" />
          </div>
          <h2 className="text-2xl font-black text-slate-900 mb-2">Bestilling modtaget!</h2>
          <p className="text-slate-500 mb-6">Din afhentning er registreret og sendt til chauffører.</p>
          
          <div className="bg-slate-50 rounded-xl p-4 mb-6 text-left space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-slate-500">Opgavetype</span>
              <span className="text-sm font-bold text-emerald-700">{tourLabel}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-slate-500">Materiale</span>
              <span className="text-sm font-bold">{orderSuccess.material}</span>
            </div>
            {orderSuccess.container_id && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-500">Container-nummer</span>
                <span className="text-sm font-bold">{orderSuccess.container_id}</span>
              </div>
            )}
            {(orderSuccess.capacity_label || orderSuccess.capacity_volume_m3 != null) && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-500">Kapacitetsmål</span>
                <span className="text-sm font-bold">{formatCapacity(orderSuccess)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-sm text-slate-500">Genbrugsplads</span>
              <span className="text-sm font-bold">{orderSuccess.genbrugsplads}</span>
            </div>
            {/* Adresse-rækken vises kun for normal afhentning. For "Byt container"
                er der ingen adresse. For værksted-flows vises i stedet værkstedets
                navn + adresse + telefon. */}
            {!isMove && !isWorkshop && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-500">Adresse</span>
                <span className="text-sm font-bold">{orderSuccess.address}</span>
              </div>
            )}
            {isWorkshop && orderSuccess.workshop_name && (
              <>
                <div className="flex justify-between">
                  <span className="text-sm text-slate-500">Værksted</span>
                  <span className="text-sm font-bold">{orderSuccess.workshop_name}</span>
                </div>
                {orderSuccess.workshop_address && (
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-500">Værksted-adresse</span>
                    <span className="text-sm font-bold">{orderSuccess.workshop_address}</span>
                  </div>
                )}
                {orderSuccess.workshop_phone && (
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-500">Værksted-telefon</span>
                    <span className="text-sm font-bold">{orderSuccess.workshop_phone}</span>
                  </div>
                )}
              </>
            )}
            <div className="flex justify-between">
              <span className="text-sm text-slate-500">Prioritet</span>
              <span className={`text-sm font-bold uppercase ${orderSuccess.priority === "haster" ? "text-red-600" : orderSuccess.priority === "senere" ? "text-blue-600" : "text-slate-700"}`}>
                {orderSuccess.priority}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-slate-500">Dato</span>
              <span className="text-sm font-bold">{orderSuccess.order_date ? new Date(orderSuccess.order_date + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" }) : "-"}</span>
            </div>
          </div>
          
          <div className="space-y-3">
            <button onClick={resetOrder} className="w-full py-3 bg-orange-500 text-white rounded-xl font-bold hover:bg-orange-600" data-testid="new-order-btn">
              Opret ny bestilling
            </button>
            <button
              onClick={() => (onLogout || onBack)()}
              className="w-full py-3 bg-slate-900 text-white rounded-xl font-medium hover:bg-slate-800"
              data-testid="success-logout-btn"
            >
              Log ud
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 overscroll-y-contain">
      {/* Header - Fase 18.40: sticky top med backdrop-blur + safe-area for
          iOS notch. Giver klassisk iOS/moderne app-følelse når indhold scroller
          under headeren. */}
      <header className="sticky top-0 z-30 bg-slate-800/95 backdrop-blur-md supports-[backdrop-filter]:bg-slate-800/80 border-b border-slate-700 py-3 sm:py-4 px-3 sm:px-4 shadow-lg" style={{ paddingTop: 'calc(env(safe-area-inset-top, 0px) + 0.75rem)' }}>
        <div className="max-w-screen-2xl mx-auto flex items-center justify-between">
          <button onClick={step > 1 && view === "order" ? () => setStep(step - 1) : onBack} className="p-2 hover:bg-slate-700 rounded-lg text-white" data-testid="order-back-btn">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <div className="text-center flex-1 min-w-0 px-2">
            <div className="flex items-center justify-center gap-2">
              <Truck className="w-4 h-4 sm:w-5 sm:h-5 text-orange-500 shrink-0" />
              <h1 className="font-black text-base sm:text-lg text-white">Container<span className="text-orange-500">Flow</span></h1>
            </div>
            <p className="text-slate-400 text-xs sm:text-sm truncate leading-tight">{location?.name}</p>
            {/* Fase 18.39: partner-navn på separat linje (cyan matcher partner-ikonet).
                Vises kun når en partner er valgt. Truncate på lang tekst. */}
            {partnerId && (() => {
              const activePartner = partners.find(p => p.id === partnerId);
              return activePartner?.name ? (
                <p className="text-cyan-400 text-[10px] sm:text-[11px] truncate leading-tight mt-0.5" data-testid="header-partner-name">
                  <Truck className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                  {activePartner.name}
                </p>
              ) : null;
            })()}
            {userName && (
              <p className="hidden sm:block text-emerald-400 text-[11px] uppercase tracking-wider" data-testid="order-user-name">
                Logget ind som {userName}
              </p>
            )}
          </div>
          {onLogout ? (
            <div className="flex items-center gap-1 shrink-0">
              {/* Fase 18.37: Mobil location-switcher ikon (kun når 2+ pladser).
                  Åbner en lille popover med lokations-listen. */}
              {availablePladser.length >= 2 && onSwitchLocation && (
                <div className="sm:hidden relative">
                  <button
                    onClick={() => setMobileLocMenuOpen(v => !v)}
                    className="p-2 hover:bg-slate-700 rounded-lg text-orange-400"
                    title="Skift lokation"
                    data-testid="mobile-location-menu-btn"
                    aria-haspopup="menu"
                    aria-expanded={mobileLocMenuOpen}
                  >
                    <MapPin className="w-5 h-5" />
                  </button>
                  {mobileLocMenuOpen && (
                    <>
                      {/* Backdrop for at lukke ved klik udenfor */}
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setMobileLocMenuOpen(false)}
                      />
                      <div
                        className="absolute right-0 top-full mt-1 z-50 min-w-[220px] max-w-[280px] bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden"
                        role="menu"
                        data-testid="mobile-location-menu"
                      >
                        <div className="px-3 py-2 border-b border-slate-700 bg-slate-800/60">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-orange-400">Skift lokation</p>
                        </div>
                        <div className="max-h-[60vh] overflow-y-auto py-1">
                          {availablePladser.map(p => (
                            <button
                              key={p.code}
                              onClick={() => {
                                if (p.code === locationCode) { setMobileLocMenuOpen(false); return; }
                                // Reset state så data IKKE blandes mellem lokationer
                                setSelectedMaterial("");
                                setSelectedContainer(null);
                                setContainers([]);
                                setAutoFillData(null);
                                setOrderSuccess(null);
                                setScheduleInfo(null);
                                setAddressEditable(false);
                                setWorkshopId("");
                                setWorkshopName("");
                                setWorkshopAddress("");
                                setWorkshopPhone("");
                                setWorkshopOverride(false);
                                setComment("");
                                setOpenFrom("");
                                setOpenTo("");
                                setPartnerId("");
                                setPartners([]);
                                setPartnersLoaded(false);
                                setStep(1);
                                setView("order");
                                setMobileLocMenuOpen(false);
                                onSwitchLocation(p.code, p.name);
                                toast.info(`Skiftede til ${p.name || p.code}`);
                              }}
                              className={`w-full flex items-center gap-2 px-3 py-2.5 text-left text-sm transition-colors ${p.code === locationCode ? "bg-orange-500/15 text-orange-300" : "text-slate-300 hover:bg-slate-800"}`}
                              data-testid={`mobile-location-item-${p.code}`}
                              role="menuitem"
                            >
                              <MapPin className={`w-3.5 h-3.5 shrink-0 ${p.code === locationCode ? "text-orange-400" : "text-slate-500"}`} />
                              <span className="truncate flex-1 min-w-0">
                                {p.name || p.code}
                                {p.city && <span className="text-slate-500 text-xs"> · {p.city}</span>}
                              </span>
                              {p.code === locationCode && <Check className="w-3.5 h-3.5 text-orange-400 shrink-0" />}
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
              {/* Fase 18.38: Mobil partner-switcher ikon (kun når 2+ partnere).
                  Cyan-farvet Truck-ikon så det er tydeligt at skelne fra
                  location-ikonet (orange MapPin). */}
              {partners.length >= 2 && partnerId && (
                <div className="sm:hidden relative">
                  <button
                    onClick={() => setMobilePartnerMenuOpen(v => !v)}
                    className="p-2 hover:bg-slate-700 rounded-lg text-cyan-400"
                    title="Skift logistik-partner"
                    data-testid="mobile-partner-menu-btn"
                    aria-haspopup="menu"
                    aria-expanded={mobilePartnerMenuOpen}
                  >
                    <Truck className="w-5 h-5" />
                  </button>
                  {mobilePartnerMenuOpen && (
                    <>
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setMobilePartnerMenuOpen(false)}
                      />
                      <div
                        className="absolute right-0 top-full mt-1 z-50 min-w-[220px] max-w-[280px] bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden"
                        role="menu"
                        data-testid="mobile-partner-menu"
                      >
                        <div className="px-3 py-2 border-b border-slate-700 bg-slate-800/60">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-400">Skift logistik-partner</p>
                        </div>
                        <div className="max-h-[60vh] overflow-y-auto py-1">
                          {partners.map(p => (
                            <button
                              key={p.id}
                              onClick={() => {
                                if (p.id === partnerId) { setMobilePartnerMenuOpen(false); return; }
                                setPartnerId(p.id);
                                setSelectedMaterial("");
                                setSelectedContainer(null);
                                setContainers([]);
                                setAutoFillData(null);
                                setOrderSuccess(null);
                                setScheduleInfo(null);
                                setAddressEditable(false);
                                setWorkshopId("");
                                setWorkshopName("");
                                setWorkshopAddress("");
                                setWorkshopPhone("");
                                setWorkshopOverride(false);
                                setComment("");
                                setOpenFrom("");
                                setOpenTo("");
                                setStep(1);
                                setView("order");
                                setMobilePartnerMenuOpen(false);
                                toast.info("Skiftede til ny logistik-partner - start forfra");
                              }}
                              className={`w-full flex items-center gap-2 px-3 py-2.5 text-left text-sm transition-colors ${p.id === partnerId ? "bg-cyan-500/15 text-cyan-300" : "text-slate-300 hover:bg-slate-800"}`}
                              data-testid={`mobile-partner-item-${p.id}`}
                              role="menuitem"
                            >
                              <Truck className={`w-3.5 h-3.5 shrink-0 ${p.id === partnerId ? "text-cyan-400" : "text-slate-500"}`} />
                              <span className="truncate flex-1 min-w-0">{p.name}</span>
                              {p.id === partnerId && <Check className="w-3.5 h-3.5 text-cyan-400 shrink-0" />}
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
              <button onClick={() => onLogout()} className="p-2 hover:bg-slate-700 rounded-lg text-white" title="Log ud" data-testid="header-logout-btn">
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <div className="w-10" />
          )}
        </div>
        {/* Tab switcher: Order / History - Fase 18.23: elegant mellem-størrelse,
            side om side i en samlet "segmented control"-pille.
            Fase 18.24 (2026-02-XX): "+ Tilføj nyt materiale" placeret på samme
            række (kun synlig for admin på materiale-trin), så det ikke
            forveksles med et rigtigt materialekort.
            Fase 18.27 (mobil-redesign): På mobil fylder tab-pillerne fuld bredde,
            og den grønne knap rykker ned på egen række. */}
        <div className="max-w-screen-2xl mx-auto mt-3 flex flex-wrap items-center justify-between gap-2 sm:gap-3">
          <div className="inline-flex w-full sm:w-auto bg-slate-800/80 backdrop-blur p-1 rounded-xl border border-slate-700/50 shadow-sm" data-testid="order-tab-switcher">
            <button onClick={() => setView("order")}
              className={`flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-3 sm:px-5 py-2 rounded-lg text-xs sm:text-sm font-bold transition-all ${
                view === "order"
                  ? "bg-orange-500 text-white shadow-md shadow-orange-500/30"
                  : "text-slate-300 hover:text-white hover:bg-slate-700/50"
              }`}
              data-testid="tab-new-order">
              <Plus className="w-4 h-4" /> Ny bestilling
            </button>
            <button onClick={() => setView("history")}
              className={`flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-3 sm:px-5 py-2 rounded-lg text-xs sm:text-sm font-bold transition-all ${
                view === "history"
                  ? "bg-orange-500 text-white shadow-md shadow-orange-500/30"
                  : "text-slate-300 hover:text-white hover:bg-slate-700/50"
              }`}
              data-testid="tab-order-history">
              <FileText className="w-4 h-4" /> Mine bestillinger
            </button>
          </div>
          {view === "order" && step === 1 && isAdmin && !showCustomMaterial && (
            <button
              onClick={() => setShowCustomMaterial(true)}
              className="hidden sm:inline-flex w-full sm:w-auto items-center justify-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl text-sm font-bold shadow-md shadow-emerald-500/30 transition-colors"
              data-testid="add-custom-material-btn-header"
            >
              <Plus className="w-4 h-4" />
              Tilføj nyt materiale
            </button>
          )}
        </div>
        {/* Lokation- + Partner-switchere: vises når brugeren har adgang til
            2+ pladser ELLER når lokationen har 2+ logistik-partnere.
            Brugerkrav 2026-06-15 (runde 15): hurtig switch uden at logge ud.
            Fase 18.37 (mobil): Lokation-switcheren er flyttet til et ikon i
            top-højre hjørne (dropdown popover). Denne række vises kun på
            desktop (sm:+). Partner-switcheren beholdes på mobilen. */}
        {(availablePladser.length >= 2 || (partners.length >= 2 && partnerId)) && (
          <div className="max-w-screen-2xl mx-auto mt-2 flex flex-wrap items-center gap-3" data-testid="header-switcher-row">
            {availablePladser.length >= 2 && onSwitchLocation && (
              <div className="hidden sm:flex items-center gap-2" data-testid="location-switcher-wrap">
                <MapPin className="w-4 h-4 text-orange-400 flex-shrink-0" />
                <span className="text-[11px] uppercase tracking-wider text-slate-400 hidden sm:inline">Lokation</span>
                <select value={locationCode}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (!next || next === locationCode) return;
                    const picked = availablePladser.find(p => p.code === next);
                    if (!picked) return;
                    // Reset state så data IKKE blandes mellem lokationer.
                    // Selve locationCode-skiftet håndteres af forælderen via
                    // `onSwitchLocation` (employee → setCustomerLocationCode,
                    // LA → sessionStorage + reload). useEffect på locationCode
                    // genhenter materialer/partnere/historik.
                    setSelectedMaterial("");
                    setSelectedContainer(null);
                    setContainers([]);
                    setAutoFillData(null);
                    setOrderSuccess(null);
                    setScheduleInfo(null);
                    setAddressEditable(false);
                    setWorkshopId("");
                    setWorkshopName("");
                    setWorkshopAddress("");
                    setWorkshopPhone("");
                    setWorkshopOverride(false);
                    setComment("");
                    setOpenFrom("");
                    setOpenTo("");
                    setPartnerId("");
                    setPartners([]);
                    setPartnersLoaded(false);
                    setStep(1);
                    setView("order");
                    onSwitchLocation(picked.code, picked.name);
                    toast.info(`Skiftede til ${picked.name || picked.code}`);
                  }}
                  className="bg-slate-700 border border-slate-600 text-white text-sm rounded-lg px-3 py-1.5 focus:border-orange-500 outline-none max-w-[220px]"
                  data-testid="location-switcher-select">
                  {availablePladser.map(p => (
                    <option key={p.code} value={p.code}>
                      {p.name || p.code}{p.city ? ` · ${p.city}` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {partners.length >= 2 && partnerId && (
              <div className="hidden sm:flex items-center gap-2" data-testid="partner-switcher-row">
                <Truck className="w-4 h-4 text-orange-400 flex-shrink-0" />
                <span className="text-[11px] uppercase tracking-wider text-slate-400 hidden sm:inline">Logistik-partner</span>
                <select value={partnerId}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next === partnerId) return;
                    // Brugerkrav 2026-06-15 (runde 2): Når partner skiftes SKAL
                    // siden refreshe til 'Vælg materiale'-fanen UANSET hvor i flowet
                    // brugeren er. Vi nulstiller ALT bestilling-state og forlader
                    // history/admin-views.
                    setPartnerId(next);
                    setSelectedMaterial("");
                    setSelectedContainer(null);
                    setContainers([]);
                    setAutoFillData(null);
                    setOrderSuccess(null);
                    setScheduleInfo(null);
                    setAddressEditable(false);
                    setWorkshopId("");
                    setWorkshopName("");
                    setWorkshopAddress("");
                    setWorkshopPhone("");
                    setWorkshopOverride(false);
                    setComment("");
                    setOpenFrom("");
                    setOpenTo("");
                    setStep(1);
                    setView("order");
                    toast.info("Skiftede til ny logistik-partner - start forfra");
                  }}
                  className="bg-slate-700 border border-slate-600 text-white text-sm rounded-lg px-3 py-1.5 focus:border-orange-500 outline-none"
                  data-testid="partner-switcher-select">
                  {partners.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}
      </header>

      <main
        className="max-w-screen-2xl mx-auto px-4 sm:px-8 pb-8"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 2rem)' }}
      >
        {/* ============ ORDER VIEW ============ */}
        {view === "order" && (
          <>
            {/* Step Indicator - desktop: 4 cirkler m. labels.
                Mobil (Fase 18.27): minimalistisk "Trin X af 4 · label" + progress-bar. */}
            <div className="py-3 sm:py-4">
              {/* Mobil-version */}
              <div className="sm:hidden">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-xs font-bold text-orange-400">
                    Trin {step} af 4 · <span className="text-white">{["Materiale", "Container", "Bekræft", "Prioritet"][step - 1] || ""}</span>
                  </p>
                  <p className="text-[10px] text-slate-500">{Math.round((step / 4) * 100)}%</p>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-orange-500 transition-all duration-300" style={{ width: `${(step / 4) * 100}%` }} data-testid="mobile-step-progress" />
                </div>
              </div>
              {/* Desktop-version */}
              <div className="hidden sm:flex items-center justify-between mb-2">
                {[
                  { n: 1, label: "Materiale" },
                  { n: 2, label: "Container" },
                  { n: 3, label: "Bekræft" },
                  { n: 4, label: "Prioritet" }
                ].map((s, i) => (
                  <div key={s.n} className="flex items-center flex-1">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                      step >= s.n ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-400"
                    }`} data-testid={`step-indicator-${s.n}`}>
                      {step > s.n ? <CheckCircle2 className="w-4 h-4" /> : s.n}
                    </div>
                    <span className={`ml-2 text-xs font-medium ${step >= s.n ? "text-orange-400" : "text-slate-500"}`}>
                      {s.label}
                    </span>
                    {i < 3 && <div className={`flex-1 h-0.5 mx-2 ${step > s.n ? "bg-orange-500" : "bg-slate-700"}`} />}
                  </div>
                ))}
              </div>
            </div>

        {/* STEP 1: Material Selection */}
        {step === 1 && (
          <section data-testid="step-material">
            <div className="mb-6">
              <h2 className="text-xl sm:text-2xl font-black text-white mb-1">Vælg materiale</h2>
              <p className="text-slate-400 text-sm">Hvilken type affald skal afhentes?</p>
            </div>
            
            {/* Search - elegant medium-bred. Fase 18.37 (mobil): søgefeltet
                er kortere så der er plads til en lille "+ Tilføj"-knap ved siden af
                (kun for admin, når vi ikke allerede er ved at tilføje). */}
            <div className="mb-5">
              <div className="flex items-center gap-2 max-w-md">
                <div className="relative flex-1 min-w-0">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
                  <input
                    type="text"
                    value={materialSearch}
                    onChange={(e) => setMaterialSearch(e.target.value)}
                    placeholder="Søg materiale..."
                    className="w-full pl-10 pr-3 py-2.5 bg-slate-800 border border-slate-700 rounded-xl text-white text-sm placeholder-slate-500 focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 outline-none transition-all"
                    data-testid="material-search"
                  />
                </div>
                {isAdmin && !showCustomMaterial && (
                  <button
                    onClick={() => setShowCustomMaterial(true)}
                    className="sm:hidden shrink-0 inline-flex items-center gap-1 px-3 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl text-xs font-bold shadow-sm shadow-emerald-500/30 transition-colors whitespace-nowrap"
                    data-testid="add-custom-material-btn-inline"
                  >
                    <Plus className="w-3.5 h-3.5" /> Tilføj
                  </button>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {filteredMaterials.map((material, i) => {
                const matCo2Id = materialCo2Map[material] || "";
                const matCo2 = matCo2Id ? co2Types.find(t => t.id === matCo2Id) : null;
                return (
                <div key={material} className="relative group min-w-0">
                  {editingMaterial === material ? (
                    /* Inline edit mode */
                    <div className="p-4 bg-slate-800 border-2 border-orange-500 rounded-xl" data-testid={`material-edit-${i}`}>
                      <input
                        type="text"
                        value={editMaterialName}
                        onChange={(e) => setEditMaterialName(e.target.value)}
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm mb-2 focus:border-orange-500 outline-none"
                        data-testid={`material-edit-input-${i}`}
                        autoFocus
                        onKeyDown={(e) => { if (e.key === "Enter") handleEditMaterial(material, editMaterialName); if (e.key === "Escape") setEditingMaterial(null); }}
                      />
                      {co2Types.length > 0 && (
                        <div className="mb-2">
                          <label className="text-[10px] uppercase tracking-wider text-emerald-300 font-bold mb-1 flex items-center gap-1">
                            <Leaf className="w-3 h-3" /> CO2-kategori
                          </label>
                          <select
                            value={editMaterialCo2Id}
                            onChange={(e) => setEditMaterialCo2Id(e.target.value)}
                            className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded-lg text-white text-xs focus:border-emerald-500 outline-none"
                            data-testid={`material-edit-co2-${i}`}
                          >
                            <option value="">- Ingen -</option>
                            {co2Types.map(t => (
                              <option key={t.id} value={t.id}>{t.name} ({t.factor.toLocaleString("da-DK")} kg/ton)</option>
                            ))}
                          </select>
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button onClick={() => handleEditMaterial(material, editMaterialName)}
                          className="flex-1 px-3 py-1.5 bg-emerald-600 text-white text-xs rounded-lg font-bold" data-testid={`material-edit-save-${i}`}>Gem</button>
                        <button onClick={() => { setEditingMaterial(null); setEditMaterialCo2Id(""); }}
                          className="px-3 py-1.5 bg-slate-700 text-slate-300 text-xs rounded-lg">Annuller</button>
                      </div>
                    </div>
                  ) : (
                    /* Normal card - elegant medium størrelse med hover-effekt.
                       Fase 18.27 (mobil): mindre ikon-boks (w-8) så materialenavn
                       får mere læseplads i den smalle mobil-grid. */
                    <button
                      onClick={() => handleMaterialSelect(material)}
                      className="w-full p-3 sm:p-3.5 bg-slate-800 border border-slate-700/80 rounded-xl text-left hover:border-orange-500/70 hover:bg-slate-800/95 hover:shadow-lg hover:shadow-orange-500/10 hover:-translate-y-0.5 transition-all duration-150"
                      data-testid={`material-card-${i}`}
                    >
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="w-8 h-8 sm:w-10 sm:h-10 bg-gradient-to-br from-orange-500/25 to-orange-600/15 rounded-lg flex items-center justify-center shrink-0 ring-1 ring-orange-500/20">
                          <FileText className="w-4 h-4 sm:w-5 sm:h-5 text-orange-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-white font-semibold text-xs sm:text-sm block truncate">{material}</span>
                          {matCo2 && (
                            <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[10px] font-semibold"
                              data-testid={`material-co2-chip-${i}`}>
                              <Leaf className="w-2.5 h-2.5" /> {matCo2.name}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  )}
                  {/* Edit/Delete buttons - kun for Location Admin */}
                  {isAdmin && editingMaterial !== material && (
                    <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingMaterial(material); setEditMaterialName(material); setEditMaterialCo2Id(materialCo2Map[material] || ""); }}
                        className="p-1.5 bg-slate-700/90 hover:bg-blue-600 text-slate-300 hover:text-white rounded-lg transition-colors"
                        title="Rediger"
                        data-testid={`material-edit-btn-${i}`}
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteMaterial(material); }}
                        className="p-1.5 bg-slate-700/90 hover:bg-red-600 text-slate-300 hover:text-white rounded-lg transition-colors"
                        title="Slet"
                        data-testid={`material-delete-btn-${i}`}
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
                );
              })}
            </div>

            {/* Add-custom-material trigger flyttet til header-rækken (Fase 18.24
                - 2026-02-XX) ved siden af "Ny bestilling" / "Mine bestillinger"
                pillerne. Den separate knap under materialegridet er fjernet
                fordi den blev forvekslet med et rigtigt materialekort. */}

            {/* Custom material input - kompakt design (Fase 18.24) */}
            {showCustomMaterial && (
              <div className="mt-4 bg-slate-800 border border-emerald-500/40 rounded-xl p-3" data-testid="custom-material-form">
                <label className="text-slate-300 text-xs font-bold mb-1.5 block uppercase tracking-wider">Tilføj nyt materiale</label>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    value={customMaterial}
                    onChange={(e) => setCustomMaterial(e.target.value)}
                    placeholder="Skriv materialenavn…"
                    className="flex-1 min-w-[200px] px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:border-emerald-500 outline-none"
                    data-testid="custom-material-input"
                    autoFocus
                    onKeyDown={(e) => { if (e.key === "Enter" && customMaterial.trim() && (co2Types.length === 0 || newMaterialCo2Id)) handleAddMaterial(customMaterial.trim()); }}
                  />
                  <button
                    onClick={() => { if (customMaterial.trim()) handleAddMaterial(customMaterial.trim()); }}
                    disabled={!customMaterial.trim() || (co2Types.length > 0 && !newMaterialCo2Id)}
                    className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-bold hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
                    data-testid="custom-material-submit"
                  >
                    Tilføj
                  </button>
                  <button
                    onClick={() => { setShowCustomMaterial(false); setCustomMaterial(""); setNewMaterialCo2Id(""); }}
                    className="px-3 py-2 bg-slate-700 text-slate-300 text-sm rounded-lg hover:bg-slate-600"
                  >
                    Annuller
                  </button>
                </div>
                {/* Fase 9 refactor (2026-06-18): CO2-kategori er obligatorisk for nye
                    materialer hvis kunden har oprettet et CO2-bibliotek. */}
                {co2Types.length > 0 && (
                  <div className="mt-2.5" data-testid="new-material-co2-block">
                    <label className="text-[10px] font-bold text-emerald-300 uppercase tracking-wider mb-1 flex items-center gap-1">
                      <Leaf className="w-3 h-3" /> CO2-kategori <span className="text-rose-400 normal-case font-normal">(obligatorisk)</span>
                    </label>
                    <select
                      value={newMaterialCo2Id}
                      onChange={(e) => setNewMaterialCo2Id(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm focus:border-emerald-500 outline-none"
                      data-testid="new-material-co2-select"
                    >
                      <option value="">- Vælg CO2-kategori -</option>
                      {co2Types.map(t => (
                        <option key={t.id} value={t.id}>{t.name} ({t.factor.toLocaleString("da-DK")} kg/ton)</option>
                      ))}
                    </select>
                    <p className="text-[10px] text-slate-400 mt-1">
                      Vælg en CO2-kategori - så beregnes CO2-aftrykket automatisk på alle bestillinger med dette materiale.
                    </p>
                  </div>
                )}
                {co2Types.length === 0 && (
                  <p className="text-[10px] text-slate-500 mt-1.5 italic">
                    Tip: Kunde Admin kan oprette CO2-kategorier under "CO2-typer".
                  </p>
                )}
              </div>
            )}
            {filteredMaterials.length === 0 && (
              <p className="text-center text-slate-500 py-8">Ingen materialer matcher din søgning</p>
            )}
          </section>
        )}

        {/* STEP 2: Container Selection */}
        {step === 2 && (
          <section data-testid="step-container">
            <div className="mb-6">
              <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
                <div>
                  <h2 className="text-xl sm:text-2xl font-black text-white mb-1">Vælg container</h2>
                  <p className="text-slate-400 text-sm">
                    Materiale: <span className="text-orange-400 font-bold">{selectedMaterial}</span>
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {/* "+ Tilføj container" - kun Location Admin */}
                  {isAdmin && (
                    <button
                      onClick={() => setConfirmAddContainer(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold whitespace-nowrap shadow-sm hover:shadow-md transition-all"
                      data-testid="add-container-btn"
                    >
                      <Plus className="w-4 h-4" /> Tilføj container
                    </button>
                  )}
                  {/* "Tilføj tilpasset bestilling" - alle roller */}
                  <button
                    onClick={() => {
                      setIsCustomRequest(true);
                      // Fase 15.16: Reset til default "opgave" mode hver gang
                      setCustomRequestMode("opgave");
                      setEstimatedCount("");
                      setAddressEditable(false);
                      setSelectedContainer({
                        label: "Tilpasset bestilling",
                        material: selectedMaterial,
                        container_id: "",
                        address: "",
                        open_from: "",
                        open_to: "",
                        locked_address: false,
                        locked_hours: false,
                        has_override: false,
                        default_address: "",
                      });
                      setAutoFillData({
                        address: "",
                        city: location?.city || "",
                        genbrugsplads: location?.name || "",
                        material: selectedMaterial,
                        container: "Tilpasset bestilling",
                        containerId: "",
                        defaultContainerId: "",
                        hasOverride: false,
                        defaultAddress: "",
                        lockedAddress: false,
                        lockedHours: false,
                      });
                      setOpenFrom("");
                      setOpenTo("");
                      setStep(3);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-bold whitespace-nowrap shadow-sm hover:shadow-md transition-all"
                    data-testid="custom-request-btn"
                  >
                    <Edit2 className="w-4 h-4" /> Tilpasset bestilling
                  </button>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {containers.map((c, i) => {
                // Fase 15.16 (2026-02-XX): Vis aktive (ikke-fuldførte)
                // bestillinger på containeren som mini-badges. Container
                // graånes ud hvis ALLE typer er blokeret (sjældent), eller
                // viser små tags pr. type så medarbejder kan se hvad der
                // allerede er bestilt. Map'en er nu indekseret på
                // container_number (fx "Container 1") - IKKE container_id.
                const blocks = blockedByContainer[(c.label || c.number || "").trim()] || [];
                const hasBlocks = blocks.length > 0;
                return (
                <div key={c.number} className="relative group" data-testid={`container-wrap-${i}`}>
                  <button
                    onClick={() => handleContainerSelect(c)}
                    className={`w-full p-3.5 bg-slate-800 border rounded-xl text-center hover:border-orange-500/70 hover:shadow-lg hover:shadow-orange-500/10 hover:-translate-y-0.5 transition-all duration-150 ${c.container_id ? "border-emerald-500/40" : "border-slate-700/80"} ${hasBlocks ? "ring-2 ring-amber-500/40" : ""}`}
                    data-testid={`container-card-${i}`}
                  >
                    <div className="w-11 h-11 bg-gradient-to-br from-orange-500/25 to-orange-600/15 rounded-xl flex items-center justify-center mx-auto mb-2 ring-1 ring-orange-500/20 group-hover:from-orange-500/35 group-hover:to-orange-600/20 transition-colors">
                      <Truck className="w-5 h-5 text-orange-400" />
                    </div>
                    {c.container_id ? (
                      <>
                        <h3 className="text-base font-black text-emerald-400 mb-0.5 truncate">{c.container_id}</h3>
                        <p className="text-slate-500 text-[11px] truncate">{c.label}</p>
                      </>
                    ) : (
                      <>
                        <h3 className="text-base font-black text-white mb-0.5 truncate">{c.label}</h3>
                        <p className="text-slate-500 text-[11px]">Intet nr. gemt</p>
                      </>
                    )}
                    {hasBlocks && (
                      <div className="mt-1.5 flex flex-wrap gap-1 justify-center" data-testid={`container-blocks-${i}`}>
                        {blocks.slice(0, 3).map((b, j) => (
                          <span
                            key={j}
                            className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40"
                            title={`Aktiv bestilling for opgavetype ${b.tour_type}${b.order_date ? ` (${b.order_date})` : ""}`}
                          >
                            {b.tour_type === "normal" ? "Afhent" : b.tour_type === "flyt" ? "Flyt" : b.tour_type === "vaerksted" ? "Til værk." : b.tour_type === "afhent_vaerksted" ? "Værk. retur" : b.tour_type}
                          </span>
                        ))}
                        {blocks.length > 3 && (
                          <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-slate-700 text-slate-300">+{blocks.length - 3}</span>
                        )}
                      </div>
                    )}
                  </button>
                  {/* Admin-only: Rediger + Slet */}
                  {isAdmin && (
                    <>
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingContainer(c); }}
                        className="absolute top-1 right-1 p-1.5 bg-slate-700/90 hover:bg-blue-600 text-slate-300 hover:text-white rounded-lg transition-colors"
                        title="Rediger grunddata"
                        data-testid={`container-edit-btn-${i}`}
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteContainer(c); }}
                        className="absolute top-1 left-1 p-1.5 bg-slate-700/90 hover:bg-red-600 text-slate-300 hover:text-white rounded-lg transition-colors"
                        title="Slet container"
                        data-testid={`container-delete-btn-${i}`}
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </>
                  )}
                </div>
                );
              })}
            </div>

            {isAdmin && (
              <p className="text-center text-slate-500 text-xs mt-4">
                Som Location Admin kan du tilføje, redigere og slette containere her. Almindelige medarbejdere kan kun vælge en eksisterende container eller bruge "Tilføj tilpasset bestilling".
              </p>
            )}
          </section>
        )}

        {/* STEP 3: Auto-fill Confirmation - EDITABLE */}
        {step === 3 && autoFillData && (
          <section data-testid="step-confirm">
            <div className="mb-4">
              <h2 className="text-lg sm:text-xl font-black text-white mb-0.5">Bekræft og rediger</h2>
              <p className="text-slate-400 text-xs">Oplysninger er udfyldt automatisk. Du kan redigere adresse og container-nummer.</p>
              {autoFillData.hasOverride && (
                <p className="text-orange-400 text-[11px] mt-1 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Bruger dine gemte data fra sidste gang
                </p>
              )}
            </div>

            {/* Fase 15.16 (2026-02-XX): "Tilpasset bestilling" type-vælger.
                Vises KUN når flow'et er custom-request. Almindelige bestillinger
                fra container-grid'et følger den normale flow uden ændringer. */}
            {/* Fase 15.41 (2026-02-22): Skift mellem opgave / estimat / løs
                afhentning. Modes vises kun hvis featuren er aktiv for klienten. */}
            {isCustomRequest && (() => {
              const modes = [
                { id: "opgave",  label: "Opgave",  desc: "Konkret bestilling - alle felter" },
                ...(estimateEnabled
                  ? [{ id: "estimat", label: "Estimat", desc: "Forventet ressourcebehov" }]
                  : []),
                // Fase 15.41 - "Løs afhentning": chauffør medbringer egne
                // tomme containere; ingen container-id, kun antal-skøn.
                ...(loesAfhentningEnabled
                  ? [{ id: "loes_afhentning", label: "Løs afhentning", desc: "Chauffør medbringer egne containere" }]
                  : []),
              ];
              const cols = modes.length === 1 ? "grid-cols-1" : (modes.length === 2 ? "grid-cols-2" : "grid-cols-3");
              return (
                <div className="bg-slate-800 border sm:border-2 border-slate-700 rounded-xl sm:rounded-2xl p-3 sm:p-4 mb-4 sm:mb-6">
                  <p className="text-slate-400 text-[10px] sm:text-xs uppercase tracking-wider mb-1.5 sm:mb-2">Type af tilpasset bestilling</p>
                  <div className={`grid ${cols} gap-1.5 sm:gap-2`}>
                    {modes.map(o => (
                      <button
                        key={o.id}
                        type="button"
                        onClick={() => {
                          if (o.id !== customRequestMode) setComment("");
                          setCustomRequestMode(o.id);
                        }}
                        data-testid={`custom-mode-${o.id}`}
                        className={`p-2 sm:p-3 rounded-lg sm:rounded-xl border sm:border-2 text-left transition-all ${
                          customRequestMode === o.id
                            ? "bg-amber-500/20 border-amber-500 text-white"
                            : "bg-slate-900 border-slate-700 text-slate-300 hover:border-amber-500/50"
                        }`}
                      >
                        <p className="font-bold text-xs sm:text-sm leading-tight">{o.label}</p>
                        <p className="text-[10px] opacity-70 mt-0.5 leading-tight">{o.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Fase 15.16 (2026-02-XX): ESTIMAT-FLOW - minimalistisk form.
                Kun materiale (read-only), estimeret antal, dato, bestil-knap.
                Ingen container-ID, adresse, værksted, åbningstider eller priority.
                Fase 15.40 (2026-02-22): Hele formen er nu gated bag feature
                `estimate` - defensiv guard så DOM aldrig renderes selv hvis
                customRequestMode skulle være "estimat" pga. cached state.
                Fase 15.41 (2026-02-22): Tilføjet LØS AFHENTNING-form (3.
                branch). Ingen container-ID, ingen kapacitetsmål - kun et
                "Estimeret antal containere"-felt så chaufføren ved hvor mange
                tomme containere de skal medbringe. Adresse er PÅKRÆVET fordi
                chaufføren skal vide hvor de skal hen. */}
            {isCustomRequest && customRequestMode === "estimat" && estimateEnabled ? (
              <div className="bg-slate-800 border-2 border-slate-700 rounded-2xl p-6 space-y-4 mb-6" data-testid="estimat-form">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 bg-orange-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <FileText className="w-5 h-5 text-orange-500" />
                  </div>
                  <div className="flex-1">
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Materiale</p>
                    <p className="text-white font-bold text-lg" data-testid="estimat-material">{autoFillData.material}</p>
                  </div>
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Estimeret antal containere <span className="text-red-400">*</span></p>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    step={1}
                    value={estimatedCount}
                    placeholder="Indtast antal"
                    onChange={(e) => {
                      // Fase 15.16 (2026-02-21): Tillad frit input - vi
                      // validerer (>0) først på submit. Tom-streng er OK
                      // så feltet kan rydes og indtastes med tastatur.
                      const v = e.target.value;
                      setEstimatedCount(v === "" ? "" : v.replace(/[^0-9]/g, ""));
                    }}
                    className="w-40 px-4 py-3 rounded-xl border-2 border-slate-700 bg-slate-900 text-white font-black text-2xl focus:outline-none focus:border-amber-500 placeholder:text-slate-600 placeholder:text-base placeholder:font-normal"
                    data-testid="estimat-count-input"
                  />
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Dato</p>
                  <div className="grid grid-cols-3 gap-2 mb-2">
                    <button onClick={() => setOrderDate(localDateStr())}
                      className={`py-3 rounded-xl font-bold text-sm transition-colors ${orderDate === localDateStr() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                      I dag
                    </button>
                    <button onClick={() => { const d = new Date(); d.setDate(d.getDate() + 1); setOrderDate(localDateStr(d)); }}
                      className={`py-3 rounded-xl font-bold text-sm transition-colors ${orderDate === (() => { const d = new Date(); d.setDate(d.getDate() + 1); return localDateStr(d); })() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                      I morgen
                    </button>
                    <input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)}
                      className="px-3 py-3 rounded-xl bg-slate-700 text-white text-sm font-bold text-center" />
                  </div>
                  <p className="text-sm text-slate-400">Valgt dato: <span className="text-orange-400 font-bold">{new Date(orderDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span></p>
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Kommentar <span className="text-slate-600 font-normal normal-case tracking-normal">(valgfri)</span></p>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Tilføj evt. en kommentar til estimatet"
                    rows={2}
                    className="w-full px-3 py-2 rounded-xl border-2 border-slate-700 bg-slate-900 text-white text-sm focus:outline-none focus:border-amber-500 placeholder:text-slate-600"
                    data-testid="estimat-comment-input"
                  />
                </div>
                <button
                  onClick={async () => {
                    const countNum = Number(estimatedCount);
                    if (!Number.isFinite(countNum) || countNum <= 0) { toast.error("Indtast et antal større end 0"); return; }
                    if (!orderDate) { toast.error("Vælg en dato"); return; }
                    setSubmitting(true);
                    try {
                      const res = await axios.post(`${API}/customer-orders/submit`, {
                        location_code: locationCode,
                        material: selectedMaterial,
                        co2_type_id: "",
                        container_number: "Estimat",
                        priority: "normal",
                        tour_type: "estimat",
                        // Fase 15.18 (2026-02-21): Kommentar må IKKE forudfyldes
                        // med antal - det vises nu i sit eget felt ("Antal
                        // containere estimeret"). Kun brugerens egen tekst gemmes.
                        comment: (comment || "").trim(),
                        custom_address: "",
                        custom_container_id: "",
                        order_date: orderDate,
                        open_from: "",
                        open_to: "",
                        plads_name: pladsName || "",
                        delivery_address_id: "",
                        workshop_id: "",
                        workshop_name: "",
                        workshop_address: "",
                        workshop_phone: "",
                        workshop_override: false,
                        partner_id: partnerId || "",
                        estimated_count: countNum,
                      });
                      setOrderSuccess(res.data);
                      setStep(5);
                      toast.success(`Estimat oprettet (${countNum} container(e))`);
                    } catch (e) {
                      toast.error(e?.response?.data?.detail || "Kunne ikke oprette estimat");
                    } finally {
                      setSubmitting(false);
                    }
                  }}
                  disabled={submitting}
                  className="w-full py-4 text-lg font-black rounded-xl transition-colors flex items-center justify-center gap-2 bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50"
                  data-testid="estimat-submit-btn"
                >
                  {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Check className="w-5 h-5" />}
                  Bestil estimat
                </button>
              </div>
            ) : isCustomRequest && customRequestMode === "loes_afhentning" && loesAfhentningEnabled ? (
              <div className="bg-slate-800 border-2 border-slate-700 rounded-2xl p-6 space-y-4 mb-6" data-testid="loes-form">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 bg-orange-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <FileText className="w-5 h-5 text-orange-500" />
                  </div>
                  <div className="flex-1">
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Materiale</p>
                    <p className="text-white font-bold text-lg" data-testid="loes-material">{autoFillData.material}</p>
                    <p className="text-[10px] text-amber-400 uppercase tracking-wider mt-2 font-bold">
                      Løs afhentning - chauffør medbringer egne tomme containere
                    </p>
                  </div>
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Estimeret antal containere <span className="text-red-400">*</span></p>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    step={1}
                    value={looseEstimatedCount}
                    placeholder="Indtast antal"
                    onChange={(e) => {
                      const v = e.target.value;
                      setLooseEstimatedCount(v === "" ? "" : v.replace(/[^0-9]/g, ""));
                    }}
                    className="w-40 px-4 py-3 rounded-xl border-2 border-slate-700 bg-slate-900 text-white font-black text-2xl focus:outline-none focus:border-amber-500 placeholder:text-slate-600 placeholder:text-base placeholder:font-normal"
                    data-testid="loes-count-input"
                  />
                  <p className="text-[11px] text-slate-500 mt-1">Skøn til chaufføren - det endelige antal afgøres på pladsen.</p>
                </div>
                <div className="border-t border-slate-700" />
                {/* Fase 15.41 - Adressen er ALLEREDE leveringsadressen for
                    pladsen (auto-fyldt fra autoFillData), så vi gentager den
                    ikke som redigerbart felt. */}
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <MapPin className="w-5 h-5 text-purple-500" />
                  </div>
                  <div className="flex-1">
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Afhentningsadresse</p>
                    <p className="text-white text-sm" data-testid="loes-address-display">
                      {autoFillData.address || "-"}
                    </p>
                  </div>
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Dato</p>
                  <div className="grid grid-cols-3 gap-2 mb-2">
                    <button onClick={() => setOrderDate(localDateStr())}
                      className={`py-3 rounded-xl font-bold text-sm transition-colors ${orderDate === localDateStr() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                      I dag
                    </button>
                    <button onClick={() => { const d = new Date(); d.setDate(d.getDate() + 1); setOrderDate(localDateStr(d)); }}
                      className={`py-3 rounded-xl font-bold text-sm transition-colors ${orderDate === (() => { const d = new Date(); d.setDate(d.getDate() + 1); return localDateStr(d); })() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                      I morgen
                    </button>
                    <input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)}
                      className="px-3 py-3 rounded-xl bg-slate-700 text-white text-sm font-bold text-center" />
                  </div>
                  <p className="text-sm text-slate-400">Valgt dato: <span className="text-orange-400 font-bold">{new Date(orderDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span></p>
                </div>
                <div className="border-t border-slate-700" />
                {/* Fase 15.42 (2026-02-22): Prioritetsvælger på Løs afhentning
                    - samme tre niveauer som almindelige bestillinger (Haster /
                    Normal / Lav). HASTER giver pulserende rød markering hos
                    chauffør, Normal og Lav er rolige farver. */}
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Prioritet</p>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      onClick={() => setPriority("haster")}
                      className={`py-3 px-2 rounded-xl font-bold text-sm transition-colors flex items-center justify-center gap-1.5 ${
                        priority === "haster"
                          ? "bg-red-500 text-white ring-2 ring-red-300"
                          : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                      }`}
                      data-testid="loes-priority-haster"
                    >
                      <AlertTriangle className="w-4 h-4" />
                      HASTER
                    </button>
                    <button
                      onClick={() => setPriority("normal")}
                      className={`py-3 px-2 rounded-xl font-bold text-sm transition-colors flex items-center justify-center gap-1.5 ${
                        priority === "normal"
                          ? "bg-orange-500 text-white ring-2 ring-orange-300"
                          : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                      }`}
                      data-testid="loes-priority-normal"
                    >
                      <Clock className="w-4 h-4" />
                      NORMAL
                    </button>
                    <button
                      onClick={() => setPriority("senere")}
                      className={`py-3 px-2 rounded-xl font-bold text-sm transition-colors flex items-center justify-center gap-1.5 ${
                        priority === "senere"
                          ? "bg-blue-500 text-white ring-2 ring-blue-300"
                          : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                      }`}
                      data-testid="loes-priority-senere"
                    >
                      <Calendar className="w-4 h-4" />
                      LAV
                    </button>
                  </div>
                </div>
                <div className="border-t border-slate-700" />
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Kommentar <span className="text-slate-600 font-normal normal-case tracking-normal">(valgfri)</span></p>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Tilføj evt. en kommentar (fx adgangsforhold)"
                    rows={2}
                    className="w-full px-3 py-2 rounded-xl border-2 border-slate-700 bg-slate-900 text-white text-sm focus:outline-none focus:border-amber-500 placeholder:text-slate-600"
                    data-testid="loes-comment-input"
                  />
                </div>
                <button
                  onClick={async () => {
                    const countNum = Number(looseEstimatedCount);
                    if (!Number.isFinite(countNum) || countNum <= 0) { toast.error("Indtast et antal større end 0"); return; }
                    if (!orderDate) { toast.error("Vælg en dato"); return; }
                    const addr = (autoFillData.address || "").trim();
                    if (!addr) { toast.error("Pladsens leveringsadresse mangler - kontakt admin"); return; }
                    setSubmitting(true);
                    try {
                      const res = await axios.post(`${API}/customer-orders/submit`, {
                        location_code: locationCode,
                        material: selectedMaterial,
                        co2_type_id: "",
                        container_number: "Løs afhentning",  // placeholder - never displayed for loes_afhentning
                        priority: priority || "normal",
                        tour_type: "loes_afhentning",
                        comment: (comment || "").trim(),
                        custom_address: addr,
                        custom_container_id: "",
                        order_date: orderDate,
                        open_from: "",
                        open_to: "",
                        plads_name: pladsName || "",
                        delivery_address_id: "",
                        workshop_id: "",
                        workshop_name: "",
                        workshop_address: "",
                        workshop_phone: "",
                        workshop_override: false,
                        partner_id: partnerId || "",
                        loose_estimated_count: countNum,
                      });
                      setOrderSuccess(res.data);
                      setStep(5);
                      toast.success(`Løs afhentning oprettet (skøn: ${countNum} container(e))`);
                    } catch (e) {
                      toast.error(e?.response?.data?.detail || "Kunne ikke oprette løs afhentning");
                    } finally {
                      setSubmitting(false);
                    }
                  }}
                  disabled={submitting}
                  className="w-full py-4 text-lg font-black rounded-xl transition-colors flex items-center justify-center gap-2 bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50"
                  data-testid="loes-submit-btn"
                >
                  {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Check className="w-5 h-5" />}
                  Bestil løs afhentning
                </button>
              </div>
            ) : (
            <>
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3 mb-4">
              {/* Material - read-only */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-orange-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                  <FileText className="w-4 h-4 text-orange-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-0.5">Materiale</p>
                  <p className="text-white font-semibold text-sm" data-testid="confirm-material">{autoFillData.material}</p>
                </div>
              </div>

              <div className="border-t border-slate-700/70" />

              {/* Opgavetype - placeret lige under Materiale (Batch 2) */}
              <div>
                <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1.5">Opgavetype</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                  {[
                    { id: "normal", label: "Afhentning", desc: "Genbrug" },
                    { id: "flyt", label: "Byt container", desc: "Skift container" },
                    { id: "vaerksted", label: "Til værksted", desc: "Reparation" },
                    { id: "afhent_vaerksted", label: "Afhent fra værksted", desc: "Retur" },
                  ].map(o => (
                    <button key={o.id}
                      type="button"
                      onClick={() => {
                        setTourType(o.id);
                        // Skift fra værksted/afhent → andet: nulstil workshop snapshot
                        if (!["vaerksted", "afhent_vaerksted"].includes(o.id)) {
                          setWorkshopId(""); setWorkshopName(""); setWorkshopAddress("");
                          setWorkshopPhone(""); setWorkshopOverride(false);
                        }
                      }}
                      data-testid={`tourtype-${o.id}`}
                      className={`p-2 rounded-lg border text-left transition-all ${
                        tourType === o.id
                          ? "bg-emerald-500/20 border-emerald-500 text-white"
                          : "bg-slate-900 border-slate-700 text-slate-300 hover:border-emerald-500/50"
                      }`}>
                      <p className="font-bold text-xs leading-tight">{o.label}</p>
                      <p className="text-[10px] opacity-60 mt-0.5">{o.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Workshop snapshot - vises kun for "Til værksted" og "Afhent fra værksted".
                  Brugeren vælger et værksted fra biblioteket (CA-administreret); navn,
                  adresse og telefon auto-fyldes. "Overskriv"-knappen tillader fri tekst. */}
              {(tourType === "vaerksted" || tourType === "afhent_vaerksted") && (
                <div className="border-t border-slate-700 pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-slate-400 text-xs uppercase tracking-wider inline-flex items-center gap-1">
                      <Wrench className="w-3.5 h-3.5" />
                      Værksted <span className="text-red-400">*</span>
                    </p>
                    <button type="button"
                      onClick={() => setWorkshopOverride(v => !v)}
                      className={`text-[11px] font-bold uppercase tracking-wider px-2 py-1 rounded ${
                        workshopOverride
                          ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                      }`}
                      data-testid="workshop-override-btn">
                      {workshopOverride ? "Brug bibliotek" : "Overskriv"}
                    </button>
                  </div>
                  <select value={workshopId}
                    disabled={workshopOverride}
                    onChange={e => {
                      const id = e.target.value;
                      setWorkshopId(id);
                      const w = workshops.find(x => x.id === id);
                      if (w) {
                        setWorkshopName(w.name || "");
                        setWorkshopAddress(w.address || "");
                        setWorkshopPhone(w.phone || "");
                      } else {
                        setWorkshopName(""); setWorkshopAddress(""); setWorkshopPhone("");
                      }
                    }}
                    className={`w-full px-3 py-2 border rounded-lg text-sm outline-none ${
                      workshopOverride
                        ? "bg-slate-900/50 border-slate-700 text-slate-500 cursor-not-allowed"
                        : workshopId
                          ? "bg-slate-900 border-slate-600 text-white"
                          : "bg-slate-900 border-red-500/50 text-white focus:border-orange-500"
                    }`}
                    data-testid="workshop-select">
                    <option value="">- Vælg værksted -</option>
                    {workshops.map(w => (
                      <option key={w.id} value={w.id}>{w.name}{w.address ? ` - ${w.address}` : ""}</option>
                    ))}
                  </select>
                  {workshops.length === 0 && !workshopOverride && (
                    <p className="text-amber-300 text-[11px] mt-1 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> Ingen værksteder i biblioteket - bed kunde-admin oprette under "Værksteder", eller klik "Overskriv" for at indtaste manuelt.
                    </p>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
                    <div>
                      <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">Navn</p>
                      <input type="text"
                        value={workshopName}
                        readOnly={!workshopOverride}
                        onChange={e => setWorkshopName(e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded-lg text-sm outline-none ${
                          workshopOverride ? "bg-slate-900 border-amber-500/50 text-white" : "bg-slate-900/60 border-slate-700 text-slate-300 cursor-not-allowed"
                        }`}
                        data-testid="workshop-name-input" />
                    </div>
                    <div>
                      <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">Adresse</p>
                      <input type="text"
                        value={workshopAddress}
                        readOnly={!workshopOverride}
                        onChange={e => setWorkshopAddress(e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded-lg text-sm outline-none ${
                          workshopOverride ? "bg-slate-900 border-amber-500/50 text-white" : "bg-slate-900/60 border-slate-700 text-slate-300 cursor-not-allowed"
                        }`}
                        data-testid="workshop-address-input" />
                    </div>
                    <div>
                      <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">Telefon</p>
                      <input type="text"
                        value={workshopPhone}
                        readOnly={!workshopOverride}
                        onChange={e => setWorkshopPhone(e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded-lg text-sm outline-none ${
                          workshopOverride ? "bg-slate-900 border-amber-500/50 text-white" : "bg-slate-900/60 border-slate-700 text-slate-300 cursor-not-allowed"
                        }`}
                        data-testid="workshop-phone-input" />
                    </div>
                  </div>
                </div>
              )}
              
              <div className="border-t border-slate-700/70" />
              
              {/* "Container"-feltet er fjernet (pr. brugerkrav 2026-06-14) -
                  kun "Container-nummer" beholdes. */}
              
              {/* Container ID */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-cyan-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                  <Edit2 className="w-4 h-4 text-cyan-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    Container-Nummer {(isCustomRequest || (!autoFillData.defaultContainerId && !autoFillData.lockedContainerId)) && <span className="text-red-400">*</span>}
                  </p>
                  {isCustomRequest ? (
                    <input
                      type="text"
                      value={autoFillData.containerId}
                      onChange={(e) => setAutoFillData({...autoFillData, containerId: e.target.value})}
                      placeholder="Indtast container-nummer..."
                      required
                      className="w-full sm:max-w-xs px-3 py-1.5 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:border-orange-500 outline-none"
                      data-testid="edit-container-id"
                    />
                  ) : (
                    <input
                      type="text"
                      value={autoFillData.defaultContainerId || ""}
                      readOnly
                      className="w-full sm:max-w-xs px-3 py-1.5 bg-slate-900/60 border border-slate-700 rounded-lg text-slate-300 text-sm cursor-not-allowed"
                      data-testid="edit-container-id"
                    />
                  )}
                </div>
              </div>

              {/* Kapacitetsmål (Batch 2 - vises som chip når sat på containeren) */}
              {autoFillData.capacityLabel && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 bg-purple-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <Ruler className="w-4 h-4 text-purple-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-0.5">Kapacitetsmål</p>
                    <p className="text-white font-semibold text-sm" data-testid="confirm-capacity">
                      {autoFillData.capacityLabel}
                      {autoFillData.capacityVolumeM3 ? <span className="text-purple-300 font-medium text-xs ml-2">{autoFillData.capacityVolumeM3} m³</span> : null}
                    </p>
                  </div>
                </div>
              )}
              
              <div className="border-t border-slate-700/70" />
              
              {/* Genbrugsplads - read-only */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-emerald-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                  <Building2 className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-0.5">Genbrugsplads</p>
                  <p className="text-white font-semibold text-sm" data-testid="confirm-genbrugsplads">{autoFillData.genbrugsplads}</p>
                </div>
              </div>
              
              <div className="border-t border-slate-700/70" />
              
              {/* Address - PRE-FILLED, READ-ONLY by default. Toggle via
                  "Ændre til anden adresse" unless container.locked_address
                  is true (then it's permanently locked).
                  Batch 2: skjult når opgavetype er Byt container / Til værksted /
                  Afhent fra værksted - disse flows har ingen leveringsadresse. */}
              {!["flyt", "vaerksted", "afhent_vaerksted"].includes(tourType) && (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-purple-500/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                  <MapPin className="w-4 h-4 text-purple-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    Leveringsadresse <span className="text-red-400">*</span>
                    {autoFillData.lockedAddress
                      ? <span className="text-amber-400 ml-1 normal-case">(låst af location admin)</span>
                      : addressEditable
                        ? <span className="text-orange-400 ml-1 normal-case">(redigerbar)</span>
                        : <span className="text-slate-500 ml-1 normal-case">(forudfyldt)</span>}
                  </p>
                  <input
                    type="text"
                    value={autoFillData.address}
                    onChange={(e) => setAutoFillData({...autoFillData, address: e.target.value})}
                    placeholder="Indtast adresse hvor containeren skal leveres..."
                    required
                    readOnly={autoFillData.lockedAddress || !addressEditable}
                    className={`w-full sm:max-w-lg px-3 py-1.5 bg-slate-900 border rounded-lg text-white text-sm placeholder-slate-500 outline-none ${
                      (autoFillData.lockedAddress || !addressEditable)
                        ? "border-slate-700 cursor-not-allowed opacity-80"
                        : autoFillData.address?.trim()
                          ? "border-slate-600 focus:border-orange-500"
                          : "border-red-500/50 focus:border-orange-500"
                    }`}
                    data-testid="edit-address"
                  />
                  {!autoFillData.lockedAddress && !addressEditable && (
                    <button
                      type="button"
                      onClick={() => setAddressEditable(true)}
                      className="mt-1 inline-flex items-center gap-1 text-orange-400 hover:text-orange-300 text-[11px] font-bold"
                      data-testid="enable-address-edit-btn">
                      <Edit2 className="w-3 h-3" /> Ændre til anden adresse
                    </button>
                  )}
                  {!autoFillData.lockedAddress && addressEditable && (
                    <button
                      type="button"
                      onClick={() => {
                        setAddressEditable(false);
                        // Restore the resolved/primary address line
                        const sel = scheduleInfo?.selected;
                        if (sel) {
                          const line = [sel.street, [sel.postcode, sel.city].filter(Boolean).join(" ")]
                            .filter(Boolean).join(", ");
                          if (line) setAutoFillData(prev => ({...prev, address: line}));
                        }
                      }}
                      className="mt-1 inline-flex items-center gap-1 text-slate-400 hover:text-slate-300 text-[11px]"
                      data-testid="cancel-address-edit-btn">
                      <X className="w-3 h-3" /> Annullér ændring
                    </button>
                  )}

                  {/* Schedule status banner */}
                  {scheduleInfo && (
                    scheduleInfo.is_closed ? (
                      <div className="mt-2 p-2.5 rounded-lg bg-red-500/10 border border-red-500/40 text-red-300 text-[11px]"
                        data-testid="schedule-closed-banner">
                        <p className="font-bold flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5" /> LUKKET på den valgte dato
                          {scheduleInfo.is_holiday && <span className="ml-1 font-normal">({scheduleInfo.holiday_name})</span>}
                        </p>
                        <p className="mt-0.5">Klik "Ændre til anden adresse" ovenfor for at indtaste en alternativ adresse, eller vælg en anden dato.</p>
                      </div>
                    ) : (scheduleInfo.is_holiday && (
                      <p className="mt-2 text-amber-300 text-[11px] flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" /> Helligdag: {scheduleInfo.holiday_name} (åbent fra {scheduleInfo.open_from || "??"})
                      </p>
                    ))
                  )}

                  {/* 2026-06-15: "Alternativ leveringsadresse" og "Vil du udfylde
                      adressen selv?" er PERMANENT FJERNET pr. brugerkrav. Brugeren
                      bruger udelukkende det forudfyldte adresse-felt ovenfor. */}

                  {/* Opening / closing hours - Fase 18.36 endelig fix:
                      iOS Safari's native time-picker har intrinsisk min-width
                      der ignorerer parent constraint. Løsning:
                      - `appearance-none` fjerner native styling
                      - `[&::-webkit-date-and-time-value]:text-left` sikrer venstre-justering
                      - eksplicit lille bredde `w-full` + `min-w-0` på både wrapper og input */}
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:max-w-xs">
                    <div className="min-w-0">
                      <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-0.5 flex items-center gap-1 truncate">
                        <Clock className="w-3 h-3 shrink-0" /> Åbner {autoFillData.lockedHours && <span className="text-amber-400 normal-case">(låst)</span>}
                      </p>
                      <input
                        type="time"
                        value={openFrom}
                        readOnly={autoFillData.lockedHours}
                        onChange={(e) => setOpenFrom(e.target.value)}
                        className={`w-full min-w-0 appearance-none px-2 py-1.5 bg-slate-900 border rounded-lg text-white text-xs sm:text-sm outline-none [&::-webkit-calendar-picker-indicator]:hidden ${autoFillData.lockedHours ? "border-amber-500/40 cursor-not-allowed opacity-80" : "border-slate-600 focus:border-orange-500"}`}
                        data-testid="edit-open-from"
                      />
                    </div>
                    <div className="min-w-0">
                      <p className="text-slate-400 text-[10px] uppercase tracking-wider mb-0.5 flex items-center gap-1 truncate">
                        <Clock className="w-3 h-3 shrink-0" /> Lukker {autoFillData.lockedHours && <span className="text-amber-400 normal-case">(låst)</span>}
                      </p>
                      <input
                        type="time"
                        value={openTo}
                        readOnly={autoFillData.lockedHours}
                        onChange={(e) => setOpenTo(e.target.value)}
                        className={`w-full min-w-0 appearance-none px-2 py-1.5 bg-slate-900 border rounded-lg text-white text-xs sm:text-sm outline-none [&::-webkit-calendar-picker-indicator]:hidden ${autoFillData.lockedHours ? "border-amber-500/40 cursor-not-allowed opacity-80" : "border-slate-600 focus:border-orange-500"}`}
                        data-testid="edit-open-to"
                      />
                    </div>
                  </div>
                  {(openFrom || openTo) && (
                    <p className="text-slate-500 text-[10px] mt-1">
                      Åbningstid: {openFrom || "??"} - {openTo || "??"}
                    </p>
                  )}
                </div>
              </div>
              )}
            </div>
            
            {/* Info-box fjernet pr. krav. */}
            
            {/* Date picker - kompakt (Fase 18.26: max-bredde + slank layout) */}
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-3 mb-4 sm:max-w-md">
              <label className="text-slate-400 text-[10px] uppercase tracking-wider mb-1.5 block">Afhentningsdato</label>
              <div className="flex flex-wrap items-center gap-2 mb-1.5">
                <button onClick={() => setOrderDate(localDateStr())}
                  className={`px-3 py-1.5 rounded-lg font-bold text-xs transition-colors ${orderDate === localDateStr() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}
                  data-testid="date-today">I dag</button>
                <button onClick={() => { const d = new Date(); d.setDate(d.getDate() + 1); setOrderDate(localDateStr(d)); }}
                  className={`px-3 py-1.5 rounded-lg font-bold text-xs transition-colors ${orderDate === (() => { const d = new Date(); d.setDate(d.getDate() + 1); return localDateStr(d); })() ? "bg-orange-500 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}
                  data-testid="date-tomorrow">I morgen</button>
                <input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)}
                  className="py-1.5 px-2.5 bg-slate-700 border border-slate-600 rounded-lg text-white text-xs text-center focus:border-orange-500 outline-none flex-1 min-w-[140px]"
                  data-testid="date-custom" />
              </div>
              <p className="text-[11px] text-slate-400">Valgt: <span className="text-orange-400 font-bold">{new Date(orderDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span></p>
            </div>
            
            {/* Comment (optional) - kompakt */}
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 mb-4">
              <label className="text-slate-400 text-[10px] uppercase tracking-wider mb-1.5 block">Kommentar (valgfri)</label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Tilføj evt. kommentar..."
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm placeholder-slate-500 h-16 resize-none focus:border-orange-500 outline-none"
                data-testid="order-comment"
              />
            </div>

            {/* CO2-type dropdown FJERNET (Fase 9 refactor - 2026-06-18):
                CO2-kategori knyttes nu til materialet (vælges når
                materialet oprettes/redigeres i Step 1). Backend slår
                automatisk CO2-faktoren op via materialets co2_category_id. */}

            <button
              onClick={() => {
                const isWorkshop = tourType === "vaerksted" || tourType === "afhent_vaerksted";
                const isMove = tourType === "flyt";
                if (!isWorkshop && !isMove) {
                  if (!autoFillData.address?.trim()) {
                    toast.error("Leveringsadresse er påkrævet");
                    return;
                  }
                }
                if (isWorkshop) {
                  if (!workshopName.trim() || !workshopAddress.trim()) {
                    toast.error("Værksted er påkrævet (navn + adresse)");
                    return;
                  }
                }
                if (isCustomRequest && !autoFillData.containerId?.trim()) {
                  toast.error("Container-nummer er påkrævet for tilpasset bestilling");
                  return;
                }
                setStep(4);
              }}
              className="w-full py-3 text-base font-black rounded-xl transition-colors flex items-center justify-center gap-2 bg-orange-500 text-white hover:bg-orange-600"
              data-testid="confirm-next-btn"
            >
              Vælg prioritet <ChevronRight className="w-5 h-5" />
            </button>
            </>)}
          </section>
        )}

        {/* STEP 4: Priority Selection */}
        {step === 4 && (
          <section data-testid="step-priority">
            <div className="mb-3 sm:mb-6">
              <h2 className="text-lg sm:text-2xl font-black text-white mb-0.5 sm:mb-1">Vælg prioritet</h2>
              <p className="text-slate-400 text-xs sm:text-base">Hvor hurtigt skal containeren afhentes?</p>
            </div>
            
            <div className="space-y-2 sm:space-y-4 mb-4 sm:mb-8">
              <button
                onClick={() => setPriority("haster")}
                className={`w-full p-3 sm:p-6 rounded-xl sm:rounded-2xl border-2 text-left transition-all flex items-center gap-3 sm:gap-4 ${
                  priority === "haster" 
                    ? "bg-red-500/20 border-red-500 text-white" 
                    : "bg-slate-800 border-slate-700 text-slate-300 hover:border-red-500/50"
                }`}
                data-testid="priority-haster"
              >
                <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-lg sm:rounded-xl flex items-center justify-center shrink-0 ${priority === "haster" ? "bg-red-500" : "bg-slate-700"}`}>
                  <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-black text-base sm:text-xl leading-tight">HASTER</h3>
                  <p className="text-xs sm:text-sm opacity-70 leading-tight">Skal afhentes hurtigst muligt</p>
                </div>
              </button>
              
              <button
                onClick={() => setPriority("normal")}
                className={`w-full p-3 sm:p-6 rounded-xl sm:rounded-2xl border-2 text-left transition-all flex items-center gap-3 sm:gap-4 ${
                  priority === "normal" 
                    ? "bg-orange-500/20 border-orange-500 text-white" 
                    : "bg-slate-800 border-slate-700 text-slate-300 hover:border-orange-500/50"
                }`}
                data-testid="priority-normal"
              >
                <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-lg sm:rounded-xl flex items-center justify-center shrink-0 ${priority === "normal" ? "bg-orange-500" : "bg-slate-700"}`}>
                  <Clock className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-black text-base sm:text-xl leading-tight">NORMAL</h3>
                  <p className="text-xs sm:text-sm opacity-70 leading-tight">Afhentes i løbet af dagen</p>
                </div>
              </button>
              
              <button
                onClick={() => setPriority("senere")}
                className={`w-full p-3 sm:p-6 rounded-xl sm:rounded-2xl border-2 text-left transition-all flex items-center gap-3 sm:gap-4 ${
                  priority === "senere" 
                    ? "bg-blue-500/20 border-blue-500 text-white" 
                    : "bg-slate-800 border-slate-700 text-slate-300 hover:border-blue-500/50"
                }`}
                data-testid="priority-senere"
              >
                <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-lg sm:rounded-xl flex items-center justify-center shrink-0 ${priority === "senere" ? "bg-blue-500" : "bg-slate-700"}`}>
                  <Calendar className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-black text-base sm:text-xl leading-tight">LAV</h3>
                  <p className="text-xs sm:text-sm opacity-70 leading-tight">Kan vente til næste dag</p>
                </div>
              </button>
            </div>

            {/* Order Summary */}
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-3 sm:p-4 mb-3 sm:mb-6">
              <h3 className="text-[10px] sm:text-xs text-slate-400 uppercase tracking-wider mb-2 sm:mb-3">Ordreopsummering</h3>
              <div className="space-y-0.5 sm:space-y-1 text-xs sm:text-sm">
                {tourType !== "normal" && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Opgavetype</span>
                    <span className="text-emerald-400 font-bold">
                      {tourType === "flyt" ? "Byt container"
                       : tourType === "vaerksted" ? "Til værksted"
                       : tourType === "afhent_vaerksted" ? "Afhent fra værksted"
                       : tourType}
                    </span>
                  </div>
                )}
                <div className="flex justify-between"><span className="text-slate-400">Materiale</span><span className="text-white font-bold">{selectedMaterial}</span></div>
                {/* Brugerkrav 2026-06-15: Vis bestillingsdato i ordreopsummering så
                    medarbejderen kan dobbeltbekræfte den planlagte afhentningsdato. */}
                {orderDate && (
                  <div className="flex justify-between" data-testid="summary-order-date">
                    <span className="text-slate-400">Bestillingsdato</span>
                    <span className="text-blue-400 font-bold">
                      {(() => { try { return new Date(orderDate).toLocaleDateString("da-DK", { day: "2-digit", month: "long", year: "numeric" }); } catch (_) { return orderDate; } })()}
                    </span>
                  </div>
                )}
                {/* "Container"-feltet (fx "Container 1") fjernet pr. brugerkrav 2026-06-14 -
                    container-nummer er det eneste container-relaterede felt. */}
                {autoFillData?.containerId && (
                  <div className="flex justify-between"><span className="text-slate-400">Container-nr.</span><span className="text-white font-bold">{autoFillData.containerId}</span></div>
                )}
                {autoFillData?.capacityLabel && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Kapacitetsmål</span>
                    <span className="text-white font-bold">{autoFillData.capacityLabel}{autoFillData.capacityVolumeM3 ? ` (${autoFillData.capacityVolumeM3} m³)` : ""}</span>
                  </div>
                )}
                <div className="flex justify-between"><span className="text-slate-400">Genbrugsplads</span><span className="text-white font-bold">{autoFillData?.genbrugsplads}</span></div>
                {!["flyt", "vaerksted", "afhent_vaerksted"].includes(tourType) && (
                  <div className="flex justify-between"><span className="text-slate-400">Adresse</span><span className="text-white font-bold">{autoFillData?.address}</span></div>
                )}
                {(tourType === "vaerksted" || tourType === "afhent_vaerksted") && workshopName && (
                  <>
                    <div className="flex justify-between"><span className="text-slate-400">Værksted</span><span className="text-white font-bold">{workshopName}</span></div>
                    {workshopAddress && <div className="flex justify-between"><span className="text-slate-400">Adresse</span><span className="text-white font-bold">{workshopAddress}</span></div>}
                    {workshopPhone && <div className="flex justify-between"><span className="text-slate-400">Telefon</span><span className="text-white font-bold">{workshopPhone}</span></div>}
                  </>
                )}
                {/* Brugerkrav 2026-06-15 (runde 10): Vis kommentar i ordreopsummeringen
                    så medarbejderen kan dobbeltbekræfte den inden de trykker "Bestil". */}
                {comment.trim() && (
                  <div className="pt-2 mt-2 border-t border-slate-700/50" data-testid="summary-comment">
                    <div className="text-slate-400 mb-1">Kommentar</div>
                    <div className="text-white text-sm whitespace-pre-wrap break-words">{comment.trim()}</div>
                  </div>
                )}
              </div>
            </div>
            
            <button
              onClick={handleSubmitOrder}
              disabled={submitting}
              className="w-full py-3 sm:py-4 bg-emerald-600 text-white text-base sm:text-lg font-black rounded-xl hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
              data-testid="submit-order-btn"
            >
              {submitting ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Opretter bestilling...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 sm:w-5 sm:h-5" />
                  Bestil afhentning
                </>
              )}
            </button>
          </section>
        )}
          </>
        )}

        {/* ============ ORDER HISTORY VIEW ============ */}
        {view === "history" && (
          <section
            className="py-3 sm:py-4 relative"
            data-testid="order-history-section"
            onTouchStart={(e) => {
              if (window.scrollY === 0 && !historyLoading) {
                pullStartY.current = e.touches[0].clientY;
                setIsPulling(true);
              }
            }}
            onTouchMove={(e) => {
              if (!isPulling) return;
              const delta = e.touches[0].clientY - pullStartY.current;
              if (delta > 0) {
                // Resistance-curve så det føles naturligt
                setPullDistance(Math.min(delta * 0.5, 100));
              }
            }}
            onTouchEnd={() => {
              if (!isPulling) return;
              if (pullDistance >= PULL_THRESHOLD) {
                fetchOrderHistory(historyDate, historyMode);
              }
              setIsPulling(false);
              setPullDistance(0);
            }}
            style={{ transform: pullDistance > 0 ? `translateY(${pullDistance}px)` : undefined, transition: isPulling ? "none" : "transform 200ms ease-out" }}
          >
            {/* Pull-to-refresh indikator (Fase 18.28) - kun synlig under pull-gesten */}
            {pullDistance > 0 && (
              <div
                className="sm:hidden absolute left-0 right-0 flex items-center justify-center pointer-events-none"
                style={{ top: -50, height: 50 }}
              >
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-xs font-bold ${pullDistance >= PULL_THRESHOLD ? "text-emerald-400" : "text-slate-400"}`}>
                  <RotateCcw className={`w-3.5 h-3.5 ${pullDistance >= PULL_THRESHOLD ? "animate-spin" : ""}`} style={{ transform: pullDistance < PULL_THRESHOLD ? `rotate(${pullDistance * 4}deg)` : undefined }} />
                  {pullDistance >= PULL_THRESHOLD ? "Slip for at opdatere" : "Træk for at opdatere"}
                </div>
              </div>
            )}
            {/* Mode toggle + uafhængige filtre (brugerkrav 2026-06-15):
                "day" - datovælger aktiv, kun den valgte dag vises (alle statuser).
                "all" - alle bestillinger uafhængigt af dato (fuldførte skjules som standard).
                Fase 18.27 (mobil-redesign): På mobil vises Pr.dato/Alle som
                fuld-bredde segmented control; filtre stables på egne rækker. */}

            {/* Pr. dato / Alle afventende - mobil: fuld-bredde segmented control */}
            <div className="flex sm:hidden bg-slate-800/80 p-1 rounded-lg border border-slate-700/50 mb-2" data-testid="history-mode-toggle-mobile">
              <button onClick={() => { setHistoryMode("day"); }}
                className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-bold transition-all ${historyMode === "day" ? "bg-orange-500 text-white shadow-sm" : "text-slate-300 hover:text-white"}`}
                data-testid="history-mode-day-mobile">
                <Calendar className="w-3.5 h-3.5" /> Pr. dato
              </button>
              <button onClick={() => { setHistoryMode("all"); }}
                className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-bold transition-all ${historyMode === "all" ? "bg-orange-500 text-white shadow-sm" : "text-slate-300 hover:text-white"}`}
                data-testid="history-mode-all-mobile">
                Alle afventende
              </button>
            </div>

            {/* Desktop: original flex-wrap layout */}
            <div className="hidden sm:flex flex-wrap items-center gap-2 mb-4" data-testid="history-mode-toggle">
              <button onClick={() => { setHistoryMode("day"); }}
                className={`px-4 py-2 rounded-lg text-sm font-bold ${historyMode === "day" ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
                data-testid="history-mode-day">
                <Calendar className="w-4 h-4 inline -mt-0.5 mr-1.5" />
                Pr. dato
              </button>
              <button onClick={() => { setHistoryMode("all"); }}
                className={`px-4 py-2 rounded-lg text-sm font-bold ${historyMode === "all" ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
                data-testid="history-mode-all">
                Alle afventende
              </button>
            </div>

            {/* Date navigation - kompakt venstre-justeret. "I dag"/"I går"
                placeret inline ved siden af dato-feltet (Fase 18.25).
                Mobil (Fase 18.27): dato-input fylder hele bredden, quick-knapper
                som chips nedenunder. */}
            {historyMode === "day" && (
            <>
            {/* Mobil-version (Fase 18.29) - kompakt og firkantet: dato-input
                fylder kun nødvendig plads, I dag/I går som firkantede knapper
                i samme række. Weekday-tekst rykker ned med god luft. */}
            <div className="sm:hidden mb-2">
              <div className="flex items-stretch gap-1.5 mb-1.5">
                <button onClick={() => changeHistoryDate(-1)}
                  className="px-2.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-white" data-testid="history-prev-mobile"
                  title="Forrige dag">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <input type="date" value={historyDate} onChange={(e) => setHistoryDate(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-white text-xs focus:border-orange-500 outline-none min-w-0"
                  data-testid="history-date-picker-mobile"
                  style={{ width: 130 }}
                />
                <button onClick={() => changeHistoryDate(1)}
                  className="px-2.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-white" data-testid="history-next-mobile"
                  title="Næste dag">
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button onClick={() => setHistoryDate(localDateStr())}
                  className={`flex-1 px-2 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${historyDate === localDateStr() ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}
                  data-testid="history-today-mobile">I dag</button>
                <button onClick={() => { const d = new Date(); d.setDate(d.getDate() - 1); setHistoryDate(localDateStr(d)); }}
                  className={`flex-1 px-2 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${historyDate === (() => { const d = new Date(); d.setDate(d.getDate() - 1); return localDateStr(d); })() ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}
                  data-testid="history-yesterday-mobile">I går</button>
              </div>
              <p className="text-slate-400 text-[11px] capitalize px-1 truncate">
                {new Date(historyDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" })}
              </p>
            </div>
            {/* Desktop-version */}
            <div className="hidden sm:flex items-center gap-2 mb-4 flex-wrap">
              <button onClick={() => changeHistoryDate(-1)}
                className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-white" data-testid="history-prev"
                title="Forrige dag">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <input type="date" value={historyDate} onChange={(e) => setHistoryDate(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white text-sm focus:border-orange-500 outline-none"
                data-testid="history-date-picker" />
              <button onClick={() => changeHistoryDate(1)}
                className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-white" data-testid="history-next"
                title="Næste dag">
                <ChevronRight className="w-4 h-4" />
              </button>
              {/* Quick-date knapper - placeret inline (Fase 18.25) */}
              <button onClick={() => setHistoryDate(localDateStr())}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${historyDate === localDateStr() ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
                data-testid="history-today">I dag</button>
              <button onClick={() => { const d = new Date(); d.setDate(d.getDate() - 1); setHistoryDate(localDateStr(d)); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${historyDate === (() => { const d = new Date(); d.setDate(d.getDate() - 1); return localDateStr(d); })() ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
                data-testid="history-yesterday">I går</button>
              <span className="text-slate-400 text-xs capitalize ml-1">
                {new Date(historyDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
              </span>
            </div>
            </>
            )}

            {/* Fase 18.33: "Mine"/"Alle bestillinger" scope-toggle er fjernet.
                historyScope er låst til "all" - alle bestillinger på lokationen vises altid.
                Desktop "Inkludér estimater"-toggle bevares til højre. */}
            <div className="hidden sm:flex justify-end mb-4">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60">
                <FileText className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-semibold text-slate-300">Inkludér estimater</span>
                {includeEstimates && (
                  <span className="px-1.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider bg-amber-500 text-slate-900" data-testid="include-estimates-active">
                    Nederst
                  </span>
                )}
                <button
                  role="switch"
                  aria-checked={includeEstimates}
                  onClick={() => setIncludeEstimates(v => !v)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400 ${includeEstimates ? "bg-amber-500" : "bg-slate-600"}`}
                  data-testid="include-estimates-toggle"
                  title={includeEstimates ? "Skjul estimater" : "Vis estimater"}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${includeEstimates ? "translate-x-4" : "translate-x-1"}`}
                  />
                </button>
              </div>
            </div>

            {/* Mobil-handlings-række (Fase 18.32) - placeret lige over
                bestillingerne. Indeholder: "Inkludér færdige ture" (kun i "Pr. dato"
                mode), "Inkludér estimater", samt lille refresh-ikon.
                Alle tre med samme diskrete subtle-ring stil. */}
            <div className="sm:hidden flex items-center justify-end gap-1.5 mb-2 flex-wrap">
              {historyMode === "day" && (
                <button
                  onClick={() => setHideCompleted(h => !h)}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-bold transition-colors ${!hideCompleted ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40" : "text-slate-500 ring-1 ring-slate-700 hover:text-slate-300"}`}
                  data-testid="history-hide-completed-toggle-mobile"
                  title={hideCompleted ? "Klik for at vise færdige ture" : "Klik for at skjule færdige ture"}>
                  <CheckCircle2 className="w-3 h-3" /> {!hideCompleted ? "Færdige ture vises" : "Inkludér færdige ture"}
                </button>
              )}
              <button
                onClick={() => setIncludeEstimates(v => !v)}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-bold transition-colors ${includeEstimates ? "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/40" : "text-slate-500 ring-1 ring-slate-700 hover:text-slate-300"}`}
                data-testid="include-estimates-toggle-mobile">
                <FileText className="w-3 h-3" /> {includeEstimates ? "Estimater vises" : "Inkludér estimater"}
              </button>
              <button
                onClick={() => fetchOrderHistory(historyDate, historyMode)}
                className="inline-flex items-center justify-center p-1 text-slate-500 hover:text-slate-300"
                data-testid="history-refresh-mobile"
                title="Genindlæs">
                <RotateCcw className={`w-4 h-4 ${historyLoading ? "animate-spin" : ""}`} />
              </button>
            </div>

            {historyLoading && (
              <div className="text-center py-12">
                <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-slate-400">Indlæser bestillinger...</p>
              </div>
            )}

            {!historyLoading && visibleHistory.length === 0 && (
              <div className="text-center py-12 bg-slate-800/50 rounded-2xl">
                <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600" />
                <p className="text-slate-400 font-bold">
                  {orderHistory.length === 0
                    ? (historyMode === "all" ? "Ingen bestillinger fundet" : "Ingen bestillinger denne dag")
                    : (pendingOnly ? "Ingen afventende bestillinger" : "Du har ikke lavet nogen bestillinger her")}
                </p>
                <p className="text-slate-500 text-sm mt-1">
                  {pendingOnly
                    ? "Fjern \"Filtrér på afventende\" for at se alle bestillinger"
                    : (historyMode === "all"
                        ? "Skift til Pr. dato eller opret en ny bestilling"
                        : "Vælg en anden dato eller opret en ny bestilling")}
                </p>
              </div>
            )}

            {!historyLoading && visibleHistory.length > 0 && (
              <div className="space-y-2 sm:space-y-3">
                <div className="flex items-center justify-between gap-2 mb-1 sm:mb-2">
                  <h2 className="text-base sm:text-lg font-black text-white">{visibleHistory.length} bestilling{visibleHistory.length !== 1 ? "er" : ""}</h2>
                  <span className="hidden sm:inline text-xs text-slate-500">
                    {historyScope === "mine" ? "Mine bestillinger" : "Alle på denne lokation"}
                    {historyMode === "all" && " · alle datoer"}
                    {pendingOnly && " · kun afventende"}
                    {hideCompleted && !pendingOnly && historyMode !== "all" && " · uden fuldførte"}
                  </span>
                </div>
                <div className="rounded-xl border border-slate-700/70 bg-slate-800/40 overflow-hidden divide-y divide-slate-700/50" data-testid="history-list">
                {visibleHistory.map((order, idx) => {
                  const canEdit = !order.claimed_by && !order.on_way && !order.completed;
                  // Fase 15.18 (2026-02-21): Estimat-bestillinger har ingen
                  // status/opgavetype/afhentes/container-nr - det er et
                  // forventet ressourcebehov, ikke en konkret opgave.
                  const isEstimat = (order.tour_type || "") === "estimat";
                  // Fase 15.18 (2026-02-21): "Tilpasset bestilling" detekteres
                  // via container_number === "Tilpasset bestilling" (opgave)
                  // eller tour_type === "estimat" (estimat).
                  const isCustom = isEstimat || (order.container_number === "Tilpasset bestilling");
                  const isExpanded = expandedHistoryId === (order.id || idx);
                  const statusLabel = isEstimat ? "Estimat" : order.completed ? "Færdig" : order.on_way ? "På vej" : order.claimed_by ? "Påbegyndt" : "Afventer";
                  const statusColor = isEstimat ? "amber" : order.completed ? "emerald" : order.on_way ? "yellow" : order.claimed_by ? "blue" : "slate";
                  const tourTypeLabel = (() => {
                    const tt = order.tour_type || "normal";
                    if (tt === "flyt") return "Flyt";
                    if (tt === "vaerksted") return "Til værksted";
                    if (tt === "afhent_vaerksted") return "Værksted retur";
                    if (tt === "loes_afhentning") return "Løs afhentning";
                    if (tt === "estimat") return "Estimat";
                    return "Afhent";
                  })();
                  const priorityLabel = (order.priority || "normal").toString();
                  const priorityColor = priorityLabel.toLowerCase().includes("hast") || priorityLabel.toLowerCase() === "urgent" ? "red" : priorityLabel.toLowerCase() === "low" ? "slate" : "slate";
                  const containerNr = order.container_id_override || order.container_id_resolved || order.custom_container_id || order.container_id || "-";
                  const orderDate = order.order_date ? _fmtDateDM(order.order_date) : "-";
                  const createdDate = order.created_at ? new Date(order.created_at).toLocaleDateString("da-DK", { day: "numeric", month: "short" }) : "-";
                  return (
                  <div
                    key={order.id || idx}
                    className={`transition-colors ${
                      isExpanded
                        ? (isEstimat ? "bg-amber-950/20" : isCustom ? "bg-purple-950/15" : "bg-slate-800/80")
                        : "hover:bg-slate-800/50"
                    }`}
                    data-testid={`history-order-${idx}`}
                  >
                    {/* List-række (kompakt header - altid synlig). Klik toggle udvider. */}
                    <button
                      type="button"
                      onClick={() => setExpandedHistoryId(isExpanded ? null : (order.id || idx))}
                      className="w-full text-left px-3.5 py-2.5 flex items-center gap-3"
                      data-testid={`history-row-${idx}`}
                      aria-expanded={isExpanded}
                    >
                      {/* Status ikon */}
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ring-1 bg-${statusColor}-500/15 ring-${statusColor}-500/30`}>
                        {isEstimat ? <FileText className="w-3.5 h-3.5 text-amber-400" /> :
                         order.completed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> :
                         order.on_way ? <Truck className="w-3.5 h-3.5 text-yellow-400" /> :
                         order.claimed_by ? <Users className="w-3.5 h-3.5 text-blue-400" /> :
                         <Clock className="w-3.5 h-3.5 text-slate-400" />}
                      </div>
                      {/* Material + container-nr - mobil: fylder hele rækken (flex-1),
                          desktop: fast 24% bredde. */}
                      <div className="min-w-0 flex-1 sm:flex-none sm:w-[24%] sm:flex-shrink-0">
                        <p className="text-white font-bold text-sm truncate leading-tight">{order.material}</p>
                        <p className="text-slate-500 text-[11px] truncate">Container {containerNr}</p>
                      </div>
                      {/* Opgavetype + prioritet */}
                      <div className="hidden sm:block min-w-0 flex-shrink-0" style={{ width: '20%' }}>
                        <p className="text-slate-300 text-xs truncate">{tourTypeLabel}</p>
                        <p className={`text-[11px] truncate ${priorityColor === "red" ? "text-red-400 font-bold" : "text-slate-500"}`}>{priorityLabel}</p>
                      </div>
                      {/* Datoer */}
                      <div className="hidden md:block min-w-0 flex-shrink-0" style={{ width: '20%' }}>
                        <p className="text-slate-300 text-xs truncate">Oprettet {createdDate}</p>
                        <p className="text-slate-500 text-[11px] truncate">Bestilt {orderDate}</p>
                      </div>
                      {/* Status badge - mobil: shrink-0 så material+container får plads.
                          Desktop: flex-1 så badge højre-justeres pænt. */}
                      <div className="flex-shrink-0 sm:flex-1 flex items-center justify-end gap-2 min-w-0">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-${statusColor}-500/20 text-${statusColor}-300`}>{statusLabel}</span>
                        <ChevronDown className={`w-4 h-4 text-slate-500 flex-shrink-0 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                      </div>
                    </button>

                    {/* Detail-view som modal popup. Vises kun ved klik på rækken;
                        lukker ved klik på backdrop eller X-knap. */}
                    <div
                      onClick={() => setExpandedHistoryId(null)}
                      className={`${isExpanded ? "" : "hidden"} fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 bg-black/70 backdrop-blur-sm`}
                      data-testid={`history-modal-backdrop-${idx}`}
                    >
                    <div
                      onClick={(e) => e.stopPropagation()}
                      className={`relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-slate-900 rounded-2xl shadow-2xl border ${
                        isEstimat
                          ? "border-amber-500/50 ring-1 ring-amber-500/20"
                          : isCustom
                            ? "border-purple-500/50 ring-1 ring-purple-500/20"
                            : "border-slate-700"
                      } px-4 py-4`}
                      data-testid={`history-expanded-${idx}`}
                    >
                      {/* Close button */}
                      <button
                        onClick={() => setExpandedHistoryId(null)}
                        className="absolute top-3 right-3 w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-white transition-colors z-10"
                        data-testid={`history-modal-close-${idx}`}
                        title="Luk"
                      >
                        <XCircle className="w-4 h-4" />
                      </button>
                    <div className="flex items-start justify-between mb-2.5">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ring-1 ${
                          isEstimat ? "bg-amber-500/15 ring-amber-500/30" :
                          order.completed ? "bg-emerald-500/15 ring-emerald-500/30" : order.on_way ? "bg-yellow-500/15 ring-yellow-500/30" : order.claimed_by ? "bg-blue-500/15 ring-blue-500/30" : "bg-slate-700/60 ring-slate-600/40"
                        }`}>
                          {isEstimat ? (
                            <FileText className="w-4 h-4 text-amber-400" />
                          ) : order.completed ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          ) : order.on_way ? (
                            <Truck className="w-4 h-4 text-yellow-400" />
                          ) : order.claimed_by ? (
                            <Users className="w-4 h-4 text-blue-400" />
                          ) : (
                            <Clock className="w-4 h-4 text-slate-400" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-white font-bold text-sm leading-tight">{order.material}</h3>
                            {/* Fase 15.18 (2026-02-21): Badges for tilpassede bestillinger. */}
                            {isEstimat && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-500 text-slate-900" data-testid={`order-badge-estimat-${idx}`}>
                                Estimat
                              </span>
                            )}
                            {isCustom && !isEstimat && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-purple-500 text-white" data-testid={`order-badge-custom-${idx}`}>
                                Tilpasset
                              </span>
                            )}
                          </div>
                          {/* Container-nr - vis IKKE for estimat */}
                          {!isEstimat && (
                            <p className="text-slate-400 text-sm">
                              {(order.container_id_override || order.container_id_resolved || order.custom_container_id || order.container_id)
                                ? <>Container-nr. <span className="text-slate-300 font-semibold">{order.container_id_override || order.container_id_resolved || order.custom_container_id || order.container_id}</span></>
                                : <span className="italic">Container-nr. ikke angivet</span>}
                            </p>
                          )}
                          {/* Info-blok - for estimat vises kun "Bestilt kl" + "Bestilt af". */}
                          <div className="mt-1.5">
                            {isEstimat ? (
                              <div className="flex flex-wrap items-center gap-y-1 text-[11px] text-slate-200" data-testid={`order-info-line-${idx}`}>
                                {order.order_date && (
                                  <span className="inline-flex items-center gap-1" title="Bestillingsdato (planlagt udførelse)">
                                    <Calendar className="w-3 h-3 text-blue-500" />
                                    <span className="text-slate-400">Bestillingsdato</span>
                                    <span className="font-semibold">{_fmtDateDM(order.order_date)}</span>
                                  </span>
                                )}
                                {(order.created_by_name || order.created_by_email) && (
                                  <>
                                    {order.order_date && <span className="mx-1.5 text-slate-500">·</span>}
                                    <span className="inline-flex items-center gap-1" title="Bestilt af">
                                      <Users className="w-3 h-3 text-blue-500" />
                                      <span className="text-slate-400">Bestilt af</span>
                                      <span className="font-semibold">{order.created_by_name || order.created_by_email}</span>
                                    </span>
                                  </>
                                )}
                              </div>
                            ) : (
                              <OrderInfoLine order={order} dark testid={`order-info-line-${idx}`} />
                            )}
                          </div>
                          {!isEstimat && historyScope === "all" && (order.created_by_name || order.created_by_email) && (
                            <p className="text-emerald-400 text-[11px] mt-1" data-testid={`order-created-by-${idx}`}>
                              Bestilt af {order.created_by_name || order.created_by_email}
                            </p>
                          )}
                        </div>
                      </div>
                      {/* Status-badge - vis IKKE for estimat.
                          Fase 18.25: mr-10 så badge ikke overlapper X-knap. */}
                      {!isEstimat && (
                        <div className="flex items-center gap-1.5 mr-10 flex-shrink-0">
                          <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase whitespace-nowrap ${
                            order.completed ? "bg-emerald-500/20 text-emerald-400" :
                            order.on_way ? "bg-yellow-500/20 text-yellow-400" :
                            order.claimed_by ? "bg-blue-500/20 text-blue-400" :
                            "bg-orange-500/20 text-orange-400"
                          }`} data-testid={`order-status-${idx}`}>
                            {order.completed ? "Fuldført" : order.on_way ? "På vej" : order.claimed_by ? "Taget" : "Afventer"}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    {/* Driver info - vises IKKE for estimat (ingen status). */}
                    {!isEstimat && (order.claimed_by || order.on_way || order.completed) && (
                      <div className="mb-3 p-2 bg-slate-900/50 rounded-lg">
                        <div className="flex items-center gap-2 text-sm">
                          <Users className="w-4 h-4 text-slate-400" />
                          <span className="text-slate-400">Chauffør:</span>
                          <span className="text-white font-bold">{order.claimed_by || order.driver_name || "-"}</span>
                        </div>
                        {order.claimed_at && (
                          <div className="flex items-center gap-2 text-sm mt-1">
                            <Users className="w-4 h-4 text-blue-400" />
                            <span className="text-slate-400">Taget:</span>
                            <span className="text-blue-400 font-bold">
                              {(() => { try { return new Date(order.claimed_at).toLocaleString("da-DK", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); } catch (_) { return order.claimed_at; } })()}
                            </span>
                          </div>
                        )}
                        {order.on_way_time && (
                          <div className="flex items-center gap-2 text-sm mt-1">
                            <Clock className="w-4 h-4 text-yellow-500" />
                            <span className="text-slate-400">Startet:</span>
                            <span className="text-yellow-400 font-bold">{order.on_way_time}</span>
                          </div>
                        )}
                        {order.time && order.completed && (
                          <div className="flex items-center gap-2 text-sm mt-1">
                            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                            <span className="text-slate-400">Færdig:</span>
                            <span className="text-emerald-400 font-bold">{order.time}</span>
                          </div>
                        )}
                      </div>
                    )}
                    
                    {isEstimat ? (
                      /* Fase 15.18 (2026-02-21): Estimat-visning - KUN
                         Adresse, Antal containere estimeret, Kommentar (hvis
                         brugeren har skrevet noget). Ingen prioritet/opgavetype/
                         status/container-nr/CO2/vægt. */
                      <div className="grid grid-cols-2 gap-2 text-sm" data-testid={`estimat-order-fields-${idx}`}>
                        <div>
                          <span className="text-slate-500">Adresse:</span>
                          <span className="text-white ml-2">{order.customer_address || order.address || "-"}</span>
                        </div>
                        <div data-testid={`estimat-order-count-${idx}`}>
                          <span className="text-slate-500">Antal containere estimeret:</span>
                          <span className="ml-2 font-black text-amber-300 text-base">
                            {Number(order.estimated_count || 0)}
                          </span>
                        </div>
                        {(order.comment || "").trim() && (
                          <div className="col-span-2">
                            <span className="text-slate-500">Kommentar:</span>
                            <span className="text-white ml-2">{order.comment}</span>
                          </div>
                        )}
                        <div className="col-span-2 text-xs text-slate-500 mt-1">
                          Oprettet: {order.created_at ? new Date(order.created_at).toLocaleString("da-DK") : "-"}
                        </div>
                      </div>
                    ) : (
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-slate-500">Adresse:</span>
                        <span className="text-white ml-2">{order.customer_address || order.address || "-"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Prioritet:</span>
                        <span className={`ml-2 font-bold uppercase ${
                          order.priority === "haster" ? "text-red-400" : order.priority === "senere" ? "text-blue-400" : "text-orange-400"
                        }`}>{order.priority}</span>
                      </div>
                      <div data-testid={`order-tour-type-${idx}`}>
                        <span className="text-slate-500">Opgavetype:</span>
                        <span className="text-white ml-2 font-semibold">
                          {(() => {
                            const tt = order.tour_type || "normal";
                            if (tt === "vaerksted") return "Til værksted";
                            if (tt === "afhent_vaerksted") return "Afhent fra værksted";
                            if (tt === "flyt") return "Flyt container";
                            if (tt === "loes_afhentning") return "Løs afhentning";
                            if (tt === "estimat") return "Estimat";
                            return "Normal afhentning";
                          })()}
                        </span>
                      </div>
                      {order.container_id && (
                        <div>
                          <span className="text-slate-500">Container-nr:</span>
                          <span className="text-white ml-2">{order.container_id}</span>
                        </div>
                      )}
                      {/* Fase 9 (2026-06-17): CO2-type + Vægt + Beregnet CO2.
                          Vægt udfyldes IKKE ved oprettelse - den lander fra chaufførens kvittering.
                          CO2 beregnes automatisk: faktor × (vægt_kg ÷ 1000).
                          Fase 11 (2026-06-18): Vises KUN for opgavetype 'normal' (afhent
                          container). De øvrige typer har hverken vægt eller CO2.
                          Fase 15.44 (2026-02-22): Også 'loes_afhentning' har CO2 + vægt - kunden
                          ønsker at se besparelsen i deres rapport selvom de ikke ejer containerne. */}
                      {((order.tour_type || "normal") === "normal" || (order.tour_type || "normal") === "loes_afhentning") && (order.co2_type_name || order.weight_kg > 0) && (
                        <>
                          {order.co2_type_name && (
                            <div>
                              <span className="text-slate-500">CO2-type:</span>
                              <span className="text-emerald-300 ml-2 font-semibold inline-flex items-center gap-1">
                                <Leaf className="w-3 h-3" /> {order.co2_type_name}
                                <span className="text-slate-400 text-xs font-normal">({(order.co2_factor || 0).toLocaleString("da-DK")} kg/ton)</span>
                              </span>
                            </div>
                          )}
                          <div>
                            <span className="text-slate-500">Vægt (kg):</span>
                            {order.weight_kg > 0
                              ? <span className="text-white ml-2 font-bold">{order.weight_kg.toLocaleString("da-DK")} kg</span>
                              : <span className="text-slate-500 ml-2 italic">afventer chauffør</span>}
                          </div>
                          <div>
                            <span className="text-slate-500">CO2:</span>
                            {order.co2_kg > 0
                              ? <span className="text-emerald-400 ml-2 font-bold inline-flex items-center gap-1"><Leaf className="w-3 h-3" /> {order.co2_kg.toLocaleString("da-DK")} kg</span>
                              : (order.co2_factor === 0 && order.weight_kg > 0
                                  ? <span className="text-slate-400 ml-2 font-bold">0 kg <span className="text-xs font-normal">(faktor=0)</span></span>
                                  : <span className="text-slate-500 ml-2 italic">beregnes automatisk</span>)
                            }
                          </div>
                        </>
                      )}
                      {order.comment && (
                        <div className="col-span-2">
                          <span className="text-slate-500">Kommentar:</span>
                          <span className="text-white ml-2">{order.comment}</span>
                        </div>
                      )}
                      <div className="col-span-2 text-xs text-slate-500 mt-1">
                        Oprettet: {order.created_at ? new Date(order.created_at).toLocaleString("da-DK") : "-"}
                      </div>
                    </div>
                    )}

                    {/* Action knapper - vises kun for ordrer der endnu ikke er
                        afhentet/i gang (Batch 2). */}
                    <div className="mt-3 pt-3 border-t border-slate-700 flex flex-wrap gap-2">
                      <button onClick={() => setAuditOrder({ order, entries: null })}
                        className="text-[11px] inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-300 font-bold"
                        data-testid={`order-history-btn-${idx}`}>
                        <History className="w-3 h-3" /> Historik
                      </button>
                      {canEdit && (
                        <>
                          <button onClick={() => setEditingOrder(order)}
                            className="text-[11px] inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 font-bold"
                            data-testid={`order-edit-btn-${idx}`}>
                            <Edit2 className="w-3 h-3" /> Redigér
                          </button>
                          <button onClick={() => setConfirmDeleteOrder(order)}
                            className="text-[11px] inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 font-bold"
                            data-testid={`order-cancel-btn-${idx}`}>
                            <XCircle className="w-3 h-3" /> Annullér
                          </button>
                        </>
                      )}
                      {!canEdit && (
                        <span className="text-[11px] text-slate-500 italic">
                          Bestillingen er allerede påbegyndt - kan ikke redigeres/slettes
                        </span>
                      )}
                    </div>
                  </div>
                  </div>
                  </div>
                  );
                })}
                </div>
              </div>
            )}
          </section>
        )}
      </main>

      {/* Mine bestillinger - Edit modal */}
      {editingOrder && (
        <OrderEditModal
          order={editingOrder}
          onClose={() => setEditingOrder(null)}
          onSaved={() => {
            setEditingOrder(null);
            fetchOrderHistory(historyDate);
          }}
        />
      )}

      {/* Mine bestillinger - Cancel confirm modal (Fase 15.51) */}
      {confirmDeleteOrder && (
        <OrderCancelConfirmModal
          order={confirmDeleteOrder}
          onCancel={() => setConfirmDeleteOrder(null)}
          onDeleted={() => {
            setConfirmDeleteOrder(null);
            fetchOrderHistory(historyDate);
          }}
        />
      )}

      {/* Mine bestillinger - Audit history modal */}
      {auditOrder && (
        <OrderAuditModal
          order={auditOrder.order}
          onClose={() => setAuditOrder(null)}
        />
      )}

      {/* Container "Rediger" base-definition modal */}
      {editingContainer && (
        <ContainerEditModal
          container={editingContainer}
          locationCode={locationCode}
          material={selectedMaterial}
          adminMode={adminMode}
          onClose={() => setEditingContainer(null)}
          onSaved={async () => {
            try {
              const pq = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
              const res = await axios.get(`${API}/locations/${locationCode}/containers?material=${encodeURIComponent(selectedMaterial)}${pq}`);
              setContainers(res.data.containers || []);
            } catch (e) { /* ignore */ }
            setEditingContainer(null);
          }}
        />
      )}

      {/* Soft-confirm: "+ Tilføj container" (admin) */}
      {confirmAddContainer && (
        <SoftConfirmModal
          title="Tilføj ny container?"
          message={<>En ny tom container tilføjes til materialet <strong>{selectedMaterial}</strong>. Du kan udfylde leveringsadresse og container-nummer bagefter via Rediger-knappen.</>}
          confirmLabel="Tilføj container"
          variant="emerald"
          onCancel={() => setConfirmAddContainer(false)}
          onConfirm={async () => {
            setConfirmAddContainer(false);
            try {
              const pq = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
              await axios.post(`${API}/locations/${locationCode}/containers/add`, { material: selectedMaterial, partner_id: partnerId });
              const res = await axios.get(`${API}/locations/${locationCode}/containers?material=${encodeURIComponent(selectedMaterial)}${pq}`);
              setContainers(res.data.containers || []);
              toast.success("Container tilføjet");
            } catch (e) {
              toast.error(e.response?.data?.detail || "Kunne ikke tilføje container");
            }
          }}
        />
      )}

      {/* Soft-confirm: slet container (admin) */}
      {confirmDeleteContainer && (
        <SoftConfirmModal
          title={`Slet ${confirmDeleteContainer.label}?`}
          message={<>Dette fjerner containeren fra <strong>{selectedMaterial}</strong>. Eksisterende bestillinger med denne container påvirkes ikke. Handlingen kan ikke fortrydes.</>}
          confirmLabel="Slet container"
          variant="red"
          onCancel={() => setConfirmDeleteContainer(null)}
          onConfirm={async () => {
            const target = confirmDeleteContainer;
            setConfirmDeleteContainer(null);
            try {
              const pq = partnerId ? `&partner_id=${encodeURIComponent(partnerId)}` : "";
              await axios.delete(`${API}/locations/${locationCode}/containers/slot?material=${encodeURIComponent(selectedMaterial)}&container_label=${encodeURIComponent(target.label)}${pq}`);
              const res = await axios.get(`${API}/locations/${locationCode}/containers?material=${encodeURIComponent(selectedMaterial)}${pq}`);
              setContainers(res.data.containers || []);
              toast.success("Container slettet");
            } catch (e) {
              toast.error(e.response?.data?.detail || "Kunne ikke slette container");
            }
          }}
        />
      )}

      {/* Soft-confirm: slet materiale (admin) */}
      {confirmDeleteMaterialName && (
        <SoftConfirmModal
          title="Slet materiale?"
          message={<>Er du sikker på at du vil slette <strong>{confirmDeleteMaterialName}</strong> fra listen?</>}
          confirmLabel="Slet materiale"
          variant="red"
          onCancel={() => setConfirmDeleteMaterialName(null)}
          onConfirm={performDeleteMaterial}
        />
      )}
    </div>
  );
};


/* ============================ ORDER EDIT MODAL (Batch 2) ============================ */
// Fase 15 (2026-06-19): Modal opfører sig nu identisk med "Bekræft og rediger"-
// step ved oprettelse. Felter vises/skjules dynamisk efter opgavetype:
//   - Afhentning / Byt container → leveringsadresse (custom_address)
//   - Til værksted / Afhent fra værksted → værksted-snapshot (navn/adresse/tlf)
// Ved typeskift vises en soft-validation: "Skifter du opgavetype slettes …".
// Når brugeren bekræfter, sendes tomme værdier til de irrelevante felter så
// backend rydder dem (audit log dækker hver feltændring).
const OrderEditModal = ({ order, onClose, onSaved }) => {
  // Fase 15.20 (2026-02-21): Estimat-bestillinger har et kraftigt reduceret
  // felt-set i edit-modalen - kun Materiale, Antal containere estimeret,
  // Bestillingsdato og Kommentar er redigerbare. Resten skjules helt.
  // Fase 15.44 (2026-02-22): Samme princip for `loes_afhentning` - kunden
  // kan justere prioritet, dato, antal og kommentar, men IKKE skifte type
  // (det ville ugyldiggøre flowet - chaufføren har en helt anden completion-
  // UI for løse afhentninger).
  const isEstimat = (order.tour_type || "") === "estimat";
  const isLoes = (order.tour_type || "") === "loes_afhentning";
  const [priority, setPriority] = useState(order.priority || "normal");
  const [comment, setComment] = useState(order.comment || "");
  const [orderDate, setOrderDate] = useState(order.order_date || "");
  const [tourType, setTourType] = useState(order.tour_type || "normal");
  // Estimat-felter
  const [material, setMaterial] = useState(order.material || order.fraction || "");
  const [estimatedCount, setEstimatedCount] = useState(String(order.estimated_count || ""));
  // Fase 15.44 (2026-02-22): Løs afhentning-antal (loose_estimated_count).
  const [looseCount, setLooseCount] = useState(String(order.loose_estimated_count || ""));
  // Delivery address (kun for normal/flyt)
  const [customAddress, setCustomAddress] = useState(order.custom_address || "");
  // Workshop snapshot (kun for vaerksted/afhent_vaerksted)
  const [workshopId, setWorkshopId] = useState(order.workshop_id || "");
  const [workshopName, setWorkshopName] = useState(order.workshop_name || "");
  const [workshopAddress, setWorkshopAddress] = useState(order.workshop_address || "");
  const [workshopPhone, setWorkshopPhone] = useState(order.workshop_phone || "");
  const [workshops, setWorkshops] = useState([]);
  const [saving, setSaving] = useState(false);
  // Soft-validation dialog state
  const [pendingTypeChange, setPendingTypeChange] = useState(null); // { from, to, fieldsToClear: [...] }
  // Original type - bruges til at vise ændringer i save-payload
  const originalType = order.tour_type || "normal";

  useEffect(() => {
    // Hent værkstedsbiblioteket - kun nødvendigt hvis brugeren skifter til
    // et værksted-flow, men fetcher altid for at undgå tomme dropdowns.
    axios.get(`${API}/org/workshops`).then(r => setWorkshops(r.data || [])).catch(() => {});
  }, []);

  const isWorkshopType = (t) => t === "vaerksted" || t === "afhent_vaerksted";
  // Fase 15.1 (2026-06-19): "Byt container" (flyt) skal vise HVERKEN
  // leveringsadresse ELLER værksted-felter (kun container-byt-info).
  const isFlytType     = (t) => t === "flyt";
  const showAddress    = !isWorkshopType(tourType) && !isFlytType(tourType);
  const showWorkshop   = isWorkshopType(tourType);

  // Beregn hvilke felter vil blive ryddet ved typeskift (til soft-validation)
  const getFieldsToClear = (from, to) => {
    const fromWs    = isWorkshopType(from);
    const toWs      = isWorkshopType(to);
    const fromFlyt  = isFlytType(from);
    const toFlyt    = isFlytType(to);
    const fromShowsAddr = !fromWs && !fromFlyt;
    const toShowsAddr   = !toWs   && !toFlyt;
    const cleared = [];
    if (fromWs && !toWs) cleared.push("Værksted (navn, adresse, telefon)");
    if (fromShowsAddr && !toShowsAddr) cleared.push("Leveringsadresse");
    return cleared;
  };

  // Fase 15 (2026-06-19) + Fase 15.1 (2026-06-19): Felter skifter ØJEBLIKKELIGT
  // ved on-change; soft-validation udskydes til Gem (se save() nedenfor).
  const handleTypeChange = (newType) => {
    if (newType === tourType) return;
    setTourType(newType);
  };

  const confirmTypeChange = () => {
    // Brugeren accepterer at irrelevante felter ryddes - kør save() igen
    // uden at vise dialogen denne gang. Vi sætter en flag-state der bypasser
    // dialogen i save().
    const next = pendingTypeChange;
    setPendingTypeChange(null);
    // Ring save() direkte med "force=true" semantik via state
    _doSave(true);
    // next er kun til debug - selve felt-vipningen er allerede sket via handleTypeChange
    void next;
  };

  // _doSave: faktisk gem-logik. Hvis confirm=false og felter vil blive ryddet,
  // vises soft-validation FØRST. Når brugeren bekræfter, kaldes _doSave(true).
  const _doSave = async (skipConfirm = false) => {
    // Fase 15.20 (2026-02-21): Estimat-flow har sit eget payload (kun
    // materiale, antal, dato, kommentar). Ingen type-switch/soft-validation.
    if (isEstimat) {
      const countNum = Number(estimatedCount);
      if (!material.trim()) { toast.error("Materiale er påkrævet"); return; }
      if (!Number.isFinite(countNum) || countNum <= 0) { toast.error("Antal containere skal være større end 0"); return; }
      if (!orderDate) { toast.error("Bestillingsdato er påkrævet"); return; }
      setSaving(true);
      try {
        const r = await axios.put(`${API}/customer-orders/${order.id}`, {
          material: material.trim(),
          estimated_count: countNum,
          order_date: orderDate,
          comment: (comment || "").trim(),
        });
        if (r.data?.no_change) toast.info("Ingen ændringer at gemme");
        else toast.success("Estimat opdateret");
        onSaved();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Kunne ikke opdatere estimat");
      } finally {
        setSaving(false);
      }
      return;
    }
    // Fase 15.44 (2026-02-22): Løs afhentning - fast tour_type, reduceret
    // felt-set (prioritet, dato, antal, kommentar). Ingen type-switch.
    if (isLoes) {
      const countNum = Number(looseCount);
      if (!Number.isFinite(countNum) || countNum <= 0) { toast.error("Estimeret antal containere skal være større end 0"); return; }
      if (!orderDate) { toast.error("Bestillingsdato er påkrævet"); return; }
      setSaving(true);
      try {
        const r = await axios.put(`${API}/customer-orders/${order.id}`, {
          priority,
          order_date: orderDate,
          loose_estimated_count: countNum,
          comment: (comment || "").trim(),
        });
        if (r.data?.no_change) toast.info("Ingen ændringer at gemme");
        else toast.success("Løs afhentning opdateret");
        onSaved();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Kunne ikke opdatere løs afhentning");
      } finally {
        setSaving(false);
      }
      return;
    }
    // Beregn hvilke felter der bliver ryddet i forhold til ORIGINAL type
    const cleared = getFieldsToClear(originalType, tourType);
    if (cleared.length > 0 && !skipConfirm) {
      setPendingTypeChange({ from: originalType, to: tourType, fieldsToClear: cleared });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        priority,
        comment,
        order_date: orderDate,
        tour_type: tourType,
      };
      if (showAddress) {
        payload.custom_address = customAddress;
        if (isWorkshopType(originalType)) {
          payload.workshop_id = "";
          payload.workshop_name = "";
          payload.workshop_address = "";
          payload.workshop_phone = "";
        }
      } else if (showWorkshop) {
        payload.workshop_id = workshopId;
        payload.workshop_name = workshopName;
        payload.workshop_address = workshopAddress;
        payload.workshop_phone = workshopPhone;
        if (!isWorkshopType(originalType)) {
          payload.custom_address = "";
        }
      } else {
        // flyt: ryd BÅDE adresse og værksted-felter
        payload.custom_address = "";
        payload.workshop_id = "";
        payload.workshop_name = "";
        payload.workshop_address = "";
        payload.workshop_phone = "";
      }
      const r = await axios.put(`${API}/customer-orders/${order.id}`, payload);
      if (r.data?.no_change) toast.info("Ingen ændringer at gemme");
      else toast.success("Bestilling opdateret");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke opdatere bestilling");
    } finally {
      setSaving(false);
    }
  };

  const save = () => _doSave(false);

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" onClick={onClose} data-testid="order-edit-modal">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden max-h-[92vh] flex flex-col"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-white">
              {isEstimat ? "Redigér estimat"
                : isLoes ? "Redigér løs afhentning"
                : "Redigér bestilling"}
            </h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {isEstimat
                ? <>Estimat · <span className="text-amber-300">{material || order.material || "-"}</span></>
                : isLoes
                ? <>Løs afhentning · <span className="text-amber-300">{order.material || "-"}</span></>
                : <>{order.material} · {order.custom_container_id || order.container_id || "Uden nr."}</>
              }
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-slate-700 text-slate-400">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 space-y-4 overflow-y-auto">
          {isLoes ? (
            /* Fase 15.44 (2026-02-22): Løs afhentning - reduceret felt-set
                (prioritet, dato, antal containere, kommentar). Opgavetypen
                er FAST og kan ikke ændres - løs afhentning har en helt
                anden completion-UI for chaufføren (multi-vægt). */
            <>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Opgavetype</label>
                <div className="mt-1 w-full px-3 py-2 bg-slate-900 border border-amber-500/50 rounded-lg text-amber-300 text-sm font-bold flex items-center gap-2" data-testid="edit-loes-tour-type">
                  <Truck className="w-4 h-4" />
                  Løs afhentning
                  <span className="ml-auto text-[10px] font-normal text-slate-500 italic">(kan ikke ændres)</span>
                </div>
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Prioritet</label>
                <div className="grid grid-cols-3 gap-1.5 mt-1.5">
                  {[
                    { id: "haster", label: "HASTER", cls: "red" },
                    { id: "normal", label: "NORMAL", cls: "orange" },
                    { id: "senere", label: "LAV", cls: "blue" },
                  ].map(p => (
                    <button key={p.id} onClick={() => setPriority(p.id)}
                      className={`py-2 rounded-lg text-xs font-bold ${
                        priority === p.id
                          ? p.cls === "red" ? "bg-red-500 text-white"
                            : p.cls === "blue" ? "bg-blue-500 text-white"
                            : "bg-orange-500 text-white"
                          : "bg-slate-900 text-slate-400 hover:bg-slate-700"
                      }`}
                      data-testid={`edit-loes-priority-${p.id}`}>{p.label}</button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Estimeret antal containere <span className="text-red-400">*</span></label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  step={1}
                  value={looseCount}
                  placeholder="Indtast antal"
                  onChange={(e) => {
                    const v = e.target.value;
                    setLooseCount(v === "" ? "" : v.replace(/[^0-9]/g, ""));
                  }}
                  className="mt-1 w-40 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-black text-2xl focus:border-amber-500 outline-none placeholder:text-slate-600 placeholder:text-base placeholder:font-normal"
                  data-testid="edit-loes-count" />
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Bestillingsdato <span className="text-red-400">*</span></label>
                <input type="date" value={orderDate} onChange={e => setOrderDate(e.target.value)}
                  className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-amber-500 outline-none"
                  data-testid="edit-loes-date" />
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Kommentar <span className="text-slate-600 font-normal normal-case tracking-normal">(valgfri)</span></label>
                <textarea value={comment} onChange={e => setComment(e.target.value)}
                  placeholder="Tilføj evt. en kommentar (fx adgangsforhold)"
                  rows={3}
                  className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm resize-none focus:border-amber-500 outline-none"
                  data-testid="edit-loes-comment" />
              </div>
            </>
          ) : isEstimat ? (
            /* Fase 15.20 (2026-02-21): Estimat - kun 4 felter (materiale,
                antal, bestillingsdato, kommentar). Ingen prioritet/
                opgavetype/adresse/værksted. */
            <>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Materiale <span className="text-red-400">*</span></label>
                <input type="text" value={material} onChange={e => setMaterial(e.target.value)}
                  placeholder="Fx Træ, Haveaffald, Tegl"
                  className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-amber-500 outline-none"
                  data-testid="edit-estimat-material" />
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Antal containere estimeret <span className="text-red-400">*</span></label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  step={1}
                  value={estimatedCount}
                  placeholder="Indtast antal"
                  onChange={(e) => {
                    const v = e.target.value;
                    setEstimatedCount(v === "" ? "" : v.replace(/[^0-9]/g, ""));
                  }}
                  className="mt-1 w-40 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-black text-2xl focus:border-amber-500 outline-none placeholder:text-slate-600 placeholder:text-base placeholder:font-normal"
                  data-testid="edit-estimat-count" />
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Bestillingsdato <span className="text-red-400">*</span></label>
                <input type="date" value={orderDate} onChange={e => setOrderDate(e.target.value)}
                  className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-amber-500 outline-none"
                  data-testid="edit-estimat-date" />
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Kommentar <span className="text-slate-600 font-normal normal-case tracking-normal">(valgfri)</span></label>
                <textarea value={comment} onChange={e => setComment(e.target.value)}
                  placeholder="Tilføj evt. en kommentar til estimatet"
                  rows={3}
                  className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm resize-none focus:border-amber-500 outline-none"
                  data-testid="edit-estimat-comment" />
              </div>
            </>
          ) : (<>
          <div>
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Prioritet</label>
            <div className="grid grid-cols-3 gap-1.5 mt-1.5">
              {[
                { id: "haster", label: "HASTER", cls: "red" },
                { id: "normal", label: "NORMAL", cls: "orange" },
                { id: "senere", label: "LAV", cls: "blue" },
              ].map(p => (
                <button key={p.id} onClick={() => setPriority(p.id)}
                  className={`py-2 rounded-lg text-xs font-bold ${
                    priority === p.id
                      ? p.cls === "red" ? "bg-red-500 text-white"
                        : p.cls === "blue" ? "bg-blue-500 text-white"
                        : "bg-orange-500 text-white"
                      : "bg-slate-900 text-slate-400 hover:bg-slate-700"
                  }`}
                  data-testid={`edit-priority-${p.id}`}>{p.label}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Dato</label>
            <input type="date" value={orderDate} onChange={e => setOrderDate(e.target.value)}
              className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
              data-testid="edit-order-date" />
          </div>
          <div>
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Opgavetype</label>
            <select value={tourType} onChange={e => handleTypeChange(e.target.value)}
              className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
              data-testid="edit-tour-type">
              <option value="normal">Afhentning</option>
              <option value="flyt">Byt container</option>
              <option value="vaerksted">Til værksted</option>
              <option value="afhent_vaerksted">Afhent fra værksted</option>
            </select>
          </div>

          {/* Dynamisk felt: leveringsadresse (kun normal / flyt) */}
          {showAddress && (
            <div data-testid="edit-address-block">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <MapPin className="w-3 h-3" /> Leveringsadresse
              </label>
              <input type="text" value={customAddress} onChange={e => setCustomAddress(e.target.value)}
                placeholder="Vej, postnr. og by"
                className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
                data-testid="edit-order-address" />
            </div>
          )}

          {/* Dynamisk felt: værksted-snapshot (kun vaerksted / afhent_vaerksted) */}
          {showWorkshop && (
            <div data-testid="edit-workshop-block" className="space-y-2">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Wrench className="w-3 h-3" /> Værksted <span className="text-red-400">*</span>
              </label>
              <select value={workshopId}
                onChange={e => {
                  const id = e.target.value;
                  setWorkshopId(id);
                  const w = workshops.find(x => x.id === id);
                  if (w) {
                    setWorkshopName(w.name || "");
                    setWorkshopAddress(w.address || "");
                    setWorkshopPhone(w.phone || "");
                  } else {
                    setWorkshopName(""); setWorkshopAddress(""); setWorkshopPhone("");
                  }
                }}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
                data-testid="edit-workshop-select">
                <option value="">- Vælg værksted -</option>
                {workshops.map(w => (
                  <option key={w.id} value={w.id}>{w.name}{w.address ? ` - ${w.address}` : ""}</option>
                ))}
              </select>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input type="text" value={workshopName} onChange={e => setWorkshopName(e.target.value)} placeholder="Navn"
                  className="px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-white text-xs" data-testid="edit-workshop-name" />
                <input type="text" value={workshopAddress} onChange={e => setWorkshopAddress(e.target.value)} placeholder="Adresse"
                  className="px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-white text-xs" data-testid="edit-workshop-address" />
                <input type="text" value={workshopPhone} onChange={e => setWorkshopPhone(e.target.value)} placeholder="Telefon"
                  className="px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-white text-xs" data-testid="edit-workshop-phone" />
              </div>
            </div>
          )}

          <div>
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Kommentar</label>
            <textarea value={comment} onChange={e => setComment(e.target.value)}
              rows={3}
              className="mt-1 w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm resize-none focus:border-orange-500 outline-none"
              data-testid="edit-order-comment" />
          </div>
          </>)}
        </div>
        <div className="flex gap-3 p-4 bg-slate-900/60 border-t border-slate-700">
          <button onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-200 bg-slate-700 hover:bg-slate-600"
            data-testid="edit-cancel-btn">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 inline-flex items-center justify-center gap-2"
            data-testid="edit-save-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>

      {/* Soft-validation dialog ved Gem hvis tour_type er skiftet og felter ryddes */}
      {pendingTypeChange && (
        <div className="absolute inset-0 z-[1000] flex items-center justify-center p-4" data-testid="edit-type-change-confirm">
          <div className="absolute inset-0 bg-black/80" onClick={() => setPendingTypeChange(null)} />
          <div className="relative bg-amber-50 dark:bg-slate-900 border-2 border-amber-400 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <AlertTriangle className="w-6 h-6 text-amber-500" />
                <h4 className="font-bold text-base text-amber-900 dark:text-amber-200">Bekræft skift af opgavetype</h4>
              </div>
              <p className="text-sm text-slate-700 dark:text-slate-200 mb-3">
                Du har skiftet opgavetypen. Når du gemmer, slettes følgende data fra bestillingen:
              </p>
              <ul className="list-disc pl-5 text-sm text-slate-700 dark:text-slate-200 mb-4">
                {pendingTypeChange.fieldsToClear.map(f => <li key={f}>{f}</li>)}
              </ul>
              <p className="text-xs text-slate-500 dark:text-slate-400 italic">
                Alle ændringer logges i bestillingens historikvindue.
              </p>
              <div className="mt-4 flex gap-2">
                <button onClick={() => setPendingTypeChange(null)}
                  className="flex-1 px-3 py-2 rounded-lg text-sm font-semibold text-slate-700 dark:text-slate-200 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300"
                  data-testid="edit-type-change-cancel">
                  Annullér
                </button>
                <button onClick={confirmTypeChange}
                  className="flex-1 px-3 py-2 rounded-lg text-sm font-bold text-white bg-amber-600 hover:bg-amber-700"
                  data-testid="edit-type-change-confirm-btn">
                  Gem og ryd felter
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/* ============================ ORDER CANCEL CONFIRM MODAL (Fase 15.51) ============================
   Fase 15.51 (2026-02-22): "Slet" → "Annuller". Bestillingen forbliver i
   databasen, men status sættes til 'cancelled' så driver-UI'en kan vise den
   grået ud nederst og rapporter kan filtrere/medtage efter behov.
   Annulleringen er ENDELIG - kunden skal oprette en ny bestilling hvis de
   fortryder. */
const OrderCancelConfirmModal = ({ order, onCancel, onDeleted }) => {
  const [busy, setBusy] = useState(false);
  const doCancel = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/customer-orders/${order.id}/cancel`);
      toast.success("Bestilling annulleret");
      onDeleted();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke annullere bestilling");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="order-cancel-confirm">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div className="p-6">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-amber-500/10 ring-8 ring-inset ring-amber-500/30 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-amber-400" />
          </div>
          <h3 className="text-lg font-bold text-white text-center mb-2">Annullér bestilling?</h3>
          <p className="text-sm text-slate-300 text-center">
            <span className="font-bold">{order.material}</span>{order.tour_type === "loes_afhentning" ? <span className="text-amber-300"> · Løs afhentning</span> : (order.custom_container_id || order.container_id ? <> · {order.custom_container_id || order.container_id}</> : null)}
            <br />
            <span className="text-rose-400 text-xs font-bold uppercase tracking-wider mt-2 block">
              Handlingen er endelig
            </span>
            <span className="text-slate-400 text-xs">
              Bestillingen kan ikke genåbnes. Hvis du fortryder skal du oprette en ny bestilling.
            </span>
          </p>
        </div>
        <div className="flex gap-3 p-4 bg-slate-900/60">
          <button onClick={onCancel} disabled={busy}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-200 bg-slate-700 hover:bg-slate-600"
            data-testid="cancel-abort-btn">
            Behold
          </button>
          <button onClick={doCancel} disabled={busy}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-60 inline-flex items-center justify-center gap-2"
            data-testid="cancel-confirm-btn">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />} Annullér
          </button>
        </div>
      </div>
    </div>
  );
};

/* ============================ ORDER AUDIT HISTORY MODAL (Batch 2) ============================ */
const OrderAuditModal = ({ order, onClose }) => {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/customer-orders/${order.id}/history`);
        if (!cancelled) setEntries(r.data || []);
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || "Kunne ikke hente historik");
      }
    })();
    return () => { cancelled = true; };
  }, [order.id]);

  const formatVal = (v) => {
    if (v === null || v === undefined || v === "") return "-";
    if (typeof v === "boolean") return v ? "Ja" : "Nej";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" onClick={onClose} data-testid="order-audit-modal">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl max-w-lg w-full max-h-[80vh] flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-white inline-flex items-center gap-2">
              <History className="w-4 h-4 text-emerald-400" /> Ændringshistorik
            </h3>
            <p className="text-[11px] text-slate-400 mt-0.5">{order.material} · {order.custom_container_id || order.container_id || "Uden nr."}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-slate-700 text-slate-400">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {error && <p className="text-rose-300 text-sm">{error}</p>}
          {!entries && !error && (
            <div className="text-center py-6"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
          )}
          {entries && entries.length === 0 && (
            <p className="text-sm text-slate-400 italic text-center py-6">Ingen ændringer endnu - bestillingen er som da den blev oprettet.</p>
          )}
          {entries && entries.map((e, i) => {
            const fields = Object.keys(e.after || {});
            return (
              <div key={e.id || i} className={`border-l-4 rounded p-3 ${
                e.action === "delete" ? "border-rose-500 bg-rose-950/20" : "border-blue-500 bg-blue-950/20"
              }`} data-testid={`audit-row-${i}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className={`text-[10px] uppercase font-bold tracking-wider ${
                    e.action === "delete" ? "text-rose-300" : "text-blue-300"
                  }`}>
                    {e.action === "delete" ? "Slettet" : "Redigeret"}
                  </span>
                  <span className="text-[11px] text-slate-400">
                    {(e.user_name || e.user_email || "-")}
                    {" · "}
                    {e.at ? new Date(e.at).toLocaleString("da-DK") : ""}
                  </span>
                </div>
                {e.action === "edit" && fields.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {fields.map(f => (
                      <div key={f} className="text-[12px] text-slate-300">
                        <span className="text-slate-500">{f}:</span>{" "}
                        <span className="line-through text-slate-500">{formatVal(e.before?.[f])}</span>{" "}
                        <span className="text-slate-400">→</span>{" "}
                        <span className="text-emerald-300 font-bold">{formatVal(e.after?.[f])}</span>
                      </div>
                    ))}
                  </div>
                )}
                {e.action === "delete" && (
                  <p className="text-[12px] text-slate-400 mt-1 italic">Bestillingen blev slettet.</p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};


/* ============================ SOFT CONFIRM MODAL ============================ */
const SoftConfirmModal = ({ title, message, confirmLabel = "Bekræft", variant = "emerald", onConfirm, onCancel }) => {
  const variantBtn = variant === "red"
    ? "bg-red-600 hover:bg-red-700"
    : variant === "amber"
      ? "bg-amber-500 hover:bg-amber-600"
      : "bg-emerald-600 hover:bg-emerald-700";
  const variantIcon = variant === "red" ? "text-red-400" : variant === "amber" ? "text-amber-400" : "text-emerald-400";
  const variantRing = variant === "red" ? "bg-red-500/10 ring-red-500/30" : variant === "amber" ? "bg-amber-500/10 ring-amber-500/30" : "bg-emerald-500/10 ring-emerald-500/30";
  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="soft-confirm-modal">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div className="p-6">
          <div className={`w-14 h-14 mx-auto mb-4 rounded-full ${variantRing} ring-8 ring-inset flex items-center justify-center`}>
            <AlertCircle className={`w-7 h-7 ${variantIcon}`} />
          </div>
          <h3 className="text-lg font-bold text-white text-center mb-2">{title}</h3>
          <div className="text-sm text-slate-300 text-center">{message}</div>
        </div>
        <div className="flex gap-3 p-4 bg-slate-900/60">
          <button onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-200 bg-slate-700 hover:bg-slate-600"
            data-testid="soft-confirm-cancel">
            Annuller
          </button>
          <button onClick={onConfirm}
            className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white ${variantBtn}`}
            data-testid="soft-confirm-ok">
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

/* ============================ CONTAINER EDIT MODAL ============================ */
const ContainerEditModal = ({ container, locationCode, material, adminMode, onClose, onSaved }) => {
  // First-time edit of a fresh slot (admin just clicked "+ Tilføj container")
  // - empty fields, defaults: lock address + lock id, hours UNLOCKED.
  const isNewSlot = !container.has_override;
  const [containerId, setContainerId] = useState(isNewSlot ? "" : (container.container_id || ""));
  const [openFromV, setOpenFromV] = useState(isNewSlot ? "" : (container.open_from || ""));
  const [openToV, setOpenToV] = useState(isNewSlot ? "" : (container.open_to || ""));
  const [lockHrs, setLockHrs] = useState(isNewSlot ? false : !!container.locked_hours);
  const [lockId, setLockId] = useState(isNewSlot ? true : !!container.locked_container_id);
  const [capacityId, setCapacityId] = useState(isNewSlot ? "" : (container.capacity_measure_id || ""));
  const [capacityList, setCapacityList] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!locationCode) return;
    axios.get(`${API}/org/capacity-measures?location_code=${locationCode}`)
      .then(r => setCapacityList(r.data || []))
      .catch(() => setCapacityList([]));
  }, [locationCode]);

  const isMissingId = !containerId.trim();
  const canSave = !isMissingId;

  const save = async () => {
    if (!canSave) {
      toast.error("Container-nummer er påkrævet");
      return;
    }
    setSaving(true);
    try {
      // Pr. 2026-06-15 brugerkrav: når lokationen har flere partnere skal
      // partner_id med så backend kan finde præcis den rigtige override-række
      // og ikke ramme en anden partners container.
      await axios.put(`${API}/locations/${locationCode}/containers/override`, {
        material,
        container_label: container.label,
        partner_id: container.partner_id || "",
        custom_container_id: containerId.trim(),
        open_from: openFromV,
        open_to: openToV,
        locked_hours: lockHrs,
        locked_container_id: lockId,
        capacity_measure_id: capacityId || "",
      });
      toast.success("Container opdateret");
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kunne ikke gemme container");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="container-edit-modal">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl max-w-md w-full p-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-white text-lg">Rediger {container.label}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-700 text-slate-300"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-xs text-slate-400 mb-4">Grunddefinitioner for denne container. Kun container-nummer er obligatorisk. Leveringsadressen vælges på selve bestillingen.</p>

        <label className="block text-xs font-semibold text-slate-400 mb-1">
          Container-nummer <span className="text-red-400">*</span>
        </label>
        <input value={containerId} onChange={e => setContainerId(e.target.value)}
          placeholder="Fx 12345"
          className={`w-full px-3 py-2 bg-slate-900 border rounded-lg text-white text-sm mb-3 outline-none ${isMissingId ? "border-red-500/60" : "border-slate-600 focus:border-orange-500"}`}
          data-testid="cont-edit-id" />

        <label className="block text-xs font-semibold text-slate-400 mb-1 inline-flex items-center gap-1">
          <Ruler className="w-3 h-3" /> Kapacitetsmål (valgfri)
        </label>
        <select value={capacityId} onChange={e => setCapacityId(e.target.value)}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm mb-3 focus:border-orange-500 outline-none"
          data-testid="cont-edit-capacity">
          <option value="">- Intet kapacitetsmål -</option>
          {capacityList.map(cm => (
            <option key={cm.id} value={cm.id}>
              {cm.label}{cm.volume_m3 ? ` (${cm.volume_m3} m³)` : ""}
            </option>
          ))}
        </select>
        {capacityList.length === 0 && (
          <p className="text-[11px] text-amber-300 mt-[-0.5rem] mb-2">
            Ingen kapacitetsmål endnu - opret dem på "Kapacitetsmål"-fanen.
          </p>
        )}

        <div className="grid grid-cols-2 gap-2 mb-3">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">Åbner</label>
            <input type="time" value={openFromV} onChange={e => setOpenFromV(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
              data-testid="cont-edit-open-from" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">Lukker</label>
            <input type="time" value={openToV} onChange={e => setOpenToV(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm focus:border-orange-500 outline-none"
              data-testid="cont-edit-open-to" />
          </div>
        </div>

        {adminMode && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-3 space-y-2" data-testid="cont-edit-locks">
            <p className="text-xs font-bold text-amber-400 uppercase tracking-wider">Låsninger (kun location admin)</p>
            <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer">
              <input type="checkbox" checked={lockHrs} onChange={e => setLockHrs(e.target.checked)}
                className="w-4 h-4 accent-amber-500" data-testid="cont-edit-lock-hrs" />
              Lås åbnings- og lukketider
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer">
              <input type="checkbox" checked={lockId} onChange={e => setLockId(e.target.checked)}
                className="w-4 h-4 accent-amber-500" data-testid="cont-edit-lock-id" />
              Lås container-nummer (kan ikke ændres under bestilling)
            </label>
          </div>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-700 text-slate-200 hover:bg-slate-600">Annuller</button>
          <button onClick={save} disabled={saving || !canSave} data-testid="cont-edit-save"
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white inline-flex items-center gap-2">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
};

// ============= CUSTOMER CODE ENTRY PAGE =============
const CustomerCodeEntry = ({ onCodeSubmit }) => {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!code.trim()) {
      setError("Indtast en kode");
      return;
    }
    
    setLoading(true);
    setError("");
    
    try {
      await axios.get(`${API}/locations/code/${code.trim()}`);
      onCodeSubmit(code.trim());
    } catch (e) {
      if (e.response && e.response.status === 404) {
        setError("Ugyldig kode. Prøv igen.");
      } else if (e.response) {
        setError(`Server fejl: ${e.response.status}`);
      } else {
        setError("Netværksfejl - prøv igen.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-red-600 to-red-800 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8">
        <div className="text-center mb-8">
          <div className="w-20 h-20 bg-slate-900 rounded-full flex items-center justify-center mx-auto mb-4">
            <Truck className="w-10 h-10 text-orange-500" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800">Container<span className="text-orange-500">Flow</span></h1>
          <p className="text-slate-500 mt-1">Smart Container Logistics</p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Indtast din lokationskode
            </label>
            <input
              type="text"
              value={code}
              onChange={(e) => { setCode(e.target.value); setError(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="F.eks. 3030"
              className="w-full px-4 py-4 text-2xl text-center font-mono border-2 rounded-xl focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
              maxLength={10}
            />
            {error && (
              <p className="text-red-500 text-sm mt-2 flex items-center gap-1">
                <AlertCircle className="w-4 h-4" /> {error}
              </p>
            )}
          </div>
          
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full py-4 bg-orange-500 text-white text-lg font-bold rounded-xl hover:bg-orange-600 disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <ChevronRight className="w-5 h-5" />
                Fortsæt
              </>
            )}
          </button>
        </div>

        <p className="text-center text-slate-400 text-sm mt-6">
          Koden findes på skiltet ved genbrugspladsen
        </p>
      </div>
    </div>
  );
};

// ============= COMPONENTS =============

const StatCard = ({ icon: Icon, value, label, color = "primary", subtext = "" }) => {
  const colorClasses = {
    primary: "bg-slate-800 text-white",
    accent: "bg-amber-500 text-black",
    success: "bg-emerald-500 text-white",
    brand: "bg-red-600 text-white",
    info: "bg-blue-600 text-white",
  };

  return (
    <div 
      data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}
      className={`stat-card ${colorClasses[color]} rounded-xl p-4 flex flex-col items-center justify-center min-w-[100px] shadow-lg transition-all hover:scale-105`}
    >
      <Icon className="w-5 h-5 mb-1 opacity-80" />
      <span className="font-heading font-black text-2xl">{value}</span>
      <span className="text-xs opacity-80 font-medium">{label}</span>
      {subtext && <span className="text-xs opacity-60 mt-1">{subtext}</span>}
    </div>
  );
};

const PladsButton = ({ name, isSelected, onClick, tourCount = 0 }) => (
  <button
    data-testid={`plads-${name.toLowerCase().replace(/\s/g, '-')}`}
    onClick={onClick}
    className={`
      relative px-4 py-2 rounded-lg text-sm font-medium transition-all
      ${isSelected 
        ? "bg-red-600 text-white shadow-lg scale-105" 
        : "bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:border-orange-400 hover:text-red-600"
      }
    `}
  >
    {name}
    {tourCount > 0 && (
      <span className={`absolute -top-2 -right-2 w-5 h-5 rounded-full text-xs flex items-center justify-center font-bold ${isSelected ? "bg-white text-red-600" : "bg-red-600 text-white"}`}>
        {tourCount}
      </span>
    )}
  </button>
);

// ============= MOBILE TOUR CARD (Yeni tasarım - resme göre) =============

const MobileTourCard = ({ tour, onUpdate, onDelete, onToggleOnWay, onToggleComplete, isInGroup, onSelect, isSelected, dragHandleProps, currentDriverName, routeInfo, canDelete = false, index = 0 }) => {
  if (tour.is_pause) {
    return (
      <div className="flex items-center justify-between p-3 bg-orange-100 dark:bg-orange-950/30 rounded-xl mb-2" data-testid={`mobile-tour-${tour.id}`}>
        <div className="flex items-center gap-2">
          <Pause className="w-4 h-4 text-orange-500" />
          <span className="font-bold text-orange-700">PAUSE</span>
          <span className="text-sm text-orange-600">{tour.time || "45 min"}</span>
        </div>
        {canDelete && (
          <button onClick={() => onDelete(tour.id)} className="p-2 text-red-500">
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    );
  }

  const priority = tour.priority || "normal";const isClaimedByOther = tour.claimed_by && tour.claimed_by !== currentDriverName;
  // Fase 6 (2026-06-16): Backend only sends pre-assigned tours to the
  // assigned driver, so when driver_id is set on a tour the driver sees,
  // it means it's pre-assigned to THEM.
  const isPreAssignedToMe = !!(tour.driver_id && !tour.completed);
  const openHours = extractOpenHours(tour);
  
  // Status colors - durum her şeyden belli olmalı
  // Fase 15.26 (2026-02-21): Case-insensitive haster-check så priority="Haster"
  // OG priority="haster" begge fanges. Tidligere kunne case-mismatch betyde
  // at status-badge ikke blev rød trods at priority-chip viste "Haster".
  const _pLower = priority.toString().toLowerCase();
  const isHaster = _pLower === "urgent" || _pLower === "haster" || _pLower === "high";
  const getStatusStyle = () => {
    if (tour.completed) {
      return {
        border: "border-l-[4px] border-l-emerald-500",
        cardBg: "bg-[#061410]",
        badge: "bg-emerald-600 text-emerald-100",
        badgeText: "FÆRDIG",
        btnBg: "bg-emerald-700 text-emerald-200",
        btnDisabled: true,
        opacity: "opacity-50",
      };
    }
    if (tour.on_way) {
      return {
        border: "border-l-[4px] border-l-amber-400",
        cardBg: "bg-[#1A1300]",
        badge: "bg-amber-400 text-amber-950",
        badgeText: "PÅ VEJ",
        btnBg: "bg-amber-400 text-amber-950",
        btnDisabled: false,
        opacity: "",
      };
    }
    if (isHaster) {
      return {
        border: "border-l-[4px] border-l-red-500",
        cardBg: "bg-[#1C0909]",
        badge: "bg-red-500 text-white",
        badgeText: "HASTER",
        btnBg: "bg-red-500 text-white",
        btnDisabled: false,
        opacity: "",
      };
    }
    return {
      border: "border-l-[4px] border-l-slate-500",
      cardBg: "bg-slate-800",
      badge: "bg-slate-600 text-slate-200",
      badgeText: "VENTER",
      btnBg: "bg-orange-500 text-white",  // Turuncu - net görünür
      btnDisabled: false,
      opacity: "",
    };
  };

  const statusStyle = getStatusStyle();

  return (
    <div 
      className={`${statusStyle.border} ${statusStyle.cardBg} ${statusStyle.opacity} rounded-r-xl mb-2 overflow-hidden transition-opacity`}
      data-testid={`mobile-tour-${tour.id}`}
    >
      <div className="p-3 flex items-start gap-3">
        {/* Left: Order number */}
        <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white text-sm font-bold ${
          tour.completed ? "bg-emerald-600" : tour.on_way ? "bg-amber-400 text-amber-950" : isHaster ? "bg-red-500" : "bg-slate-600"
        }`}>
          {index + 1}
        </div>
        
        {/* Middle: Content */}
        <div className="flex-1 min-w-0" onClick={() => onSelect(tour)}>
          {/* Fraction - büyük ve net */}
          <h3 className="font-bold text-white text-[15px] leading-tight truncate">
            {tour.fraction || "Ingen fraktion"}
          </h3>

          {/* Adres - okunabilir boyut */}
          <p className="text-slate-200 text-[13px] mt-0.5 truncate">
            {tour.address?.split(',')[0] || tour.facility || "Ingen adresse"}
          </p>

          {/* Fase 13 (2026-06-18): Dedikeret info-blok pr. tur. Chaufføren
              SKAL kunne se: opgavetype, kapacitetsmål, bestillingsdato,
              bestillingstid, afhentningsdato og bestilt-af direkte på kortet
              - uden at åbne detalje-vinduet. Vises som farvede chips, en pr.
              række hvis nødvendigt (flex-wrap), så det er tydeligt læsbart. */}
          <div className="mt-1.5 flex flex-wrap gap-1" data-testid={`tour-info-chips-${tour.id}`}>
            {/* Fase 15.42 (2026-02-22): "Løs afhentning"-tur skal være tydelig
                for chaufføren - solid amber badge med Truck-ikon i stedet for
                blot en lille opgavetype-chip. Erstattes IKKE af en separat
                sektion, men gøres visuelt mere fremtrædende på selve kortet. */}
            {tour.tour_type === "loes_afhentning" ? (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500 text-white font-black text-[10px] uppercase tracking-wider shadow-sm border border-amber-300"
                data-testid={`tour-loes-badge-${tour.id}`}
                title="Løs afhentning - du medbringer egne tomme containere"
              >
                <Truck className="w-3 h-3" />
                Løs afhentning
              </span>
            ) : (
              tour.tour_type && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-purple-500/15 text-purple-300 text-[10px] font-bold">
                  <Wrench className="w-2.5 h-2.5" />
                  {TOUR_TYPE_LABELS[tour.tour_type] || tour.tour_type}
                </span>
              )
            )}
            {/* Antal containere ved Løs afhentning - synligt på selve kortet
                så chaufføren straks ved hvor mange containere de skal med-
                bringe. */}
            {tour.tour_type === "loes_afhentning" && tour.loose_estimated_count > 0 && (
              <span
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-500/15 text-amber-200 border border-amber-500/40 text-[10px] font-bold"
                data-testid={`tour-loes-count-${tour.id}`}
              >
                <Package2 className="w-2.5 h-2.5" />
                {tour.loose_estimated_count} container{tour.loose_estimated_count === 1 ? "" : "e"}
              </span>
            )}
            {(tour.capacity_label || tour.capacity_volume_m3 != null) && tour.tour_type !== "loes_afhentning" && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-500/15 text-amber-300 text-[10px] font-bold">
                <Package2 className="w-2.5 h-2.5" />
                {formatCapacity(tour)}
              </span>
            )}
            {/* Fase 15.13 (2026-02-XX): Generel prioritets-chip - Haster/Normal/Lav
                Fase 15.26 (2026-02-21): Pulserende rød ring KUN på Haster-chippet
                når turen ikke er færdig. Det er det visuelle anker for HASTER-
                prioriteten, så det skal være tydeligt.
                Fase 15.39 (2026-02-22): Pulsen STOPPER når turen er "på vej" -
                pulsen er en opmærksomheds-krog ("tag denne tur"), så når
                chaufføren først er på vej er pulsen unødvendig støj. */}
            {(() => {
              const pc = getPriorityChip(tour);
              const isHasterChip = (pc.label || "").toLowerCase() === "haster";
              const shouldPulse = isHasterChip && !tour.completed && !tour.on_way;
              return (
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border ${pc.cls} text-[10px] font-bold ${
                  shouldPulse ? "ring-2 ring-red-400 animate-haster-pulse" : ""
                }`}
                  data-testid={`tour-priority-${tour.id}`}>
                  <Flag className="w-2.5 h-2.5" />
                  {pc.label}
                </span>
              );
            })()}
            {/* Fase 15.14 (2026-02-XX): Kundefirma-tag - vises altid hvis tour
                har customer_name så chaufføren ved hvilken kunde turen tilhører
                (vigtigt når deres logistik-firma betjener flere kunder). */}
            {tour.customer_name && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-purple-500/15 text-purple-200 border border-purple-500/40 text-[10px] font-bold max-w-[200px]"
                data-testid={`tour-customer-${tour.id}`}
                title={`Kunde: ${tour.customer_name}`}>
                <Building2 className="w-2.5 h-2.5 flex-shrink-0" />
                <span className="truncate">{tour.customer_name}</span>
              </span>
            )}
            {tour.order_date && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 text-[10px] font-bold">
                <Truck className="w-2.5 h-2.5" />
                Bestillingsdato {_fmtDateDM(tour.order_date)}
              </span>
            )}
            {tour.created_at && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-blue-500/15 text-blue-300 text-[10px] font-bold">
                <Calendar className="w-2.5 h-2.5" />
                Oprettet den {_fmtDateDM(tour.created_at)} {_fmtTimeHM(tour.created_at)}
              </span>
            )}
            {(tour.created_by_name || tour.created_by_email) && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-700/60 text-slate-300 text-[10px] font-bold max-w-[200px]"
                title={tour.created_by_email || tour.created_by_name}>
                <Users className="w-2.5 h-2.5 flex-shrink-0" />
                <span className="truncate">af {tour.created_by_name || tour.created_by_email}</span>
              </span>
            )}
            {/* Fase 15/15.7/15.8 (2026-02-XX): "Tildelt af X" - vises tydeligt
                med klar farve og kant så chaufføren ALTID kan se hvem der
                gav dem turen. Tidligere var chippen for diskret og blev
                overset. */}
            {tour.assigned_by_name && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-500 text-white border border-indigo-300 shadow-sm text-[10px] font-bold max-w-[260px]"
                title={tour.assigned_at ? `Tildelt ${tour.assigned_at}` : ""}
                data-testid={`tour-assigned-by-${tour.id}`}>
                <UserCheck className="w-2.5 h-2.5 flex-shrink-0" />
                <span className="truncate">Tildelt af {tour.assigned_by_name}</span>
              </span>
            )}
            {/* Fase 15 (2026-06-19): Tur-nummer som unik identifier */}
            {tour.tour_number && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-900/80 text-amber-300 text-[10px] font-bold font-mono"
                data-testid={`tour-number-${tour.id}`}>
                {tour.tour_number}
              </span>
            )}
            {/* Fase 15.2 (2026-06-19): "X dage forsinket"-badge når turens
                planlagte dato er før i dag og turen endnu ikke er afsluttet. */}
            {(() => {
              if (tour.completed) return null;
              const td = (tour.date || "").slice(0, 10);
              if (!td) return null;
              const today = (typeof getLocalDateStr === "function") ? getLocalDateStr() : new Date().toISOString().slice(0, 10);
              if (td >= today) return null;
              const d = new Date(td + "T12:00:00");
              const t = new Date(today + "T12:00:00");
              const delay = Math.floor((t - d) / 86400000);
              if (delay <= 0) return null;
              return (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-red-500 text-white text-[10px] font-bold uppercase animate-pulse"
                  data-testid={`tour-delay-${tour.id}`}>
                  <Clock className="w-2.5 h-2.5" />
                  {delay} {delay === 1 ? "dag" : "dage"} forsinket
                </span>
              );
            })()}
          </div>

          {/* Tur tipi + konteyner */}
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {/* Fase 6: Pre-assignment badge - Backend only sends pre-assigned tours to the assigned driver */}
            {isPreAssignedToMe && !tour.on_way && (
              <span className="bg-indigo-600 text-white text-[10px] font-bold px-2 py-0.5 rounded flex items-center gap-1" data-testid={`preassigned-badge-${tour.id}`}>
                <Users className="w-2.5 h-2.5" /> TILDELT MIG
              </span>
            )}
            {/* Fase 15.4 (2026-06-19): SOLO/HÆNGER-badge vises KUN når
                rute-optimering er aktiv (routeInfo eksisterer). Ellers er
                "Solo"-mærkningen irrelevant og fjernet pr. brugerønske. */}
            {routeInfo?.job_type === "HAENGER" && (
              <span className="bg-blue-900/60 text-blue-300 text-[10px] font-bold px-2 py-0.5 rounded">HÆNGER</span>
            )}
            {routeInfo?.job_type && routeInfo.job_type !== "HAENGER" && (
              <span className="bg-slate-700 text-slate-400 text-[10px] font-bold px-2 py-0.5 rounded">SOLO</span>
            )}
            {tour.container_id && tour.tour_type !== "loes_afhentning" && (
              <span className="text-slate-500 text-[11px]">· {tour.container_id}</span>
            )}
            {routeInfo?.distance_km > 0 && (
              <span className="text-slate-500 text-[11px]">· {routeInfo.distance_km} km</span>
            )}
            {routeInfo?.estimated_minutes && !tour.on_way && !tour.completed && (
              <span className="text-slate-500 text-[11px]">~{routeInfo.estimated_minutes}m</span>
            )}
          </div>

          {/* Aktif tur: zaman + kg */}
          {(tour.on_way || tour.completed) && (
            <div className="flex items-center gap-2 mt-1 text-[11px]">
              {tour.on_way_time && (
                <span className="text-slate-400">
                  {tour.on_way_time}{tour.completed && tour.time ? ` → ${tour.time}` : " →"}
                </span>
              )}
              {/* Fase 11 (2026-06-18): Vægt vises KUN for opgavetype 'normal' */}
              {tour.completed && tour.weight && (tour.tour_type || "normal") === "normal" && (
                <span className="text-emerald-400 font-bold">{tour.weight} kg</span>
              )}
            </div>
          )}

          {/* Bemærkning */}
          {openHours.cleanRemark && !isHaster && (
            <div className="flex items-center gap-1.5 mt-1.5 text-[11px]">
              <ChevronRight className="w-3 h-3 text-rose-400 flex-shrink-0" />
              <span className="text-rose-400 truncate">{openHours.cleanRemark}</span>
            </div>
          )}

          {/* Google Maps butonu */}
          {!tour.completed && (tour.address || tour.facility) && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                const addr = encodeURIComponent(tour.address || tour.facility || "");
                window.open(`https://maps.google.com/?q=${addr}`, "_blank");
              }}
              className="mt-2 flex items-center gap-1.5 text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
              data-testid={`maps-btn-${tour.id}`}
            >
              <MapPin className="w-3 h-3" />
              <span>Åbn kort</span>
            </button>
          )}
        </div>
        
        {/* Right: Badge + Action */}
        <div className="flex flex-col items-end gap-2 flex-shrink-0">
          <span className={`px-2.5 py-1 ${statusStyle.badge} text-[10px] font-black rounded-md whitespace-nowrap`}>
            {statusStyle.badgeText}
          </span>

          <button 
            onClick={(e) => {
              e.stopPropagation();
              if (tour.completed) return;
              // Fase 13 (2026-06-18): Send tourId, ikke hele tour-objektet -
              // handlers forventer string-id'et. Tidligere blev hele objektet
              // sendt videre, hvilket gjorde at backend-valideringen aldrig
              // blev kørt korrekt på MobileTourCard's "På vej"-knap.
              if (tour.on_way) onToggleComplete(tour.id);
              else onToggleOnWay(tour.id);
            }}
            disabled={statusStyle.btnDisabled}
            className={`w-11 h-11 rounded-xl flex items-center justify-center ${statusStyle.btnBg} hover:opacity-90 active:scale-95 transition-all shadow-md disabled:opacity-30`}
            data-testid={`tour-action-btn-${tour.id}`}
          >
            {tour.completed
              ? <CheckCircle2 className="w-5 h-5" />
              : tour.on_way
              ? <CheckCircle2 className="w-5 h-5" />
              : <Truck className="w-5 h-5" />
            }
          </button>
        </div>
      </div>
    </div>
  );
};

// Slide-up Panel for tour details
// ============= PRO RECEIPT SCANNER (Full-Screen Mobile Document Scanner) =============
// ============= AI RECEIPT SCANNER (Tesseract.js OCR - Ücretsiz) =============
const ProReceiptScanner = ({ onCapture, onClose, onWeightDetected }) => {
  const videoContainerRef = useRef(null);
  const videoElRef        = useRef(null);
  const canvasRef         = useRef(null);
  const streamRef         = useRef(null);

  const [step, setStep]               = useState("camera"); // camera | preview | ocr | confirm
  const [capturedImage, setCapturedImage] = useState(null);
  const [ocrLoading, setOcrLoading]   = useState(false);
  const [ocrError, setOcrError]       = useState(null);
  const [ocrResult, setOcrResult]     = useState(null); // { weight, text }
  const [editedWeight, setEditedWeight] = useState("");

  // ── Start camera ───────────────────────────────────────────────
  useEffect(() => {
    const video = document.createElement("video");
    video.autoplay = true; video.playsInline = true; video.muted = true;
    video.setAttribute("playsinline", "");
    video.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;";
    videoElRef.current = video;
    if (videoContainerRef.current) videoContainerRef.current.appendChild(video);
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }
    }).then(s => { streamRef.current = s; if (videoElRef.current) videoElRef.current.srcObject = s; })
      .catch(() => toast.error("Kan ikke åbne kamera"));
    return () => stopCamera();
  }, []);

  const stopCamera = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (videoElRef.current) videoElRef.current.srcObject = null;
  };

  // ── Capture photo ──────────────────────────────────────────────
  const capturePhoto = () => {
    const video = videoElRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);
    // Lightly enhance: increase contrast for better OCR
    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const d = imgData.data;
    for (let i = 0; i < d.length; i += 4) {
      const gray = 0.299 * d[i] + 0.587 * d[i+1] + 0.114 * d[i+2];
      // High-contrast B&W for receipts
      const val = gray > 128 ? 255 : 0;
      d[i] = d[i+1] = d[i+2] = val;
    }
    ctx.putImageData(imgData, 0, 0);
    const img = canvas.toDataURL("image/jpeg", 0.95);
    setCapturedImage(img);
    stopCamera();
    // Direkte scan: fotoyu çeker çekmez otomatik OCR başlat (ayrı "Læs kvittering" adımı yok)
    runOCR(img);
  };

  // ── Run Tesseract OCR ──────────────────────────────────────────
  const runOCR = async (imgArg) => {
    const img = imgArg || capturedImage;
    if (!img) return;
    setStep("ocr");
    setOcrLoading(true);
    setOcrError(null);
    try {
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("dan+eng"); // Danish + English
      const { data: { text } } = await worker.recognize(img);
      await worker.terminate();

      // ── Danish number parsing. Thousands separator may be a DOT (Damifo:
      //    "1.860") or a SPACE (Ragn-Sells: "9 140"); comma is the decimal sign.
      //    "1.860"→1860, "28.860"→28860, "9 140"→9140, "27.000"→27000, "1,5"→1.5
      const parseDanishNum = (s) => {
        if (!s) return NaN;
        s = s.replace(/\s+/g, " ").trim();
        if (/^\d{1,3}( \d{3})+$/.test(s)) return parseFloat(s.replace(/ /g, "")); // space thousands
        s = s.replace(/ /g, "");
        if (s.includes(".") && s.includes(",")) return parseFloat(s.replace(/\./g, "").replace(",", "."));
        if (s.includes(",")) return parseFloat(s.replace(",", "."));
        if (s.includes(".")) {
          if (/^\d{1,3}(\.\d{3})+$/.test(s)) return parseFloat(s.replace(/\./g, "")); // dot thousands
          return parseFloat(s); // genuine decimal like 12.5
        }
        return parseFloat(s);
      };

      // Weight - weighbridge slips (vejebilag) put the REAL weight on the
      // "Netto:" line. Always prefer it over gross/tare; fall back to any kg.
      // Number capture allows spaces/dots/commas between digit groups.
      let weight = null;
      const nettoMatch = text.match(/netto[:\s]*([\d][\d.,\s]*\d)\s*kg/i);
      if (nettoMatch) {
        const v = parseDanishNum(nettoMatch[1]);
        if (v > 0 && v < 1000000) weight = v;
      }
      if (weight == null) {
        const kgPatterns = [
          /(?:netto|brutto|vægt|vaegt)[:\s]*([\d][\d.,\s]*\d)\s*kg/i,
          /([\d][\d.,\s]*\d)\s*kg/i,
          /([\d]+)\s*kg/i,
        ];
        for (const pat of kgPatterns) {
          const m = text.match(pat);
          if (m) {
            const v = parseDanishNum(m[1]);
            if (v > 0 && v < 1000000) { weight = v; break; }
          }
        }
      }

      // Registration / vehicle number - labels vary by company:
      // "Bil: EN80254", "Regnr en80295", "Kortnr: ...". Also classic "AB 12 345".
      let plate = null;
      const bilMatch = text.match(/(?:bil|kortnr|regnr|reg\.?\s*nr)[:\s]+([A-Za-z]{2}\s?\d{4,6})/i);
      const classic = text.match(/\b([A-Z]{2})\s?(\d{2})\s?(\d{3})\b/);
      if (bilMatch) plate = bilMatch[1].toUpperCase().replace(/\s+/g, "");
      else if (classic) plate = `${classic[1].toUpperCase()} ${classic[2]} ${classic[3]}`;

      // Date - dd/mm yyyy, dd/mm/yyyy, dd.mm.yyyy, dd-mm-yyyy or yyyy-mm-dd
      let recDate = null;
      const ymd = text.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
      const dmy = text.match(/\b(\d{2})[.\/-](\d{2})[\s.\/-]+(\d{4})\b/);
      if (ymd) recDate = `${ymd[1]}-${ymd[2]}-${ymd[3]}`;
      else if (dmy) recDate = `${dmy[3]}-${dmy[2]}-${dmy[1]}`;

      // Slip number for traceability - "Vejebilag" (Damifo) or
      // "Registreringsnr" (Ragn-Sells) etc.
      let slipNo = null;
      const slip = text.match(/(?:vejebilag|registreringsnr|bilagsnr)[:\s]*(\d{4,})/i);
      if (slip) slipNo = slip[1];

      setOcrResult({ weight, plate, recDate, slipNo, text: text.slice(0, 400) });
      setEditedWeight(weight ? String(weight) : "");
      setStep("confirm");
    } catch (e) {
      console.error("OCR error:", e);
      setOcrError("OCR fejlede - indtast vægt manuelt");
      setStep("confirm");
      setOcrResult({ weight: null, text: "" });
    } finally {
      setOcrLoading(false);
    }
  };

  const retake = () => {
    setCapturedImage(null); setOcrResult(null); setOcrError(null);
    setEditedWeight(""); setStep("camera");
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }
    }).then(s => { streamRef.current = s; if (videoElRef.current) videoElRef.current.srcObject = s; })
      .catch(() => {});
  };

  const handleConfirm = () => {
    const w = parseFloat(editedWeight);
    if (onWeightDetected && w > 0) onWeightDetected(w, { plate: ocrResult?.plate || null, recDate: ocrResult?.recDate || null });
    if (capturedImage) onCapture(capturedImage);
    onClose();
  };

  // ── RENDER ─────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black z-[9999] flex flex-col" data-testid="pro-receipt-scanner" style={{ height: "100dvh" }}>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/80 flex-shrink-0">
        <button onClick={() => { stopCamera(); onClose(); }} className="w-10 h-10 flex items-center justify-center rounded-full bg-white/10">
          <X className="w-5 h-5 text-white" />
        </button>
        <span className="text-white font-bold text-sm">
          {step === "camera" && "📸 Tag foto af kvitteringen"}
          {step === "preview" && "Kontroller foto"}
          {step === "ocr" && "🔍 Læser kvittering..."}
          {step === "confirm" && "Bekræft vægt"}
        </span>
        <div className="w-10" />
      </div>

      {/* CAMERA step */}
      {step === "camera" && (
        <div className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
          <div ref={videoContainerRef} className="flex-1 relative bg-black overflow-hidden">
            {/* Scan frame overlay */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
              <div style={{ width: "85%", height: "55%", border: "2px solid rgba(255,255,255,0.7)", borderRadius: 12, boxShadow: "0 0 0 9999px rgba(0,0,0,0.45)" }}>
                <div style={{ position:"absolute", top:8, left:8, width:24, height:24, borderTop:"3px solid #EF4444", borderLeft:"3px solid #EF4444", borderRadius:"4px 0 0 0" }} />
                <div style={{ position:"absolute", top:8, right:8, width:24, height:24, borderTop:"3px solid #EF4444", borderRight:"3px solid #EF4444", borderRadius:"0 4px 0 0" }} />
                <div style={{ position:"absolute", bottom:8, left:8, width:24, height:24, borderBottom:"3px solid #EF4444", borderLeft:"3px solid #EF4444", borderRadius:"0 0 0 4px" }} />
                <div style={{ position:"absolute", bottom:8, right:8, width:24, height:24, borderBottom:"3px solid #EF4444", borderRight:"3px solid #EF4444", borderRadius:"0 0 4px 0" }} />
              </div>
            </div>
            <p className="absolute bottom-4 left-0 right-0 text-center text-white/70 text-xs z-10">Hold kvitteringen inden for rammen</p>
          </div>
          <div className="bg-black px-6 py-5 flex items-center justify-center flex-shrink-0">
            <button onClick={capturePhoto}
              className="w-20 h-20 rounded-full bg-white flex items-center justify-center shadow-2xl active:scale-95 transition-transform">
              <Camera className="w-9 h-9 text-slate-800" />
            </button>
          </div>
        </div>
      )}

      {/* PREVIEW step */}
      {step === "preview" && capturedImage && (
        <div className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
          <div className="flex-1 overflow-hidden flex items-center justify-center bg-gray-900">
            <img src={capturedImage} alt="Kvittering" className="max-w-full max-h-full object-contain" />
          </div>
          <div className="bg-black px-4 py-4 flex gap-3 flex-shrink-0">
            <button onClick={retake}
              className="flex-1 py-3.5 bg-slate-700 text-white rounded-xl font-bold active:bg-slate-600">
              Tag om
            </button>
            <button onClick={runOCR}
              className="flex-1 py-3.5 bg-red-600 text-white rounded-xl font-bold flex items-center justify-center gap-2 active:bg-red-700">
              <ScanLine className="w-5 h-5" /> Læs kvittering
            </button>
          </div>
        </div>
      )}

      {/* OCR LOADING step */}
      {step === "ocr" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 bg-slate-900 px-8">
          <div className="w-16 h-16 border-4 border-red-500 border-t-transparent rounded-full animate-spin" />
          <div className="text-center">
            <p className="text-white font-bold text-lg">Læser kvittering...</p>
            <p className="text-slate-400 text-sm mt-1">Finder vægt og data automatisk</p>
          </div>
        </div>
      )}

      {/* CONFIRM step */}
      {step === "confirm" && (
        <div className="flex-1 flex flex-col bg-slate-900 px-5 py-4 gap-4" style={{ minHeight: 0, overflowY: "auto" }}>

          {/* Photo thumbnail */}
          {capturedImage && (
            <img src={capturedImage} alt="Kvittering" className="w-full h-36 object-cover rounded-xl border-2 border-slate-600" />
          )}

          {/* OCR result */}
          {ocrResult?.weight ? (
            <div className="bg-emerald-900/40 border border-emerald-600 rounded-xl p-4">
              <p className="text-emerald-400 text-xs font-bold uppercase tracking-wide mb-1">✓ Vægt fundet automatisk</p>
              <p className="text-white text-3xl font-mono font-bold">{ocrResult.weight} <span className="text-slate-400 text-lg">kg</span></p>
            </div>
          ) : (
            <div className="bg-amber-900/30 border border-amber-600 rounded-xl p-4">
              <p className="text-amber-400 text-xs font-bold uppercase tracking-wide mb-1">
                {ocrError ? "⚠️ " + ocrError : "Vægt ikke fundet automatisk"}
              </p>
              <p className="text-slate-300 text-sm">Indtast vægten manuelt nedenfor</p>
            </div>
          )}

          {/* Extra detected fields (plate / date) */}
          {(ocrResult?.plate || ocrResult?.recDate) && (
            <div className="flex gap-2">
              {ocrResult?.plate && (
                <div className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Regnr</p>
                  <p className="text-white font-mono font-bold">{ocrResult.plate}</p>
                </div>
              )}
              {ocrResult?.recDate && (
                <div className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Dato</p>
                  <p className="text-white font-mono font-bold">{ocrResult.recDate}</p>
                </div>
              )}
              {ocrResult?.slipNo && (
                <div className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Vejebilag</p>
                  <p className="text-white font-mono font-bold">{ocrResult.slipNo}</p>
                </div>
              )}
            </div>
          )}

          {/* Editable weight */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">
              {ocrResult?.weight ? "Ret vægt hvis nødvendigt:" : "Indtast vægt:"}
            </label>
            <div className="relative">
              <input
                type="number"
                value={editedWeight}
                onChange={e => setEditedWeight(e.target.value)}
                placeholder="0"
                inputMode="numeric"
                className="w-full px-4 py-4 text-2xl font-mono font-bold text-center border-2 border-slate-600 bg-slate-800 text-white rounded-xl focus:border-red-500 outline-none"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-lg">kg</span>
            </div>
          </div>

          {/* Raw OCR text (foldable) */}
          {ocrResult?.text && (
            <details className="bg-slate-800 rounded-xl p-3">
              <summary className="text-xs text-slate-400 cursor-pointer font-semibold">Læst tekst (til kontrol)</summary>
              <pre className="text-[10px] text-slate-500 mt-2 whitespace-pre-wrap font-mono leading-relaxed max-h-24 overflow-y-auto">
                {ocrResult.text}
              </pre>
            </details>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 mt-auto">
            <button onClick={retake}
              className="flex-1 py-3.5 bg-slate-700 text-white rounded-xl font-bold active:bg-slate-600">
              Tag om
            </button>
            <button onClick={handleConfirm}
              className="flex-1 py-3.5 bg-red-600 text-white rounded-xl font-bold flex items-center justify-center gap-2 active:bg-red-700">
              <CheckCircle2 className="w-5 h-5" /> Brug
            </button>
          </div>
        </div>
      )}

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
};


// Hook to detect mobile
const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(false);
  
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  return isMobile;
};

// ============= DESKTOP TOUR ROW =============

const TourRow = ({ tour, onUpdate, onDelete, onToggleOnWay, onToggleComplete, driverName, isGroupStart, isGroupEnd, isInGroup, currentDriverName, routeInfo, canDelete = false }) => {
  const [weight, setWeight] = useState(tour.weight || "");
  const [time, setTime] = useState(tour.time || "");
  
  const isClaimedByOther = tour.claimed_by && tour.claimed_by !== currentDriverName;
  
  // Extract open hours from remark if needed
  const { openFrom, openTo, cleanRemark } = extractOpenHours(tour);

  // Only update weight on Enter key or blur - not on every keystroke
  const handleWeightChange = (e) => {
    setWeight(e.target.value);
  };

  const handleWeightSubmit = () => {
    if (isClaimedByOther) return;
    const val = parseFloat(weight);
    if (val && val > 0) {
      const currentTime = new Date().toTimeString().slice(0, 5);
      onUpdate(tour.id, { weight: val, completed: true, on_way: false, time: currentTime, claimed_by: currentDriverName, claimed_by_id: "" });
    }
  };

  const handleWeightKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleWeightSubmit();
    }
  };

  const handleTimeChange = (e) => {
    const val = e.target.value;
    setTime(val);
    onUpdate(tour.id, { time: val });
  };

  useEffect(() => {
    if (tour.time !== time) setTime(tour.time || "");
  }, [tour.time]); // eslint-disable-line

  useEffect(() => {
    if (tour.weight !== undefined && tour.weight !== parseFloat(weight)) setWeight(tour.weight || "");
  }, [tour.weight]); // eslint-disable-line

  if (tour.is_pause) {
    return (
      <tr className="bg-slate-100 dark:bg-slate-800 border-b border-border" data-testid={`tour-row-${tour.id}`}>
        <td colSpan="5" className="p-3 text-center font-bold text-slate-600 dark:text-slate-400">
          <Pause className="w-4 h-4 inline mr-2" />
          PAUSE
        </td>
        <td className="p-3 text-center font-mono text-sm">-</td>
        <td className="p-3 text-center font-mono text-sm font-bold">{tour.time || "45 min"}</td>
        <td className="p-3 text-center">
          {canDelete && (
            <button onClick={() => onDelete(tour.id)} className="text-red-500 hover:text-red-600" data-testid={`delete-tour-${tour.id}`}>
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </td>
      </tr>
    );
  }

  const rowClass = isClaimedByOther && tour.completed
    ? "bg-slate-100 dark:bg-slate-800/60 opacity-70"
    : isClaimedByOther && tour.on_way
      ? "bg-amber-50 dark:bg-amber-950/30 border-l-4 border-l-amber-400 opacity-80"
      : tour.completed 
        ? "bg-emerald-100 dark:bg-emerald-950/40" 
        : tour.on_way 
          ? "bg-yellow-100 dark:bg-yellow-950/40 border-l-4 border-l-yellow-500" 
          : cleanRemark?.toLowerCase().includes("haster")
            ? "bg-orange-50 dark:bg-orange-950/30"
            : "";

  // Group border styling for same address tours - using box-shadow as border doesn't work well on tr
  const groupStyle = isInGroup 
    ? { boxShadow: 'inset 4px 0 0 0 #ef4444' }
    : {};

  // Add visual indicator for grouped rows
  const groupBgClass = isInGroup ? "bg-red-50/50 dark:bg-red-900/20" : "";

  return (
    <tr className={`${rowClass} ${groupBgClass} border-b border-border hover:bg-muted/50 transition-colors`} style={groupStyle} data-testid={`tour-row-${tour.id}`}>
      <td className="p-3 font-medium">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            {routeInfo && routeInfo.route_order && (
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex-shrink-0" data-testid={`route-order-${tour.id}`}>
                {routeInfo.route_order}
              </span>
            )}
            <span>{tour.fraction}</span>
            {tour.is_private && (
              <span className="px-2 py-0.5 bg-purple-600 text-white text-xs font-bold rounded-full">PRIVAT</span>
            )}
            {tour.is_same_day && (
              <span className="px-2 py-0.5 bg-orange-500 text-white text-xs font-bold rounded-full">SD</span>
            )}
            {routeInfo && routeInfo.has_coordinates && (
              <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full inline-flex items-center gap-0.5 ${
                routeInfo.job_type === "HAENGER" ? "bg-red-100 text-red-700 ring-1 ring-red-300" : "bg-slate-100 text-slate-600"
              }`} data-testid={`job-type-${tour.id}`}>
                {routeInfo.job_type === "HAENGER" ? (
                  <>{routeInfo.group_size}+ cont.</>
                ) : (
                  <>1 cont.</>
                )}
              </span>
            )}
            {routeInfo && routeInfo.has_coordinates && routeInfo.distance_km > 0 && (
              <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-50 text-blue-700" data-testid={`distance-${tour.id}`}>
                {routeInfo.distance_km} km
                {routeInfo.estimated_minutes > 0 && <span className="text-blue-400 ml-0.5">~{routeInfo.estimated_minutes}m</span>}
              </span>
            )}
            {cleanRemark && (
              <span className={`px-2 py-0.5 text-xs rounded-full ${
                cleanRemark.toLowerCase().includes("haster") ? "bg-red-500 text-white" 
                : cleanRemark.toLowerCase().includes("senere") ? "bg-orange-400 text-black"
                : "bg-slate-200 dark:bg-slate-700"
              }`}>{cleanRemark}</span>
            )}
          </div>
          {tour.is_private && tour.private_company && (
            <span className="text-xs text-purple-600 mt-1">🏢 {tour.private_company}</span>
          )}
          {tour.on_way && tour.claimed_by && (
            <span className="text-xs font-bold text-amber-700 dark:text-amber-400 mt-1 flex items-center gap-1">
              <Truck className="w-3 h-3" /> {tour.claimed_by} kører
            </span>
          )}
          {isClaimedByOther && tour.completed && (
            <span className="text-xs font-bold text-slate-500 mt-1 flex items-center gap-1" data-testid={`tour-completed-stamp-${tour.id}`}>
              <CheckCircle2 className="w-3 h-3" /> {tour.claimed_by} har afsluttet{tour.completed_at ? ` ${formatCompletedAt(tour.completed_at)}` : ""}
            </span>
          )}
        </div>
      </td>
      <td className="p-3 text-sm">{tour.is_private ? tour.private_company : tour.facility}</td>
      <td className="p-3 text-sm">
        <button 
          onClick={() => openInMaps(tour.address)}
          className="text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
          title={tour.address}
        >
          <Navigation className="w-4 h-4 flex-shrink-0" />
          <span className="hidden md:inline truncate max-w-[100px]">{tour.address?.split(",")[0] || tour.address}</span>
        </button>
      </td>
      <td className="p-3 font-mono text-sm">
        {tour.tour_type === "loes_afhentning"
          ? <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500 text-white text-[10px] font-black uppercase tracking-wider"><Truck className="w-3 h-3" />Løs ({tour.loose_estimated_count || "?"})</span>
          : tour.container}
      </td>
      <td className="p-3 font-mono text-xs text-muted-foreground">
        {openFrom && openTo ? `${openFrom}-${openTo}` : openFrom || ""}
      </td>
      <td className="p-3">
        <div className="flex items-center gap-1">
          <input type="number" value={weight} onChange={handleWeightChange} 
            onKeyDown={handleWeightKeyDown}
            onBlur={handleWeightSubmit}
            placeholder="kg"
            className="w-20 px-2 py-1 text-sm font-mono bg-background border border-input rounded focus:ring-2 focus:ring-red-500"
            data-testid={`weight-input-${tour.id}`} />
          {tour.receipt_image && (
            <span className="text-emerald-500" title="Kvittering vedhæftet"><Camera className="w-3.5 h-3.5" /></span>
          )}
        </div>
      </td>
      <td className="p-3">
        <input type="time" value={time} onChange={handleTimeChange}
          className="w-24 px-2 py-1 text-sm font-mono bg-background border border-input rounded focus:ring-2 focus:ring-red-500"
          data-testid={`time-input-${tour.id}`} />
      </td>
      <td className="p-3">
        <div className="flex items-center gap-1">
          {isClaimedByOther ? (
            <span className="text-xs text-slate-400 font-medium px-2 py-1 bg-slate-100 rounded">
              {tour.claimed_by}
            </span>
          ) : (
            <>
              {!tour.completed && (
                <button onClick={() => onToggleOnWay(tour.id)}
                  className={`p-1.5 rounded ${tour.on_way ? "bg-yellow-400 text-black ring-2 ring-yellow-500" : "bg-slate-200 dark:bg-slate-700"} hover:opacity-80`}
                  title={tour.on_way ? "På vej" : "Start tur"} data-testid={`onway-btn-${tour.id}`}>
                  <Truck className="w-4 h-4" />
                </button>
              )}
              <button onClick={() => onToggleComplete(tour.id)}
                className={`p-1.5 rounded ${tour.completed ? "bg-emerald-500 text-white" : "bg-slate-200 dark:bg-slate-700"} hover:opacity-80`}
                title={tour.completed ? "Færdig" : "Markér færdig"} data-testid={`complete-btn-${tour.id}`}>
                {tour.completed ? <RotateCcw className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
              </button>
              {canDelete && (
                <button onClick={() => onDelete(tour.id)}
                  className="p-1.5 rounded bg-red-100 dark:bg-red-900/30 text-red-500 hover:bg-red-200"
                  data-testid={`delete-tour-${tour.id}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </>
          )}
        </div>
      </td>
    </tr>
  );
};

// ============= ADMIN PAGE COMPONENT =============

// Admin Receipt List (fetches all receipts)
const AdminReceiptList = () => {
  const [driverList, setDriverList] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [driverDays, setDriverDays] = useState([]);
  const [expandedDay, setExpandedDay] = useState(null);
  const [viewingImage, setViewingImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const API = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    fetchDrivers();
    // Fase 17.10 (2026-02-27): Auto-refresh hvert 30 sekund mens
    // arkivet er åbent. Hvis chaufføren netop har afsluttet en tur
    // i en anden fane, behøver admin'en ikke at refresh'e manuelt.
    const intv = setInterval(() => {
      fetchDrivers();
      if (selectedDriver) {
        // Stille re-fetch - ingen loading-spinner
        axios.get(`${API}/api/driver-archive/${encodeURIComponent(selectedDriver)}`)
          .then(r => setDriverDays(r.data.days || []))
          .catch(() => {});
      }
    }, 30000);
    return () => clearInterval(intv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDriver]);

  const refreshAll = async () => {
    setLoading(true);
    try {
      await fetchDrivers();
      if (selectedDriver) {
        const res = await axios.get(`${API}/api/driver-archive/${encodeURIComponent(selectedDriver)}`);
        setDriverDays(res.data.days || []);
      }
      toast.success("Opdateret");
    } catch (_) { toast.error("Opdatering fejlede"); }
    setLoading(false);
  };

  const fetchDrivers = async () => {
    try {
      const res = await axios.get(`${API}/api/driver-archive`);
      setDriverList(res.data.drivers || []);
    } catch (e) { console.error(e); }
  };

  const openDriverFolder = async (name) => {
    setSelectedDriver(name);
    setDriverDays([]);
    setExpandedDay(null);
    setLoading(true);
    try {
      const res = await axios.get(`${API}/api/driver-archive/${encodeURIComponent(name)}`);
      setDriverDays(res.data.days || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const downloadReceiptImage = async (receiptId, desc) => {
    try {
      // Fase 17.8 (2026-02-27): Brug binary endpoint + fetch til blob så
      // store billeder ikke loader hele base64-payload i ét hug.
      const resp = await fetch(`${API}/api/receipts/${receiptId}/image-binary`, { credentials: "include" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `kvittering-${desc || receiptId}.jpg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) { toast.error("Kunne ikke downloade"); }
  };

  const viewReceiptImage = (receiptId, desc) => {
    // Fase 17.8: åbn modal med binary-URL som <img src> - browseren
    // streamer billedet progressivt, intet base64-præfix-besvær.
    setViewingImage({
      image_url: `${API}/api/receipts/${receiptId}/image-binary`,
      description: desc || "Kvittering",
    });
  };

  const viewTourImage = async (tourId) => {
    try {
      const res = await axios.get(`${API}/api/tours/${tourId}/image`);
      if (res.data.image_data) {
        setViewingImage({ image_data: res.data.image_data, description: `${res.data.plads} - ${res.data.fraction}` });
      } else {
        toast.error("Ingen foto fundet");
      }
    } catch (e) { toast.error("Kunne ikke åbne foto"); }
  };

  // Driver list view
  if (!selectedDriver) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-muted-foreground">Vælg en chauffør for at se arkiv</p>
          <button
            onClick={refreshAll}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50 inline-flex items-center gap-1.5"
            data-testid="admin-receipt-list-refresh"
            title="Opdater listen"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Opdater
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {driverList.map(name => (
            <button
              key={name}
              onClick={() => openDriverFolder(name)}
              className="flex flex-col items-center gap-2 p-4 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-orange-400 hover:bg-orange-50 dark:hover:bg-red-950/20 transition-all group"
              data-testid={`driver-folder-${name}`}
            >
              <FolderOpen className="w-8 h-8 text-amber-500 group-hover:text-red-500 transition-colors" />
              <span className="text-sm font-bold text-slate-700 dark:text-slate-200">{name}</span>
            </button>
          ))}
          {driverList.length === 0 && (
            <p className="col-span-full text-center text-muted-foreground py-8">Ingen chauffører fundet</p>
          )}
        </div>
      </div>
    );
  }

  // Driver detail view - days list
  return (
    <div>
      {/* Back button + driver name */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => { setSelectedDriver(null); setDriverDays([]); }}
          className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
          data-testid="archive-back-btn"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <FolderOpen className="w-5 h-5 text-amber-500" />
        <h3 className="text-lg font-bold">{selectedDriver}</h3>
        <span className="text-sm text-muted-foreground">{driverDays.length} dage</span>
        <button
          onClick={refreshAll}
          disabled={loading}
          className="ml-auto px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50 inline-flex items-center gap-1.5"
          data-testid="admin-driver-detail-refresh"
          title="Opdater data for denne chauffør"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Opdater
        </button>
      </div>

      {loading && <p className="text-center py-8 text-muted-foreground">Indlæser...</p>}

      {/* Days list */}
      <div className="space-y-2">
        {driverDays.map(day => {
          const isExpanded = expandedDay === day.date;
          const completedTours = day.tours.filter(t => t.completed && !t.is_pause);
          const pauseTours = day.tours.filter(t => t.is_pause);
          const totalWeight = completedTours.reduce((s, t) => s + (t.weight || 0), 0);
          // Fase 18.1 (2026-02-28): time_summary (driver_time_entries) er
          // den autoritative kilde. Fald tilbage til legacy session/report
          // hvis chaufføren ikke har stemplet ind/ud den dag.
          const ts = day.time_summary;
          const legacy = day.sessions?.[0] || day.reports?.[0];
          const startT = ts?.start || legacy?.start_time || "";
          const endT = ts?.end || legacy?.end_time || "";
          const workMin = ts?.work_min || 0;
          const pauseMin = ts?.pause_min || 0;
          const gapMin = ts?.gap_min || 0;
          const isOpen = !!ts?.open;
          const fmtH = (m) => {
            if (!m || m <= 0) return "0m";
            const h = Math.floor(m / 60);
            const mm = m % 60;
            return h > 0 ? (mm > 0 ? `${h}t ${mm}m` : `${h}t`) : `${mm}m`;
          };
          const inclusiveMin = (ts?.span_min || 0); // start→slut incl. alt

          return (
            <div key={day.date} className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              {/* Day header - clickable */}
              <button
                onClick={() => setExpandedDay(isExpanded ? null : day.date)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${isExpanded ? "bg-orange-50 dark:bg-orange-950/20" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}
                data-testid={`day-folder-${day.date}`}
              >
                <Calendar className="w-4 h-4 text-red-500 flex-shrink-0" />
                <span className="font-bold text-sm">{day.date.split("-").reverse().join(".")}</span>
                <div className="flex-1 flex items-center gap-2 flex-wrap">
                  {startT && (
                    <span
                      className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full"
                      data-testid={`day-times-${day.date}`}
                    >
                      🕐 {startT}–{endT || (isOpen ? "åben" : "-")}
                    </span>
                  )}
                  {workMin > 0 && (
                    <span
                      className="text-xs bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full"
                      title={`Arbejde: ${fmtH(workMin)}\nPause: ${fmtH(pauseMin)}\nIkke-stemplet: ${fmtH(gapMin)}\nFra første ind til sidste ud: ${fmtH(inclusiveMin)}`}
                      data-testid={`day-duration-${day.date}`}
                    >
                      ⏱ {fmtH(workMin)}
                      {pauseMin > 0 && <span className="opacity-70"> + {fmtH(pauseMin)} pause</span>}
                    </span>
                  )}
                  <span className="text-xs bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full">{completedTours.length} ture</span>
                  {totalWeight > 0 && <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 rounded-full">{totalWeight} kg</span>}
                  {day.receipts.length > 0 && <span className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded-full">{day.receipts.length} kvit.</span>}
                  {pauseTours.length > 0 && <span className="text-xs bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 px-2 py-0.5 rounded-full">{pauseTours.length} pause</span>}
                </div>
                {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              </button>

              {/* Expanded day content */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-4 border-t border-slate-200 dark:border-slate-700">
                  {/* Working hours summary */}
                  {(ts?.any || legacy) && (
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
                      {(() => {
                        // Fase 18.3 (2026-02-28): Pladsfeltet var tomt fordi
                        // legacy-sessions ofte mangler. Brug i stedet de unikke
                        // pladser fra dagens ture som primær kilde, og fald
                        // tilbage til legacy-feltet hvis ingen ture.
                        const pladsFromTours = Array.from(new Set(
                          (day.tours || [])
                            .map(t => t.plads || t.plads_name || "")
                            .filter(Boolean)
                        ));
                        const pladsLabel = pladsFromTours.length > 0
                          ? pladsFromTours.join(", ")
                          : (legacy?.current_plads || legacy?.plads || "-");
                        return <div><span className="text-muted-foreground">Plads:</span> <span className="font-bold">{pladsLabel}</span></div>;
                      })()}
                      <div><span className="text-muted-foreground">Start:</span> <span className="font-bold">{startT || "-"}</span></div>
                      <div><span className="text-muted-foreground">Slut:</span> <span className="font-bold">{endT || (isOpen ? "åben" : "-")}</span></div>
                      <div><span className="text-muted-foreground">Vogn:</span> <span className="font-bold">{legacy?.vehicle_reg || "-"}</span></div>
                      {ts?.any && (
                        <>
                          <div><span className="text-muted-foreground">Arbejde:</span> <span className="font-bold">{fmtH(workMin)}</span></div>
                          {pauseMin > 0 && <div><span className="text-muted-foreground">Pause:</span> <span className="font-bold">{fmtH(pauseMin)}</span></div>}
                          {gapMin > 0 && <div><span className="text-muted-foreground">Ikke-stemplet:</span> <span className="font-bold text-amber-600">{fmtH(gapMin)}</span></div>}
                          <div><span className="text-muted-foreground">Total (start→slut):</span> <span className="font-bold">{fmtH(inclusiveMin)}</span></div>
                        </>
                      )}
                    </div>
                  )}

                  {/* Fase 18.1: Tids-stempel-pills (IND/PAUSE/UD-vinduer) */}
                  {ts?.any && (ts.work_slices.length > 0 || ts.pause_slices.length > 0) && (
                    <div data-testid={`day-slices-${day.date}`}>
                      <h4 className="text-xs font-bold text-blue-600 uppercase mb-2">Stempler ({ts.work_slices.length + ts.pause_slices.length})</h4>
                      <div className="flex flex-wrap gap-2">
                        {[...ts.work_slices, ...ts.pause_slices]
                          .sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""))
                          .map((s, i) => {
                            const isPause = s.slice_type === "pause";
                            const cls = isPause
                              ? "bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 border-amber-300 dark:border-amber-700"
                              : "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200 border-emerald-300 dark:border-emerald-700";
                            const label = isPause ? "☕" : "▶";
                            const endLabel = s.end_time || (s.open ? "åben" : "-");
                            return (
                              <span
                                key={s.id || i}
                                className={`text-xs px-2.5 py-1 rounded-full border ${cls} inline-flex items-center gap-1`}
                                title={`${isPause ? "Pause" : "Arbejde"} • ${fmtH(s.duration_minutes)}${s.manual ? " • manuel" : ""}${s.reason ? " • " + s.reason : ""}`}
                              >
                                <span>{label}</span>
                                <span className="font-mono">{s.start_time}–{endLabel}</span>
                                {s.duration_minutes > 0 && <span className="opacity-60">({fmtH(s.duration_minutes)})</span>}
                              </span>
                            );
                          })}
                      </div>
                    </div>
                  )}

                  {/* Tours table */}
                  {completedTours.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-red-600 uppercase mb-2">Ture ({completedTours.length})</h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="bg-slate-100 dark:bg-slate-800">
                              <th className="text-left px-2 py-1 font-bold">Start</th>
                              <th className="text-left px-2 py-1 font-bold">Slut</th>
                              <th className="text-left px-2 py-1 font-bold">Container</th>
                              <th className="text-left px-2 py-1 font-bold">Fraktion</th>
                              <th className="text-left px-2 py-1 font-bold">Adresse</th>
                              <th className="text-left px-2 py-1 font-bold">Vægt</th>
                              <th className="text-left px-2 py-1 font-bold">Kvit.</th>
                            </tr>
                          </thead>
                          <tbody>
                            {completedTours.sort((a, b) => (a.time || "").localeCompare(b.time || "")).map((t, i) => {
                              // Fase 17.12: Slut-tid hentes fra completed_at (ISO 8601) i lokal-tid.
                              const endTimeStr = t.completed_at
                                ? (() => { try { const d = new Date(t.completed_at); return isNaN(d) ? "-" : d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }); } catch (_) { return "-"; } })()
                                : "-";
                              // Antal kvitteringer linket til denne tur
                              const tourReceipts = (day.receipts || []).filter(r => r.tour_id === t.id);
                              return (
                                <tr key={t.id || i} className={i % 2 === 0 ? "" : "bg-slate-50 dark:bg-slate-900"}>
                                  <td className="px-2 py-1 font-mono font-bold">{t.time || "-"}</td>
                                  <td className="px-2 py-1 font-mono">{endTimeStr}</td>
                                  <td className="px-2 py-1">{t.container || "-"}</td>
                                  <td className="px-2 py-1">{t.fraction || "-"}{t.is_same_day ? <span className="ml-1 px-1 py-0.5 bg-red-600 text-white text-[8px] font-bold rounded">SD</span> : ""}</td>
                                  <td className="px-2 py-1">{t.address || "-"}</td>
                                  <td className="px-2 py-1 font-bold">{t.weight ? `${t.weight} kg` : "-"}</td>
                                  <td className="px-2 py-1">
                                    {tourReceipts.length > 0 ? (
                                      <div className="flex items-center gap-1">
                                        {tourReceipts.map(r => (
                                          <button
                                            key={r.id}
                                            onClick={() => viewReceiptImage(r.id, r.description)}
                                            className="text-amber-600 hover:text-amber-800 cursor-pointer"
                                            title={`Vis kvittering (${r.final_weight_kg || "?"} kg)`}
                                            data-testid={`tour-receipt-${r.id}`}
                                          >
                                            <Camera className="w-3 h-3" />
                                          </button>
                                        ))}
                                        {tourReceipts.length > 1 && <span className="text-[9px] text-amber-700">×{tourReceipts.length}</span>}
                                      </div>
                                    ) : t.has_receipt_image ? (
                                      <button onClick={() => viewTourImage(t.id)} className="text-emerald-500 hover:text-emerald-700 cursor-pointer" title="Vis foto"><Camera className="w-3 h-3" /></button>
                                    ) : ""}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Pauses */}
                  {pauseTours.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-orange-600 uppercase mb-1">Pauser</h4>
                      <div className="flex flex-wrap gap-2">
                        {pauseTours.map((p, i) => (
                          <span key={i} className="text-xs bg-orange-100 dark:bg-orange-900/30 text-orange-700 px-2 py-1 rounded">{p.time || "-"}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Receipts - thumbnails */}
                  {day.receipts.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-amber-600 uppercase mb-2">Kvitteringer ({day.receipts.length})</h4>
                      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
                        {day.receipts.map((r) => {
                          // Fase 17.12: Vis hvilken tur kvitteringen hører til.
                          const linkedTour = (day.tours || []).find(t => t.id === r.tour_id);
                          const tourLabel = linkedTour
                            ? `Tur ${linkedTour.time || "?"} · ${linkedTour.fraction || linkedTour.container || ""}`.trim()
                            : (r.tour_id ? "Ukendt tur" : "Løs kvittering");
                          return (
                          <div key={r.id} className="border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-center group hover:border-orange-400 transition-colors">
                            {/* Fase 17.8: Vis ægte thumbnail via binary endpoint
                                i stedet for et statisk kamera-ikon. */}
                            <button
                              type="button"
                              onClick={() => viewReceiptImage(r.id, r.description)}
                              className="w-full h-16 bg-slate-100 dark:bg-slate-800 rounded mb-1 overflow-hidden flex items-center justify-center cursor-pointer"
                              title="Vis billede"
                            >
                              <img
                                src={`${API}/api/receipts/${r.id}/image-binary`}
                                alt={r.description || "Kvittering"}
                                className="w-full h-full object-cover"
                                loading="lazy"
                                onError={(e) => { e.currentTarget.style.display = "none"; }}
                              />
                            </button>
                            {/* Tour-link badge */}
                            <p
                              className={`text-[9px] truncate font-semibold ${linkedTour ? "text-blue-700 dark:text-blue-300" : "text-slate-400 italic"}`}
                              title={tourLabel}
                              data-testid={`receipt-tour-link-${r.id}`}
                            >
                              {tourLabel}
                            </p>
                            <p className="text-[10px] text-slate-600 dark:text-slate-400 truncate">{r.final_weight_kg ? `${r.final_weight_kg} kg` : (r.description || "Kvittering")}</p>
                            {r.amount > 0 && <p className="text-[10px] font-bold text-emerald-600">{r.amount} kr</p>}
                            <div className="flex gap-1 mt-1">
                              <button
                                onClick={() => viewReceiptImage(r.id, r.description)}
                                className="flex-1 text-[9px] px-1 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                                data-testid={`view-receipt-${r.id}`}
                              >
                                Vis
                              </button>
                              <button
                                onClick={() => downloadReceiptImage(r.id, r.description)}
                                className="flex-1 text-[9px] px-1 py-0.5 bg-emerald-100 text-emerald-700 rounded hover:bg-emerald-200 transition-colors"
                                data-testid={`download-receipt-${r.id}`}
                              >
                                Download
                              </button>
                            </div>
                          </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {!loading && driverDays.length === 0 && (
          <p className="text-center text-muted-foreground py-8">Ingen data for denne chauffør</p>
        )}
      </div>

      {/* Image viewer modal */}
      {viewingImage && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4" onClick={() => setViewingImage(null)}>
          <div className="relative max-w-lg w-full bg-white dark:bg-slate-800 rounded-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-3 border-b">
              <span className="text-sm font-bold">{viewingImage.description || "Kvittering"}</span>
              <button onClick={() => setViewingImage(null)} className="p-1 hover:bg-slate-100 rounded"><X className="w-4 h-4" /></button>
            </div>
            {(viewingImage.image_url || viewingImage.image_data) ? (
              <img
                src={viewingImage.image_url || (String(viewingImage.image_data || "").startsWith("data:") ? viewingImage.image_data : `data:image/jpeg;base64,${viewingImage.image_data}`)}
                alt="Kvittering"
                className="w-full"
              />
            ) : (
              <div className="p-8 text-center text-muted-foreground">Ingen billede</div>
            )}
            <div className="p-3 border-t">
              <button
                onClick={async () => {
                  try {
                    const resp = await fetch(viewingImage.image_url || viewingImage.image_data, { credentials: "include" });
                    if (!resp.ok) throw new Error("HTTP " + resp.status);
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = `kvittering-${viewingImage.description || "scan"}.jpg`;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    setTimeout(() => URL.revokeObjectURL(url), 5000);
                  } catch (e) { toast.error("Download fejlede"); }
                }}
                className="w-full block text-center py-2 bg-red-600 text-white rounded-lg font-bold text-sm hover:bg-red-700"
              >
                Download billede
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const AdminPage = ({ onLogout, showConfirm, hideConfirm }) => {
  // Cross-company switching (logistics_admin may manage multiple companies)
  const { user: authUser, actingCompanyId, setActingCompanyId } = useAuth();
  // Fase 15.40 (2026-02-22): Klient-platformsfunktioner - Planlæg-ressourcer-
  // tab + view gated bag `estimate`-feature-flaget. Default OFF.
  // Fase 15.41 (2026-02-22): Tab vises også når `loes_afhentning` er aktiv
  // (begge features producerer rækker i ressource-planlægningen).
  const isFeatureEnabled = useFeatureFlag();
  const estimateEnabled = isFeatureEnabled("estimate");
  const loesAfhentningEnabled = isFeatureEnabled("loes_afhentning");
  const resourcePlanningEnabled = estimateEnabled || loesAfhentningEnabled;
  const [managedCompanies, setManagedCompanies] = useState([]);
  useEffect(() => {
    if (!authUser) return;
    if (authUser.role !== "logistics_admin" && authUser.role !== "super_admin") return;
    axios.get(`${API}/auth/managed-companies`)
      .then(({ data }) => setManagedCompanies(Array.isArray(data) ? data : []))
      .catch(() => setManagedCompanies([]));
  }, [authUser]);
  const effectiveCompanyId = actingCompanyId || authUser?.company_id || "";
  const activeCompany = managedCompanies.find(c => c.id === effectiveCompanyId);
  // 2026-10-16: Premium (selvstændigt logistikfirma) vs. partner (adgang via
  // genbrugsplads-kunder) + om firmaet har tilknyttede kunder. Styrer hvilke
  // genbrugsplads-funktioner der vises. Se LOGISTICS_TIERS.md.
  const [logisticsProfile, setLogisticsProfile] = useState(null);
  useEffect(() => {
    if (authUser?.role !== "logistics_admin") return;
    axios.get(`${API}/logistics/profile`).then(r => setLogisticsProfile(r.data)).catch(() => setLogisticsProfile(null));
  }, [authUser?.role, authUser?.company_id]);
  const isPremiumLogistics = !!logisticsProfile?.is_premium;
  // Premium-firmaer arbejder med "lokationer"; partnere med genbrugspladser.
  const siteWord = isPremiumLogistics ? "lokation" : "genbrugsplads";

  const [drivers, setDrivers] = useState([]);
  // Inaktive chauffører kan ikke logge ind og skal ikke kunne få ture.
  const activeDrivers = useMemo(() => drivers.filter(d => d.active !== false), [drivers]);
  const [stats, setStats] = useState([]);
  const [messages, setMessages] = useState([]);
  // Fase 15.14/15.15 (2026-02-XX): Konfigurerbar lønperiode pr. logistik-firma.
  // - cycle_type: "monthly" | "biweekly" | "weekly"
  // - start_day: 1-28 (monthly)
  // - anchor_date: YYYY-MM-DD (weekly/biweekly)
  // Bruges af Arkiv-fanens getCycleInfo() til at gruppere dagsrapporter.
  // Default = monthly day 20 (matcher tidligere hardkodet adfærd).
  const [payrollSettings, setPayrollSettings] = useState({
    payroll_cycle_type: "monthly",
    payroll_start_day: 20,
    payroll_anchor_date: "",
  });
  const refreshPayrollSettings = React.useCallback(async () => {
    try {
      const r = await axios.get(`${API}/company/payroll-settings`);
      setPayrollSettings({
        payroll_cycle_type: r.data?.payroll_cycle_type || "monthly",
        payroll_start_day: Number(r.data?.payroll_start_day) || 20,
        payroll_anchor_date: r.data?.payroll_anchor_date || "",
      });
    } catch (_) { /* behold defaults */ }
  }, []);
  useEffect(() => { refreshPayrollSettings(); }, [refreshPayrollSettings]);
  
  // New state for plads management and history
  const [pladsList, setPladsList] = useState([]);
  const [newPladsName, setNewPladsName] = useState("");
  const [newPladsCity, setNewPladsCity] = useState("");
  const [newPladsAddress, setNewPladsAddress] = useState("");
  const [newPladsLat, setNewPladsLat] = useState("");
  const [newPladsLng, setNewPladsLng] = useState("");
  const [editingPlads, setEditingPlads] = useState(null);
  const [reportHistory, setReportHistory] = useState([]);
  const [activeTab, setActiveTab] = useState("tours"); // tours (default), schedule, drivers, statistics (Rapportering), priser | Mere: plads, archives, team, settings
  // 2026-10-17: Koordinator-rettigheder. Administratorer (og ældre sessioner
  // uden felt) har alt; backend håndhæver det samme.
  const can = useMemo(() => {
    const p = authUser?.permissions;
    const all = ["tours_edit", "tours_assign", "tours_delete", "messages", "planning", "drivers", "reports",
      "economy_view", "economy_edit", "locations", "archive", "settings", "team"];
    if (!p || !Object.keys(p).length) return Object.fromEntries(all.map(k => [k, true]));
    return Object.fromEntries(all.map(k => [k, !!p[k]]));
  }, [authUser]);
  useEffect(() => {
    const need = { schedule: "planning", drivers: "drivers", statistics: "reports", priser: "economy_view",
      plads: "locations", archives: "archive", settings: "settings", team: "team" }[activeTab];
    if (need && !can[need]) setActiveTab("tours");
  }, [activeTab, can]);
  const [archivesSubTab, setArchivesSubTab] = useState("pdf"); // pdf | receipts | tours - within "Arkiv" tab
  const [receiptsArchiveView, setReceiptsArchiveView] = useState("table"); // table | drivers - Fase 17 merged archive view mode
  
  // Daily Overview state
  const [dailyOverview, setDailyOverview] = useState(null);
  const [adminMessages, setAdminMessages] = useState([]);
  const [replyToDriver, setReplyToDriver] = useState(null);
  const [replyText, setReplyText] = useState("");
  
  // PDF Archives state
  const [pdfArchives, setPdfArchives] = useState([]);
  
  // Container Orders state
  const [containerOrders, setContainerOrders] = useState([]);
  const [orderLocations, setOrderLocations] = useState([]);
  const [newLocation, setNewLocation] = useState({ code: "", name: "" });
  const [selectedOrderLocation, setSelectedOrderLocation] = useState("");
  const [editingOrder, setEditingOrder] = useState(null);
  
  // Statistics state
  const [statisticsData, setStatisticsData] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsPeriod, setStatsPeriod] = useState(6);
  
  // Tour management state (moved from driver page)
  const [adminSelectedPlads, setAdminSelectedPlads] = useState("");
  const [adminAddressesFor, setAdminAddressesFor] = useState(null); // plads object whose addresses we manage
  // Fase 6 (2026-06-17): Audit-log timeline modal for a specific tour
  const [auditTour, setAuditTour] = useState(null); // tour object or null
  // Fase 14 (2026-06-19): "Ret tur"-modal - admin kan genåbne en afsluttet
  // tur, ændre opgavetype, rette vægt eller slette en fejlbestilt tur.
  const [editTour, setEditTour] = useState(null); // tour object or null
  const [mailText, setMailText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [showArgoModal, setShowArgoModal] = useState(false);
  const [argoText, setArgoText] = useState("");
  const [argoParsed, setArgoParsed] = useState([]);
  const [argoLoading, setArgoLoading] = useState(false);
  // Fase 4.1 (2026-06-16): Tour-template download/upload
  const [templateUploading, setTemplateUploading] = useState(false);
  const [templateUploadResult, setTemplateUploadResult] = useState(null);
  // Firma tur (private/company tour) modal
  const [showFirmaModal, setShowFirmaModal] = useState(false);
  const [firmaLoading, setFirmaLoading] = useState(false);
  const [firmaForm, setFirmaForm] = useState({
    firma: "",
    pickups: [""],         // one or more pickup addresses
    deliveries: [{ company: "", address: "" }], // one or more delivery targets
    note: ""
  });
  const [adminRouteOptimization, setAdminRouteOptimization] = useState(null);
  const [adminTours, setAdminTours] = useState([]);
  // 2026-10-18 (P1): "Planlæg ture" (split-view tildeling) er fjernet - ture
  // tildeles på Ture-siden. Planlægning viser kun Tid & ressourcer.
  const [planningView, setPlanningView] = useState("time");
  const [adminReportId, setAdminReportId] = useState("");
  const [adminTourFilterDriver, setAdminTourFilterDriver] = useState("");
  // Fase 7 (2026-06-17): Customer separation filter - when LA serves multiple
  // customers (ARGO, Helsingør Forsyning, …) they can isolate the plads/tours
  // view to one kunde at a time. Empty = vis alle kunder grupperet.
  const [adminCustomerFilter, setAdminCustomerFilter] = useState("");
  const [adminReportDate, setAdminReportDate] = useState(() => {
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, "0");
    const d = String(today.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  });
  
  // Driver schedule state - each driver's assigned plads for today
  const [driverSchedule, setDriverSchedule] = useState({}); // { driverId: "pladsName" or "FRI" }
  
  // Weekly schedule state
  const [weekStart, setWeekStart] = useState(() => {
    const today = new Date();
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1); // Monday
    const monday = new Date(today.setDate(diff));
    return `${monday.getFullYear()}-${String(monday.getMonth()+1).padStart(2,"0")}-${String(monday.getDate()).padStart(2,"0")}`;
  });
  const [weeklySchedule, setWeeklySchedule] = useState({}); // { "driverId-date": "plads" }
  const [viewMode, setViewMode] = useState("daily"); // "daily" or "weekly"

  // Get week dates
  const getWeekDates = useCallback(() => {
    const dates = [];
    const start = new Date(weekStart + "T12:00:00");
    for (let i = 0; i < 7; i++) {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      dates.push(`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`);
    }
    return dates;
  }, [weekStart]);

  const fetchWeeklySchedule = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/schedule?week_start=${weekStart}`);
      const scheduleMap = {};
      res.data.forEach(s => {
        scheduleMap[`${s.driver_id}-${s.date}`] = s.plads;
      });
      setWeeklySchedule(scheduleMap);
    } catch (e) {
      console.error("Error fetching weekly schedule:", e);
    }
  }, [weekStart]);

  const fetchData = useCallback(async () => {
    try {
      const [driversRes, statsRes, messagesRes, pladsRes, historyRes] = await Promise.all([
        axios.get(`${API}/drivers`),
        axios.get(`${API}/admin/stats`),
        axios.get(`${API}/messages`),
        axios.get(`${API}/plads`),
        axios.get(`${API}/reports/history?days=30`)
      ]);
      setDrivers(driversRes.data);
      setStats(statsRes.data);
      setMessages(messagesRes.data);
      setPladsList(pladsRes.data);
      setReportHistory(historyRes.data);
      
      // Initialize driver schedule with their default area
      const initialSchedule = {};
      driversRes.data.forEach(d => {
        initialSchedule[d.id] = d.area || "";
      });
      setDriverSchedule(initialSchedule);
    } catch (e) {
      console.error("Error fetching admin data:", e);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchWeeklySchedule(); }, [fetchWeeklySchedule]);

  // Refetch ALL admin data when the active company changes (cross-company switcher)
  useEffect(() => {
    if (!authUser) return;
    fetchData();
    fetchWeeklySchedule();
    // adminTours / dailyOverview / messages / pdfArchives effects below will
    // re-run automatically thanks to actingCompanyId being part of their deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actingCompanyId]);
  
  // Fetch daily overview
  const fetchDailyOverview = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/daily-overview?date=${adminReportDate}`);
      setDailyOverview(res.data);
    } catch (e) {
      console.error("Error fetching daily overview:", e);
    }
  }, [adminReportDate]);
  
  // Fetch admin messages (from drivers)
  const fetchAdminMessages = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/messages/admin`);
      setAdminMessages(res.data || []);
    } catch (e) {
      console.error("Error fetching admin messages:", e);
    }
  }, []);
  
  // Fetch PDF archives
  const fetchPdfArchives = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/pdf-archive`, { params: { days: 365 } });
      setPdfArchives(res.data || []);
    } catch (e) {
      console.error("Error fetching PDF archives:", e);
    }
  }, []);
  
  useEffect(() => { 
    fetchDailyOverview(); 
    fetchAdminMessages(); 
    fetchPdfArchives();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchDailyOverview, fetchAdminMessages, fetchPdfArchives, actingCompanyId]);

  // Fetch statistics when tab is active
  const fetchStatistics = useCallback(async (silent = false) => {
    if (silent !== true) setStatsLoading(true);
    try {
      const res = await axios.get(`${API}/admin/statistics?months=${statsPeriod}`);
      setStatisticsData(res.data);
    } catch (e) {
      console.error("Error fetching statistics:", e);
    } finally {
      setStatsLoading(false);
    }
  }, [statsPeriod]);

  // 2026-10-16: Rapportering er live - genindlæses hvert 30. sekund mens fanen
  // er åben og synlig, og straks når man vender tilbage til vinduet.
  useEffect(() => {
    if (activeTab !== "statistics") return;
    fetchStatistics();
    const tick = () => { if (!document.hidden) fetchStatistics(true); };
    const iv = setInterval(tick, 30000);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    return () => { clearInterval(iv); document.removeEventListener("visibilitychange", tick); window.removeEventListener("focus", tick); };
  }, [activeTab, fetchStatistics, actingCompanyId]);
  
  // Auto-refresh overview every 15 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchDailyOverview();
      fetchAdminMessages();
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchDailyOverview, fetchAdminMessages]);
  
  // Reply to driver message
  const handleReplyToDriver = async () => {
    if (!replyText.trim() || !replyToDriver) return;
    
    try {
      await axios.post(`${API}/messages`, {
        to_driver_id: replyToDriver.from_driver_name,
        to_driver_name: replyToDriver.from_driver_name,
        content: replyText.trim()
      });
      
      // Mark original message as read
      await axios.put(`${API}/messages/${replyToDriver.id}/read`);
      
      setReplyText("");
      setReplyToDriver(null);
      fetchAdminMessages();
      toast.success("Svar sendt");
    } catch (e) {
      toast.error("Kunne ikke sende svar");
    }
  };
  
  // Fetch container orders and locations
  const lastOrderCountRef = React.useRef(null);
  const fetchContainerOrders = useCallback(async () => {
    try {
      const query = selectedOrderLocation ? `?location_code=${selectedOrderLocation}` : "";
      const res = await axios.get(`${API}/container-orders${query}`);
      const orders = res.data || [];
      setContainerOrders(orders);

      // Notify on new pending orders
      const pendingCount = orders.filter(o => o.status === "pending").length;
      if (lastOrderCountRef.current !== null && pendingCount > lastOrderCountRef.current) {
        const newCount = pendingCount - lastOrderCountRef.current;
        toast.info(`📦 ${newCount} ny bestilling${newCount > 1 ? "er" : ""} modtaget!`, {
          duration: 6000,
        });
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("📦 Ny bestilling!", {
            body: `${newCount} ny bestilling${newCount > 1 ? "er" : ""} afventer`,
            icon: "/logo192.png",
          });
        }
      }
      lastOrderCountRef.current = pendingCount;
    } catch (e) {
      console.error("Error fetching container orders:", e);
    }
  }, [selectedOrderLocation]);
  
  const fetchOrderLocations = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/locations`);
      setOrderLocations(res.data || []);
    } catch (e) {
      console.error("Error fetching locations:", e);
    }
  }, []);
  
  useEffect(() => { fetchContainerOrders(); }, [fetchContainerOrders, actingCompanyId]);
  useEffect(() => { fetchOrderLocations(); }, [fetchOrderLocations, actingCompanyId]);
  
  // Auto-refresh orders every 15 seconds
  useEffect(() => {
    const interval = setInterval(() => { fetchContainerOrders(); }, 15000);
    return () => clearInterval(interval);
  }, [fetchContainerOrders]);
  
  // Add new location
  const handleAddLocation = async () => {
    if (!newLocation.code || !newLocation.name) {
      toast.error("Udfyld kode og navn");
      return;
    }
    try {
      await axios.post(`${API}/locations`, newLocation);
      toast.success("Lokation tilføjet");
      setNewLocation({ code: "", name: "" });
      fetchOrderLocations();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kunne ikke tilføje lokation");
    }
  };

  // Delete a location
  const handleDeleteLocation = (loc) => {
    showConfirm(
      "Slet lokation?",
      `Er du sikker på at du vil slette "${loc.code} - ${loc.name}"? Dette kan ikke fortrydes.`,
      async () => {
        hideConfirm();
        try {
          await axios.delete(`${API}/locations/${loc.id}`);
          toast.success("Lokation slettet");
          fetchOrderLocations();
        } catch (e) {
          toast.error(e.response?.data?.detail || "Kunne ikke slette lokation");
        }
      },
      "danger"
    );
  };
  
  // Update order
  const handleUpdateOrder = async (orderId, update) => {
    try {
      await axios.put(`${API}/container-orders/${orderId}`, update);
      fetchContainerOrders();
      setEditingOrder(null);
      toast.success("Ordre opdateret");
    } catch (e) {
      toast.error("Kunne ikke opdatere ordre");
    }
  };
  
  // Delete order
  const handleDeleteOrder = (orderId) => {
    showConfirm(
      "Slet ordre",
      "Er du sikker på at du vil slette denne ordre?",
      async () => {
        hideConfirm();
        try {
          await axios.delete(`${API}/container-orders/${orderId}`);
          fetchContainerOrders();
          toast.success("Ordre slettet");
        } catch (e) { toast.error("Kunne ikke slette ordre"); }
      }
    );
  };

  // Initialize admin report for today
  useEffect(() => {
    const initAdminReport = async () => {
      try {
        const existingRes = await axios.get(`${API}/reports?date=${adminReportDate}`);
        if (existingRes.data && existingRes.data.length > 0) {
          setAdminReportId(existingRes.data[0].id);
        } else {
          const res = await axios.post(`${API}/reports`, { report_date: adminReportDate, start_time: "07:00" });
          setAdminReportId(res.data.id);
        }
      } catch (e) {
        console.error("Error initializing admin report:", e);
      }
    };
    initAdminReport();
  }, [adminReportDate]);

  // Fetch tours for admin - filter by DATE to ensure daily separation
  const fetchAdminTours = useCallback(async () => {
    if (!adminReportDate) return;
    try {
      // Fase 4 (2026-06-16): "Ture"-fanen viser KUN manuelle + Argo-importerede
      // ture. Customer-orders behandles separat (statistik/arkiv-tabs).
      const res = await axios.get(`${API}/tours?date=${adminReportDate}&source=manual,argo`);
      setAdminTours(res.data);
    } catch (e) {
      console.error("Error fetching admin tours:", e);
    }
  }, [adminReportDate]);

  useEffect(() => { fetchAdminTours(); }, [adminReportDate, fetchAdminTours, actingCompanyId]);

  // Fase 11 (2026-06-18): Auto-refresh admin tours hvert 5. sekund for at
  // give "near real-time" opdatering på bestillinger fra container-siden
  // og chauffør-handlinger. (Tidligere 10 sekunder.)
  // 2026-10-16: 5-sekunders polling fjernet - Ture-arbejdsfladen henter selv
  // (hvert 10. sek. og kun mens fanen er synlig).


  // Admin auto-optimize when plads changes or tours change
  const adminToursRef = useRef(adminTours);
  useEffect(() => { adminToursRef.current = adminTours; }, [adminTours]);

  const adminOptimizeRef = useRef(null);
  useEffect(() => {
    if (!adminSelectedPlads) { setAdminRouteOptimization(null); return; }
    if (adminOptimizeRef.current) clearTimeout(adminOptimizeRef.current);
    setAdminRouteOptimization(null);
    adminOptimizeRef.current = setTimeout(() => {
      const currentTours = adminToursRef.current;
      const tourIds = currentTours.filter(t => t.plads === adminSelectedPlads && !t.is_pause).map(t => t.id);
      if (tourIds.length === 0) { setAdminRouteOptimization(null); return; }
      axios.post(`${API}/optimize-route`, { plads_name: adminSelectedPlads, tour_ids: tourIds })
        .then(res => setAdminRouteOptimization(res.data))
        .catch(() => setAdminRouteOptimization(null));
    }, 800);
    return () => { if (adminOptimizeRef.current) clearTimeout(adminOptimizeRef.current); };
  }, [adminSelectedPlads, adminReportDate]);

  const getAdminRouteInfo = useCallback((tourId) => {
    if (!adminRouteOptimization?.optimized || !adminRouteOptimization?.tours) return null;
    return adminRouteOptimization.tours.find(t => t.tour_id === tourId) || null;
  }, [adminRouteOptimization]);

  // Admin mail parse handler
  const handleAdminParseMail = async () => {
    if (!mailText.trim()) { toast.error("Indsæt mail tekst først"); return; }
    if (!adminSelectedPlads) { toast.error(`Vælg en ${siteWord} først`); return; }
    
    setParsing(true);
    try {
      const res = await axios.post(`${API}/parse-mail`, { text: mailText, report_id: adminReportId });
      
      if (res.data.success && res.data.tours.length > 0) {
        const sortedTours = [...res.data.tours].sort((a, b) => {
          if (a.facility === b.facility) return a.address.localeCompare(b.address);
          return a.facility.localeCompare(b.facility);
        });
        
        const toursToCreate = sortedTours.map(t => ({
          ...t,
          date: adminReportDate,
          plads: adminSelectedPlads,
          driver_id: "",
          driver_name: "",
          report_id: adminReportId
        }));
        
        await axios.post(`${API}/tours/bulk`, toursToCreate);
        setMailText("");
        fetchAdminTours();

        // Fase 15.23 (2026-02-21): HASTER-web-push til chauffører fjernet.
        // Hasteture vises kun visuelt på chaufførens tour-kort.
        
        const grouped = res.data.grouped_by_facility;
        const facilityCount = Object.keys(grouped).length;
        toast.success(`${res.data.count} ture tilføjet til ${adminSelectedPlads}! (${facilityCount} anlæg)`);
      } else {
        toast.error("Kunne ikke parse mail");
      }
    } catch (e) {
      toast.error("Fejl ved parsing af mail");
    } finally {
      setParsing(false);
    }
  };

  // Admin PDF upload handler
  const handleAdminPdfUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error("Kun PDF-filer er tilladt");
      e.target.value = "";
      return;
    }
    if (!adminSelectedPlads) {
      toast.error(`Vælg en ${siteWord} først`);
      e.target.value = "";
      return;
    }
    
    setParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      const res = await axios.post(`${API}/parse-pdf`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      
      if (res.data.success && res.data.tours.length > 0) {
        const toursToCreate = res.data.tours.map(t => ({
          ...t,
          date: adminReportDate,
          plads: adminSelectedPlads,
          driver_id: "",
          driver_name: "",
          report_id: adminReportId
        }));
        
        await axios.post(`${API}/tours/bulk`, toursToCreate);
        fetchAdminTours();
        
        const grouped = res.data.grouped_by_facility;
        const materialCount = Object.keys(grouped).length;
        const totalJobs = res.data.count;
        toast.success(`PDF: ${totalJobs} ture oprettet fra ${materialCount} materialer i ${adminSelectedPlads}!`);
      } else {
        toast.error("Kunne ikke finde materialer i PDF");
        if (res.data.debug_info) {
          console.log("PDF parse debug:", res.data.debug_info);
        }
      }
    } catch (err) {
      if (err.response) {
        toast.error(`PDF fejl: ${err.response.status}`);
      } else {
        toast.error("Netværksfejl ved upload");
      }
    } finally {
      setParsing(false);
      e.target.value = "";
    }
  };

  // ============= ARGO IMPORT FUNCTIONS =============
  const handleArgoParse = async () => {
    if (!argoText.trim()) { toast.error("Indsæt Argo tekst først"); return; }
    setArgoLoading(true);
    try {
      const res = await axios.post(`${API}/parse-argo`, { text: argoText, date: adminReportDate });
      if (res.data.tours && res.data.tours.length > 0) {
        setArgoParsed(res.data.tours);
        toast.success(`${res.data.count} ture fundet`);
      } else {
        toast.error("Ingen ture fundet i teksten");
      }
    } catch (e) {
      toast.error("Fejl ved parsing af Argo data");
    }
    setArgoLoading(false);
  };

  const handleArgoImport = async () => {
    if (argoParsed.length === 0) return;
    if (!adminSelectedPlads) {
      toast.error(`Vælg en ${siteWord} først`);
      return;
    }
    setArgoLoading(true);
    try {
      const res = await axios.post(`${API}/import-argo`, { 
        tours: argoParsed, 
        date: adminReportDate,
        plads: adminSelectedPlads 
      });
      toast.success(res.data.message);
      setShowArgoModal(false);
      setArgoText("");
      setArgoParsed([]);
      fetchAdminTours();
    } catch (e) {
      toast.error("Fejl ved import");
    }
    setArgoLoading(false);
  };

  // Fase 4.1 (2026-06-16): Download tour-template (.xlsx with Lokation dropdown)
  const handleDownloadTourTemplate = async () => {
    try {
      const res = await axios.get(`${API}/tours/template`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      link.setAttribute("download", `ture-skabelon-${today}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Skabelon hentet");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Fejl ved download af skabelon");
    }
  };

  // Fase 4.1: Upload udfyldt tour-template
  const handleUploadTourTemplate = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setTemplateUploading(true);
    setTemplateUploadResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await axios.post(`${API}/tours/upload-template`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setTemplateUploadResult(res.data);
      if (res.data.created > 0) {
        toast.success(`${res.data.created} tur(e) oprettet`);
      }
      if (res.data.errors?.length) {
        toast.warning(`${res.data.errors.length} række(r) blev sprunget over - se detaljer nedenfor`);
      }
      fetchAdminTours();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Fejl ved upload");
      setTemplateUploadResult({ created: 0, errors: [{ row: "?", reason: e?.response?.data?.detail || "Upload fejlede" }] });
    }
    setTemplateUploading(false);
    // Reset file input
    event.target.value = "";
  };



  // Firma tur (private company tour) - create multiple tours from form
  const handleFirmaSubmit = async () => {
    if (!adminSelectedPlads) { toast.error(`Vælg en ${siteWord} først`); return; }
    if (!firmaForm.firma.trim()) { toast.error("Firma navn er påkrævet"); return; }
    const pickups = firmaForm.pickups.map(p => p.trim()).filter(Boolean);
    const deliveries = firmaForm.deliveries.filter(d => (d.company || "").trim() || (d.address || "").trim());
    if (pickups.length === 0) { toast.error("Mindst én afhentningsadresse"); return; }
    if (deliveries.length === 0) { toast.error("Mindst én afleveringsadresse"); return; }

    const facilityStr = deliveries
      .map(d => [d.company?.trim(), d.address?.trim()].filter(Boolean).join(" - "))
      .filter(Boolean)
      .join(" | ");

    const noteExtra = firmaForm.note?.trim() || "";
    const combinedRemark = noteExtra;

    const toursToCreate = pickups.map((pickup, idx) => ({
      date: adminReportDate,
      container: "",
      fraction: firmaForm.firma.trim(),
      facility: facilityStr,
      address: pickup,
      is_private: true,
      private_company: firmaForm.firma.trim(),
      remark: combinedRemark,
      plads: adminSelectedPlads,
      report_id: adminReportId || "",
      priority: "normal",
      sort_order: idx
    }));

    setFirmaLoading(true);
    try {
      await axios.post(`${API}/tours/bulk`, toursToCreate);
      toast.success(`${toursToCreate.length} firma tur${toursToCreate.length > 1 ? "e" : ""} tilføjet på ${adminSelectedPlads}`);
      setShowFirmaModal(false);
      setFirmaForm({ firma: "", pickups: [""], deliveries: [{ company: "", address: "" }], note: "" });
      fetchAdminTours();
    } catch (e) {
      toast.error("Fejl ved oprettelse af firma tur");
    }
    setFirmaLoading(false);
  };




  // Admin delete tour
  const handleAdminDeleteTour = async (tourId) => {
    try {
      await axios.delete(`${API}/tours/${tourId}`);
      setAdminTours(adminTours.filter(t => t.id !== tourId));
      toast.success("Tur slettet");
    } catch (e) {
      toast.error("Fejl ved sletning");
    }
  };

  // Fase 6 (2026-06-16): LA pre-assigns / reassigns / releases a tour to a driver.
  // Empty driverId = release (back to open pool). Backend logs audit entry.
  const handleAssignTour = async (tourId, driverId) => {
    try {
      const driver = drivers.find(d => d.id === driverId);
      await axios.put(`${API}/tours/${tourId}`, {
        driver_id: driverId || "",
        driver_name: driver ? driver.name : "",
      });
      // Update local state optimistically
      setAdminTours(prev => prev.map(t => t.id === tourId ? { ...t, driver_id: driverId || "", driver_name: driver ? driver.name : "" } : t));
      if (driverId) {
        toast.success(`Tildelt ${driver?.name || "chauffør"} - kun synlig for denne chauffør`);
      } else {
        toast.success("Tur frigivet - åben for alle chauffører");
      }
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  // Admin clear all tours for selected plads
  const handleAdminClearPlads = () => {
    if (!adminSelectedPlads) return;
    showConfirm(
      "Slet alle ture",
      `Er du sikker på at du vil slette alle ture i ${adminSelectedPlads}?`,
      async () => {
        hideConfirm();
        try {
          const toursToDelete = adminTours.filter(t => t.plads === adminSelectedPlads);
          await Promise.all(toursToDelete.map(t => axios.delete(`${API}/tours/${t.id}`)));
          fetchAdminTours();
          toast.success(`Alle ture i ${adminSelectedPlads} slettet`);
        } catch (e) { toast.error("Fejl ved sletning"); }
      }
    );
  };

  const handleAddPlads = async () => {
    if (!newPladsName.trim()) {
      toast.error("Indtast plads navn");
      return;
    }
    if (!newPladsAddress.trim()) {
      toast.error("Indtast adresse");
      return;
    }
    try {
      await axios.post(`${API}/plads`, {
        name: newPladsName.trim(),
        city: newPladsCity.trim(),
        address: newPladsAddress.trim(),
        lat: newPladsLat ? parseFloat(newPladsLat) : null,
        lng: newPladsLng ? parseFloat(newPladsLng) : null,
      });
      setNewPladsName(""); setNewPladsCity(""); setNewPladsAddress(""); setNewPladsLat(""); setNewPladsLng("");
      fetchData();
      toast.success("Plads tilføjet");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Fejl ved tilføjelse");
    }
  };

  const handleUpdatePlads = async () => {
    if (!editingPlads) return;
    try {
      await axios.put(`${API}/plads/${editingPlads.id}`, {
        name: editingPlads.name || undefined,
        city: editingPlads.city || undefined,
        address: editingPlads.address || undefined,
        lat: editingPlads.lat != null && editingPlads.lat !== "" ? parseFloat(editingPlads.lat) : undefined,
        lng: editingPlads.lng != null && editingPlads.lng !== "" ? parseFloat(editingPlads.lng) : undefined,
      });
      setEditingPlads(null);
      fetchData();
      toast.success("Plads opdateret");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Fejl ved opdatering");
    }
  };

  const handleDeletePlads = (pladsId) => {
    showConfirm(
      "Slet plads",
      "Er du sikker på at du vil slette denne plads?",
      async () => {
        hideConfirm();
        try {
          await axios.delete(`${API}/plads/${pladsId}`);
          fetchData();
          toast.success("Plads slettet");
        } catch (e) { toast.error("Fejl ved sletning"); }
      }
    );
  };

  // Handle driver schedule change
  const handleScheduleChange = (driverId, plads) => {
    setDriverSchedule(prev => ({
      ...prev,
      [driverId]: plads
    }));
  };

  // Send email to single driver
  const sendEmailToDriver = (driver, plads) => {
    if (!driver.email) {
      toast.error(`${driver.name} har ingen email adresse`);
      return;
    }
    
    const today = new Date().toLocaleDateString("da-DK", { weekday: 'long', day: 'numeric', month: 'long' });
    const subject = encodeURIComponent(`Arbejdsplan - ${today}`);
    
    let body;
    if (plads === "FRI") {
      body = encodeURIComponent(`Hej ${driver.name},\n\nDu har fri i dag (${today}).\n\nMed venlig hilsen\nContainerFlow`);
    } else {
      body = encodeURIComponent(`Hej ${driver.name},\n\nDu skal arbejde i ${plads} i dag (${today}).\n\nVogn: ${driver.plate}\n\nMed venlig hilsen\nContainerFlow`);
    }
    
    window.open(`mailto:${driver.email}?subject=${subject}&body=${body}`, '_blank');
    toast.success(`Mail åbnet for ${driver.name}`);
  };

  // Send email to all drivers with assignments
  const sendEmailToAllDrivers = () => {
    const driversWithEmail = drivers.filter(d => d.email);
    if (driversWithEmail.length === 0) {
      toast.error("Ingen chauffører har email adresse");
      return;
    }
    
    const selectedDate = new Date(adminReportDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: 'long', day: 'numeric', month: 'long' });
    const subject = encodeURIComponent(`Arbejdsplan - ${selectedDate}`);
    
    // Build schedule list
    let scheduleList = drivers.map(d => {
      const plads = driverSchedule[d.id] || "Ikke tildelt";
      return `${d.name}: ${plads === "FRI" ? "FRI" : plads}`;
    }).join("\n");
    
    const body = encodeURIComponent(`Arbejdsplan for ${selectedDate}:\n\n${scheduleList}\n\nMed venlig hilsen\nContainerFlow`);
    
    // Join all emails
    const emails = driversWithEmail.map(d => d.email).join(",");
    
    window.open(`mailto:${emails}?subject=${subject}&body=${body}`, '_blank');
    toast.success("Mail åbnet for alle chauffører");
  };

  // Navigate weeks
  const navigateWeek = (direction) => {
    const current = new Date(weekStart + "T12:00:00");
    current.setDate(current.getDate() + (direction * 7));
    setWeekStart(`${current.getFullYear()}-${String(current.getMonth()+1).padStart(2,"0")}-${String(current.getDate()).padStart(2,"0")}`);
  };

  // Handle weekly schedule change
  const handleWeeklyScheduleChange = (driverId, date, plads) => {
    setWeeklySchedule(prev => ({
      ...prev,
      [`${driverId}-${date}`]: plads
    }));
  };

  // Save weekly schedule
  const saveWeeklySchedule = async () => {
    const schedules = [];
    const weekDates = getWeekDates();
    
    drivers.forEach(driver => {
      weekDates.forEach(date => {
        const key = `${driver.id}-${date}`;
        const plads = weeklySchedule[key];
        if (plads) {
          schedules.push({
            driver_id: driver.id,
            driver_name: driver.name,
            date: date,
            plads: plads
          });
        }
      });
    });
    
    if (schedules.length === 0) {
      toast.error("Ingen ændringer at gemme");
      return;
    }
    
    try {
      await axios.post(`${API}/schedule/bulk`, { schedules });
      toast.success(`${schedules.length} planlægninger gemt!`);
      fetchWeeklySchedule();
    } catch (e) {
      toast.error("Fejl ved gemning");
    }
  };

  // Send weekly email
  const sendWeeklyEmailToAllDrivers = () => {
    const driversWithEmail = drivers.filter(d => d.email);
    if (driversWithEmail.length === 0) {
      toast.error("Ingen chauffører har email adresse");
      return;
    }
    
    const weekDates = getWeekDates();
    const dayNames = ["man", "tir", "ons", "tor", "fre", "lør", "søn"];
    
    const startDate = new Date(weekStart);
    const endDate = new Date(weekStart);
    endDate.setDate(endDate.getDate() + 6);
    
    const subject = encodeURIComponent(`Ugeplan - Uge ${getWeekNumber(startDate)}`);
    
    // Build schedule for each driver
    let scheduleList = drivers.map(driver => {
      const driverSchedule = weekDates.map((date, idx) => {
        const plads = weeklySchedule[`${driver.id}-${date}`] || "-";
        return `${dayNames[idx]}: ${plads}`;
      }).join(", ");
      return `${driver.name}: ${driverSchedule}`;
    }).join("\n");
    
    const body = encodeURIComponent(`Ugeplan (${startDate.toLocaleDateString("da-DK")} - ${endDate.toLocaleDateString("da-DK")}):\n\n${scheduleList}\n\nMed venlig hilsen\nContainerFlow`);
    
    const emails = driversWithEmail.map(d => d.email).join(",");
    window.open(`mailto:${emails}?subject=${subject}&body=${body}`, '_blank');
    toast.success("Ugeplan mail åbnet");
  };

  // Get week number
  const getWeekNumber = (date) => {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900" data-testid="admin-page">
      {/* Admin Header - sticky, dark, tabs inline (matches CustomerAdminPage style) */}
      <header className="bg-[#0F172A] text-white sticky top-0 z-20 shadow-md" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="max-w-screen-2xl mx-auto px-3 sm:px-8 py-2.5 sm:py-3 flex items-center justify-between gap-2 sm:gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-red-600 flex items-center justify-center shadow-lg">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div className="min-w-0">
              <h1 className="font-heading font-bold text-lg leading-tight">Container<span className="text-orange-500">Flow</span> <span className="text-slate-400 text-sm font-normal">Admin</span></h1>
              <p className="text-[11px] text-red-400 uppercase tracking-wider leading-tight truncate">
                {activeCompany ? activeCompany.name : "Logistik-administration"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {managedCompanies.length > 1 && (
              <div className="flex items-center gap-2 bg-slate-800 rounded-lg px-3 py-2 border border-slate-700" data-testid="admin-company-switcher-wrap">
                <Building2 className="w-4 h-4 text-orange-400 flex-shrink-0" />
                <select
                  value={effectiveCompanyId}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!v || v === authUser?.company_id) {
                      setActingCompanyId("");
                    } else {
                      setActingCompanyId(v);
                    }
                  }}
                  className="bg-transparent text-white text-sm font-medium outline-none cursor-pointer pr-2 min-w-0"
                  data-testid="admin-company-switcher"
                  title="Skift mellem virksomheder du administrerer"
                >
                  {managedCompanies.map(c => (
                    <option key={c.id} value={c.id} className="text-slate-900">
                      {c.name}{c.is_own ? " (egen)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <button onClick={onLogout} className="flex items-center gap-1.5 text-xs text-red-300 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors" data-testid="admin-logout-btn">
              <LogOut className="w-4 h-4" /> Log ud
            </button>
          </div>
        </div>

        {/* 2026-10-16: Daglige faner fremme, resten i "Mere" (samme mønster som
            Location Admin). Ture er flyttet ud af Arkiv og er nu startfanen. */}
        <AdminTabNav
          active={activeTab}
          onChange={setActiveTab}
          title={activeCompany ? activeCompany.name : "Logistik-administration"}
          tabs={[
            { id: "tours",      label: "Ture",          icon: Truck,      testid: "admin-tab-tours" },
            can.planning     && { id: "schedule",   label: "Tid & ressourcer", icon: Calendar },
            can.drivers      && { id: "drivers",    label: "Chauffører",    icon: Users },
            can.reports      && { id: "statistics", label: "Rapportering",  icon: BarChart3,  testid: "admin-statistics-tab" },
            can.economy_view && { id: "priser",     label: "Økonomi",       icon: DollarSign },
            can.archive      && { id: "archives",   label: "Arkiv",         icon: Archive,    testid: "admin-archives-tab" },
          ].filter(Boolean)}
          moreTabs={[
            can.locations && (isPremiumLogistics
              ? { id: "plads",  label: "Lokationer",    icon: MapPin }
              : { id: "plads",  label: "Genbrugspladser", icon: Building2 }),
            can.team     && { id: "team",       label: "Team & rettigheder", icon: Shield, testid: "admin-tab-team" },
            can.settings && { id: "settings",   label: "Indstillinger", icon: Settings,   testid: "admin-settings-tab" },
          ].filter(Boolean)}
        />
      </header>

      <main className="max-w-screen-2xl mx-auto px-3 py-4 sm:p-8 space-y-6">
        {/* OVERVIEW TAB - Daily Statistics */}
        {activeTab === "overview" && dailyOverview && (
          <section className="space-y-6">
            {/* Today's Summary Card */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h2 className="font-heading font-bold text-xl mb-4 flex items-center gap-2">
                <BarChart3 className="w-6 h-6 text-red-600" /> 
                Dagens Oversigt - {new Date().toLocaleDateString("da-DK", { weekday: 'long', day: 'numeric', month: 'long' })}
              </h2>
              
              {/* Main Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
                <div className="bg-slate-100 dark:bg-slate-700 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-slate-800 dark:text-white">{dailyOverview.totals.total_tours}</div>
                  <div className="text-sm text-muted-foreground">Total ture</div>
                </div>
                <div className="bg-emerald-100 dark:bg-emerald-900/30 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-emerald-600">{dailyOverview.totals.completed}</div>
                  <div className="text-sm text-emerald-700">Færdig</div>
                </div>
                <div className="bg-amber-100 dark:bg-amber-900/30 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-amber-600">{dailyOverview.totals.on_way}</div>
                  <div className="text-sm text-amber-700">På vej</div>
                </div>
                <div className="bg-blue-100 dark:bg-blue-900/30 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-blue-600">{dailyOverview.totals.waiting}</div>
                  <div className="text-sm text-blue-700">Venter</div>
                </div>
                <div className="bg-purple-100 dark:bg-purple-900/30 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-purple-600">{dailyOverview.totals.total_weight.toLocaleString()}</div>
                  <div className="text-sm text-purple-700">Total kg</div>
                </div>
                <div className="bg-red-100 dark:bg-red-900/30 rounded-xl p-4 text-center">
                  <div className="text-3xl font-black text-red-600">{dailyOverview.totals.progress_percent}%</div>
                  <div className="text-sm text-red-700">Fremskridt</div>
                </div>
              </div>
              
              {/* Progress Bar */}
              <div className="mb-6">
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium">Dagens fremskridt</span>
                  <span className="font-bold">{dailyOverview.totals.completed} / {dailyOverview.totals.total_tours} ture</span>
                </div>
                <div className="h-4 bg-slate-200 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
                    style={{ width: `${dailyOverview.totals.progress_percent}%` }}
                  />
                </div>
              </div>
              
              {/* Per Plads Stats */}
              <h3 className="font-bold text-lg mb-3">Status pr. genbrugsplads</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(dailyOverview.plads_stats).map(([pladsName, stats]) => (
                  <div key={pladsName} className="bg-slate-50 dark:bg-slate-900 rounded-xl p-4 border border-slate-200">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-lg">{pladsName}</span>
                      <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                        stats.progress_percent === 100 
                          ? "bg-emerald-500 text-white" 
                          : stats.progress_percent > 50 
                            ? "bg-amber-500 text-black"
                            : "bg-slate-300 text-slate-700"
                      }`}>
                        {stats.progress_percent}%
                      </span>
                    </div>
                    <div className="flex gap-3 text-sm mb-2">
                      <span className="text-emerald-600 font-medium">{stats.completed} færdig</span>
                      <span className="text-amber-600 font-medium">{stats.on_way} på vej</span>
                      <span className="text-slate-500">{stats.waiting} venter</span>
                    </div>
                    <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-emerald-500 transition-all"
                        style={{ width: `${stats.progress_percent}%` }}
                      />
                    </div>
                    {stats.total_weight > 0 && (
                      <div className="mt-2 text-sm text-slate-600">
                        Total: <span className="font-bold">{stats.total_weight.toLocaleString()} kg</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            
            {/* Active Drivers */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-600" /> 
                Aktive chauffører ({dailyOverview.active_drivers})
              </h3>

              {/* Per-driver job count today */}
              {dailyOverview.active_sessions?.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
                  {dailyOverview.active_sessions.map(session => {
                    const driverTours = adminTours.filter(t => 
                      (t.claimed_by === session.driver_name || t.driver_name === session.driver_name) && !t.is_pause
                    );
                    const completed = driverTours.filter(t => t.completed).length;
                    return (
                      <div key={session.id} className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900 rounded-lg p-3" data-testid={`driver-stat-${session.driver_name}`}>
                        <div className="w-10 h-10 bg-blue-500 text-white rounded-full flex items-center justify-center font-bold">
                          {session.driver_name?.charAt(0) || "?"}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">{session.driver_name}</div>
                          <div className="text-xs text-slate-500 flex items-center gap-2">
                            <span>{session.vehicle_reg || "-"}</span>
                            <span>•</span>
                            <span>{session.current_plads || "Ingen plads"}</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-lg font-black text-emerald-600">{completed}/{driverTours.length}</div>
                          <div className="text-[10px] text-slate-400">ture i dag</div>
                        </div>
                        <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" title="Online" />
                      </div>
                    );
                  })}
                </div>
              )}
              {(!dailyOverview.active_sessions || dailyOverview.active_sessions.length === 0) && (
                <p className="text-slate-500 text-center py-4">Ingen aktive chauffører</p>
              )}
            </div>
            
            {/* Messages from Drivers */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                <MessageCircle className="w-5 h-5 text-amber-600" /> 
                Beskeder fra chauffører
                {adminMessages.filter(m => !m.read).length > 0 && (
                  <span className="px-2 py-0.5 bg-red-500 text-white text-xs rounded-full">
                    {adminMessages.filter(m => !m.read).length} ulæste
                  </span>
                )}
              </h3>
              {adminMessages.length > 0 ? (
                <div className="space-y-3">
                  {adminMessages.slice(0, 10).map(msg => (
                    <div key={msg.id} className={`p-4 rounded-lg border-l-4 ${msg.read ? "bg-slate-50 border-slate-300" : "bg-amber-50 border-amber-500"}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold">{msg.from_driver_name}</span>
                            <span className="text-xs text-slate-500">
                              {new Date(msg.created_at).toLocaleString("da-DK")}
                            </span>
                          </div>
                          <p className="text-slate-700">{msg.content}</p>
                        </div>
                        <button 
                          onClick={() => setReplyToDriver(msg)}
                          className="px-3 py-1 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 flex items-center gap-1"
                        >
                          <Send className="w-3 h-3" /> Svar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-center py-4">Ingen beskeder fra chauffører</p>
              )}
              
              {/* Reply Modal */}
              {replyToDriver && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-md w-full p-6">
                    <h4 className="font-bold text-lg mb-4">Svar til {replyToDriver.from_driver_name}</h4>
                    <p className="text-sm text-slate-500 mb-4 p-3 bg-slate-100 rounded-lg">"{replyToDriver.content}"</p>
                    <textarea
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      placeholder="Skriv dit svar..."
                      className="w-full px-4 py-3 border rounded-lg mb-4 h-32 resize-none"
                    />
                    <div className="flex gap-3">
                      <button
                        onClick={() => setReplyToDriver(null)}
                        className="flex-1 px-4 py-2 border rounded-lg hover:bg-slate-100"
                      >
                        Annuller
                      </button>
                      <button
                        onClick={handleReplyToDriver}
                        disabled={!replyText.trim()}
                        className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
                      >
                        Send svar
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}
        
        {/* STATISTICS TAB - Graphs & Analytics */}
        {activeTab === "statistics" && (
          <section className="space-y-6" data-testid="admin-statistics-section">
            {/* Period Selector */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <h2 className="font-heading font-bold text-xl flex items-center gap-2">
                    <BarChart3 className="w-6 h-6 text-orange-500" /> Rapportering
                  </h2>
                  {statisticsData?.generated_at && (
                    <p className="text-xs text-slate-400 mt-1 inline-flex items-center gap-1.5" data-testid="stats-updated-at">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Live · opdateret {new Date(statisticsData.generated_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · opdateres hvert 30. sek.
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm text-slate-500">Periode:</label>
                  <select
                    value={statsPeriod}
                    onChange={(e) => setStatsPeriod(Number(e.target.value))}
                    className="px-3 py-2 border rounded-lg text-sm bg-white dark:bg-slate-700"
                    data-testid="stats-period-select"
                  >
                    <option value={1}>Sidste måned</option>
                    <option value={3}>Sidste 3 måneder</option>
                    <option value={6}>Sidste 6 måneder</option>
                    <option value={12}>Sidste år</option>
                  </select>
                  <button onClick={() => fetchStatistics()} className="px-3 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600" data-testid="stats-refresh-btn" title="Opdatér nu">
                    <RotateCcw className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {statsLoading && !statisticsData && (
              <div className="text-center py-12">
                <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-slate-500">Indlæser statistik...</p>
              </div>
            )}

            {statisticsData && (
              <>
                {/* I dag - live */}
                {statisticsData.today && (
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5" data-testid="stats-today">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-lg">I dag</h3>
                      <button onClick={() => setActiveTab("tours")} className="text-sm font-semibold text-emerald-700 hover:underline">Åbn Ture →</button>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
                      {[
                        ["Ture", statisticsData.today.total, "text-slate-800 dark:text-white"],
                        ["Færdige", statisticsData.today.completed, "text-emerald-600"],
                        ["På vej", statisticsData.today.on_way, "text-amber-600"],
                        ["Uden chauffør", statisticsData.today.unassigned, "text-slate-500"],
                        ["Haster åbne", statisticsData.today.haster_open, "text-rose-600"],
                        ["Kg i dag", (statisticsData.today.weight || 0).toLocaleString("da-DK"), "text-blue-600"],
                        ["Ikke kørt (14 d.)", statisticsData.today.overdue, "text-amber-700"],
                      ].map(([l, v, c]) => (
                        <div key={l} className="rounded-lg bg-slate-50 dark:bg-slate-900 px-3 py-2.5">
                          <div className={`text-2xl font-black tabular-nums ${c}`}>{v}</div>
                          <div className="text-xs text-slate-500">{l}</div>
                        </div>
                      ))}
                    </div>
                    {statisticsData.today.total > 0 && (
                      <div className="mt-3 h-2 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden flex">
                        <div className="bg-emerald-500" style={{ width: `${(statisticsData.today.completed / statisticsData.today.total) * 100}%` }} />
                        <div className="bg-amber-400" style={{ width: `${(statisticsData.today.on_way / statisticsData.today.total) * 100}%` }} />
                      </div>
                    )}
                  </div>
                )}

                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 text-center" data-testid="stats-total-tours">
                    <div className="text-3xl font-black text-slate-800 dark:text-white">{statisticsData.summary.total_tours}</div>
                    <div className="text-sm text-slate-500">Total ture</div>
                  </div>
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 text-center" data-testid="stats-completed-tours">
                    <div className="text-3xl font-black text-emerald-600">{statisticsData.summary.completed_tours}</div>
                    <div className="text-sm text-emerald-600">Fuldførte</div>
                  </div>
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 text-center" data-testid="stats-total-weight">
                    <div className="text-3xl font-black text-blue-600">{statisticsData.summary.total_weight.toLocaleString()}</div>
                    <div className="text-sm text-blue-600">Total kg</div>
                  </div>
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 text-center" data-testid="stats-total-drivers">
                    <div className="text-3xl font-black text-purple-600">{statisticsData.summary.total_drivers}</div>
                    <div className="text-sm text-purple-600">Chauffører</div>
                  </div>
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 text-center" data-testid="stats-active-drivers">
                    <div className="text-3xl font-black text-orange-500">{statisticsData.summary.active_drivers}</div>
                    <div className="text-sm text-orange-500">Aktive chauffører</div>
                  </div>
                </div>

                {/* Jobs Per Day Chart */}
                <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-jobs-per-day">
                  <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-blue-600" /> Ture pr. dag (sidste 30 dage)
                  </h3>
                  <div style={{ width: '100%', height: 300 }}>
                    <ResponsiveContainer>
                      <BarChart data={statisticsData.jobs_per_day} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} />
                        <YAxis fontSize={11} />
                        <Tooltip 
                          labelFormatter={(d) => new Date(d).toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" })}
                          formatter={(v, name) => [v, name === "completed" ? "Fuldført" : name === "total" ? "Total" : "Kg"]}
                        />
                        <Bar dataKey="total" fill="#94a3b8" name="Total" radius={[2, 2, 0, 0]} />
                        <Bar dataKey="completed" fill="#22c55e" name="Fuldført" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Material Usage Chart */}
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-material-usage">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <FileText className="w-5 h-5 text-orange-500" /> Materiale fordeling
                    </h3>
                    {statisticsData.material_usage.length > 0 ? (
                      <div style={{ width: '100%', height: 350 }}>
                        <ResponsiveContainer>
                          <PieChart>
                            <Pie
                              data={statisticsData.material_usage.slice(0, 10)}
                              dataKey="count"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              outerRadius={100}
                              label={({ name, percent }) => `${name.substring(0, 15)}${name.length > 15 ? '...' : ''} (${(percent * 100).toFixed(0)}%)`}
                              labelLine={true}
                              fontSize={10}
                            >
                              {statisticsData.material_usage.slice(0, 10).map((_, i) => (
                                <Cell key={i} fill={["#f97316","#3b82f6","#22c55e","#a855f7","#ef4444","#eab308","#06b6d4","#ec4899","#64748b","#14b8a6"][i % 10]} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v, name) => [v, "Antal"]} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-slate-400 text-center py-8">Ingen materialedata</p>
                    )}
                  </div>

                  {/* Plads Stats */}
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-plads">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <Building2 className="w-5 h-5 text-purple-600" /> Genbrugsplads oversigt
                    </h3>
                    {statisticsData.plads_stats.length > 0 ? (
                      <div className="space-y-3">
                        {statisticsData.plads_stats.map((p) => (
                          <div key={p.name} className="flex items-center gap-3">
                            <div className="w-24 text-sm font-medium truncate">{p.name}</div>
                            <div className="flex-1 h-6 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-orange-400 to-orange-600 rounded-full flex items-center justify-end pr-2"
                                style={{ width: `${Math.max(5, (p.completed / Math.max(p.total, 1)) * 100)}%` }}
                              >
                                <span className="text-[10px] font-bold text-white">{p.completed}/{p.total}</span>
                              </div>
                            </div>
                            <div className="text-xs text-slate-500 w-16 text-right">{p.weight.toLocaleString()} kg</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-400 text-center py-8">Ingen pladsdata</p>
                    )}
                  </div>
                </div>

                {/* Driver Performance Table */}
                <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-driver-performance">
                  <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                    <Users className="w-5 h-5 text-blue-600" /> Chauffør præstation
                  </h3>
                  {statisticsData.driver_performance.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                            <th className="p-3 text-left">Chauffør</th>
                            <th className="p-3 text-left">Nummerplade</th>
                            <th className="p-3 text-center">Arbejdsdage</th>
                            <th className="p-3 text-center">Vagt timer</th>
                            <th className="p-3 text-center">Total ture</th>
                            <th className="p-3 text-center">Fuldført</th>
                            <th className="p-3 text-center">Total kg</th>
                            <th className="p-3 text-center">Ture/dag gns.</th>
                            <th className="p-3 text-center">Gns. tur</th>
                            <th className="p-3 text-center">Total tur-tid</th>
                            <th className="p-3 text-center">Korte/Mell./Lange</th>
                          </tr>
                        </thead>
                        <tbody>
                          {statisticsData.driver_performance.map((dp) => {
                            const fmtMin = (m) => {
                              if (!m || m <= 0) return "-";
                              const h = Math.floor(m / 60);
                              const mm = m % 60;
                              return h > 0 ? `${h}t ${mm}m` : `${mm}m`;
                            };
                            return (
                            <tr key={dp.name} className="border-b hover:bg-slate-50 dark:hover:bg-slate-900">
                              <td className="p-3 font-medium">{dp.name}</td>
                              <td className="p-3 font-mono text-xs">{dp.plate}</td>
                              <td className="p-3 text-center">
                                <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold">{dp.work_days}</span>
                              </td>
                              <td className="p-3 text-center">
                                <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded-full text-xs font-bold">{dp.total_hours}t</span>
                              </td>
                              <td className="p-3 text-center font-bold">{dp.total_tours}</td>
                              <td className="p-3 text-center">
                                <span className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs font-bold">{dp.completed_tours}</span>
                              </td>
                              <td className="p-3 text-center">{dp.total_weight.toLocaleString()} kg</td>
                              <td className="p-3 text-center">
                                <span className="px-2 py-1 bg-orange-100 text-orange-700 rounded-full text-xs font-bold">{dp.avg_tours_per_day}</span>
                              </td>
                              <td className="p-3 text-center">
                                <span className="px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full text-xs font-bold">{fmtMin(dp.avg_tour_minutes)}</span>
                              </td>
                              <td className="p-3 text-center font-mono">{fmtMin(dp.total_tour_minutes)}</td>
                              <td className="p-3 text-center">
                                <span className="inline-flex gap-1">
                                  <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded text-xs font-bold" title="<30 min">{dp.short_tours || 0}</span>
                                  <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-bold" title="30-60 min">{dp.medium_tours || 0}</span>
                                  <span className="px-1.5 py-0.5 bg-rose-100 text-rose-700 rounded text-xs font-bold" title=">60 min">{dp.long_tours || 0}</span>
                                </span>
                              </td>
                            </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-slate-400 text-center py-8">Ingen chauffør data</p>
                  )}
                </div>

                {/* Tour Duration Distribution Chart per Driver */}
                {statisticsData.driver_performance.length > 0 && (
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-tour-duration-chart">
                    <h3 className="font-bold text-lg mb-1 flex items-center gap-2">
                      <Clock className="w-5 h-5 text-indigo-600" /> Tur længde fordeling pr. chauffør
                    </h3>
                    <p className="text-xs text-slate-500 mb-4">
                      <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" /> Korte (&lt;30m)
                      <span className="inline-block w-2 h-2 rounded-full bg-blue-500 ml-3 mr-1" /> Mellem (30-60m)
                      <span className="inline-block w-2 h-2 rounded-full bg-rose-500 ml-3 mr-1" /> Lange (&gt;60m)
                    </p>
                    <div style={{ width: '100%', height: 320 }}>
                      <ResponsiveContainer>
                        <BarChart data={statisticsData.driver_performance} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="name" fontSize={11} angle={-15} textAnchor="end" height={60} />
                          <YAxis fontSize={11} />
                          <Tooltip formatter={(v, name) => [v, name === "short_tours" ? "Korte (<30m)" : name === "medium_tours" ? "Mellem (30-60m)" : "Lange (>60m)"]} />
                          <Bar dataKey="short_tours" stackId="a" fill="#22c55e" name="Korte" />
                          <Bar dataKey="medium_tours" stackId="a" fill="#3b82f6" name="Mellem" />
                          <Bar dataKey="long_tours" stackId="a" fill="#f43f5e" name="Lange" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Avg Tour Duration Bar Chart */}
                {statisticsData.driver_performance.length > 0 && (
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-avg-duration-chart">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <Clock className="w-5 h-5 text-purple-600" /> Gennemsnitlig tid pr. tur (minutter)
                    </h3>
                    <div style={{ width: '100%', height: 280 }}>
                      <ResponsiveContainer>
                        <BarChart data={statisticsData.driver_performance} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="name" fontSize={11} angle={-15} textAnchor="end" height={60} />
                          <YAxis fontSize={11} label={{ value: 'min', angle: -90, position: 'insideLeft' }} />
                          <Tooltip formatter={(v) => [`${v} min`, "Gns. tur tid"]} />
                          <Bar dataKey="avg_tour_minutes" fill="#a855f7" name="Gns. min/tur" radius={[3, 3, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Driver Performance Bar Chart */}
                {statisticsData.driver_performance.length > 0 && (
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-driver-chart">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <BarChart3 className="w-5 h-5 text-emerald-600" /> Chauffør ture oversigt
                    </h3>
                    <div style={{ width: '100%', height: 300 }}>
                      <ResponsiveContainer>
                        <BarChart data={statisticsData.driver_performance} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="name" fontSize={11} />
                          <YAxis fontSize={11} />
                          <Tooltip />
                          <Legend />
                          <Bar dataKey="total_tours" fill="#94a3b8" name="Total ture" radius={[2, 2, 0, 0]} />
                          <Bar dataKey="completed_tours" fill="#22c55e" name="Fuldført" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Material Usage Table (full) */}
                <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6" data-testid="stats-material-table">
                  <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-orange-500" /> Materiale detaljer
                  </h3>
                  {statisticsData.material_usage.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                            <th className="p-3 text-left">#</th>
                            <th className="p-3 text-left">Materiale</th>
                            <th className="p-3 text-center">Antal ture</th>
                            <th className="p-3 text-center">Total vægt (kg)</th>
                            <th className="p-3 text-left">Fordeling</th>
                          </tr>
                        </thead>
                        <tbody>
                          {statisticsData.material_usage.map((m, i) => {
                            const maxCount = statisticsData.material_usage[0]?.count || 1;
                            return (
                              <tr key={m.name} className="border-b hover:bg-slate-50 dark:hover:bg-slate-900">
                                <td className="p-3 text-slate-400 font-mono text-xs">{i + 1}</td>
                                <td className="p-3 font-medium">{m.name}</td>
                                <td className="p-3 text-center font-bold">{m.count}</td>
                                <td className="p-3 text-center">{m.weight.toLocaleString()}</td>
                                <td className="p-3">
                                  <div className="h-4 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden w-32">
                                    <div
                                      className="h-full bg-orange-500 rounded-full"
                                      style={{ width: `${(m.count / maxCount) * 100}%` }}
                                    />
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-slate-400 text-center py-8">Ingen materialedata</p>
                  )}
                </div>
              </>
            )}
          </section>
        )}

        {/* ARCHIVES TAB - PDF Downloads */}
        {activeTab === "archives" && (
          <div className="space-y-4">
            {/* Sub-tab toggle - merger PDF Arkiv + Chauffør Arkiv */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-1.5 inline-flex gap-1">
              <button
                onClick={() => setArchivesSubTab("pdf")}
                data-testid="archives-subtab-pdf"
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                  archivesSubTab === "pdf"
                    ? "bg-purple-600 text-white"
                    : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                }`}
              >
                <Archive className="w-4 h-4 inline mr-2" /> Dagrapporter (PDF)
              </button>
              <button
                onClick={() => setArchivesSubTab("receipts")}
                data-testid="archives-subtab-receipts"
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                  archivesSubTab === "receipts"
                    ? "bg-emerald-600 text-white"
                    : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                }`}
              >
                <Camera className="w-4 h-4 inline mr-2" /> Kvittering-arkiv
              </button>
              {/* 2026-10-18: Genvejen "Ture → Historik" er fjernet - tur-historikken
                  findes kun under Ture > Historik. */}
            </div>

            {archivesSubTab === "receipts" && (
              <section className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm p-6 border border-border" data-testid="merged-receipts-archive-section">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <Camera className="w-5 h-5 text-emerald-600" /> Kvittering-arkiv
                  </h2>
                  {/* Fase 17: View-mode toggle. "Tabel" viser alle
                      kvitteringer i én søgbar liste med filtre.
                      "Pr. chauffør" viser den klassiske mappe-struktur. */}
                  <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-1 bg-slate-50 dark:bg-slate-900" role="tablist">
                    <button
                      onClick={() => setReceiptsArchiveView("table")}
                      data-testid="receipts-archive-view-table"
                      className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                        receiptsArchiveView === "table"
                          ? "bg-emerald-600 text-white shadow"
                          : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      }`}
                    >
                      <Camera className="w-3.5 h-3.5 inline mr-1" /> Tabel
                    </button>
                    <button
                      onClick={() => setReceiptsArchiveView("drivers")}
                      data-testid="receipts-archive-view-drivers"
                      className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                        receiptsArchiveView === "drivers"
                          ? "bg-amber-600 text-white shadow"
                          : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      }`}
                    >
                      <FolderOpen className="w-3.5 h-3.5 inline mr-1" /> Pr. chauffør
                    </button>
                  </div>
                </div>
                {receiptsArchiveView === "table" ? (
                  <ReceiptOCRArchive currentUserName={authUser?.name || ""} />
                ) : (
                  <AdminReceiptList />
                )}
              </section>
            )}

            {archivesSubTab === "pdf" && (
              <section className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
                <h2 className="font-heading font-bold text-xl mb-4 flex items-center gap-2">
                  <Archive className="w-6 h-6 text-purple-600" /> 
                  PDF Arkiv - Dagrapporter
                </h2>
            
            {pdfArchives.length > 0 ? (() => {
              // Deduplicate: keep latest archive per (driver_name + report_date)
              const dedupMap = new Map();
              pdfArchives.forEach(a => {
                const key = `${a.driver_name || ""}|${a.report_date || ""}`;
                const existing = dedupMap.get(key);
                if (!existing || (a.created_at || "") > (existing.created_at || "")) {
                  dedupMap.set(key, a);
                }
              });
              const dedupedArchives = Array.from(dedupMap.values());

              // Helper: extract HH:MM from ISO timestamp
              const isoToTime = (iso) => {
                if (!iso) return "";
                try {
                  const d = new Date(iso);
                  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
                } catch (e) { return ""; }
              };
              // Fase 18.3 (2026-02-28): Brug `time_summary` fra backend som
              // primær kilde (multi-IND/UD + pauser). Fald tilbage til legacy
              // start_time/end_time-felter hvis chaufføren ikke har stemplet.
              const getStartTime = (a) => (a.time_summary && a.time_summary.start) || a.start_time || "";
              const getEndTime = (a) => (a.time_summary && a.time_summary.end) || a.end_time || isoToTime(a.created_at);
              const calcDuration = (s, e, a) => {
                // Foretræk work_min (excl. pause) hvis time_summary findes
                if (a && a.time_summary && a.time_summary.work_min) return a.time_summary.work_min;
                if (!s || !e || !s.includes(":") || !e.includes(":")) return null;
                const [sh, sm] = s.split(":").map(Number);
                const [eh, em] = e.split(":").map(Number);
                let mins = (eh * 60 + em) - (sh * 60 + sm);
                if (mins < 0) mins += 24 * 60;
                return mins;
              };
              const fmtDur = (mins) => {
                if (mins == null) return "-";
                const h = Math.floor(mins / 60);
                const m = mins % 60;
                return `${h}t ${m.toString().padStart(2, "0")}m`;
              };
              const fmtDayMonth = (d) => d.toLocaleDateString("da-DK", { day: "numeric", month: "short" });

              // Fase 15.14/15.15 (2026-02-XX): Konfigurerbar lønperiode pr.
              // logistik-firma med 3 cyklus-typer:
              //   - monthly: payroll_start_day (1-28) → slutdag = start-1 i M+1
              //   - weekly: 7 dage fra ankerdato (ugedag fastholdes)
              //   - biweekly: 14 dage fra ankerdato
              const cycleType = payrollSettings?.payroll_cycle_type || "monthly";
              const startDayCfg = Math.max(1, Math.min(28, Number(payrollSettings?.payroll_start_day) || 20));
              const anchorDateCfg = (payrollSettings?.payroll_anchor_date || "").trim();
              const fmtIso = (d) => `${d.getFullYear()}-${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}`;
              const getCycleInfo = (reportDateStr) => {
                const d = new Date(reportDateStr + "T00:00:00");
                if (cycleType === "weekly" || cycleType === "biweekly") {
                  const cycleLen = cycleType === "weekly" ? 7 : 14;
                  const anchor = anchorDateCfg ? new Date(anchorDateCfg + "T00:00:00") : null;
                  if (!anchor || isNaN(anchor.getTime())) {
                    // Fallback: brug uge-start = mandag i d's egen uge
                    const fb = new Date(d);
                    fb.setHours(0,0,0,0);
                    const dow = fb.getDay(); // 0=Sunday..6=Saturday
                    const mondayOffset = dow === 0 ? -6 : 1 - dow;
                    fb.setDate(fb.getDate() + mondayOffset);
                    const fbEnd = new Date(fb);
                    fbEnd.setDate(fb.getDate() + cycleLen - 1);
                    const cycleKey = `${fmtIso(fb)}_${cycleLen}`;
                    return {
                      cycleKey,
                      monthLabel: `${cycleLen===7?"Uge":"14-dage"} fra ${fmtDayMonth(fb)}`,
                      rangeLabel: `${fmtDayMonth(fb)} - ${fmtDayMonth(fbEnd)}`,
                    };
                  }
                  // Beregn hvor mange cycler der er gået siden anker
                  const msPerDay = 86400000;
                  const daysDiff = Math.floor((d - anchor) / msPerDay);
                  const cyclesElapsed = Math.floor(daysDiff / cycleLen);
                  const cycleStart = new Date(anchor);
                  cycleStart.setDate(anchor.getDate() + cyclesElapsed * cycleLen);
                  const cycleEnd = new Date(cycleStart);
                  cycleEnd.setDate(cycleStart.getDate() + cycleLen - 1);
                  const cycleKey = `${fmtIso(cycleStart)}_${cycleLen}`;
                  const monthLabel = cycleType === "weekly"
                    ? `Uge fra ${fmtDayMonth(cycleStart)}`
                    : `14-dages fra ${fmtDayMonth(cycleStart)}`;
                  return {
                    cycleKey,
                    monthLabel,
                    rangeLabel: `${fmtDayMonth(cycleStart)} - ${fmtDayMonth(cycleEnd)}`,
                  };
                }
                // Monthly (default)
                const startDay = startDayCfg;
                const endDayN  = startDay <= 1 ? 28 : startDay - 1;
                const day = d.getDate();
                const cycleEndDate = new Date(d.getFullYear(), d.getMonth(), endDayN);
                if (day >= startDay) {
                  cycleEndDate.setMonth(d.getMonth() + 1);
                }
                const cycleStartDate = new Date(cycleEndDate);
                cycleStartDate.setMonth(cycleEndDate.getMonth() - 1);
                cycleStartDate.setDate(startDay);
                const cycleKey = `${cycleEndDate.getFullYear()}-${(cycleEndDate.getMonth() + 1).toString().padStart(2, "0")}`;
                const monthLabel = cycleEndDate.toLocaleDateString("da-DK", { month: "long", year: "numeric" });
                const rangeLabel = `${fmtDayMonth(cycleStartDate)} - ${fmtDayMonth(cycleEndDate)}`;
                return { cycleKey, monthLabel, rangeLabel };
              };

              // CSV export helper
              const escapeCsv = (v) => {
                if (v == null) return "";
                const s = String(v);
                if (s.includes(",") || s.includes('"') || s.includes("\n")) {
                  return '"' + s.replace(/"/g, '""') + '"';
                }
                return s;
              };
              const exportCsv = (rows, filename) => {
                // Fase 18.4 (2026-02-28): Konverteret til XLSX med to faner -
                // "Dagrapporter" (én række pr. dag som tidligere) og
                // "Tidsstempler" (én række pr. driver_time_entry, så
                // ind/ud/pause-vinduerne kan revideres på timeslice-niveau).
                // Filename .csv erstattes automatisk med .xlsx.
                const dayRows = rows.map(a => {
                  const startT = getStartTime(a);
                  const endT = getEndTime(a);
                  const dur = calcDuration(startT, endT, a);
                  const pauseM = (a.time_summary && a.time_summary.pause_min) || 0;
                  const spanM = (a.time_summary && a.time_summary.span_min) || dur || 0;
                  const slices = a.time_summary
                    ? (a.time_summary.work_slices.length + a.time_summary.pause_slices.length)
                    : 0;
                  return {
                    "Dato": a.report_date || "",
                    "Chauffør": a.driver_name || "",
                    "Plads": a.plads || "",
                    "Ture (fuldført)": a.completed_tours || 0,
                    "Ture (total)": a.total_tours || 0,
                    "Vægt (kg)": a.total_weight || 0,
                    "Start (første IND)": startT || "",
                    "Slut (sidste UD)": endT || "",
                    "Arbejde (min)": dur != null ? dur : "",
                    "Arbejde": fmtDur(dur),
                    "Pause (min)": pauseM,
                    "Total span (min)": spanM,
                    "Antal stempler": slices,
                  };
                });

                const sliceRows = [];
                rows.forEach(a => {
                  const ts = a.time_summary;
                  if (!ts || (!ts.work_slices?.length && !ts.pause_slices?.length)) return;
                  const all = [...(ts.work_slices || []), ...(ts.pause_slices || [])]
                    .sort((x, y) => (x.start_time || "").localeCompare(y.start_time || ""));
                  all.forEach((s, idx) => {
                    sliceRows.push({
                      "Dato": a.report_date || "",
                      "Chauffør": a.driver_name || "",
                      "Rækkefølge": idx + 1,
                      "Type": s.slice_type === "pause" ? "Pause" : "Arbejde",
                      "Start": s.start_time || "",
                      "Slut": s.end_time || (s.open ? "(åben)" : ""),
                      "Varighed (min)": s.duration_minutes || 0,
                      "Varighed": fmtDur(s.duration_minutes || 0),
                      "Manuel": s.manual ? "Ja" : "Nej",
                      "Stempel-type": s.manual_type || "",
                      "Årsag": s.reason || "",
                      "Åben": s.open ? "Ja" : "Nej",
                    });
                  });
                });

                const wb = XLSX.utils.book_new();
                const wsDays = XLSX.utils.json_to_sheet(dayRows);
                XLSX.utils.book_append_sheet(wb, wsDays, "Dagrapporter");
                // Auto-bred kolonner i Dagrapporter
                wsDays["!cols"] = [
                  { wch: 12 }, { wch: 20 }, { wch: 18 }, { wch: 14 }, { wch: 12 },
                  { wch: 12 }, { wch: 18 }, { wch: 18 }, { wch: 13 }, { wch: 10 },
                  { wch: 12 }, { wch: 16 }, { wch: 14 },
                ];
                if (sliceRows.length > 0) {
                  const wsSlices = XLSX.utils.json_to_sheet(sliceRows);
                  wsSlices["!cols"] = [
                    { wch: 12 }, { wch: 20 }, { wch: 11 }, { wch: 10 }, { wch: 8 },
                    { wch: 10 }, { wch: 14 }, { wch: 10 }, { wch: 8 }, { wch: 14 },
                    { wch: 30 }, { wch: 6 },
                  ];
                  XLSX.utils.book_append_sheet(wb, wsSlices, "Tidsstempler");
                } else {
                  // Tom Tidsstempler-fane så brugeren stadig kan se at fanen findes.
                  const ws = XLSX.utils.json_to_sheet([{ Info: "Ingen tidsregistreringer for denne periode" }]);
                  XLSX.utils.book_append_sheet(wb, ws, "Tidsstempler");
                }
                const xlsxName = filename.replace(/\.csv$/i, ".xlsx");
                XLSX.writeFile(wb, xlsxName);
              };

              // Bulk PDF ZIP download
              // 2026-10-16: Dagrapporter bygges FRISKT ud fra nuværende data
              // (alle stemplinger, ture, godkendte rettelser og prisreglernes
              // pause-regel) - ikke den fil chaufføren gemte ved "Afslut dag".
              const freshDayReportPdf = (a, rep) => buildDayReportPdf({
                title: "Dagrapport", report: rep, driverName: a.driver_name,
                vehicleReg: rep.vehicle_reg || a.vehicle_reg, date: a.report_date, notes: rep.notes,
              });
              const downloadFreshPdf = async (a) => {
                try {
                  const { data: rep } = await axios.get(`${API}/admin/day-report/${a.id}`);
                  freshDayReportPdf(a, rep).save(dayReportFileName("dagrapport", a.report_date, a.driver_name));
                } catch (e) {
                  toast.error(formatApiError(e) + " - åbner den gemte original i stedet");
                  window.open(`${API}/pdf-archive/${a.id}`, "_blank");
                }
              };
              const downloadPdfZip = async (rows, filename) => {
                const list = rows.filter(a => a.has_pdf !== false);
                if (list.length === 0) {
                  toast.error("Ingen PDF'er at downloade");
                  return;
                }
                try {
                  toast.info(`Bygger ${list.length} PDF'er...`);
                  const { data: reps } = await axios.post(`${API}/admin/day-reports`, { ids: list.map(a => a.id) });
                  const { default: JSZip } = await import("jszip");
                  const zip = new JSZip();
                  const used = {};
                  let skipped = 0;
                  reps.forEach(rep => {
                    const a = list.find(x => x.id === rep.archive_id);
                    if (!a || rep.error) { skipped += 1; return; }
                    let name = dayReportFileName("dagrapport", a.report_date, a.driver_name);
                    used[name] = (used[name] || 0) + 1;
                    if (used[name] > 1) name = name.replace(/\.pdf$/, `_${used[name]}.pdf`);
                    zip.file(name, freshDayReportPdf(a, rep).output("arraybuffer"));
                  });
                  const blob = await zip.generateAsync({ type: "blob" });
                  saveAs(blob, filename);
                  toast.success(`${list.length - skipped} PDF'er downloadet${skipped ? ` (${skipped} kunne ikke bygges)` : ""}`);
                } catch (e) {
                  toast.error("Fejl ved ZIP download: " + formatApiError(e));
                }
              };
              const months = {};
              dedupedArchives.forEach(a => {
                const cycleInfo = getCycleInfo(a.report_date);
                const key = cycleInfo.cycleKey;
                if (!months[key]) months[key] = {
                  label: cycleInfo.monthLabel,
                  rangeLabel: cycleInfo.rangeLabel,
                  drivers: {},
                  total_tours: 0, total_completed: 0, total_minutes: 0, total_weight: 0,
                  unique_dates: new Set()
                };
                const drv = a.driver_name || "Ukendt";
                if (!months[key].drivers[drv]) months[key].drivers[drv] = {
                  archives: [], total_tours: 0, total_completed: 0, total_minutes: 0, total_weight: 0,
                  unique_dates: new Set()
                };
                const startT = getStartTime(a);
                const endT = getEndTime(a);
                const dur = calcDuration(startT, endT, a);
                months[key].drivers[drv].archives.push({ ...a, _duration: dur, _endTime: endT, _startTime: startT });
                months[key].drivers[drv].total_tours += a.total_tours || 0;
                months[key].drivers[drv].total_completed += a.completed_tours || 0;
                months[key].drivers[drv].total_minutes += dur || 0;
                months[key].drivers[drv].total_weight += a.total_weight || 0;
                months[key].drivers[drv].unique_dates.add(a.report_date);
                months[key].total_tours += a.total_tours || 0;
                months[key].total_completed += a.completed_tours || 0;
                months[key].total_minutes += dur || 0;
                months[key].total_weight += a.total_weight || 0;
                months[key].unique_dates.add(a.report_date);
              });
              const monthKeys = Object.keys(months).sort().reverse();
              // Fase 15.22 (2026-02-21): Gruppér efter år så listen ikke
              // vokser uendeligt. Nuværende år er åbent som default,
              // tidligere år er kollapsede (klik på årstal for at se).
              const currentYear = new Date().getFullYear();
              const yearGroups = {};
              monthKeys.forEach(k => {
                const m = k.match(/^(\d{4})/);
                const yr = m ? m[1] : "Andet";
                if (!yearGroups[yr]) yearGroups[yr] = [];
                yearGroups[yr].push(k);
              });
              const years = Object.keys(yearGroups).sort().reverse();
              // Aggregér totals pr. år til badges på årstal-headeren
              const yearTotals = {};
              years.forEach(yr => {
                const totals = { completed: 0, minutes: 0, days: 0, weight: 0 };
                const dateSet = new Set();
                yearGroups[yr].forEach(k => {
                  totals.completed += months[k].total_completed || 0;
                  totals.minutes += months[k].total_minutes || 0;
                  totals.weight += months[k].total_weight || 0;
                  months[k].unique_dates.forEach(d => dateSet.add(d));
                });
                totals.days = dateSet.size;
                yearTotals[yr] = totals;
              });

              return (
                <div className="space-y-5">
                  {/* Export all button */}
                  <div className="flex justify-end">
                    <button
                      onClick={() => exportCsv(dedupedArchives, `arkiv_alle_${new Date().toISOString().slice(0, 10)}.csv`)}
                      className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white font-bold rounded-lg hover:bg-emerald-700 transition-colors text-sm"
                      data-testid="export-csv-all-btn"
                      title="Eksporterer XLSX med 2 faner: Dagrapporter + Tidsstempler"
                    >
                      <Download className="w-4 h-4" /> Eksporter alt (Excel)
                    </button>
                  </div>
                  {years.map(yr => {
                    const yt = yearTotals[yr];
                    const isCurrent = String(currentYear) === yr;
                    return (
                      <details
                        key={`year-${yr}`}
                        open={isCurrent}
                        className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
                        data-testid={`archive-year-${yr}`}
                      >
                        <summary className="cursor-pointer px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-700 dark:from-slate-900 dark:to-slate-800 text-white flex items-center justify-between gap-3 hover:from-slate-700 hover:to-slate-600 transition-colors flex-wrap">
                          <div className="flex items-center gap-2 min-w-0">
                            <ChevronRight className="w-4 h-4 group-open:rotate-90 transition-transform flex-shrink-0" />
                            <div className="leading-tight min-w-0 flex items-center gap-2">
                              <span className="font-black text-xl tabular-nums" data-testid={`archive-year-label-${yr}`}>{yr}</span>
                              {isCurrent && (
                                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-emerald-500 text-slate-900">Nuværende</span>
                              )}
                              <span className="text-[11px] text-slate-300 font-medium">· {yearGroups[yr].length} periode{yearGroups[yr].length === 1 ? "" : "r"}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 text-[11px] sm:text-xs flex-wrap" data-testid={`archive-year-stats-${yr}`}>
                            <span className="bg-white/15 px-2 py-1 rounded-md font-black flex items-center gap-1">
                              📦 {yt.completed} contai.
                            </span>
                            <span className="bg-white/15 px-2 py-1 rounded-md font-black flex items-center gap-1">
                              ⏱ {fmtDur(yt.minutes)}
                            </span>
                            <span className="bg-white/15 px-2 py-1 rounded-md font-black flex items-center gap-1">
                              📅 {yt.days} dage
                            </span>
                            <span className="bg-white/15 px-2 py-1 rounded-md font-black hidden sm:flex items-center gap-1">
                              ⚖ {(yt.weight || 0).toLocaleString()} kg
                            </span>
                          </div>
                        </summary>
                        <div className="p-3 space-y-3">
                          {yearGroups[yr].map(mkey => {
                    const m = months[mkey];
                    const monthDays = m.unique_dates.size;
                    // Fase 18.4 (2026-02-28): Hvis året kun har én periode,
                    // er årets badges identiske med månedens - skjul månedens
                    // info-badges for at undgå duplikering (CSV/ZIP-knapper
                    // beholdes naturligvis).
                    const singlePeriodInYear = yearGroups[yr].length === 1;
                    const driverKeys = Object.keys(m.drivers);
                    const singleDriverInMonth = driverKeys.length === 1;
                    return (
                      <details key={mkey} open={isCurrent} className="group/m bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                        <summary className="cursor-pointer px-4 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white flex items-center justify-between gap-3 hover:from-purple-700 hover:to-indigo-700 transition-colors flex-wrap" data-testid={`archive-month-${mkey}`}>
                          <div className="flex items-center gap-2 min-w-0">
                            <ChevronRight className="w-4 h-4 group-open:rotate-90 transition-transform flex-shrink-0" />
                            <div className="leading-tight min-w-0">
                              <div className="font-black capitalize text-base truncate">{m.label}</div>
                              <div className="text-[10px] text-purple-100/80 font-medium">{m.rangeLabel}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 text-[11px] sm:text-xs flex-wrap" data-testid={`archive-month-stats-${mkey}`}>
                            {!singlePeriodInYear && (
                              <>
                                <span className="bg-white/25 px-2 py-1 rounded-md font-black flex items-center gap-1">
                                  📦 {m.total_completed} contai.
                                </span>
                                <span className="bg-white/25 px-2 py-1 rounded-md font-black flex items-center gap-1">
                                  ⏱ {fmtDur(m.total_minutes)}
                                </span>
                                <span className="bg-white/25 px-2 py-1 rounded-md font-black flex items-center gap-1">
                                  📅 {monthDays} dage
                                </span>
                                <span className="bg-white/25 px-2 py-1 rounded-md font-black hidden sm:flex items-center gap-1">
                                  ⚖ {(m.total_weight || 0).toLocaleString()} kg
                                </span>
                              </>
                            )}
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                const rows = Object.values(m.drivers).flatMap(d => d.archives);
                                exportCsv(rows, `arkiv_${mkey}.csv`);
                              }}
                              className="bg-emerald-500 hover:bg-emerald-600 px-2 py-1 rounded-md font-black flex items-center gap-1 transition-colors"
                              data-testid={`export-csv-month-${mkey}`}
                              title="Eksporter denne måned til Excel (Dagrapporter + Tidsstempler)"
                            >
                              <Download className="w-3 h-3" /> Excel
                            </button>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                const rows = Object.values(m.drivers).flatMap(d => d.archives);
                                downloadPdfZip(rows, `pdf_arkiv_${mkey}.zip`);
                              }}
                              className="bg-rose-500 hover:bg-rose-600 px-2 py-1 rounded-md font-black flex items-center gap-1 transition-colors"
                              data-testid={`download-zip-month-${mkey}`}
                              title="Download alle PDF'er for denne måned som ZIP"
                            >
                              <Archive className="w-3 h-3" /> ZIP
                            </button>
                          </div>
                        </summary>

                        <div className="p-3 space-y-3">
                          {Object.entries(m.drivers).map(([drvName, drv]) => {
                            const drvDays = drv.unique_dates.size;
                            return (
                            <details key={drvName} open className="group bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                              <summary className="cursor-pointer px-3 py-2.5 bg-slate-100 dark:bg-slate-700/50 flex items-center justify-between gap-2 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex-wrap" data-testid={`archive-driver-${mkey}-${drvName}`}>
                                <div className="flex items-center gap-2 min-w-0">
                                  <ChevronRight className="w-3.5 h-3.5 group-open:rotate-90 transition-transform flex-shrink-0" />
                                  <Users className="w-4 h-4 text-purple-600 flex-shrink-0" />
                                  <span className="font-bold text-slate-800 dark:text-white truncate">{drvName}</span>
                                </div>
                                <div className="flex items-center gap-1.5 text-[10px] sm:text-xs flex-wrap">
                                  {!singleDriverInMonth && (
                                    <>
                                      <span className="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded font-bold">📦 {drv.total_completed} contai.</span>
                                      <span className="bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded font-bold">⏱ {fmtDur(drv.total_minutes)}</span>
                                      <span className="bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded font-bold">📅 {drvDays} dage</span>
                                      <span className="hidden sm:inline bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded font-bold">⚖ {(drv.total_weight || 0).toLocaleString()} kg</span>
                                      <button
                                        onClick={(e) => {
                                          e.preventDefault();
                                          e.stopPropagation();
                                          const safeName = (drvName || "ukendt").replace(/[^a-zA-Z0-9_-]/g, "_");
                                          exportCsv(drv.archives, `arkiv_${mkey}_${safeName}.csv`);
                                        }}
                                        className="bg-emerald-500 hover:bg-emerald-600 text-white px-2 py-0.5 rounded font-bold flex items-center gap-1 transition-colors"
                                        data-testid={`export-csv-driver-${mkey}-${drvName}`}
                                        title={`Eksporter ${drvName} til Excel (Dagrapporter + Tidsstempler)`}
                                      >
                                        <Download className="w-3 h-3" /> Excel
                                      </button>
                                      <button
                                        onClick={(e) => {
                                          e.preventDefault();
                                          e.stopPropagation();
                                          const safeName = (drvName || "ukendt").replace(/[^a-zA-Z0-9_-]/g, "_");
                                          downloadPdfZip(drv.archives, `pdf_${mkey}_${safeName}.zip`);
                                        }}
                                        className="bg-rose-500 hover:bg-rose-600 text-white px-2 py-0.5 rounded font-bold flex items-center gap-1 transition-colors"
                                        data-testid={`download-zip-driver-${mkey}-${drvName}`}
                                        title={`Download ${drvName}'s PDF'er som ZIP`}
                                      >
                                        <Archive className="w-3 h-3" /> ZIP
                                      </button>
                                    </>
                                  )}
                                </div>
                              </summary>

                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="bg-slate-50 dark:bg-slate-900/40 text-slate-600 dark:text-slate-400 text-xs">
                                      <th className="p-2 text-left font-semibold">Dato</th>
                                      <th className="p-2 text-left font-semibold">Plads</th>
                                      <th className="p-2 text-left font-semibold">Ture</th>
                                      <th className="p-2 text-left font-semibold">Vægt</th>
                                      <th className="p-2 text-left font-semibold">Start</th>
                                      <th className="p-2 text-left font-semibold">Slut</th>
                                      <th className="p-2 text-left font-semibold">Arbejde</th>
                                      <th className="p-2 text-left font-semibold">Pause</th>
                                      <th className="p-2 text-left font-semibold">Total</th>
                                      <th className="p-2 text-left font-semibold">PDF</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {drv.archives
                                      .sort((a, b) => (b.report_date || "").localeCompare(a.report_date || ""))
                                      .map(a => {
                                        const ts = a.time_summary;
                                        const sliceCount = ts ? (ts.work_slices.length + ts.pause_slices.length) : 0;
                                        const pauseM = ts?.pause_min || 0;
                                        const spanM = ts?.span_min || 0;
                                        const allSlices = ts ? [...ts.work_slices, ...ts.pause_slices].sort((x, y) => (x.start_time || "").localeCompare(y.start_time || "")) : [];
                                        const sliceTitle = allSlices.map(s => `${s.slice_type === "pause" ? "☕" : "▶"} ${s.start_time}–${s.end_time || (s.open ? "åben" : "-")}`).join("\n");
                                        return (
                                        <tr key={a.id} className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30">
                                          <td className="p-2">{new Date(a.report_date + "T00:00:00").toLocaleDateString("da-DK", { day: "2-digit", month: "short" })}</td>
                                          <td className="p-2">{a.plads || "-"}</td>
                                          <td className="p-2 font-medium">{a.completed_tours}/{a.total_tours}</td>
                                          <td className="p-2">{(a.total_weight || 0).toLocaleString()} kg</td>
                                          <td className="p-2 font-mono text-emerald-600 dark:text-emerald-400">
                                            {a._startTime || "-"}
                                            {sliceCount > 1 && (
                                              <span
                                                className="ml-1 inline-block px-1.5 py-0.5 text-[10px] font-bold bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded-full"
                                                title={sliceTitle}
                                                data-testid={`pdf-archive-slices-${a.id}`}
                                              >
                                                {sliceCount}×
                                              </span>
                                            )}
                                          </td>
                                          <td className="p-2 font-mono text-rose-600 dark:text-rose-400" data-testid={`archive-end-${a.id}`}>{a._endTime || "-"}</td>
                                          <td className="p-2 font-bold" data-testid={`pdf-archive-work-${a.id}`}>{fmtDur(a._duration)}</td>
                                          <td className="p-2 font-mono text-xs text-amber-600 dark:text-amber-400" data-testid={`pdf-archive-pause-${a.id}`}>{pauseM > 0 ? fmtDur(pauseM) : "-"}</td>
                                          <td className="p-2 font-mono text-xs text-slate-600 dark:text-slate-300" title="Fra første IND til sidste UD (inkl. pauser og huller)">{spanM > 0 ? fmtDur(spanM) : "-"}</td>
                                          <td className="p-2">
                                            {a.has_pdf !== false ? (
                                              <div className="flex items-center gap-2">
                                                <button
                                                  type="button"
                                                  onClick={() => downloadFreshPdf(a)}
                                                  className="px-3 py-1.5 bg-purple-500 hover:bg-purple-600 text-white rounded inline-flex items-center gap-1 text-xs font-bold transition-colors"
                                                  title="Dagrapport bygget ud fra de nuværende stemplinger, ture og godkendte rettelser"
                                                  data-testid={`archive-pdf-download-${a.id}`}
                                                >
                                                  <Download className="w-3.5 h-3.5" /> Download
                                                </button>
                                                <a
                                                  href={`${API}/pdf-archive/${a.id}`}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  className="text-[11px] text-slate-500 hover:text-purple-600 underline"
                                                  title="Den PDF chaufføren gemte ved Afslut dag (uændret)"
                                                >
                                                  Original
                                                </a>
                                              </div>
                                            ) : (
                                              <span className="px-2 py-1 bg-slate-200 text-slate-500 rounded text-xs italic" title="PDF data ikke gemt">PDF mangler</span>
                                            )}
                                          </td>
                                        </tr>
                                        );
                                      })}
                                  </tbody>
                                </table>
                              </div>
                            </details>
                            );
                          })}
                        </div>
                      </details>
                    );
                  })}
                          {/* Fase 15.22 (2026-02-21): luk år-gruppen */}
                        </div>
                      </details>
                    );
                  })}
                </div>
              );
            })() : (
              <div className="text-center py-12 text-slate-500">
                <Archive className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p>Ingen PDF'er gemt endnu</p>
                <p className="text-sm mt-1">PDF'er gemmes automatisk når chauffører afslutter dagen</p>
              </div>
            )}
          </section>
        )}

            {/* Fase 17: Old "receipts" + "ocr" sub-tab blocks merged
                into a single section rendered earlier (line ~7778). */}
          </div>
        )}

        {/* 2026-10-18 (P1): "Hurtigt overblik" er flyttet til én linje øverst på Ture. */}
        {/* 2026-10-16: "Ture" - ny daglig arbejdsflade (erstatter Manuelle ture
            og Arkiv > Ture). Se frontend/src/pages/ToursWorkspace.jsx. */}
        {activeTab === "tours" && (
          <ToursWorkspace
            drivers={activeDrivers}
            pladsList={pladsList}
            perms={can}
            profile={logisticsProfile}
            siteWord={isPremiumLogistics ? "Lokation" : "Genbrugsplads"}
          />
        )}

        {/* Schedule / Planning Tab
            Fase 11 (2026-06-18): Helt om-bygget side. Hovedformål: tildele
            ture (bestilt fra container-siden) til specifikke chauffører.
            Split-view: venstre = ikke-tildelte ture m. filtre, højre =
            chauffører med kapacitets-bar og aktive ture.
            Den gamle daglig/ugentlig plads-tildeling er bevaret som en
            sekundær fane ("Plads & fridag"). */}
        {activeTab === "schedule" && (
        <section className="space-y-4" data-testid="planning-section">
          {/* View Toggle */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-3 flex flex-wrap items-center gap-3">
            <h2 className="font-heading font-bold text-lg flex items-center gap-2 mr-2">
              <Calendar className="w-5 h-5 text-red-600" /> Tid &amp; ressourcer
            </h2>
            <div className="flex bg-slate-100 dark:bg-slate-700 rounded-lg p-1" role="tablist">
              {/* Fase 15.3 (2026-06-19): Ny "Tidsregistrering"-tab - vis alle
                  chaufførers Ind/Ud + Manuel-stempler for dagen som en
                  SuccessFactors-lignende timeline pr. chauffør. */}
              <button
                onClick={() => setPlanningView("time")}
                className={`px-3 py-1.5 rounded-md text-sm font-bold transition-colors ${planningView === "time" ? "bg-emerald-500 text-white shadow-sm" : "text-slate-600 dark:text-slate-300"}`}
                data-testid="planning-tab-time"
              >
                Tidsregistrering
              </button>
              {/* Fase 15.16 (2026-02-XX): "Planlæg ressourcer" - viser kun
                  Estimat-bestillinger (tour_type="estimat") så planlæggeren
                  har et samlet overblik over forventet ressourcebehov,
                  adskilt fra konkrete opgaver.
                  Fase 15.40 (2026-02-22): Tab vises kun når klienten har
                  feature `estimate` aktiveret. Default OFF.
                  Fase 15.41 (2026-02-22): Tab vises også når `loes_afhentning`
                  er aktiv - begge features fodrer rækker ind i ressource-
                  planlægningen. */}
              {resourcePlanningEnabled && (
                <button
                  onClick={() => setPlanningView("resources")}
                  className={`px-3 py-1.5 rounded-md text-sm font-bold transition-colors ${planningView === "resources" ? "bg-amber-500 text-white shadow-sm" : "text-slate-600 dark:text-slate-300"}`}
                  data-testid="planning-tab-resources"
                >
                  Planlæg ressourcer
                </button>
              )}
              {/* Fase 12 (2026-06-18): "Plads & fridag"-tab FJERNET helt
                  efter brugerønske. */}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <input
                type="date"
                value={adminReportDate}
                onChange={(e) => setAdminReportDate(e.target.value)}
                className="px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700"
                data-testid="planning-date-input"
              />
              <span className="text-xs text-muted-foreground hidden sm:inline">
                {new Date(adminReportDate + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" })}
              </span>
            </div>
          </div>

          {/* ============ TIDSREGISTRERING (Fase 15.3 + 15.28) ============ */}
          {planningView === "time" && (
            <PlanningTimeOverview reportDate={adminReportDate} drivers={drivers} />
          )}

          {/* ============ PLANLÆG RESSOURCER (Fase 15.16) ============
              Fase 15.40 (2026-02-22): Hele view'et er gated bag feature
              `estimate` - defensiv guard så DOM aldrig renderes selv hvis
              `planningView` skulle være "resources" pga. cached state.
              Fase 15.41 (2026-02-22): Også åbent for `loes_afhentning`. */}
          {planningView === "resources" && resourcePlanningEnabled && (
            <PlanningResourcesView />
          )}

          {/* ============ LEGACY DAILY/WEEKLY SCHEDULE ============ */}
          {planningView === "schedule" && (
          <section className="bg-white dark:bg-slate-800 rounded-xl shadow-lg">
          <div className="p-4 border-b border-border flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <h2 className="font-heading font-bold text-sm text-slate-600 dark:text-slate-300 uppercase tracking-wider">Plads & fridag (legacy)</h2>
              {/* View Mode Toggle */}
              <div className="flex bg-slate-100 dark:bg-slate-700 rounded-lg p-1">
                <button 
                  onClick={() => setViewMode("daily")}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === "daily" ? "bg-white dark:bg-slate-600 shadow-sm" : "text-slate-600 dark:text-slate-400"}`}
                >
                  Daglig
                </button>
                <button 
                  onClick={() => setViewMode("weekly")}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === "weekly" ? "bg-white dark:bg-slate-600 shadow-sm" : "text-slate-600 dark:text-slate-400"}`}
                >
                  Ugentlig
                </button>
              </div>
            </div>
            
            {viewMode === "daily" ? (
              <div className="flex items-center gap-2">
                <button 
                  onClick={sendEmailToAllDrivers}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                >
                  <Mail className="w-4 h-4" /> Send til alle
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button onClick={() => navigateWeek(-1)} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <span className="text-sm font-medium px-3">
                  Uge {getWeekNumber(new Date(weekStart))} - {new Date(weekStart).toLocaleDateString("da-DK", { day: 'numeric', month: 'short' })} til {new Date(new Date(weekStart).setDate(new Date(weekStart).getDate() + 6)).toLocaleDateString("da-DK", { day: 'numeric', month: 'short' })}
                </span>
                <button onClick={() => navigateWeek(1)} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
                  <ChevronRight className="w-5 h-5" />
                </button>
                <button 
                  onClick={saveWeeklySchedule}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ml-2"
                >
                  <Download className="w-4 h-4" /> Gem uge
                </button>
                <button 
                  onClick={sendWeeklyEmailToAllDrivers}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                >
                  <Mail className="w-4 h-4" /> Send ugeplan
                </button>
              </div>
            )}
          </div>
          
          {/* Daily View */}
          {viewMode === "daily" && (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                  <th className="p-3 text-left">Chauffør</th>
                  <th className="p-3 text-left">Nummerplade</th>
                  <th className="p-3 text-left">Email</th>
                  <th className="p-3 text-left">Arbejdssted</th>
                  <th className="p-3 text-center">Send Mail</th>
                </tr>
              </thead>
              <tbody>
                {drivers.map(driver => (
                  <tr key={driver.id} className={`border-b hover:bg-slate-50 dark:hover:bg-slate-900 ${driverSchedule[driver.id] === "FRI" ? "bg-green-50 dark:bg-green-950/20" : ""}`}>
                    <td className="p-3">
                      <span className="font-medium">{driver.name}</span>
                    </td>
                    <td className="p-3 font-mono text-sm">{driver.plate}</td>
                    <td className="p-3">
                      {driver.email ? (
                        <span className="text-sm text-blue-600">{driver.email}</span>
                      ) : (
                        <span className="text-sm text-red-500 italic">Ingen email</span>
                      )}
                    </td>
                    <td className="p-3">
                      <select 
                        value={driverSchedule[driver.id] || ""}
                        onChange={(e) => handleScheduleChange(driver.id, e.target.value)}
                        className={`px-3 py-2 border rounded-lg w-full max-w-xs ${driverSchedule[driver.id] === "FRI" ? "bg-green-100 text-green-800 font-bold" : ""}`}
                      >
                        <option value="">Vælg plads...</option>
                        <option value="FRI" className="bg-green-100 text-green-800 font-bold">🏖️ FRI (Fridag)</option>
                        {pladsList.map(p => (
                          <option key={p.id} value={p.name}>{p.name}</option>
                        ))}
                      </select>
                    </td>
                    <td className="p-3 text-center">
                      <button 
                        onClick={() => sendEmailToDriver(driver, driverSchedule[driver.id])}
                        disabled={!driver.email || !driverSchedule[driver.id]}
                        className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
                        title={!driver.email ? "Ingen email" : !driverSchedule[driver.id] ? "Vælg plads først" : "Send mail"}
                      >
                        <Mail className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Daily Summary */}
          <div className="p-4 border-t bg-slate-50 dark:bg-slate-900">
            <div className="flex flex-wrap gap-4 text-sm">
              <div>
                <span className="font-medium text-slate-600">Arbejder:</span>{" "}
                <span className="font-bold text-blue-600">
                  {drivers.filter(d => driverSchedule[d.id] && driverSchedule[d.id] !== "FRI").length}
                </span>
              </div>
              <div>
                <span className="font-medium text-slate-600">FRI:</span>{" "}
                <span className="font-bold text-green-600">
                  {drivers.filter(d => driverSchedule[d.id] === "FRI").length}
                </span>
              </div>
              <div>
                <span className="font-medium text-slate-600">Ikke tildelt:</span>{" "}
                <span className="font-bold text-amber-600">
                  {drivers.filter(d => !driverSchedule[d.id]).length}
                </span>
              </div>
            </div>
          </div>
          </>
          )}
          
          {/* Weekly View */}
          {viewMode === "weekly" && (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                  <th className="p-3 text-left sticky left-0 bg-slate-50 dark:bg-slate-900 z-10 min-w-[150px]">Chauffør</th>
                  {getWeekDates().map((date, idx) => {
                    const d = new Date(date);
                    const dayNames = ["søn", "man", "tir", "ons", "tor", "fre", "lør"];
                    const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                    return (
                      <th key={date} className={`p-2 text-center min-w-[100px] ${isWeekend ? "bg-slate-100 dark:bg-slate-800" : ""}`}>
                        <div className="font-bold">{dayNames[d.getDay()]}</div>
                        <div className="text-xs text-muted-foreground">{d.getDate()}/{d.getMonth() + 1}</div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {drivers.map(driver => (
                  <tr key={driver.id} className="border-b hover:bg-slate-50/50 dark:hover:bg-slate-900/50">
                    <td className="p-2 sticky left-0 bg-white dark:bg-slate-800 z-10 border-r">
                      <div className="font-medium text-sm">{driver.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{driver.plate}</div>
                    </td>
                    {getWeekDates().map((date) => {
                      const d = new Date(date);
                      const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                      const key = `${driver.id}-${date}`;
                      const value = weeklySchedule[key] || "";
                      
                      return (
                        <td key={date} className={`p-1 ${isWeekend ? "bg-slate-50 dark:bg-slate-800/50" : ""} ${value === "FRI" ? "bg-green-50 dark:bg-green-950/30" : ""}`}>
                          <select 
                            value={value}
                            onChange={(e) => handleWeeklyScheduleChange(driver.id, date, e.target.value)}
                            className={`w-full px-1 py-1.5 text-xs border rounded ${value === "FRI" ? "bg-green-100 text-green-800 font-bold" : "bg-white dark:bg-slate-700"}`}
                          >
                            <option value="">-</option>
                            <option value="FRI">🏖️ FRI</option>
                            {pladsList.map(p => (
                              <option key={p.id} value={p.name}>{p.name}</option>
                            ))}
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Weekly Summary */}
          <div className="p-4 border-t bg-slate-50 dark:bg-slate-900">
            <div className="flex flex-wrap gap-6 text-sm">
              {getWeekDates().map((date) => {
                const d = new Date(date);
                const dayNames = ["søn", "man", "tir", "ons", "tor", "fre", "lør"];
                const working = drivers.filter(dr => {
                  const val = weeklySchedule[`${dr.id}-${date}`];
                  return val && val !== "FRI";
                }).length;
                const fri = drivers.filter(dr => weeklySchedule[`${dr.id}-${date}`] === "FRI").length;
                
                return (
                  <div key={date} className="text-center">
                    <div className="font-medium text-xs text-slate-500">{dayNames[d.getDay()]} {d.getDate()}/{d.getMonth() + 1}</div>
                    <div className="flex gap-2 mt-1">
                      <span className="text-blue-600 font-bold">{working}</span>
                      <span className="text-green-600 font-bold">{fri} fri</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          </>
          )}
        </section>
          )}
        </section>
        )}

        {/* Chauffører, vogne, hængere og beskeder (2026-10-18: samme opbygning
            som Medarbejdere/Team - se frontend/src/pages/DriversPanel.jsx). */}
        {activeTab === "drivers" && (
          <DriversPanel drivers={drivers} messages={messages} onChanged={fetchData} />
        )}

        {/* Plads Management Tab */}
        {activeTab === "plads" && (
          <LogisticsLocations profile={logisticsProfile} pladsList={pladsList} onChanged={fetchData} />
        )}

        {/* History Tab */}
        {activeTab === "history" && (
        <section className="bg-white dark:bg-slate-800 rounded-xl shadow-lg">
          <div className="p-4 border-b border-border">
            <h2 className="font-heading font-bold text-lg flex items-center gap-2">
              <History className="w-5 h-5 text-red-600" /> Rapport Historik (sidste 30 dage)
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                  <th className="p-3 text-left">Dato</th>
                  <th className="p-3 text-center">Ture</th>
                  <th className="p-3 text-center">Færdig</th>
                  <th className="p-3 text-center">Total kg</th>
                  <th className="p-3 text-center">Chauffører</th>
                </tr>
              </thead>
              <tbody>
                {reportHistory.map(day => (
                  <tr key={day.date} className="border-b hover:bg-slate-50 dark:hover:bg-slate-900">
                    <td className="p-3 font-medium">
                      {new Date(day.date).toLocaleDateString("da-DK", { weekday: 'short', day: 'numeric', month: 'short' })}
                    </td>
                    <td className="p-3 text-center">
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold">
                        {day.total_tours}
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      <span className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs font-bold">
                        {day.completed_tours}
                      </span>
                    </td>
                    <td className="p-3 text-center font-mono font-bold">
                      {day.total_weight.toLocaleString()} kg
                    </td>
                    <td className="p-3 text-center">
                      {day.driver_count}
                    </td>
                  </tr>
                ))}
                {reportHistory.length === 0 && (
                  <tr>
                    <td colSpan="5" className="p-8 text-center text-muted-foreground">
                      Ingen historik fundet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          
          {/* Summary stats */}
          {reportHistory.length > 0 && (
            <div className="p-4 border-t bg-slate-50 dark:bg-slate-900">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-2xl font-bold text-blue-600">
                    {reportHistory.reduce((sum, d) => sum + d.total_tours, 0)}
                  </div>
                  <div className="text-xs text-muted-foreground">Total ture</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-emerald-600">
                    {reportHistory.reduce((sum, d) => sum + d.completed_tours, 0)}
                  </div>
                  <div className="text-xs text-muted-foreground">Fuldførte</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-amber-600">
                    {reportHistory.reduce((sum, d) => sum + d.total_weight, 0).toLocaleString()} kg
                  </div>
                  <div className="text-xs text-muted-foreground">Total vægt</div>
                </div>
              </div>
            </div>
          )}
        </section>
        )}
        
        {/* Container Orders Tab */}
        {activeTab === "orders" && (
        <section className="space-y-6">
          {/* Location Management */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
            <h2 className="font-heading font-bold text-lg flex items-center gap-2 mb-4">
              <MapPin className="w-5 h-5 text-red-600" /> Lokationer (Adgangskoder)
            </h2>
            
            {/* Add new location */}
            <div className="flex gap-3 mb-4 p-3 bg-slate-50 rounded-lg">
              <input
                type="text"
                value={newLocation.code}
                onChange={(e) => setNewLocation({...newLocation, code: e.target.value})}
                placeholder="Kode (f.eks. 3030)"
                className="px-3 py-2 border rounded-lg w-32 font-mono"
              />
              <input
                type="text"
                value={newLocation.name}
                onChange={(e) => setNewLocation({...newLocation, name: e.target.value})}
                placeholder="Lokation navn"
                className="flex-1 px-3 py-2 border rounded-lg"
              />
              <button onClick={handleAddLocation}
                className="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 flex items-center gap-1">
                <Plus className="w-4 h-4" /> Tilføj
              </button>
            </div>
            
            {/* Location list */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {orderLocations.map(loc => (
                <div key={loc.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg gap-2" data-testid={`location-card-${loc.id}`}>
                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-lg font-bold text-red-600 mr-2">{loc.code}</span>
                    <span className="text-slate-700">{loc.name}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${loc.active ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                    {loc.active ? "Aktiv" : "Inaktiv"}
                  </span>
                  <button
                    onClick={() => handleDeleteLocation(loc)}
                    className="flex-shrink-0 p-2 text-red-500 hover:bg-red-100 hover:text-red-700 rounded-lg transition-colors"
                    title="Slet lokation"
                    data-testid={`delete-location-${loc.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              {orderLocations.length === 0 && (
                <p className="text-slate-500 col-span-3 text-center py-4">Ingen lokationer - tilføj den første ovenfor</p>
              )}
            </div>
          </div>
          
          {/* Orders List */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading font-bold text-lg flex items-center gap-2">
                <Truck className="w-5 h-5 text-red-600" /> Container Bestillinger
              </h2>
              
              {/* Filter by location */}
              <select
                value={selectedOrderLocation}
                onChange={(e) => setSelectedOrderLocation(e.target.value)}
                className="px-3 py-2 border rounded-lg"
              >
                <option value="">Alle lokationer</option>
                {orderLocations.map(loc => (
                  <option key={loc.id} value={loc.code}>{loc.name}</option>
                ))}
              </select>
            </div>
            
            {/* Orders table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 dark:bg-slate-900 border-b">
                    <th className="p-3 text-left">Lokation</th>
                    <th className="p-3 text-left">Kunde</th>
                    <th className="p-3 text-left">Adresse</th>
                    <th className="p-3 text-left">Container</th>
                    <th className="p-3 text-left">Materiale</th>
                    <th className="p-3 text-left">Dato</th>
                    <th className="p-3 text-left">Prioritet</th>
                    <th className="p-3 text-left">Status</th>
                    <th className="p-3 text-left">Handlinger</th>
                  </tr>
                </thead>
                <tbody>
                  {containerOrders.map(order => (
                    <tr key={order.id} className={`border-b hover:bg-slate-50 ${
                      order.priority === "haster" ? "bg-red-50" : 
                      order.priority === "sidst" ? "bg-slate-50" : ""
                    }`}>
                      <td className="p-3">
                        <span className="font-mono font-bold text-red-600">{order.location_code}</span>
                        <div className="text-xs text-slate-500">{order.location_name}</div>
                      </td>
                      <td className="p-3 font-medium">{order.customer_name}</td>
                      <td className="p-3 text-sm">{order.customer_address}</td>
                      <td className="p-3 font-mono">{order.container_number}</td>
                      <td className="p-3">{order.material}</td>
                      <td className="p-3">{new Date(order.order_date).toLocaleDateString("da-DK")}</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                          ORDER_PRIORITIES[order.priority]?.bg || "bg-slate-200"
                        } ${ORDER_PRIORITIES[order.priority]?.text || "text-slate-700"}`}>
                          {ORDER_PRIORITIES[order.priority]?.label || order.priority}
                        </span>
                      </td>
                      <td className="p-3">
                        <select
                          value={order.status}
                          onChange={(e) => handleUpdateOrder(order.id, { status: e.target.value })}
                          className={`px-2 py-1 border rounded text-xs font-medium ${
                            order.status === "completed" ? "bg-emerald-100 border-emerald-300" :
                            order.status === "in_progress" ? "bg-amber-100 border-amber-300" :
                            "bg-white"
                          }`}
                        >
                          <option value="pending">Venter</option>
                          <option value="in_progress">I gang</option>
                          <option value="completed">Færdig</option>
                          <option value="cancelled">Annulleret</option>
                        </select>
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => setEditingOrder(order)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 rounded" title="Rediger">
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button onClick={() => handleDeleteOrder(order.id)}
                            className="p-1.5 text-red-600 hover:bg-orange-50 rounded" title="Slet">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {containerOrders.length === 0 && (
                    <tr>
                      <td colSpan="9" className="p-8 text-center text-slate-500">
                        <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        Ingen bestillinger endnu
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            
            {/* Order stats */}
            {containerOrders.length > 0 && (
              <div className="mt-4 flex gap-4 text-sm">
                <span className="px-3 py-1 bg-slate-100 rounded-full">
                  Total: <strong>{containerOrders.length}</strong>
                </span>
                <span className="px-3 py-1 bg-amber-100 text-amber-700 rounded-full">
                  Venter: <strong>{containerOrders.filter(o => o.status === "pending").length}</strong>
                </span>
                <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full">
                  I gang: <strong>{containerOrders.filter(o => o.status === "in_progress").length}</strong>
                </span>
                <span className="px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full">
                  Færdig: <strong>{containerOrders.filter(o => o.status === "completed").length}</strong>
                </span>
              </div>
            )}
          </div>
          
          {/* Edit Order Modal */}
          {editingOrder && (
            <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
              <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full p-6">
                <h3 className="font-bold text-lg mb-4">Rediger ordre</h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Prioritet</label>
                    <div className="flex gap-2">
                      {Object.entries(ORDER_PRIORITIES).map(([key, style]) => (
                        <button key={key}
                          onClick={() => setEditingOrder({...editingOrder, priority: key})}
                          className={`flex-1 py-2 px-3 rounded-lg font-medium text-sm ${
                            editingOrder.priority === key
                              ? `${style.bg} ${style.text}`
                              : "bg-slate-100 text-slate-600"
                          }`}>
                          {style.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Admin note (intern)</label>
                    <textarea
                      value={editingOrder.admin_note || ""}
                      onChange={(e) => setEditingOrder({...editingOrder, admin_note: e.target.value})}
                      className="w-full px-3 py-2 border rounded-lg h-24"
                      placeholder="Tilføj intern note..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Kundens kommentar</label>
                    <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
                      {editingOrder.comment || "Ingen kommentar"}
                    </p>
                  </div>
                </div>
                <div className="flex gap-3 mt-6">
                  <button onClick={() => setEditingOrder(null)}
                    className="flex-1 px-4 py-2 border rounded-lg hover:bg-slate-100">
                    Annuller
                  </button>
                  <button onClick={() => handleUpdateOrder(editingOrder.id, {
                    priority: editingOrder.priority,
                    admin_note: editingOrder.admin_note
                  })}
                    className="flex-1 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600">
                    Gem ændringer
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
        )}

        {/* Receipts tab merged into Archives (above) - legacy block kept as no-op for stability */}
        {false && activeTab === "receipts" && (
        <section className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm p-6 border border-border">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <FolderOpen className="w-5 h-5 text-amber-600" /> Chauffør Arkiv
            </h2>
          </div>
          <AdminReceiptList />
        </section>
        )}

        {activeTab === "priser" && (
          <EconomyPanel canEdit={can.economy_edit} />
        )}

        {activeTab === "settings" && can.settings && (
          <AdminSettingsPanel onSettingsChanged={(s) => setPayrollSettings(s)} />
        )}

        {activeTab === "team" && can.team && <TeamPanel />}
      </main>

      {adminAddressesFor && (
        <AdminPladsAddressesModal
          plads={adminAddressesFor}
          onClose={() => setAdminAddressesFor(null)}
        />
      )}

      {auditTour && (
        <TourAuditLogModal tour={auditTour} onClose={() => setAuditTour(null)} />
      )}

      {editTour && (
        <EditTourModal
          tour={editTour}
          onClose={() => setEditTour(null)}
          onSaved={(updated) => {
            setAdminTours(prev => prev.map(t => t.id === updated.id ? { ...t, ...updated } : t));
            setEditTour(null);
          }}
          onDeleted={(tourId) => {
            setAdminTours(prev => prev.filter(t => t.id !== tourId));
            setEditTour(null);
          }}
        />
      )}
    </div>
  );
};


// ============= TOUR AUDIT LOG TIMELINE MODAL =============
// Fase 6 (2026-06-17): Shows full assignment / claim / release history for a
// tour as an iMessage-style timeline. LA + SA only (server enforces).
const TourAuditLogModal = ({ tour, onClose }) => {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/tours/${tour.id}/audit-log`);
        if (!cancelled) setEntries(res.data || []);
      } catch (e) {
        if (!cancelled) setError(formatApiError(e));
      }
    })();
    return () => { cancelled = true; };
  }, [tour.id]);

  const actionMeta = (a) => ({
    assign:    { color: "bg-indigo-500",  icon: <Users className="w-3.5 h-3.5 text-white" />,    label: "Tildelt"   },
    reassign:  { color: "bg-amber-500",   icon: <RotateCcw className="w-3.5 h-3.5 text-white" />, label: "Om-tildelt" },
    release:   { color: "bg-slate-500",   icon: <X className="w-3.5 h-3.5 text-white" />,         label: "Frigivet"   },
    claim:     { color: "bg-emerald-500", icon: <CheckCircle2 className="w-3.5 h-3.5 text-white" />, label: "Taget"   },
    unclaim:   { color: "bg-orange-500",  icon: <RotateCcw className="w-3.5 h-3.5 text-white" />, label: "Frigjort"   },
  }[a] || { color: "bg-slate-400", icon: <History className="w-3.5 h-3.5 text-white" />, label: a });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose} data-testid="audit-log-modal">
      <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full max-h-[80vh] flex flex-col overflow-hidden shadow-2xl border border-slate-200 dark:border-slate-700" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-indigo-50 to-white dark:from-indigo-950/30 dark:to-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center">
              <History className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-heading font-bold text-base">Tildelings-historik</h3>
              <p className="text-xs text-muted-foreground">{tour.plads} · {tour.fraction || "-"}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg" data-testid="audit-log-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {entries === null && !error && (
            <div className="flex items-center justify-center py-12 text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Henter…
            </div>
          )}
          {error && (
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm rounded-lg p-3" data-testid="audit-log-error">
              {error}
            </div>
          )}
          {entries && entries.length === 0 && (
            <div className="text-center py-12 text-slate-400">
              <History className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Ingen tildelings-historik endnu.</p>
              <p className="text-xs mt-1">Når en logistik-admin tildeler, om-tildeler eller frigiver turen, logges det her.</p>
            </div>
          )}
          {entries && entries.length > 0 && (
            <ol className="relative ml-3 space-y-5 border-l-2 border-slate-200 dark:border-slate-700">
              {entries.map((entry, idx) => {
                const meta = actionMeta(entry.action);
                const when = entry.at ? new Date(entry.at) : null;
                const beforeName = entry.before?.driver_name || (entry.before?.driver_id ? entry.before.driver_id.substring(0,6) : "-");
                const afterName = entry.after?.driver_name || (entry.after?.driver_id ? entry.after.driver_id.substring(0,6) : "-");
                return (
                  <li key={entry.id || idx} className="ml-5" data-testid={`audit-entry-${idx}`}>
                    <span className={`absolute -left-[14px] ${meta.color} w-6 h-6 rounded-full flex items-center justify-center ring-4 ring-white dark:ring-slate-900`}>
                      {meta.icon}
                    </span>
                    <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full text-white ${meta.color}`}>{meta.label}</span>
                        {when && (
                          <span className="text-xs text-muted-foreground">
                            {when.toLocaleString("da-DK", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-700 dark:text-slate-200">
                        {entry.action === "assign" && <>Tildelt til <strong>{afterName}</strong></>}
                        {entry.action === "reassign" && <><strong>{beforeName}</strong> → <strong>{afterName}</strong></>}
                        {entry.action === "release" && <>Frigivet fra <strong>{beforeName}</strong> - åben for alle</>}
                        {!["assign", "reassign", "release"].includes(entry.action) && <span className="capitalize">{entry.action}</span>}
                      </p>
                      <p className="text-xs text-slate-500 mt-1.5">
                        af <strong>{entry.user_name || entry.user_email || "?"}</strong>
                        <span className="text-slate-400"> · {entry.user_role}</span>
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
};



// ============= PLANLÆGNING → TIDSREGISTRERING (Fase 15.3) =============
// Logistik admin's daglige overblik over alle chaufførers Ind/Ud + Manuel-
// stempler. Inspireret af SAP SuccessFactors Time Tracking: hver chauffør
// får én række med en visuel timeline (0-24h), markerede intervaller for
// hver stempling, plus en total-tid pr. dag.
// ============= PLANNING RESOURCES VIEW (Fase 15.16) =============
// Estimat-bestillinger (tour_type="estimat") vises her som et samlet
// ressource-overblik for planlæggeren. Adskilt fra konkrete opgaver.
// Filtre: dato (default = i dag), kunde (default = Alle), lokation
// (default = Alle). Tabellen viser én række pr. estimat med
// descriptive kolonner.
const PlanningResourcesView = () => {
  const [loading, setLoading] = useState(true);
  const [estimates, setEstimates] = useState([]);
  // Local date helper (timezone-safe)
  const localDateStr = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  // Default = i dag (lokal DK-dato)
  const [dateFilter, setDateFilter] = useState(() => localDateStr());
  const [customerFilter, setCustomerFilter] = useState("__all__");
  const [pladsFilter, setPladsFilter] = useState("__all__");

  const fetchEstimates = useCallback(async () => {
    setLoading(true);
    try {
      // Fase 15.49 (2026-02-22): "Planlæg ressourcer" viser KUN estimater.
      // Løs afhentning blev fjernet herfra pr. bruger-ønske - den skal
      // optræde som en almindelig tur i "Planlæg" (lige som normale
      // afhentninger), så logistik-admin kan tildele chauffør, prioritet
      // og tidspunkt direkte i den eksisterende tour-planning-flow.
      const r1 = await axios.get(`${API}/tours?tour_type=estimat&limit=500`).catch(() => ({ data: [] }));
      const arr = Array.isArray(r1.data) ? r1.data : (r1.data?.tours || []);
      arr.sort((a, b) => (a.order_date || "").localeCompare(b.order_date || ""));
      setEstimates(arr);
    } catch (_) {
      setEstimates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchEstimates(); }, [fetchEstimates]);

  const fmtDate = (s) => {
    if (!s) return "-";
    try {
      return new Date(s + "T00:00:00").toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    } catch { return s; }
  };

  // Filtre-options udledt af de hentede estimater
  const customerOptions = React.useMemo(() => {
    const s = new Set();
    estimates.forEach(e => { if (e.customer_name) s.add(e.customer_name); });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [estimates]);
  const pladsOptions = React.useMemo(() => {
    const s = new Set();
    estimates.forEach(e => { if (e.plads) s.add(e.plads); });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [estimates]);

  // Filtrér ud fra valgte kriterier
  const filtered = estimates.filter(e => {
    if (dateFilter && (e.order_date || "") !== dateFilter) return false;
    if (customerFilter !== "__all__" && (e.customer_name || "") !== customerFilter) return false;
    if (pladsFilter !== "__all__" && (e.plads || "") !== pladsFilter) return false;
    return true;
  });
  // Total = ESTIMAT bruger `estimated_count`; LØS AFHENTNING bruger
  // `loose_estimated_count` (de er to separate felter pga. Fase 15.41).
  const totalContainers = filtered.reduce((s, e) => {
    const c = (e.tour_type === "loes_afhentning")
      ? Number(e.loose_estimated_count || 0)
      : Number(e.estimated_count || 0);
    return s + c;
  }, 0);

  // Hurtig-knapper: I dag / I morgen / Alle datoer
  const setDateToday = () => setDateFilter(localDateStr());
  const setDateTomorrow = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    setDateFilter(localDateStr(d));
  };
  const clearDate = () => setDateFilter("");

  const cellBase = "px-3 py-2 text-sm align-middle";
  const headerBase = "px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 text-left whitespace-nowrap";

  return (
    <section className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700" data-testid="planning-resources-view">
      <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-amber-500" />
          <h3 className="font-bold text-base">Estimat-bestillinger (forventet ressourcebehov)</h3>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-500">
            <span className="font-bold text-slate-800 dark:text-slate-200" data-testid="planning-resources-count">{filtered.length}</span> estimater
          </span>
          <span className="text-slate-500">
            Total: <span className="font-bold text-amber-600" data-testid="planning-resources-total-containers">{totalContainers}</span> container(e)
          </span>
          <button
            onClick={fetchEstimates}
            className="px-2 py-1 rounded border border-slate-200 dark:border-slate-700 text-xs hover:bg-slate-100 dark:hover:bg-slate-700"
            data-testid="planning-resources-refresh"
          >
            Genindlæs
          </button>
        </div>
      </div>

      {/* Filtre */}
      <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 flex items-end gap-3 flex-wrap">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Dato</label>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={setDateToday}
              className={`px-2 py-1 rounded text-xs font-bold border ${dateFilter === localDateStr() ? "bg-amber-500 text-white border-amber-500" : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-100"}`}
              data-testid="planning-resources-date-today"
            >I dag</button>
            <button
              type="button"
              onClick={setDateTomorrow}
              className={`px-2 py-1 rounded text-xs font-bold border ${dateFilter === (() => { const d = new Date(); d.setDate(d.getDate() + 1); return localDateStr(d); })() ? "bg-amber-500 text-white border-amber-500" : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-100"}`}
              data-testid="planning-resources-date-tomorrow"
            >I morgen</button>
            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-xs"
              data-testid="planning-resources-date-input"
            />
            <button
              type="button"
              onClick={clearDate}
              className={`px-2 py-1 rounded text-xs font-bold border ${dateFilter === "" ? "bg-slate-600 text-white border-slate-600" : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-100"}`}
              data-testid="planning-resources-date-all"
            >Alle datoer</button>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Kunde</label>
          <select
            value={customerFilter}
            onChange={(e) => setCustomerFilter(e.target.value)}
            className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-xs min-w-[160px]"
            data-testid="planning-resources-customer-filter"
          >
            <option value="__all__">Alle kunder</option>
            {customerOptions.map(c => (<option key={c} value={c}>{c}</option>))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Lokation</label>
          <select
            value={pladsFilter}
            onChange={(e) => setPladsFilter(e.target.value)}
            className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-xs min-w-[160px]"
            data-testid="planning-resources-plads-filter"
          >
            <option value="__all__">Alle lokationer</option>
            {pladsOptions.map(p => (<option key={p} value={p}>{p}</option>))}
          </select>
        </div>
        {(customerFilter !== "__all__" || pladsFilter !== "__all__" || dateFilter) && (
          <button
            type="button"
            onClick={() => { setCustomerFilter("__all__"); setPladsFilter("__all__"); setDateFilter(""); }}
            className="px-2 py-1 rounded text-xs font-bold border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 hover:bg-slate-100"
            data-testid="planning-resources-clear-filters"
          >
            Nulstil filtre
          </button>
        )}
      </div>

      {/* Tabel */}
      {loading ? (
        <p className="text-sm text-slate-500 italic text-center py-8">Henter estimater...</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-slate-500 italic text-center py-8" data-testid="planning-resources-empty">
          {estimates.length === 0
            ? <>Ingen estimat-bestillinger endnu. Genbrugsplads-medarbejdere kan oprette estimater via "Tilpasset bestilling" → type "Estimat".</>
            : <>Ingen estimater matcher de valgte filtre.</>
          }
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="planning-resources-table">
            <thead className="bg-slate-50 dark:bg-slate-900/40 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className={headerBase}>Bestillingsdato</th>
                <th className={headerBase}>Type</th>
                <th className={headerBase}>Materiale</th>
                <th className={`${headerBase} text-right`}>Antal</th>
                <th className={headerBase}>Lokation</th>
                <th className={headerBase}>Kunde</th>
                <th className={headerBase}>Bestilt af</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {filtered.map(it => {
                const isLoes = it.tour_type === "loes_afhentning";
                const count = isLoes ? Number(it.loose_estimated_count || 0) : Number(it.estimated_count || 0);
                return (
                <tr key={it.id} className="hover:bg-amber-50/40 dark:hover:bg-amber-950/10" data-testid={`planning-resources-row-${it.id}`}>
                  <td className={`${cellBase} whitespace-nowrap`}>{fmtDate(it.order_date)}</td>
                  <td className={`${cellBase} whitespace-nowrap`}>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        isLoes
                          ? "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300"
                          : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                      }`}
                      data-testid={`planning-resources-type-${it.id}`}
                    >
                      {isLoes ? "Løs afhentning" : "Estimat"}
                    </span>
                  </td>
                  <td className={`${cellBase} font-bold`}>{it.fraction || it.material || "-"}</td>
                  <td className={`${cellBase} text-right font-black text-amber-600 dark:text-amber-300 text-base`} data-testid={`planning-resources-count-${it.id}`}>
                    ×{count}
                  </td>
                  {/* Fase 15.41: container_id/-nummer vises IKKE for løs
                      afhentning - kunden ejer ikke containerne. */}
                  <td className={`${cellBase} truncate max-w-[200px]`} title={it.plads}>{it.plads || "-"}</td>
                  <td className={`${cellBase} truncate max-w-[180px]`} title={it.customer_name}>{it.customer_name || "-"}</td>
                  <td className={`${cellBase} text-xs text-slate-500 truncate max-w-[180px]`} title={it.created_by_name || it.created_by_email}>
                    {it.created_by_name || it.created_by_email || "-"}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};



const PlanningTimeOverview = ({ reportDate, drivers = [] }) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  // Fase 15.28 (2026-02-22): Admin-modaler til at oprette manuel
  // tidsregistrering på vegne af en chauffør.
  const [showPunchModal, setShowPunchModal] = useState(false);
  const [showPeriodModal, setShowPeriodModal] = useState(false);
  // Fase 15.28: Læs reason-krav fra firmaets indstillinger så admin-modal'en
  // viser den korrekte påkrævet/valgfri-state.
  const [requireAdminReason, setRequireAdminReason] = useState(false);
  // Liste-visning af entries med Manuel-badge - toggle
  const [showFlatList, setShowFlatList] = useState(false);
  // Fase 15.31 (2026-02-22): Toggle for at vise slettede entries. Default
  // FALSE - slettede skjules. Toggle ON for at se "alle registreringer"
  // (alive + soft-deleted) i Detaljeret liste-visning.
  const [showDeleted, setShowDeleted] = useState(false);
  // Fase 15.32 (2026-02-22): Chauffør-filter - filtrerer både timeline og
  // detaljeret liste. Tom = vis alle. CSV-download honorerer dette filter.
  const [filterDriverId, setFilterDriverId] = useState("");
  // Fase 15.32: Edit/Slet pr. række. editAdminEntry sættes når admin klikker
  // "Rediger" - åbner AdminEditEntryModal. pendingAdminDeleteId styrer
  // to-trins slet-bekræftelse.
  const [editAdminEntry, setEditAdminEntry] = useState(null);
  const [pendingAdminDeleteId, setPendingAdminDeleteId] = useState(null);
  // Fase 15.35 (2026-02-22): Filter på "Mangler stempel" - uoplukkede
  // entries fra historiske dage. Toggle påvirker både timeline og
  // detaljeret liste.
  const [showOnlyMissing, setShowOnlyMissing] = useState(false);
  // Fase 15.36 (2026-02-22): Manuel trigger til søndags-påmindelses-mailen.
  const [sendingReminders, setSendingReminders] = useState(false);

  const sendMissingClockReminders = async () => {
    if (sendingReminders) return;
    if (!window.confirm(
      "Send påmindelses-mail til alle chauffører i firmaet der har åbne stemplinger i de seneste 7 dage?\n\n" +
      "(Cron-jobbet sender selv automatisk hver søndag kl. 18:00 - denne knap er kun til at sende ekstra.)"
    )) {
      return;
    }
    setSendingReminders(true);
    try {
      const r = await axios.post(`${API}/admin/missing-clock/send-reminders?days_back=7`);
      const sent = r.data?.sent || 0;
      const skipped = r.data?.skipped || 0;
      const total = (r.data?.drivers || []).length;
      if (total === 0) {
        toast.success("Ingen chauffører har åbne stemplinger i de seneste 7 dage. Alt er i orden! ✓");
      } else if (sent === total) {
        toast.success(`Påmindelse sendt til ${sent} ${sent === 1 ? 'chauffør' : 'chauffører'} ✓`);
      } else {
        toast.warning(`Sendt: ${sent} • Sprunget over: ${skipped} (se backend-log for detaljer)`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke sende påmindelser");
    } finally {
      setSendingReminders(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ date: reportDate });
        if (showDeleted) params.set("include_deleted", "true");
        // Fase 15.37 (2026-02-22): "Mangler stempel"-filtrering sker nu
        // client-side i Detaljeret liste - vi sender IKKE `missing_only` til
        // API'et længere, så driveren altid vises i timeline og badge'en
        // "X mangler" bliver synlig for adminen.
        const r = await axios.get(`${API}/admin/time-entries?${params.toString()}`);
        if (!cancelled) setData(r.data || []);
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || "Kunne ikke hente tidsregistrering");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    // Auto-refresh hvert 30 sek så åbne Ind-stempler ticker live
    const iv = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [reportDate, refreshTick, showDeleted]);

  // Fase 15.28: Fetch reason-krav (samme endpoint som chaufføren bruger)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/company/punch-reason-settings`);
        if (!cancelled) setRequireAdminReason(!!r.data?.require_admin_punch_reason);
      } catch (_) { /* defaults stay false */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fase 15.32 (2026-02-22): Hoistet HOUR_START / HOUR_END til toppen af
  // komponenten så de er tilgængelige fra alle helpers (CSV-download,
  // nowMinFromStart-beregning osv.). Tidligere stod de længere nede og
  // gav TDZ-ReferenceError under render.
  const HOUR_START = 6;
  const HOUR_END   = 22;
  const totalSpan  = (HOUR_END - HOUR_START) * 60; // minutes
  const minutesFromStart = (hhmm) => {
    if (!hhmm) return 0;
    const [h, m] = hhmm.split(":").map(Number);
    return (h - HOUR_START) * 60 + (m || 0);
  };
  const clamp = (n) => Math.max(0, Math.min(totalSpan, n));

  const totalWorked   = data.reduce((s, d) => s + (d.work_minutes ?? d.total_minutes ?? 0), 0);
  const totalPause    = data.reduce((s, d) => s + (d.pause_minutes ?? 0), 0);
  const totalPresent  = data.reduce((s, d) => s + (d.total_minutes || 0), 0);
  const activeNow     = data.filter(d => d.has_open).length;
  const completedDay  = data.filter(d => d.entries_count > 0 && !d.has_open).length;
  const onLeave       = data.filter(d => d.entries_count === 0).length;
  const fmtHM = (m) => `${Math.floor((m || 0) / 60)}t ${String((m || 0) % 60).padStart(2, "0")}m`;
  // Fase 15.32 (2026-02-22): Anvend chauffør-filter på dataet - bruges af
  // både timeline og detaljeret liste samt CSV-download.
  const displayData = filterDriverId
    ? data.filter(d => d.driver_id === filterDriverId)
    : data;
  // Fase 15.32 (2026-02-22): For dags-dato bruges current local time som cap
  // for åbne entries (så de IKKE fylder hele resten af dagen). For andre
  // dage falder vi tilbage til totalSpan (= end of view).
  const _todayStr = new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD
  const isReportToday = reportDate === _todayStr;
  const _nowDate = new Date();
  const nowMinFromStart = isReportToday
    ? Math.max(0, Math.min(((_nowDate.getHours() * 60 + _nowDate.getMinutes()) - HOUR_START * 60), HOUR_END * 60 - HOUR_START * 60))
    : (HOUR_END - HOUR_START) * 60;

  // Fase 15.32 (2026-02-22): CSV-download af detaljeret liste. Honorerer
  // chauffør-filter + showDeleted-state. Genererer en blob og trigger
  // browser-download. Felter: Chauffør, Dato, Start, Slut, Type, Manuel,
  // Årsag, Slettet.
  const downloadCsv = () => {
    const rows = [];
    rows.push(["Chauffør", "Dato", "Start", "Slut", "Varighed (min)", "Type", "Manuel", "Manuel-type", "Årsag", "Slettet", "Slettet af", "Oprettet af rolle", "Mangler stempel"]);
    displayData.forEach(d => {
      (d.entries || []).forEach(e => {
        rows.push([
          d.driver_name,
          e.date || reportDate,
          e.start_time || "",
          e.end_time || "",
          String(e.duration_minutes || 0),
          (e.slice_type || "work") === "pause" ? "Pause" : "Arbejde",
          e.manual ? "Ja" : "Nej",
          e.manual_type || "",
          (e.reason || "").replace(/[\r\n]+/g, " "),
          e.deleted ? "Ja" : "Nej",
          e.deleted_by_name || "",
          e.created_by_role || "",
          e.missing_clock ? "Ja" : "Nej",
        ]);
      });
    });
    const escape = (s) => {
      const v = String(s ?? "");
      if (v.includes(";") || v.includes('"') || v.includes("\n")) {
        return `"${v.replace(/"/g, '""')}"`;
      }
      return v;
    };
    // BOM + semikolon = Excel-DK-venligt
    const csv = "\uFEFF" + rows.map(r => r.map(escape).join(";")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    const driverPart = filterDriverId
      ? "_" + (drivers.find(x => x.id === filterDriverId)?.name || "chauffør").replace(/[^a-zA-Z0-9æøåÆØÅ]/g, "_")
      : "";
    a.href = url;
    a.download = `tidsregistrering_${reportDate}${driverPart}${showDeleted ? "_med-slettede" : ""}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success(`CSV downloadet - ${rows.length - 1} registreringer`);
  };

  // Compute time-axis: vis 06:00-22:00 som hovedinterval (16t) på timeline.
  // (Konstanterne er hoistet til toppen af komponenten - denne kommentar
  // står her for backwards-kontekst.)

  return (
    <section className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700" data-testid="planning-time-section">
      <header className="p-4 border-b border-slate-200 dark:border-slate-700 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-emerald-500" />
          <h3 className="font-bold text-base">Tidsregistrering - {reportDate}</h3>
        </div>
        <div className="flex items-center gap-2 ml-auto text-xs">
          <span className="px-2 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 font-bold">
            {activeNow} aktiv{activeNow === 1 ? "" : "e"} nu
          </span>
          <span className="px-2 py-1 rounded-full bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 font-bold">
            {completedDay} færdige
          </span>
          <span className="px-2 py-1 rounded-full bg-slate-50 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-bold">
            {onLeave} ikke aktive
          </span>
          <span className="px-2 py-1 rounded-full bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 font-bold" data-testid="planning-time-total-work">
            Arbejde {fmtHM(totalWorked)}
          </span>
          {totalPause > 0 && (
            <span className="px-2 py-1 rounded-full bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 font-bold" data-testid="planning-time-total-pause">
              Pause {fmtHM(totalPause)}
            </span>
          )}
          <span className="px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold" data-testid="planning-time-total-present">
            Tilstede {fmtHM(totalPresent)}
          </span>
          <button
            onClick={() => setRefreshTick(x => x + 1)}
            className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300"
            title="Genopfrisk"
            data-testid="planning-time-refresh"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Fase 15.28 (2026-02-22): Admin handlinger - opret manuel
          registrering på vegne af en chauffør. */}
      <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex flex-wrap items-center gap-2 bg-slate-50/60 dark:bg-slate-900/30">
        <button
          type="button"
          onClick={() => setShowPunchModal(true)}
          disabled={!drivers.length}
          className="px-3 py-2 rounded-lg text-xs font-bold bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          data-testid="planning-time-open-punch-btn"
          title="Opret enkelt manuel stempel (IND eller UD) på vegne af en chauffør"
        >
          <Plus className="w-3.5 h-3.5" /> Manuel stempel
        </button>
        <button
          type="button"
          onClick={() => setShowPeriodModal(true)}
          disabled={!drivers.length}
          className="px-3 py-2 rounded-lg text-xs font-bold bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          data-testid="planning-time-open-period-btn"
          title="Opret manuel periode (start + slut) på vegne af en chauffør"
        >
          <Plus className="w-3.5 h-3.5" /> Manuel periode
        </button>
        <button
          type="button"
          onClick={() => setShowFlatList(s => !s)}
          className={`px-3 py-2 rounded-lg text-xs font-bold border transition-colors flex items-center gap-1.5 ${
            showFlatList
              ? "bg-blue-500 text-white border-blue-500"
              : "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600"
          }`}
          data-testid="planning-time-toggle-list"
          title="Vis alle registreringer som liste med Manuel-badges + årsag"
        >
          {showFlatList ? <Check className="w-3.5 h-3.5" /> : <Edit2 className="w-3.5 h-3.5" />}
          Detaljeret liste
        </button>
        {/* Fase 15.37 (2026-02-22): "Vis slettede" og "Mangler stempel"-filtre
            er flyttet ned i "Alle registreringer"-tabellen så de virker som
            ægte tabel-filtre. Knap-renderet i flat-list-headeren nedenfor. */}
        {/* Fase 15.32 (2026-02-22): Chauffør-filter - påvirker både timeline,
            detaljeret liste OG CSV-download. */}
        <select
          value={filterDriverId}
          onChange={(e) => setFilterDriverId(e.target.value)}
          className="h-9 px-2 rounded-lg text-xs font-bold border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200"
          data-testid="planning-time-driver-filter"
          title="Filtrér på en specifik chauffør"
        >
          <option value="">Alle chauffører</option>
          {drivers.map(d => (
            <option key={d.id} value={d.id}>{d.name || d.email}</option>
          ))}
        </select>
        {/* Fase 15.32 (2026-02-22): CSV-download knap - honorerer
            chauffør-filter + showDeleted. */}
        <button
          type="button"
          onClick={downloadCsv}
          className="px-3 py-2 rounded-lg text-xs font-bold border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-950/50 flex items-center gap-1.5"
          data-testid="planning-time-csv-btn"
          title={filterDriverId ? "Download CSV for valgte chauffør" : "Download CSV for alle chauffører"}
        >
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
        {/* Fase 15.36 (2026-02-22): Manuel trigger til søndags-påmindelses-mailen.
            Sender mail til chauffører i firmaet der har åbne entries i de
            seneste 7 dage. Cron-jobbet sender selv hver søndag 18:00; denne
            knap er for at teste eller sende en ekstra påmindelse. */}
        <button
          type="button"
          onClick={sendMissingClockReminders}
          disabled={sendingReminders}
          className="px-3 py-2 rounded-lg text-xs font-bold border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-950/50 disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-1.5"
          data-testid="planning-time-send-reminders-btn"
          title="Send påmindelses-mail til alle chauffører med åbne stemplinger i de seneste 7 dage. Automatisk udsendelse sker hver søndag kl. 18:00."
        >
          {sendingReminders ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Mail className="w-3.5 h-3.5" />
          )}
          Send påmindelse
        </button>
        {!drivers.length && (
          <span className="text-[11px] text-slate-500 italic">
            Ingen chauffører i firmaet - opret en chauffør først.
          </span>
        )}
      </div>

      {loading && data.length === 0 ? (
        <div className="p-8 text-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
          Henter tidsregistreringer…
        </div>
      ) : error ? (
        <div className="p-6 text-red-600 dark:text-red-400 text-sm">{error}</div>
      ) : data.length === 0 ? (
        <div className="p-8 text-center text-muted-foreground">
          <Clock className="w-8 h-8 mx-auto mb-2 opacity-40" />
          Ingen chauffører oprettet endnu.
        </div>
      ) : (
        <div className="overflow-x-auto" data-testid="planning-time-list">
          {/* Time-axis legend */}
          <div className="px-4 pt-3 pb-1 grid grid-cols-[220px_1fr_140px] gap-3 text-[10px] text-slate-500 uppercase tracking-wider font-bold">
            <span>Chauffør</span>
            <div className="relative h-4">
              {Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => {
                const h = HOUR_START + i;
                const left = (i / (HOUR_END - HOUR_START)) * 100;
                return (
                  <span key={h}
                    className="absolute -translate-x-1/2"
                    style={{ left: `${left}%` }}>
                    {String(h).padStart(2, "0")}
                  </span>
                );
              })}
            </div>
            <span className="text-right">Total / Status</span>
          </div>
          {/* Rows */}
          <div className="divide-y divide-slate-100 dark:divide-slate-700">
            {displayData.map(d => (
              <div key={d.driver_id} className="px-4 py-3 grid grid-cols-[220px_1fr_140px] gap-3 items-center hover:bg-slate-50 dark:hover:bg-slate-700/30"
                data-testid={`planning-time-row-${d.driver_id}`}>
                {/* Driver name */}
                <div className="flex items-center gap-2 min-w-0">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold flex-shrink-0 ${
                    d.has_open ? "bg-emerald-500 text-white" :
                    d.entries_count > 0 ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300" :
                    "bg-slate-100 text-slate-400 dark:bg-slate-700"
                  }`}>
                    {(d.driver_name || "?").slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold truncate">{d.driver_name}</p>
                    <p className="text-[10px] text-slate-500">
                      {d.first_in ? `${d.first_in} → ${d.last_out || "..."}` : "ikke stemplet"}
                    </p>
                  </div>
                </div>
                {/* Timeline */}
                <div className="relative h-9 bg-slate-100 dark:bg-slate-900/40 rounded overflow-hidden">
                  {/* Hour grid */}
                  {Array.from({ length: HOUR_END - HOUR_START }, (_, i) => (
                    <div key={i} className="absolute top-0 bottom-0 border-l border-slate-200 dark:border-slate-800/60"
                      style={{ left: `${((i + 1) / (HOUR_END - HOUR_START)) * 100}%` }} />
                  ))}
                  {/* Entry bars */}
                  {(d.entries || []).filter(e => !e.deleted).map((e, idx) => {
                    const startMin = clamp(minutesFromStart(e.start_time));
                    // Fase 15.35 (2026-02-22): "Missing clock" - uoplukket
                    // entry fra historisk dato. Tegn IKKE en lang åben bar
                    // (det ville fejlagtigt antyde at chaufføren arbejdede
                    // hele dagen). Tegn i stedet en lille rød markør ved
                    // start-tiden + signaler at chaufføren glemte at lukke.
                    if (e.missing_clock) {
                      const leftPct = (startMin / totalSpan) * 100;
                      return (
                        <div key={e.id || idx}
                          className="absolute top-0 bottom-0 w-1 bg-red-500 rounded shadow-md animate-pulse"
                          style={{ left: `${leftPct}%` }}
                          title={`Mangler stempel: ${e.start_time} → ?  ${e.reason ? "· " + e.reason : ""}`}
                          data-testid={`time-bar-missing-${d.driver_id}-${idx}`}
                        />
                      );
                    }
                    // Fase 15.32 (2026-02-22): Åbne entries (no end_time)
                    // caps til current local time for dags-dato - så de
                    // IKKE fylder hele resten af dagen ud.
                    const endMin = e.end_time
                      ? clamp(minutesFromStart(e.end_time))
                      : Math.max(startMin + 1, clamp(nowMinFromStart));
                    const widthPct = ((endMin - startMin) / totalSpan) * 100;
                    const leftPct  = (startMin / totalSpan) * 100;
                    if (widthPct <= 0) return null;
                    const isOpen   = !e.end_time;
                    const isManual = !!e.manual;
                    const isPause  = (e.slice_type || "work") === "pause";
                    // Fase 15.30 (2026-02-22): Pause-slices har distinkt blå
                    // farve. Åbne pause-slices pulser blåt; lukkede er solidt blå.
                    let cls;
                    if (isPause) {
                      cls = isOpen
                        ? "bg-blue-400/80 border-2 border-blue-600 animate-pulse"
                        : (isManual
                            ? "bg-blue-300/80 border border-blue-500"
                            : "bg-blue-500/70 border border-blue-700");
                    } else {
                      cls = isOpen
                        ? "bg-emerald-400/80 border-2 border-emerald-600 animate-pulse"
                        : (isManual
                            ? "bg-cyan-400/80 border border-cyan-600"
                            : "bg-emerald-500/80 border border-emerald-700");
                    }
                    return (
                      <div key={e.id || idx}
                        className={`absolute top-1 bottom-1 rounded transition-shadow hover:shadow-md ${cls}`}
                        style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.5)}%` }}
                        title={`${isPause ? "Pause" : "Arbejde"}: ${e.start_time} → ${e.end_time || "åben"}${isManual ? " (manuel)" : ""}${e.reason ? " · " + e.reason : ""}`}
                        data-testid={`time-bar-${d.driver_id}-${idx}`}
                      />
                    );
                  })}
                </div>
                {/* Total */}
                <div className="text-right">
                  <p className="text-sm font-bold font-mono text-emerald-700 dark:text-emerald-300">
                    {fmtHM(d.work_minutes ?? d.total_minutes ?? 0)}
                  </p>
                  {(d.pause_minutes ?? 0) > 0 && (
                    <p className="text-[10px] font-mono text-blue-600 dark:text-blue-300" data-testid={`row-pause-${d.driver_id}`}>
                      + {fmtHM(d.pause_minutes)} pause
                    </p>
                  )}
                  {d.has_open && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 rounded font-bold">
                      Aktiv nu
                    </span>
                  )}
                  {/* Fase 15.35 (2026-02-22): Antallet af manglende stempler */}
                  {(d.missing_clock_count ?? 0) > 0 && (
                    <span className="ml-1 text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300 rounded font-bold animate-pulse flex items-center gap-1 inline-flex"
                      data-testid={`row-missing-clock-${d.driver_id}`}
                      title="Chauffør har glemt at stemple ud på et historisk tidspunkt">
                      <AlertTriangle className="w-3 h-3" />
                      {d.missing_clock_count} mangler
                    </span>
                  )}
                  {!d.has_open && d.entries_count > 0 && (
                    <span className="text-[10px] text-slate-500">{d.entries_count} stempling{d.entries_count === 1 ? "" : "er"}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
          {/* Legend */}
          <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-700 flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-emerald-500/80 border border-emerald-700 rounded"/> Arbejde</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-emerald-400/80 border-2 border-emerald-600 rounded animate-pulse"/> Åben arbejde (nu)</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-blue-500/70 border border-blue-700 rounded"/> Pause</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-blue-400/80 border-2 border-blue-600 rounded animate-pulse"/> Åben pause (nu)</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-cyan-400/80 border border-cyan-600 rounded"/> Manuel registrering</span>
          </div>
        </div>
      )}

      {/* Fase 15.28 (2026-02-22): Detaljeret liste med Manuel-badge + årsag.
          Vises kun når brugeren slår "Detaljeret liste" til. */}
      {showFlatList && data.length > 0 && (
        <div className="border-t border-slate-200 dark:border-slate-700" data-testid="planning-time-flat-list">
          <div className="px-4 py-2 bg-slate-50 dark:bg-slate-900/40 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between flex-wrap gap-2">
            <p className="text-[11px] uppercase tracking-wider font-bold text-slate-500">
              Alle registreringer - {reportDate}
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {/* Fase 15.37 (2026-02-22): "Vis slettede"-filter - flyttet hertil
                  fra topværktøjslinjen. Filtrerer KUN rækkerne i Alle
                  registreringer (timeline viser aldrig slettede). */}
              <button
                type="button"
                onClick={() => setShowDeleted(s => !s)}
                className={`px-3 py-1.5 rounded-md text-[11px] font-bold border transition-colors flex items-center gap-1.5 ${
                  showDeleted
                    ? "bg-red-500 text-white border-red-500"
                    : "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
                data-testid="planning-time-toggle-deleted"
                title="Inkluder slettede registreringer i listen"
              >
                <Trash2 className="w-3 h-3" />
                {showDeleted ? "Skjul slettede" : "Vis slettede"}
              </button>
              {/* Fase 15.37 (2026-02-22): "Mangler stempel"-filtrering - flyttet
                  hertil fra topværktøjslinjen. Filtrerer KUN rækkerne i Alle
                  registreringer client-side (påvirker ikke timeline). */}
              <button
                type="button"
                onClick={() => setShowOnlyMissing(s => !s)}
                className={`px-3 py-1.5 rounded-md text-[11px] font-bold border transition-colors flex items-center gap-1.5 ${
                  showOnlyMissing
                    ? "bg-orange-500 text-white border-orange-500"
                    : "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
                data-testid="planning-time-toggle-missing"
                title="Vis kun rækker der mangler UD-stempel (åbne IND fra historiske datoer)"
              >
                <AlertTriangle className="w-3 h-3" />
                {showOnlyMissing ? "Vis alle rækker" : "Mangler stempel"}
              </button>
            </div>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700">
            {(() => {
              const rows = displayData.flatMap(d =>
                (d.entries || []).map((e, idx) => ({ ...e, _driver: d.driver_name, _did: d.driver_id, _idx: idx }))
              );
              const filteredRows = showOnlyMissing ? rows.filter(e => !!e.missing_clock) : rows;
              if (filteredRows.length === 0) {
                return (
                  <div
                    className="px-4 py-6 text-center text-sm text-slate-500 italic"
                    data-testid="flat-list-empty-state"
                  >
                    {showOnlyMissing
                      ? "Ingen rækker mangler UD-stempel i visningen. ✓"
                      : "Ingen registreringer på denne dato."}
                  </div>
                );
              }
              return filteredRows.map((e, i) => {
              const isManual = !!e.manual;
              const manualType = e.manual_type || "";
              const reason = e.reason || "";
              const udReason = e.ud_reason || "";
              const isPause = (e.slice_type || "work") === "pause";
              const isDeleted = !!e.deleted;
              return (
                <div key={`${e._did}-${e._idx}-${i}`}
                  className={`px-4 py-2.5 flex flex-wrap items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-700/30 ${
                    isDeleted ? "bg-red-50/30 dark:bg-red-950/10 opacity-60 line-through" : ""
                  }`}
                  data-testid={`flat-entry-${e._did}-${e._idx}`}
                  data-deleted={isDeleted ? "true" : "false"}>
                  <span className="text-sm font-bold text-slate-800 dark:text-slate-100 min-w-[140px] truncate">
                    {e._driver}
                  </span>
                  <span className="font-mono text-sm">
                    {e.start_time || "-"} <span className="text-slate-400">→</span> {e.end_time || <em className="text-emerald-600">åben</em>}
                  </span>
                  {/* Fase 15.30 (2026-02-22): Slice-type badge */}
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 ${
                    isPause
                      ? "bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800"
                      : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800"
                  }`} data-testid={`flat-entry-slice-${e._did}-${e._idx}`}>
                    {isPause ? <Pause className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
                    {isPause ? "Pause" : "Arbejde"}
                  </span>
                  {/* Fase 15.35 (2026-02-22): "Mangler stempel"-status-badge.
                      Vises hvis entry er åben fra en fortidig dato. */}
                  {e.missing_clock && (
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-800 flex items-center gap-1 animate-pulse"
                      data-testid={`flat-entry-missing-${e._did}-${e._idx}`}
                      title="Uoplukket IND-stempling fra historisk dato - chaufføren har glemt at stemple ud"
                    >
                      <AlertTriangle className="w-2.5 h-2.5" /> Mangler stempel
                    </span>
                  )}
                  {/* Fase 15.31 (2026-02-22): "Slettet"-badge med slet-info */}
                  {isDeleted && (
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-800 flex items-center gap-1 no-underline"
                      data-testid={`flat-entry-deleted-${e._did}-${e._idx}`}
                      title={`Slettet${e.deleted_at ? " " + new Date(e.deleted_at).toLocaleString("da-DK") : ""}${e.deleted_by_name ? " af " + e.deleted_by_name : ""}${e.deleted_by_role ? " (" + e.deleted_by_role + ")" : ""}`}
                    >
                      <Trash2 className="w-2.5 h-2.5" /> Slettet
                      {e.deleted_by_role === "driver" ? " · chauffør" : e.deleted_by_role ? " · admin" : ""}
                    </span>
                  )}
                  {isManual && (
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800 flex items-center gap-1"
                      data-testid={`flat-entry-manual-${e._did}-${e._idx}`}
                      title={manualType === "period" ? "Periode oprettet manuelt af admin" : `Stempel ${manualType.replace("punch_", "")}`}
                    >
                      <Edit2 className="w-2.5 h-2.5" /> Manuel
                      {manualType === "punch_ind" && <span className="opacity-80">· IND</span>}
                      {manualType === "punch_ud" && <span className="opacity-80">· UD</span>}
                      {manualType === "period" && <span className="opacity-80">· Periode</span>}
                    </span>
                  )}
                  {reason && (
                    <span className="text-[11px] text-slate-600 dark:text-slate-300 italic"
                      data-testid={`flat-entry-reason-${e._did}-${e._idx}`}
                      title={reason}>
                      &ldquo;{reason.length > 80 ? reason.slice(0, 80) + "…" : reason}&rdquo;
                    </span>
                  )}
                  {udReason && udReason !== reason && (
                    <span className="text-[11px] text-orange-600 dark:text-orange-400 italic"
                      title={`UD-årsag: ${udReason}`}>
                      UD: &ldquo;{udReason.length > 60 ? udReason.slice(0, 60) + "…" : udReason}&rdquo;
                    </span>
                  )}
                  <span className="ml-auto text-xs text-slate-500 font-mono">
                    {Math.floor((e.duration_minutes || 0) / 60)}t {String((e.duration_minutes || 0) % 60).padStart(2, "0")}m
                  </span>
                  {/* Fase 15.32 (2026-02-22): Edit + Slet pr. række.
                      Slettede entries vises uden actions (de er allerede slettet). */}
                  {!isDeleted && (
                    <div className="flex items-center gap-1 ml-2" data-testid={`flat-entry-actions-${e._did}-${e._idx}`}>
                      <button
                        onClick={() => setEditAdminEntry(e)}
                        className="p-1.5 rounded-md border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950/30"
                        data-testid={`flat-entry-edit-${e._did}-${e._idx}`}
                        title="Rediger registrering"
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                      {pendingAdminDeleteId === e.id ? (
                        <>
                          <button
                            onClick={async () => {
                              try {
                                await axios.delete(`${API}/admin/time-entries/${e.id}`);
                                toast.success("Registrering slettet");
                                setPendingAdminDeleteId(null);
                                setRefreshTick(x => x + 1);
                              } catch (err) {
                                toast.error(err?.response?.data?.detail || "Kunne ikke slette");
                                setPendingAdminDeleteId(null);
                              }
                            }}
                            className="px-2 py-1 rounded-md text-[10px] font-bold bg-red-500 text-white hover:bg-red-600 animate-pulse"
                            data-testid={`flat-entry-delete-confirm-${e._did}-${e._idx}`}
                          >Bekræft</button>
                          <button
                            onClick={() => setPendingAdminDeleteId(null)}
                            className="px-2 py-1 rounded-md text-[10px] font-bold border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300"
                            data-testid={`flat-entry-delete-cancel-${e._did}-${e._idx}`}
                          >Annullér</button>
                        </>
                      ) : (
                        <button
                          onClick={() => setPendingAdminDeleteId(e.id)}
                          className="p-1.5 rounded-md border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/30"
                          data-testid={`flat-entry-delete-${e._did}-${e._idx}`}
                          title="Slet registrering (soft)"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            });
            })()}
          </div>
        </div>
      )}

      {/* Fase 15.28: Admin-modaler - opret manuel registrering for chauffør */}
      <ManualPunchModal
        open={showPunchModal}
        defaultDate={reportDate}
        mode="admin"
        drivers={drivers}
        requireReason={requireAdminReason}
        onClose={() => setShowPunchModal(false)}
        onSave={async (data) => {
          await axios.post(`${API}/driver/time-entries/manual-punch`, data);
          setRefreshTick(x => x + 1);
        }}
      />
      <ManualTimeEntryModal
        open={showPeriodModal}
        defaultDate={reportDate}
        mode="admin"
        drivers={drivers}
        requireReason={requireAdminReason}
        onClose={() => setShowPeriodModal(false)}
        onSave={async (data) => {
          await axios.post(`${API}/driver/time-entries`, data);
          setRefreshTick(x => x + 1);
        }}
      />

      {/* Fase 15.32 (2026-02-22): Admin-edit modal - admin kan opdatere
          enhver entry (start/slut/dato/type/reason). PATCH /admin/time-entries/{id}. */}
      <AdminEditEntryModal
        open={!!editAdminEntry}
        entry={editAdminEntry}
        onClose={() => setEditAdminEntry(null)}
        onSaved={() => { setRefreshTick(x => x + 1); }}
      />
    </section>
  );
};

// Fase 15.32 (2026-02-22): Admin-edit-modal for tidsregistrering.
const AdminEditEntryModal = ({ open, entry, onClose, onSaved }) => {
  const [date, setDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [sliceType, setSliceType] = useState("work");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (open && entry) {
      setDate(entry.date || "");
      setStartTime(entry.start_time || "");
      setEndTime(entry.end_time || "");
      setSliceType((entry.slice_type || "work").toLowerCase());
      setReason(entry.reason || "");
      setErr("");
    }
  }, [open, entry]);

  if (!open || !entry) return null;

  // Fase 15.35 (2026-02-22): Strikt regel - slut skal være efter start.
  const startEndInvalid = (() => {
    if (!startTime || !endTime) return false;
    const [sh, sm] = startTime.split(":").map(Number);
    const [eh, em] = endTime.split(":").map(Number);
    if ([sh, sm, eh, em].some(n => isNaN(n))) return false;
    return (eh * 60 + em) <= (sh * 60 + sm);
  })();
  const canSave = date && startTime && !startEndInvalid;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const payload = {
        date,
        start_time: startTime,
        end_time: endTime || "",
        slice_type: sliceType,
        reason: reason || "",
      };
      await axios.patch(`${API}/admin/time-entries/${entry.id}`, payload);
      toast.success("Registrering opdateret");
      onSaved?.();
      onClose();
    } catch (e) {
      const msg = e?.response?.data?.detail || "Kunne ikke gemme";
      setErr(msg); toast.error(msg);
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" data-testid="admin-edit-entry-modal">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Edit2 className="w-4 h-4 text-blue-500" />
            <h3 className="font-bold text-sm">Rediger registrering ({entry.driver_name || ""})</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Dato</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm"
              data-testid="admin-edit-entry-date" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Start</label>
              <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm font-mono"
                data-testid="admin-edit-entry-start" />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Slut (valgfri)</label>
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm font-mono"
                data-testid="admin-edit-entry-end" />
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Type</label>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => setSliceType("work")}
                className={`h-10 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 ${sliceType === "work" ? "bg-emerald-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="admin-edit-entry-slice-work">
                <Clock className="w-3.5 h-3.5" /> Arbejde
              </button>
              <button type="button" onClick={() => setSliceType("pause")}
                className={`h-10 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 ${sliceType === "pause" ? "bg-blue-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"}`}
                data-testid="admin-edit-entry-slice-pause">
                <Pause className="w-3.5 h-3.5" /> Pause
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Årsag (valgfri)</label>
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              className="w-full h-11 px-3 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm"
              data-testid="admin-edit-entry-reason" />
          </div>
          {err && <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-300 text-xs">{err}</div>}
          {/* Fase 15.35 (2026-02-22): Strikt regel - slut skal være efter start */}
          {startEndInvalid && (
            <p className="text-[11px] text-red-600 dark:text-red-400 font-semibold flex items-center gap-1" data-testid="admin-edit-entry-startend-error">
              <X className="w-3 h-3" /> Sluttidspunkt skal være efter starttidspunkt.
            </p>
          )}
        </div>
        <div className="p-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-2">
          <button onClick={onClose} className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
          <button onClick={submit} disabled={saving || !canSave}
            className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 flex items-center justify-center gap-2"
            data-testid="admin-edit-entry-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Gem ændringer
          </button>
        </div>
      </div>
    </div>
  );
};


// ============= EDIT TOUR MODAL (ADMIN) =============
// Fase 14 (2026-06-19): Logistik-admin kan via denne modal genåbne en
// afsluttet tur, ændre opgavetype, korrigere vægt eller slette en
// fejlbestilt tur - alt fra ét vindue. Brugt fra "Ture i {plads}"-tabellen.
const EditTourModal = ({ tour, onClose, onSaved, onDeleted }) => {
  const [tourType, setTourType] = useState(tour.tour_type || "normal");
  const [weight, setWeight]     = useState(tour.weight != null ? String(tour.weight) : "");
  const [reopen, setReopen]     = useState(false);
  const [saving, setSaving]     = useState(false);

  const isNormal      = tourType === "normal";
  const isCompleted   = !!tour.completed;
  const claimedBy     = tour.claimed_by || "";

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      if (tourType !== (tour.tour_type || "normal")) payload.tour_type = tourType;
      if (isNormal) {
        const w = parseFloat(weight);
        if (!isNaN(w) && w !== (tour.weight || 0)) payload.weight = w;
      }
      if (reopen && isCompleted) {
        payload.completed = false;
        payload.on_way    = false;
        payload.time      = "";
        // Frigør claim så turen igen er åben for chauffører at tage.
        payload.claimed_by    = "";
        payload.claimed_by_id = "";
        payload.claimed_at    = "";
      } else if (claimedBy) {
        // Send claim med for at omgå backend's restricted_fields-guard når
        // vi rører weight/completed på en allerede taget tur.
        payload.claimed_by = claimedBy;
      }
      if (Object.keys(payload).length === 0) {
        toast.info("Ingen ændringer at gemme");
        setSaving(false);
        return;
      }
      const res = await axios.put(`${API}/tours/${tour.id}`, payload);
      toast.success(reopen ? "Tur genåbnet" : "Tur opdateret");
      onSaved?.(res.data || { id: tour.id, ...payload });
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Slet turen "${tour.fraction || ""}"? Dette kan ikke fortrydes.`)) return;
    setSaving(true);
    try {
      await axios.delete(`${API}/tours/${tour.id}`);
      toast.success("Tur slettet");
      onDeleted?.(tour.id);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose} data-testid="edit-tour-modal">
      <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl border border-slate-200 dark:border-slate-700" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-blue-50 to-white dark:from-blue-950/30 dark:to-slate-900">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center flex-shrink-0">
              <Edit2 className="w-5 h-5 text-white" />
            </div>
            <div className="min-w-0">
              <h3 className="font-heading font-bold text-base">Ret tur</h3>
              <p className="text-xs text-muted-foreground truncate">{tour.plads || "-"} · {tour.fraction || "-"}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg" data-testid="edit-tour-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Status banner */}
          <div className={`rounded-lg p-3 text-xs flex items-center gap-2 ${
            isCompleted ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300"
            : tour.on_way ? "bg-yellow-50 dark:bg-yellow-950/30 text-yellow-700 dark:text-yellow-300"
            : "bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
          }`}>
            {isCompleted ? <CheckCircle2 className="w-4 h-4" /> : tour.on_way ? <Truck className="w-4 h-4" /> : <Calendar className="w-4 h-4" />}
            <span className="font-semibold">
              {isCompleted ? "Status: Afsluttet" : tour.on_way ? "Status: På vej" : claimedBy ? "Status: Taget" : "Status: Venter"}
            </span>
            {claimedBy && <span className="text-slate-500">af {claimedBy}</span>}
          </div>

          {/* Opgavetype */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wide text-slate-500 mb-1.5">Opgavetype</label>
            <select
              value={tourType}
              onChange={(e) => setTourType(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-medium focus:ring-2 focus:ring-blue-500 outline-none"
              data-testid="edit-tour-type"
            >
              {Object.entries(TOUR_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>

          {/* Vægt (kun for normal) */}
          {isNormal && (
            <div>
              <label className="block text-xs font-bold uppercase tracking-wide text-slate-500 mb-1.5">Vægt (kg)</label>
              <input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                placeholder="F.eks. 1240"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                data-testid="edit-tour-weight"
              />
            </div>
          )}

          {/* Genåben checkbox (kun hvis afsluttet) */}
          {isCompleted && (
            <label className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 cursor-pointer hover:bg-amber-100/60 dark:hover:bg-amber-950/30">
              <input
                type="checkbox"
                checked={reopen}
                onChange={(e) => setReopen(e.target.checked)}
                className="mt-0.5 w-4 h-4 accent-amber-500"
                data-testid="edit-tour-reopen"
              />
              <div>
                <div className="font-bold text-sm text-amber-900 dark:text-amber-200 flex items-center gap-1.5">
                  <RotateCcw className="w-3.5 h-3.5" /> Genåben tur
                </div>
                <p className="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
                  Sætter turen tilbage til "Venter". Chauffører kan tage den igen.
                </p>
              </div>
            </label>
          )}

          {/* Info om at fejlbestilte ture kan slettes */}
          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
            Var turen fejlbestilt? Du kan slette den her - handlingen kan ikke fortrydes.
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 px-5 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40">
          <button
            onClick={handleDelete}
            disabled={saving}
            className="px-3 py-2 rounded-lg text-sm font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center gap-1.5 disabled:opacity-50"
            data-testid="edit-tour-delete"
          >
            <Trash2 className="w-4 h-4" /> Slet tur
          </button>
          <div className="flex-1" />
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50"
            data-testid="edit-tour-cancel"
          >
            Annullér
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 flex items-center gap-1.5 disabled:opacity-50"
            data-testid="edit-tour-save"
          >
            <CheckCircle2 className="w-4 h-4" /> {saving ? "Gemmer…" : "Gem"}
          </button>
        </div>
      </div>
    </div>
  );
};


// ============= ADMIN INDSTILLINGER PANEL (Lønperiode m.m.) =============
// Fase 15.14 (2026-02-XX): Konfigurerbar lønperiode-startdag pr.
// logistik-firma. Eksisterende default = 20.
// Fase 15.15 (2026-02-XX): Udvidet med 3 cyklus-typer: monthly, biweekly, weekly.
const AdminSettingsPanel = ({ onSettingsChanged }) => {
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [cycleType, setCycleType]   = useState("monthly");
  const [startDay, setStartDay]     = useState(20);
  const [anchorDate, setAnchorDate] = useState("");
  const [errMsg, setErrMsg]         = useState("");
  // Fase 15.28 (2026-02-22): Krav om "Årsag" ved manuel stempel
  const [requireDriverReason, setRequireDriverReason] = useState(false);
  const [requireAdminReason,  setRequireAdminReason]  = useState(false);
  const [savingReason, setSavingReason] = useState(false);

  const load = async () => {
    setLoading(true); setErrMsg("");
    try {
      const r = await axios.get(`${API}/company/payroll-settings`);
      setCompanyName(r.data?.company_name || "");
      setCycleType(r.data?.payroll_cycle_type || "monthly");
      setStartDay(Number(r.data?.payroll_start_day) || 20);
      setAnchorDate(r.data?.payroll_anchor_date || "");
      setRequireDriverReason(!!r.data?.require_driver_punch_reason);
      setRequireAdminReason(!!r.data?.require_admin_punch_reason);
    } catch (e) {
      setErrMsg(e?.response?.data?.detail || "Kunne ikke hente indstillinger");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  // Fase 15.28: Gem reason-krav alene (uden at røre cycle-felterne)
  const saveReasonSettings = async (next) => {
    setSavingReason(true); setErrMsg("");
    try {
      const r = await axios.patch(`${API}/company/payroll-settings`, next);
      setRequireDriverReason(!!r.data?.require_driver_punch_reason);
      setRequireAdminReason(!!r.data?.require_admin_punch_reason);
      toast.success("Krav om årsag opdateret");
    } catch (e) {
      const msg = e?.response?.data?.detail || "Kunne ikke gemme";
      setErrMsg(msg);
      toast.error(msg);
    } finally {
      setSavingReason(false);
    }
  };
  const toggleDriverReason = () => {
    const v = !requireDriverReason;
    setRequireDriverReason(v);
    saveReasonSettings({ require_driver_punch_reason: v });
  };
  const toggleAdminReason = () => {
    const v = !requireAdminReason;
    setRequireAdminReason(v);
    saveReasonSettings({ require_admin_punch_reason: v });
  };

  // Hjælpere til preview-tekst
  const fmtDayMonth = (d) => d.toLocaleDateString("da-DK", { day: "numeric", month: "short" });
  const fmtWeekday = (d) => d.toLocaleDateString("da-DK", { weekday: "long" });
  const previewText = (() => {
    if (cycleType === "monthly") {
      const endDay = startDay <= 1 ? 28 : startDay - 1;
      return `Månedlig periode: fra dag ${startDay} til dag ${endDay} i den efterfølgende måned.`;
    }
    if (!anchorDate) return "Vælg en ankerdato.";
    const d = new Date(anchorDate + "T00:00:00");
    if (isNaN(d.getTime())) return "Ugyldig ankerdato.";
    const days = cycleType === "weekly" ? 7 : 14;
    const end = new Date(d);
    end.setDate(d.getDate() + days - 1);
    const wd = fmtWeekday(d);
    const endWd = fmtWeekday(end);
    const cycleLabel = cycleType === "weekly" ? "ugentlig (7 dage)" : "14-dages (2 uger)";
    return `${cycleLabel} periode: ${fmtDayMonth(d)} (${wd}) → ${fmtDayMonth(end)} (${endWd}). Nye perioder cykler herfra.`;
  })();

  const save = async () => {
    setSaving(true); setErrMsg("");
    try {
      const payload = {
        payroll_cycle_type: cycleType,
        payroll_start_day: Number(startDay),
        payroll_anchor_date: cycleType === "monthly" ? "" : anchorDate,
      };
      const r = await axios.patch(`${API}/company/payroll-settings`, payload);
      setCycleType(r.data?.payroll_cycle_type || "monthly");
      setStartDay(Number(r.data?.payroll_start_day) || 20);
      setAnchorDate(r.data?.payroll_anchor_date || "");
      toast.success("Lønperiode opdateret");
      // Notify parent (AdminApp) so Arkiv-fanen straks bruger ny værdi
      if (typeof onSettingsChanged === "function") {
        onSettingsChanged({
          payroll_cycle_type: r.data?.payroll_cycle_type || "monthly",
          payroll_start_day: Number(r.data?.payroll_start_day) || 20,
          payroll_anchor_date: r.data?.payroll_anchor_date || "",
        });
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || "Kunne ikke gemme";
      setErrMsg(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6" data-testid="admin-settings-panel">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
          <Settings className="w-5 h-5 text-red-600" />
          <h2 className="text-lg font-black">Lønperiode-indstillinger</h2>
        </div>
        <div className="p-6 space-y-5">
          {loading ? (
            <p className="text-slate-500 text-sm italic">Henter indstillinger...</p>
          ) : (
            <>
              <div>
                <p className="text-xs uppercase tracking-wider text-slate-500 font-bold">Logistik-firma</p>
                <p className="text-base font-black text-slate-900 dark:text-slate-100" data-testid="settings-company-name">
                  {companyName || "-"}
                </p>
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wider text-slate-500 font-bold mb-2">
                  Lønperiode-cyklus
                </label>
                <div className="flex flex-wrap gap-2">
                  {[
                    { id: "monthly",  label: "Månedlig" },
                    { id: "biweekly", label: "14-dages" },
                    { id: "weekly",   label: "Ugentlig" },
                  ].map(opt => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setCycleType(opt.id)}
                      data-testid={`settings-cycle-${opt.id}`}
                      className={`px-4 py-2 rounded-lg text-sm font-bold border transition-colors ${
                        cycleType === opt.id
                          ? "bg-red-500 text-white border-red-500"
                          : "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              {cycleType === "monthly" ? (
                <div>
                  <label className="block text-xs uppercase tracking-wider text-slate-500 font-bold mb-2">
                    Startdag i måneden
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={28}
                    value={startDay}
                    onChange={(e) => setStartDay(Math.max(1, Math.min(28, Number(e.target.value) || 1)))}
                    className="w-24 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 font-bold text-lg focus:outline-none focus:ring-2 focus:ring-red-400"
                    data-testid="settings-payroll-input"
                  />
                  <p className="mt-2 text-xs text-slate-500 italic">Gyldigt: 1–28.</p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs uppercase tracking-wider text-slate-500 font-bold mb-2">
                    Ankerdato (startdato på første periode)
                  </label>
                  <input
                    type="date"
                    value={anchorDate || ""}
                    onChange={(e) => setAnchorDate(e.target.value)}
                    className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 font-bold focus:outline-none focus:ring-2 focus:ring-red-400"
                    data-testid="settings-anchor-input"
                  />
                  <p className="mt-2 text-xs text-slate-500 italic">
                    Cykler beregnes dynamisk fra denne dato - ugedagen overføres til alle fremtidige perioder.
                  </p>
                </div>
              )}
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-200" data-testid="settings-preview">
                <span className="font-bold">Forhåndsvisning:</span> {previewText}
              </div>
              {errMsg && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm" data-testid="settings-error">
                  {errMsg}
                </div>
              )}
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={save}
                  disabled={saving || (cycleType !== "monthly" && !anchorDate)}
                  className="px-4 py-2 rounded-lg bg-red-500 text-white font-bold text-sm hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  data-testid="settings-payroll-save"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  Gem
                </button>
                <button
                  type="button"
                  onClick={load}
                  disabled={saving}
                  className="px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                  data-testid="settings-payroll-reset"
                >
                  Fortryd
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Fase 15.28 (2026-02-22): Krav om årsag ved manuel stempel.
          Gælder både chauffører og admin. Toggles auto-gemmer. */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700" data-testid="settings-punch-reason-card">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
          <Clock className="w-5 h-5 text-amber-500" />
          <div>
            <h2 className="text-lg font-black">Manuel stempel - krav om årsag</h2>
            <p className="text-xs text-slate-500 mt-0.5">Gælder både chauffører og admin-oprettede manuelle registreringer.</p>
          </div>
        </div>
        <div className="p-6 space-y-4">
          {loading ? (
            <p className="text-slate-500 text-sm italic">Henter indstillinger...</p>
          ) : (
            <>
              {/* Driver toggle */}
              <div className="flex items-start justify-between gap-4 p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/40">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-slate-800 dark:text-slate-100">Krav om årsag for chauffører</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Når chaufføren bruger "Manuel" stempling, skal feltet "Årsag" udfyldes før der kan gemmes.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={toggleDriverReason}
                  disabled={savingReason}
                  data-testid="settings-require-driver-reason-toggle"
                  aria-pressed={requireDriverReason}
                  className={`relative w-12 h-7 rounded-full transition-colors flex-shrink-0 ${
                    requireDriverReason ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"
                  } disabled:opacity-50`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                      requireDriverReason ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
              {/* Admin toggle */}
              <div className="flex items-start justify-between gap-4 p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/40">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-slate-800 dark:text-slate-100">Krav om årsag for admin</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Når logistik-admin opretter en manuel registrering på vegne af en chauffør, skal "Årsag" udfyldes.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={toggleAdminReason}
                  disabled={savingReason}
                  data-testid="settings-require-admin-reason-toggle"
                  aria-pressed={requireAdminReason}
                  className={`relative w-12 h-7 rounded-full transition-colors flex-shrink-0 ${
                    requireAdminReason ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"
                  } disabled:opacity-50`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                      requireAdminReason ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
              {savingReason && (
                <p className="text-xs text-slate-500 italic flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Gemmer...
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};


// ============= RECEIPT SCANNER =============
const ReceiptScanner = ({ onSave, onClose, driverName, plads }) => {
  const videoContainerRef = useRef(null);
  const videoElRef        = useRef(null);
  const canvasRef         = useRef(null);
  const streamRef         = useRef(null);

  const [step, setStep]                 = useState("camera"); // camera | preview | ocr | confirm
  const [capturedImage, setCapturedImage] = useState(null);
  const [ocrLoading, setOcrLoading]     = useState(false);
  const [ocrResult, setOcrResult]       = useState(null);
  const [amount, setAmount]             = useState("");
  const [description, setDescription]  = useState("");

  useEffect(() => {
    const video = document.createElement("video");
    video.autoplay = true; video.playsInline = true; video.muted = true;
    video.setAttribute("playsinline", "");
    video.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;";
    videoElRef.current = video;
    if (videoContainerRef.current) videoContainerRef.current.appendChild(video);
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }
    }).then(s => { streamRef.current = s; if (videoElRef.current) videoElRef.current.srcObject = s; })
      .catch(() => toast.error("Kan ikke åbne kamera"));
    return () => {
      if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
      if (videoElRef.current) videoElRef.current.srcObject = null;
    };
  }, []);

  const stopCamera = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (videoElRef.current) videoElRef.current.srcObject = null;
  };

  const capturePhoto = () => {
    const video = videoElRef.current; const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);
    const img = canvas.toDataURL("image/jpeg", 0.9);
    setCapturedImage(img);
    stopCamera();
    setStep("preview");
  };

  const runOCR = async () => {
    if (!capturedImage) return;
    setStep("ocr"); setOcrLoading(true);
    try {
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("dan+eng");
      const { data: { text } } = await worker.recognize(capturedImage);
      await worker.terminate();

      // Extract amount/beløb
      const amountPatterns = [
        /(?:total|beløb|kr\.?|dkk)[:\s]*([\d][\d.,]*)/i,
        /([\d][\d.,]*)\s*(?:kr\.?|dkk)/i,
        /([\d]{2,6}(?:[.,]\d{2})?)/,
      ];
      let foundAmount = null;
      for (const pat of amountPatterns) {
        const m = text.match(pat);
        if (m) { const v = parseFloat(m[1].replace(",",".")); if (v > 0) { foundAmount = v; break; } }
      }

      setOcrResult({ amount: foundAmount, text: text.slice(0, 400) });
      if (foundAmount) setAmount(String(foundAmount));
      setStep("confirm");
    } catch (e) {
      setOcrResult({ amount: null, text: "" });
      setStep("confirm");
    } finally { setOcrLoading(false); }
  };

  const retake = () => {
    setCapturedImage(null); setOcrResult(null); setAmount(""); setStep("camera");
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }
    }).then(s => { streamRef.current = s; if (videoElRef.current) videoElRef.current.srcObject = s; }).catch(() => {});
  };

  const handleSave = () => {
    if (!capturedImage) { toast.error("Tag et foto først"); return; }
    onSave({ image: capturedImage, amount: parseFloat(amount) || 0, description, driver: driverName, plads });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black z-[100] flex flex-col" data-testid="receipt-scanner" style={{ height: "100dvh" }}>
      <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between flex-shrink-0">
        <button onClick={() => { stopCamera(); onClose(); }} className="p-2 rounded-lg hover:bg-slate-700">
          <X className="w-5 h-5" />
        </button>
        <h2 className="font-bold text-sm flex items-center gap-2">
          <ScanLine className="w-4 h-4 text-red-400" />
          {step === "camera" && "Scan kvittering"}
          {step === "preview" && "Kontroller foto"}
          {step === "ocr" && "Læser..."}
          {step === "confirm" && "Gem kvittering"}
        </h2>
        <div className="w-9" />
      </div>

      {/* CAMERA */}
      {step === "camera" && (
        <div className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
          <div ref={videoContainerRef} className="flex-1 relative bg-black overflow-hidden">
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
              <div style={{ width:"85%", height:"55%", border:"2px solid rgba(255,255,255,0.6)", borderRadius:12, boxShadow:"0 0 0 9999px rgba(0,0,0,0.4)" }}>
                <div style={{ position:"absolute", top:8, left:8, width:22, height:22, borderTop:"3px solid #EF4444", borderLeft:"3px solid #EF4444", borderRadius:"4px 0 0 0" }} />
                <div style={{ position:"absolute", top:8, right:8, width:22, height:22, borderTop:"3px solid #EF4444", borderRight:"3px solid #EF4444", borderRadius:"0 4px 0 0" }} />
                <div style={{ position:"absolute", bottom:8, left:8, width:22, height:22, borderBottom:"3px solid #EF4444", borderLeft:"3px solid #EF4444", borderRadius:"0 0 0 4px" }} />
                <div style={{ position:"absolute", bottom:8, right:8, width:22, height:22, borderBottom:"3px solid #EF4444", borderRight:"3px solid #EF4444", borderRadius:"0 0 4px 0" }} />
              </div>
            </div>
            <p className="absolute bottom-4 left-0 right-0 text-center text-white/60 text-xs z-10">Hold kvitteringen inden for rammen</p>
          </div>
          <div className="bg-black px-6 py-5 flex justify-center flex-shrink-0">
            <button onClick={capturePhoto} className="w-20 h-20 rounded-full bg-white flex items-center justify-center shadow-2xl active:scale-95 transition-transform">
              <Camera className="w-9 h-9 text-slate-800" />
            </button>
          </div>
        </div>
      )}

      {/* PREVIEW */}
      {step === "preview" && capturedImage && (
        <div className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
          <div className="flex-1 flex items-center justify-center bg-gray-900 overflow-hidden">
            <img src={capturedImage} alt="Kvittering" className="max-w-full max-h-full object-contain" />
          </div>
          <div className="bg-black px-4 py-4 flex gap-3 flex-shrink-0">
            <button onClick={retake} className="flex-1 py-3.5 bg-slate-700 text-white rounded-xl font-bold">Tag om</button>
            <button onClick={runOCR} className="flex-1 py-3.5 bg-red-600 text-white rounded-xl font-bold flex items-center justify-center gap-2">
              <ScanLine className="w-5 h-5" /> Læs tekst
            </button>
          </div>
        </div>
      )}

      {/* OCR LOADING */}
      {step === "ocr" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-5 bg-slate-900">
          <div className="w-14 h-14 border-4 border-red-500 border-t-transparent rounded-full animate-spin" />
          <div className="text-center">
            <p className="text-white font-bold">Læser kvittering...</p>
            <p className="text-slate-400 text-sm mt-1">Finder beløb og data</p>
          </div>
        </div>
      )}

      {/* CONFIRM */}
      {step === "confirm" && (
        <div className="flex-1 flex flex-col bg-slate-900 px-4 py-4 gap-4" style={{ minHeight: 0, overflowY: "auto" }}>
          {capturedImage && (
            <img src={capturedImage} alt="Kvittering" className="w-full h-32 object-cover rounded-xl border-2 border-slate-600" />
          )}

          {ocrResult?.amount ? (
            <div className="bg-emerald-900/40 border border-emerald-600 rounded-xl p-3">
              <p className="text-emerald-400 text-xs font-bold uppercase">✓ Beløb fundet automatisk</p>
              <p className="text-white text-2xl font-mono font-bold mt-1">{ocrResult.amount} kr.</p>
            </div>
          ) : (
            <div className="bg-amber-900/30 border border-amber-600 rounded-xl p-3">
              <p className="text-amber-400 text-xs font-bold">Beløb ikke fundet - indtast manuelt</p>
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-1.5">Beløb (kr.)</label>
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)}
              placeholder="0.00" inputMode="decimal"
              className="w-full px-4 py-3 text-xl font-mono text-center border-2 border-slate-600 bg-slate-800 text-white rounded-xl focus:border-red-500 outline-none" />
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-1.5">Beskrivelse (valgfri)</label>
            <input type="text" value={description} onChange={e => setDescription(e.target.value)}
              placeholder="F.eks. Diesel, Bro, Parkering..."
              className="w-full px-4 py-3 border-2 border-slate-600 bg-slate-800 text-white rounded-xl focus:border-red-500 outline-none text-sm" />
          </div>

          {ocrResult?.text && (
            <details className="bg-slate-800 rounded-xl p-3">
              <summary className="text-xs text-slate-400 cursor-pointer font-semibold">Læst tekst</summary>
              <pre className="text-[10px] text-slate-500 mt-2 whitespace-pre-wrap font-mono leading-relaxed max-h-24 overflow-y-auto">{ocrResult.text}</pre>
            </details>
          )}

          <div className="flex gap-3 mt-auto">
            <button onClick={retake} className="flex-1 py-3.5 bg-slate-700 text-white rounded-xl font-bold">Tag om</button>
            <button onClick={handleSave} className="flex-1 py-3.5 bg-red-600 text-white rounded-xl font-bold flex items-center justify-center gap-2">
              <CheckCircle2 className="w-5 h-5" /> Gem
            </button>
          </div>
        </div>
      )}
      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
};


// Receipt List Component (driver view - no photos, admin only sees photos)
const ReceiptList = ({ receipts, onDelete }) => {
  if (!receipts || receipts.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Camera className="w-12 h-12 mx-auto mb-2 opacity-30" />
        <p>Ingen kvitteringer endnu</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {receipts.map((r) => (
        <div key={r.id} className="bg-white dark:bg-slate-800 rounded-xl p-3 border border-slate-200 dark:border-slate-700 flex items-center gap-3" data-testid={`receipt-${r.id}`}>
          <div className="w-10 h-10 bg-emerald-100 dark:bg-emerald-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm">{r.description || "Kvittering"}</span>
              {r.amount > 0 && (
                <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-xs font-bold rounded-full">{r.amount} kr</span>
              )}
            </div>
            <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
              <span>{r.driver_name}</span>
              <span>{r.date}</span>
              {r.plads && <span className="text-blue-500">{r.plads}</span>}
              <span className="text-emerald-500 font-medium">Sendt til admin</span>
            </div>
          </div>
          <button onClick={() => onDelete(r.id)} className="p-2 text-red-400 hover:bg-orange-50 dark:hover:bg-red-950 rounded-lg flex-shrink-0">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
};

// Receipt Viewer (fullscreen)
const ReceiptViewer = ({ receipt, onClose }) => {
  if (!receipt) return null;
  return (
    <div className="fixed inset-0 bg-black/95 z-50 flex flex-col" data-testid="receipt-viewer">
      <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between">
        <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg">
          <X className="w-5 h-5" />
        </button>
        <div className="text-center">
          <p className="font-bold">{receipt.description || "Kvittering"}</p>
          <p className="text-xs text-slate-400">{receipt.driver_name} - {receipt.date} {receipt.amount > 0 ? `- ${receipt.amount} kr` : ""}</p>
        </div>
        <div className="w-9" />
      </div>
      <div className="flex-1 flex items-center justify-center p-4">
        <img src={receipt.image_data} alt="Kvittering" className="max-w-full max-h-full object-contain rounded-lg" />
      </div>
    </div>
  );
};


// ============= MAIN APP =============

// ============= MOBILE TOUR PANEL =============
// Bottom-sheet modal shown when a driver taps a tour card. Displays tour
// details and exposes the main per-tour actions (On Way / Complete / Delete /
// Chat). All action callbacks come from the parent App component.
// 2026-10-16: Afregning på turen (PRICING_SPEC.md). Chaufføren ser HVORDAN
// turen afregnes - aldrig faste priser, tillæg eller totaler. Mens turen
// kører vælger han Med/Uden hænger; efter turen kan han anmode om rettelse
// af tider, hænger og ventetid, som logistik admin skal godkende.
const TourBillingBox = ({ tour }) => {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    if (!tour?.id) return;
    try {
      const { data } = await axios.get(`${API}/driver/tour-pricing`, { params: { ids: tour.id } });
      setInfo(data[tour.id] || null);
    } catch (_) { setInfo(null); }
  }, [tour?.id]);
  useEffect(() => { load(); }, [load, tour?.completed, tour?.on_way, tour?.used_trailer, tour?.trailer_confirmed]);
  if (!info) return null;

  const trailer = info.used_trailer === true;
  const setTrailer = async (v) => {
    try {
      await axios.put(`${API}/driver/tours/${tour.id}/trailer`, { used_trailer: v });
      setInfo(i => ({ ...i, used_trailer: v }));
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const submit = async () => {
    if (!form.comment.trim()) { toast.error("Skriv hvad der skal rettes og hvorfor"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/driver/tours/${tour.id}/change-request`, {
        start_time: form.start_time, end_time: form.end_time, trailer_count: Number(form.trailer_count),
        waiting_min: form.waiting_min === "" ? undefined : Number(form.waiting_min), comment: form.comment,
      });
      toast.success("Sendt til godkendelse hos din logistik admin");
      setForm(null); load();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };
  const modelText = info.model === "hourly"
    ? `Timepris · ${Number(info.hourly_rate || 0).toLocaleString("da-DK")} kr/t · ${info.deduct_pause ? "pause trækkes fra" : "pause tæller med"}${info.rounding && info.rounding !== "Ingen afrunding" ? ` · ${info.rounding.toLowerCase()}` : ""}`
    : info.model === "per_container" ? "Afregnes pr. container"
    : info.model === "fixed" ? "Fast pris pr. tur" : null;
  const last = info.last_request;

  return (
    <div className="mx-4 mb-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-3 space-y-2.5" data-testid="tour-billing-box">
      {modelText && (
        <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
          <Clock className="w-3.5 h-3.5 shrink-0" /> <span><b>Afregning:</b> {modelText}</span>
        </div>
      )}
      {tour.on_way && !tour.completed && !(Object.keys(tour.capture || {}).length && tour.tour_type !== "loes_afhentning") && (
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Bruger du hænger på denne tur?<span className="block font-normal text-[11px] text-slate-500">Bruges til afregningen (hængertillæg).</span></span>
          <div className="inline-flex p-0.5 rounded-lg bg-slate-200 dark:bg-slate-900" data-testid="tour-trailer-toggle">
            {[[false, "Uden"], [true, "Med hænger"]].map(([v, l]) => (
              <button key={l} type="button" onClick={() => setTrailer(v)}
                className={`px-3 py-1.5 rounded-md text-xs font-bold ${trailer === v ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500"}`}>{l}</button>
            ))}
          </div>
        </div>
      )}
      {tour.completed && (
        <>
          {last && (
            <div className={`text-xs px-2.5 py-1.5 rounded-lg ${last.status === "pending" ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200" : last.status === "approved" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200" : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200"}`}>
              {last.status === "pending" ? "Din rettelse venter på godkendelse" : last.status === "approved" ? "Din rettelse er godkendt" : `Din rettelse blev afvist${last.decision_note ? `: ${last.decision_note}` : ""}`}
            </div>
          )}
          {!form && !info.invoiced && (
            <button type="button" onClick={() => setForm({ start_time: tour.on_way_time || "", end_time: tour.time || "", trailer_count: String(info.trailer_count ?? (trailer ? 1 : 0)), waiting_min: "", comment: "" })}
              className="w-full px-3 py-2 rounded-lg text-sm font-semibold bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex items-center justify-center gap-2" data-testid="tour-change-request-btn">
              <Edit2 className="w-4 h-4" /> Ret tid, hænger eller ventetid (godkendes)
            </button>
          )}
          {form && (
            <div className="space-y-2" data-testid="tour-change-request-form">
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[11px] font-bold uppercase text-slate-500">På vej
                  <input type="time" value={form.start_time} onChange={e => setForm({ ...form, start_time: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 text-sm" /></label>
                <label className="text-[11px] font-bold uppercase text-slate-500">Afsluttet
                  <input type="time" value={form.end_time} onChange={e => setForm({ ...form, end_time: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 text-sm" /></label>
                <label className="text-[11px] font-bold uppercase text-slate-500">Ventetid (min)
                  <input type="number" min="0" inputMode="numeric" value={form.waiting_min} onChange={e => setForm({ ...form, waiting_min: e.target.value })} placeholder="0" className="mt-1 w-full px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 text-sm" /></label>
                <label className="text-[11px] font-bold uppercase text-slate-500">Hængere
                  <select value={form.trailer_count} onChange={e => setForm({ ...form, trailer_count: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 text-sm" data-testid="change-request-trailers">
                    {[0, 1, 2, 3, 4].map(n => <option key={n} value={String(n)}>{n === 0 ? "Uden hænger" : `${n} hænger${n === 1 ? "" : "e"}`}</option>)}
                  </select></label>
              </div>
              <textarea rows={2} value={form.comment} onChange={e => setForm({ ...form, comment: e.target.value })} placeholder="Hvad skal rettes og hvorfor?" className="w-full px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 text-sm" />
              <div className="flex gap-2">
                <button type="button" onClick={() => setForm(null)} className="flex-1 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-200 dark:bg-slate-700">Annuller</button>
                <button type="button" disabled={busy} onClick={submit} className="flex-1 px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white disabled:opacity-50">Send til godkendelse</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const MobileTourPanel = ({ tour, onClose, onUpdate, onDelete, onToggleOnWay, onToggleComplete, currentDriverName, onChat, onRefresh, onOpenFinish, unifiedFinish = false, deviationCodes = [] }) => {
  const [weightInput, setWeightInput] = useState("");
  const [trailerAsk, setTrailerAsk] = useState(null);
  const [trailerChoice, setTrailerChoice] = useState(null); // P5: valgt i vægtarket (null = forslaget)
  const [notCompletedCode, setNotCompletedCode] = useState("");
  const [trailerAnswered, setTrailerAnswered] = useState(false);
  useEffect(() => { setTrailerAnswered(false); setTrailerChoice(null); }, [tour?.id]);
  const [askingWeight, setAskingWeight] = useState(false);
  // Fase 15.52 (2026-02-22): "Kan ikke gennemføres"-dialog state.
  const [showNotCompletedDialog, setShowNotCompletedDialog] = useState(false);
  const [notCompletedReason, setNotCompletedReason] = useState("");
  const [submittingNotCompleted, setSubmittingNotCompleted] = useState(false);
  // Fase 15.41 (2026-02-22): Multi-vægt for "Løs afhentning"-ture. Listen
  // starter med ét tomt felt. Driver kan tilføje flere via "+ Tilføj
  // container". Mindst én vægt > 0 er påkrævet for at afslutte.
  const [containerWeights, setContainerWeights] = useState([""]);
  // Fase 14 (2026-06-19): Chaufføren skal kunne RETTE vægten på en afsluttet
  // tur uden at genåbne den - fx hvis kvitteringen blev fejllæst eller
  // tastet forkert. Egen state holder kun det nye input mens redigeringen
  // er åben.
  const [editingWeight, setEditingWeight] = useState(false);
  const [editWeightVal, setEditWeightVal] = useState("");
  // Fase 16 (OCR receipt scanner) - controls the in-app scanner modal. Each
  // scan saves its receipt to the backend immediately (skip_tour_update=true)
  // so the receipt is in the OCR archive even before the driver completes the
  // tour. The tour weight itself is set separately via the existing weight
  // popup flow.
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerTarget, setScannerTarget] = useState({ mode: "normal", rowIdx: -1 });
  // Fase 17.3 (2026-02-27): Persisterer vedhæftede billeder i sessionStorage
  // PER TUR. iOS Safari kan reload'e siden når kameraet overtager - uden
  // persistence ville scan-state forsvinde og chaufføren måtte starte
  // forfra. Vi loader pending-state ved mount (hvis tour.id er sat).
  const storageKeyNormal = tour?.id ? `pendingReceipt:${tour.id}:normal` : null;
  const storageKeyLoose = tour?.id ? `pendingReceipt:${tour.id}:loose` : null;
  const [pendingReceiptImage, setPendingReceiptImage] = useState(() => {
    try {
      if (!storageKeyNormal) return null;
      const raw = sessionStorage.getItem(storageKeyNormal);
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  });
  const [pendingLooseReceipts, setPendingLooseReceipts] = useState(() => {
    try {
      if (!storageKeyLoose) return {};
      const raw = sessionStorage.getItem(storageKeyLoose);
      return raw ? JSON.parse(raw) : {};
    } catch (_) { return {}; }
  });

  // Fase 18.7 (2026-02-28): Allerede-uploadede kvitteringer for denne tur
  // (server-side). Vises ved siden af hver vægt-række så chaufføren tydeligt
  // ser hvilke kvitteringer der er gemt. For løs afhentning matches via
  // chronologisk rækkefølge (created_at) - første receipt -> container #1 osv.
  const [uploadedReceipts, setUploadedReceipts] = useState([]);
  const [viewerReceiptId, setViewerReceiptId] = useState(null);
  const fetchUploadedReceipts = useCallback(async () => {
    if (!tour?.id) { setUploadedReceipts([]); return; }
    try {
      const { data } = await axios.get(`${API}/receipts?tour_id=${tour.id}&limit=200`);
      setUploadedReceipts(Array.isArray(data) ? data : []);
    } catch (_) { setUploadedReceipts([]); }
  }, [tour?.id]);
  useEffect(() => { fetchUploadedReceipts(); }, [fetchUploadedReceipts]);

  // Synkronisér pending-state til sessionStorage ved enhver ændring så
  // iOS Safari reloads ikke koster chaufføren et scan.
  useEffect(() => {
    if (!storageKeyNormal) return;
    try {
      if (pendingReceiptImage) {
        sessionStorage.setItem(storageKeyNormal, JSON.stringify(pendingReceiptImage));
      } else {
        sessionStorage.removeItem(storageKeyNormal);
      }
    } catch (_) { /* quota exceeded - billede for stort, ignorér */ }
  }, [pendingReceiptImage, storageKeyNormal]);

  useEffect(() => {
    if (!storageKeyLoose) return;
    try {
      if (pendingLooseReceipts && Object.keys(pendingLooseReceipts).length > 0) {
        sessionStorage.setItem(storageKeyLoose, JSON.stringify(pendingLooseReceipts));
      } else {
        sessionStorage.removeItem(storageKeyLoose);
      }
    } catch (_) { /* quota exceeded - ignorér */ }
  }, [pendingLooseReceipts, storageKeyLoose]);

  // Fase 17.6 (2026-02-27): Restore-hook. useState-initializer kører kun
  // ÉN gang ved mount - hvis tour.id endnu ikke var sat ville pending
  // image være null permanent selvom sessionStorage havde data. Denne
  // useEffect løser det ved at restore'e så snart tour.id er tilgængelig.
  useEffect(() => {
    if (!storageKeyNormal) return;
    try {
      const raw = sessionStorage.getItem(storageKeyNormal);
      if (raw) {
        const parsed = JSON.parse(raw);
        setPendingReceiptImage(parsed);
        // Åbn vægt-prompt automatisk så chaufføren ser thumbnail med det samme.
        setAskingWeight(true);
      }
    } catch (_) { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKeyNormal]);

  useEffect(() => {
    if (!storageKeyLoose) return;
    try {
      const raw = sessionStorage.getItem(storageKeyLoose);
      if (raw) setPendingLooseReceipts(JSON.parse(raw));
    } catch (_) { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKeyLoose]);

  // Fase 17.5 (2026-02-27): Preview state for modalen. Når <input
  // type="file"> change-event fyrer behandler vi billedet via canvas
  // filter og åbner preview-modalen.
  const [scannerPreview, setScannerPreview] = useState({
    base64: "",
    dataUrl: "",
    sizeKB: 0,
  });

  // Fase 17.13 (2026-02-27): Komprimerer billedet før vi koder det til
  // base64. Reducerer typisk 4-7MB iPhone-fotos til ~250-500KB ved
  // 1600px @ 80% JPEG - stadig læsbar tekst på kvitteringer, men ~10x
  // hurtigere preview-rendering og upload.
  const compressImage = (blob, callback) => {
    const img = new window.Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const MAX = 1600;
      const scale = Math.min(1, MAX / Math.max(img.width, img.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(callback, 'image/jpeg', 0.80);
    };
    img.onerror = () => { URL.revokeObjectURL(url); callback(null); };
    img.src = url;
  };

  // Fase 17.6 (2026-02-27): Forenklet flow uden canvas-filter og uden
  // preview-modal. iOS Safari kan reload'e siden umiddelbart efter
  // kameraet lukker (memory pressure med store fotos), så alt skal
  // gemmes til sessionStorage SÅ HURTIGT SOM MULIGT.
  const uploadScannedDocument = (blob, target) => {
    if (!blob) return;
    const t = target || { mode: "normal", rowIdx: -1 };
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const base64 = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
      const payload = { base64, previewDataUrl: dataUrl, contentType: "image/jpeg" };
      // Skriv DIREKTE til sessionStorage så det overlever iOS reload.
      try {
        if (t.mode === "loose" && t.rowIdx >= 0 && storageKeyLoose) {
          const existing = sessionStorage.getItem(storageKeyLoose);
          const merged = existing ? JSON.parse(existing) : {};
          merged[t.rowIdx] = payload;
          sessionStorage.setItem(storageKeyLoose, JSON.stringify(merged));
        } else if (storageKeyNormal) {
          sessionStorage.setItem(storageKeyNormal, JSON.stringify(payload));
        }
      } catch (_) { /* quota - ignorér */ }
      if (t.mode === "loose" && t.rowIdx >= 0) {
        setPendingLooseReceipts(prev => ({ ...prev, [t.rowIdx]: payload }));
      } else {
        setPendingReceiptImage(payload);
        setAskingWeight(true);
      }
      toast.success("Kvittering vedhæftet - indtast vægt for at gemme");
    };
    compressImage(blob, (compressed) => {
      reader.readAsDataURL(compressed || blob);
    });
  };

  const handleFile = (e, target) => {
    const file = e.target.files[0]
    if (!file) return
    // Send direkte til base64 - INGEN canvas-filter, INGEN Image()-load.
    // Hvert ekstra async-trin er en chance for at iOS Safari river
    // siden ned før vi når at gemme. Filteret gav alligevel uensartede
    // resultater på iOS.
    uploadScannedDocument(file, target);
    // Ryd input-værdien så samme fil kan vælges igen senere.
    try { e.target.value = ""; } catch (_) { /* ignore */ }
  }


  // Reset the inline weight prompt every time the panel switches tours.
  // Fase 15.43 (2026-02-22): Vi init'er KUN ved tour-id-skifte (mount/ny tur).
  // Efter "Gem udkast" mister vi IKKE chaufførens lokale "next-vægt"-felt
  // (trailing "" vi tilføjer manuelt). Server-spejling sker via parent's
  // setSelectedTourForPanel - vi bevidst IGNORERER container_weights-prop-
  // ændringer i denne effect så brugerens næste-input ikke fjernes.
  useEffect(() => {
    setWeightInput(tour?.weight != null && tour?.weight !== "" ? String(tour.weight) : "");
    // Fase 15.44 (2026-02-22): For LØS AFHENTNING vises multi-vægt-UI'en
    // ALTID når turen ikke er afsluttet, så chaufføren straks kan se
    // eksisterende drafts og tilføje flere. For øvrige opgavetyper opens
    // den kun på Afslut-klik (klassisk inline vægt-prompt).
    // 2026-10-17: Flere læs (løs afhentning ELLER flere indholdslinjer, fx
    // hænger 1: Beton, hænger 2: Træ) vejes hver for sig med samme UI.
    const _cargoN = Array.isArray(tour?.cargo_lines) ? tour.cargo_lines.length : 0;
    const _hasCapture = !!effectiveCapture(tour, unifiedFinish);
    const isLoesActive = (tour?.tour_type === "loes_afhentning" || _cargoN > 1) && !tour?.completed && !_hasCapture;
    setAskingWeight(isLoesActive);
    setEditingWeight(false);
    setEditWeightVal(tour?.weight != null && tour?.weight !== "" ? String(tour.weight) : "");
    const existing = Array.isArray(tour?.container_weights) ? tour.container_weights : [];
    setContainerWeights(existing.length > 0 ? existing.map(w => String(w)) : (_cargoN > 1 ? Array(_cargoN).fill("") : [""]));
    // Fase 17.3 (2026-02-27): Pending-billeder NULSTILLES IKKE her - de
    // loades fra sessionStorage så iOS Safari-reload (kamera-overtagelse)
    // ikke koster chaufføren et scan. Når uploaden lykkes ryddes både
    // state og sessionStorage i handleConfirmWeight/handleConfirmLooseWeights.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tour?.id]);
  // Fase 17.7 (2026-02-27): Lock mod dobbeltklik på OK. Skal være FØR
  // `if (!tour) return null` for at overholde rules-of-hooks.
  const [isSubmittingWeight, setIsSubmittingWeight] = useState(false);
  // 2026-10-17: Stop på turen krydses af her (lokal kopi for straks-visning).
  const [localStops, setLocalStops] = useState(null);
  useEffect(() => { setLocalStops(null); }, [tour?.id, JSON.stringify(tour?.stops || [])]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!tour) return null;
  const isClaimedByOther = tour.claimed_by && tour.claimed_by !== currentDriverName;
  const cargoLines = Array.isArray(tour.cargo_lines) ? tour.cargo_lines : [];
  // 2026-10-18: Ture der bruger afslutningsarket (capture, eller alle ture når
  // firmaet har slået "Ét afslutningsark" til). Ellers det gamle vægt-flow.
  const hasCapture = !!effectiveCapture(tour, unifiedFinish);
  const isMultiLoadTour = !hasCapture && (tour.tour_type === "loes_afhentning" || cargoLines.length > 1);
  const isGoodsTour = tour.tour_kind === "goods";
  const multiTitle = tour.tour_type === "loes_afhentning" ? "LØS AFHENTNING" : "turen";
  const tourStops = localStops || (Array.isArray(tour.stops) ? tour.stops : []);
  const loadLabel = (idx) => (cargoLines.length > 1
    ? `${cargoLines[idx]?.trailer ? `H${cargoLines[idx].trailer} ` : ""}${cargoLines[idx]?.text || `Læs ${idx + 1}`}`
    : `#${idx + 1}`);
  const handleDelete = () => {
    if (window.confirm(`Slet turen "${tour.fraction || ""}"?`)) {
      onDelete?.(tour.id);
      onClose?.();
    }
  };
  // "Tilbage" - give back / release the tour. Clears claim + on_way + completed
  // so another driver can take it again. Only the current claimer (or no
  // claimer at all) can release.
  // Fase 11 (2026-06-18): Forbedret nulstilling - nu sender den eksplicit
  // alle status-felter til default + en `weight: 0` (kun for normal-typer)
  // så turen står som dagsfrisk i UI'et igen.
  const handleRelease = async () => {
    // Fase 15.11 (2026-02-XX): To forskellige scenarier:
    //  (a) Almindelig fri tur → bekræft frigivelse → andre kan tage den.
    //  (b) Admin-tildelt tur → bekræft fortryd af kørsel → tildelingen
    //      bevares (driver_id + assigned_by_* rør vi IKKE), men PÅ VEJ
    //      nulstilles så turen igen står som VENTER.
    const isAssigned = !!tour.assigned_by_id;
    const confirmMsg = isAssigned
      ? "Fortryd kørsel? Turen skifter til VENTER men forbliver tildelt dig."
      : "Vil du give turen tilbage? Andre chauffører kan derefter tage den.";
    if (!window.confirm(confirmMsg)) return;
    try {
      const resetPayload = {
        claimed_by: "",
        claimed_by_id: "",
        on_way: false,
        completed: false,
        time: "",
        on_way_time: "",
      };
      // Vægt nulstilles kun for opgavetypen 'normal' (afhent container).
      // For de øvrige typer er vægten alligevel altid 0.
      if ((tour.tour_type || "normal") === "normal") {
        resetPayload.weight = 0;
      }
      await onUpdate?.(tour.id, resetPayload);
      toast.success(isAssigned ? "Kørsel fortrudt - turen er tilbage på VENTER" : "Turen er nulstillet og givet tilbage");
      onClose?.();
    } catch (_) { /* parent toasts errors */ }
  };
  const needTrailerConfirm = !trailerAnswered && tour.used_trailer === true && tour.trailer_source === "auto" && !tour.trailer_confirmed;
  // P5: Gem hænger-svaret fra linjen i vægtarket lige før turen afsluttes.
  const confirmTrailerFromSheet = async () => {
    if (!needTrailerConfirm) return true;
    const v = trailerChoice == null ? true : trailerChoice;
    try { await axios.put(`${API}/driver/tours/${tour.id}/trailer`, { used_trailer: v }); }
    catch (e) { toast.error(formatApiError(e)); return false; }
    setTrailerAnswered(true);
    return true;
  };
  const trailerLine = needTrailerConfirm ? (
    <div className="mb-2.5 flex items-center justify-between gap-2 rounded-lg bg-white/70 dark:bg-slate-900/40 px-2.5 py-2" data-testid="weight-sheet-trailer">
      <span className="text-sm text-slate-700 dark:text-slate-200"><b>Hænger:</b> {(trailerChoice == null ? true : trailerChoice) ? "Ja" : "Nej"}
        <span className="block text-[11px] text-slate-500">Forudfyldt fra din profil - bruges til afregningen</span></span>
      <div className="inline-flex p-0.5 rounded-lg bg-slate-200 dark:bg-slate-800">
        {[[true, "Ja"], [false, "Nej"]].map(([v, l]) => (
          <button key={l} type="button" onClick={() => setTrailerChoice(v)} data-testid={`weight-sheet-trailer-${v ? "yes" : "no"}`}
            className={`px-3 py-1.5 rounded-md text-xs font-bold ${(trailerChoice == null ? true : trailerChoice) === v ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-white" : "text-slate-500"}`}>{l}</button>
        ))}
      </div>
    </div>
  ) : null;
  const handleCompleteClick = async () => {
    // Fase 13 (2026-06-18): Hard-stop hvis allerede afsluttet - knappen
    // skal ALDRIG kunne nulstille en afsluttet tur via "Afslut" igen.
    if (tour.completed) return;
    // 2026-10-18: Hængeren blev foreslået ud fra profilen da turen startede.
    // Spørg med svaret forudfyldt, så der ikke faktureres hænger blindt.
    // P5: Vises vægtarket, står spørgsmålet som en linje dér (én skærm) -
    // modalen bruges kun når turen afsluttes uden vægtark.
    const _tt = tour.tour_type || "normal";
    const _hasLoads = (Array.isArray(tour.container_weights) ? tour.container_weights : []).some(w => parseFloat(w) > 0);
    const _hasWeight = tour.weight != null && tour.weight !== "" && parseFloat(tour.weight) > 0;
    const _sheetNext = (isMultiLoadTour && !_hasLoads && !isGoodsTour) || (!isMultiLoadTour && isGoodsTour)
      || (!isMultiLoadTour && _tt === "normal" && !_hasWeight);
    if (needTrailerConfirm && !askingWeight && !_sheetNext) {
      const v = await new Promise(res => setTrailerAsk({ resolve: res }));
      setTrailerAsk(null);
      if (v === null) return;
      try { await axios.put(`${API}/driver/tours/${tour.id}/trailer`, { used_trailer: v }); }
      catch (e) { toast.error(formatApiError(e)); return; }
      setTrailerAnswered(true);
      onRefresh?.();
    }
    // Fase 15.44 (2026-02-22): SOFT-VALIDATION - bekræft før vi markerer
    // turen som afsluttet. Et fejlklik på "Afslut" har permanent effekt
    // (claimed_by låses, vægt lægges på rapport), så vi spørger først.
    // Gælder ALLE opgavetyper. Bypass'es naturligt af `setAskingWeight(true)`
    // grenen, da brugeren der først skal udfylde vægt.
    const tt = (tour.tour_type || "normal");
    const askConfirm = (msg) => {
      try { return window.confirm(msg); } catch (_) { return true; }
    };
    const openStops = tourStops.filter(x => !x.done_at).length;
    if (openStops && !askConfirm(`${openStops} stop er ikke krydset af. Afslut turen alligevel?`)) return;
    if (isMultiLoadTour) {
      const existing = Array.isArray(tour.container_weights) ? tour.container_weights : [];
      const hasAtLeastOne = existing.some(w => parseFloat(w) > 0);
      if (!hasAtLeastOne) {
        // Flere læs: vægtene indtastes i felterne ovenfor. Gods må afsluttes uden vægt.
        if (isGoodsTour) {
          if (!askConfirm(`Afslut uden vægt?\n\n${tour.fraction || ""}`)) return;
          if (!(await confirmTrailerFromSheet())) return;
          const r = await onToggleComplete?.(tour.id, { skipWeight: true });
          if (r?.ok) onClose?.();
          return;
        }
        setAskingWeight(true);
        toast.error("Indtast mindst én vægt i felterne ovenfor");
        return;
      }
      const total = existing.reduce((s, w) => s + (parseFloat(w) || 0), 0);
      const ok = askConfirm(
        `Afslut ${multiTitle}?\n\n` +
        `Materiale: ${tour.fraction || "?"}\n` +
        `Containere: ${existing.length}\n` +
        `Total vægt: ${total.toLocaleString("da-DK")} kg\n\n` +
        `Du kan IKKE tilføje flere vægte efter afslutning.`
      );
      if (!ok) return;
      if (!(await confirmTrailerFromSheet())) return;
      const result = await onToggleComplete?.(tour.id);
      if (result?.ok) onClose?.();
      return;
    }
    if (isGoodsTour) {
      // Gods: vægt er valgfri - vis feltet med "Afslut uden vægt".
      setAskingWeight(true);
      return;
    }
    if (tt !== "normal") {
      const typeLabel = TOUR_TYPE_LABELS[tt] || tt;
      const ok = askConfirm(`Afslut "${typeLabel}"?\n\nMateriale: ${tour.fraction || "?"}`);
      if (!ok) return;
      if (!(await confirmTrailerFromSheet())) return;
      const result = await onToggleComplete?.(tour.id, { skipWeight: true });
      if (result?.ok) onClose?.();
      return;
    }
    const hasWeight = tour.weight != null && tour.weight !== "" && parseFloat(tour.weight) > 0;
    if (!hasWeight) {
      setAskingWeight(true);
      return;
    }
    const ok = askConfirm(
      `Afslut turen?\n\n` +
      `Materiale: ${tour.fraction || "?"}\n` +
      `Vægt: ${parseFloat(tour.weight).toLocaleString("da-DK")} kg`
    );
    if (!ok) return;
    if (!(await confirmTrailerFromSheet())) return;
    const result = await onToggleComplete?.(tour.id);
    if (result?.ok) onClose?.();
  };
  // Fase 17.7 (2026-02-27): Lock-state defineret ovenfor (før early return).
  const handleConfirmWeight = async () => {
    if (isSubmittingWeight) return; // kort lock kun til tour-completion (millisekunder)
    const val = parseFloat(weightInput);
    if ((!val || val <= 0) && !isGoodsTour) { toast.error("Indtast vægt"); return; }
    if (!val || val <= 0) {
      setIsSubmittingWeight(true);
      try {
        if (!(await confirmTrailerFromSheet())) return;
        const r = await onToggleComplete?.(tour.id, { skipWeight: true });
        if (r?.ok) onClose?.();
      } finally { setIsSubmittingWeight(false); }
      return;
    }
    setIsSubmittingWeight(true);
    try {
      // Fase 17.13: Luk panelet straks når turen er marked completed.
      // Receipt-upload sker via persistent kø i baggrunden - overlever
      // browser-luk, dårlig dækning og iOS reload.
      if (!(await confirmTrailerFromSheet())) return;
      const result = await onToggleComplete?.(tour.id, { weight: val });
      if (result?.ok) {
        const imageToUpload = pendingReceiptImage;
        setPendingReceiptImage(null);
        try { if (storageKeyNormal) sessionStorage.removeItem(storageKeyNormal); } catch (_) {}
        onClose?.();
        if (imageToUpload?.base64) {
          enqueueReceiptUpload({
            tour_id: tour.id,
            image_data: imageToUpload.base64,
            content_type: imageToUpload.contentType || "image/jpeg",
            description: "Vedhæftet via scanner",
            final_weight_kg: val,
            user_name: currentDriverName || tour.claimed_by || "",
            append_for_loose: false,
          });
        }
      }
    } finally {
      setIsSubmittingWeight(false);
    }
  };
  // Fase 15.41 (2026-02-22): Bekræft multi-vægt-input for løs afhentning.
  // Validerer mindst 1 vægt > 0, sender array (backend auto-beregner total).
  const handleConfirmLooseWeights = async () => {
    if (isSubmittingWeight) return; // Fase 17.7: hard lock
    const clean = containerWeights
      .map(w => parseFloat(w))
      .filter(w => Number.isFinite(w) && w > 0);
    if (clean.length === 0) {
      if (isGoodsTour) {
        if (!window.confirm(`Afslut uden vægt?\n\n${tour.fraction || ""}`)) return;
        const r = await onToggleComplete?.(tour.id, { skipWeight: true });
        if (r?.ok) onClose?.();
        return;
      }
      toast.error("Indtast mindst én vægt > 0");
      return;
    }
    // Fase 15.44 (2026-02-22): SOFT-VALIDATION inden endelig afslutning.
    const total = clean.reduce((s, w) => s + w, 0);
    let confirmed = true;
    try {
      confirmed = window.confirm(
        `Afslut ${multiTitle}?\n\n` +
        `Materiale: ${tour.fraction || "?"}\n` +
        `Containere: ${clean.length}\n` +
        `Total vægt: ${total.toLocaleString("da-DK")} kg\n\n` +
        `Du kan IKKE tilføje flere vægte efter afslutning.`
      );
    } catch (_) { confirmed = true; }
    if (!confirmed) return;
    setIsSubmittingWeight(true);
    try {
      // Fase 17.13 (2026-02-27): Luk panelet straks når turen er marked
      // completed. Uploads sker via persistent kø - overlever browser-luk.
      const looseEntries = Object.entries(pendingLooseReceipts || {})
        .filter(([idx, payload]) => payload?.base64 && parseFloat(containerWeights[Number(idx)]) > 0);
      const result = await onToggleComplete?.(tour.id, { containerWeights: clean });
      if (result?.ok) {
        setPendingLooseReceipts({});
        try { if (storageKeyLoose) sessionStorage.removeItem(storageKeyLoose); } catch (_) {}
        onClose?.();
        for (const [idx, payload] of looseEntries) {
          const rowWeight = parseFloat(containerWeights[Number(idx)]);
          enqueueReceiptUpload({
            tour_id: tour.id,
            image_data: payload.base64,
            content_type: payload.contentType || "image/jpeg",
            description: `Løs afhentning - container ${Number(idx) + 1}`,
            final_weight_kg: rowWeight,
            user_name: currentDriverName || tour.claimed_by || "",
            append_for_loose: true,
          });
        }
      }
    } finally {
      setIsSubmittingWeight(false);
    }
  };
  // Fase 15.43 (2026-02-22): "Gem udkast" - gemmer container_weights UDEN at
  // markere turen som completed. Bruges når chaufføren skal kunne tilføje
  // flere vægte over tid (fx flere ture/læs frem og tilbage til samme plads).
  // Backend opdaterer automatisk `weight` som SUM og spejler det til ordren
  // så kunden kan følge med på bestillingssiden i realtid.
  // Fase 15.44 (2026-02-22): Efter succes tilføjes ét nyt tomt felt
  // automatisk så chaufføren straks kan indtaste næste container uden at
  // skulle finde "+ Tilføj vægt"-knappen først.

  // Fase 15.52 (2026-02-22): "Kan ikke gennemføres" - chauffør markerer
  // turen som ikke-gennemførbar med obligatorisk kommentar.
  const handleConfirmNotCompleted = async () => {
    const c = (notCompletedReason || "").trim();
    if (!c && !notCompletedCode) {
      toast.error("Vælg en årsag eller skriv en kort forklaring");
      return;
    }
    setSubmittingNotCompleted(true);
    try {
      // 2026-10-18 (C3): Årsagskode (fx "Lukket") gør forgæves kørsel målbar og fakturerbar.
      await axios.post(`${API}/tours/${tour.id}/not-completed`, { comment: c, code: notCompletedCode });
      setNotCompletedCode("");
      toast.success("Tur markeret som ikke-gennemført");
      setShowNotCompletedDialog(false);
      setNotCompletedReason("");
      onClose?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke markere turen");
    } finally {
      setSubmittingNotCompleted(false);
    }
  };

  const handleSaveLooseDraft = async () => {
    const clean = containerWeights
      .map(w => parseFloat(w))
      .filter(w => Number.isFinite(w) && w > 0);
    if (clean.length === 0) {
      toast.error("Indtast mindst én vægt > 0 for at gemme udkast");
      return;
    }
    try {
      await onUpdate?.(tour.id, {
        container_weights: clean,
        claimed_by: tour.claimed_by || currentDriverName,
      });
      // Fase 18.7 (2026-02-28): Upload også pending kvitteringer NU (i stedet
      // for kun ved Afslut). Det betyder at hvis chaufføren forlader siden
      // efter et "Gem udkast", er kvitteringerne allerede sikret på serveren
      // og knyttet til den respektive vægt-række.
      // Vi uploader KUN rækker hvor (a) der er en pending receipt OG (b)
      // vægten er gyldig. Den uploadede receipt fjernes fra pendingLooseReceipts
      // og fjernes fra sessionStorage så vi ikke uploader den igen.
      const pendingEntries = Object.entries(pendingLooseReceipts || {})
        .filter(([idx, payload]) => payload?.base64 && parseFloat(containerWeights[Number(idx)]) > 0);
      if (pendingEntries.length > 0) {
        for (const [idx, payload] of pendingEntries) {
          const rowWeight = parseFloat(containerWeights[Number(idx)]);
          enqueueReceiptUpload({
            tour_id: tour.id,
            image_data: payload.base64,
            content_type: payload.contentType || "image/jpeg",
            description: `Løs afhentning - container ${Number(idx) + 1}`,
            final_weight_kg: rowWeight,
            user_name: currentDriverName || tour.claimed_by || "",
            append_for_loose: true,
            // Receipts er allerede uploadede via draft - turen er IKKE
            // markeret completed. Backend's save-for-tour håndterer dette
            // korrekt: appender til container_weights kun hvis vægten ikke
            // allerede er der (vi sender skip_tour_update=true via append-flow).
            skip_tour_update: true,
          });
        }
        setPendingLooseReceipts({});
        try { if (storageKeyLoose) sessionStorage.removeItem(storageKeyLoose); } catch (_) {}
      }
      // Tilføj automatisk et nyt tomt felt klar til næste vægt.
      setContainerWeights([...clean.map(String), ""]);
      // Refresh server-receipts så de uploadede kvitteringer dukker op.
      setTimeout(() => { fetchUploadedReceipts(); }, 800);
      const recMsg = pendingEntries.length > 0
        ? ` · ${pendingEntries.length} kvit. lagt i upload-kø`
        : "";
      toast.success(`Udkast gemt - ${clean.length} container${clean.length === 1 ? "" : "e"}, ${clean.reduce((s, w) => s + w, 0).toLocaleString("da-DK")} kg${recMsg}`);
    } catch (_) { /* parent toaster */ }
  };
  // Fase 14 (2026-06-19): Tillader chauffør at rette vægten EFTER turen er
  // afsluttet - fx hvis kvitteringen var ulæselig. Sender claimed_by med
  // for at undgå backend's 'restricted_fields'-guard.
  const handleSaveEditedWeight = async () => {
    const v = parseFloat(editWeightVal);
    if (!v || v <= 0) { toast.error("Indtast en gyldig vægt"); return; }
    try {
      await onUpdate?.(tour.id, {
        weight: v,
        claimed_by: tour.claimed_by || currentDriverName,
      });
      toast.success("Vægt rettet");
      setEditingWeight(false);
    } catch (_) { /* parent toaster håndterer */ }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-0 sm:p-4" onClick={onClose} data-testid="mobile-tour-panel">
      <div
        className="bg-white dark:bg-slate-900 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[85vh] overflow-y-auto"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h3 className="font-bold text-lg text-slate-900 dark:text-white truncate">
                {tour.fraction || "Tur"}
              </h3>
              {tour.priority && tour.priority !== "normal" && (
                <span className={`px-1.5 py-0.5 text-[10px] font-black rounded ${
                  tour.priority === "urgent" ? "bg-red-500 text-white" :
                  tour.priority === "high" ? "bg-orange-500 text-white" :
                  "bg-blue-500 text-white"
                }`}>
                  {tour.priority === "urgent" ? "HASTER" : tour.priority === "high" ? "HØJ" : "LAV"}
                </span>
              )}
              {tour.is_same_day && (
                <span className="px-1.5 py-0.5 bg-orange-500 text-white text-[10px] font-bold rounded">SD</span>
              )}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
              {/* Fase 15.41 (2026-02-22): Skjul container-id for løs
                  afhentning - vis i stedet estimeret antal containere. */}
              {[tour.plads,
                tour.tour_type === "loes_afhentning"
                  ? `Løs afhentning · ${tour.loose_estimated_count || 0} container(e)`
                  : isGoodsTour
                    ? `Fragt${Number(tour.trailer_count) ? ` · ${tour.trailer_count} hængere` : ""}`
                    : (tour.container ? `Container ${tour.container}` : (Number(tour.trailer_count) ? `${tour.trailer_count} hængere` : "")),
              ].filter(Boolean).join(" • ")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="ml-2 p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500"
            data-testid="mobile-tour-panel-close"
            aria-label="Luk"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {onChat && (
          <div className="px-4 pt-3 grid grid-cols-1 min-[380px]:grid-cols-2 gap-2">
            <CallPlannerButton tourId={tour.id} />
            <button
              onClick={onChat}
              className="w-full min-h-[44px] rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 font-semibold text-sm inline-flex items-center justify-center gap-2"
              data-testid="mobile-tour-panel-chat"
            >
              <MessageSquare className="w-4 h-4" /> Skriv til planlæggeren
            </button>
          </div>
        )}

        {/* Details */}
        <div className="p-4 space-y-3 text-sm">
          {tour.facility && tourStops.length === 0 && (
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-0.5">{isGoodsTour ? "Aflevering" : "Modtageanlæg"}</div>
              <div className="text-slate-800 dark:text-slate-200">{tour.facility}</div>
            </div>
          )}
          {tour.address && tourStops.length === 0 && (
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-0.5">Adresse</div>
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(tour.address)}&travelmode=driving`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline font-medium"
                data-testid="mobile-tour-panel-address-link"
              >
                <MapPin className="w-4 h-4" />
                {tour.address}
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
          {(tourStops.length > 0 || (tour.on_way && !tour.completed && !isClaimedByOther)) && (
            <DriverStopList tour={tour} stops={tourStops} codes={deviationCodes}
              canTick={!tour.completed && !isClaimedByOther && !!(tour.on_way || tour.claimed_by)}
              onChanged={(st, queued) => { setLocalStops(st); if (!queued) onRefresh?.(); }} />
          )}
          {(tour.open_from || tour.open_to) && (
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-0.5">Åbningstid</div>
              <div className="text-slate-800 dark:text-slate-200">
                {tour.open_from || "-"} – {tour.open_to || "-"}
              </div>
            </div>
          )}
          {tour.weight != null && tour.weight !== "" && (tour.tour_type || "normal") === "normal" && (
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-0.5">Vægt</div>
              <div className="text-slate-800 dark:text-slate-200 font-mono">{tour.weight} kg</div>
            </div>
          )}
          {tour.claimed_by && (
            <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
              <Users className="w-4 h-4" />
              <span className="font-medium">{tour.claimed_by}</span>
              {tour.completed && <span className="text-slate-500 text-xs" data-testid={`panel-completed-stamp-${tour.id}`}>har afsluttet{tour.completed_at ? ` ${formatCompletedAt(tour.completed_at)}` : ""}</span>}
              {tour.on_way && !tour.completed && <span className="text-slate-500 text-xs">kører</span>}
            </div>
          )}
        </div>

        {/* Inline weight prompt - shown when user clicked "Afslut" but no weight yet.
            Fase 15.41 (2026-02-22): Når tour.tour_type === "loes_afhentning"
            vises en MULTI-vægt-UI med "+ Tilføj container"-knap. Total
            beregnes live. */}
        {askingWeight && !isClaimedByOther && isMultiLoadTour && (
          <div className="mx-4 mb-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-800" data-testid="mobile-tour-panel-loose-prompt">
            {trailerLine}
            <label className="block text-xs uppercase tracking-wide text-amber-700 dark:text-amber-300 mb-2 font-semibold">
              {cargoLines.length > 1 ? `Vægt pr. læs (kg)${isGoodsTour ? " - valgfri" : " - mindst én påkrævet"}` : "Container-vægte (kg) - mindst én påkrævet"}
            </label>
            <div className="space-y-2">
              {containerWeights.map((w, idx) => {
                // Fase 18.7 (2026-02-28): Match server-receipts til row index
                // via chronologisk rækkefølge. Hvis chaufføren har slettet en
                // række kan der opstå mismatch - men det er sjældent og kan
                // afhjælpes ved at se ALLE uploadede kvitteringer i bunden.
                const serverReceipt = uploadedReceipts[idx] || null;
                const hasPending = !!pendingLooseReceipts[idx];
                const hasServer = !!serverReceipt;
                return (
                <div key={idx} className="flex flex-wrap items-center gap-2" data-testid={`loose-weight-row-${idx}`}>
                  <span className={`text-xs font-bold text-amber-800 dark:text-amber-200 shrink-0 ${cargoLines.length > 1 ? "w-full sm:w-auto sm:max-w-[140px] truncate" : "w-8"}`}>{loadLabel(idx)}</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.01"
                    min="0"
                    value={w}
                    onChange={(e) => {
                      const next = [...containerWeights];
                      next[idx] = e.target.value;
                      setContainerWeights(next);
                    }}
                    placeholder="kg"
                    className="flex-1 min-w-0 px-2 py-2 rounded-lg border-2 border-amber-300 dark:border-amber-600 bg-white dark:bg-amber-50 text-amber-950 font-mono font-bold outline-none focus:border-amber-500 text-base placeholder:text-amber-400 placeholder:font-normal"
                    data-testid={`loose-weight-input-${idx}`}
                  />
                  {containerWeights.length > 1 && (
                    <button
                      type="button"
                      onClick={() => {
                        const next = containerWeights.filter((_, i) => i !== idx);
                        setContainerWeights(next.length === 0 ? [""] : next);
                      }}
                      className="text-red-500 hover:text-red-700 p-1"
                      data-testid={`loose-weight-remove-${idx}`}
                      title="Fjern denne vægt"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                  {/* Fase 18.7 (2026-02-28): "Åbn"-knap viser server-uploaded
                      kvittering for denne container. Tydelig grøn badge når
                      gemt. Pending (lokal) vises som "Vedh." indtil afslut. */}
                  {hasServer ? (
                    <button
                      type="button"
                      onClick={() => setViewerReceiptId(serverReceipt.id)}
                      className="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold inline-flex items-center gap-1 shrink-0"
                      data-testid={`loose-weight-view-${idx}`}
                      title="Vis uploadet kvittering"
                    >
                      <Eye className="w-3 h-3" /> Åbn
                    </button>
                  ) : hasPending ? (
                    <span
                      className="px-2 py-1 rounded-lg bg-amber-500 text-white text-[10px] font-bold inline-flex items-center gap-1 shrink-0"
                      title="Kvittering venter på upload (sker ved Afslut)"
                      data-testid={`loose-weight-pending-${idx}`}
                    >
                      <Check className="w-3 h-3" /> Vedh.
                    </span>
                  ) : null}
                  {/* Fase 18.9 (2026-02-28): Camera label + input wrapped i en
                      separat shrink-0 div ml-auto, så ikonet aldrig presses
                      ud af skærmen på smalle mobiler. */}
                  <div className="flex items-center gap-1 ml-auto shrink-0">
                    {/* Fase 17.5 (2026-02-27): 1-TAP iOS Safari pattern.
                        Hver løs-række har sin egen label+input med unikt id. */}
                    <label
                      htmlFor={`loose-camera-input-${idx}`}
                      style={{ cursor: 'pointer' }}
                      className={`relative p-1.5 rounded-lg inline-flex items-center shrink-0 ${
                        hasServer || hasPending
                          ? "bg-emerald-600 text-white"
                          : "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-900/60"
                      }`}
                      data-testid={`loose-weight-scan-${idx}`}
                      title={hasServer ? "Skift kvittering (overskriver)" : hasPending ? "Kvittering vedhæftet - tryk for at skifte" : "Scan kvittering for denne container"}
                    >
                      <Camera className="w-4 h-4" />
                      {(hasServer || hasPending) && (
                        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 border-2 border-white dark:border-slate-900" aria-hidden="true" />
                      )}
                    </label>
                    <input
                      id={`loose-camera-input-${idx}`}
                      type="file"
                      accept="image/*"
                      onChange={(e) => handleFile(e, { mode: "loose", rowIdx: idx })}
                      style={{
                        position: 'absolute',
                        opacity: 0,
                        width: '1px',
                        height: '1px',
                        pointerEvents: 'none'
                      }}
                      data-testid={`loose-camera-input-${idx}`}
                      aria-hidden="true"
                      tabIndex={-1}
                    />
                  </div>
                </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between mt-3 pt-2 border-t border-amber-200 dark:border-amber-800">
              <span className="text-xs font-bold text-amber-800 dark:text-amber-200" data-testid="loose-weight-total">
                Total: {containerWeights
                  .map(w => parseFloat(w))
                  .filter(w => Number.isFinite(w) && w > 0)
                  .reduce((s, w) => s + w, 0)
                  .toLocaleString("da-DK", { maximumFractionDigits: 2 })} kg
              </span>
            </div>
            {/* Fase 15.44 (2026-02-22): Stor, tydelig "Tilføj vægt"-knap.
                Dukker op når sidste række har en gyldig vægt så chaufføren
                aldrig "går i stå" - der er ALTID en synlig vej til at
                tilføje endnu en container.
                Bemærk: efter "Gem udkast" tilføjes der automatisk en tom
                række så denne knap typisk først dukker op igen når chaufføren
                har udfyldt den nye række. */}
            {(() => {
              const last = containerWeights[containerWeights.length - 1];
              const lastIsValid = parseFloat(last) > 0;
              if (!lastIsValid) return null;
              return (
                <button
                  type="button"
                  onClick={() => setContainerWeights([...containerWeights, ""])}
                  className="w-full mt-3 px-4 py-2.5 rounded-lg bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 font-bold text-sm border-2 border-dashed border-amber-400 dark:border-amber-700 hover:bg-amber-200 dark:hover:bg-amber-900/60 flex items-center justify-center gap-2"
                  data-testid="loose-weight-add-btn"
                  title="Tilføj endnu en container-vægt"
                >
                  <Plus className="w-4 h-4" /> Tilføj vægt
                </button>
              );
            })()}
            {/* Fase 15.43 (2026-02-22): Kun "Gem udkast"-knappen + cancel her.
                "Afslut"-handlingen sker via den grønne Afslut-knap nederst i
                Actions-rækken (samme knap som ALLE andre tur-typer bruger),
                så vi undgår dobbelte CTA-knapper og forvirring. */}
            {/* Fase 15.43 (2026-02-22): Kun "Gem udkast"-knappen her - 
                "Afslut"-handlingen sker via den grønne Afslut-knap nederst
                i Actions-rækken (samme knap som ALLE andre tur-typer bruger),
                så vi undgår dobbelte CTA-knapper og forvirring. 
                Fase 15.44 (2026-02-22): Cancel-knappen er fjernet - panelet
                er ALTID synligt for løs afhentning indtil afslutning, så
                chaufføren ikke kan "miste" UI'en og dermed muligheden for
                at tilføje flere vægte. */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleSaveLooseDraft}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg font-semibold hover:bg-blue-600 flex items-center justify-center gap-1.5"
                data-testid="loose-weight-save-draft-btn"
                title="Gem indtastede vægte uden at afslutte turen. Kunden ser dem på 'Mine bestillinger'."
              >
                <Save className="w-4 h-4" /> Gem udkast
              </button>
            </div>
            <p className="text-[10px] text-amber-700 dark:text-amber-300 mt-2 italic">
              Tryk på den grønne <strong>Afslut</strong>-knap nederst når alt er vejet.
            </p>
          </div>
        )}

        {/* Inline weight prompt - shown when user clicked "Afslut" but no weight yet */}
        {askingWeight && !isClaimedByOther && !isMultiLoadTour && (
          <div className="mx-4 mb-2 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-300 dark:border-emerald-800" data-testid="mobile-tour-panel-weight-prompt">
            {trailerLine}
            <label className="block text-xs uppercase tracking-wide text-emerald-700 dark:text-emerald-300 mb-1.5 font-semibold">
              {isGoodsTour ? "Vægt (kg) - valgfri" : "Vægt (kg) - påkrævet for at afslutte"}
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={weightInput}
                onChange={(e) => setWeightInput(e.target.value)}
                placeholder="F.eks. 1240"
                autoFocus
                className="flex-1 px-3 py-2 rounded-lg border-2 border-emerald-300 dark:border-emerald-700 dark:bg-slate-800 text-slate-900 dark:text-white font-mono outline-none focus:border-emerald-500"
                data-testid="mobile-tour-panel-weight-input"
              />
              <button
                onClick={handleConfirmWeight}
                disabled={isSubmittingWeight}
                className="px-4 py-2 bg-emerald-500 text-white rounded-lg font-semibold hover:bg-emerald-600 flex items-center gap-1 disabled:opacity-60 disabled:cursor-not-allowed"
                data-testid="mobile-tour-panel-weight-confirm"
              >
                {isSubmittingWeight ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Gemmer…</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> {isGoodsTour && !(parseFloat(weightInput) > 0) ? "Afslut uden vægt" : "Afslut"}</>
                )}
              </button>
              <button
                onClick={() => setAskingWeight(false)}
                className="px-3 py-2 text-slate-500 hover:text-slate-700"
                data-testid="mobile-tour-panel-weight-cancel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* Fase 17.5 (2026-02-27): 1-TAP iOS Safari pattern.
                <label htmlFor> peger på permanent <input type="file"
                capture="environment"> som ER SIBLING i DOM.
                INGEN <button> inde i label'en.
                INGEN inputRef.current.click().
                INGEN display:none.
                cursor: 'pointer' på label.
                Input forbliver ALTID mountet. */}
            <label
              htmlFor="receipt-camera-input"
              style={{ cursor: 'pointer' }}
              data-testid="mobile-tour-panel-scan-receipt-btn"
              className="w-full mt-2 px-3 py-3 rounded-lg bg-emerald-600 text-white font-bold flex items-center justify-center gap-2 hover:bg-emerald-700 active:scale-[0.99] text-base shadow"
            >
              <Camera className="w-5 h-5" />
              {pendingReceiptImage ? "Skift kvittering-billede" : "Scan kvittering"}
            </label>
            <input
              id="receipt-camera-input"
              type="file"
              accept="image/*"
              onChange={(e) => handleFile(e, { mode: "normal", rowIdx: -1 })}
              style={{
                position: 'absolute',
                opacity: 0,
                width: '1px',
                height: '1px',
                pointerEvents: 'none'
              }}
              data-testid="receipt-camera-input"
              aria-hidden="true"
              tabIndex={-1}
            />

            {/* Vedhæftet-indikator: viser thumbnail af det billede der
                ligger klar til at blive uploadet sammen med vægten. */}
            {pendingReceiptImage?.previewDataUrl && (
              <div
                className="mt-2 flex items-center gap-2 p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800"
                data-testid="mobile-tour-panel-pending-receipt"
              >
                <img
                  src={pendingReceiptImage.previewDataUrl}
                  alt="Vedhæftet kvittering"
                  className="w-12 h-12 object-cover rounded border border-emerald-300 dark:border-emerald-700"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-emerald-800 dark:text-emerald-200 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Kvittering klar
                  </div>
                  <div className="text-[10px] text-emerald-700 dark:text-emerald-300">
                    Uploades når du trykker OK
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setPendingReceiptImage(null)}
                  className="p-1 rounded text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/40"
                  title="Fjern vedhæftet kvittering"
                  data-testid="mobile-tour-panel-clear-pending-receipt"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        )}

        {!isClaimedByOther && (tour.on_way || tour.completed) && <TourBillingBox tour={tour} />}

        {/* Actions */}
        <div className="grid grid-cols-2 gap-2 p-4 border-t border-slate-200 dark:border-slate-700">
          {/* Fase 14 (2026-06-19): Når turen er AFSLUTTET ser chaufføren
              kun en informations-besked + en lille "Ret vægt"-knap.
              Knapperne På vej / Afslut / Fortryd er skjult. */}
          {!isClaimedByOther && tour.completed && (
            <div className="col-span-2 space-y-2" data-testid="mobile-tour-panel-completed-block">
              <div className="px-3 py-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-sm text-emerald-800 dark:text-emerald-200 flex items-start gap-2"
                data-testid="mobile-tour-panel-completed-notice">
                <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>Turen er afsluttet. Forkert tid, hænger eller ventetid? Brug "Ret tid, hænger eller ventetid" ovenfor (godkendes af planlæggeren).{hasCapture ? " Mængde og billede rettes her under." : ""}</span>
              </div>
              {hasCapture && onOpenFinish && (
                <button onClick={() => onOpenFinish(tour)} data-testid="mobile-tour-panel-edit-registration"
                  className="w-full px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 text-slate-700 flex items-center justify-center gap-2">
                  <Edit2 className="w-4 h-4" /> Ret mængde eller billede
                </button>
              )}
              {!hasCapture && ((tour.tour_type || "normal") === "normal" || isMultiLoadTour || isGoodsTour) && !editingWeight && (
                <button
                  onClick={() => {
                    setEditWeightVal(tour.weight != null ? String(tour.weight) : "");
                    if (isMultiLoadTour) {
                      const cw = Array.isArray(tour.container_weights) ? tour.container_weights.map(String) : [];
                      setContainerWeights(cw.length ? cw : (cargoLines.length > 1 ? Array(cargoLines.length).fill("") : [""]));
                    }
                    setEditingWeight(true);
                  }}
                  className="w-full px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center gap-2"
                  data-testid="mobile-tour-panel-edit-weight-btn"
                >
                  <Edit2 className="w-4 h-4" /> Ret vægt
                </button>
              )}
              {editingWeight && isMultiLoadTour && (
                <div className="px-3 py-2.5 rounded-lg bg-amber-50 border border-amber-300 space-y-2" data-testid="mobile-tour-panel-edit-loads-block">
                  <label className="block text-xs uppercase tracking-wide text-amber-700 font-semibold">Ret vægt pr. læs (kg)</label>
                  {containerWeights.map((w, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="text-xs font-bold text-amber-800 w-28 truncate">{loadLabel(idx)}</span>
                      <input type="number" inputMode="decimal" min="0" value={w}
                        onChange={(e) => setContainerWeights(containerWeights.map((x, j) => (j === idx ? e.target.value : x)))}
                        className="flex-1 px-3 py-2 rounded-lg border-2 border-amber-300 font-mono text-base outline-none focus:border-amber-500" />
                    </div>
                  ))}
                  <div className="flex gap-2">
                    <button className="flex-1 px-4 py-2.5 bg-amber-500 text-white rounded-lg font-semibold" data-testid="mobile-tour-panel-edit-loads-save"
                      onClick={async () => {
                        const clean = containerWeights.map(x => parseFloat(x)).filter(x => Number.isFinite(x) && x >= 0);
                        try {
                          await onUpdate?.(tour.id, { container_weights: clean, claimed_by: tour.claimed_by || currentDriverName });
                          toast.success("Vægte rettet");
                          setEditingWeight(false);
                        } catch (_) { /* parent toaster */ }
                      }}>Gem</button>
                    <button onClick={() => setEditingWeight(false)} className="px-4 py-2.5 text-slate-500">Annuller</button>
                  </div>
                </div>
              )}
              {editingWeight && !isMultiLoadTour && (
                <div className="px-3 py-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-800" data-testid="mobile-tour-panel-edit-weight-block">
                  <label className="block text-xs uppercase tracking-wide text-amber-700 dark:text-amber-300 mb-1.5 font-semibold">
                    Ret vægt (kg)
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      min="0"
                      value={editWeightVal}
                      onChange={(e) => setEditWeightVal(e.target.value)}
                      autoFocus
                      placeholder="F.eks. 1240"
                      className="flex-1 px-3 py-2 rounded-lg border-2 border-amber-300 dark:border-amber-700 dark:bg-slate-800 text-slate-900 dark:text-white font-mono outline-none focus:border-amber-500"
                      data-testid="mobile-tour-panel-edit-weight-input"
                    />
                    <button
                      onClick={handleSaveEditedWeight}
                      className="px-4 py-2 bg-amber-500 text-white rounded-lg font-semibold hover:bg-amber-600 flex items-center gap-1"
                      data-testid="mobile-tour-panel-edit-weight-save"
                    >
                      <CheckCircle2 className="w-4 h-4" /> Gem
                    </button>
                    <button
                      onClick={() => setEditingWeight(false)}
                      className="px-3 py-2 text-slate-500 hover:text-slate-700"
                      data-testid="mobile-tour-panel-edit-weight-cancel"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
          {!isClaimedByOther && !tour.completed && (
            <>
              {/* Fase 11 (2026-06-18): "På vej" kan KUN aktiveres én gang -
                  klik igen gør ingenting. For at fjerne status bruger
                  chaufføren "Fortryd"-knappen.
                  Fase 12 (2026-06-18): Auto-luk vinduet efter "På vej" så
                  chaufføren ikke skal trykke X bagefter. */}
              <button
                onClick={async () => {
                  if (!tour.on_way && !tour.completed) {
                    await onToggleOnWay?.(tour.id);
                    // Vent kort på, at parent's state opdaterer, og luk så.
                    setTimeout(() => onClose?.(), 150);
                  }
                }}
                disabled={tour.on_way || tour.completed}
                className={`px-3 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 ${
                  tour.on_way
                    ? "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300 cursor-not-allowed"
                    : tour.completed
                    ? "bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-500 cursor-not-allowed"
                    : "bg-orange-500 text-white hover:bg-orange-600"
                }`}
                data-testid="mobile-tour-panel-onway"
              >
                <Truck className="w-4 h-4" /> {tour.on_way ? "På vej ✓" : "På vej"}
              </button>
              {/* Fase 13 (2026-06-18): Afslut-knappen er HARD DISABLED når
                  turen allerede er afsluttet - klik kan ikke fortryde
                  status. Chaufføren skal bruge "Fortryd"-knappen hvis de
                  vil nulstille turen.
                  Fase 15.43 (2026-02-22): For Løs afhentning fungerer
                  knappen i 2 trin:
                    1. Hvis multi-vægt-UI'en ikke er åben → åbn den.
                    2. Hvis UI er åben OG mindst 1 vægt > 0 → afslut direkte.
                  Dette eliminerer den tidligere gule "Afslut tur"-knap
                  inde i UI'en og forhindrer dobbelt-CTA-forvirring. */}
              <button
                onClick={() => {
                  if (tour.completed) return;
                  if (hasCapture && onOpenFinish) { onOpenFinish(tour); return; }
                  const tt = (tour.tour_type || "normal");
                  if ((tt === "loes_afhentning" || isMultiLoadTour) && askingWeight) {
                    // UI er åben - afslut hvis valid
                    handleConfirmLooseWeights();
                    return;
                  }
                  handleCompleteClick();
                }}
                disabled={tour.completed}
                aria-disabled={tour.completed}
                className={`px-3 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 ${
                  tour.completed
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 cursor-not-allowed opacity-70"
                    : "bg-emerald-500 text-white hover:bg-emerald-600"
                }`}
                data-testid="mobile-tour-panel-complete"
                title={tour.completed ? "Turen er afsluttet - brug 'Fortryd' for at nulstille" : "Afslut tur"}
              >
                <CheckCircle2 className="w-4 h-4" /> {tour.completed ? "Afsluttet ✓" : "Afslut"}
              </button>
              {/* Fase 15.52 (2026-02-22): "Kan ikke gennemføres" - synlig
                  KUN når turen er PÅ VEJ + ikke afsluttet. Chauffør angiver
                  obligatorisk kommentar, turen forsvinder fra chauffør-listen
                  og dukker op hos logistik-admin for gen-aktivering. */}
              {tour.on_way && !tour.completed && (
                <button
                  onClick={() => setShowNotCompletedDialog(true)}
                  className="col-span-2 px-3 py-2 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 bg-rose-500/15 text-rose-600 dark:text-rose-300 hover:bg-rose-500/25 border border-rose-500/40"
                  data-testid="mobile-tour-panel-not-completed"
                  title="Marker turen som ikke-gennemførbar (kræver kommentar)"
                >
                  <AlertTriangle className="w-4 h-4" /> Kan ikke gennemføres
                </button>
              )}
            </>
          )}
          {/* Chat-knap fjernet (Fase 12 - 2026-06-18): tur-vinduet skal kun
              have 3 knapper: På vej, Afslut, Fortryd (= tidligere "Tilbage").
              Fase 14 (2026-06-19): "Fortryd" vises KUN når turen er aktivt
              "på vej" - ikke på afsluttede ture.
              Fase 15.11 (2026-02-XX): "Fortryd" vises NU også på admin-tildelte
              ture (assigned_by_id sat) - men knappens semantik er ændret: den
              nulstiller kun PÅ VEJ → VENTER, og tildelingen forbliver intakt
              (driver_id + assigned_by_* bevares). For ikke-tildelte ture
              fungerer den som før: turen frigives så andre kan tage den. */}
          {!isClaimedByOther && tour.on_way && !tour.completed && (
            <button
              onClick={handleRelease}
              className="px-3 py-2.5 rounded-lg font-semibold text-sm bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600 flex items-center justify-center gap-2 col-span-2"
              data-testid="mobile-tour-panel-release"
              title={tour.assigned_by_id
                ? "Fortryd kørsel - turen skifter til VENTER men forbliver tildelt dig"
                : "Fortryd kørsel - frigiv turen så andre kan tage den"
              }
            >
              <RotateCcw className="w-4 h-4" /> Fortryd
            </button>
          )}
          {!isClaimedByOther && tour.on_way && !tour.completed && tour.assigned_by_id && (
            <div className="col-span-2 px-2 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/30 text-center text-[10px] text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800" data-testid="mobile-tour-panel-admin-locked">
              <Users className="w-3 h-3 inline mr-1" />
              Tildelt af {tour.assigned_by_name || "administrator"} - kontakt din logistikadmin for at frigøre helt.
            </div>
          )}
          {isClaimedByOther && (
            <div className="col-span-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-center text-sm text-slate-600 dark:text-slate-300" data-testid="mobile-tour-panel-locked-notice">
              🔒 Denne tur er taget af <b>{tour.claimed_by}</b>
            </div>
          )}
        </div>
      </div>
      {/* Fase 15.52 (2026-02-22): "Kan ikke gennemføres"-dialog */}
      {showNotCompletedDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
             onClick={() => !submittingNotCompleted && setShowNotCompletedDialog(false)}
             data-testid="not-completed-dialog">
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden border border-rose-500/40"
               onClick={(e) => e.stopPropagation()}>
            <div className="p-5">
              <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-rose-500/10 ring-8 ring-inset ring-rose-500/30 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-rose-500" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white text-center mb-1">Kan ikke gennemføres?</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 text-center mb-3">
                Turen markeres som ikke-gennemført og forsvinder fra din liste.
                Logistik-admin kan gen-aktivere turen senere.
              </p>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                Årsag <span className="text-rose-500">*</span>
              </label>
              {deviationCodes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2" data-testid="not-completed-codes">
                  {deviationCodes.map(code => (
                    <button key={code} type="button" onClick={() => setNotCompletedCode(c => (c === code ? "" : code))}
                      className={`px-3 py-1.5 rounded-full border text-xs font-semibold ${notCompletedCode === code ? "bg-rose-600 border-rose-600 text-white" : "border-slate-300 text-slate-600 dark:text-slate-300"}`}>{code}</button>
                  ))}
                </div>
              )}
              <textarea
                value={notCompletedReason}
                onChange={(e) => setNotCompletedReason(e.target.value)}
                placeholder={notCompletedCode ? "Kort forklaring (valgfri)" : "Beskriv årsagen - f.eks. lukket, ingen adgang, forkert adresse"}
                rows={3}
                className="w-full px-3 py-2 rounded-lg border-2 border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm focus:outline-none focus:border-rose-500 placeholder:text-slate-400"
                data-testid="not-completed-reason-input"
                autoFocus
              />
            </div>
            <div className="flex gap-2 p-4 bg-slate-50 dark:bg-slate-950/40">
              <button
                onClick={() => { setShowNotCompletedDialog(false); setNotCompletedReason(""); }}
                disabled={submittingNotCompleted}
                className="flex-1 px-4 py-2 rounded-xl text-sm font-semibold text-slate-700 dark:text-slate-200 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300"
                data-testid="not-completed-cancel-btn"
              >
                Annullér
              </button>
              <button
                onClick={handleConfirmNotCompleted}
                disabled={submittingNotCompleted || (!notCompletedReason.trim() && !notCompletedCode)}
                className="flex-1 px-4 py-2 rounded-xl text-sm font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 inline-flex items-center justify-center gap-1.5"
                data-testid="not-completed-confirm-btn"
              >
                {submittingNotCompleted ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />}
                Bekræft
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Fase 17.5 (2026-02-27): Preview-only modal. handleFile + label
          ligger i panelet - modal'en aktiveres når et billede er
          behandlet og vises som preview. */}
      <OCRReceiptScanner
        open={scannerOpen}
        onClose={() => {
          setScannerOpen(false);
          setScannerPreview({ base64: "", dataUrl: "", sizeKB: 0 });
        }}
        isLoose={scannerTarget.mode === "loose"}
        imageBase64={scannerPreview.base64}
        previewDataUrl={scannerPreview.dataUrl}
        sizeKB={scannerPreview.sizeKB}
        title={
          scannerTarget.mode === "loose"
            ? `Scan kvittering - container ${scannerTarget.rowIdx + 1}`
            : "Scan kvittering"
        }
        onRetake={() => {
          // Luk modalen og ryd file-input.value så samme fil kan vælges igen.
          setScannerOpen(false);
          setScannerPreview({ base64: "", dataUrl: "", sizeKB: 0 });
          try {
            const inpId = scannerTarget.mode === "loose"
              ? `loose-camera-input-${scannerTarget.rowIdx}`
              : "receipt-camera-input";
            const inp = document.getElementById(inpId);
            if (inp) inp.value = "";
          } catch (_) { /* ignore */ }
          toast.message("Tryk \"Scan kvittering\" igen for at tage et nyt billede");
        }}
        onConfirm={({ imageBase64, previewDataUrl, contentType }) => {
          const payload = { base64: imageBase64, previewDataUrl, contentType };
          if (scannerTarget.mode === "loose" && scannerTarget.rowIdx >= 0) {
            setPendingLooseReceipts(prev => ({ ...prev, [scannerTarget.rowIdx]: payload }));
          } else {
            setPendingReceiptImage(payload);
            setAskingWeight(true);
          }
          setScannerOpen(false);
          setScannerPreview({ base64: "", dataUrl: "", sizeKB: 0 });
          // Ryd file-input så samme fil kan vælges igen senere.
          try {
            const inpId = scannerTarget.mode === "loose"
              ? `loose-camera-input-${scannerTarget.rowIdx}`
              : "receipt-camera-input";
            const inp = document.getElementById(inpId);
            if (inp) inp.value = "";
          } catch (_) { /* ignore */ }
          toast.success("Billede vedhæftet - indtast vægt for at gemme");
        }}
      />

      {/* Fase 18.7 (2026-02-28): Quick-viewer for allerede-uploadede kvitteringer
          på den løse afhentning. Henter billede via /image-binary (blob) så
          chaufføren kan verificere at en gemt kvittering ER den rigtige. */}
      {viewerReceiptId && (
        <DriverReceiptQuickViewer
          receiptId={viewerReceiptId}
          onClose={() => setViewerReceiptId(null)}
        />
      )}
      {trailerAsk && (
        <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={(e) => { e.stopPropagation(); trailerAsk.resolve(null); }}>
          <div className="w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl bg-white dark:bg-slate-900 p-5 space-y-4" style={{ paddingBottom: "calc(1.25rem + env(safe-area-inset-bottom))" }}
            onClick={(e) => e.stopPropagation()} data-testid="trailer-confirm">
            <div>
              <div className="text-lg font-bold text-slate-900 dark:text-white">Kørte du med hænger?</div>
              <p className="text-sm text-slate-500 mt-1">Forudfyldt fra din profil. Bruges til afregningen af turen (hængertillæg).</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[[true, "Ja, med hænger"], [false, "Nej, uden"]].map(([v, l]) => (
                <button key={l} type="button" onClick={() => trailerAsk.resolve(v)} data-testid={`trailer-confirm-${v ? "yes" : "no"}`}
                  className={`py-4 rounded-xl text-base font-bold border-2 ${v === (tour.used_trailer === true) ? "border-emerald-600 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200" : "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`}>{l}</button>
              ))}
            </div>
            <button type="button" className="w-full py-2 text-sm text-slate-500" onClick={() => trailerAsk.resolve(null)}>Annuller</button>
          </div>
        </div>
      )}
    </div>
  );
};

// Fase 18.7 (2026-02-28): Chauffør-quickviewer for én kvittering. Bruger
// blob-streaming så vi ikke trækker hele base64-payloaden gennem JSON.
function DriverReceiptQuickViewer({ receiptId, onClose }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setBlobUrl(null);
    (async () => {
      try {
        const res = await axios.get(`${API}/receipts/${receiptId}/image-binary`, { responseType: "blob" });
        if (!active) return;
        setBlobUrl(URL.createObjectURL(res.data));
      } catch (e) {
        if (active) setError(e?.response?.data?.detail || "Kunne ikke hente billede");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [receiptId]);
  useEffect(() => () => { if (blobUrl) URL.revokeObjectURL(blobUrl); }, [blobUrl]);
  return (
    <div className="fixed inset-0 z-[70] bg-black/80 flex items-center justify-center p-3" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }} data-testid="driver-receipt-viewer">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <h3 className="font-bold text-sm">Kvittering</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="driver-receipt-viewer-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-auto bg-slate-100 dark:bg-slate-950 flex items-center justify-center p-3">
          {loading && <Loader2 className="w-6 h-6 animate-spin text-slate-400" />}
          {error && <span className="text-rose-600 text-sm">{error}</span>}
          {blobUrl && <img src={blobUrl} alt="Kvittering" className="max-w-full max-h-[75vh] object-contain rounded shadow" />}
        </div>
      </div>
    </div>
  );
}

function App() {
  // ============= MULTI-TENANT AUTH =============
  const { user: authUser, logout: authLogout } = useAuth();

  // Page routing state - check hash + pathname for the order page.
  // Two entry points are supported:
  //   1. Hash route:   /#order           - legacy, shows the kode-input form
  //   2. Path route:   /order/<code>     - direct QR-code deep link (preferred)
  //                    /bestilling/<code>
  // The path-based entry skips the kode-input form and goes straight to
  // step 1 with the location code baked in.
  const _initialOrderState = (() => {
    const hash = window.location.hash;
    if (hash === "#order" || hash === "#bestilling") {
      return { page: "customer_code", code: null };
    }
    const m = window.location.pathname.match(/^\/(?:order|bestilling)\/([A-Za-z0-9_-]+)\/?$/);
    if (m && m[1]) {
      return { page: "customer_order", code: m[1] };
    }
    return { page: "main", code: null };
  })();

  const [currentPage, setCurrentPage] = useState(_initialOrderState.page);
  const [customerLocationCode, setCustomerLocationCode] = useState(_initialOrderState.code);
  const [customerPladsName, setCustomerPladsName] = useState("");
  const [customerPrefillAddress, setCustomerPrefillAddress] = useState("");

  // Listen for hash changes
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      if (hash === "#order" || hash === "#bestilling") {
        setCurrentPage("customer_code");
        setCustomerLocationCode(null);
      } else if (hash === "" || hash === "#") {
        setCurrentPage("main");
      }
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);
  
  // Auth state
  const [isAdmin, setIsAdmin] = useState(false);
  const [showAdminLogin, setShowAdminLogin] = useState(false);
  const [adminUser, setAdminUser] = useState("");
  const [adminPass, setAdminPass] = useState("");

  // Sync new auth user → existing legacy state.
  // - logistics_admin → auto enter Admin Page (existing AdminPage)
  // - driver → auto-fill driver name and skip the 3-step setup
  useEffect(() => {
    if (!authUser) return;
    if (authUser.role === "logistics_admin") {
      setIsAdmin(true);
    } else if (authUser.role === "driver") {
      const name = (authUser.driver_name || authUser.name || "").trim();
      if (name) {
        try { localStorage.setItem("korkman2_driver_name", name); } catch (_) { /* ignore */ }
        setDriverName(name);
        // Fase 5: Postpone vehicle-step decision until we know whether an
        // active customer has been picked. The driver-customer bootstrap
        // useEffect below handles the routing.
        const veh = (() => { try { return localStorage.getItem("korkman2_vehicle_reg") || ""; } catch (_) { return ""; } })();
        if (!veh) {
          setSetupName(name);
        }
      }
    }
  }, [authUser]);

  // Driver setup state - check localStorage
  const [driverSetupDone, setDriverSetupDone] = useState(() => {
    return !!localStorage.getItem("korkman2_driver_name");
  });
  const [setupStep, setSetupStep] = useState(1); // 1=login-redirect (deprecated), 2=greet, 3=customer-picker, 4=plate (Vognnummer), 5=trailer (Hænger)
  const [setupEmail, setSetupEmail] = useState("");
  const [setupName, setSetupName] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [setupPlate, setSetupPlate] = useState(() => {
    return localStorage.getItem("korkman2_vehicle_reg") || "";
  });
  // Fase 10 (2026-06-17): chaufføren vælger ÉN vogn + (valgfri) ÉN hænger
  // fra logistik-virksomhedens centrale lister ved login.
  const [vehiclesList, setVehiclesList] = useState([]);
  const [trailersList, setTrailersList] = useState([]);
  const [setupVehicleId, setSetupVehicleId] = useState("");
  const [setupTrailerId, setSetupTrailerId] = useState(""); // "" = ingen hænger
  // Fase 5: active customer selection (multi-tenant chauffør-side)
  const [driverCustomers, setDriverCustomers] = useState([]);
  const [activeCustomer, setActiveCustomer] = useState(null); // { id, name, customer_id, city }
  const [customerSwitchOpen, setCustomerSwitchOpen] = useState(false);

  // Fase 5 bootstrap: when driver logs in, fetch their customer list + current
  // active customer, then route to the appropriate setup step:
  //   - 0 customers → driver has nothing to do (LA must assign their company
  //     to a customer first); show a friendly empty state.
  //   - 1 customer → auto-select it. Then continue with plate (step 4) or full UI.
  //   - 2+ customers and no active → step 3 (customer picker).
  //   - active customer already set + no plate → step 4 (plate picker).
  //   - active + plate → setupDone, show driver UI.
  useEffect(() => {
    if (!authUser || authUser.role !== "driver") return;
    let cancelled = false;
    (async () => {
      try {
        const [custRes, activeRes] = await Promise.all([
          axios.get(`${API}/driver/customers`),
          axios.get(`${API}/driver/active-customer`),
        ]);
        if (cancelled) return;
        const custs = Array.isArray(custRes.data) ? custRes.data : [];
        setDriverCustomers(custs);
        const currentActive = activeRes.data?.customer || null;
        const veh = (() => { try { return localStorage.getItem("korkman2_vehicle_reg") || ""; } catch (_) { return ""; } })();

        if (currentActive) {
          setActiveCustomer(currentActive);
          if (veh) {
            setDriverSetupDone(true);
          } else {
            setSetupStep(4);
          }
          return;
        }
        // No active customer yet (Fase 11 - 2026-06-17: ALDRIG auto-vælg
        // kunde, selv hvis der kun er én. Brugeren ønsker aktivt valg fra
        // chaufføren - han skal bekræfte hvem han kører for i dag.)
        // 2026-10-16: Undtagelse - et premium-logistikfirma uden kunder har
        // kun "Egne ture"; der er ingen kunde at bekræfte, så valget springes over.
        if (custs.length === 1 && custs[0].own) {
          await axios.post(`${API}/driver/active-customer`, { customer_id: custs[0].id });
          if (cancelled) return;
          setActiveCustomer(custs[0]);
          if (veh) setDriverSetupDone(true); else setSetupStep(4);
          return;
        }
        setSetupStep(3);  // show customer picker (works for 1, 2, or 0 customers)
      } catch (e) {
        // Fallback: skip to plate step
        setSetupStep(4);
      }
    })();
    return () => { cancelled = true; };
  }, [authUser]);

  // Fase 11 (2026-06-18): Hent driver's nuværende active_trailer_id fra
  // /auth/me så hænger-skift-dropdownen kan vise nuværende valg.
  useEffect(() => {
    if (!authUser || authUser.role !== "driver") return;
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/auth/me`);
        if (!cancelled) setActiveTrailerId(r.data?.active_trailer_id || "");
      } catch (_) { /* swallow */ }
    })();
    return () => { cancelled = true; };
  }, [authUser]);

  // Fase 11 (2026-06-18): Skift hænger fra driver-headeren.
  const handleChangeTrailer = async (trailerId) => {
    try {
      await axios.post(`${API}/driver/active-vehicle-trailer`, {
        active_trailer_id: trailerId || "",
      });
      setActiveTrailerId(trailerId || "");
      setShowTrailerDropdown(false);
      const tr = trailersList.find(t => t.id === trailerId);
      toast.success(trailerId
        ? `Hænger skiftet til ${tr?.number || "ny hænger"}`
        : "Hænger fjernet");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke skifte hænger");
    }
  };

  // Fase 5: switch active customer (from header dropdown or initial picker)
  const handleSwitchCustomer = async (customer) => {
    if (!customer || !customer.id) return;
    try {
      await axios.post(`${API}/driver/active-customer`, { customer_id: customer.id });
      setActiveCustomer(customer);
      // Clear all in-memory data so next fetch repopulates from the new customer
      setTours([]);
      setPladsList([]);
      setSelectedPlads("");
      setCustomerFilter("");
      setRouteOptimization(null);
      setCustomerSwitchOpen(false);
      toast.success(`Skiftede til ${customer.name}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke skifte kunde");
    }
  };

  // Data state
  const [drivers, setDrivers] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [tours, setTours] = useState([]);
  const [reportId, setReportId] = useState("");
  const [pladsList, setPladsList] = useState([]); // Dynamic plads list from DB
  
  // Filter state
  const [selectedPlads, setSelectedPlads] = useState("");
  // Fase 15.5 (2026-06-19): Sekundær plads-filter der KUN er aktiv når
  // selectedPlads === "__MINE__". Tom streng = "alle mine pladser".
  // Chaufføren kan via en separat dropdown filtrere deres egne ture på en
  // specifik plads UDEN at skifte hovedvalg.
  const [mineSelectedPlads, setMineSelectedPlads] = useState("");
  const [tourSearch, setTourSearch] = useState(""); // Driver UI: filter tours by fraction (materyal)
  const [customerFilter, setCustomerFilter] = useState(""); // Driver UI: scope tour list by customer (ARGO / MARTO / ...)
  
  // Form state - init from localStorage
  const [driverName, setDriverName] = useState(() => {
    return localStorage.getItem("korkman2_driver_name") || "";
  });
  const [vehicleReg, setVehicleReg] = useState(() => {
    return localStorage.getItem("korkman2_vehicle_reg") || "";
  });
  // Local date helper (avoids UTC timezone shift)
  const getLocalDateStr = (d = new Date()) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const [startTime, setStartTime] = useState("07:00");
  const [endTime, setEndTime] = useState("");
  const [reportDate, setReportDate] = useState(getLocalDateStr());

  // Date navigation helpers
  const navigateDate = (days) => {
    const d = new Date(reportDate + "T12:00:00");
    d.setDate(d.getDate() + days);
    setTours([]); // Clear tours immediately for daily separation
    setRouteOptimization(null);
    setReportDate(getLocalDateStr(d));
  };
  const goToToday = () => { setTours([]); setRouteOptimization(null); setReportDate(getLocalDateStr()); setCustomerFilter(""); };
  const isToday = reportDate === getLocalDateStr();
  // Fase 15.1 (2026-06-19): "Ind"/"Ud" må kun trigges på dags dato.
  // "Manuel" må kun trigges for i dag eller tidligere datoer (ikke fremtid).
  const isFuture = reportDate > getLocalDateStr();
  const formatDateLabel = (dateStr) => {
    const today = getLocalDateStr();
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterday = getLocalDateStr(yesterdayDate);
    if (dateStr === today) return "I dag";
    if (dateStr === yesterday) return "I går";
    return new Date(dateStr + "T12:00:00").toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" });
  };
  const [customPlads, setCustomPlads] = useState("");
  const [notes, setNotes] = useState("");
  
  // Manual tour form
  const [manualFraction, setManualFraction] = useState("");
  const [manualFacility, setManualFacility] = useState("");
  const [manualAddress, setManualAddress] = useState("");
  const [manualContainer, setManualContainer] = useState("");
  const [isSameDay, setIsSameDay] = useState(false);
  const [isPrivateTour, setIsPrivateTour] = useState(false);
  const [privateCompany, setPrivateCompany] = useState("");
  
  // Materials list from backend
  const [materialsList, setMaterialsList] = useState([]);
  
  // Dropdown states
  const [showPladsDropdown, setShowPladsDropdown] = useState(false);
  const [showPlateDropdown, setShowPlateDropdown] = useState(false);
  // Fase 11 (2026-06-18): Chauffør kan skifte hænger fra driver-headeren -
  // ikke kun ved login. activeTrailerId hentes fra /api/auth/me.
  const [activeTrailerId, setActiveTrailerId] = useState("");
  const [showTrailerDropdown, setShowTrailerDropdown] = useState(false);
  const [toolbarExpanded, setToolbarExpanded] = useState(false);

  // Fase 18.13 (2026-02-28): Mobile bottom-nav 3-tab struktur (Tid/Ture/Profil).
  // Kun mobil - md:hidden wrapper styrer dette. Desktop er urørt.
  const [activeTab, setActiveTab] = useState('tid');
  // Fase 18.15 (2026-02-28): Inline-picker på Profil-tab. Værdier:
  // 'vehicle' | 'plads' | null - ingen redirect til Ture-tab.
  const [profilPicker, setProfilPicker] = useState(null);
  // Fase 18.17 (2026-02-28): Inline plads-picker på Ture-tab ("Lokation"-knap).
  const [turePladsPickerOpen, setTurePladsPickerOpen] = useState(false);
  // Fase 18.17: Dropdown-menu for "Dagens stempling/manuel" + "Afslut dag".
  const [tidMenuOpen, setTidMenuOpen] = useState(false);
  useEffect(() => {
    // Skift body baggrund så pinch-zoom på mobil ikke viser hvid kant.
    const prev = document.body.style.backgroundColor;
    document.body.style.backgroundColor = activeTab === 'tid' ? '#0f0f0f' : '#f4f4f5';
    return () => { document.body.style.backgroundColor = prev; };
  }, [activeTab]);

  // Route optimization state
  const [routeOptimization, setRouteOptimization] = useState(null);
  const [isOptimizing, setIsOptimizing] = useState(false);
  // Fase 12 (2026-06-18): Ruteoptimering er SLUKKET som standard.
  // Chaufføren skal selv aktivere via "Optimer rute"-knappen.
  // Persistér valget i localStorage så den huskes på samme device.
  const [routeOptEnabled, setRouteOptEnabled] = useState(() => {
    try { return localStorage.getItem("cf:driver:routeOpt") === "1"; }
    catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("cf:driver:routeOpt", routeOptEnabled ? "1" : "0"); }
    catch {}
  }, [routeOptEnabled]);

  // Auto-optimize route when plads or date changes - kun hvis chaufføren
  // har aktiveret optimering.
  const autoOptimizeRef = useRef(null);
  const toursRef = useRef(tours);
  useEffect(() => { toursRef.current = tours; }, [tours]);

  useEffect(() => {
    if (!selectedPlads || !routeOptEnabled) { setRouteOptimization(null); return; }
    if (autoOptimizeRef.current) clearTimeout(autoOptimizeRef.current);
    setRouteOptimization(null);
    autoOptimizeRef.current = setTimeout(() => {
      const currentTours = toursRef.current;
      const activeTours = currentTours.filter(t => t.plads === selectedPlads && !t.is_pause);
      if (activeTours.length === 0) { setRouteOptimization(null); return; }
      setIsOptimizing(true);
      axios.post(`${API}/optimize-route`, {
        plads_name: selectedPlads,
        tour_ids: activeTours.map(t => t.id),
      }).then(res => {
        if (res.data.optimized) {
          setRouteOptimization(res.data);
          const orderMap = {};
          res.data.tours.forEach(t => { orderMap[t.tour_id] = t; });
          setTours(prev => {
            const otherTours = prev.filter(t => t.plads !== selectedPlads || t.is_pause);
            const pladsTours = prev.filter(t => t.plads === selectedPlads && !t.is_pause);
            const sorted = [...pladsTours].sort((a, b) => {
              const oa = orderMap[a.id]?.route_order ?? 999;
              const ob = orderMap[b.id]?.route_order ?? 999;
              return oa - ob;
            });
            return [...otherTours, ...sorted];
          });
        } else {
          setRouteOptimization(null);
        }
      }).catch(() => {
        setRouteOptimization(null);
      }).finally(() => {
        setIsOptimizing(false);
      });
    }, 800);
    return () => { if (autoOptimizeRef.current) clearTimeout(autoOptimizeRef.current); };
  }, [selectedPlads, reportDate, routeOptEnabled]);

  // Mobile tour panel state
  const [selectedTourForPanel, setSelectedTourForPanel] = useState(null);
  // 2026-10-16: Tur-beskeder (planlægger <-> chauffør) - ulæste pr. tur + åben tråd.
  const [driverTourUnread, setDriverTourUnread] = useState({});
  const [chatTour, setChatTour] = useState(null);
  // 2026-10-17: "Afslut tur"-ark for ture med "Ved afslutning"-valg (capture).
  const [finishTour, setFinishTour] = useState(null);
  // 2026-10-18: Firmaets indstillinger til afslutningsarket (afvigelseskoder,
  // "Ét afslutningsark" for alle ture).
  const [finishSettings, setFinishSettings] = useState({ codes: [], unified_finish: false });
  useEffect(() => {
    if (authUser?.role !== "driver") return;
    axios.get(`${API}/driver/finish-settings`).then(r => setFinishSettings(r.data || {})).catch(() => {});
  }, [authUser?.role, authUser?.id]);
  // Offline-køen: sig til hvis serveren afviste en handling der blev sendt senere.
  useEffect(() => subscribeOps((_n, ev) => {
    if (ev?.type === "rejected") toast.error(`En handling fra da du var offline blev afvist: ${ev.message}`, { duration: 8000 });
    if (ev?.type === "sent" && authUser?.role === "driver") fetchTours();
  }), [authUser?.role]); // eslint-disable-line react-hooks/exhaustive-deps
  const driverUnreadTotalRef = useRef(null);
  const [inlineWeightTourId, setInlineWeightTourId] = useState(null);
  const [showInlineScanner, setShowInlineScanner] = useState(false);
  const [inlineWeight, setInlineWeight] = useState("");
  const [inlinePlate, setInlinePlate] = useState("");

  // Messages for driver
  const [driverMessages, setDriverMessages] = useState([]);
  const [showMessages, setShowMessages] = useState(false);
  
  // Incoming message auto-popup
  const [incomingMessage, setIncomingMessage] = useState(null); // { id, from_driver_name, content, created_at, from_admin }
  const [incomingReplyText, setIncomingReplyText] = useState("");
  const [incomingReplyMode, setIncomingReplyMode] = useState(false);
  const seenMessageIdsRef = useRef(new Set());
  
  // Active pause timer
  const [activePause, setActivePause] = useState(null); // { endMs: number, minutes: number }
  const [pauseRemainingSec, setPauseRemainingSec] = useState(0);
  
  // Chat system - private messaging
  const [showChat, setShowChat] = useState(false);
  // Light/Dark theme toggle (driver-only)
  const [lightMode, setLightMode] = useState(() => {
    try { return localStorage.getItem("driver_light_mode") === "1"; } catch { return false; }
  });
  const toggleTheme = () => {
    setLightMode(prev => {
      const next = !prev;
      try { localStorage.setItem("driver_light_mode", next ? "1" : "0"); } catch { /* noop */ }
      return next;
    });
  };
  // God morgen hero card dismissal (per-day via sessionStorage)
  const [heroDismissed, setHeroDismissed] = useState(false);
  useEffect(() => {
    try {
      const dateKey = new Date().toISOString().slice(0, 10);
      setHeroDismissed(!!sessionStorage.getItem(`hero_dismissed_${dateKey}`));
    } catch (e) { /* noop */ }
  }, []);
  const dismissHero = () => {
    try {
      const dateKey = new Date().toISOString().slice(0, 10);
      sessionStorage.setItem(`hero_dismissed_${dateKey}`, "1");
    } catch (e) { /* noop */ }
    setHeroDismissed(true);
  };
  const [showReceiptScanner, setShowReceiptScanner] = useState(false);
  const [receipts, setReceipts] = useState([]);
  const [viewingReceipt, setViewingReceipt] = useState(null);
  const [showReceiptList, setShowReceiptList] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [chatRecipient, setChatRecipient] = useState("admin"); // "admin" or driver name
  const [availableDrivers, setAvailableDrivers] = useState([]); // Other drivers for chat
  
  // Drag and drop state
  const [draggedTour, setDraggedTour] = useState(null);
  
  // Driver tab navigation
  const [activeDriverTab, setActiveDriverTab] = useState("trips");
  // Fase 12 (2026-06-18): Manuel tidsregistrering modal - dag-niveau fallback
  // for når chaufføren glemmer at stemple ind/ud.
  const [manualTimeModalOpen, setManualTimeModalOpen] = useState(false);
  // Fase 15.31 (2026-02-22): Edit-mode for manuelt-oprettede entries.
  // Når chaufføren klikker "Rediger" på en egen manuel entry sættes denne;
  // ManualPunchEditModal vises og kan PATCH'e backend.
  const [editEntry, setEditEntry] = useState(null);
  // Fase 15.32 (2026-02-22): To-trins slet-bekræftelse - første klik sætter
  // entry.id som "pending delete", andet klik udfører faktisk soft-delete.
  // Robust mod blokeret window.confirm i PWA-context.
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  // Fase 15.28 (2026-02-22): Per-firma indstilling for om "Årsag"-feltet er
  // obligatorisk ved manuel stempel - hentes ved login så modalen kan
  // tvinge feltet udfyldt.
  const [requireDriverPunchReason, setRequireDriverPunchReason] = useState(false);
  // Fase 13 (2026-06-18): Multiple Ind/Ud-stempling pr. dag. timeEntries
  // er listen af dagens perioder (open + lukkede). showTimeOverview viser
  // det fulde overblik i en modal.
  const [timeEntries, setTimeEntries] = useState([]);
  const [showTimeOverview, setShowTimeOverview] = useState(false);
  // Fase 15.1 (2026-06-19) + Fase 15.2 (2026-06-19): "Vis afventende ture"-
  // toggle. Når TRUE udvider chaufførens tur-liste med alle ikke-afsluttede
  // ture fra i dag og tidligere dage (fra ALLE pladser chaufføren har adgang
  // til). Ingen modal længere - turene vises direkte i hovedlisten så
  // chaufføren kan starte dem fra samme view. Original `date`-felt på
  // turen ændres ikke.
  // 2026-10-17: Ledige ture fra tidligere dage vises altid (under "Ledige" ›
  // "Fra tidligere dage") - før lå de bag en skjult "Afventende"-knap.
  const [showPendingInList, setShowPendingInList] = useState(true);

  // Hent dagens stempling-perioder
  const fetchTimeEntries = useCallback(async () => {
    if (!reportDate) return;
    try {
      const r = await axios.get(`${API}/driver/time-entries?date_from=${reportDate}&date_to=${reportDate}`);
      setTimeEntries(r.data || []);
    } catch (_) { /* swallow */ }
  }, [reportDate]);
  // 2026-10-16: Hent også igen når brugeren logger ind - komponenten er
  // monteret før login, så første kald fik 401 og "Timer i dag" stod på 0.
  useEffect(() => { fetchTimeEntries(); }, [fetchTimeEntries, authUser?.id]);

  // Fase 15.28 (2026-02-22): Hent punch-reason-indstilling så manuel
  // stempel-modal'en ved om Årsag-feltet er obligatorisk.
  useEffect(() => {
    if (!authUser) return;
    (async () => {
      try {
        const r = await axios.get(`${API}/company/punch-reason-settings`);
        setRequireDriverPunchReason(!!r.data?.require_driver_punch_reason);
      } catch (_) { /* swallow */ }
    })();
  }, [authUser]);

  // Stempl ind eller ud
  const handlePunch = async (type, opts = {}) => {
    try {
      const now = getCurrentTime();
      const body = { date: reportDate, time: now, type };
      // Fase 15.30 (2026-02-22): slice_type sendes kun for IND. Default "work".
      // Når chaufføren trykker "Start pause" sendes slice_type="pause". Når
      // chaufføren trykker "Start arbejde" (i pause) sendes slice_type="work".
      if (type === "ind") body.slice_type = opts.sliceType || "work";
      const r = await axios.post(`${API}/driver/time-entries/punch`, body);
      // Sync startTime/endTime så collapsed-toolbar viser ind-tid
      if (type === "ind") {
        setStartTime(now);
        setEndTime("");
        if (body.slice_type === "pause") {
          toast.success(`Pause startet kl. ${now}`);
        } else {
          // Tjek om dette var en pause-til-arbejde transition (returneret
          // slice_type=work men der var en pause-slice åben før).
          toast.success(`Stemplet ind kl. ${now}`);
        }
      } else {
        setEndTime(now);
        const dur = r.data?.duration_minutes || 0;
        const hh = Math.floor(dur / 60);
        const mm = dur % 60;
        toast.success(`Stemplet ud kl. ${now} - ${hh}t ${String(mm).padStart(2, "0")}m`);
      }
      fetchTimeEntries();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Stempling fejlede");
    }
  };
  // Fase 11 (2026-06-18): Skjul færdiggjorte ture fra hovedlisten -
  // chaufføren klikker "Vis færdiggjorte" for at se dem.
  const [showCompletedDriver, setShowCompletedDriver] = useState(() => {
    try { return localStorage.getItem("cf:driver:showCompleted") === "1"; }
    catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("cf:driver:showCompleted", showCompletedDriver ? "1" : "0"); }
    catch {}
  }, [showCompletedDriver]);
  const [isScrolled, setIsScrolled] = useState(false);
  // Fase 15.13 (2026-02-XX): Collapsible "Ture hos andre chauffører" på
  // lokationssider. Pre-collapsed pr. session, læser/skriver i localStorage
  // så valget overlever refresh.
  const [otherDriverSectionOpen, setOtherDriverSectionOpen] = useState(() => {
    try { return localStorage.getItem("cf:driver:otherSectionOpen") === "1"; }
    catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("cf:driver:otherSectionOpen", otherDriverSectionOpen ? "1" : "0"); }
    catch {}
  }, [otherDriverSectionOpen]);
  
  // Online status
  const isOnline = useOnlineStatus();
  const { canInstall, isInstalled, install: installPWA } = usePWAInstall();
  const [showInstallBanner, setShowInstallBanner] = useState(true);

  // Sync offline queue when back online
  useEffect(() => {
    if (isOnline) {
      syncOfflineQueue();
    }
  }, [isOnline]);

  // Scroll detection for sticky controls
  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 60);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Get plads names from dynamic list
  const pladsOptions = pladsList.map(p => p.name);

  // Receipt handlers
  const fetchReceipts = async () => {
    try {
      const res = await axios.get(`${API}/receipts`, { params: { driver_name: driverName } });
      setReceipts(res.data);
    } catch (e) {
      console.error("Error fetching receipts:", e);
    }
  };

  const handleSaveReceipt = async (receiptData) => {
    try {
      await axios.post(`${API}/receipts`, receiptData);
      await fetchReceipts();
      toast.success("Kvittering gemt!");
    } catch (e) {
      console.error("Error saving receipt:", e);
      toast.error("Kunne ikke gemme kvittering");
    }
  };

  const handleDeleteReceipt = async (id) => {
    try {
      await axios.delete(`${API}/receipts/${id}`);
      setReceipts(receipts.filter(r => r.id !== id));
      toast.success("Kvittering slettet");
    } catch (e) {
      console.error("Error deleting receipt:", e);
      toast.error("Kunne ikke slette kvittering");
    }
  };

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = () => {
      setShowPladsDropdown(false);
      setShowPlateDropdown(false);
    };
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  // ============= DRIVER SETUP =============

  const handleSetupCode = async () => {
    if (!setupCode.trim()) { toast.error("Indtast din kode"); return; }
    try {
      // Verify code only
      await axios.post(`${API}/driver/verify-code`, { code: setupCode.trim() });
      setSetupStep(2);
    } catch (e) {
      if (e.response && e.response.status === 401) {
        toast.error("Forkert kode");
      } else {
        toast.error("Netværksfejl - prøv igen");
      }
    }
  };

  const handleSetupName = async () => {
    if (!setupName.trim()) { toast.error("Vælg en chauffør"); return; }
    localStorage.setItem("korkman2_driver_name", setupName.trim());
    setDriverName(setupName.trim());
    setSetupStep(3);
  };

  const handleSetupPlate = async () => {
    if (!setupVehicleId && !setupPlate.trim()) {
      toast.error("Vælg et vognnummer"); return;
    }
    // Persist server-side (binds vehicle to user doc + mirrors `plate`)
    if (setupVehicleId) {
      try {
        await axios.post(`${API}/driver/active-vehicle-trailer`, {
          active_vehicle_id: setupVehicleId,
        });
      } catch (e) { toast.error(formatApiError(e)); return; }
    }
    const chosen = vehiclesList.find(v => v.id === setupVehicleId);
    const display = chosen ? chosen.number : setupPlate.trim();
    localStorage.setItem("korkman2_vehicle_reg", display);
    setVehicleReg(display);
    setSetupPlate(display);
    // Fase 10: next step → vælg hænger (valgfrit). Hvis der ikke er nogen
    // hængere i firmaet, spring direkte til driver-UI.
    if ((trailersList || []).length > 0) {
      setSetupStep(5);
    } else {
      setDriverSetupDone(true);
    }
  };

  const handleSetupTrailer = async (trailerId) => {
    try {
      await axios.post(`${API}/driver/active-vehicle-trailer`, {
        active_trailer_id: trailerId || "",
      });
      setSetupTrailerId(trailerId || "");
      setDriverSetupDone(true);
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const handleChangePlate = (newPlate) => {
    setVehicleReg(newPlate);
    localStorage.setItem("korkman2_vehicle_reg", newPlate);
  };

  const handleLogoutDriver = async () => {
    // End session on server before logout
    try {
      await axios.delete(`${API}/driver-session/${driverName}`);
    } catch (e) {
      console.error("Error ending session:", e);
    }
    
    localStorage.removeItem("korkman2_driver_name");
    localStorage.removeItem("korkman2_vehicle_reg");
    localStorage.removeItem("korkman2_session");
    setDriverName("");
    setVehicleReg("");
    setSetupName("");
    setSetupCode("");
    setSetupPlate("");
    setSetupStep(1);
    setSetupEmail("");
    setDriverSetupDone(false);
    setSelectedPlads("");
    // Also clear JWT auth so the unified login is shown
    if (authUser) {
      try { await authLogout(); } catch (_) { /* ignore */ }
    }
    toast.success("Du er logget ud");
  };
  
  // Save driver session to server
  const saveDriverSession = useCallback(async () => {
    if (!driverName) return;
    
    try {
      const session = {
        driver_name: driverName,
        vehicle_reg: vehicleReg,
        current_plads: selectedPlads,
        start_time: startTime,
        report_date: reportDate
      };
      
      await axios.post(`${API}/driver-session`, session);
      
      // Also save to localStorage for offline
      localStorage.setItem("korkman2_session", JSON.stringify(session));
    } catch (e) {
      console.error("Error saving session:", e);
    }
  }, [driverName, vehicleReg, selectedPlads, startTime, reportDate]);
  
  // Load driver session from server
  const loadDriverSession = useCallback(async () => {
    if (!driverName) return;
    
    try {
      const res = await axios.get(`${API}/driver-session/${driverName}`);
      if (res.data) {
        // Restore session data
        if (res.data.vehicle_reg) setVehicleReg(res.data.vehicle_reg);
        if (res.data.current_plads) setSelectedPlads(res.data.current_plads);
        if (res.data.start_time) setStartTime(res.data.start_time);
        // 2026-10-18: Kun dagens dato genskabes - ellers så chaufføren
        // gårsdagens ture næste morgen (sessionen husker sidste dato).
        if (res.data.report_date && res.data.report_date === getLocalDateStr()) setReportDate(res.data.report_date);
        
        toast.success(`Velkommen tilbage, ${driverName}!`);
      }
    } catch (e) {
      // Try to load from localStorage if offline
      const localSession = localStorage.getItem("korkman2_session");
      if (localSession) {
        const session = JSON.parse(localSession);
        if (session.vehicle_reg) setVehicleReg(session.vehicle_reg);
        if (session.current_plads) setSelectedPlads(session.current_plads);
        if (session.start_time) setStartTime(session.start_time);
      }
    }
  }, [driverName]);
  
  // Fetch messages for this driver (both from admin and other drivers)
  const fetchDriverMessages = useCallback(async () => {
    if (!driverName) return;
    
    try {
      const res = await axios.get(`${API}/messages/driver/${encodeURIComponent(driverName)}`);
      setDriverMessages(res.data || []);
    } catch (e) {
      console.error("Error fetching messages:", e);
    }
  }, [driverName]);
  
  // Fetch available drivers for chat (other active drivers)
  const fetchAvailableDrivers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/drivers`);
      // Filter out current driver
      const others = (res.data || []).filter(d => d.name !== driverName);
      setAvailableDrivers(others);
    } catch (e) {
      console.error("Error fetching drivers:", e);
    }
  }, [driverName]);
  
  // Subscribe to push notifications
  // 2026-10-17: Push er slået TIL igen efter ønske (Fase 15.23 slog det fra).
  // Har chaufføren givet lov, fornyes abonnementet stille ved opstart.
  // Første gang vises en venlig "Slå til"-boks (iOS kræver et tryk), og på
  // iPhone/iPad uden hjemmeskærm-installation en kort guide. Chaufføren kan
  // slå det fra under Profil.
  const [pushPrompt, setPushPrompt] = useState(null); // null | "ask" | "ios-install"
  const [pushOn, setPushOn] = useState(true);
  const subscribeToPush = useCallback(async () => {
    const enabled = authUser?.push_enabled !== false;
    setPushOn(enabled && pushPermission() === "granted");
    if (!enabled) return;
    if (await syncPush(driverName, true)) { setPushOn(true); return; }
    let dismissed = 0;
    try { dismissed = Number(localStorage.getItem("cf_push_prompt_dismissed") || 0); } catch (_) { /* ignore */ }
    if (Date.now() - dismissed < 3 * 86400000) return;
    if (pushSupported() && pushPermission() === "default") setPushPrompt("ask");
    else if (isIOS() && !isStandalone()) setPushPrompt("ios-install");
  }, [authUser, driverName]);
  const dismissPushPrompt = () => {
    try { localStorage.setItem("cf_push_prompt_dismissed", String(Date.now())); } catch (_) { /* ignore */ }
    setPushPrompt(null);
  };
  const handleTogglePush = async (on) => {
    try {
      if (on) { await enablePush(driverName); setPushOn(true); setPushPrompt(null); toast.success("Notifikationer er slået til"); }
      else { await disablePush(); setPushOn(false); toast.success("Notifikationer er slået fra"); }
    } catch (e) {
      toast.error(e?.message || "Kunne ikke ændre notifikationer");
      if (on && isIOS() && !isStandalone()) setPushPrompt("ios-install");
    }
  };
  
  // Send message (to admin or another driver)
  const sendChatMessage = async () => {
    if (!chatMessage.trim()) return;
    
    try {
      if (chatRecipient === "admin") {
        // Message to admin
        await axios.post(`${API}/messages`, {
          to_admin: true,
          from_driver_name: driverName,
          content: chatMessage.trim()
        });
        toast.success("Besked sendt til admin");
      } else {
        // Message to another driver
        await axios.post(`${API}/messages`, {
          to_driver_name: chatRecipient,
          from_driver_name: driverName,
          content: chatMessage.trim()
        });
        toast.success(`Besked sendt til ${chatRecipient}`);
      }
      
      setChatMessage("");
      fetchDriverMessages();
    } catch (e) {
      toast.error("Kunne ikke sende besked");
    }
  };
  
  // Get messages filtered by current chat recipient
  const getFilteredChatMessages = () => {
    if (chatRecipient === "admin") {
      // Messages between this driver and admin
      return driverMessages.filter(m => 
        m.to_admin || m.from_admin
      );
    } else {
      // Messages between this driver and selected driver
      return driverMessages.filter(m => 
        (m.from_driver_name === chatRecipient && m.to_driver_name === driverName) ||
        (m.from_driver_name === driverName && m.to_driver_name === chatRecipient)
      );
    }
  };

  // ============= API CALLS =============

  const fetchDrivers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/drivers`);
      setDrivers(res.data);
    } catch (e) {
      console.error("Error fetching drivers:", e);
    }
  }, []);

  const lastKnownHasterRef = React.useRef(new Set());

  const fetchTours = useCallback(async () => {
    try {
      // Fase 15.2 / 15.3 (2026-06-19): Hent altid bredt nok til at vi kan
      // inkludere chaufførens egne forsinkede ture (ikke-afsluttede, før i
      // dag). Hvis "Vis afventende ture" er slået til, vises også ledige
      // afventende ture fra andre pladser.
      const todayStr = getLocalDateStr();
      // Fase 15.8 (2026-02-XX): selectedDriver bliver aldrig sat i
      // driver-flowet, så vi falder tilbage på authUser?.id for at undgå
      // at admin-tildelte ture (med driver_id sat) bliver fejlagtigt
      // filtreret væk.
      const myId = selectedDriver?.id || authUser?.id || "";
      const myName = driverName || authUser?.name || authUser?.driver_name || "";
      const url = `${API}/tours?limit=500`;
      const res = await axios.get(url);
      let newTours = res.data || [];

      // Fase 15.3 (2026-06-19): DEFENSIV CLIENT-SIDE FILTER -
      // skjul ture der er "på vej" men ikke ejet af mig. Backend bør
      // allerede gøre dette, men en stale/orphan-tur kan slippe igennem
      // (fx admin der løsriver claim uden at rydde on_way).
      //
      // Fase 15.5 (2026-06-19): UDVIDET - også skjul ture der er PRE-ASSIGNED
      // til en anden chauffør (driver_id sat til andre end mig).
      //
      // Fase 15.13 (2026-02-XX): RELAKSERET - vi BEHOLDER ture hos andre
      // chauffører i fetchen så lokationssiden kan vise dem read-only i
      // den nye "Ture hos andre chauffører"-sektion. Vi tagger turen via
      // `_is_other_driver` så UI kan placere dem korrekt og spærre
      // handlinger. Orphan-ture (on_way uden ejer) skjules fortsat.
      newTours = newTours.filter(t => {
        // 3) On-way uden ejerskab → orphan, skjul (defensiv)
        if (t.on_way && !t.completed) {
          const hasNoOwner = !t.claimed_by && !t.claimed_by_id && !(t.driver_id || "").trim();
          if (hasNoOwner) return false;
        }
        // Fase 15.52 (2026-02-22): Skjul ikke-gennemførte ture fra chauffør -
        // de er kun synlige hos logistik-admin indtil gen-aktivering.
        if (t.not_completed) return false;
        return true;
      }).map(t => {
        const otherDriverId = (t.driver_id || "").trim();
        const claimedByOtherId = t.claimed_by_id && t.claimed_by_id !== myId;
        const claimedByOtherName = !t.claimed_by_id && t.claimed_by && myName && t.claimed_by !== myName;
        const isOtherDriverTour = !!(
          (otherDriverId && otherDriverId !== myId) ||
          claimedByOtherId ||
          claimedByOtherName
        );
        return { ...t, _is_other_driver: isOtherDriverTour };
      });

      // Date-scoping:
      //   - I dag (reportDate): alle
      //   - Fremtidige: aldrig
      //   - Tidligere: kun afventende OG (mine ELLER toggle on)
      //   - Tidligere afsluttede: aldrig
      newTours = newTours.filter(t => {
        const td = (t.date || "").slice(0, 10);
        if (td === reportDate) return true;
        if (!td) return false;
        if (td > todayStr) return false;        // skjul fremtidige
        if (t.completed) return false;          // afsluttede fra fortiden = ikke længere "afventende"
        const isMine = (myId && t.claimed_by_id === myId) ||
                       (myName && t.claimed_by === myName) ||
                       (myId && (t.driver_id || "") === myId);
        if (isMine) return true;                // mine forsinkede ture vises altid
        return showPendingInList;               // ledige forsinkede kun ved toggle
      });
      setTours(newTours);
      // Fase 15.43 (2026-02-22): Hvis brugeren har MobileTourPanel åbent, så
      // synkroniser også dens `tour` prop med den friske server-version, så
      // chaufføren ser opdaterede vægte/status efter "Gem udkast" eller når
      // en anden bruger/admin har ændret turen. Vi sammenligner med
      // JSON-stringify for at undgå unødvendige re-renders der ville sætte
      // chaufførens åbne inputfelt på vippen.
      setSelectedTourForPanel(prev => {
        if (!prev) return prev;
        const fresh = newTours.find(t => t.id === prev.id);
        if (!fresh) return prev;  // tur ikke længere synlig - luk ikke automatisk
        // Stable comparison af de felter der har visuel effekt på panelet.
        if (
          fresh.weight === prev.weight &&
          fresh.completed === prev.completed &&
          fresh.on_way === prev.on_way &&
          fresh.claimed_by === prev.claimed_by &&
          fresh.used_trailer === prev.used_trailer &&
          fresh.trailer_confirmed === prev.trailer_confirmed &&
          JSON.stringify(fresh.stops || []) === JSON.stringify(prev.stops || []) &&
          (fresh.container_weights || []).join(",") === (prev.container_weights || []).join(",")
        ) {
          return prev;
        }
        return fresh;
      });

      // Detect NEW haster tours that weren't known before
      // Fase 15.23 (2026-02-21): In-app HASTER-toast + browser-notifikation +
      // vibration er fjernet pr. brugerkrav - der skal ikke længere være
      // system-toasts om hasteture på chauffør-siden. Hasteture vises
      // stadig som rødt HASTER-chip i tour-listen (visuel-only).
      // (Vi rydder fortsat lastKnownHasterRef så fremtidige genaktiveringer
      //  ikke bliver bagudkompatibilitets-bumset.)
      if (driverSetupDone && driverName) {
        const activeIds = new Set(newTours.map(t => t.id));
        lastKnownHasterRef.current.forEach(id => {
          if (!activeIds.has(id)) lastKnownHasterRef.current.delete(id);
        });
      }
    } catch (e) {
      console.error("Error fetching tours:", e);
    }
  }, [reportDate, driverSetupDone, driverName, activeCustomer?.id, showPendingInList]);

  const seedData = useCallback(async () => {
    // Legacy single-tenant seeding is disabled. The multi-tenant world
    // creates pladser via the customer_admin UI; calling /api/seed would
    // pollute the system with demo drivers + 10 default pladser tied to
    // `company_id=default`. We only refresh the plads list here.
    try {
      fetchDrivers();
      const pladsRes = await axios.get(`${API}/plads`);
      setPladsList(pladsRes.data);
    } catch (e) {
      console.error("Error refreshing data:", e);
    }
  }, [fetchDrivers]);

  // Fase 7 (2026-06-17): Whenever pladsList changes (e.g. customer switched),
  // make sure selectedPlads still belongs to the new list. If not, clear it
  // so the driver doesn't see a stale plads header (e.g. SAC selected while
  // active customer is ARGO).
  useEffect(() => {
    if (!selectedPlads || pladsList.length === 0) return;
    // Fase 15.8 (2026-02-XX): Bevar virtuel "__MINE__"-plads selvom den
    // aldrig optræder i pladsList. Tidligere blev "__MINE__" nulstillet til
    // "" lige efter klik, hvilket fik UI tilbage til welcome-skærmen.
    if (selectedPlads === "__MINE__") return;
    const stillValid = pladsList.some(p => p.name === selectedPlads);
    if (!stillValid) {
      setSelectedPlads("");
    }
  }, [pladsList, selectedPlads]);

  // ============= EFFECTS =============

  useEffect(() => { seedData(); }, [seedData]);
  useEffect(() => { fetchTours(); }, [fetchTours]); // Fetch tours on load

  // Re-fetch the plads list whenever the authenticated user OR the active
  // customer changes. Fase 5+ (2026-06-16): Drivers can switch between
  // partnered customers and must always see ONLY the plads of the currently
  // selected customer. Without `activeCustomer?.id` in the deps, switching
  // customer would leave pladsList empty (cleared in handleSwitchCustomer)
  // until the next page reload.
  useEffect(() => {
    if (!authUser) return;
    axios.get(`${API}/plads`)
      .then(res => {
        const list = res.data || [];
        setPladsList(list);
        // Fase 7 (2026-06-17): If the previously-selected plads is no longer
        // in the new (customer-filtered) list, clear it. Otherwise the driver
        // would see a "ghost" selection (e.g. Helsingør Forsyning's SAC while
        // their active customer is ARGO).
        // Fase 15.8 (2026-02-XX): Bevar virtuel "__MINE__"-plads.
        if (selectedPlads && selectedPlads !== "__MINE__") {
          const stillValid = list.some(p => p.name === selectedPlads);
          if (!stillValid) {
            setSelectedPlads("");
          }
        }
      })
      .catch(() => { /* ignore - seedData already populated something */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser?.id, authUser?.company_id, activeCustomer?.id]);

  // Fase 10 (2026-06-17): Hent firmaets centrale vognnumre + hængere så
  // chaufføren kan vælge ved login. Begge dele kan være tomme.
  useEffect(() => {
    if (!authUser) return;
    axios.get(`${API}/vehicles`).then(r => setVehiclesList(r.data || [])).catch(() => {});
    axios.get(`${API}/trailers`).then(r => setTrailersList(r.data || [])).catch(() => {});
  }, [authUser?.id, authUser?.company_id]);

  // Fetch materials list
  useEffect(() => {
    axios.get(`${API}/materials`).then(res => setMaterialsList(res.data?.materials || [])).catch(() => {});
  }, []);
  
  // Load driver session when driver logs in
  useEffect(() => {
    if (driverSetupDone && driverName) {
      loadDriverSession();
      fetchDriverMessages();
      fetchAvailableDrivers();
      subscribeToPush();
      // Fase 15.23 (2026-02-21): Notifikations-permission-prompt fjernet -
      // chauffører får ikke længere in-app eller browser-baseret HASTER-
      // notifikation. Visuelle HASTER-chips på tour-kortene er nok.
    }
  }, [driverSetupDone, driverName, loadDriverSession, fetchDriverMessages, fetchAvailableDrivers, subscribeToPush]);
  
  // Save session when data changes
  useEffect(() => {
    if (driverSetupDone && driverName) {
      saveDriverSession();
    }
  }, [driverSetupDone, driverName, vehicleReg, selectedPlads, startTime, saveDriverSession]);

  // Fase 11 (2026-06-18): Auto-refresh tours hvert 5. sekund (tidligere 10s)
  // for "near real-time" opdatering - chaufføren ser bestillinger og admin-
  // tildelinger næsten med det samme.
  useEffect(() => {
    const interval = setInterval(() => {
      fetchTours();
      if (driverName) fetchDriverMessages();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchTours]);

  const fetchDriverTourUnread = useCallback(async () => {
    if (!authUser || authUser.role !== "driver") return;
    try {
      const r = await axios.get(`${API}/tour-messages/unread`);
      setDriverTourUnread(r.data.unread || {});
      const total = r.data.total || 0;
      if (driverUnreadTotalRef.current !== null && total > driverUnreadTotalRef.current) {
        const m = (r.data.latest || [])[0];
        if (m) toast.message(`Besked fra ${m.sender_name || "planlægger"}`, { description: m.text, duration: 8000 });
        try { navigator.vibrate && navigator.vibrate([120, 60, 120]); } catch (_) { /* ikke understøttet */ }
      }
      driverUnreadTotalRef.current = total;
    } catch (e) { /* ikke kritisk */ }
  }, [authUser]);
  useEffect(() => {
    fetchDriverTourUnread();
    const iv = setInterval(() => { if (!document.hidden) fetchDriverTourUnread(); }, 15000);
    return () => clearInterval(iv);
  }, [fetchDriverTourUnread]);

  // Pause countdown timer + finish notification
  useEffect(() => {
    if (!activePause) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((activePause.endMs - Date.now()) / 1000));
      setPauseRemainingSec(remaining);
      if (remaining <= 0) {
        // Pause finished
        toast.success("Pause er slut! Tilbage til arbejde.", { duration: 8000 });
        // Browser notification
        if ("Notification" in window && Notification.permission === "granted") {
          try {
            new Notification("Pause er slut!", {
              body: "Din pause er færdig. Tilbage på vej.",
              icon: "/logo192.png",
              tag: "pause-finished"
            });
          } catch (e) { /* ignore */ }
        }
        // Vibrate on mobile if available
        if (navigator.vibrate) navigator.vibrate([200, 100, 200, 100, 400]);
        setActivePause(null);
        setPauseRemainingSec(0);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [activePause]);

  // Detect newly-arrived messages addressed to this driver and auto-popup
  useEffect(() => {
    if (!driverName || !driverMessages.length) return;
    // Find first unread message TO this driver that hasn't been shown yet
    const next = driverMessages.find(m =>
      m.to_driver_name === driverName &&
      !m.read &&
      !seenMessageIdsRef.current.has(m.id)
    );
    if (next && !incomingMessage) {
      seenMessageIdsRef.current.add(next.id);
      setIncomingMessage(next);
      setIncomingReplyMode(false);
      setIncomingReplyText("");
      // Vibrate / notify
      if (navigator.vibrate) navigator.vibrate([150, 80, 150]);
      if ("Notification" in window && Notification.permission === "granted") {
        try {
          new Notification(`Ny besked fra ${next.from_driver_name || "Admin"}`, {
            body: next.content,
            icon: "/logo192.png",
            tag: `msg-${next.id}`
          });
        } catch (e) { /* ignore */ }
      }
    }
  }, [driverMessages, driverName, incomingMessage]);

  // Close incoming message popup (marks as read)
  const closeIncomingMessage = async () => {
    if (!incomingMessage) return;
    try { await axios.put(`${API}/messages/${incomingMessage.id}/read`); } catch (e) { /* noop */ }
    setDriverMessages(prev => prev.filter(m => m.id !== incomingMessage.id));
    setIncomingMessage(null);
    setIncomingReplyMode(false);
    setIncomingReplyText("");
  };

  // Reply to incoming message
  const replyIncomingMessage = async () => {
    if (!incomingMessage || !incomingReplyText.trim()) return;
    try {
      const from = incomingMessage.from_driver_name || "Admin";
      if (incomingMessage.from_admin || from === "Admin") {
        // Reply to admin
        await axios.post(`${API}/messages`, {
          from_driver_name: driverName,
          to_admin: true,
          content: incomingReplyText.trim()
        });
      } else {
        // Reply to another driver
        await axios.post(`${API}/messages`, {
          from_driver_name: driverName,
          to_driver_name: from,
          content: incomingReplyText.trim()
        });
      }
      toast.success("Svar sendt");
      await closeIncomingMessage();
    } catch (e) {
      toast.error("Kunne ikke sende svar");
    }
  };

  useEffect(() => {
    const initReport = async () => {
      if (!reportId) {
        try {
          // First check if there's already a report for today
          const existingRes = await axios.get(`${API}/reports?date=${reportDate}`);
          if (existingRes.data && existingRes.data.length > 0) {
            // Use existing report
            setReportId(existingRes.data[0].id);
          } else {
            // Create new report
            const res = await axios.post(`${API}/reports`, {
              report_date: reportDate,
              start_time: "07:00"
            });
            setReportId(res.data.id);
          }
        } catch (e) {
          console.error("Error initializing report:", e);
        }
      }
    };
    initReport();
  }, [reportDate, reportId]);

  // ============= HANDLERS =============

  const handleAdminLogin = async () => {
    try {
      const res = await axios.post(`${API}/admin/login`, { username: "admin", password: adminPass });
      if (res.data.success) {
        setIsAdmin(true);
        setShowAdminLogin(false);
        toast.success("Admin login successful");
      }
    } catch (e) {
      if (e.response && e.response.status === 401) {
        toast.error("Forkert kode");
      } else if (e.response) {
        toast.error(`Server fejl: ${e.response.status}`);
      } else {
        toast.error("Netværksfejl - prøv igen");
      }
    }
  };
  
  const markMessageRead = async (messageId) => {
    try {
      await axios.put(`${API}/messages/${messageId}/read`);
      setDriverMessages(driverMessages.filter(m => m.id !== messageId));
      if (driverMessages.length <= 1) {
        setShowMessages(false);
      }
    } catch (e) {
      console.error("Error marking message read:", e);
    }
  };

  const handleAddManualTour = async () => {
    if (!manualFraction || !manualFacility) { toast.error("Udfyld fraktion og modtageanlæg!"); return; }
    if (isPrivateTour && !privateCompany) { toast.error("Indtast firma navn for privat tur!"); return; }
    
    console.log("Adding tour with plads:", selectedPlads, "reportId:", reportId);
    
    try {
      const res = await axios.post(`${API}/tours`, {
        date: reportDate,
        fraction: manualFraction,
        facility: manualFacility,
        address: manualAddress,
        container: manualContainer,
        is_same_day: isSameDay,
        is_private: isPrivateTour,
        private_company: privateCompany,
        plads: selectedPlads || "",
        driver_id: selectedDriver?.id || "",
        driver_name: driverName,
        report_id: reportId
      });
      console.log("Tour added:", res.data);
      setTours(prevTours => [...prevTours, res.data]);
      setManualFraction(""); setManualFacility(""); setManualAddress(""); setManualContainer(""); 
      setIsSameDay(false); setIsPrivateTour(false); setPrivateCompany("");
      toast.success("Tur tilføjet");
    } catch (e) {
      console.error("Error adding tour:", e);
      toast.error("Fejl ved tilføjelse");
    }
  };

  const handleAddPause = async (minutes = 45) => {
    const now = new Date();
    const pauseStart = now.toTimeString().slice(0, 5);
    const endDate = new Date(now.getTime() + minutes * 60000);
    const pauseEnd = endDate.toTimeString().slice(0, 5);
    
    try {
      const res = await axios.post(`${API}/tours/pause?report_id=${reportId}&plads=${selectedPlads}&driver_id=${selectedDriver?.id || ""}&driver_name=${driverName}&date=${reportDate}`);
      await axios.put(`${API}/tours/${res.data.id}`, { time: `${pauseStart}-${pauseEnd}` });
      setTours([...tours, { ...res.data, time: `${pauseStart}-${pauseEnd}` }]);
      // Start countdown timer
      setActivePause({ endMs: endDate.getTime(), minutes, startedAt: now.getTime() });
      setPauseRemainingSec(minutes * 60);
      // Request browser notification permission if not granted
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
      }
      toast.success(`Pause: ${pauseStart} - ${pauseEnd} (${minutes} min)`);
    } catch (e) {
      toast.error("Fejl ved pause");
    }
  };

  const handleUpdateTour = async (tourId, update) => {
    // Claim lock: a tour belongs exclusively to the driver who took it.
    // Block in-place updates (weight edit, on_way, etc.) from any other
    // driver. The exception is when the SAME driver clears the claim
    // themselves (update sets claimed_by: "").
    const tour = tours.find(t => t.id === tourId);
    if (
      tour?.claimed_by &&
      tour.claimed_by !== driverName &&
      update?.claimed_by !== "" // allow the rightful owner to unclaim
    ) {
      toast.error(`Denne tur er taget af ${tour.claimed_by}`);
      throw new Error("locked-by-other-driver");
    }
    try {
      const res = await axios.put(`${API}/tours/${tourId}`, update);
      setTours(tours.map(t => t.id === tourId ? res.data : t));
      // Fase 15.43 (2026-02-22): Synkroniser også panelets `tour` prop hvis
      // brugeren har MobileTourPanel åbent for præcis denne tur. Uden dette
      // beholder panelet stale data (især container_weights efter "Gem
      // udkast") og brugeren oplever at vægte "forsvinder" når de lukker
      // og genåbner panelet.
      setSelectedTourForPanel(prev => (prev && prev.id === tourId) ? res.data : prev);
    } catch (e) {
      if (e?.response?.status === 409) {
        toast.error(e.response.data?.detail || "Tur er allerede taget af en anden chauffør");
        fetchTours();
      } else {
        console.error("Error updating tour:", e);
      }
      throw e;
    }
  };

  const handleToggleOnWay = async (tourId) => {
    const tour = tours.find(t => t.id === tourId);
    if (!tour) return;
    if (tour.claimed_by && tour.claimed_by !== driverName) {
      toast.error(`Denne tur er taget af ${tour.claimed_by}`);
      return;
    }
    const newOnWay = !tour.on_way;
    const currentTime = newOnWay ? getCurrentTime() : tour.time;
    // Fase 13 (2026-06-18): Pre-flight kapacitets-tjek inden vi rammer backend.
    // Backend håndhæver det også som hard-stop (409), men en lokal advarsel
    // giver hurtigere feedback. Gælder kun ved CLAIM, ikke ved un-claim.
    //
    // Fase 14 (2026-06-19): "AKTIV" tæller KUN ture som faktisk er
    // 'på vej' (on_way=true && !completed). Tidligere talte vi også
    // claimede-men-ikke-startede ture med samt ture hvor on_way ikke var
    // ryddet ved Afslut - det blokerede chaufføren fra at fortsætte
    // arbejdet selvom turene reelt var FÆRDIGE.
    if (newOnWay && !tour.claimed_by) {
      const trailer = (trailersList || []).find(t => t.id === activeTrailerId);
      const capacity = trailer ? (trailer.container_capacity ?? 1) : 0;
      const maxSimultaneous = capacity > 0 ? capacity + 1 : 1;
      // Fase 15.3 (2026-06-19): Sikker per-chauffør tælling.
      // Tidligere kunne `t.claimed_by_id === (selectedDriver?.id || "")`
      // matche ALLE ledige (claimed_by_id="") ture når selectedDriver.id
      // var tom - hvilket falsk overskred kapaciteten på tværs af alle
      // chauffører. Vi kræver nu et IKKE-TOMT id/navn for at tælle.
      // Fase 15.8 (2026-02-XX): authUser?.id fallback (selectedDriver er null i driver-flowet).
      const myId   = selectedDriver?.id || authUser?.id || "";
      const myName = driverName || authUser?.name || authUser?.driver_name || "";
      const currentActive = tours.filter(t => {
        if (!t.on_way || t.completed || t.is_pause) return false;
        const byId   = myId   && t.claimed_by_id === myId;
        const byName = myName && t.claimed_by === myName;
        return !!(byId || byName);
      }).length;
      if (currentActive >= maxSimultaneous) {
        const msg = capacity > 0
          ? `Max ${maxSimultaneous} samtidige ture med din hænger (${trailer?.number || "?"} · kapacitet ${capacity}). Afslut en aktiv tur først.`
          : `Du må kun have 1 aktiv tur uden hænger. Vælg en hænger i toppen eller afslut din aktive tur.`;
        toast.error(msg, { duration: 5000 });
        return;
      }
    }
    try {
      if (newOnWay) {
        // Claiming the tour
        const startBody = {
          on_way: true,
          on_way_time: currentTime,
          claimed_by: driverName,
          claimed_by_id: selectedDriver?.id || authUser?.id || ""
        };
        try {
          await handleUpdateTour(tourId, startBody);
        } catch (e) {
          // 2026-10-18: Uden net startes turen på telefonen og sendes senere.
          if (!isNetworkError(e)) throw e;
          enqueueOp({ kind: "put", tour_id: tourId, body: startBody });
          setTours(prev => prev.map(t => (t.id === tourId ? { ...t, ...startBody, queued: true } : t)));
          toast.message("Ingen forbindelse - starten sendes når der er net");
          return;
        }
        toast.success(`${driverName || "Chauffør"} er på vej!`);
      } else {
        // Unclaiming - first update with own name to pass validation, then clear
        await handleUpdateTour(tourId, { 
          on_way: false, 
          time: currentTime,
          claimed_by: driverName,
          claimed_by_id: selectedDriver?.id || authUser?.id || ""
        });
        // Now clear the claim
        await axios.put(`${API}/tours/${tourId}`, { claimed_by: "", claimed_by_id: "" });
        fetchTours();
      }
    } catch (e) {
      // Error already handled in handleUpdateTour
    }
  };

  const handleToggleComplete = async (tourId, opts = {}) => {
    const tour = tours.find(t => t.id === tourId);
    if (!tour) return;
    if (tour.claimed_by && tour.claimed_by !== driverName) {
      toast.error(`Denne tur er taget af ${tour.claimed_by}`);
      return;
    }
    const nowCompleting = !tour.completed;
    const currentTime = new Date().toTimeString().slice(0, 5);

    // Business rule: weight is REQUIRED before a tour can be marked completed.
    // The optional `opts.weight` parameter lets a caller (e.g. the panel's
    // inline weight prompt) supply a freshly-entered weight in the same call.
    // Fase 11 (2026-06-18): For opgavetyper der IKKE er 'normal' (afhent
    // container) er vægt slet ikke relevant - afslut uden vægt-validering.
    // Fase 15.41 (2026-02-22): "Løs afhentning" har sin egen multi-vægt
    // (containerWeights array). Mindst én > 0 påkrævet. Backend auto-
    // beregner total `weight` som SUM så de aldrig kommer ud af sync.
    const tourType = (tour.tour_type || "normal");
    const isMultiLoad = tourType === "loes_afhentning" || (tour.cargo_lines || []).length > 1;
    if (nowCompleting && isMultiLoad && !opts.skipWeight) {
      const incoming = Array.isArray(opts.containerWeights) ? opts.containerWeights : null;
      const existing = Array.isArray(tour.container_weights) ? tour.container_weights : [];
      const finalWeights = incoming && incoming.length > 0 ? incoming : existing;
      const positive = (finalWeights || []).map(w => parseFloat(w)).filter(w => Number.isFinite(w) && w > 0);
      if (positive.length === 0) {
        toast.error("Indtast mindst én vægt før du kan afslutte turen");
        return { needsWeight: true };
      }
      try {
        await handleUpdateTour(tourId, {
          completed: true,
          on_way: false,
          time: currentTime,
          container_weights: positive,
          claimed_by: driverName,
          claimed_by_id: selectedDriver?.id || authUser?.id || "",
        });
        toast.success(tourType === "loes_afhentning" ? "Løs afhentning fuldført!" : "Tur fuldført!");
        return { ok: true };
      } catch (e) {
        return { error: e };
      }
    }
    const isNormalTourType = tourType === "normal";
    if (nowCompleting && isNormalTourType && !opts.skipWeight) {
      const explicitWeight = opts.weight != null ? parseFloat(opts.weight) : null;
      const existingWeight = tour.weight != null && tour.weight !== ""
        ? parseFloat(tour.weight) : null;
      const finalWeight = (explicitWeight && explicitWeight > 0)
        ? explicitWeight
        : ((existingWeight && existingWeight > 0) ? existingWeight : null);
      if (!finalWeight) {
        toast.error("Indtast vægt før du kan afslutte turen");
        return { needsWeight: true };
      }
      try {
        await handleUpdateTour(tourId, {
          completed: true,
          on_way: false,
          time: currentTime,
          weight: finalWeight,
          claimed_by: driverName,
          claimed_by_id: selectedDriver?.id || authUser?.id || ""
        });
        toast.success("Tur fuldført!");
        return { ok: true };
      } catch (e) {
        return { error: e };
      }
    }
    // Non-normal tour completion path (no weight required) OR opts.skipWeight.
    // 2026-10-17: Gods-ture kan afsluttes med en valgfri vægt.
    if (nowCompleting) {
      try {
        const optW = opts.weight != null ? parseFloat(opts.weight) : null;
        await handleUpdateTour(tourId, {
          completed: true,
          on_way: false,
          time: currentTime,
          ...(optW && optW > 0 ? { weight: optW } : {}),
          claimed_by: driverName,
          claimed_by_id: selectedDriver?.id || authUser?.id || ""
        });
        toast.success("Tur fuldført!");
        return { ok: true };
      } catch (e) {
        return { error: e };
      }
    }

    // Un-completing path (unchanged behaviour)
    try {
      await handleUpdateTour(tourId, {
        completed: false,
        on_way: false,
        time: tour.time,
        claimed_by: driverName,
        claimed_by_id: selectedDriver?.id || authUser?.id || ""
      });
      await axios.put(`${API}/tours/${tourId}`, { claimed_by: "", claimed_by_id: "" });
      fetchTours();
      return { ok: true };
    } catch (e) {
      return { error: e };
    }
  };

  const handleInlineComplete = async (tourId) => {
    const val = parseFloat(inlineWeight);
    if (!val || val <= 0) { toast.error("Indtast vægt"); return; }
    const currentTime = new Date().toTimeString().slice(0, 5);
    await handleUpdateTour(tourId, {
      weight: val, completed: true, on_way: false, time: currentTime,
      claimed_by: driverName, claimed_by_id: selectedDriver?.id || authUser?.id || "",
      ...(inlinePlate ? { reg_nr: inlinePlate } : {})
    });
    setInlineWeightTourId(null);
    setInlineWeight("");
    setInlinePlate("");
    toast.success("Tur fuldført!");
  };

  // Fase 14 (2026-06-19): Når chauffør trykker på "PÅ VEJ"-badge skal
  // vægt-input KUN dukke op for opgavetype "normal" (= afhent container).
  // For andre opgavetyper (flyt, værksted, afhent_værksted) afsluttes
  // turen straks uden vægt - Bemærkninger-feltet skal heller ikke vises.
  const handleStartInlineComplete = async (tour) => {
    const isNormal = (tour.tour_type || "normal") === "normal";
    if (isNormal) {
      setInlineWeightTourId(tour.id);
      setInlineWeight("");
      return;
    }
    // Non-normal: gennemfør uden vægt direkte.
    const currentTime = new Date().toTimeString().slice(0, 5);
    try {
      await handleUpdateTour(tour.id, {
        completed: true, on_way: false, time: currentTime,
        claimed_by: driverName, claimed_by_id: selectedDriver?.id || authUser?.id || "",
      });
      toast.success("Tur fuldført!");
    } catch (_) { /* fejl-toast håndteres i handleUpdateTour */ }
  };

  const handleDeleteTour = (tourId) => {
    const tour = tours.find(t => t.id === tourId);
    if (tour?.claimed_by && tour.claimed_by !== driverName) {
      toast.error(`Denne tur er taget af ${tour.claimed_by} - kan ikke slettes`);
      return;
    }
    showConfirm(
      "Slet tur",
      "Er du sikker på at du vil slette denne tur? Denne handling kan ikke fortrydes.",
      async () => {
        hideConfirm();
        try {
          await axios.delete(`${API}/tours/${tourId}`);
          setTours(tours.filter(t => t.id !== tourId));
          toast.success("Tur slettet");
        } catch (e) { toast.error("Fejl ved sletning"); }
      }
    );
  };
  
  // Reorder tours (drag & drop)
  const handleReorderTours = async (fromIndex, toIndex) => {
    const filteredTours = tours
      .filter(t => !selectedPlads || t.plads === selectedPlads)
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    
    if (fromIndex === toIndex) return;
    
    const newTours = [...filteredTours];
    const [movedTour] = newTours.splice(fromIndex, 1);
    newTours.splice(toIndex, 0, movedTour);
    
    // Update sort_order for all affected tours
    const tourOrders = newTours.map((tour, idx) => ({
      id: tour.id,
      sort_order: idx
    }));
    
    // Optimistic update
    const updatedTours = tours.map(t => {
      const orderInfo = tourOrders.find(o => o.id === t.id);
      return orderInfo ? { ...t, sort_order: orderInfo.sort_order } : t;
    });
    setTours(updatedTours);
    
    try {
      await axios.put(`${API}/tours/reorder`, tourOrders);
    } catch (e) {
      console.error("Error reordering:", e);
      fetchTours(); // Revert on error
    }
  };

  const handleClearAll = () => {
    if (!selectedPlads) { toast.error("Vælg en plads først"); return; }
    showConfirm(
      "Slet alle ture",
      `Er du sikker på at du vil slette alle ture i ${selectedPlads}?`,
      async () => {
        hideConfirm();
        try {
          const toursToDelete = tours.filter(t => t.plads === selectedPlads);
          await Promise.all(toursToDelete.map(t => axios.delete(`${API}/tours/${t.id}`)));
          setTours(tours.filter(t => t.plads !== selectedPlads));
          setRouteOptimization(null);
          toast.success(`Alle ture i ${selectedPlads} slettet`);
        } catch (e) { toast.error("Fejl"); }
      }
    );
  };

  // Route optimization handler
  // 2026-10-17: Optimér chaufførens egne ture fra den plads de fleste hører
  // til - uden at skulle vælge en plads først (ny TURE-fane).
  const handleOptimizeFor = async (pladsName, tourIds) => {
    if (!pladsName || !tourIds?.length) return;
    setIsOptimizing(true);
    try {
      const res = await axios.post(`${API}/optimize-route`, { plads_name: pladsName, tour_ids: tourIds });
      if (res.data?.optimized) {
        setRouteOptimization(res.data);
        toast.success(`Rækkefølge optimeret - ${res.data.tours_with_coordinates}/${res.data.total_tours} ture med placering`);
      } else {
        toast.error(res.data?.reason || "Kunne ikke optimere ruten");
      }
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleOptimizeRoute = async () => {
    if (!selectedPlads) { toast.error("Vælg en lokation først"); return; }
    const activeTours = tours.filter(t => t.plads === selectedPlads && !t.is_pause);
    if (activeTours.length === 0) { toast.error("Ingen ture at optimere"); return; }
    // Fase 12 (2026-06-18): Manuelt tryk slår optimeringen TIL hvis den er
    // slukket - så bliver den auto-effekt også genaktiveret ved næste plads-skift.
    if (!routeOptEnabled) setRouteOptEnabled(true);
    
    setIsOptimizing(true);
    try {
      const res = await axios.post(`${API}/optimize-route`, {
        plads_name: selectedPlads,
        tour_ids: activeTours.map(t => t.id),
      });
      const data = res.data;
      if (data.optimized) {
        setRouteOptimization(data);
        // Reorder tours in UI based on optimization
        const orderMap = {};
        data.tours.forEach(t => { orderMap[t.tour_id] = t; });
        setTours(prev => {
          const otherTours = prev.filter(t => t.plads !== selectedPlads || t.is_pause);
          const pladsTours = prev.filter(t => t.plads === selectedPlads && !t.is_pause);
          const sorted = [...pladsTours].sort((a, b) => {
            const oa = orderMap[a.id]?.route_order ?? 999;
            const ob = orderMap[b.id]?.route_order ?? 999;
            return oa - ob;
          });
          return [...otherTours, ...sorted];
        });
        toast.success(`Rute optimeret! ${data.tours_with_coordinates}/${data.total_tours} ture med koordinater`);
      } else {
        toast.info(data.reason || "Kunne ikke optimere ruten");
        setRouteOptimization(null);
      }
    } catch (e) {
      toast.error("Fejl ved ruteoptimering");
      setRouteOptimization(null);
    } finally {
      setIsOptimizing(false);
    }
  };

  // Get route info for a specific tour
  const getRouteInfo = (tourId) => {
    if (!routeOptimization?.optimized || !routeOptimization?.tours) return null;
    return routeOptimization.tours.find(t => t.tour_id === tourId) || null;
  };

  const handleGeneratePDF = async () => {
    try {
      const { data: report } = await axios.get(`${API}/driver/day-report`, { params: { date: reportDate } });
      const doc = buildDayReportPdf({
        title: "Kørselsrapport", report, driverName, vehicleReg, date: reportDate, notes,
      });
      doc.save(dayReportFileName("korselsrapport", reportDate, driverName));
      toast.success("PDF genereret!");
    } catch (error) {
      console.error("PDF error:", error);
      toast.error("Fejl: " + (error?.response?.data?.detail || error.message));
    }
  };

  // ============= END OF SHIFT (GÜN BİTTİ) =============
  const [isEndingShift, setIsEndingShift] = useState(false);

  // ============= CONFIRMATION MODAL STATE =============
  const [confirmModal, setConfirmModal] = useState({ open: false, title: "", message: "", onConfirm: null, variant: "danger" });
  const showConfirm = (title, message, onConfirm, variant = "danger") => {
    setConfirmModal({ open: true, title, message, onConfirm, variant });
  };
  const hideConfirm = () => setConfirmModal({ open: false, title: "", message: "", onConfirm: null, variant: "danger" });

  // Fase 18.2 (2026-02-28): Tidsregistrering-validering før "Afslut dag".
  // Dansk lov (1. juli 2024) kræver objektiv tidsregistrering. Tre scenarier
  // håndteres:
  //   1) Ingen IND i dag       → modal: "Registrer venligst" / "Afslut alligevel"
  //   2) IND uden UD           → auto-stempel UD nu, vis info-modal, fortsæt
  //   3) IND + UD              → fortsæt direkte
  const [timeRegModal, setTimeRegModal] = useState({
    open: false, scenario: 0, autoTime: "", onProceed: null,
  });
  const closeTimeRegModal = () => setTimeRegModal({ open: false, scenario: 0, autoTime: "", onProceed: null });

  // 2026-10-18 (P8): Ture der stadig er "På vej" når dagen afsluttes - typisk
  // en glemt "Afslut". Ellers bliver turen afsluttet næste morgen, og tiden
  // (og dermed timeprisen) bliver forkert.
  const [onWayWarn, setOnWayWarn] = useState(null);
  const handleEndOfShift = async (opts = {}) => {
    if (isEndingShift) return;
    if (!opts.skipOnWay) {
      const myId = selectedDriver?.id || authUser?.id || "";
      const stillOnWay = (tours || []).filter(t => t.on_way && !t.completed && !t.not_completed && !t.is_pause
        && ((myId && t.claimed_by_id === myId) || (driverName && t.claimed_by === driverName)));
      if (stillOnWay.length) { setOnWayWarn(stillOnWay); return; }
    }

    // Fase 18.2: Tjek today's driver_time_entries FØR shift-flow startes.
    const todayWork = (timeEntries || []).filter(e =>
      !e.deleted && (e.slice_type || "work") === "work" && e.date === reportDate
    );

    // SCENARIO 1: Ingen IND-stempler i dag
    if (todayWork.length === 0) {
      setTimeRegModal({
        open: true,
        scenario: 1,
        autoTime: "",
        onProceed: () => {
          closeTimeRegModal();
          // "Afslut alligevel" - kør den oprindelige flow
          proceedToEndOfShift();
        },
      });
      return;
    }

    // SCENARIO 2: Mindst én work-entry, men den nyeste mangler end_time
    const openEntry = todayWork.find(e => !e.end_time);
    if (openEntry) {
      const nowT = getCurrentTime();
      try {
        await axios.post(`${API}/driver/time-entries/punch`, {
          date: reportDate, time: nowT, type: "ud",
        });
        await fetchTimeEntries();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Kunne ikke stemple dig ud automatisk");
        return;
      }
      setTimeRegModal({
        open: true,
        scenario: 2,
        autoTime: nowT,
        onProceed: () => {
          closeTimeRegModal();
          // Sync UI slut-tid hvis tom, så PDF-flow bruger korrekt tid
          if (!endTime || !/^\d{2}:\d{2}$/.test(endTime)) setEndTime(nowT);
          proceedToEndOfShift(nowT);
        },
      });
      return;
    }

    // SCENARIO 3: Alle stempler komplette - fortsæt som normal
    proceedToEndOfShift();
  };

  // Fase 18.2: Den oprindelige "Afslut dag"-logik (slut-tid validering +
  // performEndOfShift) er flyttet hertil, så scenarie 1+2 kan gen-bruge den.
  // 2026-10-16: Spørger ikke længere om "Slut tid" - dagrapporten tager
  // start/slut fra stemplingerne. Den gamle slut-tid-state var ofte tom
  // (fx efter genindlæsning), så chaufføren fik foreslået "nu" selvom han
  // stemplede ud for timer siden. Klokken nu bruges kun som fallback hvis
  // der slet ingen stemplinger er.
  const proceedToEndOfShift = (forcedEndTime) => {
    const effectiveEnd = forcedEndTime || endTime;
    const isValidTime = effectiveEnd && /^\d{2}:\d{2}$/.test(effectiveEnd);
    performEndOfShift(isValidTime ? effectiveEnd : getCurrentTime());
  };

  const performEndOfShift = async (effectiveEndTime) => {
    if (isEndingShift) return;
    const nowTime = effectiveEndTime;
    
    setIsEndingShift(true);
    try {
      // 2026-10-16: Samme PDF som manuel download, bygget på alle dagens
      // stemplinger + alle ture afsluttet i dag (hentes friskt, så en
      // automatisk UD-stempling lige før også kommer med).
      const { data: report } = await axios.get(`${API}/driver/day-report`, { params: { date: reportDate } });
      const ts = report.time_summary || {};
      const formattedDate = reportDate.split("-").reverse().join(".");
      const doc = buildDayReportPdf({
        title: "Dagrapport", report, driverName, vehicleReg, date: reportDate, notes,
      });
      const pdfBase64 = doc.output('datauristring').split(',')[1];
      const reportPlads = [...new Set((report.tours || []).map(t => t.plads).filter(Boolean))].join(", ")
        || (selectedPlads && selectedPlads !== "__MINE__" ? selectedPlads : "") || customPlads || "";

      await axios.post(`${API}/driver/end-shift`, {
        driver_name: driverName,
        vehicle_reg: vehicleReg,
        plads: reportPlads,
        report_date: reportDate,
        file_name: `dagrapport_${formattedDate}_${driverName || "rapport"}.pdf`,
        file_data: pdfBase64,
        total_tours: (report.tours || []).length,
        completed_tours: (report.tours || []).length,
        total_weight: (report.tours || []).reduce((sum, t) => sum + (Number(t.weight) || 0), 0),
        start_time: ts.start || startTime,
        end_time: ts.end || nowTime
      });

      // Also download the PDF locally
      doc.save(`dagrapport_${formattedDate}_${driverName || "rapport"}.pdf`);
      
      toast.success("Dagen er afsluttet! Rapport gemt og sendt til admin.");
    } catch (error) {
      console.error("End of shift error:", error);
      toast.error("Fejl ved afslutning: " + error.message);
    } finally {
      setIsEndingShift(false);
    }
  };

  // ============= COMPUTED VALUES =============

  const activeTours = tours.filter(t => !t.is_pause);
  const completedTours = activeTours.filter(t => t.completed);
  const myCompletedTours = activeTours.filter(t => t.completed && t.claimed_by === driverName);
  const totalWeight = activeTours.reduce((sum, t) => sum + (t.weight || 0), 0);
  
  // Filter tours by plads - only show tours that belong to selected plads
  // Fase 15.2 (2026-06-19): Når "Vis afventende ture" er slået til, tillader
  // vi også afventende ture fra ANDRE pladser at dukke op i listen, så
  // chaufføren kan starte dem direkte uden at skifte plads.
  //
  // Fase 15.5 (2026-06-19):
  //   - "Vis afventende" respekterer nu den valgte plads (ingen krydsleak).
  //   - Virtuel plads "__MINE__" → kun chaufførens egne ture (på tværs af
  //     alle pladser). Toggle ON inkluderer mine afventende fra fortiden.
  const todayStrForFilter = getLocalDateStr();
  // Fase 15.8 (2026-02-XX): authUser.id som fallback - selectedDriver bliver
  // aldrig sat i driver-flowet (kun i admin-flowet), så uden fallback ville
  // "Mine ture"-filteret matche NUL admin-tildelte ture.
  const _myIdFlt   = selectedDriver?.id || authUser?.id || "";
  const _myNameFlt = driverName || authUser?.name || authUser?.driver_name || "";
  const _isMineTour = (t) => {
    const byClaim  = (_myIdFlt && t.claimed_by_id === _myIdFlt) || (_myNameFlt && t.claimed_by === _myNameFlt);
    const byAssign = (_myIdFlt && (t.driver_id || "") === _myIdFlt);
    return byClaim || byAssign;
  };
  const filteredTours = selectedPlads
    ? tours.filter(t => {
        // ----- Virtuel "Mine ture"-plads -----
        // Fase 15.5/15.6/15.7 (2026-06-19):
        //   - Default: kun chaufførens egne ture (claimed/assigned by me) på
        //     tværs af alle pladser. Fuldførte styres af visibleTours/
        //     showCompletedDriver-toggle nedstrøms.
        //   - Når "Vis afventende" toggle ON: tillader OGSÅ unclaimed
        //     afventende ture fra fortid/i dag at vises (ikke pre-assigned
        //     til andre, ikke claimed af andre, ikke completed, ikke på vej).
        //   - mineSelectedPlads (sub-dropdown): yderligere filter på plads
        //     uden at navigere væk fra "Mine ture".
        if (selectedPlads === "__MINE__") {
          if (mineSelectedPlads && t.plads !== mineSelectedPlads) return false;
          // Pauser bevares altid
          if (t.is_pause) {
            const q = (tourSearch || "").trim().toLowerCase();
            return !q || true;
          }
          const isMine = _isMineTour(t);
          // Fase 15.13 (2026-02-XX): "Mine ture"-fanen er nu STRICT - kun
          // ture chaufføren ejer (tildelt eller taget af mig). HASTER-
          // undtagelsen er fjernet fordi den forvirrede chaufføren med
          // ture de ikke skulle håndtere. Brug lokationssiden for at se
          // alle HASTER-ture på en specifik plads.
          const q = (tourSearch || "").trim().toLowerCase();
          const passesSearch = !q || (t.fraction || "").toLowerCase().includes(q);
          if (isMine) {
            return passesSearch;
          }
          return false;
        }
        // ----- Almindelig plads-filter -----
        const isThisPlads = t.plads === selectedPlads;
        const isPastPending = showPendingInList
          && !t.completed
          && !t.is_pause
          && (t.date || "").slice(0, 10) < todayStrForFilter
          // Fase 15.5: respekter valgt plads - vis kun afventende fra DENNE plads.
          && t.plads === selectedPlads;
        if (!isThisPlads && !isPastPending) return false;
        if (customerFilter && !t.is_pause) {
          const cn = (t.customer_name || "").trim();
          if (customerFilter === "__own__") {
            if (cn) return false;
          } else if (cn !== customerFilter) {
            return false;
          }
        }
        const q = (tourSearch || "").trim().toLowerCase();
        if (!q) return true;
        if (t.is_pause) return true;
        return (t.fraction || "").toLowerCase().includes(q);
      })
    : []; // Plads seçilmeden turlar gösterilmez

  // Unique customer names visible for the selected plads (used to render the
  // customer-scope tabs above the tour list).
  const customerOptions = React.useMemo(() => {
    if (!selectedPlads) return [];
    const seen = new Set();
    let hasOwn = false;
    tours.forEach(t => {
      if (t.plads !== selectedPlads || t.is_pause) return;
      const cn = (t.customer_name || "").trim();
      if (cn) seen.add(cn); else hasOwn = true;
    });
    const list = Array.from(seen).sort((a, b) => a.localeCompare(b));
    return { customers: list, hasOwn, total: list.length + (hasOwn ? 1 : 0) };
  }, [tours, selectedPlads]);
  
  // Stats for filtered (selected plads) tours
  const filteredActive = filteredTours.filter(t => !t.is_pause);
  const filteredCompleted = filteredActive.filter(t => t.completed);
  const filteredMyCompleted = filteredActive.filter(t => t.completed && t.claimed_by === driverName);
  const filteredOnWay = filteredActive.filter(t => t.on_way && !t.completed);
  const filteredWaiting = filteredActive.filter(t => !t.completed && !t.on_way && (!t.claimed_by || t.claimed_by === driverName));
  const filteredClaimedByOthers = filteredActive.filter(t => (t.on_way || t.completed) && t.claimed_by && t.claimed_by !== driverName);
  const filteredWeight = filteredActive.filter(t => !t.claimed_by || t.claimed_by === driverName).reduce((sum, t) => sum + (t.weight || 0), 0);
  
  // Sort: HASTER on top, then on_way, then route order, then completed last
  const sortedTours = [...filteredTours].sort((a, b) => {
    // Pauses at the end
    if (a.is_pause && !b.is_pause) return 1;
    if (!a.is_pause && b.is_pause) return -1;
    
    // Completed tours at end
    if (a.completed && !b.completed) return 1;
    if (!a.completed && b.completed) return -1;
    
    // HASTER/urgent priority ALWAYS on top (overrides everything)
    const aUrgent = ["urgent", "haster", "high"].includes(String(a.priority || "").toLowerCase()) ? 1 : 0;
    const bUrgent = ["urgent", "haster", "high"].includes(String(b.priority || "").toLowerCase()) ? 1 : 0;
    if (aUrgent !== bUrgent) return bUrgent - aUrgent;
    
    // On way tours next
    if (a.on_way && !b.on_way) return -1;
    if (!a.on_way && b.on_way) return 1;
    
    // Fase 15.9 (2026-02-XX): Tildelte ture FØR frie ture.
    // En tur regnes som tildelt hvis den enten har en admin-tildeling
    // (driver_id sat) eller er claimed_by en chauffør.
    const aAssigned = ((a.driver_id || "").trim() || (a.claimed_by || "").trim()) ? 1 : 0;
    const bAssigned = ((b.driver_id || "").trim() || (b.claimed_by || "").trim()) ? 1 : 0;
    if (aAssigned !== bAssigned) return bAssigned - aAssigned;
    
    // Fase 15.12 (2026-02-XX): Inden for samme sektion sorteres kronologisk.
    // PÅ VEJ-ture sorteres ASC efter on_way_time (først startet → først vist),
    // VENTER-ture sorteres ASC efter order_date (Bestillingsdato), så de
    // mest presserende dato-baserede afhentninger ligger øverst i sektionen.
    if (a.on_way && b.on_way) {
      const at = (a.on_way_time || "").toString();
      const bt = (b.on_way_time || "").toString();
      if (at !== bt) return at.localeCompare(bt);
    }
    if (!a.on_way && !b.on_way) {
      const ad = (a.order_date || "").toString();
      const bd = (b.order_date || "").toString();
      if (ad !== bd) return ad.localeCompare(bd);
    }
    
    // Priority order (high > normal > low)
    const priorityOrder = { urgent: 0, high: 1, normal: 2, low: 3 };
    const aPriority = priorityOrder[a.priority] ?? 2;
    const bPriority = priorityOrder[b.priority] ?? 2;
    if (aPriority !== bPriority) return aPriority - bPriority;
    
    // Respect manual sort_order if set
    if ((a.sort_order || 0) !== (b.sort_order || 0)) {
      return (a.sort_order || 0) - (b.sort_order || 0);
    }
    
    // Group by facility (same facility together)
    if (a.facility !== b.facility) {
      return (a.facility || "").localeCompare(b.facility || "");
    }
    
    // Same facility - sort by address
    return (a.address || "").localeCompare(b.address || "");
  });

  // Fase 11 (2026-06-18): Skjul færdiggjorte ture når toggle er slået fra.
  // Pauser bevares altid (de er ikke ture i klassisk forstand).
  // Fase 15.19 (2026-02-21): KRITISK ISOLATIONS-REGEL - Estimat-bestillinger
  // (tour_type="estimat") må ALDRIG vises på chauffør-siden. De findes kun
  // i "Planlæg ressourcer" på logistik-admin-siden.
  const visibleTours = (showCompletedDriver
    ? sortedTours
    : sortedTours.filter(t => t.is_pause || !t.completed)
  ).filter(t => (t.tour_type || "") !== "estimat");
  
  const calculateTotalTime = () => {
    if (!startTime || !endTime) return "0t 0m";
    const [startH, startM] = startTime.split(":").map(Number);
    const [endH, endM] = endTime.split(":").map(Number);
    let totalMinutes = (endH * 60 + endM) - (startH * 60 + startM);
    if (totalMinutes < 0) totalMinutes += 24 * 60;
    return `${Math.floor(totalMinutes / 60)}t ${totalMinutes % 60}m`;
  };
  
  // Get tour count per plads
  const getPladsTourCount = (plads) => tours.filter(t => t.plads === plads && !t.is_pause).length;

  // ============= RENDER =============

  // ============= MULTI-TENANT AUTH ROUTING =============
  // Public customer order pages (QR-code based) skip auth.
  // For the main app: require login; route by role.
  const isPublicCustomerFlow = currentPage === "customer_code" || currentPage === "customer_order";

  if (!isPublicCustomerFlow) {
    // Token-based password-set/reset routes are public - they MUST be served
    // even if the user is currently logged in (e.g. a logged-in user clicks a
    // colleague's invite link by accident, we still let them complete the
    // password choice; the next login uses their own creds anyway).
    const pathname = typeof window !== "undefined" ? window.location.pathname : "";
    if (pathname.startsWith("/set-password")) return <SetPasswordPage mode="invitation" />;
    if (pathname.startsWith("/reset-password")) return <SetPasswordPage mode="reset" />;

    if (authUser === undefined) {
      // Still checking session
      return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center text-white" data-testid="auth-loading">
          <div className="animate-pulse">Indlæser...</div>
        </div>
      );
    }
    if (authUser === null) {
      return <LoginPage />;
    }
    if (authUser.role === "super_admin") {
      return <SuperAdminPage />;
    }
    if (authUser.role === "customer_admin") {
      return <CustomerAdminPage />;
    }
    if (authUser.role === "location_admin") {
      // Location admin can jump to the order page (CustomerOrderPage) for any
      // of their managed pladser. We pass through via sessionStorage so the
      // redirect survives a full page navigation. The "admin mode" tells the
      // order page to expose the lock/unlock controls for delivery address +
      // opening hours.
      const orderLoc = (() => {
        try { return JSON.parse(sessionStorage.getItem("ladmin_order_loc") || "null"); }
        catch (_) { return null; }
      })();
      if (orderLoc?.code) {
        return (
          <>
            <CustomerOrderPage
              locationCode={orderLoc.code}
              pladsName={orderLoc.name || ""}
              userName={authUser.name}
              adminMode={true}
              onSwitchLocation={(newCode, newName) => {
                // LA "Lokation"-switcher (brugerkrav 2026-06-15 runde 15):
                // Opdater sessionStorage så routeren genåbner ordresiden for
                // den nye plads, og reload så locationCode-prop'en re-mountes.
                try {
                  sessionStorage.setItem("ladmin_order_loc", JSON.stringify({ code: newCode, name: newName }));
                } catch (_) { /* ignore */ }
                window.location.reload();
              }}
              onBack={() => {
                try { sessionStorage.removeItem("ladmin_order_loc"); } catch (_) { /* ignore */ }
                window.location.reload();
              }}
              onLogout={async () => {
                try { sessionStorage.removeItem("ladmin_order_loc"); } catch (_) { /* ignore */ }
                try { await authLogout(); } catch (_) { /* ignore */ }
              }}
            />
          </>
        );
      }
      return <LocationAdminPage />;
    }
    if (authUser.role === "genbrug_plads") {
      return <GenbrugPladsRouter />;
    }
    // "order" role → use existing customer order flow at root
    if (authUser.role === "order" && currentPage === "main") {
      // Brugerkrav 2026-06-15 (runde 9): Multi-lokation medarbejder kan have
      // assigned_plads_ids med 2+ koder. I så fald SKAL pickeren vises så
      // medarbejderen kan vælge hvilken lokation de logger ind på.
      const userAssigned = Array.from(new Set([
        ...(authUser.assigned_plads_ids || []),
        authUser.location_code,
      ].filter(Boolean)));
      const hasMultipleLocations = userAssigned.length > 1;

      // Hvis kun 1 lokation OG location_code er sat → spring picker over
      if (!hasMultipleLocations && authUser.location_code && !customerLocationCode) {
        return (
          <>
            <CustomerOrderPage
              locationCode={authUser.location_code}
              userName={authUser.name}
              onBack={() => { /* "Tilbage til start" resets the form internally;
                                  pinned-location-code users have no picker to return to */ }}
              onLogout={async () => { try { await authLogout(); } catch (_) { /* ignore */ } }}
            />
          </>
        );
      }
      // If a plads was just selected, show the order page for it
      if (customerLocationCode) {
        return (
          <>
            <CustomerOrderPage
              locationCode={customerLocationCode}
              pladsName={customerPladsName}
              prefillAddress={customerPrefillAddress}
              userName={authUser.name}
              onSwitchLocation={(newCode, newName) => {
                // Employee "Lokation"-switcher: simpelthen opdater state og
                // CustomerOrderPage re-renderes med den nye locationCode.
                // Ingen reload nødvendig - useEffect i CustomerOrderPage
                // genhenter location/partners/materials/historik.
                setCustomerLocationCode(newCode);
                setCustomerPladsName(newName || "");
                setCustomerPrefillAddress("");
              }}
              onBack={() => { setCustomerLocationCode(null); setCustomerPladsName(""); setCustomerPrefillAddress(""); }}
              onLogout={async () => { try { await authLogout(); } catch (_) { /* ignore */ } }}
            />
          </>
        );
      }
      // Otherwise show the plads picker (list of cities) for their company
      return (
        <>
          <PladsPickerPage
            onSelect={(code, plads, pickedAddress) => {
              setCustomerLocationCode(code);
              setCustomerPladsName(plads?.name || "");
              if (pickedAddress) {
                const full = [
                  pickedAddress.street,
                  [pickedAddress.postcode, pickedAddress.city].filter(Boolean).join(" "),
                ].filter(Boolean).join(", ");
                const prefix = pickedAddress.sub_area ? `${pickedAddress.sub_area} · ` : "";
                setCustomerPrefillAddress(prefix + full);
              } else {
                setCustomerPrefillAddress("");
              }
            }}
          />
        </>
      );
    }
    // logistics_admin / driver fall through to existing flow below.
  }

  // Customer Order Pages - check first before other pages
  if (currentPage === "customer_code") {
    return (
      <>
        <CustomerCodeEntry onCodeSubmit={(code) => {
          setCustomerLocationCode(code);
          setCurrentPage("customer_order");
        }} />
      </>
    );
  }

  if (currentPage === "customer_order" && customerLocationCode) {
    return (
      <>
        <CustomerOrderPage 
          locationCode={customerLocationCode}
          onBack={() => {
            setCustomerLocationCode(null);
            setCurrentPage("customer_code");
          }}
        />
      </>
    );
  }

  // Admin login handled via JWT LoginPage

  // Admin page
  if (isAdmin) {
    return (
      <>
        <AdminPage onLogout={async () => { setIsAdmin(false); if (authUser) { try { await authLogout(); } catch (_) { /* ignore */ } } }} showConfirm={showConfirm} hideConfirm={hideConfirm} />
        <ConfirmModal
          open={confirmModal.open}
          title={confirmModal.title}
          message={confirmModal.message}
          onConfirm={confirmModal.onConfirm}
          onCancel={hideConfirm}
          variant={confirmModal.variant}
        />
      </>
    );
  }

  // Driver setup screen
  if (!driverSetupDone) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" data-testid="driver-setup">
        {/* PWA Install Banner on Setup */}
        {canInstall && showInstallBanner && (
          <div className="fixed top-0 left-0 right-0 bg-slate-800 text-white px-4 py-2.5 flex items-center justify-between gap-3 text-sm z-50" data-testid="pwa-install-banner-setup">
            <div className="flex items-center gap-2">
              <Download className="w-4 h-4 text-orange-400" />
              <span>Installer ContainerFlow som app</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={async () => { await installPWA(); setShowInstallBanner(false); }}
                className="px-3 py-1 bg-orange-500 rounded-lg font-bold hover:bg-orange-600 text-xs">
                Installer
              </button>
              <button onClick={() => setShowInstallBanner(false)} className="p-1 hover:bg-slate-700 rounded">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
        <div className="w-full max-w-md">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-3 bg-slate-900 text-white px-6 py-3 rounded-xl shadow-lg mb-4">
              <Truck className="w-8 h-8 text-orange-500" />
              <span className="font-heading font-black text-2xl">Container<span className="text-orange-500">Flow</span></span>
            </div>
            <p className="text-sm text-muted-foreground">Smart Container Logistics</p>
          </div>

          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl p-8">
            {setupStep === 1 && (
              <div className="space-y-5" data-testid="setup-step-deprecated">
                {/* Phase 2: Step 1 (email + driver_code) er udfaset.
                    Alle chauffører skal nu logge ind via standard LoginPage med
                    email + password. Vises kun som fallback hvis nogen lander
                    på siden uden authUser. */}
                <div className="text-center">
                  <Shield className="w-12 h-12 mx-auto mb-3 text-orange-500" />
                  <h2 className="font-heading font-bold text-xl">Log ind for at fortsætte</h2>
                  <p className="text-muted-foreground text-sm mt-2">
                    Chauffør-login bruger nu email og adgangskode. Hvis du ikke
                    har et password endnu, kontakt din logistik-admin for en
                    invitation.
                  </p>
                </div>
                <button onClick={async () => { try { await authLogout(); } catch (_) { /* ignore */ } window.location.reload(); }}
                  className="w-full py-3 bg-orange-500 text-white rounded-xl font-bold text-lg hover:bg-orange-600 transition-colors"
                  data-testid="setup-step1-go-login-btn">
                  Gå til login
                </button>
              </div>
            )}

            {setupStep === 2 && (
              <div className="space-y-6" data-testid="setup-step-name">
                <div className="text-center">
                  <Users className="w-12 h-12 mx-auto mb-3 text-orange-500" />
                  <h2 className="font-heading font-bold text-xl">
                    Hej {setupName || authUser?.name || ""}!
                  </h2>
                  <p className="text-muted-foreground text-sm mt-1">Klar til at starte din vagt?</p>
                </div>
                <button onClick={() => {
                  // Fase 5: ved klik på Næste → kunde-picker (hvis nødvendigt),
                  // ellers springer bootstrap useEffect direkte til plate (step 4)
                  if (driverCustomers.length === 0) {
                    setSetupStep(3); // Will show "No customers" empty state
                  } else if (driverCustomers.length === 1 && activeCustomer) {
                    setSetupStep(4);
                  } else if (driverCustomers.length >= 2 && !activeCustomer) {
                    setSetupStep(3);
                  } else {
                    setSetupStep(4);
                  }
                }}
                  className="w-full py-3 bg-orange-500 text-white rounded-xl font-bold text-lg hover:bg-orange-600 transition-colors"
                  data-testid="setup-name-btn">
                  Næste
                </button>
              </div>
            )}

            {/* Fase 5: Customer picker - vises kun når driver har 2+ kunder
                ELLER eksplicit skifter via header-dropdown. */}
            {setupStep === 3 && (
              <div className="space-y-5" data-testid="setup-step-customer">
                <div className="text-center">
                  <Building2 className="w-12 h-12 mx-auto mb-3 text-orange-500" />
                  <h2 className="font-heading font-bold text-xl">Hvilken kunde kører du for i dag?</h2>
                  <p className="text-muted-foreground text-sm mt-1">
                    Du kan skifte senere fra topbjælken
                  </p>
                </div>
                {driverCustomers.length === 0 ? (
                  <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-center text-sm text-amber-800 dark:text-amber-300">
                    <p className="font-semibold mb-1">Ingen kunder tildelt endnu</p>
                    <p className="text-xs">Dit logistik-firma er ikke koblet til nogen kunde. Kontakt din administrator.</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-y-auto" data-testid="customer-picker-list">
                    {driverCustomers.map(c => (
                      <button key={c.id}
                        onClick={async () => {
                          await handleSwitchCustomer(c);
                          const veh = (() => { try { return localStorage.getItem("korkman2_vehicle_reg") || ""; } catch (_) { return ""; } })();
                          if (veh) { setDriverSetupDone(true); }
                          else { setSetupStep(4); }
                        }}
                        className="w-full text-left px-4 py-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 hover:border-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/20 transition-all flex items-center gap-3"
                        data-testid={`customer-option-${c.id}`}>
                        <Building2 className="w-5 h-5 text-orange-500 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="font-bold text-base truncate">{c.name}</p>
                          {c.customer_id && <p className="text-xs text-slate-400">{c.customer_id}{c.city ? ` · ${c.city}` : ""}</p>}
                        </div>
                        <ChevronRight className="w-5 h-5 text-slate-400 flex-shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {setupStep === 4 && (
              <div className="space-y-6" data-testid="setup-step-plate">
                <div className="text-center">
                  <Car className="w-12 h-12 mx-auto mb-3 text-orange-500" />
                  <h2 className="font-heading font-bold text-xl">Hej {setupName}!</h2>
                  <p className="text-muted-foreground text-sm mt-1">Hvilket vognnummer kører du i dag?</p>
                  {activeCustomer && (
                    <div className="mt-3 inline-flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1 rounded-full">
                      <Building2 className="w-3 h-3" />
                      Kører for: <strong>{activeCustomer.name}</strong>
                    </div>
                  )}
                </div>
                <div>
                  {/* Fase 10 (2026-06-17): Vognnummer-dropdown fra firmaets
                      centrale liste (administreret af LA). Hvis listen er
                      tom, kan chaufføren stadig fortsætte med fri-tekst
                      fallback (kommer fra ældre flow + Fase 7). */}
                  {vehiclesList.length > 0 ? (
                    <div className="space-y-2">
                      <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Vognnummer</label>
                      <div className="grid grid-cols-2 gap-2">
                        {vehiclesList.map(v => (
                          <button key={v.id}
                            onClick={() => { setSetupVehicleId(v.id); setSetupPlate(v.number); }}
                            className={`px-3 py-3 rounded-lg font-mono text-sm border-2 transition-all ${
                              setupVehicleId === v.id
                                ? "border-orange-500 bg-orange-50 text-orange-700 font-bold dark:bg-orange-950/30"
                                : "border-slate-200 dark:border-slate-700 hover:border-orange-300 hover:bg-orange-50 dark:hover:bg-orange-950/20"
                            }`}
                            data-testid={`setup-vehicle-option-${v.id}`}>
                            {v.number}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Vognnummer</label>
                      <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg p-2.5">
                        ⚠ Logistik-admin har ikke oprettet vognnumre endnu. Du kan stadig indtaste manuelt nedenfor.
                      </p>
                      <input type="text"
                        inputMode="text"
                        autoCapitalize="characters"
                        value={setupPlate}
                        onChange={(e) => { setSetupPlate(e.target.value.toUpperCase().slice(0, 10)); setSetupVehicleId(""); }}
                        placeholder="INDTAST VOGNNUMMER"
                        className="w-full px-4 py-3 rounded-lg font-mono text-base border-2 border-slate-200 focus:border-orange-500 focus:outline-none text-center tracking-wider uppercase"
                        data-testid="setup-plate-input" />
                    </div>
                  )}
                </div>
                {(setupVehicleId || setupPlate) && (
                  <button onClick={handleSetupPlate}
                    className="w-full py-3 bg-orange-500 text-white rounded-xl font-bold text-lg hover:bg-orange-600 transition-colors"
                    data-testid="setup-plate-btn">
                    Næste
                  </button>
                )}
                {driverCustomers.length > 1 && (
                  <button onClick={() => setSetupStep(3)}
                    className="w-full py-2 text-slate-400 hover:text-slate-600 text-sm"
                    data-testid="setup-back-to-customer-btn">
                    ← Skift kunde
                  </button>
                )}
              </div>
            )}

            {/* Fase 10 (2026-06-17): Trin 5 - vælg hænger (valgfrit). Springes
                automatisk over hvis firmaet ikke har oprettet hængere. */}
            {setupStep === 5 && (
              <div className="space-y-6" data-testid="setup-step-trailer">
                <div className="text-center">
                  <Package2 className="w-12 h-12 mx-auto mb-3 text-purple-500" />
                  <h2 className="font-heading font-bold text-xl">Vælg hænger</h2>
                  <p className="text-muted-foreground text-sm mt-1">
                    Hvilken hænger kører du i dag? Du kan tage flere ture samtidig med en hænger.
                  </p>
                </div>
                <div className="space-y-2">
                  {trailersList.map(t => (
                    <button key={t.id}
                      onClick={() => { setSetupTrailerId(t.id); handleSetupTrailer(t.id); }}
                      className={`w-full px-4 py-3 rounded-xl text-left border-2 transition-all flex items-center justify-between ${
                        setupTrailerId === t.id
                          ? "border-purple-500 bg-purple-50 text-purple-700 font-bold dark:bg-purple-950/30"
                          : "border-slate-200 dark:border-slate-700 hover:border-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950/20"
                      }`}
                      data-testid={`setup-trailer-option-${t.id}`}>
                      <div className="flex items-center gap-3">
                        <Package2 className="w-5 h-5" />
                        <div>
                          <div className="font-bold">{t.number}</div>
                          <div className="text-xs opacity-70 font-normal">Kapacitet: {t.container_capacity} container{t.container_capacity === 1 ? "" : "e"}</div>
                        </div>
                      </div>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 font-semibold">
                        Max {t.container_capacity + 1} ture
                      </span>
                    </button>
                  ))}
                </div>
                <button onClick={() => handleSetupTrailer("")}
                  className="w-full py-3 border-2 border-dashed border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-xl font-medium hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                  data-testid="setup-no-trailer-btn">
                  Ingen hænger - kør videre
                </button>
                <p className="text-[11px] text-center text-muted-foreground">
                  Uden hænger kan du højest tage 1 tur ad gangen. Du kan altid logge ud og vælge en hænger senere.
                </p>
                <button onClick={() => setSetupStep(4)}
                  className="w-full py-2 text-slate-400 hover:text-slate-600 text-sm"
                  data-testid="setup-back-to-vehicle-btn">
                  ← Skift vognnummer
                </button>
              </div>
            )}
          </div>


        </div>
      </div>
    );
  }

  // Main app
  return (
    <div className={`min-h-screen ${lightMode ? "driver-light bg-slate-50" : "bg-slate-900"} pb-20`} data-testid="app-container">
      {/* Fase 11 (2026-06-18): Light-mode baggrund er nu `bg-slate-50` (samme
          som container-siden), ikke ren hvid - for at matche LA-side styling. */}
      
      {/* PWA Install Banner */}
      {canInstall && showInstallBanner && (
        <div className="bg-slate-800 text-white px-4 py-2.5 flex items-center justify-between gap-3 text-sm" data-testid="pwa-install-banner">
          <div className="flex items-center gap-2">
            <Download className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span>Installer ILK som app</span>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={async () => { await installPWA(); setShowInstallBanner(false); }}
              className="px-3 py-1 bg-red-600 rounded-lg font-bold hover:bg-red-700 text-xs" data-testid="pwa-install-btn">
              Installer
            </button>
            <button onClick={() => setShowInstallBanner(false)} className="p-1 hover:bg-slate-700 rounded">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
      
      {/* Offline Mode Banner */}
      {!isOnline && (() => {
        const queueLen = (() => { try { return JSON.parse(localStorage.getItem("ilk-offline-queue") || "[]").length; } catch { return 0; } })();
        return (
          <div className="bg-amber-500 text-black px-4 py-1.5 flex items-center justify-center gap-2 text-xs font-bold" data-testid="offline-banner">
            <WifiOff className="w-3.5 h-3.5" />
            📴 Offline tilstand - viser cached data
            {queueLen > 0 && <span className="bg-black/20 px-2 py-0.5 rounded-full">{queueLen} afventende</span>}
          </div>
        );
      })()}
      
      {/* Header - Professional Toolbar */}
      <header className={`bg-[#0F172A] text-white shadow-lg ${activeTab === 'ture' || activeTab === 'tid' || activeTab === 'profil' ? 'hidden' : ''}`} data-testid="app-header">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-8 py-2">
          {/* Desktop: single row | Mobile: stacked */}
          <div className="hidden md:flex items-center justify-between">
            {/* Brand - desktop */}
            <div className="flex items-center gap-3 mr-4">
              <div>
                <h1 className="font-heading font-black text-lg md:text-xl tracking-tight leading-none">Container<span className="text-orange-500">Flow</span></h1>
                <p className="text-slate-500 text-[10px] leading-none mt-0.5">Smart Container Logistics</p>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-800/60 px-2.5 py-1 rounded-full">
                <span className="text-xs font-semibold text-slate-300 truncate max-w-[120px]">{driverName}</span>
              </div>
            </div>
            {/* Toolbar - desktop (Fase 11 (2026-06-17): wifi/kamera/tema-knapper fjernet
                efter brugerønske; kvitteringer scannes inde fra hver tur).
                Fase 12 (2026-06-18): Billede-ikon (kvittering-liste) fjernet helt
                efter brugerønske - funktionaliteten ønskes ikke længere. */}
            <div className="toolbar-wrap">
              <button onClick={() => showConfirm("Afslut dagen", `Er du sikker på at du vil afslutte denne dag? (${reportDate.split("-").reverse().join(".")})`, () => { hideConfirm(); handleEndOfShift(); }, "warning")}
                disabled={isEndingShift} className="toolbar-btn danger" data-tip="Gün Bitti" data-testid="end-shift-btn">
                <CheckCircle2 className="w-5 h-5" />
              </button>
              <div className="toolbar-divider" />
              <button onClick={() => setShowChat(!showChat)} className="toolbar-btn" data-tip="Beskeder" data-testid="chat-btn">
                <MessageCircle className="w-5 h-5" />
                {driverMessages.filter(m => m.from_admin && !m.read).length > 0 && <span className="badge">{driverMessages.filter(m => m.from_admin && !m.read).length}</span>}
              </button>
              <div className="toolbar-divider" />
              <button onClick={handleLogoutDriver} className="toolbar-btn" data-tip="Log ud" data-testid="logout-btn">
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Mobile: brand row + toolbar row (Fase 11 - 2026-06-17: online-indikator,
              kamera-knap og tema-toggle fjernet per brugerønske. Fase 12 (2026-06-18):
              Billede-ikon (kvittering-liste) fjernet helt).
              Fase 18.11 (2026-02-28): Refresh - brand m. orange Truck-badge,
              kolonne-knapper med tydelige labels + dominant rød "Afslut dag".
              Breakpoint flyttet fra sm:hidden → md:hidden så landscape-mobiler
              også får den nye fede header. */}
          <div className={`md:hidden ${activeTab === 'ture' || activeTab === 'tid' || activeTab === 'profil' ? 'hidden' : ''}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-orange-500 flex items-center justify-center shadow-md flex-shrink-0">
                  <Truck className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h1 className="font-heading font-black text-base tracking-tight leading-none">Container<span className="text-orange-500">Flow</span></h1>
                  <p className="text-slate-400 text-[10px] leading-none mt-0.5 font-medium">{driverName}</p>
                </div>
              </div>
            </div>
            {/* 3 ana buton - uden kamera, uden tema-toggle, uden billed-ikon */}
            <div className="grid grid-cols-3 gap-2">
              {/* Chat */}
              <button
                onClick={() => setShowChat(!showChat)}
                className="relative flex flex-col items-center justify-center gap-1 py-2.5 rounded-2xl bg-slate-700/80 text-slate-300 hover:bg-slate-700 active:scale-95 transition-all"
                data-testid="chat-btn-mobile"
              >
                <MessageCircle className="w-5 h-5" />
                <span className="text-[10px] font-semibold">Beskeder</span>
                {driverMessages.filter(m => m.from_admin && !m.read).length > 0 && (
                  <span className="absolute top-1.5 right-3 w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                )}
              </button>
              {/* Afslut dag - primær handling, visuelt dominant. Kalder
                  handleEndOfShift direkte; Fase 18.2-validerings-modalen
                  inde i den funktion håndterer al bekræftelse. */}
              <button
                onClick={handleEndOfShift}
                disabled={isEndingShift}
                className="flex flex-col items-center justify-center gap-1 py-2.5 rounded-2xl bg-red-600 hover:bg-red-500 active:scale-95 disabled:opacity-50 transition-all shadow-lg shadow-red-900/40"
                data-testid="end-shift-btn-mobile"
              >
                <CheckCircle2 className="w-5 h-5 text-white" />
                <span className="text-[10px] font-bold text-white">Afslut dag</span>
              </button>
              {/* Log ud */}
              <button
                onClick={handleLogoutDriver}
                className="flex flex-col items-center justify-center gap-1 py-2.5 rounded-2xl bg-slate-700/80 text-slate-300 hover:bg-slate-700 active:scale-95 transition-all"
                data-testid="logout-btn-mobile"
              >
                <LogOut className="w-5 h-5" />
                <span className="text-[10px] font-semibold">Log ud</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ============================================================
          Fase 18.15 (2026-02-28) - Trin B (revideret): Mobile "TURE"-tab
          fuld layout efter brugerens screenshot. Indeholder:
            - Brand strip (logo + chauffør + bell)
            - Beskeder/Log ud knapper
            - Stor grøn hero med ring + tilbageværende ture + Næste-warning
            - 3 stat cards (Vægt / Ture / Timer)
            - Mine ture card med dato + aktiv badge + progress bar
            - Søgning + Afventende toggle
            - Mine ture / Lokation switcher
            - Optimer rute knap
            - TUREOVERSIGT header
          Den eksisterende tour-list nedenfor er bevaret uændret. ALLE
          handlers (setShowChat, handleLogoutDriver, setShowPendingInList,
          handleOptimizeRoute, setSelectedPlads, setTourSearch) er
          eksisterende - ZERO funktionsændring.
          ============================================================ */}
      {activeTab === 'ture' && (
        <DriverTodayView
          tours={tours}
          myId={selectedDriver?.id || authUser?.id || ""}
          myName={driverName || authUser?.name || ""}
          reportDate={reportDate}
          setReportDate={setReportDate}
          onPrevDay={() => navigateDate(-1)}
          onNextDay={() => navigateDate(1)}
          customers={driverCustomers}
          activeCustomer={activeCustomer}
          onSwitchCustomer={handleSwitchCustomer}
          unread={driverTourUnread}
          messagesUnread={(driverMessages || []).filter(m => m.from_admin && !m.read).length}
          onMessages={() => setShowChat(true)}
          onStart={(t) => handleToggleOnWay(t.id)}
          onFinish={(t) => {
            // Ture med "Ved afslutning"-valg (nye manuelle ture) bruger det samlede
            // afslutnings-ark. Ældre ture/bestillinger: vægt i tur-panelet.
            if (effectiveCapture(t, finishSettings.unified_finish)) { setFinishTour(t); return; }
            const tt = t.tour_type || "normal";
            const multi = tt === "loes_afhentning" || (t.cargo_lines || []).length > 1;
            const askTrailer = t.used_trailer === true && t.trailer_source === "auto" && !t.trailer_confirmed;
            if (tt === "normal" || multi || t.tour_kind === "goods" || askTrailer) setSelectedTourForPanel(t);
            else if (window.confirm(`Afslut "${TOUR_TYPE_LABELS[tt] || tt}"?\n\n${t.fraction || ""}`)) handleToggleComplete(t.id);
          }}
          onOpen={(t) => setSelectedTourForPanel(t)}
          onChat={(t) => setChatTour(t)}
          getRouteInfo={getRouteInfo}
          onOptimize={handleOptimizeFor}
          optimizing={isOptimizing}
          workedMin={(timeEntries || []).filter(e => e && !e.deleted && e.date === reportDate && (e.slice_type || "work") !== "pause")
            .reduce((sum, e) => sum + (e.duration_minutes || 0), 0)}
        />
      )}
      {(() => {
        // Beregn dagens worked + pause status fra timeEntries
        // Fase 18.17 (2026-02-28): Brug LOKAL dato (getLocalDateStr) i stedet
        // for UTC - ellers vil "i dag" være forkert omkring midnat CEST.
        const todayStr = getLocalDateStr();
        const isToday = reportDate === todayStr;
        const isFutureDate = reportDate > todayStr;
        const dayEntries = (timeEntries || []).filter(e => e && !e.deleted && e.date === reportDate);
        const workEntries = dayEntries.filter(e => (e.slice_type || "work") === "work");
        const pauseEntries = dayEntries.filter(e => e.slice_type === "pause");
        const _toMin = (hhmm) => {
          if (!hhmm || !/^\d{2}:\d{2}$/.test(hhmm)) return -1;
          const [h, m] = hhmm.split(":").map(Number);
          return h * 60 + m;
        };
        const now = new Date();
        const nowMin = now.getHours() * 60 + now.getMinutes();
        let workedMin = 0;
        let firstIn = "";
        let firstInMin = 999999;
        for (const e of workEntries) {
          const sM = _toMin(e.start_time);
          if (sM >= 0 && sM < firstInMin) { firstInMin = sM; firstIn = e.start_time; }
          if (e.end_time) {
            const eM = _toMin(e.end_time);
            if (sM >= 0 && eM >= sM) workedMin += (eM - sM);
          } else if (isToday && sM >= 0 && nowMin > sM) {
            workedMin += (nowMin - sM);
          }
        }
        // Aktiv stempling: seneste work-record uden end_time
        const sortedWork = [...workEntries].sort((a, b) => _toMin(b.start_time) - _toMin(a.start_time));
        const openWork = sortedWork.find(e => !e.end_time);
        const isClockedIn = !!openWork;
        // Pause: seneste pause uden end_time
        const sortedPause = [...pauseEntries].sort((a, b) => _toMin(b.start_time) - _toMin(a.start_time));
        const openPause = sortedPause.find(e => !e.end_time);
        const isOnPause = !!openPause;
        // Ring-progress (8t = 480min)
        const ringPct = Math.max(0, Math.min(1, workedMin / 480));
        const dashOffset = 314 - ringPct * 314;
        const workedH = Math.floor(workedMin / 60);
        const workedM = workedMin % 60;
        // Weekday navn
        const weekdayName = (() => {
          try {
            const d = new Date(reportDate + "T00:00:00");
            return d.toLocaleDateString("da-DK", { weekday: "long" }).toUpperCase();
          } catch (_) { return ""; }
        })();
        const dateBig = (() => {
          try {
            const d = new Date(reportDate + "T00:00:00");
            return d.toLocaleDateString("da-DK", { day: "2-digit", month: "short" }).replace(".", "");
          } catch (_) { return reportDate; }
        })();
        const unreadCount = (driverMessages || []).filter(m => m.from_admin && !m.read).length;

        return (
          <>
            {/* ===== TID TAB (mørk) ===== */}
            {activeTab === 'tid' && (
              <div className="fixed inset-0 z-40 overflow-y-auto" style={{ background: '#0f0f0f', paddingBottom: '76px' }} data-testid="tid-tab">
                <div className="max-w-md mx-auto">
                {/* Header (mørk) */}
                <div className="flex items-center justify-between" style={{ padding: '12px 16px' }}>
                  <div>
                    <h1 className="font-heading font-black tracking-tight leading-none" style={{ fontSize: '15px', color: '#ffffff' }}>
                      Container<span style={{ color: '#f97316' }}>Flow</span>
                    </h1>
                    <p className="font-bold uppercase mt-1" style={{ fontSize: '8px', letterSpacing: '1px', color: '#6b7280' }}>{driverName}</p>
                  </div>
                  <button onClick={() => setShowChat(true)} className="relative flex items-center justify-center" style={{ width: 32, height: 32, borderRadius: 10, background: '#1a1a1a' }} data-testid="tid-tab-bell">
                    <MessageCircle style={{ width: 16, height: 16, color: '#d1d5db' }} />
                    {unreadCount > 0 && <span className="absolute" style={{ top: 6, right: 6, width: 8, height: 8, borderRadius: 999, background: '#f97316' }} />}
                  </button>
                </div>

                {/* Weekday + dato m. chevrons */}
                <div className="text-center" style={{ marginTop: 16 }}>
                  <p className="font-bold uppercase" style={{ fontSize: 11, letterSpacing: 1.5, color: '#6b7280' }}>{weekdayName}</p>
                  <div className="flex items-center justify-center gap-3 mt-2">
                    <button onClick={() => navigateDate(-1)} className="flex items-center justify-center" style={{ width: 32, height: 32, borderRadius: 8, background: '#1a1a1a' }} data-testid="tid-prev-date">
                      <ChevronLeft style={{ width: 16, height: 16, color: '#9ca3af' }} />
                    </button>
                    <h2 className="font-black tracking-tight leading-none" style={{ fontSize: 32, color: '#ffffff', letterSpacing: '-1px' }}>{dateBig}</h2>
                    <button onClick={() => navigateDate(1)} className="flex items-center justify-center" style={{ width: 32, height: 32, borderRadius: 8, background: '#1a1a1a' }} data-testid="tid-next-date">
                      <ChevronRight style={{ width: 16, height: 16, color: '#9ca3af' }} />
                    </button>
                  </div>
                </div>

                {/* Tid-ring */}
                <div className="flex items-center justify-center" style={{ marginTop: 32 }}>
                  <div style={{ position: 'relative', width: 160, height: 160 }}>
                    <svg width="160" height="160" viewBox="0 0 120 120">
                      <circle cx="60" cy="60" r="50" fill="none" stroke="#262626" strokeWidth="6" />
                      <circle cx="60" cy="60" r="50" fill="none" stroke="#f97316" strokeWidth="6" strokeLinecap="round"
                        strokeDasharray="314" strokeDashoffset={dashOffset}
                        transform="rotate(-90 60 60)" style={{ transition: 'stroke-dashoffset 0.5s ease' }} />
                    </svg>
                    <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                      <span className="font-black" style={{ fontSize: 28, color: '#ffffff', lineHeight: 1 }} data-testid="tid-tab-worked">{workedH}t {String(workedM).padStart(2, '0')}m</span>
                      <span className="uppercase font-bold mt-1" style={{ fontSize: 9, color: '#6b7280', letterSpacing: 1 }}>TIMER I DAG</span>
                    </div>
                  </div>
                </div>

                {/* Status */}
                <div className="text-center" style={{ marginTop: 24 }}>
                  {isOnPause ? (
                    <p style={{ fontSize: 11, color: '#f97316' }} data-testid="tid-tab-status">
                      På pause siden kl. <span className="font-bold" style={{ color: '#ffffff' }}>{openPause.start_time}</span>
                    </p>
                  ) : isClockedIn ? (
                    <p style={{ fontSize: 11, color: '#9ca3af' }} data-testid="tid-tab-status">
                      Stemplet ind kl. <span className="font-bold" style={{ color: '#ffffff' }}>{firstIn}</span>
                    </p>
                  ) : (
                    <p style={{ fontSize: 11, color: '#6b7280' }} data-testid="tid-tab-status">Ikke stemplet ind</p>
                  )}
                </div>

                {/* IND / UD - IND aktiv hvis ikke i åbent arbejde. UD aktiv så
                    længe der er åben work. Når der er åben pause skjules begge
                    helt - kun "Afslut pause"-knappen vises nedenfor, og den
                    automatisk genoptager arbejde efter pausen er afsluttet.
                    Fase 18.15 (2026-02-28): Som desktop-version - stempling
                    kan KUN ske på dags dato (!isToday → disabled). */}
                {!isOnPause && (
                  <div className="grid grid-cols-2 gap-2" style={{ margin: '24px 16px 0' }}>
                    <button
                      onClick={() => handlePunch("ind", { sliceType: "work" })}
                      disabled={isClockedIn || !isToday}
                      title={!isToday ? "Stempling kan kun ske på dags dato - skift dato til i dag" : ""}
                      className="flex flex-col items-center justify-center gap-1"
                      style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 14, padding: '16px 8px', opacity: (isClockedIn || !isToday) ? 0.5 : 1, minHeight: 64 }}
                      data-testid="tid-btn-ind"
                    >
                      <Clock style={{ width: 20, height: 20, color: (isClockedIn || !isToday) ? '#4b5563' : '#ffffff' }} />
                      <span className="font-extrabold" style={{ fontSize: 10, letterSpacing: 0.8, color: (isClockedIn || !isToday) ? '#4b5563' : '#ffffff' }}>IND</span>
                    </button>
                    <button
                      onClick={() => handlePunch("ud")}
                      disabled={!isClockedIn || !isToday}
                      title={!isToday ? "Stempling kan kun ske på dags dato - skift dato til i dag" : ""}
                      className="flex flex-col items-center justify-center gap-1"
                      style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 14, padding: '16px 8px', opacity: (!isClockedIn || !isToday) ? 0.5 : 1, minHeight: 64 }}
                      data-testid="tid-btn-ud"
                    >
                      <Clock style={{ width: 20, height: 20, color: (!isClockedIn || !isToday) ? '#4b5563' : '#ffffff' }} />
                      <span className="font-extrabold" style={{ fontSize: 10, letterSpacing: 0.8, color: (!isClockedIn || !isToday) ? '#4b5563' : '#ffffff' }}>UD</span>
                    </button>
                  </div>
                )}

                {/* Pause-knap.
                    Når arbejde er åbent: vis "Start pause".
                    Når pause er åben: vis kun "Afslut pause" - klik lukker
                    pausen OG genstarter arbejde automatisk (ind work). */}
                {(isClockedIn || isOnPause) && (
                  <button
                    onClick={async () => {
                      if (isOnPause) {
                        // Afslut pause + auto-start work igen
                        await handlePunch("ud");
                        await handlePunch("ind", { sliceType: "work" });
                      } else {
                        // Start pause
                        await handlePunch("ind", { sliceType: "pause" });
                      }
                    }}
                    disabled={!isToday}
                    title={!isToday ? "Stempling kan kun ske på dags dato - skift dato til i dag" : ""}
                    className="w-full flex items-center justify-center gap-2"
                    style={{ background: isOnPause ? '#f97316' : '#1a1a1a', border: isOnPause ? '1px solid #f97316' : '1px solid #2a2a2a', borderRadius: 14, padding: '16px 8px', margin: isOnPause ? '24px 16px 0' : '8px 16px 0', width: 'calc(100% - 32px)', opacity: !isToday ? 0.5 : 1, minHeight: isOnPause ? 64 : 48 }}
                    data-testid="tid-btn-pause"
                  >
                    <Pause style={{ width: isOnPause ? 20 : 16, height: isOnPause ? 20 : 16, color: isOnPause ? '#ffffff' : '#d1d5db' }} />
                    <span className="font-extrabold uppercase" style={{ fontSize: isOnPause ? 12 : 10, letterSpacing: 0.8, color: isOnPause ? '#ffffff' : '#d1d5db' }}>
                      {isOnPause ? "AFSLUT PAUSE" : "START PAUSE"}
                    </span>
                  </button>
                )}

                {/* "Mere"-dropdown - kombinerer Manuel stempling + Afslut dag.
                    Klik på den lille kebab-knap åbner panelet under.
                    Afslut dag er KUN blokeret for fremtidige datoer; backdated
                    er tilladt så chaufføren kan lukke en glemt dag. */}
                <div className="relative" style={{ margin: '14px 16px 16px' }} data-testid="tid-more-wrap">
                  <button
                    onClick={() => setTidMenuOpen(v => !v)}
                    className="w-full flex items-center justify-center gap-2"
                    style={{ background: '#111111', border: '1px solid #2a2a2a', borderRadius: 14, padding: '13px 8px', minHeight: 48 }}
                    data-testid="tid-btn-more"
                  >
                    <MoreVertical style={{ width: 16, height: 16, color: '#ffffff' }} />
                    <span className="font-extrabold uppercase" style={{ fontSize: 11, letterSpacing: 0.5, color: '#ffffff' }}>
                      {tidMenuOpen ? "Luk menu" : "Flere handlinger"}
                    </span>
                  </button>
                  {tidMenuOpen && (
                    <div className="absolute left-0 right-0 z-30" style={{ marginTop: 6, background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 12, overflow: 'hidden', boxShadow: '0 12px 28px rgba(0,0,0,0.6)' }} data-testid="tid-more-menu">
                      <button
                        onClick={() => { setTidMenuOpen(false); setShowTimeOverview(true); }}
                        className="w-full flex items-center gap-3"
                        style={{ padding: '14px 16px', minHeight: 52, borderBottom: '0.5px solid #2a2a2a' }}
                        data-testid="tid-menu-manuel"
                      >
                        <Calendar style={{ width: 16, height: 16, color: '#10b981', flexShrink: 0 }} />
                        <div className="text-left flex-1">
                          <p className="font-extrabold uppercase" style={{ fontSize: 11, letterSpacing: 0.4, color: '#ffffff' }}>Dagens stempling · Manuel</p>
                          <p className="font-medium" style={{ fontSize: 10, color: '#9ca3af', marginTop: 1 }}>Tilføj / redigér tidspunkter</p>
                        </div>
                        <ChevronRight style={{ width: 14, height: 14, color: '#6b7280' }} />
                      </button>
                      <button
                        onClick={() => { setTidMenuOpen(false); handleEndOfShift(); }}
                        disabled={isEndingShift || isFutureDate}
                        title={isFutureDate ? "Dagen er fremtidig - kan ikke afslutte" : ""}
                        className="w-full flex items-center gap-3"
                        style={{ padding: '14px 16px', minHeight: 52, opacity: (isEndingShift || isFutureDate) ? 0.4 : 1 }}
                        data-testid="tid-menu-afslut"
                      >
                        <CheckCircle2 style={{ width: 16, height: 16, color: '#ef4444', flexShrink: 0 }} />
                        <div className="text-left flex-1">
                          <p className="font-extrabold uppercase" style={{ fontSize: 11, letterSpacing: 0.4, color: '#ffffff' }}>Afslut dag</p>
                          <p className="font-medium" style={{ fontSize: 10, color: '#9ca3af', marginTop: 1 }}>
                            {isFutureDate ? "Ikke muligt for fremtidig dato" : "Luk dagen - også bagudrettede"}
                          </p>
                        </div>
                        <ChevronRight style={{ width: 14, height: 14, color: '#6b7280' }} />
                      </button>
                    </div>
                  )}
                </div>
                </div>{/* /max-w wrapper */}
              </div>
            )}

            {/* ===== PROFIL TAB (lys) ===== */}
            {activeTab === 'profil' && (() => {
              // 2026-10-17: Profil samler det chaufføren indstiller: hvem man kører
              // for, vogn, hænger, notifikationer og log ud (før manglede både
              // kunde-skift, hænger og log ud her).
              const Row = ({ icon: Icon, label, value, onClick, open, testid }) => (
                <button onClick={onClick} className="w-full flex items-center gap-3 px-4 min-h-[60px] text-left active:bg-slate-50" data-testid={testid}>
                  <span className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0"><Icon className="w-[18px] h-[18px] text-slate-600" /></span>
                  <span className="flex-1 min-w-0"><span className="block text-[11px] text-slate-400">{label}</span><span className="block text-[15px] font-bold text-slate-900 truncate">{value}</span></span>
                  <ChevronDown className={`w-4 h-4 text-slate-300 transition-transform ${open ? "rotate-180" : ""}`} />
                </button>
              );
              const Option = ({ on, label, onClick, testid }) => (
                <button onClick={onClick} className={`w-full flex items-center justify-between gap-2 px-5 min-h-[48px] text-left border-t border-slate-100 ${on ? "bg-orange-50" : "active:bg-slate-50"}`} data-testid={testid}>
                  <span className={`text-[14px] font-semibold truncate ${on ? "text-orange-700" : "text-slate-800"}`}>{label}</span>
                  {on && <Check className="w-4 h-4 text-orange-600 shrink-0" />}
                </button>
              );
              const trailerLabel = (trailersList || []).find(t => t.id === activeTrailerId)?.number || "Ingen hænger";
              return (
              <div className="fixed inset-0 z-40 overflow-y-auto bg-slate-100" style={{ paddingBottom: 96, paddingTop: "env(safe-area-inset-top)" }} data-testid="profil-tab">
                <div className="max-w-md mx-auto px-4 pt-5 space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white flex items-center justify-center text-lg font-extrabold">{(driverName || "?").charAt(0).toUpperCase()}</div>
                    <div className="min-w-0">
                      <p className="text-lg font-extrabold text-slate-900 truncate" data-testid="profil-driver-name">{driverName || "-"}</p>
                      <p className="text-sm text-slate-500 truncate">{authUser?.company_name || "Chauffør"}</p>
                    </div>
                  </div>

                  {(driverCustomers || []).length > 1 && (
                    <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
                      <Row icon={Building2} label="Kører for" value={activeCustomer?.name || "Vælg kunde"} open={profilPicker === 'customer'}
                        onClick={() => setProfilPicker(profilPicker === 'customer' ? null : 'customer')} testid="profil-customer" />
                      {profilPicker === 'customer' && driverCustomers.map(c => (
                        <Option key={c.id} on={activeCustomer?.id === c.id} label={c.name}
                          onClick={() => { setProfilPicker(null); if (activeCustomer?.id !== c.id) handleSwitchCustomer(c); }} />
                      ))}
                    </div>
                  )}

                  <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden divide-y divide-slate-100">
                    <div>
                      <Row icon={Truck} label="Vognnummer" value={vehicleReg || "Vælg vogn"} open={profilPicker === 'vehicle'}
                        onClick={() => setProfilPicker(profilPicker === 'vehicle' ? null : 'vehicle')} testid="profil-vehicle" />
                      {profilPicker === 'vehicle' && (
                        <div className="max-h-64 overflow-y-auto" data-testid="profil-vehicle-picker">
                          {vehiclesList.length === 0 && <p className="px-5 py-3 text-sm text-slate-400 border-t border-slate-100">Ingen vogne oprettet</p>}
                          {vehiclesList.map(v => {
                            const label = v.number || v.registration_number || v.vehicle_number || v.name || `Vogn ${(v.id || "").slice(0, 6)}`;
                            return <Option key={v.id || label} on={vehicleReg === label} label={label} testid={`profil-vehicle-option-${label}`}
                              onClick={() => { setVehicleReg(label); setProfilPicker(null); toast.success(`Vognnummer skiftet til ${label}`); }} />;
                          })}
                        </div>
                      )}
                    </div>
                    {(trailersList || []).length > 0 && (
                      <div>
                        <Row icon={Package2} label="Hænger" value={trailerLabel} open={profilPicker === 'trailer'}
                          onClick={() => setProfilPicker(profilPicker === 'trailer' ? null : 'trailer')} testid="profil-trailer" />
                        {profilPicker === 'trailer' && (
                          <div className="max-h-64 overflow-y-auto">
                            <Option on={!activeTrailerId} label="Ingen hænger" onClick={() => { setProfilPicker(null); handleChangeTrailer(""); }} />
                            {trailersList.map(t => <Option key={t.id} on={activeTrailerId === t.id} label={t.number || t.name} onClick={() => { setProfilPicker(null); handleChangeTrailer(t.id); }} />)}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl bg-white border border-slate-200 px-4 py-3.5" data-testid="profil-push">
                    <div className="flex items-center gap-3">
                      <span className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0"><Bell className="w-[18px] h-[18px] text-slate-600" /></span>
                      <span className="flex-1 min-w-0">
                        <span className="block text-[15px] font-bold text-slate-900">Notifikationer</span>
                        <span className="block text-[12px] text-slate-500">Nye ture, haster, ændringer og beskeder</span>
                      </span>
                      <button role="switch" aria-checked={pushOn} onClick={() => handleTogglePush(!pushOn)} data-testid="profil-push-toggle"
                        className={`w-[52px] h-[30px] rounded-full relative transition-colors shrink-0 ${pushOn ? "bg-emerald-500" : "bg-slate-300"}`}>
                        <span className={`absolute top-[3px] w-6 h-6 rounded-full bg-white shadow transition-all ${pushOn ? "left-[25px]" : "left-[3px]"}`} />
                      </button>
                    </div>
                    {isIOS() && !isStandalone() && (
                      <p className="mt-2 text-[12px] text-amber-800 bg-amber-50 rounded-lg px-3 py-2">På iPhone/iPad virker notifikationer kun når appen er lagt på hjemmeskærmen: tryk Del-ikonet i Safari og vælg "Føj til hjemmeskærm". Åbn så appen derfra.</p>
                    )}
                    {pushSupported() && pushPermission() === "denied" && (
                      <p className="mt-2 text-[12px] text-amber-800 bg-amber-50 rounded-lg px-3 py-2">Notifikationer er blokeret i telefonens indstillinger for denne app. Slå dem til der og prøv igen.</p>
                    )}
                  </div>

                  <button onClick={handleLogoutDriver} className="w-full min-h-[52px] rounded-2xl bg-white border border-slate-200 text-rose-600 font-bold flex items-center justify-center gap-2" data-testid="profil-logout">
                    <LogOut className="w-5 h-5" /> Log ud
                  </button>
                </div>
              </div>
              );
            })()}

            {/* ===== BOTTOM NAV (altid synlig) ===== */}
            <div className="fixed bottom-0 left-0 right-0 z-50 flex"
              style={{
                background: activeTab === 'tid' ? '#0f0f0f' : '#ffffff',
                borderTop: activeTab === 'tid' ? '1px solid #1f1f1f' : '0.5px solid #e5e7eb',
                paddingBottom: 'env(safe-area-inset-bottom, 0px)',
              }}
              data-testid="mobile-bottom-nav"
            >
              {[
                { id: 'tid', label: 'TID', Icon: Clock },
                { id: 'ture', label: 'TURE', Icon: Truck },
                { id: 'profil', label: 'PROFIL', Icon: Users },
              ].map(({ id, label, Icon }) => {
                const isActive = activeTab === id;
                const isDark = activeTab === 'tid';
                const activeColor = isDark ? '#f97316' : '#111111';
                const inactiveColor = isDark ? '#4b5563' : '#9ca3af';
                const color = isActive ? activeColor : inactiveColor;
                return (
                  <button key={id} onClick={() => setActiveTab(id)}
                    className="flex-1 flex flex-col items-center justify-center"
                    style={{ gap: 4, padding: '10px 4px', minHeight: 56, color }}
                    data-testid={`mobile-nav-${id}`}>
                    <Icon style={{ width: 18, height: 18, color }} />
                    <span className="font-bold uppercase" style={{ fontSize: 9, letterSpacing: 0.3, color }}>{label}</span>
                  </button>
                );
              })}
            </div>
          </>
        );
      })()}

      {/* Chat Panel - Private Messaging */}
      {showChat && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-end justify-center sm:items-center" onClick={() => setShowChat(false)}>
          <div
            className="bg-white dark:bg-slate-900 w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-2xl max-h-[88vh] flex flex-col animate-slide-up overflow-hidden border border-slate-200 dark:border-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            {/* iMessage-style Header */}
            <div className="flex items-center justify-between px-3 py-2.5 bg-white/95 dark:bg-slate-900/95 backdrop-blur border-b border-slate-200 dark:border-slate-800">
              <button
                onClick={() => setShowChat(false)}
                className="text-[#007AFF] dark:text-[#0A84FF] text-sm font-medium px-1.5 -ml-1.5 hover:opacity-70"
                data-testid="chat-close-btn"
              >
                <ChevronLeft className="w-5 h-5 inline -mt-0.5" />Tilbage
              </button>
              <div className="flex flex-col items-center">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#34C759] to-[#007AFF] flex items-center justify-center font-bold text-white text-sm shadow-sm">
                  {chatRecipient === "admin" ? <Shield className="w-4 h-4" /> : (chatRecipient ? chatRecipient[0].toUpperCase() : <Users className="w-4 h-4" />)}
                </div>
                <div className="text-[11px] font-medium text-slate-900 dark:text-white mt-0.5 leading-none" data-testid="chat-recipient-name">
                  {chatRecipient === "admin" ? "Admin" : chatRecipient || "Vælg"}
                </div>
              </div>
              <div className="w-16" />
            </div>

            {/* Recipient pill bar */}
            <div className="px-3 py-1.5 border-b border-slate-200 dark:border-slate-800 overflow-x-auto bg-slate-50 dark:bg-slate-900">
              <div className="flex flex-nowrap gap-1.5">
                <button
                  onClick={() => setChatRecipient("admin")}
                  className={`flex-shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-all ${
                    chatRecipient === "admin"
                      ? "bg-[#007AFF] text-white"
                      : "bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700"
                  }`}
                  data-testid="chat-recipient-admin"
                >
                  <Shield className="w-3 h-3 inline mr-1 -mt-0.5" /> Admin
                </button>
                {availableDrivers.map(driver => (
                  <button
                    key={driver.id}
                    onClick={() => setChatRecipient(driver.name)}
                    className={`flex-shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-all ${
                      chatRecipient === driver.name
                        ? "bg-[#007AFF] text-white"
                        : "bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700"
                    }`}
                  >
                    {driver.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Messages - iMessage style, white/dark bg */}
            <div
              className="flex-1 overflow-y-auto px-3 py-2 space-y-1 min-h-[280px] max-h-[420px] bg-white dark:bg-slate-900"
              data-testid="chat-messages-area"
            >
              {getFilteredChatMessages().length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-slate-400 dark:text-slate-500 text-xs text-center max-w-[80%] py-8">
                    Ingen beskeder med <b>{chatRecipient === "admin" ? "Admin" : chatRecipient}</b> endnu.
                    <br />Skriv første besked nedenfor.
                  </div>
                </div>
              ) : (
                getFilteredChatMessages().map((msg, idx, arr) => {
                  const isFromMe = msg.from_driver_name === driverName;
                  const prevMsg = idx > 0 ? arr[idx - 1] : null;
                  const nextMsg = idx < arr.length - 1 ? arr[idx + 1] : null;
                  const showDateDivider = !prevMsg || new Date(prevMsg.created_at).toDateString() !== new Date(msg.created_at).toDateString();
                  // Group consecutive bubbles from same sender (tight stack)
                  const prevSameSender = prevMsg && prevMsg.from_driver_name === msg.from_driver_name && new Date(msg.created_at) - new Date(prevMsg.created_at) < 120000;
                  const nextSameSender = nextMsg && nextMsg.from_driver_name === msg.from_driver_name && new Date(nextMsg.created_at) - new Date(msg.created_at) < 120000;
                  const time = new Date(msg.created_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
                  const dateLabel = (() => {
                    const d = new Date(msg.created_at);
                    const today = new Date();
                    const yest = new Date(); yest.setDate(yest.getDate() - 1);
                    const time2 = d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
                    if (d.toDateString() === today.toDateString()) return `I dag ${time2}`;
                    if (d.toDateString() === yest.toDateString()) return `I går ${time2}`;
                    return d.toLocaleDateString("da-DK", { weekday: "long", day: "2-digit", month: "short" }) + ` ${time2}`;
                  })();

                  // iMessage corner-radius rules for stacked bubbles
                  const radius = isFromMe
                    ? `${prevSameSender ? "rounded-tr-md" : "rounded-tr-2xl"} ${nextSameSender ? "rounded-br-md" : "rounded-br-2xl"} rounded-tl-2xl rounded-bl-2xl`
                    : `${prevSameSender ? "rounded-tl-md" : "rounded-tl-2xl"} ${nextSameSender ? "rounded-bl-md" : "rounded-bl-2xl"} rounded-tr-2xl rounded-br-2xl`;

                  return (
                    <div key={msg.id}>
                      {showDateDivider && (
                        <div className="flex justify-center my-3">
                          <span className="text-slate-400 dark:text-slate-500 text-[11px] font-medium">{dateLabel}</span>
                        </div>
                      )}
                      <div className={`flex ${isFromMe ? "justify-end" : "justify-start"} ${nextSameSender ? "mb-0.5" : "mb-1.5"}`}>
                        <div className={`max-w-[78%] px-3 py-1.5 ${radius} ${
                          isFromMe
                            ? "bg-[#007AFF] text-white"
                            : msg.from_admin
                              ? "bg-[#FF3B30] text-white"
                              : "bg-[#E9E9EB] dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                        }`}>
                          {!isFromMe && msg.from_admin && !prevSameSender && (
                            <p className="text-[10px] font-bold opacity-90 mb-0.5">Admin</p>
                          )}
                          <p className="text-sm whitespace-pre-wrap break-words leading-snug">{msg.content}</p>
                        </div>
                      </div>
                      {!nextSameSender && (
                        <div className={`flex ${isFromMe ? "justify-end" : "justify-start"} mb-1`}>
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 px-1.5 flex items-center gap-1">
                            {time}
                            {isFromMe && (
                              <span className="text-[#007AFF] dark:text-[#0A84FF] font-medium">Leveret</span>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Input - iMessage style */}
            <div className="p-2 bg-slate-50 dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800 flex items-end gap-2">
              <div className="flex-1 flex items-end bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-3xl pl-4 pr-1 py-1">
                <input
                  type="text"
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendChatMessage()}
                  placeholder="iMessage"
                  className="flex-1 bg-transparent border-0 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none py-1.5"
                  data-testid="chat-input-field"
                />
                <button
                  onClick={sendChatMessage}
                  disabled={!chatMessage.trim()}
                  className={`w-7 h-7 flex-shrink-0 rounded-full flex items-center justify-center transition-all ${
                    chatMessage.trim()
                      ? "bg-[#007AFF] text-white hover:bg-[#0064D1]"
                      : "bg-slate-300 dark:bg-slate-700 text-slate-100 dark:text-slate-500 cursor-not-allowed"
                  }`}
                  data-testid="chat-send-btn"
                  aria-label="Send"
                >
                  <Send className="w-3.5 h-3.5" style={{ transform: "translateX(-1px)" }} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Message Box for Driver */}
      {showMessages && driverMessages.length > 0 && (
        <div className="bg-amber-50 border-b-4 border-amber-500 py-4 px-4">
          <div className="max-w-screen-2xl mx-auto">
            <div className="flex items-center gap-2 mb-3">
              <Mail className="w-5 h-5 text-amber-600" />
              <h3 className="font-bold text-amber-800">Beskeder fra admin</h3>
              <button onClick={() => setShowMessages(false)} className="ml-auto text-amber-600 hover:text-amber-800">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-2">
              {driverMessages.map(msg => (
                <div key={msg.id} className="bg-white rounded-lg p-4 shadow-sm border-l-4 border-amber-500 flex items-start justify-between">
                  <div>
                    <p className="text-slate-800">{msg.content}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {new Date(msg.created_at).toLocaleString("da-DK")}
                    </p>
                  </div>
                  <button onClick={() => markMessageRead(msg.id)}
                    className="px-3 py-1 bg-emerald-500 text-white text-sm rounded-lg hover:bg-emerald-600 flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" /> OK
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sticky Controls + Tabs */}
      <div className={`sticky top-0 z-20 bg-white dark:bg-slate-800 border-b transition-all ${isScrolled ? 'shadow-lg' : 'shadow-sm'} ${activeTab === 'ture' || activeTab === 'tid' || activeTab === 'profil' ? 'hidden' : ''}`} data-testid="sticky-controls">
        <div className="max-w-screen-2xl mx-auto px-3 py-2">
          {/* Fase 12 (2026-06-18): ALTID synlig top-række - dato + Ind/Ud +
              Manuel tidsregistrering må aldrig kunne skjules.
              Fase 13 (2026-06-18): Ind/Ud er nu TO separate knapper med
              tilstandsregler: Ind aktiv når ikke stemplet ind, Ud aktiv når
              stemplet ind. Multiple Ind/Ud pr. dag understøttes. */}
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5" data-testid="driver-always-visible-bar">
            {/* Dato med pile */}
            <div className="flex items-center gap-1" data-testid="always-date-group">
              <button onClick={() => navigateDate(-1)}
                className="h-9 w-8 flex-shrink-0 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-600"
                title="Forrige dag" data-testid="always-date-prev-btn">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <input
                type="date"
                value={reportDate}
                onChange={(e) => setReportDate(e.target.value)}
                className="h-9 px-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg font-mono text-xs text-slate-700 dark:text-slate-200 text-center w-[130px]"
                data-testid="always-date-input"
              />
              <button onClick={() => navigateDate(1)}
                className="h-9 w-8 flex-shrink-0 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-600"
                title="Næste dag" data-testid="always-date-next-btn">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Ind / Ud / Start pause - tilstands-baserede knapper.
                Fase 15.30 (2026-02-22): Pause er nu en slice-type. Når
                chaufføren har en åben arbejds-slice vises "Start pause".
                Når chaufføren har en åben pause-slice vises "Start arbejde". */}
            {(() => {
              const openEntry = timeEntries.find(e => !e.end_time);
              const hasOpen = !!openEntry;
              const openIsPause = (openEntry?.slice_type || "work") === "pause";
              // Fase 15.1 (2026-06-19): Ind/Ud må KUN trigges på dags dato.
              const dateLockTitle    = !isToday ? "Stempling kan kun ske på dags dato - skift dato til i dag" : "";

              if (!hasOpen) {
                // Ingen åben slice → vis "Ind" (start arbejde) + Ud (disabled)
                const punchInDisabled  = !isToday;
                const punchOutDisabled = true;
                return (
                  <>
                    <button
                      onClick={() => handlePunch("ind", { sliceType: "work" })}
                      disabled={punchInDisabled}
                      className={`h-9 px-3 rounded-lg text-xs font-bold border-2 transition-colors flex items-center gap-1.5 ${
                        punchInDisabled
                          ? "bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed"
                          : "bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600"
                      }`}
                      data-testid="punch-in-btn"
                      title={!isToday ? dateLockTitle : "Stempl ind nu"}
                    >
                      <Clock className="w-3.5 h-3.5" /> Ind
                    </button>
                    <button
                      disabled={punchOutDisabled}
                      className="h-9 px-3 rounded-lg text-xs font-bold border-2 bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed flex items-center gap-1.5"
                      data-testid="punch-out-btn"
                      title="Stempl ind først"
                    >
                      <Clock className="w-3.5 h-3.5" /> Ud
                    </button>
                  </>
                );
              }

              if (openIsPause) {
                // Pause er åben → "Start arbejde" + "Ud (afslut pause)"
                const disabled = !isToday;
                return (
                  <>
                    <button
                      onClick={() => handlePunch("ind", { sliceType: "work" })}
                      disabled={disabled}
                      className={`h-9 px-3 rounded-lg text-xs font-bold border-2 transition-colors flex items-center gap-1.5 ${
                        disabled
                          ? "bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed"
                          : "bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600"
                      }`}
                      data-testid="punch-start-work-btn"
                      title={!isToday ? dateLockTitle : "Afslut pause og start arbejde igen"}
                    >
                      <Clock className="w-3.5 h-3.5" /> Start arbejde
                    </button>
                    <button
                      onClick={() => handlePunch("ud")}
                      disabled={disabled}
                      className={`h-9 px-3 rounded-lg text-xs font-bold border-2 transition-colors flex items-center gap-1.5 ${
                        disabled
                          ? "bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed"
                          : "bg-orange-500 text-white border-orange-500 hover:bg-orange-600"
                      }`}
                      data-testid="punch-out-btn"
                      title={!isToday ? dateLockTitle : "Slut dagen (afslut pause)"}
                    >
                      <Clock className="w-3.5 h-3.5" /> Ud
                    </button>
                  </>
                );
              }

              // Arbejde er åben → "Start pause" + "Ud"
              const disabled = !isToday;
              return (
                <>
                  <button
                    onClick={() => handlePunch("ind", { sliceType: "pause" })}
                    disabled={disabled}
                    className={`h-9 px-3 rounded-lg text-xs font-bold border-2 transition-colors flex items-center gap-1.5 ${
                      disabled
                        ? "bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed"
                        : "bg-blue-500 text-white border-blue-500 hover:bg-blue-600"
                    }`}
                    data-testid="punch-start-pause-btn"
                    title={!isToday ? dateLockTitle : "Pausér arbejdet nu"}
                  >
                    <Pause className="w-3.5 h-3.5" /> Start pause
                  </button>
                  <button
                    onClick={() => handlePunch("ud")}
                    disabled={disabled}
                    className={`h-9 px-3 rounded-lg text-xs font-bold border-2 transition-colors flex items-center gap-1.5 ${
                      disabled
                        ? "bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600 cursor-not-allowed"
                        : "bg-orange-500 text-white border-orange-500 hover:bg-orange-600"
                    }`}
                    data-testid="punch-out-btn"
                    title={!isToday ? dateLockTitle : "Stempl ud nu"}
                  >
                    <Clock className="w-3.5 h-3.5" /> Ud
                  </button>
                </>
              );
            })()}

            {/* Fase 15.31 (2026-02-22): Topbar-"Manuel"-knap fjernet - manuel
                tidsregistrering oprettes nu via "Tilføj manuel" inde i
                Dagens stempling-modalet (åbnes via klokke-overview-knappen). */}

            {/* Day overview - kompakt sammenfatning af dagens stempling.
                Fase 15.30 (2026-02-22): Viser arbejdstid + pausetid separat.
                Fase 15.31 (2026-02-22): Knappen vises ALTID (også uden
                entries) - så chaufføren kan åbne modalet og bruge
                "Tilføj manuel" til at oprette sin første registrering. */}
            {(() => {
              const workMin = timeEntries
                .filter(e => (e.slice_type || "work") !== "pause")
                .reduce((sum, e) => sum + (e.duration_minutes || 0), 0);
              const pauseMin = timeEntries
                .filter(e => (e.slice_type || "work") === "pause")
                .reduce((sum, e) => sum + (e.duration_minutes || 0), 0);
              const openEntry = timeEntries.find(e => !e.end_time);
              const hasOpen = !!openEntry;
              const openIsPause = (openEntry?.slice_type || "work") === "pause";
              const wh = Math.floor(workMin / 60);
              const wm = workMin % 60;
              const ph = Math.floor(pauseMin / 60);
              const pm = pauseMin % 60;
              const hasEntries = timeEntries.length > 0;
              return (
                <button
                  onClick={() => setShowTimeOverview(true)}
                  className="h-9 px-3 rounded-lg text-xs font-bold border-2 border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-950/50 transition-colors flex items-center gap-1.5"
                  data-testid="time-overview-btn"
                  title={hasEntries ? `Arbejde ${wh}t ${wm}m · Pause ${ph}t ${pm}m - klik for detaljer` : "Vis dagens stempling-overblik (tom)"}
                >
                  <Clock className="w-3.5 h-3.5" />
                  {hasEntries
                    ? <>{wh}t {String(wm).padStart(2, "0")}m</>
                    : <span>Stempling</span>}
                  {hasEntries && pauseMin > 0 && (
                    <span className="text-blue-600 dark:text-blue-300 font-mono" data-testid="punch-summary-pause">
                      +{ph > 0 ? `${ph}t ` : ""}{String(pm).padStart(2, "0")}m P
                    </span>
                  )}
                  {hasOpen && (
                    <span className={`ml-1 px-1 py-0.5 rounded text-[9px] ${
                      openIsPause
                        ? "bg-blue-200 dark:bg-blue-800/50 text-blue-700 dark:text-blue-300"
                        : "bg-amber-200 dark:bg-amber-800/50 text-amber-700 dark:text-amber-300"
                    }`} data-testid="punch-summary-open-state">
                      {openIsPause ? "PAUSE" : "ÅBEN"}
                    </span>
                  )}
                </button>
              );
            })()}

            {/* Fase 15.2 (2026-06-19): "Afventende ture"-knappen er flyttet
                ned tæt på tur-listen så chaufføren kan slå funktionen til/fra
                lige hvor turene vises. Toggle udvider hovedlisten i stedet
                for at åbne modal. Se afventende-toggle-btn længere nede. */}
          </div>

          {/* Collapsed Toolbar Summary - always visible */}
          <button onClick={() => setToolbarExpanded(!toolbarExpanded)}
            className="w-full flex items-center justify-between px-2 py-1.5 rounded-xl bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors mt-1.5"
            data-testid="toolbar-toggle">
            <div className="flex items-center gap-2 min-w-0">
              <Users className="w-3.5 h-3.5 text-red-600 flex-shrink-0" />
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300 truncate">{driverName}</span>
              <span className="text-[10px] text-slate-400">|</span>
              <Car className="w-3 h-3 text-slate-400 flex-shrink-0" />
              <span className="text-xs font-mono font-semibold text-slate-600 dark:text-slate-400">{vehicleReg || "-"}</span>
            </div>
            <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${toolbarExpanded ? "rotate-180" : ""}`} />
          </button>

          {/* Expanded Controls */}
          {toolbarExpanded && (
          <div className="mt-2 space-y-2">
          {/* Controls Grid - 2 cols mobile, 4 cols desktop */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-2">
            {/* Fase 5: Kunde-vælger (kun synlig hvis driver kører for 2+ kunder).
                Switch resetter tour/plads-listen så ingen residual data fra
                forrige kunde vises.
                Fase 11 (2026-06-18): Grøn farve fjernet (var usynlig mod lys
                baggrund) - bruger nu neutrale slate-farver som matcher
                container-siden. */}
            {driverCustomers.length >= 2 && (
              <div className="relative order-1 col-span-2 md:col-span-1" data-testid="customer-switcher-group">
                <label className="block text-[11px] font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">Kunde</label>
                <button onClick={(e) => { e.stopPropagation(); setCustomerSwitchOpen(!customerSwitchOpen); setShowPlateDropdown(false); setShowPladsDropdown(false); }}
                  className="w-full h-10 px-3 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 flex items-center justify-between text-sm hover:border-orange-400 transition-colors"
                  data-testid="customer-switcher-btn">
                  <div className="flex items-center gap-2 min-w-0">
                    <Building2 className="w-4 h-4 text-orange-500 flex-shrink-0" />
                    <span className="truncate font-semibold text-slate-800 dark:text-slate-100">{activeCustomer?.name || "Vælg..."}</span>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${customerSwitchOpen ? "rotate-180" : ""}`} />
                </button>
                {customerSwitchOpen && (
                  <div className="absolute z-30 w-full mt-1 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg shadow-xl max-h-48 overflow-y-auto" data-testid="customer-switcher-dropdown">
                    {driverCustomers.map(c => (
                      <button key={c.id} onClick={() => handleSwitchCustomer(c)}
                        className={`w-full px-3 py-2.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0 ${activeCustomer?.id === c.id ? "bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 font-bold" : "text-slate-700 dark:text-slate-300"}`}
                        data-testid={`customer-switcher-option-${c.id}`}>
                        <div className="flex items-center gap-2">
                          <Building2 className="w-4 h-4 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate">{c.name}</p>
                            {c.customer_id && <p className="text-[10px] text-slate-500">{c.customer_id}{c.city ? ` · ${c.city}` : ""}</p>}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Vehicle - order 1 on mobile, 1 on desktop */}
            <div className="relative order-1" data-testid="vehicle-group">
              <label className="block text-[11px] font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">Vogn</label>
              <button onClick={(e) => { e.stopPropagation(); setShowPlateDropdown(!showPlateDropdown); setShowPladsDropdown(false); }}
                className="w-full h-10 px-3 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 flex items-center justify-between text-sm font-mono hover:border-orange-300 transition-colors"
                data-testid="vehicle-reg-input">
                <div className="flex items-center gap-2 min-w-0">
                  <Car className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <span className={`truncate ${vehicleReg ? "font-semibold text-slate-800 dark:text-slate-200" : "text-slate-400"}`}>{vehicleReg || "Vælg..."}</span>
                </div>
                <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${showPlateDropdown ? "rotate-180" : ""}`} />
              </button>
              {showPlateDropdown && (
                <div className="absolute z-30 w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-xl max-h-48 overflow-y-auto">
                  {drivers.map(d => d.plate).filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).map(plate => (
                    <button key={plate} onClick={() => { handleChangePlate(plate); setShowPlateDropdown(false); }}
                      className={`w-full px-3 py-2.5 text-left font-mono text-sm hover:bg-slate-700 border-b border-slate-700 last:border-0 ${vehicleReg === plate ? "bg-slate-700 text-orange-400 font-bold" : "text-slate-300"}`}>
                      {plate}
                    </button>
                  ))}
                  <div className="p-2 border-t border-slate-700">
                    <input type="text" value={vehicleReg}
                      onChange={(e) => handleChangePlate(e.target.value.toUpperCase())}
                      placeholder="Skriv manuelt..."
                      className="w-full h-9 px-3 bg-slate-700 border border-slate-600 rounded-lg text-sm font-mono text-white"
                      onClick={(e) => e.stopPropagation()} />
                  </div>
                </div>
              )}
            </div>

            {/* Fase 11 (2026-06-18): Hænger-vælger (hvis firmaet har hængere).
                Chaufføren kan skifte hænger fra headeren - ikke kun ved login. */}
            {(trailersList || []).length > 0 && (
              <div className="relative order-2" data-testid="trailer-group">
                <label className="block text-[11px] font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">Hænger</label>
                <button onClick={(e) => { e.stopPropagation(); setShowTrailerDropdown(v => !v); setShowPlateDropdown(false); setShowPladsDropdown(false); setCustomerSwitchOpen(false); }}
                  className="w-full h-10 px-3 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 flex items-center justify-between text-sm font-mono hover:border-orange-300 transition-colors"
                  data-testid="trailer-picker-btn">
                  <div className="flex items-center gap-2 min-w-0">
                    <Truck className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    {(() => {
                      const cur = trailersList.find(t => t.id === activeTrailerId);
                      return (
                        <span className={`truncate ${cur ? "font-semibold text-slate-800 dark:text-slate-200" : "text-slate-400"}`}>
                          {cur ? `${cur.number}${cur.container_capacity != null ? ` · ${cur.container_capacity} stk` : ""}` : "Ingen hænger"}
                        </span>
                      );
                    })()}
                  </div>
                  <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${showTrailerDropdown ? "rotate-180" : ""}`} />
                </button>
                {showTrailerDropdown && (
                  <div className="absolute z-30 w-full mt-1 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg shadow-xl max-h-48 overflow-y-auto" data-testid="trailer-picker-dropdown">
                    <button onClick={() => handleChangeTrailer("")}
                      className={`w-full px-3 py-2.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 ${!activeTrailerId ? "bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 font-bold" : "text-slate-700 dark:text-slate-300"}`}
                      data-testid="trailer-picker-option-none">
                      <span className="inline-flex items-center gap-2"><X className="w-3.5 h-3.5" /> Ingen hænger (max 1 tur ad gangen)</span>
                    </button>
                    {trailersList.map(t => (
                      <button key={t.id} onClick={() => handleChangeTrailer(t.id)}
                        className={`w-full px-3 py-2.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0 ${activeTrailerId === t.id ? "bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 font-bold" : "text-slate-700 dark:text-slate-300"}`}
                        data-testid={`trailer-picker-option-${t.id}`}>
                        <div className="flex items-center gap-2">
                          <Truck className="w-4 h-4 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <p className="font-mono font-semibold truncate">{t.number}</p>
                            <p className="text-[10px] text-slate-500">Kapacitet: {t.container_capacity ?? 1} container{(t.container_capacity ?? 1) !== 1 ? "e" : ""} · max {(t.container_capacity ?? 1) + 1} samtidige ture</p>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Fase 12 (2026-06-18): Start/Slut tids-felter + dato-vælger
                fjernet fra expanded-toolbar. Erstattet af "Ind/Ud"-knap +
                "Manuel tidsregistrering" i den ALTID synlige bar i toppen
                (driver-always-visible-bar). */}
          </div>

          {/* Date label bar */}
          <div className="flex items-center justify-between mt-1.5 px-1">
            <span className={`text-xs font-bold ${isToday ? "text-orange-400" : "text-slate-500"}`} data-testid="date-label">
              {formatDateLabel(reportDate)}
            </span>
            {!isToday && (
              <button onClick={goToToday}
                className="text-[10px] font-medium text-orange-400 hover:text-orange-300 px-2 py-0.5 bg-slate-700 rounded-full"
                data-testid="go-today-btn">
                I dag
              </button>
            )}
          </div>
          </div>
          )}

          {/* Plads Selection.
              Fase 12 (2026-06-18): Knap omdøbt fra "Vælg genbrugsplads…" til
              "Lokationer" + bredde optimeret.
              Fase 14 (2026-06-19): Lokationsvælgeren var alt for bred -
              fyldte hele kort-bredden med stort tomrum efter "Blishøj 1 (2)".
              Begrænset til max ~260px (sm:max-w-xs) og indholdet pakkes ind
              i en w-fit-stil så badget altid sidder lige ved siden af navnet. */}
          <div className="mt-3 relative w-full max-w-[260px]">
            <button onClick={(e) => { e.stopPropagation(); setShowPladsDropdown(!showPladsDropdown); setShowPlateDropdown(false); }}
              className={`w-full px-3 py-2 rounded-xl text-left flex items-center justify-between transition-all text-sm ${selectedPlads ? "bg-slate-700 border-2 border-orange-500" : "bg-slate-700 border-2 border-slate-600 hover:border-orange-400"}`}
              data-testid="plads-dropdown-btn">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <MapPin className={`w-4 h-4 flex-shrink-0 ${selectedPlads ? "text-orange-500" : "text-slate-400"}`} />
                <span className={`truncate ${selectedPlads ? "font-bold text-orange-400 text-sm" : "text-slate-400 text-sm"}`}>
                  {selectedPlads === "__MINE__" ? "Mine ture" : (selectedPlads || "Lokationer")}
                </span>
                {selectedPlads && (
                  <span className="px-1.5 py-0.5 bg-orange-500 text-white text-[10px] rounded-full font-bold flex-shrink-0">
                    {selectedPlads === "__MINE__"
                      ? (tours || []).filter(t => {
                          if (t.is_pause || t.completed) return false;
                          // Fase 15.8: authUser fallback (selectedDriver er null)
                          const myId   = selectedDriver?.id || authUser?.id || "";
                          const myName = driverName || authUser?.name || authUser?.driver_name || "";
                          const byClaim  = (myId && t.claimed_by_id === myId) || (myName && t.claimed_by === myName);
                          const byAssign = (myId && (t.driver_id || "") === myId);
                          return byClaim || byAssign;
                        }).length
                      : getPladsTourCount(selectedPlads)}
                  </span>
                )}
              </div>
              <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform flex-shrink-0 ml-1 ${showPladsDropdown ? "rotate-180" : ""}`} />
            </button>
            {showPladsDropdown && (
              <div className="absolute z-30 w-full mt-1 bg-slate-800 border-2 border-slate-600 rounded-xl shadow-xl max-h-64 overflow-y-auto">
                {/* Fase 15.5 (2026-06-19): Virtuel "Mine ture"-option øverst.
                    Viser KUN chaufførens egne ture (på tværs af alle pladser).
                    Når valgt + "Vis afventende" toggle ON → driver ser ALLE
                    deres afventende ture uanset plads. */}
                {(() => {
                  // Fase 15.8: authUser fallback (selectedDriver er null)
                  const myId   = selectedDriver?.id || authUser?.id || "";
                  const myName = driverName || authUser?.name || authUser?.driver_name || "";
                  const mineCount = (tours || []).filter(t => {
                    if (t.is_pause || t.completed) return false;
                    const byClaim  = (myId && t.claimed_by_id === myId) || (myName && t.claimed_by === myName);
                    const byAssign = (myId && (t.driver_id || "") === myId);
                    return byClaim || byAssign;
                  }).length;
                  const active = selectedPlads === "__MINE__";
                  return (
                    <button onClick={() => { setSelectedPlads("__MINE__"); setMineSelectedPlads(""); setShowPladsDropdown(false); }}
                      className={`w-full px-4 py-2.5 text-left flex items-center justify-between hover:bg-slate-700 border-b border-slate-600 text-sm ${active ? "bg-slate-700" : "bg-indigo-950/40"}`}
                      data-testid="plads-option-mine">
                      <div className="flex items-center gap-2">
                        <Users className={`w-4 h-4 ${active ? "text-indigo-300" : "text-indigo-400"}`} />
                        <span className={active ? "text-indigo-300 font-bold" : "text-indigo-200 font-bold"}>Mine ture</span>
                      </div>
                      {mineCount > 0 && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${active ? "bg-indigo-500 text-white" : "bg-indigo-600/70 text-white"}`}>{mineCount}</span>
                      )}
                    </button>
                  );
                })()}
                {pladsOptions.map(plads => {
                  const count = getPladsTourCount(plads);
                  return (
                    <button key={plads} onClick={() => { setSelectedPlads(plads); setMineSelectedPlads(""); setShowPladsDropdown(false); }}
                      className={`w-full px-4 py-2.5 text-left flex items-center justify-between hover:bg-slate-700 border-b border-slate-700 last:border-0 text-sm ${selectedPlads === plads ? "bg-slate-700" : ""}`}
                      data-testid={`plads-option-${plads.toLowerCase()}`}>
                      <div className="flex items-center gap-2">
                        <MapPin className={`w-4 h-4 ${selectedPlads === plads ? "text-orange-500" : "text-slate-400"}`} />
                        <span className={selectedPlads === plads ? "text-orange-400 font-bold" : "text-slate-300 font-medium"}>{plads}</span>
                      </div>
                      {count > 0 && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${selectedPlads === plads ? "bg-orange-500 text-white" : "bg-slate-600 text-slate-300"}`}>{count}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          {/* Fase 15.6 (2026-06-19): Sub-dropdown der KUN vises når
              "Mine ture" er aktiv. Tillader chaufføren at filtrere deres
              egne ture på en specifik lokation uden at forlade "Mine ture". */}
          {selectedPlads === "__MINE__" && (
            <div className="mt-2 w-full max-w-[260px]" data-testid="mine-plads-filter-wrap">
              <label className="block text-[10px] font-bold text-indigo-300 uppercase tracking-wider mb-1">
                Se mine ture for en lokation
              </label>
              <select
                value={mineSelectedPlads}
                onChange={(e) => setMineSelectedPlads(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm bg-slate-700 border-2 border-indigo-700 text-indigo-200 font-semibold focus:outline-none focus:border-indigo-400"
                data-testid="mine-plads-filter-select"
              >
                <option value="">Alle mine lokationer</option>
                {(() => {
                  // Kun pladser hvor jeg faktisk HAR ture
                  // Fase 15.8: authUser fallback (selectedDriver er null i driver-flowet)
                  const myId   = selectedDriver?.id || authUser?.id || "";
                  const myName = driverName || authUser?.name || authUser?.driver_name || "";
                  const myPladser = Array.from(new Set((tours || [])
                    .filter(t => {
                      const byClaim  = (myId && t.claimed_by_id === myId) || (myName && t.claimed_by === myName);
                      const byAssign = (myId && (t.driver_id || "") === myId);
                      return (byClaim || byAssign) && t.plads;
                    })
                    .map(t => t.plads)))
                    .sort();
                  return myPladser.map(p => (
                    <option key={p} value={p}>{p}</option>
                  ));
                })()}
              </select>
            </div>
          )}
        </div>

        {/* Tab Bar fjernet (Fase 12 - 2026-06-18): Med "Tilføj tur manuelt"
            flyttet til Logistik Admin er der kun "Ture"-fanen tilbage -
            ingen grund til et tab-bar. Aktive ture vises direkte nedenfor. */}
      </div>

      {/* Main Content - Tab Views */}
      <main className="max-w-screen-2xl mx-auto p-4 md:p-6 space-y-3">

        {/* === TRIPS TAB === */}
        {activeDriverTab === "trips" && (
          <>
            {/* 2026-10-16: Den gamle mørke turliste (hero, progress, HÆNGER/SOLO-
                sektioner) var altid skjult bag TID/TURE/PROFIL-fanerne men blev
                stadig renderet ved hver 5-sek. opdatering. Fjernet - TURE-fanen
                bruger nu DriverTourCard. */}
        
        {/* Mobile Tour Detail Panel */}
        {selectedTourForPanel && (
          <MobileTourPanel
            tour={selectedTourForPanel}
            onClose={() => setSelectedTourForPanel(null)}
            onUpdate={handleUpdateTour}
            onDelete={handleDeleteTour}
            onToggleOnWay={handleToggleOnWay}
            onToggleComplete={handleToggleComplete}
            currentDriverName={driverName}
            onChat={() => { const t = selectedTourForPanel; setSelectedTourForPanel(null); setChatTour(t); }}
            onRefresh={fetchTours}
            onOpenFinish={(t) => setFinishTour(t)}
            unifiedFinish={!!finishSettings.unified_finish}
            deviationCodes={finishSettings.codes || []}
          />
        )}

        <DriverChatSheet tour={chatTour} onClose={() => setChatTour(null)} onChanged={fetchDriverTourUnread} />
        {finishTour && (
          <FinishSheet tour={finishTour} onClose={() => setFinishTour(null)}
            capture={effectiveCapture(finishTour, finishSettings.unified_finish)} codes={finishSettings.codes} hasTrailer={!!activeTrailerId}
            onDone={(r) => {
              setSelectedTourForPanel(null);
              // Uden net: vis turen som afsluttet med det samme (køen sender den).
              if (r?.queued) setTours(prev => prev.map(t => (t.id === r.tourId ? { ...t, ...(r.regs?.weight != null ? { weight: r.regs.weight } : {}), completed: true, on_way: false, queued: true } : t)));
              else fetchTours();
            }}
            driverName={driverName} myId={selectedDriver?.id || authUser?.id || ""} />
        )}

        {pushPrompt && authUser?.role === "driver" && (
          <div className="fixed inset-x-0 z-[85] px-3" style={{ bottom: "calc(84px + env(safe-area-inset-bottom))" }} data-testid="push-prompt">
            <div className="max-w-md mx-auto rounded-2xl bg-slate-900 text-white shadow-2xl p-4">
              <div className="flex items-start gap-3">
                <Bell className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="font-bold">Få besked på telefonen</p>
                  {pushPrompt === "ask" ? (
                    <p className="text-sm text-slate-300 mt-0.5">Når du får en ny tur, en haster-tur, en ændring eller en besked fra planlæggeren - også når appen er lukket.</p>
                  ) : (
                    <p className="text-sm text-slate-300 mt-0.5">Læg appen på hjemmeskærmen for at få notifikationer: tryk Del-ikonet i Safari → "Føj til hjemmeskærm", og åbn appen derfra.</p>
                  )}
                </div>
                <button onClick={dismissPushPrompt} className="p-1 -mr-1 text-slate-400" aria-label="Luk"><X className="w-5 h-5" /></button>
              </div>
              {pushPrompt === "ask" && (
                <div className="mt-3 flex gap-2">
                  <button onClick={() => handleTogglePush(true)} className="flex-1 h-11 rounded-xl bg-orange-500 font-bold" data-testid="push-prompt-enable">Slå til</button>
                  <button onClick={dismissPushPrompt} className="h-11 px-4 rounded-xl bg-white/10 font-semibold">Senere</button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Fase 14 (2026-06-19): "Bemærkninger"-sektionen er fjernet pr.
            brugerens ønske - den blev ikke brugt. */}

        {/* PDF button moved to header */}
          </>
        )}

        {/* === ADD TRIP TAB === */}
        {activeDriverTab === "addTrip" && (
          <section className="bg-white dark:bg-slate-800 rounded-lg border border-border shadow-sm" data-testid="add-trip-form">
            <div className="p-3 border-b border-border">
              <h2 className="font-heading font-bold text-base flex items-center gap-2">
                <Plus className="w-5 h-5 text-orange-500" /> Tilføj tur manuelt
              </h2>
            </div>
            <div className="p-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                <input type="text" value={manualFraction} onChange={(e) => setManualFraction(e.target.value)}
                  placeholder="Fraktion" className="px-3 py-2 border rounded-lg text-sm" data-testid="manual-fraction-input" />
                <input type="text" value={manualFacility} onChange={(e) => setManualFacility(e.target.value)}
                  placeholder="Modtageanlæg" className="px-3 py-2 border rounded-lg text-sm" data-testid="manual-facility-input" />
                <input type="text" value={manualAddress} onChange={(e) => setManualAddress(e.target.value)}
                  placeholder="Adresse" className="px-3 py-2 border rounded-lg text-sm" data-testid="manual-address-input" />
                <input type="text" value={manualContainer} onChange={(e) => setManualContainer(e.target.value)}
                  placeholder="Container" className="px-3 py-2 border rounded-lg font-mono text-sm" data-testid="manual-container-input" />
                <label className="flex items-center gap-2 px-3 py-2">
                  <input type="checkbox" checked={isSameDay} onChange={(e) => setIsSameDay(e.target.checked)}
                    className="w-4 h-4 rounded" data-testid="same-day-checkbox" />
                  <span className="text-sm">Samme dag</span>
                </label>
              </div>
              
              {/* Privat tur section */}
              <div className="mt-3 p-3 bg-purple-50 dark:bg-purple-950/30 rounded-lg border border-purple-200">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={isPrivateTour} onChange={(e) => setIsPrivateTour(e.target.checked)}
                    className="w-4 h-4 rounded accent-purple-600" data-testid="private-tour-checkbox" />
                  <span className="text-sm font-medium text-purple-800">Privat tur (særlig firma)</span>
                </label>
                {isPrivateTour && (
                  <input 
                    type="text" 
                    value={privateCompany} 
                    onChange={(e) => setPrivateCompany(e.target.value)}
                    placeholder="Firma navn (f.eks. Mærsk, DSV...)"
                    className="mt-2 w-full px-3 py-2 border border-purple-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm"
                    data-testid="private-company-input"
                  />
                )}
              </div>
              
              <button onClick={async () => {
                  if (!manualFraction || !manualFacility) { toast.error("Udfyld fraktion og modtageanlæg!"); return; }
                  await handleAddManualTour();
                  setActiveDriverTab("trips");
                }}
                className="mt-4 flex items-center gap-2 px-6 py-2.5 bg-orange-500 text-white rounded-lg font-medium hover:bg-orange-600 w-full justify-center"
                data-testid="add-trip-submit-btn">
                <Plus className="w-4 h-4" /> Tilføj tur
              </button>
            </div>
          </section>
        )}
      </main>

      {/* Mobile PDF button moved to header */}

      {/* Receipt Scanner Overlay */}
      {showReceiptScanner && (
        <ReceiptScanner 
          onSave={handleSaveReceipt}
          onClose={() => setShowReceiptScanner(false)}
          driverName={driverName}
          plads={selectedPlads}
        />
      )}

      {/* Receipt List Overlay */}
      {showReceiptList && (
        <div className="fixed inset-0 bg-black/50 z-40 flex items-end md:items-center justify-center" onClick={() => setShowReceiptList(false)}>
          <div className="bg-white dark:bg-slate-800 w-full md:max-w-lg md:rounded-2xl rounded-t-2xl max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
              <h2 className="font-bold text-lg flex items-center gap-2">
                <Camera className="w-5 h-5 text-amber-600" /> Mine kvitteringer
              </h2>
              <button onClick={() => setShowReceiptList(false)} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              <ReceiptList 
                receipts={receipts} 
                onDelete={handleDeleteReceipt} 
              />
            </div>
            <div className="p-4 border-t border-slate-200 dark:border-slate-700">
              <button 
                onClick={() => { setShowReceiptList(false); setShowReceiptScanner(true); }}
                className="w-full py-3 bg-red-600 text-white rounded-xl font-bold flex items-center justify-center gap-2"
                data-testid="scan-new-receipt-btn"
              >
                <Camera className="w-5 h-5" /> Scan ny kvittering
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Receipt Viewer removed from driver - photos are admin-only */}

      {/* Pause Countdown Timer - floating */}
      {activePause && pauseRemainingSec > 0 && (
        <div className="fixed bottom-4 right-4 z-40 bg-gradient-to-br from-orange-500 to-amber-600 text-white px-4 py-3 rounded-2xl shadow-2xl flex items-center gap-3 animate-slide-up" data-testid="pause-timer-widget">
          <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
            <Pause className="w-5 h-5" />
          </div>
          <div className="min-w-[80px]">
            <div className="text-[10px] uppercase tracking-wider opacity-80 font-bold">Pause</div>
            <div className="text-2xl font-mono font-black leading-tight" data-testid="pause-countdown">
              {Math.floor(pauseRemainingSec / 60).toString().padStart(2, "0")}:{(pauseRemainingSec % 60).toString().padStart(2, "0")}
            </div>
          </div>
          <button
            onClick={() => { setActivePause(null); setPauseRemainingSec(0); }}
            className="ml-1 p-1.5 hover:bg-white/20 rounded-lg transition-colors"
            title="Annuller timer"
            data-testid="pause-timer-close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Incoming Message Auto-Popup */}
      {incomingMessage && (
        <div className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4 animate-fade-in" data-testid="incoming-message-popup">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border-2 border-amber-400">
            <div className="bg-gradient-to-r from-amber-500 to-orange-500 px-5 py-3 flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-white/25 flex items-center justify-center">
                <MessageCircle className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-white/80 font-bold">Ny besked fra</div>
                <div className="text-white font-bold text-base truncate" data-testid="incoming-message-from">
                  {incomingMessage.from_driver_name || "Admin"}
                </div>
              </div>
              <button onClick={closeIncomingMessage} className="p-1.5 hover:bg-white/20 rounded-lg" data-testid="incoming-message-close">
                <X className="w-5 h-5 text-white" />
              </button>
            </div>
            <div className="p-5">
              <p className="text-slate-800 dark:text-slate-100 text-base whitespace-pre-wrap" data-testid="incoming-message-content">
                {incomingMessage.content}
              </p>
              <p className="text-xs text-slate-500 mt-2">
                {new Date(incomingMessage.created_at).toLocaleString("da-DK")}
              </p>

              {incomingReplyMode ? (
                <div className="mt-4 space-y-2">
                  <textarea
                    value={incomingReplyText}
                    onChange={(e) => setIncomingReplyText(e.target.value)}
                    placeholder="Skriv dit svar..."
                    autoFocus
                    rows={3}
                    className="w-full px-3 py-2 text-sm border-2 border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-800 dark:text-white rounded-xl focus:outline-none focus:border-amber-500 resize-none"
                    data-testid="incoming-message-reply-input"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setIncomingReplyMode(false); setIncomingReplyText(""); }}
                      className="flex-1 py-2.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors"
                    >
                      Tilbage
                    </button>
                    <button
                      onClick={replyIncomingMessage}
                      disabled={!incomingReplyText.trim()}
                      className="flex-1 py-2.5 bg-emerald-500 text-white font-bold rounded-xl hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                      data-testid="incoming-message-send-reply"
                    >
                      <Send className="w-4 h-4" /> Send
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-5 flex gap-2">
                  <button
                    onClick={closeIncomingMessage}
                    className="flex-1 py-3 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors"
                    data-testid="incoming-message-dismiss"
                  >
                    Luk
                  </button>
                  <button
                    onClick={() => setIncomingReplyMode(true)}
                    className="flex-1 py-3 bg-amber-500 text-white font-bold rounded-xl hover:bg-amber-600 transition-colors flex items-center justify-center gap-2"
                    data-testid="incoming-message-reply-btn"
                  >
                    <MessageCircle className="w-4 h-4" /> Svar
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="bg-slate-900 text-slate-400 py-4 px-4 text-center text-xs mt-8" data-testid="app-footer">
        <p>&copy; 2026 ContainerFlow. All rights reserved.</p>
        <p className="text-slate-500 mt-1">Smart Container Logistics</p>
      </footer>

      {/* Confirmation Modal */}
      <ConfirmModal
        open={confirmModal.open}
        title={confirmModal.title}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onCancel={hideConfirm}
        variant={confirmModal.variant}
      />

      {/* Fase 18.2 (2026-02-28): Tidsregistrering-modal før Afslut dag.
          Scenarie 1: Ingen IND-stempel - opfordrer chauffør til at registrere.
          Scenarie 2: Auto-stemplet ud - bekræfter til chauffør.
          Modal er fullscreen-mobil-venlig (full width på sm-, store knapper). */}
      {onWayWarn && (
        <div className="fixed inset-0 z-[60] bg-black/60 flex items-end sm:items-center justify-center p-4" onClick={() => setOnWayWarn(null)} data-testid="onway-warn">
          <div className="w-full sm:max-w-sm rounded-2xl bg-white dark:bg-slate-900 p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="text-lg font-bold text-slate-900 dark:text-white">{onWayWarn.length === 1 ? "1 tur er stadig På vej" : `${onWayWarn.length} ture er stadig På vej`}</div>
            <p className="text-sm text-slate-600 dark:text-slate-300">Afslut turen nu, så tiden passer. Afsluttes den først i morgen, bliver tiden (og prisen) forkert.</p>
            <ul className="text-sm text-slate-700 dark:text-slate-200 space-y-1">
              {onWayWarn.slice(0, 4).map(t => <li key={t.id}>• {t.fraction || "Tur"} · {t.address} <span className="text-slate-400">(siden {t.on_way_time})</span></li>)}
            </ul>
            <div className="grid grid-cols-1 gap-2 pt-1">
              <button type="button" className="py-3 rounded-xl bg-emerald-600 text-white font-bold" data-testid="onway-warn-goto"
                onClick={() => { const t = onWayWarn[0]; setOnWayWarn(null); setActiveTab("ture"); setSelectedTourForPanel(t); }}>Gå til turen</button>
              <button type="button" className="py-3 rounded-xl border border-slate-200 dark:border-slate-700 font-semibold text-slate-700 dark:text-slate-200" data-testid="onway-warn-continue"
                onClick={() => { setOnWayWarn(null); handleEndOfShift({ skipOnWay: true }); }}>Afslut dagen alligevel</button>
            </div>
          </div>
        </div>
      )}
      {timeRegModal.open && (
        <div
          className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
          data-testid="time-reg-modal"
          onClick={(e) => {
            // Klik på baggrunden lukker KUN i scenarie 2 (info-modal).
            // Scenarie 1 kræver eksplicit valg.
            if (e.target === e.currentTarget && timeRegModal.scenario === 2) {
              closeTimeRegModal();
            }
          }}
        >
          <div className="w-full sm:max-w-md bg-white dark:bg-slate-800 rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden">
            {timeRegModal.scenario === 1 && (
              <>
                <div className="p-5 border-b border-slate-200 dark:border-slate-700 bg-amber-50 dark:bg-amber-900/20">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
                      <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white" data-testid="time-reg-modal-title">
                      Ingen tidsregistrering
                    </h3>
                  </div>
                </div>
                <div className="p-5 space-y-3">
                  <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
                    Du har ikke stemplet ind i dag.
                    <br />
                    Registrer venligst din arbejdstid før du afslutter dagen.
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 italic">
                    Dansk lov kræver objektiv tidsregistrering (juli 2024).
                  </p>
                </div>
                <div className="p-4 space-y-2 bg-slate-50 dark:bg-slate-900/40">
                  <button
                    onClick={closeTimeRegModal}
                    className="w-full px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-bold text-base shadow"
                    data-testid="time-reg-modal-back"
                  >
                    Gå tilbage og registrer
                  </button>
                  <button
                    onClick={() => timeRegModal.onProceed && timeRegModal.onProceed()}
                    className="w-full px-4 py-2 rounded-xl text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:underline"
                    data-testid="time-reg-modal-skip"
                  >
                    Afslut alligevel
                  </button>
                </div>
              </>
            )}

            {timeRegModal.scenario === 2 && (
              <>
                <div className="p-5 border-b border-slate-200 dark:border-slate-700 bg-emerald-50 dark:bg-emerald-900/20">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
                      <Check className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white" data-testid="time-reg-modal-title">
                      Vi har stemplet dig ud
                    </h3>
                  </div>
                </div>
                <div className="p-5 space-y-3">
                  <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
                    Du var stadig stemplet ind.
                    <br />
                    Vi har registreret din udstemplingstid som{" "}
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 font-mono" data-testid="time-reg-modal-auto-time">
                      {timeRegModal.autoTime}
                    </span>.
                  </p>
                  <p className="text-sm text-slate-700 dark:text-slate-200">
                    Din arbejdsdag afsluttes nu.
                  </p>
                </div>
                <div className="p-4 bg-slate-50 dark:bg-slate-900/40">
                  <button
                    onClick={() => timeRegModal.onProceed && timeRegModal.onProceed()}
                    className="w-full px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-bold text-base shadow"
                    data-testid="time-reg-modal-ok"
                  >
                    OK, afslut dag
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Fase 15.28 (2026-02-22): Driver manuel stempel (event-baseret).
          Erstatter den tidligere periode-baserede modal - chauffør kan nu
          kun oprette ÉT stempel ad gangen (IND eller UD). Periode-modalen
          er flyttet til logistik-admin → Planlægning → Tidsregistrering. */}
      <ManualPunchModal
        open={manualTimeModalOpen}
        defaultDate={reportDate}
        mode="driver"
        requireReason={requireDriverPunchReason}
        onClose={() => setManualTimeModalOpen(false)}
        onSave={async (data) => {
          await axios.post(`${API}/driver/time-entries/manual-punch`, data);
          await fetchTimeEntries();
          // Sync lokal IND/UD state best-effort
          if (data.date === reportDate) {
            if (data.type === "ind") setStartTime(data.time);
            else if (data.type === "ud") setEndTime(data.time);
          }
          // Fase 15.31 (2026-02-22): Genåbn dagens stempling-modal så
          // chaufføren straks ser den nye entry og kan redigere/slette den.
          setTimeout(() => setShowTimeOverview(true), 100);
        }}
      />

      {/* Fase 15.31 (2026-02-22): Edit-modal - chaufføren kan rette egne
          manuelle entries (start/slut/dato/årsag/slice_type). Soft-delete
          knappes håndteres direkte fra dagens overblik (inline confirm). */}
      <EditOwnEntryModal
        open={!!editEntry}
        entry={editEntry}
        onClose={() => setEditEntry(null)}
        onSaved={async () => {
          await fetchTimeEntries();
          // Fase 15.31: Reopen overview så chaufføren ser ændringen
          setTimeout(() => setShowTimeOverview(true), 100);
        }}
      />

      {/* Fase 13 (2026-06-18): Day Time Overview Modal - alle perioder
          for valgt dag + total + manuel-badge. */}
      {showTimeOverview && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
             onClick={() => setShowTimeOverview(false)}
             data-testid="time-overview-modal">
          <div className="bg-white dark:bg-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden animate-slide-up"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-xl bg-emerald-500/15 flex items-center justify-center">
                  <Clock className="w-5 h-5 text-emerald-500" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-800 dark:text-slate-100">Dagens stempling</h2>
                  <p className="text-[11px] text-slate-500">{reportDate}</p>
                </div>
              </div>
              <button onClick={() => setShowTimeOverview(false)}
                className="w-8 h-8 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center justify-center"
                data-testid="time-overview-close-btn">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-2 max-h-[60vh] overflow-y-auto">
              {timeEntries.length === 0 ? (
                <p className="text-center text-sm text-slate-500 py-6 italic">Ingen stempling endnu i dag</p>
              ) : timeEntries.map((entry, idx) => {
                const isOpen = !entry.end_time;
                const isPause = (entry.slice_type || "work") === "pause";
                const dur = entry.duration_minutes || 0;
                const hh = Math.floor(dur / 60);
                const mm = dur % 60;
                // Fase 15.32 (2026-02-22): Chauffør må nu redigere/slette ALLE
                // sine egne entries - både auto IND/UD og manuelle. Kun
                // admin-oprettede er låste. Da GET /driver/time-entries
                // returnerer kun chaufførens egne entries, behøver vi kun
                // udelukke admin-oprettede.
                const adminCreated = entry.created_by_role === "logistics_admin"
                                    || entry.created_by_role === "super_admin";
                const canEditOwn = !adminCreated;
                const pendingThis = pendingDeleteId === entry.id;
                return (
                  <div key={entry.id} className={`p-3 rounded-lg border ${
                    isOpen
                      ? (isPause
                          ? "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800"
                          : "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800")
                      : (isPause
                          ? "bg-blue-50/60 dark:bg-blue-950/10 border-blue-200/60 dark:border-blue-900"
                          : "bg-slate-50 dark:bg-slate-700/30 border-slate-200 dark:border-slate-600")
                  }`} data-testid={`time-entry-row-${idx}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-bold text-sm text-slate-700 dark:text-slate-200">
                          {entry.start_time} → {entry.end_time || "..."}
                        </span>
                        <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${
                          isPause
                            ? "bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300"
                            : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                        }`} data-testid={`time-entry-slice-${idx}`}>
                          {isPause ? "PAUSE" : "ARBEJDE"}
                        </span>
                        {entry.manual && (
                          <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 text-[10px] font-bold rounded">
                            MANUEL
                          </span>
                        )}
                        {isOpen && (
                          <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded animate-pulse ${
                            isPause
                              ? "bg-blue-200 dark:bg-blue-800/40 text-blue-700 dark:text-blue-300"
                              : "bg-amber-200 dark:bg-amber-800/40 text-amber-700 dark:text-amber-300"
                          }`}>
                            {isPause ? "I PAUSE" : "ÅBEN"}
                          </span>
                        )}
                      </div>
                      {!isOpen && (
                        <span className={`font-mono text-xs font-semibold ${
                          isPause
                            ? "text-blue-700 dark:text-blue-300"
                            : "text-emerald-700 dark:text-emerald-300"
                        }`}>
                          {hh}t {String(mm).padStart(2, "0")}m
                        </span>
                      )}
                    </div>
                    {entry.reason && (
                      <p className="text-[11px] text-slate-500 mt-1 italic">{entry.reason}</p>
                    )}
                    {/* Fase 15.31 (2026-02-22): Edit/Delete-knapper kun for
                        chaufførens egne entries (auto IND/UD + manuelle).
                        Fase 15.32: To-trins slet-bekræftelse uden window.confirm. */}
                    {canEditOwn && (
                      <div className="mt-2 flex items-center gap-2" data-testid={`time-entry-own-actions-${idx}`}>
                        <button
                          onClick={() => { setEditEntry(entry); setShowTimeOverview(false); }}
                          className="px-2.5 py-1 rounded-md text-[11px] font-bold border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950/30 flex items-center gap-1"
                          data-testid={`time-entry-edit-${idx}`}
                        >
                          <Edit2 className="w-3 h-3" /> Rediger
                        </button>
                        {pendingThis ? (
                          <>
                            <button
                              onClick={async () => {
                                try {
                                  await axios.delete(`${API}/driver/time-entries/${entry.id}`);
                                  toast.success("Registrering slettet");
                                  setPendingDeleteId(null);
                                  await fetchTimeEntries();
                                } catch (e) {
                                  toast.error(e?.response?.data?.detail || "Kunne ikke slette");
                                  setPendingDeleteId(null);
                                }
                              }}
                              className="px-2.5 py-1 rounded-md text-[11px] font-bold bg-red-500 text-white hover:bg-red-600 flex items-center gap-1 animate-pulse"
                              data-testid={`time-entry-delete-confirm-${idx}`}
                            >
                              <Trash2 className="w-3 h-3" /> Bekræft slet
                            </button>
                            <button
                              onClick={() => setPendingDeleteId(null)}
                              className="px-2.5 py-1 rounded-md text-[11px] font-bold border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                              data-testid={`time-entry-delete-cancel-${idx}`}
                            >
                              Annullér
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => setPendingDeleteId(entry.id)}
                            className="px-2.5 py-1 rounded-md text-[11px] font-bold border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center gap-1"
                            data-testid={`time-entry-delete-${idx}`}
                          >
                            <Trash2 className="w-3 h-3" /> Slet
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Fase 15.30 (2026-02-22): Tre tal i bunden - arbejde, pause,
                total tilstede. Total tilstede = work + pause. */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
              <div className="grid grid-cols-3 gap-3 flex-1 min-w-0">
                {(() => {
                  const workMin = timeEntries.filter(e => (e.slice_type || "work") !== "pause").reduce((s, e) => s + (e.duration_minutes || 0), 0);
                  const pauseMin = timeEntries.filter(e => (e.slice_type || "work") === "pause").reduce((s, e) => s + (e.duration_minutes || 0), 0);
                  const totalMin = workMin + pauseMin;
                  const fmt = (m) => `${Math.floor(m / 60)}t ${String(m % 60).padStart(2, "0")}m`;
                  return (
                    <>
                      <div className="min-w-0">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Arbejde</p>
                        <p className="text-base font-bold text-emerald-700 dark:text-emerald-300 font-mono truncate" data-testid="time-overview-work">{fmt(workMin)}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Pause</p>
                        <p className="text-base font-bold text-blue-700 dark:text-blue-300 font-mono truncate" data-testid="time-overview-pause">{fmt(pauseMin)}</p>
                      </div>
                      <div className="min-w-0">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Total</p>
                        <p className="text-base font-bold text-slate-700 dark:text-slate-200 font-mono truncate" data-testid="time-overview-total">{fmt(totalMin)}</p>
                      </div>
                    </>
                  );
                })()}
              </div>
              <button
                onClick={() => { setManualTimeModalOpen(true); setShowTimeOverview(false); }}
                className="px-3 py-2 rounded-lg font-semibold text-sm bg-orange-500 text-white hover:bg-orange-600 flex items-center gap-1.5 flex-shrink-0"
                data-testid="time-overview-add-manual-btn"
              >
                <Edit2 className="w-3.5 h-3.5" />
                Tilføj manuel
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
