import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Send, Loader2, MessageSquare } from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Beskedtråd pr. tur mellem planlægger og chauffør (2026-10-16).
 * Backend: GET/POST /api/tour-messages/{tour_id}. Åbning af tråden markerer
 * modpartens beskeder som læst. Hurtigsvar gør det muligt at svare med én
 * hånd fra førerhuset.
 */
const QUICK = {
  driver: ["Jeg er på vej", "Forsinket ca. 15 min", "Container ikke klar", "Ingen adgang", "Ring til mig"],
  planner: ["Ring venligst", "Tag den som den næste", "Kunden er orienteret", "Vent med denne"],
};

const fmt = (iso) => {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const today = new Date().toDateString() === d.toDateString();
  const time = d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
  return today ? time : `${d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit" })} ${time}`;
};

export default function TourChat({ tourId, side = "planner", onChanged, maxHeight = 320, autoFocus = false, readOnly = false, header = null }) {
  const [msgs, setMsgs] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef(null);
  const taRef = useRef(null);
  const mine = side === "driver" ? "driver" : "planner";

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/tour-messages/${tourId}`);
      setMsgs(r.data.messages || []);
      onChanged && onChanged();
    } catch (e) {
      setMsgs([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourId]);

  useEffect(() => {
    setMsgs(null);
    load();
    const iv = setInterval(() => { if (!document.hidden) load(); }, 8000);
    return () => clearInterval(iv);
  }, [load]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [msgs]);

  const send = async (body) => {
    const t = (body ?? text).trim();
    if (!t || sending) return;
    setSending(true);
    try {
      const r = await axios.post(`${API}/tour-messages/${tourId}`, { text: t });
      setMsgs(prev => [...(prev || []), r.data]);
      if (body === undefined) { setText(""); if (taRef.current) taRef.current.style.height = "44px"; }
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e));
    }
    setSending(false);
  };

  return (
    <div className="flex flex-col gap-2" data-testid={`tour-chat-${tourId}`}>
      <div ref={listRef} className="overflow-y-auto space-y-2 pr-1" style={{ maxHeight }}>
        {msgs === null && (
          <div className="flex items-center gap-2 text-xs text-slate-400 py-3"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Henter beskeder…</div>
        )}
        {msgs && msgs.length === 0 && (
          <div className="flex items-center gap-2 text-xs text-slate-400 py-3">
            <MessageSquare className="w-4 h-4" />
            {side === "driver" ? "Ingen beskeder endnu. Skriv til planlæggeren her." : "Ingen beskeder endnu. Chaufføren ser beskeden i appen ved turen."}
          </div>
        )}
        {(msgs || []).map(m => {
          const own = m.sender_role === mine;
          const seen = own && (mine === "planner" ? m.read_by_driver : m.read_by_planner);
          return (
            <div key={m.id} className={`flex ${own ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-snug ${
                own ? "bg-emerald-600 text-white rounded-br-md" : "bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100 rounded-bl-md"
              }`}>
                {!own && <div className="text-[10px] font-bold opacity-70 mb-0.5">{m.sender_name || (m.sender_role === "driver" ? "Chauffør" : "Planlægger")}</div>}
                <div className="whitespace-pre-wrap break-words">{m.text}</div>
                <div className={`text-[10px] mt-0.5 ${own ? "text-emerald-100" : "text-slate-400"}`}>
                  {fmt(m.created_at)}{own && (seen ? " · Læst" : " · Sendt")}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {header}
      {readOnly ? (
        <p className="text-xs text-slate-400">Du kan læse beskeder, men ikke skrive (kræver rettigheden "Skriv med chauffører").</p>
      ) : (<>
      <div className="flex flex-wrap gap-1.5">
        {QUICK[mine].map(q => (
          <button key={q} type="button" disabled={sending} onClick={() => send(q)}
            className="px-2.5 py-1.5 rounded-full border border-slate-200 dark:border-slate-600 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50">
            {q}
          </button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2">
        <textarea
          ref={taRef}
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = "44px";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
          }}
          style={{ height: 44, minHeight: 44, maxHeight: 120 }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          rows={1}
          maxLength={1000}
          placeholder="Skriv en besked…"
          className="flex-1 resize-none px-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          data-testid="tour-chat-input"
        />
        <button type="submit" disabled={sending || !text.trim()}
          className="h-11 w-11 shrink-0 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white flex items-center justify-center disabled:opacity-40"
          aria-label="Send" data-testid="tour-chat-send">
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </form>
      </>)}
    </div>
  );
}
