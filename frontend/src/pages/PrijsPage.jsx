import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Plus, Trash2, Edit2, X, Loader2, Download,
  DollarSign, BarChart3, Calendar, Users, TrendingUp,
  ChevronDown, Save, AlertTriangle, ArrowLeft
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";

const PERIODS = [
  { value: "daily",   label: "Daglig" },
  { value: "weekly",  label: "Ugentlig" },
  { value: "monthly", label: "Månedlig" },
];

export default function PrijsPage({ onBack = null }) {
  const { logout } = useAuth();
  const [tab, setTab] = useState("priser"); // priser | rapport

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {onBack && (
              <button
                onClick={onBack}
                data-testid="prijs-back-btn"
                className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-600 dark:text-slate-300"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <div>
              <h1 className="font-bold text-lg text-slate-900 dark:text-white">
                Container<span className="text-orange-500">Flow</span>
              </h1>
              <p className="text-xs text-slate-500">Priser & Rapporter</p>
            </div>
          </div>
          <button onClick={logout}
            className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1">
            Log ud
          </button>
        </div>
        {/* Tabs */}
        <div className="max-w-5xl mx-auto px-4 flex gap-1 border-t border-slate-100 dark:border-slate-700">
          {[
            { id: "priser", label: "Priser", icon: DollarSign },
            { id: "rapport", label: "Rapport", icon: BarChart3 },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                tab === t.id
                  ? "border-orange-500 text-slate-900 dark:text-white"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}>
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5">
        {tab === "priser" && <PrijsPanel />}
        {tab === "rapport" && <RapportPanel />}
      </main>
    </div>
  );
}

/* ============== PRISER PANEL ============== */
function PrijsPanel() {
  const [prices, setPrices]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing]  = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [filterPlads, setFilterPlads] = useState("");
  const [hasterFee, setHasterFee] = useState(200);
  const [editingHaster, setEditingHaster] = useState(false);

  const emptyForm = { plads: "", fraction: "", price: "", kind: "material" };
  const [form, setForm] = useState(emptyForm);
  const KIND_LABELS = { material: "Materiale", flyt: "Flyt container", vaerksted: "Til værksted" };

  const fetchPrices = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/tour-prices`);
      setPrices(data.prices || []);
      setHasterFee(data.haster_fee ?? 200);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPrices(); }, [fetchPrices]);

  const pladsOptions = [...new Set(prices.map(p => p.plads))].filter(Boolean).sort();

  const filtered = filterPlads
    ? prices.filter(p => p.plads === filterPlads)
    : prices;

  const openCreate = () => { setEditing(null); setForm(emptyForm); setShowForm(true); };
  const openEdit   = (p)  => { setEditing(p);   setForm({ plads: p.plads, fraction: p.fraction || "", price: String(p.price), kind: p.kind || "material" }); setShowForm(true); };

  const save = async () => {
    const isSpecial = form.kind && form.kind !== "material";
    if (!form.plads || !form.price || (!isSpecial && !form.fraction)) {
      toast.error("Udfyld alle felter"); return;
    }
    const body = {
      plads: form.plads,
      fraction: isSpecial ? "" : form.fraction,
      price: parseFloat(form.price),
      kind: form.kind || "material",
    };
    try {
      if (editing) {
        await axios.put(`${API}/tour-prices/${editing.id}`, body);
        toast.success("Pris opdateret");
      } else {
        await axios.post(`${API}/tour-prices`, body);
        toast.success("Pris tilføjet");
      }
      setShowForm(false);
      fetchPrices();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/tour-prices/${id}`);
      toast.success("Pris slettet");
      fetchPrices();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setDeletingId(null); }
  };

  const saveHasterFee = async () => {
    try {
      await axios.post(`${API}/tour-prices/haster-fee`, { fee: hasterFee });
      toast.success("Haster tillæg gemt");
      setEditingHaster(false);
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-4">
      {/* Haster fee */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" /> Haster tillæg
          </p>
          <p className="text-xs text-slate-400 mt-0.5">Ekstra beløb per haster-tur, oven i grundprisen</p>
        </div>
        {editingHaster ? (
          <div className="flex items-center gap-2">
            <input type="number" value={hasterFee} onChange={e => setHasterFee(Number(e.target.value))}
              className="w-24 px-3 py-1.5 border-2 border-amber-400 rounded-lg text-sm font-mono text-right dark:bg-slate-700 dark:text-white outline-none" />
            <span className="text-sm text-slate-500">kr</span>
            <button onClick={saveHasterFee} className="p-1.5 bg-emerald-500 text-white rounded-lg"><Save className="w-4 h-4" /></button>
            <button onClick={() => setEditingHaster(false)} className="p-1.5 bg-slate-200 dark:bg-slate-600 rounded-lg"><X className="w-4 h-4" /></button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-amber-500">+ {hasterFee} kr</span>
            <button onClick={() => setEditingHaster(true)} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
              <Edit2 className="w-4 h-4 text-slate-400" />
            </button>
          </div>
        )}
      </div>

      {/* Price table */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center gap-3">
          <select value={filterPlads} onChange={e => setFilterPlads(e.target.value)}
            className="text-sm px-3 py-1.5 border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none flex-1">
            <option value="">Alle pladser</option>
            {pladsOptions.map(p => <option key={p}>{p}</option>)}
          </select>
          <button onClick={openCreate}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white rounded-lg text-sm font-semibold whitespace-nowrap">
            <Plus className="w-4 h-4" /> Tilføj pris
          </button>
        </div>

        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : filtered.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">
            Ingen priser endnu - tilføj din første pris
          </div>
        ) : (
          <>
            <div className="grid text-[10px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900/50 px-4 py-2 border-b border-slate-100 dark:border-slate-700"
              style={{ gridTemplateColumns: "1fr 1fr 100px 72px" }}>
              <div>Plads</div>
              <div>Fraction / Materiale</div>
              <div className="text-right">Pris</div>
              <div></div>
            </div>
            {filtered.map(p => (
              <div key={p.id}
                className="grid items-center px-4 py-2.5 border-b border-slate-100 dark:border-slate-700/50 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-700/30 group"
                style={{ gridTemplateColumns: "1fr 1fr 100px 72px" }}>
                <div className="font-medium text-sm text-slate-800 dark:text-white">{p.plads}</div>
                <div className="text-sm text-slate-500">
                  {p.kind && p.kind !== "material" ? (
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300">{KIND_LABELS[p.kind] || p.kind}</span>
                  ) : p.fraction}
                </div>
                <div className="text-right font-bold text-sm text-emerald-600">{p.price} kr</div>
                <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => openEdit(p)}
                    className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-600 rounded text-slate-400 hover:text-slate-600">
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => setDeletingId(p.id)}
                    className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            <div className="px-4 py-2 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-100 dark:border-slate-700 text-xs text-slate-400">
              {filtered.length} priser {filterPlads ? `for ${filterPlads}` : "i alt"}
            </div>
          </>
        )}
      </div>

      {/* Add/Edit form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-sm p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-slate-900 dark:text-white">
                {editing ? "Rediger pris" : "Tilføj ny pris"}
              </h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded">
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Type</label>
                <select value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none">
                  <option value="material">Materiale (pr. fraction)</option>
                  <option value="flyt">Flyt container (fast pr. plads)</option>
                  <option value="vaerksted">Til værksted (fast pr. plads)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Plads</label>
                <input value={form.plads} onChange={e => setForm({ ...form, plads: e.target.value })}
                  placeholder="f.eks. Glostrup"
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none" />
              </div>
              {(!form.kind || form.kind === "material") && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Fraction / Materiale</label>
                  <input value={form.fraction} onChange={e => setForm({ ...form, fraction: e.target.value })}
                    placeholder="f.eks. Jord, grus"
                    className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none" />
                </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Pris (kr)</label>
                <input type="number" value={form.price} onChange={e => setForm({ ...form, price: e.target.value })}
                  placeholder="500"
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none" />
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={() => setShowForm(false)}
                  className="flex-1 py-2 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg text-sm font-medium">
                  Annuller
                </button>
                <button onClick={save}
                  className="flex-1 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg text-sm font-bold">
                  {editing ? "Gem ændringer" : "Tilføj pris"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deletingId && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl p-5 max-w-xs w-full text-center">
            <p className="font-bold text-slate-900 dark:text-white mb-2">Slet pris?</p>
            <p className="text-sm text-slate-500 mb-4">Denne handling kan ikke fortrydes.</p>
            <div className="flex gap-2">
              <button onClick={() => setDeletingId(null)}
                className="flex-1 py-2 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg text-sm">
                Annuller
              </button>
              <button onClick={() => remove(deletingId)}
                className="flex-1 py-2 bg-red-500 text-white rounded-lg text-sm font-bold">
                Slet
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============== RAPPORT PANEL ============== */
function RapportPanel() {
  const [period, setPeriod]   = useState("weekly");
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");

  const fetchReport = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ period });
      if (dateFrom) params.append("date_from", dateFrom);
      if (dateTo)   params.append("date_to",   dateTo);
      const { data: d } = await axios.get(`${API}/tour-prices/rapport?${params}`);
      setData(d);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [period, dateFrom, dateTo]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const exportCSV = () => {
    if (!data?.rows?.length) return;
    const headers = ["Dato", "Chauffør", "Plads", "Fraction", "Haster", "Pris (kr)"];
    const rows = data.rows.map(r => [
      r.date, r.driver, r.plads, r.fraction,
      r.is_haster ? "Ja" : "Nej",
      r.price
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `rapport_${period}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    toast.success("CSV downloadet!");
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">Periode</label>
          <select value={period} onChange={e => setPeriod(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm outline-none">
            {PERIODS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">Fra dato</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm outline-none" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">Til dato</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm outline-none" />
        </div>
        <button onClick={exportCSV}
          className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold ml-auto">
          <Download className="w-4 h-4" /> CSV
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Ture i alt", value: data.summary?.total_tours ?? 0, color: "text-slate-900 dark:text-white" },
              { label: "Total beløb", value: `${(data.summary?.total_amount ?? 0).toLocaleString("da-DK")} kr`, color: "text-emerald-600" },
              { label: "Haster tillæg", value: `${(data.summary?.haster_amount ?? 0).toLocaleString("da-DK")} kr`, color: "text-amber-500" },
              { label: "Chauffører", value: data.summary?.driver_count ?? 0, color: "text-slate-900 dark:text-white" },
            ].map(s => (
              <div key={s.label} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
                <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">{s.label}</p>
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              </div>
            ))}
          </div>

          {/* Driver breakdown */}
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
              <p className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2">
                <Users className="w-4 h-4 text-orange-500" /> Chauffør oversigt
              </p>
            </div>
            {!data.by_driver?.length ? (
              <p className="text-center text-slate-400 text-sm py-8">Ingen data i denne periode</p>
            ) : (
              <>
                <div className="grid text-[10px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900/50 px-4 py-2"
                  style={{ gridTemplateColumns: "1fr 60px 60px 100px" }}>
                  <div>Chauffør</div>
                  <div className="text-right">Ture</div>
                  <div className="text-right">Haster</div>
                  <div className="text-right">Beløb</div>
                </div>
                {data.by_driver.map((d, i) => (
                  <div key={i}
                    className="grid items-center px-4 py-2.5 border-b border-slate-100 dark:border-slate-700/50 last:border-0"
                    style={{ gridTemplateColumns: "1fr 60px 60px 100px" }}>
                    <div className="font-medium text-sm text-slate-800 dark:text-white">{d.driver}</div>
                    <div className="text-right text-sm text-slate-500">{d.tours}</div>
                    <div className="text-right text-sm text-amber-500 font-medium">{d.haster}</div>
                    <div className="text-right text-sm font-bold text-emerald-600">
                      {d.amount.toLocaleString("da-DK")} kr
                    </div>
                  </div>
                ))}
                <div className="grid items-center px-4 py-2.5 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-200 dark:border-slate-700"
                  style={{ gridTemplateColumns: "1fr 60px 60px 100px" }}>
                  <div className="font-bold text-sm text-slate-800 dark:text-white">Total</div>
                  <div className="text-right text-sm font-bold text-slate-700 dark:text-slate-200">{data.summary?.total_tours}</div>
                  <div className="text-right text-sm font-bold text-amber-500">{data.summary?.total_haster}</div>
                  <div className="text-right text-sm font-bold text-emerald-600">
                    {(data.summary?.total_amount ?? 0).toLocaleString("da-DK")} kr
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Tour rows */}
          {data.rows?.length > 0 && (
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
                <p className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-orange-500" /> Alle ture ({data.rows.length})
                </p>
              </div>
              <div className="grid text-[10px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900/50 px-4 py-2"
                style={{ gridTemplateColumns: "80px 1fr 1fr 1fr 60px 80px" }}>
                <div>Dato</div>
                <div>Chauffør</div>
                <div>Plads</div>
                <div>Fraction</div>
                <div className="text-center">Haster</div>
                <div className="text-right">Pris</div>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {data.rows.map((r, i) => (
                  <div key={i}
                    className="grid items-center px-4 py-2 border-b border-slate-100 dark:border-slate-700/50 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-700/30"
                    style={{ gridTemplateColumns: "80px 1fr 1fr 1fr 60px 80px" }}>
                    <div className="text-xs text-slate-400 font-mono">{r.date}</div>
                    <div className="text-sm text-slate-700 dark:text-slate-200 truncate">{r.driver}</div>
                    <div className="text-sm text-slate-500 truncate">{r.plads}</div>
                    <div className="text-sm text-slate-500 truncate">{r.fraction}</div>
                    <div className="text-center">
                      {r.is_haster && (
                        <span className="text-[9px] bg-amber-100 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded font-bold">HASTER</span>
                      )}
                    </div>
                    <div className="text-right text-sm font-semibold text-emerald-600">{r.price} kr</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
