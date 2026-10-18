import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Users, Truck, Package2, Send, Plus, Edit2, Trash2, Mail, Loader2, Check, X, Clock, CheckCircle2,
  Eye, EyeOff, AlertTriangle, Info,
} from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Chauffører (2026-10-18). Logistik admins "grunddata" om chauffører og
 * flåde: chauffører (invitation, rediger, aktiv/inaktiv), vognnumre, hængere
 * og generelle beskeder til en chauffør. Samme opbygning som "Medarbejdere"
 * på lokationssiden og "Team & rettigheder": en liste i et kort, og oprettelse
 * og redigering i et vindue.
 */
const card = "bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm";
const INPUT = "w-full px-3 py-2 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-lg text-sm focus:border-emerald-500 outline-none";
const btnPrimary = "inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-50";
const iconBtn = "p-1.5 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-50";
const TH = "px-4 py-2.5";

function Field({ label, hint, children }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-semibold text-slate-500 mb-1">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

function Modal({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid={testid}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full p-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700" aria-label="Luk"><X className="w-4 h-4 text-slate-500" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function FormButtons({ onCancel, onSave, saving, saveLabel = "Gem", left = null }) {
  return (
    <div className="flex items-center gap-2 justify-end mt-4">
      {left && <div className="mr-auto">{left}</div>}
      <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200">Annuller</button>
      <button onClick={onSave} disabled={saving} className={btnPrimary} data-testid="drivers-form-save">
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} {saveLabel}
      </button>
    </div>
  );
}

function ConfirmModal({ title, message, confirmLabel = "Slet", onConfirm, onCancel }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" data-testid="drivers-confirm">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div className="p-6">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-950/40 ring-8 ring-red-50 dark:ring-red-950/20 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-600" />
          </div>
          <h3 className="text-lg font-bold text-slate-900 dark:text-white text-center mb-2">{title}</h3>
          <div className="text-sm text-center text-slate-600 dark:text-slate-300">{message}</div>
        </div>
        <div className="flex gap-3 p-4 bg-slate-50 dark:bg-slate-900/40">
          <button onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600">
            Annuller
          </button>
          <button disabled={busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-60 inline-flex items-center justify-center gap-2"
            data-testid="drivers-confirm-btn">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ d }) {
  const inactive = d.active === false;
  const pending = d.invitation_status === "pending";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
      inactive ? "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
        : pending ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
          : "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"}`} data-testid={`driver-status-${d.id}`}>
      {inactive ? "Inaktiv" : pending ? <><Clock className="w-3 h-3" /> Afventer</> : <><CheckCircle2 className="w-3 h-3" /> Aktiv</>}
    </span>
  );
}

function Empty({ children }) {
  return <div className={`${card} py-10 text-center text-slate-400 text-sm`}>{children}</div>;
}

/* ============================ CHAUFFØRER ============================ */
function DriversList({ drivers, onChanged, formOpen, setFormOpen }) {
  const empty = { name: "", email: "", phone: "" };
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => { if (formOpen && !editing) setForm(empty); }, [formOpen]); // eslint-disable-line react-hooks/exhaustive-deps
  const openEdit = (d) => { setEditing(d); setForm({ name: d.name || "", email: d.email || "", phone: d.phone || "" }); setFormOpen(true); };
  const close = () => { setFormOpen(false); setEditing(null); };

  const save = async () => {
    if (!form.name.trim() || !form.email.trim()) { toast.error("Navn og e-mail skal udfyldes"); return; }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`${API}/drivers/${editing.id}`, { name: form.name.trim(), email: form.email.trim(), phone: form.phone.trim() });
        toast.success("Chauffør opdateret");
      } else {
        await axios.post(`${API}/drivers`, { name: form.name.trim(), email: form.email.trim(), phone: form.phone.trim() });
        toast.success(`Invitation sendt til ${form.email.trim()}`);
      }
      close(); onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };
  const toggleActive = async (d) => {
    const next = d.active === false;
    setBusyId(d.id);
    try {
      await axios.put(`${API}/drivers/${d.id}`, { active: next });
      toast.success(next ? `${d.name} er aktiveret` : `${d.name} er inaktiveret - kan ikke logge ind og kan ikke få ture`);
      onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusyId(""); }
  };
  const resend = async (d) => {
    setBusyId(d.id);
    try { await axios.post(`${API}/drivers/${d.id}/resend-invitation`); toast.success(`Invitation sendt igen til ${d.email}`); }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setBusyId(""); }
  };
  const remove = async () => {
    try {
      await axios.delete(`${API}/drivers/${deleteTarget.id}`);
      toast.success("Chauffør slettet");
      setDeleteTarget(null); close(); onChanged();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const rows = [...drivers].sort((a, b) => ((a.active === false) - (b.active === false)) || String(a.name || "").localeCompare(String(b.name || ""), "da"));

  return (
    <>
      {rows.length === 0 ? (
        <Empty>Ingen chauffører endnu. Tryk "Ny chauffør" for at invitere den første.</Empty>
      ) : (
        <div className={`${card} overflow-hidden`}>
          {/* Telefon: én linje pr. chauffør i stedet for en tabel man skal scrolle */}
          <ul className="sm:hidden divide-y divide-slate-100 dark:divide-slate-700/60">
            {rows.map(d => (
              <li key={d.id} className={`px-4 py-3 flex items-start gap-3 ${d.active === false ? "opacity-60" : ""}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap"><span className="font-semibold text-slate-900 dark:text-white">{d.name}</span><StatusPill d={d} /></div>
                  <div className="text-xs text-slate-500 truncate">{d.email}</div>
                  {d.phone && <div className="text-xs text-slate-500">{d.phone}</div>}
                </div>
                <button onClick={() => openEdit(d)} className={iconBtn} title="Rediger"><Edit2 className="w-4 h-4" /></button>
              </li>
            ))}
          </ul>
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-sm" data-testid="drivers-table">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className={TH}>Navn</th>
                  <th className={TH}>E-mail</th>
                  <th className={TH}>Tlf.</th>
                  <th className={TH}>Status</th>
                  <th className={TH}>Aktiv</th>
                  <th className={`${TH} text-right`}>Handlinger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {rows.map(d => {
                  const inactive = d.active === false;
                  return (
                    <tr key={d.id} className={inactive ? "opacity-60" : ""} data-testid={`driver-row-${d.id}`}>
                      <td className="px-4 py-3 font-medium text-slate-900 dark:text-white whitespace-nowrap">{d.name || "-"}</td>
                      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{d.email || ""}</td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{d.phone || ""}</td>
                      <td className="px-4 py-3"><StatusPill d={d} /></td>
                      <td className="px-4 py-3">
                        <button onClick={() => toggleActive(d)} disabled={busyId === d.id}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-bold disabled:opacity-50 ${
                            inactive ? "bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 text-emerald-700"
                              : "bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/30 text-amber-700"}`}
                          data-testid={`toggle-driver-${d.id}`}>
                          {inactive ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                          {inactive ? "Aktivér" : "Inaktivér"}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button onClick={() => openEdit(d)} className={iconBtn} title="Rediger" data-testid={`edit-driver-${d.id}`}><Edit2 className="w-4 h-4" /></button>
                        {d.invitation_status === "pending" && !inactive && (
                          <button onClick={() => resend(d)} disabled={busyId === d.id} className={`${iconBtn} hover:!text-orange-600 hover:!bg-orange-50`}
                            title="Send invitation igen" data-testid={`resend-invite-${d.id}`}>
                            {busyId === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {formOpen && (
        <Modal title={editing ? "Rediger chauffør" : "Ny chauffør"} onClose={close} testid="driver-form">
          <Field label="Navn *">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={INPUT} autoFocus data-testid="new-driver-name" />
          </Field>
          <Field label="E-mail *" hint={editing ? "Ændrer du e-mailen, skal chaufføren bruge den nye til at logge ind." : null}>
            <input type="text" inputMode="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={INPUT} data-testid="new-driver-email" />
          </Field>
          <Field label="Telefon">
            <input inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className={INPUT} data-testid="new-driver-phone" />
          </Field>
          {editing && (
            <div className="sm:hidden flex flex-wrap gap-2 mb-2">
              <button onClick={() => { toggleActive(editing); close(); }} className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200">
                {editing.active === false ? "Aktivér" : "Inaktivér"}
              </button>
              {editing.invitation_status === "pending" && editing.active !== false && (
                <button onClick={() => resend(editing)} className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 inline-flex items-center gap-1">
                  <Mail className="w-3.5 h-3.5" /> Send invitation igen
                </button>
              )}
            </div>
          )}
          {!editing && (
            <p className="text-xs text-slate-500 -mt-1 mb-2">
              Chaufføren får en invitations-mail med et 72-timers link og vælger selv adgangskode. Vogn og hænger vælger chaufføren selv ved login.
            </p>
          )}
          <FormButtons onCancel={close} onSave={save} saving={saving} saveLabel={editing ? "Gem" : "Send invitation"}
            left={editing && (
              <button onClick={() => setDeleteTarget(editing)} className="text-xs font-semibold text-slate-500 hover:text-red-600 inline-flex items-center gap-1" data-testid="delete-driver-btn">
                <Trash2 className="w-3.5 h-3.5" /> Slet
              </button>
            )} />
        </Modal>
      )}

      {deleteTarget && (
        <ConfirmModal title="Slet chauffør?" confirmLabel="Slet permanent" onCancel={() => setDeleteTarget(null)} onConfirm={remove}
          message={<>
            <p className="font-medium text-slate-800 dark:text-slate-100">{deleteTarget.name}</p>
            <p className="text-xs text-slate-500 mt-1">{deleteTarget.email}</p>
            <p className="text-xs mt-3">Kørte ture beholder chaufførens navn. Vil du bare stoppe adgangen, så brug "Inaktivér" i stedet - det kan fortrydes. Sletning kan ikke fortrydes.</p>
          </>} />
      )}
    </>
  );
}

/* ============================ VOGNE OG HÆNGERE ============================ */
// Samme liste-mønster til vognnumre og hængere; `kind` styrer felter og tekster.
const FLEET = {
  vehicles: {
    url: "vehicles", one: "vognnummer", title: (x) => x ? "Rediger vognnummer" : "Nyt vognnummer",
    empty: { number: "" },
    toForm: (v) => ({ number: v.number || "" }),
    toBody: (f) => ({ number: f.number.trim().toUpperCase() }),
    valid: (f) => (f.number.trim() ? "" : "Vognnummer skal udfyldes"),
  },
  trailers: {
    url: "trailers", one: "hænger", title: (x) => x ? "Rediger hænger" : "Ny hænger",
    empty: { number: "", container_capacity: 1 },
    toForm: (t) => ({ number: t.number || "", container_capacity: t.container_capacity || 1 }),
    toBody: (f) => ({ number: f.number.trim(), container_capacity: parseInt(f.container_capacity, 10) }),
    valid: (f) => (!f.number.trim() ? "Hængernummer skal udfyldes"
      : !(parseInt(f.container_capacity, 10) >= 1) ? "Antal containere skal være mindst 1" : ""),
  },
};

function FleetList({ kind, formOpen, setFormOpen, onCount }) {
  const cfg = FLEET[kind];
  const [items, setItems] = useState(null);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(cfg.empty);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/${cfg.url}`); setItems(r.data || []); onCount?.(kind, (r.data || []).length); }
    catch (e) { toast.error(formatApiError(e)); setItems([]); }
  }, [cfg.url, kind, onCount]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (formOpen && !editing) setForm(cfg.empty); }, [formOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const openEdit = (x) => { setEditing(x); setForm(cfg.toForm(x)); setFormOpen(true); };
  const close = () => { setFormOpen(false); setEditing(null); };
  const save = async () => {
    const err = cfg.valid(form);
    if (err) { toast.error(err); return; }
    setSaving(true);
    try {
      const body = cfg.toBody(form);
      if (editing) await axios.put(`${API}/${cfg.url}/${editing.id}`, body);
      else await axios.post(`${API}/${cfg.url}`, body);
      toast.success(editing ? "Gemt" : `${cfg.one[0].toUpperCase()}${cfg.one.slice(1)} "${body.number}" oprettet`);
      close(); load();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    try { await axios.delete(`${API}/${cfg.url}/${deleteTarget.id}`); toast.success("Slettet"); setDeleteTarget(null); load(); }
    catch (e) { toast.error(formatApiError(e)); }
  };

  if (items === null) return <div className={`${card} py-10 text-center`}><Loader2 className="w-5 h-5 animate-spin inline text-slate-400" /></div>;
  const trailers = kind === "trailers";
  const cap = parseInt(form.container_capacity, 10) || 0;

  return (
    <>
      {items.length === 0 ? (
        <Empty>{trailers ? "Ingen hængere endnu." : "Ingen vognnumre endnu."} Tryk "{cfg.title(null)}" for at oprette den første.</Empty>
      ) : (
        <div className={`${card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid={`${kind}-table`}>
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className={TH}>{trailers ? "Hængernummer" : "Vognnummer"}</th>
                  {trailers && <th className={TH}>Containere pr. hænger</th>}
                  {trailers && <th className={TH}>Maks. samtidige ture</th>}
                  <th className={`${TH} text-right`}>Handlinger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {items.map(x => (
                  <tr key={x.id} data-testid={`${kind === "trailers" ? "trailer" : "vehicle"}-row-${x.id}`}>
                    <td className={`px-4 py-3 font-semibold text-slate-900 dark:text-white ${trailers ? "" : "font-mono tracking-wide"}`}>{x.number}</td>
                    {trailers && <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{x.container_capacity}</td>}
                    {trailers && <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{(x.container_capacity || 0) + 1}</td>}
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <button onClick={() => openEdit(x)} className={iconBtn} title="Rediger"><Edit2 className="w-4 h-4" /></button>
                      <button onClick={() => setDeleteTarget(x)} className={`${iconBtn} hover:!text-red-600 hover:!bg-red-50`} title="Slet"><Trash2 className="w-4 h-4" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {formOpen && (
        <Modal title={cfg.title(editing)} onClose={close} testid={`${kind}-form`}>
          <Field label={trailers ? "Hængernummer *" : "Vognnummer *"} hint={trailers ? null : "Skrives med store bogstaver, fx CF 21 401."}>
            <input value={form.number} autoFocus
              onChange={(e) => setForm({ ...form, number: trailers ? e.target.value : e.target.value.toUpperCase() })}
              className={`${INPUT} ${trailers ? "" : "font-mono uppercase"}`} data-testid={`${kind}-number`} />
          </Field>
          {trailers && (
            <Field label="Antal containere pr. hænger *" hint={cap >= 1 ? `Chaufføren må højst have ${cap + 1} ture i gang på samme tid (kapacitet + 1).` : null}>
              <input type="number" min="1" value={form.container_capacity}
                onChange={(e) => setForm({ ...form, container_capacity: e.target.value })} className={INPUT} data-testid="trailers-capacity" />
            </Field>
          )}
          <FormButtons onCancel={close} onSave={save} saving={saving} />
        </Modal>
      )}

      {deleteTarget && (
        <ConfirmModal title={`Slet ${cfg.one}?`} onCancel={() => setDeleteTarget(null)} onConfirm={remove}
          message={<>
            <p className="font-medium text-slate-800 dark:text-slate-100">{deleteTarget.number}</p>
            <p className="text-xs mt-3">Chaufførerne kan ikke længere vælge den ved login. Kørte ture beholder nummeret.</p>
          </>} />
      )}
    </>
  );
}

/* ============================ BESKEDER ============================ */
function MessagesBox({ drivers, messages, onChanged }) {
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!to || !text.trim()) { toast.error("Vælg chauffør og skriv en besked"); return; }
    setBusy(true);
    try { await axios.post(`${API}/messages`, { to_driver_id: to, content: text.trim() }); setText(""); toast.success("Besked sendt"); onChanged(); }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };
  const remove = async (id) => {
    try { await axios.delete(`${API}/messages/${id}`); onChanged(); }
    catch (e) { toast.error(formatApiError(e)); }
  };
  // Kun beskeder fra planlæggeren til en chauffør (svar fra chauffører ligger i indbakken).
  const sent = (messages || []).filter(m => m.from_admin !== false && (m.to_driver_name || m.to_driver_id));
  return (
    <div className="space-y-4">
      <div className={`${card} p-4 sm:p-5`}>
        <div className="grid grid-cols-1 sm:grid-cols-[220px_1fr_auto] gap-3 items-end">
          <Field label="Til">
            <select value={to} onChange={(e) => setTo(e.target.value)} className={INPUT} data-testid="message-driver">
              <option value="">Vælg chauffør …</option>
              {drivers.filter(d => d.active !== false).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="Besked">
            <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Skriv en besked …" className={INPUT} data-testid="message-text" />
          </Field>
          <div className="mb-3"><button onClick={send} disabled={busy} className={`${btnPrimary} w-full`} data-testid="message-send">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Send
          </button></div>
        </div>
        <p className="text-xs text-slate-500 flex items-start gap-1.5"><Info className="w-3.5 h-3.5 mt-0.5 shrink-0" /> Til generelle beskeder. Handler beskeden om en bestemt tur, så skriv den i turens tråd under Ture - så står den ved turen.</p>
      </div>
      {sent.length === 0 ? <Empty>Ingen sendte beskeder</Empty> : (
        <div className={`${card} overflow-hidden`}>
          <ul className="divide-y divide-slate-100 dark:divide-slate-700/60 max-h-[60vh] overflow-y-auto">
            {sent.map(m => (
              <li key={m.id} className="px-4 py-3 flex items-start gap-3">
                <span className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-200 text-xs font-bold flex items-center justify-center shrink-0">
                  {(m.to_driver_name || "?").split(" ").map(x => x[0]).join("").slice(0, 2).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm"><span className="font-semibold text-slate-900 dark:text-white">{m.to_driver_name}</span>
                    <span className="text-xs text-slate-400 ml-2">{m.created_at ? new Date(m.created_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" }) : ""}</span></div>
                  <div className="text-sm text-slate-600 dark:text-slate-300 break-words">{m.content}</div>
                </div>
                <button onClick={() => remove(m.id)} className={`${iconBtn} hover:!text-red-600 hover:!bg-red-50`} title="Slet besked"><Trash2 className="w-4 h-4" /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ============================ FANEN ============================ */
const SECTIONS = [
  { id: "drivers", label: "Chauffører", icon: Users, add: "Ny chauffør" },
  { id: "vehicles", label: "Vogne", icon: Truck, add: "Nyt vognnummer" },
  { id: "trailers", label: "Hængere", icon: Package2, add: "Ny hænger" },
  { id: "messages", label: "Beskeder", icon: Send },
];
const INTRO = {
  drivers: "Invitér og administrér jeres chauffører. En inaktiv chauffør kan ikke logge ind og kan ikke få ture.",
  vehicles: "Firmaets vognliste. Chaufføren vælger sin vogn, når de logger ind.",
  trailers: "Firmaets hængere. Kapaciteten afgør, hvor mange ture chaufføren må have i gang på samme tid (kapacitet + 1).",
  messages: "Send en besked til en chauffør. Den vises i chaufførens app.",
};

export default function DriversPanel({ drivers, messages, onChanged }) {
  const [section, setSection] = useState("drivers");
  const [formOpen, setFormOpen] = useState(false);
  const [counts, setCounts] = useState({});
  const onCount = useCallback((k, n) => setCounts(c => (c[k] === n ? c : { ...c, [k]: n })), []);
  const cur = SECTIONS.find(s => s.id === section);
  const count = { drivers: drivers.length, ...counts };

  return (
    <section className="space-y-4" data-testid="drivers-panel">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2"><Users className="w-5 h-5 text-emerald-600" /> Chauffører</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">{INTRO[section]}</p>
        </div>
        {cur.add && <button className={btnPrimary} onClick={() => setFormOpen(true)} data-testid={`add-${section}-btn`}><Plus className="w-4 h-4" /> {cur.add}</button>}
      </div>

      <div className="grid grid-cols-2 gap-1 sm:inline-flex sm:gap-0 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-1" role="tablist">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button key={id} role="tab" aria-selected={section === id} onClick={() => { setSection(id); setFormOpen(false); }} data-testid={`drivers-section-${id}`}
            className={`px-3 py-1.5 rounded-lg text-sm font-semibold inline-flex items-center justify-center sm:justify-start gap-1.5 ${section === id ? "bg-emerald-600 text-white" : "text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"}`}>
            <Icon className="w-4 h-4 hidden sm:block" /> {label}
            {count[id] !== undefined && <span className={`text-[11px] font-bold ${section === id ? "text-white/80" : "text-slate-400"}`}>{count[id]}</span>}
          </button>
        ))}
      </div>

      {section === "drivers" && <DriversList drivers={drivers} onChanged={onChanged} formOpen={formOpen} setFormOpen={setFormOpen} />}
      {/* Vogne og hængere hentes også når fanen ikke er valgt, så tallene i vælgeren passer. */}
      <div hidden={section !== "vehicles"}><FleetList kind="vehicles" formOpen={section === "vehicles" && formOpen} setFormOpen={setFormOpen} onCount={onCount} /></div>
      <div hidden={section !== "trailers"}><FleetList kind="trailers" formOpen={section === "trailers" && formOpen} setFormOpen={setFormOpen} onCount={onCount} /></div>
      {section === "messages" && <MessagesBox drivers={drivers} messages={messages} onChanged={onChanged} />}
    </section>
  );
}
