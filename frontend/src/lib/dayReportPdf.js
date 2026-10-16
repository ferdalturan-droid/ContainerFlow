import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

/**
 * Dagrapport-PDF (2026-10-16). Én fælles bygger for chaufførens egen PDF
 * ("Afslut dag" + manuel download) og logistik admins Arkiv. Data kommer fra
 * /driver/day-report eller /admin/day-report/{id} og bygges altid friskt.
 */

const TASK = {
  normal: "Afhentning", flyt: "Byt container", vaerksted: "Til værksted",
  afhent_vaerksted: "Hent fra værksted", loes_afhentning: "Løs afhentning",
};
const INK = [15, 23, 42];
const MUTED = [100, 116, 139];
const LINE = [226, 232, 240];
const ACCENT = [234, 88, 12];

export const fmtMinutes = (m) => {
  if (m == null || Number.isNaN(m)) return "-";
  const v = Math.round(m);
  return `${Math.floor(v / 60)}t ${String(v % 60).padStart(2, "0")}m`;
};

const longDate = (d) => {
  try {
    return new Date(d + "T00:00:00").toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  } catch (_) { return d; }
};

export const dayReportFileName = (kind, date, driverName) =>
  `${kind}_${(date || "").split("-").reverse().join(".")}_${driverName || "rapport"}.pdf`;

