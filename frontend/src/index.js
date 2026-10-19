import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { Toaster } from "sonner";
import { AuthProvider } from "@/auth/AuthContext";
import UpdateBanner from "@/components/UpdateBanner";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <AuthProvider>
      <App />
      {/* Single global Toaster - having multiple <Toaster /> in different
          branches of App.js caused intermittent React `insertBefore` DOM errors
          because each Sonner portal mounts/unmounts when routes swap.
          Pr. 2026-06-15: ONE Toaster på root-niveau. */}
      <Toaster position="top-right" richColors />
      <UpdateBanner />
    </AuthProvider>
  </React.StrictMode>,
);
