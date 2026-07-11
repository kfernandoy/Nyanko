import { contextBridge, ipcRenderer } from "electron";

// Preload seguro mínimo (sandbox:true → solo contextBridge + ipcRenderer disponibles).
// Namespace nyanko: la frontera nativa completa (Fase 3) — cada método es un canal
// IPC específico y tipado. NUNCA se expone ipcRenderer crudo ni un invoke genérico
// (T-03-03): una superficie amplia sería EoP desde el renderer web.
// IMPORTANTE: no definir __TAURI_INTERNALS__ — el renderer degrada solo cuando falta.
contextBridge.exposeInMainWorld("nyanko", {
  // Arranque/logs (Fase 2).
  openLogsFolder: () => ipcRenderer.invoke("openLogsFolder"),
  retryStartup: () => ipcRenderer.invoke("startup:retry"),
  quit: () => ipcRenderer.send("startup:quit"),
  readAppDataFile: (name: string) => ipcRenderer.invoke("readAppDataFile", name),
  // Frontera nativa cableada (Fase 3). appVersion pasa de placeholder ("" en prod)
  // a invoke → app.getVersion() en el main.
  appVersion: () => ipcRenderer.invoke("appVersion"),
  openExternal: (url: string) => ipcRenderer.invoke("openExternal", url),
  openPath: (path: string) => ipcRenderer.invoke("openPath", path),
  revealItemInDir: (path: string) => ipcRenderer.invoke("revealItemInDir", path),
  openFolderDialog: () => ipcRenderer.invoke("openFolderDialog"),
  notify: (title: string, body: string) => ipcRenderer.invoke("notify", title, body),
  // Controles de ventana frameless (NATIVE-04): canales nombrados y tipados,
  // nunca ipcRenderer crudo (T-04-02). Actúan solo sobre la ventana del emisor.
  minimizeWindow: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximizeWindow: () => ipcRenderer.invoke("window:toggle-maximize"),
  closeWindow: () => ipcRenderer.invoke("window:close"),
  // Suscripción a "detección pausada"; el emisor (tray/window) llega en Fase 4.
  // Devuelve un unsubscribe para no fugar listeners al desmontar.
  onDetectionPaused: (cb: (paused: boolean) => void) => {
    const h = (_e: unknown, paused: boolean) => cb(paused);
    ipcRenderer.on("detection-paused", h);
    return () => ipcRenderer.removeListener("detection-paused", h);
  },
});
