import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { assertUserDataDir, userDataDir } from "./compat-paths";
import { setupLogging } from "./logging";
import { isDevMode, startSidecar, killSidecar } from "./sidecar";
import { createSplash, showSplashError } from "./splash";
import { registerIpc } from "./ipc";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── DATA-01: lock del data dir ANTES de cualquier acceso a paths ──
// Orden crítico: sin esto Electron usaría %APPDATA%\Nyanko (productName) y la
// biblioteca de prod existente quedaría huérfana.
app.setPath("userData", userDataDir(app.getPath("appData")));
assertUserDataDir(app.getPath("userData"));

// OBS-01: logging temprano (justo tras el lock, antes de whenReady) para que
// main.log capture el arranque completo.
setupLogging();

// Resuelve en ready-to-show para que el gate cierre el splash solo cuando la
// ventana principal ya tiene contenido (D-02: nada de "Cargando biblioteca").
function createWindow(): Promise<BrowserWindow> {
  const win = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    frame: false,
    show: false,
    webPreferences: {
      preload: join(__dirname, "../preload/index.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  const shown = new Promise<BrowserWindow>((resolve) => {
    win.once("ready-to-show", () => {
      win.show();
      resolve(win);
    });
  });

  // Dual-path estándar de electron-vite: dev sirve desde el vite server, prod
  // carga el index.html construido.
  const devUrl = process.env["ELECTRON_RENDERER_URL"];
  if (devUrl) {
    void win.loadURL(devUrl);
  } else {
    void win.loadFile(join(__dirname, "../renderer/index.html"));
  }
  return shown;
}

let splashWin: BrowserWindow | null = null;

// D-01/D-02/D-06/D-10: gate de arranque orquestado. Reejecutable vía Retry del
// splash (onRetry = runStartup), por eso reutiliza un splash vivo en vez de
// duplicarlo.
async function runStartup(): Promise<void> {
  if (!splashWin || splashWin.isDestroyed()) {
    splashWin = createSplash();
  } else {
    // Retry desde estado de error → volver a "loading".
    splashWin.webContents
      .executeJavaScript('document.body.removeAttribute("data-state")')
      .catch(() => {});
  }

  try {
    // D-10: en dev se omite el sidecar (backend Python a mano). PERO
    // NYANKO_SIDECAR_EXE es el hook explícito para probar el camino de PROD antes
    // de empaquetar (Fase 5): `electron-vite preview` corre SIN empaquetar, así que
    // app.isPackaged es false ahí — el override fuerza el spawn para verificar el gate.
    const forceSidecar = Boolean(process.env.NYANKO_SIDECAR_EXE);
    if (isDevMode(app.isPackaged) && !forceSidecar) {
      // dev: la app usa el backend Python arrancado a mano.
    } else {
      // D-01: prod → spawn + espera de readiness ANTES de abrir la ventana.
      // dataDir ABSOLUTO = el mismo userData lockeado arriba (config.py ancla un
      // NYANKO_DATA_DIR relativo a apps/backend → bug de las 6 DBs divergentes).
      await startSidecar({ dataDir: userDataDir(app.getPath("appData")) });
    }
    await createWindow();
    if (splashWin && !splashWin.isDestroyed()) splashWin.close();
    splashWin = null;
  } catch {
    // D-06: fallo del sidecar → panel de error del splash (Reintentar/Abrir logs/Salir).
    if (splashWin && !splashWin.isDestroyed()) showSplashError(splashWin);
  }
}

app.whenReady().then(() => {
  // registerIpc UNA sola vez: ipcMain.handle rechaza handlers duplicados, y el
  // Retry re-corre el gate sin re-registrar.
  registerIpc({ onRetry: () => void runStartup() });
  void runStartup();
});

// D-08: matar el sidecar en cada salida antes de cerrar. Se difiere el quit hasta
// que killSidecar (graceful → taskkill /T /F del árbol) termine — si no, el loop
// muere antes del taskkill y queda un nyanko-api.exe huérfano. El updater de
// Phase 5 llama esta MISMA killSidecar antes de quitAndInstall.
let quitting = false;
app.on("before-quit", (e) => {
  if (quitting) return;
  e.preventDefault();
  quitting = true;
  void killSidecar().finally(() => app.quit());
});

app.on("window-all-closed", () => {
  // Windows es el target primario: salir al cerrar todas las ventanas.
  app.quit();
});
