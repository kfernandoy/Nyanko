import { app, ipcMain } from "electron";
import { openLogsFolder } from "./logging";

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
}
