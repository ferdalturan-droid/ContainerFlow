/* ============================================================
   excelExport.js  -  Single-sheet, professional Excel rapporter
   ============================================================
   Brugerkrav 2026-06-15: Excel-eksporten skal IKKE være opdelt
   i flere ark. Alt skal være på ÉT ark, med klar layout, totals,
   farver, borders, frozen header og auto-filter - så en kunde
   kan åbne filen direkte i Excel/Numbers/LibreOffice og forstå
   rapporten uden at klikke på faner.

   Implementeret med ExcelJS (fuld styling-support i browseren)
   + file-saver til pålidelig download i Emergent-iframen.
*/

import ExcelJS from "exceljs";
import { saveAs } from "file-saver";

/* ---------------- Farver (corporate palette) ---------------- */
const C = {
  brand: "FF1E3A8A",       // brand-blå (titel-baggrund)
  brandLight: "FFDCE7FA",  // sektionsoverskrift-baggrund
  headerText: "FFFFFFFF",
  zebra: "FFF7FAFC",       // hver anden datarække
  total: "FFE0E7FF",       // totals-baggrund
  border: "FFB6C6E5",
  textMuted: "FF64748B",
};

/* ---------------- Helpers ---------------- */
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const fmt = {
  int: "#,##0",
  weight: '#,##0" kg"',
  pct: "0.0%",
  date: "yyyy-mm-dd",
};

const colWidths = {
  S: 12, M: 18, L: 28, XL: 38,
};

function addBorder(cell, color = C.border) {
  cell.border = {
    top: { style: "thin", color: { argb: color } },
    left: { style: "thin", color: { argb: color } },
    bottom: { style: "thin", color: { argb: color } },
    right: { style: "thin", color: { argb: color } },
  };
}

function sectionHeader(ws, row, span, label) {
  ws.mergeCells(row, 1, row, span);
  const cell = ws.getCell(row, 1);
  cell.value = label;
  cell.font = { bold: true, size: 13, color: { argb: C.brand } };
  cell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
  cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: C.brandLight } };
  ws.getRow(row).height = 24;
}

function tableHeader(ws, row, headers) {
  headers.forEach((h, i) => {
    const cell = ws.getCell(row, i + 1);
    cell.value = h;
    cell.font = { bold: true, color: { argb: C.headerText }, size: 11 };
    cell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: C.brand } };
    addBorder(cell, C.brand);
  });
  ws.getRow(row).height = 22;
}

function totalRow(ws, row, values, span) {
  values.forEach((v, i) => {
    const cell = ws.getCell(row, i + 1);
    cell.value = v;
    cell.font = { bold: true, size: 11 };
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: C.total } };
    addBorder(cell);
  });
  // Hvis kun første kolonne har label, merge resten frem til total-kolonnen
  ws.getRow(row).height = 20;
}

function dataRow(ws, row, values, zebra = false) {
  values.forEach((v, i) => {
    const cell = ws.getCell(row, i + 1);
    cell.value = v;
    cell.alignment = { vertical: "middle", indent: i === 0 ? 1 : 0 };
    if (zebra) cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: C.zebra } };
    addBorder(cell);
  });
  ws.getRow(row).height = 18;
}

/* ============================================================
   buildSingleSheetReport
   data: rapport-payload fra /api/org/reports/orders (+ multi)
   options:
     - title:   string  (vises i title-banner)
     - subtitle: string (under title - fx "Lokation X · Periode...")
     - includeByLocation: bool - hvis true tilføjes "Pr. lokation"-blok
                           (CA-rapport har by_location, LA har ikke)
     - filename: string
   ============================================================ */
