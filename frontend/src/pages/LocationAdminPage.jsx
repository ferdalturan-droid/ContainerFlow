import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { saveAs } from "file-saver";
import axios from "axios";
import { toast } from "sonner";
import {
  MapPin, Users, Plus, Trash2, X, Check, Loader2, Mail, Edit2,
  LogOut, ClipboardList, Truck, Clock, CheckCircle2, AlertTriangle, Filter,
  Eye, EyeOff, Calendar, Activity, PowerOff, ShieldAlert, Copy, Save, Lock,
  Pause, Power, Search, Megaphone, BarChart3, Ruler, FileDown, FileSpreadsheet, FileText,
  Bell, Leaf, ChevronDown, MoreHorizontal, Menu, CalendarClock,
} from "lucide-react";
import FixedSchedulesTab from "./FixedSchedulesTab";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";
import { exportReportXLSX } from "../lib/excelExport";

/**
 * Location admin - admin of ONE OR MORE plads (locations) inside a customer
 * company. The customer_admin grants access via assigned_plads_ids; a single
 * admin can therefore manage several pladser at once.
 *
 * Tabs:
 *   - Medarbejdere     - add/edit/inactivate/SLET employees across all
 *                        managed pladser. Each employee belongs to ONE plads.
 *   - Bestillinger     - local dashboard of orders at all managed pladser
 *   - Logistik-partnere - READ-ONLY view of partners assigned to each plads
 *                        by the customer_admin
 *   - Slet permanent   - GDPR-style permanent purge of inactive employees
 */

/* --------------------------------------------------------------------
   DeltaShortcutButton - header-genvej til at åbne helligdags-delta-popup.
   Bruger CustomEvents 'cf:delta-count' (læser antal) og dispatcher
   'cf:open-delta-popup' når der trykkes. Pr. 2026-06-15 brugerkrav.
   -------------------------------------------------------------------- */
function DeltaShortcutButton() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const onCount = (e) => setCount((e.detail && e.detail.count) || 0);
    window.addEventListener("cf:delta-count", onCount);
    return () => window.removeEventListener("cf:delta-count", onCount);
  }, []);
  if (count === 0) return null;
  return (
    <button
      onClick={() => window.dispatchEvent(new Event("cf:open-delta-popup"))}
      className="relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold animate-pulse hover:animate-none"
      title="Genåbn helligdags-delta-popup"
      data-testid="ladmin-delta-shortcut">
      <Bell className="w-3.5 h-3.5" />
      <span className="hidden sm:inline">Genåbn delta</span>
      <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 bg-red-500 text-white text-[10px] font-bold rounded-full">
        {count}
      </span>
    </button>
  );
}


