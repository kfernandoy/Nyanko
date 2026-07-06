import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppSettingsProvider } from "./i18n";
import { installTooltips } from "./tooltip";
import "./styles.css";

installTooltips();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppSettingsProvider>
      <App />
    </AppSettingsProvider>
  </StrictMode>,
);
