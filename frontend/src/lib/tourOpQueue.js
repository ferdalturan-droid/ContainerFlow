// tourOpQueue.js - 2026-10-18
// Offline-kø for chaufførens handlinger på en tur: start (På vej), stop-kryds,
// billeder og afslutning. Samme mønster som receiptUploadQueue.js:
// localStorage overlever browser-luk og iOS-reload, og køen sendes igen ved
// app-start, når fanen bliver synlig, når nettet kommer tilbage og hvert 30. s.
//
// Kun netværksfejl (intet svar) og serverfejl (5xx) prøves igen. Siger
// serveren nej (4xx, fx "turen er taget af en anden"), fjernes handlingen og
// chaufføren får beskeden - den bliver ikke rigtig af at blive sendt igen.
//
// Afslutning sendes med et op_id, så serveren ignorerer en gentagelse
// (POST /tours/{id}/finish er sikker at sende to gange).

import axios from "axios";

const KEY = "cf:tourOps";
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
let busy = false;
let listeners = [];
let started = false;

const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) { return []; } };
const save = (q) => {
  try { localStorage.setItem(KEY, JSON.stringify(q)); }
  catch (_) { if (q.length > 1) save(q.slice(-Math.ceil(q.length / 2))); }
};
const notify = (event) => { const n = load().length; listeners.forEach(fn => { try { fn(n, event); } catch (_) { /* ignore */ } }); };

export const isNetworkError = (e) => !e?.response || (e.response.status >= 500 && e.response.status !== 501);
export const pendingOps = () => load();
export const pendingCount = () => load().length;
export function subscribeOps(fn) { listeners.push(fn); return () => { listeners = listeners.filter(l => l !== fn); }; }

export function newOpId() {
  return (window.crypto?.randomUUID?.() || `op_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`);
}

/** Læg en handling i køen. kind: "put" | "stop" | "photo" | "finish" | "take" | "start". */
export function enqueueOp(op) {
  const q = load();
  // Samme afslutning (op_id) eller samme stop-kryds lægges ikke i køen to gange.
  const dup = q.find(x => (op.op_id && x.op_id === op.op_id) || (op.kind === "stop" && x.kind === "stop" && x.tour_id === op.tour_id && x.stop_id === op.stop_id));
  if (dup) Object.assign(dup, op);
  else q.push({ ...op, qid: newOpId(), queued_at: Date.now(), attempts: 0 });
  save(q);
  notify();
  setTimeout(processOps, 1500);
}

async function send(op) {
  if (op.kind === "put") return axios.put(`${API}/tours/${op.tour_id}`, op.body, { timeout: 30000 });
  if (op.kind === "stop") return axios.post(`${API}/tours/${op.tour_id}/stops/${op.stop_id}/done`, op.body, { timeout: 30000 });
  if (op.kind === "photo") return axios.post(`${API}/tours/${op.tour_id}/photos`, { image: op.image }, { timeout: 60000 });
  if (op.kind === "finish") return axios.post(`${API}/tours/${op.tour_id}/finish`, { ...op.body, op_id: op.op_id }, { timeout: 45000 });
  // 2026-10-20: "Tag turen" og start (evt. flere ture sammen på hængeren).
  if (op.kind === "take") return axios.post(`${API}/driver/tours/${op.tour_id}/take`, {}, { timeout: 30000 });
  if (op.kind === "start") return axios.post(`${API}/driver/tours/start`, { tour_ids: op.tour_ids, op_id: op.op_id }, { timeout: 30000 });
  return null;
}

export async function processOps() {
  if (busy || typeof navigator !== "undefined" && navigator.onLine === false) return;
  if (!axios.defaults.headers.common?.Authorization) return; // ikke logget ind endnu
  busy = true;
  try {
    // Rækkefølgen bevares: en tur startes før den afsluttes, billeder før afslutning.
    for (const op of load()) {
      try {
        await send(op);
        save(load().filter(x => x.qid !== op.qid));
        notify({ type: "sent", op });
      } catch (e) {
        if (isNetworkError(e)) {
          const q = load();
          const it = q.find(x => x.qid === op.qid);
          if (it) { it.attempts += 1; save(q); }
          break; // stadig offline - prøv igen senere, i samme rækkefølge
        }
        save(load().filter(x => x.qid !== op.qid));
        notify({ type: "rejected", op, message: e?.response?.data?.detail || "Serveren afviste handlingen" });
      }
    }
  } finally { busy = false; }
}

export function initTourOpQueue() {
  if (started) return;
  started = true;
  window.addEventListener("online", () => processOps());
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") processOps(); });
  setInterval(processOps, 30000);
  setTimeout(processOps, 2000);
}
