// ReceiptScanner.jsx - Fase 17.5 (2026-02-27)
// PREVIEW-ONLY modal. INGEN file-input herinde. Label + input lever
// i MobileTourPanel (App.js) som permanent sibling - det er det
// eneste der virker pålideligt på iOS Safari (1-tap til kameraet).
//
// Modal'en unmount'es ALDRIG (CSS visibility).

import React from "react";
import { X, Camera, CheckCircle2, RefreshCw, Save } from "lucide-react";

export default function ReceiptScanner({
  open,
  onClose,
  onConfirm,
  onRetake,
  imageBase64 = "",
  previewDataUrl = "",
  sizeKB = 0,
  isLoose = false,
  title = "Scan kvittering",
}) {
  const handleConfirm = () => {
    if (!imageBase64) return;
    onConfirm && onConfirm({
      imageBase64,
      previewDataUrl,
      contentType: "image/jpeg",
    });
  };

  return (
    <div
      className="fixed inset-0 z-[1000] bg-black/70 backdrop-blur-sm flex items-start sm:items-center justify-center overflow-y-auto p-2 sm:p-4 transition-opacity duration-150"
      style={{
        visibility: open ? 'visible' : 'hidden',
        pointerEvents: open ? 'auto' : 'none'
      }}
      data-testid="receipt-scanner-modal"
      aria-hidden={!open}
    >
      <div
        className="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl flex flex-col my-auto"
        style={{ maxHeight: "calc(100dvh - 16px)" }}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 sticky top-0 bg-white dark:bg-slate-900 z-10 rounded-t-2xl">
          <h3 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Camera className="w-5 h-5 text-emerald-600" />
            {title}
            {isLoose && (
              <span className="ml-1 text-[10px] font-bold uppercase tracking-wide bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 px-1.5 py-0.5 rounded">
                Løs
              </span>
            )}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
            data-testid="receipt-scanner-close-btn"
            aria-label="Luk scanner"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-4 py-2 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700 text-[11px] text-slate-700 dark:text-slate-300 flex items-center justify-between flex-wrap gap-1">
          <span><strong>Status:</strong> {previewDataUrl ? "klar til bekræftelse" : "venter på billede"}</span>
          {sizeKB > 0 && (
            <span className="text-emerald-700 dark:text-emerald-300 font-semibold">
              {sizeKB} KB
            </span>
          )}
        </div>

        <div className="overflow-y-auto p-4 space-y-3 flex-1">
          {previewDataUrl && (
            <div className="space-y-3" data-testid="receipt-scanner-preview">
              <img
                src={previewDataUrl}
                alt="Scannet kvittering"
                className="w-full max-h-80 object-contain rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
                data-testid="receipt-scanner-preview-img"
              />

              <div className="px-3 py-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-100 text-sm flex items-start gap-2">
                <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0 text-emerald-600" />
                <div>
                  <div className="font-semibold">Ser billedet rigtigt ud?</div>
                  <div className="text-xs mt-0.5 opacity-90">
                    Tryk &quot;Brug billede&quot; - kvitteringen vedhæftes til turen.
                    Vægten indtaster du på turen og uploades sammen.
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={onRetake}
                  className="flex-1 px-3 py-3 rounded-lg border-2 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-semibold flex items-center justify-center gap-1.5 hover:bg-slate-50 dark:hover:bg-slate-800 text-sm"
                  data-testid="receipt-scanner-retake-btn"
                >
                  <RefreshCw className="w-4 h-4" /> Nyt billede
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={!imageBase64}
                  className="flex-1 px-3 py-3 rounded-lg bg-emerald-600 text-white font-bold flex items-center justify-center gap-1.5 hover:bg-emerald-700 disabled:opacity-50 text-sm"
                  data-testid="receipt-scanner-confirm-btn"
                >
                  <Save className="w-4 h-4" /> Brug billede
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
