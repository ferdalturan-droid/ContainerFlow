// receiptUploadQueue.js - Fase 17.13 (2026-02-27)
// Robust upload-kø for kvitteringer. Persisteres i localStorage så den
// overlever browser-luk, dårlig dækning og iOS Safari memory-pressure.
//
// Design:
//   - Hver pending upload ligger i en kø under nøglen `cf:receiptQueue`
//   - Når et item enqueues, prøver vi straks at uploade i baggrunden
//   - Ved success fjernes item fra køen
//   - Ved fail øges attempts; max 5 forsøg, derefter markeres som permanent fejl
//   - Retry sker også ved app-mount og når browser-fanen bliver synlig igen
//
// Sikkerhed: Vi gemmer det base64-kodede billede + tour_id + vægt midlertidigt
// i localStorage - kun mens uploaden venter. Items slettes umiddelbart efter
// succesfuld upload. Ingen JWT/secrets gemmes her (axios sender det automatisk
// via Authorization-header fra in-memory state).

import axios from "axios";

const QUEUE_KEY = "cf:receiptQueue";
const MAX_ATTEMPTS = 5;
const RETRY_BACKOFF_MS = [0, 2000, 5000, 15000, 60000]; // 0s, 2s, 5s, 15s, 60s

let _isProcessing = false;
let _listeners = [];

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function loadQueue() {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (_) { return []; }
}

function saveQueue(q) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
  } catch (e) {
    // localStorage kvota overskredet - fjern de ældste poster.
    if (q.length > 1) saveQueue(q.slice(-Math.floor(q.length / 2)));
  }
}

function notifyListeners() {
  const count = loadQueue().filter(i => !i.permanentFailure).length;
  _listeners.forEach(fn => { try { fn(count); } catch (_) {} });
}

export function subscribeQueue(listener) {
  _listeners.push(listener);
  // Returnér unsubscribe.
  return () => { _listeners = _listeners.filter(l => l !== listener); };
}

export function getQueueCount() {
  return loadQueue().filter(i => !i.permanentFailure).length;
}

export function enqueueReceiptUpload(payload) {
  const queue = loadQueue();
  // Dedupe: hvis et item med samme tour_id + samme final_weight_kg +
  // samme image-prefix allerede ligger i køen, springer vi over.
  const imgPrefix = (payload.image_data || "").slice(0, 64);
  const dup = queue.find(i =>
    i.tour_id === payload.tour_id &&
    i.final_weight_kg === payload.final_weight_kg &&
    (i.image_data || "").slice(0, 64) === imgPrefix &&
    i.append_for_loose === payload.append_for_loose
  );
  if (dup) return dup.queueId;
  const queueId = `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  queue.push({
    queueId,
    ...payload,
    attempts: 0,
    queuedAt: Date.now(),
    permanentFailure: false,
    lastError: null,
  });
  saveQueue(queue);
  notifyListeners();
  // Start processing i baggrunden - ikke async/await så caller ikke blokeres.
  setTimeout(() => processQueue(), 0);
  return queueId;
}

async function uploadOne(item) {
  const body = {
    tour_id: item.tour_id,
    image_data: item.image_data,
    content_type: item.content_type || "image/jpeg",
    description: item.description || "Vedhæftet via scanner",
    final_weight_kg: item.final_weight_kg,
    user_name: item.user_name || "",
    append_for_loose: !!item.append_for_loose,
    skip_tour_update: true,
  };
  await axios.post(`${API}/receipts/save-for-tour`, body, { timeout: 60000 });
}

export async function processQueue() {
  if (_isProcessing) return;
  _isProcessing = true;
  try {
    let queue = loadQueue();
    let progress = true;
    while (progress) {
      progress = false;
      queue = loadQueue();
      for (let i = 0; i < queue.length; i++) {
        const item = queue[i];
        if (item.permanentFailure) continue;
        const backoff = RETRY_BACKOFF_MS[Math.min(item.attempts, RETRY_BACKOFF_MS.length - 1)];
        if (Date.now() - (item.lastAttemptAt || 0) < backoff) continue;
        try {
          item.lastAttemptAt = Date.now();
          item.attempts = (item.attempts || 0) + 1;
          saveQueue(queue);
          await uploadOne(item);
          // Succes - fjern item.
          queue = loadQueue().filter(x => x.queueId !== item.queueId);
          saveQueue(queue);
          progress = true;
          break; // re-loop med opdateret kø
        } catch (e) {
          item.lastError = e?.response?.data?.detail || e?.message || "ukendt fejl";
          if (item.attempts >= MAX_ATTEMPTS) {
            item.permanentFailure = true;
          }
          saveQueue(queue);
        }
      }
    }
  } finally {
    _isProcessing = false;
    notifyListeners();
  }
}

// Startup hook: registrér retry-triggers på app-load.
export function initReceiptUploadQueue() {
  if (typeof window === "undefined") return;
  // Retry når browser-fanen igen bliver synlig (chauffør åbner appen).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") processQueue();
  });
  // Retry når netværk vender tilbage.
  window.addEventListener("online", () => processQueue());
  // Førstegangs-retry kort efter mount.
  setTimeout(() => processQueue(), 1000);
}
