import React, { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Recycle, LogOut, Search, Download, Calendar,
  Loader2, BarChart3, Truck, Weight, ChevronDown,
  TrendingUp, Package, CheckCircle2, Clock, PieChart as PieIcon, User,
  DollarSign
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";

const PERIODS = [
  { value: "today",   label: "I dag" },
  { value: "week",    label: "Denne uge" },
  { value: "month",   label: "Denne måned" },
  { value: "custom",  label: "Vælg periode" },
];

export default function GenbrugPladsPage({ onOpenPrices = null }) {
  const { user, logout } = useAuth();
  const [tours, setTours]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [period, setPeriod]     = useState("today");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");
  const [search, setSearch]     = useState("");
  const [filterMaterial, setFilterMaterial] = useState("");
  const [filterDriver, setFilterDriver]     = useState("");
  const [expandedId, setExpandedId]         = useState(null);

  const fetchTours = useCallback(async () => {
    setLoading(true);
    try {
      // Get completed tours for this plads
      const params = new URLSearchParams();
      if (period !== "custom") params.append("period", period);
      if (period === "custom" && dateFrom) params.append("date_from", dateFrom);
      if (period === "custom" && dateTo)   params.append("date_to", dateTo);
      const { data } = await axios.get(`${API}/genbrug/plads-rapport?${params}`);
      setTours(data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally { setLoading(false); }
  }, [period, dateFrom, dateTo]);

  useEffect(() => { fetchTours(); }, [fetchTours]);

  // Unique materials and drivers for filters
  const materials = useMemo(() => [...new Set(tours.map(t => t.fraction).filter(Boolean))].sort(), [tours]);
  const drivers   = useMemo(() => [...new Set(tours.map(t => t.driver_name || t.claimed_by).filter(Boolean))].sort(), [tours]);

  const filtered = useMemo(() => {
    let list = [...tours];
    if (search)         list = list.filter(t =>
      (t.fraction || "").toLowerCase().includes(search.toLowerCase()) ||
      (t.driver_name || t.claimed_by || "").toLowerCase().includes(search.toLowerCase()) ||
      (t.address || "").toLowerCase().includes(search.toLowerCase())
    );
    if (filterMaterial) list = list.filter(t => t.fraction === filterMaterial);
    if (filterDriver)   list = list.filter(t => (t.driver_name || t.claimed_by) === filterDriver);
    return list;
  }, [tours, search, filterMaterial, filterDriver]);

  // Summary stats
  const summary = useMemo(() => ({
    total:     filtered.length,
    total_kg:  filtered.reduce((s, t) => s + (parseFloat(t.weight) || 0), 0),
    materials: [...new Set(filtered.map(t => t.fraction).filter(Boolean))].length,
    drivers:   [...new Set(filtered.map(t => t.driver_name || t.claimed_by).filter(Boolean))].length,
  }), [filtered]);

  // Monthly trend (from all tours, not just filtered)
  const monthlyTrend = useMemo(() => {
    const m = {};
    tours.forEach(t => {
      const key = (t.date || "").slice(0,7);
      if (!key) return;
      if (!m[key]) m[key] = { month: key, tours: 0, kg: 0 };
      m[key].tours++;
      m[key].kg += parseFloat(t.weight) || 0;
    });
    return Object.values(m).sort((a,b) => a.month.localeCompare(b.month)).slice(-6);
  }, [tours]);

  // Material breakdown
  const byMaterial = useMemo(() => {
    const m = {};
    filtered.forEach(t => {
      const k = t.fraction || "Ukendt";
      if (!m[k]) m[k] = { name: k, count: 0, kg: 0 };
      m[k].count++;
      m[k].kg += parseFloat(t.weight) || 0;
    });
    return Object.values(m).sort((a, b) => b.kg - a.kg);
  }, [filtered]);

  const exportCSV = () => {
    if (!filtered.length) { toast.error("Ingen data at eksportere"); return; }
    const headers = ["Dato", "Tid", "Chauffør", "Materiale", "Adresse", "Vægt (kg)", "Kontejner", "Regnr"];
    const rows = filtered.map(t => [
      t.date || "",
      t.time || "",
      t.driver_name || t.claimed_by || "",
      t.fraction || "",
      t.address || "",
      t.weight || "",
      t.container || "",
      t.reg_nr || "",
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const label = PERIODS.find(p => p.value === period)?.label || "periode";
    a.download = `genbrug_${label.replace(/ /g,"_")}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    toast.success("CSV downloadet!");
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">

      {/* Header */}
      <header className="bg-[#0D2B1F] text-white sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-emerald-600 rounded-lg flex items-center justify-center flex-shrink-0">
              <Recycle className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-bold text-base leading-tight">Genbrug Plads</p>
              <p className="text-emerald-400 text-[11px] uppercase tracking-wider leading-tight">
                {user?.company_name || "Forsyning"}
                {user?.is_hq_admin && (
                  <span className="ml-2 px-1.5 py-0.5 bg-emerald-500/30 text-emerald-200 rounded text-[9px] font-bold">HQ</span>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onOpenPrices && (
              <button
                onClick={onOpenPrices}
                data-testid="open-prices-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                <DollarSign className="w-3.5 h-3.5" /> Priser
              </button>
            )}
            <button onClick={logout}
              className="flex items-center gap-1.5 text-xs text-emerald-300 hover:text-white transition-colors">
              <LogOut className="w-4 h-4" /> Log ud
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-5 space-y-5">

        {/* Site-user info banner: indicates filtered view */}
        {user?.role === "genbrug_plads" && !user?.is_hq_admin && (
          <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3 flex items-start gap-3" data-testid="site-user-banner">
            <div className="w-8 h-8 bg-amber-100 dark:bg-amber-900/40 rounded-lg flex items-center justify-center flex-shrink-0">
              <User className="w-4 h-4 text-amber-700 dark:text-amber-300" />
            </div>
            <div className="text-sm text-amber-900 dark:text-amber-100">
              <p className="font-semibold leading-tight">Site-bruger visning</p>
              <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
                Du ser kun ture for de pladser, der er tildelt din konto.
                Kontakt din HQ-administrator for at få adgang til flere pladser.
              </p>
            </div>
          </div>
        )}

        {/* Period selector + CSV */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-1">
            {PERIODS.map(p => (
              <button key={p.value} onClick={() => setPeriod(p.value)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  period === p.value
                    ? "bg-emerald-600 text-white"
                    : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                }`}>
                {p.label}
              </button>
            ))}
          </div>

          {period === "custom" && (
            <div className="flex items-center gap-2">
              <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                className="px-3 py-1.5 border border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm outline-none focus:border-emerald-500" />
              <span className="text-slate-400 text-sm">→</span>
              <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                className="px-3 py-1.5 border border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm outline-none focus:border-emerald-500" />
            </div>
          )}

          <button onClick={exportCSV}
            className="ml-auto flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold transition-colors">
            <Download className="w-4 h-4" />
            Download CSV
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Ture i alt",    value: summary.total,    icon: Truck,        color: "text-slate-800 dark:text-white",  bg: "bg-slate-100 dark:bg-slate-700" },
            { label: "Total vægt",    value: `${summary.total_kg.toLocaleString("da-DK")} kg`, icon: Weight, color: "text-emerald-700 dark:text-emerald-300", bg: "bg-emerald-50 dark:bg-emerald-950/30" },
            { label: "Materialer",    value: summary.materials, icon: Package,      color: "text-blue-700 dark:text-blue-300",  bg: "bg-blue-50 dark:bg-blue-950/30" },
            { label: "Chauffører",    value: summary.drivers,   icon: TrendingUp,   color: "text-purple-700 dark:text-purple-300", bg: "bg-purple-50 dark:bg-purple-950/30" },
          ].map(s => (
            <div key={s.label} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className={`w-10 h-10 ${s.bg} rounded-lg flex items-center justify-center flex-shrink-0`}>
                <s.icon className={`w-5 h-5 ${s.color}`} />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold leading-none">{s.label}</p>
                <p className={`text-xl font-bold mt-0.5 leading-none ${s.color}`}>{s.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Charts row */}
        {byMaterial.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

            {/* Material bar chart */}
            <div className="md:col-span-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-500" /> Materiale oversigt (kg)
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byMaterial.slice(0,8)} layout="vertical" margin={{left:8,right:16}}>
                  <XAxis type="number" tick={{fontSize:10}} tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(1)}t` : v} />
                  <YAxis type="category" dataKey="name" tick={{fontSize:10}} width={90} />
                  <Tooltip formatter={(v) => [`${v.toLocaleString("da-DK")} kg`]} />
                  <Bar dataKey="kg" fill="#22C55E" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Pie chart - tur sayısı */}
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4 flex items-center gap-2">
                <PieIcon className="w-4 h-4 text-blue-500" /> Ture fordeling
              </p>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={byMaterial.slice(0,6)} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={65} label={false}>
                    {byMaterial.slice(0,6).map((_, i) => (
                      <Cell key={i} fill={["#22C55E","#3B82F6","#F59E0B","#EF4444","#8B5CF6","#06B6D4"][i % 6]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v + " ture", n]} />
                  <Legend iconSize={8} wrapperStyle={{fontSize:"10px"}} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Top drivers */}
        {filtered.length > 0 && (() => {
          const driverStats = {};
          filtered.forEach(t => {
            const d = t.driver_name || t.claimed_by || "Ukendt";
            if (!driverStats[d]) driverStats[d] = { name: d, tours: 0, kg: 0 };
            driverStats[d].tours++;
            driverStats[d].kg += parseFloat(t.weight) || 0;
          });
          const topDrivers = Object.values(driverStats).sort((a,b) => b.kg - a.kg).slice(0,5);
          if (!topDrivers.length) return null;
          return (
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3 flex items-center gap-2">
                <User className="w-4 h-4 text-purple-500" /> Top chauffører
              </p>
              <div className="space-y-2">
                {topDrivers.map((d, i) => {
                  const maxKg = topDrivers[0]?.kg || 1;
                  return (
                    <div key={d.name} className="flex items-center gap-3">
                      <span style={{
                        width:"20px",height:"20px",borderRadius:"50%",
                        background:["#22C55E","#3B82F6","#F59E0B","#8B5CF6","#EF4444"][i],
                        color:"white",fontSize:"10px",fontWeight:"700",
                        display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0
                      }}>{i+1}</span>
                      <span className="text-sm text-slate-600 dark:text-slate-300 w-32 truncate">{d.name}</span>
                      <div className="flex-1 h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{width:`${(d.kg/maxKg)*100}%`, background:["#22C55E","#3B82F6","#F59E0B","#8B5CF6","#EF4444"][i]}} />
                      </div>
                      <span className="text-xs text-slate-500 w-32 text-right">
                        {d.tours} ture · {d.kg.toLocaleString("da-DK")} kg
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        {/* Monthly trend */}
        {period !== "today" && monthlyTrend.length > 1 && (
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-500" /> Månedlig trend (kg)
            </p>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={monthlyTrend} margin={{left:0,right:8}}>
                <XAxis dataKey="month" tick={{fontSize:10}} tickFormatter={v => v.slice(5)} />
                <YAxis tick={{fontSize:10}} tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}t` : v} />
                <Tooltip formatter={(v) => [`${v.toLocaleString("da-DK")} kg`]} labelFormatter={l => l} />
                <Bar dataKey="kg" fill="#22C55E" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Søg materiale, chauffør, adresse..."
              className="w-full pl-9 pr-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm outline-none focus:border-emerald-500" />
          </div>
          <select value={filterMaterial} onChange={e => setFilterMaterial(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm outline-none focus:border-emerald-500">
            <option value="">Alle materialer</option>
            {materials.map(m => <option key={m}>{m}</option>)}
          </select>
          <select value={filterDriver} onChange={e => setFilterDriver(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm outline-none focus:border-emerald-500">
            <option value="">Alle chauffører</option>
            {drivers.map(d => <option key={d}>{d}</option>)}
          </select>
          {(search || filterMaterial || filterDriver) && (
            <button onClick={() => { setSearch(""); setFilterMaterial(""); setFilterDriver(""); }}
              className="px-3 py-2 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
              Ryd filter
            </button>
          )}
        </div>

        {/* Tour table */}
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid text-[10px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900/50 px-4 py-2.5 border-b border-slate-200 dark:border-slate-700"
            style={{ gridTemplateColumns: "90px 1fr 140px 100px 90px 24px" }}>
            <div>Dato / Tid</div>
            <div>Materiale / Adresse</div>
            <div>Chauffør</div>
            <div className="text-right">Vægt</div>
            <div>Regnr</div>
            <div></div>
          </div>

          {loading ? (
            <div className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Recycle className="w-10 h-10 mx-auto mb-3 text-slate-200 dark:text-slate-600" />
              <p className="text-slate-400 text-sm font-medium">Ingen ture fundet</p>
              <p className="text-slate-300 dark:text-slate-600 text-xs mt-1">Prøv en anden periode eller fjern filtre</p>
            </div>
          ) : (
            <>
              {filtered.map((t, idx) => {
                const driver = t.driver_name || t.claimed_by || "-";
                const isExpanded = expandedId === t.id;
                return (
                  <div key={t.id || idx}>
                    <div
                      className="grid items-center px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-700/30 cursor-pointer transition-colors"
                      style={{ gridTemplateColumns: "90px 1fr 140px 100px 90px 24px" }}
                      onClick={() => setExpandedId(isExpanded ? null : t.id)}
                    >
                      {/* Dato */}
                      <div>
                        <p className="text-xs font-mono text-slate-700 dark:text-slate-200">{t.date || "-"}</p>
                        <p className="text-[10px] text-slate-400">{t.time || ""}</p>
                      </div>

                      {/* Materiale + adresse */}
                      <div className="min-w-0 pr-3">
                        <p className="text-sm font-semibold text-slate-800 dark:text-white truncate">{t.fraction || "-"}</p>
                        <p className="text-[11px] text-slate-400 truncate">{t.address || ""}</p>
                      </div>

                      {/* Chauffør */}
                      <div className="min-w-0 pr-3">
                        <p className="text-sm text-slate-600 dark:text-slate-300 truncate">{driver}</p>
                        {t.container && <p className="text-[10px] text-slate-400">{t.container}</p>}
                      </div>

                      {/* Vægt */}
                      <div className="text-right">
                        {t.weight ? (
                          <p className="text-sm font-bold text-emerald-600">
                            {parseFloat(t.weight).toLocaleString("da-DK")} kg
                          </p>
                        ) : (
                          <p className="text-xs text-slate-300">-</p>
                        )}
                      </div>

                      {/* Regnr */}
                      <div>
                        <p className="text-xs font-mono text-slate-500">{t.reg_nr || "-"}</p>
                      </div>

                      {/* Expand arrow */}
                      <div className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}>
                        <ChevronDown className="w-4 h-4 text-slate-300" />
                      </div>
                    </div>

                    {/* Expanded detail */}
                    {isExpanded && (
                      <div className="bg-slate-50 dark:bg-slate-900/40 border-b border-slate-200 dark:border-slate-700 px-4 py-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          {[
                            { label: "Chauffør",   value: driver },
                            { label: "Regnr",      value: t.reg_nr || "-" },
                            { label: "Materiale",  value: t.fraction || "-" },
                            { label: "Container",  value: t.container || "-" },
                            { label: "Adresse",    value: t.address || "-" },
                            { label: "Plads",      value: t.plads || "-" },
                            { label: "Vægt",       value: t.weight ? `${parseFloat(t.weight).toLocaleString("da-DK")} kg` : "-" },
                            { label: "Dato / Tid", value: `${t.date || "-"} ${t.time || ""}`.trim() },
                          ].map(f => (
                            <div key={f.label} className="bg-white dark:bg-slate-800 rounded-lg p-2.5 border border-slate-200 dark:border-slate-700">
                              <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-0.5">{f.label}</p>
                              <p className="text-sm font-medium text-slate-800 dark:text-white">{f.value}</p>
                            </div>
                          ))}
                        </div>
                        {t.remark && (
                          <div className="mt-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                            <span className="font-semibold">Bemærkning:</span> {t.remark}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Footer */}
              <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between">
                <span className="text-xs text-slate-400">{filtered.length} ture · {summary.total_kg.toLocaleString("da-DK")} kg i alt</span>
                <button onClick={exportCSV}
                  className="flex items-center gap-1.5 text-xs text-emerald-600 hover:text-emerald-700 font-semibold">
                  <Download className="w-3.5 h-3.5" /> Download CSV
                </button>
              </div>
            </>
          )}
        </div>

      </main>
    </div>
  );
}
