import React, { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Truck, LogIn, Mail, Lock, ShieldCheck, Loader2, ArrowLeft, CheckCircle2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { API, formatApiError } from "../auth/api";

/** Login page now also handles "Glemt adgangskode" inline so brugeren ikke skal
 *  navigere til en separat URL. Stages:
 *    "login"  -> default form
 *    "forgot" -> indtast email, modtag mail med 72-timers link
 *    "sent"   -> bekræftelse-skærm
 */
export default function LoginPage() {
  const { login } = useAuth();
  const [stage, setStage] = useState("login"); // "login" | "forgot" | "sent"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submitLogin = async (e) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !password) {
      setError("Email og adgangskode er påkrævet");
      return;
    }
    setError(""); setLoading(true);
    try {
      const user = await login(cleanEmail, password);
      toast.success(`Velkommen, ${user.name}!`);
    } catch (err) {
      const status = err?.response?.status;
      const msg = err?.response?.data?.detail || formatApiError(err);
      if (status === 429) { setError("⚠️ " + msg); toast.error("For mange forsøg - " + msg); }
      else { setError(msg); toast.error(msg); }
    } finally { setLoading(false); }
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail) { setError("Indtast din email"); return; }
    setError(""); setLoading(true);
    try {
      await axios.post(`${API}/auth/forgot-password`, { email: cleanEmail });
      setStage("sent");
    } catch (err) {
      // Server svarer altid 200 medmindre der er rate-limit/validation, men vis alligevel besked
      const msg = err?.response?.data?.detail || formatApiError(err);
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="relative min-h-[100dvh] bg-slate-900 flex items-center justify-center p-4 overflow-hidden" data-testid="login-page">

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
            {stage === "login" && "Log ind på din konto"}
            {stage === "forgot" && "Glemt adgangskode"}
            {stage === "sent" && "Tjek din indbakke"}
          </p>
        </div>

        {stage === "sent" ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 space-y-5 border border-slate-200 dark:border-slate-700 text-center" data-testid="forgot-sent-card">
            <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
            <h1 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
              Mail sendt
            </h1>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              Hvis <span className="font-semibold">{email}</span> findes i ContainerFlow, har vi sendt et link til at vælge ny adgangskode.
              Linket er gyldigt i 72 timer.
            </p>
            <button onClick={() => { setStage("login"); setError(""); setPassword(""); }}
              className="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-base inline-flex items-center justify-center gap-2"
              data-testid="forgot-back-btn">
              <ArrowLeft className="w-4 h-4" /> Tilbage til login
            </button>
          </div>
        ) : (
          <form
            onSubmit={stage === "forgot" ? submitForgot : submitLogin}
            className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 space-y-5 border border-slate-200 dark:border-slate-700"
            data-testid={stage === "forgot" ? "forgot-form" : "login-form"}
          >
            <div className="flex items-center justify-center gap-2 pb-2">
              <ShieldCheck className="w-6 h-6 text-orange-500" />
              <h1 className="font-heading font-bold text-xl text-slate-900 dark:text-white">
                {stage === "forgot" ? "Nulstil adgangskode" : "Login"}
              </h1>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="din@email.dk"
                  autoComplete="email"
                  autoFocus
                  disabled={loading}
                  className="w-full pl-10 pr-4 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-xl text-base focus:border-orange-500 focus:ring-0 outline-none disabled:opacity-50"
                  data-testid="login-email-input"
                />
              </div>
            </div>

            {stage === "login" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">Adgangskode</label>
                  <button
                    type="button"
                    onClick={() => { setStage("forgot"); setError(""); setPassword(""); }}
                    className="text-xs font-semibold text-orange-600 hover:text-orange-700 dark:text-orange-400 dark:hover:text-orange-300"
                    data-testid="forgot-password-link"
                  >
                    Glemt adgangskode?
                  </button>
                </div>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Indtast adgangskode"
                    autoComplete="current-password"
                    disabled={loading}
                    className="w-full pl-10 pr-4 py-3 border-2 border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-white rounded-xl text-base focus:border-orange-500 focus:ring-0 outline-none disabled:opacity-50"
                    data-testid="login-password-input"
                  />
                </div>
              </div>
            )}

            {error && (
              <div
                className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 px-4 py-2.5 rounded-lg text-sm"
                data-testid="login-error"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-base inline-flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-orange-500/20"
              data-testid={stage === "forgot" ? "forgot-submit-btn" : "login-submit-btn"}
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> {stage === "forgot" ? "Sender..." : "Logger ind..."}</>
              ) : stage === "forgot" ? (
                <><Mail className="w-4 h-4" /> Send nulstillingslink</>
              ) : (
                <><LogIn className="w-4 h-4" /> Log ind</>
              )}
            </button>

            {stage === "forgot" && (
              <button
                type="button"
                onClick={() => { setStage("login"); setError(""); }}
                className="w-full text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 inline-flex items-center justify-center gap-1.5"
                data-testid="forgot-cancel-btn"
              >
                <ArrowLeft className="w-3 h-3" /> Tilbage til login
              </button>
            )}
          </form>
        )}

        <div className="mt-6 text-center text-xs text-slate-500">
          ContainerFlow Multi-tenant Platform
        </div>
      </div>
    </div>
  );
}
