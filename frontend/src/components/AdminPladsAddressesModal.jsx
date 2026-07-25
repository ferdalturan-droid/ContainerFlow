import React, { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Home, Search, Plus, Upload, Trash2, Building2, Loader2 } from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Modal for managing sub-addresses under a plads.
 * Used by both Logistics Admin (AdminPage) and Super Admin pages.
 * Uses tenant-scoped /api/plads/{id}/addresses endpoints.
 */
export default function AdminPladsAddressesModal({ plads, onClose }) {
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("list");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ sub_area: "", postcode: "", city: "", street: "" });
  const [bulkText, setBulkText] = useState("");

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/plads/${plads.id}/addresses`);
      setAddresses(data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [plads.id]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const filtered = addresses.filter(a => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (a.street || "").toLowerCase().includes(s)
      || (a.sub_area || "").toLowerCase().includes(s)
      || (a.city || "").toLowerCase().includes(s)
      || (a.postcode || "").toLowerCase().includes(s);
  });

  const grouped = useMemo(() => {
    const g = {};
    filtered.forEach(a => {
      const k = a.sub_area || "Andre";
      if (!g[k]) g[k] = [];
      g[k].push(a);
    });
    return Object.entries(g).sort((a, b) => a[0].localeCompare(b[0], "da"));
  }, [filtered]);

  const addOne = async () => {
    if (!form.street.trim()) { toast.error("Adresse er påkrævet"); return; }
    try {
      await axios.post(`${API}/plads/${plads.id}/addresses`, form);
      toast.success("Adresse oprettet");
      setForm({ sub_area: "", postcode: "", city: "", street: "" });
      fetchList();
      setTab("list");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const addBulk = async () => {
    const lines = bulkText.split("\n").map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) { toast.error("Indtast mindst én linje"); return; }
    const items = lines.map(line => {
      const sep = line.includes("|") ? "|" : ";";
      const parts = line.split(sep).map(s => s.trim());
      let sub_area = "", postcode = "", city = "", street = "";
      if (parts.length >= 3) {
        sub_area = parts[0];
        const pc = parts[1].match(/^(\d{4})\s+(.+)$/);
        if (pc) { postcode = pc[1]; city = pc[2]; } else { city = parts[1]; }
        street = parts.slice(2).join(" ").trim();
      } else if (parts.length === 2) {
        sub_area = parts[0];
        street = parts[1];
      } else {
        street = parts[0];
      }
      return { sub_area, postcode, city, street };
    });
    try {
      const res = await axios.post(`${API}/plads/${plads.id}/addresses/bulk`, { items });
      toast.success(`${res.data.created} adresser oprettet`);
      setBulkText("");
      fetchList();
      setTab("list");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const removeAddr = async (id) => {
    try {
      await axios.delete(`${API}/plads/addresses/${id}`);
      toast.success("Adresse slettet");
      fetchList();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="admin-addresses-modal">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-3xl w-full max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
          <div className="min-w-0">
            <h3 className="font-bold text-lg sm:text-xl text-slate-900 dark:text-white truncate inline-flex items-center gap-2">
              <Home className="w-5 h-5 text-orange-500 flex-shrink-0" /> Adresser · {plads.name}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">{addresses.length} adresser i alt</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700" data-testid="admin-addresses-close">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="px-5 pt-3 flex gap-1 border-b border-slate-200 dark:border-slate-700">
          {["list", "add", "bulk"].map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm font-semibold border-b-2 ${
                tab === t ? "border-orange-500 text-slate-900 dark:text-white" : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              }`}
              data-testid={`admin-addresses-tab-${t}`}
            >
              {t === "list" ? "Liste" : t === "add" ? "+ Tilføj én" : "↑ Bulk import"}
            </button>
          ))}
        </div>

        <div className="overflow-y-auto p-5 flex-1">
          {tab === "list" && (
            <>
              <div className="relative max-w-sm mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Søg..."
                  className="pl-9 pr-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm w-full focus:border-orange-500 outline-none"
                  data-testid="admin-addresses-search" />
              </div>
              {loading ? (
                <div className="text-center py-12 text-slate-500"><Loader2 className="w-5 h-5 inline animate-spin" /></div>
              ) : grouped.length === 0 ? (
                <p className="text-center text-slate-500 py-12">Ingen adresser endnu. Skift til "Bulk import" for at tilføje mange på én gang.</p>
              ) : (
                <div className="space-y-4">
                  {grouped.map(([area, list]) => (
                    <div key={area}>
                      <h4 className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-1.5 inline-flex items-center gap-1.5">
                        <Building2 className="w-3 h-3" /> {area} <span className="text-slate-400">· {list.length}</span>
                      </h4>
                      <div className="divide-y divide-slate-100 dark:divide-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
                        {list.map(a => (
                          <div key={a.id} className="px-3 py-2 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-900/40">
                            <Home className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{a.street}</p>
                              <p className="text-xs text-slate-500">{[a.postcode, a.city].filter(Boolean).join(" ")}</p>
                            </div>
                            <button onClick={() => removeAddr(a.id)} className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-950/40" title="Slet"
                              data-testid={`admin-address-delete-${a.id}`}>
                              <Trash2 className="w-3.5 h-3.5 text-red-600" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "add" && (
            <div className="space-y-3 max-w-md">
              <div>
                <label className="block text-sm font-medium mb-1.5 text-slate-700 dark:text-slate-300">Underområde (fx Nordkysten)</label>
                <input value={form.sub_area} onChange={(e) => setForm({ ...form, sub_area: e.target.value })}
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500"
                  data-testid="admin-address-sub-area" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-slate-700 dark:text-slate-300">Postnr</label>
                  <input value={form.postcode} onChange={(e) => setForm({ ...form, postcode: e.target.value })}
                    placeholder="3000"
                    className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500 font-mono"
                    data-testid="admin-address-postcode" />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium mb-1.5 text-slate-700 dark:text-slate-300">By</label>
                  <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}
                    placeholder="Helsingør"
                    className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500"
                    data-testid="admin-address-city" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5 text-slate-700 dark:text-slate-300">Adresse *</label>
                <input value={form.street} onChange={(e) => setForm({ ...form, street: e.target.value })}
                  placeholder="Folehaven 1"
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500"
                  data-testid="admin-address-street" />
              </div>
              <button onClick={addOne} className="mt-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-bold text-sm inline-flex items-center gap-2"
                data-testid="admin-address-add-btn">
                <Plus className="w-4 h-4" /> Tilføj
              </button>
            </div>
          )}

          {tab === "bulk" && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600 dark:text-slate-300">Indsæt liste - én linje per adresse. Format:</p>
              <code className="block bg-slate-100 dark:bg-slate-900 rounded p-2 text-xs font-mono">
                Underområde | Postnr By | Adresse
              </code>
              <textarea rows={12} value={bulkText} onChange={(e) => setBulkText(e.target.value)}
                placeholder={"Nordkysten | 3000 Helsingør | Folehaven 1\nNordkysten | 3000 Helsingør | Kongevejen 1, afd. 82 - Hovparken\nBoliggården | 3000 Helsingør | Blishøj 1"}
                className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500 font-mono text-xs leading-relaxed"
                data-testid="admin-address-bulk-text" />
              <button onClick={addBulk} className="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-bold text-sm inline-flex items-center gap-2"
                data-testid="admin-address-bulk-btn">
                <Upload className="w-4 h-4" /> Importer
              </button>
              <p className="text-xs text-slate-500">Tip: du kan paste direkte fra et Excel-ark. Også <code>;</code> som separator virker.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
