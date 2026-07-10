import { join } from "node:path";

// Fuente única de verdad de rutas heredadas. ELECTRON-FREE a propósito: el
// self-check DATA-01 (Plan 02) lo ejecuta bajo Node plano, sin mock de electron.

// Identifier Tauri original. userData DEBE quedar aquí o la biblioteca de prod
// existente queda huérfana (%APPDATA%\Nyanko por productName sería otro dir).
export const LEGACY_APP_ID = "app.nyanko.desktop";

// %APPDATA%\app.nyanko.desktop — solo depende de node:path.
export function userDataDir(appDataPath: string): string {
  return join(appDataPath, LEGACY_APP_ID);
}

// Crash-guard de arranque: revienta si userData no cayó en el id heredado.
export function assertUserDataDir(resolved: string): void {
  if (!resolved.endsWith(LEGACY_APP_ID)) {
    throw new Error(
      `userData resolvió a "${resolved}", se esperaba que terminara en "${LEGACY_APP_ID}". ` +
        `Fijar app.setPath('userData', ...) ANTES de cualquier acceso a paths.`,
    );
  }
}
