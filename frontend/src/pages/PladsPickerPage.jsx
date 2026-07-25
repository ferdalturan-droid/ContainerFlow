import React, { useState, useEffect, useMemo, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MapPin, Search, LogOut, Truck, ChevronRight, ChevronLeft, Loader2, Building2, Home } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";

export default function PladsPickerPage({ onSelect }) {
  const { user, logout } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // Step state: if a plads with sub-addresses is selected, show address picker
  const [selectedPlads, setSelectedPlads] = useState(null);
  const [addresses, setAddresses] = useState([]);
  const [loadingAddresses, setLoadingAddresses] = useState(false);

  const fetchPlads = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/plads`);
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPlads(); }, [fetchPlads]);

  const filtered = useMemo(() => {
    const list = [...items].sort((a, b) =>
      (a.city || a.name || "").localeCompare(b.city || b.name || "", "da")
    );
    if (!search) return list;
    const s = search.toLowerCase();
    return list.filter(p =>
      (p.name || "").toLowerCase().includes(s) ||
      (p.city || "").toLowerCase().includes(s) ||
      (p.address || "").toLowerCase().includes(s)
    );
  }, [items, search]);

  const handlePladsClick = async (plads) => {
    const code = plads.effective_location_code || plads.location_code;
    if (!code) {
      toast.error("Ingen lokation tilgængelig. Kontakt din administrator.");
      return;
    }
    if (plads.address_count > 0) {
      // Show address picker step
      setSelectedPlads(plads);
      setLoadingAddresses(true);
      try {
        const { data } = await axios.get(`${API}/plads/${plads.id}/addresses`);
        setAddresses(data || []);
      } catch (e) {
        toast.error(formatApiError(e));
      } finally {
        setLoadingAddresses(false);
      }
    } else {
      // Direct to order page
      if (onSelect) onSelect(code, plads, null);
    }
  };

  const handleAddressClick = (addr) => {
    const code = selectedPlads.effective_location_code || selectedPlads.location_code;
    if (onSelect) onSelect(code, selectedPlads, addr);
  };

  // ===== Step 2: address picker =====
  if (selectedPlads) {
    return (
      <AddressPicker
        plads={selectedPlads}
        addresses={addresses}
        loading={loadingAddresses}
        onBack={() => { setSelectedPlads(null); setAddresses([]); setSearch(""); }}
        onLogout={logout}
        onSelect={handleAddressClick}
      />
    );
  }

  // ===== Step 1: plads picker =====
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900" data-testid="plads-picker-page">

      {/* Header */}
      <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center">
              <Truck className="w-5 h-5 text-orange-400" />
            </div>
            <div>
              <h1 className="font-heading font-bold text-lg leading-tight">Bestil Afhentning</h1>
              <p className="text-xs text-slate-400">{user?.company_name || user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
            data-testid="picker-logout-btn"
          >
            <LogOut className="w-4 h-4" /> Log ud
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-5">
        <div>
          <h2 className="font-heading font-bold text-2xl sm:text-3xl text-slate-900 dark:text-white">
            Vælg genbrugsplads
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Tryk på pladsen du vil bestille afhentning til.
          </p>
        </div>

        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Søg by, plads eller adresse..."
            className="pl-10 pr-3 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl text-sm focus:border-orange-500 outline-none w-full"
            data-testid="plads-picker-search"
          />
        </div>

        {loading ? (
          <div className="text-center py-16 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin inline" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white dark:bg-slate-800 rounded-xl p-12 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
            <MapPin className="w-10 h-10 mx-auto mb-3 text-slate-300" />
            {items.length === 0 ? (
              <>
                <p className="font-medium">Ingen pladser tilgængelige endnu</p>
                <p className="text-sm mt-1">Kontakt din administrator for at få adgang.</p>
              </>
            ) : (
              <>
                <p className="font-medium">Ingen pladser matcher din søgning</p>
                <p className="text-sm mt-1">Prøv et andet søgeord.</p>
              </>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="plads-picker-grid">
            {filtered.map(p => {
              const code = p.effective_location_code || p.location_code;
              const ready = !!code;
              const hasSubAddresses = (p.address_count || 0) > 0;
              return (
                <button
                  key={p.id}
                  onClick={() => handlePladsClick(p)}
                  disabled={!ready}
                  className={`group text-left bg-white dark:bg-slate-800 rounded-xl p-5 border-2 transition-all shadow-sm hover:shadow-lg ${
                    ready
                      ? "border-slate-200 dark:border-slate-700 hover:border-orange-500 hover:-translate-y-0.5 cursor-pointer"
                      : "border-slate-200 dark:border-slate-700 opacity-50 cursor-not-allowed"
                  }`}
                  data-testid={`plads-picker-card-${p.id}`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 bg-orange-100 text-orange-600 dark:bg-orange-950/40 dark:text-orange-400">
                      {hasSubAddresses ? <Building2 className="w-5 h-5" /> : <MapPin className="w-5 h-5" />}
                    </div>
                    <ChevronRight className={`w-5 h-5 text-slate-300 transition-all ${ready ? "group-hover:text-orange-500 group-hover:translate-x-1" : ""}`} />
                  </div>
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-base text-slate-900 dark:text-white">
                      {p.city || p.name}
                    </h3>
                    {p.city && p.name && p.city !== p.name && (
                      <p className="text-sm text-slate-600 dark:text-slate-300 truncate">{p.name}</p>
                    )}
                    {p.address && (
                      <p className="text-xs text-slate-500 truncate">{p.address}</p>
                    )}
                    {hasSubAddresses && (
                      <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mt-1.5 inline-flex items-center gap-1">
                        <Home className="w-3 h-3" /> {p.address_count} adresser
                      </p>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        <p className="text-xs text-slate-400 text-center pt-4">
          Pladserne administreres af din administrator via Super Admin panelet.
        </p>
      </main>
    </div>
  );
}

/* ============== Sub-Address Picker (Step 2) ============== */
function AddressPicker({ plads, addresses, loading, onBack, onLogout, onSelect }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search) return addresses;
    const s = search.toLowerCase();
    return addresses.filter(a =>
      (a.street || "").toLowerCase().includes(s) ||
      (a.sub_area || "").toLowerCase().includes(s) ||
      (a.city || "").toLowerCase().includes(s) ||
      (a.postcode || "").toLowerCase().includes(s)
    );
  }, [addresses, search]);

  // Group by sub_area for nicer display
  const grouped = useMemo(() => {
    const groups = {};
    filtered.forEach(a => {
      const key = a.sub_area || "Andre";
      if (!groups[key]) groups[key] = [];
      groups[key].push(a);
    });
    return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0], "da"));
  }, [filtered]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900" data-testid="address-picker-page">

      <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={onBack}
              className="p-2 rounded-lg hover:bg-slate-800 text-slate-300 flex-shrink-0"
              title="Tilbage"
              data-testid="address-back-btn"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div className="w-10 h-10 rounded-xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center flex-shrink-0">
              <Building2 className="w-5 h-5 text-orange-400" />
            </div>
            <div className="min-w-0">
              <h1 className="font-heading font-bold text-base sm:text-lg leading-tight truncate">{plads.name}</h1>
              <p className="text-xs text-slate-400 truncate">Vælg adresse · {addresses.length} adresser</p>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex-shrink-0"
          >
            <LogOut className="w-4 h-4" /> Log ud
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-5">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Søg adresse, postnr, område..."
            className="pl-10 pr-3 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl text-sm focus:border-orange-500 outline-none w-full"
            data-testid="address-search"
            autoFocus
          />
        </div>

        {loading ? (
          <div className="text-center py-16 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
        ) : grouped.length === 0 ? (
          <div className="bg-white dark:bg-slate-800 rounded-xl p-12 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
            <Home className="w-10 h-10 mx-auto mb-3 text-slate-300" />
            <p className="font-medium">Ingen adresser matcher</p>
          </div>
        ) : (
          <div className="space-y-5">
            {grouped.map(([area, list]) => (
              <section key={area}>
                <h3 className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-2 px-1 inline-flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5" /> {area}
                  <span className="text-slate-400 font-medium">· {list.length}</span>
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {list.map(a => (
                    <button
                      key={a.id}
                      onClick={() => onSelect(a)}
                      className="group text-left bg-white dark:bg-slate-800 rounded-xl px-4 py-3 border border-slate-200 dark:border-slate-700 shadow-sm hover:border-orange-500 hover:shadow-md transition-all flex items-center gap-3"
                      data-testid={`address-card-${a.id}`}
                    >
                      <Home className="w-4 h-4 text-orange-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm text-slate-900 dark:text-white truncate">{a.street}</p>
                        {(a.postcode || a.city) && (
                          <p className="text-xs text-slate-500 truncate">
                            {[a.postcode, a.city].filter(Boolean).join(" ")}
                          </p>
                        )}
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-orange-500 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
