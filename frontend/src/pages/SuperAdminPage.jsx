import React, { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Shield, Building2, Users, Plus, Trash2, Edit2, X, LogOut, Mail,
  Download, Check,
  Search, KeyRound, UserPlus, Building, Loader2, AlertTriangle,
  MapPin, Layers, Upload, ChevronDown, Home, ListPlus, Settings, Eye, EyeOff, Save,
  BarChart3, TrendingUp, Truck, Calendar, Activity, FileSpreadsheet,
  CheckCircle2, XCircle, Clock, AlertCircle, Globe, Recycle, Power, PowerOff,
  GitMerge, FileText, FileDown, Copy, Pause, Send, Megaphone,
  Archive, History,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";

const ROLES = [
  { value: "customer_admin", label: "Kunde Admin" },
  { value: "location_admin", label: "Lokations Admin" },
  { value: "logistics_admin", label: "Logistics Admin" },
  { value: "driver", label: "Chauffør" },
  { value: "order", label: "Order" },
  { value: "genbrug_plads", label: "Genbrug Plads" },
  { value: "super_admin", label: "Super Admin" },
];

// ============== Export Helpers (Plads addresses) ==============
async function fetchPladsAddressesMap(pladsList) {
  // Fetch sub-addresses for each plads in parallel; return map { plads_id: [addresses] }
  const map = {};
  await Promise.all(
    (pladsList || []).map(async (p) => {
      try {
        const { data } = await axios.get(`${API}/superadmin/plads/${p.id}/addresses`);
        map[p.id] = data || [];
      } catch (_) {
        map[p.id] = [];
      }
    }),
  );
  return map;
}

async function exportPladsExcel(pladsList, companies) {
  if (!pladsList || pladsList.length === 0) {
    toast.error("Ingen pladser at eksportere");
    return;
  }
  // Brugerkrav 2026-06-15: ÉT ark - pladser + underadresser i en samlet
  // tabel hvor underadresser indrykkes under deres plads. Bruger ExcelJS for
  // styling (frozen header, autofilter, brand-banner, totals).
  try {
    const { default: ExcelJS } = await import("exceljs");
    const { saveAs } = await import("file-saver");
    const cmap = Object.fromEntries((companies || []).map((c) => [c.id, c.name]));
    const addrMap = await fetchPladsAddressesMap(pladsList);

    const wb = new ExcelJS.Workbook();
    wb.creator = "ContainerFlow";
    wb.created = new Date();
    const ws = wb.addWorksheet("Pladser", { views: [{ state: "frozen", ySplit: 4 }] });
    ws.columns = [
      { width: 24 }, { width: 30 }, { width: 14 }, { width: 30 }, { width: 16 },
      { width: 20 }, { width: 8 },
    ];

    // Title-banner
    ws.mergeCells("A1:G1");
    const t = ws.getCell("A1");
    t.value = "ContainerFlow - Pladser & underadresser";
    t.font = { bold: true, size: 16, color: { argb: "FFFFFFFF" } };
    t.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF1E3A8A" } };
    t.alignment = { vertical: "middle", indent: 1 };
    ws.getRow(1).height = 28;

    ws.mergeCells("A2:G2");
    const s = ws.getCell("A2");
    s.value = `${pladsList.length} pladser · genereret ${new Date().toLocaleString("da-DK")}`;
    s.font = { italic: true, color: { argb: "FF64748B" }, size: 10 };
    s.alignment = { vertical: "middle", indent: 1 };

    // Header
    const headers = ["Virksomhed", "Plads-navn", "Lokationskode", "Adresse", "By", "Underadresse / Område", "Postnr"];
    headers.forEach((h, i) => {
      const c = ws.getCell(4, i + 1);
      c.value = h;
      c.font = { bold: true, color: { argb: "FFFFFFFF" } };
      c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF1E3A8A" } };
      c.alignment = { vertical: "middle", indent: 1 };
      c.border = {
        top: { style: "thin", color: { argb: "FFB6C6E5" } },
        left: { style: "thin", color: { argb: "FFB6C6E5" } },
        bottom: { style: "thin", color: { argb: "FFB6C6E5" } },
        right: { style: "thin", color: { argb: "FFB6C6E5" } },
      };
    });
    ws.getRow(4).height = 22;

    let row = 5;
    const startData = row;
    let stripe = false;
    pladsList.forEach((p) => {
      const company = cmap[p.company_id] || p.company_name || "";
      const baseRow = [company, p.name || "", p.location_code || "", p.address || "", p.city || "", "", ""];
      ws.getRow(row).values = baseRow;
      ws.getRow(row).eachCell((cell) => {
        cell.alignment = { vertical: "middle", indent: 1 };
        if (stripe) cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF7FAFC" } };
        cell.border = {
          top: { style: "thin", color: { argb: "FFE2E8F0" } },
          left: { style: "thin", color: { argb: "FFE2E8F0" } },
          bottom: { style: "thin", color: { argb: "FFE2E8F0" } },
          right: { style: "thin", color: { argb: "FFE2E8F0" } },
        };
      });
      row++;

      // Indrykkede underadresser
      (addrMap[p.id] || []).forEach((a) => {
        ws.getCell(row, 1).value = "";
        ws.getCell(row, 2).value = `   ↳ ${a.sub_area || "Område"}`;
        ws.getCell(row, 4).value = a.street || "";
        ws.getCell(row, 5).value = a.city || "";
        ws.getCell(row, 6).value = a.sub_area || "";
        ws.getCell(row, 7).value = a.postcode || "";
        ws.getRow(row).eachCell((cell) => {
          cell.font = { italic: true, color: { argb: "FF475569" }, size: 10 };
          cell.alignment = { vertical: "middle", indent: 1 };
          cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF8FAFC" } };
        });
        row++;
      });
      stripe = !stripe;
    });

    // AutoFilter på header-rækken
    ws.autoFilter = {
      from: { row: 4, column: 1 },
      to:   { row: row - 1, column: 7 },
    };

    const filename = `pladser_${new Date().toISOString().slice(0, 10)}.xlsx`;
    const buf = await wb.xlsx.writeBuffer();
    const blob = new Blob([buf], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    saveAs(blob, filename);
    toast.success(`${filename} downloaded`);
  } catch (e) {
    toast.error("Excel eksport fejlede");
    console.error(e);
  }
}

async function exportPladsPdf(pladsList, companies) {
  if (!pladsList || pladsList.length === 0) {
    toast.error("Ingen pladser at eksportere");
    return;
  }
  try {
    const { default: jsPDF } = await import("jspdf");
    const autoTableModule = await import("jspdf-autotable");
    const autoTable = autoTableModule.default || autoTableModule;
    const cmap = Object.fromEntries((companies || []).map((c) => [c.id, c.name]));
    const addrMap = await fetchPladsAddressesMap(pladsList);

    const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
    const today = new Date().toLocaleDateString("da-DK");
    doc.setFontSize(16);
    doc.text("Genbrug Pladser - Oversigt", 40, 40);
    doc.setFontSize(10);
    doc.setTextColor(120);
    doc.text(`Genereret ${today} · ${pladsList.length} pladser`, 40, 58);

    // Group by company
    const grouped = {};
    pladsList.forEach((p) => {
      const k = cmap[p.company_id] || p.company_name || p.company_id || "Ukendt";
      if (!grouped[k]) grouped[k] = [];
      grouped[k].push(p);
    });

    let startY = 80;
    Object.entries(grouped)
      .sort((a, b) => a[0].localeCompare(b[0], "da"))
      .forEach(([companyName, plads]) => {
        doc.setFontSize(12);
        doc.setTextColor(20);
        doc.text(companyName, 40, startY);
        startY += 6;

        const rows = plads.map((p) => {
          const subs = (addrMap[p.id] || []).length;
          return [
            p.name || "",
            p.city || "",
            p.address || "",
            p.location_code || "-",
            String(subs),
          ];
        });
        autoTable(doc, {
          startY: startY + 4,
          head: [["Navn", "By", "Adresse", "Kode", "Underadr."]],
          body: rows,
          theme: "striped",
          headStyles: { fillColor: [16, 122, 84], textColor: 255 },
          styles: { fontSize: 9, cellPadding: 4 },
          columnStyles: {
            0: { cellWidth: 200 },
            1: { cellWidth: 100 },
            2: { cellWidth: 220 },
            3: { cellWidth: 60 },
            4: { cellWidth: 60, halign: "right" },
          },
          margin: { left: 40, right: 40 },
        });
        startY = doc.lastAutoTable.finalY + 20;
        if (startY > 520) {
          doc.addPage();
          startY = 40;
        }
      });

    const filename = `pladser_${new Date().toISOString().slice(0, 10)}.pdf`;
    doc.save(filename);
    toast.success(`${filename} downloaded`);
  } catch (e) {
    toast.error("PDF eksport fejlede");
    console.error(e);
  }
}


/* ============== Company Stats Modal ============== */
function CompanyStatsModal({ company, onClose }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/superadmin/company-stats/${company.id}`)
      .then(({ data }) => setStats(data))
      .catch(() => toast.error("Kunne ikke hente statistik"))
      .finally(() => setLoading(false));
  }, [company.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full p-6 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="font-bold text-xl text-slate-900 dark:text-white flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-500" /> {company.name}
            </h3>
            <p className="text-sm text-slate-500 mt-0.5">Statistik oversigt</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {loading ? (
          <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
        ) : stats ? (
          <div className="space-y-5">
            {/* Tours */}
            <div>
              <h4 className="font-semibold text-sm text-slate-600 dark:text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-2">
                <Truck className="w-4 h-4" /> Ture
              </h4>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "I alt", value: stats.tours.total, color: "text-slate-700 dark:text-white" },
                  { label: "Fuldført", value: stats.tours.completed, color: "text-emerald-600" },
                  { label: "Gennemførelse", value: `${stats.tours.completion_rate}%`, color: "text-blue-600" },
                  { label: "Total vægt", value: `${stats.tours.total_weight_kg} kg`, color: "text-purple-600" },
                ].map(s => (
                  <div key={s.label} className="bg-slate-50 dark:bg-slate-700 rounded-lg p-3">
                    <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Genbrug orders */}
            {stats.genbrug_orders.total > 0 && (
              <div>
                <h4 className="font-semibold text-sm text-slate-600 dark:text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-2">
                  <Recycle className="w-4 h-4" /> Genbrug Bestillinger
                </h4>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {[
                    ["I alt", stats.genbrug_orders.total],
                    ["Afventer", stats.genbrug_orders.by_status.pending || 0],
                    ["Modtaget", stats.genbrug_orders.by_status.received || 0],
                    ["Færdig", stats.genbrug_orders.by_status.completed || 0],
                  ].map(([label, val]) => (
                    <div key={label} className="bg-slate-50 dark:bg-slate-700 rounded-lg p-2.5 flex items-center justify-between">
                      <span className="text-slate-500">{label}</span>
                      <span className="font-bold text-slate-800 dark:text-white">{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top materials */}
            {stats.materials.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm text-slate-600 dark:text-slate-300 uppercase tracking-wide mb-3">Top materialer</h4>
                <div className="space-y-2">
                  {stats.materials.slice(0,5).map(([mat, count]) => {
                    const max = stats.materials[0]?.[1] || 1;
                    return (
                      <div key={mat} className="flex items-center gap-3">
                        <span className="text-sm text-slate-700 dark:text-slate-200 truncate w-32">{mat}</span>
                        <div className="flex-1 h-2 bg-slate-100 dark:bg-slate-700 rounded-full">
                          <div className="h-full bg-orange-500 rounded-full" style={{ width: `${(count/max)*100}%` }} />
                        </div>
                        <span className="text-xs text-slate-500 w-8 text-right">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ) : <p className="text-center text-slate-400 py-8">Ingen data</p>}
      </div>
    </div>
  );
}

function ConfirmDialog({ open, title, message, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full p-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-950/40 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-red-600" />
          </div>
          <h3 className="font-bold text-lg text-slate-900 dark:text-white">{title}</h3>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-5">{message}</p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600"
            data-testid="confirm-cancel"
          >
            Annuller
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-red-600 hover:bg-red-700 text-white"
            data-testid="confirm-delete"
          >
            Slet
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SuperAdminPage() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("companies"); // companies | users | admins | logistics

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900" data-testid="superadmin-page">

      {/* Header */}
      <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-screen-2xl mx-auto px-6 sm:px-10 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-orange-500/15 border border-orange-500/30 flex items-center justify-center">
              <Shield className="w-5 h-5 text-orange-400" />
            </div>
            <div>
              <h1 className="font-heading font-bold text-lg leading-tight">Super Admin</h1>
              <p className="text-xs text-slate-400">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
            data-testid="superadmin-logout-btn"
          >
            <LogOut className="w-4 h-4" /> Log ud
          </button>
        </div>

        {/* Tabs */}
        <div className="max-w-screen-2xl mx-auto px-6 sm:px-10 flex gap-1 -mb-px overflow-x-auto">
          <TabBtn active={tab === "companies"} onClick={() => setTab("companies")} icon={Building2} label="Kunder & Logistik" testid="tab-companies" />
          <TabBtn active={tab === "users"} onClick={() => setTab("users")} icon={Users} label="Ejere" testid="tab-users" />
          <TabBtn active={tab === "admins"} onClick={() => setTab("admins")} icon={KeyRound} label="Kunde Administration" testid="tab-admins" />
          <TabBtn active={tab === "logistics"} onClick={() => setTab("logistics")} icon={Truck} label="Tilføj logistik partner" testid="tab-logistics" />
          <TabBtn active={tab === "holidays"} onClick={() => setTab("holidays")} icon={Calendar} label="Administrer helligdagsinformation" testid="tab-holidays" />
          {/* Fase 15.40 (2026-02-22): Klient-platformsfunktioner - toggle
              features pr. klient. */}
          <TabBtn active={tab === "features"} onClick={() => setTab("features")} icon={Power} label="Administrer Klientplatformsfunktioner" testid="tab-features" />
          {/* Fase 16 (2026-02-XX): Per-kunde opbevaringsperiode for kvitterings-billeder. */}
          <TabBtn active={tab === "retention"} onClick={() => setTab("retention")} icon={Archive} label="Administrer dataopbevaring" testid="tab-retention" />
        </div>
      </header>

      <main className="max-w-screen-2xl mx-auto px-6 sm:px-10 py-6">
        {/* Summary cards vises på alle faner. License-overblikket (Aktive
            medarbejdere pr. kunde) er kun relevant under "Kunde Administration". */}
        {tab !== "logistics" && tab !== "holidays" && tab !== "features" && tab !== "retention" && <PlatformStats key={tab /* force refresh when switching */} showLicenseRows={tab === "admins"} />}
        {tab === "companies" && <CompaniesPanel />}
        {tab === "users" && <UsersPanel />}
        {tab === "admins" && <CustomerAdminsPanel />}
        {tab === "logistics" && <LogisticsPartnersPanel />}
        {tab === "holidays" && <HolidayInfoPanel />}
        {tab === "features" && <ClientFeaturesPanel />}
        {tab === "retention" && <RetentionPolicyPanel />}
      </main>
    </div>
  );
}

function TabBtn({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors inline-flex items-center gap-2 whitespace-nowrap ${
        active ? "border-orange-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
      data-testid={testid}
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

/* ============== Companies Panel ============== */

/* ============== Platform Stats (overview bar) ==============
 * Auto-refreshes when the parent tab changes (PlatformStats key={tab})
 * and also every 15s in case the user keeps the page open.
 */
function PlatformStats({ showLicenseRows = true }) {
  const [stats, setStats] = useState(null);
  const [licenseRows, setLicenseRows] = useState([]);

  const refresh = useCallback(async () => {
    const [companies, users, plads] = await Promise.all([
      axios.get(`${API}/superadmin/companies`).catch(() => ({ data: [] })),
      axios.get(`${API}/superadmin/users`).catch(() => ({ data: [] })),
      axios.get(`${API}/superadmin/plads`).catch(() => ({ data: [] })),
    ]);
    // Brugerkrav 2026-06-15 (runde 8): KPI-kortene SKAL kun tælle AKTIVE
    // kunder/firmaer og deres tilhørende lokationer/medarbejdere. Inaktive
    // kunder skal ikke skævvride overblikket - de er stadig synlige via
    // toggle-knappen, men ikke i statistikken.
    const allCompanies = companies.data || [];
    const activeCompanies = allCompanies.filter(c => c.active !== false);
    const activeCompanyIds = new Set(activeCompanies.map(c => c.id));

    const cust = activeCompanies.filter(c => c.company_type !== "logistics");
    const logi = activeCompanies.filter(c => c.company_type === "logistics");
    const allPlads = plads.data || [];
    const activePlads = allPlads.filter(p =>
      // Kun pladser der tilhører en aktiv kunde
      !p.company_id || activeCompanyIds.has(p.company_id)
    );
    const activeUsers = (users.data || []).filter(u =>
      u.role !== "super_admin"
      && u.active
      && (!u.company_id || activeCompanyIds.has(u.company_id))
    );
    setStats({
      customers: cust.length,
      logistics: logi.length,
      locations: activePlads.length,
      employees: activeUsers.length,
    });

    // Aktive-medarbejdere-pr.-kunde tabel (license overblik).
    // active_employee_count kommer fra backend som antallet af aktive
    // 'order' + 'location_admin' brugere - det er den base vi fakturerer på.
    const rows = allCompanies
      .filter(c => c.company_type !== "logistics") // license-aftaler er for kunder
      .map(c => ({
        company_id: c.id,
        company_name: c.name,
        customer_id: c.customer_id || "-",
        active_employees: c.active_employee_count ?? 0,
        status: c.active === false ? "inaktiv" : "aktiv",
      }))
      .sort((a, b) => b.active_employees - a.active_employees);
    setLicenseRows(rows);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  if (!stats) return null;
  const totalActiveEmployees = licenseRows.reduce((sum, r) => sum + r.active_employees, 0);

  return (
    <div className="space-y-4 mb-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Kunder", value: stats.customers, icon: Building, color: "text-emerald-500", bg: "bg-emerald-50 dark:bg-emerald-950/20", testid: "stat-customers" },
          { label: "Logistik-firmaer", value: stats.logistics, icon: Truck, color: "text-orange-500", bg: "bg-orange-50 dark:bg-orange-950/20", testid: "stat-logistics" },
          { label: "Lokationer", value: stats.locations, icon: MapPin, color: "text-purple-500", bg: "bg-purple-50 dark:bg-purple-950/20", testid: "stat-locations" },
          { label: "Medarbejdere", value: stats.employees, icon: Users, color: "text-blue-500", bg: "bg-blue-50 dark:bg-blue-950/20", testid: "stat-employees" },
        ].map(s => (
          <div key={s.label} className={`${s.bg} rounded-xl p-4 border border-slate-200 dark:border-slate-700 flex items-center gap-3`} data-testid={s.testid}>
            <s.icon className={`w-8 h-8 ${s.color} flex-shrink-0`} />
            <div>
              <p className="text-2xl font-heading font-bold text-slate-900 dark:text-white">{s.value}</p>
              <p className="text-xs text-slate-500">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Aktive medarbejdere pr. kunde (license overblik) - vises KUN på "Kunde Administration" */}
      {showLicenseRows && (
      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden" data-testid="license-overview-panel">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 font-semibold text-sm text-slate-800 dark:text-white flex items-center justify-between">
          <span className="inline-flex items-center gap-2">
            <Users className="w-4 h-4 text-orange-500" /> Aktive medarbejdere pr. kunde
          </span>
          <span className="text-xs font-normal text-slate-500">License-overblik · I alt: <strong className="text-slate-800 dark:text-white">{totalActiveEmployees}</strong></span>
        </div>
        {licenseRows.length === 0 ? (
          <div className="py-8 text-center text-sm text-slate-400">Ingen kunder oprettet endnu.</div>
        ) : (
          <>
            <div className="grid text-[10px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50 dark:bg-slate-900/50 px-4 py-2 border-b border-slate-100 dark:border-slate-700"
              style={{gridTemplateColumns:"1.5fr 120px 1fr 110px"}}>
              <div>Kunde</div>
              <div>Kunde-ID</div>
              <div>Status</div>
              <div className="text-right">Aktive medarb.</div>
            </div>
            {licenseRows.map((r) => (
              <div key={r.company_id} data-testid={`license-row-${r.company_id}`}
                className="grid items-center px-4 py-2.5 border-b border-slate-100 dark:border-slate-700/50 last:border-0"
                style={{gridTemplateColumns:"1.5fr 120px 1fr 110px"}}>
                <div className="font-medium text-sm text-slate-800 dark:text-white truncate">{r.company_name}</div>
                <div className="text-xs text-slate-500 font-mono">{r.customer_id}</div>
                <div>
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                    r.status === "aktiv"
                      ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                      : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                  }`}>{r.status}</span>
                </div>
                <div className="text-right text-lg font-bold text-slate-900 dark:text-white">{r.active_employees}</div>
              </div>
            ))}
          </>
        )}
      </div>
      )}
    </div>
  );
}

function CompaniesPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [statsFor, setStatsFor] = useState(null);
  const [resendingId, setResendingId] = useState(null);
  // Brugerkrav 2026-06-15 (runde 7): Default filtrér på aktive kunder.
  // Toggle-knap kan vise alle (inkl. inaktive).
  const [showInactive, setShowInactive] = useState(false);

  // Forenklet form: System-ejer opretter kun (a) firma + obligatorisk Kunde-ID
  // og (b) firmaets FØRSTE admin via email-invitation. Adgangskode sættes
  // udelukkende af admin selv via det 72-timers link de modtager.
  const emptyForm = {
    company_name: "",
    company_type: "customer",
    customer_id: "",
    active: true,
    holiday_group_id: "",
    admin: { name: "", email: "", phone: "" },
  };
  const [form, setFormState] = useState(emptyForm);
  const [holidayGroups, setHolidayGroups] = useState([]);
  const [saving, setSaving] = useState(false);
  const setTop = (k, v) => setFormState(p => ({ ...p, [k]: v }));
  const setAdminF = (k, v) => setFormState(p => ({ ...p, admin: { ...p.admin, [k]: v } }));

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const [comps, groups] = await Promise.all([
        axios.get(`${API}/superadmin/companies`),
        axios.get(`${API}/superadmin/holiday-groups`).catch(() => ({ data: [] })),
      ]);
      setItems(comps.data);
      setHolidayGroups(groups.data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCompanies(); }, [fetchCompanies]);

  // openQuick(): opens an empty form. preferType controls which company_type
  // tab is pre-selected. "Ny logistik partner" pre-selects logistics so the
  // System Owner can maintain that list independently from kunderne (selvom
  // alle vises i samme oversigt – med badge).
  const openQuick = (preferType = "customer") => {
    setEditing(null);
    setFormState({ ...emptyForm, company_type: preferType });
    setShowForm(true);
  };
  const openEdit = (c) => {
    setEditing(c);
    setFormState({
      company_name: c.name || "",
      company_type: c.company_type || "customer",
      customer_id: c.customer_id || "",
      active: c.active !== false,
      holiday_group_id: c.holiday_group_id || "",
      admin: {
        name: c.first_admin?.name || "",
        email: c.first_admin?.email || "",
        phone: c.first_admin?.phone || c.admin_phone || "",
      },
    });
    setShowForm(true);
  };
  const closeForm = () => { setShowForm(false); setEditing(null); setFormState(emptyForm); };

  const save = async () => {
    if (!form.company_name.trim()) { toast.error("Firmanavn er påkrævet"); return; }
    if (!form.customer_id.trim()) { toast.error("Kunde-ID er påkrævet"); return; }
    const adminEmail = (form.admin.email || "").trim();
    if (!editing && adminEmail && !adminEmail.includes("@")) {
      toast.error("Ugyldig admin-email"); return;
    }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API}/superadmin/companies/${editing.id}`, {
          name: form.company_name.trim(),
          customer_id: form.customer_id.trim(),
          active: !!form.active,
          admin_phone: form.admin.phone.trim(),
          admin_name: form.admin.name.trim(),
          admin_email: form.admin.email.trim().toLowerCase(),
          holiday_group_id: form.holiday_group_id || null,
        });
        toast.success("Firma opdateret");
      } else {
        await axios.post(`${API}/superadmin/companies`, {
          name: form.company_name.trim(),
          company_type: form.company_type,
          customer_id: form.customer_id.trim(),
          active: !!form.active,
          admin_phone: form.admin.phone.trim(),
          admin_name: form.admin.name.trim(),
          admin_email: adminEmail.toLowerCase(),
          holiday_group_id: form.holiday_group_id || null,
        });
        toast.success(adminEmail ? "Firma oprettet - invitation sendt på e-mail" : "Firma oprettet");
      }
      closeForm();
      fetchCompanies();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/superadmin/companies/${id}`);
      toast.success("Firma slettet");
      fetchCompanies();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setDeletingId(null);
    }
  };

  const toggleActive = async (c) => {
    const nextActive = !(c.active !== false);
    const verb = nextActive ? "aktivere" : "suspendere";
    if (c.id === "default" && !nextActive) {
      toast.error("Standard-gruppen kan ikke suspenderes"); return;
    }
    if (!window.confirm(`Er du sikker på at du vil ${verb} "${c.name}"?${!nextActive ? "\n\nAlle brugere i denne gruppe vil blive blokeret fra at logge ind." : ""}`)) {
      return;
    }
    try {
      await axios.put(`${API}/superadmin/companies/${c.id}`, { active: nextActive });
      toast.success(nextActive ? "Gruppe aktiveret" : "Gruppe suspenderet");
      fetchCompanies();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const resendInvite = async (c) => {
    setResendingId(c.id);
    try {
      const { data } = await axios.post(`${API}/superadmin/companies/${c.id}/resend-invitation`);
      toast.success(`Invitation gensendt til ${data.admin_email}`);
      fetchCompanies();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setResendingId(null);
    }
  };

  return (
    <section data-testid="companies-panel">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Kunder & Logistik-firmaer</h2>
          <p className="text-sm text-slate-500">Hvert firma har sine egne data, brugere og roller.</p>
        </div>
        <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setShowInactive(s => !s)}
          className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm border transition-colors ${
            showInactive
              ? "bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/30 dark:hover:bg-amber-950 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200"
              : "bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
          }`}
          data-testid="toggle-inactive-customers"
          title={showInactive ? "Skjul inaktive kunder" : "Vis også inaktive kunder"}
        >
          {showInactive ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          {showInactive ? "Vis kun aktive" : "Vis alle (inkl. inaktive)"}
        </button>
        <button
          onClick={() => openQuick("customer")}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold text-sm shadow-md"
          data-testid="quick-setup-btn"
        >
          <Plus className="w-4 h-4" /> Ny kunde
        </button>
      </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
      ) : items.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-8 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
          Ingen firmaer endnu. Opret det første ovenfor.
        </div>
      ) : (() => {
        // Brugerkrav 2026-06-15 (runde 7): Default skjul inaktive kunder.
        const visible = showInactive
          ? items
          : items.filter(c => c.active !== false);
        if (visible.length === 0) {
          return (
            <div className="bg-white dark:bg-slate-800 rounded-xl p-8 text-center text-slate-500 border border-slate-200 dark:border-slate-700"
              data-testid="all-inactive-hidden">
              Alle kunder er sat inaktive. Tryk "Vis alle (inkl. inaktive)" for at se dem.
            </div>
          );
        }
        return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {visible.map((c) => {
            // Cascade firmaets aktive-status ned på admin-displayet: når kunden
            // er sat inaktiv, vises admin også som inaktiv (login er allerede
            // blokeret pga. suspended company).
            const companyActive = c.active !== false;
            const rawStatus = c.first_admin?.invitation_status || "active";
            const adminInactive = !companyActive;
            const isPending = !adminInactive && rawStatus === "pending";
            const statusLabel = adminInactive ? "Inaktiv" : (isPending ? "Afventer" : "Aktiv");
            const statusIcon = adminInactive ? PowerOff : (isPending ? Clock : CheckCircle2);
            const StatusIcon = statusIcon;
            const statusColorClasses = adminInactive
              ? "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
              : isPending
                ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
                : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300";
            return (
              <div
                key={c.id}
                className={`bg-white dark:bg-slate-800 rounded-xl p-5 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-shadow ${!companyActive ? "opacity-75" : ""}`}
                data-testid={`company-card-${c.id}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-lg bg-orange-100 dark:bg-orange-950/40 text-orange-600 flex items-center justify-center">
                    <Building className="w-5 h-5" />
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => setStatsFor(c)} className="p-2 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950/40" title="Statistik" data-testid={`stats-company-${c.id}`}>
                      <BarChart3 className="w-4 h-4 text-blue-500" />
                    </button>
                    <button onClick={() => openEdit(c)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700" title="Rediger" data-testid={`edit-company-${c.id}`}>
                      <Edit2 className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                    </button>
                  </div>
                </div>
                <h3 className="font-bold text-lg text-slate-900 dark:text-white flex items-center gap-2 flex-wrap">
                  {c.name}
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                    c.company_type === "logistics"
                      ? "bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300"
                      : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                  }`}>
                    {c.company_type === "logistics" ? (c.from_library ? "Logistik-partner" : "Logistik · Premium") : "Kunde"}
                  </span>
                </h3>
                <div className="mt-2 space-y-1 text-xs text-slate-500">
                  {c.customer_id && (
                    <div className="font-mono">Kunde-ID: <span className="font-semibold text-slate-700 dark:text-slate-200">{c.customer_id}</span></div>
                  )}
                  {c.first_admin?.email && (
                    <div className="truncate">Admin: <span className="text-slate-700 dark:text-slate-200">{c.first_admin.email}</span></div>
                  )}
                  {(c.first_admin?.phone || c.admin_phone) && (
                    <div>Tlf: <span className="text-slate-700 dark:text-slate-200">{c.first_admin?.phone || c.admin_phone}</span></div>
                  )}
                  {c.created_at && (
                    <div>Oprettet: <span className="text-slate-700 dark:text-slate-200">{new Date(c.created_at).toLocaleDateString("da-DK")}</span></div>
                  )}
                  <div className="inline-flex items-center gap-2">
                    <Users className="w-3 h-3" /> {c.active_employee_count ?? 0} aktive medarbejdere
                  </div>
                  {c.company_type !== "logistics" && (
                    <div className="grid grid-cols-3 gap-1 mt-2 pt-2 border-t border-slate-100 dark:border-slate-700" data-testid={`kundeoverblik-${c.id}`}>
                      <div className="text-center">
                        <div className="text-base font-bold text-emerald-600 dark:text-emerald-400">{c.locations_count ?? 0}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Lokationer</div>
                      </div>
                      <div className="text-center">
                        <div className="text-base font-bold text-blue-600 dark:text-blue-400">{c.partners_count ?? 0}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Partnere</div>
                      </div>
                      <div className="text-center">
                        <div className="text-base font-bold text-purple-600 dark:text-purple-400">{c.active_users_incl_partners ?? 0}</div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Akt. brugere</div>
                      </div>
                    </div>
                  )}
                </div>
                <div className="mt-3 flex items-center justify-between flex-wrap gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase inline-flex items-center gap-1 ${statusColorClasses}`} data-testid={`company-status-${c.id}`}>
                    <StatusIcon className="w-3 h-3" /> {statusLabel}
                  </span>
                  {c.first_admin?.email && !adminInactive && (
                    <button onClick={() => resendInvite(c)} disabled={resendingId === c.id}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-bold bg-orange-50 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-950/60 disabled:opacity-60"
                      title="Gensend invitations-mail til admin"
                      data-testid={`resend-invite-${c.id}`}>
                      {resendingId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mail className="w-3 h-3" />}
                      Gensend invitation
                    </button>
                  )}
                </div>
                {adminInactive && (
                  <div className="mt-2 text-[11px] text-slate-500 italic">
                    Firma er suspenderet - admin kan ikke logge ind. Aktivér via Rediger.
                  </div>
                )}
              </div>
            );
          })}
        </div>
        );
      })()}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeForm} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-xl text-slate-900 dark:text-white">
                {editing ? `Rediger ${editing.company_type === "logistics" ? "logistik" : "kunde"}` : "Ny kunde / logistik-firma"}
              </h3>
              <button onClick={closeForm} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-5">
              {/* Firma type */}
              {!editing && (
                <div>
                  <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">Firmatype</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: "customer", icon: Building, label: "Kunde", desc: "har lokationer" },
                      { id: "logistics", icon: Truck, label: "Logistik (premium)", desc: "eget system: lokationer, ture, chauffører" },
                    ].map(t => (
                      <button key={t.id} type="button" onClick={() => setTop("company_type", t.id)}
                        data-testid={`type-${t.id}`}
                        className={`p-3 rounded-xl border-2 text-left transition-all ${
                          form.company_type === t.id
                            ? "bg-emerald-500/10 border-emerald-500"
                            : "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 hover:border-emerald-400"
                        }`}>
                        <div className="flex items-center gap-2">
                          <t.icon className={`w-4 h-4 ${form.company_type === t.id ? "text-emerald-600" : "text-slate-400"}`} />
                          <span className="font-bold text-sm text-slate-800 dark:text-white">{t.label}</span>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">{t.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Firmanavn */}
              <div>
                <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">Firmanavn *</label>
                <input
                  value={form.company_name}
                  onChange={(e) => setTop("company_name", e.target.value)}
                  placeholder={form.company_type === "logistics" ? "F.eks. ILK Transport ApS" : "F.eks. ARGO I/S"}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none"
                  data-testid="company-name-input"
                />
              </div>

              {/* Kunde-ID (obligatorisk) + Status (active) */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">Kunde-ID *</label>
                  <input
                    value={form.customer_id}
                    onChange={(e) => setTop("customer_id", e.target.value)}
                    placeholder="F.eks. K001"
                    required
                    className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none font-mono text-sm"
                    data-testid="customer-id-input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">Status</label>
                  <label className="flex items-center gap-2 px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg cursor-pointer">
                    <input type="checkbox" checked={!!form.active}
                      onChange={(e) => setTop("active", e.target.checked)}
                      className="w-4 h-4 accent-emerald-500"
                      data-testid="company-active-toggle" />
                    <span className={`text-sm font-semibold ${form.active ? "text-emerald-600" : "text-slate-400"}`}>
                      {form.active ? "Aktiv" : "Inaktiv"}
                    </span>
                  </label>
                </div>
              </div>

              {/* Helligdagsgruppe (kun for kunder - logistik partner-firmaer har ingen åbningstider) */}
              {form.company_type === "customer" && (
                <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                  <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">
                    Helligdagsgruppe
                    <span className="ml-2 text-xs font-normal text-slate-400">- Location Admins arver disse helligdage som default</span>
                  </label>
                  <select value={form.holiday_group_id || ""}
                    onChange={e => setTop("holiday_group_id", e.target.value)}
                    className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none text-sm"
                    data-testid="company-holiday-group-select">
                    <option value="">- Ingen helligdagsgruppe -</option>
                    {holidayGroups.map(g => (
                      <option key={g.id} value={g.id}>{g.name} ({g.holidays?.length || 0} helligdage)</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Vedligehold listen under fanen "Helligdagsgrupper".
                  </p>
                </div>
              )}

              {/* Admin info (email + telefon + navn - adgangskode sættes via invitations-link). */}
              <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">
                  {form.company_type === "logistics" ? "Logistik-admin" : "Kunde-admin"}
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    {editing ? "(redigér nedenfor)" : "- modtager en invitation på e-mail (72 timer)"}
                  </span>
                </label>
                <div className="grid grid-cols-1 gap-2">
                  <input value={form.admin.name} onChange={e => setAdminF("name", e.target.value)} placeholder="Navn"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none text-sm"
                    data-testid="admin-name-input" />
                  <input value={form.admin.email} onChange={e => setAdminF("email", e.target.value)} placeholder="Email"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none text-sm"
                    data-testid="admin-email-input" />
                  <input value={form.admin.phone} onChange={e => setAdminF("phone", e.target.value)} placeholder="Telefon"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-emerald-500 outline-none text-sm"
                    data-testid="admin-phone-input" />
                </div>
                {!editing && (
                  <p className="text-xs text-slate-500 mt-1.5">
                    Når du gemmer, sender vi automatisk en invitations-mail til admin'en med et 72-timers link, hvor de selv vælger deres adgangskode.
                  </p>
                )}
                {editing && (
                  <p className="text-xs text-slate-500 mt-1.5">
                    Du kan ændre admin-navn og e-mail her. Brug "Gensend invitation"-knappen på kortet hvis linket er udløbet.
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={closeForm} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
              <button
                onClick={save}
                disabled={saving}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white inline-flex items-center gap-2"
                data-testid="save-company-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                {editing ? "Gem ændringer" : "Opret firma"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deletingId}
        title="Slet firma?"
        message="Denne handling kan ikke fortrydes. Firmaet kan kun slettes hvis det ikke har brugere."
        onConfirm={() => remove(deletingId)}
        onCancel={() => setDeletingId(null)}
      />
      {statsFor && <CompanyStatsModal company={statsFor} onClose={() => setStatsFor(null)} />}
    </section>
  );
}


/* ============== Users Panel ============== */
function UsersPanel() {
  const [users, setUsers] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [allPlads, setAllPlads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterCompany, setFilterCompany] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [csvResult, setCsvResult] = useState(null);
  const [csvUploading, setCsvUploading] = useState(false);

  const [form, setForm] = useState({
    email: "", name: "", password: "", role: "super_admin", company_id: "*",
    phone: "",
  });

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [u, c, p] = await Promise.all([
        axios.get(`${API}/superadmin/users`),
        axios.get(`${API}/superadmin/companies`),
        axios.get(`${API}/superadmin/plads`),
      ]);
      // The "Owners" tab is exclusively for system-level co-administrators
      // (people who run the platform itself). Everything else - customer
      // admins, location admins, drivers, employees - is created from inside
      // each tenant's own pages.
      setUsers((u.data || []).filter(x => x.role === "super_admin"));
      setCompanies(c.data);
      setAllPlads(p.data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openCreate = () => {
    setEditing(null);
    setForm({ email: "", name: "", password: "", role: "super_admin", company_id: "*", phone: "" });
    setShowForm(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm({
      email: u.email,
      name: u.name,
      password: "",
      role: "super_admin",
      company_id: u.company_id,
      phone: u.phone || "",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.email.trim() || !form.name.trim()) {
      toast.error("Email og navn er påkrævet"); return;
    }
    if (!editing && (!form.password || form.password.length < 4)) {
      toast.error("Adgangskode skal være mindst 4 tegn"); return;
    }
    try {
      const payload = {
        email: form.email.trim().toLowerCase(),
        name: form.name.trim(),
        role: "super_admin",
        company_id: "*",
        phone: form.phone.trim(),
      };
      if (editing) {
        if (form.password) payload.password = form.password;
        await axios.put(`${API}/superadmin/users/${editing.id}`, payload);
        toast.success("Ejer opdateret");
      } else {
        payload.password = form.password;
        await axios.post(`${API}/superadmin/users`, payload);
        toast.success("Ejer oprettet");
      }
      setShowForm(false);
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const toggleActive = async (u) => {
    try {
      await axios.put(`${API}/superadmin/users/${u.id}`, { active: !u.active });
      fetchAll();
      toast.success(u.active ? "Bruger deaktiveret" : "Bruger aktiveret");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/superadmin/users/${id}`);
      toast.success("Bruger slettet");
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = users.filter((u) => {
    if (filterCompany && u.company_id !== filterCompany) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      (u.email || "").toLowerCase().includes(s) ||
      (u.name || "").toLowerCase().includes(s) ||
      (u.role || "").toLowerCase().includes(s)
    );
  });

  return (
    <section data-testid="users-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Ejere</h2>
          <p className="text-sm text-slate-500">System-ejere (platform-administratorer). Andre roller administreres af de relevante firma-admins.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Søg..."
              className="pl-10 pr-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none w-full md:w-56"
              data-testid="user-search-input"
            />
          </div>
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-sm shadow-md"
            data-testid="create-user-btn"
          >
            <UserPlus className="w-4 h-4" /> Ny ejer
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3">Navn</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Telefon</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Handlinger</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-slate-100 dark:divide-slate-700">
                {filtered.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">Ingen ejere fundet</td></tr>
                ) : filtered.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30" data-testid={`user-row-${u.id}`}>
                    <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">{u.name}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{u.email}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{u.phone || "-"}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => toggleActive(u)}
                        className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                          u.active
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                            : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                        }`}
                        data-testid={`toggle-active-${u.id}`}
                      >
                        {u.active ? "Aktiv" : "Inaktiv"}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => openEdit(u)}
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
                        title="Rediger"
                        data-testid={`edit-user-${u.id}`}
                      >
                        <Edit2 className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                      </button>
                      <button
                        onClick={() => setDeletingId(u.id)}
                        className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40"
                        title="Slet"
                        data-testid={`delete-user-${u.id}`}
                      >
                        <Trash2 className="w-4 h-4 text-red-600" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowForm(false)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-xl text-slate-900 dark:text-white">
                {editing ? "Rediger bruger" : "Ny bruger"}
              </h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-4">
              <p className="text-xs text-slate-500 -mt-2">
                System-ejere har fuld platform-adgang. Andre brugere (kunde-/lokations-/logistik-admin, chauffør, medarbejder) oprettes via deres respektive admin-sider.
              </p>
              <Field label="Email *">
                <input
                  type="text"
                  inputMode="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="user-email-input"
                />
              </Field>
              <Field label="Navn *">
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="user-name-input"
                />
              </Field>
              <Field label="Telefon">
                <input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="user-phone-input"
                />
              </Field>
              <Field label={editing ? "Ny adgangskode (lad være tom for at beholde)" : "Adgangskode *"}>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder={editing ? "••••••" : "min. 4 tegn"}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="user-password-input"
                />
              </Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
              <button
                onClick={save}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-white inline-flex items-center gap-2"
                data-testid="save-user-btn"
              >
                {editing ? <KeyRound className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                {editing ? "Gem" : "Opret"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deletingId}
        title="Slet bruger?"
        message="Brugeren mister adgang med det samme. Denne handling kan ikke fortrydes."
        onConfirm={() => remove(deletingId)}
        onCancel={() => setDeletingId(null)}
      />
    </section>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5 text-slate-700 dark:text-slate-300">{label}</label>
      {children}
    </div>
  );
}


/* ============== Customer Admins Panel (Super Admin's 3. tab) ============== */
/**
 * Read-only overblik over alle kunde-administratorer i systemet:
 *   - Hvilken kunde de tilhører
 *   - Email, telefon, navn
 *   - Aktiverings-status (Afventer / Aktiv)
 *   - Mulighed for at gensende invitation hvis Afventer
 *
 * Vi bygger listen ud fra `/api/superadmin/companies` (som allerede returnerer
 * first_admin pr. firma) - det undgår et separat backend-endpoint.
 */
function CustomerAdminsPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [resendingId, setResendingId] = useState(null);
  const [search, setSearch] = useState("");
  // Brugerkrav 2026-06-15 (runde 8): Default skjul inaktive kunder. Brugeren
  // kan stadig vælge "Alle" eller andre statusser fra dropdown.
  const [statusFilter, setStatusFilter] = useState("active");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/superadmin/companies`);
      const out = (data || [])
        .filter(c => c.company_type === "customer" && c.first_admin)
        .map(c => {
          // Cascade: if firma er sat inaktiv, admin vises også som "inaktiv".
          const companyActive = c.active !== false;
          const rawStatus = c.first_admin.invitation_status || "active";
          return {
            company_id: c.id,
            company_name: c.name,
            customer_id: c.customer_id || "-",
            name: c.first_admin.name || "",
            email: c.first_admin.email || "",
            phone: c.first_admin.phone || c.admin_phone || "",
            status: !companyActive ? "inactive" : rawStatus,
            company_active: companyActive,
            created_at: c.created_at,
          };
        });
      setRows(out);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const filtered = rows.filter(r => {
    if (statusFilter !== "all" && r.status !== statusFilter) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return (r.email + r.name + r.company_name + r.customer_id).toLowerCase().includes(s);
  });

  const resend = async (companyId) => {
    setResendingId(companyId);
    try {
      const { data } = await axios.post(`${API}/superadmin/companies/${companyId}/resend-invitation`);
      toast.success(`Invitation gensendt til ${data.admin_email}`);
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally { setResendingId(null); }
  };

  return (
    <section data-testid="customer-admins-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Kunde Administration</h2>
          <p className="text-sm text-slate-500">Overblik over kundernes førsteadmins og deres aktiverings-status.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Søg navn, email, kunde..."
              className="pl-10 pr-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none w-full md:w-72"
              data-testid="admins-search-input"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none"
            data-testid="admins-status-filter"
          >
            <option value="all">Alle statusser</option>
            <option value="pending">Afventer</option>
            <option value="active">Aktiv</option>
            <option value="inactive">Inaktiv</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3">Kunde</th>
                  <th className="px-4 py-3">Kunde-ID</th>
                  <th className="px-4 py-3">Admin navn</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Telefon</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Handlinger</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-slate-100 dark:divide-slate-700">
                {filtered.length === 0 ? (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Ingen kunde-admins fundet</td></tr>
                ) : filtered.map((r) => (
                  <tr key={r.company_id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30" data-testid={`admin-row-${r.company_id}`}>
                    <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">{r.company_name}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-500">{r.customer_id}</td>
                    <td className="px-4 py-3 text-slate-700 dark:text-slate-200">{r.name || "-"}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{r.email}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{r.phone || "-"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                        r.status === "inactive"
                          ? "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                          : r.status === "pending"
                            ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                      }`} data-testid={`admin-status-${r.company_id}`}>
                        {r.status === "inactive"
                          ? <><PowerOff className="w-3 h-3" /> Inaktiv</>
                          : r.status === "pending"
                            ? <><Clock className="w-3 h-3" /> Afventer</>
                            : <><CheckCircle2 className="w-3 h-3" /> Aktiv</>}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => resend(r.company_id)}
                        disabled={resendingId === r.company_id || r.status === "inactive"}
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-orange-50 hover:bg-orange-100 dark:bg-orange-950/40 dark:hover:bg-orange-950/60 text-orange-700 dark:text-orange-300 rounded-lg text-xs font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                        data-testid={`resend-admin-${r.company_id}`}
                        title={r.status === "inactive" ? "Aktivér firmaet først" : "Gensend invitation"}
                      >
                        {resendingId === r.company_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mail className="w-3 h-3" />}
                        Gensend invitation
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}


/* ============== Logistics Partners Panel (Super Admin's 4. tab) ============== */
/**
 * Dedicated CRUD for logistics partners (catalog/registry). Customer admins
 * pick from this list when linking partners to their lokationer. This panel is
 * intentionally SEPARATE from "Kunder & Logistik-firmaer" - logistics partners
 * are a platform-wide directory, not customer data.
 *
 * UX rules:
 *   - Create uses email-invitation flow (no password)
 *   - Edit can change company name, customer_id (intern referencekode), telefon, status
 *   - Resend invitation on each row when admin is still pending
 *   - No delete from card; deactivation via Edit (consistent with kunder)
 */
function LogisticsPartnersPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [resendingId, setResendingId] = useState(null);
  const [search, setSearch] = useState("");
  // Brugerkrav 2026-06-15 (runde 7): Default filtrér på aktive partnere.
  const [showInactive, setShowInactive] = useState(false);

  const empty = {
    name: "", customer_id: "", active: true,
    admin: { name: "", email: "", phone: "" },
  };
  const [form, setFormState] = useState(empty);
  const [saving, setSaving] = useState(false);
  const setTop = (k, v) => setFormState(p => ({ ...p, [k]: v }));
  const setAdminF = (k, v) => setFormState(p => ({ ...p, admin: { ...p.admin, [k]: v } }));

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      // Brug det dedikerede partner-library filter, så vi kun ser library-
      // entries (oprettet via denne tab) - IKKE de logistik-firmaer som
      // System Owner allerede vedligeholder under "Kunder & Logistik".
      const { data } = await axios.get(`${API}/superadmin/companies?include_library=true`);
      setItems((data || []).filter(c => c.company_type === "logistics" && c.from_library === true));
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openCreate = () => { setEditing(null); setFormState(empty); setShowForm(true); };
  const openEdit = (c) => {
    setEditing(c);
    setFormState({
      name: c.name || "",
      customer_id: c.customer_id || "",
      active: c.active !== false,
      admin: {
        name: c.first_admin?.name || "",
        email: c.first_admin?.email || "",
        phone: c.first_admin?.phone || c.admin_phone || "",
      },
    });
    setShowForm(true);
  };
  const closeForm = () => { setShowForm(false); setEditing(null); setFormState(empty); };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Firmanavn er påkrævet"); return; }
    if (!form.customer_id.trim()) { toast.error("Intern referencekode er påkrævet"); return; }
    const adminEmail = (form.admin.email || "").trim();
    if (!editing && adminEmail && !adminEmail.includes("@")) { toast.error("Ugyldig admin-email"); return; }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API}/superadmin/companies/${editing.id}`, {
          name: form.name.trim(),
          customer_id: form.customer_id.trim(),
          active: !!form.active,
          admin_phone: form.admin.phone.trim(),
          admin_name: form.admin.name.trim(),
          admin_email: form.admin.email.trim().toLowerCase(),
        });
        toast.success("Logistik-partner opdateret");
      } else {
        await axios.post(`${API}/superadmin/companies`, {
          name: form.name.trim(),
          company_type: "logistics",
          customer_id: form.customer_id.trim(),
          active: !!form.active,
          admin_phone: form.admin.phone.trim(),
          admin_name: form.admin.name.trim(),
          admin_email: adminEmail.toLowerCase(),
          // mark this entry as living in the partner-library so it doesn't
          // leak into the "Kunder & Logistik" listing.
          from_library: true,
        });
        toast.success(adminEmail ? "Logistik-partner oprettet - invitation sendt" : "Logistik-partner oprettet");
      }
      closeForm(); fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const resendInvite = async (c) => {
    setResendingId(c.id);
    try {
      const { data } = await axios.post(`${API}/superadmin/companies/${c.id}/resend-invitation`);
      toast.success(`Invitation gensendt til ${data.admin_email}`);
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setResendingId(null); }
  };

  const filtered = items.filter(c => {
    // Brugerkrav 2026-06-15 (runde 7): Default skjul inaktive partnere.
    if (!showInactive && c.active === false) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      (c.name || "").toLowerCase().includes(s) ||
      (c.customer_id || "").toLowerCase().includes(s) ||
      (c.first_admin?.email || "").toLowerCase().includes(s)
    );
  });

  return (
    <section data-testid="logistics-partners-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Logistik-partnere</h2>
          <p className="text-sm text-slate-500">Katalog over logistik-firmaer. Kunde-administratorer vælger fra denne liste når de tildeler partnere til deres lokationer.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Søg navn, ref-kode, admin..."
              className="pl-10 pr-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-blue-500 outline-none w-full md:w-72"
              data-testid="logistics-search-input"
            />
          </div>
          <button
            onClick={() => setShowInactive(s => !s)}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm border transition-colors ${
              showInactive
                ? "bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/30 dark:hover:bg-amber-950 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200"
                : "bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            }`}
            data-testid="toggle-inactive-logistics"
            title={showInactive ? "Skjul inaktive partnere" : "Vis også inaktive partnere"}
          >
            {showInactive ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            {showInactive ? "Vis kun aktive" : "Vis alle (inkl. inaktive)"}
          </button>
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-sm shadow-md"
            data-testid="add-logistics-partner-btn"
          >
            <Plus className="w-4 h-4" /> Tilføj logistik partner
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-8 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
          {items.length === 0
            ? "Ingen logistik-partnere endnu. Tryk \u201CTilføj logistik partner\u201D ovenfor."
            : "Ingen logistik-partnere matcher søgningen."}
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3">Firma</th>
                  <th className="px-4 py-3">Ref. kode</th>
                  <th className="px-4 py-3">Admin</th>
                  <th className="px-4 py-3">Telefon</th>
                  <th className="px-4 py-3">Oprettet</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Handlinger</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-slate-100 dark:divide-slate-700">
                {filtered.map(c => {
                  const companyActive = c.active !== false;
                  const rawStatus = c.first_admin?.invitation_status || "active";
                  const status = !companyActive ? "inactive" : rawStatus;
                  return (
                    <tr key={c.id} className={`hover:bg-slate-50 dark:hover:bg-slate-900/30 ${!companyActive ? "opacity-70" : ""}`} data-testid={`logistics-row-${c.id}`}>
                      <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">
                        <div className="flex items-center gap-2">
                          <Truck className="w-4 h-4 text-blue-500" />
                          {c.name}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-slate-500">{c.customer_id || "-"}</td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300">
                        {c.first_admin?.email || "-"}
                        {c.first_admin?.name && (
                          <div className="text-xs text-slate-400">{c.first_admin.name}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{c.first_admin?.phone || c.admin_phone || "-"}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {c.created_at ? new Date(c.created_at).toLocaleDateString("da-DK") : "-"}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                          status === "inactive"
                            ? "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                            : status === "pending"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                              : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                        }`} data-testid={`logistics-status-${c.id}`}>
                          {status === "inactive"
                            ? <><PowerOff className="w-3 h-3" /> Inaktiv</>
                            : status === "pending"
                              ? <><Clock className="w-3 h-3" /> Afventer</>
                              : <><CheckCircle2 className="w-3 h-3" /> Aktiv</>}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex gap-1">
                          {companyActive && c.first_admin?.email && (
                            <button onClick={() => resendInvite(c)} disabled={resendingId === c.id}
                              className="inline-flex items-center gap-1 px-2 py-1.5 rounded text-[11px] font-bold bg-orange-50 hover:bg-orange-100 dark:bg-orange-950/40 dark:hover:bg-orange-950/60 text-orange-700 dark:text-orange-300 disabled:opacity-50"
                              title="Gensend invitation"
                              data-testid={`logistics-resend-${c.id}`}>
                              {resendingId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Mail className="w-3 h-3" />}
                            </button>
                          )}
                          <button onClick={() => openEdit(c)}
                            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
                            title="Rediger"
                            data-testid={`logistics-edit-${c.id}`}>
                            <Edit2 className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeForm} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-xl text-slate-900 dark:text-white inline-flex items-center gap-2">
                <Truck className="w-5 h-5 text-blue-500" />
                {editing ? "Rediger logistik-partner" : "Tilføj logistik partner"}
              </h3>
              <button onClick={closeForm} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-5">
              <Field label="Firmanavn *">
                <input
                  value={form.name}
                  onChange={(e) => setTop("name", e.target.value)}
                  placeholder="F.eks. ILK Transport ApS"
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-blue-500 outline-none"
                  data-testid="logistics-name-input"
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Intern referencekode *">
                  <input
                    value={form.customer_id}
                    onChange={(e) => setTop("customer_id", e.target.value)}
                    placeholder="F.eks. L001"
                    required
                    className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-blue-500 outline-none font-mono text-sm"
                    data-testid="logistics-customer-id-input"
                  />
                </Field>
                <Field label="Status">
                  <label className="flex items-center gap-2 px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg cursor-pointer">
                    <input type="checkbox" checked={!!form.active}
                      onChange={(e) => setTop("active", e.target.checked)}
                      className="w-4 h-4 accent-blue-500"
                      data-testid="logistics-active-toggle" />
                    <span className={`text-sm font-semibold ${form.active ? "text-blue-600" : "text-slate-400"}`}>
                      {form.active ? "Aktiv" : "Inaktiv"}
                    </span>
                  </label>
                </Field>
              </div>

              <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">
                  Logistik-admin
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    {editing ? "(redigér nedenfor)" : "- modtager en invitation på e-mail (72 timer)"}
                  </span>
                </label>
                <div className="grid grid-cols-1 gap-2">
                  <input value={form.admin.name} onChange={e => setAdminF("name", e.target.value)} placeholder="Admin navn"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-blue-500 outline-none text-sm"
                    data-testid="logistics-admin-name-input" />
                  <input value={form.admin.email} onChange={e => setAdminF("email", e.target.value)} placeholder="Admin email"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-blue-500 outline-none text-sm"
                    data-testid="logistics-admin-email-input" />
                  <input value={form.admin.phone} onChange={e => setAdminF("phone", e.target.value)} placeholder="Telefon"
                    className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-blue-500 outline-none text-sm"
                    data-testid="logistics-admin-phone-input" />
                </div>
                {!editing && (
                  <p className="text-xs text-slate-500 mt-1.5">
                    Når du gemmer, sender vi automatisk en invitations-mail med et 72-timers link, hvor logistik-admin'en selv vælger sin adgangskode.
                  </p>
                )}
                {editing && (
                  <p className="text-xs text-slate-500 mt-1.5">
                    Du kan ændre admin-navn og e-mail her. Brug Gensend-knappen i tabellen hvis linket er udløbet.
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={closeForm} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
              <button
                onClick={save}
                disabled={saving}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white inline-flex items-center gap-2"
                data-testid="save-logistics-partner-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                {editing ? "Gem ændringer" : "Opret logistik-partner"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}


/* ============== Plads Panel ============== */
function PladsPanel() {
  const [items, setItems] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterCompany, setFilterCompany] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [addressesFor, setAddressesFor] = useState(null); // plads object whose addresses we manage
  const [mergeSource, setMergeSource] = useState(null);   // plads object to merge FROM

  const [form, setForm] = useState({
    company_id: "default", name: "", city: "", address: "", location_code: "",
  });
  const [bulk, setBulk] = useState({ company_id: "default", text: "" });

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([
        axios.get(`${API}/superadmin/plads`),
        axios.get(`${API}/superadmin/companies`),
      ]);
      setItems(p.data);
      setCompanies(c.data);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openCreate = () => {
    setEditing(null);
    setForm({
      company_id: filterCompany || companies[0]?.id || "default",
      name: "", city: "", address: "", location_code: "",
    });
    setShowForm(true);
  };
  const openEdit = (p) => {
    setEditing(p);
    setForm({
      company_id: p.company_id, name: p.name || "",
      city: p.city || "", address: p.address || "",
      location_code: p.location_code || "",
    });
    setShowForm(true);
  };
  const openBulk = () => {
    setBulk({ company_id: filterCompany || companies[0]?.id || "default", text: "" });
    setShowBulk(true);
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Navn er påkrævet"); return; }
    try {
      if (editing) {
        await axios.put(`${API}/superadmin/plads/${editing.id}`, form);
        toast.success("Plads opdateret");
      } else {
        await axios.post(`${API}/superadmin/plads`, form);
        toast.success("Plads oprettet");
      }
      setShowForm(false);
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const saveBulk = async () => {
    const lines = bulk.text.split("\n").map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) { toast.error("Indtast mindst én plads"); return; }
    const items = lines.map(line => {
      // format: "Navn; By; Adresse; Lokationskode" (alle felter undtagen Navn er valgfri)
      const parts = line.split(";").map(s => s.trim());
      return {
        name: parts[0],
        city: parts[1] || "",
        address: parts[2] || "",
        location_code: parts[3] || "",
      };
    });
    try {
      const res = await axios.post(`${API}/superadmin/plads/bulk`, {
        company_id: bulk.company_id, items,
      });
      toast.success(`${res.data.created} pladser oprettet`);
      setShowBulk(false);
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/superadmin/plads/${id}`);
      toast.success("Plads slettet");
      fetchAll();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = items.filter(p => {
    if (filterCompany && p.company_id !== filterCompany) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return (p.name || "").toLowerCase().includes(s)
      || (p.city || "").toLowerCase().includes(s)
      || (p.address || "").toLowerCase().includes(s);
  });

  // Group by company for nicer display
  const grouped = useMemoGroupedByCompany(filtered, companies);

  return (
    <section data-testid="plads-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">
            Genbrug Pladser
          </h2>
          <p className="text-sm text-slate-500">
            Tilføj genbrugspladser under hvert firma (fx en gruppe som Vestforbrænding kan have 50+ pladser).
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Søg plads..."
              className="pl-10 pr-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none w-full md:w-56"
              data-testid="plads-search" />
          </div>
          <select value={filterCompany} onChange={(e) => setFilterCompany(e.target.value)}
            className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none"
            data-testid="plads-filter-company">
            <option value="">Alle grupper</option>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button onClick={openBulk}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700 hover:bg-slate-800 text-white rounded-xl font-semibold text-sm"
            data-testid="bulk-plads-btn">
            <Upload className="w-4 h-4" /> Bulk import
          </button>
          <button onClick={() => exportPladsExcel(filtered, companies)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-semibold text-sm"
            data-testid="export-excel-btn"
            title="Download Excel">
            <FileSpreadsheet className="w-4 h-4" /> Excel
          </button>
          <button onClick={() => exportPladsPdf(filtered, companies)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl font-semibold text-sm"
            data-testid="export-pdf-btn"
            title="Download PDF">
            <FileDown className="w-4 h-4" /> PDF
          </button>
          <button onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-sm shadow-md"
            data-testid="create-plads-btn">
            <Plus className="w-4 h-4" /> Ny plads
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-12 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
          <Layers className="w-10 h-10 mx-auto mb-3 text-slate-300" />
          <p className="font-medium">Ingen pladser endnu</p>
          <p className="text-sm mt-1">Opret den første plads eller brug bulk import.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(g => (
            <div key={g.company_id} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                <div className="flex items-center gap-2">
                  <Building className="w-4 h-4 text-orange-500" />
                  <h3 className="font-bold text-slate-900 dark:text-white">{g.company_name || g.company_id}</h3>
                </div>
                <span className="text-xs text-slate-500 font-semibold">{g.items.length} pladser</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100 dark:divide-slate-700">
                {g.items.map(p => (
                  <div key={p.id} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-900/30 flex items-start gap-3" data-testid={`plads-card-${p.id}`}>
                    <div className="w-9 h-9 rounded-lg bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 flex items-center justify-center flex-shrink-0">
                      <MapPin className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm text-slate-900 dark:text-white truncate">{p.name}</p>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                        {(p.city || p.address) && (
                          <p className="text-xs text-slate-500 truncate">
                            {[p.city, p.address].filter(Boolean).join(" · ")}
                          </p>
                        )}
                        {p.location_code ? (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                            #{p.location_code}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                            ej linket
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      <button onClick={() => setAddressesFor(p)} className="p-1.5 rounded hover:bg-orange-50 dark:hover:bg-orange-950/40" title="Underadresser" data-testid={`addresses-plads-${p.id}`}>
                        <Home className="w-3.5 h-3.5 text-orange-600" />
                      </button>
                      <button onClick={() => openEdit(p)} className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700" title="Rediger" data-testid={`edit-plads-${p.id}`}>
                        <Edit2 className="w-3.5 h-3.5 text-slate-600 dark:text-slate-400" />
                      </button>
                      <button onClick={() => setDeletingId(p.id)} className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-950/40" title="Slet" data-testid={`delete-plads-${p.id}`}>
                        <Trash2 className="w-3.5 h-3.5 text-red-600" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowForm(false)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-xl text-slate-900 dark:text-white">{editing ? "Rediger plads" : "Ny plads"}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-3">
              <Field label="Gruppe / Firma *">
                <select value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="plads-company-select">
                  {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Navn *">
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="F.eks. Skipstrup Genbrugsplads"
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="plads-name-input" />
              </Field>
              <Field label="By">
                <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="plads-city-input" />
              </Field>
              <Field label="Adresse">
                <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="plads-address-input" />
              </Field>
              <Field label="Lokationskode (link til bestillingsside)">
                <input value={form.location_code} onChange={(e) => setForm({ ...form, location_code: e.target.value })}
                  placeholder="F.eks. 3030 - uden kode kan pladsen ikke modtage bestillinger"
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none font-mono text-sm"
                  data-testid="plads-location-code-input" />
              </Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
              <button onClick={save} className="px-4 py-2 rounded-lg text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-white inline-flex items-center gap-2" data-testid="save-plads-btn">
                <Check className="w-4 h-4" /> {editing ? "Gem" : "Opret"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk import modal */}
      {showBulk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowBulk(false)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-xl text-slate-900 dark:text-white inline-flex items-center gap-2">
                <Upload className="w-5 h-5 text-orange-500" /> Bulk import af pladser
              </h3>
              <button onClick={() => setShowBulk(false)} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-3">
              <Field label="Gruppe / Firma *">
                <select value={bulk.company_id} onChange={(e) => setBulk({ ...bulk, company_id: e.target.value })}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none"
                  data-testid="bulk-company-select">
                  {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Liste (én plads per linje, format: Navn; By; Adresse; Lokationskode)">
                <textarea rows={12} value={bulk.text} onChange={(e) => setBulk({ ...bulk, text: e.target.value })}
                  placeholder={"Skipstrup Genbrugsplads; Skipstrup; Skipstrupvej 1; 3030\nCirklen Genbrugsplads; København; ; 3131\nGladsaxe Genbrugsstation"}
                  className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-orange-500 outline-none font-mono text-xs leading-relaxed"
                  data-testid="bulk-text-input" />
              </Field>
              <p className="text-xs text-slate-500">By, adresse og lokationskode er valgfri. Lokationskoden linker pladsen til bestillingssiden - uden kode kan order-brugere ikke bestille fra pladsen.</p>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowBulk(false)} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
              <button onClick={saveBulk} className="px-4 py-2 rounded-lg text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-white inline-flex items-center gap-2" data-testid="save-bulk-btn">
                <Upload className="w-4 h-4" /> Importer
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={!!deletingId} title="Slet plads?"
        message="Pladsen fjernes permanent. Eksisterende ture og data på pladsen bliver IKKE slettet."
        onConfirm={() => remove(deletingId)} onCancel={() => setDeletingId(null)} />

      {addressesFor && (
        <PladsAddressesModal
          plads={addressesFor}
          onClose={() => setAddressesFor(null)}
        />
      )}

      {mergeSource && (
        <PladsMergeModal
          source={mergeSource}
          allPlads={items}
          onClose={() => setMergeSource(null)}
          onMerged={() => { setMergeSource(null); fetchAll(); }}
        />
      )}
    </section>
  );
}

/* ============== Plads Addresses Modal ============== */
function PladsAddressesModal({ plads, onClose }) {
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("list"); // list | add | bulk
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ sub_area: "", postcode: "", city: "", street: "" });
  const [bulkText, setBulkText] = useState("");

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/superadmin/plads/${plads.id}/addresses`);
      setAddresses(data || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [plads.id]);

  useEffect(() => { fetch(); }, [fetch]);

  const filtered = addresses.filter(a => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (a.street || "").toLowerCase().includes(s)
      || (a.sub_area || "").toLowerCase().includes(s)
      || (a.city || "").toLowerCase().includes(s)
      || (a.postcode || "").toLowerCase().includes(s);
  });

  const grouped = (() => {
    const g = {};
    filtered.forEach(a => {
      const k = a.sub_area || "Andre";
      if (!g[k]) g[k] = [];
      g[k].push(a);
    });
    return Object.entries(g).sort((a, b) => a[0].localeCompare(b[0], "da"));
  })();

  const addOne = async () => {
    if (!form.street.trim()) { toast.error("Adresse er påkrævet"); return; }
    try {
      await axios.post(`${API}/superadmin/plads/${plads.id}/addresses`, form);
      toast.success("Adresse oprettet");
      setForm({ sub_area: "", postcode: "", city: "", street: "" });
      fetch();
      setTab("list");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const addBulk = async () => {
    const lines = bulkText.split("\n").map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) { toast.error("Indtast mindst én linje"); return; }
    const items = lines.map(line => {
      // Format: "sub_area | postnr og by | gade"  OR  "sub_area; postnr by; gade"
      const sep = line.includes("|") ? "|" : ";";
      const parts = line.split(sep).map(s => s.trim());
      // First column = sub_area, second = postnr+by ("3000 Helsingør"), third = street
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
      const res = await axios.post(`${API}/superadmin/plads/${plads.id}/addresses/bulk`, { items });
      toast.success(`${res.data.created} adresser oprettet`);
      setBulkText("");
      fetch();
      setTab("list");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const removeAddr = async (id) => {
    try {
      await axios.delete(`${API}/superadmin/plads/addresses/${id}`);
      toast.success("Adresse slettet");
      fetch();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-3xl w-full max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
          <div className="min-w-0">
            <h3 className="font-bold text-lg sm:text-xl text-slate-900 dark:text-white truncate inline-flex items-center gap-2">
              <Home className="w-5 h-5 text-orange-500 flex-shrink-0" /> Adresser · {plads.name}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">{addresses.length} adresser i alt</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 flex-shrink-0">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="px-5 pt-3 flex gap-1 border-b border-slate-200 dark:border-slate-700">
          <SubTab active={tab === "list"} onClick={() => setTab("list")}>Liste</SubTab>
          <SubTab active={tab === "add"} onClick={() => setTab("add")}>+ Tilføj én</SubTab>
          <SubTab active={tab === "bulk"} onClick={() => setTab("bulk")}>↑ Bulk import</SubTab>
        </div>

        <div className="overflow-y-auto p-5 flex-1">
          {tab === "list" && (
            <>
              <div className="relative max-w-sm mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Søg..."
                  className="pl-9 pr-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm w-full focus:border-orange-500 outline-none" />
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
                            <button onClick={() => removeAddr(a.id)} className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-950/40" title="Slet">
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
              <Field label="Underområde (fx Nordkysten)">
                <input value={form.sub_area} onChange={(e) => setForm({ ...form, sub_area: e.target.value })}
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500" />
              </Field>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Postnr">
                  <input value={form.postcode} onChange={(e) => setForm({ ...form, postcode: e.target.value })}
                    placeholder="3000"
                    className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500 font-mono" />
                </Field>
                <div className="col-span-2">
                  <Field label="By">
                    <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}
                      placeholder="Helsingør"
                      className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500" />
                  </Field>
                </div>
              </div>
              <Field label="Adresse *">
                <input value={form.street} onChange={(e) => setForm({ ...form, street: e.target.value })}
                  placeholder="Folehaven 1"
                  className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500" />
              </Field>
              <button onClick={addOne} className="mt-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-bold text-sm inline-flex items-center gap-2">
                <Plus className="w-4 h-4" /> Tilføj
              </button>
            </div>
          )}

          {tab === "bulk" && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Indsæt liste - én linje per adresse. Format:
              </p>
              <code className="block bg-slate-100 dark:bg-slate-900 rounded p-2 text-xs font-mono">
                Underområde | Postnr By | Adresse
              </code>
              <textarea rows={12} value={bulkText} onChange={(e) => setBulkText(e.target.value)}
                placeholder={"Nordkysten | 3000 Helsingør | Folehaven 1\nNordkysten | 3000 Helsingør | Kongevejen 1, afd. 82 - Hovparken\nBoliggården | 3000 Helsingør | Blishøj 1"}
                className="w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg outline-none focus:border-orange-500 font-mono text-xs leading-relaxed" />
              <button onClick={addBulk} className="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-bold text-sm inline-flex items-center gap-2">
                <Upload className="w-4 h-4" /> Importer
              </button>
              <p className="text-xs text-slate-500">
                Tip: du kan paste direkte fra et Excel-ark. Også <code>;</code> som separator virker.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============== Plads Merge Modal (Slå sammen) ============== */
function PladsMergeModal({ source, allPlads, onClose, onMerged }) {
  const [targetId, setTargetId] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [merging, setMerging] = useState(false);

  // Eligible targets: same company, different id
  const candidates = (allPlads || []).filter(
    (p) => p.id !== source.id && p.company_id === source.company_id,
  );

  const target = candidates.find((p) => p.id === targetId) || null;

  const doMerge = async () => {
    if (!targetId) {
      toast.error("Vælg en målplads");
      return;
    }
    if (confirmText.trim().toUpperCase() !== "SLET") {
      toast.error('Skriv "SLET" for at bekræfte');
      return;
    }
    setMerging(true);
    try {
      const { data } = await axios.post(`${API}/superadmin/plads/merge`, {
        source_id: source.id,
        target_id: targetId,
      });
      const m = data.moved || {};
      toast.success(
        `Pladser slået sammen - ${m.tours || 0} ture, ${m.addresses || 0} adresser flyttet`,
      );
      onMerged?.();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setMerging(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="plads-merge-modal">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-xl text-slate-900 dark:text-white inline-flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-purple-600" /> Slå pladser sammen
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="space-y-4">
          <div className="bg-purple-50 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800 rounded-lg p-3">
            <p className="text-xs uppercase tracking-wide text-purple-700 dark:text-purple-300 font-bold mb-1">Kildeplads (slettes)</p>
            <p className="font-semibold text-slate-900 dark:text-white">{source.name}</p>
            {(source.city || source.address) && (
              <p className="text-xs text-slate-500 mt-0.5">{[source.city, source.address].filter(Boolean).join(" · ")}</p>
            )}
          </div>

          <Field label="Målplads (alt flyttes hertil)">
            {candidates.length === 0 ? (
              <p className="text-xs text-slate-500 italic">Ingen andre pladser i samme virksomhed at flette med.</p>
            ) : (
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-purple-500 outline-none"
                data-testid="merge-target-select"
              >
                <option value="">Vælg målplads…</option>
                {candidates.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.city ? `· ${p.city}` : ""}
                  </option>
                ))}
              </select>
            )}
          </Field>

          {target && (
            <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3 text-xs text-emerald-900 dark:text-emerald-100">
              <p className="font-semibold mb-1">Hvad sker der?</p>
              <ul className="list-disc list-inside space-y-0.5 text-emerald-800 dark:text-emerald-200">
                <li>Alle ture, ordrer og priser fra <b>{source.name}</b> peger på <b>{target.name}</b>.</li>
                <li>Underadresser flyttes til {target.name}.</li>
                <li>Site-brugere, der havde {source.name} tildelt, får i stedet {target.name}.</li>
                <li>{source.name} slettes herefter permanent.</li>
              </ul>
            </div>
          )}

          <Field label='Bekræft ved at skrive "SLET"'>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="SLET"
              className="w-full px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg focus:border-red-500 outline-none font-mono"
              data-testid="merge-confirm-input"
            />
          </Field>
        </div>

        <div className="flex gap-2 justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200"
          >
            Annuller
          </button>
          <button
            onClick={doMerge}
            disabled={merging || !targetId || confirmText.trim().toUpperCase() !== "SLET"}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-purple-600 hover:bg-purple-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white inline-flex items-center gap-2"
            data-testid="confirm-merge-btn"
          >
            {merging ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitMerge className="w-4 h-4" />}
            Slå sammen
          </button>
        </div>
      </div>
    </div>
  );
}


function SubTab({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 text-sm font-semibold border-b-2 ${
        active
          ? "border-orange-500 text-slate-900 dark:text-white"
          : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function useMemoGroupedByCompany(items, companies) {
  return React.useMemo(() => {
    const cmap = {};
    companies.forEach(c => { cmap[c.id] = c.name; });
    const groups = {};
    items.forEach(it => {
      const cid = it.company_id || "default";
      if (!groups[cid]) groups[cid] = { company_id: cid, company_name: cmap[cid] || it.company_name, items: [] };
      groups[cid].items.push(it);
    });
    return Object.values(groups).sort((a, b) => (a.company_name || "").localeCompare(b.company_name || ""));
  }, [items, companies]);
}

/* ============== Settings Panel (Systemkoder) ============== */
function SettingsPanel() {
  const [settings, setSettings] = useState({ admin_password: "", driver_code: "", super_admin_email: "" });
  const [form, setForm] = useState({ admin_password: "", driver_code: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showAdminPw, setShowAdminPw] = useState(false);
  const [showDriverCode, setShowDriverCode] = useState(false);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/superadmin/settings`);
      setSettings(data);
      setForm({ admin_password: data.admin_password || "", driver_code: data.driver_code || "" });
    } catch (e) {
      toast.error(formatApiError(e));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/superadmin/settings`, form);
      toast.success("Koder opdateret!");
      fetchSettings();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>;

  return (
    <section data-testid="settings-panel" className="max-w-lg space-y-6">
      <div>
        <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Systemkoder</h2>
        <p className="text-sm text-slate-500 mt-1">Skift chauffør- og adminkoder. Ændringer træder i kraft med det samme.</p>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6 space-y-5">
        {/* Admin Password */}
        <div>
          <label className="block text-sm font-semibold mb-1.5 text-slate-700 dark:text-slate-300">
            Logistics Admin kode
          </label>
          <p className="text-xs text-slate-400 mb-2">Bruges af logistik-admins til at logge ind</p>
          <div className="relative">
            <input
              type={showAdminPw ? "text" : "password"}
              value={form.admin_password}
              onChange={e => setForm({ ...form, admin_password: e.target.value })}
              placeholder="Ny admin kode"
              className="w-full px-4 py-3 pr-10 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-xl focus:border-orange-500 outline-none font-mono"
              data-testid="admin-password-input"
            />
            <button onClick={() => setShowAdminPw(!showAdminPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
              {showAdminPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-1.5">
            Nuværende: <span className="font-mono text-slate-600 dark:text-slate-300">{showAdminPw ? settings.admin_password : "••••••••"}</span>
          </p>
        </div>

        {/* Driver Code - DEPRECATED i Fase 2:
            Chauffører bruger nu individuelt email + password via
            invitation-flow. Felter fjernet for at undgå forvirring. */}
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-1">
            Chauffør adgangskode er udfaset
          </p>
          <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
            Fra Fase 2 har hver chauffør sit eget email + password.
            Logistik-admin opretter chauffører i sit dashboard, og
            chaufføren modtager en invitations-email.
          </p>
        </div>

        <button onClick={save} disabled={saving}
          className="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold flex items-center justify-center gap-2 disabled:opacity-50"
          data-testid="save-settings-btn">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Gemmer..." : "Gem ændringer"}
        </button>
      </div>

      {/* Info box */}
      <div className="bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl p-4 text-xs text-slate-500 space-y-1.5">
        <p className="font-semibold text-slate-600 dark:text-slate-400 mb-2">ℹ️ Information</p>
        <p>• Chauffører oprettes nu med email + invitation (administreres af logistik-admin)</p>
        <p>• Admin kode: bruges af logistik-admins (ikke super admin)</p>
        <p>• Super admin login styres via .env filen på serveren</p>
        <p>• Ændringer træder i kraft med det samme - ingen genstart nødvendig</p>
      </div>
    </section>
  );
}

/* ============== Activity Log Panel ============== */
function ActivityLogPanel() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter ? `?action=${filter}&limit=200` : "?limit=200";
      const { data } = await axios.get(`${API}/superadmin/activity-log${params}`);
      setLogs(data);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const getActionMeta = (action) => {
    switch(action) {
      case "login_success":     return { label: "Login OK",           cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300", icon: CheckCircle2 };
      case "login_failed":      return { label: "Login fejl",         cls: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",               icon: XCircle };
      case "login_blocked_suspended": return { label: "Blokeret",     cls: "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300",   icon: AlertCircle };
      case "company_created":   return { label: "Firma oprettet",     cls: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",           icon: Building2 };
      case "company_deleted":   return { label: "Firma slettet",      cls: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",               icon: Trash2 };
      case "user_created":      return { label: "Bruger oprettet",    cls: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",           icon: Users };
      case "user_deleted":      return { label: "Bruger slettet",     cls: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",               icon: Trash2 };
      default:                  return { label: action,               cls: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",          icon: Activity };
    }
  };

  const exportCSV = () => {
    const headers = ["Tidspunkt", "Email", "Handling", "Rolle", "IP", "Årsag"];
    const rows = logs.map(l => [
      new Date(l.timestamp).toLocaleString("da-DK"),
      l.email || "",
      l.action || "",
      l.role || "",
      l.ip || "",
      l.reason || "",
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `aktivitetslog_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  };

  const successCount = logs.filter(l => l.action === "login_success").length;
  const failedCount = logs.filter(l => l.action === "login_failed").length;

  return (
    <section data-testid="activity-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Aktivitetslog</h2>
          <p className="text-sm text-slate-500">Hvem loggede ind, hvornår og fra hvilken IP.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select value={filter} onChange={e => setFilter(e.target.value)}
            className="px-3 py-2.5 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg text-sm focus:border-orange-500 outline-none">
            <option value="">Alle handlinger</option>
            <option value="login_success">Login OK</option>
            <option value="login_failed">Login fejl</option>
          </select>
          <button onClick={exportCSV}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold text-sm">
            <Download className="w-4 h-4" /> Eksporter CSV
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 text-center">
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{logs.length}</p>
          <p className="text-xs text-slate-500 mt-0.5">Handlinger i alt</p>
        </div>
        <div className="bg-emerald-50 dark:bg-emerald-950/20 rounded-xl p-4 border border-emerald-200 dark:border-emerald-800 text-center">
          <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">{successCount}</p>
          <p className="text-xs text-slate-500 mt-0.5">Vellykkede logins</p>
        </div>
        <div className="bg-red-50 dark:bg-red-950/20 rounded-xl p-4 border border-red-200 dark:border-red-800 text-center">
          <p className="text-2xl font-bold text-red-700 dark:text-red-300">{failedCount}</p>
          <p className="text-xs text-slate-500 mt-0.5">Fejlede logins</p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin inline text-slate-400" /></div>
      ) : logs.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-12 text-center text-slate-500 border border-slate-200 dark:border-slate-700">
          <Activity className="w-10 h-10 mx-auto mb-3 text-slate-300" />
          <p>Ingen aktivitet endnu</p>
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3 text-left">Tidspunkt</th>
                  <th className="px-4 py-3 text-left">Email</th>
                  <th className="px-4 py-3 text-left">Handling</th>
                  <th className="px-4 py-3 text-left">Rolle</th>
                  <th className="px-4 py-3 text-left">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {logs.map(log => {
                  const meta = getActionMeta(log.action);
                  const Icon = meta.icon;
                  return (
                    <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30">
                      <td className="px-4 py-3 font-mono text-xs text-slate-500 whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString("da-DK")}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-800 dark:text-white">{log.email}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${meta.cls}`}>
                          <Icon className="w-3 h-3" /> {meta.label}
                        </span>
                        {log.reason && <span className="ml-2 text-xs text-slate-400">({log.reason})</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-500">{log.role || "-"}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">{log.ip || "-"}</td>
                      {log.details && Object.keys(log.details).length > 0 && (
                        <td className="px-4 py-3 text-xs text-slate-400 hidden xl:table-cell">
                          {Object.entries(log.details).map(([k,v]) => `${k}: ${v}`).join(" · ")}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

/* ============================ HOLIDAY GROUPS PANEL ============================ */
function HolidayGroupsPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null); // group object or null
  const [form, setForm] = useState({ name: "", year: "", holidays: [] });
  const [saving, setSaving] = useState(false);
  const [copyDialog, setCopyDialog] = useState(null); // {group, target_year}
  // Brugerkrav 2026-06-15 (runde 7): React-baseret confirm-dialog så slet
  // virker pålideligt i alle browsere/iframes (window.confirm kan afvises).
  const [deletingGroup, setDeletingGroup] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/superadmin/holiday-groups`);
      setItems(data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", year: String(new Date().getFullYear()), holidays: [] });
    setShowForm(true);
  };
  const openEdit = (g) => {
    setEditing(g);
    setForm({
      name: g.name || "",
      year: g.year != null ? String(g.year) : "",
      holidays: [...(g.holidays || [])],
    });
    setShowForm(true);
  };

  const addHoliday = () => {
    setForm(p => ({ ...p, holidays: [...p.holidays, { name: "", date: "" }] }));
  };
  const updateHoliday = (idx, field, val) => {
    setForm(p => ({
      ...p,
      holidays: p.holidays.map((h, i) => i === idx ? { ...h, [field]: val } : h),
    }));
  };
  const removeHoliday = (idx) => {
    setForm(p => ({ ...p, holidays: p.holidays.filter((_, i) => i !== idx) }));
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Navn er påkrævet"); return; }
    const clean = form.holidays.filter(h => h.name.trim() && h.date.trim());
    const yearInt = form.year ? parseInt(form.year, 10) : null;
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API}/superadmin/holiday-groups/${editing.id}`, {
          name: form.name.trim(), year: yearInt, holidays: clean,
        });
        toast.success("Helligdagsgruppe opdateret");
      } else {
        await axios.post(`${API}/superadmin/holiday-groups`, {
          name: form.name.trim(), year: yearInt, holidays: clean,
        });
        toast.success("Helligdagsgruppe oprettet");
      }
      setShowForm(false); setEditing(null); fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const remove = (g) => {
    const cnt = g.assigned_count || 0;
    if (cnt > 0) {
      // Brugerkrav 2026-06-15 (runde 7): Slet-knappen SKAL give visuel feedback.
      // Tidligere var knappen `disabled` → klik gjorde intet. Nu vises en
      // tydelig forklaring så brugeren ved præcis hvad der skal gøres.
      window.alert(
        `Helligdagsgruppen "${g.name}" er tildelt ${cnt} kunde(r) og kan derfor ikke slettes.\n\n` +
        `Du har to muligheder:\n` +
        `  1) "Deaktivér" gruppen - eksisterende tildelinger bevares men ingen nye kunder kan vælge den.\n` +
        `  2) Frakobl gruppen fra alle kunder først (under "Kunder & Logistik" → rediger hver kunde → ` +
        `vælg en anden gruppe eller "Ingen helligdagsgruppe"), og slet derefter gruppen permanent.`
      );
      return;
    }
    setDeletingGroup(g);
  };
  const performDeleteGroup = async () => {
    const g = deletingGroup;
    setDeletingGroup(null);
    if (!g) return;
    try {
      await axios.delete(`${API}/superadmin/holiday-groups/${g.id}`);
      toast.success("Helligdagsgruppe slettet");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const toggleActive = async (g) => {
    const cnt = g.assigned_count || 0;
    if (g.active !== false && cnt > 0) {
      const ok = window.confirm(`Deaktivér "${g.name}"?\n\nGruppen er aktuelt tildelt ${cnt} kunde(r). Eksisterende tilknytninger bevares; nye kunder kan ikke tildeles gruppen.`);
      if (!ok) return;
    }
    try {
      await axios.post(`${API}/superadmin/holiday-groups/${g.id}/toggle-active`,
                       { active: g.active === false });
      toast.success(g.active === false ? "Gruppe genaktiveret" : "Gruppe deaktiveret");
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const doCopy = async () => {
    const t = parseInt(copyDialog.target_year || "0", 10);
    if (!t || t < 2000 || t > 2100) { toast.error("Vælg et gyldigt år (2000-2100)"); return; }
    try {
      await axios.post(`${API}/superadmin/holiday-groups/${copyDialog.group.id}/copy`,
                       { target_year: t });
      toast.success(`Kopieret til ${t}. Husk at justere datoerne.`);
      setCopyDialog(null);
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <section data-testid="holiday-groups-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Helligdagsgrupper</h2>
          <p className="text-sm text-slate-500 mt-1">Standardgrundlag for Location Admins helligdagskalendere. Opret én gruppe pr. år.</p>
        </div>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold"
          data-testid="add-holiday-group-btn"
        >
          <Plus className="w-4 h-4" /> Ny helligdagsgruppe
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen helligdagsgrupper endnu. Opret den første.</div>
        ) : items.map(g => {
          const isInactive = g.active === false;
          const assigned = g.assigned_count || 0;
          return (
          <div key={g.id}
            className={`border-b border-slate-100 dark:border-slate-700/50 last:border-0 p-4 ${isInactive ? "opacity-70 bg-slate-50 dark:bg-slate-900/30" : ""}`}
            data-testid={`holiday-group-row-${g.id}`}>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-bold text-slate-900 dark:text-white">{g.name}</p>
                  {g.year && (
                    <span className="text-[11px] font-bold uppercase bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full"
                      data-testid={`year-badge-${g.id}`}>
                      {g.year}
                    </span>
                  )}
                  {isInactive && (
                    <span className="text-[11px] font-bold uppercase bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded-full"
                      data-testid={`inactive-badge-${g.id}`}>
                      Inaktiv
                    </span>
                  )}
                  {assigned > 0 && (
                    <span className="text-[11px] font-semibold bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full">
                      Tildelt {assigned} kunde{assigned === 1 ? "" : "r"}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-0.5">{g.holidays?.length || 0} helligdage</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={() => setCopyDialog({ group: g, target_year: g.year ? String(g.year + 1) : String(new Date().getFullYear() + 1) })}
                  className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 hover:text-purple-600"
                  title="Kopiér til andet år"
                  data-testid={`copy-holiday-group-${g.id}`}>
                  <Copy className="w-4 h-4" />
                </button>
                <button onClick={() => toggleActive(g)}
                  className={`p-1.5 rounded ${isInactive ? "hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-emerald-600" : "hover:bg-amber-50 dark:hover:bg-amber-950/30 text-amber-600"}`}
                  title={isInactive ? "Genaktivér" : "Deaktivér"}
                  data-testid={`toggle-active-holiday-group-${g.id}`}>
                  {isInactive ? <CheckCircle2 className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                </button>
                <button onClick={() => openEdit(g)}
                  className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 hover:text-blue-600"
                  data-testid={`edit-holiday-group-${g.id}`}>
                  <Edit2 className="w-4 h-4" />
                </button>
                <button onClick={() => remove(g)}
                  className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-950/30 text-slate-500 hover:text-red-600"
                  title={assigned > 0 ? `Tildelt ${assigned} kunde(r) - kræver frakobling først` : "Slet permanent"}
                  data-testid={`delete-holiday-group-${g.id}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            {g.holidays && g.holidays.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1">
                {g.holidays.slice(0, 12).map((h, i) => (
                  <span key={i} className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider bg-orange-100 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 px-2 py-0.5 rounded-full font-semibold">
                    <Calendar className="w-3 h-3" /> {h.date} <span className="opacity-80">· {h.name}</span>
                  </span>
                ))}
                {g.holidays.length > 12 && (
                  <span className="text-[10px] text-slate-400 font-semibold">+{g.holidays.length - 12} flere</span>
                )}
              </div>
            )}
          </div>
        );})}
      </div>

      {/* COPY DIALOG */}
      {copyDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="copy-holiday-group-modal">
          <div className="absolute inset-0 bg-black/60" onClick={() => setCopyDialog(null)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-5">
            <h3 className="font-bold text-slate-900 dark:text-white mb-2">Kopiér helligdagsgruppe</h3>
            <p className="text-sm text-slate-500 mb-4">
              Kopiér <strong>{copyDialog.group.name}</strong> til et nyt år. Helligdagsnavne og datoer kopieres som de er -
              du skal justere datoerne manuelt bagefter (de fleste danske helligdage flytter sig).
            </p>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Målår</label>
            <input type="number" min="2000" max="2100"
              value={copyDialog.target_year}
              onChange={e => setCopyDialog({ ...copyDialog, target_year: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm mb-4"
              data-testid="copy-target-year-input" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setCopyDialog(null)}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
                Annullér
              </button>
              <button onClick={doCopy}
                className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-semibold"
                data-testid="confirm-copy-btn">
                <Copy className="w-4 h-4" /> Kopiér
              </button>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowForm(false)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between shrink-0">
              <h3 className="font-bold text-slate-900 dark:text-white">{editing ? "Rediger helligdagsgruppe" : "Ny helligdagsgruppe"}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-500"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-5 overflow-y-auto space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Navn *</label>
                  <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Fx Helligdage i Danmark"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm"
                    data-testid="holiday-group-name-input" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">År</label>
                  <input type="number" min="2000" max="2100" value={form.year}
                    onChange={e => setForm({ ...form, year: e.target.value })}
                    placeholder="2027"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm"
                    data-testid="holiday-group-year-input" />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-slate-500">Helligdage</p>
                  <button onClick={addHoliday} className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded text-xs font-semibold"
                    data-testid="add-holiday-btn">
                    <Plus className="w-3 h-3" /> Tilføj helligdag
                  </button>
                </div>
                <div className="space-y-1.5">
                  {form.holidays.length === 0 && (
                    <p className="text-xs text-slate-400 italic">Ingen helligdage endnu - tryk "Tilføj helligdag".</p>
                  )}
                  {form.holidays.map((h, i) => (
                    <div key={i} className="flex gap-2 items-center" data-testid={`holiday-row-${i}`}>
                      <input value={h.name} onChange={e => updateHoliday(i, "name", e.target.value)}
                        placeholder="Navn (fx Juledag)"
                        className="flex-1 px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-sm"
                        data-testid={`holiday-name-${i}`} />
                      <input type="date" value={h.date} onChange={e => updateHoliday(i, "date", e.target.value)}
                        className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded text-sm"
                        data-testid={`holiday-date-${i}`} />
                      <button onClick={() => removeHoliday(i)} className="p-1.5 hover:bg-red-50 dark:hover:bg-red-950/30 rounded text-slate-400 hover:text-red-500"
                        data-testid={`remove-holiday-${i}`}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2 shrink-0">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
                Annuller
              </button>
              <button onClick={save} disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
                data-testid="holiday-group-save-btn">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deletingGroup}
        title="Slet helligdagsgruppe?"
        message={deletingGroup ? `Slet "${deletingGroup.name}" permanent? Denne handling kan ikke fortrydes.` : ""}
        onConfirm={performDeleteGroup}
        onCancel={() => setDeletingGroup(null)}
      />
    </section>
  );
}



/* ============== Helligdags-delta panel ============== */

const OP_LABELS = {
  add: { label: "Tilføj", color: "emerald" },
  modify: { label: "Ændr", color: "blue" },
  delete: { label: "Slet", color: "rose" },
};

function HolidayDeltasPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | "new" | obj
  const [publishing, setPublishing] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/superadmin/holiday-deltas`);
      setItems(data || []);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const [publishTarget, setPublishTarget] = useState(null); // delta object eller null
  // Brugerkrav 2026-06-15 (runde 7): Slet-knappen skal RIGTIGT virke. Tidligere
  // brugte vi `window.confirm` der i nogle browsere/iframes silently afvises
  // → klik gjorde intet. Vi bruger nu en React-baseret ConfirmDialog.
  const [deletingDelta, setDeletingDelta] = useState(null);

  const remove = (d) => setDeletingDelta(d);
  const performDelete = async () => {
    const d = deletingDelta;
    setDeletingDelta(null);
    if (!d) return;
    try {
      const r = await axios.delete(`${API}/superadmin/holiday-deltas/${d.id}`);
      toast.success(`Slettet${r.data?.deleted_notifications ? ` · ${r.data.deleted_notifications} notifikation(er) ryddet` : ""}`);
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const openPublish = (d) => setPublishTarget(d);
  const doPublish = async (companyIds) => {
    if (!publishTarget) return;
    setPublishing(publishTarget.id);
    try {
      const r = await axios.post(
        `${API}/superadmin/holiday-deltas/${publishTarget.id}/publish`,
        { company_ids: companyIds || [] },
      );
      const scope = companyIds && companyIds.length > 0
        ? `${companyIds.length} kunde${companyIds.length === 1 ? "" : "r"}`
        : "ALLE kunder";
      toast.success(`Publiceret til ${scope} · ${r.data.notifications_created} ny notifikation${r.data.notifications_created === 1 ? "" : "er"}`);
      setPublishTarget(null);
      fetchAll();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setPublishing(null); }
  };

  return (
    <section data-testid="holiday-deltas-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white">Helligdags-delta</h2>
          <p className="text-sm text-slate-500 mt-1">
            Publicér helligdags-opdateringer til alle Lokations-administratorer. Hver LA kan derefter gennemgå,
            redigere og importere ændringerne i deres kontinuerlige helligdagskalender.
          </p>
        </div>
        <button onClick={() => setEditing("new")}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold"
          data-testid="add-delta-btn">
          <Plus className="w-4 h-4" /> Nyt delta
        </button>
      </div>

      <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm">Ingen helligdags-delta'er endnu.</div>
        ) : items.map(d => {
          const isPub = d.status === "published";
          return (
            <div key={d.id} className="px-5 py-4 border-b border-slate-100 dark:border-slate-700 last:border-b-0" data-testid={`delta-row-${d.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-bold text-slate-900 dark:text-white">{d.name}</p>
                    {d.year && (
                      <span className="text-[10px] font-bold uppercase bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">{d.year}</span>
                    )}
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                      isPub
                        ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                        : "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
                    }`}>
                      {isPub ? "Publiceret" : "Kladde"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{(d.operations || []).length} operation{(d.operations || []).length === 1 ? "" : "er"}</p>
                  {isPub && d.published_at && (
                    <p className="text-[11px] text-slate-400 mt-0.5">Publiceret: {new Date(d.published_at).toLocaleString("da-DK")}</p>
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  {!isPub && (
                    <button onClick={() => setEditing(d)} className="p-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-950/30 text-slate-500 hover:text-blue-600" title="Rediger" data-testid={`edit-delta-${d.id}`}>
                      <Edit2 className="w-4 h-4" />
                    </button>
                  )}
                  <button onClick={() => openPublish(d)} disabled={publishing === d.id}
                    className="p-1.5 rounded hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-slate-500 hover:text-emerald-600 disabled:opacity-50"
                    title={isPub ? "Genpublicér til nye kunder" : "Publicér til kunder"} data-testid={`publish-delta-${d.id}`}>
                    {publishing === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </button>
                  <button onClick={() => remove(d)}
                    className="p-1.5 rounded hover:bg-rose-50 dark:hover:bg-rose-950/30 text-slate-500 hover:text-rose-600"
                    title="Slet" data-testid={`delete-delta-${d.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(d.operations || []).slice(0, 6).map((o, i) => {
                  const meta = OP_LABELS[o.op] || OP_LABELS.modify;
                  return (
                    <span key={i} className={`px-2 py-0.5 rounded text-[11px] font-semibold bg-${meta.color}-50 dark:bg-${meta.color}-950/40 text-${meta.color}-700 dark:text-${meta.color}-300 border border-${meta.color}-200 dark:border-${meta.color}-800`}>
                      {meta.label}: {o.match_name || o.new_name}{o.new_date ? ` · ${o.new_date}` : ""}
                    </span>
                  );
                })}
                {(d.operations || []).length > 6 && (
                  <span className="text-[11px] text-slate-400">+{d.operations.length - 6} mere</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {editing && (
        <HolidayDeltaEditor
          delta={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}

      {publishTarget && (
        <PublishDeltaCompanyPicker
          delta={publishTarget}
          onCancel={() => setPublishTarget(null)}
          onPublish={doPublish}
          publishing={publishing === publishTarget.id}
        />
      )}

      <ConfirmDialog
        open={!!deletingDelta}
        title={`Slet ${deletingDelta?.status === "published" ? "publiceret " : ""}delta?`}
        message={deletingDelta ? (
          deletingDelta.status === "published"
            ? `Slet "${deletingDelta.name}" permanent? Delta'et og alle relaterede notifikationer hos Lokations-administratorerne fjernes. LA'er der allerede har importeret beholder deres data.`
            : `Slet "${deletingDelta.name}" permanent? Denne handling kan ikke fortrydes.`
        ) : ""}
        onConfirm={performDelete}
        onCancel={() => setDeletingDelta(null)}
      />
    </section>
  );
}

function PublishDeltaCompanyPicker({ delta, onCancel, onPublish, publishing }) {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState(new Set());
  const [search, setSearch] = useState("");
  const [allMode, setAllMode] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/superadmin/companies`);
        const customers = (r.data || []).filter(c =>
          (c.company_type || c.type || "customer") !== "logistics" && c.active !== false,
        );
        setCompanies(customers);
      } catch (e) { toast.error(formatApiError(e)); }
      finally { setLoading(false); }
    })();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter(c => (c.name || "").toLowerCase().includes(q)
      || (c.customer_id || "").toLowerCase().includes(q));
  }, [companies, search]);

  const toggle = (id) => {
    setPicked(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    if (picked.size === filtered.length) setPicked(new Set());
    else setPicked(new Set(filtered.map(c => c.id)));
  };

  const submit = () => {
    if (allMode) {
      onPublish([]);
    } else if (picked.size === 0) {
      toast.error("Vælg mindst én kunde");
    } else {
      onPublish(Array.from(picked));
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" data-testid="publish-delta-modal">
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 dark:text-white">Publicér "{delta.name}"</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">Vælg de kunder der skal modtage denne helligdags-delta.</p>
          </div>
          <button onClick={onCancel} className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={allMode} onChange={e => setAllMode(e.target.checked)}
              className="w-4 h-4 accent-emerald-600"
              data-testid="publish-all-checkbox" />
            <span className="text-sm text-slate-700 dark:text-slate-200 font-bold">Publicér til ALLE aktive kunder</span>
          </label>
        </div>
        {!allMode && (
          <>
            <div className="px-5 py-2 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Søg kunde (navn eller ID)"
                className="flex-1 px-3 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm"
                data-testid="publish-search-input" />
              <button onClick={toggleAll}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 whitespace-nowrap"
                data-testid="publish-toggle-all-filtered">
                {picked.size === filtered.length && filtered.length > 0 ? "Fravælg alle" : "Vælg alle"} ({filtered.length})
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-2 space-y-1">
              {loading ? (
                <div className="py-6 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>
              ) : filtered.length === 0 ? (
                <p className="py-6 text-sm text-slate-400 italic text-center">Ingen kunder fundet.</p>
              ) : filtered.map(c => {
                const on = picked.has(c.id);
                return (
                  <label key={c.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer ${
                      on ? "bg-emerald-50 dark:bg-emerald-950/30" : "hover:bg-slate-50 dark:hover:bg-slate-700/30"
                    }`}
                    data-testid={`publish-company-${c.id}`}>
                    <input type="checkbox" checked={on} onChange={() => toggle(c.id)}
                      className="w-4 h-4 accent-emerald-600 rounded" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-slate-900 dark:text-white">{c.name}</p>
                      {c.customer_id && <p className="text-[11px] text-slate-500">{c.customer_id}</p>}
                    </div>
                  </label>
                );
              })}
            </div>
          </>
        )}
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-between items-center">
          <span className="text-[11px] text-slate-500">
            {allMode ? `→ Sendes til ALLE kunder` : `${picked.size} valgt`}
          </span>
          <div className="flex gap-2">
            <button onClick={onCancel}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
              Annuller
            </button>
            <button onClick={submit} disabled={publishing || (!allMode && picked.size === 0)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
              data-testid="publish-confirm-btn">
              {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Publicér
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function HolidayDeltaEditor({ delta, onClose, onSaved }) {
  const isEdit = !!delta;
  const [name, setName] = useState(delta?.name || "");
  const [year, setYear] = useState(delta?.year ? String(delta.year) : "");
  const [ops, setOps] = useState(() => (delta?.operations || []).map(o => ({ ...o })));
  const [saving, setSaving] = useState(false);

  const addOp = (op) => setOps(prev => [...prev, { op, match_name: "", new_name: "", new_date: "" }]);
  const updateOp = (i, k, v) => setOps(prev => prev.map((o, idx) => idx === i ? { ...o, [k]: v } : o));
  const removeOp = (i) => setOps(prev => prev.filter((_, idx) => idx !== i));

  const save = async () => {
    if (!name.trim()) { toast.error("Navn er påkrævet"); return; }
    if (ops.length === 0) { toast.error("Tilføj mindst én operation"); return; }
    const yearInt = year ? parseInt(year, 10) : null;
    const payload = { name: name.trim(), year: yearInt, operations: ops };
    setSaving(true);
    try {
      if (isEdit) {
        await axios.put(`${API}/superadmin/holiday-deltas/${delta.id}`, payload);
        toast.success("Delta opdateret");
      } else {
        await axios.post(`${API}/superadmin/holiday-deltas`, payload);
        toast.success("Delta oprettet");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center p-4" data-testid="delta-editor-modal">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h3 className="font-bold text-slate-900 dark:text-white">{isEdit ? "Rediger" : "Nyt"} helligdags-delta</h3>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-500"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 overflow-y-auto space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-500 mb-1">Navn *</label>
              <input value={name} onChange={e => setName(e.target.value)}
                placeholder='fx "Helligdagsopdatering 2027"'
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm"
                data-testid="delta-name-input" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">År (valgfri)</label>
              <input type="number" min="2000" max="2100" value={year} onChange={e => setYear(e.target.value)}
                placeholder={String(new Date().getFullYear())}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 rounded-lg text-sm"
                data-testid="delta-year-input" />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-slate-500">Operationer</p>
              <div className="flex gap-1">
                <button onClick={() => addOp("add")} className="px-2 py-1 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200" data-testid="add-op-add">+ Tilføj</button>
                <button onClick={() => addOp("modify")} className="px-2 py-1 rounded text-[11px] font-bold bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200" data-testid="add-op-modify">+ Ændr</button>
                <button onClick={() => addOp("delete")} className="px-2 py-1 rounded text-[11px] font-bold bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200" data-testid="add-op-delete">+ Slet</button>
              </div>
            </div>
            <div className="space-y-2">
              {ops.length === 0 && <p className="text-xs text-slate-400 italic">Tilføj operation: "Tilføj" en ny dag, "Ændr" en eksisterende, eller "Slet" en helligdag.</p>}
              {ops.map((o, i) => {
                const meta = OP_LABELS[o.op] || OP_LABELS.modify;
                return (
                  <div key={i} className={`border-l-4 border-${meta.color}-500 bg-slate-50 dark:bg-slate-900/40 rounded p-3 space-y-2`} data-testid={`op-row-${i}`}>
                    <div className="flex items-center justify-between">
                      <span className={`text-[11px] font-bold uppercase text-${meta.color}-700 dark:text-${meta.color}-300`}>{meta.label}</span>
                      <button onClick={() => removeOp(i)} className="p-1 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded text-slate-400 hover:text-rose-500" data-testid={`remove-op-${i}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <input value={o.match_name || ""} onChange={e => updateOp(i, "match_name", e.target.value)}
                        placeholder={o.op === "add" ? "Nyt navn" : "Navn der skal matches"}
                        className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm"
                        data-testid={`op-match-name-${i}`} />
                      {o.op !== "delete" && (
                        <>
                          {o.op === "modify" && (
                            <input value={o.new_name || ""} onChange={e => updateOp(i, "new_name", e.target.value)}
                              placeholder="Nyt navn (valgfri)"
                              className="px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm"
                              data-testid={`op-new-name-${i}`} />
                          )}
                          <input type="date" value={o.new_date || ""} onChange={e => updateOp(i, "new_date", e.target.value)}
                            className={`px-2 py-1.5 border border-slate-300 dark:border-slate-600 dark:bg-slate-800 rounded text-sm ${o.op === "modify" ? "" : "sm:col-span-2"}`}
                            data-testid={`op-date-${i}`} />
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
            Annuller
          </button>
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-sm font-semibold"
            data-testid="save-delta-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Gem
          </button>
        </div>
      </div>
    </div>
  );
}


/* ============================ HOLIDAY INFO PANEL (combined) ============================
   Erstatter de tidligere separate "Helligdagsgrupper" og "Helligdags-delta" tabs.
   Viser begge sektioner side om side, så super admin kan administrere alt på ét sted. */
function HolidayInfoPanel() {
  return (
    <section data-testid="holiday-info-panel" className="space-y-10">
      <div>
        <h2 className="font-heading font-bold text-2xl text-slate-900 dark:text-white mb-2">
          Administrer helligdagsinformation
        </h2>
        <p className="text-sm text-slate-500">
          Opret og vedligehold helligdagsgrupper (præ-definerede sæt fx Christmas-pakke 2026) samt
          publicér helligdags-deltaer til specifikke kunder.
        </p>
      </div>
      <div className="space-y-10">
        {/* Sektion 1: Helligdagsgrupper-bibliotek */}
        <HolidayGroupsPanel />
        {/* Tydelig separator */}
        <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
          {/* Sektion 2: Delta-administration + publicering */}
          <HolidayDeltasPanel />
        </div>
      </div>
    </section>
  );
}


/* ============== Client Features Panel (Super Admin's tab - Fase 15.40) ==============
 *
 * Tillader super-admin at toggle platforms-features pr. klient. Modellen er
 * meget bevidst minimal:
 *
 *   - Venstre kolonne: liste over ALLE klienter (companies). Vælg én.
 *   - Højre kolonne: liste over features (key + description + toggle).
 *   - Lokal "dirty"-state pr. feature; super-admin trykker GEM nederst for
 *     at persistere via PATCH-endpoints.
 *   - Audit-info vises pr. feature: "Sidst ændret: {date} af {email}".
 *
 * Sådan tilføjer du en ny feature (fremtidssikring):
 *   1) Tilføj nøglen til `FEATURE_KEYS` i backend (`server.py`).
 *   2) Tilføj en ny række - backend returnerer den automatisk her.
 *   3) Wrap UI-elementet med `useFeatureFlag()` i frontend.
 */
function ClientFeaturesPanel() {
  const [companies, setCompanies] = useState([]);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [features, setFeatures] = useState([]);   // [{key, enabled, description, updated_at, updated_by}]
  const [dirty, setDirty] = useState({});         // {feature_key: nextBool}
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [loadingFeatures, setLoadingFeatures] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load all clients/companies once.
  useEffect(() => {
    setLoadingCompanies(true);
    // Fase 15.40: super-admin har sit eget /superadmin/companies-endpoint
    // som returnerer alle firmaer på tværs af tenants.
    axios.get(`${API}/superadmin/companies`)
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : [];
        // Sort alfabetisk, men flyt suspended/inactive nederst.
        list.sort((a, b) => {
          const aAct = a.active !== false ? 0 : 1;
          const bAct = b.active !== false ? 0 : 1;
          if (aAct !== bAct) return aAct - bAct;
          return (a.name || "").localeCompare(b.name || "", "da");
        });
        setCompanies(list);
      })
      .catch(() => setCompanies([]))
      .finally(() => setLoadingCompanies(false));
  }, []);

  // Load features for the selected client.
  const loadFeatures = useCallback(async (companyId) => {
    if (!companyId) {
      setFeatures([]);
      setDirty({});
      return;
    }
    setLoadingFeatures(true);
    try {
      const { data } = await axios.get(`${API}/admin/companies/${companyId}/features`);
      setFeatures(Array.isArray(data?.features) ? data.features : []);
      setDirty({});  // reset pending edits when switching client
    } catch (e) {
      toast.error(formatApiError(e) || "Kunne ikke hente features");
      setFeatures([]);
    } finally {
      setLoadingFeatures(false);
    }
  }, []);

  useEffect(() => {
    loadFeatures(selectedId);
  }, [selectedId, loadFeatures]);

  const selectedCompany = companies.find(c => c.id === selectedId) || null;
  const filteredCompanies = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter(c =>
      (c.name || "").toLowerCase().includes(q) ||
      (c.id || "").toLowerCase().includes(q),
    );
  }, [companies, filter]);

  const hasDirty = Object.keys(dirty).length > 0;

  const toggleLocal = (key) => {
    const current = features.find(f => f.key === key);
    if (!current) return;
    const currentBool = key in dirty ? dirty[key] : !!current.enabled;
    const nextBool = !currentBool;
    setDirty(d => {
      const next = { ...d };
      // Hvis nextBool matcher den oprindelige værdi, fjern dirty-flaget.
      if (nextBool === !!current.enabled) delete next[key];
      else next[key] = nextBool;
      return next;
    });
  };

  const onSave = async () => {
    if (!selectedId || !hasDirty || saving) return;
    setSaving(true);
    let failures = 0;
    let successes = 0;
    let latestFeatures = features;
    for (const [key, nextBool] of Object.entries(dirty)) {
      try {
        const { data } = await axios.patch(
          `${API}/admin/companies/${selectedId}/features/${key}`,
          { is_enabled: nextBool },
        );
        if (Array.isArray(data?.features)) latestFeatures = data.features;
        successes += 1;
      } catch (e) {
        failures += 1;
        toast.error(`${key}: ${formatApiError(e) || "fejl ved gem"}`);
      }
    }
    setFeatures(latestFeatures);
    if (failures === 0) {
      toast.success(`Gemt ✓ (${successes} ${successes === 1 ? "ændring" : "ændringer"})`);
      setDirty({});
    } else if (successes > 0) {
      toast.warning(`Gemt delvist: ${successes} OK, ${failures} fejlede`);
      // Behold kun de dirty-keys der fejlede.
      setDirty(d => {
        const next = {};
        for (const k of Object.keys(d)) {
          if (!latestFeatures.find(f => f.key === k && f.enabled === d[k])) next[k] = d[k];
        }
        return next;
      });
    }
    setSaving(false);
  };

  const onReset = () => {
    if (!hasDirty || saving) return;
    setDirty({});
  };

  return (
    <section className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden" data-testid="client-features-panel">
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <h2 className="text-base font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <Power className="w-4 h-4 text-amber-500" />
          Administrer Klientplatformsfunktioner
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Vælg en klient til venstre og slå platforms-features til/fra. Ændringer træder
          i kraft ved klientens næste login eller side-refresh.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] divide-y md:divide-y-0 md:divide-x divide-slate-200 dark:divide-slate-700">
        {/* Venstre: klient-liste */}
        <div className="p-3 max-h-[640px] overflow-y-auto" data-testid="client-features-clients-list">
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Søg klient…"
              className="w-full pl-8 pr-2 py-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded-md bg-white dark:bg-slate-900"
              data-testid="client-features-search"
            />
          </div>
          {loadingCompanies ? (
            <div className="text-xs italic text-slate-500 py-4 text-center">
              <Loader2 className="w-4 h-4 inline animate-spin mr-1" />Henter klienter…
            </div>
          ) : filteredCompanies.length === 0 ? (
            <p className="text-xs italic text-slate-500 py-4 text-center">Ingen klienter matcher.</p>
          ) : (
            <ul className="space-y-0.5">
              {filteredCompanies.map(c => {
                const isSel = c.id === selectedId;
                const isInactive = c.active === false;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(c.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-md text-sm transition-colors ${
                        isSel
                          ? "bg-amber-100 dark:bg-amber-900/30 text-amber-900 dark:text-amber-200 font-bold"
                          : "hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-700 dark:text-slate-300"
                      } ${isInactive ? "opacity-60" : ""}`}
                      data-testid={`client-features-client-${c.id}`}
                    >
                      <span className="truncate block">{c.name || "(uden navn)"}</span>
                      {isInactive && (
                        <span className="text-[10px] text-red-500 font-normal">suspenderet</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Højre: feature-toggle-liste */}
        <div className="p-4 md:p-6">
          {!selectedId ? (
            <div className="text-center py-10" data-testid="client-features-empty-state">
              <Building2 className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Vælg en klient til venstre for at se og administrere deres platforms-features.
              </p>
            </div>
          ) : loadingFeatures ? (
            <div className="text-center py-10 text-sm text-slate-500">
              <Loader2 className="w-4 h-4 inline animate-spin mr-1" />Henter features…
            </div>
          ) : (
            <div className="space-y-4" data-testid="client-features-form">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">Klient</p>
                <p className="text-lg font-bold text-slate-800 dark:text-slate-100">{selectedCompany?.name || "-"}</p>
                <p className="text-[10px] text-slate-400">{selectedId}</p>
              </div>

              <table className="w-full border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/50 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-3 py-2 text-left font-bold">Feature</th>
                    <th className="px-3 py-2 text-left font-bold">Beskrivelse</th>
                    <th className="px-3 py-2 text-left font-bold">Sidst ændret</th>
                    <th className="px-3 py-2 text-right font-bold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                  {features.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-6 text-center italic text-slate-500">
                        Ingen features tilgængelige.
                      </td>
                    </tr>
                  ) : features.map(f => {
                    const effective = f.key in dirty ? dirty[f.key] : !!f.enabled;
                    const isDirty = f.key in dirty;
                    // Fase 15.41: Pretty-print feature-nøgler. Tilføj nye keys
                    // her hvis fremtidige features har snake_case eller
                    // forkortelser der bør vises pænt i super-admin's UI.
                    const FEATURE_DISPLAY_NAMES = {
                      estimate: "Estimat",
                      loes_afhentning: "Løs afhentning",
                    };
                    const prettyName = FEATURE_DISPLAY_NAMES[f.key] || (f.key.charAt(0).toUpperCase() + f.key.slice(1));
                    return (
                      <tr key={f.key} className={isDirty ? "bg-amber-50/60 dark:bg-amber-900/10" : ""} data-testid={`client-features-row-${f.key}`}>
                        <td className="px-3 py-2.5 font-bold text-slate-800 dark:text-slate-200">
                          {prettyName}
                          {isDirty && <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-300 font-normal">(ugemt)</span>}
                        </td>
                        <td className="px-3 py-2.5 text-slate-600 dark:text-slate-400 text-xs max-w-md">{f.description || "-"}</td>
                        <td className="px-3 py-2.5 text-xs text-slate-500">
                          {f.updated_at ? (
                            <>
                              <div data-testid={`client-features-updated-at-${f.key}`}>{new Date(f.updated_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</div>
                              <div className="text-[10px] text-slate-400" data-testid={`client-features-updated-by-${f.key}`}>{f.updated_by || "-"}</div>
                            </>
                          ) : (
                            <span className="italic">aldrig ændret</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={effective}
                            onClick={() => toggleLocal(f.key)}
                            disabled={saving}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400 ${
                              effective ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"
                            } ${saving ? "opacity-50 cursor-not-allowed" : ""}`}
                            data-testid={`client-features-toggle-${f.key}`}
                          >
                            <span
                              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                                effective ? "translate-x-5" : "translate-x-1"
                              }`}
                            />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="flex items-center justify-between gap-2 pt-2">
                <p className="text-xs text-slate-500">
                  {hasDirty
                    ? <><span className="font-bold text-amber-600 dark:text-amber-300">{Object.keys(dirty).length}</span> ugemt {Object.keys(dirty).length === 1 ? "ændring" : "ændringer"}</>
                    : "Ingen ugemte ændringer"}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={onReset}
                    disabled={!hasDirty || saving}
                    className="px-3 py-1.5 text-sm font-bold rounded-md border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    data-testid="client-features-reset-btn"
                  >
                    Annuller
                  </button>
                  <button
                    type="button"
                    onClick={onSave}
                    disabled={!hasDirty || saving}
                    className="px-4 py-1.5 text-sm font-bold rounded-md bg-amber-500 hover:bg-amber-600 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                    data-testid="client-features-save-btn"
                  >
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Gem ændringer
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* ============== Fase 16: Retention Policy Panel ============== */
function RetentionPolicyPanel() {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get(`${API}/superadmin/retention-policies`);
      setCompanies(resp.data?.companies || []);
    } catch (e) {
      toast.error(formatApiError(e) || "Kunne ikke hente kunder");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);

  const saveRetention = async (companyId) => {
    const days = parseInt(draft, 10);
    if (!Number.isFinite(days) || days < 30 || days > 36500) {
      toast.error("Indtast et tal mellem 30 og 36500 dage");
      return;
    }
    try {
      await axios.put(`${API}/superadmin/companies/${companyId}/retention-policy`, {
        receipt_retention_days: days,
      });
      toast.success("Opbevaringsperiode opdateret");
      setCompanies((prev) => prev.map((c) => c.id === companyId ? { ...c, receipt_retention_days: days } : c));
      setEditingId(null);
      setDraft("");
    } catch (e) {
      toast.error(formatApiError(e) || "Kunne ikke gemme");
    }
  };

  const presets = [
    { days: 365, label: "1 år" },
    { days: 1095, label: "3 år (anbefalet)" },
    { days: 2555, label: "7 år (bogføringslov)" },
    { days: 3650, label: "10 år" },
  ];

  const filtered = companies.filter(c =>
    !search.trim() ||
    c.name?.toLowerCase().includes(search.toLowerCase()) ||
    c.customer_id?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <section data-testid="retention-policy-panel" className="space-y-6">
      <div className="bg-gradient-to-r from-emerald-50 to-blue-50 dark:from-emerald-950/30 dark:to-blue-950/30 rounded-xl p-5 border border-emerald-200 dark:border-emerald-800">
        <h2 className="font-heading font-bold text-xl flex items-center gap-2 mb-2">
          <Archive className="w-6 h-6 text-emerald-600" />
          Administrer dataopbevaring
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Sæt opbevaringsperioden for kvitteringsbilleder pr. kunde. Når en kvittering bliver ældre
          end den valgte periode, slettes den automatisk (samme dag i Europe/Copenhagen).
          <br />
          <strong>Standard:</strong> 1095 dage (3 år) - matcher dansk regnskabsstandard.
        </p>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow p-4">
        <div className="flex items-center gap-2 mb-3">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Søg kunde…"
            className="flex-1 px-2 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
            data-testid="retention-search-input"
          />
        </div>

        {loading ? (
          <div className="py-12 text-center text-slate-500">
            <Loader2 className="w-6 h-6 inline animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 dark:border-slate-700">
                  <th className="py-2 pr-3">Kunde</th>
                  <th className="py-2 pr-3">Kunde-ID</th>
                  <th className="py-2 pr-3 text-right">Opbevaring (dage)</th>
                  <th className="py-2 pr-3 text-right">≈</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id} className="border-b border-slate-100 dark:border-slate-700" data-testid={`retention-row-${c.id}`}>
                    <td className="py-2 pr-3 font-semibold">{c.name}</td>
                    <td className="py-2 pr-3 font-mono text-xs text-slate-500">{c.customer_id || "-"}</td>
                    <td className="py-2 pr-3 text-right">
                      {editingId === c.id ? (
                        <input
                          type="number"
                          min="30"
                          max="36500"
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          className="w-24 px-2 py-1 text-right rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                          autoFocus
                          data-testid={`retention-input-${c.id}`}
                        />
                      ) : (
                        <span className="font-mono font-bold" data-testid={`retention-days-${c.id}`}>{c.receipt_retention_days || 1095}</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right text-xs text-slate-500">
                      {(((editingId === c.id ? parseInt(draft, 10) : c.receipt_retention_days) || 1095) / 365).toFixed(1)} år
                    </td>
                    <td className="py-2 text-right">
                      {editingId === c.id ? (
                        <div className="flex items-center justify-end gap-1">
                          {presets.map(p => (
                            <button
                              key={p.days}
                              onClick={() => setDraft(String(p.days))}
                              className="px-1.5 py-0.5 text-[10px] rounded bg-slate-100 dark:bg-slate-700 hover:bg-emerald-100 dark:hover:bg-emerald-900/30"
                              data-testid={`retention-preset-${c.id}-${p.days}`}
                              title={`Sæt til ${p.label}`}
                            >
                              {p.label}
                            </button>
                          ))}
                          <button
                            onClick={() => saveRetention(c.id)}
                            className="px-2 py-1 rounded bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700"
                            data-testid={`retention-save-${c.id}`}
                          >
                            <Check className="w-3 h-3 inline" /> Gem
                          </button>
                          <button
                            onClick={() => { setEditingId(null); setDraft(""); }}
                            className="px-2 py-1 rounded bg-slate-200 dark:bg-slate-700 text-xs"
                            data-testid={`retention-cancel-${c.id}`}
                          >
                            <X className="w-3 h-3 inline" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => { setEditingId(c.id); setDraft(String(c.receipt_retention_days || 1095)); }}
                          className="px-3 py-1 rounded bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700"
                          data-testid={`retention-edit-${c.id}`}
                        >
                          <Edit2 className="w-3 h-3 inline mr-1" /> Rediger
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-500 italic">
                      Ingen kunder matcher søgningen.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
