import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  UserPlus, Shield, Loader2, Check, X, Mail, Phone, RotateCcw, UserX, ChevronDown, Info, Users,
} from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Team & rettigheder (2026-10-17). Logistik admin kan invitere koordinatorer
 * og bestemme præcis hvad de må. Administratorer har altid alt. En
 * koordinator med "Team og rettigheder" kan kun give rettigheder vedkommende
 * selv har, og kan ikke ændre sine egne.
 */
const card = "bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm";
const inputCls = "w-full px-3 py-2.5 sm:py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";
const labelCls = "block text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1";
const btnPrimary = "inline-flex items-center justify-center gap-1.5 px-4 py-2.5 sm:py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-50";
const btnGhost = "inline-flex items-center justify-center gap-1.5 px-3 py-2.5 sm:py-2 rounded-lg border border-slate-200 dark:border-slate-600 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50";

// Grupperet så det er til at overskue - samme nøgler som backend (COORDINATOR_PERMS).
const GROUPS = [
  { title: "Daglig drift", keys: ["tours_edit", "tours_assign", "tours_delete", "messages", "planning"] },
  { title: "Overblik", keys: ["reports", "archive"] },
  { title: "Økonomi", keys: ["economy_view", "economy_edit"] },
  { title: "Opsætning", keys: ["drivers", "locations", "settings", "team"] },
];
const PRESETS = [
  { id: "dispatch", label: "Disponent", keys: ["tours_edit", "tours_assign", "messages", "planning"] },
  { id: "dispatch_plus", label: "Disponent + overblik", keys: ["tours_edit", "tours_assign", "tours_delete", "messages", "planning", "reports", "archive", "drivers"] },
  { id: "bookkeeper", label: "Bogholder", keys: ["economy_view", "economy_edit", "reports", "archive"] },
  { id: "all_but_money", label: "Alt undtagen økonomi", keys: ["tours_edit", "tours_assign", "tours_delete", "messages", "planning", "reports", "archive", "drivers", "locations", "settings"] },
];
const toPerms = (keys) => Object.fromEntries(keys.map(k => [k, true]));