export async function exportReportXLSX({
  data,
  title = "ContainerFlow Rapport",
  subtitle = "",
  includeByLocation = false,
  filename = "rapport.xlsx",
}) {
  if (!data) throw new Error("data mangler");

  const wb = new ExcelJS.Workbook();
  wb.creator = "ContainerFlow";
  wb.created = new Date();
  wb.modified = new Date();
  wb.properties = {
    title,
    subject: "Bestillings-rapport",
    keywords: "containerflow, bestillinger, rapport",
  };

  const ws = wb.addWorksheet("Rapport", {
    views: [{ state: "frozen", ySplit: 6 }], // frys de første 6 rækker (banner + KPI'er)
    pageSetup: { paperSize: 9, orientation: "landscape", fitToPage: true },
  });

  // Bredde-skema (8 kolonner - tilstrækkeligt til alle sektioner)
  ws.columns = [
    { width: colWidths.XL }, // 1
    { width: colWidths.M },  // 2
    { width: colWidths.M },  // 3
    { width: colWidths.M },  // 4
    { width: colWidths.M },  // 5
    { width: colWidths.M },  // 6
    { width: colWidths.M },  // 7
    { width: colWidths.M },  // 8
  ];

  /* --------- Title-banner --------- */
  ws.mergeCells("A1:H1");
  const t = ws.getCell("A1");
  t.value = title;
  t.font = { bold: true, size: 18, color: { argb: C.headerText } };
  t.alignment = { vertical: "middle", indent: 1 };
  t.fill = { type: "pattern", pattern: "solid", fgColor: { argb: C.brand } };
  ws.getRow(1).height = 34;

  if (subtitle) {
    ws.mergeCells("A2:H2");
    const s = ws.getCell("A2");
    s.value = subtitle;
    s.font = { italic: true, size: 11, color: { argb: C.textMuted } };
    s.alignment = { vertical: "middle", indent: 1 };
    ws.getRow(2).height = 18;
  }

  /* --------- Periode + nøglemetrikker (KPI's) ---------
   * Brugerkrav 2026-06-15 (runde 9): "Afventer i alt - live" omdøbt til
   * "Åbne bestillinger lige nu" (klar betydning). Tilføjet 4 ekstra KPI'er
   * så rapporten er meget federe: total vægt, antal unikke materialer,
   * gennemsnitlig vægt og top-materiale.
   */
  const totalWeight = (data.by_material || []).reduce((s, m) => s + num(m.weight), 0);
  const uniqueMaterials = (data.by_material || []).length;
  const uniqueEmployees = (data.by_employee || []).length;
  const avgWeight = num(data.total_orders) > 0 ? totalWeight / num(data.total_orders) : 0;
  const topMaterial = (data.by_material || [])
    .slice()
    .sort((a, b) => num(b.count) - num(a.count))[0];
  const topEmployee = (data.by_employee || [])
    .slice()
    .sort((a, b) => num(b.count) - num(a.count))[0];
  const busiestBucket = (data.pattern || [])
    .slice()
    .sort((a, b) => num(b.count) - num(a.count))[0];

  // Brugerkrav 2026-06-15: 8 KPI'er fordelt på 2 rækker (4 + 4)
  const kpisRow1 = [
    { label: "Bestillinger i perioden", value: num(data.total_orders), fmt: fmt.int, accent: "FF2563EB" },
    { label: "Afventer (i perioden)", value: num(data.pending_in_period), fmt: fmt.int, accent: "FFF59E0B" },
    { label: "Haste bestillinger", value: num(data.urgent_count), fmt: fmt.int, accent: "FFEF4444" },
    { label: "Værkstedsbesøg", value: num(data.workshop_count), fmt: fmt.int, accent: "FF10B981" },
  ];
  const kpisRow2 = [
    { label: "Samlet vægt", value: totalWeight, fmt: fmt.weight, accent: "FF7C3AED" },
    { label: "Gns. vægt pr. ordre", value: Math.round(avgWeight), fmt: fmt.weight, accent: "FFEC4899" },
    { label: "Samlet CO2", value: num(data.total_co2_kg), fmt: '#,##0.000" kg"', accent: "FF059669" },
    { label: "Antal medarbejdere aktive", value: uniqueEmployees, fmt: fmt.int, accent: "FF14B8A6" },
  ];

  const renderKpiRow = (kpis, labelRow, valueRow) => {
    kpis.forEach((k, i) => {
      const startCol = i * 2 + 1;
      ws.mergeCells(labelRow, startCol, labelRow, startCol + 1);
      const c1 = ws.getCell(labelRow, startCol);
      c1.value = k.label;
      c1.font = { bold: true, size: 9, color: { argb: C.textMuted } };
      c1.alignment = { horizontal: "left", vertical: "middle", indent: 1 };
      c1.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF1F5F9" } };

      ws.mergeCells(valueRow, startCol, valueRow, startCol + 1);
      const c2 = ws.getCell(valueRow, startCol);
      c2.value = k.value;
      c2.numFmt = k.fmt;
      c2.font = { bold: true, size: 18, color: { argb: k.accent } };
      c2.alignment = { horizontal: "left", vertical: "middle", indent: 1 };
      c2.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF8FAFC" } };
    });
    ws.getRow(labelRow).height = 18;
    ws.getRow(valueRow).height = 32;
  };
  renderKpiRow(kpisRow1, 4, 5);
  renderKpiRow(kpisRow2, 6, 7);

  /* --------- Højdepunkter (highlights-bar) --------- */
  // Tre side-by-side "winner" celler - Top materiale + Top medarbejder + Travleste periode
  const highlights = [
    {
      label: "Top materiale",
      value: topMaterial
        ? `${topMaterial.name} (${num(topMaterial.count)} ordrer · ${num(topMaterial.weight).toLocaleString("da-DK")} kg)`
        : "-",
    },
    {
      label: "Top medarbejder",
      value: topEmployee ? `${topEmployee.name} (${num(topEmployee.count)} ordrer)` : "-",
    },
    {
      label: "Travleste " + (({ hour: "time", day: "dag", week: "uge", month: "måned" })[data.granularity] || "periode"),
      value: busiestBucket ? `${busiestBucket.bucket} (${num(busiestBucket.count)} ordrer)` : "-",
    },
  ];
  highlights.forEach((h, i) => {
    const startCol = (i * 8) / 3 + 1;  // fordel over 8 kolonner
    // Brug fast ratio for simpel layout: 3 kolonner pr highlight (col 1-3, 4-6, 7-8)
  });
  // Simpler approach: hver highlight optager række 8 cell-spans of 3 cols
  // Col 1-3 = Top materiale, Col 4-6 = Top medarbejder, Col 7-8 = Travleste
  const spans = [[1, 3], [4, 6], [7, 8]];
  spans.forEach((sp, i) => {
    ws.mergeCells(8, sp[0], 8, sp[1]);
    const c = ws.getCell(8, sp[0]);
    c.value = `${highlights[i].label}: ${highlights[i].value}`;
    c.font = { bold: true, size: 10, color: { argb: "FF334155" } };
    c.alignment = { horizontal: "left", vertical: "middle", indent: 1 };
    c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFFEF3C7" } };
  });
  ws.getRow(8).height = 22;

  // Tom række
  let cursor = 10;
  // Opdater frozen-views til at låse op til efter KPI-blokken
  ws.views = [{ state: "frozen", ySplit: 9 }];

  /* --------- Pr. lokation (KUN customer-admin) --------- */
  if (includeByLocation && (data.by_location || []).length > 0) {
    sectionHeader(ws, cursor++, 6, "Pr. lokation");
    tableHeader(ws, cursor++, ["Lokation", "Kode", "Bestillinger", "Afventer", "Vægt", "CO2 (kg)"]);
    const startData = cursor;
    let totalC = 0, totalP = 0, totalW = 0, totalCO2 = 0;
    (data.by_location || []).forEach((l, idx) => {
      const c = num(l.count), p = num(l.pending), w = num(l.weight), co2 = num(l.co2_kg);
      totalC += c; totalP += p; totalW += w; totalCO2 += co2;
      dataRow(ws, cursor, [
        l.location_name || "(ukendt)",
        l.location_code || "",
        c, p, w, co2,
      ], idx % 2 === 1);
      ws.getCell(cursor, 3).numFmt = fmt.int;
      ws.getCell(cursor, 4).numFmt = fmt.int;
      ws.getCell(cursor, 5).numFmt = fmt.weight;
      ws.getCell(cursor, 6).numFmt = '#,##0.000" kg"';
      cursor++;
    });
    totalRow(ws, cursor++, ["I alt", "", totalC, totalP, totalW, totalCO2], 6);
    ws.getCell(cursor - 1, 3).numFmt = fmt.int;
    ws.getCell(cursor - 1, 4).numFmt = fmt.int;
    ws.getCell(cursor - 1, 5).numFmt = fmt.weight;
    ws.getCell(cursor - 1, 6).numFmt = '#,##0.000" kg"';
    // AutoFilter for denne tabel
    ws.autoFilter = {
      from: { row: startData - 1, column: 1 },
      to:   { row: cursor - 2,    column: 6 },
    };
    cursor++; // tom række
  }

  /* --------- Fase 9 (2026-06-17): Pr. CO2-type --------- */
  if ((data.by_co2_type || []).length > 0) {
    sectionHeader(ws, cursor++, 5, "CO2-aftryk pr. materiale");
    tableHeader(ws, cursor++, ["CO2-type", "Faktor (kg/ton)", "Antal", "Vægt (kg)", "CO2 (kg)"]);
    let totalCnt = 0, totalKg = 0, totalCO2 = 0;
    (data.by_co2_type || []).forEach((t, idx) => {
      const cnt = num(t.count), kg = num(t.weight_kg), co2 = num(t.co2_kg);
      totalCnt += cnt; totalKg += kg; totalCO2 += co2;
      dataRow(ws, cursor, [t.name || "(ukendt)", num(t.factor), cnt, kg, co2], idx % 2 === 1);
      ws.getCell(cursor, 2).numFmt = "#,##0.0";
      ws.getCell(cursor, 3).numFmt = fmt.int;
      ws.getCell(cursor, 4).numFmt = fmt.weight;
      ws.getCell(cursor, 5).numFmt = '#,##0.000" kg"';
      cursor++;
    });
    totalRow(ws, cursor++, ["I alt", "", totalCnt, totalKg, totalCO2], 5);
    ws.getCell(cursor - 1, 3).numFmt = fmt.int;
    ws.getCell(cursor - 1, 4).numFmt = fmt.weight;
    ws.getCell(cursor - 1, 5).numFmt = '#,##0.000" kg"';
    cursor++;
  }

  /* --------- Pr. materiale --------- */
  if ((data.by_material || []).length > 0) {
    sectionHeader(ws, cursor++, 4, "Pr. materiale");
    tableHeader(ws, cursor++, ["Materiale", "Antal", "Vægt", "Andel"]);
    const totalCount = (data.by_material || []).reduce((s, m) => s + num(m.count), 0) || 1;
    let totalC = 0, totalW = 0;
    (data.by_material || []).forEach((m, idx) => {
      const c = num(m.count), w = num(m.weight);
      totalC += c; totalW += w;
      dataRow(ws, cursor, [m.name || "(ukendt)", c, w, c / totalCount], idx % 2 === 1);
      ws.getCell(cursor, 2).numFmt = fmt.int;
      ws.getCell(cursor, 3).numFmt = fmt.weight;
      ws.getCell(cursor, 4).numFmt = fmt.pct;
      cursor++;
    });
    totalRow(ws, cursor++, ["I alt", totalC, totalW, 1], 4);
    ws.getCell(cursor - 1, 2).numFmt = fmt.int;
    ws.getCell(cursor - 1, 3).numFmt = fmt.weight;
    ws.getCell(cursor - 1, 4).numFmt = fmt.pct;
    cursor++;
  }

  /* --------- Pr. medarbejder --------- */
  if ((data.by_employee || []).length > 0) {
    sectionHeader(ws, cursor++, 3, "Pr. medarbejder");
    tableHeader(ws, cursor++, ["Medarbejder", "Antal", "Andel"]);
    const totalCount = (data.by_employee || []).reduce((s, e) => s + num(e.count), 0) || 1;
    let total = 0;
    (data.by_employee || []).forEach((e, idx) => {
      const c = num(e.count);
      total += c;
      dataRow(ws, cursor, [e.name || "(ukendt)", c, c / totalCount], idx % 2 === 1);
      ws.getCell(cursor, 2).numFmt = fmt.int;
      ws.getCell(cursor, 3).numFmt = fmt.pct;
      cursor++;
    });
    totalRow(ws, cursor++, ["I alt", total, 1], 3);
    ws.getCell(cursor - 1, 2).numFmt = fmt.int;
    ws.getCell(cursor - 1, 3).numFmt = fmt.pct;
    cursor++;
  }

  /* --------- Tidsmønster --------- */
  if ((data.pattern || []).length > 0) {
    const granLabel = ({ hour: "Time", day: "Dag", week: "Uge", month: "Måned" })[data.granularity] || "Periode";
    sectionHeader(ws, cursor++, 3, `Tidsmønster (${granLabel.toLowerCase()}-niveau)`);
    tableHeader(ws, cursor++, [granLabel, "Antal", "Andel"]);
    const totalCount = (data.pattern || []).reduce((s, p) => s + num(p.count), 0) || 1;
    let total = 0;
    (data.pattern || []).forEach((p, idx) => {
      const c = num(p.count);
      total += c;
      dataRow(ws, cursor, [p.bucket || "", c, c / totalCount], idx % 2 === 1);
      ws.getCell(cursor, 2).numFmt = fmt.int;
      ws.getCell(cursor, 3).numFmt = fmt.pct;
      cursor++;
    });
    totalRow(ws, cursor++, ["I alt", total, 1], 3);
    ws.getCell(cursor - 1, 2).numFmt = fmt.int;
    ws.getCell(cursor - 1, 3).numFmt = fmt.pct;
    cursor++;
  }

  /* --------- Afventende bestillinger (top-100) --------- */
  if ((data.pending_orders || []).length > 0) {
    sectionHeader(ws, cursor++, 7, `Afventende bestillinger (${(data.pending_orders || []).length} stk)`);
    tableHeader(ws, cursor++, [
      "Bestillingsdato", "Lokation", "Materiale", "Container-nummer",
      "Vægt", "Bestilt af", "Status",
    ]);
    const startData = cursor;
    (data.pending_orders || []).forEach((o, idx) => {
      dataRow(ws, cursor, [
        o.order_date || "",
        o.location_code || "",
        o.material || "",
        o.container_number || o.container_no || "",
        num(o.weight),
        o.created_by_name || o.created_by_email || "",
        o.status_label || "afventer",
      ], idx % 2 === 1);
      ws.getCell(cursor, 1).numFmt = fmt.date;
      ws.getCell(cursor, 5).numFmt = fmt.weight;
      cursor++;
    });
    // AutoFilter for de afventende
    ws.autoFilter = {
      from: { row: startData - 1, column: 1 },
      to:   { row: cursor - 1,    column: 7 },
    };
    cursor++;
  }

  /* --------- Footer --------- */
  ws.mergeCells(cursor, 1, cursor, 8);
  const foot = ws.getCell(cursor, 1);
  foot.value = `Genereret ${new Date().toLocaleString("da-DK")} · ContainerFlow · Periode ${data.start} til ${data.end}`;
  foot.font = { italic: true, size: 9, color: { argb: C.textMuted } };
  foot.alignment = { horizontal: "right", vertical: "middle", indent: 1 };
  ws.getRow(cursor).height = 16;

  /* --------- Skriv fil --------- */
  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  try {
    saveAs(blob, filename);
    return true;
  } catch (_) {
    // Fallback via manuel anchor
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.style.display = "none";
    document.body.appendChild(a); a.click();
    setTimeout(() => {
      try { document.body.removeChild(a); } catch (__) { /* allerede væk */ }
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    }, 100);
    return true;
  }
}
