import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Truck, ShieldCheck, Lock, Loader2, CheckCircle2, AlertTriangle, ArrowRight,
} from "lucide-react";
import { API, formatApiError } from "../auth/api";

/**
 * Generisk "vælg ny adgangskode"-side, der bruges af både:
 *   - /set-password?token=...   (accept-invitation)
 *   - /reset-password?token=... (password reset)
 *
 * Modet kontrolleres af `mode`-prop (default: deduceres fra path).
 * Når adgangskoden er sat, viser vi en bekræftelse og linker tilbage til login.
 */
export default function SetPasswordPage({ mode }) {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  const effectiveMode = mode || (window.location.pathname.startsWith("/reset-password") ? "reset" : "invitation");

  const [verifying, setVerifying] = useState(true);
  const [meta, setMeta] = useState(null);    // {email, name, role, company_name}
  const [verifyError, setVerifyError] = useState("");
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) { setVerifying(false); setVerifyError("Token mangler i linket"); return; }
    (async () => {
      try {
        const { data } = await axios.get(`${API}/auth/verify-token`, { params: { token, type: effectiveMode } });
        setMeta(data);
      } catch (err) {
        setVerifyError(err?.response?.data?.detail || formatApiError(err));
      } finally {
        setVerifying(false);
      }
    })();
  }, [token, effectiveMode]);

  const submit = async (e) => {
    e.preventDefault();
    if (!password1 || password1.length < 6) {
      toast.error("Adgangskoden skal være mindst 6 tegn");
      return;
    }
    if (password1 !== password2) {
      toast.error("De to adgangskoder er ikke ens");
      return;
    }
    setSubmitting(true);
    try {
      const endpoint = effectiveMode === "reset" ? "reset-password" : "accept-invitation";
      await axios.post(`${API}/auth/${endpoint}`, { token, new_password: password1 });
      setDone(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || formatApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-[100dvh] bg-slate-900 flex items-center justify-center p-4 overflow-hidden" data-testid="set-password-page">
      <div className="pointer-events-none absolute inset-0 opacity-30">
        <div className="absolute top-1/4 -left-32 w-96 h-96 rounded-full bg-orange-500/20 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 w-96 h-96 rounded-full bg-blue-600/20 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 bg-slate-900 text-white px-6 py-3 rounded-xl shadow-lg mb-4 border border-slate-700">
            <Truck className="w-8 h-8 text-orange-500" />
            <span className="font-heading font-black text-2xl">
              Container<span className="text-orange-500">Flow</span>
            </span>
          </div>
          <p className="text-sm text-slate-400">
            {effectiveMode === "reset" ? "Vælg en ny adgangskode" : "Aktivér din konto"}
          </p>
        </div>

        {verifying ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 text-center border border-slate-200 dark:border-slate-700">
            <Loader2 className="w-7 h-7 animate-spin text-orange-500 mx-auto" />
            <p className="text-sm text-slate-500 mt-3">Verificerer link...</p>
          </div>
        ) : verifyError ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 text-center border border-slate-200 dark:border-slate-700 space-y-4" data-testid="token-error-card">
            <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto" />
            <h1 className="font-heading font-bold text-lg text-slate-900 dark:text-white">Linket virker ikke</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">{verifyError}</p>
            <p className="text-xs text-slate-500">Bed din administrator om at gensende invitationen, eller anmod om et nyt nulstillingslink fra login-siden.</p>
            <a href="/" className="inline-flex items-center justify-center gap-2 w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-base">
              Tilbage til login
            </a>
          </div>
        ) : done ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 text-center border border-slate-200 dark:border-slate-700 space-y-4" data-testid="set-password-success">
            <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
            <h1 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
              {effectiveMode === "reset" ? "Adgangskode opdateret" : "Konto aktiveret"}
            </h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Du kan nu logge ind med din nye adgangskode.
            </p>
            <a href="/" className="inline-flex items-center justify-center gap-2 w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-base">
              Gå til login <ArrowRight className="w-4 h-4" />
            </a>
          </div>
        ) : (
          <form onSubmit={submit} className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 space-y-5 border border-slate-200 dark:border-slate-700" data-testid="set-password-form">
            <div className="flex items-center justify-center gap-2 pb-2">
              <ShieldCheck className="w-6 h-6 text-orange-500" />
              <h1 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
                {effectiveMode === "reset" ? "Vælg ny adgangskode" : "Aktivér din konto"}
              </h1>
            </div>

            {meta && (
              <div className="bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm space-y-1">
                <p className="text-slate-500 text-xs uppercase tracking-wide">{meta.company_name || "ContainerFlow"}</p>
                <p className="font-semibold text-slate-900 dark:text-white" data-testid="set-password-meta-email">{meta.email}</p>
                {meta.name && <p className="text-xs text-slate-500">{meta.name}</p>}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">Ny adgangskode (mindst 6 tegn)</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="password"
                  value={password1}
                  onChange={(e) => setPassword1(e.target.value)}
                  autoFocus
                  minLength={6}
                  disabled={submitting}
                  className="w-full pl-10 pr-4 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-xl text-base focus:border-orange-500 focus:ring-0 outline-none disabled:opacity-50"
                  data-testid="set-password-input-1"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">Gentag adgangskode</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="password"
                  value={password2}
                  onChange={(e) => setPassword2(e.target.value)}
                  minLength={6}
                  disabled={submitting}
                  className="w-full pl-10 pr-4 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-xl text-base focus:border-orange-500 focus:ring-0 outline-none disabled:opacity-50"
                  data-testid="set-password-input-2"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-base inline-flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="set-password-submit-btn"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Gemmer...</> : <>Gem adgangskode</>}
            </button>
          </form>
        )}

        <div className="mt-6 text-center text-xs text-slate-500">
          ContainerFlow Multi-tenant Platform
        </div>
      </div>
    </div>
  );
}
