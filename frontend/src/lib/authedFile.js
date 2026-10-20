// 2026-10-20: Filer fra API'et (vejesedler, dagrapport-PDF'er) kræver login
// (siden 2026-10-18). Et <img src>, et link eller window.open sender ikke
// login-headeren med - så hentes filen med axios og vises som blob-URL.
import { useEffect, useState } from "react";
import axios from "axios";

export async function fetchBlobUrl(url) {
  const r = await axios.get(url, { responseType: "blob" });
  return URL.createObjectURL(r.data);
}

/** Åbn i ny fane. Fanen åbnes straks (ellers stopper pop-up-blokeringen den). */
export async function openAuthed(url, filename = "") {
  const w = window.open("", "_blank");
  try {
    const obj = await fetchBlobUrl(url);
    if (w) {
      w.location.href = obj;
    } else {
      const a = document.createElement("a");
      a.href = obj; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(obj), 60000);
  } catch (e) {
    if (w) w.close();
    throw e;
  }
}

export async function downloadAuthed(url, filename) {
  const obj = await fetchBlobUrl(url);
  const a = document.createElement("a");
  a.href = obj; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(obj), 5000);
}

/** Billede fra API'et til et <img>. data:-URL'er bruges som de er.
 *  Giver "" mens det hentes og "error" hvis det ikke kunne hentes. */
export function useAuthedImage(src) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!src || String(src).startsWith("data:") || String(src).startsWith("blob:")) { setUrl(src || ""); return undefined; }
    let alive = true;
    let obj = "";
    setUrl("");
    fetchBlobUrl(src)
      .then((u) => { obj = u; if (alive) setUrl(u); else URL.revokeObjectURL(u); })
      .catch(() => { if (alive) setUrl("error"); });
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj); };
  }, [src]);
  return url;
}

export function AuthedImg({ src, alt = "", ...rest }) {
  const url = useAuthedImage(src);
  if (!url || url === "error") return null;
  return <img src={url} alt={alt} {...rest} />;
}
