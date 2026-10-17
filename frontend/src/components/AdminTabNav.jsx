import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MoreHorizontal, ChevronDown, Check, Menu as MenuIcon, X } from "lucide-react";

/**
 * Fane-navigation til logistik admin (2026-10-16). Samme mønster som
 * Location Admin: de daglige faner står fremme, resten ligger i en lodret
 * "Mere"-menu (portal, så den ikke klippes af den vandrette scroll). På
 * mobil vises den aktive fane + en menu-knap der åbner en side-skuffe.
 */
export default function AdminTabNav({ tabs, moreTabs, active, onChange, badges = {}, title = "" }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [rect, setRect] = useState(null);
  const moreRef = useRef(null);
  const menuRef = useRef(null);
  const activeMore = moreTabs.find(t => t.id === active);
  const current = [...tabs, ...moreTabs].find(t => t.id === active) || tabs[0];

  useEffect(() => {
    if (!moreOpen) return;
    const update = () => moreRef.current && setRect(moreRef.current.getBoundingClientRect());
    update();
    const onDoc = (e) => {
      if (moreRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      setMoreOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [moreOpen]);

  const Badge = ({ id }) => badges[id] ? (
    <span className="ml-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold inline-flex items-center justify-center">{badges[id]}</span>
  ) : null;

  return (
    <>
      {/* Desktop */}
      <div className="hidden sm:block border-t border-slate-800">
        <div className="max-w-screen-2xl mx-auto px-8 flex gap-1 overflow-x-auto scrollbar-none items-stretch">
          {tabs.map(t => (
            <button key={t.id} onClick={() => onChange(t.id)} data-testid={t.testid || `admin-tab-${t.id}`}
              className={`px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 whitespace-nowrap border-b-2 transition-colors ${
                active === t.id ? "border-red-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"}`}>
              <t.icon className="w-4 h-4" /> {t.label}<Badge id={t.id} />
            </button>
          ))}
          {moreTabs.length > 0 && <button ref={moreRef} onClick={() => setMoreOpen(v => !v)} data-testid="admin-tab-more"
            aria-haspopup="menu" aria-expanded={moreOpen}
            className={`px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 whitespace-nowrap border-b-2 transition-colors ${
              activeMore ? "border-red-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"}`}>
            <MoreHorizontal className="w-4 h-4" /> {activeMore ? activeMore.label : "Mere"}
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${moreOpen ? "rotate-180" : ""}`} />
          </button>}
        </div>
      </div>

      {/* Mobil */}
      <div className="sm:hidden border-t border-slate-800 px-3 py-2 flex items-center gap-2" style={{ flexWrap: "nowrap" }}>
        <button onClick={() => setDrawer(true)} className="p-2 rounded-lg bg-slate-800/70 text-red-300" aria-label="Åbn menu" data-testid="admin-mobile-menu-btn">
          <MenuIcon className="w-5 h-5" />
        </button>
        {/* flexWrap inline: index.css har en gammel "header .flex { flex-wrap: wrap }" for mobil */}
        <div className="flex flex-nowrap gap-1 overflow-x-auto scrollbar-none flex-1 min-w-0" style={{ flexWrap: "nowrap" }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => onChange(t.id)}
              className={`shrink-0 whitespace-nowrap px-3 py-1.5 rounded-lg text-[13px] font-semibold inline-flex items-center gap-1 ${active === t.id ? "bg-white text-slate-900" : "text-slate-300"}`}>
              {t.label}<Badge id={t.id} />
            </button>
          ))}
          {activeMore && <span className="shrink-0 whitespace-nowrap px-3 py-1.5 rounded-lg text-[13px] font-semibold bg-white text-slate-900">{activeMore.label}</span>}
        </div>
      </div>

      {moreOpen && rect && createPortal(
        <div ref={menuRef} role="menu" data-testid="admin-tab-more-menu"
          className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl py-1.5"
          style={{ position: "fixed", top: rect.bottom + 6, left: Math.min(rect.left, window.innerWidth - 268), minWidth: 260, zIndex: 1000 }}>
          {moreTabs.map(m => {
            const on = active === m.id;
            return (
              <button key={m.id} role="menuitem" onClick={() => { onChange(m.id); setMoreOpen(false); }} data-testid={m.testid || `admin-tab-${m.id}`}
                className={`w-full text-left flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                  on ? "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300" : "text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50"}`}>
                <m.icon className={`w-4 h-4 ${on ? "text-red-600" : "text-slate-400"}`} />
                <span className="flex-1">{m.label}</span>
                {m.hint && <span className="text-[11px] text-slate-400">{m.hint}</span>}
                {on && <Check className="w-3.5 h-3.5 text-red-600" />}
              </button>
            );
          })}
        </div>,
        document.body
      )}

      {drawer && createPortal(
        <div className="sm:hidden fixed inset-0 z-[60]">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-72 max-w-[85vw] bg-slate-900 border-r border-slate-700 shadow-2xl flex flex-col"
            style={{ paddingTop: "env(safe-area-inset-top)" }}>
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <p className="text-white font-bold text-sm truncate">{title}</p>
              <button onClick={() => setDrawer(false)} className="p-2 rounded-lg bg-slate-800 text-slate-300" aria-label="Luk"><X className="w-4 h-4" /></button>
            </div>
            <nav className="flex-1 overflow-y-auto py-2">
              {[...tabs, { divider: true, id: "__d" }, ...moreTabs].map(t => t.divider ? (
                <div key={t.id} className="my-2 border-t border-slate-800" />
              ) : (
                <button key={t.id} onClick={() => { onChange(t.id); setDrawer(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-medium border-l-4 ${
                    active === t.id ? "bg-red-500/15 text-red-200 border-red-500" : "text-slate-300 border-transparent hover:bg-slate-800"}`}>
                  <t.icon className={`w-4 h-4 ${active === t.id ? "text-red-400" : "text-slate-400"}`} />
                  <span className="flex-1 text-left">{t.label}</span><Badge id={t.id} />
                </button>
              ))}
            </nav>
          </div>
        </div>,
        document.body
      )}
      <span className="sr-only">{current?.label}</span>
    </>
  );
}
