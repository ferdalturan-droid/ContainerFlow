// ReceiptOCRArchive.jsx - Fase 17
// Logistik-admins samlede kvitterings-arkiv (tidligere "OCR-arkiv").
// Lister alle kvitteringer på tværs af en tenant med filtre
// (dato, chauffør, plads, fraktion, kunde, fri-tekst), paginering,
// detalje-view med billede + download + manuel vægt-override + audit-log.
//
// Fase 17 (2026-02-27): OCR-funktionalitet fjernet i UI. Vægten
// indtastes altid manuelt af chaufføren i den nye jscanify-scanner.

import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Search, X, Camera, AlertTriangle, CheckCircle2, Loader2,
  Calendar, RefreshCw, Download, Edit3, History, ImageOff,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const PAGE_SIZE = 25;

function fmtKg(n) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  return Number(n).toLocaleString("da-DK", { maximumFractionDigits: 1 }) + " kg";
}
function fmtDate(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" });
  } catch (_) { return iso; }
}

// Fase 18.3 (2026-02-28): Normalisér et tids-felt til HH:MM. Backend kan
// returnere enten en allerede-formateret "HH:MM" eller en fuld ISO-streng
// (afhængig af om turen blev stemplet manuelt eller via tour-flow).
function fmtTimeShort(val) {
  if (!val) return "-";
  if (typeof val === "string" && /^\d{2}:\d{2}$/.test(val)) return val;
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) return "-";
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch (_) { return "-"; }
}

