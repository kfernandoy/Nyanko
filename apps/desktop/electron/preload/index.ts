import { contextBridge, ipcRenderer } from "electron";

// Preload seguro mínimo (sandbox:true → solo contextBridge + ipcRenderer disponibles).
// Namespace nyanko: appVersion (placeholder) + acciones de logs/arranque (Fase 2).
// El bridge nativo completo llega en Fase 3. Nunca se expone ipcRenderer/Node crudo.
// IMPORTANTE: no definir __TAURI_INTERNALS__ — el renderer degrada solo cuando falta.
contextBridge.exposeInMainWorld("nyanko", {
  appVersion: process.env.npm_package_version ?? "",
  openLogsFolder: () => ipcRenderer.invoke("openLogsFolder"),
  retryStartup: () => ipcRenderer.invoke("startup:retry"),
  quit: () => ipcRenderer.send("startup:quit"),
});