export function buildDayReportPdf({ title = "Dagrapport", report, driverName, vehicleReg, date, notes }) {
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 12;
  const ts = report?.time_summary || {};
  const tours = report?.tours || [];
  const slices = [...(ts.work_slices || []), ...(ts.pause_slices || [])]
    .sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""));
  const totalWeight = tours.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  const places = [...new Set(tours.map(t => t.plads).filter(Boolean))].join(", ") || "-";
  const name = driverName || report?.driver_name || "";

  // ----- Header
  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.setTextColor(...INK);
  doc.text(title, M, 18);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.setTextColor(...MUTED);
  doc.text(`${name}  ·  ${longDate(date)}`, M, 25);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(...INK);
  const flowW = doc.getTextWidth("Flow");
  doc.text("Container", W - M - flowW, 17, { align: "right" });
  doc.setTextColor(...ACCENT);
  doc.text("Flow", W - M, 17, { align: "right" });
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(`Genereret ${new Date().toLocaleString("da-DK")}`, W - M, 23, { align: "right" });
  doc.setDrawColor(...LINE);
  doc.setLineWidth(0.4);
  doc.line(M, 30, W - M, 30);

  // ----- Summary tiles
  const tiles = [
    ["Første start", ts.start || "-"],
    ["Sidste slut", ts.end ? `${ts.end}${ts.open ? " (i gang)" : ""}` : (ts.open ? "i gang" : "-")],
    ["Arbejdstid", ts.any ? fmtMinutes(ts.work_min) : "-"],
    ["Pause", ts.any ? fmtMinutes(ts.pause_min) : "-"],
    ["Ture", String(tours.length)],
    ["Vægt", `${totalWeight.toLocaleString("da-DK")} kg`],
  ];
  const gap = 4;
  const tw = (W - 2 * M - gap * (tiles.length - 1)) / tiles.length;
  tiles.forEach(([k, v], i) => {
    const x = M + i * (tw + gap);
    doc.setFillColor(248, 250, 252);
    doc.setDrawColor(...LINE);
    doc.roundedRect(x, 35, tw, 17, 2, 2, "FD");
    doc.setFontSize(7);
    doc.setTextColor(...MUTED);
    doc.text(k.toUpperCase(), x + 3.5, 40.5);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.setTextColor(...INK);
    doc.text(v, x + 3.5, 48);
    doc.setFont("helvetica", "normal");
  });
  doc.setFontSize(8.5);
  doc.setTextColor(...MUTED);
  doc.text(`Vogn nr.: ${vehicleReg || "-"}     Lokationer: ${places}`, M, 58);

  const tableBase = {
    theme: "plain",
    margin: { left: M, right: M, bottom: 16 },
    styles: { font: "helvetica", fontSize: 8.5, textColor: INK, cellPadding: { top: 2, bottom: 2, left: 2.5, right: 2.5 }, lineColor: LINE, lineWidth: { bottom: 0.2 } },
    headStyles: { fontStyle: "bold", fontSize: 7, textColor: MUTED, fillColor: [248, 250, 252] },
    footStyles: { fontStyle: "bold", fillColor: [248, 250, 252], textColor: INK },
  };
  const section = (text, y) => {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(...INK);
    doc.text(text, M, y);
    doc.setFont("helvetica", "normal");
  };

  // ----- Arbejdstid: every period
  let y = 67;
  section("Arbejdstid", y);
  if (slices.length === 0) {
    doc.setFontSize(9);
    doc.setTextColor(...MUTED);
    doc.text("Ingen stemplinger registreret denne dag.", M, y + 7);
    y += 14;
  } else {
    autoTable(doc, {
      ...tableBase,
      startY: y + 3,
      head: [["#", "Type", "Fra", "Til", "Varighed", "Bemærkning"]],
      body: slices.map((s, i) => [
        i + 1, s.slice_type === "pause" ? "Pause" : "Arbejde", s.start_time || "-",
        s.end_time || "i gang", fmtMinutes(s.duration_minutes),
        [s.manual ? "Manuel registrering" : "", s.reason || ""].filter(Boolean).join(": "),
      ]),
      foot: [["", "I alt", "", "", `Arbejde ${fmtMinutes(ts.work_min)}`,
        `Pause ${fmtMinutes(ts.pause_min)}${ts.gap_min ? `   ·   Ikke stemplet ${fmtMinutes(ts.gap_min)}` : ""}`]],
      columnStyles: { 0: { cellWidth: 10 }, 1: { cellWidth: 30 }, 2: { cellWidth: 22 }, 3: { cellWidth: 22 }, 4: { cellWidth: 40 } },
      didParseCell: (d) => {
        if (d.section === "body" && slices[d.row.index]?.slice_type === "pause") {
          d.cell.styles.fillColor = [255, 247, 237];
          if (d.column.index === 1) d.cell.styles.textColor = [194, 65, 12];
        }
        if (d.section === "body" && d.column.index === 1 && slices[d.row.index]?.slice_type !== "pause") {
          d.cell.styles.textColor = [21, 128, 61];
        }
      },
    });
    y = doc.lastAutoTable.finalY + 10;
  }

  // ----- Ture
  if (y > H - 40) { doc.addPage(); y = 18; }
  section(`Ture (${tours.length})`, y);
  if (tours.length === 0) {
    doc.setFontSize(9);
    doc.setTextColor(...MUTED);
    doc.text("Ingen afsluttede ture denne dag.", M, y + 7);
    y += 14;
  } else {
    const billing = (t) => {
      const b = t.billing || {};
      if (b.model === "hourly") return `Timepris · pause ${b.deduct_pause ? "fratrækkes" : "tæller med"}`;
      if (b.model === "fixed") return "Fast pris";
      if (b.model === "per_container") return "Pr. container";
      return "Ingen prisregel";
    };
    const billed = (t) => {
      const b = t.billing || {};
      if (b.model !== "hourly") return "-";
      return b.billable_min != null ? fmtMinutes(b.billable_min) : "Mangler tid";
    };
    const net = (t) => t.duration_min == null ? null : Math.max(0, t.duration_min - (t.pause_min || 0));
    autoTable(doc, {
      ...tableBase,
      startY: y + 3,
      head: [["#", "Tur", "Lokation", "Materiale", "Opgave", "Modtager", "Start", "Slut", "Varighed", "Pause i tur", "Netto", "Afregning", "Afregnet tid", "Hænger", "Vægt"]],
      body: tours.map((t, i) => [
        i + 1, `${t.tour_number || "-"}${t.billing?.corrected ? " *" : ""}`, t.plads || "-", t.fraction || "-",
        TASK[t.task_type] || t.task_type || "-", t.facility || "-", t.start_time || "-", t.end_time || "-",
        fmtMinutes(t.duration_min), t.pause_min ? fmtMinutes(t.pause_min) : "-", fmtMinutes(net(t)),
        billing(t), billed(t), t.used_trailer ? "Ja" : "Nej",
        t.weight ? `${Number(t.weight).toLocaleString("da-DK")} kg` : "-",
      ]),
      foot: [["", "", "", "", "", "I alt", "", "",
        fmtMinutes(tours.reduce((s, t) => s + (t.duration_min || 0), 0)),
        fmtMinutes(tours.reduce((s, t) => s + (t.pause_min || 0), 0)),
        fmtMinutes(tours.reduce((s, t) => s + (net(t) || 0), 0)), "",
        fmtMinutes(tours.reduce((s, t) => s + (t.billing?.model === "hourly" ? (t.billing.billable_min || 0) : 0), 0)),
        "", `${totalWeight.toLocaleString("da-DK")} kg`]],
      columnStyles: {
        0: { cellWidth: 7 }, 1: { cellWidth: 17 }, 6: { cellWidth: 14 }, 7: { cellWidth: 14 },
        8: { cellWidth: 17 }, 9: { cellWidth: 17 }, 10: { cellWidth: 16, fontStyle: "bold" },
        11: { cellWidth: 31 }, 12: { cellWidth: 19, fontStyle: "bold" }, 13: { cellWidth: 15 },
        14: { cellWidth: 19, halign: "right" },
      },
      didParseCell: (d) => {
        if (d.section === "body" && d.column.index === 9 && tours[d.row.index]?.pause_min) {
          d.cell.styles.textColor = [194, 65, 12];
        }
      },
    });
    y = doc.lastAutoTable.finalY + 6;
    const notesLines = [
      "Pause i tur = pause startet under \"Tid\" mens turen kørte (registreres kun ét sted). Netto = varighed minus pause i tur.",
      "Afregning følger firmaets prisregel for turen, herunder om pausen fratrækkes. Afregnet tid (timepris) er efter pausefradrag, afrunding og deling ved samtidige ture.",
    ];
    if (tours.some(t => t.billing?.corrected)) notesLines.push("* Turen er rettet efter godkendelse eller tilpasset af logistik admin.");
    doc.setFontSize(7.5);
    doc.setTextColor(...MUTED);
    notesLines.forEach((l, i) => doc.text(l, M, y + i * 4));
    y += notesLines.length * 4 + 4;
  }

  if (notes) {
    if (y > H - 30) { doc.addPage(); y = 18; }
    section("Bemærkninger", y);
    doc.setFontSize(9);
    doc.setTextColor(...INK);
    doc.text(doc.splitTextToSize(notes, W - 2 * M), M, y + 6);
  }

  const pages = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setDrawColor(...LINE);
    doc.line(M, H - 11, W - M, H - 11);
    doc.setFontSize(7.5);
    doc.setTextColor(...MUTED);
    doc.text(`ContainerFlow  ·  ${title}  ·  ${name}  ·  ${(date || "").split("-").reverse().join(".")}`, M, H - 6);
    doc.text(`Side ${i} af ${pages}`, W - M, H - 6, { align: "right" });
  }
  return doc;
}