function typeBadge(status) {
  // Fase 17: erstatter de gamle OCR-statusser med en enkelt "Type"-badge
  // der signalerer hvordan vægten er kommet på kvitteringen. Alle nye
  // kvitteringer er nu "Manuel" siden vægten altid indtastes af chaufføren.
  const isManual = status === "manual" || status === "none";
  const color = isManual
    ? "bg-blue-100 text-blue-800 border-blue-300"
    : "bg-slate-100 text-slate-700 border-slate-300";
  const label = isManual ? "Manuel" : "Ældre";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${color}`} data-testid={`receipt-type-${status || "none"}`}>
      {label}
    </span>
  );
}

function buildImageSrc(detail) {
  // Fase 17: bruger det dedikerede binary endpoint så browseren kan
  // streame billedet progressivt i stedet for at hente hele base64-payloaden
  // i én sjat fra /full. Returnerer "" hvis intet billede.
  if (!detail) return "";
  // Bagudkompatibel: hvis detail.image_data er sat (gamle responses), brug det.
  if (detail.image_data) {
    return String(detail.image_data).startsWith("data:")
      ? detail.image_data
      : `data:image/jpeg;base64,${detail.image_data}`;
  }
  if (detail.id) {
    return `${API}/receipts/${detail.id}/image-binary`;
  }
  return "";
}

export default function ReceiptOCRArchive({ currentUserName = "" }) {
  const [filters, setFilters] = useState({
    date_from: "",
    date_to: "",
    driver_name: "",
    plads: "",
    fraction: "",
    customer_company_id: "",
    search: "",
  });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null); // selected full receipt
  const [detailLoading, setDetailLoading] = useState(false);
  const [customers, setCustomers] = useState([]);

  const fetchArchive = useCallback(async () => {
    setLoading(true);
    try {
      const params = { ...filters, limit: PAGE_SIZE, offset };
      Object.keys(params).forEach(k => params[k] === "" && delete params[k]);
      const resp = await axios.get(`${API}/receipts-archive`, { params });
      setData(resp.data || { total: 0, items: [] });
    } catch (e) {
      toast.error("Kunne ikke hente arkiv");
    } finally {
      setLoading(false);
    }
  }, [filters, offset]);

  useEffect(() => {
    fetchArchive();
  }, [fetchArchive]);

  // Kunde-dropdown (kun super-admins får et 200-svar her)
  useEffect(() => {
    (async () => {
      try {
        const resp = await axios.get(`${API}/superadmin/retention-policies`);
        setCustomers(resp.data?.companies || []);
      } catch (_) { /* ikke super-admin → stille */ }
    })();
  }, []);

  const clearFilters = () => {
    setFilters({ date_from: "", date_to: "", driver_name: "", plads: "", fraction: "", customer_company_id: "", search: "" });
    setOffset(0);
  };

  const openDetail = async (id) => {
    setDetail({ id, _loading: true });
    setDetailLoading(true);
    try {
      const resp = await axios.get(`${API}/receipts/${id}/full`);
      const receiptData = resp.data;

      // Fase 18.9 (2026-02-28): For løs afhentning hent også søskende-
      // kvitteringer for samme tur, så admin kan navigere mellem dem.
      if (receiptData.tour_id) {
        try {
          const siblingResp = await axios.get(
            `${API}/receipts-archive`,
            { params: { limit: 20, offset: 0 } }
          );
          const siblings = (siblingResp.data?.items || []).filter(
            r => r.tour_id === receiptData.tour_id && r.id !== id
          );
          receiptData._siblings = siblings;
        } catch (_) {
          receiptData._siblings = [];
        }
      }

      setDetail(receiptData);
    } catch (_) {
      toast.error("Kunne ikke hente kvittering");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const overrideWeight = async (newWeight, reason) => {
    if (!detail) return;
    try {
      const resp = await axios.put(`${API}/receipts/${detail.id}/weight-override`, {
        new_weight_kg: Number(newWeight),
        user_name: currentUserName,
        reason: reason || "",
      });
      toast.success("Vægt rettet - audit-log opdateret");
      setDetail({ ...detail, final_weight_kg: Number(newWeight), ocr_status: "manual", audit_log: resp.data.audit_log });
      fetchArchive();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kunne ikke rette vægt");
    }
  };

  return (
    <section className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-4 sm:p-6 space-y-4" data-testid="receipt-ocr-archive">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-heading font-bold text-xl flex items-center gap-2">
          <Camera className="w-6 h-6 text-emerald-600" />
          Kvitterings-arkiv
        </h2>
        <button
          onClick={fetchArchive}
          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 inline-flex items-center gap-2"
          data-testid="receipt-archive-refresh"
        >
          <RefreshCw className="w-4 h-4" /> Opdater
        </button>
      </div>

      {/* Filter row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Fra dato</label>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => { setFilters({ ...filters, date_from: e.target.value }); setOffset(0); }}
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-date-from"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Til dato</label>
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => { setFilters({ ...filters, date_to: e.target.value }); setOffset(0); }}
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-date-to"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Chauffør</label>
          <input
            type="text"
            value={filters.driver_name}
            onChange={(e) => { setFilters({ ...filters, driver_name: e.target.value }); setOffset(0); }}
            placeholder="Navn"
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-driver"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Plads</label>
          <input
            type="text"
            value={filters.plads}
            onChange={(e) => { setFilters({ ...filters, plads: e.target.value }); setOffset(0); }}
            placeholder="Plads-navn"
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-plads"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Fraktion</label>
          <input
            type="text"
            value={filters.fraction}
            onChange={(e) => { setFilters({ ...filters, fraction: e.target.value }); setOffset(0); }}
            placeholder="fx Træ, Jern…"
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-fraction"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Kunde</label>
          <select
            value={filters.customer_company_id}
            onChange={(e) => { setFilters({ ...filters, customer_company_id: e.target.value }); setOffset(0); }}
            className="w-full px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="receipt-archive-customer"
          >
            <option value="">Alle kunder</option>
            {customers.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="col-span-2 md:col-span-2">
          <label className="block text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-0.5">Søg i tekst / beskrivelse</label>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-2 top-2 text-slate-400" />
            <input
              type="text"
              value={filters.search}
              onChange={(e) => { setFilters({ ...filters, search: e.target.value }); setOffset(0); }}
              placeholder="Søg…"
              className="w-full pl-8 pr-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
              data-testid="receipt-archive-search"
            />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
        <span>
          {loading ? <Loader2 className="w-3 h-3 inline animate-spin mr-1" /> : null}
          {data.total} resultat{data.total === 1 ? "" : "er"}
        </span>
        <button
          onClick={clearFilters}
          className="text-blue-600 dark:text-blue-400 hover:underline"
          data-testid="receipt-archive-clear-filters"
        >
          Ryd filtre
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
              <th className="py-2 pr-3">Dato</th>
              <th className="py-2 pr-3">Chauffør</th>
              <th className="py-2 pr-3">Plads</th>
              <th className="py-2 pr-3">Fraktion</th>
              <th className="py-2 pr-3 text-right">Vægt</th>
              <th className="py-2 pr-3">Tur start</th>
              <th className="py-2 pr-3">Tur slut</th>
              <th className="py-2 pr-3">Type</th>
              <th className="py-2 pr-3"></th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr
                key={r.id}
                className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/40 cursor-pointer"
                onClick={() => openDetail(r.id)}
                data-testid={`receipt-row-${r.id}`}
              >
                <td className="py-2 pr-3 whitespace-nowrap">{r.date || fmtDate(r.created_at)}</td>
                <td className="py-2 pr-3">{r.driver_name || "-"}</td>
                <td className="py-2 pr-3">{r.plads || "-"}</td>
                <td className="py-2 pr-3">{r.fraction || "-"}</td>
                <td className="py-2 pr-3 text-right font-mono font-semibold">{fmtKg(r.final_weight_kg)}</td>
                <td className="py-2 pr-3 font-mono text-xs text-emerald-600 dark:text-emerald-400" data-testid={`receipt-tour-start-${r.id}`}>{fmtTimeShort(r.tour_started_at)}</td>
                <td className="py-2 pr-3 font-mono text-xs text-rose-600 dark:text-rose-400" data-testid={`receipt-tour-end-${r.id}`}>{fmtTimeShort(r.tour_completed_at)}</td>
                <td className="py-2 pr-3">
                  {typeBadge(r.ocr_status || "none")}
                </td>
                <td className="py-2 pr-3">
                  {(r.description?.includes("Løs afhentning") ||
                    r.description?.includes("container") ||
                    r.tour_type === "loes_afhentning") && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border bg-purple-100 text-purple-800 border-purple-300" data-testid={`receipt-loose-badge-${r.id}`}>
                      Løs
                    </span>
                  )}
                </td>
                <td className="py-2 text-right">
                  <button className="text-blue-600 hover:underline text-xs font-semibold" data-testid={`receipt-row-open-${r.id}`}>
                    Åbn
                  </button>
                </td>
              </tr>
            ))}
            {!data.items.length && !loading && (
              <tr>
                <td colSpan="10" className="py-8 text-center text-slate-500 italic" data-testid="receipt-archive-empty">
                  Ingen kvitteringer matcher dine filtre.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 disabled:opacity-40"
            data-testid="receipt-archive-prev"
          >
            ← Forrige
          </button>
          <span className="text-slate-600 dark:text-slate-300">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} af {data.total}
          </span>
          <button
            disabled={offset + PAGE_SIZE >= data.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 disabled:opacity-40"
            data-testid="receipt-archive-next"
          >
            Næste →
          </button>
        </div>
      )}

      {detail && (
        <ReceiptDetailModal
          detail={detail}
          loading={detailLoading}
          onClose={() => setDetail(null)}
          onOverride={overrideWeight}
          onOpenSibling={openDetail}
        />
      )}
    </section>
  );
}

function ReceiptDetailModal({ detail, loading, onClose, onOverride, onOpenSibling }) {
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(String(detail?.final_weight_kg ?? ""));
  const [reason, setReason] = useState("");
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [zoom, setZoom] = useState(false);

  // Reset img-state hver gang vi får et nyt billede
  useEffect(() => {
    setImgError(false);
    setImgLoaded(false);
    setEditVal(String(detail?.final_weight_kg ?? ""));
  }, [detail?.id, detail?.final_weight_kg]);

  const imgSrc = buildImageSrc(detail);

  const handleDownload = async () => {
    if (!imgSrc) {
      toast.error("Intet billede at downloade");
      return;
    }
    const dt = (detail.date || "").replace(/[^0-9-]/g, "") || "ukendt";
    const pladsSlug = (detail.plads || "kvittering").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 40);
    const filename = `kvittering-${pladsSlug}-${dt}.jpg`;
    try {
      // Fase 17: hent som blob så download virker både for data-URLs
      // (bagudkompat) OG for det nye binary endpoint.
      const resp = await fetch(imgSrc, { credentials: "include" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast.success("Download startet");
    } catch (e) {
      toast.error(`Download fejlede: ${e?.message || "ukendt"}`);
    }
  };

  const isLoading = loading || detail?._loading;

  return (
    <div
      className="fixed inset-0 z-[1100] bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
      data-testid="receipt-detail-modal"
    >
      <div
        className="bg-white dark:bg-slate-900 w-full sm:max-w-3xl rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[95vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 sticky top-0 bg-white dark:bg-slate-900 z-10">
          <h3 className="font-bold text-slate-900 dark:text-white text-sm sm:text-base truncate pr-2">
            {isLoading ? "Henter kvittering…" : `Kvittering - ${detail.driver_name || "?"} · ${detail.plads || "?"}`}
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800" data-testid="receipt-detail-close" aria-label="Luk">
            <X className="w-5 h-5" />
          </button>
        </div>

        {isLoading ? (
          <div className="p-10 flex flex-col items-center gap-3" data-testid="receipt-detail-loading">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
            <p className="text-sm text-slate-600 dark:text-slate-300">Indlæser kvittering…</p>
          </div>
        ) : (
          <>
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Billede-preview */}
              <div className="space-y-2">
                <div className="relative bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center min-h-[280px]">
                  {imgSrc && !imgError ? (
                    <>
                      {!imgLoaded && (
                        <div className="absolute inset-0 flex items-center justify-center" data-testid="receipt-detail-image-loading">
                          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                        </div>
                      )}
                      <img
                        src={imgSrc}
                        alt="Kvittering"
                        className={`w-full h-auto object-contain cursor-zoom-in transition-opacity duration-150 ${imgLoaded ? "opacity-100" : "opacity-0"}`}
                        onLoad={() => setImgLoaded(true)}
                        onError={() => { setImgError(true); setImgLoaded(true); }}
                        onClick={() => setZoom(true)}
                        data-testid="receipt-detail-image"
                      />
                    </>
                  ) : (
                    <div className="text-center text-slate-400 italic py-12 flex flex-col items-center gap-2" data-testid="receipt-detail-no-image">
                      <ImageOff className="w-10 h-10 opacity-50" />
                      <span>{imgError ? "Billedet kunne ikke vises" : "Intet billede"}</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleDownload}
                    disabled={!imgSrc || imgError}
                    className="flex-1 px-3 py-2 rounded-lg bg-emerald-600 text-white font-semibold text-sm flex items-center justify-center gap-1.5 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    data-testid="receipt-detail-download-btn"
                  >
                    <Download className="w-4 h-4" /> Download billede
                  </button>
                  {imgSrc && !imgError && (
                    <button
                      onClick={() => setZoom(true)}
                      className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                      data-testid="receipt-detail-zoom-btn"
                      title="Forstør"
                    >
                      <Search className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Detaljer */}
              <div className="space-y-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500">Vægt</div>
                  <div className="text-2xl font-bold font-mono" data-testid="receipt-detail-weight">{fmtKg(detail.final_weight_kg)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {typeBadge(detail.ocr_status || "none")}
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500">Fraktion</div>
                  <div>{detail.fraction || "-"}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500">Tour ID</div>
                  <div className="font-mono text-xs">{detail.tour_id || "-"}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500">Oprettet</div>
                  <div>{fmtDate(detail.created_at)}</div>
                </div>
                {detail.description && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">Beskrivelse</div>
                    <div className="text-xs">{detail.description}</div>
                  </div>
                )}

                {editing ? (
                  <div className="space-y-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
                    <div className="text-xs font-semibold">Ret vægt manuelt</div>
                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.1"
                      min="0"
                      value={editVal}
                      onChange={(e) => setEditVal(e.target.value)}
                      className="w-full px-2 py-1.5 rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                      data-testid="receipt-detail-edit-weight"
                    />
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Begrundelse (logges)"
                      rows={2}
                      className="w-full px-2 py-1.5 rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                      data-testid="receipt-detail-edit-reason"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => { onOverride(editVal, reason); setEditing(false); setReason(""); }}
                        className="flex-1 px-3 py-1.5 rounded bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700"
                        data-testid="receipt-detail-edit-save"
                      >
                        Gem
                      </button>
                      <button
                        onClick={() => setEditing(false)}
                        className="flex-1 px-3 py-1.5 rounded bg-slate-200 dark:bg-slate-700 font-semibold text-sm"
                        data-testid="receipt-detail-edit-cancel"
                      >
                        Annullér
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => { setEditing(true); setEditVal(String(detail.final_weight_kg ?? "")); }}
                    className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline text-sm"
                    data-testid="receipt-detail-edit-btn"
                  >
                    <Edit3 className="w-4 h-4" /> Ret vægt
                  </button>
                )}
              </div>
            </div>

            {/* Fase 18.9 (2026-02-28): Søskende-kvitteringer for samme løs
                afhentning-tur. Admin kan klikke for at navigere mellem dem. */}
            {detail._siblings?.length > 0 && (
              <div className="mx-4 mb-4 p-3 rounded-lg bg-purple-50 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800" data-testid="receipt-detail-siblings">
                <div className="text-xs font-bold text-purple-800 dark:text-purple-300 mb-2">
                  Løs afhentning - øvrige kvitteringer på samme tur ({detail._siblings.length})
                </div>
                <div className="flex flex-wrap gap-2">
                  {detail._siblings.map(s => (
                    <button
                      key={s.id}
                      onClick={() => onOpenSibling && onOpenSibling(s.id)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200 hover:bg-purple-200 dark:hover:bg-purple-900/60 border border-purple-300 dark:border-purple-700"
                      data-testid={`receipt-sibling-${s.id}`}
                    >
                      {s.description || `Container`} - {fmtKg(s.final_weight_kg)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {detail.audit_log?.length > 0 && (
              <details className="mx-4 mb-4 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700" data-testid="receipt-detail-audit-log">
                <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-2">
                  <History className="w-3 h-3" /> Historik ({detail.audit_log.length})
                </summary>
                <ul className="px-3 pb-3 space-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                  {detail.audit_log.map((a, i) => (
                    <li key={i} className="border-l-2 border-blue-300 dark:border-blue-700 pl-2">
                      <div><strong>{a.action || "?"}</strong> · {a.user || "ukendt"} · {fmtDate(a.ts)}</div>
                      {a.before != null && <div>Før: {fmtKg(a.before)}</div>}
                      {a.after != null && <div>Efter: {fmtKg(a.after)}</div>}
                      {a.reason && <div className="italic">&quot;{a.reason}&quot;</div>}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}

        {/* Forstørret billede-overlay */}
        {zoom && imgSrc && !imgError && (
          <div
            className="fixed inset-0 z-[1200] bg-black/90 flex items-center justify-center p-2 cursor-zoom-out"
            onClick={() => setZoom(false)}
            data-testid="receipt-detail-zoom-overlay"
          >
            <img src={imgSrc} alt="Kvittering forstørret" className="max-w-full max-h-full object-contain" />
            <button
              onClick={(e) => { e.stopPropagation(); setZoom(false); }}
              className="absolute top-3 right-3 p-2 rounded-full bg-white/20 text-white hover:bg-white/30"
              aria-label="Luk"
            >
              <X className="w-6 h-6" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
