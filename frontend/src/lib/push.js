// Web push for chauffører (2026-10-17). Slået til som standard; chaufføren
// kan slå det fra under Profil. iPhone/iPad kræver at appen er lagt på
// hjemmeskærmen (iOS 16.4+), ellers findes push-API'et ikke i Safari.
import axios from "axios";
import { API } from "../auth/api";

export const isIOS = () => {
  const ua = navigator.userAgent || "";
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
};
export const isStandalone = () =>
  (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || window.navigator.standalone === true;
export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
export const permission = () => (("Notification" in window) ? Notification.permission : "unsupported");

const b64ToUint8 = (b64) => {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
};

async function subscribe(driverName) {
  const reg = await navigator.serviceWorker.ready;
  const { data } = await axios.get(`${API}/push/vapid-public-key`);
  if (!data?.public_key) throw new Error("Notifikationer er ikke sat op på serveren endnu");
  let sub = await reg.pushManager.getSubscription();
  const key = b64ToUint8(data.public_key);
  // Er abonnementet lavet med en anden nøgle, laves det om.
  if (sub && sub.options?.applicationServerKey) {
    const cur = new Uint8Array(sub.options.applicationServerKey);
    if (cur.length !== key.length || cur.some((v, i) => v !== key[i])) { await sub.unsubscribe(); sub = null; }
  }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  await axios.post(`${API}/push/subscribe`, { driver_name: driverName || "", subscription: sub.toJSON() });
  return true;
}

/** Skal kaldes fra et tryk (iOS kræver en brugerhandling). */
export async function enablePush(driverName) {
  if (!pushSupported()) throw new Error(isIOS() && !isStandalone()
    ? "Læg appen på hjemmeskærmen først (Del → Føj til hjemmeskærm)"
    : "Din browser understøtter ikke notifikationer");
  const p = await Notification.requestPermission();
  if (p !== "granted") throw new Error("Notifikationer er blokeret i telefonens indstillinger");
  await subscribe(driverName);
  return true;
}

/** Stille synk ved opstart: har chaufføren allerede givet lov, fornyes abonnementet. */
export async function syncPush(driverName, enabled) {
  if (!pushSupported() || !enabled || permission() !== "granted") return false;
  try { await subscribe(driverName); return true; } catch (_) { return false; }
}

export async function disablePush() {
  try {
    if (pushSupported()) {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
    }
  } catch (_) { /* ignore */ }
  await axios.put(`${API}/driver/push-settings`, { enabled: false });
}
