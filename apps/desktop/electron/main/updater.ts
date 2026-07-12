import { app } from "electron";
import log from "electron-log/main";
import electronUpdater from "electron-updater";
import { isDevMode, killSidecar } from "./sidecar";

// PKG-02: auto-update desde GitHub Releases (electron-updater). Wrapper fino sin
// lógica pura — no hay nada que testear bajo Node plano, así que no lleva
// .test.ts hermano (mismo caso que tray.ts).
// ponytail: sin capa pura inventada solo para cumplir la convención del split.

// electron-updater es CJS: el named export no sobrevive al interop de ESM.
const { autoUpdater } = electronUpdater;

// La confirmación del usuario va ANTES de bajar ~130 MB (paridad 0.1.15: el
// check() de Tauri no descargaba nada).
autoUpdater.autoDownload = false;
// Nada de instalar al salir sin que el usuario haya dicho que sí.
autoUpdater.autoInstallOnAppQuit = false;
// OBS-01: los fallos del updater aterrizan en main.log (el mismo logger que
// configura logging.ts) o son invisibles.
autoUpdater.logger = log;

// T-05-04: el feed NO se configura aquí. Sale de `app-update.yml`, que
// electron-builder mete dentro del paquete a partir del bloque `publish:` del
// electron-builder.yml (Plan 01). Ni el renderer ni este módulo pueden apuntar el
// updater a otro origen, y el SHA512 de latest.yml lo verifica electron-updater
// de oficio.

// T-05-05: guarda de instalación. El renderer no puede disparar una instalación
// sin que un check previo haya encontrado update de verdad.
let updateAvailable = false;

// Sin paquete no existe app-update.yml y electron-updater revienta con un error
// opaco. isDevMode es el MISMO discriminador que usa el sidecar — no se inventa otro.
function assertPackaged(): void {
  if (isDevMode(app.isPackaged)) {
    throw new Error("Las actualizaciones solo funcionan en la app instalada (no en desarrollo).");
  }
}

// Consulta el feed. Devuelve la versión disponible, o null si ya estamos al día.
export async function checkForUpdate(): Promise<{ version: string } | null> {
  assertPackaged();
  const result = await autoUpdater.checkForUpdates();
  updateAvailable = result?.isUpdateAvailable === true;
  if (!result || !updateAvailable) return null;
  return { version: result.updateInfo.version };
}

// Descarga, mata el sidecar e instala. Solo tras un checkForUpdate() positivo.
export async function downloadAndInstallUpdate(): Promise<void> {
  assertPackaged();
  if (!updateAvailable) {
    throw new Error("No hay ninguna actualización confirmada por un check previo.");
  }
  await autoUpdater.downloadUpdate();
  // D-05: el sidecar mantiene bloqueados _internal\* y su propio exe; si sobrevive
  // a la instalación, el copiado falla. Se reusa la MISMA killSidecar del
  // before-quit (es idempotente, así que su segunda llamada es un no-op).
  await killSidecar();
  // D-04: isSilent = update sin wizard (aunque la primera instalación sea asistida);
  // isForceRunAfter = relanzar, paridad con el relaunch() de 0.1.15.
  autoUpdater.quitAndInstall(true, true);
}
