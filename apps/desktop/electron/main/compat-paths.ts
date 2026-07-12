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

// PKG-01: icono de marca ÚNICO (D-07: 256x256, sin monocromo dedicado) que comparten
// la ventana principal y la bandeja. `build/` es el buildResources de electron-builder
// y NO viaja dentro de la app: en el NSIS la única copia es resources/icon.png
// (extraResources, Plan 01). Misma forma que resolveSidecarExe() (sidecar.ts), con la
// única desviación de que el icono se necesita en AMBOS caminos — de ahí la rama.
// isPackaged/resourcesPath entran como PARÁMETROS: este módulo es Electron-free por
// contrato (su self-check corre bajo Node plano, sin mock de electron).
export function iconPath(isPackaged: boolean, resourcesPath: string, mainDir: string): string {
  if (isPackaged) return join(resourcesPath, "icon.png");
  return join(mainDir, "..", "..", "build", "icon.png"); // dev: out/main → apps/desktop
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
