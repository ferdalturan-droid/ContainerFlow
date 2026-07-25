import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import axios from "axios";
import { authApi, getAuthToken, setAuthToken, API } from "./api";

const AuthContext = createContext(null);

const ACTING_KEY = "containerflow_acting_company_id";
const ACTING_HEADER = "X-Acting-Company-Id";

function applyActingHeader(value) {
  if (value) {
    axios.defaults.headers.common[ACTING_HEADER] = value;
  } else {
    delete axios.defaults.headers.common[ACTING_HEADER];
  }
}

// Apply persisted acting-company header on first import (page reload)
try {
  const persisted = localStorage.getItem(ACTING_KEY);
  if (persisted) applyActingHeader(persisted);
} catch (_) { /* ignore */ }

export function AuthProvider({ children }) {
  // user: null = unauthenticated, undefined = still checking, object = logged in
  const [user, setUser] = useState(undefined);
  const [actingCompanyId, _setActingCompanyId] = useState(() => {
    try { return localStorage.getItem(ACTING_KEY) || ""; } catch (_) { return ""; }
  });

  const setActingCompanyId = useCallback((cid) => {
    const next = cid || "";
    try {
      if (next) localStorage.setItem(ACTING_KEY, next);
      else localStorage.removeItem(ACTING_KEY);
    } catch (_) { /* ignore */ }
    applyActingHeader(next);
    _setActingCompanyId(next);
  }, []);

  // Load user on mount if token exists
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      return;
    }
    authApi
      .me()
      .then((u) => setUser(u))
      .catch(() => {
        setAuthToken(null);
        setUser(null);
      });
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await authApi.login(email, password);
    setAuthToken(data.token);
    setUser(data.user);
    // Clear any stale acting-company on fresh login
    applyActingHeader("");
    _setActingCompanyId("");
    try { localStorage.removeItem(ACTING_KEY); } catch (_) { /* ignore */ }
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setAuthToken(null);
    setUser(null);
    applyActingHeader("");
    _setActingCompanyId("");
    // Clear other legacy state so the old driver setup re-appears for an unauthenticated visitor
    try {
      localStorage.removeItem("korkman2_driver_name");
      localStorage.removeItem("korkman2_vehicle_reg");
      localStorage.removeItem("korkman2_session");
      localStorage.removeItem(ACTING_KEY);
    } catch (_) { /* ignore */ }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const u = await authApi.me();
      setUser(u);
      return u;
    } catch (_) {
      setUser(null);
      return null;
    }
  }, []);

  // Fase 15.40b (2026-02-22): Dynamisk feature-flag-opdatering. Når super-
  // admin toggler en feature, skal det slå igennem på brugerens UI uden
  // logout. Vi polller /clients/me/features hvert 30. sekund + når browser-
  // fanen får fokus igen (tab switch / vinduet kommer i fokus). Det er nok
  // til at give "near real-time"-følelse uden websocket-kompleksitet.
  const reloadFeaturesOnly = useCallback(async () => {
    try {
      const token = getAuthToken();
      if (!token) return;
      const { data } = await axios.get(`${API}/clients/me/features`);
      const nextFeatures = (data && data.features) || {};
      setUser((u) => {
        if (!u) return u;
        // Skip update hvis features er identiske (undgår unødvendige re-renders).
        const cur = u.features || {};
        const keys = new Set([...Object.keys(cur), ...Object.keys(nextFeatures)]);
        let changed = false;
        for (const k of keys) {
          if (Boolean(cur[k]) !== Boolean(nextFeatures[k])) { changed = true; break; }
        }
        if (!changed) return u;
        return { ...u, features: nextFeatures };
      });
    } catch (_) { /* ignore - næste poll prøver igen */ }
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    // Kør én gang med det samme efter user-load, så vi får friske features
    // umiddelbart efter login (dækker over evt. ændringer mens brugeren var
    // logget ud). Derefter hver 30. sekund.
    reloadFeaturesOnly();
    const iv = setInterval(reloadFeaturesOnly, 30_000);
    // Når fanen kommer i fokus igen, refresh straks (typisk efter tab-switch).
    const onFocus = () => { reloadFeaturesOnly(); };
    const onVisibility = () => { if (document.visibilityState === "visible") reloadFeaturesOnly(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(iv);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, reloadFeaturesOnly]);

  const value = {
    user, login, logout, refresh, setUser,
    actingCompanyId, setActingCompanyId,
    // Fase 15.40 (2026-02-22): Central feature-flag-helper. Læser features
    // fra det cachede user-objekt (sat ved login + /auth/me + polling).
    isFeatureEnabled: (key) => Boolean(user && user.features && user.features[key]),
    features: (user && user.features) || {},
    // Eksposeret så fx super-admin's egen toggle-fane kan force-refresh sit
    // eget cached state med det samme (uden at vente på næste poll).
    reloadFeatures: reloadFeaturesOnly,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// Fase 15.40 (2026-02-22): Tynd convenience-hook der bare returnerer
// isFeatureEnabled-funktionen. Brug overalt hvor du vil gate UI:
//   const isEnabled = useFeatureFlag();
//   if (!isEnabled('estimate')) return null;
export function useFeatureFlag() {
  return useAuth().isFeatureEnabled;
}
