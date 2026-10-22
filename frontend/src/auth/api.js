import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "korkman2_auth_token";

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    localStorage.removeItem(TOKEN_KEY);
    delete axios.defaults.headers.common["Authorization"];
  }
}

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

// Apply token on module load (page refresh)
const _existing = getAuthToken();
if (_existing) {
  axios.defaults.headers.common["Authorization"] = `Bearer ${_existing}`;
}

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Noget gik galt";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  if (detail && typeof detail.message === "string") return detail.message;
  return String(detail);
}

const OFFLINE_MSG = "Ingen forbindelse til serveren. Prøv igen om lidt.";

export const authApi = {
  async login(email, password) {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });
    // 2026-10-22: Et svar uden bruger/token (fx fra en gammel offline-hjælper
    // når serveren ikke svarer) er ikke et login.
    if (!data || !data.token || !data.user) throw new Error(OFFLINE_MSG);
    return data;
  },
  async me() {
    const { data } = await axios.get(`${API}/auth/me`);
    if (!data || !data.id || !data.role) throw new Error(OFFLINE_MSG);
    return data;
  },
  async logout() {
    try {
      await axios.post(`${API}/auth/logout`);
    } catch (_) { /* ignore */ }
  },
  async changePassword(oldPassword, newPassword) {
    const { data } = await axios.post(`${API}/auth/change-password`, {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return data;
  },
};
