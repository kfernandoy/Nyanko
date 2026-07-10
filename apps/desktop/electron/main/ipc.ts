import { app, ipcMain } from "electron";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openLogsFolder } from "./logging";

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
}