function PermGrid({ catalog, value, onChange, allowed, disabled }) {
  const label = Object.fromEntries(catalog.map(c => [c.key, c.label]));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map(p => (
          <button key={p.id} type="button" disabled={disabled}
            onClick={() => onChange(toPerms(p.keys.filter(k => allowed[k])))}
            className="px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-600 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-40">
            {p.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {GROUPS.map(g => (
          <div key={g.title} className="rounded-xl border border-slate-100 dark:border-slate-700 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400 mb-1.5">{g.title}</div>
            {g.keys.filter(k => label[k]).map(k => {
              const can = allowed[k] && !disabled;
              return (
                <label key={k} className={`flex items-center gap-2.5 py-1.5 text-sm ${can ? "cursor-pointer" : "opacity-50"}`}
                  title={allowed[k] ? "" : "Du kan kun give rettigheder du selv har"}>
                  <input type="checkbox" className="w-4 h-4 accent-emerald-600" disabled={!can}
                    checked={!!value[k]} onChange={(e) => onChange({ ...value, [k]: e.target.checked })} />
                  <span className="text-slate-700 dark:text-slate-200">{label[k]}</span>
                </label>
              );
            })}
          </div>
        ))}
      </div>
      {value.economy_edit && !value.economy_view && (
        <p className="text-xs text-amber-700">"Ændre priser" kræver også "Se priser og økonomi".</p>
      )}
    </div>
  );
}

function MemberRow({ m, catalog, me, onSaved }) {
  const [open, setOpen] = useState(false);
  const [perms, setPerms] = useState(m.permissions);
  const [phone, setPhone] = useState(m.phone || "");
  const [busy, setBusy] = useState(false);
  const isMe = m.id === me.id;
  const editable = m.is_coordinator && !isMe;
  const count = Object.values(m.permissions).filter(Boolean).length;

  useEffect(() => { setPerms(m.permissions); setPhone(m.phone || ""); }, [m]);

  const save = async (extra = {}) => {
    setBusy(true);
    try {
      const p = { ...perms };
      if (p.economy_edit) p.economy_view = true;
      await axios.put(`${API}/logistics/team/${m.id}`, { name: m.name, phone, permissions: p, ...extra });
      toast.success("Gemt");
      onSaved();
    } catch (e) { toast.error(formatApiError(e)); }
    setBusy(false);
  };
  const remove = async () => {
    if (!window.confirm(m.invitation_status === "pending" ? `Træk invitationen til ${m.name} tilbage?` : `Deaktivér ${m.name}? Vedkommende kan ikke længere logge ind.`)) return;
    try { await axios.delete(`${API}/logistics/team/${m.id}`); toast.success("Fjernet"); onSaved(); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  const resend = async () => {
    try { await axios.post(`${API}/logistics/team/${m.id}/resend`); toast.success("Invitation sendt igen"); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <li className={`${!m.active ? "opacity-60" : ""}`} data-testid={`team-member-${m.id}`}>
      <button className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-700/30" onClick={() => setOpen(v => !v)}>
        <span className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${m.is_coordinator ? "bg-emerald-100 text-emerald-800" : "bg-slate-900 text-white"}`}>
          {(m.name || m.email || "?").charAt(0).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-900 dark:text-white truncate">{m.name}{isMe ? " (dig)" : ""}</span>
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${m.is_coordinator ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300" : "bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200"}`}>
              {m.is_coordinator ? "Koordinator" : "Administrator"}
            </span>
            {m.invitation_status === "pending" && <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">Afventer</span>}
            {!m.active && <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">Deaktiveret</span>}
          </span>
          <span className="block text-xs text-slate-500 truncate">{m.email}{m.phone ? ` · ${m.phone}` : ""}</span>
        </span>
        <span className="text-xs text-slate-400 hidden sm:inline">{m.is_coordinator ? `${count} af ${catalog.length} rettigheder` : "Alle rettigheder"}</span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3">
          <div className="max-w-xs">
            <label className={labelCls}>Telefon (chauffører kan ringe)</label>
            <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+45 …" inputMode="tel" />
          </div>
          {m.is_coordinator ? (
            <PermGrid catalog={catalog} value={perms} onChange={setPerms} allowed={me.permissions} disabled={!editable} />
          ) : (
            <p className="text-sm text-slate-500 flex items-center gap-2"><Shield className="w-4 h-4" /> Administratorer har altid adgang til alt.</p>
          )}
          {isMe && m.is_coordinator && <p className="text-xs text-slate-500">Du kan ikke ændre dine egne rettigheder.</p>}
          <div className="flex flex-wrap gap-2">
            <button className={btnPrimary} disabled={busy} onClick={() => save()} data-testid="team-save">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Gem</button>
            {m.invitation_status === "pending" && <button className={btnGhost} onClick={resend}><Mail className="w-4 h-4" /> Send invitation igen</button>}
            {editable && m.active && <button className={btnGhost} onClick={remove}><UserX className="w-4 h-4" /> {m.invitation_status === "pending" ? "Træk tilbage" : "Deaktivér"}</button>}
            {editable && !m.active && <button className={btnGhost} onClick={() => save({ active: true })}><RotateCcw className="w-4 h-4" /> Genaktivér</button>}
          </div>
        </div>
      )}
    </li>
  );
}

export default function TeamPanel() {
  const [data, setData] = useState(null);
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", permissions: toPerms(PRESETS[0].keys) });
  const [busy, setBusy] = useState(false);
  const [contact, setContact] = useState({ phone: "", name: "" });

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/logistics/team`);
      setData(r.data);
      setContact({ phone: r.data.dispatch_phone || "", name: r.data.dispatch_name || "" });
    } catch (e) { setData({ error: formatApiError(e) }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    setBusy(true);
    try {
      const p = { ...form.permissions };
      if (p.economy_edit) p.economy_view = true;
      await axios.post(`${API}/logistics/team`, { ...form, permissions: p });
      toast.success(`Invitation sendt til ${form.email}`);
      setInviting(false);
      setForm({ name: "", email: "", phone: "", permissions: toPerms(PRESETS[0].keys) });
      load();
    } catch (e) { toast.error(formatApiError(e)); }
    setBusy(false);
  };
  const saveContact = async () => {
    try { await axios.put(`${API}/logistics/team-contact`, contact); toast.success("Disponent-telefon gemt"); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  if (!data) return <div className={`${card} p-10 flex justify-center`}><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  if (data.error) return (
    <div className={`${card} p-8 text-center space-y-3`}>
      <p className="text-sm text-slate-600 dark:text-slate-300">Kunne ikke hente teamet: {data.error}</p>
      <button className={btnGhost} onClick={() => { setData(null); load(); }}><RotateCcw className="w-4 h-4" /> Prøv igen</button>
    </div>
  );

  return (
    <section className="space-y-4" data-testid="team-panel">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2"><Users className="w-5 h-5 text-emerald-600" /> Team &amp; rettigheder</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Invitér koordinatorer og vælg præcis hvad de må se og ændre.</p>
        </div>
        {!inviting && <button className={btnPrimary} onClick={() => setInviting(true)} data-testid="team-invite-btn"><UserPlus className="w-4 h-4" /> Invitér koordinator</button>}
      </div>

      {inviting && (
        <div className={`${card} p-4 sm:p-5 space-y-4`} data-testid="team-invite-form">
          <div className="flex items-center justify-between">
            <h3 className="font-bold">Ny koordinator</h3>
            <button onClick={() => setInviting(false)} className="p-1.5 text-slate-400" aria-label="Luk"><X className="w-5 h-5" /></button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div><label className={labelCls}>Navn</label><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div><label className={labelCls}>E-mail</label><input type="email" className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div><label className={labelCls}>Telefon</label><input className={inputCls} inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Valgfri" /></div>
          </div>
          <PermGrid catalog={data.catalog} value={form.permissions} onChange={(p) => setForm({ ...form, permissions: p })} allowed={data.me.permissions} />
          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={() => setInviting(false)}>Annuller</button>
            <button className={btnPrimary} disabled={busy || !form.name.trim() || !form.email.trim()} onClick={invite} data-testid="team-invite-send">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />} Send invitation
            </button>
          </div>
          <p className="text-xs text-slate-500">Koordinatoren får en mail med et link til at vælge adgangskode (gyldigt i 72 timer).</p>
        </div>
      )}

      <div className={`${card} overflow-hidden`}>
        <ul className="divide-y divide-slate-100 dark:divide-slate-700">
          {data.members.map(m => <MemberRow key={m.id} m={m} catalog={data.catalog} me={data.me} onSaved={load} />)}
        </ul>
      </div>

      <div className={`${card} p-4 sm:p-5 space-y-3`}>
        <h3 className="font-bold flex items-center gap-2"><Phone className="w-4 h-4 text-slate-400" /> Chaufførerne ringer til</h3>
        <p className="text-sm text-slate-500">Chaufføren har en "Ring"-knap på hver tur. Den ringer til den der tildelte turen (hvis vedkommende har et telefonnummer), ellers til nummeret her.</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div><label className={labelCls}>Navn</label><input className={inputCls} value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} placeholder="Fx Disponenten" /></div>
          <div><label className={labelCls}>Telefon</label><input className={inputCls} inputMode="tel" value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} placeholder="+45 …" /></div>
          <div><button className={btnPrimary} onClick={saveContact}><Check className="w-4 h-4" /> Gem</button></div>
        </div>
      </div>

      <div className="flex gap-2 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-900 text-sm text-sky-900 dark:text-sky-100">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <div>Ændringer gælder med det samme (senest efter 15 sekunder). En deaktiveret koordinator bliver logget ud ved næste handling.</div>
      </div>
    </section>
  );
}