export default function LocationAdminPage() {
  const { user, logout } = useAuth();
  const [locations, setLocations] = useState([]); // managed pladser, FULL objects
  const [tab, setTab] = useState("employees");
  // Selected plads for the "Gå til bestilling" launcher
  const [orderTarget, setOrderTarget] = useState(null);
  const primaryCode = user?.location_code;
  const managedCodes = useMemo(() => {
    const codes = new Set([...(user?.assigned_plads_ids || []), primaryCode].filter(Boolean));
    return Array.from(codes);
  }, [user, primaryCode]);

  // Load every managed plads (name + partners) for the header + employee form.
  useEffect(() => {
    if (managedCodes.length === 0) return;
    axios.get(`${API}/org/locations`).then(({ data }) => {
      setLocations((data || []).filter(l =>
        managedCodes.includes(l.code) || managedCodes.includes(l.location_code),
      ));
    }).catch(() => {});
  }, [managedCodes]);

  // Fase 18.20 (2026-02-28): Tab-rækkefølge per brugerkrav. Primære faner
  // står i toppen i denne præcise rækkefølge. Sekundære faner samles i en
  // "Mere"-dropdown så hovedlinjen er ren og handlingsorienteret.
  const TABS = [
    { id: "orders", label: "Bestillinger", icon: ClipboardList },
    { id: "fixed", label: "Faste tømninger", icon: CalendarClock },
    { id: "employees", label: "Medarbejdere", icon: Users },
    { id: "schedule", label: "Åbnings- og lukketidspunkter", icon: Clock },
    { id: "archive", label: "Arkiv", icon: FileText },
    { id: "reports", label: "Rapportering", icon: BarChart3 },
  ];
  const MORE_TABS = [
    { id: "capacity", label: "Kapacitetsmål", icon: Ruler },
    { id: "delivery", label: "Leveringsadresser", icon: MapPin },
    { id: "received-deltas", label: "Modtagne delta'er", icon: Bell },
    { id: "partners", label: "Logistik-partnere", icon: Truck },
    { id: "purge", label: "Slet permanent", icon: ShieldAlert },
  ];
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const activeMoreTab = MORE_TABS.find(t => t.id === tab);
  const activeTab = [...TABS, ...MORE_TABS].find(t => t.id === tab) || TABS[0];
  // Luk dropdown ved klik udenfor (tjekker BÅDE knap og portal-menu).
  const moreRef = useRef(null);
  const moreMenuRef = useRef(null);
  const [moreRect, setMoreRect] = useState(null);
  useEffect(() => {
    if (!moreOpen) return;
    // Beregn knappens bounding-rect ved åbning + ved resize/scroll så menu
    // følger med uden at blive klippet af forælder-overflow.
    const update = () => {
      if (moreRef.current) setMoreRect(moreRef.current.getBoundingClientRect());
    };
    update();
    const onDocClick = (e) => {
      const t = e.target;
      const inBtn = moreRef.current && moreRef.current.contains(t);
      const inMenu = moreMenuRef.current && moreMenuRef.current.contains(t);
      if (!inBtn && !inMenu) setMoreOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [moreOpen]);

  // Header subtitle - one plads name or "N pladser"
  const locName = locations.length === 1
    ? locations[0].name
    : locations.length > 1
      ? `${locations.length} lokationer`
      : (primaryCode || "Lokation");

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900" data-testid="location-admin-page">
      <header className="bg-[#0F172A] text-white sticky top-0 z-10">
        <div className="max-w-screen-2xl mx-auto px-3 sm:px-10 py-2 sm:py-3 flex items-center justify-between gap-2">
          {/* Mobil hamburger-menu - åbner side-drawer med alle moduler */}
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="sm:hidden p-2 rounded-lg bg-slate-800/70 hover:bg-slate-700 text-emerald-300 shrink-0"
            data-testid="ladmin-mobile-menu-btn"
            aria-label="Åbn menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            <div className="hidden sm:flex w-9 h-9 bg-emerald-600 rounded-lg items-center justify-center shrink-0"><MapPin className="w-5 h-5" /></div>
            <div className="min-w-0">
              <p className="font-bold leading-tight text-sm sm:text-lg truncate" data-testid="ladmin-location-name">
                {locName}
              </p>
              <p className="text-emerald-400 text-[10px] sm:text-[11px] uppercase tracking-wider leading-tight truncate">
                <span className="sm:hidden">{activeTab.label}</span>
                <span className="hidden sm:inline">{user?.company_name || "Lokation"} · {user?.name || user?.email}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <DeltaShortcutButton />
            {locations.length > 0 && (
              <button
                onClick={() => setOrderTarget(locations.length === 1 ? locations[0] : "__pick__")}
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-xs font-bold"
                data-testid="ladmin-go-to-order-btn"
              >
                <Plus className="w-3.5 h-3.5" /> Naviger til bestillingsside
              </button>
            )}
            {/* Mobil: ikon-only logout */}
            <button onClick={logout} className="sm:hidden p-2 rounded-lg bg-slate-800/70 text-emerald-300 hover:bg-slate-700" data-testid="ladmin-logout-btn-mobile" title="Log ud">
              <LogOut className="w-4 h-4" />
            </button>
            <button onClick={logout} className="hidden sm:flex items-center gap-1.5 text-xs text-emerald-300 hover:text-white" data-testid="ladmin-logout-btn">
              <LogOut className="w-4 h-4" /> Log ud
            </button>
          </div>
        </div>
        {/* Desktop tab-bar (vandret scroll med "Mere"-dropdown) - skjult på mobil.
            Fase 18.28: På mobil bruges side-drawer (hamburger-menu) i stedet. */}
        <div className="relative hidden sm:block">
          <div className="max-w-screen-2xl mx-auto px-4 sm:px-10 flex gap-1 overflow-x-auto items-stretch scrollbar-thin">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                data-testid={`ladmin-tab-${t.id}`}
                className={`px-3.5 sm:px-4 py-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
                  tab === t.id ? "border-emerald-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
                }`}>
                <t.icon className="w-4 h-4" /> {t.label}
              </button>
            ))}
            <div className="relative">
              <button
                ref={moreRef}
                onClick={() => setMoreOpen(v => !v)}
                data-testid="ladmin-tab-more"
                className={`px-4 py-2.5 text-sm font-medium border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
                  activeMoreTab ? "border-emerald-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
                aria-haspopup="menu"
                aria-expanded={moreOpen}
              >
                <MoreHorizontal className="w-4 h-4" />
                {activeMoreTab ? activeMoreTab.label : "Mere"}
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${moreOpen ? "rotate-180" : ""}`} />
              </button>
            </div>
          </div>
        </div>
        {/* Mobile: kompakt "Naviger til bestillingsside" knap */}
        {locations.length > 0 && (
          <div className="sm:hidden max-w-screen-2xl mx-auto px-3 pb-2 pt-0.5">
            <button
              onClick={() => setOrderTarget(locations.length === 1 ? locations[0] : "__pick__")}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-bold shadow-md shadow-orange-500/20"
              data-testid="ladmin-go-to-order-btn-mobile"
            >
              <Plus className="w-4 h-4" /> Naviger til bestillingsside
            </button>
          </div>
        )}
      </header>

      {/* Mobil side-drawer (Fase 18.28) - moderne menu-liste-mønster.
          Vises kun på mobil. Åbnes af hamburger-knappen øverst til venstre. */}
      {mobileMenuOpen && createPortal(
        <div className="sm:hidden fixed inset-0 z-[60]" data-testid="ladmin-mobile-drawer">
          {/* Backdrop */}
          <div
            onClick={() => setMobileMenuOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          />
          {/* Panel - slider ind fra venstre */}
          <div className="absolute left-0 top-0 bottom-0 w-72 max-w-[85vw] bg-slate-900 border-r border-slate-700 shadow-2xl flex flex-col">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 bg-emerald-600 rounded-lg flex items-center justify-center shrink-0"><MapPin className="w-4 h-4 text-white" /></div>
                <div className="min-w-0">
                  <p className="text-white font-bold text-sm truncate">{locName}</p>
                  <p className="text-emerald-400 text-[10px] uppercase tracking-wider truncate">{user?.company_name || "Lokation"}</p>
                </div>
              </div>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 shrink-0"
                data-testid="ladmin-mobile-drawer-close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-2">
              {[...TABS, ...MORE_TABS].map(t => (
                <button
                  key={t.id}
                  onClick={() => { setTab(t.id); setMobileMenuOpen(false); }}
                  data-testid={`ladmin-drawer-tab-${t.id}`}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                    tab === t.id
                      ? "bg-emerald-500/15 text-emerald-300 border-l-4 border-emerald-500"
                      : "text-slate-300 hover:bg-slate-800 border-l-4 border-transparent"
                  }`}
                >
                  <t.icon className={`w-4 h-4 shrink-0 ${tab === t.id ? "text-emerald-400" : "text-slate-400"}`} />
                  <span className="truncate">{t.label}</span>
                </button>
              ))}
            </nav>
            <div className="px-4 py-3 border-t border-slate-700">
              <button
                onClick={() => { logout(); }}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-rose-300 text-sm font-bold"
              >
                <LogOut className="w-4 h-4" /> Log ud
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Mere-menu via createPortal - render uden for header/overflow-x-auto
          så menuen IKKE klippes. Position fastgøres til knappens bounding-
          rect ved åbning og opdateres ved resize/scroll. */}
      {moreOpen && moreRect && createPortal(
        <div
          ref={moreMenuRef}
          className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl py-1.5"
          style={{
            position: 'fixed',
            top: moreRect.bottom + 6,
            right: Math.max(8, window.innerWidth - moreRect.right),
            minWidth: 260,
            maxWidth: 320,
            zIndex: 1000,
          }}
          data-testid="ladmin-tab-more-menu"
          role="menu"
        >
          {MORE_TABS.map(m => {
            const active = tab === m.id;
            return (
              <button
                key={m.id}
                onClick={() => { setTab(m.id); setMoreOpen(false); }}
                data-testid={`ladmin-tab-${m.id}`}
                className={`w-full text-left flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                  active
                    ? "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300"
                    : "text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50"
                }`}
                role="menuitem"
              >
                <m.icon className={`w-4 h-4 flex-shrink-0 ${active ? "text-emerald-600" : "text-slate-400"}`} />
                <span className="flex-1 truncate">{m.label}</span>
                {active && <Check className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />}
              </button>
            );
          })}
        </div>,
        document.body
      )}

      <main className="max-w-screen-2xl mx-auto px-6 sm:px-10 py-5">
        {managedCodes.length === 0 ? (
          <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
            Din konto er ikke knyttet til en lokation. Kontakt din kunde-administrator.
          </div>
        ) : (
          <>
            {tab === "employees" && <EmployeesTab locations={locations} />}
            {tab === "orders" && <OrdersTab locations={locations} />}
            {tab === "fixed" && <FixedSchedulesTab locations={locations} />}
            {tab === "schedule" && <SchedulesTab locations={locations} />}
            {tab === "delivery" && <DeliveryAddressesTab locations={locations} />}
            {tab === "capacity" && <CapacityMeasuresTab locations={locations} />}
            {tab === "reports" && <ReportsTab locations={locations} />}
            {tab === "archive" && <ArchiveTab locations={locations} />}
            {tab === "partners" && <PartnersReadOnlyTab locations={locations} />}
            {tab === "received-deltas" && <ReceivedDeltasTab locations={locations} />}
            {tab === "purge" && <PermanentDeleteTab />}
          </>
        )}
      </main>

      {/* Pop-up med ventende helligdags-delta'er - vises altid når der findes
          ubehandlede notifikationer. Genåbnes ved hver page-mount så LA ikke
          kan ignorere dem. */}
      <DeltaNotificationsPopup locations={locations} />

      {orderTarget === "__pick__" && locations.length > 1 && (
        <PickLocationModal locations={locations}
          onClose={() => setOrderTarget(null)}
          onPick={(loc) => setOrderTarget(loc)} />
      )}
      {orderTarget && orderTarget !== "__pick__" && (
        <OrderRedirectModal
          location={orderTarget}
          onClose={() => setOrderTarget(null)}
          adminName={user?.name || user?.email}
        />
      )}
    </div>
  );
}

/* ============================ PICK LOCATION MODAL ============================ */
function PickLocationModal({ locations, onClose, onPick }) {
  return (
    <Modal title="Vælg lokation" onClose={onClose}>
      <p className="text-xs text-slate-500 mb-3">Du administrerer flere lokationer - vælg hvilken du vil oprette en bestilling for.</p>
      <div className="space-y-2">
        {locations.map(l => (
          <button key={l.id} onClick={() => onPick(l)}
            className="w-full text-left px-3 py-2 rounded-lg border-2 border-slate-200 dark:border-slate-700 hover:border-orange-500"
            data-testid={`pick-loc-${l.code}`}>
            <p className="font-semibold text-sm text-slate-800 dark:text-white">{l.name}</p>
            <p className="text-[11px] text-slate-500">{l.code}{l.city ? ` · ${l.city}` : ""}</p>
          </button>
        ))}
      </div>
    </Modal>
  );
}

/* ============================ ORDER REDIRECT MODAL ============================ */
function OrderRedirectModal({ location, onClose, adminName }) {
  useEffect(() => {
    try {
      sessionStorage.setItem(
        "ladmin_order_loc",
        JSON.stringify({ code: location.code || location.location_code, name: location.name }),
      );
      window.location.reload();
    } catch (_) { /* ignore */ }
  }, [location]);
  return (
    <Modal title="Åbner bestillingsside …" onClose={onClose}>
      <p className="text-sm text-slate-500">Omdirigerer dig til bestillingssiden for <strong>{location.name}</strong>…</p>
      <p className="text-[11px] text-slate-400 mt-2">Bruger: {adminName}</p>
    </Modal>
  );
}

/* ============================ EMPLOYEES TAB ============================ */
function EmployeesTab({ locations = [] }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);   // default filter = aktive only
  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);    // direct hard-delete from list
  const [deletingId, setDeletingId] = useState(null);
  const [locFilter, setLocFilter] = useState("all");          // "all" or specific code
  // Brugerkrav 2026-06-15 (runde 9): Multi-lokation medarbejder.
  // Felt `location_codes` (array) erstatter (eller komplementerer) det enkelte
  // `location_code`. Backend gemmer det i `assigned_plads_ids`.
  const empty = { name: "", email: "", phone: "", employment_date: "", location_codes: [] };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [resendingId, setResendingId] = useState(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/org/users`); setItems(data || []); }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchItems(); }, [fetchItems]);

  const filtered = useMemo(
    () => items.filter(u => {
      if (!showInactive && u.active === false) return false;
      if (locFilter === "all") return true;
      // Filter på primary location_code ELLER assigned_plads_ids
      const codes = new Set([u.location_code, ...(u.assigned_plads_ids || [])].filter(Boolean));
      return codes.has(locFilter);
    }),
    [items, showInactive, locFilter],
  );

  const locName = (code) => {
    const m = locations.find(l => l.code === code || l.location_code === code);
    return m?.name || code;
  };

  // Default = ALLE LA's pladser hvis LA kun har 1, ellers ingen (user-vælg)
  const defaultLocCodes = locations.length === 1
    ? [locations[0].code || locations[0].location_code]
    : [];

  const openCreate = () => {
    setEditing(null);
    setForm({ ...empty, location_codes: defaultLocCodes });
    setShowForm(true);
  };
  const openEdit = (u) => {
    setEditing(u);
    // Saml location_code + assigned_plads_ids til ét sæt valgte koder
    const existing = Array.from(new Set([
      u.location_code,
      ...(u.assigned_plads_ids || []),
    ].filter(Boolean)));
    setForm({
      name: u.name || "", email: u.email || "",
      phone: u.phone || "", employment_date: u.employment_date || "",
      location_codes: existing.length > 0 ? existing : defaultLocCodes,
    });
    setShowForm(true);
  };

  const toggleLocationCode = (code) => {
    setForm(prev => {
      const set = new Set(prev.location_codes || []);
      if (set.has(code)) set.delete(code); else set.add(code);
      return { ...prev, location_codes: Array.from(set) };
    });
  };

  const save = async () => {
    // Fase 15.55b (2026-02-22): Navn + email obligatoriske (begge create + edit).
    if (!form.name.trim()) { toast.error("Navn er påkrævet"); return; }
    if (!form.email.trim()) { toast.error("Email er påkrævet"); return; }
    if (!form.location_codes || form.location_codes.length === 0) {
      toast.error("Vælg mindst én lokation");
      return;
    }
    setSaving(true);
    try {
      const primaryCode = form.location_codes[0];
      if (editing) {
        await axios.put(`${API}/org/users/${editing.id}`, {
          name: form.name.trim(),
          email: form.email.trim().toLowerCase(),
          phone: form.phone.trim(),
          employment_date: form.employment_date.trim(),
          location_codes: form.location_codes,
          location_code: primaryCode,
        });
        toast.success("Medarbejder opdateret");
      } else {
        await axios.post(`${API}/org/users`, {
          name: form.name.trim(),
          email: form.email.trim().toLowerCase(),
          phone: form.phone.trim(),
          employment_date: form.employment_date.trim(),
          role: "order",
          location_code: primaryCode,
          location_codes: form.location_codes,
          send_invitation: true,
        });
        toast.success(
          form.location_codes.length > 1
            ? `Invitation sendt - medarbejderen har adgang til ${form.location_codes.length} lokationer`
            : "Invitation sendt til medarbejder"
        );
      }
      setShowForm(false); setForm(empty); fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const toggleActive = async (u) => {
    const next = !(u.active !== false);
    try {
      await axios.put(`${API}/org/users/${u.id}`, { active: next });
      toast.success(next ? "Aktiveret" : "Inaktiveret");
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const resend = async (u) => {
    setResendingId(u.id);
    try {
      await axios.post(`${API}/org/users/${u.id}/resend-invitation`);
      toast.success(`Invitation gensendt til ${u.email}`);
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setResendingId(null); }
  };

  const fullDelete = async () => {
    if (!deleteTarget) return;
    setDeletingId(deleteTarget.id);
    try {
      await axios.delete(`${API}/org/users/${deleteTarget.id}`);
      toast.success("Medarbejder slettet permanent");
      setDeleteTarget(null);
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setDeletingId(null); }
  };

  // Brugerkrav 2026-06-15 (runde 11): Multi-lokation medarbejdere skal vises
  // som ÉN række med alle tildelte lokationer som chips i sin egen kolonne -
  // IKKE duplikeret under hver lokation. Derfor er den gamle grouping fjernet
  // til fordel for en flad tabel med en dedikeret "Lokationer"-kolonne.

  // Reusable row renderer
  const renderRow = (u) => {
    const isPending = u.invitation_status === "pending";
    const isInactive = u.active === false;
    // Brugerkrav 2026-06-15 (runde 10): Vis ALLE lokationer medarbejderen har
    // adgang til - som chips - så LA kan se det med ét blik.
    const allCodes = Array.from(new Set([
      u.location_code,
      ...(u.assigned_plads_ids || []),
    ].filter(Boolean)));
    return (
      <tr key={u.id} className={isInactive ? "opacity-60" : ""} data-testid={`employee-row-${u.id}`}>
        <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">{u.name || "-"}</td>
        <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{u.email}</td>
        {locations.length > 1 && (
          <td className="px-4 py-3 text-slate-500 text-xs" data-testid={`employee-locations-${u.id}`}>
            {allCodes.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {allCodes.map(c => (
                  <span key={c} className="inline-block px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 text-[10px] font-semibold whitespace-nowrap">
                    {locName(c)}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-slate-300"></span>
            )}
          </td>
        )}
        <td className="px-4 py-3 text-slate-500">{u.phone || ""}</td>
        <td className="px-4 py-3 text-slate-500">{u.employment_date || ""}</td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
            isInactive
              ? "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
              : isPending
                ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
                : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
          }`} data-testid={`employee-status-${u.id}`}>
            {isInactive ? "Inaktiv" : isPending ? <><Clock className="w-3 h-3" /> Afventer</> : <><CheckCircle2 className="w-3 h-3" /> Aktiv</>}
          </span>
        </td>
        <td className="px-4 py-3">
          <button onClick={() => toggleActive(u)}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-bold ${
              isInactive
                ? "bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700"
                : "bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/30 text-amber-700"
            }`}
            data-testid={`toggle-employee-${u.id}`}>
            {isInactive ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            {isInactive ? "Aktivér" : "Inaktivér"}
          </button>
        </td>
        <td className="px-4 py-3 text-right whitespace-nowrap">
          <button onClick={() => openEdit(u)}
            className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 hover:text-slate-700 dark:hover:text-slate-200"
            title="Rediger"
            data-testid={`edit-employee-${u.id}`}>
            <Edit2 className="w-4 h-4" />
          </button>
          {isPending && !isInactive && (
            <button onClick={() => resend(u)} disabled={resendingId === u.id}
              className="p-1.5 rounded hover:bg-orange-50 dark:hover:bg-orange-950/30 text-slate-500 hover:text-orange-600 disabled:opacity-50"
              title="Gensend invitation"
              data-testid={`resend-employee-${u.id}`}>
              {resendingId === u.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
            </button>
          )}
          {/* Permanent delete is intentionally hidden from this tab - use
              the "Slet permanent" tab to perform GDPR-style purges. */}
        </td>
      </tr>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-sm text-slate-500">Tilføj og rediger medarbejdere for {locations.length > 1 ? "dine lokationer" : "denne lokation"}. Medarbejdere kan logge ind og bestille afhentning.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {locations.length > 1 && (
            <select value={locFilter} onChange={e => setLocFilter(e.target.value)}
              className="px-3 py-2 rounded-lg text-xs font-semibold border-2 bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
              data-testid="emp-loc-filter">
              <option value="all">Alle lokationer</option>
              {locations.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          )}
          <button onClick={() => setShowInactive(s => !s)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border-2 ${
              showInactive
                ? "bg-slate-100 dark:bg-slate-700 border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200"
                : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-500"
            }`}
            data-testid="toggle-show-inactive">
            <Filter className="w-3.5 h-3.5" />
            {showInactive ? "Vis kun aktive" : "Vis også inaktive"}
          </button>
          <button onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold"
            data-testid="add-employee-btn">
            <Plus className="w-4 h-4" /> Ny medarbejder
          </button>
        </div>
      </div>

      {/* Grouped (multi-location) or flat (single-location) */}
      {loading ? (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl py-10 text-center">
          <Loader2 className="w-5 h-5 animate-spin inline text-slate-400" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl py-10 text-center text-slate-400 text-sm">
          {items.length === 0 ? "Ingen medarbejdere endnu" : "Ingen aktive medarbejdere - tryk \u201CVis også inaktive\u201D for at se de øvrige."}
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <EmployeesTable showLoc={locations.length > 1} rows={filtered} renderRow={renderRow} />
          </div>
        </div>
      )}

      {showForm && (
        <Modal title={editing ? "Rediger medarbejder" : "Ny medarbejder"} onClose={() => setShowForm(false)}>
          {locations.length > 1 ? (
            // Brugerkrav 2026-06-15 (runde 9): Multi-select lokationer.
            // Kun LA's egne pladser vises som valg.
            <Field label={`Lokation(er) * - ${form.location_codes?.length || 0} valgt`}>
              <div className="space-y-1 max-h-44 overflow-y-auto border border-slate-300 dark:border-slate-600 rounded-lg p-2 bg-white dark:bg-slate-800">
                {locations.map(l => {
                  const code = l.code || l.location_code;
                  const on = (form.location_codes || []).includes(code);
                  return (
                    <label key={code}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer ${
                        on
                          ? "bg-blue-50 dark:bg-blue-950/30 text-blue-900 dark:text-blue-100"
                          : "hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-700 dark:text-slate-200"
                      }`}>
                      <input type="checkbox" checked={on} onChange={() => toggleLocationCode(code)}
                        className="w-4 h-4 accent-blue-500"
                        data-testid={`emp-loc-toggle-${code}`} />
                      <span className="flex-1">{l.name} <span className="text-[11px] text-slate-400">· {code}</span></span>
                    </label>
                  );
                })}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Medarbejderen vil kunne vælge mellem de afkrydsede lokationer ved login. Vælg mindst én.
              </p>
            </Field>
          ) : (
            // Kun 1 lokation managed → auto-valgt
            <div className="hidden">
              {/* Sikrer at form.location_codes er sat selvom UI'et er skjult */}
            </div>
          )}
          <Field label="Navn *">
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              className={INPUT} data-testid="emp-name-input" />
          </Field>
          <Field label="Email *">
            <input value={form.email}
              type="text" inputMode="email"
              onChange={e => setForm({ ...form, email: e.target.value })}
              className={INPUT} data-testid="emp-email-input" />
            {editing && <p className="text-[11px] text-slate-400 mt-1">Hvis du ændrer e-mailen, skal medarbejderen bruge den nye til at logge ind.</p>}
          </Field>
          <Field label="Telefon">
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}
              className={INPUT} data-testid="emp-phone-input" />
          </Field>
          <Field label="Ansættelsesdato">
            <input type="date" value={form.employment_date}
              onChange={e => setForm({ ...form, employment_date: e.target.value })}
              className={INPUT} data-testid="emp-employment-date-input" />
          </Field>
          {!editing && (
            <p className="text-xs text-slate-500 -mt-1 mb-2">
              Medarbejderen modtager en invitations-mail med et 72-timers link, hvor de selv vælger deres adgangskode.
            </p>
          )}
          <FormButtons onCancel={() => setShowForm(false)} onSave={save} saving={saving} />
        </Modal>
      )}

      {deleteTarget && (
        <ConfirmDeleteModal
          title="Slet medarbejder fuldt?"
          message={
            <>
              <p className="text-slate-700 dark:text-slate-200 font-medium">{deleteTarget.name || deleteTarget.email}</p>
              <p className="text-xs text-slate-500 mt-1">{deleteTarget.email}</p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-3">
                Denne handling sletter medarbejderen <strong>permanent</strong> - også selvom de er aktive. Alle invitations-links fjernes også. Dette kan ikke fortrydes.
              </p>
            </>
          }
          onConfirm={fullDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}

// Shared employees table renderer
function EmployeesTable({ rows, renderRow, showLoc }) {
  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        <tr>
          <th className="px-4 py-2.5">Navn</th>
          <th className="px-4 py-2.5">Email</th>
          {showLoc && <th className="px-4 py-2.5">Lokationer</th>}
          <th className="px-4 py-2.5">Tlf.</th>
          <th className="px-4 py-2.5">Ansat fra</th>
          <th className="px-4 py-2.5">Status</th>
          <th className="px-4 py-2.5">Aktiv</th>
          <th className="px-4 py-2.5 text-right">Handlinger</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
        {rows.map(renderRow)}
      </tbody>
    </table>
  );
}

/* ============================ ORDERS DASHBOARD ============================ */
function OrdersTab({ locations = [] }) {
  const codes = useMemo(
    () => locations.map(l => l.code || l.location_code).filter(Boolean),
    [locations],
  );
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all"); // all | afventer | accepteret | afhentet
  // Fase 15.53 (2026-02-22): Multi-location filter - tom Set = "Alle".
  // Tidligere var det en enkelt string ("all" / kode), nu kan brugeren
  // vælge flere lokationer på samme tid.
  const [selectedLocs, setSelectedLocs] = useState(() => new Set());
  const [locDropdownOpen, setLocDropdownOpen] = useState(false);
  // Fase 15.54 (2026-02-22): Date preset - "I dag" (default) / "Denne uge"
  // (man-søn i indeværende uge) / "Brugerdefineret" (date range).
  // "Måned"/"År" eksisterer som filtre nedenfor men kan kombineres med presets.
  const [datePreset, setDatePreset] = useState("today");  // today | week | custom | all
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [yearFilter, setYearFilter] = useState("all");
  const [monthFilter, setMonthFilter] = useState("all");
  const [materialFilter, setMaterialFilter] = useState("all");
  const [containerFilter, setContainerFilter] = useState("all");
  const [employeeFilter, setEmployeeFilter] = useState("all");
  const [searchText, setSearchText] = useState("");
  // Fase 15.54: Paginering - kun vise N rækker ad gangen + Vis mere-knap.
  const PAGE_SIZE = 50;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const fetchOrders = useCallback(async () => {
    if (codes.length === 0) { setOrders([]); setLoading(false); return; }
    setLoading(true);
    try {
      const results = await Promise.all(
        codes.map(c => axios.get(`${API}/container-orders/by-location/${c}`).then(r => r.data || [])),
      );
      setOrders(results.flat());
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [codes]);
  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  const locName = (code) => locations.find(l => l.code === code || l.location_code === code)?.name || code;

  // Helper: extract YYYY-MM-DD from an order (always uses order_date with
  // fallback to created_at when order_date mangler).
  const orderDateOf = useCallback((o) => {
    return o.order_date || (o.created_at || "").slice(0, 10);
  }, []);

  // Fase 15.54 (2026-02-22): Beregn [from, to]-interval for date-preset.
  const dateRange = useMemo(() => {
    const today = new Date();
    const ymd = (d) => d.toISOString().slice(0, 10);
    if (datePreset === "today") {
      const t = ymd(today);
      return { from: t, to: t };
    }
    if (datePreset === "week") {
      // Mandag = 1 ... søndag = 0 (JS getDay). Vi vil have mandag som start.
      const d = new Date(today);
      const dow = (d.getDay() + 6) % 7;  // 0=man ... 6=søn
      const monday = new Date(d); monday.setDate(d.getDate() - dow);
      const sunday = new Date(monday); sunday.setDate(monday.getDate() + 6);
      return { from: ymd(monday), to: ymd(sunday) };
    }
    if (datePreset === "custom") {
      return { from: customStart || "", to: customEnd || "" };
    }
    return { from: "", to: "" };
  }, [datePreset, customStart, customEnd]);

  // Distinct values for filter dropdowns derived from the loaded orders.
  const distinct = useMemo(() => {
    const years = new Set();
    const materials = new Set();
    const containers = new Set();
    const employees = new Set();
    orders.forEach(o => {
      const ds = orderDateOf(o);
      if (ds && ds.length >= 4) years.add(ds.slice(0, 4));
      if (o.material) materials.add(o.material);
      if (o.container_number) containers.add(o.container_number);
      const emp = o.created_by_name || o.created_by_email;
      if (emp) employees.add(emp);
    });
    return {
      years: Array.from(years).sort().reverse(),
      materials: Array.from(materials).sort(),
      containers: Array.from(containers).sort(),
      employees: Array.from(employees).sort(),
    };
  }, [orders, orderDateOf]);

  const filtered = useMemo(
    () => orders.filter(o => {
      if (statusFilter !== "all" && (o.status_label || "afventer") !== statusFilter) return false;
      if (selectedLocs.size > 0 && !selectedLocs.has(o.location_code)) return false;
      const ds = orderDateOf(o);
      // Fase 15.54: Date-preset interval-filter.
      if (dateRange.from && ds < dateRange.from) return false;
      if (dateRange.to && ds > dateRange.to) return false;
      if (yearFilter !== "all" && !ds.startsWith(yearFilter)) return false;
      if (monthFilter !== "all" && ds.slice(5, 7) !== monthFilter) return false;
      if (materialFilter !== "all" && o.material !== materialFilter) return false;
      if (containerFilter !== "all" && o.container_number !== containerFilter) return false;
      if (employeeFilter !== "all") {
        const emp = o.created_by_name || o.created_by_email || "";
        if (emp !== employeeFilter) return false;
      }
      if (searchText.trim()) {
        const q = searchText.trim().toLowerCase();
        const hay = [o.customer_address, o.container_id_resolved, o.material,
                     o.container_number, o.created_by_name, o.created_by_email,
                     o.comment, o.id].filter(Boolean).join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    }),
    [orders, statusFilter, selectedLocs, yearFilter, monthFilter, materialFilter,
     containerFilter, employeeFilter, searchText, orderDateOf, dateRange]
  );

  // Fase 15.54: Reset visible count when filtered set changes
  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [statusFilter, selectedLocs, yearFilter, monthFilter, materialFilter, containerFilter, employeeFilter, searchText, datePreset, customStart, customEnd]);

  const resetFilters = () => {
    setStatusFilter("all"); setSelectedLocs(new Set());
    setDatePreset("today"); setCustomStart(""); setCustomEnd("");
    setYearFilter("all"); setMonthFilter("all");
    setMaterialFilter("all"); setContainerFilter("all"); setEmployeeFilter("all");
    setSearchText("");
  };
  const activeFilterCount = [statusFilter, yearFilter, monthFilter,
                             materialFilter, containerFilter, employeeFilter].filter(v => v !== "all").length
                            + (searchText.trim() ? 1 : 0)
                            + (selectedLocs.size > 0 ? 1 : 0)
                            + (datePreset !== "today" ? 1 : 0);

  const summary = useMemo(() => {
    const s = { afventer: 0, accepteret: 0, afhentet: 0, annulleret: 0 };
    orders.forEach(o => { s[o.status_label || "afventer"] = (s[o.status_label || "afventer"] || 0) + 1; });
    return s;
  }, [orders]);

  const STATUS_META = {
    afventer: { label: "Afventer", cls: "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300", Icon: Clock },
    accepteret: { label: "Accepteret", cls: "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300", Icon: Truck },
    afhentet: { label: "Afhentet", cls: "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300", Icon: CheckCircle2 },
    annulleret: { label: "Annulleret", cls: "bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-300", Icon: X },
    // Fase 15.51 (2026-02-22): Estimat er ikke en rigtig bestilling - vis N/A.
    estimat: { label: "N/A", cls: "bg-slate-100 dark:bg-slate-900/30 text-slate-500 dark:text-slate-400 italic", Icon: Clock },
    // Fase 15.52 (2026-02-22): Ikke-gennemført tur (chauffør markerede tur
    // som ikke-gennemførbar - afventer logistik-admin gen-aktivering).
    ikke_gennemfoert: { label: "Ikke gennemført", cls: "bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300", Icon: AlertTriangle },
  };

  return (
    <div className="space-y-4">
      {/* Status summary tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="orders-summary">
        {["afventer", "accepteret", "afhentet"].map(k => {
          const m = STATUS_META[k];
          const Icon = m.Icon;
          return (
            <button key={k} onClick={() => setStatusFilter(statusFilter === k ? "all" : k)}
              className={`text-left p-3 rounded-xl border-2 ${
                statusFilter === k
                  ? "border-emerald-500 bg-emerald-50/40 dark:bg-emerald-950/20"
                  : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
              }`}
              data-testid={`orders-summary-${k}`}>
              <div className="flex items-center justify-between">
                <Icon className="w-4 h-4 text-slate-400" />
                <span className="text-2xl font-heading font-bold text-slate-900 dark:text-white">{summary[k] || 0}</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{m.label}</p>
            </button>
          );
        })}
        <button onClick={() => setStatusFilter("all")}
          className={`text-left p-3 rounded-xl border-2 ${
            statusFilter === "all"
              ? "border-emerald-500 bg-emerald-50/40 dark:bg-emerald-950/20"
              : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
          }`}
          data-testid="orders-summary-all">
          <div className="flex items-center justify-between">
            <Activity className="w-4 h-4 text-slate-400" />
            <span className="text-2xl font-heading font-bold text-slate-900 dark:text-white">{orders.length}</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">I alt</p>
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 -mt-2">
        <p className="text-xs text-slate-500">
          Tabellen viser bestillinger for dine pladser (multi-tenant isoleret).
        </p>
        {locations.length > 1 && (
          <div className="ml-auto relative" data-testid="orders-loc-multiselect-wrapper">
            <button
              type="button"
              onClick={() => setLocDropdownOpen(!locDropdownOpen)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold border-2 bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 flex items-center gap-2 hover:border-emerald-400"
              data-testid="orders-loc-multiselect-toggle"
            >
              <Filter className="w-3 h-3" />
              {selectedLocs.size === 0
                ? `Alle lokationer (${locations.length})`
                : `${selectedLocs.size} af ${locations.length} valgt`}
              <ChevronDown className={`w-3 h-3 transition-transform ${locDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {locDropdownOpen && (
              <div className="absolute right-0 mt-1 w-72 max-h-80 overflow-y-auto bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-20 p-2"
                   data-testid="orders-loc-multiselect-panel">
                <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-slate-200 dark:border-slate-700">
                  <button onClick={() => setSelectedLocs(new Set(locations.map(l => l.code)))}
                    className="text-[11px] font-bold text-emerald-600 hover:text-emerald-700"
                    data-testid="orders-loc-select-all">
                    Vælg alle
                  </button>
                  <button onClick={() => setSelectedLocs(new Set())}
                    className="text-[11px] font-bold text-slate-500 hover:text-slate-700"
                    data-testid="orders-loc-clear-all">
                    Ryd alle
                  </button>
                </div>
                {locations.map(l => {
                  const checked = selectedLocs.has(l.code);
                  return (
                    <label key={l.code}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700/50 cursor-pointer"
                      data-testid={`orders-loc-option-${l.code}`}>
                      <input type="checkbox" checked={checked} className="accent-emerald-500"
                        onChange={() => {
                          const next = new Set(selectedLocs);
                          if (checked) next.delete(l.code); else next.add(l.code);
                          setSelectedLocs(next);
                        }} />
                      <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate flex-1">
                        {l.name} <span className="text-slate-400 font-normal">({l.code})</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Advanced filters - added iteration 17 */}
      <div className="bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded-xl p-3 space-y-2"
        data-testid="orders-advanced-filters">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5" /> Filtrér bestillinger
            {activeFilterCount > 0 && (
              <span className="bg-emerald-600 text-white px-1.5 py-0.5 rounded-full text-[10px]">
                {activeFilterCount} aktiv{activeFilterCount === 1 ? "" : "e"}
              </span>
            )}
          </p>
          {activeFilterCount > 0 && (
            <button onClick={resetFilters}
              className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 inline-flex items-center gap-1"
              data-testid="orders-reset-filters">
              <X className="w-3 h-3" /> Nulstil
            </button>
          )}
        </div>
        {/* Fase 15.54 (2026-02-22): Dato-preset bar - I dag / Denne uge /
            Brugerdefineret / Alle. Default = I dag for at gøre listen
            håndterbar. Brugerdefineret viser to date-pickere. */}
        <div className="flex flex-wrap items-center gap-1.5 mb-2">
          {[
            { id: "today", label: "I dag" },
            { id: "week",  label: "Denne uge" },
            { id: "custom", label: "Brugerdefineret" },
            { id: "all",   label: "Alle" },
          ].map(p => (
            <button key={p.id}
              onClick={() => setDatePreset(p.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold ${
                datePreset === p.id
                  ? "bg-emerald-600 text-white"
                  : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-emerald-400"
              }`}
              data-testid={`orders-date-preset-${p.id}`}>
              {p.label}
            </button>
          ))}
          {datePreset === "custom" && (
            <>
              <input type="date" value={customStart} onChange={e => setCustomStart(e.target.value)}
                className="px-2 py-1 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
                data-testid="orders-custom-start" />
              <span className="text-xs text-slate-500">→</span>
              <input type="date" value={customEnd} onChange={e => setCustomEnd(e.target.value)}
                className="px-2 py-1 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
                data-testid="orders-custom-end" />
            </>
          )}
          <span className="text-[10px] text-slate-500 ml-auto" data-testid="orders-date-range-info">
            {dateRange.from && dateRange.to
              ? (dateRange.from === dateRange.to
                  ? dateRange.from
                  : `${dateRange.from} → ${dateRange.to}`)
              : "Alle datoer"}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          <select value={yearFilter} onChange={e => setYearFilter(e.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="orders-year-filter">
            <option value="all">Alle år</option>
            {distinct.years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={monthFilter} onChange={e => setMonthFilter(e.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="orders-month-filter">
            <option value="all">Alle måneder</option>
            <option value="01">Januar</option><option value="02">Februar</option>
            <option value="03">Marts</option><option value="04">April</option>
            <option value="05">Maj</option><option value="06">Juni</option>
            <option value="07">Juli</option><option value="08">August</option>
            <option value="09">September</option><option value="10">Oktober</option>
            <option value="11">November</option><option value="12">December</option>
          </select>
          <select value={materialFilter} onChange={e => setMaterialFilter(e.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="orders-material-filter">
            <option value="all">Alle materialer</option>
            {distinct.materials.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={containerFilter} onChange={e => setContainerFilter(e.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="orders-container-filter">
            <option value="all">Alle containere</option>
            {distinct.containers.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={employeeFilter} onChange={e => setEmployeeFilter(e.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-semibold border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            data-testid="orders-employee-filter">
            <option value="all">Alle medarbejdere</option>
            {distinct.employees.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
          <div className="relative col-span-2">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input value={searchText} onChange={e => setSearchText(e.target.value)}
              placeholder="Søg i adresse, container, kommentar…"
              className="w-full pl-7 pr-2 py-1.5 rounded-lg text-xs border bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
              data-testid="orders-search-input" />
          </div>
        </div>
        <p className="text-[10px] text-slate-400 mt-1" data-testid="orders-count-summary">
          {/* Fase 15.54 (2026-02-22): Tæller af filterede vs totale ordrer +
              note om at kun de første N vises (paginering). */}
          Viser {Math.min(visibleCount, filtered.length)} af {filtered.length} filtrerede
          {filtered.length !== orders.length && ` (af i alt ${orders.length})`}
        </p>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : filtered.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen bestillinger her endnu</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Bestilt</th>
                  {locations.length > 1 && <th className="px-4 py-2.5">Lokation</th>}
                  <th className="px-4 py-2.5">Materiale</th>
                  <th className="px-4 py-2.5">Container</th>
                  <th className="px-4 py-2.5">Container-nummer</th>
                  <th className="px-4 py-2.5">Adresse</th>
                  <th className="px-4 py-2.5">Bestilt af</th>
                  <th className="px-4 py-2.5">Kommentar</th>
                  {/* Fase 15.53 (2026-02-22): Vægt + CO2 - kun relevant for
                      normal + løs afhentning. Andre opgavetyper og estimater
                      viser tankestreg. */}
                  <th className="px-4 py-2.5 text-right">Vægt (kg)</th>
                  <th className="px-4 py-2.5 text-right">CO2 (kg)</th>
                  <th className="px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {filtered.slice(0, visibleCount).map(o => {
                  // Fase 15.53 (2026-02-22): Defensive fallback hvis backend
                  // returnerer en ny status_label vi endnu ikke har mappet.
                  const meta = STATUS_META[o.status_label || "afventer"] || STATUS_META.afventer;
                  const Icon = meta.Icon;
                  // container_id_resolved comes from the backend enrichment -
                  // it's the per-order override if set, else the saved default.
                  const containerNo = (o.container_id_resolved || o.container_id_override || "").trim();
                  return (
                    <tr key={o.id} data-testid={`order-row-${o.id}`}>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                        <Calendar className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                        {o.order_date || (o.created_at || "").slice(0, 10)}
                        <div className="text-[10px] text-slate-400">{(o.created_at || "").slice(11, 16)}</div>
                      </td>
                      {locations.length > 1 && (
                        <td className="px-4 py-3 text-emerald-700 dark:text-emerald-400 text-xs font-semibold">{locName(o.location_code)}</td>
                      )}
                      <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">{o.material}</td>
                      <td className="px-4 py-3 text-slate-500">
                        {/* Fase 15.54 (2026-02-22): "Container"-kolonne viser
                            opgavetypen i klartekst - IKKE den interne
                            container-template ("Container 1/2/3" osv.).
                            Det matcher hvad chauffør og kunde ser i UI'en. */}
                        {(() => {
                          const tt = o.tour_type || "normal";
                          if (tt === "loes_afhentning") return <span className="text-amber-700 dark:text-amber-300 font-semibold">Løs afhentning</span>;
                          if (tt === "flyt") return "Flyt container";
                          if (tt === "vaerksted") return "Til værksted";
                          if (tt === "afhent_vaerksted") return "Afhent fra værksted";
                          if (tt === "estimat") return <span className="italic text-slate-400">Estimat</span>;
                          return "Almindelig afhentning";
                        })()}
                      </td>
                      <td className="px-4 py-3 text-slate-900 dark:text-white font-mono" data-testid={`order-container-id-${o.id}`}>
                        {containerNo || <span className="text-slate-400 italic font-sans">-</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-500 max-w-xs truncate">{o.customer_address || "-"}</td>
                      <td className="px-4 py-3 text-slate-500">
                        {/* 2026-10-19: Bestilt af logistikfirmaet på jeres vegne */}
                        {o.on_behalf_company_name ? (
                          <span data-testid={`order-on-behalf-${o.id}`}><span className="font-semibold text-sky-700 dark:text-sky-300">{o.on_behalf_company_name}</span> for jer{o.requested_by ? <span className="block text-xs">{o.requested_by}</span> : null}</span>
                        ) : (o.created_by_name || o.created_by_email || "-")}
                        {o.status === "cancelled" && (o.cancel_reason || o.cancelled_by_logistics) && (
                          <span className="block text-xs text-slate-400">Annulleret{o.cancelled_by_logistics ? " af logistikfirmaet" : ""}{o.cancel_reason ? `: ${o.cancel_reason}` : ""}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300 max-w-xs"
                          data-testid={`order-comment-${o.id}`}>
                        {o.comment ? (
                          <span className="text-xs italic line-clamp-2" title={o.comment}>
                            {o.comment}
                          </span>
                        ) : (
                          <span className="text-slate-400 text-xs">-</span>
                        )}
                      </td>
                      {/* Fase 15.53 (2026-02-22): Vægt + CO2 - kun for normal +
                          løs afhentning. Andre typer + estimater = tankestreg. */}
                      <td className="px-4 py-3 text-right font-mono tabular-nums whitespace-nowrap" data-testid={`order-weight-${o.id}`}>
                        {(["normal", "loes_afhentning"].includes(o.tour_type || "normal") && o.weight_kg > 0)
                          ? <span className="font-semibold text-slate-800 dark:text-slate-100">{Number(o.weight_kg).toLocaleString("da-DK", { maximumFractionDigits: 1 })}</span>
                          : <span className="text-slate-400">-</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums whitespace-nowrap" data-testid={`order-co2-${o.id}`}>
                        {(["normal", "loes_afhentning"].includes(o.tour_type || "normal") && o.co2_kg > 0)
                          ? <span className="font-semibold text-emerald-600 dark:text-emerald-400">{Number(o.co2_kg).toLocaleString("da-DK", { maximumFractionDigits: 1 })}</span>
                          : <span className="text-slate-400">-</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${meta.cls}`}>
                          <Icon className="w-3 h-3" /> {meta.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {/* Fase 15.54 (2026-02-22): "Vis mere"-knap når der er flere
                ordrer end vist (paginering). */}
            {filtered.length > visibleCount && (
              <div className="p-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 text-center">
                <button
                  onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
                  className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                  data-testid="orders-show-more-btn"
                >
                  Vis {Math.min(PAGE_SIZE, filtered.length - visibleCount)} flere - {filtered.length - visibleCount} tilbage
                </button>
                <button
                  onClick={() => setVisibleCount(filtered.length)}
                  className="ml-2 px-4 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold"
                  data-testid="orders-show-all-btn"
                >
                  Vis alle
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
function PartnersReadOnlyTab({ locations = [] }) {
  return (
    <div className="space-y-3" data-testid="partners-readonly-tab">
      <p className="text-sm text-slate-500">
        Logistik-partnere som din kunde-administrator har tildelt {locations.length > 1 ? "hver af dine lokationer" : "denne lokation"}. Denne liste er <strong>kun til information</strong> - du kan ikke tilføje eller fjerne partnere her.
      </p>
      {locations.map(loc => {
        const partners = loc.logistics_partners || [];
        return (
          <div key={loc.id || loc.code} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden" data-testid={`partners-loc-${loc.code}`}>
            <div className="px-4 py-2 bg-slate-50 dark:bg-slate-900/40 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-emerald-600" />
              <p className="text-sm font-bold text-slate-800 dark:text-white">{loc.name}</p>
              <span className="text-[10px] uppercase tracking-wider text-slate-400 ml-auto">{partners.length} partner{partners.length === 1 ? "" : "e"}</span>
            </div>
            {partners.length === 0 ? (
              <div className="py-6 text-center text-slate-400 text-sm">Ingen logistik-partnere tilknyttet endnu</div>
            ) : partners.map(p => (
              <div key={p.id} className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0" data-testid={`partner-readonly-${loc.code}-${p.id}`}>
                <div className="w-9 h-9 rounded-lg bg-blue-100 dark:bg-blue-950/40 text-blue-600 flex items-center justify-center">
                  <Truck className="w-5 h-5" />
                </div>
                <p className="font-semibold text-sm text-slate-800 dark:text-white">{p.name}</p>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/* ============================ PERMANENT DELETE ============================ */
function PermanentDeleteTab({ code }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [confirm, setConfirm] = useState(null); // { id, email }

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/org/users`); setItems((data || []).filter(u => u.active === false)); }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchItems(); }, [fetchItems]);

  const purge = async () => {
    if (!confirm) return;
    const { id } = confirm;
    setDeletingId(id);
    setConfirm(null);
    try {
      await axios.delete(`${API}/org/users/${id}`);
      toast.success("Medarbejder slettet permanent");
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setDeletingId(null); }
  };

  return (
    <div className="space-y-3" data-testid="purge-tab">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold">Permanent sletning</p>
          <p className="text-xs">Kun medarbejdere der allerede er <strong>inaktive</strong> kan slettes permanent her. Inaktivér først på fanen "Medarbejdere".</p>
        </div>
      </div>
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen inaktive medarbejdere</div>
        ) : items.map(u => (
          <div key={u.id} className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0" data-testid={`purge-row-${u.id}`}>
            <div>
              <p className="font-semibold text-sm text-slate-800 dark:text-white">{u.name || u.email}</p>
              <p className="text-xs text-slate-400">{u.email}{u.employment_date ? ` · Ansat fra ${u.employment_date}` : ""}</p>
            </div>
            <button onClick={() => setConfirm({ id: u.id, email: u.email, name: u.name })} disabled={deletingId === u.id}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              data-testid={`purge-employee-${u.id}`}>
              {deletingId === u.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              Slet permanent
            </button>
          </div>
        ))}
      </div>

      {confirm && (
        <ConfirmDeleteModal
          title="Slet medarbejder permanent?"
          message={
            <>
              <p className="text-slate-700 dark:text-slate-200 font-medium">{confirm.name || confirm.email}</p>
              <p className="text-xs text-slate-500 mt-1">{confirm.email}</p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-3">
                Dette kan <strong>IKKE</strong> fortrydes. Alle invitations-links til denne bruger fjernes også.
              </p>
            </>
          }
          onConfirm={purge}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}

/* ---------- Inline confirm modal (no window.confirm, fixes blocked dialogs) ---------- */
function ConfirmDeleteModal({ title, message, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="confirm-delete-modal">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div className="p-6">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-950/40 ring-8 ring-red-50 dark:ring-red-950/20 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-600" />
          </div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-white text-center mb-2">{title}</h3>
          <div className="text-sm text-center">{message}</div>
        </div>
        <div className="flex gap-3 p-4 bg-slate-50 dark:bg-slate-900/40">
          <button onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600"
            data-testid="confirm-cancel-btn">
            Annuller
          </button>
          <button onClick={onConfirm}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-red-600 hover:bg-red-700"
            data-testid="confirm-delete-btn">
            Slet permanent
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- small shared UI ---------- */
const INPUT = "w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-emerald-500 outline-none disabled:opacity-60";
function Field({ label, children }) {
  return (<div className="mb-3"><label className="block text-xs font-semibold text-slate-500 mb-1">{label}</label>{children}</div>);
}
function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full p-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700"><X className="w-4 h-4 text-slate-500" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
function FormButtons({ onCancel, onSave, saving }) {
  return (
    <div className="flex gap-2 justify-end mt-4">
      <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
      <button onClick={onSave} disabled={saving} className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white inline-flex items-center gap-2" data-testid="save-employee-btn">
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem
      </button>
    </div>
  );
}

/* ============================ SCHEDULES TAB ============================ */
/**
 * Administrer åbnings- og lukketidspunkter - split in two sections:
 *  - Helligdage: oprette helligdagskalendere + tilknyt til materialer
 *  - Åbnings-/lukketid: oprette ugekalendere + tilknyt til materialer (ikke-helligdage)
 *
 * Calendars are scoped per-plads (location_code). When the admin manages
 * multiple pladser they pick which one in the dropdown at the top.
 */
function SchedulesTab({ locations = [] }) {
  const initialCode = locations[0]?.code || locations[0]?.location_code || "";
  const [activeCode, setActiveCode] = useState(initialCode);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyRefreshTick, setCopyRefreshTick] = useState(0);
  useEffect(() => {
    if (!activeCode && locations[0]) {
      setActiveCode(locations[0].code || locations[0].location_code);
    }
  }, [locations, activeCode]);
  const activeLoc = locations.find(l => (l.code || l.location_code) === activeCode);

  if (locations.length === 0) {
    return (
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
        Ingen lokationer tilknyttet din konto endnu.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="schedules-tab">
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lokation:</p>
          {locations.map(l => {
            const code = l.code || l.location_code;
            const on = code === activeCode;
            return (
              <button key={code} onClick={() => setActiveCode(code)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`}
                data-testid={`schedule-loc-${code}`}>
                {l.name}
              </button>
            );
          })}
        </div>
      )}

      {/* Overskrift + "Kopier fra eksisterende"-knap.
          Fase 18.44: Location admins kan kopiere konfiguration fra en anden
          lokation de administrerer - sparer tid ved opsætning af nye pladser. */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
          Administrer åbnings- og lukketidspunkter
          {activeLoc && <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {activeLoc.name}</span>}
        </h2>
        {locations.length >= 2 && (
          <button
            onClick={() => setCopyOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm"
            data-testid="copy-config-btn"
            title="Kopiér helligdage, åbningstider og leveringsadresser fra en anden lokation"
          >
            <Copy className="w-3.5 h-3.5" /> Kopier fra eksisterende
          </button>
        )}
      </div>

      <HolidaySection key={`h-${activeCode}-${copyRefreshTick}`} locationCode={activeCode} location={activeLoc} />
      <HoursSection key={`o-${activeCode}-${copyRefreshTick}`} locationCode={activeCode} location={activeLoc} />

      {copyOpen && (
        <CopyConfigModal
          locations={locations}
          targetCode={activeCode}
          targetName={activeLoc?.name || activeCode}
          onClose={() => setCopyOpen(false)}
          onSuccess={() => { setCopyOpen(false); setCopyRefreshTick(t => t + 1); }}
        />
      )}
    </div>
  );
}

/* ----- KOPIER-KONFIG MODAL (Fase 18.44) -----
   Location admin vælger source-lokation + hvilke sections der skal kopieres.
   Backend sletter target's eksisterende data i valgte sections og importerer
   source's data. */
function CopyConfigModal({ locations, targetCode, targetName, onClose, onSuccess }) {
  const [sourceCode, setSourceCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const otherLocations = locations.filter(l => (l.code || l.location_code) !== targetCode);

  const doCopy = async () => {
    if (!sourceCode) { toast.error("Vælg en source-lokation"); return; }
    setBusy(true);
    try {
      // Kopier ALT: send "all" så backend inkluderer alle sektioner
      // (helligdage, åbningstider, material-mapninger, leveringsadresser,
      // kapacitetsmål, container-overrides, container-antal, materialer +
      // partner-materialer + CO2-mapninger). Target ryddes helt før kopi.
      const res = await axios.post(`${API}/org/schedule/copy-config`, {
        source_code: sourceCode,
        target_code: targetCode,
        sections: ["all"],
      });
      toast.success(`Kopieret til ${targetName}`);
      if (res.data) onSuccess();
    } catch (err) {
      toast.error("Kopiering fejlede: " + (err?.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  };

  const COPIED_SECTIONS = [
    { label: "Helligdagskalendere", desc: "Alle kalendere + hvilke materialer de er tilknyttet" },
    { label: "Åbnings-/lukketidskalendere", desc: "Alle kalendere + hvilke materialer de er tilknyttet" },
    { label: "Leveringsadresser", desc: "Alle registrerede leveringsadresser" },
    { label: "Kapacitetsmål", desc: "Alle kapacitetsmål (LA-bibliotek)" },
    { label: "Container-overrides", desc: "Per-container adresse, tid, ID, lås og kapacitetsref" },
    { label: "Container-antal", desc: "Antal containere pr. materiale/partner" },
    { label: "Materialer", desc: "Aktive + inaktive materialer, partner-materialer, CO2-mapninger" },
  ];

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="copy-config-modal">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading font-bold text-lg text-slate-900 dark:text-white flex items-center gap-2">
            <Copy className="w-5 h-5 text-blue-600" /> Kopier fra eksisterende
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Kopier <strong>al</strong> konfiguration fra en anden lokation til <strong className="text-slate-900 dark:text-white">{targetName}</strong>.
          Målet ryddes helt før kopieringen - ingen preudfyldning.
        </p>

        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Source-lokation</label>
        <select
          value={sourceCode}
          onChange={e => setSourceCode(e.target.value)}
          className="w-full mb-4 px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white"
          data-testid="copy-source-select"
        >
          <option value="">- Vælg lokation -</option>
          {otherLocations.map(l => {
            const code = l.code || l.location_code;
            return <option key={code} value={code}>{l.name}</option>;
          })}
        </select>

        <p className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Følgende data kopieres 1:1</p>
        <div className="space-y-1.5 mb-4 rounded-lg border border-slate-200 dark:border-slate-700 p-3 bg-slate-50 dark:bg-slate-800/40">
          {COPIED_SECTIONS.map(s => (
            <div key={s.label} className="flex items-start gap-2 text-xs">
              <Check className="w-3.5 h-3.5 text-emerald-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-900 dark:text-white">{s.label}</p>
                <p className="text-slate-500">{s.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-bold" disabled={busy}>
            Annullér
          </button>
          <button
            onClick={() => setConfirmOpen(true)}
            disabled={busy || !sourceCode}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold inline-flex items-center gap-1.5"
            data-testid="copy-confirm-open-btn"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}
            Kopier alt
          </button>
        </div>

        {confirmOpen && (
          <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4" onClick={() => !busy && setConfirmOpen(false)}>
            <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-amber-600" />
                </div>
                <h4 className="font-bold text-lg text-slate-900 dark:text-white">Er du sikker?</h4>
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-5">
                Alt eksisterende data for <strong>{targetName}</strong> (kalendere, adresser, materialer, kapacitetsmål, container-overrides m.m.) vil blive <strong className="text-red-600">slettet permanent</strong> og erstattet med en 1:1 kopi fra source-lokationen.
              </p>
              <div className="flex justify-end gap-2">
                <button onClick={() => setConfirmOpen(false)} disabled={busy} className="px-4 py-2 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-bold">Annullér</button>
                <button onClick={doCopy} disabled={busy} className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-bold inline-flex items-center gap-1.5" data-testid="copy-confirm-execute-btn">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  Ja, slet og kopier alt
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ----- HELLIGDAGE ----- */
function HolidaySection({ locationCode, location }) {
  const [calendars, setCalendars] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [saGroups, setSaGroups] = useState([]); // SA holiday-groups available to copy from
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  // Source for prefill in the new-cal form: "blank" | "group:<id>" | "cal:<id>"
  const [newSource, setNewSource] = useState("blank");

  const fetchAll = useCallback(async () => {
    if (!locationCode) return;
    setLoading(true);
    try {
      const [c, l, m, sg] = await Promise.all([
        axios.get(`${API}/org/holiday-calendars?location_code=${locationCode}`),
        axios.get(`${API}/locations/${locationCode}/containers`),
        axios.get(`${API}/org/material-calendars?location_code=${locationCode}`),
        // Holiday groups for "Kopiér fra SA-gruppe" option. Hits an
        // LA-accessible endpoint (the /superadmin one would 403 here).
        axios.get(`${API}/org/holiday-groups`).catch(() => ({ data: [] })),
      ]);
      setCalendars(c.data || []);
      const mats = (l.data?.materials || []).map(x => x.material);
      setMaterials(mats);
      setAssignments(m.data || []);
      setSaGroups((sg.data || []).filter(g => g.active !== false));
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [locationCode]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const create = async () => {
    if (!newName.trim()) { toast.error("Navn er påkrævet"); return; }
    // År-feltet er fjernet fra UI'et pr. brugerkrav 2026-06-14 -
    // helligdagskalendere er nu kontinuerlige.
    try {
      if (newSource.startsWith("group:")) {
        // Copy from a Super Admin holiday-group
        const gid = newSource.slice(6);
        await axios.post(`${API}/org/holiday-calendars/copy-from-group`, {
          location_code: locationCode,
          group_id: gid,
          name: newName.trim(),
        });
        toast.success("Helligdagskalender oprettet (fra SA-gruppe)");
      } else if (newSource.startsWith("cal:")) {
        // Duplicate an existing LA calendar
        const cid = newSource.slice(4);
        await axios.post(`${API}/org/holiday-calendars/${cid}/copy`, {
          name: newName.trim(),
        });
        toast.success("Helligdagskalender kopieret");
      } else {
        // "Tom kalender" - send eksplicit days:[] så backend IKKE
        // pre-udfylder fra holiday_group. Brugerkrav 2026-06-15.
        await axios.post(`${API}/org/holiday-calendars`, {
          location_code: locationCode, name: newName.trim(), days: [],
        });
        toast.success("Tom helligdagskalender oprettet");
      }
      setCreating(false); setNewName(""); setNewSource("blank");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (cal) => {
    const cnt = cal.assigned_count || 0;
    if (cnt > 0) {
      toast.error(`Kan ikke slettes - kalenderen er tilknyttet ${cnt} materiale(r). Brug "Deaktivér" i stedet.`);
      return;
    }
    if (!window.confirm(`Slet helligdagskalenderen "${cal.name}" permanent?`)) return;
    try {
      await axios.delete(`${API}/org/holiday-calendars/${cal.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const toggleActive = async (cal) => {
    const cnt = cal.assigned_count || 0;
    if (cal.is_active !== false && cnt > 0) {
      const ok = window.confirm(`Deaktivér "${cal.name}"?\n\nKalenderen er aktuelt tilknyttet ${cnt} materiale(r). Eksisterende tilknytninger bevares; nye tilknytninger blokeres.`);
      if (!ok) return;
    }
    try {
      await axios.post(`${API}/org/holiday-calendars/${cal.id}/toggle-active`,
                       { active: cal.is_active === false });
      toast.success(cal.is_active === false ? "Aktiveret" : "Deaktiveret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const assignmentFor = (mat) => assignments.find(a => a.material === mat) || {};

  const setMaterialHoliday = async (material, holiday_calendar_id) => {
    const cur = assignmentFor(material);
    try {
      await axios.put(`${API}/org/material-calendars`, {
        location_code: locationCode,
        material,
        holiday_calendar_id: holiday_calendar_id || null,
        hours_calendar_id: cur.hours_calendar_id || null,
      });
      toast.success("Tilknytning opdateret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  // Only active calendars show up as options when linking to a material
  const linkableCalendars = calendars.filter(c => c.is_active !== false);

  return (
    <section className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden" data-testid="holiday-section">
      <header className="px-5 py-3 bg-orange-50 dark:bg-orange-950/30 border-b border-orange-100 dark:border-orange-900">
        <h3 className="font-bold text-orange-800 dark:text-orange-300 flex items-center gap-2"><Calendar className="w-4 h-4" /> Helligdage</h3>
      </header>
      <div className="p-5 space-y-6">
        {/* Sub-section 1 */}
        <div>
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div>
              <p className="font-bold text-slate-900 dark:text-white text-sm">Helligdagskalendere</p>
              <p className="text-xs text-slate-500 mt-0.5">Når året skifter, opret en ny kalender for det nye år ud fra Super Admins gruppe eller en af jeres egne kalendere.</p>
            </div>
            {!creating && (
              <button onClick={() => setCreating(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold"
                data-testid="add-holiday-calendar-btn">
                <Plus className="w-3.5 h-3.5" /> Ny helligdagskalender
              </button>
            )}
          </div>
          {creating && (
            <div className="bg-slate-50 dark:bg-slate-900/50 rounded-lg p-3 mb-3 space-y-2" data-testid="new-holiday-calendar-form">
              <input value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Navn (fx Hovedkalender, Værksted, …)"
                className="w-full px-3 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm" autoFocus
                data-testid="new-holiday-name-input" />
              <p className="text-[11px] text-slate-400">
                Helligdagskalendere er kontinuerlige - opdater dem løbende via super admin's "Helligdags-delta" eller manuelt.
              </p>
              <select value={newSource} onChange={e => setNewSource(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm"
                data-testid="new-holiday-source-select">
                <option value="blank">- Tom kalender -</option>
                {saGroups.length > 0 && (
                  <optgroup label="Kopiér fra Super Admin helligdagsgruppe">
                    {saGroups.map(g => (
                      <option key={`g-${g.id}`} value={`group:${g.id}`}>
                        {g.name}{g.year ? ` (${g.year})` : ""}
                      </option>
                    ))}
                  </optgroup>
                )}
                {calendars.length > 0 && (
                  <optgroup label="Kopiér fra egen kalender">
                    {calendars.map(c => (
                      <option key={`c-${c.id}`} value={`cal:${c.id}`}>
                        {c.name}{c.year ? ` (${c.year})` : ""}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              <div className="flex gap-2 justify-end">
                <button onClick={() => { setCreating(false); setNewName(""); setNewSource("blank"); }}
                  className="px-3 py-1.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded text-xs font-semibold">
                  Annuller
                </button>
                <button onClick={create} className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-bold inline-flex items-center gap-1"
                  data-testid="confirm-new-holiday-btn">
                  <Save className="w-3.5 h-3.5" /> Opret
                </button>
              </div>
            </div>
          )}
          <div className="space-y-2">
            {loading ? (
              <div className="py-6 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
            ) : calendars.length === 0 ? (
              <p className="text-xs text-slate-400 italic">Ingen helligdagskalendere endnu.</p>
            ) : calendars.map(cal => {
              const isInactive = cal.is_active === false;
              const cnt = cal.assigned_count || 0;
              return (
              <div key={cal.id}
                className={`border rounded-lg p-3 ${isInactive ? "border-amber-200 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-950/20 opacity-80" : "border-slate-200 dark:border-slate-700"}`}
                data-testid={`holiday-calendar-${cal.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-800 dark:text-white text-sm">{cal.name}</p>
                      {/* År-badge fjernet pr. brugerkrav 2026-06-14 - helligdagskalendere er kontinuerlige. */}
                      {isInactive && (
                        <span className="text-[10px] font-bold uppercase bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded"
                          data-testid={`holiday-cal-inactive-${cal.id}`}>
                          Inaktiv
                        </span>
                      )}
                      {cnt > 0 && (
                        <span className="text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded">
                          {cnt} tilknytning{cnt === 1 ? "" : "er"}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400">{cal.days?.length || 0} dage</p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => setEditing(cal)}
                      className="p-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-950/30 text-slate-500 hover:text-blue-600"
                      title="Rediger" data-testid={`edit-holiday-cal-${cal.id}`}>
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => toggleActive(cal)}
                      className={`p-1.5 rounded ${isInactive ? "hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-emerald-600" : "hover:bg-amber-50 dark:hover:bg-amber-950/30 text-amber-600"}`}
                      title={isInactive ? "Genaktivér" : "Deaktivér"}
                      data-testid={`toggle-holiday-cal-${cal.id}`}>
                      {isInactive ? <CheckCircle2 className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                    </button>
                    <button onClick={() => remove(cal)}
                      disabled={cnt > 0}
                      className={`p-1.5 rounded ${cnt > 0 ? "opacity-30 cursor-not-allowed" : "hover:bg-red-50 dark:hover:bg-red-950/30 text-slate-500 hover:text-red-600"}`}
                      title={cnt > 0 ? `Kan ikke slettes - ${cnt} tilknytning(er)` : "Slet permanent"}
                      data-testid={`delete-holiday-cal-${cal.id}`}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );})}
          </div>
        </div>

        {/* Sub-section 2 */}
        <div className="border-t border-slate-100 dark:border-slate-700 pt-5">
          <p className="font-bold text-slate-900 dark:text-white text-sm mb-1">Tilknyt helligdagskalender til materialer</p>
          <p className="text-xs text-slate-500 mb-3">Vælg én helligdagskalender pr. materiale (eller "ingen helligdagskalender"). Kun aktive kalendere vises som valgmuligheder.</p>
          {materials.length === 0 ? (
            <p className="text-xs text-amber-600">Ingen materialer på lokationen endnu. Tilføj materialer fra bestillingssiden først.</p>
          ) : (
            <div className="space-y-1.5">
              {materials.map(m => {
                const a = assignmentFor(m);
                return (
                  <div key={m} className="flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-900/40 rounded" data-testid={`holiday-link-row-${m}`}>
                    <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-white truncate">{m}</span>
                    <select value={a.holiday_calendar_id || ""}
                      onChange={e => setMaterialHoliday(m, e.target.value)}
                      className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-xs"
                      data-testid={`holiday-link-select-${m}`}>
                      <option value="">Ingen helligdagskalender</option>
                      {linkableCalendars.map(c => (
                        <option key={c.id} value={c.id}>{c.name}{c.year ? ` (${c.year})` : ""}</option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {editing && (
        <HolidayCalendarEditor
          calendar={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}
    </section>
  );
}

/* ----- HOLIDAY CALENDAR EDITOR ----- */
// Brugerkrav 2026-06-15 (runde 7): Helligdage skal automatisk sorteres efter
// dato. fx "Juleaften 24. december 2026" skal stå EFTER "Nytårsdag 31. december
// 2025" men FØR "Nytårsdag 31. december 2026". Tomme datoer sorteres nederst
// så nye rækker er synlige indtil de udfyldes.
const sortDaysByDate = (days) => {
  return [...days].sort((a, b) => {
    const da = (a.date || "").trim();
    const db = (b.date || "").trim();
    if (!da && !db) return 0;
    if (!da) return 1;   // tom dato nederst
    if (!db) return -1;
    return da.localeCompare(db);  // ISO-format YYYY-MM-DD sorteres rigtigt med streng-compare
  });
};

function HolidayCalendarEditor({ calendar, onClose, onSaved }) {
  const [name, setName] = useState(calendar.name || "");
  const [days, setDays] = useState(() => sortDaysByDate(calendar.days || []));
  const [addresses, setAddresses] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/org/delivery-addresses?location_code=${calendar.location_code}`)
      .then(r => setAddresses(r.data || []))
      .catch(() => setAddresses([]));
  }, [calendar.location_code]);

  const addDay = () => setDays(prev => sortDaysByDate([...prev, { name: "", date: "", closed: false, open_from: "", open_to: "", delivery_address_id: null }]));
  const updateDay = (idx, field, val) => setDays(prev => {
    const next = prev.map((d, i) => i === idx ? { ...d, [field]: val } : d);
    // Sortér igen når dato ændres så rækkefølgen altid afspejler kronologi
    return field === "date" ? sortDaysByDate(next) : next;
  });
  const removeDay = (idx) => setDays(prev => prev.filter((_, i) => i !== idx));
  const toggleClosed = (idx, closed) => setDays(prev => prev.map((d, i) => i === idx ? {
    ...d, closed, open_from: closed ? "" : d.open_from, open_to: closed ? "" : d.open_to,
  } : d));
  // Brugerkrav 2026-06-15: "Kopiér til alle rækker" - overfører denne rækkes
  // åbningstider + lukket-status + leveringsadresse til ALLE andre rækker.
  // Navn + dato beholdes individuelt (de er unikke pr. helligdag). Hvis kun
  // én række eksisterer, gør funktionen ingenting.
  const copyToAll = (idx) => setDays(prev => {
    if (prev.length <= 1) { toast.info("Der er ingen andre rækker at kopiere til"); return prev; }
    const src = prev[idx];
    const next = prev.map((d, i) => i === idx ? d : ({
      ...d,
      closed: src.closed,
      open_from: src.closed ? "" : src.open_from,
      open_to: src.closed ? "" : src.open_to,
      delivery_address_id: src.delivery_address_id,
    }));
    toast.success(`Kopieret til ${prev.length - 1} andre række${prev.length - 1 === 1 ? "" : "r"}`);
    return next;
  });

  const save = async () => {
    if (!name.trim()) { toast.error("Navn er påkrævet"); return; }
    setSaving(true);
    try {
      await axios.put(`${API}/org/holiday-calendars/${calendar.id}`, {
        name: name.trim(),
        days: sortDaysByDate(days.filter(d => d.name?.trim() && d.date?.trim())),
      });
      toast.success("Helligdagskalender opdateret");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="holiday-cal-editor">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h3 className="font-bold text-slate-900 dark:text-white">Rediger helligdagskalender</h3>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-500"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 overflow-y-auto">
          <label className="block text-xs font-semibold text-slate-500 mb-1">Navn</label>
          <input value={name} onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm mb-4"
            data-testid="holiday-cal-name-input" />
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-slate-500">Helligdage</p>
            <button onClick={addDay} className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded text-xs font-semibold" data-testid="add-day-btn">
              <Plus className="w-3 h-3" /> Tilføj dag
            </button>
          </div>
          <div className="space-y-2">
            {days.length === 0 && (
              <p className="text-xs text-slate-400 italic">Ingen helligdage endnu. Tryk "Tilføj dag".</p>
            )}
            {days.map((d, i) => (
              <div key={i} className="border border-slate-200 dark:border-slate-700 rounded-lg p-2 space-y-2" data-testid={`day-row-${i}`}>
                <div className="grid grid-cols-1 sm:grid-cols-[2fr,1fr,1fr,1fr,auto] gap-2 items-center">
                  <input value={d.name} onChange={e => updateDay(i, "name", e.target.value)}
                    placeholder="Navn (fx Juledag)"
                    className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-sm"
                    data-testid={`day-name-${i}`} />
                  <input type="date" value={d.date}
                    readOnly={d.closed}
                    onChange={e => updateDay(i, "date", e.target.value)}
                    className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded text-sm ${d.closed ? "bg-slate-100 dark:bg-slate-900/50 cursor-not-allowed" : "dark:bg-slate-900"}`}
                    data-testid={`day-date-${i}`} />
                  <input type="time" value={d.open_from}
                    readOnly={d.closed}
                    onChange={e => updateDay(i, "open_from", e.target.value)}
                    className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded text-sm ${d.closed ? "bg-slate-100 dark:bg-slate-900/50 cursor-not-allowed" : "dark:bg-slate-900"}`}
                    data-testid={`day-from-${i}`} />
                  <input type="time" value={d.open_to}
                    readOnly={d.closed}
                    onChange={e => updateDay(i, "open_to", e.target.value)}
                    className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded text-sm ${d.closed ? "bg-slate-100 dark:bg-slate-900/50 cursor-not-allowed" : "dark:bg-slate-900"}`}
                    data-testid={`day-to-${i}`} />
                  <div className="flex items-center gap-1">
                    <button onClick={() => copyToAll(i)} className="p-1.5 hover:bg-blue-50 dark:hover:bg-blue-950/30 rounded text-slate-400 hover:text-blue-500" title="Kopiér åbningstider + adresse til alle andre rækker" data-testid={`day-copy-${i}`}>
                      <Copy className="w-4 h-4" />
                    </button>
                    <button onClick={() => removeDay(i)} className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500" data-testid={`day-remove-${i}`}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 cursor-pointer text-xs">
                    <input type="radio" name={`closed-${i}`} checked={d.closed}
                      onClick={() => toggleClosed(i, !d.closed)}
                      onChange={() => {}}
                      className="w-4 h-4 accent-amber-500"
                      data-testid={`day-closed-${i}`} />
                    <span className="text-slate-700 dark:text-slate-200 font-semibold inline-flex items-center gap-1">
                      <Lock className="w-3 h-3" /> Lukket?
                    </span>
                    <span className="text-slate-400 text-[11px]">(låser dato + tider)</span>
                  </label>
                  <div className="flex items-center gap-1.5 ml-auto">
                    <MapPin className="w-3.5 h-3.5 text-slate-400" />
                    <label className="text-[11px] text-slate-500">Leveringsadresse (valgfri):</label>
                    <select value={d.delivery_address_id || ""}
                      onChange={e => updateDay(i, "delivery_address_id", e.target.value || null)}
                      className="px-2 py-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-xs max-w-[200px]"
                      data-testid={`day-address-${i}`}>
                      <option value="">- Fald tilbage til ugedag -</option>
                      {addresses.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            data-testid="save-holiday-cal-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
}

/* ----- HOURS (WEEKDAYS) SECTION ----- */
const WEEKDAYS = [
  { key: "mon", label: "Mandag" }, { key: "tue", label: "Tirsdag" },
  { key: "wed", label: "Onsdag" }, { key: "thu", label: "Torsdag" },
  { key: "fri", label: "Fredag" }, { key: "sat", label: "Lørdag" },
  { key: "sun", label: "Søndag" },
];

function HoursSection({ locationCode, location }) {
  const [calendars, setCalendars] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const fetchAll = useCallback(async () => {
    if (!locationCode) return;
    setLoading(true);
    try {
      const [c, l, m] = await Promise.all([
        axios.get(`${API}/org/hours-calendars?location_code=${locationCode}`),
        axios.get(`${API}/locations/${locationCode}/containers`),
        axios.get(`${API}/org/material-calendars?location_code=${locationCode}`),
      ]);
      setCalendars(c.data || []);
      const mats = (l.data?.materials || []).map(x => x.material);
      setMaterials(mats);
      setAssignments(m.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [locationCode]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const create = async () => {
    if (!newName.trim()) { toast.error("Navn er påkrævet"); return; }
    try {
      await axios.post(`${API}/org/hours-calendars`, {
        location_code: locationCode, name: newName.trim(),
        weekdays: WEEKDAYS.reduce((acc, w) => ({ ...acc, [w.key]: { closed: false, open_from: "07:00", open_to: "16:00" } }), {}),
      });
      toast.success("Åbningstidskalender oprettet");
      setCreating(false); setNewName("");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (cal) => {
    const cnt = cal.assigned_count || 0;
    if (cnt > 0) {
      toast.error(`Kan ikke slettes - kalenderen er tilknyttet ${cnt} materiale(r). Brug "Deaktivér" i stedet.`);
      return;
    }
    if (!window.confirm(`Slet åbningstidskalenderen "${cal.name}" permanent?`)) return;
    try {
      await axios.delete(`${API}/org/hours-calendars/${cal.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const toggleActive = async (cal) => {
    const cnt = cal.assigned_count || 0;
    if (cal.is_active !== false && cnt > 0) {
      const ok = window.confirm(`Deaktivér "${cal.name}"?\n\nKalenderen er aktuelt tilknyttet ${cnt} materiale(r). Eksisterende tilknytninger bevares; nye tilknytninger blokeres.`);
      if (!ok) return;
    }
    try {
      await axios.post(`${API}/org/hours-calendars/${cal.id}/toggle-active`,
                       { active: cal.is_active === false });
      toast.success(cal.is_active === false ? "Aktiveret" : "Deaktiveret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const copy = async (cal) => {
    try {
      await axios.post(`${API}/org/hours-calendars/${cal.id}/copy`,
                       { name: `${cal.name} (kopi)` });
      toast.success("Åbningstidskalender kopieret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const assignmentFor = (mat) => assignments.find(a => a.material === mat) || {};

  const setMaterialHours = async (material, hours_calendar_id) => {
    const cur = assignmentFor(material);
    try {
      await axios.put(`${API}/org/material-calendars`, {
        location_code: locationCode,
        material,
        holiday_calendar_id: cur.holiday_calendar_id || null,
        hours_calendar_id: hours_calendar_id || null,
      });
      toast.success("Tilknytning opdateret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <section className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden" data-testid="hours-section">
      <header className="px-5 py-3 bg-emerald-50 dark:bg-emerald-950/30 border-b border-emerald-100 dark:border-emerald-900">
        <h3 className="font-bold text-emerald-800 dark:text-emerald-300 flex items-center gap-2"><Clock className="w-4 h-4" /> Åbnings- og lukketidsplan</h3>
      </header>
      <div className="p-5 space-y-6">
        {/* Sub-section 1 */}
        <div>
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div>
              <p className="font-bold text-slate-900 dark:text-white text-sm">Opret åbnings- og lukketidskalender</p>
              <p className="text-xs text-slate-500 mt-0.5">Sæt åbnings- og lukketid pr. ugedag. En dag kan markeres som "Lukket".</p>
            </div>
            {!creating && (
              <button onClick={() => setCreating(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold"
                data-testid="add-hours-calendar-btn">
                <Plus className="w-3.5 h-3.5" /> Ny åbningstidskalender
              </button>
            )}
          </div>
          {creating && (
            <div className="bg-slate-50 dark:bg-slate-900/50 rounded-lg p-3 mb-3 flex gap-2 items-center" data-testid="new-hours-calendar-form">
              <input value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Navn (fx Standard åbningstider)"
                className="flex-1 px-3 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm" autoFocus
                data-testid="new-hours-name-input" />
              <button onClick={create} className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-bold inline-flex items-center gap-1" data-testid="confirm-new-hours-btn">
                <Save className="w-3.5 h-3.5" /> Opret
              </button>
              <button onClick={() => { setCreating(false); setNewName(""); }} className="px-3 py-1.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded text-xs font-semibold">
                Annuller
              </button>
            </div>
          )}
          <div className="space-y-2">
            {loading ? (
              <div className="py-6 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
            ) : calendars.length === 0 ? (
              <p className="text-xs text-slate-400 italic">Ingen åbningstidskalendere endnu.</p>
            ) : calendars.map(cal => {
              const isInactive = cal.is_active === false;
              const cnt = cal.assigned_count || 0;
              return (
              <div key={cal.id}
                className={`border rounded-lg p-3 ${isInactive ? "border-amber-200 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-950/20 opacity-80" : "border-slate-200 dark:border-slate-700"}`}
                data-testid={`hours-calendar-${cal.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-800 dark:text-white text-sm">{cal.name}</p>
                      {isInactive && (
                        <span className="text-[10px] font-bold uppercase bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded"
                          data-testid={`hours-cal-inactive-${cal.id}`}>
                          Inaktiv
                        </span>
                      )}
                      {cnt > 0 && (
                        <span className="text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded">
                          {cnt} tilknytning{cnt === 1 ? "" : "er"}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400 truncate">
                      {WEEKDAYS.map(w => {
                        const d = cal.weekdays?.[w.key] || {};
                        if (d.closed) return `${w.label.slice(0,3)}: Lukket`;
                        if (d.open_from || d.open_to) return `${w.label.slice(0,3)}: ${d.open_from}-${d.open_to}`;
                        return `${w.label.slice(0,3)}: -`;
                      }).join(" · ")}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => setEditing(cal)}
                      className="p-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-950/30 text-slate-500 hover:text-blue-600"
                      title="Rediger" data-testid={`edit-hours-cal-${cal.id}`}>
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => copy(cal)}
                      className="p-1.5 rounded hover:bg-purple-50 dark:hover:bg-purple-950/30 text-slate-500 hover:text-purple-600"
                      title="Kopiér" data-testid={`copy-hours-cal-${cal.id}`}>
                      <Copy className="w-4 h-4" />
                    </button>
                    <button onClick={() => toggleActive(cal)}
                      className={`p-1.5 rounded ${isInactive ? "hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-emerald-600" : "hover:bg-amber-50 dark:hover:bg-amber-950/30 text-amber-600"}`}
                      title={isInactive ? "Genaktivér" : "Deaktivér"}
                      data-testid={`toggle-hours-cal-${cal.id}`}>
                      {isInactive ? <CheckCircle2 className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                    </button>
                    <button onClick={() => remove(cal)}
                      disabled={cnt > 0}
                      className={`p-1.5 rounded ${cnt > 0 ? "opacity-30 cursor-not-allowed" : "hover:bg-red-50 dark:hover:bg-red-950/30 text-slate-500 hover:text-red-600"}`}
                      title={cnt > 0 ? `Kan ikke slettes - ${cnt} tilknytning(er)` : "Slet permanent"}
                      data-testid={`delete-hours-cal-${cal.id}`}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );})}
          </div>
        </div>

        {/* Sub-section 2 */}
        <div className="border-t border-slate-100 dark:border-slate-700 pt-5">
          <p className="font-bold text-slate-900 dark:text-white text-sm mb-1">Tilknyt åbnings- og lukketidspunkter for ikke-helligdage</p>
          <p className="text-xs text-slate-500 mb-3">Disse åbningstider gælder alle dage UNDTAGEN dem der står i den tilknyttede helligdagskalender.</p>
          {materials.length === 0 ? (
            <p className="text-xs text-amber-600">Ingen materialer på lokationen endnu.</p>
          ) : (
            <div className="space-y-1.5">
              {materials.map(m => {
                const a = assignmentFor(m);
                return (
                  <div key={m} className="flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-900/40 rounded" data-testid={`hours-link-row-${m}`}>
                    <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-white truncate">{m}</span>
                    <select value={a.hours_calendar_id || ""}
                      onChange={e => setMaterialHours(m, e.target.value)}
                      className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-xs"
                      data-testid={`hours-link-select-${m}`}>
                      <option value="">Ingen åbningstidskalender</option>
                      {calendars.filter(c => c.is_active !== false).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {editing && (
        <HoursCalendarEditor calendar={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); fetchAll(); }} />
      )}
    </section>
  );
}

/* ----- HOURS CALENDAR EDITOR ----- */
function HoursCalendarEditor({ calendar, onClose, onSaved }) {
  const [name, setName] = useState(calendar.name || "");
  const [weekdays, setWeekdays] = useState(() => {
    const w = { ...(calendar.weekdays || {}) };
    WEEKDAYS.forEach(d => {
      if (!w[d.key]) w[d.key] = { closed: false, open_from: "", open_to: "", delivery_address_id: null };
    });
    return w;
  });
  const [addresses, setAddresses] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/org/delivery-addresses?location_code=${calendar.location_code}`)
      .then(r => setAddresses(r.data || []))
      .catch(() => setAddresses([]));
  }, [calendar.location_code]);

  const updateDay = (key, field, val) => {
    setWeekdays(p => ({ ...p, [key]: { ...p[key], [field]: val } }));
  };
  const toggleClosed = (key) => {
    setWeekdays(p => ({
      ...p,
      [key]: {
        ...p[key],
        closed: !p[key].closed,
        open_from: !p[key].closed ? "" : p[key].open_from,
        open_to: !p[key].closed ? "" : p[key].open_to,
      },
    }));
  };
  // Brugerkrav 2026-06-15: "Kopiér til alle ugedage" - denne ugedags
  // åbnings-/lukketider + lukket-status + leveringsadresse overføres til
  // de øvrige 6 dage. Lørdag/søndag overskrives også; brugeren kan derefter
  // manuelt sætte dem til lukket hvis det ønskes.
  const copyWeekdayToAll = (srcKey) => {
    const src = weekdays[srcKey];
    if (!src) return;
    setWeekdays(p => {
      const next = { ...p };
      WEEKDAYS.forEach(w => {
        if (w.key === srcKey) return;
        next[w.key] = {
          ...next[w.key],
          closed: src.closed,
          open_from: src.closed ? "" : src.open_from,
          open_to: src.closed ? "" : src.open_to,
          delivery_address_id: src.delivery_address_id,
        };
      });
      return next;
    });
    toast.success(`Kopieret til de øvrige ${WEEKDAYS.length - 1} ugedage`);
  };

  const save = async () => {
    if (!name.trim()) { toast.error("Navn er påkrævet"); return; }
    // Leveringsadresse er obligatorisk for åbne ugedage
    const missing = WEEKDAYS.filter(w => {
      const d = weekdays[w.key] || {};
      return !d.closed && !d.delivery_address_id;
    }).map(w => w.label);
    if (missing.length > 0) {
      toast.error(`Leveringsadresse er obligatorisk for: ${missing.join(", ")}`);
      return;
    }
    setSaving(true);
    try {
      await axios.put(`${API}/org/hours-calendars/${calendar.id}`, {
        name: name.trim(), weekdays,
      });
      toast.success("Åbningstidskalender opdateret");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="hours-cal-editor">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h3 className="font-bold text-slate-900 dark:text-white">Rediger åbningstidskalender</h3>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-500"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 overflow-y-auto">
          <label className="block text-xs font-semibold text-slate-500 mb-1">Navn</label>
          <input value={name} onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm mb-4"
            data-testid="hours-cal-name-input" />
          <p className="text-xs font-semibold text-slate-500 mb-2">Ugedage</p>
          <div className="space-y-2">
            {WEEKDAYS.map(w => {
              const d = weekdays[w.key] || {};
              return (
                <div key={w.key} className="border border-slate-200 dark:border-slate-700 rounded-lg p-2 space-y-2" data-testid={`weekday-row-${w.key}`}>
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr,1fr,1fr,auto,auto] gap-2 items-center">
                    <span className="font-bold text-sm text-slate-800 dark:text-white">{w.label}</span>
                    <input type="time" value={d.open_from || ""}
                      readOnly={d.closed}
                      onChange={e => updateDay(w.key, "open_from", e.target.value)}
                      className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded text-sm ${d.closed ? "bg-slate-100 dark:bg-slate-900/50 cursor-not-allowed" : "dark:bg-slate-900"}`}
                      data-testid={`weekday-from-${w.key}`} />
                    <input type="time" value={d.open_to || ""}
                      readOnly={d.closed}
                      onChange={e => updateDay(w.key, "open_to", e.target.value)}
                      className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded text-sm ${d.closed ? "bg-slate-100 dark:bg-slate-900/50 cursor-not-allowed" : "dark:bg-slate-900"}`}
                      data-testid={`weekday-to-${w.key}`} />
                    <label className="flex items-center gap-1 cursor-pointer text-xs">
                      <input type="radio" name={`closed-${w.key}`}
                        checked={!!d.closed}
                        onClick={() => toggleClosed(w.key)}
                        onChange={() => {}}
                        className="w-4 h-4 accent-amber-500"
                        data-testid={`weekday-closed-${w.key}`} />
                      <span className="text-slate-700 dark:text-slate-200 font-semibold inline-flex items-center gap-1">
                        <Lock className="w-3 h-3" /> Lukket?
                      </span>
                    </label>
                    <button onClick={() => copyWeekdayToAll(w.key)}
                      className="p-1.5 hover:bg-blue-50 dark:hover:bg-blue-950/30 rounded text-slate-400 hover:text-blue-500"
                      title="Kopiér tider + adresse til alle andre ugedage"
                      data-testid={`weekday-copy-${w.key}`}>
                      <Copy className="w-4 h-4" />
                    </button>
                  </div>
                  {!d.closed && (
                    <div className="flex items-center gap-2">
                      <MapPin className="w-3.5 h-3.5 text-slate-400" />
                      <label className="text-[11px] text-slate-500 font-semibold">Leveringsadresse *</label>
                      <select value={d.delivery_address_id || ""}
                        onChange={e => updateDay(w.key, "delivery_address_id", e.target.value || null)}
                        className={`flex-1 px-2 py-1 border rounded text-xs ${
                          d.delivery_address_id
                            ? "border-slate-300 dark:border-slate-600 dark:bg-slate-900"
                            : "border-rose-400 dark:border-rose-700 bg-rose-50 dark:bg-rose-950/30"
                        }`}
                        data-testid={`weekday-address-${w.key}`}>
                        <option value="">- Vælg leveringsadresse -</option>
                        {addresses.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            data-testid="save-hours-cal-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
}


/* ============================ LEVERINGSADRESSER TAB ============================ */
/**
 * Manage delivery addresses for each managed plads. Each address can be
 * linked to one or more materials. For every (plads, material) tuple
 * exactly ONE address can be marked PRIMARY - that's the default that's
 * auto-populated on container creation and on the order page.
 */
function DeliveryAddressesTab({ locations = [] }) {
  const initialCode = locations[0]?.code || locations[0]?.location_code || "";
  const [activeCode, setActiveCode] = useState(initialCode);
  useEffect(() => {
    if (!activeCode && locations[0]) {
      setActiveCode(locations[0].code || locations[0].location_code);
    }
  }, [locations, activeCode]);
  const activeLoc = locations.find(l => (l.code || l.location_code) === activeCode);

  if (locations.length === 0) {
    return (
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
        Ingen lokationer tilknyttet din konto endnu.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="delivery-addresses-tab">
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lokation:</p>
          {locations.map(l => {
            const code = l.code || l.location_code;
            const on = code === activeCode;
            return (
              <button key={code} onClick={() => setActiveCode(code)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`}
                data-testid={`delivery-loc-${code}`}>
                {l.name}
              </button>
            );
          })}
        </div>
      )}
      <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
        Leveringsadresser
        {activeLoc && <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {activeLoc.name}</span>}
      </h2>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Et bibliotek af leveringsadresser. Tilknyt en adresse til en bestemt helligdag eller en ugedag
        i fanen <em>Åbnings- og lukketidspunkter</em>. Den samme adresse kan bruges på flere dage og kalendre.
      </p>
      <DeliverySection locationCode={activeCode} />
    </div>
  );
}

function DeliverySection({ locationCode }) {
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | "new" | obj

  const fetchAll = useCallback(async () => {
    if (!locationCode) return;
    setLoading(true);
    try {
      const a = await axios.get(`${API}/org/delivery-addresses?location_code=${locationCode}`);
      setAddresses(a.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [locationCode]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const remove = async (a) => {
    if (!window.confirm(`Slet leveringsadressen "${a.label}"?`)) return;
    try {
      await axios.delete(`${API}/org/delivery-addresses/${a.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Indlæser…</div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-700 dark:text-slate-300 font-semibold">
          {addresses.length} leveringsadresse{addresses.length === 1 ? "" : "r"}
        </p>
        <button onClick={() => setEditing("new")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
          data-testid="add-delivery-address-btn">
          <Plus className="w-3.5 h-3.5" /> Ny leveringsadresse
        </button>
      </div>

      {addresses.length === 0 ? (
        <div className="bg-slate-50 dark:bg-slate-800/50 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-6 text-center text-sm text-slate-500 dark:text-slate-400">
          Ingen leveringsadresser oprettet endnu. Klik på <strong>Ny leveringsadresse</strong> for at komme i gang.
        </div>
      ) : (
        <div className="space-y-3">
          {addresses.map(a => {
            const fullLine = [a.street, [a.postcode, a.city].filter(Boolean).join(" ")].filter(Boolean).join(", ");
            return (
              <div key={a.id} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4"
                data-testid={`delivery-row-${a.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-900 dark:text-white">{a.label}</p>
                    {fullLine && <p className="text-sm text-slate-600 dark:text-slate-400 mt-0.5">{fullLine}</p>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button onClick={() => setEditing(a)}
                      className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300"
                      data-testid={`edit-delivery-${a.id}`} title="Rediger">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => remove(a)}
                      className="p-2 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950 text-rose-600"
                      data-testid={`delete-delivery-${a.id}`} title="Slet">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <DeliveryAddressModal
          locationCode={locationCode}
          address={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}
    </div>
  );
}

function DeliveryAddressModal({ locationCode, address, onClose, onSaved }) {
  const isEdit = !!address;
  const [label, setLabel] = useState(address?.label || "");
  const [street, setStreet] = useState(address?.street || "");
  const [postcode, setPostcode] = useState(address?.postcode || "");
  const [city, setCity] = useState(address?.city || "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    // Fase 15.55b (2026-02-22): Alle 4 felter obligatoriske ved opret + edit.
    if (!label.trim()) { toast.error("Navn er påkrævet"); return; }
    if (!street.trim()) { toast.error("Gade og nr. er påkrævet"); return; }
    if (!postcode.trim()) { toast.error("Postnr. er påkrævet"); return; }
    if (!city.trim()) { toast.error("By er påkrævet"); return; }
    const payload = {
      location_code: locationCode,
      label: label.trim(),
      street: street.trim(),
      postcode: postcode.trim(),
      city: city.trim(),
    };
    setSaving(true);
    try {
      if (isEdit) {
        await axios.put(`${API}/org/delivery-addresses/${address.id}`, payload);
        toast.success("Leveringsadresse opdateret");
      } else {
        await axios.post(`${API}/org/delivery-addresses`, payload);
        toast.success("Leveringsadresse oprettet");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()} data-testid="delivery-address-modal">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between sticky top-0 bg-white dark:bg-slate-800 z-10">
          <p className="font-bold text-slate-900 dark:text-white">{isEdit ? "Rediger leveringsadresse" : "Ny leveringsadresse"}</p>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Navn *</label>
            <input value={label} onChange={e => setLabel(e.target.value)}
              placeholder='fx "Hovedindgang", "Bagside ved port 3"'
              className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
              data-testid="delivery-label-input" />
          </div>
          <div>
            <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Gade og nr. *</label>
            <input value={street} onChange={e => setStreet(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
              data-testid="delivery-street-input" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Postnr. *</label>
              <input value={postcode} onChange={e => setPostcode(e.target.value)}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
                data-testid="delivery-postcode-input" />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">By *</label>
              <input value={city} onChange={e => setCity(e.target.value)}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
                data-testid="delivery-city-input" />
            </div>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
            Adressen kan tilknyttes en bestemt ugedag eller helligdag i fanen <em>Åbnings- og lukketidspunkter</em>.
          </p>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2 sticky bottom-0 bg-white dark:bg-slate-800">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            data-testid="save-delivery-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
}




/* ============================ KAPACITETSMÅL TAB ============================ */
function CapacityMeasuresTab({ locations = [] }) {
  const initialCode = locations[0]?.code || locations[0]?.location_code || "";
  const [activeCode, setActiveCode] = useState(initialCode);
  useEffect(() => {
    if (!activeCode && locations[0]) {
      setActiveCode(locations[0].code || locations[0].location_code);
    }
  }, [locations, activeCode]);
  const activeLoc = locations.find(l => (l.code || l.location_code) === activeCode);

  if (locations.length === 0) {
    return (
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
        Ingen lokationer tilknyttet din konto endnu.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="capacity-measures-tab">
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lokation:</p>
          {locations.map(l => {
            const code = l.code || l.location_code;
            const on = code === activeCode;
            return (
              <button key={code} onClick={() => setActiveCode(code)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"}`}
                data-testid={`capacity-loc-${code}`}>
                {l.name}
              </button>
            );
          })}
        </div>
      )}
      <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
        Kapacitetsmål-bibliotek
        {activeLoc && <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {activeLoc.name}</span>}
      </h2>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Standardiserede kapacitetsmål (label + volumen i m³) der kan tilknyttes containere.
        Bruges blandt andet ved oprettelse/redigering af containere og vises på bestillingssiden.
      </p>
      <CapacityMeasuresSection locationCode={activeCode} />
    </div>
  );
}

function CapacityMeasuresSection({ locationCode }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  const fetchAll = useCallback(async () => {
    if (!locationCode) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/org/capacity-measures?location_code=${locationCode}`);
      setItems(r.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [locationCode]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const remove = async (cm) => {
    if (!window.confirm(`Slet "${cm.label}"?`)) return;
    try {
      await axios.delete(`${API}/org/capacity-measures/${cm.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Indlæser…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-700 dark:text-slate-300 font-semibold">
          {items.length} kapacitetsmål
        </p>
        <button onClick={() => setEditing("new")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
          data-testid="add-capacity-btn">
          <Plus className="w-3.5 h-3.5" /> Nyt kapacitetsmål
        </button>
      </div>

      {items.length === 0 ? (
        <div className="bg-slate-50 dark:bg-slate-800/50 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-6 text-center text-sm text-slate-500 dark:text-slate-400">
          Ingen kapacitetsmål endnu. Klik <strong>Nyt kapacitetsmål</strong> for at oprette det første.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map(cm => (
            <div key={cm.id} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4" data-testid={`capacity-row-${cm.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-slate-900 dark:text-white truncate">{cm.label}</p>
                  <p className="text-xs text-slate-500 mt-1 inline-flex items-center gap-1">
                    <Ruler className="w-3 h-3" /> {cm.volume_m3 ?? "-"} m³
                  </p>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => setEditing(cm)} className="p-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-950/30 text-slate-500 hover:text-blue-600"
                    title="Rediger" data-testid={`edit-capacity-${cm.id}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button onClick={() => remove(cm)} className="p-1.5 rounded hover:bg-rose-50 dark:hover:bg-rose-950/30 text-slate-500 hover:text-rose-600"
                    title="Slet" data-testid={`delete-capacity-${cm.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <CapacityMeasureModal
          locationCode={locationCode}
          measure={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}
    </div>
  );
}

function CapacityMeasureModal({ locationCode, measure, onClose, onSaved }) {
  const isEdit = !!measure;
  const [label, setLabel] = useState(measure?.label || "");
  const [volume, setVolume] = useState(measure?.volume_m3 ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    // Fase 15.55b (2026-02-22): Label + Volumen obligatoriske.
    if (!label.trim()) { toast.error("Label er påkrævet"); return; }
    const volStr = String(volume ?? "").trim();
    if (volStr === "") { toast.error("Volumen er påkrævet"); return; }
    const volNum = parseFloat(volStr);
    if (!Number.isFinite(volNum) || volNum <= 0) {
      toast.error("Volumen skal være et tal > 0");
      return;
    }
    const payload = {
      location_code: locationCode,
      label: label.trim(),
      volume_m3: volNum,
    };
    setSaving(true);
    try {
      if (isEdit) {
        await axios.put(`${API}/org/capacity-measures/${measure.id}`, payload);
        toast.success("Kapacitetsmål opdateret");
      } else {
        await axios.post(`${API}/org/capacity-measures`, payload);
        toast.success("Kapacitetsmål oprettet");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" onClick={onClose} data-testid="capacity-modal">
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative bg-white dark:bg-slate-800 rounded-xl shadow-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <p className="font-bold text-slate-900 dark:text-white">{isEdit ? "Rediger kapacitetsmål" : "Nyt kapacitetsmål"}</p>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Label *</label>
            <input value={label} onChange={e => setLabel(e.target.value)}
              placeholder='fx "20 m³ open-top"'
              className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
              data-testid="capacity-label-input" />
          </div>
          <div>
            <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Volumen (m³) *</label>
            <input type="number" min="0" step="0.1" value={volume} onChange={e => setVolume(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
              data-testid="capacity-volume-input" />
          </div>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            data-testid="save-capacity-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================ DELTA NOTIFICATIONS POPUP ============================ */
/* Persistent pop-up der altid vises når LA har ubehandlede helligdags-delta'er.
   Pr. 2026-06-15 brugerkrav: Lukker man X'et, BLIVER den lukket - polling
   må IKKE genåbne medmindre der kommer et NYT (uset) delta. Brugeren kan
   altid genåbne via badge'en nederst-højre. Escape lukker også. */
function DeltaNotificationsPopup({ locations = [] }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(null); // {notif, delta}
  const lastCountRef = useRef(0);

  const fetchPending = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/org/holiday-deltas/pending`);
      const data = r.data || [];
      setItems(data);
      // Broadcast count så header-genvejen kan vise badge UDEN at have egen polling.
      try { window.dispatchEvent(new CustomEvent("cf:delta-count", { detail: { count: data.length } })); } catch (_) {}
      if (data.length > lastCountRef.current) setOpen(true);
      lastCountRef.current = data.length;
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    fetchPending();
    const t = setInterval(fetchPending, 60000); // poll hver 60s
    return () => clearInterval(t);
  }, [fetchPending]);

  // Lyt efter "åbn-delta"-event fra header-genvejen (Genåbn senest lukkede delta).
  // Brugerkrav 2026-06-15: Hurtig åbning uden at vente på næste polling-cyklus.
  useEffect(() => {
    const onOpen = () => { if (items.length > 0) setOpen(true); else fetchPending(); };
    window.addEventListener("cf:open-delta-popup", onOpen);
    return () => window.removeEventListener("cf:open-delta-popup", onOpen);
  }, [items.length, fetchPending]);

  // Escape lukker popup (men ikke den indre review-modal - den lukker via egen onClose).
  useEffect(() => {
    if (!open || active) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, active]);

  if (items.length === 0) return null;
  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 bg-amber-500 hover:bg-amber-600 text-white rounded-full px-4 py-2 shadow-lg inline-flex items-center gap-2"
        data-testid="delta-popup-reopen">
        <Bell className="w-4 h-4" /> {items.length} ventende delta
      </button>
    );
  }

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" data-testid="delta-popup"
        onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 bg-amber-50 dark:bg-amber-950/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Megaphone className="w-5 h-5 text-amber-600" />
              <div>
                <p className="font-bold text-slate-900 dark:text-white">Nye helligdags-opdateringer</p>
                <p className="text-xs text-slate-500">{items.length} ubehandlet{items.length === 1 ? "" : "e"} delta - gennemgå og importér til din helligdagskalender.</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="p-1.5 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30"
              title="Minimér (vises som badge nederst)" data-testid="delta-popup-minimize">
              <X className="w-4 h-4 text-slate-500" />
            </button>
          </div>
          <div className="p-5 overflow-y-auto space-y-3">
            {items.map(n => (
              <div key={n.id} className="border border-slate-200 dark:border-slate-700 rounded-lg p-3" data-testid={`delta-notif-${n.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-900 dark:text-white">{n.delta?.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {(n.delta?.operations || []).length} operation{(n.delta?.operations || []).length === 1 ? "" : "er"}
                      {n.delta?.year ? ` · ${n.delta.year}` : ""}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(n.delta?.operations || []).slice(0, 4).map((o, i) => (
                        <span key={i} className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          o.op === "add" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                          : o.op === "delete" ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
                          : "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                        }`}>
                          {o.op === "add" ? "Tilføj" : o.op === "delete" ? "Slet" : "Ændr"}: {o.match_name || o.new_name}
                          {o.new_date ? ` · ${o.new_date}` : ""}
                        </span>
                      ))}
                      {(n.delta?.operations || []).length > 4 && (
                        <span className="text-[11px] text-slate-400">+{n.delta.operations.length - 4} mere</span>
                      )}
                    </div>
                  </div>
                  <button onClick={() => setActive(n)}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold whitespace-nowrap"
                    data-testid={`open-delta-${n.id}`}>
                    Gennemgå
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {active && (
        <DeltaReviewModal
          notif={active}
          locations={locations}
          onClose={() => setActive(null)}
          onDone={() => { setActive(null); fetchPending(); }}
        />
      )}
    </>
  );
}

function DeltaReviewModal({ notif, locations, onClose, onDone }) {
  const [ops, setOps] = useState(() => (notif.delta?.operations || []).map(o => ({ ...o, _skip: false })));
  const [calendars, setCalendars] = useState([]);
  // Brugerkrav 2026-06-15 (Krav 2): Multi-publish via flere kalendere på én gang.
  const [pickedCalIds, setPickedCalIds] = useState([]);
  const [busy, setBusy] = useState(null); // "import" | "reject"

  // Pre-populerede `applied_calendar_ids` fra notif - så vi ikke gentager
  // publicering til samme kalender via popup-flowet. (UI'et for re-publish
  // ligger i den dedikerede "Modtagne delta'er"-tab.)
  const alreadyApplied = useMemo(() => new Set(notif.applied_calendar_ids || []), [notif]);

  useEffect(() => {
    // Hent alle helligdagskalendere på tværs af alle administrerede pladser
    const all = [];
    Promise.all((locations || []).map(l => {
      const code = l.code || l.location_code;
      return axios.get(`${API}/org/holiday-calendars?location_code=${code}`)
        .then(r => (r.data || []).forEach(c => all.push({ ...c, _locName: l.name })))
        .catch(() => {});
    })).then(() => {
      const active = all.filter(c => c.is_active !== false);
      setCalendars(active);
      // Auto-select hvis der kun er én aktiv kalender - uanset om den allerede
      // er publiceret til (LA kan retry idempotent for at fixe tidligere fejl).
      if (active.length === 1) setPickedCalIds([active[0].id]);
    });
  }, [locations]);

  const toggleCal = (id) => {
    setPickedCalIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const update = (i, k, v) => setOps(prev => prev.map((o, idx) => idx === i ? { ...o, [k]: v } : o));

  const importDelta = async () => {
    if (pickedCalIds.length === 0) { toast.error("Vælg mindst én helligdagskalender"); return; }
    const filtered = ops.filter(o => !o._skip).map(({ _skip, ...rest }) => rest);
    if (filtered.length === 0) { toast.error("Vælg mindst én operation"); return; }
    setBusy("import");
    try {
      const r = await axios.post(`${API}/org/holiday-deltas/${notif.id}/import`, {
        calendar_ids: pickedCalIds,
        operations: filtered,
      });
      toast.success(
        `Importeret til ${pickedCalIds.length} kalender${pickedCalIds.length === 1 ? "" : "e"}: ` +
        `${r.data.added} tilføjet · ${r.data.modified} ændret · ${r.data.deleted} slettet`
      );
      onDone();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(null); }
  };

  const rejectDelta = async () => {
    if (!window.confirm("Afvis dette delta? Det vil ikke længere være synligt.")) return;
    setBusy("reject");
    try {
      await axios.post(`${API}/org/holiday-deltas/${notif.id}/reject`);
      toast.success("Delta afvist");
      onDone();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-[1000] bg-black/60 flex items-center justify-center p-4" data-testid="delta-review-modal">
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <div>
            <p className="font-bold text-slate-900 dark:text-white">{notif.delta?.name}</p>
            <p className="text-xs text-slate-500">Rediger eller spring enkelte operationer over inden import.</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        <div className="p-5 overflow-y-auto space-y-3 flex-1">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-2">
              Vælg helligdagskalendere (vælg flere - delta sendes til hver)
            </label>
            {calendars.length === 0 ? (
              <p className="text-xs text-amber-600 mt-1">
                Ingen aktive helligdagskalendere. Opret en under "Åbnings- og lukketidspunkter".
              </p>
            ) : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2"
                data-testid="delta-pick-calendars">
                {calendars.map(c => {
                  const applied = alreadyApplied.has(c.id);
                  const on = pickedCalIds.includes(c.id);
                  return (
                    <label
                      key={c.id}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer ${
                        on
                          ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-100"
                          : applied
                            ? "bg-slate-50 dark:bg-slate-700/30 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700/50"
                            : "hover:bg-slate-50 dark:hover:bg-slate-700/40 text-slate-700 dark:text-slate-200"
                      }`}
                      data-testid={`delta-cal-${c.id}`}
                    >
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => toggleCal(c.id)}
                        className="w-4 h-4 accent-emerald-500"
                      />
                      <span className="flex-1">
                        {c._locName} · {c.name}{c.year ? ` (${c.year})` : ""}
                      </span>
                      {applied && (
                        <span className="text-[10px] uppercase tracking-wider font-semibold text-amber-600 dark:text-amber-400" title="Du har allerede publiceret hertil - du kan trykke igen for at gen-anvende (idempotent på navn+dato)">
                          Allerede publiceret · klik for at gen-publicere
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}
            <p className="text-[10px] text-slate-400 mt-1">
              {pickedCalIds.length} kalender{pickedCalIds.length === 1 ? "" : "e"} valgt.
              Du kan altid publicere delta'et til flere kalendere senere via fanen "Modtagne delta'er".
            </p>
          </div>
          <div className="space-y-2">
            {ops.map((o, i) => {
              const color = o.op === "add" ? "emerald" : o.op === "delete" ? "rose" : "blue";
              return (
                <div key={i} className={`border-l-4 border-${color}-500 bg-slate-50 dark:bg-slate-900/40 rounded p-3 ${o._skip ? "opacity-40" : ""}`} data-testid={`review-op-${i}`}>
                  <div className="flex items-start gap-2">
                    <input type="checkbox" checked={!o._skip} onChange={() => update(i, "_skip", !o._skip)}
                      className="mt-1 w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500"
                      data-testid={`review-op-include-${i}`} />
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <input value={o.match_name || ""} onChange={e => update(i, "match_name", e.target.value)}
                        placeholder={o.op === "add" ? "Nyt navn" : "Navn der skal matches"}
                        className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm"
                        data-testid={`review-match-${i}`} />
                      {o.op !== "delete" && o.op === "modify" && (
                        <input value={o.new_name || ""} onChange={e => update(i, "new_name", e.target.value)}
                          placeholder="Nyt navn (valgfri)"
                          className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm"
                          data-testid={`review-new-name-${i}`} />
                      )}
                      {o.op !== "delete" && (
                        <input type="date" value={o.new_date || ""} onChange={e => update(i, "new_date", e.target.value)}
                          className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm ${o.op === "add" ? "sm:col-span-2" : ""}`}
                          data-testid={`review-date-${i}`} />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-between items-center gap-2">
          <button onClick={rejectDelta} disabled={busy !== null}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-rose-100 hover:bg-rose-200 dark:bg-rose-950/30 dark:hover:bg-rose-950 text-rose-700 dark:text-rose-300 disabled:opacity-60"
            data-testid="reject-delta-btn">
            {busy === "reject" ? <Loader2 className="w-4 h-4 animate-spin" /> : "Afvis ændringer"}
          </button>
          <div className="flex gap-2">
            <button onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
              Beslut senere
            </button>
            <button onClick={importDelta} disabled={busy !== null || pickedCalIds.length === 0}
              className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
              data-testid="import-delta-btn">
              {busy === "import" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Indsæt i {pickedCalIds.length || ""} kalender{pickedCalIds.length === 1 ? "" : "e"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================ MODTAGNE DELTA'ER TAB (30 dage) ============================ */
// Brugerkrav 2026-06-15 (Krav 2): LA kan gen-publicere modtagne delta'er til
// flere kalendere over tid. Delta'er forbliver synlige i 30 dage uanset status.
function ReceivedDeltasTab({ locations = [] }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null); // {notif, delta} til republish-modal

  const fetchReceived = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/org/holiday-deltas/received?days=30`);
      setItems(r.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchReceived(); }, [fetchReceived]);

  // Index alle kalender-navne for at vise "Publiceret til X, Y, Z"
  const [calIndex, setCalIndex] = useState({});
  useEffect(() => {
    const all = {};
    Promise.all((locations || []).map(l => {
      const code = l.code || l.location_code;
      return axios.get(`${API}/org/holiday-calendars?location_code=${code}`)
        .then(r => (r.data || []).forEach(c => { all[c.id] = `${l.name} · ${c.name}`; }))
        .catch(() => {});
    })).then(() => setCalIndex(all));
  }, [locations]);

  if (loading) {
    return <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>;
  }

  if (items.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-10 text-center"
        data-testid="received-deltas-empty">
        <Bell className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-500">Ingen delta'er modtaget de seneste 30 dage.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="received-deltas-tab">
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-xs text-blue-800 dark:text-blue-200">
        Her ses alle delta'er du har modtaget de seneste 30 dage - også dem du allerede har publiceret.
        Klik "Publicér igen" for at sende et delta til endnu en kalender.
      </div>
      {items.map(n => {
        const statusColor = n.status === "pending"
          ? "amber"
          : n.status === "rejected" ? "rose" : "emerald";
        const statusLabel = n.status === "pending"
          ? "Afventer"
          : n.status === "rejected" ? "Afvist" : "Publiceret";
        const created = (n.created_at || "").slice(0, 10);
        const available = n.available_calendar_ids || [];
        const applied = n.applied_calendar_ids || [];
        return (
          <div key={n.id} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4"
            data-testid={`received-delta-${n.id}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-bold text-slate-900 dark:text-white">{n.delta?.name}</p>
                  <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full font-semibold bg-${statusColor}-100 text-${statusColor}-700 dark:bg-${statusColor}-950/30 dark:text-${statusColor}-300`}>
                    {statusLabel}
                  </span>
                  {n.delta?.year && (
                    <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
                      {n.delta.year}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Modtaget {created} · {(n.delta?.operations || []).length} operation
                  {(n.delta?.operations || []).length === 1 ? "" : "er"}
                </p>
                {applied.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                      Publiceret til:
                    </span>
                    {applied.map(cid => (
                      <span key={cid} className="text-[10px] bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded font-semibold">
                        {calIndex[cid] || cid.slice(0, 6)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1.5 shrink-0">
                <button onClick={() => setActive(n)}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold whitespace-nowrap"
                  data-testid={`republish-delta-${n.id}`}>
                  {applied.length > 0 ? "Publicér igen" : "Gennemgå"}
                </button>
              </div>
            </div>
          </div>
        );
      })}
      {active && (
        <DeltaReviewModal
          notif={active}
          locations={locations}
          onClose={() => setActive(null)}
          onDone={() => { setActive(null); fetchReceived(); }}
        />
      )}
    </div>
  );
}

/* ============================ RAPPORT OG STATISTIK TAB ============================ */
function ReportsTab({ locations = [] }) {
  // Fase 15.53 (2026-02-22): Multi-location rapportering - brugeren kan
  // vælge én eller flere lokationer og se data aggregeret på tværs. Tom
  // selection = vis ALLE lokationer (sum). Backward compatible: hvis
  // brugeren har præcis ÉN lokation, fungerer det som før.
  // Fase 18.19 (2026-02-28): allCodes/effectiveCodes memoized - undgår at
  // nye array-referencer pr. render trigger fetchData/useEffect-cyklus i
  // ReportsSection, hvilket forårsagede ResizeObserver+chart-loop og
  // konstant scroll-skub hvert 5. sekund.
  const allCodes = useMemo(
    () => locations.map(l => l.code || l.location_code).filter(Boolean),
    [locations]
  );
  const [selectedCodes, setSelectedCodes] = useState(() => new Set(
    locations[0] ? [locations[0].code || locations[0].location_code] : [],
  ));
  useEffect(() => {
    if (selectedCodes.size === 0 && locations[0]) {
      setSelectedCodes(new Set([locations[0].code || locations[0].location_code]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations]);

  // Stabil reference: kun ny array når valg eller allCodes faktisk skifter.
  const effectiveCodesKey = selectedCodes.size > 0
    ? Array.from(selectedCodes).sort().join("|")
    : allCodes.slice().sort().join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const effectiveCodes = useMemo(
    () => selectedCodes.size > 0 ? Array.from(selectedCodes) : allCodes,
    [effectiveCodesKey, allCodes]
  );

  if (locations.length === 0) {
    return (
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
        Ingen lokationer tilknyttet din konto endnu.
      </div>
    );
  }
  const displayName = effectiveCodes.length === 1
    ? (locations.find(l => (l.code || l.location_code) === effectiveCodes[0])?.name || effectiveCodes[0])
    : `${effectiveCodes.length} lokationer`;

  return (
    <div className="space-y-6" data-testid="reports-tab">
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap" data-testid="reports-loc-tabs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mr-1">Lokationer:</p>
          {locations.map(l => {
            const code = l.code || l.location_code;
            const on = selectedCodes.has(code);
            return (
              <button key={code}
                onClick={() => {
                  const next = new Set(selectedCodes);
                  if (on) next.delete(code); else next.add(code);
                  setSelectedCodes(next);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-emerald-400"}`}
                data-testid={`reports-loc-${code}`}>
                {on && <Check className="w-3 h-3" />}
                {l.name}
              </button>
            );
          })}
          <div className="flex gap-1 ml-auto">
            <button onClick={() => setSelectedCodes(new Set(allCodes))}
              className="text-[11px] font-bold text-emerald-600 hover:text-emerald-700 px-2 py-1"
              data-testid="reports-loc-select-all">Vælg alle</button>
            <button onClick={() => setSelectedCodes(new Set([allCodes[0]]))}
              className="text-[11px] font-bold text-slate-500 hover:text-slate-700 px-2 py-1"
              data-testid="reports-loc-reset">Nulstil</button>
          </div>
        </div>
      )}
      <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
        Rapportering
        <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {displayName}</span>
      </h2>
      <ReportsSection
        locationCodes={effectiveCodes}
        locationName={displayName}
        key={effectiveCodes.join("|")}
      />
    </div>
  );
}

const PERIOD_LABELS = [
  { id: "day", label: "I dag" },
  { id: "week", label: "Uge" },
  { id: "month", label: "Måned" },
  { id: "3months", label: "3 mdr." },
  { id: "6months", label: "6 mdr." },
  { id: "year", label: "År" },
  { id: "custom", label: "Brugerdef." },
];

function ReportsSection({ locationCodes = [], locationName }) {
  const [period, setPeriod] = useState("month");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  // Pre-load PDF lib only - Excel-eksport bruger nu vores ExcelJS-helper
  // (`/lib/excelExport.js`) som producerer ÉT veldesignet ark med KPI's,
  // sektioner, totals, AutoFilter og frozen header. Brugerkrav 2026-06-15.
  const pdfRef = useRef(null);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const jp = await import("jspdf");
        const at = await import("jspdf-autotable");
        if (active) pdfRef.current = { jsPDF: jp.jsPDF || jp.default, autoTable: at.default || at.autoTable };
      } catch (_) { /* network/CDN fejl - vises ved klik */ }
    })();
    return () => { active = false; };
  }, []);

  // Robust download-helper. Vi bruger `file-saver` som er IE/iframe-venlig
  // og falder tilbage til en manuel <a download>+click + window.open hvis
  // file-saver selv fejler. Brugerens browser blokerede tidligere blob-clicks
  // på grund af Emergents preview-iframe; saveAs() håndterer dette korrekt.
  const triggerDownload = (blob, filename) => {
    try {
      saveAs(blob, filename);
      return true;
    } catch (e) {
      // Fallback 1: manual anchor + click
      const url = URL.createObjectURL(blob);
      try {
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.rel = "noopener";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          try { document.body.removeChild(a); } catch (_) {}
          setTimeout(() => URL.revokeObjectURL(url), 4000);
        }, 100);
        return true;
      } catch (_) {
        // Fallback 2: open in new tab
        try { window.open(url, "_blank", "noopener"); } catch (__) {}
        setTimeout(() => URL.revokeObjectURL(url), 8000);
        return false;
      }
    }
  };

  const fetchData = useCallback(async () => {
    if (!locationCodes || locationCodes.length === 0) return;
    setLoading(true);
    try {
      // Fase 15.53 (2026-02-22): Multi-location aggregation. Fetch én request
      // pr. lokation parallelt og slå data sammen client-side. Bevarer
      // backend's eksisterende `/org/reports/orders?location_code=X` endpoint
      // uden ændringer.
      const responses = await Promise.all(locationCodes.map(code => {
        const params = new URLSearchParams({ location_code: code, period });
        if (period === "custom") {
          if (!start || !end) return Promise.resolve({ data: null });
          params.set("start", start); params.set("end", end);
        }
        return axios.get(`${API}/org/reports/orders?${params.toString()}`);
      }));
      const datasets = responses.map(r => r.data).filter(Boolean);
      if (datasets.length === 0) { setData(null); return; }
      if (datasets.length === 1) { setData(datasets[0]); return; }
      // Merge: sum numerical totals, concat arrays, keep first period range.
      const merged = JSON.parse(JSON.stringify(datasets[0]));
      const sumField = (obj, src, key) => { obj[key] = (obj[key] || 0) + (src[key] || 0); };
      for (const d of datasets.slice(1)) {
        sumField(merged, d, "total_orders");
        sumField(merged, d, "total_weight_kg");
        sumField(merged, d, "total_co2_kg");
        sumField(merged, d, "cancelled_count");
        sumField(merged, d, "not_completed_count");
        // Concat orders array (if present)
        if (Array.isArray(merged.orders) && Array.isArray(d.orders)) {
          merged.orders = merged.orders.concat(d.orders);
        }
        // Merge by_material map
        if (merged.by_material && d.by_material) {
          for (const [mat, v] of Object.entries(d.by_material)) {
            if (!merged.by_material[mat]) merged.by_material[mat] = { count: 0, weight_kg: 0, co2_kg: 0 };
            merged.by_material[mat].count += (v.count || 0);
            merged.by_material[mat].weight_kg += (v.weight_kg || 0);
            merged.by_material[mat].co2_kg += (v.co2_kg || 0);
          }
        }
      }
      merged._multi_location = true;
      merged._location_codes = locationCodes;
      setData(merged);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
    // Fase 18.19 (2026-02-28): Brug join("|") som primitiv dep i stedet for
    // array-referencen - så fetchData IKKE re-skabes ved hver render selv
    // hvis forælderen sender en ny (men indholdsmæssigt ens) array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationCodes.slice().sort().join("|"), period, start, end]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = async () => {
    if (!data) return;
    try {
      // Fase 15.53 (2026-02-22): Multi-location export - `locationCodes` er nu
      // et array. Bruger første kode som suffix hvis kun én er valgt, ellers
      // markerer rapporten som "multi".
      const codeForFilename = locationCodes.length === 1 ? locationCodes[0] : "multi";
      const codeForSubtitle = locationCodes.length === 1 ? locationCodes[0] : `${locationCodes.length} lokationer`;
      const safeName = (locationName || codeForFilename).replace(/\s+/g, "_");
      await exportReportXLSX({
        data,
        title: `Lokations-rapport - ${locationName || codeForSubtitle}`,
        subtitle: `${codeForSubtitle} · Periode ${data.start} til ${data.end}`,
        includeByLocation: locationCodes.length > 1,
        filename: `rapport-${safeName}-${data.start}-${data.end}.xlsx`,
      });
      toast.success("Excel-fil downloadet");
    } catch (e) {
      console.error("[exportCSV]", e);
      toast.error("Kunne ikke generere Excel-fil: " + (e?.message || "ukendt fejl"));
    }
  };

  const exportPDF = () => {
    if (!data) return;
    const lib = pdfRef.current;
    if (!lib || !lib.jsPDF || !lib.autoTable) {
      toast.error("PDF-bibliotek indlæses stadig. Prøv igen om et øjeblik.");
      return;
    }
    try {
      const { jsPDF, autoTable } = lib;
      const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
      doc.setFontSize(16);
      doc.text(`Rapport ${data.start} -> ${data.end}`, 40, 40);
      doc.setFontSize(11);
      doc.text(`Total bestillinger: ${data.total_orders}`, 40, 60);
      doc.text(`Voerksteder: ${data.workshop_count}`, 40, 75);
      doc.text(`Afventer (i perioden): ${data.pending_in_period}`, 40, 90);
      doc.text(`Haste bestillinger: ${data.urgent_count ?? 0}`, 40, 105);
      autoTable(doc, {
        head: [["Materiale", "Antal", "Vaegt (kg)"]],
        body: (data.by_material || []).map(m => [m.name, m.count, m.weight]),
        startY: 130,
      });
      autoTable(doc, {
        head: [["Medarbejder", "Antal bestillinger"]],
        body: (data.by_employee || []).map(e => [e.name, e.count]),
      });
      const blob = doc.output("blob");
      const ok = triggerDownload(blob, `rapport-${data.start}-${data.end}.pdf`);
      toast.success(ok ? "PDF downloadet" : "PDF åbnet i ny tab - højreklik og 'Gem som...'");
    } catch (e) {
      console.error("[exportPDF]", e);
      toast.error("Kunne ikke generere PDF: " + (e?.message || "ukendt fejl"));
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3">
        {PERIOD_LABELS.map(p => (
          <button key={p.id} onClick={() => setPeriod(p.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold ${period === p.id ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"}`}
            data-testid={`period-${p.id}`}>{p.label}</button>
        ))}
        {period === "custom" && (
          <div className="flex items-center gap-1 ml-2">
            <input type="date" value={start} onChange={e => setStart(e.target.value)}
              className="px-2 py-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-xs"
              data-testid="period-custom-start" />
            <span className="text-slate-400">→</span>
            <input type="date" value={end} onChange={e => setEnd(e.target.value)}
              className="px-2 py-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-xs"
              data-testid="period-custom-end" />
          </div>
        )}
        <div className="ml-auto flex gap-2">
          <button onClick={exportCSV} disabled={!data}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-100 text-xs font-bold disabled:opacity-50"
            data-testid="export-excel-btn">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
          </button>
          <button onClick={exportPDF} disabled={!data}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-100 text-xs font-bold disabled:opacity-50"
            data-testid="export-pdf-btn">
            <FileDown className="w-3.5 h-3.5" /> PDF
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-10 text-center"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
      ) : !data ? (
        <p className="text-sm text-slate-500">Ingen data.</p>
      ) : (
        <ReportsCharts data={data} />
      )}
    </div>
  );
}

function ReportsCharts({ data }) {
  // Lazy import recharts (kun når tab er aktiv)
  const [R, setR] = useState(null);
  useEffect(() => {
    import("recharts").then(m => setR(m));
  }, []);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="rounded-xl border p-4 bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800" data-testid="tile-total">
          <p className="text-xs font-bold uppercase text-emerald-700 dark:text-emerald-300">I alt</p>
          <p className="text-3xl font-bold text-emerald-700 dark:text-emerald-300 mt-1">{data.total_orders}</p>
        </div>
        <div className="rounded-xl border p-4 bg-purple-50 dark:bg-purple-950/30 border-purple-200 dark:border-purple-800" data-testid="tile-workshops">
          <p className="text-xs font-bold uppercase text-purple-700 dark:text-purple-300">Værksteder</p>
          <p className="text-3xl font-bold text-purple-700 dark:text-purple-300 mt-1">{data.workshop_count}</p>
        </div>
        <div className="rounded-xl border p-4 bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800" data-testid="tile-pending-period">
          <p className="text-xs font-bold uppercase text-amber-700 dark:text-amber-300">Afventer (periode)</p>
          <p className="text-3xl font-bold text-amber-700 dark:text-amber-300 mt-1">{data.pending_in_period}</p>
        </div>
        <div className="rounded-xl border p-4 bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800" data-testid="tile-urgent">
          <p className="text-xs font-bold uppercase text-rose-700 dark:text-rose-300">Haste bestillinger</p>
          <p className="text-3xl font-bold text-rose-700 dark:text-rose-300 mt-1">{data.urgent_count ?? 0}</p>
        </div>
        {/* Fase 9 refactor (2026-06-18): CO2-aftryk synligt for Location Admin */}
        <div className="rounded-xl border p-4 bg-teal-50 dark:bg-teal-950/30 border-teal-200 dark:border-teal-800" data-testid="tile-co2">
          <p className="text-xs font-bold uppercase text-teal-700 dark:text-teal-300 flex items-center gap-1">
            <Leaf className="w-3 h-3" /> CO2 (kg)
          </p>
          <p className="text-3xl font-bold text-teal-700 dark:text-teal-300 mt-1">{(data.total_co2_kg ?? 0).toLocaleString("da-DK")}</p>
        </div>
      </div>

      {R && (
        <>
          {/* Trend chart: bestillinger pr. tidsenhed */}
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
            <p className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-2 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-emerald-500" />
              Bestillinger pr. {data.granularity === "hour" ? "time" : data.granularity === "day" ? "dag" : data.granularity === "week" ? "uge" : "måned"}
            </p>
            {data.pattern.length === 0 ? (
              <p className="text-xs text-slate-400 italic py-6 text-center">Ingen data i perioden.</p>
            ) : (
              <R.ResponsiveContainer width="100%" height={260} debounce={150}>
                <R.BarChart data={data.pattern}>
                  <R.CartesianGrid strokeDasharray="3 3" />
                  <R.XAxis dataKey="bucket" fontSize={10} />
                  <R.YAxis fontSize={10} />
                  <R.Tooltip />
                  <R.Bar dataKey="count" fill="#f97316" radius={[8, 8, 0, 0]} />
                </R.BarChart>
              </R.ResponsiveContainer>
            )}
          </div>

          {/* Fase 9 refactor (2026-06-18): CO2-rapport (også for Location Admin) */}
          {((data.co2_over_time || []).length > 0 || (data.by_co2_type || []).length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4" data-testid="ladmin-co2-over-time">
                <p className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-1 flex items-center gap-2">
                  <Leaf className="w-4 h-4 text-emerald-500" /> CO2-udvikling over tid
                </p>
                <p className="text-[11px] text-slate-500 mb-2">
                  Total {(data.total_co2_kg ?? 0).toLocaleString("da-DK")} kg CO2 · {(data.total_weight_kg ?? 0).toLocaleString("da-DK")} kg materiale
                </p>
                {(data.co2_over_time || []).length === 0 ? (
                  <p className="text-xs text-slate-400 italic py-6 text-center">Ingen CO2-data i perioden.</p>
                ) : (
                  <R.ResponsiveContainer width="100%" height={260} debounce={150}>
                    <R.LineChart data={data.co2_over_time}>
                      <R.CartesianGrid strokeDasharray="3 3" />
                      <R.XAxis dataKey="date" fontSize={10} stroke="#64748b" />
                      <R.YAxis fontSize={10} stroke="#64748b" label={{ value: "kg CO2", angle: -90, position: "insideLeft", fontSize: 10 }} />
                      <R.Tooltip formatter={(v) => [`${v.toLocaleString("da-DK")} kg`, "CO2"]} />
                      <R.Line type="monotone" dataKey="co2_kg" stroke="#059669" strokeWidth={2} dot={{ r: 3, fill: "#059669" }} />
                    </R.LineChart>
                  </R.ResponsiveContainer>
                )}
              </div>

              <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4" data-testid="ladmin-co2-by-material">
                <p className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-1 flex items-center gap-2">
                  <Leaf className="w-4 h-4 text-emerald-500" /> CO2 pr. materiale
                </p>
                <p className="text-[11px] text-slate-500 mb-2">Hvilke materialer trækker mest CO2</p>
                {(data.by_co2_type || []).filter(t => t.co2_kg > 0).length === 0 ? (
                  <p className="text-xs text-slate-400 italic py-6 text-center">Endnu ingen CO2 beregnet (afventer chaufførens vægt).</p>
                ) : (
                  <R.ResponsiveContainer width="100%" height={260} debounce={150}>
                    <R.BarChart data={(data.by_co2_type || []).filter(t => t.co2_kg > 0).slice(0, 8)}>
                      <R.CartesianGrid strokeDasharray="3 3" />
                      <R.XAxis dataKey="name" fontSize={10} stroke="#64748b" />
                      <R.YAxis fontSize={10} stroke="#64748b" label={{ value: "kg CO2", angle: -90, position: "insideLeft", fontSize: 10 }} />
                      <R.Tooltip formatter={(v) => [`${v.toLocaleString("da-DK")} kg`, "CO2"]} />
                      <R.Bar dataKey="co2_kg" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </R.BarChart>
                  </R.ResponsiveContainer>
                )}
                {(data.by_co2_type || []).filter(t => t.co2_kg > 0).length > 0 && (
                  <div className="mt-3 space-y-1.5 text-xs">
                    {data.by_co2_type.filter(t => t.co2_kg > 0).slice(0, 6).map(t => (
                      <div key={t.name} className="flex items-center justify-between gap-2 py-1 border-b border-slate-100 dark:border-slate-700/50 last:border-0">
                        <span className="font-semibold text-slate-700 dark:text-slate-200 truncate" title={t.name}>{t.name}</span>
                        <span className="text-slate-500 dark:text-slate-400 tabular-nums whitespace-nowrap">
                          {t.weight_kg.toLocaleString("da-DK")} kg →{" "}
                          <strong className="text-emerald-700 dark:text-emerald-300">{t.co2_kg.toLocaleString("da-DK")} kg CO2</strong>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Materiale detaljer-tabel (rang | navn | antal | total vægt | fordeling-bar) */}
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
              <span className="inline-flex w-7 h-7 rounded-lg bg-orange-100 dark:bg-orange-950/40 text-orange-600 dark:text-orange-300 items-center justify-center">
                <FileText className="w-4 h-4" />
              </span>
              <p className="font-heading font-bold text-lg text-slate-900 dark:text-white">Materiale detaljer</p>
            </div>
            {data.by_material.length === 0 ? (
              <p className="text-xs text-slate-400 italic py-6 text-center">Ingen data.</p>
            ) : (() => {
              const top = data.by_material.slice(0, 25);
              const maxCount = top[0]?.count || 1;
              return (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="material-detail-table">
                    <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500 text-xs uppercase tracking-wider">
                      <tr>
                        <th className="px-4 py-2 text-left font-bold w-12">#</th>
                        <th className="px-4 py-2 text-left font-bold">Materiale</th>
                        <th className="px-4 py-2 text-right font-bold">Antal ture</th>
                        <th className="px-4 py-2 text-right font-bold">Total vægt (kg)</th>
                        <th className="px-4 py-2 text-left font-bold w-32">Fordeling</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top.map((m, idx) => (
                        <tr key={m.name} className="border-t border-slate-100 dark:border-slate-700/50 hover:bg-slate-50/60 dark:hover:bg-slate-900/30"
                          data-testid={`material-row-${idx}`}>
                          <td className="px-4 py-2 text-slate-400 font-medium">{idx + 1}</td>
                          <td className="px-4 py-2 text-slate-800 dark:text-slate-200 font-medium">{m.name}</td>
                          <td className="px-4 py-2 text-right font-bold text-slate-900 dark:text-white">{m.count}</td>
                          <td className="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">
                            {m.weight?.toLocaleString("da-DK")}
                          </td>
                          <td className="px-4 py-2">
                            <div className="w-full h-2 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                              <div className="h-full rounded-full bg-gradient-to-r from-orange-400 to-orange-600"
                                style={{ width: `${(m.count / maxCount) * 100}%` }} />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>

          {/* Materiale fordeling-pie + Medarbejdere-tabel side om side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
              <p className="font-heading font-bold text-lg text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="inline-flex w-7 h-7 rounded-lg bg-orange-100 dark:bg-orange-950/40 text-orange-600 dark:text-orange-300 items-center justify-center">
                  <FileText className="w-4 h-4" />
                </span>
                Materiale fordeling
              </p>
              {data.by_material.length === 0 ? (
                <p className="text-xs text-slate-400 italic py-6 text-center">Ingen data.</p>
              ) : (() => {
                const COLORS = ["#f97316", "#3b82f6", "#10b981", "#a855f7", "#ef4444",
                                "#f59e0b", "#06b6d4", "#ec4899", "#64748b", "#84cc16"];
                const top10 = data.by_material.slice(0, 10);
                const totalAll = data.by_material.reduce((s, m) => s + m.count, 0) || 1;
                const sliceData = top10.map((m) => ({ name: m.name, value: m.count, pct: Math.round((m.count / totalAll) * 100) }));
                return (
                  <R.ResponsiveContainer width="100%" height={340} debounce={150}>
                    <R.PieChart>
                      <R.Pie data={sliceData} dataKey="value" nameKey="name"
                        cx="50%" cy="50%" outerRadius={120}
                        label={({ name, pct }) => `${name.length > 14 ? name.slice(0, 13) + "…" : name} (${pct}%)`}
                        labelLine={true}>
                        {sliceData.map((_, i) => (
                          <R.Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </R.Pie>
                      <R.Tooltip formatter={(v, n) => [`${v} ture`, n]} />
                    </R.PieChart>
                  </R.ResponsiveContainer>
                );
              })()}
            </div>

            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
                <span className="inline-flex w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-950/40 text-purple-600 dark:text-purple-300 items-center justify-center">
                  <Users className="w-4 h-4" />
                </span>
                <p className="font-heading font-bold text-lg text-slate-900 dark:text-white">Top medarbejdere</p>
              </div>
              {data.by_employee.length === 0 ? (
                <p className="text-xs text-slate-400 italic py-6 text-center">Ingen data.</p>
              ) : (() => {
                const top = data.by_employee.slice(0, 15);
                const maxCount = top[0]?.count || 1;
                return (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500 text-xs uppercase tracking-wider">
                        <tr>
                          <th className="px-4 py-2 text-left font-bold w-12">#</th>
                          <th className="px-4 py-2 text-left font-bold">Medarbejder</th>
                          <th className="px-4 py-2 text-right font-bold">Bestillinger</th>
                          <th className="px-4 py-2 text-left font-bold w-24">Fordeling</th>
                        </tr>
                      </thead>
                      <tbody>
                        {top.map((e, idx) => (
                          <tr key={e.name + idx} className="border-t border-slate-100 dark:border-slate-700/50">
                            <td className="px-4 py-2 text-slate-400 font-medium">{idx + 1}</td>
                            <td className="px-4 py-2 text-slate-800 dark:text-slate-200">{e.name}</td>
                            <td className="px-4 py-2 text-right font-bold text-slate-900 dark:text-white">{e.count}</td>
                            <td className="px-4 py-2">
                              <div className="w-full h-1.5 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                                <div className="h-full rounded-full bg-gradient-to-r from-purple-400 to-purple-600"
                                  style={{ width: `${(e.count / maxCount) * 100}%` }} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </div>
          </div>

          {data.pending_orders && data.pending_orders.length > 0 && (
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4">
              <p className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-2">Afventende bestillinger ({data.pending_orders.length})</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 dark:bg-slate-900">
                    <tr>
                      <th className="px-2 py-1.5 text-left font-bold">Dato</th>
                      <th className="px-2 py-1.5 text-left font-bold">Materiale</th>
                      <th className="px-2 py-1.5 text-left font-bold">Container</th>
                      <th className="px-2 py-1.5 text-left font-bold">Bestilt af</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pending_orders.slice(0, 20).map(o => (
                      <tr key={o.id} className="border-t border-slate-100 dark:border-slate-700">
                        <td className="px-2 py-1.5">{o.order_date}</td>
                        <td className="px-2 py-1.5">{o.material}</td>
                        <td className="px-2 py-1.5">{o.container_number || "-"}</td>
                        <td className="px-2 py-1.5">{o.on_behalf_company_name ? `${o.on_behalf_company_name} for jer` : (o.created_by_name || o.created_by_email || "-")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ============================================================================
// Fase 18.5 (2026-02-28) - Tur-arkiv (Archive) til Location Admin
// Viser turhistorik for en eller flere lokationer. For løs afhentning vises
// total + breakdown pr. kvittering (tooltip på desktop, klik-popover på mobil).
//
// Fase 18.6 (2026-02-28) update - default = i dag + alle lokationer,
// kolonner for CO2, partner, opgavetype, bestilt af + tidspunkt, og
// "Åbn"-knap pr. kvittering med download.
// ============================================================================
const TASK_TYPE_LABELS = {
  "normal": { label: "Almindelig afhentning", cls: "bg-emerald-100 text-emerald-700" },
  "loes_afhentning": { label: "Løs afhentning", cls: "bg-purple-100 text-purple-700" },
  "flyt": { label: "Bytte container", cls: "bg-amber-100 text-amber-700" },
  "vaerksted": { label: "Værksted til", cls: "bg-blue-100 text-blue-700" },
  "afhent_vaerksted": { label: "Værksted fra", cls: "bg-indigo-100 text-indigo-700" },
  "estimat": { label: "Estimat", cls: "bg-slate-100 text-slate-700" },
};
function getTaskTypeMeta(t) {
  return TASK_TYPE_LABELS[t || "normal"] || { label: t || "-", cls: "bg-slate-100 text-slate-700" };
}

const ARCHIVE_PERIODS = [
  { id: "today", label: "I dag" },
  { id: "week", label: "Denne uge" },
  { id: "month", label: "Denne måned" },
  { id: "all", label: "Alle" },
  { id: "custom", label: "Brugerdef." },
];

function dateRangeFor(period) {
  const today = new Date();
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (period === "today") {
    const t = ymd(today);
    return { from: t, to: t };
  }
  if (period === "week") {
    const day = (today.getDay() + 6) % 7; // mandag=0
    const monday = new Date(today); monday.setDate(today.getDate() - day);
    return { from: ymd(monday), to: ymd(today) };
  }
  if (period === "month") {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    return { from: ymd(first), to: ymd(today) };
  }
  return { from: "", to: "" };
}

export function ArchiveTab({ locations = [] }) {
  const allCodes = locations.map(l => l.code || l.location_code).filter(Boolean);
  // Default: ALLE tildelte lokationer (brugerønske).
  const [selectedCodes, setSelectedCodes] = useState(() => new Set(allCodes));
  // Default-periode = I dag
  const [period, setPeriod] = useState("today");
  const initRange = dateRangeFor("today");
  const [dateFrom, setDateFrom] = useState(initRange.from);
  const [dateTo, setDateTo] = useState(initRange.to);
  const [search, setSearch] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [popoverFor, setPopoverFor] = useState(null);     // tour.id (vægt-popover)
  const [receiptModal, setReceiptModal] = useState(null); // {id, driver_name, date, weight}
  // Fase 18.8 (2026-02-28): Skjul igangværende ture by default. Knap viser
  // dem øverst i tabellen sorteret før de afsluttede.
  const [includeOngoing, setIncludeOngoing] = useState(false);

  useEffect(() => {
    // Når lokationerne loades, defaulter vi til alle tildelte.
    if (allCodes.length > 0 && selectedCodes.size === 0) {
      setSelectedCodes(new Set(allCodes));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations]);

  // Periode-skift sætter date range automatisk (medmindre custom)
  useEffect(() => {
    if (period === "custom") return;
    const r = dateRangeFor(period);
    setDateFrom(r.from); setDateTo(r.to);
  }, [period]);

  const effectiveCodes = selectedCodes.size > 0 ? Array.from(selectedCodes) : allCodes;
  const displayName = effectiveCodes.length === locations.length && locations.length > 1
    ? `Alle ${locations.length} lokationer`
    : effectiveCodes.length === 1
      ? (locations.find(l => (l.code || l.location_code) === effectiveCodes[0])?.name || effectiveCodes[0])
      : `${effectiveCodes.length} lokationer`;

  const fetchArchive = useCallback(async () => {
    if (effectiveCodes.length === 0) { setData(null); return; }
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("location_codes", effectiveCodes.join(","));
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const { data: payload } = await axios.get(`${API}/org/tour-archive?${params.toString()}`);
      setData(payload);
    } catch (e) {
      toast.error(formatApiError(e, "Kunne ikke hente arkivet"));
      setData(null);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveCodes.join("|"), dateFrom, dateTo]);

  useEffect(() => { fetchArchive(); }, [fetchArchive]);

  if (locations.length === 0) {
    return (
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-200">
        Ingen lokationer tilknyttet din konto endnu.
      </div>
    );
  }

  const fmtDate = (s) => {
    if (!s) return "-";
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
      try { return new Date(s).toLocaleDateString("da-DK", { day: "2-digit", month: "short", year: "numeric" }); }
      catch (_) { return s; }
    }
    return s;
  };
  const fmtDateTime = (s) => {
    if (!s) return "-";
    try { return new Date(s).toLocaleString("da-DK", { day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit" }); }
    catch (_) { return s; }
  };
  const fmtTime = (s) => {
    if (!s) return "-";
    if (/^\d{2}:\d{2}$/.test(s)) return s;
    try { const d = new Date(s); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }
    catch (_) { return "-"; }
  };
  const fmtKg = (n) => {
    if (n == null || !Number.isFinite(Number(n))) return "-";
    return Number(n).toLocaleString("da-DK", { maximumFractionDigits: 1 }) + " kg";
  };
  const fmtCo2 = (n) => {
    if (!n || !Number.isFinite(Number(n))) return "-";
    return Number(n).toLocaleString("da-DK", { maximumFractionDigits: 1 });
  };

  const tours = (() => {
    // 1) Søge-filter (samme som før)
    let arr = (data?.tours || []).filter(t => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return [t.fraction, t.driver_name, t.container, t.address, t.plads, t.tour_number, t.comment, t.ordered_by, t.partner_name]
        .some(v => (v || "").toLowerCase().includes(q));
    });
    // 2) Igangværende filtreres væk by default. Når includeOngoing er TIL
    //    vises kun "på vej"-ture (dvs. ture med on_way_time sat eller
    //    on_way=true). Ikke-startede claimet/planlagte ture vises IKKE
    //    (de er ikke i faktisk gang og hører til på Logistik-fanen).
    if (!includeOngoing) {
      arr = arr.filter(t => t.completed || t.not_completed);
    } else {
      arr = arr.filter(t =>
        t.completed
        || t.not_completed
        || ((t.on_way || (t.on_way_time && t.on_way_time.trim() !== "")))
      );
    }
    // 3) Sortering: igangværende ØVERST (hvis inkluderet), derefter
    //    kronologisk efter dato (nyeste først). Vi sorterer på
    //    completed_at hvis sat, ellers order_date som fallback.
    const ts = (t) => {
      const d = t.completed_at || t.ordered_at || t.order_date || t.date || "";
      const m = new Date(d).getTime();
      return Number.isFinite(m) ? m : 0;
    };
    arr.sort((a, b) => {
      const aOngoing = !a.completed && !a.not_completed;
      const bOngoing = !b.completed && !b.not_completed;
      if (aOngoing !== bOngoing) return aOngoing ? -1 : 1; // igangværende først
      return ts(b) - ts(a); // nyeste først
    });
    return arr;
  })();
  // Antal "på vej"-ture (ikke fuldført, men startet - det er disse der
  // dukker op når includeOngoing slås til).
  const ongoingCount = (data?.tours || []).filter(t =>
    !t.completed && !t.not_completed && (t.on_way || (t.on_way_time && t.on_way_time.trim() !== ""))
  ).length;

  const kpiTours = tours.length;
  const kpiCompleted = tours.filter(t => t.completed).length;
  const kpiWeight = tours.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  const kpiCo2 = tours.reduce((s, t) => s + (Number(t.co2_kg) || 0), 0);
  const kpiContainers = tours.reduce((s, t) => {
    if (t.tour_type === "loes_afhentning") return s + (t.container_weights?.length || 0);
    return s + 1;
  }, 0);

  const exportXlsx = async () => {
    const xlsx = await import("xlsx");
    const rows = tours.map(t => {
      const isLoose = t.tour_type === "loes_afhentning";
      const meta = getTaskTypeMeta(t.tour_type);
      return {
        "Bestilt dato": t.order_date || "",
        "Bestilt tidspunkt": t.ordered_at ? new Date(t.ordered_at).toLocaleString("da-DK") : "",
        "Bestilt af": t.ordered_by || t.ordered_by_email || "",
        "Fuldført": t.completed_at ? new Date(t.completed_at).toLocaleString("da-DK") : "",
        "Lokation": t.plads || "",
        "Logistik-partner": t.partner_name || "",
        "Opgavetype": meta.label,
        "Materiale": t.fraction || "",
        "Container": t.container || "",
        "Antal containere": isLoose ? (t.container_weights?.length || 0) : 1,
        "Vægt (kg)": Number(t.weight || 0),
        "CO2 (kg)": Number(t.co2_kg || 0),
        "Tur start": t.on_way_time || "",
        "Tur slut": t.completed_at ? new Date(t.completed_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : "",
        "Chauffør": t.driver_name || "",
        "Adresse": t.address || "",
        "Status": t.completed ? "Fuldført" : (t.not_completed ? "Ikke gennemført" : "Igangværende"),
        // 2026-10-20: Fakturagrundlag uden priser (basic har ikke Økonomi).
        "Tur-nr.": t.tour_number || "",
        "Haster": (t.priority === "urgent" || t.priority === "haster") ? "Ja" : "",
        "Hængere": t.trailer_count_actual != null ? Number(t.trailer_count_actual) : (t.used_trailer ? 1 : ""),
        "Ventetid (min)": t.waiting_reported_min || "",
        "Afvigelse": t.not_completed_code || t.finish_issue || (t.cancelled ? "Annulleret" : ""),
      };
    });
    const subRows = [];
    tours.forEach(t => {
      if (t.tour_type !== "loes_afhentning") return;
      (t.container_weights || []).forEach((w, i) => {
        const r = (t.receipts || [])[i] || {};
        subRows.push({
          "Tur (bestilt)": t.order_date || "",
          "Lokation": t.plads || "",
          "Materiale": t.fraction || "",
          "Chauffør": t.driver_name || "",
          "Afhentning #": i + 1,
          "Tidspunkt": r.created_at ? new Date(r.created_at).toLocaleString("da-DK") : "",
          "Vægt (kg)": Number(w || 0),
          "CO2 (kg)": Number(t.co2_factor || 0) * (Number(w || 0) / 1000),
        });
      });
    });
    const wb = xlsx.utils.book_new();
    xlsx.utils.book_append_sheet(wb, xlsx.utils.json_to_sheet(rows), "Ture");
    if (subRows.length > 0) {
      xlsx.utils.book_append_sheet(wb, xlsx.utils.json_to_sheet(subRows), "Løse afhentninger");
    }
    xlsx.writeFile(wb, `arkiv_${effectiveCodes.join("_")}_${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  return (
    <div className="space-y-5" data-testid="archive-tab">
      {/* Lokations-vælger */}
      {locations.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap" data-testid="archive-loc-tabs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mr-1">Lokationer:</p>
          {locations.map(l => {
            const code = l.code || l.location_code;
            const on = selectedCodes.has(code);
            return (
              <button key={code}
                onClick={() => {
                  const next = new Set(selectedCodes);
                  if (on) next.delete(code); else next.add(code);
                  setSelectedCodes(next);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 ${on ? "bg-emerald-600 text-white" : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-emerald-400"}`}
                data-testid={`archive-loc-${code}`}>
                {on && <Check className="w-3 h-3" />}
                {l.name}
              </button>
            );
          })}
          <div className="flex gap-1 ml-auto">
            <button onClick={() => setSelectedCodes(new Set(allCodes))} className="text-[11px] font-bold text-emerald-600 hover:text-emerald-700 px-2 py-1" data-testid="archive-loc-all">Vælg alle</button>
            <button onClick={() => setSelectedCodes(new Set([allCodes[0]]))} className="text-[11px] font-bold text-slate-500 hover:text-slate-700 px-2 py-1">Kun første</button>
          </div>
        </div>
      )}

      <h2 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
        Arkiv <span className="text-emerald-600 dark:text-emerald-400 ml-2">· {displayName}</span>
      </h2>

      {/* Periode-vælger + filtre */}
      <div className="space-y-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3">
        <div className="flex flex-wrap gap-1.5" data-testid="archive-periods">
          {ARCHIVE_PERIODS.map(p => (
            <button key={p.id} onClick={() => setPeriod(p.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold ${period === p.id ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200"}`}
              data-testid={`archive-period-${p.id}`}>
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col">
            <label className="text-[11px] font-semibold text-slate-500 mb-1">Fra dato</label>
            <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPeriod("custom"); }} className="px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900" data-testid="archive-date-from" />
          </div>
          <div className="flex flex-col">
            <label className="text-[11px] font-semibold text-slate-500 mb-1">Til dato</label>
            <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPeriod("custom"); }} className="px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900" data-testid="archive-date-to" />
          </div>
          <div className="flex flex-col flex-1 min-w-[200px]">
            <label className="text-[11px] font-semibold text-slate-500 mb-1">Søg (materiale, chauffør, partner, bestilt af...)</label>
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Skriv for at filtrere..." className="px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900" data-testid="archive-search" />
          </div>
          <button onClick={exportXlsx} disabled={tours.length === 0}
            className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 text-white text-sm font-bold inline-flex items-center gap-1.5"
            data-testid="archive-export-xlsx">
            <FileSpreadsheet className="w-4 h-4" /> Excel
          </button>
        </div>
        {/* Fase 18.8 (2026-02-28): Toggle for igangværende ture. By default
            er disse skjult - knappen viser dem øverst i tabellen. */}
        {ongoingCount > 0 && (
          <div className="flex items-center gap-2 pt-1 border-t border-slate-100 dark:border-slate-700">
            <button
              onClick={() => setIncludeOngoing(v => !v)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 ${includeOngoing ? "bg-amber-500 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-amber-100 dark:hover:bg-amber-900/40"}`}
              data-testid="archive-toggle-ongoing"
              title="Vis/skjul igangværende ture (ikke afsluttede)"
            >
              {includeOngoing ? <Check className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
              {includeOngoing ? "Skjul igangværende" : "Inkluder igangværende ture"}
              <span className={`inline-flex items-center justify-center min-w-[20px] h-4 px-1 rounded-full text-[10px] font-bold ${includeOngoing ? "bg-white/30" : "bg-amber-100 text-amber-700"}`}>{ongoingCount}</span>
            </button>
            {includeOngoing && <span className="text-[11px] text-amber-600">Igangværende ture vises øverst</span>}
          </div>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-xl p-3">
          <p className="text-[11px] text-emerald-700 dark:text-emerald-300 font-semibold uppercase">Ture</p>
          <p className="text-2xl font-black text-emerald-700 dark:text-emerald-200" data-testid="archive-kpi-tours">{kpiTours}</p>
          <p className="text-[10px] text-emerald-600/70">{kpiCompleted} fuldført</p>
        </div>
        <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl p-3">
          <p className="text-[11px] text-blue-700 dark:text-blue-300 font-semibold uppercase">Containere</p>
          <p className="text-2xl font-black text-blue-700 dark:text-blue-200" data-testid="archive-kpi-containers">{kpiContainers}</p>
          <p className="text-[10px] text-blue-600/70">inkl. løse</p>
        </div>
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-3">
          <p className="text-[11px] text-amber-700 dark:text-amber-300 font-semibold uppercase">Total vægt</p>
          <p className="text-2xl font-black text-amber-700 dark:text-amber-200" data-testid="archive-kpi-weight">{fmtKg(kpiWeight)}</p>
        </div>
        <div className="bg-teal-50 dark:bg-teal-950/30 border border-teal-200 dark:border-teal-800 rounded-xl p-3">
          <p className="text-[11px] text-teal-700 dark:text-teal-300 font-semibold uppercase flex items-center gap-1"><Leaf className="w-3 h-3" /> CO2 (kg)</p>
          <p className="text-2xl font-black text-teal-700 dark:text-teal-200" data-testid="archive-kpi-co2">{fmtCo2(kpiCo2)}</p>
        </div>
      </div>

      {/* Tabel */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-visible">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-900/40 text-slate-600 dark:text-slate-400 text-[11px] uppercase">
                <th className="p-2 text-left font-semibold">Bestilt</th>
                <th className="p-2 text-left font-semibold">Bestilt af</th>
                <th className="p-2 text-left font-semibold">Fuldført</th>
                <th className="p-2 text-left font-semibold">Lokation</th>
                <th className="p-2 text-left font-semibold">Partner</th>
                <th className="p-2 text-left font-semibold">Opgavetype</th>
                <th className="p-2 text-left font-semibold">Materiale</th>
                <th className="p-2 text-left font-semibold">Container</th>
                <th className="p-2 text-right font-semibold">Antal</th>
                <th className="p-2 text-right font-semibold">Vægt</th>
                <th className="p-2 text-right font-semibold">CO2 (kg)</th>
                <th className="p-2 text-left font-semibold">Tur start</th>
                <th className="p-2 text-left font-semibold">Tur slut</th>
                <th className="p-2 text-left font-semibold">Chauffør</th>
                <th className="p-2 text-left font-semibold">Kvit.</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan="15" className="p-8 text-center text-slate-500"><Loader2 className="w-5 h-5 animate-spin inline mr-2" /> Henter...</td></tr>
              )}
              {!loading && tours.length === 0 && (
                <tr><td colSpan="15" className="p-8 text-center text-slate-500 italic" data-testid="archive-empty">Ingen ture matcher dine filtre.</td></tr>
              )}
              {!loading && tours.map(t => {
                const isLoose = t.tour_type === "loes_afhentning";
                const containerCount = isLoose ? (t.container_weights?.length || 0) : 1;
                const receipts = t.receipts || [];
                const popoverOpen = popoverFor === t.id;
                const meta = getTaskTypeMeta(t.tour_type);
                const statusBadge = t.completed
                  ? <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700">Fuldført</span>
                  : t.not_completed
                    ? <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-700" title={t.not_completed_comment}>Ikke gennemført</span>
                    : <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700">Igangværende</span>;
                const tooltipText = isLoose && t.container_weights?.length
                  ? `Opdeling:\n` + t.container_weights.map((w, i) => `${i + 1}. ${fmtKg(w)}${receipts[i]?.created_at ? " · " + new Date(receipts[i].created_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : ""}`).join("\n")
                  : "";
                return (
                  <tr key={t.id} className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 align-top" data-testid={`archive-row-${t.id}`}>
                    <td className="p-2 whitespace-nowrap text-xs">{fmtDate(t.order_date)}</td>
                    <td className="p-2 whitespace-nowrap text-xs">
                      <div className="font-semibold">{t.ordered_by || "-"}</div>
                      <div className="text-[10px] text-slate-400">{t.ordered_at ? fmtDateTime(t.ordered_at) : ""}</div>
                    </td>
                    <td className="p-2 whitespace-nowrap text-xs">{t.completed_at ? fmtDateTime(t.completed_at) : "-"}</td>
                    <td className="p-2 text-xs">{t.plads || "-"}</td>
                    <td className="p-2 text-xs">
                      {t.partner_name
                        ? <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-100 text-cyan-700">{t.partner_name}</span>
                        : <span className="text-slate-300">-</span>}
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${meta.cls}`}>{meta.label}</span>
                      <div className="mt-1">{statusBadge}</div>
                    </td>
                    <td className="p-2 font-semibold">{t.fraction || "-"}</td>
                    <td className="p-2 text-xs">{t.container || "-"}</td>
                    <td className="p-2 text-right font-mono font-semibold">{containerCount}</td>
                    <td className="p-2 text-right relative">
                      {isLoose && (t.container_weights?.length || 0) > 0 ? (
                        <>
                          <button
                            onClick={() => setPopoverFor(popoverOpen ? null : t.id)}
                            className="font-mono font-bold text-emerald-700 dark:text-emerald-400 hover:underline cursor-pointer"
                            data-testid={`archive-weight-${t.id}`}
                            title={tooltipText}
                          >
                            {fmtKg(t.weight)}
                            <span className="ml-1 text-[10px] text-purple-600 font-bold">{containerCount}×</span>
                          </button>
                          {popoverOpen && (
                            <div
                              className="absolute right-0 top-full mt-1 z-30 bg-white dark:bg-slate-900 border-2 border-purple-300 dark:border-purple-700 rounded-lg shadow-2xl p-3 text-left w-72"
                              onClick={(e) => e.stopPropagation()}
                              data-testid={`archive-weight-popover-${t.id}`}
                            >
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-xs font-bold text-purple-700 uppercase">Opdeling pr. afhentning</p>
                                <button onClick={() => setPopoverFor(null)} className="text-slate-400 hover:text-slate-700"><X className="w-4 h-4" /></button>
                              </div>
                              <ul className="space-y-1.5 text-xs">
                                {t.container_weights.map((w, i) => {
                                  const r = receipts[i] || {};
                                  const co2_i = Number(t.co2_factor || 0) * (Number(w || 0) / 1000);
                                  return (
                                    <li key={i} className="flex flex-col gap-0.5 border-b border-slate-100 dark:border-slate-700 pb-1">
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="text-slate-500 font-mono">#{i + 1}</span>
                                        <span className="text-slate-700 dark:text-slate-300">{r.created_at ? new Date(r.created_at).toLocaleString("da-DK", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-"}</span>
                                        <span className="font-mono font-bold text-emerald-700">{fmtKg(w)}</span>
                                      </div>
                                      {co2_i > 0 && (
                                        <div className="text-[10px] text-teal-600 text-right flex items-center justify-end gap-1">
                                          <Leaf className="w-2.5 h-2.5" /> {fmtCo2(co2_i)} kg CO2
                                        </div>
                                      )}
                                      {r.id && (
                                        <button onClick={() => setReceiptModal({ id: r.id, driver_name: r.driver_name, weight: w, date: r.created_at })}
                                          className="text-[10px] text-blue-600 hover:underline text-left mt-0.5"
                                          data-testid={`archive-popover-open-receipt-${r.id}`}>
                                          Åbn kvittering →
                                        </button>
                                      )}
                                    </li>
                                  );
                                })}
                              </ul>
                              <div className="mt-2 pt-2 border-t border-slate-300 dark:border-slate-600 flex justify-between text-xs">
                                <span className="font-bold">Total</span>
                                <span className="font-mono font-bold text-emerald-700">{fmtKg(t.weight)}</span>
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="font-mono font-semibold">{fmtKg(t.weight)}</span>
                      )}
                    </td>
                    <td className="p-2 text-right text-xs font-mono text-teal-700 dark:text-teal-300">
                      {t.co2_kg > 0 ? <span className="inline-flex items-center gap-0.5"><Leaf className="w-3 h-3" /> {fmtCo2(t.co2_kg)}</span> : <span className="text-slate-300">-</span>}
                    </td>
                    <td className="p-2 font-mono text-xs text-emerald-600 dark:text-emerald-400">{fmtTime(t.on_way_time)}</td>
                    <td className="p-2 font-mono text-xs text-rose-600 dark:text-rose-400">{t.completed_at ? fmtTime(t.completed_at) : "-"}</td>
                    <td className="p-2 text-xs">{t.driver_name || "-"}</td>
                    <td className="p-2">
                      {receipts.length > 0 ? (
                        <div className="flex flex-col gap-1">
                          {receipts.map((r, i) => (
                            <button key={r.id || i}
                              onClick={() => setReceiptModal({ id: r.id, driver_name: r.driver_name, weight: isLoose ? (t.container_weights?.[i] || r.final_weight_kg) : r.final_weight_kg, date: r.created_at })}
                              className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 hover:bg-blue-200 text-blue-700 inline-flex items-center gap-0.5 transition-colors"
                              data-testid={`archive-open-receipt-${r.id || i}`}>
                              <Eye className="w-3 h-3" /> Åbn
                            </button>
                          ))}
                        </div>
                      ) : <span className="text-slate-300">-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Kvitterings-modal */}
      {receiptModal && (
        <ReceiptViewerModal
          receiptId={receiptModal.id}
          driverName={receiptModal.driver_name}
          weight={receiptModal.weight}
          date={receiptModal.date}
          onClose={() => setReceiptModal(null)}
        />
      )}
    </div>
  );
}

// Fase 18.6 (2026-02-28): Kvitterings-viewer-modal. Bruger /receipts/{id}/image-binary
// for at undgå at trække hele base64-payloaden gennem JSON (vi havde tidligere
// crashes på iOS Safari ved store kvitteringer). Download-knappen henter
// samme endpoint og gemmer som JPEG.
function ReceiptViewerModal({ receiptId, driverName, weight, date, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [blobUrl, setBlobUrl] = useState(null);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setBlobUrl(null);
    (async () => {
      try {
        const res = await axios.get(`${API}/receipts/${receiptId}/image-binary`, { responseType: "blob" });
        if (!active) return;
        const url = URL.createObjectURL(res.data);
        setBlobUrl(url);
      } catch (e) {
        if (active) setError(formatApiError(e, "Kunne ikke hente kvitteringsbillede"));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; if (blobUrl) URL.revokeObjectURL(blobUrl); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receiptId]);

  const handleDownload = () => {
    if (!blobUrl) return;
    const a = document.createElement("a");
    a.href = blobUrl;
    const safeName = (driverName || "kvittering").replace(/[^a-zA-Z0-9_-]/g, "_");
    const dateStr = date ? new Date(date).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10);
    a.download = `kvittering_${safeName}_${dateStr}.jpg`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm flex items-center justify-center p-3" data-testid="receipt-viewer-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-bold text-slate-900 dark:text-white text-sm">Kvittering</h3>
            <p className="text-xs text-slate-500">
              {driverName ? <>{driverName} · </> : null}
              {date ? new Date(date).toLocaleString("da-DK") : "-"}
              {weight ? <> · <span className="font-mono">{Number(weight).toLocaleString("da-DK")} kg</span></> : null}
            </p>
          </div>
          <button onClick={handleDownload} disabled={!blobUrl}
            className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-bold inline-flex items-center gap-1.5"
            data-testid="receipt-viewer-download">
            <FileDown className="w-3.5 h-3.5" /> Download
          </button>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="receipt-viewer-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-auto bg-slate-100 dark:bg-slate-950 flex items-center justify-center p-3">
          {loading && <div className="text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline mr-2" /> Henter billede...</div>}
          {error && <div className="text-rose-600 text-sm">{error}</div>}
          {blobUrl && <img src={blobUrl} alt="Kvittering" className="max-w-full max-h-[70vh] object-contain rounded shadow" data-testid="receipt-viewer-image" />}
        </div>
      </div>
    </div>
  );
}
