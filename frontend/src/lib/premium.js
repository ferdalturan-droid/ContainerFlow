import axios from "axios";

/**
 * 2026-10-20: Pakken (basic/premium + moduler) kan ændres af super admin mens
 * en side står åben. Siderne henter derfor profilen igen jævnligt (se
 * subscribePremiumRefresh), og hvis serveren alligevel afviser noget som premium,
 * opdateres siden med det samme, så funktionen forsvinder i stedet for at
 * blive ved med at give fejl.
 */
export const PREMIUM_EVENT = "cf:premium-changed";
let installed = false;

export function installPremiumInterceptor() {
  if (installed) return;
  installed = true;
  axios.interceptors.response.use(undefined, (error) => {
    const d = error?.response?.data;
    if (error?.response?.status === 403 && d && typeof d === "object" && d.premium_required) {
      // Skærmen viser selv serverens besked ("... er en del af ContainerFlow
      // Premium") - her opdateres kun siden, så funktionen forsvinder.
      window.dispatchEvent(new Event(PREMIUM_EVENT));
      error.premiumHandled = true;
    }
    return Promise.reject(error);
  });
}

/** Kald `refetch` hvert 30. sekund, når appen kommer i forgrunden, og straks
 *  når serveren har afvist noget som premium. */
export function subscribePremiumRefresh(refetch) {
  const onVis = () => { if (!document.hidden) refetch(); };
  const iv = setInterval(onVis, 30000);
  window.addEventListener(PREMIUM_EVENT, refetch);
  window.addEventListener("focus", onVis);
  document.addEventListener("visibilitychange", onVis);
  return () => {
    clearInterval(iv);
    window.removeEventListener(PREMIUM_EVENT, refetch);
    window.removeEventListener("focus", onVis);
    document.removeEventListener("visibilitychange", onVis);
  };
}
