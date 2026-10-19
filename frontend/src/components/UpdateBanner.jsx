import React, { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

/**
 * 2026-10-19: "Ny version - tryk for at opdatere".
 * En side der står åben hele dagen (fx chaufførens telefon) kører den kode
 * den blev indlæst med - også efter en opdatering af appen. Hvert 5. minut og
 * når appen kommer i forgrunden, ser vi om serveren har en nyere version.
 */
const scriptName = (text) => (String(text || "").match(/main\.[a-z0-9]+\.js/) || [])[0] || "";

export default function UpdateBanner() {
  const [stale, setStale] = useState(false);
  useEffect(() => {
    const mine = scriptName(Array.from(document.scripts).map(s => s.src).join(" "));
    if (!mine) return undefined; // udviklingsserver - intet at sammenligne med
    let off = false;
    const check = async () => {
      if (document.hidden) return;
      try {
        const res = await fetch(`/?v=${Date.now()}`, { cache: "no-store" });
        const live = scriptName(await res.text());
        if (!off && live && live !== mine) setStale(true);
      } catch (_) { /* offline - prøv igen senere */ }
    };
    const iv = setInterval(check, 5 * 60 * 1000);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      off = true;
      clearInterval(iv);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
    };
  }, []);
  if (!stale) return null;
  return (
    <button type="button" onClick={() => window.location.reload()} data-testid="update-banner"
      className="fixed left-1/2 -translate-x-1/2 z-[200] max-w-[92vw] px-4 py-2.5 rounded-full bg-slate-900 text-white text-sm font-semibold shadow-xl inline-flex items-center gap-2"
      style={{ top: "calc(env(safe-area-inset-top) + 10px)" }}>
      <RefreshCw className="w-4 h-4 shrink-0" /> Der er en ny version af ContainerFlow · Tryk for at opdatere
    </button>
  );
}
