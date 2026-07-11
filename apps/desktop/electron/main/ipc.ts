import { app, ipcMain, shell, dialog, Notification, BrowserWindow } from "electron";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openLogsFolder } from "./logging";
import { currentWindowPrefs, updateWindowPrefs } from "./window-prefs";

// Whitelist dura: el renderer solo puede leer estos ficheros del userData, nunca
// una ruta arbitraria (path traversal). El sidecar escribe ambos en NYANKO_DATA_DIR
// = userData.
const READABLE_APPDATA_FILES = new Set(["port", "instance_token"]);

// Primer ipcMain.handle del repo — establece el patrón que Fase 3 (native.ts)
// reutiliza. Registrar finos handlers de control que consume el preload/splash.
export function registerIpc({ onRetry }: { onRetry: () => void }): void {
  // D-11 / T-02-IPC: SIN argumento del renderer. Abre SIEMPRE app.getPath('logs')
  // (openLogsFolder ignora cualquier payload); un path atacante-controlado nunca
  // llega a shell.openPath.
  ipcMain.handle("openLogsFolder", () => openLogsFolder());
  // Splash Retry: re-corre el gate de arranque (control-only).
  ipcMain.handle("startup:retry", () => onRetry());
  // Splash Exit: control-only, sin payload.
  ipcMain.on("startup:quit", () => app.quit());
  // Analog Electron del readAppDataFile de Tauri: api.ts (renderer) lee port /
  // instance_token del userData para resolver la URL del sidecar (puerto dinámico)
  // y el token de instancia. Whitelist dura → sin path traversal. La frontera
  // nativa completa (native.ts) llega en Fase 3; esto es la porción mínima que
  // el criterio 1 (biblioteca carga en frío) necesita.
  ipcMain.handle("readAppDataFile", (_event, name: unknown) => {
    if (typeof name !== "string" || !READABLE_APPDATA_FILES.has(name)) return null;
    try {
      return readFileSync(join(app.getPath("userData"), name), "utf-8").trim();
    } catch {
      return null;
    }
  });

  // ── Frontera nativa cableada (Fase 3) ──
  // T-03-02 (high): openExternal SOLO acepta http/https. Sin file:, sin protocol
  // handlers custom, sin lanzar ejecutables desde un renderer comprometido.
  ipcMain.handle("openExternal", (_e, url: unknown) => {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url)) return;
    return shell.openExternal(url);
  });
  // T-03-02 (medium): openPath/revealItemInDir abren SOLO rutas locales de la
  // biblioteca; se rechaza cualquier string con esquema URL (://).
  ipcMain.handle("openPath", (_e, p: unknown) => {
    if (typeof p !== "string" || p.includes("://")) return "";
    return shell.openPath(p);
  });
  ipcMain.handle("revealItemInDir", (_e, p: unknown) => {
    if (typeof p !== "string" || p.includes("://")) return;
    shell.showItemInFolder(p);
  });
  // Diálogo de carpeta (asociar biblioteca). Devuelve la ruta o null si se cancela.
  ipcMain.handle("openFolderDialog", async () => {
    const w = BrowserWindow.getFocusedWindow();
    const r = await dialog.showOpenDialog(w!, { properties: ["openDirectory"] });
    return r.canceled || !r.filePaths[0] ? null : r.filePaths[0];
  });
  // Versión real de la app (antes era placeholder "" en prod desde el preload).
  ipcMain.handle("appVersion", () => app.getVersion());
  // Notificación nativa. Título/cuerpo son strings i18n de la propia app
  // (T-03-04: spoofing negligible, aceptado); se castea por si acaso.
  ipcMain.handle("notify", (_e, title: unknown, body: unknown) => {
    new Notification({ title: String(title), body: String(body) }).show();
  });

  // ── Controles de ventana frameless (NATIVE-04) ──
  // T-04-01 (EoP): cada handler opera SOLO sobre la ventana del emisor
  // (BrowserWindow.fromWebContents(event.sender)) — un renderer nunca controla
  // otra ventana por id, y no se acepta payload alguno.
  ipcMain.handle("window:minimize", (e) => {
    BrowserWindow.fromWebContents(e.sender)?.minimize();
  });
  ipcMain.handle("window:toggle-maximize", (e) => {
    const w = BrowserWindow.fromWebContents(e.sender);
    if (w) w.isMaximized() ? w.unmaximize() : w.maximize();
  });
  ipcMain.handle("window:close", (e) => {
    BrowserWindow.fromWebContents(e.sender)?.close();
  });

  // ── Preferencias de ventana (NATIVE-04 / D-05) ──
  // get devuelve la caché sembrada en el arranque; set persiste el payload
  // COACCIONADO (T-04-05) al data dir de la app (T-04-04) — el renderer nunca
  // aporta ni la ruta ni claves arbitrarias.
  ipcMain.handle("window-prefs:get", () => currentWindowPrefs());
  ipcMain.handle("window-prefs:set", (_e, prefs: unknown) => updateWindowPrefs(prefs));
}
