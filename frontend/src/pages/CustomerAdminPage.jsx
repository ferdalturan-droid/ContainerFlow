import React, { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import { saveAs } from "file-saver";
import {
  Building, MapPin, Users, Truck, Plus, Trash2, X, Check, Loader2, Mail, Edit2,
  LogOut, Link2, Link2Off, BarChart3, Wrench, Tags, Save, Phone, MessageSquare,
  FileSpreadsheet, FileDown, Leaf, Menu,
} from "lucide-react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";
import { exportReportXLSX } from "../lib/excelExport";

/**
 * Customer admin (e.g. Jørgen / ARGO). Org-wide admin of ONE customer company.
 * Manages: locations, location admins, logistics partners, and an org-wide report.
 * Everything is automatically scoped to this customer company by the backend.
 */
export default function CustomerAdminPage() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("locations");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const TABS = [
    { id: "locations", label: "Lokationer", icon: MapPin },
    { id: "groups",     label: "Lokationsgrupper", icon: Tags },
    { id: "admins",     label: "Tilføj location admin", icon: Users },
    { id: "workshops",  label: "Værksteder", icon: Wrench },
    { id: "co2",        label: "CO2-typer", icon: Leaf },
    { id: "partners",   label: "Logistik-partnere", icon: Truck },
    { id: "report",     label: "Rapport", icon: BarChart3 },
  ];
  const activeTab = TABS.find(t => t.id === tab) || TABS[0];

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-[#0F172A] text-white sticky top-0 z-10">
        <div className="max-w-screen-2xl mx-auto px-3 sm:px-10 py-2 sm:py-3 flex items-center justify-between gap-2">
          {/* Mobil hamburger-menu (Fase 18.28) */}
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="sm:hidden p-2 rounded-lg bg-slate-800/70 hover:bg-slate-700 text-emerald-300 shrink-0"
            data-testid="cadmin-mobile-menu-btn"
            aria-label="Åbn menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            <div className="hidden sm:flex w-9 h-9 bg-emerald-600 rounded-lg items-center justify-center shrink-0">
              <Building className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <p className="font-bold leading-tight text-sm sm:text-base truncate">{user?.company_name || "Kunde"}</p>
              <p className="text-emerald-400 text-[10px] sm:text-[11px] uppercase tracking-wider leading-tight truncate">
                <span className="sm:hidden">{activeTab.label}</span>
                <span className="hidden sm:inline">Kunde-administration</span>
              </p>
            </div>
          </div>
          {/* Mobil: ikon-only logout */}
          <button onClick={logout} className="sm:hidden p-2 rounded-lg bg-slate-800/70 text-emerald-300 hover:bg-slate-700 shrink-0" title="Log ud">
            <LogOut className="w-4 h-4" />
          </button>
          <button onClick={logout} className="hidden sm:flex items-center gap-1.5 text-xs text-emerald-300 hover:text-white shrink-0">
            <LogOut className="w-4 h-4" /> Log ud
          </button>
        </div>
        {/* Desktop tabs - skjult på mobil (drawer i stedet) */}
        <div className="relative hidden sm:block">
          <div className="max-w-screen-2xl mx-auto px-4 sm:px-10 flex gap-1 overflow-x-auto scrollbar-thin">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                data-testid={`cadmin-tab-${t.id}`}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
                  tab === t.id ? "border-emerald-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
                }`}>
                <t.icon className="w-4 h-4" /> {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Mobil side-drawer (Fase 18.28) - moderne menu-liste-mønster */}
      {mobileMenuOpen && createPortal(
        <div className="sm:hidden fixed inset-0 z-[60]" data-testid="cadmin-mobile-drawer">
          <div
            onClick={() => setMobileMenuOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />
          <div className="absolute left-0 top-0 bottom-0 w-72 max-w-[85vw] bg-slate-900 border-r border-slate-700 shadow-2xl flex flex-col">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 bg-emerald-600 rounded-lg flex items-center justify-center shrink-0"><Building className="w-4 h-4 text-white" /></div>
                <div className="min-w-0">
                  <p className="text-white font-bold text-sm truncate">{user?.company_name || "Kunde"}</p>
                  <p className="text-emerald-400 text-[10px] uppercase tracking-wider truncate">Kunde-administration</p>
                </div>
              </div>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 shrink-0"
                data-testid="cadmin-mobile-drawer-close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-2">
              {TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => { setTab(t.id); setMobileMenuOpen(false); }}
                  data-testid={`cadmin-drawer-tab-${t.id}`}
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
                onClick={logout}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-rose-300 text-sm font-bold"
              >
                <LogOut className="w-4 h-4" /> Log ud
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      <main className="max-w-screen-2xl mx-auto px-4 sm:px-10 py-4 sm:py-5">
        {tab === "locations" && <LocationsTab />}
        {tab === "groups" && <LocationGroupsTab />}
        {tab === "admins" && <LocationAdminsTab />}
        {tab === "workshops" && <WorkshopsTab />}
        {tab === "co2" && <CO2TypesTab />}
        {tab === "partners" && <PartnersTab />}
        {tab === "report" && <ReportTab />}
      </main>
    </div>
  );
}

/* ---------- Locations ---------- */
function LocationsTab() {
  const [items, setItems] = useState([]);
  const [partners, setPartners] = useState([]);
  const [admins, setAdmins] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const empty = { name: "", address: "", city: "", admin_user_id: "", location_group_id: "" };
  const [form, setForm] = useState(empty);
  const [editingLoc, setEditingLoc] = useState(null); // edit location modal
  const [editLocForm, setEditLocForm] = useState({ name: "", address: "", city: "", location_group_id: "" });
  const [adminPickerFor, setAdminPickerFor] = useState(null); // location id whose admin we are editing
  const [saving, setSaving] = useState(false);
  const [assigningId, setAssigningId] = useState(null); // location id being edited for partners

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const [locs, parts, users, grps] = await Promise.all([
        axios.get(`${API}/org/locations`),
        axios.get(`${API}/org/my-partners`),
        axios.get(`${API}/org/users`),
        axios.get(`${API}/org/location-groups`).catch(() => ({ data: [] })),
      ]);
      setItems(locs.data || []);
      setPartners(parts.data || []);
      setAdmins((users.data || []).filter(u => u.role === "location_admin"));
      setGroups(grps.data || []);
    }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchItems(); }, [fetchItems]);

  const save = async () => {
    if (!form.name.trim()) { toast.error("Lokationsnavn er påkrævet"); return; }
    // Fase 15.55 (2026-02-22): Adresse + By er nu obligatoriske.
    if (!form.address.trim()) { toast.error("Adresse er påkrævet"); return; }
    if (!form.city.trim()) { toast.error("By er påkrævet"); return; }
    setSaving(true);
    try {
      const { data: created } = await axios.post(`${API}/org/locations`, {
        name: form.name, address: form.address, city: form.city,
        location_group_id: form.location_group_id || null,
      });
      toast.success("Lokation oprettet");
      // Optional: extend the selected location_admin's managed plads list
      if (form.admin_user_id) {
        const adm = admins.find(a => a.id === form.admin_user_id);
        const next = [
          ...new Set([
            ...(adm?.assigned_plads_ids || []),
            adm?.location_code,
            created.location_code || created.code,
          ].filter(Boolean)),
        ];
        try {
          await axios.put(`${API}/org/users/${form.admin_user_id}`, { location_codes: next });
          toast.success("Lokation tilknyttet valgt admin");
        } catch (e) { toast.error(formatApiError(e)); }
      }
      setShowForm(false); setForm(empty); fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try { await axios.delete(`${API}/org/locations/${id}`); toast.success("Slettet"); fetchItems(); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  const openEditLocation = (loc) => {
    setEditingLoc(loc);
    setEditLocForm({
      name: loc.name || "",
      address: loc.address || "",
      city: loc.city || "",
      location_group_id: loc.location_group_id || "",
    });
  };

  const saveEditLocation = async () => {
    if (!editingLoc) return;
    if (!editLocForm.name.trim()) { toast.error("Lokationsnavn er påkrævet"); return; }
    // Fase 15.55 (2026-02-22): Adresse + By er nu obligatoriske ved edit også.
    if (!editLocForm.address.trim()) { toast.error("Adresse er påkrævet"); return; }
    if (!editLocForm.city.trim()) { toast.error("By er påkrævet"); return; }
    try {
      await axios.put(`${API}/org/locations/${editingLoc.id}`, {
        name: editLocForm.name.trim(),
        address: editLocForm.address.trim(),
        city: editLocForm.city.trim(),
        // Send empty string to clear the grouping
        location_group_id: editLocForm.location_group_id || "",
      });
      toast.success("Lokation opdateret");
      setEditingLoc(null);
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const togglePartner = async (loc, partnerId) => {
    const current = loc.assigned_logistics_company_ids || [];
    const next = current.includes(partnerId)
      ? current.filter(x => x !== partnerId)
      : [...current, partnerId];
    try {
      await axios.put(`${API}/org/locations/${loc.id}/logistics-partners`, { logistics_company_ids: next });
      toast.success("Logistik-partnere opdateret");
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const partnerName = (id) => partners.find(p => p.id === id)?.name || id;
  const adminsForLoc = (code) => admins.filter(a => {
    const all = [...(a.assigned_plads_ids || []), a.location_code].filter(Boolean);
    return all.includes(code);
  });

  // Toggle whether an admin is assigned to a given location (additive set).
  // Krav 2026-06-15 (1): Klik én gang for at tilknytte, klik igen for at frakoble.
  const toggleAdminAssignment = async (loc, admin) => {
    const code = loc.code || loc.location_code;
    const current = new Set([...(admin.assigned_plads_ids || []), admin.location_code].filter(Boolean));
    const wasAttached = current.has(code);
    if (wasAttached) current.delete(code); else current.add(code);
    const next = Array.from(current);
    try {
      await axios.put(`${API}/org/users/${admin.id}`, { location_codes: next });
      toast.success(
        wasAttached
          ? `${admin.name || admin.email} frakoblet ${loc.name}`
          : `${admin.name || admin.email} tilknyttet ${loc.name}`
      );
      fetchItems();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs sm:text-sm text-slate-500 flex-1 min-w-0">Hver lokation (f.eks. KØGE, ROSKILDE) kan have én eller flere admins.</p>
        <button onClick={() => { setForm(empty); setShowForm(true); }}
          className="inline-flex items-center justify-center gap-1.5 p-2 sm:px-4 sm:py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shrink-0"
          data-testid="add-location-btn"
          title="Ny lokation">
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">Ny lokation</span>
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen lokationer endnu</div>
        ) : items.map(loc => {
          const assigned = loc.assigned_logistics_company_ids || [];
          const isExpanded = assigningId === loc.id;
          const isAdminPicker = adminPickerFor === loc.id;
          const code = loc.code || loc.location_code;
          const locAdmins = adminsForLoc(code);
          const groupName = loc.location_group_id
            ? (groups.find(g => g.id === loc.location_group_id)?.name || null)
            : null;
          return (
            <div key={loc.id} className="border-b border-slate-100 dark:border-slate-700/50 last:border-0">
              <div className="flex items-center justify-between px-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-slate-800 dark:text-white">{loc.name}</p>
                  <p className="text-xs text-slate-400">Kode {loc.code}{loc.city ? ` · ${loc.city}` : ""}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {groupName && (
                      <span className="text-[10px] uppercase tracking-wider bg-purple-100 dark:bg-purple-950/30 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full font-semibold inline-flex items-center gap-1"
                        data-testid={`loc-group-chip-${loc.id}`}>
                        <Tags className="w-2.5 h-2.5" /> {groupName}
                      </span>
                    )}
                    {locAdmins.length === 0 ? (
                      <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold" data-testid={`no-admin-${loc.id}`}>
                        Ingen location admin
                      </span>
                    ) : locAdmins.map(a => (
                      <span key={a.id} data-testid={`loc-admin-chip-${loc.id}-${a.id}`}
                        className="text-[10px] uppercase tracking-wider bg-blue-100 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full font-semibold">
                        {a.name || a.email}
                      </span>
                    ))}
                    {assigned.length === 0 ? (
                      <span className="text-[10px] uppercase tracking-wider text-amber-600 dark:text-amber-400 font-semibold" data-testid={`no-partners-${loc.id}`}>
                        Ingen logistik-partnere
                      </span>
                    ) : assigned.map(pid => (
                      <span key={pid} className="text-[10px] uppercase tracking-wider bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full font-semibold">
                        {partnerName(pid)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => openEditLocation(loc)}
                    className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                    title="Rediger"
                    data-testid={`edit-location-${loc.id}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setAdminPickerFor(isAdminPicker ? null : loc.id)}
                    className="text-xs text-blue-600 hover:text-blue-700 px-2 py-1 rounded hover:bg-blue-50 dark:hover:bg-blue-950/30"
                    data-testid={`assign-admin-${loc.id}`}>
                    {isAdminPicker ? "Luk admins" : "Admins"}
                  </button>
                  <button
                    onClick={() => setAssigningId(isExpanded ? null : loc.id)}
                    className="text-xs text-emerald-600 hover:text-emerald-700 px-2 py-1 rounded hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
                    data-testid={`assign-partners-${loc.id}`}
                  >
                    {isExpanded ? "Luk" : "Logistik"}
                  </button>
                  <button onClick={() => remove(loc.id)} className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {isAdminPicker && (
                <div className="bg-slate-50 dark:bg-slate-900/40 px-4 pb-3 pt-2 space-y-1.5" data-testid={`admin-picker-${loc.id}`}>
                  {admins.length === 0 ? (
                    <p className="text-xs text-amber-600">Ingen location-admins endnu. Opret en under fanen "Lokations-admins".</p>
                  ) : admins.map(a => {
                    const codes = new Set([...(a.assigned_plads_ids || []), a.location_code].filter(Boolean));
                    const on = codes.has(code);
                    return (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => toggleAdminAssignment(loc, a)}
                        data-testid={`admin-toggle-${loc.id}-${a.id}`}
                        className={`w-full flex items-center gap-3 cursor-pointer text-sm px-3 py-2 rounded-lg border transition-all text-left ${
                          on
                            ? "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700 text-blue-900 dark:text-blue-100"
                            : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-blue-200 dark:hover:border-blue-800"
                        }`}
                      >
                        <span className={`inline-flex items-center justify-center w-5 h-5 rounded-full border-2 transition-colors ${
                          on
                            ? "bg-blue-500 border-blue-500 text-white"
                            : "border-slate-300 dark:border-slate-600"
                        }`}>
                          {on && <Check className="w-3 h-3" strokeWidth={3} />}
                        </span>
                        <span className="flex-1">
                          {a.name || a.email}
                          <span className="text-[10px] text-slate-400 ml-1">· {a.email}</span>
                        </span>
                        <span className={`text-[10px] font-semibold uppercase tracking-wider ${
                          on ? "text-blue-600 dark:text-blue-400" : "text-slate-400"
                        }`}>
                          {on ? "Tilknyttet" : "Klik for at tilknytte"}
                        </span>
                      </button>
                    );
                  })}
                  <p className="text-[10px] text-slate-400 pt-1">
                    Klik én gang for at tilknytte - klik igen for at frakoble. Samme location-admin kan tildeles flere lokationer.
                  </p>
                </div>
              )}
              {isExpanded && (
                <div className="bg-slate-50 dark:bg-slate-900/40 px-4 pb-3 pt-2 space-y-1.5" data-testid={`partner-picker-${loc.id}`}>
                  {partners.length === 0 ? (
                    <p className="text-xs text-amber-600">
                      Du har ingen logistik-partnere endnu. Tilføj en under fanen "Logistik-partnere".
                    </p>
                  ) : partners.map(p => {
                    const on = assigned.includes(p.id);
                    return (
                      <label key={p.id} className="flex items-center gap-2 cursor-pointer text-sm text-slate-700 dark:text-slate-200 px-2 py-1 rounded hover:bg-white dark:hover:bg-slate-800">
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => togglePartner(loc, p.id)}
                          className="w-4 h-4 accent-emerald-500"
                          data-testid={`partner-toggle-${loc.id}-${p.id}`}
                        />
                        <span className="flex-1">{p.name}</span>
                      </label>
                    );
                  })}
                  <p className="text-[10px] text-slate-400 pt-1">
                    Kun de markerede logistik-firmaer ser denne lokation i deres app og kan modtage bestillinger herfra.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showForm && (
        <Modal title="Ny lokation" onClose={() => setShowForm(false)}>
          <Field label="Navn *"><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="F.eks. KØGE" className={INPUT} data-testid="loc-form-name" /></Field>
          <Field label="Adresse *"><input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} className={INPUT} data-testid="loc-form-address" /></Field>
          <Field label="By *"><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} className={INPUT} data-testid="loc-form-city" /></Field>
          <Field label="Lokationsgruppe (valgfri)">
            <select value={form.location_group_id}
              onChange={e => setForm({ ...form, location_group_id: e.target.value })}
              className={INPUT}
              data-testid="loc-form-group">
              <option value="">- Ingen gruppe -</option>
              {groups.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">
              Opret grupper på fanen <em>Lokationsgrupper</em> så du kan samle flere lokationer (fx Sjælland, Jylland).
            </p>
          </Field>
          <Field label="Tilknyt location admin (valgfri)">
            <select value={form.admin_user_id}
              onChange={e => setForm({ ...form, admin_user_id: e.target.value })}
              className={INPUT}
              data-testid="loc-form-admin-select">
              <option value="">- Vælg eksisterende admin -</option>
              {admins.map(a => (
                <option key={a.id} value={a.id}>{a.name || a.email}</option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">
              Samme admin kan administrere flere lokationer. Lad feltet stå tomt, og tildel admin senere fra "Admins"-knappen.
            </p>
          </Field>
          <FormButtons onCancel={() => setShowForm(false)} onSave={save} saving={saving} />
        </Modal>
      )}

      {editingLoc && (
        <Modal title={`Rediger lokation: ${editingLoc.name}`} onClose={() => setEditingLoc(null)}>
          <Field label="Navn *"><input value={editLocForm.name} onChange={e => setEditLocForm({ ...editLocForm, name: e.target.value })} className={INPUT} data-testid="loc-edit-name" /></Field>
          <Field label="Adresse *"><input value={editLocForm.address} onChange={e => setEditLocForm({ ...editLocForm, address: e.target.value })} className={INPUT} data-testid="loc-edit-address" /></Field>
          <Field label="By *"><input value={editLocForm.city} onChange={e => setEditLocForm({ ...editLocForm, city: e.target.value })} className={INPUT} data-testid="loc-edit-city" /></Field>
          <Field label="Lokationsgruppe">
            <select value={editLocForm.location_group_id}
              onChange={e => setEditLocForm({ ...editLocForm, location_group_id: e.target.value })}
              className={INPUT}
              data-testid="loc-edit-group">
              <option value="">- Ingen gruppe -</option>
              {groups.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </Field>
          <FormButtons onCancel={() => setEditingLoc(null)} onSave={saveEditLocation} saving={false} />
        </Modal>
      )}
    </div>
  );
}

/* ---------- Location admins ---------- */
function LocationAdminsTab() {
  const [admins, setAdmins] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const empty = {
    name: "", email: "", role: "location_admin",
    phone: "", employment_date: "",
    // Multi-location support - first selected becomes primary `location_code`,
    // all selected are stored in assigned_plads_ids
    selected_codes: [],
    // when picker = "__new__", these are filled and a brand new plads is
    // created by the backend at the same time
    location_name: "",
  };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [resendingId, setResendingId] = useState(null);
  const [creatingNewLoc, setCreatingNewLoc] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [u, l] = await Promise.all([
        axios.get(`${API}/org/users`),
        axios.get(`${API}/org/locations`),
      ]);
      setAdmins((u.data || []).filter(x => x.role === "location_admin"));
      setLocations(l.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const toggleCode = (code) => {
    setForm(p => ({
      ...p,
      selected_codes: p.selected_codes.includes(code)
        ? p.selected_codes.filter(c => c !== code)
        : [...p.selected_codes, code],
    }));
  };

  const save = async () => {
    // Fase 15.55 (2026-02-22): Navn + email obligatoriske (både opret + edit).
    if (!form.name.trim()) { toast.error("Navn er påkrævet"); return; }
    if (!form.email.trim()) { toast.error("Email er påkrævet"); return; }
    if (!editing) {
      if (!creatingNewLoc && form.selected_codes.length === 0) {
        toast.error("Vælg mindst én lokation"); return;
      }
      if (creatingNewLoc && !form.location_name.trim()) {
        toast.error("Lokationsnavn er påkrævet"); return;
      }
    }
    setSaving(true);
    try {
      if (editing) {
        // Edit-flow: name/email/phone/employment_date + location set are mutable.
        // Sending location_codes lets the customer_admin add/remove pladser
        // for an existing admin (multi-tenant safe - backend validates).
        const payload = {
          name: form.name.trim(),
          email: form.email.trim().toLowerCase(),
          phone: form.phone.trim(),
          employment_date: form.employment_date.trim(),
        };
        if (form.selected_codes.length > 0) {
          payload.location_codes = form.selected_codes;
        }
        await axios.put(`${API}/org/users/${editing.id}`, payload);
        toast.success("Lokations-admin opdateret");
      } else {
        const body = {
          name: form.name, email: form.email,
          phone: form.phone, employment_date: form.employment_date,
          role: "location_admin",
          send_invitation: true,
          ...(creatingNewLoc
            ? { location_name: form.location_name.trim() }
            : { location_codes: form.selected_codes,
                location_code: form.selected_codes[0] }),
        };
        await axios.post(`${API}/org/users`, body);
        toast.success(creatingNewLoc
          ? `Lokation '${form.location_name}' oprettet - invitation sendt`
          : "Invitation sendt til lokations-admin");
      }
      setShowForm(false); setEditing(null); setForm(empty); setCreatingNewLoc(false); fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const openEdit = (a) => {
    setEditing(a);
    const codes = Array.from(new Set([
      ...(a.assigned_plads_ids || []),
      ...(a.location_code ? [a.location_code] : []),
    ]));
    setCreatingNewLoc(false);
    setForm({
      name: a.name || "",
      email: a.email || "",
      role: "location_admin",
      phone: a.phone || "",
      employment_date: a.employment_date || "",
      selected_codes: codes,
      location_name: "",
    });
    setShowForm(true);
  };
  const openCreate = () => { setEditing(null); setForm(empty); setCreatingNewLoc(false); setShowForm(true); };

  const resendInvite = async (userId, email) => {
    setResendingId(userId);
    try {
      await axios.post(`${API}/org/users/${userId}/resend-invitation`);
      toast.success(`Invitation gensendt til ${email}`);
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setResendingId(null); }
  };
  const remove = async (id) => {
    try { await axios.delete(`${API}/org/users/${id}`); toast.success("Slettet"); fetchAll(); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  const locName = (code) => locations.find(l => l.code === code)?.name || code;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs sm:text-sm text-slate-500 flex-1 min-w-0">En location admin kan administrere flere lokationer på én gang.</p>
        <button onClick={openCreate}
          className="inline-flex items-center justify-center gap-1.5 p-2 sm:px-4 sm:py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shrink-0"
          data-testid="add-location-admin-btn"
          title="Ny location admin">
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">Ny location admin</span>
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : admins.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen lokations-admins endnu</div>
        ) : admins.map(a => {
          const isPending = a.invitation_status === "pending";
          const codes = Array.from(new Set([
            ...(a.assigned_plads_ids || []),
            ...(a.location_code ? [a.location_code] : []),
          ]));
          return (
            <div key={a.id} className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0" data-testid={`ladmin-row-${a.id}`}>
              <div className="min-w-0">
                <p className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2 flex-wrap">
                  {a.name || a.email}
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                    isPending
                      ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
                      : a.active === false
                        ? "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                        : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                  }`} data-testid={`ladmin-status-${a.id}`}>
                    {isPending ? "Afventer" : a.active === false ? "Inaktiv" : "Aktiv"}
                  </span>
                </p>
                <p className="text-xs text-slate-400 truncate">
                  {a.email}
                </p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {codes.length === 0 ? (
                    <span className="text-[10px] uppercase tracking-wider text-slate-400">Ingen lokationer</span>
                  ) : codes.map(c => (
                    <span key={c} data-testid={`ladmin-loc-${a.id}-${c}`}
                      className="text-[10px] uppercase tracking-wider bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full font-semibold">
                      {locName(c)}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex gap-1 ml-3 shrink-0">
                <button onClick={() => openEdit(a)}
                  className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                  title="Rediger"
                  data-testid={`ladmin-edit-${a.id}`}>
                  <Edit2 className="w-4 h-4" />
                </button>
                {isPending && (
                  <button onClick={() => resendInvite(a.id, a.email)} disabled={resendingId === a.id}
                    className="p-1.5 rounded hover:bg-orange-50 dark:hover:bg-orange-950/30 text-slate-400 hover:text-orange-500 disabled:opacity-50"
                    title="Gensend invitation"
                    data-testid={`ladmin-resend-${a.id}`}>
                    {resendingId === a.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                  </button>
                )}
                <button onClick={() => remove(a.id)} className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500" title="Slet">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {showForm && (
        <Modal title={editing ? "Rediger location admin" : "Ny location admin"} onClose={() => { setShowForm(false); setEditing(null); }}>
          {!editing && (
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-2">
                <button type="button" onClick={() => setCreatingNewLoc(false)}
                  className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold ${!creatingNewLoc ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"}`}
                  data-testid="loc-mode-existing">
                  Vælg eksisterende
                </button>
                <button type="button" onClick={() => setCreatingNewLoc(true)}
                  className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold ${creatingNewLoc ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"}`}
                  data-testid="loc-mode-new">
                  Opret ny lokation
                </button>
              </div>
              {creatingNewLoc ? (
                <Field label="Nyt lokationsnavn">
                  <input value={form.location_name}
                    onChange={e => setForm({ ...form, location_name: e.target.value })}
                    placeholder="F.eks. KØGE"
                    className={INPUT}
                    data-testid="loc-admin-new-location-name" />
                  <p className="text-[11px] text-slate-400 mt-1">En 4-cifret kode genereres automatisk.</p>
                </Field>
              ) : (
                <Field label={`Vælg lokation(er) - ${form.selected_codes.length} valgt`}>
                  {locations.length === 0 ? (
                    <p className="text-xs text-amber-600">Ingen lokationer endnu. Opret én under fanen "Lokationer", eller brug knappen "Opret ny lokation" ovenfor.</p>
                  ) : (
                    <div className="space-y-1 max-h-48 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2">
                      {locations.map(l => {
                        const on = form.selected_codes.includes(l.code);
                        return (
                          <label key={l.code} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm">
                            <input type="checkbox" checked={on}
                              onChange={() => toggleCode(l.code)}
                              className="w-4 h-4 accent-emerald-500"
                              data-testid={`loc-code-${l.code}`} />
                            <span className="flex-1">{l.name} <span className="text-[10px] text-slate-400">· {l.code}</span></span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </Field>
              )}
            </div>
          )}
          {editing && (
            <Field label={`Lokationer - ${form.selected_codes.length} valgt`}>
              {locations.length === 0 ? (
                <p className="text-xs text-amber-600">Ingen lokationer endnu.</p>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2">
                  {locations.map(l => {
                    const on = form.selected_codes.includes(l.code);
                    return (
                      <label key={l.code} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer text-sm">
                        <input type="checkbox" checked={on}
                          onChange={() => toggleCode(l.code)}
                          className="w-4 h-4 accent-emerald-500"
                          data-testid={`edit-loc-code-${l.code}`} />
                        <span className="flex-1">{l.name} <span className="text-[10px] text-slate-400">· {l.code}</span></span>
                      </label>
                    );
                  })}
                </div>
              )}
              <p className="text-[11px] text-slate-400 mt-1">
                Samme admin kan tildeles flere lokationer på én gang.
              </p>
            </Field>
          )}
          <Field label="Navn *"><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={INPUT} data-testid="ladmin-name-input" /></Field>
          <Field label="Email *"><input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={INPUT} data-testid="ladmin-email-input" /></Field>
          <Field label="Telefon"><input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={INPUT} data-testid="ladmin-phone-input" /></Field>
          {!editing && (
            <p className="text-xs text-slate-500 -mt-2 mb-1">
              Location admin'en modtager en invitations-mail med et 72-timers link, hvor de selv vælger deres adgangskode.
            </p>
          )}
          {editing && (
            <p className="text-xs text-slate-500 -mt-2 mb-1">
              Hvis du ændrer e-mailen, skal admin'en bruge den nye til at logge ind. Adgangskoden ændres ikke automatisk.
            </p>
          )}
          <FormButtons onCancel={() => { setShowForm(false); setEditing(null); }} onSave={save} saving={saving} />
        </Modal>
      )}
    </div>
  );
}

/* ---------- Logistics partners ---------- */
function PartnersTab() {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linkFor, setLinkFor] = useState(null); // company being linked (confirmation only)
  const [unlinkFor, setUnlinkFor] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/org/logistics-companies`); setCompanies(data || []); }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchCompanies(); }, [fetchCompanies]);

  const link = async (companyId) => {
    setSaving(true);
    try {
      // Customer admins can ONLY assign; creating the logistics admin user
      // (email/password) is the System Owner's responsibility.
      await axios.post(`${API}/org/logistics-partners`, { logistics_company_id: companyId });
      toast.success("Logistik-partner tilknyttet");
      setLinkFor(null); fetchCompanies();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };
  // 2026-10-18: Frakobling fjerner også partnerens adgang til jeres pladser og
  // til ture, der ikke er startet (de skal gives til en anden partner).
  const unlink = async (companyId) => {
    setSaving(true);
    try {
      const { data } = await axios.delete(`${API}/org/logistics-partners/${companyId}`);
      const n = data?.open_tours_released || 0;
      toast.success(n ? `Frakoblet - ${n} tur${n === 1 ? "" : "e"}, der ikke var startet, er taget fra partneren` : "Frakoblet");
      setUnlinkFor(null); fetchCompanies();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">Tilknyt et logistik-firma så deres chauffører kan se og køre jeres ture.
        Et logistik-firma kan betjene flere kunder. <span className="text-slate-400">Bruger-oprettelse (email/adgangskode) håndteres af system-ejeren.</span></p>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : companies.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen logistik-firmaer i systemet endnu - bed system-ejeren oprette ét.</div>
        ) : companies.map(c => (
          <div key={c.id} className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0">
            <div className="flex items-center gap-2">
              <Truck className="w-4 h-4 text-blue-500" />
              <span className="font-semibold text-sm text-slate-800 dark:text-white">{c.name}</span>
              {c.linked && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300">Tilknyttet</span>}
            </div>
            {c.linked ? (
              <button onClick={() => setUnlinkFor(c)} data-testid={`unlink-partner-${c.id}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg text-xs font-semibold">
                <Link2Off className="w-3.5 h-3.5" /> Frakobl
              </button>
            ) : (
              <button onClick={() => setLinkFor(c)} data-testid={`link-partner-${c.id}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold">
                <Link2 className="w-3.5 h-3.5" /> Tilknyt
              </button>
            )}
          </div>
        ))}
      </div>

      {unlinkFor && (
        <Modal title={`Frakobl ${unlinkFor.name}?`} onClose={() => setUnlinkFor(null)}>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-2">
            <span className="font-bold">{unlinkFor.name}</span> mister adgangen til jeres pladser og bestillinger.
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
            Ture, der ikke er startet, fjernes fra dem - tildel pladsen til en anden partner, så får den partner turene. Ture, der er i gang eller kørt, kan de stadig se.
          </p>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setUnlinkFor(null)} disabled={saving} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
            <button onClick={() => unlink(unlinkFor.id)} disabled={saving} data-testid="confirm-unlink-partner-btn" className="px-4 py-2 rounded-lg text-sm font-semibold bg-rose-600 hover:bg-rose-700 text-white inline-flex items-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2Off className="w-4 h-4" />} Frakobl
            </button>
          </div>
        </Modal>
      )}

      {linkFor && (
        <Modal title={`Tilknyt ${linkFor.name}`} onClose={() => setLinkFor(null)}>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-2">
            Du tilknytter <span className="font-bold">{linkFor.name}</span> som logistik-partner.
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
            Logistik-firmaets admin (email & adgangskode) er allerede oprettet af system-ejeren.
            Her tilknytter du blot firmaet, så dets chauffører kan se jeres ture.
          </p>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setLinkFor(null)} disabled={saving} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
            <button onClick={() => link(linkFor.id)} disabled={saving} data-testid="confirm-link-partner-btn" className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Tilknyt
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ---------- Report (org-wide) ---------- */
function ReportTab() {
  // Brugerkrav 2026-06-15: Customer Admin Reports - på TVÆRS af alle
  // lokationer i kundens selskab + per-lokation breakdown. Kunden kan
  // også filtrere på en delmængde af pladser via multi-select.
  const [period, setPeriod] = useState("month");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [locationOptions, setLocationOptions] = useState([]);
  const [selectedCodes, setSelectedCodes] = useState([]); // tom = ALLE
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Pre-load PDF lib only - Excel-eksporten bruger nu vores ExcelJS-helper.
  const pdfRef = useRef(null);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const jp = await import("jspdf");
        const at = await import("jspdf-autotable");
        if (active) pdfRef.current = { jsPDF: jp.jsPDF || jp.default, autoTable: at.default || at.autoTable };
      } catch (_) { /* lib indlæsning kan fejle silent */ }
    })();
    return () => { active = false; };
  }, []);

  // Hent kundens lokationer til filter-listen
  useEffect(() => {
    axios.get(`${API}/org/locations`)
      .then(r => setLocationOptions((r.data || []).map(l => ({ code: l.code || l.location_code, name: l.name }))))
      .catch(() => setLocationOptions([]));
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ period });
      if (period === "custom") {
        if (!start || !end) { setLoading(false); return; }
        params.set("start", start); params.set("end", end);
      }
      if (selectedCodes.length > 0) params.set("location_codes", selectedCodes.join(","));
      const r = await axios.get(`${API}/org/reports/orders-multi?${params.toString()}`);
      setData(r.data);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [period, start, end, selectedCodes]);
  useEffect(() => { fetchData(); }, [fetchData]);

  // Robust download (saveAs + fallbacks)
  const triggerDownload = (blob, filename) => {
    try { saveAs(blob, filename); return true; }
    catch (_) {
      const url = URL.createObjectURL(blob);
      try {
        const a = document.createElement("a"); a.href = url; a.download = filename;
        a.style.display = "none"; document.body.appendChild(a); a.click();
        setTimeout(() => { try { document.body.removeChild(a); } catch (__) { /* node muligvis allerede væk */ } setTimeout(() => URL.revokeObjectURL(url), 4000); }, 100);
        return true;
      } catch (__) {
        try { window.open(url, "_blank", "noopener"); } catch (___) { /* popup blokeret */ }
        setTimeout(() => URL.revokeObjectURL(url), 8000);
        return false;
      }
    }
  };

  const exportExcel = async () => {
    if (!data) return;
    try {
      const scope = selectedCodes.length === 0
        ? "Alle lokationer"
        : `${selectedCodes.length} lokation${selectedCodes.length === 1 ? "" : "er"}`;
      await exportReportXLSX({
        data,
        title: "Kunde-rapport på tværs af lokationer",
        subtitle: `${scope} · Periode ${data.start} til ${data.end}`,
        includeByLocation: true,
        filename: `kunderapport-${data.start}-${data.end}.xlsx`,
      });
      toast.success("Excel-fil downloadet");
    } catch (e) {
      console.error("[CA exportExcel]", e);
      toast.error("Kunne ikke generere Excel-fil: " + (e?.message || "ukendt fejl"));
    }
  };

  const exportPDF = () => {
    if (!data) return;
    const lib = pdfRef.current;
    if (!lib) { toast.error("PDF-bibliotek indlæses stadig. Prøv igen om et øjeblik."); return; }
    try {
      const { jsPDF, autoTable } = lib;
      const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
      doc.setFontSize(16);
      doc.text(`Kunderapport ${data.start} -> ${data.end}`, 40, 40);
      doc.setFontSize(11);
      doc.text(`Lokationer: ${data.location_count} · Bestillinger: ${data.total_orders}`, 40, 60);
      doc.text(`Afventer (periode): ${data.pending_in_period} · Haste bestillinger: ${data.urgent_count ?? 0}`, 40, 75);
      autoTable(doc, {
        head: [["Lokation", "Kode", "Antal", "Afventer", "Vægt (kg)"]],
        body: (data.by_location || []).map(l => [l.location_name, l.location_code, l.count, l.pending, l.weight]),
        startY: 100,
      });
      autoTable(doc, {
        head: [["Materiale", "Antal", "Vægt (kg)"]],
        body: (data.by_material || []).map(m => [m.name, m.count, m.weight]),
      });
      autoTable(doc, {
        head: [["Medarbejder", "Antal"]],
        body: (data.by_employee || []).map(e => [e.name, e.count]),
      });
      const blob = doc.output("blob");
      const ok = triggerDownload(blob, `kunderapport-${data.start}-${data.end}.pdf`);
      toast.success(ok ? "PDF downloadet" : "PDF åbnet i ny tab");
    } catch (e) {
      console.error("[CA exportPDF]", e);
      toast.error("Kunne ikke generere PDF: " + (e?.message || "ukendt fejl"));
    }
  };

  const toggleLocation = (code) => {
    setSelectedCodes(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);
  };

  const PERIODS = [
    ["day", "I dag"], ["week", "Uge"], ["month", "Måned"],
    ["3months", "3 mdr"], ["6months", "6 mdr"], ["year", "År"], ["custom", "Brugerdef."],
  ];

  return (
    <div className="space-y-5" data-testid="cadmin-report-tab">
      {/* Filter row */}
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2" data-testid="cadmin-report-period-row">
          {PERIODS.map(([v, l]) => (
            <button key={v} onClick={() => setPeriod(v)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium ${period === v ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"}`}
              data-testid={`cadmin-period-${v}`}>{l}</button>
          ))}
          {period === "custom" && (
            <>
              <input type="date" value={start} onChange={e => setStart(e.target.value)}
                className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-sm"
                data-testid="cadmin-period-start" />
              <span className="text-slate-500">→</span>
              <input type="date" value={end} onChange={e => setEnd(e.target.value)}
                className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-sm"
                data-testid="cadmin-period-end" />
            </>
          )}
          <div className="ml-auto flex gap-2">
            <button onClick={exportExcel} disabled={!data}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-100 text-xs font-bold disabled:opacity-50"
              data-testid="cadmin-export-excel">
              <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
            </button>
            <button onClick={exportPDF} disabled={!data}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-100 text-xs font-bold disabled:opacity-50"
              data-testid="cadmin-export-pdf">
              <FileDown className="w-3.5 h-3.5" /> PDF
            </button>
          </div>
        </div>
        {/* Multi-location chip filter */}
        <div className="flex flex-wrap gap-1.5 items-center" data-testid="cadmin-location-filter">
          <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mr-1">Lokationer:</span>
          <button onClick={() => setSelectedCodes([])}
            className={`px-2.5 py-1 rounded-full text-xs font-semibold ${selectedCodes.length === 0 ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"}`}
            data-testid="cadmin-loc-all">
            Alle ({locationOptions.length})
          </button>
          {locationOptions.map(l => (
            <button key={l.code} onClick={() => toggleLocation(l.code)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium ${selectedCodes.includes(l.code) ? "bg-emerald-600 text-white" : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"}`}
              data-testid={`cadmin-loc-${l.code}`}>
              {l.name}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="text-center py-10"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
      )}
      {!loading && data && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3" data-testid="cadmin-report-kpis">
            <Kpi label="Bestillinger" value={data.total_orders} />
            <Kpi label="Lokationer" value={data.location_count} />
            <Kpi label="Afventer (periode)" value={data.pending_in_period} accent="amber" />
            <Kpi label="Haste bestillinger" value={data.urgent_count ?? 0} accent="rose" />
            {/* Fase 9 (2026-06-17): Samlet CO2-aftryk for perioden */}
            <Kpi label="CO2 (kg)" value={(data.total_co2_kg ?? 0).toLocaleString("da-DK")} accent="green" />
          </div>

          {/* Fase 9: CO2 udvikling over tid + CO2 pr. materiale */}
          {(data.co2_over_time || []).length > 0 || (data.by_co2_type || []).length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="cadmin-co2-section">
              <Section title="CO2-udvikling over tid" subtitle={`Total ${(data.total_co2_kg ?? 0).toLocaleString("da-DK")} kg CO2 · ${(data.total_weight_kg ?? 0).toLocaleString("da-DK")} kg materiale`} testid="cadmin-co2-over-time">
                {(data.co2_over_time || []).length === 0 ? (
                  <p className="text-slate-400 text-sm italic">Ingen CO2-data i perioden.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={data.co2_over_time}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#64748b" />
                      <YAxis tick={{ fontSize: 11 }} stroke="#64748b" label={{ value: "kg CO2", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip formatter={(v) => `${v.toLocaleString("da-DK")} kg`} />
                      <Line type="monotone" dataKey="co2_kg" stroke="#059669" strokeWidth={2} dot={{ r: 3, fill: "#059669" }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </Section>
              <Section title="CO2 pr. materiale" subtitle="Hvilke materialer trækker mest CO2" testid="cadmin-co2-by-material">
                {(data.by_co2_type || []).filter(t => t.co2_kg > 0).length === 0 ? (
                  <p className="text-slate-400 text-sm italic">Endnu ingen CO2 beregnet (afventer chaufførens vægt).</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={(data.by_co2_type || []).filter(t => t.co2_kg > 0).slice(0, 8)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#64748b" />
                      <YAxis tick={{ fontSize: 11 }} stroke="#64748b" label={{ value: "kg CO2", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <Tooltip formatter={(v, n, p) => [`${v.toLocaleString("da-DK")} kg`, n === "co2_kg" ? "CO2" : n]} />
                      <Bar dataKey="co2_kg" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
                {(data.by_co2_type || []).filter(t => t.co2_kg > 0).length > 0 && (
                  <ul className="mt-3 text-xs space-y-1 border-t border-slate-200 dark:border-slate-700 pt-2">
                    {data.by_co2_type.filter(t => t.co2_kg > 0).slice(0, 6).map(t => (
                      <li key={t.name} className="flex justify-between">
                        <span className="text-slate-600 dark:text-slate-300">
                          {t.name} <span className="text-slate-400">({t.factor.toLocaleString("da-DK")} kg/ton)</span>
                        </span>
                        <span className="font-mono text-emerald-600 dark:text-emerald-400">
                          {t.weight_kg.toLocaleString("da-DK")} kg → <strong>{t.co2_kg.toLocaleString("da-DK")} kg CO2</strong>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </div>
          ) : null}

          {/* Per-location breakdown */}
          <Section title="Pr. lokation" subtitle="Brydes ned så du kan se hvilken plads der trækker mest" testid="cadmin-by-location">
            {(data.by_location || []).length === 0 ? (
              <p className="text-slate-400 text-sm italic">Ingen data i perioden.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-slate-700">
                  <tr><th className="text-left py-2">Lokation</th><th className="text-right py-2">Bestillinger</th><th className="text-right py-2">Afventer</th><th className="text-right py-2">Vægt (kg)</th><th className="text-right py-2">CO2 (kg)</th></tr>
                </thead>
                <tbody>
                  {data.by_location.map(l => (
                    <tr key={l.location_code} className="border-b border-slate-100 dark:border-slate-700/50 last:border-0" data-testid={`cadmin-loc-row-${l.location_code}`}>
                      <td className="py-2 font-semibold text-slate-700 dark:text-slate-200">{l.location_name} <span className="text-[11px] text-slate-400 font-mono ml-1">{l.location_code}</span></td>
                      <td className="text-right text-emerald-600 dark:text-emerald-400 font-bold">{l.count}</td>
                      <td className="text-right text-amber-600 dark:text-amber-400">{l.pending}</td>
                      <td className="text-right text-slate-600 dark:text-slate-300">{l.weight.toLocaleString("da-DK")}</td>
                      <td className="text-right text-emerald-700 dark:text-emerald-300 font-semibold">{(l.co2_kg ?? 0).toLocaleString("da-DK")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Section title="Pr. materiale" subtitle="Samlet på tværs af alle valgte lokationer" testid="cadmin-by-material">
              {(data.by_material || []).length === 0 ? (
                <p className="text-slate-400 text-sm italic">Ingen data.</p>
              ) : (
                <ul className="space-y-1.5">
                  {data.by_material.slice(0, 10).map(m => (
                    <li key={m.name} className="flex items-center justify-between text-sm">
                      <span className="text-slate-700 dark:text-slate-200">{m.name}</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">{m.count} · {m.weight.toLocaleString("da-DK")} kg</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
            <Section title="Pr. medarbejder" subtitle="Top bestillere" testid="cadmin-by-employee">
              {(data.by_employee || []).length === 0 ? (
                <p className="text-slate-400 text-sm italic">Ingen data.</p>
              ) : (
                <ul className="space-y-1.5">
                  {data.by_employee.slice(0, 10).map(e => (
                    <li key={e.name} className="flex items-center justify-between text-sm">
                      <span className="text-slate-700 dark:text-slate-200 truncate">{e.name}</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">{e.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, accent }) {
  const color = accent === "amber" ? "text-amber-600 dark:text-amber-400"
    : accent === "rose" ? "text-rose-600 dark:text-rose-400"
    : accent === "green" ? "text-emerald-600 dark:text-emerald-400"
    : "text-emerald-600 dark:text-emerald-400";
  return (
    <div className={`bg-white dark:bg-slate-800 border ${accent === "green" ? "border-emerald-200 dark:border-emerald-800 bg-gradient-to-br from-white to-emerald-50/30 dark:from-slate-800 dark:to-emerald-950/10" : "border-slate-200 dark:border-slate-700"} rounded-xl p-3`} data-testid={`cadmin-kpi-${label.toLowerCase().replace(/[^a-z]/g, '-')}`}>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center gap-1">
        {accent === "green" && <Leaf className="w-3 h-3 text-emerald-500" />}
        {label}
      </p>
      <p className={`text-2xl font-black ${color}`}>{value}</p>
    </div>
  );
}

function Section({ title, subtitle, children, testid }) {
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-4" data-testid={testid}>
      <p className="font-bold text-slate-900 dark:text-white">{title}</p>
      {subtitle && <p className="text-xs text-slate-500 mb-3">{subtitle}</p>}
      {children}
    </div>
  );
}

/* ---------- small shared UI ---------- */
const INPUT = "w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-emerald-500 outline-none";
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
      <button onClick={onSave} disabled={saving} className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white inline-flex items-center gap-2">
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem
      </button>
    </div>
  );
}


/* ============================ LOCATION GROUPS TAB ============================ */
function LocationGroupsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/org/location-groups`);
      setItems(r.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const save = async () => {
    if (!name.trim()) { toast.error("Navn er påkrævet"); return; }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API}/org/location-groups/${editing.id}`, { name: name.trim() });
        toast.success("Lokationsgruppe opdateret");
      } else {
        await axios.post(`${API}/org/location-groups`, { name: name.trim() });
        toast.success("Lokationsgruppe oprettet");
      }
      setShowForm(false); setEditing(null); setName("");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const remove = async (g) => {
    if (!window.confirm(`Slet "${g.name}"?\n\nLokationer der peger på gruppen frakobles automatisk.`)) return;
    try {
      await axios.delete(`${API}/org/location-groups/${g.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-4" data-testid="location-groups-tab">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs sm:text-sm text-slate-500 flex-1 min-w-0">
          Grupper flere lokationer (fx <em>Sjælland</em> = Roskilde + Køge + Greve). Bruges som filter på rapporter og fremtidige chauffør-flows.
        </p>
        <button onClick={() => { setEditing(null); setName(""); setShowForm(true); }}
          className="inline-flex items-center justify-center gap-1.5 p-2 sm:px-4 sm:py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shrink-0"
          data-testid="add-group-btn"
          title="Ny lokationsgruppe">
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">Ny lokationsgruppe</span>
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen lokationsgrupper endnu</div>
        ) : items.map(g => (
          <div key={g.id} className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0"
            data-testid={`group-row-${g.id}`}>
            <div>
              <p className="font-semibold text-sm text-slate-800 dark:text-white">{g.name}</p>
              <p className="text-xs text-slate-400">{g.locations_count ?? 0} lokation{(g.locations_count ?? 0) === 1 ? "" : "er"}</p>
            </div>
            <div className="flex gap-1">
              <button onClick={() => { setEditing(g); setName(g.name); setShowForm(true); }}
                className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                title="Rediger" data-testid={`edit-group-${g.id}`}>
                <Edit2 className="w-4 h-4" />
              </button>
              <button onClick={() => remove(g)}
                className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500"
                title="Slet" data-testid={`delete-group-${g.id}`}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <Modal title={editing ? "Rediger lokationsgruppe" : "Ny lokationsgruppe"} onClose={() => { setShowForm(false); setEditing(null); }}>
          <Field label="Navn *">
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder='fx "Sjælland"'
              className={INPUT}
              data-testid="group-name-input" />
          </Field>
          <FormButtons
            onCancel={() => { setShowForm(false); setEditing(null); }}
            onSave={save} saving={saving} />
        </Modal>
      )}
    </div>
  );
}

/* ============================ WORKSHOPS TAB ============================ */
function WorkshopsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | "new" | obj

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/org/workshops`);
      setItems(r.data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const remove = async (w) => {
    if (!window.confirm(`Slet værksted "${w.name}"?\n\nFremtidige bestillinger vil ikke længere kunne vælge det.`)) return;
    try {
      await axios.delete(`${API}/org/workshops/${w.id}`);
      toast.success("Slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="space-y-4" data-testid="workshops-tab">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-500">
          Et bibliotek af værksteder som dine ordrebrugere kan vælge når en bestilling er <em>Til værksted</em> eller <em>Afhent fra værksted</em>.
        </p>
        <button onClick={() => setEditing("new")}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold"
          data-testid="add-workshop-btn">
          <Plus className="w-4 h-4" /> Nyt værksted
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen værksteder endnu</div>
        ) : items.map(w => (
          <div key={w.id} className="flex items-start justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0"
            data-testid={`workshop-row-${w.id}`}>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm text-slate-800 dark:text-white inline-flex items-center gap-2">
                <Wrench className="w-3.5 h-3.5 text-emerald-500" />
                {w.name}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{w.address}</p>
              <div className="flex flex-wrap gap-3 mt-1">
                {w.phone && (
                  <span className="text-[11px] text-slate-500 inline-flex items-center gap-1">
                    <Phone className="w-3 h-3" /> {w.phone}
                  </span>
                )}
                {w.comment && (
                  <span className="text-[11px] text-slate-500 inline-flex items-center gap-1 max-w-md truncate">
                    <MessageSquare className="w-3 h-3" /> {w.comment}
                  </span>
                )}
              </div>
            </div>
            <div className="flex gap-1 shrink-0">
              <button onClick={() => setEditing(w)}
                className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                title="Rediger" data-testid={`edit-workshop-${w.id}`}>
                <Edit2 className="w-4 h-4" />
              </button>
              <button onClick={() => remove(w)}
                className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500"
                title="Slet" data-testid={`delete-workshop-${w.id}`}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {editing && (
        <WorkshopModal
          workshop={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}
    </div>
  );
}

function WorkshopModal({ workshop, onClose, onSaved }) {
  const isEdit = !!workshop;
  const [name, setName] = useState(workshop?.name || "");
  const [address, setAddress] = useState(workshop?.address || "");
  const [phone, setPhone] = useState(workshop?.phone || "");
  const [comment, setComment] = useState(workshop?.comment || "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) { toast.error("Navn er påkrævet"); return; }
    if (!address.trim()) { toast.error("Adresse er påkrævet"); return; }
    setSaving(true);
    try {
      const payload = { name: name.trim(), address: address.trim(),
                        phone: phone.trim(), comment: comment.trim() };
      if (isEdit) {
        await axios.put(`${API}/org/workshops/${workshop.id}`, payload);
        toast.success("Værksted opdateret");
      } else {
        await axios.post(`${API}/org/workshops`, payload);
        toast.success("Værksted oprettet");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <Modal title={isEdit ? "Rediger værksted" : "Nyt værksted"} onClose={onClose}>
      <Field label="Navn *">
        <input value={name} onChange={e => setName(e.target.value)}
          placeholder='fx "Værksted Nord"'
          className={INPUT}
          data-testid="workshop-name-input" />
      </Field>
      <Field label="Adresse *">
        <input value={address} onChange={e => setAddress(e.target.value)}
          placeholder='fx "Hovedvej 21, 4000 Roskilde"'
          className={INPUT}
          data-testid="workshop-address-input" />
      </Field>
      <Field label="Telefon (valgfri)">
        <input value={phone} onChange={e => setPhone(e.target.value)}
          className={INPUT}
          data-testid="workshop-phone-input" />
      </Field>
      <Field label="Kommentar (valgfri)">
        <textarea value={comment} onChange={e => setComment(e.target.value)}
          rows={3}
          placeholder="Fx åbningstider, ansvarlig kontakt, instruktioner…"
          className={`${INPUT} resize-none`}
          data-testid="workshop-comment-input" />
      </Field>
      <FormButtons onCancel={onClose} onSave={save} saving={saving} />
    </Modal>
  );
}


/* ---------- CO2-typer (Fase 9 - 2026-06-17) ---------- */
/**
 * Per-kunde bibliotek af materiale + CO2-faktor (kg CO2 per ton).
 * Bruges af bestillinger til at beregne CO2 automatisk når vægten lander
 * fra chaufførens kvittering: co2_kg = factor × (weight_kg / 1000).
 */
function CO2TypesTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", factor: 0 });
  const [saving, setSaving] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/co2-types`);
      setItems(r.data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { fetchItems(); }, [fetchItems]);

  const startCreate = () => { setEditing(null); setForm({ name: "", factor: 0 }); setShowForm(true); };
  const startEdit = (t) => { setEditing(t); setForm({ name: t.name, factor: t.factor }); setShowForm(true); };

  const save = async () => {
    // Fase 15.55 (2026-02-22): Navn + Faktor obligatoriske. Faktor=0 er
    // tilladt for materialer uden CO2-aftryk (jord, beton, tegl), men
    // feltet skal være EKSPLICIT udfyldt (ikke tomt).
    if (!form.name.trim()) { toast.error("Navn er påkrævet"); return; }
    const rawFactor = String(form.factor ?? "").trim();
    if (rawFactor === "") { toast.error("Faktor er påkrævet (skriv 0 for materialer uden CO2-aftryk)"); return; }
    const f = parseFloat(rawFactor);
    if (!Number.isFinite(f) || f < 0) {
      toast.error("Faktor skal være et tal ≥ 0");
      return;
    }
    setSaving(true);
    try {
      const payload = { name: form.name.trim(), factor: parseFloat(form.factor) || 0 };
      if (editing) {
        await axios.put(`${API}/co2-types/${editing.id}`, payload);
        toast.success(`CO2-type "${payload.name}" opdateret`);
      } else {
        await axios.post(`${API}/co2-types`, payload);
        toast.success(`CO2-type "${payload.name}" oprettet`);
      }
      setShowForm(false);
      await fetchItems();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const del = async (t) => {
    if (!window.confirm(`Slet CO2-type "${t.name}"? Eksisterende ordrer beholder deres beregnede CO2.`)) return;
    try {
      await axios.delete(`${API}/co2-types/${t.id}`);
      toast.success("Slettet");
      await fetchItems();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="space-y-4" data-testid="co2-types-tab">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base sm:text-lg font-bold flex items-center gap-2">
            <Leaf className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-600 shrink-0" /> CO2-typer
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Definer materialer med CO2-faktor (kg CO2 per ton). Skriv 0 for materialer uden CO2-aftryk.
          </p>
        </div>
        {/* Kompakt knap: ikon-only på mobil, ikon+tekst på desktop */}
        <button onClick={startCreate}
          className="inline-flex items-center justify-center gap-1.5 p-2 sm:px-3 sm:py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg shadow-sm shrink-0"
          data-testid="co2-add-btn"
          title="Opret CO2-type">
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">Opret CO2-type</span>
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Henter…
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-8 text-center" data-testid="co2-empty">
          <Leaf className="w-8 h-8 mx-auto text-emerald-600 opacity-50 mb-2" />
          <p className="text-sm text-muted-foreground">Endnu ingen CO2-typer. Opret den første med <strong>Opret CO2-type</strong> ovenfor.</p>
          <p className="text-xs text-muted-foreground mt-2">Eksempler: PAP (1.300 kg/ton), Træ (80 kg/ton), Metal (22 kg/ton), Beton (0 kg/ton).</p>
        </div>
      ) : (
        <>
        {/* Mobil: card-layout (Fase 18.28) - hver CO2-type vises som et kort
            med navn + faktor stablet, så Faktor ikke gemmes bag tabel-scroll. */}
        <div className="sm:hidden space-y-2" data-testid="co2-cards-mobile">
          {items.map(t => (
            <div key={t.id} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-3 flex items-center gap-3" data-testid={`co2-card-${t.id}`}>
              <div className="w-9 h-9 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                <Leaf className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm text-slate-900 dark:text-white truncate">{t.name}</p>
                <p className="text-xs mt-0.5">
                  <span className="text-slate-500">Faktor: </span>
                  <span className={`font-bold font-mono ${t.factor === 0 ? "text-slate-500" : "text-emerald-600 dark:text-emerald-400"}`}>
                    {t.factor.toLocaleString("da-DK")} kg/ton
                  </span>
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => startEdit(t)} className="p-2 text-slate-500 hover:text-emerald-600 rounded-lg" data-testid={`co2-edit-mobile-${t.id}`}>
                  <Edit2 className="w-4 h-4" />
                </button>
                <button onClick={() => del(t)} className="p-2 text-slate-500 hover:text-red-600 rounded-lg" data-testid={`co2-delete-mobile-${t.id}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-muted-foreground mt-2 px-1">
            CO2 beregnes automatisk: <strong>CO2 = faktor × (vægt_kg ÷ 1000)</strong>.
          </p>
        </div>
        {/* Desktop: original tabel-layout */}
        <div className="hidden sm:block bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-400">Navn</th>
                <th className="px-4 py-3 text-right font-semibold text-slate-600 dark:text-slate-400">Faktor <span className="font-normal text-xs">(kg CO2 / ton)</span></th>
                <th className="px-4 py-3 text-center font-semibold text-slate-600 dark:text-slate-400 w-32">Handlinger</th>
              </tr>
            </thead>
            <tbody>
              {items.map(t => (
                <tr key={t.id} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/50" data-testid={`co2-row-${t.id}`}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900 dark:text-white">{t.name}</div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-bold ${t.factor === 0 ? "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300" : "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300"}`}>
                      {t.factor.toLocaleString("da-DK")} kg/ton
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button onClick={() => startEdit(t)} className="p-1.5 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 rounded" data-testid={`co2-edit-${t.id}`}>
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => del(t)} className="p-1.5 text-slate-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded" data-testid={`co2-delete-${t.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900/50 text-xs text-muted-foreground border-t border-slate-200 dark:border-slate-700">
            CO2 beregnes automatisk på bestillinger: <strong>CO2 = faktor × (vægt_kg ÷ 1000)</strong>. Vægten hentes fra chaufførens kvittering.
          </div>
        </div>
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="co2-form-modal">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Leaf className="w-5 h-5 text-emerald-600" />
                {editing ? "Rediger CO2-type" : "Opret CO2-type"}
              </h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Navn (typisk materiale) *</label>
                <input type="text" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="fx PAP, Træ, Metal, Beton"
                  className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:border-emerald-500 focus:outline-none bg-white dark:bg-slate-800"
                  data-testid="co2-name-input" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Faktor <span className="font-normal">(kg CO2 per ton)</span> *</label>
                <input type="number" step="0.1" min="0" value={form.factor}
                  onChange={(e) => setForm({ ...form, factor: e.target.value })}
                  placeholder="80"
                  className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:border-emerald-500 focus:outline-none bg-white dark:bg-slate-800 font-mono"
                  data-testid="co2-factor-input" />
                <p className="text-[11px] text-muted-foreground mt-1">Skriv 0 hvis materialet ikke har CO2-aftryk (jord, beton, tegl).</p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">Annullér</button>
              <button onClick={save} disabled={saving}
                className="px-4 py-2 text-sm font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                data-testid="co2-save-btn">
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {editing ? "Gem" : "Opret"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
