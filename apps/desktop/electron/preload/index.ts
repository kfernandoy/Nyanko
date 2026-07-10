import { contextBridge } from "electron";

// Preload seguro mínimo (sandbox:true → solo contextBridge + ipcRenderer disponibles).
// Namespace placeholder; el bridge nativo completo llega en Fase 3.
// IMPORTANTE: no definir __TAURI_INTERNALS__ — el renderer degrada solo cuando falta.
contextBridge.exposeInMainWorld("nyanko", {
  appVersion: process.env.npm_package_version ?? "",
});
